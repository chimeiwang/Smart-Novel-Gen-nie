"""视频制作业务服务与 Agent 投递边界。"""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile
from inkforge_contracts.video import (
    AssetModality,
    UploadAssetDuty,
    VideoPlanCallReservationRequest,
    VideoPlanCallReservationResponse,
    VideoPlanCompletionCallback,
    VideoPlanFailureCallback,
    VideoPlanProgressQuery,
    VideoPlanProgressResponse,
    VideoStoryPlanCheckpointCallback,
    validate_uploaded_asset_duty_modality,
)

from ..db.base import generate_id
from ..errors import ApiError
from .media_probe import VideoMediaProbe, VideoMediaProbeError
from .repository import VideoRepository
from .schemas import (
    CreateVideoProjectRequest,
    VideoAssetResponse,
    VideoProjectDetailResponse,
    VideoProjectListResponse,
    VideoProjectResponse,
)
from .storage import VideoAssetStorage


class VideoService:
    """协调数据库事实和供应商启用门禁；队列投递只由后台任务负责。"""

    def __init__(
        self,
        repository: VideoRepository,
        storage: VideoAssetStorage,
        *,
        video_preview_enabled: bool = False,
        seedance_configured: bool = False,
        seedance_enabled: bool = False,
        duration_probe: VideoMediaProbe | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._video_preview_enabled = video_preview_enabled
        self._seedance_configured = seedance_configured
        self._seedance_enabled = seedance_enabled
        self._duration_probe = duration_probe

    async def create_project(
        self,
        user_id: str,
        novel_id: str,
        request: CreateVideoProjectRequest,
    ) -> VideoProjectResponse:
        """创建小说级视频项目。"""

        self._require_preview_enabled()
        return await self._repository.create_project(user_id, novel_id, request)

    async def list_projects(self, user_id: str, novel_id: str) -> VideoProjectListResponse:
        """列出项目，并让空项目工作台也能显示真实能力门禁。"""

        return VideoProjectListResponse(
            projects=await self._repository.list_projects(user_id, novel_id),
            previewEnabled=self._video_preview_enabled,
            seedanceConfigured=self._seedance_configured,
            seedanceEnabled=self._seedance_enabled,
        )

    async def get_project(self, user_id: str, project_id: str) -> VideoProjectDetailResponse:
        """返回制作台完整读模型。"""

        return await self._repository.get_project(
            user_id,
            project_id,
            preview_enabled=self._video_preview_enabled,
            seedance_configured=self._seedance_configured,
            seedance_enabled=self._seedance_enabled,
        )

    async def complete_plan(self, callback: VideoPlanCompletionCallback) -> None:
        """把 Agent 成功回调交给仓储事务处理。"""

        await self._repository.complete_plan(callback)

    async def fail_plan(self, callback: VideoPlanFailureCallback) -> None:
        """把 Agent 失败回调交给仓储事务处理。"""

        await self._repository.fail_plan(callback)

    async def get_plan_progress(
        self,
        query: VideoPlanProgressQuery,
    ) -> VideoPlanProgressResponse:
        """读取跨进程可恢复的故事阶段进度。"""

        return await self._repository.get_plan_progress(query)

    async def save_story_plan_checkpoint(
        self,
        callback: VideoStoryPlanCheckpointCallback,
    ) -> None:
        """保存完整故事规范及其共享纠正预算状态。"""

        await self._repository.save_story_plan_checkpoint(callback)

    async def reserve_plan_call(
        self,
        request: VideoPlanCallReservationRequest,
    ) -> VideoPlanCallReservationResponse:
        """在供应商调用前原子预留全局五次预算中的一次。"""

        return await self._repository.reserve_plan_call(request)

    async def upload_asset(
        self,
        user_id: str,
        project_id: str,
        *,
        upload: UploadFile,
        name: str,
        modality: AssetModality,
        duty: UploadAssetDuty,
        source_kind: str,
    ) -> VideoAssetResponse:
        """安全保存真实媒体，数据库失败时补偿删除已写文件。"""

        self._require_preview_enabled()
        normalized_name = name.strip() or (upload.filename or "未命名素材")
        if len(normalized_name) > 200:
            raise ApiError(
                status_code=422,
                code="VIDEO_ASSET_NAME_TOO_LONG",
                message="素材名称不能超过 200 字",
            )
        if source_kind not in {
            "user_upload",
            "authorized_real",
            "virtual",
            "model_generated",
        }:
            raise ApiError(
                status_code=422,
                code="VIDEO_ASSET_SOURCE_INVALID",
                message="素材来源类型无效",
            )
        # 复用共享契约执行职责与模态的交叉校验；最终成片只能由受控导出器创建。
        try:
            validate_uploaded_asset_duty_modality(modality, duty)
        except ValueError as exc:
            raise ApiError(
                status_code=422,
                code="VIDEO_ASSET_DUTY_MODALITY_INVALID",
                message=str(exc),
            ) from exc
        await self._repository.require_project(user_id, project_id)
        asset_id = generate_id()
        stored = await self._storage.save(project_id, asset_id, modality, upload)
        try:
            duration_ms: int | None = None
            if modality in {"audio", "video"}:
                if self._duration_probe is None or not self._duration_probe.available:
                    raise ApiError(
                        status_code=503,
                        code="VIDEO_MEDIA_PROBE_UNAVAILABLE",
                        message="当前环境缺少 ffprobe，不能登记音视频素材的真实时长",
                    )
                try:
                    duration_ms = await self._duration_probe.probe_duration_ms(
                        stored.absolute_path
                    )
                except VideoMediaProbeError as exc:
                    raise ApiError(
                        status_code=422,
                        code="VIDEO_ASSET_DURATION_INVALID",
                        message="无法读取上传音视频的有效时长",
                    ) from exc
            return await self._repository.create_asset(
                user_id,
                project_id,
                asset_id,
                name=normalized_name,
                modality=modality,
                duty=duty,
                source_kind=source_kind,
                duration_ms=duration_ms,
                stored=stored,
            )
        except Exception:
            self._storage.delete(stored.storage_key)
            raise

    async def confirm_asset(
        self,
        user_id: str,
        asset_id: str,
        rights_status: str,
    ) -> VideoAssetResponse:
        """保存用户权利声明并按状态锁定或解锁素材。"""

        self._require_preview_enabled()
        return await self._repository.confirm_asset(user_id, asset_id, rights_status)

    async def get_asset_file(
        self,
        user_id: str,
        asset_id: str,
    ) -> tuple[Path, str, str]:
        """归属校验后解析素材文件，供受保护下载接口使用。"""

        asset = await self._repository.get_asset_file(user_id, asset_id)
        return self._storage.resolve(asset.storage_key), asset.mime_type, asset.name

    def _require_preview_enabled(self) -> None:
        """用 Core 开关统一阻断所有新视频写入，历史读取不受影响。"""

        if not self._video_preview_enabled:
            raise ApiError(
                status_code=503,
                code="VIDEO_PREVIEW_DISABLED",
                message="长篇视频开发预览暂未启用",
            )
