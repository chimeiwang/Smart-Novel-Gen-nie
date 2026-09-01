from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from . import control_app, controlled_provider


class _FakeAsyncClient:
    def __init__(self, *, base_url: str, **options: object) -> None:
        assert options["trust_env"] is False
        self.base_url = base_url

    async def get(self, path: str, *, headers: dict[str, str]) -> httpx.Response:
        assert self.base_url == "http://agent:8001"
        assert path == "/internal/v1/health/ready"
        assert headers["x-request-fact"] == "preserved"
        return httpx.Response(
            503,
            content=b'{"status":"not_ready"}',
            headers={
                "Content-Type": "application/json",
                "Retry-After": "7",
                "X-InkForge-Manifest-Fingerprint": "test-fingerprint",
            },
            request=httpx.Request("GET", f"{self.base_url}{path}"),
        )

    async def post(
        self, path: str, *, content: bytes, headers: dict[str, str]
    ) -> httpx.Response:
        assert self.base_url == "http://agent:8001"
        assert path == "/internal/v1/runs"
        assert content == b"{}"
        assert headers["content-type"] == "application/json"
        return httpx.Response(
            422,
            content=b'{"detail":[{"loc":["body"],"type":"missing"}]}',
            headers={"Content-Type": "application/json", "X-Probe-Fact": "agent"},
            request=httpx.Request("POST", f"{self.base_url}{path}"),
        )

    async def aclose(self) -> None:
        return None


def _environment(monkeypatch: pytest.MonkeyPatch, *, environment: str = "test") -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("E2E_EXECUTION_CONTROL_TOKEN", "t" * 40)
    monkeypatch.setenv("E2E_CORE_UPSTREAM", "http://core:8000")
    monkeypatch.setenv("E2E_AGENT_UPSTREAM", "http://agent:8001")
    monkeypatch.setenv("E2E_CONTROL_DATABASE", ":memory:")


def test_agent_readiness_status_body_and_protocol_headers_are_transparent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _environment(monkeypatch)
    monkeypatch.setattr(control_app.httpx, "AsyncClient", _FakeAsyncClient)

    with TestClient(control_app.create_app()) as client:
        response = client.get(
            "/internal/v1/health/ready",
            headers={"X-Request-Fact": "preserved"},
        )

    assert response.status_code == 503
    assert response.content == b'{"status":"not_ready"}'
    assert response.headers["retry-after"] == "7"
    assert response.headers["x-inkforge-manifest-fingerprint"] == "test-fingerprint"


def test_control_app_rejects_non_test_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _environment(monkeypatch, environment="development")

    with pytest.raises(RuntimeError, match="E2E 控制器缺少"):
        control_app.create_app()


def test_agent_post_transport_probe_is_forwarded_without_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _environment(monkeypatch)
    monkeypatch.setattr(control_app.httpx, "AsyncClient", _FakeAsyncClient)

    with TestClient(control_app.create_app()) as client:
        response = client.post(
            "/internal/v1/runs",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.content == b'{"detail":[{"loc":["body"],"type":"missing"}]}'
    assert response.headers["x-probe-fact"] == "agent"


def test_controlled_provider_http_client_ignores_host_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controlled_provider.httpx, "AsyncClient", _FakeAsyncClient)

    provider = controlled_provider.ControlledFakeModelProvider(
        control_url="http://control:8090",
        control_token="t" * 40,
    )

    assert provider._http.base_url == "http://control:8090"  # noqa: SLF001
