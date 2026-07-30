from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import httpx

from .credentials import validate_core_origin


class SseConnectionError(RuntimeError):
    pass


class CoreApiError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        *,
        code: str,
        message: str,
        details: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.request_id = request_id
        self.exit_code = 3 if status_code == 401 else 4 if status_code == 409 else 5
        super().__init__(message)


class CoreApiClient:
    def __init__(
        self,
        origin: str,
        token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.origin = validate_core_origin(origin)
        self._token = token
        self._client = httpx.Client(
            base_url=self.origin,
            timeout=httpx.Timeout(30.0, read=300.0),
            transport=transport,
        )

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith("/api/v1/") or "/internal/" in path:
            raise ValueError("CLI 只能调用 /api/v1/** 公共接口")

    def _headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        result = dict(headers or {})
        if self._token is not None:
            result["Cookie"] = f"inkforge-token={self._token}"
        return result

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        code = f"HTTP_{response.status_code}"
        message = "Core API 请求失败"
        details: Any | None = None
        request_id: str | None = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                raw_request_id = payload.get("requestId")
                if isinstance(raw_request_id, str):
                    request_id = raw_request_id
                detail = payload.get("detail")
                if isinstance(detail, dict):
                    payload = detail
                raw_code = payload.get("code")
                raw_message = payload.get("message")
                if isinstance(raw_code, str):
                    code = raw_code
                if isinstance(raw_message, str):
                    message = raw_message
                elif isinstance(detail, str):
                    message = detail
                details = payload.get("details")
                nested_request_id = payload.get("requestId")
                if isinstance(nested_request_id, str):
                    request_id = nested_request_id
        except (ValueError, json.JSONDecodeError):
            pass
        raise CoreApiError(
            response.status_code,
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )

    def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        self._validate_path(path)
        supplied_headers = kwargs.pop("headers", None)
        response = self._client.request(
            method,
            path,
            headers=self._headers(supplied_headers),
            **kwargs,
        )
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        response = self._client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        self._raise_for_status(response)
        token = response.cookies.get("inkforge-token")
        if not token:
            raise CoreApiError(
                500,
                code="LOGIN_COOKIE_MISSING",
                message="登录成功响应缺少 inkforge-token Cookie",
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise CoreApiError(
                500,
                code="INVALID_LOGIN_RESPONSE",
                message="登录响应格式无效",
            )
        return payload, token

    def iter_sse(
        self,
        task_id: str,
        last_event_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        path = f"/api/v1/writing/runs/{quote(task_id, safe='')}/events"
        self._validate_path(path)
        headers: dict[str, str] = {"Accept": "text/event-stream"}
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id
        try:
            with self._client.stream("GET", path, headers=self._headers(headers)) as response:
                self._raise_for_status(response)
                frame: dict[str, Any] = {}
                data_lines: list[str] = []
                for line in response.iter_lines():
                    if line == "":
                        if frame or data_lines:
                            raw_data = "\n".join(data_lines)
                            try:
                                data: Any = json.loads(raw_data)
                            except json.JSONDecodeError:
                                data = raw_data
                            yield {
                                "id": frame.get("id"),
                                "event": frame.get("event", "message"),
                                "data": data,
                            }
                        frame = {}
                        data_lines = []
                        continue
                    if line.startswith(":"):
                        continue
                    field, separator, value = line.partition(":")
                    if separator and value.startswith(" "):
                        value = value[1:]
                    if field == "data":
                        data_lines.append(value)
                    elif field in {"id", "event"}:
                        frame[field] = value
                if frame or data_lines:
                    raw_data = "\n".join(data_lines)
                    try:
                        data = json.loads(raw_data)
                    except json.JSONDecodeError:
                        data = raw_data
                    yield {
                        "id": frame.get("id"),
                        "event": frame.get("event", "message"),
                        "data": data,
                    }
        except httpx.TransportError as exc:
            raise SseConnectionError("SSE 连接意外中断") from exc

    def close(self) -> None:
        self._client.close()
