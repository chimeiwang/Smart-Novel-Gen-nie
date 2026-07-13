from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine, Sequence
from typing import Any

from pydantic import ValidationError

from ..providers.base import ModelMessage, ModelTurnRequest
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
        exposed = {tool.name: tool for tool in exposed_tools}
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
            if response.content:
                visible_parts.append(response.content)
            if not response.toolCalls:
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
            while index < len(response.toolCalls):
                call = response.toolCalls[index]
                tool = exposed.get(call.name)
                if tool is None:
                    visible_parts.append(
                        f"工具“{call.name}”未向当前智能体暴露，已停止本轮工具调用。"
                    )
                    return self._result(
                        visible_parts,
                        control_events,
                        tool_calls,
                        tool_results,
                        usage,
                        "tool_authorization_error",
                    )

                safe_batch = []
                while index < len(response.toolCalls):
                    candidate = response.toolCalls[index]
                    candidate_tool = exposed.get(candidate.name)
                    if (
                        candidate_tool is None
                        or candidate_tool.toolKind != "read"
                        or not candidate_tool.permission.readOnly
                        or not candidate_tool.permission.concurrencySafe
                    ):
                        break
                    safe_batch.append((candidate, candidate_tool))
                    index += 1
                if safe_batch:
                    try:
                        validated_batch = [
                            (call_item, tool_item, tool_item.validate(call_item.arguments))
                            for call_item, tool_item in safe_batch
                        ]
                    except ValidationError as exc:
                        visible_parts.append(f"工具参数校验失败：{exc}")
                        return self._result(
                            visible_parts,
                            control_events,
                            tool_calls,
                            tool_results,
                            usage,
                            "tool_validation_error",
                        )
                    tasks: list[Coroutine[Any, Any, dict[str, Any]]] = [
                        self._registry.execute(tool_item.name, arguments, context)
                        for _, tool_item, arguments in validated_batch
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for (call_item, tool_item, arguments), result in zip(
                        validated_batch, results, strict=True
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

                try:
                    arguments = tool.validate(call.arguments)
                except ValidationError as exc:
                    visible_parts.append(f"工具参数校验失败：{exc}")
                    return self._result(
                        visible_parts,
                        control_events,
                        tool_calls,
                        tool_results,
                        usage,
                        "tool_validation_error",
                    )
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
                        normalized = await self._registry.execute(tool.name, arguments, context)
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
