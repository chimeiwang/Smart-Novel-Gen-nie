from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from inkforge_contracts.long_serial import (
    LONG_SERIAL_RUN_PAYLOAD_ADAPTER,
    SelectionTarget,
    SourceBinding,
)
from pydantic import ValidationError


def valid_start_payload() -> dict[str, object]:
    return {
        "version": 1,
        "workflow": "long_serial",
        "chapterId": "chapter-1",
        "writingSessionId": None,
        "operation": "plan_chapter",
        "target": {"type": "chapter", "id": "chapter-1"},
        "scope": {"kind": "chapter", "chapterId": "chapter-1"},
        "sourceBindings": [
            {
                "resourceType": "chapter",
                "resourceId": "chapter-1",
                "exists": True,
                "updatedAt": "2026-08-05T10:00:00Z",
                "contentSha256": "a" * 64,
                "revision": None,
                "absenceSentinel": None,
            }
        ],
        "targetWordCount": 4_000,
        "userInstruction": "规划本章",
        "resume": False,
        "resumeInput": None,
    }


def test_long_serial_start_payload_is_strict_and_discriminated() -> None:
    payload = valid_start_payload()
    parsed = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(payload)

    assert parsed.resume is False
    assert parsed.target.id == "chapter-1"
    assert parsed.scope.kind == "chapter"

    with pytest.raises(ValidationError):
        LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(
            {**payload, "selectedAgents": ["写作"]}
        )


@pytest.mark.parametrize("resource_type", [
    "chapter_content",
    "outline_content",
    "outline_node_content",
])
def test_selection_target_accepts_unicode_codepoint_identity(resource_type: str) -> None:
    target = SelectionTarget.model_validate(
        {
            "resourceType": resource_type,
            "resourceId": "resource-1",
            "baseUpdatedAt": "2026-08-05T10:00:00Z",
            "baseContentHash": "a" * 64,
            "selectionStart": 1,
            "selectionEnd": 3,
            "selectedTextHash": "b" * 64,
        }
    )
    assert target.selectionEnd == 3


def test_selection_target_rejects_empty_reverse_unknown_and_uppercase_hash() -> None:
    values = {
        "resourceType": "chapter_content",
        "resourceId": "resource-1",
        "baseUpdatedAt": "2026-08-05T10:00:00Z",
        "baseContentHash": "a" * 64,
        "selectionStart": 3,
        "selectionEnd": 3,
        "selectedTextHash": "b" * 64,
    }
    with pytest.raises(ValidationError):
        SelectionTarget.model_validate(values)
    with pytest.raises(ValidationError):
        SelectionTarget.model_validate({**values, "selectionEnd": 2})
    with pytest.raises(ValidationError):
        SelectionTarget.model_validate({**values, "selectionEnd": 4, "unknown": 1})
    with pytest.raises(ValidationError):
        SelectionTarget.model_validate({**values, "selectionEnd": 4, "baseContentHash": "A" * 64})


def test_selection_operations_require_target_and_preserve_rewrite_scene_semantics() -> None:
    payload = valid_start_payload()
    payload.update(
        {
            "operation": "rewrite_chapter_selection",
            "selectionTarget": {
                "resourceType": "chapter_content",
                "resourceId": "chapter-1",
                "baseUpdatedAt": "2026-08-05T10:00:00Z",
                "baseContentHash": "a" * 64,
                "selectionStart": 0,
                "selectionEnd": 1,
                "selectedTextHash": "b" * 64,
            },
        }
    )
    parsed = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(payload)
    assert parsed.selectionTarget is not None

    with pytest.raises(ValidationError):
        LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(
            {**payload, "selectionTarget": None}
        )

    full_scene = {**payload, "operation": "rewrite_scene", "selectionTarget": None}
    scene = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(full_scene)
    assert scene.operation == "rewrite_scene"

    with pytest.raises(ValidationError):
        LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(
            {**payload, "resumeInput": {"userMessage": "继续"}}
        )


def test_long_serial_user_instruction_preserves_original_whitespace() -> None:
    payload = valid_start_payload()
    payload["userInstruction"] = "  保留这个排版要求  "

    parsed = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(payload)

    assert parsed.userInstruction == "  保留这个排版要求  "

    payload["userInstruction"] = "   "
    with pytest.raises(ValidationError):
        LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(payload)


def test_long_serial_resume_requires_checkpoint_input_and_keeps_full_context() -> None:
    payload = valid_start_payload()
    payload.update(
        {
            "operation": "write_chapter",
            "resume": True,
            "resumeInput": {"userMessage": "继续写作"},
        }
    )

    parsed = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(payload)

    assert parsed.resume is True
    assert parsed.operation == "write_chapter"
    assert parsed.target.id == "chapter-1"
    assert parsed.sourceBindings[0].resourceId == "chapter-1"
    assert parsed.resumeInput.userMessage == "继续写作"

    missing_input = deepcopy(payload)
    missing_input["resumeInput"] = None
    with pytest.raises(ValidationError):
        LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(missing_input)

    artifact_decision = deepcopy(payload)
    artifact_decision["resumeInput"] = {
        "userMessage": None,
        "artifactId": "artifact-1",
        "decision": "approve",
    }
    decision_resume = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(
        artifact_decision
    )

    assert decision_resume.resumeInput.artifactId == "artifact-1"
    assert decision_resume.resumeInput.decision == "approve"

    incomplete_decision = deepcopy(artifact_decision)
    incomplete_decision["resumeInput"] = {"artifactId": "artifact-1"}
    with pytest.raises(ValidationError):
        LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(incomplete_decision)


def test_new_long_serial_payload_rejects_historical_sync_lore() -> None:
    payload = valid_start_payload()
    payload["operation"] = "sync_lore"

    with pytest.raises(ValidationError):
        LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(payload)


@pytest.mark.parametrize(
    "scope",
    [
        {"kind": "chapter", "chapterId": "chapter-1"},
        {"kind": "chapter_range", "chapterStartOrder": 1, "chapterEndOrder": 3},
        {"kind": "outline_node", "outlineNodeId": "node-1"},
        {"kind": "novel"},
    ],
)
def test_long_serial_scope_union_accepts_declared_namespaces(
    scope: dict[str, object],
) -> None:
    payload = valid_start_payload()
    payload["scope"] = scope

    parsed = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(payload)

    assert parsed.scope.kind == scope["kind"]


@pytest.mark.parametrize(
    "scope",
    [
        {"kind": "chapter_range", "chapterStartOrder": 3, "chapterEndOrder": 1},
        {"kind": "outline_node", "outlineNodeId": "   "},
        {"kind": "volume", "volumeId": "volume-1"},
        {"kind": "novel", "chapterId": "chapter-1"},
    ],
)
def test_long_serial_scope_union_rejects_invalid_shapes(
    scope: dict[str, object],
) -> None:
    payload = valid_start_payload()
    payload["scope"] = scope

    with pytest.raises(ValidationError):
        LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(payload)


def test_source_binding_validates_existing_resource_shape() -> None:
    binding = SourceBinding.model_validate(
        {
            "resourceType": "chapter",
            "resourceId": "chapter-1",
            "exists": True,
            "updatedAt": datetime(2026, 8, 5, 10, 0, tzinfo=UTC),
            "contentSha256": "b" * 64,
            "revision": 2,
            "absenceSentinel": None,
        }
    )

    assert binding.revision == 2

    for invalid in (
        {**binding.model_dump(), "updatedAt": None},
        {**binding.model_dump(), "contentSha256": None},
        {
            **binding.model_dump(),
            "absenceSentinel": {
                "resourceType": "novel",
                "resourceId": "novel-1",
            },
        },
        {**binding.model_dump(), "contentSha256": "A" * 64},
    ):
        with pytest.raises(ValidationError):
            SourceBinding.model_validate(invalid)


def test_source_binding_validates_absent_resource_shape() -> None:
    binding = SourceBinding.model_validate(
        {
            "resourceType": "outline",
            "resourceId": "novel:novel-1:outline",
            "exists": False,
            "updatedAt": None,
            "contentSha256": None,
            "revision": None,
            "absenceSentinel": {
                "resourceType": "novel",
                "resourceId": "novel-1",
            },
        }
    )

    assert binding.absenceSentinel is not None

    for invalid in (
        {**binding.model_dump(), "absenceSentinel": None},
        {**binding.model_dump(), "revision": 1},
        {**binding.model_dump(), "updatedAt": "2026-08-05T10:00:00Z"},
        {**binding.model_dump(), "unknownField": True},
    ):
        with pytest.raises(ValidationError):
            SourceBinding.model_validate(invalid)
