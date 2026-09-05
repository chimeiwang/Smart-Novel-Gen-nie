"""开发视频 V2 的完整来源、精确阶段输入与无供应商原文的规范化输出。"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from .execution import ExecutionId, Sha256
from .video_adaptation import (
    ChapterAdaptationPlanCandidate,
    ChapterAdaptationPlanJobPayload,
    ChapterAdaptationPromptJobPayload,
    CinematicReviewFinding,
    CinematicReviewResult,
    CinematicShotDesignResult,
    DramaticStructureCheckpoint,
    ShotPromptSpecBatch,
)

VideoStageKey = Literal[
    "dramatic_structure", "shot_design", "missing_beat_shots", "cinematic_review", "shot_prompt"
]
ShotKey = Annotated[str, Field(pattern=r"^S[0-9]{2,3}$")]
BeatKey = Annotated[str, Field(pattern=r"^B[0-9]{2,3}$")]
ScaleLabel = Literal[
    "过肩镜头",
    "双人镜头",
    "主观镜头",
    "大特写",
    "中近景",
    "大全景",
    "大远景",
    "特写",
    "近景",
    "中景",
    "全景",
    "远景",
]
EffectLabel = Literal[
    "火花", "火焰", "爆炸", "闪电或电弧", "粒子效果", "光束或光柱", "浓烟", "雨雪", "血迹"
]
ActionMarker = Literal[
    "凝成",
    "亮起",
    "熄灭",
    "弹开",
    "打开",
    "关闭",
    "碎裂",
    "破裂",
    "加速",
    "减速",
    "转为",
    "变成",
    "显现",
    "消失",
    "再次",
    "再度",
    "又一次",
    "反复",
    "继续",
    "重试",
    "回拧",
    "反向",
    "转动",
    "旋转",
]
PromptField = Literal["subjectAndScene", "visibleAction", "expressionAndGaze", "camera", "audio"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VideoNoParameters(_StrictModel):
    pass


class VideoCountParameters(_StrictModel):
    actual: Annotated[int, Field(ge=0)]
    maximum: Annotated[int, Field(ge=1)]


class VideoActionCountParameters(VideoCountParameters):
    durationMs: Annotated[int, Field(ge=500, le=15_000)]


class VideoScaleParameters(_StrictModel):
    requiredScale: ScaleLabel
    conflictingScales: Annotated[list[ScaleLabel], Field(min_length=1)]


class VideoEffectParameters(_StrictModel):
    effects: Annotated[list[EffectLabel], Field(min_length=1, max_length=9)]


class VideoActionParameters(_StrictModel):
    markers: Annotated[list[ActionMarker], Field(min_length=1)]


class VideoRepeatedFieldParameters(_StrictModel):
    fields: Annotated[list[PromptField], Field(min_length=2, max_length=2)]


VideoFindingCode = Literal[
    "protocol_invalid",
    "dramatic_protocol",
    "dramatic_materialization",
    "design_protocol",
    "design_materialization",
    "prompt_schema",
    "prompt_target_order",
    "prompt_performance",
    "prompt_continuity",
    "prompt_metadata",
    "prompt_neighbor",
    "prompt_scale",
    "prompt_action_count",
    "prompt_expression_invisible",
    "prompt_expression_micro",
    "prompt_expression_interpretation",
    "prompt_action_interpretation",
    "prompt_effects",
    "prompt_affirmative_effects",
    "prompt_unconfirmed_action",
    "prompt_required_hand_blocked",
    "prompt_required_subject_blocked",
    "prompt_required_hand_missing",
    "prompt_repeated_fields",
    "prompt_compile",
    "prompt_budget",
]


class VideoStageValidationFinding(_StrictModel):
    code: VideoFindingCode
    shotKey: ShotKey | None
    parameters: (
        VideoNoParameters
        | VideoActionCountParameters
        | VideoCountParameters
        | VideoScaleParameters
        | VideoEffectParameters
        | VideoActionParameters
        | VideoRepeatedFieldParameters
    )
    blocking: bool

    @model_validator(mode="after")
    def validate_parameters(self) -> Self:
        expected = {
            "prompt_budget": VideoCountParameters,
            "prompt_action_count": VideoActionCountParameters,
            "prompt_scale": VideoScaleParameters,
            "prompt_effects": VideoEffectParameters,
            "prompt_affirmative_effects": VideoEffectParameters,
            "prompt_unconfirmed_action": VideoActionParameters,
            "prompt_repeated_fields": VideoRepeatedFieldParameters,
        }.get(self.code, VideoNoParameters)
        if type(self.parameters) is not expected:
            raise ValueError("验证发现参数必须精确符合该固定错误码")
        if self.code in {
            "protocol_invalid",
            "dramatic_protocol",
            "dramatic_materialization",
            "design_protocol",
            "design_materialization",
            "prompt_schema",
            "prompt_target_order",
        }:
            if self.shotKey is not None or not self.blocking:
                raise ValueError("全阶段结构诊断不得带镜号且必须为结构错误")
        elif self.shotKey is None:
            raise ValueError("逐镜质量诊断必须绑定镜号")
        return self


_FINDING_MESSAGES = {
    "protocol_invalid": "严格返回 JSON Schema 指定对象，不得返回可见正文或不完整结构",
    "dramatic_protocol": "严格按 JSON Schema 返回完整 scenes 对象，不得返回可见正文或不完整结构",
    "dramatic_materialization": (
        "重新检查完整场景与来源绑定，连续行动空间必须分场，Beat 来源按原文顺序排列"
    ),
    "design_protocol": "严格使用 JSON Schema 枚举，从头重写全部 shots",
    "design_materialization": (
        "重新检查每镜来源与所属 Beat 目标、500ms 时长粒度及具体剪辑动机，"
        "保留全部 Beat 顺序并从头重写完整 shots 数组"
    ),
    "prompt_schema": "严格返回 JSON Schema 指定对象，不得返回可见正文或不完整结构",
    "prompt_target_order": "按目标镜头顺序完整返回全部 prompts，不得漏镜、重复或额外添加镜头",
    "prompt_performance": "新候选不得提交历史 performance 字段",
    "prompt_continuity": "新候选不得提交历史 continuity 字段",
    "prompt_metadata": "字段不得重复画幅或时长，二者由编译器统一添加",
    "prompt_neighbor": "不得复述、预演或指导上一镜/下一镜",
    "prompt_expression_invisible": "物件、无人或只见手部镜头的 expressionAndGaze 必须为 null",
    "prompt_expression_micro": "全景或大全景不得描述五官微表情",
    "prompt_expression_interpretation": "expressionAndGaze 只能写可见事实，不能解释内心",
    "prompt_action_interpretation": "visibleAction 只能写可见变化，不能解释内心",
    "prompt_required_hand_blocked": "negativeConstraints 禁止了完成正式动作所必需的手部",
    "prompt_required_subject_blocked": "negativeConstraints 禁止了当前正式镜头必须出现的人物主体",
    "prompt_required_hand_missing": "动作需要人物施力，但主体与动作都没有写出必要手部",
    "prompt_compile": "无法编译：编译后的即梦提示词超过 2000 字安全包络",
}


def video_finding_message(finding: VideoStageValidationFinding) -> str:
    """只从有限模板与已验证参数生成原纠正文字，不回放供应商输入。"""
    params = finding.parameters
    if isinstance(params, VideoActionCountParameters):
        message = (
            f"{params.durationMs / 1000:g} 秒镜头最多允许 {params.maximum} 个动作句，"
            f"当前为 {params.actual} 个"
        )
    elif isinstance(params, VideoCountParameters):
        message = f"编译后 {params.actual} 字，超过当前时长的 {params.maximum} 字上限"
    elif isinstance(params, VideoScaleParameters):
        message = (
            f"显式景别必须保持正式{params.requiredScale}，不能写成："
            f"{', '.join(params.conflictingScales)}"
        )
    elif isinstance(params, VideoEffectParameters):
        prefix = (
            "候选新增了正式镜头未确认的视觉效果："
            if finding.code == "prompt_effects"
            else "negativeConstraints 混入了正向画面要求："
        )
        message = prefix + "、".join(params.effects)
    elif isinstance(params, VideoActionParameters):
        message = f"visibleAction 新增了正式镜头未确认的状态变化：{', '.join(params.markers)}"
    elif isinstance(params, VideoRepeatedFieldParameters):
        message = f"{'/'.join(params.fields)} 重复了同一段镜头事实"
    else:
        message = _FINDING_MESSAGES[finding.code]
    return f"{finding.shotKey} {message}" if finding.shotKey is not None else message


class VideoStepDependency(_StrictModel):
    stepId: ExecutionId
    resultHash: Sha256


class VideoTaskContextV2(_StrictModel):
    taskId: ExecutionId
    payload: Annotated[
        ChapterAdaptationPlanJobPayload | ChapterAdaptationPromptJobPayload,
        Field(discriminator="workflow"),
    ]
    inheritedCheckpoint: DramaticStructureCheckpoint | None

    @model_validator(mode="after")
    def validate_inherited(self) -> Self:
        if (
            isinstance(self.payload, ChapterAdaptationPromptJobPayload)
            and self.inheritedCheckpoint is not None
        ):
            raise ValueError("逐镜提示词不能继承拆镜分析检查点")
        return self


class _VideoInput(_StrictModel):
    cycle: Literal[0, 1]
    correction: bool
    dependencies: Annotated[list[VideoStepDependency], Field(max_length=9)]

    @field_validator("cycle", mode="before")
    @classmethod
    def validate_cycle_type(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("阶段轮次必须是整数，不能使用布尔值")
        return value

    @field_validator("correction", mode="before")
    @classmethod
    def validate_correction_type(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("阶段纠正标记必须是布尔值")
        return value

    @model_validator(mode="after")
    def validate_dependencies(self) -> Self:
        if len({item.stepId for item in self.dependencies}) != len(self.dependencies):
            raise ValueError("阶段依赖不能重复")
        if self.correction and (self.cycle != 0 or not self.dependencies):
            raise ValueError("结构纠正只能绑定初始轮次的前序结果")
        return self


class VideoDramaticStructureInput(_VideoInput):
    stageKey: Literal["dramatic_structure"]
    cycle: Literal[0]
    correctionFindings: list[VideoStageValidationFinding]

    @model_validator(mode="after")
    def validate_correction(self) -> Self:
        if self.correction != bool(self.correctionFindings):
            raise ValueError("分析纠正标记与原因不一致")
        if any(
            item.code not in {"protocol_invalid", "dramatic_protocol", "dramatic_materialization"}
            for item in self.correctionFindings
        ):
            raise ValueError("分析纠正只能绑定本阶段安全诊断")
        return self


class VideoShotDesignInput(_VideoInput):
    stageKey: Literal["shot_design"]
    checkpoint: DramaticStructureCheckpoint
    requiredChanges: list[str]
    correctionFindings: list[VideoStageValidationFinding]

    @model_validator(mode="after")
    def validate_design(self) -> Self:
        if self.correction != bool(self.correctionFindings) or (
            self.cycle == 0 and bool(self.requiredChanges)
        ):
            raise ValueError("镜头设计必须区分结构纠正与审镜返工")
        if any(
            item.code not in {"protocol_invalid", "design_protocol", "design_materialization"}
            for item in self.correctionFindings
        ):
            raise ValueError("镜头结构纠正不能借用其他阶段诊断")
        return self


class VideoMissingBeatShotsInput(_VideoInput):
    stageKey: Literal["missing_beat_shots"]
    correction: Literal[False]
    checkpoint: DramaticStructureCheckpoint
    design: CinematicShotDesignResult
    missingBeatKeys: Annotated[list[BeatKey], Field(min_length=1)]


class VideoCinematicReviewInput(_VideoInput):
    stageKey: Literal["cinematic_review"]
    correction: Literal[False]
    candidate: ChapterAdaptationPlanCandidate


class VideoShotPromptInput(_VideoInput):
    stageKey: Literal["shot_prompt"]
    cycle: Literal[0]
    correctionFindings: list[VideoStageValidationFinding]

    @model_validator(mode="after")
    def validate_correction(self) -> Self:
        if self.correction != bool(self.correctionFindings):
            raise ValueError("提示词纠正标记与原因不一致")
        if any(
            item.code != "protocol_invalid" and not item.code.startswith("prompt_")
            for item in self.correctionFindings
        ):
            raise ValueError("提示词纠正不能借用其他阶段诊断")
        return self


VideoStageInput = Annotated[
    VideoDramaticStructureInput
    | VideoShotDesignInput
    | VideoMissingBeatShotsInput
    | VideoCinematicReviewInput
    | VideoShotPromptInput,
    Field(discriminator="stageKey"),
]
VIDEO_STAGE_INPUT_ADAPTER: TypeAdapter[VideoStageInput] = TypeAdapter(VideoStageInput)


class _VideoOutput(_StrictModel):
    validationFindings: list[VideoStageValidationFinding]


class VideoDramaticStructureOutput(_VideoOutput):
    stageKey: Literal["dramatic_structure"]
    outcome: Literal["ready", "needs_correction"]
    checkpoint: DramaticStructureCheckpoint | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if (self.outcome == "ready") != (self.checkpoint is not None) or (
            self.outcome == "needs_correction"
        ) != bool(self.validationFindings):
            raise ValueError("分析阶段结果与产物不一致")
        return self


class VideoShotDesignOutput(_VideoOutput):
    stageKey: Literal["shot_design"]
    outcome: Literal["ready", "needs_correction", "needs_supplement"]
    design: CinematicShotDesignResult | None
    candidate: ChapterAdaptationPlanCandidate | None
    missingBeatKeys: list[BeatKey]

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if (
            (self.outcome == "ready") != (self.candidate is not None)
            or (self.outcome == "needs_supplement")
            != (self.design is not None and bool(self.missingBeatKeys))
            or (self.outcome == "needs_correction") != bool(self.validationFindings)
        ):
            raise ValueError("镜头设计结果与规范化产物不一致")
        if self.outcome != "needs_supplement" and (self.design is not None or self.missingBeatKeys):
            raise ValueError("非补槽结果不得夹带部分设计")
        return self


class VideoMissingBeatShotsOutput(_VideoOutput):
    stageKey: Literal["missing_beat_shots"]
    outcome: Literal["ready", "needs_correction"]
    candidate: ChapterAdaptationPlanCandidate | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if (self.outcome == "ready") != (self.candidate is not None) or (
            self.outcome == "needs_correction"
        ) != bool(self.validationFindings):
            raise ValueError("补槽合并物化结果不一致")
        return self


class VideoCinematicReviewConclusion(CinematicReviewResult):
    """仅扩大程序合并后的发现包络；模型本身仍最多返回 240 条。"""

    findings: list[CinematicReviewFinding] = Field(max_length=1203)


class VideoCinematicReviewOutput(_VideoOutput):
    stageKey: Literal["cinematic_review"]
    outcome: Literal["ready"]
    review: VideoCinematicReviewConclusion


class VideoShotPromptOutput(_VideoOutput):
    stageKey: Literal["shot_prompt"]
    outcome: Literal["ready", "needs_correction"]
    promptBatch: ShotPromptSpecBatch | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome == "ready" and (
            self.promptBatch is None or any(item.blocking for item in self.validationFindings)
        ):
            raise ValueError("可用提示词批次不能缺失或含硬错误")
        if self.outcome == "needs_correction" and not self.validationFindings:
            raise ValueError("提示词纠正必须携带安全发现")
        return self
