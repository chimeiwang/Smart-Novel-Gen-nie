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


def _terminal_callback_attempt(
    *,
    core_status: int,
    receipt_status: str | None,
    receipt_identity_matches: bool,
) -> dict[str, object]:
    return {
        "action": "forwarded",
        "run_id": "run-1",
        "step_id": "step-1",
        "job_id": "job-1",
        "fencing_token": 1,
        "request_hash": "request-hash",
        "result_hash": "result-hash",
        "core_status": core_status,
        "receipt_status": receipt_status,
        "receipt_identity_matches": receipt_identity_matches,
    }


def _assert_restart_callback_bindings(
    attempts: list[dict[str, object]],
    *,
    allow_unauthenticated: bool,
) -> None:
    Acceptance.assert_callback_attempt_bindings(
        run_id="run-1",
        step={
            "id": "step-1",
            "fencingToken": 1,
            "requestHash": "request-hash",
            "resultHash": "result-hash",
        },
        journal={"jobId": "job-1"},
        attempts=attempts,
        allow_one_unauthenticated_inflight_request=allow_unauthenticated,
    )


def test_agent_restart_allows_one_unauthenticated_old_callback_with_live_receipt() -> None:
    attempts = [
        _terminal_callback_attempt(
            core_status=401,
            receipt_status=None,
            receipt_identity_matches=False,
        ),
        _terminal_callback_attempt(
            core_status=200,
            receipt_status="accepted",
            receipt_identity_matches=True,
        ),
    ]

    _assert_restart_callback_bindings(attempts, allow_unauthenticated=True)


def test_callback_binding_rejects_unauthenticated_request_outside_restart() -> None:
    attempt = _terminal_callback_attempt(
        core_status=401,
        receipt_status=None,
        receipt_identity_matches=False,
    )

    with pytest.raises(AssertionError, match="Core 回执或身份无效"):
        _assert_restart_callback_bindings([attempt], allow_unauthenticated=False)


def test_restart_rejects_multiple_unauthenticated_old_callbacks() -> None:
    unauthenticated = _terminal_callback_attempt(
        core_status=401,
        receipt_status=None,
        receipt_identity_matches=False,
    )

    with pytest.raises(AssertionError, match="多条未通过鉴权"):
        _assert_restart_callback_bindings(
            [unauthenticated, unauthenticated],
            allow_unauthenticated=True,
        )


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
            redis_hash=lambda *_args: {},
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
    assert acceptance.safe_diagnostics["database"] == {"runId": "run-1", **facts}
    _assert_fake_billing_evidence(facts["billing"])


def _core_restart_evidence(fence: int = 2) -> dict[str, object]:
    submits = [
        {
            "run_id": "run-1", "step_id": "step-1", "job_id": f"job-{number}",
            "fencing_token": number, "request_hash": "request-hash",
            "agent_status": 202, "validation_errors": [],
        }
        for number in range(1, fence + 1)
    ]
    old = _terminal_callback_attempt(
        core_status=401, receipt_status=None, receipt_identity_matches=False,
    )
    held = {**old, "action": "held_before_forward", "core_status": None,
            "receipt_identity_matches": None}
    accepted = {
        **_terminal_callback_attempt(
            core_status=200, receipt_status="accepted", receipt_identity_matches=True,
        ),
        "job_id": f"job-{fence}", "fencing_token": fence,
    }
    return {
        "run_id": "run-1",
        "step": {"id": "step-1", "attemptCount": fence, "fencingToken": fence,
                 "requestHash": "request-hash", "resultHash": "result-hash"},
        "journal": {"jobId": f"job-{fence}", "fencingToken": fence,
                    "requestHash": "request-hash", "resultHash": "result-hash"},
        "submits": submits,
        "attempts": [held.copy(), held.copy(), old.copy(), old.copy(), accepted],
    }


@pytest.mark.parametrize("fence", [1, 2])
def test_core_restart_accepts_exact_dispatch_history_and_paired_held_callbacks(fence: int) -> None:
    Acceptance.assert_core_restart_recovery_bindings(**_core_restart_evidence(fence))


@pytest.mark.parametrize("receipt", ["stale", "superseded"])
def test_core_restart_accepts_proven_old_fence_nonmaterializing_receipt(receipt: str) -> None:
    evidence = _core_restart_evidence()
    attempts = evidence["attempts"]
    assert isinstance(attempts, list)
    attempts.insert(-1, _terminal_callback_attempt(
        core_status=200, receipt_status=receipt, receipt_identity_matches=True,
    ))
    Acceptance.assert_core_restart_recovery_bindings(**evidence)


@pytest.mark.parametrize(
    "mutation",
    ["third_fence", "attempt_mismatch", "missing_submit", "changed_request", "same_job",
     "invalid_submit", "wrong_run", "wrong_step", "changed_result", "journal_mismatch",
     "old_success", "unpaired_401", "late_held", "new_identity_401", "no_accepted",
     "unknown_identity", "unproven_stale", "invalid_schema", "new_fence_held_401"],
)
def test_core_restart_rejects_unproven_refence_or_callback(mutation: str) -> None:
    evidence = _core_restart_evidence(3 if mutation == "third_fence" else 2)
    step = evidence["step"]
    journal = evidence["journal"]
    submits = evidence["submits"]
    attempts = evidence["attempts"]
    assert isinstance(step, dict) and isinstance(journal, dict)
    assert isinstance(submits, list) and isinstance(attempts, list)
    if mutation == "attempt_mismatch":
        step["attemptCount"] = 1
    elif mutation == "missing_submit":
        submits.pop(0)
    elif mutation == "changed_request":
        submits[-1]["request_hash"] = "changed"
    elif mutation == "same_job":
        submits[-1]["job_id"] = "job-1"
    elif mutation == "invalid_submit":
        submits[-1]["agent_status"] = 503
    elif mutation == "wrong_run":
        submits[0]["run_id"] = "another-run"
    elif mutation == "wrong_step":
        submits[0]["step_id"] = "another-step"
    elif mutation == "changed_result":
        attempts[0]["result_hash"] = "changed"
    elif mutation == "journal_mismatch":
        journal["jobId"] = "job-1"
    elif mutation == "old_success":
        attempts[-1]["job_id"] = "job-1"
        attempts[-1]["fencing_token"] = 1
    elif mutation == "unpaired_401":
        attempts.insert(-1, attempts[2].copy())
    elif mutation == "late_held":
        attempts[0], attempts[2] = attempts[2], attempts[0]
    elif mutation == "new_identity_401":
        attempts[2]["job_id"] = "job-2"
        attempts[2]["fencing_token"] = 2
    elif mutation == "no_accepted":
        attempts[-1]["receipt_status"] = "duplicate"
    elif mutation == "unknown_identity":
        attempts[0]["job_id"] = "unknown-job"
    elif mutation == "unproven_stale":
        attempts[-1]["receipt_status"] = "stale"
    elif mutation == "invalid_schema":
        submits[-1]["validation_errors"] = [{"type": "missing"}]
    elif mutation == "new_fence_held_401":
        new_held = {**attempts[0], "job_id": "job-2", "fencing_token": 2}
        new_401 = {**attempts[2], "job_id": "job-2", "fencing_token": 2}
        attempts[-1:-1] = [new_held, new_401]
    with pytest.raises(AssertionError):
        Acceptance.assert_core_restart_recovery_bindings(**evidence)


@pytest.mark.parametrize(
    "mutation",
    [None, "ordinary_fence_2", "provider_duplicate", "provider_incomplete", "billing_duplicate",
     "message_duplicate", "completed_event_duplicate", "step_duplicate"],
)
def test_core_restart_preserves_single_model_billing_message_and_event_rules(
    mutation: str | None,
) -> None:
    evidence = _core_restart_evidence()
    step = evidence["step"]
    assert isinstance(step, dict)
    step.update({"status": "completed", "purpose": "generation", "providerAttempts": 1})
    provider = {"idempotency_key": "run-1.step-1", "physical_calls": 1, "completed_calls": 1}
    billing = _safe_billing_evidence(
        _raw_billing(), step_usage=_usage(), expected_run_id="run-1", expected_step_id="step-1",
        expected_user_id="user-1", initial_balance_micros=987_654_321,
    )
    facts = {
        "run": {"status": "completed", "operation": "answer_question", "engineVersion": 2,
                "lastEventSequence": 11, "errorCode": None, "cancelRequestId": None,
                "cancelRequestedAtPresent": False, "writingSessionId": "session-1"},
        "steps": [step], "messageRoles": {"agent": 1, "user": 1}, "artifactCount": 0,
        "evaluationCount": 0, "billing": billing, "completedEventCount": 1,
    }
    if mutation == "provider_duplicate":
        provider["physical_calls"] = 2
    elif mutation == "provider_incomplete":
        provider["completed_calls"] = 0
    elif mutation == "billing_duplicate":
        billing["tokenUsageCount"] = 2
    elif mutation == "message_duplicate":
        facts["messageRoles"] = {"agent": 2, "user": 1}
    elif mutation == "completed_event_duplicate":
        facts["completedEventCount"] = 2
    elif mutation == "step_duplicate":
        facts["steps"] = [step, step]
    acceptance = cast(Acceptance, SimpleNamespace(
        database_facts=lambda *_args: facts,
        control_state=lambda: {"providerCalls": [provider]},
        wait_delivered_journal=lambda *_args: evidence["journal"],
    ))
    def assert_facts() -> None:
        Acceptance.assert_scenario_facts(
            acceptance, run_id="run-1", session_id="session-1", provider_before=set(),
            core_restart=mutation != "ordinary_fence_2",
        )
    if mutation is None:
        assert_facts()
    else:
        with pytest.raises(AssertionError):
            assert_facts()


def test_missing_execution_journal_uses_empty_json_hash() -> None:
    acceptance = cast(
        Acceptance,
        SimpleNamespace(stack=SimpleNamespace(redis_hash=lambda *_args: {})),
    )

    assert Acceptance.journal_facts(acceptance, "step-missing") == {
        "present": False,
        "state": None,
        "callbackDelivery": None,
        "requestHash": None,
        "resultHash": None,
        "jobId": None,
        "fencingToken": None,
        "terminalPayloadPresent": False,
    }


def test_redis_json_hash_preserves_empty_values_and_all_unicode_line_separators() -> None:
    expected = {
        "state": "result", "novel_id": "",
        "terminal_payload": '{"content":"前\u0085中\u2028后\u001c\ufeff尾"}',
        "fencing_token": "1",
    }

    def run(arguments, *, timeout):
        assert arguments == [
            "exec", "-T", "execution-redis", "redis-cli", "--json", "HGETALL", "journal-1",
        ]
        assert timeout == 30
        return SimpleNamespace(stdout=json.dumps(expected, ensure_ascii=False) + "\n")

    stack = cast(ComposeStack, SimpleNamespace(run=run))
    assert ComposeStack.redis_hash(stack, "journal-1") == expected


@pytest.mark.parametrize("invalid", [[], None, {"state": None}, {"state": 1}])
def test_redis_json_hash_rejects_non_string_mapping(invalid) -> None:
    stack = cast(ComposeStack, SimpleNamespace(
        run=lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps(invalid)),
    ))
    with pytest.raises(AssertionError, match="HGETALL"):
        ComposeStack.redis_hash(stack, "journal-1")
