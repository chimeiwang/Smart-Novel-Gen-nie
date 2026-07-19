from __future__ import annotations

import pytest
from inkforge_contracts.jobs import WritingJobPayload
from pydantic import ValidationError


def test_short_outline_job_requires_explicit_consistent_identity() -> None:
    payload = WritingJobPayload.model_validate(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": None,
            "resumeInput": None,
            "workflowKind": "short_medium",
            "operation": "develop_short_outline",
            "targetTotalWordCount": 6000,
            "source": {
                "kind": "short_outline_inspiration",
                "originalInspiration": "一名守夜人发现城市每天都会忘记一个人。",
            },
            "startRequest": {"clientRequestId": "request-00000001"},
        }
    )

    assert payload.operation == "develop_short_outline"
    assert payload.targetTotalWordCount == 6000


def test_short_outline_job_accepts_null_reference_word_count() -> None:
    payload = WritingJobPayload.model_validate(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": None,
            "resumeInput": None,
            "workflowKind": "short_medium",
            "operation": "develop_short_outline",
            "targetTotalWordCount": None,
            "source": {
                "kind": "short_outline_inspiration",
                "originalInspiration": "灵感",
            },
        }
    )

    assert payload.targetTotalWordCount is None


@pytest.mark.parametrize(
    "change",
    [
        {"operation": None},
        {"operation": "write_chapter"},
        {"targetTotalWordCount": 5999},
        {"targetTotalWordCount": 80001},
        {"source": None},
        {
            "source": {
                "kind": "approved_short_outline",
                "outlineArtifactId": "artifact-1",
                "outlineRevision": 1,
                "outlineHash": "a" * 64,
            }
        },
    ],
)
def test_short_outline_job_rejects_missing_or_cross_profile_identity(
    change: dict[str, object],
) -> None:
    value: dict[str, object] = {
        "version": 1,
        "resume": False,
        "chapterId": "chapter-1",
        "writingSessionId": None,
        "resumeInput": None,
        "workflowKind": "short_medium",
        "operation": "develop_short_outline",
        "targetTotalWordCount": 6000,
        "source": {
            "kind": "short_outline_inspiration",
            "originalInspiration": "灵感",
        },
    }
    value.update(change)

    with pytest.raises(ValidationError):
        WritingJobPayload.model_validate(value)


def test_long_job_keeps_nullable_operation_but_rejects_short_operation() -> None:
    payload = WritingJobPayload.model_validate(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": None,
            "resumeInput": None,
            "workflowKind": "long_serial",
            "operation": None,
            "targetTotalWordCount": None,
            "source": None,
        }
    )
    assert payload.operation is None

    with pytest.raises(ValidationError):
        WritingJobPayload.model_validate(
            {
                **payload.model_dump(mode="json"),
                "operation": "develop_short_outline",
            }
        )


def test_long_job_rejects_removed_sync_lore_operation() -> None:
    with pytest.raises(ValidationError, match="已移除"):
        WritingJobPayload.model_validate(
            {
                "version": 1,
                "resume": False,
                "chapterId": "chapter-1",
                "writingSessionId": None,
                "resumeInput": None,
                "workflowKind": "long_serial",
                "operation": "sync_lore",
                "targetTotalWordCount": None,
                "source": None,
            }
        )
