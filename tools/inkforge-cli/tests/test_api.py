from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from inkforge_cli.api import CoreApiClient, CoreApiError, SseConnectionError


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> CoreApiClient:
    return CoreApiClient(
        "http://127.0.0.1:8000",
        "session-cookie",
        transport=httpx.MockTransport(handler),
    )


def test_client_sends_only_public_api_cookie_and_parses_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/me"
        assert request.headers["cookie"] == "inkforge-token=session-cookie"
        assert "/internal/" not in request.url.path
        return httpx.Response(200, json={"id": "user-1", "username": "nie"})

    assert make_client(handler).request("GET", "/api/v1/auth/me")["username"] == "nie"


@pytest.mark.parametrize(("status", "exit_code"), [(401, 3), (409, 4)])
def test_client_maps_auth_and_conflict_statuses(status: int, exit_code: int) -> None:
    client = make_client(
        lambda request: httpx.Response(
            status,
            json={"code": "ERROR", "message": "请求失败"},
            request=request,
        )
    )

    with pytest.raises(CoreApiError) as caught:
        client.request("GET", "/api/v1/novels")

    assert caught.value.exit_code == exit_code
    assert "session-cookie" not in repr(caught.value)


def test_client_preserves_public_error_details_and_request_id() -> None:
    client = make_client(
        lambda request: httpx.Response(
            409,
            json={
                "code": "STALE_VERSION",
                "message": "版本已过期",
                "details": {"expected": "v1", "current": "v2"},
                "requestId": "request-server-1",
            },
            request=request,
        )
    )

    with pytest.raises(CoreApiError) as caught:
        client.request("GET", "/api/v1/novels")

    assert caught.value.details == {"expected": "v1", "current": "v2"}
    assert caught.value.request_id == "request-server-1"


def test_login_extracts_cookie_without_returning_it_in_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"username": "nie", "password": "pw-secret"}
        return httpx.Response(
            200,
            headers={"set-cookie": "inkforge-token=cookie-secret; HttpOnly; Path=/"},
            json={"id": "user-1", "username": "nie"},
        )

    client = CoreApiClient(
        "http://127.0.0.1:8000",
        transport=httpx.MockTransport(handler),
    )
    user, cookie = client.login("nie", "pw-secret")

    assert user == {"id": "user-1", "username": "nie"}
    assert cookie == "cookie-secret"


def test_client_rejects_internal_or_non_public_paths_before_transport() -> None:
    client = make_client(
        lambda request: pytest.fail(f"不应发出请求：{request.url}")
    )

    with pytest.raises(ValueError):
        client.request("GET", "/internal/v1/writing/runs/task-1")


def test_sse_parser_preserves_ids_event_types_and_complete_json_data() -> None:
    body = (
        'id: 7\nevent: progress\ndata: {"sequence":7,"text":"正文尾部😀"}\n\n'
        'id: 8\nevent: done\ndata: {"sequence":8}\n\n'
    )
    client = make_client(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=body,
            request=request,
        )
    )

    events = list(client.iter_sse("task-1", last_event_id="6"))

    assert events == [
        {
            "id": "7",
            "event": "progress",
            "data": {"sequence": 7, "text": "正文尾部😀"},
        },
        {"id": "8", "event": "done", "data": {"sequence": 8}},
    ]


def test_sse_transport_failure_uses_a_specific_retryable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("断线", request=request)

    client = make_client(handler)

    with pytest.raises(SseConnectionError):
        list(client.iter_sse("task-1"))
