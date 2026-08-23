from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..config import Settings
from .base import (
    ModelFinishReason,
    ModelMessage,
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
)
from .openai_compatible import normalize_finish_reason


class DeepSeekV4Provider:
    """DeepSeek V4 原始 Chat Completions 传输层。"""

    billable = True
    provider_name = "openai_compatible"

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
            raise ValueError("真实模型提供方缺少 OPENAI_API_KEY")
        self.model_name = settings.openai_model
        self._endpoint = _completion_endpoint(settings.openai_base_url)
        self._api_key = settings.openai_api_key.get_secret_value()
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        payload = {
            "model": self.model_name,
            "messages": [_message_to_wire(message) for message in request.messages],
            "max_tokens": request.maxOutputTokens,
        }
        if request.tools:
            payload["tools"] = [
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
        _apply_policy(payload, request)
        try:
            response = await self._client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"DeepSeek 请求失败：{exc}") from exc
        if response.is_error:
            detail = response.text[:1000]
            raise RuntimeError(f"DeepSeek 请求失败：HTTP {response.status_code} {detail}")
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("DeepSeek 响应不是有效 JSON") from exc
        return _parse_response(body)


def _completion_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.query:
        raise ValueError("DeepSeek base URL 不能包含 query")
    if parsed.fragment:
        raise ValueError("DeepSeek base URL 不能包含 fragment")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("DeepSeek base URL 必须是有效 HTTP URL")
    if (
        parsed.hostname
        and parsed.hostname.lower() == "api.deepseek.com"
        and parsed.port is None
        and parsed.path.rstrip("/") in {"", "/v1"}
    ):
        return "https://api.deepseek.com/chat/completions"
    return base_url.rstrip("/") + "/chat/completions"


def _message_to_wire(message: ModelMessage) -> dict[str, Any]:
    if message.role == "tool":
        if message.tool_call_id is None:
            raise ValueError("DeepSeek 工具消息缺少 toolCallId")
        return {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id,
            **({"name": message.name} if message.name is not None else {}),
        }
    if message.role == "assistant":
        wire: dict[str, Any] = {"role": "assistant", "content": message.content}
        if message.reasoningContent is not None:
            wire["reasoning_content"] = message.reasoningContent
        if message.tool_calls:
            wire["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            call.arguments, ensure_ascii=False, separators=(",", ":")
                        ),
                    },
                }
                for call in message.tool_calls
            ]
        return wire
    return {"role": message.role, "content": message.content}


def _apply_policy(payload: dict[str, Any], request: ModelTurnRequest) -> None:
    policy = request.policy
    if policy.thinkingMode == "enabled":
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = policy.reasoningEffort or "high"
    elif policy.thinkingMode == "disabled":
        payload["thinking"] = {"type": "disabled"}
        if policy.requiredToolName:
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": policy.requiredToolName},
            }


def _parse_response(body: object) -> ModelTurnResult:
    if not isinstance(body, Mapping):
        raise ValueError("DeepSeek 响应顶层不是对象")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise ValueError("DeepSeek 响应缺少 choices")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("DeepSeek 响应缺少 message")
    content = message.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise ValueError("DeepSeek 响应 content 不是文本或 null")
    tool_calls = _parse_tool_calls(message.get("tool_calls", []))
    raw_reason = choice.get("finish_reason")
    normalized: ModelFinishReason = normalize_finish_reason(raw_reason)
    usage = _parse_usage(body.get("usage"))
    response_id = body.get("id")
    return ModelTurnResult(
        content=content,
        reasoningContent=_optional_text(message.get("reasoning_content")),
        toolCalls=tool_calls,
        providerResponseId=_optional_text(response_id),
        usage=usage[0],
        diagnostics=usage[1],
        finishReason=normalized,
        rawFinishReason=_raw_reason(raw_reason),
    )


def _parse_tool_calls(raw: object) -> list[ModelToolCall]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("DeepSeek tool_calls 不是数组")
    parsed: list[ModelToolCall] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("DeepSeek 工具调用不是对象")
        call_id = item.get("id")
        function = item.get("function")
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("DeepSeek 工具调用缺少有效 ID")
        if not isinstance(function, Mapping):
            raise ValueError("DeepSeek 工具调用缺少 function")
        name = function.get("name")
        raw_arguments = function.get("arguments")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("DeepSeek 工具名称缺失")
        if not isinstance(raw_arguments, str):
            raise ValueError("DeepSeek 工具参数不是 JSON 字符串")
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"DeepSeek 工具参数 JSON 无效：{exc.msg}") from exc
        if not isinstance(arguments, dict):
            raise ValueError("DeepSeek 工具参数 JSON 必须是对象")
        parsed.append(ModelToolCall(id=call_id, name=name, arguments=arguments))
    return parsed


def _parse_usage(raw: object) -> tuple[ModelUsage, ModelUsageDiagnostics]:
    usage = raw if isinstance(raw, Mapping) else {}
    prompt = _nonnegative_int(usage.get("prompt_tokens", 0), "prompt_tokens")
    cached = _nonnegative_int(usage.get("prompt_cache_hit_tokens", 0), "prompt_cache_hit_tokens")
    completion = _nonnegative_int(usage.get("completion_tokens", 0), "completion_tokens")
    total = _nonnegative_int(usage.get("total_tokens", prompt + completion), "total_tokens")
    miss_value = usage.get("prompt_cache_miss_tokens")
    miss = None if miss_value is None else _nonnegative_int(miss_value, "prompt_cache_miss_tokens")
    details = usage.get("completion_tokens_details")
    reasoning_value = details.get("reasoning_tokens") if isinstance(details, Mapping) else None
    reasoning = (
        None if reasoning_value is None else _nonnegative_int(reasoning_value, "reasoning_tokens")
    )
    if miss is not None and cached + miss != prompt:
        raise ValueError("DeepSeek 用量矛盾：缓存命中与未命中不等于 prompt_tokens")
    if reasoning is not None and reasoning > completion:
        raise ValueError("DeepSeek 用量矛盾：reasoning_tokens 大于 completion_tokens")
    diagnostics = ModelUsageDiagnostics(
        promptCacheMissTokens=miss,
        reasoningTokens=reasoning,
        providerUsageKeys=sorted(str(key) for key in usage),
    )
    return ModelUsage(
        promptTokens=prompt,
        cachedTokens=cached,
        completionTokens=completion,
        totalTokens=total,
    ), diagnostics


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"DeepSeek 用量字段 {field} 无效")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("DeepSeek 响应文本字段类型无效")
    return value


def _raw_reason(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)
