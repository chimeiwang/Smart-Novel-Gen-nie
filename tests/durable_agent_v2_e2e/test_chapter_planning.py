from copy import deepcopy
from unittest.mock import Mock

import pytest

from .chapter_planning import _artifact, assert_completed_plan


def test_plan_detail_uses_snapshot_exact_revision_in_public_get() -> None:
    acceptance = Mock()
    detail = {
        "engineVersion": 2,
        "kind": "beat_plan",
        "workflowRunId": "run-1",
        "taskId": None,
        "revision": 3,
        "sourceBindingStatus": "verified",
        "payload": {
            "beatPlan": {
                "title": "隔离章节规划",
                "sceneBeats": [{"order": 1}, {"order": 2}],
            }
        },
    }
    acceptance.request.return_value.json.return_value = detail
    result = _artifact(
        acceptance,
        {
            "runId": "run-1",
            "artifact": {"artifactId": "artifact-1", "artifactRevision": 3},
        },
    )
    assert result == detail
    acceptance.request.assert_called_once_with(
        "GET",
        "/api/v1/review-artifacts/artifact-1?revision=3",
        expected=200,
    )


def plan_facts() -> dict[str, object]:
    return {
        "engineVersion": 2,
        "operation": "plan_chapter",
        "status": "completed",
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": 1,
        "artifactKind": "beat_plan",
        "artifactStatus": "applied",
        "revisionCount": 1,
        "evaluationCount": 1,
        "reviewVerdicts": ["pass"],
        "modelStepCount": 2,
        "badModelStepCount": 0,
        "matchedBillingCount": 2,
        "reservationCount": 2,
        "tokenUsageCount": 2,
        "creditLedgerCount": 0,
        "balanceDeltaMicros": 0,
        "completedEventCount": 1,
        "approvedPlanCount": 1,
        "totalPlanCount": 1,
        "supersededPlanCount": 0,
        "sceneBeatCount": 2,
        "chapterSha256": "a" * 64,
    }


def test_plan_acceptance_requires_core_results_and_per_step_unique_billing() -> None:
    assert_completed_plan(
        plan_facts(),
        model_steps=2,
        revisions=1,
        formal_plans=1,
        applied=True,
        original_chapter_sha256="a" * 64,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation", "answer_question"),
        ("engineVersion", 1),
        ("status", "waiting_user"),
        ("legacyTaskCount", 1),
        ("legacyCommandCount", 1),
        ("artifactKind", "chapter_draft"),
        ("modelStepCount", 1),
        ("reviewVerdicts", ["issues_found"]),
        ("matchedBillingCount", 1),
        ("tokenUsageCount", 3),
        ("creditLedgerCount", 1),
        ("balanceDeltaMicros", -1),
        ("completedEventCount", 2),
        ("sceneBeatCount", 4),
        ("supersededPlanCount", 1),
        ("chapterSha256", "b" * 64),
    ],
)
def test_plan_acceptance_rejects_partial_or_wrong_workflow_evidence(
    field: str,
    value: object,
) -> None:
    facts = deepcopy(plan_facts())
    facts[field] = value
    with pytest.raises(AssertionError):
        assert_completed_plan(
            facts,
            model_steps=2,
            revisions=1,
            formal_plans=1,
            applied=True,
            original_chapter_sha256="a" * 64,
        )
