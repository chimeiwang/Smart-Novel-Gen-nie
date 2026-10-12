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
    assert "candidatePatch" not in findings[0]
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


class _WritingSubmitClient(_FakeAsyncClient):
    async def post(self, path: str, *, content: bytes, headers: dict[str, str]) -> httpx.Response:
        assert path == "/internal/v1/executions"
        return httpx.Response(
            202, json={"status": "accepted"}, request=httpx.Request("POST", self.base_url + path)
        )


@pytest.mark.parametrize("mode", ["pass", "revise_once", "patch_once", "patch_conflict"])
@pytest.mark.parametrize("operation", ["write_chapter", "rewrite_scene"])
def test_writing_review_control_binds_two_roles_and_exact_revision_durably(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    operation: str,
) -> None:
    _environment(monkeypatch)
    monkeypatch.setenv("E2E_CONTROL_DATABASE", str(tmp_path / "control.sqlite3"))
    monkeypatch.setattr(control_app.httpx, "AsyncClient", _WritingSubmitClient)
    headers = {"X-InkForge-E2E-Token": "t" * 40}
    endpoint = "/control/provider/chapter-writing-review-decision"
    identities = []
    with TestClient(control_app.create_app()) as client:
        assert (
            client.put("/control/chapter-writing-review-mode", json={"mode": mode}).status_code
            == 403
        )
        assert (
            client.put(
                "/control/chapter-writing-review-mode", json={"mode": mode}, headers=headers
            ).status_code
            == 200
        )
        for revision in (1, 2):
            for role in ("consistency", "editorial"):
                key = f"run-1.review-{role}-{revision}"
                identity = {
                    "idempotencyKey": key,
                    "requestSha256": str(revision) * 64,
                    "role": role,
                }
                identities.append(identity)
                assert client.post(endpoint, json=identity, headers=headers).status_code == 409
                body = {
                    "workflow": "long_serial",
                    "operation": operation,
                    "purpose": "review",
                    "idempotencyKey": key,
                    "artifactRevision": revision,
                    "modelProfile": {"profile": f"reviewer.chapter_draft_{role}.v1"},
                    "input": {"candidate": {"content": "不可泄漏的正文"}},
                }
                assert client.post("/internal/v1/executions", json=body).status_code == 202
                provider = {name: identity[name] for name in ("idempotencyKey", "requestSha256")}
                assert (
                    client.post(
                        "/control/provider/reached", json=provider, headers=headers
                    ).status_code
                    == 200
                )
                response = client.post(endpoint, json=identity, headers=headers)
                assert response.status_code == 200
                assert response.json() == {
                    "contentVerdict": "issues_found"
                    if revision == 1 and mode != "pass"
                    else "pass",
                    "mode": mode,
                    "artifactRevision": revision,
                }
                assert (
                    client.post(
                        endpoint, json=identity | {"role": "other"}, headers=headers
                    ).status_code
                    == 422
                )
                wrong_role = "editorial" if role == "consistency" else "consistency"
                assert (
                    client.post(
                        endpoint, json=identity | {"role": wrong_role}, headers=headers
                    ).status_code
                    == 409
                )
                assert (
                    client.post(
                        endpoint, json=identity | {"requestSha256": "f" * 64}, headers=headers
                    ).status_code
                    == 409
                )
                assert (
                    client.post(
                        endpoint, json=identity | {"content": "不应发送正文"}, headers=headers
                    ).status_code
                    == 422
                )
                assert (
                    client.post(
                        "/internal/v1/executions", json=body | {"artifactRevision": revision + 1}
                    ).status_code
                    == 409
                )
        state = client.get("/control/state", headers=headers).json()
        assert len(state["chapterWritingReviews"]) == 4
        assert "不可泄漏" not in json.dumps(state, ensure_ascii=False)
    with TestClient(control_app.create_app()) as client:
        assert (
            client.put(
                "/control/chapter-writing-review-mode", json={"mode": "pass"}, headers=headers
            ).status_code
            == 200
        )
        replay = client.post(endpoint, json=identities[0], headers=headers)
        assert replay.json()["mode"] == mode
        assert client.post("/control/reset", headers=headers).status_code == 200
        assert client.get("/control/state", headers=headers).json()["chapterWritingReviews"] == []


class _WritingDecisionClient(_ReviewDecisionClient):
    mode = "patch_once"
    revision = 1

    async def post(self, path: str, *, json: dict[str, object]) -> httpx.Response:
        if path.endswith("chapter-writing-review-decision"):
            self.calls.append((path, json))
            return httpx.Response(
                200,
                json={
                    "mode": self.mode,
                    "artifactRevision": self.revision,
                    "contentVerdict": "issues_found"
                    if self.revision == 1 and self.mode != "pass"
                    else "pass",
                },
                request=httpx.Request("POST", "http://control" + path),
            )
        return await super().post(path, json=json)


def _writing_review_request(role: str, operation: str = "write_chapter") -> ModelTurnRequest:
    from inkforge_agents.execution.registry import load_execution_registry
    from inkforge_contracts import materialize_chapter_draft_output

    request = _review_request(f"reviewer.chapter_draft_{role}.v1")
    envelope = json.loads(request.messages[0].content)
    envelope["operation"] = operation
    envelope["input"] = {
        "candidate": materialize_chapter_draft_output(
            {
                "summary": "完整正文",
                "content": "林舟把旧行动线索放在桌上，逐一核对。\n\n窗外雨声渐紧，他终于作出选择。",
            }
        )
    }
    schema = (
        load_execution_registry(environment="test")
        .output_schemas["output.chapter_draft_review_report.v1"]
        .json_schema_value()
    )
    return request.model_copy(
        update={
            "messages": [
                ModelMessage(role="user", content=json.dumps(envelope, ensure_ascii=False))
            ],
            "structuredOutput": request.structuredOutput.model_copy(update={"jsonSchema": schema}),
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["consistency", "editorial"])
@pytest.mark.parametrize("revision", [1, 2])
@pytest.mark.parametrize("mode", ["pass", "revise_once", "patch_once", "patch_conflict"])
@pytest.mark.parametrize("operation", ["write_chapter", "rewrite_scene"])
async def test_controlled_writing_review_modes_are_revision_bound_and_never_send_content(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    revision: int,
    mode: str,
    operation: str,
) -> None:
    _WritingDecisionClient.mode = mode
    _WritingDecisionClient.revision = revision
    _WritingDecisionClient.calls = []
    monkeypatch.setattr(controlled_provider.httpx, "AsyncClient", _WritingDecisionClient)
    provider = controlled_provider.ControlledFakeModelProvider(
        control_url="http://control:8090", control_token="t" * 40
    )
    request = _writing_review_request(role, operation)
    result = await provider.complete_turn(request)
    jsonschema_rs.validator_for(request.structuredOutput.jsonSchema).validate(
        result.structuredOutput
    )
    needs_revision = revision == 1 and mode != "pass"
    assert result.structuredOutput["contentVerdict"] == (
        "issues_found" if needs_revision else "pass"
    )
    findings = result.structuredOutput["findings"]
    if needs_revision:
        assert len(findings) == 1
        assert findings[0]["dimension"] == "chapter_draft.local"
        if mode in {"patch_once", "patch_conflict"}:
            patch = findings[0]["candidatePatch"]
            assert patch["find"] == "旧行动线索"
            assert patch["replace"] == (
                "另一行动线索" if mode == "patch_conflict" and role == "editorial" else "新行动线索"
            )
        else:
            assert "candidatePatch" not in findings[0]
    else:
        assert findings == []
    assert result.usage.completionTokens == len(
        json.dumps(result.structuredOutput, ensure_ascii=False)
    )
    assert result.usage.totalTokens == result.usage.promptTokens + result.usage.completionTokens
    calls = _WritingDecisionClient.calls
    assert [path for path, _ in calls] == [
        "/control/provider/reached",
        "/control/provider/chapter-writing-review-decision",
        "/control/provider/completed",
    ]
    assert calls[1][1]["role"] == role
    assert set(calls[1][1]) == {"idempotencyKey", "requestSha256", "role"}
    assert "林舟" not in json.dumps(calls, ensure_ascii=False)
    await provider.aclose()
