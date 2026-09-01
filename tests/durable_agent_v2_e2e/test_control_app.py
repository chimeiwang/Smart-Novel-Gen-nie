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

    async def put(
        self, path: str, *, content: bytes, headers: dict[str, str]
    ) -> httpx.Response:
        if self.base_url == "http://core:8000":
            assert path == "/internal/v1/workflow-runs/run-1/steps/step-1/result"
            payload = httpx.Response(200, content=content).json()
            assert headers["content-type"] == "application/json"
            return httpx.Response(
                200,
                json={
                    "protocolVersion": "2.0",
                    "runId": payload["runId"],
                    "stepId": payload["stepId"],
                    "jobId": payload["jobId"],
                    "fencingToken": payload["fencingToken"],
                    "requestHash": payload["requestHash"],
                    "status": "accepted",
                    "receivedAt": "2026-09-01T00:00:00Z",
                },
                request=httpx.Request("PUT", f"{self.base_url}{path}"),
            )
        assert self.base_url == "http://agent:8001"
        assert path == "/internal/v1/executions/job-1/cancel"
        assert content == b'{"cancelRequestId":"cancel-1"}'
        assert headers["content-type"] == "application/json"
        return httpx.Response(
            202,
            content=b'{"status":"accepted"}',
            headers={"Content-Type": "application/json"},
            request=httpx.Request("PUT", f"{self.base_url}{path}"),
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


def test_agent_execution_cancel_is_forwarded_without_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _environment(monkeypatch)
    monkeypatch.setattr(control_app.httpx, "AsyncClient", _FakeAsyncClient)

    with TestClient(control_app.create_app()) as client:
        response = client.put(
            "/internal/v1/executions/job-1/cancel",
            content=b'{"cancelRequestId":"cancel-1"}',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 202
    assert response.content == b'{"status":"accepted"}'


def test_callback_proxy_records_matching_core_receipt_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _environment(monkeypatch)
    monkeypatch.setattr(control_app.httpx, "AsyncClient", _FakeAsyncClient)
    request_hash = "1" * 64
    result_hash = "2" * 64

    with TestClient(control_app.create_app()) as client:
        response = client.put(
            "/internal/v1/workflow-runs/run-1/steps/step-1/result",
            json={
                "runId": "run-1",
                "stepId": "step-1",
                "jobId": "job-1",
                "fencingToken": 1,
                "requestHash": request_hash,
                "resultHash": result_hash,
            },
        )
        state = client.get(
            "/control/state",
            headers={"X-InkForge-E2E-Token": "t" * 40},
        ).json()

    assert response.status_code == 200
    attempts = state["callbackAttempts"]
    assert len(attempts) == 1
    assert attempts[0]["core_status"] == 200
    assert attempts[0]["receipt_status"] == "accepted"
    assert attempts[0]["receipt_identity_matches"] is True


def test_controlled_provider_http_client_ignores_host_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controlled_provider.httpx, "AsyncClient", _FakeAsyncClient)

    provider = controlled_provider.ControlledFakeModelProvider(
        control_url="http://control:8090",
        control_token="t" * 40,
    )

    assert provider._http.base_url == "http://control:8090"  # noqa: SLF001
