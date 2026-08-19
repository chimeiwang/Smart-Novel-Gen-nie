"""视频队列入口按 workflow 隔离旧预览与章节改编。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from inkforge_agents.jobs.video_dispatch import VideoJobDispatcher
from inkforge_agents.queue.repository import QueueJob
from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanJobPayload,
    VideoAdaptationJobPayload,
)


class _LegacyHandler:
    def __init__(self) -> None:
        self.jobs: list[QueueJob] = []

    async def __call__(self, job: QueueJob) -> None:
        self.jobs.append(job)


class _AdaptationHandler:
    def __init__(self) -> None:
        self.values: list[tuple[QueueJob, VideoAdaptationJobPayload]] = []

    async def run(
        self,
        job: QueueJob,
        payload: VideoAdaptationJobPayload,
    ) -> None:
        self.values.append((job, payload))


def _job(payload: dict[str, object]) -> QueueJob:
    return QueueJob(
        jobId="job-1",
        kind="video",
        runId="task-1",
        taskId="task-1",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload=payload,
        createdAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_dispatches_chapter_adaptation_without_entering_legacy_handler() -> None:
    source = "人物推门。"
    payload = ChapterAdaptationPlanJobPayload(
        workflow="chapter_cinematic_adaptation_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        chapterId="chapter-1",
        chapterTitle="第一章",
        sourceText=source,
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        ratio="9:16",
        targetLanguage="zh-CN",
        pacingPreset="short_drama",
        targetEpisodeSeconds=90,
    )
    legacy = _LegacyHandler()
    adaptation = _AdaptationHandler()
    dispatcher = VideoJobDispatcher(legacy, adaptation)

    await dispatcher(_job(payload.model_dump(mode="json")))

    assert legacy.jobs == []
    assert adaptation.values[0][1] == payload


@pytest.mark.asyncio
async def test_dispatches_legacy_workflow_without_importing_adaptation_logic() -> None:
    legacy = _LegacyHandler()
    adaptation = _AdaptationHandler()
    dispatcher = VideoJobDispatcher(legacy, adaptation)
    job = _job({"workflow": "video_scene_plan_v1"})

    await dispatcher(job)

    assert legacy.jobs == [job]
    assert adaptation.values == []
