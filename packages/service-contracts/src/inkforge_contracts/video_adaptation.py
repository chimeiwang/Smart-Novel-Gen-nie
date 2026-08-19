"""长篇章节影视化工作台的跨服务契约与纯函数。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from .video import AspectRatio, LongSerialSettingSnapshot, VideoPlanningModel

ChapterPacingPreset = Literal["short_drama", "cinematic", "dialogue_driven"]
ChapterAdaptationType = Literal["direct", "visualized", "voiceover", "supplemental"]
ShotNarrativePurpose = Literal[
    "establishing",
    "action",
    "dialogue",
    "reaction",
    "reveal",
    "insert",
    "transition",
    "atmosphere",
]
ShotScale = Literal[
    "extreme_long",
    "long",
    "medium",
    "medium_close",
    "close",
    "extreme_close",
    "over_shoulder",
    "two_shot",
    "pov",
]
ShotCameraAngle = Literal[
    "eye_level",
    "high_angle",
    "low_angle",
    "overhead",
    "dutch_angle",
]
ShotCameraMovement = Literal[
    "locked",
    "pan",
    "tilt",
    "push_in",
    "pull_out",
    "tracking",
    "arc",
    "handheld",
    "focus_shift",
]
ShotAudioMode = Literal[
    "sync_dialogue",
    "offscreen_dialogue",
    "voiceover",
    "ambient",
    "music",
    "silence",
]

_MECHANICAL_CUT_MARKERS = (
    "说话人变化",
    "说话人切换",
    "句子结束",
    "原文换行",
    "段落结束",
    "进入下一句",
    "下一句话",
)


class VideoAdaptationContractModel(BaseModel):
    """章节影视化服务契约统一拒绝未声明字段。"""

    model_config = ConfigDict(extra="forbid")


class ChapterAdaptationSourceRange(VideoAdaptationContractModel):
    """相对于不可变章节全文的 Unicode code point 左闭右开范围。"""

    start: int = Field(ge=0)
    end: int = Field(ge=1)
    sourceText: str = Field(min_length=1, max_length=120_000)

    @model_validator(mode="after")
    def validate_range(self) -> ChapterAdaptationSourceRange:
        if self.end <= self.start:
            raise ValueError("来源范围 end 必须大于 start")
        if len(self.sourceText) != self.end - self.start:
            raise ValueError("来源范围长度与 sourceText 不一致")
        return self


class CinematicShotCandidate(VideoAdaptationContractModel):
    """候选镜头是一段连续机位和一个主要可见动作。"""

    shotKey: str = Field(pattern=r"^S[0-9]{2,3}$")
    title: str = Field(min_length=1, max_length=120)
    narrativePurpose: ShotNarrativePurpose
    adaptationType: ChapterAdaptationType
    shotScale: ShotScale
    cameraAngle: ShotCameraAngle
    cameraMovement: ShotCameraMovement
    visualIntent: str = Field(min_length=1, max_length=1_200)
    audioMode: ShotAudioMode
    audioIntent: str = Field(min_length=1, max_length=600)
    cutReason: str = Field(min_length=1, max_length=600)
    timelineDurationMs: int = Field(strict=True, ge=500, le=15_000)
    sourceRanges: list[ChapterAdaptationSourceRange] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_shot(self) -> CinematicShotCandidate:
        if self.timelineDurationMs % 500 != 0:
            raise ValueError("镜头时间线时长只允许 500ms 粒度")
        if self.adaptationType == "supplemental":
            if self.sourceRanges:
                raise ValueError("补充镜头不能伪造原文来源")
        elif not self.sourceRanges:
            raise ValueError("非补充镜头至少需要一个原文来源")
        if _is_mechanical_cut_reason(self.cutReason):
            raise ValueError("镜头不能使用说话人、句子或换行作为机械切镜理由")
        _validate_ordered_ranges(self.sourceRanges, label="镜头来源")
        return self


class DramaticBeatCandidate(VideoAdaptationContractModel):
    """戏剧节拍表达人物目标、信息、情绪、权力或行动结果的变化。"""

    beatKey: str = Field(pattern=r"^B[0-9]{2,3}$")
    title: str = Field(min_length=1, max_length=160)
    dramaticTurn: str = Field(min_length=1, max_length=800)
    visualStrategy: str = Field(min_length=1, max_length=800)
    sourceRanges: list[ChapterAdaptationSourceRange] = Field(min_length=1, max_length=24)
    shots: list[CinematicShotCandidate] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_beat(self) -> DramaticBeatCandidate:
        _validate_ordered_ranges(self.sourceRanges, label="节拍来源")
        for shot in self.shots:
            for source_range in shot.sourceRanges:
                if not any(
                    beat_range.start <= source_range.start
                    and beat_range.end >= source_range.end
                    and source_range.sourceText
                    == beat_range.sourceText[
                        source_range.start - beat_range.start :
                        source_range.end - beat_range.start
                    ]
                    for beat_range in self.sourceRanges
                ):
                    raise ValueError(
                        f"镜头 {shot.shotKey} 的来源必须属于所属戏剧节拍"
                    )
        return self


class CinematicSceneCandidate(VideoAdaptationContractModel):
    """由时间、地点和连续行动空间决定的真实场景候选。"""

    sceneKey: str = Field(pattern=r"^SC[0-9]{2,3}$")
    title: str = Field(min_length=1, max_length=160)
    locationLabel: str = Field(min_length=1, max_length=160)
    timeLabel: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=800)
    changeSummary: str = Field(min_length=1, max_length=800)
    beats: list[DramaticBeatCandidate] = Field(min_length=1, max_length=40)


class ChapterAdaptationPlanCandidate(VideoAdaptationContractModel):
    """进入 ReviewArtifact 的完整 Scene → Beat → Shot 候选。"""

    schemaVersion: Literal["chapter_adaptation_plan_v2"]
    adaptationId: str = Field(min_length=1)
    sourceHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenes: list[CinematicSceneCandidate] = Field(min_length=1, max_length=30)
    suggestedEpisodeBreakAfterShotKeys: list[str] = Field(default_factory=list, max_length=119)

    @model_validator(mode="after")
    def validate_timeline(self) -> ChapterAdaptationPlanCandidate:
        scene_keys = [scene.sceneKey for scene in self.scenes]
        if scene_keys != _ordered_keys("SC", len(scene_keys)):
            raise ValueError("场景 Key 必须从 SC01 连续递增")
        beats = [beat for scene in self.scenes for beat in scene.beats]
        beat_keys = [beat.beatKey for beat in beats]
        if beat_keys != _ordered_keys("B", len(beat_keys)):
            raise ValueError("戏剧节拍 Key 必须从 B01 连续递增")
        shots = [shot for beat in beats for shot in beat.shots]
        shot_keys = [shot.shotKey for shot in shots]
        if len(shots) > 120:
            raise ValueError("单章镜头数量不能超过 120")
        if shot_keys != _ordered_keys("S", len(shot_keys)):
            raise ValueError("镜头 Key 必须从 S01 连续递增")
        positions = {shot_key: index for index, shot_key in enumerate(shot_keys)}
        boundaries = self.suggestedEpisodeBreakAfterShotKeys
        if len(set(boundaries)) != len(boundaries):
            raise ValueError("建议分集边界不能重复")
        if set(boundaries) - set(shot_keys[:-1]):
            raise ValueError("建议分集边界只能引用非末尾镜头")
        if boundaries != sorted(boundaries, key=positions.__getitem__):
            raise ValueError("建议分集边界必须按镜头顺序排列")
        return self


class FormalCinematicShot(CinematicShotCandidate):
    """批准后具有数据库身份的正式镜头读模型。"""

    id: str = Field(min_length=1)


class FormalDramaticBeat(VideoAdaptationContractModel):
    id: str = Field(min_length=1)
    beatKey: str = Field(pattern=r"^B[0-9]{2,3}$")
    title: str
    dramaticTurn: str
    visualStrategy: str
    sourceRanges: list[ChapterAdaptationSourceRange]
    shots: list[FormalCinematicShot]


class FormalCinematicScene(VideoAdaptationContractModel):
    id: str = Field(min_length=1)
    sceneKey: str = Field(pattern=r"^SC[0-9]{2,3}$")
    title: str
    locationLabel: str
    timeLabel: str
    objective: str
    changeSummary: str
    beats: list[FormalDramaticBeat]


class FormalChapterAdaptationPlan(VideoAdaptationContractModel):
    schemaVersion: Literal["chapter_adaptation_plan_v2"]
    planVersionId: str = Field(min_length=1)
    versionNo: int = Field(ge=1)
    adaptationId: str = Field(min_length=1)
    sourceHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenes: list[FormalCinematicScene]
    episodeBreakAfterShotKeys: list[str] = Field(default_factory=list)


class DramaticBeatDraft(VideoAdaptationContractModel):
    """模型第一阶段只提交戏剧分析，不提交镜头或字符下标。"""

    title: str = Field(min_length=1, max_length=160)
    sourceUnitIds: list[str] = Field(min_length=1)
    dramaticTurn: str = Field(min_length=1, max_length=800)
    visualStrategy: str = Field(min_length=1, max_length=800)


class DramaticSceneDraft(VideoAdaptationContractModel):
    title: str = Field(min_length=1, max_length=160)
    locationLabel: str = Field(min_length=1, max_length=160)
    timeLabel: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=800)
    changeSummary: str = Field(min_length=1, max_length=800)
    beats: list[DramaticBeatDraft] = Field(min_length=1, max_length=40)


class DramaticStructureResult(VideoAdaptationContractModel):
    scenes: list[DramaticSceneDraft] = Field(min_length=1, max_length=30)


class DramaticBeatCheckpoint(VideoAdaptationContractModel):
    beatKey: str = Field(pattern=r"^B[0-9]{2,3}$")
    title: str
    sourceUnitIds: list[str]
    dramaticTurn: str
    visualStrategy: str


class DramaticSceneCheckpoint(VideoAdaptationContractModel):
    sceneKey: str = Field(pattern=r"^SC[0-9]{2,3}$")
    title: str
    locationLabel: str
    timeLabel: str
    objective: str
    changeSummary: str
    beats: list[DramaticBeatCheckpoint]


class DramaticStructureCheckpoint(VideoAdaptationContractModel):
    schemaVersion: Literal["dramatic_structure_v2_1"] = "dramatic_structure_v2_1"
    scenes: list[DramaticSceneCheckpoint]


class CinematicShotDesignDraft(VideoAdaptationContractModel):
    """模型第二阶段只引用服务器生成的 beatKey 和 sourceUnitIds。"""

    beatKey: str = Field(pattern=r"^B[0-9]{2,3}$")
    title: str = Field(min_length=1, max_length=120)
    narrativePurpose: str = Field(min_length=1, max_length=80)
    adaptationType: str = Field(min_length=1, max_length=80)
    shotScale: str = Field(min_length=1, max_length=80)
    cameraAngle: str = Field(min_length=1, max_length=80)
    cameraMovement: str = Field(min_length=1, max_length=80)
    visualIntent: str = Field(min_length=1, max_length=1_200)
    audioMode: str = Field(min_length=1, max_length=80)
    audioIntent: str = Field(min_length=1, max_length=600)
    cutReason: str = Field(min_length=1, max_length=600)
    # 模型草案兼容供应商常见的秒、毫秒和带单位字符串；正式候选由 Agent 归一为严格整数。
    timelineDurationMs: int | float | str
    sourceUnitIds: list[str]

    @model_validator(mode="after")
    def validate_design(self) -> CinematicShotDesignDraft:
        # adaptationType、来源有无和 500ms 粒度由 Agent 根据来源数组确定性归一。
        if _is_mechanical_cut_reason(self.cutReason):
            raise ValueError("镜头不能使用说话人、句子或换行作为机械切镜理由")
        return self


class CinematicShotDesignResult(VideoAdaptationContractModel):
    shots: list[CinematicShotDesignDraft] = Field(min_length=1, max_length=120)
    suggestedEpisodeBreakAfterShotNumbers: list[int] = Field(default_factory=list)


class CinematicReviewResult(VideoAdaptationContractModel):
    decision: Literal["pass", "revise"]
    summary: str = Field(min_length=1, max_length=1_200)
    requiredChanges: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_review(self) -> CinematicReviewResult:
        if self.decision == "revise" and not self.requiredChanges:
            raise ValueError("要求返工时必须提供具体修改意见")
        if self.decision == "pass" and self.requiredChanges:
            raise ValueError("通过时不能同时要求返工")
        return self


class ChapterAdaptationPlanJobPayload(VideoAdaptationContractModel):
    """Core 投递给 Agent 的完整不可变章节拆镜输入。"""

    workflow: Literal["chapter_cinematic_adaptation_v2"]
    adaptationId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    chapterId: str = Field(min_length=1)
    chapterTitle: str = Field(min_length=1, max_length=240)
    sourceText: str = Field(min_length=1, max_length=120_000)
    sourceHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ratio: AspectRatio
    targetLanguage: str = Field(min_length=2, max_length=32)
    pacingPreset: ChapterPacingPreset
    targetEpisodeSeconds: Literal[60, 90, 120]
    planningRoute: Literal["responses_json_schema_v1"] = "responses_json_schema_v1"
    planningModel: VideoPlanningModel = "deepseek-v4-flash"

    @model_validator(mode="after")
    def validate_source(self) -> ChapterAdaptationPlanJobPayload:
        if hashlib.sha256(self.sourceText.encode("utf-8")).hexdigest() != self.sourceHash:
            raise ValueError("章节改编来源哈希不一致")
        return self


class ChapterAdaptationPromptJobPayload(VideoAdaptationContractModel):
    """逐镜提示词任务固定到正式镜头方案和设定快照。"""

    workflow: Literal["chapter_shot_prompt_v2"]
    adaptationId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    shotPlanVersionId: str = Field(min_length=1)
    sourceText: str = Field(min_length=1, max_length=120_000)
    sourceHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    shotPlan: ChapterAdaptationPlanCandidate
    episodeBreakAfterShotKeys: list[str]
    targetShotKeys: list[str] = Field(min_length=1, max_length=120)
    ratio: AspectRatio
    targetLanguage: str = Field(min_length=2, max_length=32)
    settingSnapshot: LongSerialSettingSnapshot
    planningRoute: Literal["responses_json_schema_v1"] = "responses_json_schema_v1"
    planningModel: VideoPlanningModel = "deepseek-v4-flash"

    @model_validator(mode="after")
    def validate_prompt_input(self) -> ChapterAdaptationPromptJobPayload:
        if hashlib.sha256(self.sourceText.encode("utf-8")).hexdigest() != self.sourceHash:
            raise ValueError("逐镜提示词来源哈希不一致")
        if self.shotPlan.sourceHash != self.sourceHash:
            raise ValueError("逐镜提示词方案与来源不一致")
        plan_keys = {
            shot.shotKey
            for scene in self.shotPlan.scenes
            for beat in scene.beats
            for shot in beat.shots
        }
        if len(set(self.targetShotKeys)) != len(self.targetShotKeys):
            raise ValueError("逐镜提示词目标不能重复")
        if set(self.targetShotKeys) - plan_keys:
            raise ValueError("逐镜提示词引用了方案之外的镜头")
        return self


type VideoAdaptationJobPayload = (
    ChapterAdaptationPlanJobPayload | ChapterAdaptationPromptJobPayload
)
_VIDEO_ADAPTATION_JOB_ADAPTER: TypeAdapter[VideoAdaptationJobPayload] = TypeAdapter(
    VideoAdaptationJobPayload
)


def parse_video_adaptation_job_payload(
    value: Mapping[str, object] | str,
) -> VideoAdaptationJobPayload:
    """严格解析章节改编队列判别联合。"""

    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("章节改编任务载荷不是合法 JSON") from exc
    else:
        raw = dict(value)
    if not isinstance(raw, dict):
        raise ValueError("章节改编任务载荷必须是对象")
    return _VIDEO_ADAPTATION_JOB_ADAPTER.validate_python(raw)


class VideoAdaptationWorkflowProgressQuery(VideoAdaptationContractModel):
    protocolVersion: Literal["1.0"]
    jobId: str
    runId: str
    taskId: str
    novelId: str
    projectId: str
    adaptationId: str
    workflow: Literal["chapter_cinematic_adaptation_v2", "chapter_shot_prompt_v2"]


class VideoAdaptationWorkflowProgressResponse(VideoAdaptationWorkflowProgressQuery):
    status: Literal["active", "completed", "failed"]
    checkpoint: DramaticStructureCheckpoint | None = None


class VideoAdaptationCheckpointCallback(VideoAdaptationContractModel):
    protocolVersion: Literal["1.0"]
    eventId: str
    jobId: str
    runId: str
    taskId: str
    novelId: str
    projectId: str
    adaptationId: str
    checkpoint: DramaticStructureCheckpoint


class VideoAdaptationPlanCompletionCallback(VideoAdaptationContractModel):
    protocolVersion: Literal["1.0"]
    eventId: str
    jobId: str
    runId: str
    taskId: str
    novelId: str
    projectId: str
    adaptationId: str
    candidate: ChapterAdaptationPlanCandidate


class SeedanceShotPromptSpec(VideoAdaptationContractModel):
    """模型只填结构化内容，最终即梦文本由纯函数按固定顺序编译。"""

    subjectAndScene: str = Field(min_length=1, max_length=600)
    visibleAction: str = Field(min_length=1, max_length=600)
    performance: str = Field(min_length=1, max_length=500)
    camera: str = Field(min_length=1, max_length=500)
    audio: str = Field(min_length=1, max_length=500)
    continuity: str = Field(min_length=1, max_length=500)
    negativeConstraints: list[
        Annotated[str, StringConstraints(min_length=1, max_length=240)]
    ] = Field(default_factory=list, max_length=12)


class ShotPromptSpecCandidate(VideoAdaptationContractModel):
    shotKey: str = Field(pattern=r"^S[0-9]{2,3}$")
    spec: SeedanceShotPromptSpec


class ShotPromptSpecResult(VideoAdaptationContractModel):
    """模型输出不携带机械协议版本，版本由 Agent 物化。"""

    prompts: list[ShotPromptSpecCandidate] = Field(min_length=1, max_length=120)


class ShotPromptSpecBatch(VideoAdaptationContractModel):
    schemaVersion: Literal["shot_prompt_spec_batch_v2"] = "shot_prompt_spec_batch_v2"
    prompts: list[ShotPromptSpecCandidate] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_unique_shots(self) -> ShotPromptSpecBatch:
        shot_keys = [prompt.shotKey for prompt in self.prompts]
        if len(set(shot_keys)) != len(shot_keys):
            raise ValueError("逐镜提示词候选不能包含重复镜头")
        return self


class VideoAdaptationPromptCompletionCallback(VideoAdaptationContractModel):
    protocolVersion: Literal["1.0"]
    eventId: str
    jobId: str
    runId: str
    taskId: str
    novelId: str
    projectId: str
    adaptationId: str
    promptBatch: ShotPromptSpecBatch


class VideoAdaptationFailureCallback(VideoAdaptationContractModel):
    protocolVersion: Literal["1.0"]
    eventId: str
    jobId: str
    runId: str
    taskId: str
    novelId: str
    projectId: str
    adaptationId: str
    code: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=2_000)
    recoverable: bool = True


def compile_seedance_shot_prompt(
    spec: SeedanceShotPromptSpec,
    *,
    ratio: AspectRatio,
    timeline_duration_ms: int,
) -> str:
    """按可审核固定顺序编译即梦提示词；超限明确失败，绝不截断。"""

    if not 500 <= timeline_duration_ms <= 15_000 or timeline_duration_ms % 500 != 0:
        raise ValueError("即梦提示词镜头时长必须是 500ms 到 15000ms 的 500ms 倍数")
    duration_seconds = timeline_duration_ms / 1000
    duration_text = (
        str(int(duration_seconds))
        if duration_seconds.is_integer()
        else f"{duration_seconds:.1f}"
    )
    parts = [
        f"{ratio} 画幅，{duration_text} 秒",
        _sentence_content(spec.subjectAndScene),
        _sentence_content(spec.visibleAction),
        f"表演：{_sentence_content(spec.performance)}",
        f"摄影机：{_sentence_content(spec.camera)}",
        f"声音：{_sentence_content(spec.audio)}",
        f"连续性：{_sentence_content(spec.continuity)}",
    ]
    if spec.negativeConstraints:
        parts.append(
            f"禁止：{'；'.join(_sentence_content(item) for item in spec.negativeConstraints)}"
        )
    prompt = "。".join(parts) + "。"
    if len(prompt) > 2_000:
        raise ValueError("编译后的即梦提示词超过 2000 字安全包络")
    return prompt


def _validate_ordered_ranges(
    ranges: Sequence[ChapterAdaptationSourceRange],
    *,
    label: str,
) -> None:
    previous_end = -1
    for source_range in ranges:
        if source_range.start < previous_end:
            raise ValueError(f"{label}必须按原文顺序排列且不能重叠")
        previous_end = source_range.end


def _ordered_keys(prefix: str, count: int) -> list[str]:
    return [f"{prefix}{index:02d}" for index in range(1, count + 1)]


def _is_mechanical_cut_reason(reason: str) -> bool:
    """只拒绝把文本边界本身当理由，不误杀包含反证和真实视觉动机的长说明。"""

    normalized = "".join(reason.split())
    return normalized in _MECHANICAL_CUT_MARKERS or (
        len(normalized) <= 18
        and any(marker in normalized for marker in _MECHANICAL_CUT_MARKERS)
    )


def _sentence_content(value: str) -> str:
    return value.strip().rstrip("。；;，,.！!？?")
