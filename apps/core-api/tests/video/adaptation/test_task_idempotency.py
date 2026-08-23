"""章节影视化任务网络重放必须先命中自身任务。"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import inkforge_core.video.adaptation.repository as repository_module
import pytest
from inkforge_contracts.video_adaptation import ChapterAdaptationPlanJobPayload
from inkforge_core.db.models import (
    VideoAdaptationTask,
    VideoChapterAdaptation,
    VideoChapterAdaptationHead,
    VideoProject,
)
from inkforge_core.video.adaptation.repository import VideoAdaptationRepository
from inkforge_core.video.adaptation.schemas import StartShotPlanRunRequest


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        del args


class _Session:
    def __init__(self, existing: VideoAdaptationTask) -> None:
        self.existing = existing

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def begin(self) -> _Transaction:
        return _Transaction()

    async def scalar(self, statement: object) -> VideoAdaptationTask:
        del statement
        return self.existing


@pytest.mark.asyncio
async def test_plan_task_replay_returns_existing_before_active_task_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "人物推门进入雨夜书房。"
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
    existing = VideoAdaptationTask(
        id="task-1",
        adaptationId="adaptation-1",
        projectId="project-1",
        novelId="novel-1",
        jobId="job-1",
        kind="shot_plan",
        workflow=payload.workflow,
        provider="deepseek",
        status="processing",
        idempotencyKey="existing",
        requestJson=payload.model_dump_json(),
        checkpointStage="none",
        attemptCount=0,
        updatedAt=datetime(2026, 8, 18),
    )
    session = _Session(existing)
    adaptation = VideoChapterAdaptation(
        id="adaptation-1",
        projectId="project-1",
        novelId="novel-1",
    )
    project = VideoProject(id="project-1", novelId="novel-1", mode="series")
    head = VideoChapterAdaptationHead(adaptationId="adaptation-1", revision=1)

    async def owned(*args: object, **kwargs: object) -> tuple[Any, Any, Any]:
        del args, kwargs
        return adaptation, project, head

    async def forbidden_guard(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("幂等重放不应先进入活动任务互斥门禁")

    monkeypatch.setattr(repository_module, "_require_owned_adaptation", owned)
    monkeypatch.setattr(repository_module, "_require_no_active_task", forbidden_guard)
    repository = VideoAdaptationRepository(lambda: session)  # type: ignore[arg-type]

    accepted = await repository.create_plan_task(
        "user-1",
        "adaptation-1",
        StartShotPlanRunRequest(
            clientRequestId="0123456789abcdef",
            pacingPreset="short_drama",
            targetEpisodeSeconds=90,
        ),
    )

    assert accepted.task_id == "task-1"
