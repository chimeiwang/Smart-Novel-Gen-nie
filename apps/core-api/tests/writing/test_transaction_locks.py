from __future__ import annotations

from collections.abc import Sequence

import pytest
from inkforge_core.db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    WritingRunCommand,
    WritingTask,
)
from inkforge_core.errors import ApiError
from inkforge_core.writing.transaction_locks import (
    WritingLockRequest,
    lock_writing_rows,
)


class ScalarSession:
    def __init__(self, values: Sequence[object | None]) -> None:
        self.values = list(values)
        self.statements: list[object] = []

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        return self.values.pop(0)


def _novel(*, user_id: str = "user-1") -> Novel:
    return Novel(id="novel-1", userId=user_id)


def _chapter(chapter_id: str, *, novel_id: str = "novel-1") -> Chapter:
    return Chapter(id=chapter_id, novelId=novel_id)


def _task(*, novel_id: str = "novel-1", chapter_id: str = "chapter-a") -> WritingTask:
    return WritingTask(id="task-1", novelId=novel_id, chapterId=chapter_id)


def _artifact(
    *,
    novel_id: str = "novel-1",
    chapter_id: str = "chapter-a",
    task_id: str = "task-1",
) -> ReviewArtifact:
    return ReviewArtifact(
        id="artifact-1",
        novelId=novel_id,
        chapterId=chapter_id,
        taskId=task_id,
    )


def _command(
    *, task_id: str = "task-1", artifact_id: str | None = "artifact-1"
) -> WritingRunCommand:
    return WritingRunCommand(
        id="command-1", taskId=task_id, artifactId=artifact_id
    )


@pytest.mark.asyncio
async def test_lock_writing_rows_uses_fixed_order_and_sorted_unique_chapters() -> None:
    session = ScalarSession(
        [
            _novel(),
            _chapter("chapter-a"),
            _chapter("chapter-b"),
            _task(),
            _artifact(),
            _command(),
        ]
    )

    locked = await lock_writing_rows(  # type: ignore[arg-type]
        session,
        user_id="user-1",
        request=WritingLockRequest(
            novel_id="novel-1",
            chapter_ids=("chapter-b", "chapter-a", "chapter-b"),
            task_id="task-1",
            artifact_id="artifact-1",
            command_id="command-1",
        ),
    )

    entities = [
        statement.column_descriptions[0]["entity"].__name__
        for statement in session.statements
    ]
    assert entities == [
        "Novel",
        "Chapter",
        "Chapter",
        "WritingTask",
        "ReviewArtifact",
        "WritingRunCommand",
    ]
    assert all("FOR UPDATE" in str(statement) for statement in session.statements)
    chapter_params = [
        set(statement.compile().params.values())
        for statement in session.statements[1:3]
    ]
    assert chapter_params[0] >= {"novel-1", "chapter-a"}
    assert chapter_params[1] >= {"novel-1", "chapter-b"}
    assert [chapter.id for chapter in locked.chapters] == [
        "chapter-a",
        "chapter-b",
    ]
    assert locked.novel.id == "novel-1"
    assert locked.task is not None and locked.task.id == "task-1"
    assert locked.artifact is not None and locked.artifact.id == "artifact-1"
    assert locked.command is not None and locked.command.id == "command-1"


@pytest.mark.asyncio
async def test_lock_writing_rows_skips_unrequested_optional_rows() -> None:
    session = ScalarSession([_novel()])

    locked = await lock_writing_rows(  # type: ignore[arg-type]
        session,
        user_id="user-1",
        request=WritingLockRequest(novel_id="novel-1"),
    )

    assert len(session.statements) == 1
    assert locked.chapters == ()
    assert locked.task is None
    assert locked.artifact is None
    assert locked.command is None


@pytest.mark.parametrize(
    ("lock_request", "values", "error_code"),
    [
        (WritingLockRequest(novel_id="novel-1"), [None], "NOVEL_NOT_FOUND"),
        (
            WritingLockRequest(
                novel_id="novel-1", chapter_ids=("chapter-a",)
            ),
            [_novel(), None],
            "CHAPTER_NOT_FOUND",
        ),
        (
            WritingLockRequest(novel_id="novel-1", task_id="task-1"),
            [_novel(), None],
            "WRITING_TASK_NOT_FOUND",
        ),
        (
            WritingLockRequest(novel_id="novel-1", artifact_id="artifact-1"),
            [_novel(), None],
            "REVIEW_ARTIFACT_NOT_FOUND",
        ),
        (
            WritingLockRequest(novel_id="novel-1", command_id="command-1"),
            [_novel(), None],
            "WRITING_COMMAND_NOT_FOUND",
        ),
    ],
)
@pytest.mark.asyncio
async def test_lock_writing_rows_returns_stable_errors_for_missing_rows(
    lock_request: WritingLockRequest,
    values: list[object | None],
    error_code: str,
) -> None:
    session = ScalarSession(values)

    with pytest.raises(ApiError) as error:
        await lock_writing_rows(  # type: ignore[arg-type]
            session,
            user_id="user-1",
            request=lock_request,
        )

    assert error.value.status_code == 404
    assert error.value.code == error_code


@pytest.mark.parametrize(
    ("lock_request", "values", "error_code"),
    [
        (
            WritingLockRequest(novel_id="novel-1"),
            [_novel(user_id="user-2")],
            "NOVEL_NOT_FOUND",
        ),
        (
            WritingLockRequest(
                novel_id="novel-1", chapter_ids=("chapter-a",)
            ),
            [_novel(), _chapter("chapter-a", novel_id="novel-2")],
            "CHAPTER_NOT_FOUND",
        ),
        (
            WritingLockRequest(
                novel_id="novel-1",
                chapter_ids=("chapter-a",),
                task_id="task-1",
            ),
            [_novel(), _chapter("chapter-a"), _task(novel_id="novel-2")],
            "WRITING_TASK_NOT_FOUND",
        ),
        (
            WritingLockRequest(
                novel_id="novel-1",
                task_id="task-1",
                artifact_id="artifact-1",
            ),
            [_novel(), _task(), _artifact(task_id="task-2")],
            "REVIEW_ARTIFACT_NOT_FOUND",
        ),
        (
            WritingLockRequest(
                novel_id="novel-1",
                task_id="task-1",
                command_id="command-1",
            ),
            [_novel(), _task(), _command(task_id="task-2")],
            "WRITING_COMMAND_NOT_FOUND",
        ),
    ],
)
@pytest.mark.asyncio
async def test_lock_writing_rows_revalidates_ownership_and_associations(
    lock_request: WritingLockRequest,
    values: list[object],
    error_code: str,
) -> None:
    session = ScalarSession(values)

    with pytest.raises(ApiError) as error:
        await lock_writing_rows(  # type: ignore[arg-type]
            session,
            user_id="user-1",
            request=lock_request,
        )

    assert error.value.code == error_code
