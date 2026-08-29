from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any
from urllib.parse import unquote, urlsplit

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
    ProviderTransportError,
)
from .openai_compatible import (
    _resolve_deepseek_strict_base_url,
    normalize_finish_reason,
)

_DEEPSEEK_STRICT_SCHEMA_KEYS = (
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "const",
    "anyOf",
    "items",
    "$ref",
    "$defs",
    "description",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
)


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
        strict_base_url = _resolve_deepseek_strict_base_url(settings)
        self._strict_endpoint = (
            _completion_endpoint(strict_base_url) if strict_base_url is not None else None
        )
        self._api_key = settings.openai_api_key.get_secret_value()
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=300, write=60, pool=60)
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        strict_tool_count = sum(tool.strict for tool in request.tools)
        if 0 < strict_tool_count < len(request.tools):
            raise ValueError("DeepSeek 工具请求不能混用 strict 与非 strict 函数")
        use_strict_endpoint = strict_tool_count > 0
        if use_strict_endpoint:
            if self._strict_endpoint is None:
                raise ValueError("DeepSeek strict 工具请求缺少 OPENAI_STRICT_BASE_URL")
            endpoint = self._strict_endpoint
        else:
            endpoint = self._endpoint
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
                        "parameters": (
                            _project_deepseek_strict_schema(tool.parameters)
                            if use_strict_endpoint
                            else tool.parameters
                        ),
                        **({"strict": True} if use_strict_endpoint else {}),
                    },
                }
                for tool in request.tools
            ]
        _apply_policy(payload, request)
        response: httpx.Response | None = None
        transport_error: ProviderTransportError | None = None
        try:
            response = await self._client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException:
            transport_error = ProviderTransportError(
                code="timeout_error",
                statusCode=None,
                requestId=None,
            )
        except httpx.HTTPError as exc:
            del exc
            transport_error = ProviderTransportError(
                code="connection_error",
                statusCode=None,
                requestId=None,
            )
        # 离开捕获块后再抛出，避免原始网络异常及其请求信息进入异常链和日志。
        if transport_error is not None:
            raise transport_error
        if response is None:
            raise RuntimeError("DeepSeek HTTP 客户端未返回响应")
        if not response.is_success:
            raise ProviderTransportError(
                code="http_error",
                statusCode=response.status_code,
                requestId=_response_request_id(response),
            )
        try:
            body = response.json()
        except (ValueError, UnicodeError) as exc:
            raise ValueError("DeepSeek 响应不是有效 JSON") from exc
        return _parse_response(body)


def _project_deepseek_strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """将业务 JSON Schema 投影为 DeepSeek strict 支持的确定性子集。"""

    projected: dict[str, Any] = {}
    for key in _DEEPSEEK_STRICT_SCHEMA_KEYS:
        if key not in schema:
            continue
        value = schema[key]
        if key in {"properties", "$defs"} and isinstance(value, Mapping):
            projected[key] = {
                property_name: _project_deepseek_strict_schema(property_schema)
                for property_name, property_schema in value.items()
                if isinstance(property_schema, Mapping)
            }
        elif key == "anyOf" and isinstance(value, list):
            projected[key] = [
                (
                    _project_deepseek_strict_schema(item)
                    if isinstance(item, Mapping)
                    else deepcopy(item)
                )
                for item in value
            ]
        elif key == "items" and isinstance(value, Mapping):
            projected[key] = _project_deepseek_strict_schema(value)
        else:
            projected[key] = deepcopy(value)

    if projected.get("type") == "object" and isinstance(projected.get("properties"), Mapping):
        properties = projected["properties"]
        projected["required"] = list(properties)
        projected["additionalProperties"] = False
    return projected


def _completion_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.query:
        raise ValueError("DeepSeek base URL 不能包含 query")
    if parsed.fragment:
        raise ValueError("DeepSeek base URL 不能包含 fragment")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("DeepSeek base URL 必须是有效 HTTP URL")
    decoded_path = unquote(parsed.path)
    if (
        any(segment in {".", ".."} for segment in decoded_path.split("/"))
        or "\\" in decoded_path
        or "//" in decoded_path
    ):
        raise ValueError("DeepSeek base URL 路径包含不安全路径段")
    if (
        parsed.hostname
        and parsed.hostname.lower() == "api.deepseek.com"
        and parsed.port is None
        and parsed.path.rstrip("/") in {"", "/v1"}
    ):
        return "https://api.deepseek.com/chat/completions"
    return base_url.rstrip("/") + "/chat/completions"


def _response_request_id(response: httpx.Response) -> str | None:
    """只读取固定响应头中的短标识，禁止让任意头值进入日志。"""

    for header in ("x-request-id", "request-id", "x-ds-request-id"):
        value = response.headers.get(header)
        if not isinstance(value, str) or not value or len(value) > 256:
            continue
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")
        if all(character in allowed for character in value):
            return value
    return None


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
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
        raise ValueError("DeepSeek 响应 choices 必须恰好一个")
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
    if not isinstance(raw, Mapping):
        raise ValueError("DeepSeek 用量缺失或不是对象")
    usage = raw
    required = (
        "prompt_tokens",
        "prompt_cache_hit_tokens",
        "completion_tokens",
        "total_tokens",
    )
    if any(field not in usage for field in required):
        missing = next(field for field in required if field not in usage)
        raise ValueError(f"DeepSeek 用量缺少必填字段：{missing}")
    prompt = _nonnegative_int(usage["prompt_tokens"], "prompt_tokens")
    completion = _nonnegative_int(usage["completion_tokens"], "completion_tokens")
    total = _nonnegative_int(usage["total_tokens"], "total_tokens")
    if total != prompt + completion:
        raise ValueError(
            "DeepSeek 用量矛盾：total_tokens 不等于 prompt_tokens 与 completion_tokens 之和"
        )
    cached = _nonnegative_int(usage["prompt_cache_hit_tokens"], "prompt_cache_hit_tokens")
    miss = (
        _nonnegative_int(usage["prompt_cache_miss_tokens"], "prompt_cache_miss_tokens")
        if "prompt_cache_miss_tokens" in usage
        else None
    )
    if miss is not None and cached + miss != prompt:
        raise ValueError("DeepSeek 用量矛盾：缓存命中与未命中不等于 prompt_tokens")
    details = usage.get("completion_tokens_details")
    if details is not None and not isinstance(details, Mapping):
        raise ValueError("DeepSeek 用量明细不是对象")
    reasoning_value = (
        details["reasoning_tokens"]
        if isinstance(details, Mapping) and "reasoning_tokens" in details
        else None
    )
    top_level_has_reasoning = "reasoning_tokens" in usage
    if top_level_has_reasoning:
        top_level_reasoning = usage["reasoning_tokens"]
        if reasoning_value is not None and top_level_reasoning != reasoning_value:
            raise ValueError("DeepSeek 用量矛盾：reasoning_tokens 重复值不一致")
        reasoning_value = top_level_reasoning
    if (
        isinstance(details, Mapping) and "reasoning_tokens" in details and reasoning_value is None
    ) or (top_level_has_reasoning and reasoning_value is None):
        raise ValueError("DeepSeek 用量字段 reasoning_tokens 无效")
    reasoning = (
        None if reasoning_value is None else _nonnegative_int(reasoning_value, "reasoning_tokens")
    )
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
