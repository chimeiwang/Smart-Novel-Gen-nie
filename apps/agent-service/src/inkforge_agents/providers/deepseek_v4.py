from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import unquote, urlsplit

import httpx
import jsonschema_rs

from ..config import Settings
from .base import (
    ModelFinishReason,
    ModelInvalidToolCallCode,
    ModelMessage,
    ModelStructuredOutputDiagnostic,
    ModelStructuredOutputRoute,
    ModelToolCall,
    ModelToolRecoveryCode,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
    ProviderProtocolError,
    ProviderTransportError,
)
from .deepseek_strict import prepare_deepseek_tools, schema_validation_errors
from .error_details import (
    FailureDiagnostic,
    capture_failure_diagnostic,
    capture_provider_error_details,
)
from .openai_compatible import (
    StructuredOutputRecoveryCode,
    _append_missing_container_closers,
    _is_official_deepseek_endpoint,
    _log_structured_output_recovery,
    _parse_and_validate_structured_output,
    _resolve_deepseek_strict_base_url,
    normalize_finish_reason,
)


class DeepSeekV4Provider:
    """DeepSeek V4 原始 Chat Completions 传输层。"""

    billable = True
    provider_name = "openai_compatible"
    transport_profile = "transport.deepseek-v4.v1"
    capability_version = "capability.deepseek-v4.chat-json.v1"
    supports_request_idempotency = False

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
            raise ValueError("真实模型提供方缺少 OPENAI_API_KEY")
        self.model_name = settings.openai_model
        self.endpoint_profile = (
            "endpoint.deepseek-official.v1"
            if _is_official_deepseek_endpoint(settings.openai_base_url)
            else "endpoint.deepseek-custom.v1"
        )
        self._endpoint = _completion_endpoint(settings.openai_base_url)
        strict_base_url = _resolve_deepseek_strict_base_url(settings)
        self._strict_endpoint = (
            _completion_endpoint(strict_base_url) if strict_base_url is not None else None
        )
        self._strict_endpoint_profile = (
            "endpoint.deepseek-strict-official.v1"
            if self._strict_endpoint == "https://api.deepseek.com/beta/chat/completions"
            else "endpoint.deepseek-strict-custom.v1"
        )
        self._api_key = settings.openai_api_key.get_secret_value()
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=300, write=60, pool=60)
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        return route in {"chat_json_output_v1", "plain_text_v1"} or (
            route == "quality_strict_tool_v1" and self._strict_endpoint is not None
        )

    def execution_identity(self, route: ModelStructuredOutputRoute) -> tuple[str, str]:
        """质量调用依据真实 strict 端点授权，不借普通 base URL 冒充官方端点。"""
        if route == "plain_text_v1":
            return self.endpoint_profile, "capability.deepseek-v4.plain-text.v1"
        if route == "quality_strict_tool_v1":
            if self._strict_endpoint is None:
                raise ValueError("质量 strict 路由未配置")
            return self._strict_endpoint_profile, "capability.deepseek-v4.quality-strict.v1"
        return self.endpoint_profile, self.capability_version

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        prepared = prepare_deepseek_tools(request, secrets=(self._api_key,))
        request = prepared.request
        structured_output = request.structuredOutput
        structured_validator: jsonschema_rs.Validator | None = None
        if structured_output is not None:
            if structured_output.route != "chat_json_output_v1":
                raise ValueError("DeepSeek V4 原始适配器只支持 chat_json_output_v1")
            if not any("json" in message.content.casefold() for message in request.messages):
                raise ValueError("chat_json_output_v1 的消息正文必须显式包含 json")
            try:
                structured_validator = jsonschema_rs.validator_for(structured_output.jsonSchema)
            except ValueError:
                raise ValueError("structuredOutput.jsonSchema 不是有效的 JSON Schema") from None
        use_strict_endpoint = any(tool.strict for tool in request.tools)
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
        if structured_output is not None:
            payload["response_format"] = {"type": "json_object"}
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
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
        except httpx.TimeoutException as exc:
            transport_error = ProviderTransportError(
                code="timeout_error",
                statusCode=None,
                requestId=None,
                details=capture_provider_error_details(error=exc, secrets=(self._api_key,)),
            )
        except httpx.HTTPError as exc:
            transport_error = ProviderTransportError(
                code="connection_error",
                statusCode=None,
                requestId=None,
                details=capture_provider_error_details(error=exc, secrets=(self._api_key,)),
            )
        # 先采集脱敏详情，再离开捕获块抛出，避免原始请求进入后续异常链。
        if transport_error is not None:
            raise transport_error
        if response is None:
            raise RuntimeError("DeepSeek HTTP 客户端未返回响应")
        if not response.is_success:
            raise ProviderTransportError(
                code="http_error",
                statusCode=response.status_code,
                requestId=_response_request_id(response),
                details=capture_provider_error_details(response=response, secrets=(self._api_key,)),
            )
        protocol_error: ProviderProtocolError | None = None
        try:
            body = response.json()
        except (ValueError, UnicodeError) as exc:
            protocol_error = ProviderProtocolError(
                code="invalid_response_json",
                statusCode=response.status_code,
                requestId=_response_request_id(response),
                details=capture_provider_error_details(
                    response=response,
                    error=exc,
                    secrets=(self._api_key,),
                    include_success_body=True,
                ),
            )
            body = None
        # 与网络错误相同，离开捕获块后再抛出，清除可能携带正文的 JSON 异常上下文。
        if protocol_error is not None:
            raise protocol_error
        parsed_error: ProviderProtocolError | None = None
        try:
            result = _parse_response(
                body,
                request,
                status_code=response.status_code,
                request_id=_response_request_id(response),
                secrets=(self._api_key,),
                business_schemas={
                    name: tool.parameters for name, tool in prepared.originals.items()
                },
            )
        except ProviderProtocolError as exc:
            details = capture_provider_error_details(
                response=response,
                error=exc,
                secrets=(self._api_key,),
                include_success_body=True,
            )
            if exc.details is not None:
                details.exceptionChain.extend(exc.details.exceptionChain)
            exc.details = details
            parsed_error = exc
        if parsed_error is not None:
            raise parsed_error
        if structured_output is not None:
            raw_structured_content = result.content
            if structured_validator is None:
                raise RuntimeError("DeepSeek V4 结构化输出校验器缺失")
            unexpected_tool_output = bool(
                result.toolCalls or result.invalidToolCallCount or result.recoveredToolCallCount
            )
            parsed: dict[str, Any] | None
            diagnostic: ModelStructuredOutputDiagnostic | None
            recovery_code: StructuredOutputRecoveryCode | None
            if unexpected_tool_output:
                parsed = None
                recovery_code = None
                diagnostic = ModelStructuredOutputDiagnostic(
                    code="unexpected_output",
                    jsonPointer="",
                    keyword="toolCalls",
                )
            else:
                parsed, diagnostic, recovery_code = _parse_and_validate_structured_output(
                    raw_text=result.content,
                    structured_output=structured_output,
                    validator=structured_validator,
                )
            if recovery_code == "escape_json_string_controls":
                _log_structured_output_recovery(
                    model_name=self.model_name,
                    structured_output=structured_output,
                    recovery_code=recovery_code,
                    usage=result.usage,
                )
            result = ModelTurnResult.model_validate(
                result.model_dump(mode="python")
                | {
                    "failureDiagnostics": result.failureDiagnostics,
                    "content": "",
                    "reasoningContent": None,
                    "toolCalls": [],
                    "invalidToolCallCount": 0,
                    "invalidToolCallNames": [],
                    "invalidToolCallCodes": [],
                    "invalidToolCallArgumentCharacterCounts": [],
                    "recoveredToolCallCount": 0,
                    "recoveredToolCallCodes": [],
                    "recoveredToolCallAppendedContainerCounts": [],
                    "structuredOutput": parsed,
                    "structuredOutputDiagnostic": diagnostic,
                    "structuredOutputCorrectionCount": (1 if recovery_code is not None else 0),
                }
            )
            if diagnostic is not None:
                structured_error: Exception | None = None
                validation_errors: list[dict[str, Any]] = []
                try:
                    structured_value = _load_strict_json(raw_structured_content)
                    validation_errors = schema_validation_errors(
                        structured_output.jsonSchema,
                        structured_value,
                    )
                except (ValueError, RecursionError) as exc:
                    structured_error = exc
                result.failureDiagnostics.append(
                    capture_failure_diagnostic(
                        stage="provider.structured_output",
                        code=diagnostic.code,
                        payload={
                            "output": body,
                            "expectedSchema": structured_output.jsonSchema,
                            "diagnostic": diagnostic.model_dump(),
                            "validationErrors": validation_errors,
                        },
                        error=structured_error,
                        secrets=(self._api_key,),
                    )
                )
        return prepared.decode_result(result)


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


class _ParsedToolCalls:
    """DeepSeek 工具调用的有效结果、安全失败诊断与恢复审计。"""

    def __init__(self) -> None:
        self.calls: list[ModelToolCall] = []
        self.invalid_names: list[str] = []
        self.invalid_codes: list[ModelInvalidToolCallCode] = []
        self.invalid_argument_character_counts: list[int] = []
        self.recovered_codes: list[ModelToolRecoveryCode] = []
        self.recovered_appended_container_counts: list[int] = []
        self.diagnostics: list[FailureDiagnostic] = []
        self.payload: dict[str, Any] = {}
        self.secrets: tuple[str, ...] = ()

    def add_invalid(
        self,
        *,
        name: str,
        code: ModelInvalidToolCallCode,
        argument_character_count: int,
        stage: str = "tool.envelope",
        error: BaseException | None = None,
    ) -> None:
        self.invalid_names.append(name)
        self.invalid_codes.append(code)
        self.invalid_argument_character_counts.append(argument_character_count)
        self.diagnostics.append(
            capture_failure_diagnostic(
                stage=stage,
                code=code,
                payload=self.payload,
                error=error,
                secrets=self.secrets,
            )
        )


def _parse_response(
    body: object,
    request: ModelTurnRequest,
    *,
    status_code: int,
    request_id: str | None,
    secrets: tuple[str, ...] = (),
    business_schemas: dict[str, dict[str, Any]] | None = None,
) -> ModelTurnResult:
    if not isinstance(body, Mapping):
        raise ProviderProtocolError(
            code="invalid_response_envelope",
            statusCode=status_code,
            requestId=request_id,
        )
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
        raise ProviderProtocolError(
            code="invalid_response_envelope",
            statusCode=status_code,
            requestId=request_id,
        )
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise ProviderProtocolError(
            code="invalid_response_envelope",
            statusCode=status_code,
            requestId=request_id,
        )
    content = message.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise ProviderProtocolError(
            code="invalid_response_envelope",
            statusCode=status_code,
            requestId=request_id,
        )
    usage_protocol_error: ProviderProtocolError | None = None
    try:
        usage = _parse_usage(body.get("usage"))
    except ValueError as exc:
        usage_protocol_error = ProviderProtocolError(
            code="invalid_usage",
            statusCode=status_code,
            requestId=request_id,
            details=capture_provider_error_details(error=exc, secrets=secrets),
        )
        usage = None
    if usage_protocol_error is not None:
        raise usage_protocol_error
    usage = cast(tuple[ModelUsage, ModelUsageDiagnostics], usage)
    parsed_tool_calls = _parse_tool_calls(
        message.get("tool_calls", []), request, secrets=secrets, business_schemas=business_schemas
    )
    raw_reason = choice.get("finish_reason")
    normalized: ModelFinishReason = normalize_finish_reason(raw_reason)
    envelope_protocol_error: ProviderProtocolError | None = None
    try:
        reasoning_content = _optional_text(message.get("reasoning_content"))
        response_id = _optional_text(body.get("id"))
    except ValueError as exc:
        envelope_protocol_error = ProviderProtocolError(
            code="invalid_response_envelope",
            statusCode=status_code,
            requestId=request_id,
            details=capture_provider_error_details(error=exc, secrets=secrets),
        )
        reasoning_content = None
        response_id = None
    if envelope_protocol_error is not None:
        raise envelope_protocol_error
    return ModelTurnResult(
        content=content,
        reasoningContent=reasoning_content,
        toolCalls=parsed_tool_calls.calls,
        failureDiagnostics=parsed_tool_calls.diagnostics,
        invalidToolCallCount=len(parsed_tool_calls.invalid_codes),
        invalidToolCallNames=parsed_tool_calls.invalid_names,
        invalidToolCallCodes=parsed_tool_calls.invalid_codes,
        invalidToolCallArgumentCharacterCounts=(
            parsed_tool_calls.invalid_argument_character_counts
        ),
        recoveredToolCallCount=len(parsed_tool_calls.recovered_codes),
        recoveredToolCallCodes=parsed_tool_calls.recovered_codes,
        recoveredToolCallAppendedContainerCounts=(
            parsed_tool_calls.recovered_appended_container_counts
        ),
        providerResponseId=response_id,
        usage=usage[0],
        diagnostics=usage[1],
        finishReason=normalized,
        rawFinishReason=_raw_reason(raw_reason),
        effectiveMaxOutputTokens=request.maxOutputTokens,
    )


def _parse_tool_calls(
    raw: object,
    request: ModelTurnRequest,
    *,
    secrets: tuple[str, ...] = (),
    business_schemas: dict[str, dict[str, Any]] | None = None,
) -> _ParsedToolCalls:
    result = _ParsedToolCalls()
    result.secrets = secrets
    result.payload = {"toolCalls": raw}
    if raw is None:
        return result
    if not isinstance(raw, list):
        result.add_invalid(
            name="未知工具",
            code="unknown_invalid_tool_call",
            argument_character_count=0,
        )
        return result
    requested_by_name = {tool.name: tool for tool in request.tools}
    for item in raw:
        result.payload = {"toolCall": item}
        if not isinstance(item, Mapping):
            result.add_invalid(
                name="未知工具",
                code="unknown_invalid_tool_call",
                argument_character_count=0,
            )
            continue
        call_id = item.get("id")
        function = item.get("function")
        if not isinstance(function, Mapping):
            result.add_invalid(
                name="未知工具",
                code="unknown_invalid_tool_call",
                argument_character_count=0,
            )
            continue
        name = function.get("name")
        raw_arguments = function.get("arguments")
        result.payload = {
            "toolName": name,
            "callId": call_id,
            "rawArguments": raw_arguments,
            "wireSchema": requested_by_name[name].parameters
            if isinstance(name, str) and name in requested_by_name
            else None,
            "businessSchema": (business_schemas or {}).get(name) if isinstance(name, str) else None,
        }
        argument_character_count = len(raw_arguments) if isinstance(raw_arguments, str) else 0
        safe_name = name if isinstance(name, str) and name in requested_by_name else "未知工具"
        if not isinstance(name, str) or not name.strip():
            result.add_invalid(
                name="未知工具",
                code="missing_tool_name",
                argument_character_count=argument_character_count,
            )
            continue
        if not isinstance(call_id, str) or not call_id.strip():
            result.add_invalid(
                name=safe_name,
                code="unknown_invalid_tool_call",
                argument_character_count=argument_character_count,
            )
            continue
        if not isinstance(raw_arguments, str):
            result.add_invalid(
                name=safe_name,
                code="unknown_invalid_tool_call",
                argument_character_count=0,
            )
            continue
        try:
            arguments = _load_strict_json(raw_arguments)
        except (ValueError, RecursionError) as exc:
            recovery = (
                _recover_deepseek_tool_call(
                    call_id=call_id,
                    name=name,
                    raw_arguments=raw_arguments,
                    schema=requested_by_name[name].parameters,
                )
                if name in requested_by_name
                else None
            )
            if recovery is not None:
                recovered_call, appended_container_count = recovery
                result.calls.append(recovered_call)
                result.recovered_codes.append("append_container_closers")
                result.recovered_appended_container_counts.append(appended_container_count)
                repaired = _append_missing_container_closers(raw_arguments)
                result.diagnostics.append(
                    capture_failure_diagnostic(
                        stage="tool.json_recovery",
                        code="append_container_closers",
                        error=exc,
                        payload={
                            **result.payload,
                            "repairedArguments": repaired[0] if repaired else None,
                            "appendedContainerCount": appended_container_count,
                        },
                        secrets=secrets,
                    )
                )
                continue
            result.add_invalid(
                name=safe_name,
                code="json_decode_error",
                argument_character_count=argument_character_count,
                stage="tool.json_parse",
                error=exc,
            )
            continue
        if not isinstance(arguments, dict):
            result.add_invalid(
                name=safe_name,
                code="unknown_invalid_tool_call",
                argument_character_count=argument_character_count,
            )
            continue
        if name not in requested_by_name:
            result.add_invalid(
                name="未知工具",
                code="unknown_invalid_tool_call",
                argument_character_count=argument_character_count,
            )
            continue
        requested_tool = requested_by_name[name]
        if requested_tool.strict:
            try:
                jsonschema_rs.validate(requested_tool.parameters, arguments)
            except ValueError as exc:
                result.payload["validationErrors"] = schema_validation_errors(
                    requested_tool.parameters,
                    arguments,
                )
                result.add_invalid(
                    name=safe_name,
                    code="provider_strict_schema_violation",
                    argument_character_count=argument_character_count,
                    stage="tool.wire_schema",
                    error=exc,
                )
                continue
        result.calls.append(ModelToolCall(id=call_id, name=name, arguments=arguments))
    return result


def _recover_deepseek_tool_call(
    *,
    call_id: str,
    name: str,
    raw_arguments: str,
    schema: dict[str, Any],
) -> tuple[ModelToolCall, int] | None:
    """只追加缺失容器闭合符，并以本轮原始 Schema 复验。"""

    repaired = _append_missing_container_closers(raw_arguments)
    if repaired is None:
        return None
    candidate, appended_container_count = repaired
    try:
        parsed = _load_strict_json(candidate)
    except (ValueError, RecursionError):
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        jsonschema_rs.validate(schema, parsed)
    except ValueError:
        return None
    return (
        ModelToolCall(id=call_id, name=name, arguments=parsed),
        appended_container_count,
    )


def _load_strict_json(value: str) -> object:
    """拒绝 Python JSON 解码器默认接受的 NaN/Infinity 非标准常量。"""

    def reject_nonstandard_constant(_: str) -> None:
        raise ValueError("工具参数包含非标准 JSON 常量")

    return json.loads(value, parse_constant=reject_nonstandard_constant)


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
