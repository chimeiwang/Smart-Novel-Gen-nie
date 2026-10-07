from __future__ import annotations

import json
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
    value = re.sub(r"https?://[^\s\"'<>]+", lambda match: _redact_url(match.group()), value)
    # Cookie 的分号分隔片段都属于凭据；带引号的值按完整边界匹配，保留同一行其他诊断。
    quoted = r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')"""
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


class _JsonPairs(list[tuple[str, Any]]):
    """保留错误 JSON 中的重复键，避免字典解析静默覆盖供应商诊断。"""


def _render_json(value: Any, secrets: tuple[str, ...]) -> str:
    if isinstance(value, _JsonPairs):
        return (
            "{"
            + ", ".join(
                json.dumps(_redact_text(key, secrets), ensure_ascii=False)
                + ": "
                + (
                    json.dumps(_REDACTED, ensure_ascii=False)
                    if _sensitive(key)
                    else _render_json(item, secrets)
                )
                for key, item in value
            )
            + "}"
        )
    if isinstance(value, list):
        return "[" + ", ".join(_render_json(item, secrets) for item in value) + "]"
    return json.dumps(
        _redact_text(value, secrets) if isinstance(value, str) else value, ensure_ascii=False
    )


def capture_provider_error_details(
    *,
    response: httpx.Response | None = None,
    error: BaseException | None = None,
    secrets: tuple[str, ...] = (),
) -> ProviderErrorDetails:
    """在异常清链前采集失败；不复制请求内容、成功模型正文或调用栈局部变量。"""
    try:
        return _capture_details(response=response, error=error, secrets=secrets)
    except Exception as failure:
        # 详情采集只是辅助证据；不可用时保留明确分类，绝不覆盖原供应商错误。
        return ProviderErrorDetails(captureFailure=type(failure).__name__)


def _capture_details(
    *,
    response: httpx.Response | None,
    error: BaseException | None,
    secrets: tuple[str, ...],
) -> ProviderErrorDetails:
    details = ProviderErrorDetails()
    if response is not None:
        details.statusCode = response.status_code
        details.responseHeaders = [
            (name, _REDACTED if _sensitive(name) else _redact_text(value, secrets))
            for name, value in response.headers.multi_items()
        ]
        if not response.is_success:
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
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        try:
            message = str(error)
        except Exception as failure:
            message = f"无法格式化异常消息（{type(failure).__name__}）"
        try:
            stack = "".join(traceback.format_tb(error.__traceback__))
        except Exception as failure:
            stack = f"无法读取调用栈（{type(failure).__name__}）"
        details.exceptionChain.append(
            ProviderExceptionDetails(
                type=type(error).__name__,
                message=_redact_text(message, secrets),
                traceback=_redact_text(stack, secrets),
            )
        )
        if details.requestUrl is None:
            try:
                request = getattr(error, "request", None)
            except RuntimeError:
                request = None
            if isinstance(request, httpx.Request):
                details.requestMethod = request.method
                details.requestUrl = _redact_text(_redact_url(str(request.url)), secrets)
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    return details
