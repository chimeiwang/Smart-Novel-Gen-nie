from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine, Sequence
from typing import Any

from pydantic import ValidationError

from ..providers.base import ModelMessage, ModelToolCall, ModelTurnRequest, ModelTurnResult
from ..tools.registry import ToolContext, ToolDefinition, ToolRegistry
from .model_runtime import ModelCallContext, ModelRuntime
from .turn_result import (
    AgentTurnResult,
    RuntimeToolCall,
    RuntimeToolResult,
    add_usage,
    aggregate_visible_content,
    empty_usage,
)

_BUILDER_CONTINUATION_TOOLS = {
    "append_update_batch",
    "append_outline_tree",
    "put_update_text_block",
    "put_update_item_text_block",
    "put_update_item_text_blocks",
    "finish_update_builder",
}


class AgentRuntime:
    def __init__(self, model_runtime: ModelRuntime, registry: ToolRegistry) -> None:
        self._model_runtime = model_runtime
        self._registry = registry

    async def run(
        self,
        *,
        messages: Sequence[dict[str, object] | ModelMessage],
        exposed_tools: list[ToolDefinition],
        context: ToolContext,
        max_iterations: int = 10,
        max_output_tokens: int = 8192,
        terminal_control_tools: set[str] | frozenset[str] = frozenset(),
        model_context: ModelCallContext | None = None,
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

        for _ in range(max_iterations):
            available_tools = [
                tool
                for tool in exposed_tools
                if not (active_builder_key is not None and tool.name == "start_update_builder")
            ]
            response = await self._model_runtime.run_turn(
                ModelTurnRequest(
                    messages=conversation,
                    tools=[tool.as_model_tool() for tool in available_tools],
                    maxOutputTokens=max_output_tokens,
                ),
                context=model_context,
            )
            usage = add_usage(usage, response.usage)
            validated_calls = self._preflight_response(
                response,
                {tool.name: tool for tool in available_tools},
                terminal_control_tools,
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
                    tasks: list[Coroutine[Any, Any, dict[str, Any]]] = [
                        self._registry.execute_validated(
                            tool_item, validated_arguments, context
                        )
                        for _, tool_item, validated_arguments in safe_batch
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for (call_item, tool_item, arguments), result in zip(
                        safe_batch, results, strict=True
                    ):
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
                    except Exception as exc:
                        normalized = {"error": str(exc)}
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

    @staticmethod
    def _preflight_response(
        response: ModelTurnResult,
        exposed: dict[str, ToolDefinition],
        terminal_control_tools: set[str] | frozenset[str],
    ) -> list[tuple[ModelToolCall, ToolDefinition, dict[str, Any]]]:
        if response.finishReason == "length":
            raise RuntimeError(
                "MODEL_OUTPUT_TRUNCATED：供应商报告模型输出达到长度上限"
                f"（原始原因：{response.rawFinishReason or '未提供'}）"
            )
        if response.finishReason == "content_filter":
            raise RuntimeError(
                "MODEL_OUTPUT_FILTERED：供应商报告模型输出被内容过滤"
                f"（原始原因：{response.rawFinishReason or '未提供'}）"
            )

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
        for call in response.toolCalls:
            tool = exposed.get(call.name)
            if tool is None:
                raise RuntimeError(
                    f"MODEL_TOOL_NOT_EXPOSED：模型调用了未暴露工具 {call.name}"
                )
            try:
                arguments = tool.validate(call.arguments)
            except ValidationError as exc:
                raise RuntimeError(
                    f"MODEL_TOOL_ARGUMENTS_INVALID：工具 {call.name} 参数校验失败：{exc}"
                ) from exc
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
    def _normalize_result(result: object) -> dict[str, Any]:
        if isinstance(result, Exception):
            return {"error": str(result)}
        if not isinstance(result, dict):
            return {"error": "工具返回值不是对象"}
        return result

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
