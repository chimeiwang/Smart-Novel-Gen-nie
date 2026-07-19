from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..errors import ApiError
from .schemas import (
    CreateNovelRequest,
    CreateNovelResponse,
    DashboardResponse,
    NovelResponse,
    ShortMediumCreateNovelRequest,
    UpdateNovelTitleRequest,
    UpdateNovelTitleResponse,
    WorkspaceBootstrapResponse,
    WorkspaceLoreResponse,
    WorkspacePlanningResponse,
    WorkspaceResourcesResponse,
    WorkspaceResponse,
)


@dataclass(frozen=True, slots=True)
class NovelCreation:
    user_id: str
    name: str
    summary: str | None
    story_progress: str | None
    story_length_profile: str
    target_total_word_count: int | None
    genre: str | None
    core_selling_point: str | None
    reader_promise: str | None
    notes: str | None
    first_chapter_title: str
    first_chapter_order: int
    outline_content: str
    current_stage: str
    current_goal: str | None


def require_valid_creation_target(profile: str, target: int | None) -> None:
    if profile == "short_medium":
        if target is not None and not 6_000 <= target <= 80_000:
            raise ApiError(
                status_code=422,
                code="SHORT_STORY_TARGET_WORD_COUNT_INVALID",
                message="中短篇篇幅参考必须为空或在 6000 到 80000 之间",
            )
        return
    if profile == "long_serial":
        if target is None or target <= 0:
            raise ApiError(
                status_code=422,
                code="NOVEL_TARGET_WORD_COUNT_INVALID",
                message="长篇目标总字数必须大于 0",
            )
        return
    raise ApiError(
        status_code=422,
        code="STORY_LENGTH_PROFILE_INVALID",
        message="作品篇幅模式无效",
    )


class NovelRepositoryPort(Protocol):
    async def create_novel(self, creation: NovelCreation) -> dict[str, str]: ...
    async def list_dashboard(self, user_id: str) -> DashboardResponse: ...
    async def list_novels(self, user_id: str) -> list[NovelResponse]: ...
    async def get_novel(self, novel_id: str, user_id: str) -> NovelResponse: ...
    async def update_title(
        self,
        novel_id: str,
        user_id: str,
        name: str,
        expected_updated_at: datetime,
    ) -> UpdateNovelTitleResponse: ...
    async def get_workspace(
        self, novel_id: str, user_id: str, chapter_id: str | None
    ) -> WorkspaceResponse: ...
    async def get_workspace_bootstrap(
        self, novel_id: str, user_id: str, chapter_id: str | None
    ) -> WorkspaceBootstrapResponse: ...
    async def get_workspace_lore(
        self, novel_id: str, user_id: str
    ) -> WorkspaceLoreResponse: ...
    async def get_workspace_planning(
        self, novel_id: str, user_id: str
    ) -> WorkspacePlanningResponse: ...
    async def get_workspace_resources(
        self, novel_id: str, user_id: str
    ) -> WorkspaceResourcesResponse: ...


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class NovelService:
    def __init__(self, repository: NovelRepositoryPort) -> None:
        self._repository = repository

    async def create_novel(self, user_id: str, request: CreateNovelRequest) -> CreateNovelResponse:
        if isinstance(request, ShortMediumCreateNovelRequest):
            name = (request.name or "").strip() or "未命名中短篇"
            summary = _clean_optional(request.inspiration)
            if summary is None:
                raise ApiError(
                    status_code=422,
                    code="SHORT_STORY_INSPIRATION_REQUIRED",
                    message="中短篇灵感不能为空",
                )
            goal = None
            protagonist = None
            target_total_word_count = request.targetTotalWordCount
            genre = None
            core_selling_point = None
            reader_promise = None
            first_chapter_title = "正文"
        else:
            name = request.name.strip()
            summary = _clean_optional(request.summary)
            goal = _clean_optional(request.firstChapterGoal)
            protagonist = _clean_optional(request.protagonist)
            target_total_word_count = request.targetTotalWordCount or 1_000_000
            genre = _clean_optional(request.genre)
            core_selling_point = _clean_optional(request.coreSellingPoint)
            reader_promise = _clean_optional(request.readerPromise)
            first_chapter_title = "第一章"
        require_valid_creation_target(request.storyLengthProfile, target_total_word_count)
        if not name:
            raise ApiError(
                status_code=422,
                code="NOVEL_NAME_REQUIRED",
                message="小说名称不能为空",
            )
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
        result = await self._repository.create_novel(
            NovelCreation(
                user_id=user_id,
                name=name,
                summary=summary,
                story_progress=f"第一章目标：{goal}" if goal else None,
                story_length_profile=request.storyLengthProfile,
                target_total_word_count=target_total_word_count,
                genre=genre,
                core_selling_point=core_selling_point,
                reader_promise=reader_promise,
                notes=notes,
                first_chapter_title=first_chapter_title,
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

    async def update_title(
        self, user_id: str, novel_id: str, request: UpdateNovelTitleRequest
    ) -> UpdateNovelTitleResponse:
        name = request.name.strip()
        if not name:
            raise ApiError(
                status_code=422,
                code="NOVEL_NAME_REQUIRED",
                message="小说名称不能为空",
            )
        return await self._repository.update_title(
            novel_id,
            user_id,
            name,
            request.expectedUpdatedAt,
        )

    async def get_workspace(
        self, user_id: str, novel_id: str, chapter_id: str | None
    ) -> WorkspaceResponse:
        return await self._repository.get_workspace(novel_id, user_id, chapter_id)

    async def get_workspace_bootstrap(
        self, user_id: str, novel_id: str, chapter_id: str | None
    ) -> WorkspaceBootstrapResponse:
        return await self._repository.get_workspace_bootstrap(novel_id, user_id, chapter_id)

    async def get_workspace_lore(
        self, user_id: str, novel_id: str
    ) -> WorkspaceLoreResponse:
        return await self._repository.get_workspace_lore(novel_id, user_id)

    async def get_workspace_planning(
        self, user_id: str, novel_id: str
    ) -> WorkspacePlanningResponse:
        return await self._repository.get_workspace_planning(novel_id, user_id)

    async def get_workspace_resources(
        self, user_id: str, novel_id: str
    ) -> WorkspaceResourcesResponse:
        return await self._repository.get_workspace_resources(novel_id, user_id)
