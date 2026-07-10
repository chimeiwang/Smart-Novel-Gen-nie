from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, JsonValue
from starlette.exceptions import HTTPException

from .http.request_id import get_request_id


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: JsonValue | None
    requestId: str


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: JsonValue | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)


async def handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):
        return _error_response(request, 500, "INTERNAL_SERVER_ERROR", "服务器内部错误")
    return _error_response(
        request,
        exc.status_code,
        exc.code,
        exc.message,
        exc.details,
    )


async def handle_request_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return _error_response(request, 500, "INTERNAL_SERVER_ERROR", "服务器内部错误")

    details: list[JsonValue] = []
    for error in exc.errors():
        error_type = str(error.get("type", "validation_error"))
        details.append(
            {
                "path": [str(item) if not isinstance(item, int) else item for item in error["loc"]],
                "message": _translate_validation_message(error_type, error.get("ctx")),
                "type": error_type,
            }
        )
    return _error_response(
        request,
        422,
        "VALIDATION_ERROR",
        "请求参数校验失败",
        details,
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        return _error_response(request, 500, "INTERNAL_SERVER_ERROR", "服务器内部错误")

    if exc.status_code == 404:
        return _error_response(request, 404, "NOT_FOUND", "请求的资源不存在", headers=exc.headers)

    if isinstance(exc.detail, str):
        message = exc.detail
        details: JsonValue | None = None
    else:
        message = "请求处理失败"
        details = exc.detail
    return _error_response(
        request,
        exc.status_code,
        "HTTP_ERROR",
        message,
        details,
        headers=exc.headers,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    del exc
    return _error_response(request, 500, "INTERNAL_SERVER_ERROR", "服务器内部错误")


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: JsonValue | None = None,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request)
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    body = ErrorResponse(
        code=code,
        message=message,
        details=details,
        requestId=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=response_headers,
    )


def _translate_validation_message(
    error_type: str,
    context: Mapping[str, Any] | None,
) -> str:
    if error_type == "greater_than":
        threshold = (context or {}).get("gt")
        return f"输入值必须大于 {threshold}"
    messages = {
        "timezone_aware": "日期时间必须包含时区信息",
        "missing": "缺少必需字段",
        "extra_forbidden": "包含不允许的字段",
        "string_type": "输入值必须是字符串",
        "int_type": "输入值必须是整数",
        "int_parsing": "输入值必须是有效整数",
        "bool_type": "输入值必须是布尔值",
        "list_type": "输入值必须是列表",
        "dict_type": "输入值必须是对象",
        "literal_error": "输入值不在允许范围内",
        "string_too_short": "输入文本过短",
        "string_too_long": "输入文本过长",
        "json_invalid": "请求体不是有效 JSON",
    }
    return messages.get(error_type, "输入值无效")
