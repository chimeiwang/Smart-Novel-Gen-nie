from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from ..errors import ApiError
from ..novels.schemas import WorkspaceChapter
from .schemas import (
    ChapterMutationResponse,
    ChapterProgressRequest,
    ChapterStatusRequest,
    ChapterStatusResponse,
    UpdateChapterRequest,
)


class ChapterRecordPort(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def novel_id(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def completed_at(self) -> datetime | None: ...


class ChapterRepositoryPort(Protocol):
    async def require_chapter(
        self, chapter_id: str, user_id: str, *, lock: bool = False
    ) -> ChapterRecordPort: ...
    async def create_chapter(self, novel_id: str, user_id: str) -> WorkspaceChapter: ...
    async def list_chapters(self, novel_id: str, user_id: str) -> list[WorkspaceChapter]: ...
    async def get_chapter(self, chapter_id: str, user_id: str) -> WorkspaceChapter: ...
    async def update_draft(
        self, chapter_id: str, user_id: str, title: str, content: str
    ) -> datetime: ...
    async def upsert_progress(self, chapter_id: str, user_id: str, content: str) -> datetime: ...
    async def get_consistency_status(self, chapter_id: str) -> str | None: ...
    async def set_status_with_default_check(
        self,
        chapter_id: str,
        user_id: str,
        status: str,
        completed_at: datetime | None,
        *,
        create_default_check: bool,
    ) -> ChapterRecordPort: ...


class ChapterService:
    def __init__(self, repository: ChapterRepositoryPort) -> None:
        self._repository = repository

    async def create_chapter(self, user_id: str, novel_id: str) -> WorkspaceChapter:
        return await self._repository.create_chapter(novel_id, user_id)

    async def list_chapters(self, user_id: str, novel_id: str) -> list[WorkspaceChapter]:
        return await self._repository.list_chapters(novel_id, user_id)

    async def get_chapter(self, user_id: str, chapter_id: str) -> WorkspaceChapter:
        return await self._repository.get_chapter(chapter_id, user_id)

    async def update_chapter(
        self, user_id: str, chapter_id: str, request: UpdateChapterRequest
    ) -> ChapterMutationResponse:
        await self._repository.require_chapter(chapter_id, user_id)
        title = request.title.strip() or "未命名章节"
        updated_at = await self._repository.update_draft(
            chapter_id, user_id, title, request.content
        )
        return ChapterMutationResponse(updatedAt=updated_at)

    async def update_progress(
        self, user_id: str, chapter_id: str, request: ChapterProgressRequest
    ) -> ChapterMutationResponse:
        await self._repository.require_chapter(chapter_id, user_id)
        updated_at = await self._repository.upsert_progress(chapter_id, user_id, request.content)
        return ChapterMutationResponse(updatedAt=updated_at)

    async def set_status(
        self, user_id: str, chapter_id: str, request: ChapterStatusRequest
    ) -> ChapterStatusResponse:
        chapter = await self._repository.require_chapter(chapter_id, user_id, lock=True)
        target = request.status
        if target == chapter.status:
            if target == "review":
                chapter = await self._repository.set_status_with_default_check(
                    chapter_id,
                    user_id,
                    target,
                    chapter.completed_at,
                    create_default_check=True,
                )
            return ChapterStatusResponse(
                id=chapter.id, status=chapter.status, completedAt=chapter.completed_at
            )
        allowed = {
            "drafting": {"review"},
            "review": {"drafting", "completed"},
            "completed": {"drafting"},
        }
        if target not in allowed.get(chapter.status, set()):
            raise ApiError(
                status_code=409,
                code="INVALID_CHAPTER_STATUS_TRANSITION",
                message="章节状态不能这样切换",
            )
        if target == "completed":
            check_status = await self._repository.get_consistency_status(chapter_id)
            if check_status not in {"completed", "skipped"}:
                raise ApiError(
                    status_code=409,
                    code="QUALITY_CHECK_REQUIRED",
                    message="一致性终检完成或跳过后，才能标记章节完成",
                )
        completed_at = datetime.now(UTC) if target == "completed" else None
        updated = await self._repository.set_status_with_default_check(
            chapter_id,
            user_id,
            target,
            completed_at,
            create_default_check=target == "review",
        )
        return ChapterStatusResponse(
            id=updated.id, status=updated.status, completedAt=updated.completed_at
        )
