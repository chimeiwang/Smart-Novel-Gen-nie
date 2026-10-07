from __future__ import annotations

import json
import logging
import re
import traceback
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

_REDACTED = "[已脱敏]"
_SENSITIVE = re.compile(
    r"(?:authorization|cookie|apikey|accesskey|secret|secretkey|password|passwd|"
    r"credential|credentials|token)$",
    re.IGNORECASE,
)


class ProviderExceptionDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    message: str
    traceback: str


class ProviderErrorDetails(BaseModel):
    """完整失败诊断只供服务日志使用，不进入公共错误或业务状态。"""

    model_config = ConfigDict(extra="forbid")

    statusCode: int | None = None
    responseBody: str | None = None
    responseHeaders: list[tuple[str, str]] = Field(default_factory=list)
    requestMethod: str | None = None
    requestUrl: str | None = None
    exceptionChain: list[ProviderExceptionDetails] = Field(default_factory=list)
    captureFailure: str | None = None


class FailureDiagnostic(BaseModel):
    """仅在进程内传递给日志层，不能作为业务结果或模型纠正输入。"""

    model_config = ConfigDict(extra="forbid")

    stage: str
    code: str
    payloadJson: str | None = None
    errorDetails: ProviderErrorDetails | None = None
    captureFailure: str | None = None


def _json_default(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="backslashreplace")
    if isinstance(value, BaseException):
        details = capture_provider_error_details(error=value, secrets=secrets)
        return details.exceptionChain[0].message if details.exceptionChain else "异常详情不可用"
    return str(value)


def _collect_credential_values(payload: Any) -> tuple[str, ...]:
    """校验错误会在 input 和异常文本再次回显凭据，必须先从字段语义收集再全局遮盖。"""
    found: set[str] = set()
    pending: list[tuple[Any, bool, bool]] = [(payload, False, False)]
    seen: set[int] = set()
    while pending:
        value, sensitive, business_input = pending.pop()
        if isinstance(value, str):
            if sensitive and value:
                found.add(value)
            elif value.lstrip().startswith(("{", "[")):
                try:
                    pending.append((json.loads(value, object_pairs_hook=_JsonPairs), False, True))
                except (ValueError, RecursionError):
                    pass
            continue
        if sensitive and isinstance(value, (int, float)) and not isinstance(value, bool):
            found.add(str(value))
            continue
        if isinstance(value, (dict, list, tuple, BaseModel)):
            if id(value) in seen:
                continue
            seen.add(id(value))
        if isinstance(value, BaseModel):
            pending.append((value.model_dump(mode="python"), sensitive, business_input))
        elif isinstance(value, (dict, _JsonPairs)):
            pairs = list(value.items()) if isinstance(value, dict) else value
            as_dict = dict(pairs)
            location = as_dict.get("loc", as_dict.get("instancePath", []))
            sensitive_location = isinstance(location, (list, tuple)) and any(
                isinstance(part, str) and _sensitive(part) for part in location
            )
            for key, item in pairs:
                key = str(key)
                if not business_input and key.lower().endswith(("schema", "schemas")):
                    continue
                pending.append(
                    (
                        item,
                        sensitive
                        or _sensitive(key)
                        or (sensitive_location and key in {"input", "instance"}),
                        business_input or key in {"arguments", "rawArguments", "input", "instance"},
                    )
                )
        elif isinstance(value, (list, tuple)):
            pending.extend((item, sensitive, business_input) for item in value)
    return tuple(found)


def capture_failure_diagnostic(
    *,
    stage: str,
    code: str,
    payload: Any = None,
    error: BaseException | None = None,
    details: ProviderErrorDetails | None = None,
    secrets: tuple[str, ...] = (),
) -> FailureDiagnostic:
    """完整失败证据统一脱敏；辅助采集故障不能替换原异常。"""
    diagnostic = FailureDiagnostic(stage=stage, code=code)
    try:
        secret_sources = [payload]
        errors = getattr(error, "errors", None)
        if callable(errors):
            try:
                validation_errors = errors()
                secret_sources.append(validation_errors)
                # Pydantic 的异常字符串会裁剪输入，完整结构必须独立写入诊断正文。
                if isinstance(payload, dict):
                    if "validationErrors" not in payload:
                        payload = {**payload, "validationErrors": validation_errors}
                else:
                    payload = {"evidence": payload, "validationErrors": validation_errors}
            except Exception as failure:
                diagnostic.captureFailure = type(failure).__name__
        secrets = (*secrets, *_collect_credential_values(secret_sources))
        if payload is not None:
            parsed = json.loads(
                json.dumps(
                    payload, ensure_ascii=False, default=lambda item: _json_default(item, secrets)
                ),
                object_pairs_hook=_JsonPairs,
            )
            diagnostic.payloadJson = _render_json(parsed, secrets, schema_fields=True)
        if details is not None:
            safe_details = _render_json(
                json.loads(details.model_dump_json(), object_pairs_hook=_JsonPairs), secrets
            )
            diagnostic.errorDetails = ProviderErrorDetails.model_validate_json(safe_details)
        elif error is not None:
            diagnostic.errorDetails = capture_provider_error_details(error=error, secrets=secrets)
    except Exception as failure:
        diagnostic.captureFailure = type(failure).__name__
    return diagnostic


def log_failure_diagnostic(
    logger: logging.Logger,
    diagnostic: FailureDiagnostic,
    **identity: Any,
) -> None:
    """JSON 单行输出避免诊断正文伪造日志，sink 故障不改变执行结果。"""
    try:
        record = capture_failure_diagnostic(
            stage=diagnostic.stage, code=diagnostic.code, payload=identity
        )
        logger.warning(
            "完整失败诊断 identity=%s diagnostic=%s",
            record.payloadJson,
            diagnostic.model_dump_json(),
        )
    except Exception:  # noqa: S110 - 日志 sink 不可用时不能再次触发同一 sink。
        pass


def _sensitive(name: str) -> bool:
    return bool(_SENSITIVE.search(re.sub(r"[^a-zA-Z]", "", name)))


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        netloc = parts.netloc.rsplit("@", 1)[-1]
        query = urlencode(
            [
                (key, _REDACTED if _sensitive(key) else item)
                for key, item in parse_qsl(parts.query, keep_blank_values=True)
            ]
        )
        return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
    except ValueError:
        return _REDACTED


def _redact_text(value: str, secrets: tuple[str, ...]) -> str:
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        value = value.replace(secret, _REDACTED)
    value = re.sub(r"(?i)\bBearer\s+[^\s\"'<>;,]+", "Bearer " + _REDACTED, value)
    value = re.sub(
        r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+", lambda match: _redact_url(match.group()), value
    )
    # Cookie 的分号分隔片段都属于凭据；带引号的值按完整边界匹配，保留同一行其他诊断。
    quoted = r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')"""
    value = _strip_reasoning_objects(value)
    value = re.sub(
        r"(?i)(\breasoning[_-]?content\b[\"']?\s*[:=]\s*)(" + quoted + r"|[^\r\n<]+)",
        lambda match: match.group(1) + "[推理内容已排除]",
        value,
    )
    value = re.sub(
        r"(?i)(\b(?:cookie|set-cookie)\b[\"']?\s*[:=]\s*)(" + quoted + r"|[^\r\n<]+)",
        lambda match: match.group(1) + _REDACTED,
        value,
    )
    # 同一敏感字段分类用于 JSON、请求地址和自由文本；普通 token 统计字段保持完整。
    value = re.sub(
        r"(?i)(\b(?P<name>[\w.-]*(?:authorization|cookie|api[_-]?key|access[_-]?key|"
        r"secret(?:[_-]?key)?|password|passwd|credentials?|token))[\"']?\s*[:=]\s*)("
        + quoted
        + r"|[^\r\n;,<]+)",
        lambda match: (
            match.group(1) + _REDACTED if _sensitive(match.group("name")) else match.group()
        ),
        value,
    )
    return value


def _strip_reasoning_objects(value: str) -> str:
    """坏 JSON 无法结构解析时，仍按不受字符串括号影响的对象边界排除推理项。"""
    matches = list(re.finditer(r'"type"\s*:\s*"reasoning"', value))
    if not matches:
        return value
    opened: list[int] = []
    ranges: list[tuple[int, int]] = []
    quoted = False
    escaped = False
    for index, character in enumerate(value):
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character == "{":
            opened.append(index)
        elif character == "}" and opened:
            ranges.append((opened.pop(), index + 1))
    ranges.extend((start, len(value)) for start in opened)
    removed = set()
    for match in matches:
        candidates = [
            (start, end) for start, end in ranges if start <= match.start() and end >= match.end()
        ]
        if candidates:
            removed.add(max(candidates))
    for start, end in sorted(removed, reverse=True):
        value = value[:start] + '"[推理内容已排除]"' + value[end:]
    return value


class _JsonPairs(list[tuple[str, Any]]):
    """保留错误 JSON 中的重复键，避免字典解析静默覆盖供应商诊断。"""


def _render_json(
    value: Any, secrets: tuple[str, ...], *, schema: bool = False, schema_fields: bool = False
) -> str:
    if isinstance(value, _JsonPairs):
        location = dict(value).get("loc", dict(value).get("instancePath", []))
        sensitive_location = isinstance(location, (list, tuple)) and any(
            isinstance(part, str) and _sensitive(part) for part in location
        )
        if any(key == "type" and item == "reasoning" for key, item in value):
            return json.dumps("[推理内容已排除]", ensure_ascii=False)
        return (
            "{"
            + ", ".join(
                json.dumps(_redact_text(key, secrets), ensure_ascii=False)
                + ": "
                + (
                    json.dumps(_REDACTED, ensure_ascii=False)
                    if not schema
                    and (_sensitive(key) or (sensitive_location and key in {"input", "instance"}))
                    else _render_json(
                        item,
                        secrets,
                        schema=(
                            schema
                            or (
                                schema_fields
                                and key
                                in {
                                    "wireSchema",
                                    "businessSchema",
                                    "expectedSchema",
                                    "schema",
                                    "outputSchema",
                                }
                            )
                        ),
                    )
                )
                for key, item in value
                if re.sub(r"[^a-zA-Z]", "", key).lower() != "reasoningcontent"
            )
            + "}"
        )
    if isinstance(value, list):
        return "[" + ", ".join(_render_json(item, secrets, schema=schema) for item in value) + "]"
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(value, object_pairs_hook=_JsonPairs)
            rendered = _render_json(parsed, secrets)
            # 无脱敏变化时保留原 arguments 的空白、顺序与完整原文。
            if json.loads(rendered, object_pairs_hook=_JsonPairs) != parsed:
                value = rendered
        except (ValueError, RecursionError):
            pass
    if isinstance(value, (int, float)) and not isinstance(value, bool) and str(value) in secrets:
        return json.dumps(_REDACTED, ensure_ascii=False)
    return json.dumps(
        _redact_text(value, secrets) if isinstance(value, str) else value, ensure_ascii=False
    )


def capture_provider_error_details(
    *,
    response: httpx.Response | None = None,
    error: BaseException | None = None,
    secrets: tuple[str, ...] = (),
    include_success_body: bool = False,
) -> ProviderErrorDetails:
    """在异常清链前采集失败；不复制请求内容、成功模型正文或调用栈局部变量。"""
    try:
        return _capture_details(
            response=response,
            error=error,
            secrets=secrets,
            include_success_body=include_success_body,
        )
    except Exception as failure:
        # 详情采集只是辅助证据；不可用时保留明确分类，绝不覆盖原供应商错误。
        return ProviderErrorDetails(captureFailure=type(failure).__name__)


def _capture_details(
    *,
    response: httpx.Response | None,
    error: BaseException | None,
    secrets: tuple[str, ...],
    include_success_body: bool,
) -> ProviderErrorDetails:
    details = ProviderErrorDetails()
    if response is not None:
        details.statusCode = response.status_code
        details.responseHeaders = [
            (name, _REDACTED if _sensitive(name) else _redact_text(value, secrets))
            for name, value in response.headers.multi_items()
        ]
        if not response.is_success or include_success_body:
            try:
                body = response.content.decode(
                    response.encoding or "utf-8", errors="backslashreplace"
                )
            except LookupError:
                body = response.content.decode("utf-8", errors="backslashreplace")
            try:
                parsed = json.loads(body, object_pairs_hook=_JsonPairs)
                rendered = _render_json(parsed, secrets)
            except (ValueError, RecursionError):
                details.responseBody = _redact_text(body, secrets)
            else:
                details.responseBody = rendered
        try:
            request = response.request
        except RuntimeError:
            request = None
        if request is not None:
            details.requestMethod = request.method
            details.requestUrl = _redact_text(_redact_url(str(request.url)), secrets)
    seen: set[int] = set()
    pending: list[BaseException] = [error] if error is not None else []
    while pending:
        error = pending.pop(0)
        if id(error) in seen:
            continue
        seen.add(id(error))
        cached = getattr(error, "_inkforgeExceptionDetails", None)
        if isinstance(cached, ProviderExceptionDetails):
            message, stack = cached.message, cached.traceback
        else:
            try:
                message = str(error)
            except Exception as failure:
                message = f"无法格式化异常消息（{type(failure).__name__}）"
            try:
                stack = "".join(traceback.format_tb(error.__traceback__))
            except Exception as failure:
                stack = f"无法读取调用栈（{type(failure).__name__}）"
        entry = ProviderExceptionDetails(
            type=type(error).__name__,
            message=_redact_text(message, secrets),
            traceback=_redact_text(stack, secrets),
        )
        # 上层无供应商凭据时复用安全证据；不缓存原值，也不修改公开异常文本。
        try:
            error._inkforgeExceptionDetails = entry  # type: ignore[attr-defined]
        except Exception:
            details.captureFailure = "exception_cache_unavailable"
        details.exceptionChain.append(entry)
        metadata = getattr(error, "_inkforgeRequestMetadata", None)
        if isinstance(metadata, tuple) and len(metadata) == 2:
            method, request_url = metadata
            metadata = (method, _redact_text(request_url, secrets))
        else:
            try:
                request = getattr(error, "request", None)
            except RuntimeError:
                request = None
            if isinstance(request, httpx.Request):
                metadata = (request.method, _redact_text(_redact_url(str(request.url)), secrets))
        if metadata is not None:
            try:
                error._inkforgeRequestMetadata = metadata  # type: ignore[attr-defined]
            except Exception:
                details.captureFailure = "request_metadata_cache_unavailable"
            if details.requestUrl is None:
                details.requestMethod, details.requestUrl = metadata
        cause = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
        if cause is not None:
            pending.append(cause)
        if isinstance(error, BaseExceptionGroup):
            pending.extend(error.exceptions)
    return details
