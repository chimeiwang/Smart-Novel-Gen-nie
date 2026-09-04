"""自然入口的验收断言不能把新建第二 Run 或遗漏解析计费当作成功。"""

from copy import deepcopy
from typing import cast
from unittest.mock import Mock, patch

import pytest

from .natural_entry import _next_message, assert_natural_facts, assert_provider_steps, natural_body
from .run_e2e import Acceptance


def facts() -> dict[str, object]:
    return {
        "engineVersion": 2,
        "databaseOperation": None,
        "publicOperation": "plan_chapter",
        "status": "completed",
        "errorCode": None,
        "sessionRunCount": 1,
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "resolverCount": 2,
        "businessStepCount": 2,
        "modelStepCount": 4,
        "badModelStepCount": 0,
        "matchedBillingCount": 4,
        "reservationCount": 4,
        "tokenUsageCount": 4,
        "creditLedgerCount": 0,
        "balanceDeltaMicros": 0,
        "questionCount": 1,
        "answerCount": 1,
        "selectionCount": 1,
        "badControlStepCount": 0,
        "evidenceBundleCount": 2,
        "resolverEvidenceCount": 1,
        "badResolverEvidenceCount": 0,
        "businessEvidenceCount": 1,
        "businessOnIntentEvidenceCount": 0,
        "completedEventCount": 1,
        "failedEventCount": 0,
        "messageHistoryVerified": True,
        "inputHistoryVerified": True,
        "controlHashesVerified": True,
    }


def assert_plan(value: dict[str, object]) -> None:
    assert_natural_facts(value, operation="plan_chapter", answers=1, business_steps=2)


def test_natural_assertion_includes_resolver_usage_and_same_run_identity() -> None:
    assert_plan(facts())


def test_same_session_next_message_requires_explicit_two_run_expectation() -> None:
    value = facts()
    value["sessionRunCount"] = 2
    assert_natural_facts(
        value, operation="plan_chapter", answers=1, business_steps=2, session_runs=2
    )
    for invalid_count in (0, 1, 3):
        value["sessionRunCount"] = invalid_count
        with pytest.raises(AssertionError):
            assert_natural_facts(
                value, operation="plan_chapter", answers=1, business_steps=2, session_runs=2
            )


@pytest.mark.parametrize("mutation", [None, "same_run", "old_replay_latest"])
def test_same_session_scenario_does_not_resume_old_run_or_replay_latest_run(
    mutation: str | None,
) -> None:
    acceptance = Mock()
    body = natural_body("novel-1", "chapter-1", "session-1", "e2e-first-start-001", "原文")
    old: dict[str, object] = {
        "runId": "run-old",
        "status": "completed",
        "operation": "answer_question",
    }
    latest: dict[str, object] = {
        "runId": "run-new",
        "status": "completed",
        "operation": "answer_question",
    }
    acceptance.start_run.side_effect = [
        Mock(json=lambda: {"runId": "run-old" if mutation == "same_run" else "run-new"}),
        Mock(json=lambda: latest if mutation == "old_replay_latest" else old),
        Mock(json=lambda: latest),
    ]
    acceptance.wait_terminal.return_value = latest
    first = facts()
    first.update(
        publicOperation="answer_question",
        resolverCount=1,
        businessStepCount=1,
        modelStepCount=2,
        matchedBillingCount=2,
        reservationCount=2,
        tokenUsageCount=2,
        questionCount=0,
        answerCount=0,
        modelStepDiagnostics=[{"id": "resolve"}, {"id": "answer"}],
    )
    current = {**first, "sessionRunCount": 2}
    previous_providers = [
        {"idempotency_key": f"run-old.{step}", "physical_calls": 1, "completed_calls": 1}
        for step in ("resolve", "answer")
    ]
    latest_providers = [
        {"idempotency_key": f"run-new.{step}", "physical_calls": 1, "completed_calls": 1}
        for step in ("resolve", "answer")
    ]
    acceptance.provider_keys.return_value = {p["idempotency_key"] for p in previous_providers}
    acceptance.provider_facts.return_value = previous_providers + latest_providers
    with patch(f"{_next_message.__module__}._facts", return_value=current):
        if mutation is not None:
            with pytest.raises(AssertionError):
                _next_message(cast(Acceptance, acceptance), body, old, first, previous_providers)
        else:
            result = _next_message(
                cast(Acceptance, acceptance), body, old, first, previous_providers
            )
            assert result.run_id == "run-new"
            assert result.session_id == "session-1"
            assert result.database_facts["sessionRunCount"] == 2
            assert result.database_facts["previousRunId"] == "run-old"
            assert acceptance.start_run.call_args_list[1].args == (body,)
            assert acceptance.start_run.call_args_list[0].args[0]["writingSessionId"] == "session-1"


@pytest.mark.parametrize(
    "field,value",
    [
        ("databaseOperation", "plan_chapter"),
        ("publicOperation", None),
        ("sessionRunCount", 2),
        ("engineVersion", 1),
        ("status", "waiting_user"),
        ("legacyTaskCount", 1),
        ("legacyCommandCount", 1),
        ("modelStepCount", 2),
        ("badModelStepCount", 1),
        ("matchedBillingCount", 2),
        ("reservationCount", 2),
        ("tokenUsageCount", 3),
        ("creditLedgerCount", 1),
        ("balanceDeltaMicros", -1),
        ("questionCount", 0),
        ("answerCount", 2),
        ("selectionCount", 0),
        ("badControlStepCount", 1),
        ("evidenceBundleCount", 1),
        ("resolverEvidenceCount", 2),
        ("badResolverEvidenceCount", 1),
        ("businessEvidenceCount", 0),
        ("businessOnIntentEvidenceCount", 1),
        ("completedEventCount", 2),
        ("failedEventCount", 1),
        ("messageHistoryVerified", False),
        ("inputHistoryVerified", False),
        ("controlHashesVerified", False),
    ],
)
def test_natural_assertion_rejects_missing_or_wrong_facts(field: str, value: object) -> None:
    wrong = deepcopy(facts())
    wrong[field] = value
    with pytest.raises(AssertionError):
        assert_plan(wrong)
    wrong = facts()
    wrong.pop(field)
    with pytest.raises(AssertionError):
        assert_plan(wrong)


def test_unresolved_after_two_answers_has_three_billed_resolvers_without_business() -> None:
    value = facts()
    value.update(
        publicOperation=None,
        status="failed",
        errorCode="INTENT_UNRESOLVED",
        resolverCount=3,
        businessStepCount=0,
        modelStepCount=3,
        matchedBillingCount=3,
        reservationCount=3,
        tokenUsageCount=3,
        questionCount=2,
        answerCount=2,
        selectionCount=0,
        evidenceBundleCount=1,
        businessEvidenceCount=0,
        completedEventCount=0,
        failedEventCount=1,
    )
    assert_natural_facts(value, operation=None, answers=2, business_steps=0)


def test_natural_body_does_not_inject_explicit_operation_or_modify_full_input() -> None:
    text = "  完整😀\r\n　" * 50
    value = natural_body("novel-1", "chapter-1", "session-1", "e2e-natural-start-001", text)
    assert value == {
        "inputMode": "natural",
        "workflow": "long_serial",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "writingSessionId": "session-1",
        "clientRequestId": "e2e-natural-start-001",
        "userInstruction": text,
        "targetWordCount": 1000,
    }


@pytest.mark.parametrize("bad", ["physical_calls", "completed_calls"])
def test_provider_assertion_requires_each_step_exactly_one_real_fake_call(bad: str) -> None:
    provider = {"idempotency_key": "call-1", "physical_calls": 1, "completed_calls": 1}
    assert_provider_steps([provider], 1)
    with pytest.raises(AssertionError):
        assert_provider_steps([{**provider, bad: 2}], 1)
    with pytest.raises(AssertionError):
        assert_provider_steps([provider, provider], 2)
