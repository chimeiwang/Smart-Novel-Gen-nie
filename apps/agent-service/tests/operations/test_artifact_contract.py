from __future__ import annotations

import hashlib

import pytest
from inkforge_agents.operations.artifact_contract import (
    stable_artifact_key,
    validate_artifact_submission,
)
from inkforge_agents.operations.definitions import OPERATION_DEFINITIONS


def text_event(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "type": "begin_artifact_output",
        "kind": "chapter_draft",
        "summary": "正文草案",
    }
    event.update(overrides)
    return event


def test_text_submission_extracts_complete_content_and_generates_exact_stable_key() -> None:
    result = validate_artifact_submission(
        definition=OPERATION_DEFINITIONS["write_chapter"],
        events=[text_event()],
        visible_content="ARTIFACT_OUTPUT_START\n完整正文\nARTIFACT_OUTPUT_END",
        authoritative_artifact=None,
        task_id="task-1",
        operation_kind="write_chapter",
    )

    expected = "artifact-" + hashlib.sha256(
        b"artifact-task-1-write_chapter"
    ).hexdigest()
    assert result.artifactKey == expected
    assert result.event["artifactKey"] == expected
    assert result.content == "完整正文"
    assert stable_artifact_key("task-1", "write_chapter") == expected
    assert stable_artifact_key("task-2", "write_chapter") != expected
    assert stable_artifact_key("task-1", "rewrite_scene") != expected


@pytest.mark.parametrize(
    "events",
    [
        [text_event(kind="lore_draft")],
        [{"type": "submit_beat_plan", "summary": "错误事件"}],
        [text_event(), text_event(summary="第二份草案")],
    ],
)
def test_text_submission_rejects_wrong_kind_event_or_multiple_candidates(
    events: list[dict[str, object]],
) -> None:
    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["write_chapter"],
            events=events,
            visible_content="ARTIFACT_OUTPUT_START\n正文\nARTIFACT_OUTPUT_END",
            authoritative_artifact=None,
            task_id="task-1",
            operation_kind="write_chapter",
        )


def test_incomplete_builder_and_direct_submission_conflict_is_rejected() -> None:
    events = [
        {
            "type": "start_update_builder",
            "artifactKey": "builder-key",
            "summary": "批量设定",
        },
        {
            "type": "propose_updates",
            "summary": "直接设定",
            "updates": {"storyBackground": "冲突"},
        },
    ]

    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["revise_lore"],
            events=events,
            visible_content="设定",
            authoritative_artifact=None,
            task_id="task-1",
            operation_kind="revise_lore",
        )


def test_two_builder_finishes_are_rejected_instead_of_using_last_one() -> None:
    events = [
        {
            "type": "start_update_builder",
            "artifactKey": "builder-key",
            "summary": "批量设定",
        },
        {
            "type": "append_update_batch",
            "artifactKey": "builder-key",
            "updates": {"storyBackground": "完整设定"},
        },
        {"type": "finish_update_builder", "artifactKey": "builder-key"},
        {"type": "finish_update_builder", "artifactKey": "builder-key"},
    ]

    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["revise_lore"],
            events=events,
            visible_content="设定",
            authoritative_artifact=None,
            task_id="task-1",
            operation_kind="revise_lore",
        )


def test_builder_rejects_events_with_different_keys() -> None:
    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["revise_lore"],
            events=[
                {
                    "type": "start_update_builder",
                    "artifactKey": "builder-one",
                    "summary": "批量设定",
                },
                {
                    "type": "append_update_batch",
                    "artifactKey": "builder-two",
                    "updates": {"storyBackground": "错误混用"},
                },
            ],
            visible_content="设定",
            authoritative_artifact=None,
            task_id="task-1",
            operation_kind="revise_lore",
        )


def test_builder_submission_preserves_validated_builder_key() -> None:
    result = validate_artifact_submission(
        definition=OPERATION_DEFINITIONS["revise_lore"],
        events=[
            {
                "type": "start_update_builder",
                "artifactKey": "builder-key",
                "summary": "批量设定",
            },
            {
                "type": "append_update_batch",
                "artifactKey": "builder-key",
                "updates": {"storyBackground": "完整设定"},
            },
            {"type": "finish_update_builder", "artifactKey": "builder-key"},
        ],
        visible_content="设定完成",
        authoritative_artifact=None,
        task_id="task-1",
        operation_kind="revise_lore",
    )

    assert result.artifactKey == "builder-key"
    assert result.event["kind"] == "agent_updates"


def test_beat_plan_is_normalized_to_authoritative_kind_and_stable_key() -> None:
    result = validate_artifact_submission(
        definition=OPERATION_DEFINITIONS["plan_chapter"],
        events=[
            {
                "type": "submit_beat_plan",
                "title": "第一章",
                "beatCount": 1,
                "summary": "章节计划",
            }
        ],
        visible_content="计划说明",
        authoritative_artifact=None,
        task_id="task-1",
        operation_kind="plan_chapter",
    )

    assert result.event["kind"] == "beat_plan"
    assert result.artifactKey == stable_artifact_key("task-1", "plan_chapter")


def test_revision_fills_missing_authoritative_key_and_rejects_changed_key() -> None:
    authority = {
        "id": "artifact-1",
        "artifactKey": "authority-key",
        "kind": "chapter_draft",
        "revision": 1,
    }
    filled = validate_artifact_submission(
        definition=OPERATION_DEFINITIONS["write_chapter"],
        events=[text_event()],
        visible_content="ARTIFACT_OUTPUT_START\n返工正文\nARTIFACT_OUTPUT_END",
        authoritative_artifact=authority,
        task_id="task-1",
        operation_kind="write_chapter",
    )
    assert filled.artifactKey == "authority-key"

    with pytest.raises(ValueError, match="ARTIFACT_REVISION_IDENTITY_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["write_chapter"],
            events=[text_event(artifactKey="changed-key")],
            visible_content="ARTIFACT_OUTPUT_START\n返工正文\nARTIFACT_OUTPUT_END",
            authoritative_artifact=authority,
            task_id="task-1",
            operation_kind="write_chapter",
        )


def test_revision_rejects_authority_without_key() -> None:
    with pytest.raises(ValueError, match="ARTIFACT_REVISION_IDENTITY_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["write_chapter"],
            events=[text_event()],
            visible_content="ARTIFACT_OUTPUT_START\n返工正文\nARTIFACT_OUTPUT_END",
            authoritative_artifact={
                "id": "artifact-1",
                "kind": "chapter_draft",
                "revision": 1,
            },
            task_id="task-1",
            operation_kind="write_chapter",
        )


def test_revision_rejects_authoritative_kind_mismatch() -> None:
    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["write_chapter"],
            events=[text_event()],
            visible_content="ARTIFACT_OUTPUT_START\n返工正文\nARTIFACT_OUTPUT_END",
            authoritative_artifact={
                "id": "artifact-1",
                "artifactKey": "authority-key",
                "kind": "lore_draft",
                "revision": 1,
            },
            task_id="task-1",
            operation_kind="write_chapter",
        )


def test_text_submission_rejects_incomplete_markers_without_truncating() -> None:
    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["write_chapter"],
            events=[text_event()],
            visible_content="ARTIFACT_OUTPUT_START\n被截断正文",
            authoritative_artifact=None,
            task_id="task-1",
            operation_kind="write_chapter",
        )
