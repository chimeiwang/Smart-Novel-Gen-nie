from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from inkforge_core.reviews.repository import _response


def _artifact(*, kind: str = "chapter_draft", payload: dict[str, object] | None = None) -> object:
    now = datetime(2026, 8, 6, tzinfo=UTC)
    return SimpleNamespace(
        id="artifact-1",
        novelId="novel-1",
        chapterId="chapter-1",
        taskId="task-1",
        workflowRunId=None,
        artifactKey="chapter-1:draft",
        kind=kind,
        status="awaiting_user",
        title="章节草案",
        summary="摘要",
        payloadJson='{"kind":"chapter_draft","content":"正文","_inkforgeControl":{"sourceCommandId":"command-1"}}'
        if payload is None
        else json.dumps(payload, ensure_ascii=False),
        diffJson=None,
        createdByAgent="写作",
        updatedByAgent="写作",
        reviewerAgent=None,
        revision=1,
        createdAt=now,
        updatedAt=now,
    )


def test_response_strips_control_field_and_exposes_verified_source_bindings() -> None:
    response = _response(
        _artifact(),
        [],
        source_bindings=[
            {
                "resourceType": "chapter",
                "resourceId": "chapter-1",
                "exists": True,
                "updatedAt": "2026-08-06T00:00:00Z",
                "contentSha256": "a" * 64,
                "revision": None,
                "absenceSentinel": None,
            }
        ],
        source_binding_status="verified",
    )

    assert response.payload == {"kind": "chapter_draft", "content": "正文"}
    assert response.sourceBindingStatus == "verified"
    assert response.sourceBindings is not None
    assert response.sourceBindings[0].resourceId == "chapter-1"


def test_response_marks_unprotected_kind_as_not_yet_supported() -> None:
    response = _response(_artifact(kind="agent_updates", payload={"kind": "agent_updates"}), [])

    assert response.sourceBindingStatus == "not_yet_supported"
    assert response.sourceBindings is None
