from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
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
from .openai_compatible import (
    _append_missing_container_closers,
    _is_official_deepseek_endpoint,
    _parse_and_validate_structured_output,
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
_QUALITY_TOOL_NAME = "submit_quality_report"
_QUALITY_OPTIONAL_STRING_PATHS = {
    ("properties", "rewriteBrief"),
    ("properties", "issues", "items", "properties", "location"),
}


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
        self._api_key = settings.openai_api_key.get_secret_value()
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=300, write=60, pool=60)
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        return route == "chat_json_output_v1"

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
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
        strict_tool_count = sum(tool.strict for tool in request.tools)
        if 0 < strict_tool_count < len(request.tools):
            raise ValueError("DeepSeek 工具请求不能混用 strict 与非 strict 函数")
        use_strict_endpoint = strict_tool_count > 0
        if use_strict_endpoint:
            if self._strict_endpoint is None:
                raise ValueError("DeepSeek strict 工具请求缺少 OPENAI_STRICT_BASE_URL")
            if len(request.tools) != 1 or request.tools[0].name != _QUALITY_TOOL_NAME:
                raise ValueError("DeepSeek strict 当前只支持 submit_quality_report")
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
                        "parameters": (
                            _project_deepseek_quality_schema(tool.parameters)
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
        protocol_error: ProviderProtocolError | None = None
        try:
            body = response.json()
        except (ValueError, UnicodeError):
            protocol_error = ProviderProtocolError(
                code="invalid_response_json",
                statusCode=response.status_code,
                requestId=_response_request_id(response),
            )
            body = None
        # 与网络错误相同，离开捕获块后再抛出，清除可能携带正文的 JSON 异常上下文。
        if protocol_error is not None:
            raise protocol_error
        result = _parse_response(
            body,
            request,
            status_code=response.status_code,
            request_id=_response_request_id(response),
        )
        if structured_output is not None:
            if structured_validator is None:
                raise RuntimeError("DeepSeek V4 结构化输出校验器缺失")
            unexpected_tool_output = bool(
                result.toolCalls or result.invalidToolCallCount or result.recoveredToolCallCount
            )
            parsed: dict[str, Any] | None
            diagnostic: ModelStructuredOutputDiagnostic | None
            recovery_code: str | None
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
            result = ModelTurnResult.model_validate(
                result.model_dump(mode="python")
                | {
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
        return _normalize_deepseek_quality_result(result) if use_strict_endpoint else result


def _project_deepseek_quality_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """把质量报告 Schema 收敛为无引用、无 null 的 DeepSeek strict 方言。"""

    definitions = schema.get("$defs")
    if not isinstance(definitions, Mapping):
        raise ValueError("质量报告 Schema 缺少 $defs")
    inlined = _inline_quality_schema_node(schema, definitions, stack=())
    normalized, optional_paths = _replace_quality_nullable_strings(inlined, path=())
    if optional_paths != _QUALITY_OPTIONAL_STRING_PATHS:
        raise ValueError("质量报告 Schema 可选字符串路径不符合预期")
    if not isinstance(normalized, Mapping):
        raise ValueError("质量报告 Schema 根节点必须是对象")
    projected = _project_deepseek_strict_schema(normalized)
    _apply_quality_wire_descriptions(projected)
    return projected


def _inline_quality_schema_node(
    node: object,
    definitions: Mapping[str, Any],
    *,
    stack: tuple[str, ...],
) -> object:
    if isinstance(node, list):
        return [_inline_quality_schema_node(item, definitions, stack=stack) for item in node]
    if not isinstance(node, Mapping):
        return deepcopy(node)
    if "$ref" in node:
        if len(node) != 1:
            raise ValueError("质量报告 Schema 引用节点不能携带其他约束")
        reference = node["$ref"]
        prefix = "#/$defs/"
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise ValueError("质量报告 Schema 只允许本地 $defs 引用")
        name = reference.removeprefix(prefix)
        if not name or "/" in name or name not in definitions:
            raise ValueError("质量报告 Schema 引用目标不存在")
        if name in stack:
            raise ValueError("质量报告 Schema 不能包含循环引用")
        return _inline_quality_schema_node(
            definitions[name],
            definitions,
            stack=(*stack, name),
        )
    return {
        str(key): _inline_quality_schema_node(value, definitions, stack=stack)
        for key, value in node.items()
        if key != "$defs"
    }


def _replace_quality_nullable_strings(
    node: object,
    *,
    path: tuple[str, ...],
) -> tuple[object, set[tuple[str, ...]]]:
    if isinstance(node, list):
        values: list[object] = []
        found: set[tuple[str, ...]] = set()
        for index, item in enumerate(node):
            normalized, child_found = _replace_quality_nullable_strings(
                item,
                path=(*path, str(index)),
            )
            values.append(normalized)
            found.update(child_found)
        return values, found
    if not isinstance(node, Mapping):
        return deepcopy(node), set()
    string_branch = _nullable_string_branch(node)
    if string_branch is not None:
        if path not in _QUALITY_OPTIONAL_STRING_PATHS:
            raise ValueError("质量报告 Schema 出现未登记的可空字符串")
        return deepcopy(string_branch), {path}
    normalized_mapping: dict[str, object] = {}
    found = set()
    for key, value in node.items():
        if key == "properties" and isinstance(value, Mapping):
            properties: dict[str, object] = {}
            for property_name, property_schema in value.items():
                normalized, child_found = _replace_quality_nullable_strings(
                    property_schema,
                    path=(*path, "properties", str(property_name)),
                )
                properties[str(property_name)] = normalized
                found.update(child_found)
            normalized_mapping[key] = properties
        elif key == "items":
            normalized, child_found = _replace_quality_nullable_strings(
                value,
                path=(*path, "items"),
            )
            normalized_mapping[key] = normalized
            found.update(child_found)
        else:
            normalized, child_found = _replace_quality_nullable_strings(
                value,
                path=(*path, str(key)),
            )
            normalized_mapping[str(key)] = normalized
            found.update(child_found)
    return normalized_mapping, found


def _nullable_string_branch(node: Mapping[str, Any]) -> Mapping[str, Any] | None:
    branches = node.get("anyOf")
    if not isinstance(branches, list) or len(branches) != 2:
        return None
    string_branches = [
        branch
        for branch in branches
        if isinstance(branch, Mapping) and branch.get("type") == "string"
    ]
    null_branches = [
        branch
        for branch in branches
        if isinstance(branch, Mapping) and branch.get("type") == "null"
    ]
    return string_branches[0] if len(string_branches) == len(null_branches) == 1 else None


def _apply_quality_wire_descriptions(schema: dict[str, Any]) -> None:
    try:
        properties = schema["properties"]
        issues = properties["issues"]
        issue_properties = issues["items"]["properties"]
    except (KeyError, TypeError) as exc:
        raise ValueError("质量报告 Schema 结构不符合预期") from exc
    descriptions = {
        "message": "1～500 字。",
        "evidence": "1～1000 字。",
        "location": "0～200 字；无明确位置时返回空字符串。",
        "suggestion": "1～1000 字。",
    }
    for field, description in descriptions.items():
        target = issue_properties.get(field)
        if not isinstance(target, dict):
            raise ValueError("质量报告 issue Schema 结构不符合预期")
        target["description"] = description
    issues["description"] = "最多 100 项；没有问题时返回空数组。"
    report = properties.get("report")
    rewrite_brief = properties.get("rewriteBrief")
    if not isinstance(report, dict) or not isinstance(rewrite_brief, dict):
        raise ValueError("质量报告文本 Schema 结构不符合预期")
    report["description"] = "非空完整一致性终检报告。"
    rewrite_brief["description"] = "0～1000 字；无需返工时返回空字符串。"


def _normalize_deepseek_quality_arguments(
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """只归一化 quality wire 中约定的两个可选字符串。"""

    normalized = deepcopy(dict(arguments))
    if normalized.get("rewriteBrief") == "":
        normalized["rewriteBrief"] = None
    issues = normalized.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            if isinstance(issue, dict) and issue.get("location") == "":
                issue["location"] = None
    return normalized


def _normalize_deepseek_quality_result(result: ModelTurnResult) -> ModelTurnResult:
    calls = [
        call.model_copy(update={"arguments": _normalize_deepseek_quality_arguments(call.arguments)})
        if call.name == _QUALITY_TOOL_NAME
        else call
        for call in result.toolCalls
    ]
    return result.model_copy(update={"toolCalls": calls})


def _project_deepseek_strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """将业务 JSON Schema 投影为 DeepSeek strict 支持的确定性子集。"""

    projected = _project_deepseek_strict_schema_node(schema)
    if not isinstance(projected, dict):
        raise ValueError("DeepSeek strict Schema 根节点必须是对象")
    return projected


def _project_deepseek_strict_schema_node(node: object) -> object:
    """递归投影 Schema 节点，同时保留 JSON Schema 布尔节点。"""

    if not isinstance(node, Mapping):
        if isinstance(node, list):
            return [_project_deepseek_strict_schema_node(item) for item in node]
        return deepcopy(node)

    projected: dict[str, Any] = {}
    for key in _DEEPSEEK_STRICT_SCHEMA_KEYS:
        if key not in node:
            continue
        value = node[key]
        if key in {"properties", "$defs"} and isinstance(value, Mapping):
            projected[key] = {
                property_name: _project_deepseek_strict_schema_node(property_schema)
                for property_name, property_schema in value.items()
            }
        elif key in {"anyOf", "items", "additionalProperties"}:
            projected[key] = _project_deepseek_strict_schema_node(value)
        else:
            projected[key] = deepcopy(value)

    if projected.get("type") == "object":
        properties = projected.get("properties")
        # 非法 properties 不被放宽为可接收额外字段，保持 strict 约束并让供应商拒绝坏 Schema。
        projected["required"] = list(properties) if isinstance(properties, Mapping) else []
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


class _ParsedToolCalls:
    """DeepSeek 工具调用的有效结果、安全失败诊断与恢复审计。"""

    def __init__(self) -> None:
        self.calls: list[ModelToolCall] = []
        self.invalid_names: list[str] = []
        self.invalid_codes: list[ModelInvalidToolCallCode] = []
        self.invalid_argument_character_counts: list[int] = []
        self.recovered_codes: list[ModelToolRecoveryCode] = []
        self.recovered_appended_container_counts: list[int] = []

    def add_invalid(
        self,
        *,
        name: str,
        code: ModelInvalidToolCallCode,
        argument_character_count: int,
    ) -> None:
        self.invalid_names.append(name)
        self.invalid_codes.append(code)
        self.invalid_argument_character_counts.append(argument_character_count)


def _parse_response(
    body: object,
    request: ModelTurnRequest,
    *,
    status_code: int,
    request_id: str | None,
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
    except ValueError:
        usage_protocol_error = ProviderProtocolError(
            code="invalid_usage",
            statusCode=status_code,
            requestId=request_id,
        )
        usage = None
    if usage_protocol_error is not None:
        raise usage_protocol_error
    usage = cast(tuple[ModelUsage, ModelUsageDiagnostics], usage)
    parsed_tool_calls = _parse_tool_calls(message.get("tool_calls", []), request)
    raw_reason = choice.get("finish_reason")
    normalized: ModelFinishReason = normalize_finish_reason(raw_reason)
    envelope_protocol_error: ProviderProtocolError | None = None
    try:
        reasoning_content = _optional_text(message.get("reasoning_content"))
        response_id = _optional_text(body.get("id"))
    except ValueError:
        envelope_protocol_error = ProviderProtocolError(
            code="invalid_response_envelope",
            statusCode=status_code,
            requestId=request_id,
        )
        reasoning_content = None
        response_id = None
    if envelope_protocol_error is not None:
        raise envelope_protocol_error
    return ModelTurnResult(
        content=content,
        reasoningContent=reasoning_content,
        toolCalls=parsed_tool_calls.calls,
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
) -> _ParsedToolCalls:
    result = _ParsedToolCalls()
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
        except (ValueError, RecursionError):
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
                continue
            result.add_invalid(
                name=safe_name,
                code="json_decode_error",
                argument_character_count=argument_character_count,
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
            except ValueError:
                result.add_invalid(
                    name=safe_name,
                    code="provider_strict_schema_violation",
                    argument_character_count=argument_character_count,
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
