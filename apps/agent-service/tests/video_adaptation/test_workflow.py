"""章节影视化工作流按 Scene/Beat/Shot 执行并持久化中间检查点。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from inkforge_agents.clients.core import RunResource
from inkforge_agents.jobs.video_adaptation import (
    ModelVideoAdaptationPlanner,
    VideoAdaptationJobHandler,
    _conflicting_prompt_shot_scales,
    _contains_neighbor_language,
    _contains_nonvisual_interpretation,
    _formal_shot_information_density_issue,
    _materialize_candidate,
    _negative_constraint_blocks_required_action,
    _negative_constraints_block_required_subject,
    _normalize_duration_ms,
    _normalize_explicit_shot_scale,
    _project_character_appearance,
    _realign_design_beat_slots,
    _remove_repeated_subject_shot_scale,
    _repeated_prompt_fields,
    _required_hand_is_missing,
    _sentence_count,
    _source_units,
    _strip_compiler_owned_metadata,
    _unconfirmed_action_markers,
)
from inkforge_agents.jobs.video_adaptation_quality import collect_cinematic_findings
from inkforge_agents.providers.base import ModelTurnRequest, ModelTurnResult, ModelUsage
from inkforge_agents.queue.repository import QueueJob
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_contracts.video import LongSerialSettingSnapshot
from inkforge_contracts.video_adaptation import (
    BeatCoverageGoal,
    ChapterAdaptationPlanCandidate,
    ChapterAdaptationPlanJobPayload,
    ChapterAdaptationPromptJobPayload,
    ChapterAdaptationSourceRange,
    CinematicSceneCandidate,
    CinematicShotCandidate,
    CinematicShotDesignResult,
    DramaticBeatCandidate,
    DramaticStructureCheckpoint,
    SeedanceShotPromptSpec,
    ShotVisualReferenceBundle,
    ShotVisualReferenceSnapshot,
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
        if name == "chapter_dramatic_structure_v3":
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
                                "coverageGoals": [
                                    {
                                        "kind": "story_information",
                                        "priority": "essential",
                                        "description": "观众确认染血钥匙带来危险线索",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        elif name == "chapter_goal_driven_shot_design_v3":
            value = {
                "beatsByKey": {
                    "B01": [
                        {
                            "title": "建立雨夜书房",
                            "narrativePurpose": "establishing",
                            "storyFunction": "交代书房人物关系和雨夜压迫感",
                            "audienceGain": "观众看清两人的距离和空间位置",
                            "coveredGoalKeys": ["G01"],
                            "sourceRelation": "supplemental",
                            "shotScale": "long",
                            "cameraAngle": "eye_level",
                            "cameraMovement": "locked",
                            "visualIntent": "门外冷光切进安静书房，林岚坐在桌边",
                            "speechMode": "none",
                            "spokenText": None,
                            "soundDesign": "持续雨声和门轴声",
                            "cutReason": "进入新场景先建立人物空间关系和压迫氛围",
                            "timelineDurationMs": 2000,
                            "sourceUnitIds": [],
                        },
                        {
                            "title": "林岚发问",
                            "narrativePurpose": "dialogue",
                            "storyFunction": "用完整发问建立两人紧张关系",
                            "audienceGain": "观众知道林岚主动试探来客",
                            "coveredGoalKeys": ["G01"],
                            "sourceRelation": "direct",
                            "shotScale": "two_shot",
                            "cameraAngle": "eye_level",
                            "cameraMovement": "locked",
                            "visualIntent": "两人保持距离，林岚抬眼发问，来客没有移动",
                            "speechMode": "sync",
                            "spokenText": "你来了。",
                            "soundDesign": "雨声在对白下持续",
                            "cutReason": "从空间建立进入两人关系主镜头，承载完整发问而非逐句切换",
                            "timelineDurationMs": 3000,
                            "sourceUnitIds": ["U001", "U002"],
                        },
                        {
                            "title": "沉默反应",
                            "narrativePurpose": "reaction",
                            "storyFunction": "让未回答本身形成悬念",
                            "audienceGain": "观众感到来客刻意隐瞒信息",
                            "coveredGoalKeys": ["G01"],
                            "sourceRelation": "supplemental",
                            "shotScale": "close",
                            "cameraAngle": "eye_level",
                            "cameraMovement": "locked",
                            "visualIntent": "来客沉默看着林岚，手仍藏在画外",
                            "speechMode": "none",
                            "spokenText": None,
                            "soundDesign": "短暂压低雨声，不新增对白",
                            "cutReason": "切到倾听者沉默反应，让未回答本身形成悬念",
                            "timelineDurationMs": 1500,
                            "sourceUnitIds": [],
                        },
                        {
                            "title": "钥匙落桌",
                            "narrativePurpose": "insert",
                            "storyFunction": "用关键物件兑现节拍的信息转折",
                            "audienceGain": "观众看清钥匙带血并意识到危险",
                            "coveredGoalKeys": ["G01"],
                            "sourceRelation": "direct",
                            "shotScale": "extreme_close",
                            "cameraAngle": "high_angle",
                            "cameraMovement": "push_in",
                            "visualIntent": "染血钥匙被放上桌面，血迹进入焦点",
                            "speechMode": "none",
                            "spokenText": None,
                            "soundDesign": "钥匙碰桌的金属声",
                            "cutReason": "关键物件改变信息量，以插入特写完成节拍揭示",
                            "timelineDurationMs": 1500,
                            "sourceUnitIds": ["U003"],
                        },
                    ]
                },
                "suggestedEpisodeBreakAfterShotNumbers": [],
            }
        elif name == "chapter_cinematic_review_v3":
            value = {
                "decision": "pass",
                "summary": "切镜均有戏剧动机",
                "requiredChanges": [],
                "findings": [],
            }
        elif name == "chapter_missing_beat_shots_v3":
            value = {
                "beatsByKey": {
                    "B02": [
                        {
                            "title": "钥匙显现",
                            "narrativePurpose": "reveal",
                            "storyFunction": "补全遗漏的线索揭示",
                            "audienceGain": "观众看清钥匙",
                            "coveredGoalKeys": ["G02"],
                            "sourceRelation": "direct",
                            "shotScale": "close",
                            "cameraAngle": "eye_level",
                            "cameraMovement": "locked",
                            "visualIntent": "乙从暗处拿出钥匙",
                            "speechMode": "none",
                            "spokenText": None,
                            "soundDesign": "钥匙轻响",
                            "cutReason": "关键物件出现改变信息量",
                            "timelineDurationMs": 2000,
                            "sourceUnitIds": ["U002"],
                        }
                    ]
                },
                "suggestedEpisodeBreakAfterShotNumbers": [],
            }
        elif name == "chapter_shot_prompt_spec_v4":
            value = {
                "prompts": [
                    {
                        "shotKey": "S01",
                        "spec": {
                            "subjectAndScene": "雨夜书房内，林岚坐在桌边",
                            "visibleAction": "门外冷光切入，林岚抬眼看向来客",
                            "expressionAndGaze": None,
                            "camera": "全景固定机位，不越过人物轴线",
                            "audio": "持续雨声与轻微门轴声",
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


class _PromptCorrectionProvider(_Provider):
    def __init__(self) -> None:
        super().__init__()
        self.prompt_attempts = 0

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        assert request.structuredOutput is not None
        if request.structuredOutput.name == "chapter_shot_prompt_spec_v4":
            self.prompt_attempts += 1
            if self.prompt_attempts == 1:
                self.requests.append(request)
                return ModelTurnResult(
                    content="这不是合法 JSON",
                    toolCalls=[],
                    structuredOutput=None,
                    usage=ModelUsage(
                        promptTokens=100,
                        completionTokens=10,
                        totalTokens=110,
                    ),
                    finishReason="stop",
                    rawFinishReason="response.completed",
                )
        return await super().complete_turn(request)


class _PromptQualityCorrectionProvider(_Provider):
    def __init__(self) -> None:
        super().__init__()
        self.prompt_attempts = 0

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        assert request.structuredOutput is not None
        if request.structuredOutput.name == "chapter_shot_prompt_spec_v4":
            self.prompt_attempts += 1
            if self.prompt_attempts == 1:
                self.requests.append(request)
                return ModelTurnResult(
                    content="",
                    toolCalls=[],
                    structuredOutput={
                        "prompts": [
                            {
                                "shotKey": "S01",
                                "spec": {
                                    "subjectAndScene": "9:16 画幅，雨夜书房内，林岚坐在桌边",
                                    "visibleAction": "林岚抬眼。随后她起身。",
                                    "performance": "林岚抬眼并起身",
                                    "expressionAndGaze": None,
                                    "camera": "全景固定机位",
                                    "audio": "持续雨声",
                                    "continuity": "为下一镜保留起身动作",
                                    "negativeConstraints": [],
                                },
                            }
                        ]
                    },
                    usage=ModelUsage(
                        promptTokens=100,
                        completionTokens=100,
                        totalTokens=200,
                    ),
                    finishReason="stop",
                    rawFinishReason="response.completed",
                )
        return await super().complete_turn(request)


class _PromptPersistentQualityProvider(_Provider):
    def __init__(self) -> None:
        super().__init__()
        self.prompt_attempts = 0

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        assert request.structuredOutput is not None
        if request.structuredOutput.name == "chapter_shot_prompt_spec_v4":
            self.prompt_attempts += 1
            self.requests.append(request)
            return ModelTurnResult(
                content="",
                toolCalls=[],
                structuredOutput={
                    "prompts": [
                        {
                            "shotKey": "S01",
                            "spec": {
                                "subjectAndScene": "雨夜书房内，林岚坐在桌边",
                                "visibleAction": "林岚意识到危险",
                                "expressionAndGaze": None,
                                "camera": "全景固定机位",
                                "audio": "持续雨声",
                                "negativeConstraints": [],
                            },
                        }
                    ]
                },
                usage=ModelUsage(
                    promptTokens=100,
                    completionTokens=100,
                    totalTokens=200,
                ),
                finishReason="stop",
                rawFinishReason="response.completed",
            )
        return await super().complete_turn(request)


class _PromptVisualEffectCorrectionProvider(_Provider):
    def __init__(self) -> None:
        super().__init__()
        self.prompt_attempts = 0

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        assert request.structuredOutput is not None
        if request.structuredOutput.name == "chapter_shot_prompt_spec_v4":
            self.prompt_attempts += 1
            if self.prompt_attempts == 1:
                self.requests.append(request)
                return ModelTurnResult(
                    content="",
                    toolCalls=[],
                    structuredOutput={
                        "prompts": [
                            {
                                "shotKey": "S01",
                                "spec": {
                                    "subjectAndScene": "雨夜书房内，林岚坐在桌边",
                                    "visibleAction": "门外冷光切入，林岚抬眼看向来客",
                                    "expressionAndGaze": None,
                                    "camera": "全景固定机位",
                                    "audio": "持续雨声与轻微门轴声",
                                    "negativeConstraints": [
                                        "不出现霓虹，只保留冷蓝环境光与暖黄机械火花"
                                    ],
                                },
                            }
                        ]
                    },
                    usage=ModelUsage(
                        promptTokens=100,
                        completionTokens=100,
                        totalTokens=200,
                    ),
                    finishReason="stop",
                    rawFinishReason="response.completed",
                )
        return await super().complete_turn(request)


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
        request.structuredOutput.name for request in provider.requests if request.structuredOutput
    ]
    assert output_names == [
        "chapter_dramatic_structure_v3",
        "chapter_goal_driven_shot_design_v3",
        "chapter_cinematic_review_v3",
    ]
    assert [
        (request.policy.policyId, request.policy.thinkingMode, request.policy.reasoningEffort)
        for request in provider.requests
    ] == [
        ("v1:video-adaptation-plan-no-thinking", "disabled", None),
        ("v1:video-adaptation-plan-no-thinking", "disabled", None),
        ("v1:video-adaptation-review-no-thinking", "disabled", None),
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
        visualReferenceBundles=[
            ShotVisualReferenceBundle(
                shotKey="S01",
                references=[
                    ShotVisualReferenceSnapshot(
                        canonVersionId="canon-version-1",
                        assetId="asset-1",
                        assetSha256="a" * 64,
                        settingKind="character",
                        settingId="character-1",
                        settingName="林岚",
                        duty="identity",
                        variantKey="default",
                        label="标准身份",
                        includeFeatures=["黑色高马尾"],
                        excludeFeatures=["强笑"],
                        strength=72,
                    )
                ],
            )
        ],
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
    assert (
        prompt_request.policy.policyId,
        prompt_request.policy.thinkingMode,
        prompt_request.policy.reasoningEffort,
    ) == ("v1:video-adaptation-prompt-no-thinking", "disabled", None)
    assert prompt_request.structuredOutput is not None
    assert "schemaVersion" not in prompt_request.structuredOutput.jsonSchema.get(
        "properties",
        {},
    )
    prompt_spec_schema = prompt_request.structuredOutput.jsonSchema["$defs"][
        "SeedanceShotPromptSpec"
    ]
    prompt_candidate_schema = prompt_request.structuredOutput.jsonSchema["$defs"][
        "ShotPromptSpecCandidate"
    ]
    assert "performance" not in prompt_spec_schema["properties"]
    assert "continuity" not in prompt_spec_schema["properties"]
    assert "qualityWarnings" not in prompt_candidate_schema["properties"]
    expression_types = {
        item.get("type") for item in prompt_spec_schema["properties"]["expressionAndGaze"]["anyOf"]
    }
    assert expression_types == {
        "string",
        "null",
    }
    assert "章节正文" not in prompt_request.messages[1].content
    assert '"requiredShotScale":{"code":"long","label":"全景"}' in (
        prompt_request.messages[1].content
    )
    assert '"canonVersionId":"canon-version-1"' in prompt_request.messages[1].content

    correction_provider = _PromptCorrectionProvider()
    corrected = await ModelVideoAdaptationPlanner(
        ModelRuntime(correction_provider),
        max_output_tokens=48_000,
    ).generate_prompts(
        RunResource(
            userId="user-1",
            novelId="novel-1",
            taskId="task-correction",
            runId="run-correction",
        ),
        prompt_payload,
    )
    prompt_requests = [
        request
        for request in correction_provider.requests
        if request.structuredOutput is not None
        and request.structuredOutput.name == "chapter_shot_prompt_spec_v4"
    ]
    assert correction_provider.prompt_attempts == 2
    assert len(corrected.prompts) == 1
    assert "上一次响应没有形成可执行的逐镜规格" in prompt_requests[1].messages[1].content

    quality_provider = _PromptQualityCorrectionProvider()
    quality_corrected = await ModelVideoAdaptationPlanner(
        ModelRuntime(quality_provider),
        max_output_tokens=48_000,
    ).generate_prompts(
        RunResource(
            userId="user-1",
            novelId="novel-1",
            taskId="task-quality-correction",
            runId="run-quality-correction",
        ),
        prompt_payload,
    )
    quality_requests = [
        request
        for request in quality_provider.requests
        if request.structuredOutput is not None
        and request.structuredOutput.name == "chapter_shot_prompt_spec_v4"
    ]
    assert quality_provider.prompt_attempts == 2
    assert quality_corrected.prompts[0].spec.performance is None
    assert quality_corrected.prompts[0].spec.continuity is None
    correction_message = quality_requests[1].messages[1].content
    assert "最多允许 1 个动作句" in correction_message
    assert "新候选不得提交历史 performance 字段" not in correction_message
    assert "字段不得重复画幅或时长" not in correction_message

    persistent_quality_provider = _PromptPersistentQualityProvider()
    warned = await ModelVideoAdaptationPlanner(
        ModelRuntime(persistent_quality_provider),
        max_output_tokens=48_000,
    ).generate_prompts(
        RunResource(
            userId="user-1",
            novelId="novel-1",
            taskId="task-quality-warning",
            runId="run-quality-warning",
        ),
        prompt_payload,
    )
    assert persistent_quality_provider.prompt_attempts == 2
    assert warned.prompts[0].qualityWarnings == ["visibleAction 只能写可见变化，不能解释内心"]

    visual_effect_provider = _PromptVisualEffectCorrectionProvider()
    visual_effect_corrected = await ModelVideoAdaptationPlanner(
        ModelRuntime(visual_effect_provider),
        max_output_tokens=48_000,
    ).generate_prompts(
        RunResource(
            userId="user-1",
            novelId="novel-1",
            taskId="task-visual-effect-correction",
            runId="run-visual-effect-correction",
        ),
        prompt_payload,
    )
    visual_effect_requests = [
        request
        for request in visual_effect_provider.requests
        if request.structuredOutput is not None
        and request.structuredOutput.name == "chapter_shot_prompt_spec_v4"
    ]
    assert visual_effect_provider.prompt_attempts == 2
    visual_effect_correction = visual_effect_requests[1].messages[1].content
    assert "候选新增了正式镜头未确认的视觉效果：火花" in visual_effect_correction
    assert "negativeConstraints 混入了正向画面要求：火花" in visual_effect_correction
    assert "新增了正式镜头未确认的视觉效果：霓虹" not in visual_effect_correction
    assert visual_effect_corrected.prompts[0].qualityWarnings == []


def test_prompt_normalization_only_removes_proven_redundancy_and_action_conflicts() -> None:
    shot = CinematicShotCandidate(
        shotKey="S14",
        title="黄铜匣特写",
        narrativePurpose="insert",
        storyFunction="展示解锁受阻",
        audienceGain="观众看清齿钥卡死",
        coveredGoalKeys=["G01"],
        sourceRelation="supplemental",
        shotScale="close",
        cameraAngle="high_angle",
        cameraMovement="locked",
        visualIntent="手握齿钥转动半圈后卡死",
        speechMode="none",
        spokenText=None,
        soundDesign="金属滞涩声",
        cutReason="切至关键物件",
        timelineDurationMs=2000,
        sourceRanges=[],
    )
    missing_hand_spec = SeedanceShotPromptSpec(
        subjectAndScene="16:9 画幅，黄铜匣嵌在平台中央",
        visibleAction="齿钥转动半圈后卡死",
        camera="固定高角度特写",
        audio="金属滞涩声",
        negativeConstraints=["不要出现人物面部、手部或任何身体部位"],
    )

    assert _strip_compiler_owned_metadata(missing_hand_spec.subjectAndScene) == (
        "黄铜匣嵌在平台中央"
    )
    assert _required_hand_is_missing(missing_hand_spec, shot)
    assert _negative_constraint_blocks_required_action(
        missing_hand_spec.negativeConstraints[0],
        shot,
        missing_hand_spec.visibleAction,
    )
    wrong_scale_spec = missing_hand_spec.model_copy(
        update={"subjectAndScene": "高角度特写，黄铜匣嵌在平台中央"}
    )
    assert _conflicting_prompt_shot_scales(wrong_scale_spec, shot) == ["特写"]
    assert (
        _normalize_explicit_shot_scale(
            wrong_scale_spec.subjectAndScene,
            shot,
        )
        == "高角度近景，黄铜匣嵌在平台中央"
    )
    assert _normalize_explicit_shot_scale("固定平视，近景侧面特写", shot) == ("固定平视，近景侧面")
    assert (
        _remove_repeated_subject_shot_scale(
            "近景侧面，林岚垂眸看向罗盘",
            "固定平视，近景侧面",
            shot,
        )
        == "侧面，林岚垂眸看向罗盘"
    )
    assert not _contains_neighbor_language(
        missing_hand_spec.model_copy(
            update={"negativeConstraints": ["不得出现前后镜的攀爬或落地动作"]}
        )
    )
    assert _unconfirmed_action_markers(
        "手指转动齿钥半圈至卡死，随后用力回拧却纹丝不动",
        shot,
    ) == ["回拧"]

    executable_spec = missing_hand_spec.model_copy(
        update={
            "subjectAndScene": "一只手握住插在锁孔内的齿钥，黄铜匣嵌在平台中央",
            "negativeConstraints": [],
        }
    )
    assert not _required_hand_is_missing(executable_spec, shot)
    assert not _required_hand_is_missing(
        missing_hand_spec.model_copy(
            update={"subjectAndScene": "黄铜罗盘在掌中，指节收拢握紧盘缘"}
        ),
        shot,
    )
    performer_shot = shot.model_copy(
        update={"title": "林岚侧面近景", "visualIntent": "林岚垂眸握紧罗盘"}
    )
    assert _unconfirmed_action_markers(
        "罗盘在掌中缓慢转动",
        performer_shot,
    ) == ["转动"]
    dense_shot = shot.model_copy(
        update={
            "visualIntent": "黄铜匣占据画面，七座灯塔刻痕清晰，第七座仅剩凹痕，齿钥转动半圈卡死"
        }
    )
    density_issue = _formal_shot_information_density_issue(dense_shot)
    assert density_issue is not None
    assert "建议确认是否延长时长或拆镜" in density_issue.message
    assert _negative_constraints_block_required_subject(
        executable_spec.model_copy(
            update={"negativeConstraints": ["禁止出现父亲的脸或任何人物轮廓"]}
        ),
        performer_shot,
    )
    assert not _negative_constraints_block_required_subject(
        executable_spec.model_copy(update={"negativeConstraints": ["禁止出现其他人物"]}),
        performer_shot,
    )


def test_prompt_setting_projection_respects_shot_scale_and_visible_language() -> None:
    appearance = "黑色高马尾，灰蓝色短款防水邮差斗篷，旧铜扣长靴，斜背棕色皮质邮袋"

    assert (
        _project_character_appearance(
            appearance,
            target_text="林岚垂眸的侧面特写",
            shot_scale="close",
        )
        == "黑色高马尾"
    )
    assert (
        _project_character_appearance(
            appearance,
            target_text="林岚全身沿石阶下行，邮袋铜扣被海风吹动",
            shot_scale="long",
        )
        == appearance
    )
    assert (
        _project_character_appearance(
            appearance,
            target_text="林岚全身沿石阶下行",
            shot_scale="long",
            protected_duties={"identity"},
        )
        == "灰蓝色短款防水邮差斗篷，旧铜扣长靴，斜背棕色皮质邮袋"
    )
    assert (
        _project_character_appearance(
            appearance,
            target_text="林岚垂眸的侧面特写",
            shot_scale="close",
            protected_duties={"costume"},
        )
        == "黑色高马尾"
    )
    assert _contains_nonvisual_interpretation("林岚试图追忆父亲的脸")
    assert _sentence_count("手握齿钥转动半圈，随即钥匙卡死不动") == 1
    assert _sentence_count("林岚抬眼。随后她起身。") == 2

    repeated_spec = SeedanceShotPromptSpec(
        subjectAndScene="林岚侧面近景",
        visibleAction="她垂眸，眉头微蹙",
        expressionAndGaze="眉头微蹙，目光落在罗盘上",
        camera="固定平视侧面特写",
        audio="海风与呼吸声",
    )
    assert _repeated_prompt_fields(repeated_spec) == ("visibleAction/expressionAndGaze")


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


def test_materialization_does_not_force_new_scene_first_shot_to_establishing() -> None:
    source = "林岚攀上梯架，脚下海水涌动。"
    payload = ChapterAdaptationPlanJobPayload(
        workflow="chapter_cinematic_adaptation_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        chapterId="chapter-1",
        chapterTitle="钟楼",
        sourceText=source,
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        ratio="9:16",
        targetLanguage="zh-CN",
        pacingPreset="short_drama",
        targetEpisodeSeconds=90,
    )
    units = _source_units(source)
    checkpoint = DramaticStructureCheckpoint.model_validate(
        {
            "scenes": [
                {
                    "sceneKey": "SC01",
                    "title": "攀上梯架",
                    "locationLabel": "钟楼内部梯架",
                    "timeLabel": "夜",
                    "objective": "林岚接近机关",
                    "changeSummary": "攀爬从稳定转为危险",
                    "beats": [
                        {
                            "beatKey": "B01",
                            "title": "梯架松动",
                            "sourceUnitIds": [units[0].unit_id],
                            "dramaticTurn": "林岚意识到脚下结构不稳",
                            "visualStrategy": "用动作和脚下水面关系表达危险",
                            "coverageGoals": [
                                {
                                    "goalKey": "G01",
                                    "kind": "action",
                                    "priority": "essential",
                                    "description": "观众看清攀爬动作变得危险",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )
    design = CinematicShotDesignResult.model_validate(
        {
            "beatsByKey": {
                "B01": [
                    {
                        "title": "手指扣住湿滑横档",
                        "narrativePurpose": "action",
                        "storyFunction": "直接进入攀爬压力，不重复交代已知地点",
                        "audienceGain": "观众感到横档正在失去支撑",
                        "coveredGoalKeys": ["G02"],
                        "sourceRelation": "direct",
                        "shotScale": "close",
                        "cameraAngle": "low_angle",
                        "cameraMovement": "handheld",
                        "visualIntent": "林岚手指扣紧湿滑横档，横档突然下沉",
                        "speechMode": "none",
                        "spokenText": None,
                        "soundDesign": "木头绷裂声与下方海水声同时逼近",
                        "cutReason": "横档下沉改变动作结果，下一镜需要展示人物反应",
                        "timelineDurationMs": 2000,
                        "sourceUnitIds": [units[0].unit_id],
                    }
                ]
            },
            "suggestedEpisodeBreakAfterShotNumbers": [],
        }
    )

    candidate = _materialize_candidate(payload, checkpoint, design, units=units)
    first_shot = candidate.scenes[0].beats[0].shots[0]

    assert first_shot.narrativePurpose == "action"
    assert first_shot.shotScale == "close"
    assert first_shot.cutReason == "横档下沉改变动作结果，下一镜需要展示人物反应"
    assert first_shot.coveredGoalKeys == []
    assert candidate.reviewFindings[0].message == "模型目标绑定已按所属节拍纠正"


def test_source_units_realign_shots_that_reuse_stale_beat_keys() -> None:
    checkpoint = DramaticStructureCheckpoint.model_validate(
        {
            "scenes": [
                {
                    "sceneKey": "SC01",
                    "title": "连续场景",
                    "locationLabel": "钟楼",
                    "timeLabel": "夜",
                    "objective": "完成两个连续变化",
                    "changeSummary": "动作推进到线索揭示",
                    "beats": [
                        {
                            "beatKey": "B01",
                            "title": "动作",
                            "sourceUnitIds": ["U001"],
                            "dramaticTurn": "人物开始行动",
                            "visualStrategy": "动作推进",
                            "coverageGoals": [
                                {
                                    "goalKey": "G01",
                                    "kind": "action",
                                    "priority": "essential",
                                    "description": "观众看清动作开始",
                                }
                            ],
                        },
                        {
                            "beatKey": "B02",
                            "title": "线索",
                            "sourceUnitIds": ["U002"],
                            "dramaticTurn": "人物发现线索",
                            "visualStrategy": "物件揭示",
                            "coverageGoals": [
                                {
                                    "goalKey": "G02",
                                    "kind": "story_information",
                                    "priority": "essential",
                                    "description": "观众看清新线索",
                                }
                            ],
                        },
                    ],
                }
            ]
        }
    )
    design = CinematicShotDesignResult.model_validate(
        {
            "beatsByKey": {
                "B01": [
                    {
                        "title": "线索特写",
                        "narrativePurpose": "reveal",
                        "storyFunction": "揭示线索",
                        "audienceGain": "观众获得新信息",
                        "coveredGoalKeys": ["G02"],
                        "sourceRelation": "direct",
                        "shotScale": "close",
                        "cameraAngle": "eye_level",
                        "cameraMovement": "locked",
                        "visualIntent": "线索进入画面",
                        "speechMode": "none",
                        "spokenText": None,
                        "soundDesign": "环境声",
                        "cutReason": "信息量发生变化",
                        "timelineDurationMs": 2000,
                        "sourceUnitIds": ["U002"],
                    }
                ]
            },
            "suggestedEpisodeBreakAfterShotNumbers": [1],
        }
    )

    realigned = _realign_design_beat_slots(design, checkpoint)

    assert "B01" not in realigned.beatsByKey
    assert realigned.beatsByKey["B02"][0].title == "线索特写"
    assert realigned.suggestedEpisodeBreakAfterShotNumbers == []


@pytest.mark.asyncio
async def test_missing_beat_completion_preserves_existing_slots() -> None:
    source = "甲推门。乙拿出钥匙。"
    units = _source_units(source)
    payload = ChapterAdaptationPlanJobPayload(
        workflow="chapter_cinematic_adaptation_v2",
        adaptationId="adaptation-1",
        projectId="project-1",
        chapterId="chapter-1",
        chapterTitle="补镜",
        sourceText=source,
        sourceHash=hashlib.sha256(source.encode()).hexdigest(),
        ratio="9:16",
        targetLanguage="zh-CN",
        pacingPreset="short_drama",
        targetEpisodeSeconds=90,
    )
    checkpoint = DramaticStructureCheckpoint.model_validate(
        {
            "scenes": [
                {
                    "sceneKey": "SC01",
                    "title": "室内",
                    "locationLabel": "门厅",
                    "timeLabel": "夜",
                    "objective": "人物发现钥匙",
                    "changeSummary": "进入后获得线索",
                    "beats": [
                        {
                            "beatKey": "B01",
                            "title": "推门",
                            "sourceUnitIds": [units[0].unit_id],
                            "dramaticTurn": "人物进入室内",
                            "visualStrategy": "动作推进",
                            "coverageGoals": [
                                {
                                    "goalKey": "G01",
                                    "kind": "action",
                                    "priority": "essential",
                                    "description": "观众看清人物进入",
                                }
                            ],
                        },
                        {
                            "beatKey": "B02",
                            "title": "钥匙",
                            "sourceUnitIds": [units[1].unit_id],
                            "dramaticTurn": "钥匙成为新线索",
                            "visualStrategy": "物件揭示",
                            "coverageGoals": [
                                {
                                    "goalKey": "G02",
                                    "kind": "story_information",
                                    "priority": "essential",
                                    "description": "观众看清钥匙",
                                }
                            ],
                        },
                    ],
                }
            ]
        }
    )
    existing = CinematicShotDesignResult.model_validate(
        {
            "beatsByKey": {
                "B01": [
                    {
                        "title": "推门",
                        "narrativePurpose": "action",
                        "storyFunction": "推进进入动作",
                        "audienceGain": "观众确认人物进入",
                        "coveredGoalKeys": ["G01"],
                        "sourceRelation": "direct",
                        "shotScale": "medium",
                        "cameraAngle": "eye_level",
                        "cameraMovement": "tracking",
                        "visualIntent": "甲推门进入",
                        "speechMode": "none",
                        "spokenText": None,
                        "soundDesign": "门轴声",
                        "cutReason": "人物进入新空间",
                        "timelineDurationMs": 2500,
                        "sourceUnitIds": [units[0].unit_id],
                    }
                ]
            },
            "suggestedEpisodeBreakAfterShotNumbers": [],
        }
    )
    provider = _Provider()
    planner = ModelVideoAdaptationPlanner(
        ModelRuntime(provider),
        max_output_tokens=48_000,
    )

    completed = await planner._complete_missing_beat_slots(
        RunResource(
            userId="user-1",
            novelId="novel-1",
            taskId="task-1",
            runId="run-1",
        ),
        payload,
        checkpoint,
        existing,
        units=units,
    )

    assert len(provider.requests) == 1
    assert (
        provider.requests[0].policy.policyId,
        provider.requests[0].policy.thinkingMode,
        provider.requests[0].policy.reasoningEffort,
    ) == ("v1:video-adaptation-plan-no-thinking", "disabled", None)
    assert completed.beatsByKey["B01"][0].title == "推门"
    assert completed.beatsByKey["B02"][0].title == "钥匙显现"


def test_short_drama_audit_reports_old_mechanical_baseline_without_rejecting() -> None:
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
            storyFunction="重复等待动作，测试非阻断审镜",
            audienceGain=f"观众看到第 {index} 次等待反应",
            coveredGoalKeys=["G01" if index <= 25 else "G02"],
            sourceRelation="supplemental",
            shotScale="long" if index == 1 else "close",
            cameraAngle="eye_level",
            cameraMovement="locked",
            visualIntent=f"人物保持等待，机械变化编号 {index}",
            speechMode="none",
            spokenText=None,
            soundDesign="持续雨声",
            cutReason="人物情绪发生可见变化，需要观察新的反应层次",
            timelineDurationMs=5_000,
            sourceRanges=[],
        )
        for index in range(1, 50)
    ]
    candidate = ChapterAdaptationPlanCandidate(
        schemaVersion="chapter_adaptation_plan_v3",
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
                        coverageGoals=[
                            BeatCoverageGoal(
                                goalKey="G01",
                                kind="emotion",
                                priority="essential",
                                description="观众感到等待转为警觉",
                            )
                        ],
                        sourceRanges=[source_range],
                        shots=shots[:25],
                    ),
                    DramaticBeatCandidate(
                        beatKey="B02",
                        title="继续等待",
                        dramaticTurn="人物从警觉转为不安",
                        visualStrategy="以环境和表演完成变化",
                        coverageGoals=[
                            BeatCoverageGoal(
                                goalKey="G02",
                                kind="emotion",
                                priority="essential",
                                description="观众感到警觉继续转为不安",
                            )
                        ],
                        sourceRanges=[source_range],
                        shots=shots[25:],
                    ),
                ],
            )
        ],
        suggestedEpisodeBreakAfterShotKeys=[],
    )

    findings = collect_cinematic_findings(
        candidate,
        pacing_preset="short_drama",
        target_episode_seconds=90,
    )

    assert any("平均镜头时长" in finding.message for finding in findings)
    assert any("超出目标" in finding.message for finding in findings)
