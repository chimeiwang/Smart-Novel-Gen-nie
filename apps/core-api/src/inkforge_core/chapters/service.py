from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..novels.schemas import ChapterStatus, WorkspaceChapter
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
    def status(self) -> ChapterStatus: ...

    @property
    def completed_at(self) -> datetime | None: ...

    @property
    def updated_at(self) -> datetime: ...


class ChapterRepositoryPort(Protocol):
    async def require_chapter(
        self, chapter_id: str, user_id: str, *, lock: bool = False
    ) -> ChapterRecordPort: ...
    async def create_chapter(self, novel_id: str, user_id: str) -> WorkspaceChapter: ...
    async def list_chapters(self, novel_id: str, user_id: str) -> list[WorkspaceChapter]: ...
    async def get_chapter(self, chapter_id: str, user_id: str) -> WorkspaceChapter: ...
    async def update_draft(
        self,
        chapter_id: str,
        user_id: str,
        title: str,
        content: str,
        expected_updated_at: datetime,
    ) -> datetime: ...
    async def upsert_progress(self, chapter_id: str, user_id: str, content: str) -> datetime: ...
    async def transition_status(
        self,
        chapter_id: str,
        user_id: str,
        status: ChapterStatus,
        expected_updated_at: datetime,
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
            chapter_id,
            user_id,
            title,
            request.content,
            request.expectedUpdatedAt,
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
        updated = await self._repository.transition_status(
            chapter_id,
            user_id,
            request.status,
            request.expectedUpdatedAt,
        )
        return ChapterStatusResponse(
            id=updated.id,
            status=updated.status,
            completedAt=updated.completed_at,
            updatedAt=updated.updated_at,
        )
