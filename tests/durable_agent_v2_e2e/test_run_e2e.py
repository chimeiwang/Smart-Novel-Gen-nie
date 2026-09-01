from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import cast

import pytest

from . import run_e2e
from .run_e2e import (
    SSE_TIMEOUT,
    Acceptance,
    ComposeStack,
    _assert_agent_restart_receipts,
    _assert_fake_billing_evidence,
    _safe_billing_evidence,
)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler 固定接口
        body = b'{"status":"local"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return None


def test_acceptance_clients_ignore_all_host_proxy_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:1")
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack = cast(
        ComposeStack,
        SimpleNamespace(
            core_port=server.server_port,
            control_port=server.server_port,
            control_token=secrets.token_urlsafe(32),
        ),
    )
    acceptance = Acceptance(stack)
    try:
        assert acceptance.core.get("/local").json() == {"status": "local"}
        assert acceptance.control.get("/local").json() == {"status": "local"}
    finally:
        acceptance.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_sse_only_extends_read_timeout() -> None:
    assert SSE_TIMEOUT.read == 45.0
    assert SSE_TIMEOUT.connect == 10.0
    assert SSE_TIMEOUT.write == 10.0
    assert SSE_TIMEOUT.pool == 10.0


def test_manual_restart_uses_started_at_instead_of_restart_policy_count() -> None:
    runtimes = iter(
        (
            {
                "containerId": "container-1",
                "restartCount": 0,
                "startedAt": "2026-09-01T00:00:00Z",
                "status": "running",
                "health": "healthy",
                "healthCheckedAt": "2026-09-01T00:00:00Z",
                "healthCheckExitCode": 0,
            },
            {
                "containerId": "container-1",
                "restartCount": 0,
                "startedAt": "2026-09-01T00:00:01Z",
                "status": "running",
                "health": "healthy",
                "healthCheckedAt": "2026-09-01T00:00:02Z",
                "healthCheckExitCode": 0,
            },
        )
    )
    calls: list[tuple[str, object]] = []
    stack = cast(
        ComposeStack,
        SimpleNamespace(
            service_runtime=lambda service: next(runtimes),
            restart=lambda service: calls.append(("restart", service)),
            run=lambda arguments, **kwargs: calls.append(("run", arguments)),
        ),
    )

    result = ComposeStack.restart_and_wait(stack, "agent-service")

    assert result["before"]["restartCount"] == 0
    assert result["after"]["restartCount"] == 0
    assert calls == [("restart", "agent-service")]


def test_service_runtime_records_latest_healthcheck_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = cast(
        ComposeStack,
        SimpleNamespace(
            docker="docker",
            run=lambda *_args, **_kwargs: SimpleNamespace(stdout="container-1\n"),
        ),
    )
    monkeypatch.setattr(
        run_e2e.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                "container-1|0|2026-09-01T00:00:00Z|running|healthy|"
                "2026-09-01T00:00:01Z@1,2026-09-01T00:00:02Z@0,\n"
            ),
        ),
    )

    runtime = ComposeStack.service_runtime(stack, "agent-service")

    assert runtime["healthCheckedAt"] == "2026-09-01T00:00:02Z"
    assert runtime["healthCheckExitCode"] == 0


def test_restart_rejects_container_recreation() -> None:
    runtimes = iter(
        (
            {
                "containerId": "container-before",
                "restartCount": 0,
                "startedAt": "2026-09-01T00:00:00Z",
                "status": "running",
                "health": "healthy",
                "healthCheckedAt": "2026-09-01T00:00:00Z",
                "healthCheckExitCode": 0,
            },
            {
                "containerId": "container-after",
                "restartCount": 0,
                "startedAt": "2026-09-01T00:00:01Z",
                "status": "running",
                "health": "healthy",
                "healthCheckedAt": "2026-09-01T00:00:02Z",
                "healthCheckExitCode": 0,
            },
        )
    )
    stack = cast(
        ComposeStack,
        SimpleNamespace(
            service_runtime=lambda service: next(runtimes),
            restart=lambda service: None,
        ),
    )

    with pytest.raises(AssertionError, match="重启运行事实无效"):
        ComposeStack.restart_and_wait(stack, "agent-service")


def test_dependency_recovery_waits_for_same_service_instance() -> None:
    runtimes = iter(
        (
            {
                "containerId": "agent-1",
                "restartCount": 0,
                "startedAt": "2026-09-01T00:00:00Z",
                "status": "running",
                "health": "healthy",
                "healthCheckedAt": "2026-09-01T00:00:01Z",
                "healthCheckExitCode": 0,
            },
            {
                "containerId": "agent-1",
                "restartCount": 0,
                "startedAt": "2026-09-01T00:00:00Z",
                "status": "running",
                "health": "healthy",
                "healthCheckedAt": "2026-09-01T00:00:03Z",
                "healthCheckExitCode": 1,
            },
            {
                "containerId": "agent-1",
                "restartCount": 0,
                "startedAt": "2026-09-01T00:00:00Z",
                "status": "running",
                "health": "healthy",
                "healthCheckedAt": "2026-09-01T00:00:04Z",
                "healthCheckExitCode": 0,
            },
        )
    )
    stack = cast(
        ComposeStack,
        SimpleNamespace(service_runtime=lambda service: next(runtimes)),
    )

    runtime = ComposeStack.wait_service_healthy(
        stack,
        "agent-service",
        expected_container_id="agent-1",
        expected_started_at="2026-09-01T00:00:00Z",
        minimum_health_checked_at="2026-09-01T00:00:02Z",
        timeout=1,
    )

    assert runtime["health"] == "healthy"
    assert runtime["healthCheckExitCode"] == 0


def test_dependency_recovery_rejects_agent_recreation() -> None:
    stack = cast(
        ComposeStack,
        SimpleNamespace(
            service_runtime=lambda service: {
                "containerId": "agent-2",
                "startedAt": "2026-09-01T00:00:01Z",
                "status": "running",
                "health": "healthy",
            }
        ),
    )

    with pytest.raises(AssertionError, match="被意外重建或重启"):
        ComposeStack.wait_service_healthy(
            stack,
            "agent-service",
            expected_container_id="agent-1",
            expected_started_at="2026-09-01T00:00:00Z",
            timeout=1,
        )


@pytest.mark.parametrize(
    "receipts",
    (["accepted"], ["duplicate", "accepted"]),
)
def test_agent_restart_accepts_live_replayer_receipt_without_forcing_old_socket(
    receipts: list[str],
) -> None:
    _assert_agent_restart_receipts(receipts)


@pytest.mark.parametrize("receipts", ([], ["duplicate"], ["stale"]))
def test_agent_restart_rejects_receipts_that_do_not_prove_first_commit(
    receipts: list[str],
) -> None:
    with pytest.raises(AssertionError, match="Agent 重启 callback receipt 无效"):
        _assert_agent_restart_receipts(receipts)


def _usage() -> dict[str, object]:
    return {
        "usageStatus": "partial",
        "providerAttempts": 1,
        "protocolCorrections": 0,
        "wallTimeMillis": 17,
        "inputTokens": 31,
        "cachedTokens": 0,
        "promptCacheMissTokens": 31,
        "completionTokens": 7,
        "reasoningTokens": 0,
        "visibleOutputTokens": 7,
    }


def _raw_billing() -> dict[str, object]:
    usage = _usage()
    return {
        "reservationCount": 1,
        "reservation": {
            "runId": "run-1",
            "stepId": "step-1",
            "userId": "user-1",
            "requestId": "reservation-secret-id",
            "status": "settled",
            "reservedMicros": 0,
            "chargedMicros": 0,
            "usage": usage,
            "settledAtPresent": True,
        },
        "tokenUsageCount": 1,
        "tokenUsage": {
            "requestId": "reservation-secret-id",
            "runId": "run-1",
            "taskId": "step-1",
            "userId": "user-1",
            "model": "fake",
            "promptTokens": 31,
            "cachedTokens": 0,
            "promptCacheMissTokens": 31,
            "completionTokens": 7,
            "reasoningTokens": 0,
            "totalTokens": 38,
        },
        "creditLedgerCount": 0,
        "userBalanceMicros": 987_654_321,
    }


def test_fake_billing_evidence_requires_settled_zero_charge_audit_facts() -> None:
    evidence = _safe_billing_evidence(
        _raw_billing(),
        step_usage=_usage(),
        expected_run_id="run-1",
        expected_step_id="step-1",
        expected_user_id="user-1",
        initial_balance_micros=987_654_321,
    )

    _assert_fake_billing_evidence(evidence)
    assert evidence["balanceDeltaMicros"] == 0
    assert evidence["balanceUnchanged"] is True
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    assert "reservation-secret-id" not in serialized
    assert "987654321" not in serialized
    assert "usageJson" not in serialized


def test_fake_billing_evidence_reports_precise_safe_failed_field() -> None:
    raw = _raw_billing()
    reservation = raw["reservation"]
    assert isinstance(reservation, dict)
    reservation["status"] = "reserved"
    evidence = _safe_billing_evidence(
        raw,
        step_usage=_usage(),
        expected_run_id="run-1",
        expected_step_id="step-1",
        expected_user_id="user-1",
        initial_balance_micros=987_654_321,
    )

    with pytest.raises(AssertionError, match=r"reservation\.status"):
        _assert_fake_billing_evidence(evidence)
    assert evidence["reservationCount"] == 1


def test_database_facts_saves_scrubbed_billing_before_business_assertion() -> None:
    raw = {
        "run": {"status": "completed"},
        "steps": [
            {
                "id": "step-1",
                "status": "completed",
                "purpose": "generation",
                "attemptCount": 1,
                "providerAttempts": 1,
                "usageRaw": _usage(),
                "resultHash": "result-hash",
                "errorCode": None,
            }
        ],
        "messageRoles": {"agent": 1, "user": 1},
        "artifactCount": 0,
        "evaluationCount": 0,
        "billingRaw": _raw_billing(),
        "completedEventCount": 1,
        "events": [],
    }
    stack = cast(
        ComposeStack,
        SimpleNamespace(
            core_port=1,
            control_port=1,
            control_token=secrets.token_urlsafe(32),
            psql=lambda *_args, **_kwargs: json.dumps(raw),
            redis=lambda *_args: [],
        ),
    )
    acceptance = Acceptance(stack)
    acceptance.user_id = "user-1"
    acceptance.initial_credit_balance_micros = 987_654_321
    try:
        facts = acceptance.database_facts("run-1", "session-1")
    finally:
        acceptance.close()

    assert "billingRaw" not in facts
    assert "usageRaw" not in facts["steps"][0]
    assert acceptance.safe_diagnostics["billing"] == facts["billing"]
    _assert_fake_billing_evidence(facts["billing"])
