from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

from json_repair import repair_json
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from ..config import Settings
from .base import (
    ModelFinishReason,
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)

logger = logging.getLogger(__name__)


def normalize_finish_reason(value: object) -> ModelFinishReason:
    if not isinstance(value, str):
        return "unknown"
    aliases: dict[str, ModelFinishReason] = {
        "stop": "stop",
        "tool_calls": "tool_calls",
        "function_call": "tool_calls",
        "length": "length",
        "max_tokens": "length",
        "content_filter": "content_filter",
    }
    return aliases.get(value, "unknown")


def _raw_finish_reason(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


class OpenAICompatibleProvider:
    billable = True
    provider_name = "openai_compatible"

    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
            raise ValueError("真实模型提供方缺少 OPENAI_API_KEY")
        self._model = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=0,
        )
        self.model_name = settings.openai_model

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        model: Any = self._model
        if request.tools:
            bind_kwargs: dict[str, str] = {}
            if request.requiredToolName is not None:
                bind_kwargs["tool_choice"] = request.requiredToolName
            model = model.bind_tools(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        },
                    }
                    for tool in request.tools
                ],
                **bind_kwargs,
            )
        messages: list[BaseMessage] = []
        for message in request.messages:
            if message.role == "system":
                messages.append(SystemMessage(content=message.content, name=message.name))
            elif message.role == "user":
                messages.append(HumanMessage(content=message.content, name=message.name))
            elif message.role == "assistant":
                messages.append(
                    AIMessage(
                        content=message.content,
                        tool_calls=[
                            {
                                "id": tool_call.id,
                                "name": tool_call.name,
                                "args": tool_call.arguments,
                                "type": "tool_call",
                            }
                            for tool_call in message.tool_calls
                        ],
                    )
                )
            elif message.tool_call_id is not None:
                messages.append(
                    ToolMessage(
                        content=message.content,
                        tool_call_id=message.tool_call_id,
                        name=message.name,
                    )
                )
            else:
                raise ValueError("工具消息缺少 toolCallId")
        invoke_kwargs: dict[str, Any] = {
            "max_tokens": request.maxOutputTokens,
        }
        if request.requiredToolName is not None:
            invoke_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = cast(
            AIMessage,
            await model.ainvoke(messages, **invoke_kwargs),
        )
        if not isinstance(response.content, str):
            raise ValueError("模型返回了不支持的非文本可见内容")

        usage: Mapping[str, Any] = response.usage_metadata or {}
        input_details = usage.get("input_token_details") or {}
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
        tool_calls = [
            ModelToolCall(
                id=str(tool_call.get("id", "")),
                name=str(tool_call["name"]),
                arguments=tool_call.get("args", {}),
            )
            for tool_call in response.tool_calls
        ]
        tool_calls.extend(_repair_invalid_tool_calls(response))
        provider_finish_reason = response.response_metadata.get("finish_reason")
        return ModelTurnResult(
            content=response.content,
            toolCalls=tool_calls,
            finishReason=normalize_finish_reason(provider_finish_reason),
            rawFinishReason=_raw_finish_reason(provider_finish_reason),
            usage=ModelUsage(
                promptTokens=prompt_tokens,
                cachedTokens=int(input_details.get("cache_read", 0)),
                completionTokens=completion_tokens,
                totalTokens=total_tokens,
            ),
        )


def _repair_invalid_tool_calls(response: AIMessage) -> list[ModelToolCall]:
    repaired_calls: list[ModelToolCall] = []
    for invalid_call in response.invalid_tool_calls:
        call_id = invalid_call.get("id")
        name = invalid_call.get("name")
        raw_arguments = invalid_call.get("args")
        if (
            not isinstance(call_id, str)
            or not call_id
            or not isinstance(name, str)
            or not name
            or not isinstance(raw_arguments, str)
            or not raw_arguments
        ):
            raise ValueError("MODEL_TOOL_ARGUMENTS_INVALID：供应商工具调用缺少必要字段")
        repaired = repair_json(raw_arguments, return_objects=True)
        if not isinstance(repaired, dict):
            raise ValueError("MODEL_TOOL_ARGUMENTS_INVALID：供应商工具参数无法修复为对象")
        logger.warning(
            "供应商返回的工具参数不是合法 JSON，已修复后交由严格工具契约复验",
            extra={"toolName": name, "toolCallId": call_id},
        )
        repaired_calls.append(
            ModelToolCall(id=call_id, name=name, arguments=repaired)
        )
    return repaired_calls
