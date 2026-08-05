from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    WritingRunCommand,
    WritingTask,
)
from ..errors import ApiError


@dataclass(frozen=True, slots=True)
class WritingLockRequest:
    novel_id: str
    chapter_ids: tuple[str, ...] = ()
    task_id: str | None = None
    artifact_id: str | None = None
    command_id: str | None = None


@dataclass(frozen=True, slots=True)
class LockedWritingRows:
    novel: Novel
    chapters: tuple[Chapter, ...]
    task: WritingTask | None
    artifact: ReviewArtifact | None
    command: WritingRunCommand | None


async def lock_writing_rows(
    session: AsyncSession,
    *,
    user_id: str,
    request: WritingLockRequest,
) -> LockedWritingRows:
    novel = await session.scalar(
        select(Novel)
        .where(Novel.id == request.novel_id, Novel.userId == user_id)
        .with_for_update()
    )
    if novel is None or novel.id != request.novel_id or novel.userId != user_id:
        raise _not_found("NOVEL_NOT_FOUND", "小说不存在")

    chapter_ids = tuple(sorted(set(request.chapter_ids)))
    chapters: list[Chapter] = []
    for chapter_id in chapter_ids:
        chapter = await session.scalar(
            select(Chapter)
            .where(
                Chapter.id == chapter_id,
                Chapter.novelId == request.novel_id,
            )
            .with_for_update()
        )
        if (
            chapter is None
            or chapter.id != chapter_id
            or chapter.novelId != request.novel_id
        ):
            raise _not_found("CHAPTER_NOT_FOUND", "章节不存在或不属于该小说")
        chapters.append(chapter)

    task: WritingTask | None = None
    if request.task_id is not None:
        task = await session.scalar(
            select(WritingTask)
            .where(WritingTask.id == request.task_id)
            .with_for_update()
        )
        if (
            task is None
            or task.id != request.task_id
            or task.novelId != request.novel_id
            or (chapter_ids and task.chapterId not in chapter_ids)
        ):
            raise _not_found("WRITING_TASK_NOT_FOUND", "写作任务不存在")

    artifact: ReviewArtifact | None = None
    if request.artifact_id is not None:
        artifact = await session.scalar(
            select(ReviewArtifact)
            .where(ReviewArtifact.id == request.artifact_id)
            .with_for_update()
        )
        if (
            artifact is None
            or artifact.id != request.artifact_id
            or artifact.novelId != request.novel_id
            or (
                request.task_id is not None
                and artifact.taskId != request.task_id
            )
            or (
                chapter_ids
                and artifact.chapterId is not None
                and artifact.chapterId not in chapter_ids
            )
        ):
            raise _not_found(
                "REVIEW_ARTIFACT_NOT_FOUND",
                "审核产物不存在或关联关系不匹配",
            )

    command: WritingRunCommand | None = None
    if request.command_id is not None:
        command_statement = (
            select(WritingRunCommand)
            .join(WritingTask, WritingTask.id == WritingRunCommand.taskId)
            .where(
                WritingRunCommand.id == request.command_id,
                WritingTask.novelId == request.novel_id,
            )
            .with_for_update(of=WritingRunCommand)
        )
        command = await session.scalar(command_statement)
        if (
            command is None
            or command.id != request.command_id
            or (
                request.task_id is not None
                and command.taskId != request.task_id
            )
            or (
                request.artifact_id is not None
                and command.artifactId != request.artifact_id
            )
        ):
            raise _not_found(
                "WRITING_COMMAND_NOT_FOUND",
                "写作命令不存在或关联关系不匹配",
            )

    return LockedWritingRows(
        novel=novel,
        chapters=tuple(chapters),
        task=task,
        artifact=artifact,
        command=command,
    )


def _not_found(code: str, message: str) -> ApiError:
    return ApiError(status_code=404, code=code, message=message)
