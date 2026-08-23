"""按冻结 workflow 把视频队列任务分发到互不依赖的领域处理器。"""

from __future__ import annotations

from typing import Protocol

from inkforge_contracts.video_adaptation import (
    VideoAdaptationJobPayload,
    parse_video_adaptation_job_payload,
)

from ..queue.repository import QueueJob

_ADAPTATION_WORKFLOWS = {
    "chapter_cinematic_adaptation_v2",
    "chapter_shot_prompt_v2",
}


class _LegacyVideoHandler(Protocol):
    async def __call__(self, job: QueueJob) -> None: ...


class _AdaptationVideoHandler(Protocol):
    async def run(
        self,
        job: QueueJob,
        payload: VideoAdaptationJobPayload,
    ) -> None: ...


class VideoJobDispatcher:
    """队列集成层只识别 workflow；旧预览和章节改编不互相导入。"""

    def __init__(
        self,
        legacy_handler: _LegacyVideoHandler,
        adaptation_handler: _AdaptationVideoHandler,
    ) -> None:
        self._legacy_handler = legacy_handler
        self._adaptation_handler = adaptation_handler

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "video":
            raise ValueError("视频分发器收到错误任务类型")
        if job.payload.get("workflow") in _ADAPTATION_WORKFLOWS:
            await self._adaptation_handler.run(
                job,
                parse_video_adaptation_job_payload(job.payload),
            )
            return
        await self._legacy_handler(job)
