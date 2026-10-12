"""整章审阅、场景改写和大纲选区 E2E 断言的自检。"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from .review_rewrites import (
    OutlineSource,
    _assert_decision_snapshot_matches_get,
    _outline_artifact,
    _selection_body,
    _wait_artifact,
    assert_durable_facts,
)
from .run_e2e import Acceptance


def durable_facts() -> dict[str, object]:
    return {
        "engineVersion": 2,
        "databaseOperation": "rewrite_outline_selection",
        "status": "completed",
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": 1,
        "artifactKind": "outline_draft",
        "artifactStatus": "applied",
        "revisionCount": 2,
        "evaluationCount": 2,
        "reviewVerdicts": ["pass", "pass"],
        "modelStepCount": 4,
        "badModelStepCount": 0,
        "matchedBillingCount": 4,
        "reservationCount": 4,
        "tokenUsageCount": 4,
        "creditLedgerCount": 0,
        "balanceDeltaMicros": 0,
        "completedEventCount": 1,
        "messageRoles": ["user"],
    }


def assert_outline(value: dict[str, object]) -> None:
    assert_durable_facts(
        value,
        database_operation="rewrite_outline_selection",
        model_steps=4,
        artifact_kind="outline_draft",
        artifact_status="applied",
        revisions=2,
        verdicts=["pass", "pass"],
        message_roles=["user"],
    )


def test_durable_assertion_requires_exact_model_billing_artifact_and_no_v1() -> None:
    assert_outline(durable_facts())


@pytest.mark.parametrize(
    "field,value",
    [
        ("engineVersion", 1),
        ("databaseOperation", "rewrite_scene"),
        ("status", "waiting_user"),
        ("legacyTaskCount", 1),
        ("legacyCommandCount", 1),
        ("artifactCount", 2),
        ("artifactKind", "chapter_draft"),
        ("artifactStatus", "draft"),
        ("revisionCount", 1),
        ("evaluationCount", 1),
        ("reviewVerdicts", ["issues_found", "pass"]),
        ("modelStepCount", 3),
        ("badModelStepCount", 1),
        ("matchedBillingCount", 3),
        ("reservationCount", 5),
        ("tokenUsageCount", 5),
        ("creditLedgerCount", 1),
        ("balanceDeltaMicros", -1),
        ("completedEventCount", 2),
        ("messageRoles", ["user", "agent"]),
    ],
)
def test_durable_assertion_rejects_partial_or_wrong_evidence(field: str, value: object) -> None:
    facts = deepcopy(durable_facts())
    facts[field] = value
    with pytest.raises(AssertionError):
        assert_outline(facts)
    facts = durable_facts()
    facts.pop(field)
    with pytest.raises(AssertionError):
        assert_outline(facts)


def test_outline_body_uses_unicode_code_points_and_full_source_hash() -> None:
    content = "总纲前😀旧线索\r\n总纲后　"
    selected = "😀旧线索"
    start = content.index(selected)
    source = OutlineSource(
        resource_type="outline_content",
        resource_id="outline-1",
        content=content,
        updated_at="2026-09-05T04:05:06.789Z",
        selection_start=start,
        selection_end=start + len(selected),
    )
    acceptance = cast(
        Acceptance,
        SimpleNamespace(novel_id="novel-1", chapter_id="chapter-1"),
    )

    body = _selection_body(
        acceptance,
        source,
        session_id="session-1",
        client_request_id="e2e-outline-start-001",
        instruction="完整改写所选大纲",
    )

    target = body["selectionTarget"]
    assert isinstance(target, dict)
    assert target == {
        "resourceType": "outline_content",
        "resourceId": "outline-1",
        "baseUpdatedAt": "2026-09-05T04:05:06.789Z",
        "baseContentHash": hashlib.sha256(content.encode()).hexdigest(),
        "selectionStart": 3,
        "selectionEnd": 7,
        "selectedTextHash": hashlib.sha256(selected.encode()).hexdigest(),
    }
    assert body["scope"] == {"kind": "novel"}
    assert "selectedText" not in target


def test_outline_node_body_binds_scope_to_same_resource() -> None:
    source = OutlineSource(
        resource_type="outline_node_content",
        resource_id="node-1",
        content="节点前😀旧节点\r\n节点后",
        updated_at="2026-09-05T04:05:06.789Z",
        selection_start=3,
        selection_end=7,
    )
    acceptance = cast(
        Acceptance,
        SimpleNamespace(novel_id="novel-1", chapter_id="chapter-1"),
    )

    body = _selection_body(
        acceptance,
        source,
        session_id="session-1",
        client_request_id="e2e-outline-node-start-001",
        instruction="改写节点选区",
    )

    assert body["scope"] == {"kind": "outline_node", "outlineNodeId": "node-1"}


def test_outline_detail_uses_snapshot_revision_and_reconstructs_exact_outside_text() -> None:
    source = OutlineSource(
        resource_type="outline_content",
        resource_id="outline-1",
        content="总纲前😀旧线索\r\n总纲后",
        updated_at="2026-09-05T04:05:06.789Z",
        selection_start=3,
        selection_end=7,
    )
    replacement = "新的行动线索"
    candidate = source.prefix + replacement + source.suffix
    detail = {
        "engineVersion": 2,
        "id": "artifact-1",
        "kind": "outline_draft",
        "taskId": None,
        "workflowRunId": "run-1",
        "revision": 2,
        "sourceBindingStatus": "verified",
        "payload": {
            "kind": "outline_draft",
            "operation": "rewrite_outline_selection",
            "target": {
                "mode": "outline_content_selection",
                "resourceType": source.resource_type,
                "resourceId": source.resource_id,
                "baseUpdatedAt": source.updated_at,
                "baseContentHash": source.content_sha256,
                "selectionStart": source.selection_start,
                "selectionEnd": source.selection_end,
                "selectedTextHash": source.selected_text_sha256,
            },
            "resourceType": source.resource_type,
            "resourceId": source.resource_id,
            "baseUpdatedAt": source.updated_at,
            "baseContentHash": source.content_sha256,
            "selectionStart": source.selection_start,
            "selectionEnd": source.selection_end,
            "selectedTextHash": source.selected_text_sha256,
            "selectedText": source.selected_text,
            "contextBefore": source.prefix,
            "contextAfter": source.suffix,
            "selection": {
                "start": source.selection_start,
                "end": source.selection_end,
                "selectedText": source.selected_text,
                "selectedTextHash": source.selected_text_sha256,
            },
            "replacement": replacement,
            "contentSha256": hashlib.sha256(replacement.encode()).hexdigest(),
            "candidate": candidate,
            "candidatePrefix": source.prefix,
            "candidateSuffix": source.suffix,
        },
        "diff": {
            "type": "selection",
            "mode": "outline_content_selection",
            "resourceType": source.resource_type,
            "resourceId": source.resource_id,
            "selectionStart": source.selection_start,
            "selectionEnd": source.selection_end,
            "selectedText": source.selected_text,
            "replacement": replacement,
            "before": source.content,
            "after": candidate,
            "candidate": candidate,
            "prefix": source.prefix,
            "suffix": source.suffix,
        },
    }
    acceptance = Mock()
    acceptance.request.return_value.json.return_value = detail

    result = _outline_artifact(
        acceptance,
        {"runId": "run-1", "artifact": {"artifactId": "artifact-1", "artifactRevision": 2}},
        source,
    )

    assert result == detail
    acceptance.request.assert_called_once_with(
        "GET", "/api/v1/review-artifacts/artifact-1?revision=2", expected=200
    )


def test_outline_detail_rejects_candidate_that_changes_text_outside_selection() -> None:
    source = OutlineSource(
        resource_type="outline_content",
        resource_id="outline-1",
        content="总纲前😀旧线索\r\n总纲后",
        updated_at="2026-09-05T04:05:06.789Z",
        selection_start=3,
        selection_end=7,
    )
    acceptance = Mock()
    acceptance.request.return_value.json.return_value = {
        "engineVersion": 2,
        "id": "artifact-1",
        "kind": "outline_draft",
        "taskId": None,
        "workflowRunId": "run-1",
        "revision": 1,
        "sourceBindingStatus": "verified",
        "payload": {
            "kind": "outline_draft",
            "operation": "rewrite_outline_selection",
            "target": {},
            "replacement": "替换",
            "contentSha256": hashlib.sha256("替换".encode()).hexdigest(),
            "candidatePrefix": "被改坏的前缀",
            "candidateSuffix": source.suffix,
            "candidate": "被改坏的前缀替换" + source.suffix,
        },
        "diff": {},
    }
    with pytest.raises(AssertionError, match="选区外"):
        _outline_artifact(
            acceptance,
            {"runId": "run-1", "artifact": {"artifactId": "artifact-1", "artifactRevision": 1}},
            source,
        )


def test_natural_rewrite_wait_allows_unresolved_operation_only_before_candidate() -> None:
    acceptance = Mock()
    acceptance.request.side_effect = [
        Mock(
            json=lambda: {
                "engineVersion": 2,
                "runId": "run-1",
                "operation": None,
                "status": "running",
            }
        ),
        Mock(
            json=lambda: {
                "engineVersion": 2,
                "runId": "run-1",
                "operation": "rewrite_scene",
                "status": "waiting_user",
                "artifact": {"artifactId": "artifact-1", "artifactRevision": 1},
            }
        ),
    ]

    result = _wait_artifact(
        cast(Acceptance, acceptance), "run-1", "rewrite_scene", timeout=1
    )

    assert result["operation"] == "rewrite_scene"


def test_decision_receipt_and_get_only_differ_by_documented_task_alias() -> None:
    receipt: dict[str, object] = {
        "engineVersion": 2,
        "runId": "run-1",
        "taskId": None,
        "status": "completed",
        "revision": 7,
        "operation": "rewrite_scene",
        "artifact": {"artifactId": "artifact-1", "artifactRevision": 2},
    }
    terminal = {**receipt, "taskId": "run-1"}

    _assert_decision_snapshot_matches_get(receipt, terminal, "run-1")
    without_alias = dict(receipt)
    without_alias.pop("taskId")
    _assert_decision_snapshot_matches_get(without_alias, terminal, "run-1")


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", 8),
        ("artifact", {"artifactId": "artifact-2", "artifactRevision": 2}),
    ],
)
def test_decision_snapshot_comparison_rejects_non_alias_drift(
    field: str, value: object
) -> None:
    receipt: dict[str, object] = {
        "engineVersion": 2,
        "runId": "run-1",
        "taskId": None,
        "status": "completed",
        "revision": 7,
        "operation": "rewrite_scene",
        "artifact": {"artifactId": "artifact-1", "artifactRevision": 2},
    }
    terminal = {**receipt, "taskId": "run-1", field: value}

    with pytest.raises(AssertionError, match="taskId 外不一致"):
        _assert_decision_snapshot_matches_get(receipt, terminal, "run-1")
