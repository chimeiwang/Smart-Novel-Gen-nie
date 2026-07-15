from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

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
                ]
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
        response = cast(
            AIMessage,
            await model.ainvoke(
                messages,
                max_tokens=request.maxOutputTokens,
            ),
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
