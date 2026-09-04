from __future__ import annotations

import json
from pathlib import Path

import httpx
import jsonschema_rs
import pytest
from fastapi.testclient import TestClient
from inkforge_agents.providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelStructuredOutputRequest,
    ModelTurnRequest,
)

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

    async def post(self, path: str, *, content: bytes, headers: dict[str, str]) -> httpx.Response:
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

    async def put(self, path: str, *, content: bytes, headers: dict[str, str]) -> httpx.Response:
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


def test_chapter_plan_review_decision_is_durable_idempotent_and_consumed_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _environment(monkeypatch)
    monkeypatch.setenv("E2E_CONTROL_DATABASE", str(tmp_path / "control.sqlite3"))
    monkeypatch.setattr(control_app.httpx, "AsyncClient", _FakeAsyncClient)
    headers = {"X-InkForge-E2E-Token": "t" * 40}
    first = {"idempotencyKey": "plan-review-1", "requestSha256": "1" * 64}
    second = {"idempotencyKey": "plan-review-2", "requestSha256": "2" * 64}
    with TestClient(control_app.create_app()) as client:
        assert (
            client.put(
                "/control/chapter-plan-review-mode", json={"mode": "revise_once"}
            ).status_code
            == 403
        )
        response = client.put(
            "/control/chapter-plan-review-mode", json={"mode": "revise_once"}, headers=headers
        )
        assert response.status_code == 200
        assert (
            client.post("/control/provider/reached", json=first, headers=headers).status_code == 200
        )
        decision = client.post(
            "/control/provider/chapter-plan-review-decision", json=first, headers=headers
        )
        assert decision.json() == {"contentVerdict": "issues_found"}
        assert (
            client.post(
                "/control/provider/chapter-plan-review-decision", json=first, headers=headers
            ).json()
            == decision.json()
        )

    # 用同一个SQLite新建控制器，模拟控制器/Agent进程重启后重试供应商请求。
    with TestClient(control_app.create_app()) as client:
        assert (
            client.post("/control/provider/reached", json=first, headers=headers).status_code == 200
        )
        assert client.post(
            "/control/provider/chapter-plan-review-decision", json=first, headers=headers
        ).json() == {"contentVerdict": "issues_found"}
        assert (
            client.post("/control/provider/reached", json=second, headers=headers).status_code
            == 200
        )
        assert client.post(
            "/control/provider/chapter-plan-review-decision", json=second, headers=headers
        ).json() == {"contentVerdict": "pass"}
        conflict = client.post(
            "/control/provider/chapter-plan-review-decision",
            json={**first, "requestSha256": "3" * 64},
            headers=headers,
        )
        assert conflict.status_code == 409
        state = client.get("/control/state", headers=headers).json()
        assert [item["content_verdict"] for item in state["chapterPlanReviews"]] == [
            "issues_found",
            "pass",
        ]
        assert state["chapterPlanReviewMode"] == {"reviseRemaining": 0}
        assert client.post("/control/reset", headers=headers).status_code == 200
        reset = client.get("/control/state", headers=headers).json()
        assert reset["chapterPlanReviews"] == []
        assert reset["chapterPlanReviewMode"] == {"reviseRemaining": 0}


class _ReviewDecisionClient:
    decisions: list[str] = []
    calls: list[tuple[str, dict[str, object]]] = []

    def __init__(self, **options: object) -> None:
        assert options["trust_env"] is False

    async def post(self, path: str, *, json: dict[str, object]) -> httpx.Response:
        self.calls.append((path, json))
        payload = {"status": "proceed"}
        if path.endswith("chapter-plan-review-decision"):
            payload = {"contentVerdict": self.decisions.pop(0)}
        return httpx.Response(
            200, json=payload, request=httpx.Request("POST", "http://control" + path)
        )

    async def aclose(self) -> None:
        return None


def _review_request(profile: str = "reviewer.chapter_plan_editorial.v1") -> ModelTurnRequest:
    registry = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts/agent-execution/output-schema-registry.v1.json"
        ).read_text(encoding="utf-8")
    )
    schema = next(
        entry["jsonSchema"]
        for entry in registry["schemas"]
        if entry["key"] == "output.chapter_review_report.v1"
    )
    return ModelTurnRequest(
        messages=[
            ModelMessage(
                role="user",
                content=json.dumps(
                    {
                        "workflow": "long_serial",
                        "operation": "plan_chapter",
                        "purpose": "review",
                        "input": {"candidate": {"privateBody": "测试正文不得进入控制器"}},
                        "evidenceBundle": {
                            "items": [
                                {"id": "evidence-1", "exists": True, "contentSha256": "a" * 64}
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
            )
        ],
        tools=[],
        maxOutputTokens=2000,
        policy=ModelExecutionPolicy(policyId=profile, thinkingMode="disabled"),
        structuredOutput=ModelStructuredOutputRequest(
            name="evaluation",
            route="responses_json_schema_v1",
            jsonSchema=schema,
        ),
        requestIdempotencyKey="provider-review-1",
    )


@pytest.mark.asyncio
async def test_controlled_plan_reviewer_uses_frozen_evidence_without_logging_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ReviewDecisionClient.decisions = ["issues_found"]
    _ReviewDecisionClient.calls = []
    monkeypatch.setattr(controlled_provider.httpx, "AsyncClient", _ReviewDecisionClient)
    provider = controlled_provider.ControlledFakeModelProvider(
        control_url="http://control:8090", control_token="t" * 40
    )
    request = _review_request()
    result = await provider.complete_turn(request)
    assert result.structuredOutput is not None
    assert request.structuredOutput is not None
    jsonschema_rs.validator_for(request.structuredOutput.jsonSchema).validate(
        result.structuredOutput
    )
    assert result.structuredOutput["contentVerdict"] == "issues_found"
    findings = result.structuredOutput["findings"]
    assert isinstance(findings, list) and len(findings) == 1
    assert findings[0]["dimension"] == "chapter_plan.local"
    assert findings[0]["confidence"] >= 0.8
    assert findings[0]["candidateRange"] is None
    assert findings[0]["evidence"] == [
        {"evidenceItemId": "evidence-1", "contentSha256": "a" * 64, "range": None}
    ]
    assert result.usage.totalTokens == result.usage.promptTokens + result.usage.completionTokens
    assert result.usage.completionTokens == len(
        json.dumps(result.structuredOutput, ensure_ascii=False)
    )
    assert [path for path, _ in _ReviewDecisionClient.calls] == [
        "/control/provider/reached",
        "/control/provider/chapter-plan-review-decision",
        "/control/provider/completed",
    ]
    assert all(
        set(body) == {"idempotencyKey", "requestSha256"} for _, body in _ReviewDecisionClient.calls
    )
    assert "测试正文" not in json.dumps(_ReviewDecisionClient.calls, ensure_ascii=False)
    await provider.aclose()


@pytest.mark.asyncio
async def test_other_review_profile_does_not_consume_chapter_plan_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ReviewDecisionClient.decisions = []
    _ReviewDecisionClient.calls = []
    monkeypatch.setattr(controlled_provider.httpx, "AsyncClient", _ReviewDecisionClient)
    provider = controlled_provider.ControlledFakeModelProvider(
        control_url="http://control:8090", control_token="t" * 40
    )
    result = await provider.complete_turn(_review_request("reviewer.editorial.v1"))
    assert result.structuredOutput == {"contentVerdict": "pass", "findings": []}
    assert [path for path, _ in _ReviewDecisionClient.calls] == [
        "/control/provider/reached",
        "/control/provider/completed",
    ]
    await provider.aclose()
