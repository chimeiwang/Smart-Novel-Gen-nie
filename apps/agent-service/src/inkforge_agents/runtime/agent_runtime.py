from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable, Coroutine, Sequence
from contextlib import suppress
from functools import partial
from typing import Any

from pydantic import ValidationError

from ..providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
)
from ..providers.error_details import (
    FailureDiagnostic,
    capture_failure_diagnostic,
    log_failure_diagnostic,
)
from ..queue.cancellation import JobCancelledError, RunCancellationPort
from ..tools.registry import ToolContext, ToolDefinition, ToolRegistry
from .model_runtime import ModelCallContext, ModelLane, ModelRuntime
from .turn_result import (
    AgentTurnResult,
    RuntimeToolCall,
    RuntimeToolResult,
    add_usage,
    aggregate_visible_content,
    empty_usage,
)

logger = logging.getLogger(__name__)

_BUILDER_CONTINUATION_TOOLS = {
    "append_update_batch",
    "append_outline_tree",
    "put_update_text_block",
    "put_update_item_text_block",
    "put_update_item_text_blocks",
    "finish_update_builder",
}

_SAFE_TOOL_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_SAFE_FIELD_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_SAFE_ERROR_TYPE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_SAFE_VALIDATION_ISSUE_PATTERN = re.compile(
    r"loc=(?:<root>|\?|[A-Za-z_][A-Za-z0-9_]{0,63}"
    r"(?:\.(?:[A-Za-z_][A-Za-z0-9_]{0,63}|[0-9]{1,4}|\?))*) "
    r"type=[a-z][a-z0-9_]{0,63}"
)
_MAX_VALIDATION_ISSUES = 10
_MAX_PROTOCOL_ISSUES = 10
_SAFE_PROTOCOL_ISSUE_PATTERN = re.compile(
    r"tool=[a-z][a-z0-9_]{0,63} "
    r"code=[a-z][a-z0-9_]{0,63} chars=[0-9]{1,9}"
)
_TOOL_PROTOCOL_CORRECTION_INSTRUCTION = (
    "上一轮输出未通过工具协议校验。请重新生成本轮完整工具调用；"
    "必须只使用当前声明的工具，arguments 必须是完整 JSON 对象并严格符合对应 JSON Schema；"
    "不要解释、不要输出纯文本替代工具调用，也不要复述上一轮内容。"
)
_TOOL_CORRECTION_HINTS = {
    "outline_locator_required": (
        "get_outline_node 必须提供 node_id 或 node_title 中至少一个非空字符串。"
        "尚无真实节点定位时，先调用 list_outline_summary 获取大纲索引，不要编造节点。"
    ),
    "item_target_required": "必须提供 targetId、targetKey 或 targetName 中至少一个非空字符串。",
    "artifact_locator_required": "必须提供 artifactId 或 artifactKey 中至少一个非空字符串。",
    "evaluation_revision_combination_invalid": (
        "pass/block 不得携带 revisionMode 或 patches；revise 必须声明 revisionMode；"
        "patch 必须提交 1 到 20 个 patches，rewrite 不得携带 patches。"
    ),
    "artifact_operation_mismatch": (
        "产物种类和字段必须符合当前操作的工具 Schema；"
        "普通正文提交 content，选区替换提交 replacement 与完整冻结身份，不能混用。"
    ),
    "artifact_content_required": "缺少完整正文 content。",
    "artifact_content_blank": "content 不能只包含空白。",
    "artifact_selection_incomplete": "混入了不完整的选区字段。",
    "artifact_selection_content_conflict": "选区 replacement 与完整 content 不能混用。",
    "artifact_selection_range_invalid": "selectionEnd 必须大于 selectionStart。",
    "artifact_selection_hash_invalid": "选区哈希必须是小写 SHA-256。",
}


class ModelToolArgumentsInvalidError(RuntimeError):
    """公共文本只含安全摘要，完整失败参数通过独立属性送入日志。"""

    code = "MODEL_TOOL_ARGUMENTS_INVALID"
    retryable = False

    def __init__(self, tool_name: str, validation_issues: Sequence[str]) -> None:
        self.tool_name = (
            tool_name if _SAFE_TOOL_NAME_PATTERN.fullmatch(tool_name) else "unknown_tool"
        )
        self.validation_issues = tuple(
            issue
            for issue in validation_issues[:_MAX_VALIDATION_ISSUES]
            if _SAFE_VALIDATION_ISSUE_PATTERN.fullmatch(issue)
        )
        self.failureDiagnostics: list[FailureDiagnostic] = []
        summary = "|".join(self.validation_issues) or "none"
        super().__init__(
            f"{self.code}：工具 {self.tool_name} 参数校验失败（{summary}）"
        )

    @classmethod
    def from_validation_error(
        cls,
        tool_name: str,
        error: ValidationError,
        *,
        arguments: dict[str, Any] | None = None,
        schema_supplier: Callable[[], dict[str, Any]] | None = None,
        call_id: str | None = None,
    ) -> ModelToolArgumentsInvalidError:
        issues: list[str] = []
        for detail in error.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )[:_MAX_VALIDATION_ISSUES]:
            location = _safe_validation_location(detail.get("loc"))
            error_type = detail.get("type")
            safe_type = (
                error_type
                if isinstance(error_type, str)
                and _SAFE_ERROR_TYPE_PATTERN.fullmatch(error_type)
                else "unknown"
            )
            issues.append(f"loc={location} type={safe_type}")
        result = cls(tool_name, issues)
        with suppress(Exception):
            payload = {
                "toolName": tool_name, "toolCallId": call_id,
                "arguments": arguments,
                "validationErrors": error.errors(include_url=False),
            }
            schema_failure: str | None = None
            if schema_supplier is not None:
                try:
                    payload.update(schema_supplier())
                except Exception as schema_error:
                    schema_failure = type(schema_error).__name__
            diagnostic = capture_failure_diagnostic(
                stage="tool_arguments_pydantic", code=result.code, error=error,
                payload=payload,
            )
            if schema_failure is not None:
                diagnostic.captureFailure = schema_failure
            result.failureDiagnostics.append(diagnostic)
        return result


class ModelToolProtocolRecoveryFailedError(RuntimeError):
    """有界纠正后仍无合法工具调用；只携带安全派生诊断。"""

    code = "MODEL_TOOL_PROTOCOL_RECOVERY_FAILED"
    retryable = False

    def __init__(
        self,
        *,
        protocol_issues: Sequence[str] = (),
        validation_issues: Sequence[str] = (),
    ) -> None:
        self.protocol_issues = tuple(
            issue
            for issue in protocol_issues[:_MAX_PROTOCOL_ISSUES]
            if _SAFE_PROTOCOL_ISSUE_PATTERN.fullmatch(issue)
        )
        self.validation_issues = tuple(
            issue
            for issue in validation_issues[:_MAX_VALIDATION_ISSUES]
            if _SAFE_VALIDATION_ISSUE_PATTERN.fullmatch(issue)
        )
        protocol_summary = "|".join(self.protocol_issues) or "none"
        validation_summary = "|".join(self.validation_issues) or "none"
        super().__init__(
            f"{self.code}：工具协议纠正失败"
            f"（protocol={protocol_summary},validation={validation_summary}）"
        )

    @classmethod
    def from_response(
        cls,
        response: ModelTurnResult,
    ) -> ModelToolProtocolRecoveryFailedError:
        issues: list[str] = []
        for name, code, character_count in zip(
            response.invalidToolCallNames,
            response.invalidToolCallCodes,
            response.invalidToolCallArgumentCharacterCounts,
            strict=True,
        ):
            safe_name = (
                name if _SAFE_TOOL_NAME_PATTERN.fullmatch(name) else "unknown_tool"
            )
            issues.append(
                f"tool={safe_name} code={code} chars={min(character_count, 999_999_999)}"
            )
        return cls(protocol_issues=issues)

    @classmethod
    def from_arguments_error(
        cls,
        error: ModelToolArgumentsInvalidError,
    ) -> ModelToolProtocolRecoveryFailedError:
        return cls(
            protocol_issues=(
                f"tool={error.tool_name} code=schema_validation chars=0",
            ),
            validation_issues=error.validation_issues,
        )

    @classmethod
    def missing_corrected_tool_call(cls) -> ModelToolProtocolRecoveryFailedError:
        return cls(
            protocol_issues=(
                "tool=unknown_tool code=missing_corrected_tool_call chars=0",
            )
        )


def _safe_validation_location(value: object) -> str:
    if not isinstance(value, tuple) or not value:
        return "<root>"
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item if _SAFE_FIELD_NAME_PATTERN.fullmatch(item) else "?")
        elif isinstance(item, int) and 0 <= item <= 9999:
            parts.append(str(item))
        else:
            parts.append("?")
    return ".".join(parts)


def _tool_failure_schemas(
    tool: ToolDefinition, parameters: dict[str, Any] | None,
) -> dict[str, Any]:
    """参数预检使用业务契约；供应商转换前的操作契约单独命名，避免混淆。"""
    return {
        "businessSchema": tool.argumentsModel.model_json_schema(),
        "modelSchema": tool.as_model_tool(parameters=parameters).parameters,
    }


def _with_tool_protocol_correction(
    conversation: Sequence[ModelMessage],
    error: ModelToolProtocolRecoveryFailedError,
    *,
    chapter_artifact: bool,
) -> list[ModelMessage]:
    """仅将已脱敏诊断与固定修复指令放入提示，不回放无效响应或参数值。"""

    leading_system_count = 0
    for message in conversation:
        if message.role != "system":
            break
        leading_system_count += 1
    instructions = [_TOOL_PROTOCOL_CORRECTION_INSTRUCTION]
    instructions.append(
        "安全校验诊断：" + "；".join((*error.protocol_issues, *error.validation_issues))
    )
    for code, hint in _TOOL_CORRECTION_HINTS.items():
        if any(issue.endswith(f"type={code}") for issue in error.validation_issues):
            instructions.append(hint)
    if chapter_artifact:
        instructions.append(
            "本次是普通章节正文提交：调用 begin_artifact_output，"
            "只提交 kind=chapter_draft、summary 和完整非空 content；其余字段省略，"
            "不得混入选区身份或 replacement，不得概述或截断正文。"
        )
    correction = ModelMessage(role="system", content="\n".join(instructions))
    return [
        *conversation[:leading_system_count],
        correction,
        *conversation[leading_system_count:],
    ]


class AgentRuntime:
    def __init__(
        self,
        model_runtime: ModelRuntime,
        registry: ToolRegistry,
        *,
        max_output_tokens: int,
        cancellation: RunCancellationPort | None = None,
    ) -> None:
        self._model_runtime = model_runtime
        self._registry = registry
        self._max_output_tokens = max_output_tokens
        self._cancellation = cancellation

    async def run(
        self,
        *,
        messages: Sequence[dict[str, object] | ModelMessage],
        exposed_tools: list[ToolDefinition],
        context: ToolContext,
        max_iterations: int = 10,
        terminal_control_tools: set[str] | frozenset[str] = frozenset(),
        policy: ModelExecutionPolicy,
        model_context: ModelCallContext | None = None,
        model_lane: ModelLane = "interactive",
        reviewer: bool = False,
        allow_chapter_artifact_correction: bool = False,
        model_tool_schemas: dict[str, dict[str, Any]] | None = None,
    ) -> AgentTurnResult:
        """日志只观察失败；原异常、取消、工具权限和纠正次数保持原语义。"""
        try:
            return await self._run_impl(
                messages=messages, exposed_tools=exposed_tools, context=context,
                max_iterations=max_iterations, terminal_control_tools=terminal_control_tools,
                policy=policy, model_context=model_context, model_lane=model_lane,
                reviewer=reviewer,
                allow_chapter_artifact_correction=allow_chapter_artifact_correction,
                model_tool_schemas=model_tool_schemas,
            )
        except JobCancelledError:
            raise
        except Exception as exc:
            self._record_failure(
                stage="agent_runtime", code="AGENT_RUNTIME_FAILED", error=exc,
                context=context, model_context=model_context,
                payload_factory=lambda: {"exposedTools": [tool.name for tool in exposed_tools]},
            )
            raise

    def _record_failure(
        self, *, stage: str, code: str, context: ToolContext,
        model_context: ModelCallContext | None = None, error: BaseException | None = None,
        payload_factory: Callable[[], Any] | None = None,
    ) -> None:
        """将载荷构造也置于保护内，序列化失败不能覆盖原业务错误。"""
        with suppress(Exception):
            diagnostic = capture_failure_diagnostic(
                stage=stage, code=code, error=error,
                payload=payload_factory() if payload_factory is not None else None,
            )
            self._record_diagnostic(diagnostic, context, model_context)

    def _record_diagnostic(
        self, diagnostic: FailureDiagnostic, context: ToolContext,
        model_context: ModelCallContext | None = None,
    ) -> None:
        """兼容旧运行时替身，日志写入失败不能变成业务失败。"""
        with suppress(Exception):
            callback = getattr(self._model_runtime, "record_failure_diagnostic", None)
            if callable(callback):
                callback(diagnostic, context=model_context or ModelCallContext(
                    userId=context.userId, novelId=context.novelId, taskId=context.taskId,
                    runId=context.runId, agentId=context.agentId,
                ))
            else:
                log_failure_diagnostic(logger, diagnostic, task_id=context.taskId,
                                       run_id=context.runId, agent_id=context.agentId)

    async def _run_impl(
        self,
        *,
        messages: Sequence[dict[str, object] | ModelMessage],
        exposed_tools: list[ToolDefinition],
        context: ToolContext,
        max_iterations: int = 10,
        terminal_control_tools: set[str] | frozenset[str] = frozenset(),
        policy: ModelExecutionPolicy,
        model_context: ModelCallContext | None = None,
        model_lane: ModelLane = "interactive",
        reviewer: bool = False,
        allow_chapter_artifact_correction: bool = False,
        model_tool_schemas: dict[str, dict[str, Any]] | None = None,
    ) -> AgentTurnResult:
        conversation = [
            message if isinstance(message, ModelMessage) else ModelMessage.model_validate(message)
            for message in messages
        ]
        visible_parts: list[str] = []
        control_events: list[dict[str, Any]] = []
        tool_calls: list[RuntimeToolCall] = []
        tool_results: list[RuntimeToolResult] = []
        usage = empty_usage()
        active_builder_key: str | None = None
        protocol_corrections_used = 0
        read_correction_used = False

        for _ in range(max_iterations):
            available_tools = [
                tool
                for tool in exposed_tools
                if not (active_builder_key is not None and tool.name == "start_update_builder")
            ]
            request_messages = conversation
            correction_in_progress = False
            while True:
                await self._ensure_active(context)
                response = await self._model_runtime.run_turn(
                    ModelTurnRequest(
                        messages=request_messages,
                        tools=[
                            tool.as_model_tool(
                                parameters=(model_tool_schemas or {}).get(tool.name)
                            )
                            for tool in available_tools
                        ],
                        maxOutputTokens=self._max_output_tokens,
                        policy=policy,
                    ),
                    context=model_context,
                    lane=model_lane,
                    reviewer=reviewer,
                )
                await self._ensure_active(context)
                usage = add_usage(usage, response.usage)
                try:
                    self._raise_incomplete_response(response)
                except Exception as exc:
                    self._record_failure(
                        stage="model_finish_reason", code="MODEL_COMPLETION_REJECTED", error=exc,
                        context=context, model_context=model_context,
                        payload_factory=partial(response.model_dump, exclude={"reasoningContent"}),
                    )
                    raise

                protocol_error: ModelToolProtocolRecoveryFailedError | None = None
                artifact_arguments_invalid = False
                if response.invalidToolCallCount:
                    protocol_error = ModelToolProtocolRecoveryFailedError.from_response(
                        response
                    )
                elif (
                    correction_in_progress
                    and response.finishReason == "tool_calls"
                    and not response.toolCalls
                ):
                    protocol_error = (
                        ModelToolProtocolRecoveryFailedError.missing_corrected_tool_call()
                    )
                else:
                    try:
                        validated_calls = self._preflight_response(
                            response,
                            {tool.name: tool for tool in available_tools},
                            context,
                            terminal_control_tools,
                            model_tool_schemas=model_tool_schemas,
                        )
                    except ModelToolArgumentsInvalidError as error:
                        for diagnostic in error.failureDiagnostics:
                            self._record_diagnostic(diagnostic, context, model_context)
                        protocol_error = (
                            ModelToolProtocolRecoveryFailedError.from_arguments_error(error)
                        )
                        artifact_arguments_invalid = error.tool_name == "begin_artifact_output"
                    except Exception as exc:
                        self._record_failure(
                            stage="tool_preflight", code="TOOL_PREFLIGHT_FAILED", error=exc,
                            context=context, model_context=model_context,
                            payload_factory=partial(
                                response.model_dump, exclude={"reasoningContent"},
                            ),
                        )
                        raise
                    else:
                        if correction_in_progress and not validated_calls:
                            protocol_error = (
                                ModelToolProtocolRecoveryFailedError.missing_corrected_tool_call()
                            )
                if protocol_error is None:
                    break

                # 只有已成功纠正过纯读取响应，后续正文提交才可使用保留机会；
                # 同一纠正响应再次失败必须立即结束，不能连续放宽预算。
                use_chapter_reserve = (
                    allow_chapter_artifact_correction
                    and read_correction_used
                    and protocol_corrections_used == 1
                    and not correction_in_progress
                    and artifact_arguments_invalid
                )
                can_correct = bool(available_tools) and (
                    protocol_corrections_used == 0 or use_chapter_reserve
                )
                action = (
                    "correct_chapter_artifact" if use_chapter_reserve
                    else "correct" if can_correct else "fail"
                )
                with suppress(Exception):
                    logger.warning(
                        "工具协议校验未通过 run_id=%s corrections_used=%s action=%s "
                        "protocol=%s validation=%s",
                        context.runId, protocol_corrections_used, action,
                        protocol_error.protocol_issues, protocol_error.validation_issues,
                    )
                self._record_failure(
                    stage="tool_protocol_correction", code=protocol_error.code,
                    context=context, model_context=model_context,
                    payload_factory=partial(
                        dict, correctionsUsed=protocol_corrections_used, action=action,
                        providerResponseId=response.providerResponseId,
                        protocolIssues=protocol_error.protocol_issues,
                        validationIssues=protocol_error.validation_issues,
                    ),
                )
                if not can_correct:
                    raise protocol_error from None
                if protocol_corrections_used == 0:
                    response_tool_names = {
                        *(call.name for call in response.toolCalls),
                        *response.invalidToolCallNames,
                    }
                    read_tool_names = {
                        tool.name for tool in available_tools
                        if tool.toolKind == "read" and tool.permission.readOnly
                    }
                    read_correction_used = bool(response_tool_names) and (
                        response_tool_names <= read_tool_names
                    )
                protocol_corrections_used += 1
                correction_in_progress = True
                request_messages = _with_tool_protocol_correction(
                    conversation, protocol_error,
                    chapter_artifact=(
                        allow_chapter_artifact_correction and artifact_arguments_invalid
                    ),
                )
            if response.content:
                visible_parts.append(response.content)
            if not validated_calls:
                return self._result(
                    visible_parts,
                    control_events,
                    tool_calls,
                    tool_results,
                    usage,
                    "completed",
                )

            conversation.append(
                ModelMessage(
                    role="assistant",
                    content=response.content,
                    reasoning_content=response.reasoningContent,
                    toolCalls=response.toolCalls,
                )
            )
            terminal = False
            index = 0
            while index < len(validated_calls):
                call, tool, arguments = validated_calls[index]
                safe_batch = []
                while index < len(validated_calls):
                    candidate, candidate_tool, candidate_arguments = validated_calls[index]
                    if (
                        candidate_tool.toolKind != "read"
                        or not candidate_tool.permission.readOnly
                        or not candidate_tool.permission.concurrencySafe
                    ):
                        break
                    safe_batch.append(
                        (candidate, candidate_tool, candidate_arguments)
                    )
                    index += 1
                if safe_batch:
                    await self._ensure_active(context)
                    tasks: list[Coroutine[Any, Any, dict[str, Any]]] = [
                        self._registry.execute_validated(
                            tool_item, validated_arguments, context
                        )
                        for _, tool_item, validated_arguments in safe_batch
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    await self._ensure_active(context)
                    for (call_item, tool_item, arguments), result in zip(
                        safe_batch, results, strict=True
                    ):
                        self._record_tool_failure(
                            call_item, arguments, result, context, model_context,
                        )
                        normalized = self._normalize_result(result)
                        self._record_tool(
                            call_item.id,
                            tool_item,
                            arguments,
                            normalized,
                            conversation,
                            tool_calls,
                            tool_results,
                        )
                    continue

                await self._ensure_active(context)
                if tool.toolKind == "control":
                    artifact_key = arguments.get("artifactKey")
                    if tool.name == "start_update_builder":
                        if active_builder_key is not None:
                            normalized = {
                                "acknowledged": False,
                                "tool": tool.name,
                                "error": (
                                    "更新构建器已经开始，请继续追加内容或调用 "
                                    "finish_update_builder"
                                ),
                                "artifactKey": active_builder_key,
                            }
                        else:
                            active_builder_key = str(artifact_key)
                            control_events.append({"type": tool.name, **arguments})
                            normalized = {
                                "acknowledged": True,
                                "tool": tool.name,
                                "builderState": "started",
                                "artifactKey": active_builder_key,
                                "next": "请追加更新，完成后调用 finish_update_builder",
                            }
                    elif tool.name in _BUILDER_CONTINUATION_TOOLS:
                        if active_builder_key is None:
                            normalized = {
                                "acknowledged": False,
                                "tool": tool.name,
                                "error": "更新构建器尚未开始，请先调用 start_update_builder",
                            }
                        elif artifact_key != active_builder_key:
                            normalized = {
                                "acknowledged": False,
                                "tool": tool.name,
                                "error": "更新构建器 artifactKey 与当前草稿箱不一致",
                                "artifactKey": active_builder_key,
                            }
                        else:
                            control_events.append({"type": tool.name, **arguments})
                            normalized = {
                                "acknowledged": True,
                                "tool": tool.name,
                                "builderState": (
                                    "finished"
                                    if tool.name == "finish_update_builder"
                                    else "building"
                                ),
                                "artifactKey": active_builder_key,
                                "next": (
                                    "更新构建器已完成"
                                    if tool.name == "finish_update_builder"
                                    else "可以继续追加，完成后调用 finish_update_builder"
                                ),
                            }
                            terminal = terminal or tool.name in terminal_control_tools
                    else:
                        normalized = {"acknowledged": True, "tool": tool.name}
                        control_events.append({"type": tool.name, **arguments})
                        terminal = terminal or tool.name in terminal_control_tools
                else:
                    try:
                        normalized = await self._registry.execute_validated(
                            tool, arguments, context
                        )
                    except JobCancelledError:
                        raise
                    except Exception as exc:
                        self._record_tool_failure(call, arguments, exc, context, model_context)
                        normalized = {"error": str(exc)}
                    else:
                        self._record_tool_failure(
                            call, arguments, normalized, context, model_context,
                        )
                    await self._ensure_active(context)
                if tool.toolKind == "control" and normalized.get("acknowledged") is False:
                    self._record_tool_failure(call, arguments, normalized, context, model_context)
                self._record_tool(
                    call.id,
                    tool,
                    arguments,
                    normalized,
                    conversation,
                    tool_calls,
                    tool_results,
                )
                index += 1
                if terminal:
                    break
            if terminal:
                return self._result(
                    visible_parts,
                    control_events,
                    tool_calls,
                    tool_results,
                    usage,
                    "terminal_control_tool",
                )

        visible_parts.append("模型达到最大工具调用轮次，请缩小请求范围后重试。")
        return self._result(
            visible_parts,
            control_events,
            tool_calls,
            tool_results,
            usage,
            "max_iterations",
        )

    async def _ensure_active(self, context: ToolContext) -> None:
        if self._cancellation is not None:
            await self._cancellation.ensure_active(context.jobId)

    def _preflight_response(
        self,
        response: ModelTurnResult,
        exposed: dict[str, ToolDefinition],
        context: ToolContext,
        terminal_control_tools: set[str] | frozenset[str],
        *,
        model_tool_schemas: dict[str, dict[str, Any]] | None = None,
    ) -> list[tuple[ModelToolCall, ToolDefinition, dict[str, Any]]]:
        self._raise_incomplete_response(response)

        has_tool_calls = bool(response.toolCalls)
        if (response.finishReason == "stop" and has_tool_calls) or (
            response.finishReason == "tool_calls" and not has_tool_calls
        ):
            raise RuntimeError(
                "PROVIDER_FINISH_REASON_INVALID：供应商完成原因与工具调用状态不一致"
            )
        if response.finishReason == "unknown" and not has_tool_calls:
            raise RuntimeError(
                "PROVIDER_FINISH_REASON_UNKNOWN：供应商未提供可确认完成的结束原因"
            )

        validated_calls: list[
            tuple[ModelToolCall, ToolDefinition, dict[str, Any]]
        ] = []
        seen_call_ids: set[str] = set()
        for call in response.toolCalls:
            if not call.id.strip():
                raise RuntimeError(
                    "MODEL_TOOL_CALL_ID_INVALID：模型工具调用缺少有效 ID"
                )
            if call.id in seen_call_ids:
                raise RuntimeError(
                    f"MODEL_TOOL_CALL_ID_DUPLICATE：模型工具调用 ID 重复 {call.id}"
                )
            seen_call_ids.add(call.id)
            tool = exposed.get(call.name)
            if tool is None:
                raise RuntimeError(
                    f"MODEL_TOOL_NOT_EXPOSED：模型调用了未暴露工具 {call.name}"
                )
            tool = self._registry.require_authorized(tool, context)
            try:
                arguments = tool.validate_model_arguments(
                    call.arguments,
                    parameters=(model_tool_schemas or {}).get(tool.name),
                )
            except ValidationError as exc:
                raise ModelToolArgumentsInvalidError.from_validation_error(
                    call.name,
                    exc,
                    arguments=call.arguments,
                    schema_supplier=partial(
                        _tool_failure_schemas, tool, (model_tool_schemas or {}).get(tool.name),
                    ),
                    call_id=call.id,
                ) from None
            validated_calls.append((call, tool, arguments))

        terminal_count = sum(
            call.name in terminal_control_tools for call in response.toolCalls
        )
        if terminal_count > 1:
            raise RuntimeError(
                "MODEL_TERMINAL_TOOL_CONFLICT：同一模型响应包含多个终止控制工具"
            )
        return validated_calls

    @staticmethod
    def _raise_incomplete_response(response: ModelTurnResult) -> None:
        raw_finish_reason = (
            response.rawFinishReason
            if response.rawFinishReason is not None
            else "未提供"
        )
        if response.finishReason == "length":
            raise RuntimeError(
                "MODEL_OUTPUT_TRUNCATED：供应商报告模型输出达到长度上限"
                f"（原始原因：{raw_finish_reason}）"
            )
        if response.finishReason == "content_filter":
            raise RuntimeError(
                "MODEL_OUTPUT_FILTERED：供应商报告模型输出被内容过滤"
                f"（原始原因：{raw_finish_reason}）"
            )
        if response.finishReason == "insufficient_system_resource":
            raise RuntimeError(
                "MODEL_INSUFFICIENT_SYSTEM_RESOURCE：供应商报告系统资源不足"
                f"（原始原因：{raw_finish_reason}）"
            )

    @staticmethod
    def _normalize_result(result: object) -> dict[str, Any]:
        if isinstance(result, Exception):
            return {"error": str(result)}
        if not isinstance(result, dict):
            return {"error": "工具返回值不是对象"}
        return result

    def _record_tool_failure(
        self, call: ModelToolCall, arguments: dict[str, Any], result: object,
        context: ToolContext, model_context: ModelCallContext | None,
    ) -> None:
        """并发与串行工具保留各自失败证据，正常工具结果不重复写入诊断。"""
        failed = not isinstance(result, dict) or (
            "error" in result or result.get("acknowledged") is False
        )
        if not failed or isinstance(result, JobCancelledError):
            return
        self._record_failure(
            stage="tool_execution", code="TOOL_EXECUTION_FAILED",
            error=result if isinstance(result, BaseException) else None,
            context=context, model_context=model_context,
            payload_factory=lambda: {
                "toolName": call.name, "toolCallId": call.id,
                "arguments": arguments,
                "result": None if isinstance(result, BaseException) else result,
            },
        )

    @staticmethod
    def _record_tool(
        call_id: str,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        result: dict[str, Any],
        conversation: list[ModelMessage],
        calls: list[RuntimeToolCall],
        results: list[RuntimeToolResult],
    ) -> None:
        calls.append(
            RuntimeToolCall(
                name=tool.name,
                toolKind=tool.toolKind,
                arguments=arguments,
            )
        )
        results.append(RuntimeToolResult(name=tool.name, result=result))
        conversation.append(
            ModelMessage(
                role="tool",
                name=tool.name,
                toolCallId=call_id,
                content=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            )
        )

    @staticmethod
    def _result(
        visible_parts: list[str],
        control_events: list[dict[str, Any]],
        tool_calls: list[RuntimeToolCall],
        tool_results: list[RuntimeToolResult],
        usage: object,
        finish_reason: str,
    ) -> AgentTurnResult:
        from ..providers.base import ModelUsage

        if not isinstance(usage, ModelUsage):
            raise TypeError("模型用量类型无效")
        return AgentTurnResult(
            visibleContent=aggregate_visible_content(visible_parts),
            controlEvents=control_events,
            toolCalls=tool_calls,
            toolResults=tool_results,
            usage=usage,
            finishReason=finish_reason,
        )
