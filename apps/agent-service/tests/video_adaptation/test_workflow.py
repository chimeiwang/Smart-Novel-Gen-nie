"""章节影视化工作流按 Scene/Beat/Shot 执行并持久化中间检查点。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from inkforge_agents.clients.core import RunResource
from inkforge_agents.jobs.video_adaptation import (
    ModelVideoAdaptationPlanner,
    VideoAdaptationJobHandler,
    _normalize_duration_ms,
)
from inkforge_agents.jobs.video_adaptation_quality import validate_cinematic_candidate
from inkforge_agents.providers.base import ModelTurnRequest, ModelTurnResult, ModelUsage
from inkforge_agents.queue.repository import QueueJob
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_contracts.video import LongSerialSettingSnapshot
from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanCandidate,
    ChapterAdaptationPlanJobPayload,
    ChapterAdaptationPromptJobPayload,
    ChapterAdaptationSourceRange,
    CinematicSceneCandidate,
    CinematicShotCandidate,
    DramaticBeatCandidate,
    VideoAdaptationCheckpointCallback,
    VideoAdaptationFailureCallback,
    VideoAdaptationPlanCompletionCallback,
    VideoAdaptationPromptCompletionCallback,
    VideoAdaptationWorkflowProgressQuery,
    VideoAdaptationWorkflowProgressResponse,
)


class _Provider:
    billable = False
    provider_name = "openai_compatible"
    model_name = "deepseek-v4-flash"

    def __init__(self) -> None:
        self.requests: list[ModelTurnRequest] = []

    def supports_structured_output(self, route: object) -> bool:
        return route == "responses_json_schema_v1"

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.requests.append(request)
        assert request.structuredOutput is not None
        name = request.structuredOutput.name
        if name == "chapter_dramatic_structure_v2":
            value = {
                "scenes": [
                    {
                        "title": "雨夜书房",
                        "locationLabel": "书房",
                        "timeLabel": "雨夜",
                        "objective": "林岚确认来客带来的线索",
                        "changeSummary": "染血钥匙让等待变成危险预警",
                        "beats": [
                            {
                                "title": "沉默来客交出钥匙",
                                "sourceUnitIds": ["U001", "U002", "U003"],
                                "dramaticTurn": "林岚从等待转为意识到危险",
                                "visualStrategy": "对白跨越倾听反应，最后以钥匙特写揭示",
                            }
                        ],
                    }
                ]
            }
        elif name == "chapter_cinematic_shot_design_v2":
            value = {
                "shots": [
                    {
                        "beatKey": "B01",
                        "title": "建立雨夜书房",
                        "narrativePurpose": "establishing",
                        "adaptationType": "supplemental",
                        "shotScale": "long",
                        "cameraAngle": "eye_level",
                        "cameraMovement": "locked",
                        "visualIntent": "门外冷光切进安静书房，林岚坐在桌边",
                        "audioMode": "ambient",
                        "audioIntent": "持续雨声和门轴声",
                        "cutReason": "进入新场景先建立人物空间关系和压迫氛围",
                        "timelineDurationMs": 2000,
                        "sourceUnitIds": [],
                    },
                    {
                        "beatKey": "B01",
                        "title": "林岚发问",
                        "narrativePurpose": "dialogue",
                        "adaptationType": "direct",
                        "shotScale": "two_shot",
                        "cameraAngle": "eye_level",
                        "cameraMovement": "locked",
                        "visualIntent": "两人保持距离，林岚抬眼发问，来客没有移动",
                        "audioMode": "sync_dialogue",
                        "audioIntent": "保留林岚原文对白，雨声在对白下持续",
                        "cutReason": "从空间建立进入两人关系主镜头，承载完整发问而非逐句切换",
                        "timelineDurationMs": 3000,
                        "sourceUnitIds": ["U001", "U002"],
                    },
                    {
                        "beatKey": "B01",
                        "title": "沉默反应",
                        "narrativePurpose": "reaction",
                        "adaptationType": "supplemental",
                        "shotScale": "close",
                        "cameraAngle": "eye_level",
                        "cameraMovement": "locked",
                        "visualIntent": "来客沉默看着林岚，手仍藏在画外",
                        "audioMode": "silence",
                        "audioIntent": "短暂压低雨声，不新增对白",
                        "cutReason": "切到倾听者沉默反应，让未回答本身形成悬念",
                        "timelineDurationMs": 1500,
                        "sourceUnitIds": [],
                    },
                    {
                        "beatKey": "B01",
                        "title": "钥匙落桌",
                        "narrativePurpose": "insert",
                        "adaptationType": "direct",
                        "shotScale": "extreme_close",
                        "cameraAngle": "high_angle",
                        "cameraMovement": "push_in",
                        "visualIntent": "染血钥匙被放上桌面，血迹进入焦点",
                        "audioMode": "ambient",
                        "audioIntent": "钥匙碰桌的金属声",
                        "cutReason": "关键物件改变信息量，以插入特写完成节拍揭示",
                        "timelineDurationMs": 1500,
                        "sourceUnitIds": ["U003"],
                    },
                ],
                "suggestedEpisodeBreakAfterShotNumbers": [],
            }
        elif name == "chapter_cinematic_review_v2":
            value = {"decision": "pass", "summary": "切镜均有戏剧动机", "requiredChanges": []}
        elif name == "chapter_shot_prompt_spec_v2":
            value = {
                "prompts": [
                    {
                        "shotKey": "S01",
                        "spec": {
                            "subjectAndScene": "雨夜书房内，林岚坐在桌边",
                            "visibleAction": "门外冷光切入，林岚抬眼看向来客",
                            "performance": "克制警觉，呼吸平稳",
                            "camera": "全景固定机位，不越过人物轴线",
                            "audio": "持续雨声与轻微门轴声",
                            "continuity": "人物保持在画面左侧，视线朝右",
                            "negativeConstraints": ["禁止新增人物", "禁止字幕"],
                        },
                    }
                ]
            }
        else:
            raise AssertionError(name)
        return ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput=value,
            usage=ModelUsage(promptTokens=100, completionTokens=100, totalTokens=200),
            finishReason="stop",
            rawFinishReason="stop",
        )


class _Core:
    def __init__(self) -> None:
        self.checkpoints: list[VideoAdaptationCheckpointCallback] = []
        self.completed: list[VideoAdaptationPlanCompletionCallback] = []
        self.failed: list[VideoAdaptationFailureCallback] = []
        self.prompt_completed: list[VideoAdaptationPromptCompletionCallback] = []

    async def get_video_adaptation_progress(
        self,
        resource: RunResource,
        query: VideoAdaptationWorkflowProgressQuery,
    ) -> VideoAdaptationWorkflowProgressResponse:
        del resource
        return VideoAdaptationWorkflowProgressResponse(
            **query.model_dump(mode="python"),
            status="active",
            checkpoint=None,
        )

    async def save_video_adaptation_checkpoint(
        self,
        resource: RunResource,
        callback: VideoAdaptationCheckpointCallback,
    ) -> None:
        del resource
        self.checkpoints.append(callback)

    async def complete_video_adaptation_plan(
        self,
        resource: RunResource,
        callback: VideoAdaptationPlanCompletionCallback,
    ) -> None:
        del resource
        self.completed.append(callback)

    async def complete_video_adaptation_prompts(
        self,
        resource: RunResource,
        callback: VideoAdaptationPromptCompletionCallback,
    ) -> None:
        del resource
        self.prompt_completed.append(callback)

    async def fail_video_adaptation(
        self,
        resource: RunResource,
        callback: VideoAdaptationFailureCallback,
    ) -> None:
        del resource
        self.failed.append(callback)


@pytest.mark.asyncio
async def test_plan_workflow_persists_dramatic_checkpoint_before_cinematic_candidate() -> None:
    source = "“你来了。”林岚抬眼。男人沉默着放下染血的钥匙。"
    payload = ChapterAdaptationPlanJobPayload(
        workflow="chapter_cinematic_adaptation_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        chapterId="chapter-1",
        chapterTitle="雨夜",
        sourceText=source,
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        ratio="9:16",
        targetLanguage="zh-CN",
        pacingPreset="short_drama",
        targetEpisodeSeconds=90,
    )
    provider = _Provider()
    core = _Core()
    handler = VideoAdaptationJobHandler(
        core,
        ModelVideoAdaptationPlanner(ModelRuntime(provider), max_output_tokens=48_000),
    )
    job = QueueJob(
        jobId="video-adaptation-test-task-1",
        kind="video",
        runId="task-1",
        taskId="task-1",
        novelId="novel-1",
        userId="user-1",
        priority=15,
        payload=payload.model_dump(mode="json"),
        createdAt=datetime.now(UTC),
    )

    await handler.run(job, payload)

    assert len(core.checkpoints) == 1
    assert len(core.completed) == 1
    candidate = core.completed[0].candidate
    shots = candidate.scenes[0].beats[0].shots
    assert [shot.shotKey for shot in shots] == ["S01", "S02", "S03", "S04"]
    assert shots[1].sourceRanges[0].sourceText == "“你来了。”林岚抬眼。"
    assert shots[2].sourceRanges == []
    assert "说话人变化" not in " ".join(shot.cutReason for shot in shots)
    output_names = [
        request.structuredOutput.name
        for request in provider.requests
        if request.structuredOutput
    ]
    assert output_names == [
        "chapter_dramatic_structure_v2",
        "chapter_cinematic_shot_design_v2",
        "chapter_cinematic_review_v2",
    ]


@pytest.mark.asyncio
async def test_prompt_workflow_returns_versioned_batch_without_asking_model_for_version() -> None:
    source = "“你来了。”林岚抬眼。男人沉默着放下染血的钥匙。"
    plan_payload = ChapterAdaptationPlanJobPayload(
        workflow="chapter_cinematic_adaptation_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        chapterId="chapter-1",
        chapterTitle="雨夜",
        sourceText=source,
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        ratio="9:16",
        targetLanguage="zh-CN",
        pacingPreset="short_drama",
        targetEpisodeSeconds=90,
    )
    provider = _Provider()
    core = _Core()
    handler = VideoAdaptationJobHandler(
        core,
        ModelVideoAdaptationPlanner(ModelRuntime(provider), max_output_tokens=48_000),
    )
    plan_job = QueueJob(
        jobId="video-adaptation-plan",
        kind="video",
        runId="task-plan",
        taskId="task-plan",
        novelId="novel-1",
        userId="user-1",
        priority=15,
        payload=plan_payload.model_dump(mode="json"),
        createdAt=datetime.now(UTC),
    )
    await handler.run(plan_job, plan_payload)
    candidate = core.completed[0].candidate
    prompt_payload = ChapterAdaptationPromptJobPayload(
        workflow="chapter_shot_prompt_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        shotPlanVersionId="plan-version-1",
        sourceText=source,
        sourceHash=plan_payload.sourceHash,
        shotPlan=candidate,
        episodeBreakAfterShotKeys=[],
        targetShotKeys=["S01"],
        ratio="9:16",
        targetLanguage="zh-CN",
        settingSnapshot=LongSerialSettingSnapshot.from_entries([]),
    )
    prompt_job = QueueJob(
        jobId="video-adaptation-prompt",
        kind="video",
        runId="task-prompt",
        taskId="task-prompt",
        novelId="novel-1",
        userId="user-1",
        priority=15,
        payload=prompt_payload.model_dump(mode="json"),
        createdAt=datetime.now(UTC),
    )

    await handler.run(prompt_job, prompt_payload)

    assert len(core.prompt_completed) == 1
    assert core.prompt_completed[0].promptBatch.schemaVersion == "shot_prompt_spec_batch_v2"
    prompt_request = provider.requests[-1]
    assert prompt_request.structuredOutput is not None
    assert "schemaVersion" not in prompt_request.structuredOutput.jsonSchema.get(
        "properties",
        {},
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2500, 2500), (2.5, 2500), ("2.5s", 2500), ("2.5秒", 2500), ("2500ms", 2500)],
)
def test_duration_normalization_keeps_formal_half_second_grid(
    value: int | float | str,
    expected: int,
) -> None:
    assert _normalize_duration_ms(value) == expected


@pytest.mark.parametrize("value", [0, "250ms", 16, "16000ms", float("inf")])
def test_duration_normalization_rejects_out_of_range_values(
    value: int | float | str,
) -> None:
    with pytest.raises(ValueError, match="镜头时长"):
        _normalize_duration_ms(value)


def test_short_drama_quality_gate_rejects_old_mechanical_baseline() -> None:
    source = "甲在雨中等待。"
    source_range = ChapterAdaptationSourceRange(
        start=0,
        end=len(source),
        sourceText=source,
    )
    shots = [
        CinematicShotCandidate(
            shotKey=f"S{index:02d}",
            title=f"机械镜头 {index}",
            narrativePurpose="establishing" if index == 1 else "reaction",
            adaptationType="supplemental",
            shotScale="long" if index == 1 else "close",
            cameraAngle="eye_level",
            cameraMovement="locked",
            visualIntent=f"人物保持等待，机械变化编号 {index}",
            audioMode="ambient",
            audioIntent="持续雨声",
            cutReason="人物情绪发生可见变化，需要观察新的反应层次",
            timelineDurationMs=5_000,
            sourceRanges=[],
        )
        for index in range(1, 50)
    ]
    candidate = ChapterAdaptationPlanCandidate(
        schemaVersion="chapter_adaptation_plan_v2",
        adaptationId="adaptation-1",
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        scenes=[
            CinematicSceneCandidate(
                sceneKey="SC01",
                title="雨中等待",
                locationLabel="街口",
                timeLabel="雨夜",
                objective="人物等待来客",
                changeSummary="等待逐渐转为不安",
                beats=[
                    DramaticBeatCandidate(
                        beatKey="B01",
                        title="起初等待",
                        dramaticTurn="人物从平静转为警觉",
                        visualStrategy="以环境和表演完成变化",
                        sourceRanges=[source_range],
                        shots=shots[:25],
                    ),
                    DramaticBeatCandidate(
                        beatKey="B02",
                        title="继续等待",
                        dramaticTurn="人物从警觉转为不安",
                        visualStrategy="以环境和表演完成变化",
                        sourceRanges=[source_range],
                        shots=shots[25:],
                    ),
                ],
            )
        ],
        suggestedEpisodeBreakAfterShotKeys=[],
    )

    with pytest.raises(ValueError, match="平均镜头时长"):
        validate_cinematic_candidate(
            candidate,
            pacing_preset="short_drama",
            target_episode_seconds=90,
        )
