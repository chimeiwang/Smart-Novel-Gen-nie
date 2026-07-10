from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _resolve_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        token = _current_request_id.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _current_request_id.reset(token)


def get_request_id(request: Request | None = None) -> str:
    if request is not None:
        request_id = getattr(request.state, "request_id", None)
        if isinstance(request_id, str):
            return request_id
    return _current_request_id.get() or str(uuid4())


def _resolve_request_id(raw_request_id: str | None) -> str:
    if raw_request_id is None:
        return str(uuid4())
    request_id = raw_request_id.strip()
    if not 1 <= len(request_id) <= 128 or _contains_control_character(request_id):
        return str(uuid4())
    return request_id


def _contains_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
