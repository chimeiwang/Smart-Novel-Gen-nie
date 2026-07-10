from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..errors import ApiError
from .schemas import (
    CreateNovelRequest,
    CreateNovelResponse,
    DashboardResponse,
    NovelResponse,
    WorkspaceResponse,
)


@dataclass(frozen=True, slots=True)
class NovelCreation:
    user_id: str
    name: str
    summary: str | None
    story_progress: str | None
    story_length_profile: str
    target_total_word_count: int
    genre: str | None
    core_selling_point: str | None
    reader_promise: str | None
    notes: str | None
    first_chapter_title: str
    first_chapter_order: int
    outline_content: str
    current_stage: str
    current_goal: str | None


class NovelRepositoryPort(Protocol):
    async def create_novel(self, creation: NovelCreation) -> dict[str, str]: ...
    async def list_dashboard(self, user_id: str) -> DashboardResponse: ...
    async def list_novels(self, user_id: str) -> list[NovelResponse]: ...
    async def get_novel(self, novel_id: str, user_id: str) -> NovelResponse: ...
    async def get_workspace(
        self, novel_id: str, user_id: str, chapter_id: str | None
    ) -> WorkspaceResponse: ...


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class NovelService:
    def __init__(self, repository: NovelRepositoryPort) -> None:
        self._repository = repository

    async def create_novel(self, user_id: str, request: CreateNovelRequest) -> CreateNovelResponse:
        name = request.name.strip()
        if not name:
            raise ApiError(
                status_code=422,
                code="NOVEL_NAME_REQUIRED",
                message="小说名称不能为空",
            )
        goal = _clean_optional(request.firstChapterGoal)
        protagonist = _clean_optional(request.protagonist)
        notes = (
            "\n".join(
                part
                for part in (
                    f"主角起点：{protagonist}" if protagonist else "",
                    f"第一章目标：{goal}" if goal else "",
                )
                if part
            )
            or None
        )
        defaults = {"short_medium": 80_000, "long_serial": 1_000_000}
        result = await self._repository.create_novel(
            NovelCreation(
                user_id=user_id,
                name=name,
                summary=_clean_optional(request.summary),
                story_progress=f"第一章目标：{goal}" if goal else None,
                story_length_profile=request.storyLengthProfile,
                target_total_word_count=request.targetTotalWordCount
                or defaults[request.storyLengthProfile],
                genre=_clean_optional(request.genre),
                core_selling_point=_clean_optional(request.coreSellingPoint),
                reader_promise=_clean_optional(request.readerPromise),
                notes=notes,
                first_chapter_title="第一章",
                first_chapter_order=1,
                outline_content="",
                current_stage="开篇",
                current_goal=goal,
            )
        )
        return CreateNovelResponse.model_validate(result)

    async def dashboard(self, user_id: str) -> DashboardResponse:
        return await self._repository.list_dashboard(user_id)

    async def list_novels(self, user_id: str) -> list[NovelResponse]:
        return await self._repository.list_novels(user_id)

    async def get_novel(self, user_id: str, novel_id: str) -> NovelResponse:
        return await self._repository.get_novel(novel_id, user_id)

    async def get_workspace(
        self, user_id: str, novel_id: str, chapter_id: str | None
    ) -> WorkspaceResponse:
        return await self._repository.get_workspace(novel_id, user_id, chapter_id)
