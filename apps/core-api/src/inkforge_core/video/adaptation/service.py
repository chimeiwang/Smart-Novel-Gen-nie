"""章节影视化改编业务门禁与仓储编排。"""

from __future__ import annotations

from inkforge_contracts.video_adaptation import (
    VideoAdaptationCheckpointCallback,
    VideoAdaptationFailureCallback,
    VideoAdaptationPlanCompletionCallback,
    VideoAdaptationPromptCompletionCallback,
    VideoAdaptationWorkflowProgressQuery,
    VideoAdaptationWorkflowProgressResponse,
)

from ...errors import ApiError
from .repository import VideoAdaptationRepository
from .schemas import (
    ChapterAdaptationListResponse,
    ChapterAdaptationResponse,
    ChapterAdaptationTaskAcceptedResponse,
    ConfirmAdaptationPlanRequest,
    CreateChapterAdaptationRequest,
    DiscardAdaptationCandidateRequest,
    SaveEpisodePlanRequest,
    SaveShotPromptRequest,
    StartPromptRunRequest,
    StartShotPlanRunRequest,
)


class VideoAdaptationService:
    """浏览器与 Agent 共用同一业务边界，所有正式写入仍由 Core 完成。"""

    def __init__(
        self,
        repository: VideoAdaptationRepository,
        *,
        video_preview_enabled: bool,
    ) -> None:
        self._repository = repository
        self._video_preview_enabled = video_preview_enabled

    async def create_adaptation(
        self,
        user_id: str,
        project_id: str,
        request: CreateChapterAdaptationRequest,
    ) -> ChapterAdaptationResponse:
        self._require_enabled()
        return await self._repository.create_adaptation(user_id, project_id, request)

    async def list_adaptations(
        self,
        user_id: str,
        project_id: str,
    ) -> ChapterAdaptationListResponse:
        return await self._repository.list_adaptations(user_id, project_id)

    async def get_adaptation(
        self,
        user_id: str,
        adaptation_id: str,
    ) -> ChapterAdaptationResponse:
        return await self._repository.get_adaptation(user_id, adaptation_id)

    async def start_plan(
        self,
        user_id: str,
        adaptation_id: str,
        request: StartShotPlanRunRequest,
    ) -> ChapterAdaptationTaskAcceptedResponse:
        self._require_enabled()
        accepted = await self._repository.create_plan_task(
            user_id,
            adaptation_id,
            request,
        )
        return ChapterAdaptationTaskAcceptedResponse(
            adaptation=await self._repository.get_adaptation(user_id, adaptation_id),
            task=await self._repository.get_task_response(user_id, accepted.task_id),
        )

    async def confirm_plan(
        self,
        user_id: str,
        adaptation_id: str,
        request: ConfirmAdaptationPlanRequest,
    ) -> ChapterAdaptationResponse:
        self._require_enabled()
        return await self._repository.confirm_plan(user_id, adaptation_id, request)

    async def save_episode_plan(
        self,
        user_id: str,
        adaptation_id: str,
        request: SaveEpisodePlanRequest,
    ) -> ChapterAdaptationResponse:
        self._require_enabled()
        return await self._repository.save_episode_plan(user_id, adaptation_id, request)

    async def discard_candidate(
        self,
        user_id: str,
        adaptation_id: str,
        request: DiscardAdaptationCandidateRequest,
    ) -> ChapterAdaptationResponse:
        self._require_enabled()
        return await self._repository.discard_candidate(
            user_id,
            adaptation_id,
            request,
        )

    async def start_prompts(
        self,
        user_id: str,
        adaptation_id: str,
        request: StartPromptRunRequest,
    ) -> ChapterAdaptationTaskAcceptedResponse:
        self._require_enabled()
        accepted = await self._repository.create_prompt_task(
            user_id,
            adaptation_id,
            request,
        )
        return ChapterAdaptationTaskAcceptedResponse(
            adaptation=await self._repository.get_adaptation(user_id, adaptation_id),
            task=await self._repository.get_task_response(user_id, accepted.task_id),
        )

    async def save_prompt(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        request: SaveShotPromptRequest,
    ) -> ChapterAdaptationResponse:
        self._require_enabled()
        return await self._repository.save_prompt(
            user_id,
            adaptation_id,
            shot_id,
            request,
        )

    async def get_progress(
        self,
        query: VideoAdaptationWorkflowProgressQuery,
    ) -> VideoAdaptationWorkflowProgressResponse:
        return await self._repository.get_workflow_progress(query)

    async def save_checkpoint(self, callback: VideoAdaptationCheckpointCallback) -> None:
        await self._repository.save_checkpoint(callback)

    async def complete_plan(self, callback: VideoAdaptationPlanCompletionCallback) -> None:
        await self._repository.complete_plan(callback)

    async def complete_prompts(
        self,
        callback: VideoAdaptationPromptCompletionCallback,
    ) -> None:
        await self._repository.complete_prompts(callback)

    async def fail_task(self, callback: VideoAdaptationFailureCallback) -> None:
        await self._repository.fail_task(callback)

    def _require_enabled(self) -> None:
        if not self._video_preview_enabled:
            raise ApiError(
                status_code=503,
                code="VIDEO_PREVIEW_DISABLED",
                message="当前环境未开启视频开发预览写入",
            )
