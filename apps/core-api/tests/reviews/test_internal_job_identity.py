from __future__ import annotations

from types import SimpleNamespace

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.reviews.repository import ReviewRepository
from inkforge_core.reviews.schemas import (
    CreateArtifactRequest,
    SubmitArtifactEvaluationRequest,
)


class _Session:
    def __init__(self, results: list[object] | None = None) -> None:
        self.added: list[object] = []
        self._results = iter(
            results
            or [SimpleNamespace(id="task-1", chapterId="chapter-1"), None]
        )

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def begin(self) -> _Session:
        return self

    async def scalar(self, statement):
        del statement
        return next(self._results)

    def add(self, value: object) -> None:
        self.added.append(value)


@pytest.mark.asyncio
async def test_cancelled_or_old_job_cannot_create_artifact() -> None:
    session = _Session()
    repository = ReviewRepository(lambda: session)  # type: ignore[arg-type]
    request = CreateArtifactRequest(
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        jobId="cancelled-command",
        chapterId="chapter-1",
        kind="chapter_draft",
        status="awaiting_user",
        payload={"kind": "chapter_draft", "content": "正文"},
        createdByAgent="写作",
    )

    with pytest.raises(ApiError) as caught:
        await repository.create_or_revise("user-1", request)

    assert caught.value.status_code == 409
    assert caught.value.code == "WRITING_JOB_MISMATCH"
    assert session.added == []


@pytest.mark.asyncio
async def test_cancelled_or_old_job_cannot_submit_artifact_evaluation() -> None:
    session = _Session(
        [
            SimpleNamespace(id="task-1", chapterId="chapter-1"),
            SimpleNamespace(id="artifact-1", revision=1),
            None,
        ]
    )
    repository = ReviewRepository(lambda: session)  # type: ignore[arg-type]
    request = SubmitArtifactEvaluationRequest(
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        jobId="cancelled-command",
        revision=1,
        evaluatorAgent="编辑",
        verdict="pass",
        summary="通过",
    )

    with pytest.raises(ApiError) as caught:
        await repository.submit_evaluation("user-1", "artifact-1", request)

    assert caught.value.status_code == 409
    assert caught.value.code == "WRITING_JOB_MISMATCH"
    assert session.added == []


def _create_request(*, expected_revision: int | None) -> CreateArtifactRequest:
    return CreateArtifactRequest(
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        jobId="job-1",
        chapterId="chapter-1",
        artifactKey="task-1:write_chapter",
        kind="chapter_draft",
        status="under_review",
        payload={"kind": "chapter_draft", "content": "修订正文"},
        createdByAgent="写作",
        expectedRevision=expected_revision,
    )


@pytest.mark.asyncio
async def test_new_artifact_rejects_expected_revision_without_side_effect() -> None:
    session = _Session(
        [
            SimpleNamespace(id="task-1", chapterId="chapter-1"),
            "job-1",
            None,
        ]
    )
    repository = ReviewRepository(lambda: session)  # type: ignore[arg-type]

    with pytest.raises(ApiError) as caught:
        await repository.create_or_revise(
            "user-1", _create_request(expected_revision=1)
        )

    assert caught.value.code == "ARTIFACT_REVISION_CONFLICT"
    assert session.added == []


@pytest.mark.asyncio
async def test_revision_conflict_does_not_change_payload_or_create_revision() -> None:
    existing = SimpleNamespace(
        id="artifact-1",
        kind="chapter_draft",
        revision=2,
        payloadJson='{"kind":"chapter_draft","content":"原正文"}',
    )
    session = _Session(
        [
            SimpleNamespace(id="task-1", chapterId="chapter-1"),
            "job-1",
            existing,
        ]
    )
    repository = ReviewRepository(lambda: session)  # type: ignore[arg-type]

    with pytest.raises(ApiError) as caught:
        await repository.create_or_revise(
            "user-1", _create_request(expected_revision=1)
        )

    assert caught.value.code == "ARTIFACT_REVISION_CONFLICT"
    assert existing.revision == 2
    assert existing.payloadJson == '{"kind":"chapter_draft","content":"原正文"}'
    assert session.added == []
