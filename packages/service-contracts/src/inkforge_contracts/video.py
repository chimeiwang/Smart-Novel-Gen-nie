"""Core 与 Agent 共用的视频规划、提示词和回调契约。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from math import ceil
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

AssetModality = Literal["image", "video", "audio"]
AssetDuty = Literal[
    "identity",
    "costume",
    "scene",
    "prop",
    "style",
    "storyboard",
    "keyframe",
    "motion",
    "camera",
    "voice",
    "ambience",
    "sfx",
    "music",
    "episode_export",
]
UploadAssetDuty = Literal[
    "identity",
    "costume",
    "scene",
    "prop",
    "style",
    "storyboard",
    "keyframe",
    "motion",
    "camera",
    "voice",
    "ambience",
    "sfx",
    "music",
]
PlannedAssetDuty = Literal[
    "identity",
    "costume",
    "scene",
    "prop",
    "style",
    "storyboard",
    "keyframe",
    "motion",
    "camera",
    "voice",
    "ambience",
    "music",
    "relation_interaction",
]
SettingKind = Literal["character", "relationship", "location", "item", "world_setting"]
AssetBindingScope = Literal["canon_slot", "scene_direct"]
ShotSize = Literal["大全景", "全景", "中景", "近景", "特写"]
Resolution = Literal["480p", "720p"]
AspectRatio = Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
OutputFormat = Literal["mp4", "mov"]
AssetFeatureDomain = Literal[
    "character_identity",
    "character_costume",
    "location",
    "prop",
    "style",
    "storyboard",
    "keyframe",
    "motion",
    "camera",
    "voice",
    "ambience",
    "music",
    "relationship_interaction",
]
KeyframeRole = Literal["initial_state", "end_state", "transition_anchor"]
ActionComplexity = Literal[
    "legacy_unclassified",
    "simple",
    "mechanical_sequence",
    "transformation",
    "impact_transition",
]
DirectorActionComplexity = Literal[
    "simple",
    "mechanical_sequence",
    "transformation",
    "impact_transition",
]
PlannerAssetDuty = Literal[
    "identity",
    "costume",
    "scene",
    "prop",
    "style",
    "storyboard",
    "keyframe",
    "motion",
    "camera",
    "voice",
    "ambience",
    "relation_interaction",
]
PlannerAssetScope = Literal["canon_slot", "scene_direct"]
VideoPlanningRoute = Literal[
    "responses_json_schema_v1",
    "legacy_strict_tool_v1",
    "chat_json_output_v1",
]
VideoPlanningModel = Literal["deepseek-v4-flash"]
DirectorDraftVersion = Literal["1.0", "1.1", "1.2", "1.3", "1.4"]
SourceEventFamily = Literal[
    "insert",
    "crush",
    "open",
    "touch",
    "accelerate",
    "raise",
    "fall",
    "smash",
]
ShotChangeMode = Literal["continuous", "cut", "match_cut", "impact_cut"]
PromptCompileProfile = Literal[
    "legacy_single_prompt_v1",
    "dual_layer_v1",
    "seedance_cinematic_v2",
    "seedance_director_v3",
    "seedance_director_v3_compat",
]
CaptureFormat = Literal["super_35", "full_frame"]
LensProjection = Literal["spherical", "anamorphic"]
CameraAxisRule = Literal["maintain_180", "intentional_cross", "not_applicable"]
ScreenDirection = Literal["left_to_right", "right_to_left", "neutral"]
CameraAxisSide = Literal["screen_left", "screen_right", "on_axis"]
AxisTransition = Literal[
    "hold",
    "continuous_cross",
    "neutral_reset",
    "cutaway_reset",
]
CameraLensType = Literal["prime", "zoom", "macro_prime"]
CameraSupport = Literal[
    "tripod",
    "slider",
    "dolly",
    "gimbal",
    "steadicam",
    "handheld",
    "shoulder",
    "jib",
    "crane",
]
CameraMovementType = Literal[
    "locked_off",
    "dolly_in",
    "dolly_out",
    "truck_left",
    "truck_right",
    "pan_left",
    "pan_right",
    "tilt_up",
    "tilt_down",
    "pedestal_up",
    "pedestal_down",
    "arc_left",
    "arc_right",
    "boom_up",
    "boom_down",
    "zoom_in",
    "zoom_out",
    "handheld_follow",
]
CameraMovementSpeed = Literal["static", "very_slow", "slow", "medium", "fast"]
CameraMovementEasing = Literal["none", "ease_in", "ease_out", "ease_in_out"]
CompositionRule = Literal[
    "centered",
    "rule_of_thirds",
    "symmetrical",
    "leading_lines",
    "frame_within_frame",
    "negative_space",
]
SubjectPlacement = Literal[
    "left_third",
    "center",
    "right_third",
    "lower_center",
    "upper_center",
]
Headroom = Literal["tight", "standard", "generous", "not_applicable"]
DepthOfField = Literal["shallow", "medium", "deep"]
FocusTransition = Literal["locked", "rack_focus"]
ExposureStyle = Literal["low_key", "balanced", "high_key"]
NegativeFillSide = Literal["none", "camera_left", "camera_right", "both"]
LightingContinuityMode = Literal["establish", "inherit", "motivated_change"]
LightRole = Literal["key", "fill", "rim", "background", "practical"]
LightDirection = Literal[
    "front",
    "front_left",
    "front_right",
    "side_left",
    "side_right",
    "back_left",
    "back_right",
    "back",
    "top",
    "bottom",
]
LightQuality = Literal["hard", "soft"]
LightDelivery = Literal["direct", "diffused", "bounced"]
LightFalloff = Literal["fast", "medium", "slow"]
FillStrategy = Literal["none", "soft_fill", "bounce_fill", "negative_fill"]

_PLANNER_ASSET_DUTIES: tuple[PlannerAssetDuty, ...] = (
    "identity",
    "costume",
    "scene",
    "prop",
    "style",
    "storyboard",
    "keyframe",
    "motion",
    "camera",
    "voice",
    "ambience",
    "relation_interaction",
)
_DIRECTOR_ACTION_COMPLEXITIES: tuple[DirectorActionComplexity, ...] = (
    "simple",
    "mechanical_sequence",
    "transformation",
    "impact_transition",
)
_IRREVERSIBLE_MECHANISM_ACTION_MARKERS = (
    "插入",
    "插进",
    "卡入",
    "卡合",
    "嵌入",
    "咬碎",
    "碾碎",
    "弹开",
    "启动",
    "触发",
    "加速",
    "转动",
    "提到最高",
    "提至最高",
    "拉起",
    "松开",
    "落下",
    "砸向",
    "砸碎",
    "崩裂",
    "断裂",
)
_IRREVERSIBLE_MECHANISM_CONTEXT_MARKERS = (
    "机关",
    "齿槽",
    "齿轮",
    "转轮",
    "锁孔",
    "黄铜匣",
    "罗盘",
    "牵引链",
    "链条",
    "钟摆",
    "机械",
)
_CHARACTER_PERFORMANCE_BAN_PATTERNS = (
    re.compile(
        r"(?:不出现|不使用|不得出现|不得包含|不得有|不允许|不要有|禁止|不要|无|没有|"
        r"去掉|移除|取消)(?:任何|所有|一切)?(?:角色|人物)(?:的)?(?:表演|动作|反应|表情)"
    ),
    re.compile(
        r"(?:角色|人物)(?:不要|不得|不能|不可)(?:出现|有|进行)?"
        r"(?:任何|所有|一切)?(?:表演|动作|反应|表情)"
    ),
)
_SOURCE_EVENT_FAMILIES: tuple[tuple[SourceEventFamily, tuple[str, ...]], ...] = (
    ("insert", ("插入", "插进", "嵌入", "卡入", "扣入", "塞入")),
    ("crush", ("咬碎", "碾碎", "压碎", "粉碎")),
    ("open", ("弹开", "打开", "掀开")),
    ("touch", ("触碰", "触到", "触及", "接触")),
    ("accelerate", ("加速", "提速")),
    (
        "raise",
        (
            "提到最高",
            "提至最高",
            "拉到最高",
            "拉至最高",
            "升至最高",
            "提至顶点",
            "拉至顶点",
            "升至顶点",
        ),
    ),
    ("fall", ("落下", "坠下", "下坠")),
    ("smash", ("砸碎", "砸裂", "砸开", "撞碎", "撞裂", "击碎")),
)
_SOURCE_EVENT_FAMILY_LABELS: dict[SourceEventFamily, str] = {
    "insert": "插入",
    "crush": "咬碎",
    "open": "弹开",
    "touch": "触碰",
    "accelerate": "加速",
    "raise": "提起",
    "fall": "落下",
    "smash": "砸碎",
}
_SOURCE_EVENT_NON_ACTUAL_PREFIXES = (
    "未",
    "尚未",
    "还未",
    "没有",
    "并未",
    "不曾",
    "避免",
    "防止",
    "禁止",
    "不得",
    "即将",
    "将要",
    "准备",
    "等待",
)
_SOURCE_EVENT_NON_ACTUAL_SUFFIXES = ("前", "之前", "以前")
_SOURCE_EVENT_GROUNDING_EQUIVALENTS: dict[
    SourceEventFamily,
    tuple[str, ...],
] = {
    "crush": (
        "碎裂",
        "破碎",
        "崩碎",
        "崩裂",
        "断裂",
        "碎成",
        "断成碎片",
        "裂成碎片",
    ),
    "fall": ("砸落", "坠落", "下落"),
    "smash": ("碎裂", "破碎", "破口", "裂缝"),
}
_SOURCE_EVENT_GROUNDING_CONTEXT: dict[
    SourceEventFamily,
    tuple[str, ...],
] = {
    "crush": (
        "机关",
        "齿槽",
        "齿口",
        "齿牙",
        "咬合",
        "夹压",
        "挤压",
        "碾压",
    ),
    "fall": ("钟摆", "重物", "牵引链", "下坠"),
    "smash": ("砸", "撞", "击", "冲击", "钟摆", "墙面"),
}
_KEYFRAME_ROLES: tuple[KeyframeRole, ...] = (
    "initial_state",
    "end_state",
    "transition_anchor",
)
_SHOT_SIZES: tuple[ShotSize, ...] = ("大全景", "全景", "中景", "近景", "特写")
_SHOT_CHANGE_MODES: tuple[ShotChangeMode, ...] = (
    "continuous",
    "cut",
    "match_cut",
    "impact_cut",
)
_CAPTURE_FORMATS: tuple[CaptureFormat, ...] = ("super_35", "full_frame")
_LENS_PROJECTIONS: tuple[LensProjection, ...] = ("spherical", "anamorphic")
_CAMERA_AXIS_RULES: tuple[CameraAxisRule, ...] = (
    "maintain_180",
    "intentional_cross",
    "not_applicable",
)
_SCREEN_DIRECTIONS: tuple[ScreenDirection, ...] = (
    "left_to_right",
    "right_to_left",
    "neutral",
)
_CAMERA_AXIS_SIDES: tuple[CameraAxisSide, ...] = (
    "screen_left",
    "screen_right",
    "on_axis",
)
_AXIS_TRANSITIONS: tuple[AxisTransition, ...] = (
    "hold",
    "continuous_cross",
    "neutral_reset",
    "cutaway_reset",
)
_CAMERA_LENS_TYPES: tuple[CameraLensType, ...] = ("prime", "zoom", "macro_prime")
_CAMERA_SUPPORTS: tuple[CameraSupport, ...] = (
    "tripod",
    "slider",
    "dolly",
    "gimbal",
    "steadicam",
    "handheld",
    "shoulder",
    "jib",
    "crane",
)
_CAMERA_MOVEMENT_TYPES: tuple[CameraMovementType, ...] = (
    "locked_off",
    "dolly_in",
    "dolly_out",
    "truck_left",
    "truck_right",
    "pan_left",
    "pan_right",
    "tilt_up",
    "tilt_down",
    "pedestal_up",
    "pedestal_down",
    "arc_left",
    "arc_right",
    "boom_up",
    "boom_down",
    "zoom_in",
    "zoom_out",
    "handheld_follow",
)
_CAMERA_MOVEMENT_SPEEDS: tuple[CameraMovementSpeed, ...] = (
    "static",
    "very_slow",
    "slow",
    "medium",
    "fast",
)
_CAMERA_MOVEMENT_EASINGS: tuple[CameraMovementEasing, ...] = (
    "none",
    "ease_in",
    "ease_out",
    "ease_in_out",
)
_COMPOSITION_RULES: tuple[CompositionRule, ...] = (
    "centered",
    "rule_of_thirds",
    "symmetrical",
    "leading_lines",
    "frame_within_frame",
    "negative_space",
)
_SUBJECT_PLACEMENTS: tuple[SubjectPlacement, ...] = (
    "left_third",
    "center",
    "right_third",
    "lower_center",
    "upper_center",
)
_HEADROOMS: tuple[Headroom, ...] = ("tight", "standard", "generous", "not_applicable")
_DEPTHS_OF_FIELD: tuple[DepthOfField, ...] = ("shallow", "medium", "deep")
_FOCUS_TRANSITIONS: tuple[FocusTransition, ...] = ("locked", "rack_focus")
_EXPOSURE_STYLES: tuple[ExposureStyle, ...] = ("low_key", "balanced", "high_key")
_NEGATIVE_FILL_SIDES: tuple[NegativeFillSide, ...] = (
    "none",
    "camera_left",
    "camera_right",
    "both",
)
_LIGHTING_CONTINUITY_MODES: tuple[LightingContinuityMode, ...] = (
    "establish",
    "inherit",
    "motivated_change",
)
_LIGHT_ROLES: tuple[LightRole, ...] = ("key", "fill", "rim", "background", "practical")
_LIGHT_DIRECTIONS: tuple[LightDirection, ...] = (
    "front",
    "front_left",
    "front_right",
    "side_left",
    "side_right",
    "back_left",
    "back_right",
    "back",
    "top",
    "bottom",
)
_LIGHT_QUALITIES: tuple[LightQuality, ...] = ("hard", "soft")
_LIGHT_DELIVERIES: tuple[LightDelivery, ...] = ("direct", "diffused", "bounced")
_LIGHT_FALLOFFS: tuple[LightFalloff, ...] = ("fast", "medium", "slow")
_FILL_STRATEGIES: tuple[FillStrategy, ...] = (
    "none",
    "soft_fill",
    "bounce_fill",
    "negative_fill",
)

_FEATURE_DOMAIN_BY_DUTY: dict[str, str] = {
    "identity": "character_identity",
    "costume": "character_costume",
    "scene": "location",
    "prop": "prop",
    "style": "style",
    "storyboard": "storyboard",
    "keyframe": "keyframe",
    "motion": "motion",
    "camera": "camera",
    "voice": "voice",
    "ambience": "ambience",
    "music": "music",
    "relation_interaction": "relationship_interaction",
}
_ALLOWED_MODALITIES_BY_DUTY: dict[str, tuple[AssetModality, ...]] = {
    "identity": ("image", "video"),
    "costume": ("image", "video"),
    "scene": ("image", "video"),
    "prop": ("image", "video"),
    "style": ("image", "video"),
    "storyboard": ("image",),
    "keyframe": ("image",),
    "motion": ("image", "video"),
    "camera": ("video",),
    "voice": ("audio",),
    "ambience": ("audio",),
    "sfx": ("audio",),
    "music": ("audio",),
    "episode_export": ("video",),
    "relation_interaction": ("image", "video"),
}


def validate_asset_duty_modality(modality: AssetModality, duty: str) -> None:
    """统一校验真实素材和规划素材的职责/模态组合。"""

    allowed = _ALLOWED_MODALITIES_BY_DUTY.get(duty)
    if allowed is None or modality not in allowed:
        raise ValueError(f"素材职责 {duty} 不支持 {modality} 模态")


def validate_uploaded_asset_duty_modality(modality: AssetModality, duty: str) -> None:
    """客户端只能上传输入素材；整集成片必须由受控导出器创建。"""

    if duty == "episode_export":
        raise ValueError("episode_export 只能由整集导出任务创建")
    validate_asset_duty_modality(modality, duty)
# 轻量草案不让模型选择可由职责唯一固化的媒介，避免制造无意义组合分支。
_DEFAULT_DRAFT_MODALITY_BY_DUTY: dict[PlannerAssetDuty, AssetModality] = {
    "identity": "image",
    "costume": "image",
    "scene": "image",
    "prop": "image",
    "style": "image",
    "storyboard": "image",
    "keyframe": "image",
    "motion": "video",
    "camera": "video",
    "voice": "audio",
    "ambience": "audio",
    "relation_interaction": "image",
}
_SETTING_DUTIES_BY_KIND: dict[str, set[str]] = {
    "character": {"identity", "costume", "voice"},
    "relationship": {"relation_interaction"},
    "location": {"scene"},
    "item": {"prop"},
    "world_setting": {"style"},
}
_SETTING_KIND_BY_CANON_DUTY: dict[str, SettingKind] = {
    "identity": "character",
    "costume": "character",
    "voice": "character",
    "relation_interaction": "relationship",
    "scene": "location",
    "prop": "item",
    "style": "world_setting",
}
_PLANNER_ASSET_SLOT_COUNT = 11
_PLANNER_FEATURE_SLOT_COUNT = 12
_PLANNER_NEGATIVE_CONSTRAINT_LIMIT = 18
_PLANNER_UNUSED_SENTINEL = "__UNUSED__"
_PLANNER_INHERIT_LIGHTING_SENTINEL = "__INHERIT__"
_PLANNER_NONE_SETTING_ID = "__NONE__"
_PLANNER_CANON_TARGET = "__CANON__"
_PLANNER_NOT_APPLICABLE_KEYFRAME_ROLE = "not_applicable"
VIDEO_PLAN_MAX_EFFECTIVE_CALLS = 5
_SHOT_SIZE_RANK: dict[str, int] = {
    "大全景": 0,
    "全景": 1,
    "中景": 2,
    "近景": 3,
    "特写": 4,
}


class VideoContractModel(BaseModel):
    """所有视频服务契约都拒绝未声明字段。"""

    model_config = ConfigDict(extra="forbid")


class SettingReference(VideoContractModel):
    """指向长篇冻结设定快照中的一个类型化条目。"""

    kind: SettingKind
    id: str = Field(min_length=1, max_length=160)


class CharacterSettingSnapshot(VideoContractModel):
    """规划任务冻结的人物设定最小投影。"""

    kind: Literal["character"] = "character"
    id: str = Field(min_length=1, max_length=160)
    contentHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    appearance: str | None = None
    identity: str | None = None


class RelationshipSettingSnapshot(VideoContractModel):
    """规划任务冻结的有向人物关系投影。"""

    kind: Literal["relationship"] = "relationship"
    id: str = Field(min_length=1, max_length=160)
    contentHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: str = Field(min_length=1, max_length=200)
    sourceCharacterId: str = Field(min_length=1, max_length=160)
    targetCharacterId: str = Field(min_length=1, max_length=160)
    relationType: str = Field(min_length=1, max_length=120)
    description: str | None = None


class LocationSettingSnapshot(VideoContractModel):
    """规划任务冻结的地点设定投影。"""

    kind: Literal["location"] = "location"
    id: str = Field(min_length=1, max_length=160)
    contentHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    locationType: str | None = None
    parentLocationId: str | None = None
    climate: str | None = None
    culture: str | None = None
    description: str | None = None


class ItemSettingSnapshot(VideoContractModel):
    """规划任务冻结的道具设定投影。"""

    kind: Literal["item"] = "item"
    id: str = Field(min_length=1, max_length=160)
    contentHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    itemType: str | None = None
    ownerCharacterId: str | None = None
    description: str | None = None


class WorldSettingSnapshot(VideoContractModel):
    """规划任务冻结的世界视觉设定来源。"""

    kind: Literal["world_setting"] = "world_setting"
    id: str = Field(min_length=1, max_length=160)
    contentHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


SettingSnapshotEntry = Annotated[
    CharacterSettingSnapshot
    | RelationshipSettingSnapshot
    | LocationSettingSnapshot
    | ItemSettingSnapshot
    | WorldSettingSnapshot,
    Field(discriminator="kind"),
]


def calculate_setting_snapshot_fingerprint(
    entries: Sequence[SettingSnapshotEntry],
) -> str:
    """用稳定顺序和规范 JSON 计算设定快照指纹。"""

    values = [entry.model_dump(mode="json") for entry in entries]
    values.sort(key=lambda item: (str(item["kind"]), str(item["id"])))
    canonical = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LongSerialSettingSnapshot(VideoContractModel):
    """Core 冻结后随长篇视频任务发送的完整设定投影。"""

    schemaVersion: Literal["1.0"] = "1.0"
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: list[SettingSnapshotEntry]

    @classmethod
    def from_entries(
        cls,
        entries: Sequence[SettingSnapshotEntry],
    ) -> LongSerialSettingSnapshot:
        """从条目构造带可信指纹的冻结快照。"""

        values = list(entries)
        return cls(
            fingerprint=calculate_setting_snapshot_fingerprint(values),
            entries=values,
        )

    @model_validator(mode="after")
    def validate_snapshot(self) -> LongSerialSettingSnapshot:
        """拒绝重复身份、悬空关系和与内容不一致的指纹。"""

        keys = [(entry.kind, entry.id) for entry in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError("长篇设定快照不能包含重复的类型化身份")

        character_ids = {entry.id for entry in self.entries if entry.kind == "character"}
        for entry in self.entries:
            if entry.kind == "relationship" and (
                entry.sourceCharacterId not in character_ids
                or entry.targetCharacterId not in character_ids
            ):
                raise ValueError("关系设定的两端人物必须同时存在于冻结快照")
            if entry.kind == "item" and (
                entry.ownerCharacterId is not None and entry.ownerCharacterId not in character_ids
            ):
                raise ValueError("道具设定的持有人必须存在于冻结快照")

        expected = calculate_setting_snapshot_fingerprint(self.entries)
        if self.fingerprint != expected:
            raise ValueError("长篇设定快照指纹与内容不一致")
        return self

    def resolve(self, reference: SettingReference) -> SettingSnapshotEntry:
        """按类型与身份解析条目，找不到时明确失败。"""

        for entry in self.entries:
            if entry.kind == reference.kind and entry.id == reference.id:
                return entry
        raise ValueError(f"设定引用不存在：{reference.kind}:{reference.id}")


class PlannedAsset(VideoContractModel):
    """语言模型提出的素材需求；它不是已上传、已锁定的真实素材。"""

    assetId: str = Field(min_length=1, max_length=160)
    modality: AssetModality
    duty: PlannedAssetDuty
    bindingScope: AssetBindingScope = "scene_direct"
    settingReference: SettingReference | None = None
    featureDomain: AssetFeatureDomain | None = None
    keyframeRole: KeyframeRole | None = None
    targetEntity: str = Field(min_length=1, max_length=200)
    includeFeatures: list[str] = Field(min_length=1, max_length=12)
    excludeFeatures: list[str] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_duty_modality(self) -> PlannedAsset:
        """阻止音频承担运镜、图片承担音色等不可能的职责。"""

        validate_asset_duty_modality(self.modality, self.duty)
        if self.bindingScope == "canon_slot" and self.settingReference is None:
            raise ValueError("canon_slot 素材必须引用冻结设定")
        if self.bindingScope == "scene_direct" and self.settingReference is not None:
            raise ValueError("scene_direct 素材不能同时引用设定槽位")

        if (
            self.settingReference is not None
            and self.duty not in _SETTING_DUTIES_BY_KIND[self.settingReference.kind]
        ):
            raise ValueError(f"设定类型 {self.settingReference.kind} 不能承担素材职责 {self.duty}")
        expected_domain = _FEATURE_DOMAIN_BY_DUTY[self.duty]
        if self.featureDomain is not None and self.featureDomain != expected_domain:
            raise ValueError(f"素材职责 {self.duty} 必须使用原子特征域 {expected_domain}")
        if self.duty != "keyframe" and self.keyframeRole is not None:
            raise ValueError("只有 keyframe 素材可以声明 keyframeRole")
        return self


class PlannedAssetArguments(VideoContractModel):
    """导演 strict 工具的素材需求；排除本流程禁止或仅供旧数据使用的值。"""

    assetId: str = Field(min_length=1, max_length=160)
    modality: AssetModality
    duty: PlannerAssetDuty
    bindingScope: AssetBindingScope
    settingReference: SettingReference | None
    featureDomain: AssetFeatureDomain
    keyframeRole: KeyframeRole | None
    targetEntity: str = Field(min_length=1, max_length=200)
    includeFeatures: list[str] = Field(min_length=1, max_length=12)
    excludeFeatures: list[str] = Field(max_length=12)

    @model_validator(mode="before")
    @classmethod
    def reject_planner_only_invalid_values(cls, value: Any) -> Any:
        """为被供应商或测试绕过的 strict 失败保留稳定错误码。"""

        if isinstance(value, dict):
            if value.get("duty") == "music":
                raise ValueError("VIDEO_PLAN_MUSIC_FORBIDDEN：视频规划不得创建 music 素材")
            if value.get("featureDomain") is None:
                raise ValueError(
                    "VIDEO_PLAN_FEATURE_DOMAIN_REQUIRED：每个素材必须声明原子 featureDomain"
                )
        return value

    @model_validator(mode="after")
    def validate_asset_semantics(self) -> PlannedAssetArguments:
        """复用正式素材契约的模态、作用域、设定映射和特征域校验。"""

        PlannedAsset.model_validate(self.model_dump())
        return self


class CameraActionUnit(VideoContractModel):
    """一个主体动作及其唯一可见结果。"""

    # 供应商常用自然语言完整描述一个动作；160 字仍能防止把整段剧本塞入单拍。
    subject: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=160)
    visibleResult: str = Field(min_length=1, max_length=160)

    def to_text(self) -> str:
        """生成动作字段使用的稳定中文镜像。"""

        return f"{self.subject}{self.action}，{self.visibleResult}"


def render_action_units(units: Sequence[CameraActionUnit]) -> str:
    """把结构化动作确定性投影为兼容 action 文本。"""

    return "；".join(unit.to_text() for unit in units)


def source_event_family_sequence(text: str) -> tuple[SourceEventFamily, ...]:
    """按冻结文本首次出现位置返回高信号事件族，不携带原句或实体。"""

    normalized = text.casefold()
    positions: list[tuple[int, SourceEventFamily]] = []
    for family, markers in _SOURCE_EVENT_FAMILIES:
        matches = [normalized.find(marker) for marker in markers if marker in normalized]
        if matches:
            positions.append((min(matches), family))
    positions.sort(key=lambda item: item[0])
    return tuple(family for _position, family in positions)


def source_event_family_label(family: SourceEventFamily) -> str:
    """返回可安全进入提示与诊断的静态事件族标签。"""

    return _SOURCE_EVENT_FAMILY_LABELS[family]


def text_affirms_source_event(
    text: str,
    family: SourceEventFamily,
) -> bool:
    """判断一段受控导演文字是否明确表达指定事件已经发生。"""

    normalized = text.casefold()

    def has_actual_marker(markers: Sequence[str]) -> bool:
        """判断至少一个词在局部上下文中表达已经发生。"""

        for marker in markers:
            search_from = 0
            while (index := normalized.find(marker, search_from)) >= 0:
                prefix = normalized[max(0, index - 6) : index]
                suffix_start = index + len(marker)
                suffix = normalized[suffix_start : suffix_start + 3]
                has_non_actual_prefix = any(
                    prefix.endswith(value) for value in _SOURCE_EVENT_NON_ACTUAL_PREFIXES
                )
                has_non_actual_suffix = any(
                    suffix.startswith(value) for value in _SOURCE_EVENT_NON_ACTUAL_SUFFIXES
                )
                if not has_non_actual_prefix and not has_non_actual_suffix:
                    return True
                search_from = suffix_start
        return False

    if has_actual_marker(dict(_SOURCE_EVENT_FAMILIES)[family]):
        return True
    equivalent_markers = _SOURCE_EVENT_GROUNDING_EQUIVALENTS.get(family, ())
    context_markers = _SOURCE_EVENT_GROUNDING_CONTEXT.get(family, ())
    if not equivalent_markers or not context_markers:
        return False
    if not any(marker in normalized for marker in context_markers):
        return False
    return has_actual_marker(equivalent_markers)


def action_unit_affirms_source_event(
    unit: CameraActionUnit,
    family: SourceEventFamily,
) -> bool:
    """只认主体、动作和结果共同表达的已发生事件，排除否定、将来与发生前。"""

    return text_affirms_source_event(
        f"{unit.subject}，{unit.action}，{unit.visibleResult}",
        family,
    )


def is_irreversible_mechanical_beat(
    action_complexity: DirectorActionComplexity,
    action_units: Sequence[CameraActionUnit],
) -> bool:
    """用复杂度和高信号动作共同识别全场首个不可逆机关起点。"""

    if action_complexity == "mechanical_sequence":
        return True
    action_text = render_action_units(action_units).casefold()
    return any(
        marker in action_text for marker in _IRREVERSIBLE_MECHANISM_ACTION_MARKERS
    ) and any(marker in action_text for marker in _IRREVERSIBLE_MECHANISM_CONTEXT_MARKERS)


def bans_required_character_performance(constraint: str) -> bool:
    """识别笼统禁止人物表演的全局禁项，不误伤“禁止夸张表演”等窄约束。"""

    normalized = re.sub(r"\s+", "", constraint.casefold())
    return any(
        pattern.search(normalized) is not None
        for pattern in _CHARACTER_PERFORMANCE_BAN_PATTERNS
    )


class CameraShotProgression(VideoContractModel):
    """单个镜头节拍内的起止景别及其变化方式。"""

    startShotSize: ShotSize
    endShotSize: ShotSize
    changeMode: ShotChangeMode


class CinematographyBase(VideoContractModel):
    """全场共享的摄影机成像与轴线基线。"""

    captureFormat: CaptureFormat
    lensProjection: LensProjection
    frameRateFps: Literal[24, 25, 30]
    shutterAngleDegrees: Literal[90, 144, 180, 270, 360]
    axisRule: CameraAxisRule
    screenDirection: ScreenDirection


class CameraPositionSpec(VideoContractModel):
    """相对主体的可复核机位，不把“低机位”等模糊词当成唯一事实。"""

    heightCm: int = Field(ge=0, le=1_000)
    azimuthDegrees: int = Field(ge=-180, le=180)
    elevationDegrees: int = Field(ge=-90, le=90)
    rollDegrees: int = Field(ge=-45, le=45)
    subjectDistanceMeters: float = Field(gt=0, le=100)
    axisSide: CameraAxisSide


class CameraCompositionSpec(VideoContractModel):
    """镜头构图和画面层次。"""

    rule: CompositionRule
    subjectPlacement: SubjectPlacement
    subjectFramePercent: int = Field(ge=5, le=100)
    headroom: Headroom
    foregroundLayer: str = Field(min_length=1, max_length=160)
    backgroundLayer: str = Field(min_length=1, max_length=160)


class CameraMovementSpec(VideoContractModel):
    """单一主运镜；位移与旋转量用于本地可执行性校验。"""

    support: CameraSupport
    movementType: CameraMovementType
    travelDistanceMeters: float = Field(ge=0, le=50)
    rotationDegrees: float = Field(ge=0, le=360)
    speed: CameraMovementSpeed
    easing: CameraMovementEasing

    @model_validator(mode="after")
    def validate_movement(self) -> CameraMovementSpec:
        """拒绝锁定机位仍位移、定焦镜头变焦等物理冲突的运动事实。"""

        translating = {
            "dolly_in",
            "dolly_out",
            "truck_left",
            "truck_right",
            "pedestal_up",
            "pedestal_down",
            "boom_up",
            "boom_down",
            "handheld_follow",
        }
        rotating = {"pan_left", "pan_right", "tilt_up", "tilt_down"}
        if self.movementType == "locked_off":
            if self.travelDistanceMeters != 0 or self.rotationDegrees != 0:
                raise ValueError("locked_off 机位不能同时声明位移或旋转")
            if self.speed != "static":
                raise ValueError("locked_off 机位的速度必须是 static")
        elif self.speed == "static":
            raise ValueError("非 locked_off 运镜不能使用 static 速度")

        if self.movementType in translating and self.travelDistanceMeters <= 0:
            raise ValueError("位移运镜必须声明大于零的 travelDistanceMeters")
        if self.movementType in rotating and self.rotationDegrees <= 0:
            raise ValueError("摇摄或俯仰运镜必须声明大于零的 rotationDegrees")
        if self.movementType in {"arc_left", "arc_right"} and (
            self.travelDistanceMeters <= 0 or self.rotationDegrees <= 0
        ):
            raise ValueError("环绕运镜必须同时声明位移距离和旋转角度")
        if self.movementType in {"zoom_in", "zoom_out"} and (
            self.travelDistanceMeters != 0 or self.rotationDegrees != 0
        ):
            raise ValueError("光学变焦不能伪装成摄影机位移或旋转")
        return self


class CameraFocusSpec(VideoContractModel):
    """景深和焦点迁移计划。"""

    depthOfField: DepthOfField
    startTarget: str = Field(min_length=1, max_length=120)
    endTarget: str = Field(min_length=1, max_length=120)
    transition: FocusTransition
    rackDurationSeconds: float = Field(ge=0, le=30)

    @model_validator(mode="after")
    def validate_focus(self) -> CameraFocusSpec:
        """焦点锁定与拉焦必须各自形成唯一、无矛盾的状态。"""

        if self.transition == "locked":
            if self.startTarget != self.endTarget or self.rackDurationSeconds != 0:
                raise ValueError("锁定焦点时起止目标必须一致且拉焦时长为零")
        elif self.startTarget == self.endTarget or self.rackDurationSeconds <= 0:
            raise ValueError("拉焦必须声明不同的起止目标和大于零的时长")
        return self


class ShotCameraSpec(VideoContractModel):
    """单拍专业摄影规格；所有数值都以生成意图而非硬件遥测解释。"""

    lensType: CameraLensType
    focalLengthMm: int = Field(ge=12, le=200)
    endFocalLengthMm: int = Field(ge=12, le=200)
    tStop: float = Field(ge=1.0, le=22)
    position: CameraPositionSpec
    composition: CameraCompositionSpec
    movement: CameraMovementSpec
    focus: CameraFocusSpec

    @model_validator(mode="after")
    def validate_lens_and_movement(self) -> ShotCameraSpec:
        """镜头类别、焦距变化和主运镜必须能够同时成立。"""

        is_zoom_move = self.movement.movementType in {"zoom_in", "zoom_out"}
        if self.lensType in {"prime", "macro_prime"}:
            if self.endFocalLengthMm != self.focalLengthMm or is_zoom_move:
                raise ValueError("定焦或微距定焦镜头不能声明焦距变化或 zoom 运镜")
        elif not is_zoom_move or self.endFocalLengthMm == self.focalLengthMm:
            raise ValueError("zoom 镜头必须用 zoom_in/zoom_out 并声明不同的起止焦距")
        if self.movement.movementType == "zoom_in" and (
            self.endFocalLengthMm <= self.focalLengthMm
        ):
            raise ValueError("zoom_in 的结束焦距必须大于起始焦距")
        if self.movement.movementType == "zoom_out" and (
            self.endFocalLengthMm >= self.focalLengthMm
        ):
            raise ValueError("zoom_out 的结束焦距必须小于起始焦距")
        return self


class LightingSetup(VideoContractModel):
    """全场环境曝光与灯光连续性基线。"""

    exposureStyle: ExposureStyle
    ambientSource: str = Field(min_length=1, max_length=160)
    ambientColorTemperatureK: int = Field(ge=1_500, le=20_000)
    # 旧版场景没有记录机内白平衡；1.3 在场景级门禁中将其收紧为必填。
    cameraWhiteBalanceK: int | None = Field(default=None, ge=1_500, le=20_000)
    keyToFillStops: float = Field(ge=0, le=8)
    negativeFillSide: NegativeFillSide
    atmosphere: str = Field(min_length=1, max_length=200)


class LightSourceSpec(VideoContractModel):
    """一盏有动机、有方向并能描述画面结果的灯。"""

    role: LightRole
    motivatedBy: str = Field(min_length=1, max_length=160)
    direction: LightDirection
    azimuthDegrees: int = Field(ge=-180, le=180)
    elevationDegrees: int = Field(ge=-90, le=90)
    quality: LightQuality
    delivery: LightDelivery
    colorTemperatureK: int = Field(ge=1_500, le=20_000)
    relativeExposureStops: float = Field(ge=-8, le=8)
    beamAngleDegrees: int = Field(ge=1, le=180)
    falloff: LightFalloff
    spillControl: str = Field(min_length=1, max_length=160)
    visibleResult: str = Field(min_length=1, max_length=240)


class ShotLightingCue(VideoContractModel):
    """逐拍灯光：主光必填，边缘/背景/实景光按需启用。"""

    continuityMode: LightingContinuityMode
    motivatedChange: str = Field(max_length=160)
    keyLight: LightSourceSpec
    fillStrategy: FillStrategy
    fillDirection: LightDirection | None
    fillRelativeStops: float = Field(ge=-8, le=8)
    edgeLight: LightSourceSpec | None = None
    atmosphere: str = Field(min_length=1, max_length=200)
    visibleResult: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_roles(self) -> ShotLightingCue:
        """固定主光和边缘光职责，防止同一灯槽表达多种互斥角色。"""

        if self.continuityMode != "inherit" and not self.motivatedChange.strip():
            raise ValueError("establish 与 motivated_change 必须说明灯光建立或变化动机")
        if self.keyLight.role != "key":
            raise ValueError("keyLight 的 role 必须是 key")
        if self.edgeLight is not None and self.edgeLight.role not in {
            "rim",
            "background",
            "practical",
        }:
            raise ValueError("edgeLight 只能承担 rim、background 或 practical 职责")
        if self.fillStrategy == "none" and self.fillRelativeStops != -8:
            raise ValueError("无补光时 fillRelativeStops 必须使用 -8 作为关闭值")
        if self.fillStrategy != "none" and self.fillDirection is None:
            raise ValueError("启用补光时必须声明 fillDirection")
        return self


class CameraBeatSpec(VideoContractModel):
    """整数秒、单一主运镜的连续镜头节拍。"""

    beatId: str = Field(min_length=1, max_length=120)
    startSecond: int = Field(ge=0, le=29)
    endSecond: int = Field(gt=0, le=30)
    shotSize: ShotSize
    cameraAngle: str = Field(min_length=1, max_length=80)
    cameraMovement: str = Field(min_length=1, max_length=120)
    # 1.0 至 1.2 的历史场景缺少导演语义，保持可空只用于读取兼容。
    dramaticPurpose: str | None = Field(default=None, min_length=1, max_length=240)
    performanceDirection: str | None = Field(default=None, min_length=1, max_length=300)
    blocking: str | None = Field(default=None, min_length=1, max_length=300)
    cameraMotivation: str | None = Field(default=None, min_length=1, max_length=240)
    axisTransition: AxisTransition | None = None
    action: str = Field(min_length=1, max_length=500)
    actionUnits: list[CameraActionUnit] = Field(default_factory=list, max_length=3)
    actionComplexity: ActionComplexity = "legacy_unclassified"
    shotProgression: CameraShotProgression | None = None
    cameraSpec: ShotCameraSpec | None = None
    lightingCue: ShotLightingCue | None = None
    sound: str | None = None
    transition: str | None = None
    referencedAssetIds: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_time_range(self) -> CameraBeatSpec:
        """单个节拍不能倒序或零时长。"""

        if self.endSecond <= self.startSecond:
            raise ValueError("镜头节拍结束时间必须晚于开始时间")
        if self.shotProgression is not None and self.shotProgression.startShotSize != self.shotSize:
            raise ValueError("shotSize 必须等于 shotProgression.startShotSize")
        return self


class CameraBeatPlanArguments(VideoContractModel):
    """strict 工具只提交导演事实，不重复提交由服务器生成的兼容镜像。"""

    beatId: str = Field(min_length=1, max_length=120)
    startSecond: int = Field(ge=0, le=29)
    endSecond: int = Field(gt=0, le=30)
    cameraAngle: str = Field(min_length=1, max_length=80)
    cameraMovement: str = Field(min_length=1, max_length=120)
    dramaticPurpose: str = Field(min_length=1, max_length=240)
    performanceDirection: str = Field(min_length=1, max_length=300)
    blocking: str = Field(min_length=1, max_length=300)
    cameraMotivation: str = Field(min_length=1, max_length=240)
    axisTransition: AxisTransition
    actionUnits: list[CameraActionUnit] = Field(min_length=1, max_length=3)
    actionComplexity: DirectorActionComplexity
    shotProgression: CameraShotProgression
    cameraSpec: ShotCameraSpec
    lightingCue: ShotLightingCue
    sound: str = Field(min_length=1, max_length=500)
    transition: str | None
    referencedAssetIds: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="before")
    @classmethod
    def reject_planner_only_invalid_values(cls, value: Any) -> Any:
        """strict 被绕过时也返回与导演门禁一致的稳定错误码。"""

        if isinstance(value, dict):
            if not value.get("actionUnits"):
                raise ValueError("VIDEO_PLAN_ACTION_UNITS_REQUIRED：每个镜头必须声明动作单元")
            if value.get("actionComplexity") == "legacy_unclassified":
                raise ValueError(
                    "VIDEO_PLAN_ACTION_COMPLEXITY_REQUIRED：导演规划不能使用 legacy 值"
                )
            sound = value.get("sound")
            if not isinstance(sound, str) or not sound.strip():
                raise ValueError("VIDEO_PLAN_SYNC_SOUND_REQUIRED：每个镜头必须声明同步声音")
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> CameraBeatPlanArguments:
        """工具节拍也必须在进入 Agent 业务校验前拒绝倒序时间。"""

        if self.endSecond <= self.startSecond:
            raise ValueError("镜头节拍结束时间必须晚于开始时间")
        return self


class ScenePlanToolArguments(VideoContractModel):
    """DeepSeek strict 工具必须提交的完整单场景结构。"""

    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)
    dramaticArc: str = Field(min_length=1, max_length=500)
    visualStyle: str = Field(min_length=1, max_length=500)
    globalDirection: str = Field(min_length=1, max_length=500)
    cinematographyBase: CinematographyBase
    lightingSetup: LightingSetup
    assets: list[PlannedAssetArguments] = Field(min_length=1, max_length=12)
    beats: list[CameraBeatPlanArguments] = Field(min_length=1, max_length=5)
    # 服务器最多再加入禁 BGM 与不可读文字两条硬约束，预留容量避免编译期溢出。
    negativeConstraints: list[str] = Field(min_length=1, max_length=18)


class StoryBeatPlanArguments(VideoContractModel):
    """第一阶段完成业务归一化后的单拍叙事与调度事实。"""

    beatId: str = Field(min_length=1, max_length=120)
    startSecond: int = Field(ge=0, le=29)
    endSecond: int = Field(gt=0, le=30)
    dramaticPurpose: str = Field(min_length=1, max_length=240)
    performanceDirection: str = Field(min_length=1, max_length=300)
    blocking: str = Field(min_length=1, max_length=300)
    actionUnits: list[CameraActionUnit] = Field(min_length=1, max_length=2)
    # v2 canonical checkpoint 保存模型对原文事件首次发生位置的结构化归属；
    # 内层顺序与 actionUnits 一一对应，E 别名不会进入最终 Provider 提示词。
    sourceEventAliasesByAction: list[list[str]] = Field(default_factory=list, max_length=2)
    actionComplexity: DirectorActionComplexity
    sound: str = Field(min_length=1, max_length=500)
    referencedAssetIds: list[str] = Field(max_length=11)

    @model_validator(mode="after")
    def validate_time_range(self) -> StoryBeatPlanArguments:
        """规范阶段也不能保存倒序或零时长节拍。"""

        if self.endSecond <= self.startSecond:
            raise ValueError("镜头节拍结束时间必须晚于开始时间")
        if self.sourceEventAliasesByAction and len(self.sourceEventAliasesByAction) != len(
            self.actionUnits
        ):
            raise ValueError("原文事件归属必须与动作单元一一对应")
        for aliases in self.sourceEventAliasesByAction:
            if len(aliases) != len(set(aliases)):
                raise ValueError("单个动作槽不能重复归属同一原文事件")
            if any(re.fullmatch(r"E[0-9]{2}", alias) is None for alias in aliases):
                raise ValueError("原文事件归属只能使用 E 短别名")
        return self


class SceneAssetsStageArguments(VideoContractModel):
    """场景与素材阶段完成本地归一化后的耐久规范。"""

    schemaVersion: Literal["1.0"] = "1.0"
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=240)
    dramaticArc: str = Field(min_length=1, max_length=240)
    visualStyle: str = Field(min_length=1, max_length=240)
    globalDirection: str = Field(min_length=1, max_length=240)
    assets: list[PlannedAssetArguments] = Field(min_length=1, max_length=11)
    negativeConstraints: list[str] = Field(min_length=1, max_length=18)

    @model_validator(mode="after")
    def validate_compact_assets(self) -> SceneAssetsStageArguments:
        """锁定连续素材 ID 和新阶段的紧凑文本包络。"""

        expected_asset_ids = [_planner_asset_key(index) for index in range(1, len(self.assets) + 1)]
        if [asset.assetId for asset in self.assets] != expected_asset_ids:
            raise ValueError("场景素材阶段的素材 ID 必须按 asset01 起连续编号")
        for asset in self.assets:
            _require_strict_text(asset.targetEntity, 80, f"{asset.assetId}.targetEntity")
            for index, value in enumerate(asset.includeFeatures):
                _require_strict_text(value, 80, f"{asset.assetId}.include[{index}]")
            for index, value in enumerate(asset.excludeFeatures):
                _require_strict_text(value, 80, f"{asset.assetId}.exclude[{index}]")
        for index, value in enumerate(self.negativeConstraints):
            _require_strict_text(value, 120, f"negativeConstraints[{index}]")
        return self


class StoryBeatsStageArguments(VideoContractModel):
    """故事节拍阶段完成本地归一化后的耐久规范。"""

    schemaVersion: Literal["1.0", "2.0"] = "1.0"
    beats: list[StoryBeatPlanArguments] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_compact_beats(self) -> StoryBeatsStageArguments:
        """锁定连续时间、节拍身份及新阶段的紧凑文本包络。"""

        previous_end = 0
        for index, beat in enumerate(self.beats, start=1):
            if beat.beatId != f"beat-{index:02d}":
                raise ValueError("故事节拍阶段的节拍 ID 必须按 beat-01 起连续编号")
            if beat.startSecond != previous_end:
                raise ValueError("故事节拍阶段的时间轴必须从 0 秒开始并保持连续")
            _require_strict_text(
                beat.dramaticPurpose,
                160,
                f"{beat.beatId}.dramaticPurpose",
            )
            _require_strict_text(
                beat.performanceDirection,
                200,
                f"{beat.beatId}.performanceDirection",
            )
            _require_strict_text(beat.blocking, 200, f"{beat.beatId}.blocking")
            _require_strict_text(beat.sound, 240, f"{beat.beatId}.sound")
            if len(beat.referencedAssetIds) != len(set(beat.referencedAssetIds)):
                raise ValueError("故事节拍阶段的单拍素材引用不能重复")
            if self.schemaVersion == "2.0" and len(beat.sourceEventAliasesByAction) != len(
                beat.actionUnits
            ):
                raise ValueError("2.0 故事检查点必须保存每个动作槽的原文事件归属")
            if self.schemaVersion == "1.0" and beat.sourceEventAliasesByAction:
                raise ValueError("1.0 故事检查点不能混入 2.0 原文事件归属")
            previous_end = beat.endSecond
        return self


class StoryPlanStageArguments(VideoContractModel):
    """可序列化并交给第二阶段只读的版本化叙事规范。"""

    schemaVersion: Literal["1.0", "2.0"] = "1.0"
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)
    dramaticArc: str = Field(min_length=1, max_length=500)
    visualStyle: str = Field(min_length=1, max_length=500)
    globalDirection: str = Field(min_length=1, max_length=500)
    assets: list[PlannedAssetArguments] = Field(min_length=1, max_length=11)
    beats: list[StoryBeatPlanArguments] = Field(min_length=1, max_length=5)
    negativeConstraints: list[str] = Field(min_length=1, max_length=18)

    @model_validator(mode="after")
    def validate_canonical_references(self) -> StoryPlanStageArguments:
        """锁定规范槽位身份、连续时间与双向素材引用完整性。"""

        expected_asset_ids = [_planner_asset_key(index) for index in range(1, len(self.assets) + 1)]
        actual_asset_ids = [asset.assetId for asset in self.assets]
        if actual_asset_ids != expected_asset_ids:
            raise ValueError("第一阶段规范的素材 ID 必须按 asset01 起连续编号")

        known_assets = set(actual_asset_ids)
        referenced_assets: set[str] = set()
        previous_end = 0
        for index, beat in enumerate(self.beats, start=1):
            if beat.beatId != f"beat-{index:02d}":
                raise ValueError("第一阶段规范的节拍 ID 必须按 beat-01 起连续编号")
            if beat.startSecond != previous_end:
                raise ValueError("第一阶段规范的时间轴必须从 0 秒开始并保持连续")
            unknown_assets = set(beat.referencedAssetIds) - known_assets
            if unknown_assets:
                names = "、".join(sorted(unknown_assets))
                raise ValueError(f"第一阶段规范的节拍引用了未声明素材：{names}")
            if len(beat.referencedAssetIds) != len(set(beat.referencedAssetIds)):
                raise ValueError("第一阶段规范的单拍素材引用不能重复")
            if self.schemaVersion == "2.0" and len(beat.sourceEventAliasesByAction) != len(
                beat.actionUnits
            ):
                raise ValueError("2.0 故事规范必须保存每个动作槽的原文事件归属")
            if self.schemaVersion == "1.0" and beat.sourceEventAliasesByAction:
                raise ValueError("1.0 故事规范不能混入 2.0 原文事件归属")
            referenced_assets.update(beat.referencedAssetIds)
            previous_end = beat.endSecond
        if referenced_assets != known_assets:
            names = "、".join(sorted(known_assets - referenced_assets))
            raise ValueError(f"第一阶段规范包含未被任何节拍使用的素材：{names}")
        return self


class DirectorSourceAliasV1(VideoContractModel):
    """服务器为冻结设定分配的短别名，模型只能回传 alias。"""

    alias: str = Field(pattern=r"^[CRLIW][0-9]{2}$")
    settingReference: SettingReference
    name: str = Field(min_length=1, max_length=200)
    allowedDuties: list[PlannerAssetDuty] = Field(min_length=1)


class DirectorAssetAliasV1(VideoContractModel):
    """服务器为已物化素材分配的短别名，不向模型暴露正式 assetId。"""

    alias: str = Field(pattern=r"^A[0-9]{2}$")
    ordinal: int = Field(ge=1, le=11)
    targetEntity: str = Field(min_length=1, max_length=200)
    duty: PlannerAssetDuty


class DirectorBeatAliasV1(VideoContractModel):
    """服务器锁定的节拍短别名与时间骨架。"""

    alias: str = Field(pattern=r"^B[0-9]{2}$")
    ordinal: int = Field(ge=1, le=5)
    startSecond: int = Field(ge=0, le=29)
    endSecond: int = Field(gt=0, le=30)

    @model_validator(mode="after")
    def validate_time_range(self) -> DirectorBeatAliasV1:
        """服务器骨架也不能携带倒序或零时长节拍。"""

        if self.endSecond <= self.startSecond:
            raise ValueError("导演草案节拍结束时间必须晚于开始时间")
        return self


class DirectorSourceEventAliasV1(VideoContractModel):
    """服务器从冻结原文提取的事件族短别名；标签只来自静态白名单。"""

    alias: str = Field(pattern=r"^E[0-9]{2}$")
    ordinal: int = Field(ge=1, le=99)
    family: SourceEventFamily
    label: str = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_static_label(self) -> DirectorSourceEventAliasV1:
        """禁止调用方把原句或自由文本伪装成安全事件标签。"""

        if self.label != source_event_family_label(self.family):
            raise ValueError("原文事件别名必须使用服务器静态标签")
        return self


class VideoDirectorDraftSkeletonV1(VideoContractModel):
    """由服务器生成、供三阶段共享的冻结别名骨架。"""

    sourceAliases: list[DirectorSourceAliasV1]
    assetAliases: list[DirectorAssetAliasV1]
    beatAliases: list[DirectorBeatAliasV1] = Field(min_length=1, max_length=5)
    sourceEventAliases: list[DirectorSourceEventAliasV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_aliases(self) -> VideoDirectorDraftSkeletonV1:
        """所有短别名和顺序号都必须唯一且连续。"""

        for label, aliases in (
            ("设定", [item.alias for item in self.sourceAliases]),
            ("素材", [item.alias for item in self.assetAliases]),
            ("节拍", [item.alias for item in self.beatAliases]),
            ("原文事件", [item.alias for item in self.sourceEventAliases]),
        ):
            if len(aliases) != len(set(aliases)):
                raise ValueError(f"导演草案骨架包含重复{label}别名")
        if [item.ordinal for item in self.assetAliases] != list(
            range(1, len(self.assetAliases) + 1)
        ):
            raise ValueError("导演草案素材顺序号必须从1连续递增")
        if [item.ordinal for item in self.beatAliases] != list(range(1, len(self.beatAliases) + 1)):
            raise ValueError("导演草案节拍顺序号必须从1连续递增")
        if [item.ordinal for item in self.sourceEventAliases] != list(
            range(1, len(self.sourceEventAliases) + 1)
        ):
            raise ValueError("导演草案原文事件顺序号必须从1连续递增")
        return self


class SceneAssetDraftItemV1(VideoContractModel):
    """模型提交的单项素材创意；身份、媒介与正式 ID 由服务器派生。"""

    sourceAlias: Annotated[str, StringConstraints(min_length=1, max_length=8)] | None
    duty: PlannerAssetDuty
    targetEntity: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None
    includeFeatures: list[str] = Field(min_length=1, max_length=12)
    excludeFeatures: list[str] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_source_choice(self) -> SceneAssetDraftItemV1:
        """冻结设定别名与场景直绑名称必须二选一。"""

        if self.sourceAlias is None and self.targetEntity is None:
            raise ValueError("场景直绑素材必须填写 targetEntity")
        if self.sourceAlias is not None and self.targetEntity is not None:
            raise ValueError("冻结设定素材不能同时填写 targetEntity")
        return self


class SceneAssetsDraftV1(VideoContractModel):
    """Responses JSON Schema 第一阶段只承载场景与素材创意。"""

    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=240)
    dramaticArc: str = Field(min_length=1, max_length=240)
    visualStyle: str = Field(min_length=1, max_length=240)
    globalDirection: str = Field(min_length=1, max_length=240)
    assets: list[SceneAssetDraftItemV1] = Field(min_length=1, max_length=11)
    negativeConstraints: list[str] = Field(min_length=1, max_length=18)


class StoryBeatDraftItemV1(VideoContractModel):
    """历史 v1 单拍草案；素材引用仍分散在每拍数组中，仅保留读取兼容。"""

    beatAlias: str
    dramaticPurpose: str = Field(min_length=1, max_length=160)
    performanceDirection: str = Field(min_length=1, max_length=200)
    blocking: str = Field(min_length=1, max_length=200)
    actions: list[CameraActionUnit] = Field(min_length=1, max_length=2)
    actionComplexity: DirectorActionComplexity
    sound: str = Field(min_length=1, max_length=240)
    assetAliases: list[str] = Field(max_length=11)


class StoryBeatsDraftV1(VideoContractModel):
    """历史 Responses v1 故事草案；新任务必须改用 v2。"""

    beats: list[StoryBeatDraftItemV1] = Field(min_length=1, max_length=5)


class StoryBeatDraftItemV2(VideoContractModel):
    """v2 单拍叙事创意；素材覆盖改由顶层动态对象统一表达。"""

    beatAlias: str
    dramaticPurpose: str = Field(min_length=1, max_length=160)
    performanceDirection: str = Field(min_length=1, max_length=200)
    blocking: str = Field(min_length=1, max_length=200)
    # 使用固定主/次动作槽，避免 Responses wire 投影移除 maxItems 后供应商扩写数组。
    primaryAction: CameraActionUnit
    secondaryAction: CameraActionUnit | None
    actionComplexity: DirectorActionComplexity
    sound: str = Field(min_length=1, max_length=240)


class StoryAssetUsageDraftV2(VideoContractModel):
    """模型为一项既有素材选择至少一个故事节拍，服务器再反向生成逐拍引用。"""

    primaryBeatAlias: str
    additionalBeatAliases: list[str] = Field(max_length=4)
    # 只有 initial_state 关键帧填写；普通素材必须显式填写 null。
    anchorAssetAlias: str | None


class StoryBeatsDraftV2(VideoContractModel):
    """Responses v2 故事草案，以素材为中心确保所有 A 别名都有使用拍点。"""

    beats: list[StoryBeatDraftItemV2] = Field(min_length=1, max_length=5)
    assetUsageByAlias: dict[str, StoryAssetUsageDraftV2] = Field(
        min_length=1,
        max_length=11,
    )


class StoryBeatDraftItemV3(StoryBeatDraftItemV2):
    """v3 单拍在动作旁保存原文事件首次发生归属，避免自由文本顺序误判。"""

    # 单个动作槽内只表达成员关系；服务器按冻结 E 顺序确定性排序。
    primarySourceEventAliases: list[str] = Field(max_length=8)
    secondarySourceEventAliases: list[str] = Field(max_length=8)


class StoryBeatsDraftV3(VideoContractModel):
    """Responses v3 故事草案，同时闭合素材使用与原文事件归属。"""

    beats: list[StoryBeatDraftItemV3] = Field(min_length=1, max_length=5)
    assetUsageByAlias: dict[str, StoryAssetUsageDraftV2] = Field(
        min_length=1,
        max_length=11,
    )


class StoryBeatDraftItemV4(VideoContractModel):
    """v4 单拍只提交故事创意；B 身份与 E 事件槽都由服务器对象键决定。"""

    dramaticPurpose: str = Field(min_length=1, max_length=160)
    performanceDirection: str = Field(min_length=1, max_length=200)
    blocking: str = Field(min_length=1, max_length=200)
    primaryAction: CameraActionUnit
    secondaryAction: CameraActionUnit | None
    actionComplexity: DirectorActionComplexity
    sound: str = Field(min_length=1, max_length=240)


class StoryBeatsDraftV4(VideoContractModel):
    """Responses v4 使用闭合 B 对象，模型不能再移动或伪造 E 事件归属。"""

    beatsByAlias: dict[str, StoryBeatDraftItemV4] = Field(min_length=1, max_length=5)
    assetUsageByAlias: dict[str, StoryAssetUsageDraftV2] = Field(
        min_length=1,
        max_length=11,
    )


class CinematographyBeatDraftItemV1(VideoContractModel):
    """模型提交的单拍摄影事实；兼容文字镜像与节拍身份由服务器派生。"""

    beatAlias: str
    cameraSpec: ShotCameraSpec
    # null 明确表示继承上一拍，不再让模型填写 __INHERIT__ 哨兵。
    lightingCue: ShotLightingCue | None
    cameraMotivation: str = Field(min_length=1, max_length=240)
    axisTransition: AxisTransition
    shotProgression: CameraShotProgression
    # null 明确表示无转场，不再让模型填写 __UNUSED__ 哨兵。
    transition: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None

    @model_validator(mode="after")
    def validate_natural_inheritance(self) -> CinematographyBeatDraftItemV1:
        """非空灯光对象不能再表达继承，继承只使用自然 null。"""

        if self.lightingCue is not None and self.lightingCue.continuityMode == "inherit":
            raise ValueError("摄影草案的灯光继承必须使用 null")
        return self


class CinematographyDraftV1(VideoContractModel):
    """Responses JSON Schema 第三阶段只承载摄影、灯光与转场事实。"""

    cinematographyBase: CinematographyBase
    lightingSetup: LightingSetup
    beats: list[CinematographyBeatDraftItemV1] = Field(min_length=1, max_length=5)


class CinematographyDraftV2(VideoContractModel):
    """按服务器既有 B 别名闭合的摄影草案，允许每拍使用不同灯光约束。"""

    cinematographyBase: CinematographyBase
    lightingSetup: LightingSetup
    beatsByAlias: dict[str, CinematographyBeatDraftItemV1] = Field(
        min_length=1,
        max_length=5,
    )


def source_event_aliases_for_text(source_text: str) -> list[DirectorSourceEventAliasV1]:
    """从冻结原文生成连续 E 别名；不把原句或实体复制到结构化上下文。"""

    return [
        DirectorSourceEventAliasV1(
            alias=f"E{index:02d}",
            ordinal=index,
            family=family,
            label=source_event_family_label(family),
        )
        for index, family in enumerate(source_event_family_sequence(source_text), start=1)
    ]


def distribute_source_event_aliases(
    source_events: Sequence[DirectorSourceEventAliasV1],
    beat_aliases: Sequence[DirectorBeatAliasV1],
) -> dict[str, list[list[str]]]:
    """把连续 E 事件确定性分配给固定 B 拍的主次动作槽。"""

    if not beat_aliases:
        raise ValueError("原文事件归属至少需要一个固定故事拍")
    events_by_beat: list[list[DirectorSourceEventAliasV1]] = [
        [] for _beat in beat_aliases
    ]
    if len(source_events) >= len(beat_aliases):
        base, extra = divmod(len(source_events), len(beat_aliases))
        cursor = 0
        for index in range(len(beat_aliases)):
            size = base + (1 if index < extra else 0)
            events_by_beat[index] = list(source_events[cursor : cursor + size])
            cursor += size
    else:
        for index, event in enumerate(source_events):
            events_by_beat[index] = [event]

    schedule: dict[str, list[list[str]]] = {}
    for beat, beat_events in zip(beat_aliases, events_by_beat, strict=True):
        capacity = _planner_action_capacity(beat.startSecond, beat.endSecond)
        if capacity == 1 or len(beat_events) <= 1:
            primary_events = beat_events
            secondary_events: list[DirectorSourceEventAliasV1] = []
        else:
            split_at = ceil(len(beat_events) / 2)
            primary_events = beat_events[:split_at]
            secondary_events = beat_events[split_at:]
        slots = [[event.alias for event in primary_events]]
        if capacity == 2:
            slots.append([event.alias for event in secondary_events])
        schedule[beat.alias] = slots
    return schedule


def validate_source_event_sequence(
    source_text: str,
    beats: Sequence[StoryBeatPlanArguments],
    *,
    require_structured: bool,
) -> None:
    """复核原文高信号事件覆盖与顺序；新检查点只接受结构化 E 归属。"""

    expected = source_event_aliases_for_text(source_text)
    expected_aliases = [event.alias for event in expected]
    expected_by_alias = {event.alias: event for event in expected}
    required_order = " -> ".join(event.label for event in expected)
    if require_structured:
        assigned: list[tuple[str, CameraActionUnit]] = []
        for beat in beats:
            if len(beat.sourceEventAliasesByAction) != len(beat.actionUnits):
                raise ValueError(
                    "VIDEO_PLAN_SOURCE_EVENT_ASSIGNMENT_INVALID：每个动作槽都必须提交原文事件"
                    "归属数组"
                )
            for unit, aliases in zip(
                beat.actionUnits,
                beat.sourceEventAliasesByAction,
                strict=True,
            ):
                # 同一动作槽可以同时承载“动作 -> 可见结果”中的连续事件；这里的
                # JSON 数组只表示成员关系，按冻结序号排序后再与跨槽顺序比较。
                ordered_aliases = sorted(
                    aliases,
                    key=lambda alias: int(alias[1:]),
                )
                assigned.extend((alias, unit) for alias in ordered_aliases)
        actual_aliases = [alias for alias, _unit in assigned]
        if any(alias not in expected_by_alias for alias in actual_aliases):
            raise ValueError(
                "VIDEO_PLAN_SOURCE_EVENT_ASSIGNMENT_INVALID：原文事件归属包含未知 E 别名"
            )
        duplicated_aliases = sorted(
            {
                alias
                for alias in actual_aliases
                if actual_aliases.count(alias) > 1
            },
            key=lambda alias: int(alias[1:]),
        )
        if duplicated_aliases:
            duplicates = "、".join(duplicated_aliases)
            expected_sequence = " -> ".join(expected_aliases)
            actual_sequence = " -> ".join(actual_aliases)
            raise ValueError(
                "VIDEO_PLAN_SOURCE_EVENT_DUPLICATED：每个原文事件只能归属一次；"
                f"重复 {duplicates}；期望 {expected_sequence}；实际 {actual_sequence}"
            )
        if any(alias not in actual_aliases for alias in expected_aliases):
            raise ValueError(
                "VIDEO_PLAN_REQUIRED_SOURCE_EVENT_MISSING：动作单元必须覆盖冻结原文的高信号"
                f"机关事件；本场事件族顺序为 {required_order}"
            )
        if actual_aliases != expected_aliases:
            expected_sequence = " -> ".join(expected_aliases)
            actual_sequence = " -> ".join(actual_aliases) or "（空）"
            raise ValueError(
                "VIDEO_PLAN_SOURCE_EVENT_ORDER_INVALID：原文事件归属必须按拍次和主次动作槽"
                f"严格递增；期望 {expected_sequence}；实际 {actual_sequence}；"
                f"本场事件族顺序为 {required_order}"
            )
        for alias, unit in assigned:
            event = expected_by_alias[alias]
            if not action_unit_affirms_source_event(unit, event.family):
                raise ValueError(
                    "VIDEO_PLAN_SOURCE_EVENT_GROUNDING_INVALID："
                    f"{alias}（{event.label}）必须在对应动作或可见结果中明确发生；"
                    f"本场事件族顺序为 {required_order}"
                )
        return

    # 历史 1.0 检查点只保留自然语言；继续使用旧兼容门禁，但不能冒充 2.0 结构证明。
    if len(expected) < 2:
        return
    submitted_actions = "；".join(render_action_units(beat.actionUnits) for beat in beats)
    submitted_positions: dict[SourceEventFamily, int] = {}
    normalized = submitted_actions.casefold()
    for family, markers in _SOURCE_EVENT_FAMILIES:
        matches = [normalized.find(marker) for marker in markers if marker in normalized]
        if matches:
            submitted_positions[family] = min(matches)
    required_families = [event.family for event in expected]
    if any(family not in submitted_positions for family in required_families):
        raise ValueError(
            "VIDEO_PLAN_REQUIRED_SOURCE_EVENT_MISSING：动作单元必须覆盖冻结原文的高信号"
            f"机关事件；本场事件族顺序为 {required_order}"
        )
    positions = [submitted_positions[family] for family in required_families]
    if positions != sorted(positions):
        raise ValueError(
            "VIDEO_PLAN_SOURCE_EVENT_ORDER_INVALID：动作单元必须按冻结原文顺序提交，"
            "同拍 primaryAction 先于 secondaryAction；"
            f"本场事件族顺序为 {required_order}"
        )


class PlannerToolEnvelopeV2(VideoContractModel):
    """DeepSeek strict 工具的固定节拍与有界数组原始包络。

    节拍键集合由任务时长决定，素材和负约束数量由本地归一化器裁决；
    ``normalize_strict_tool_arguments`` 会按生成该 schema 的同一输入完成确定性校验与投影。
    """

    title: str
    summary: str
    dramaticArc: str
    visualStyle: str
    globalDirection: str
    cinematographyBase: dict[str, JsonValue]
    lightingSetup: dict[str, JsonValue]
    assets: dict[str, JsonValue]
    beats: dict[str, JsonValue]
    negativeConstraints: dict[str, JsonValue]


class AssetBinding(PlannedAsset):
    """编译阶段的素材绑定；fixture 明确表示它仍是待补齐素材。"""

    # assetId 始终是稳定槽位 ID；真实媒体 ID 独立保存，不能破坏镜头引用。
    mediaAssetId: str | None = None
    isFixture: bool = True

    @model_validator(mode="after")
    def validate_materialization(self) -> AssetBinding:
        """fixture 与真实媒体 ID 必须保持互斥且完整。"""

        if self.isFixture and self.mediaAssetId is not None:
            raise ValueError("fixture 素材不能携带真实媒体 ID")
        if not self.isFixture and self.mediaAssetId is None:
            raise ValueError("非 fixture 素材必须携带真实媒体 ID")
        return self


class SeedanceOutputSpec(VideoContractModel):
    """当前已由火山方舟公开文档确认的 Seedance 2.5 输出参数。"""

    model: Literal["doubao-seedance-2-5-260628"] = "doubao-seedance-2-5-260628"
    resolution: Resolution = "720p"
    ratio: AspectRatio = "16:9"
    durationSeconds: int = Field(ge=4, le=30)
    generateAudio: bool = True
    outputFormat: OutputFormat = "mp4"
    watermark: bool = False


class ScenePromptSpec(VideoContractModel):
    """确定性编译器接受的完整场景规范。"""

    schemaVersion: Literal["1.0", "1.1", "1.2", "1.3"] = "1.0"
    sceneId: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1)
    # 历史场景没有戏剧弧字段；仅 1.3 将其作为可执行导演事实强制要求。
    dramaticArc: str | None = Field(default=None, min_length=1, max_length=500)
    visualStyle: str = Field(min_length=1)
    globalDirection: str = Field(min_length=1)
    cinematographyBase: CinematographyBase | None = None
    lightingSetup: LightingSetup | None = None
    assets: list[AssetBinding] = Field(min_length=1, max_length=50)
    beats: list[CameraBeatSpec] = Field(min_length=1, max_length=12)
    negativeConstraints: list[str] = Field(min_length=1, max_length=20)
    output: SeedanceOutputSpec

    @model_validator(mode="after")
    def validate_scene(self) -> ScenePromptSpec:
        """一次性校验素材引用、镜头连续性和输出时长。"""

        asset_ids = [asset.assetId for asset in self.assets]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("素材 assetId 不能重复")

        known_assets = set(asset_ids)
        previous_end = 0
        beat_ids: set[str] = set()
        for beat in self.beats:
            if beat.beatId in beat_ids:
                raise ValueError("镜头 beatId 不能重复")
            beat_ids.add(beat.beatId)
            if beat.startSecond != previous_end:
                raise ValueError("镜头时间轴必须从 0 秒开始并保持连续")
            unknown_assets = set(beat.referencedAssetIds) - known_assets
            if unknown_assets:
                names = "、".join(sorted(unknown_assets))
                raise ValueError(f"镜头引用了未声明素材：{names}")
            previous_end = beat.endSecond

        if previous_end != self.output.durationSeconds:
            raise ValueError("镜头时间轴终点必须等于输出时长")
        if self.schemaVersion in {"1.1", "1.2", "1.3"}:
            self._validate_director_semantics()
        if self.schemaVersion in {"1.2", "1.3"}:
            self._validate_cinematography_and_lighting()
        if self.schemaVersion == "1.3":
            self._validate_director_language_and_axis()
        return self

    def _validate_director_semantics(self) -> None:
        """校验新导演语义版本的原子素材、动作、镜头和声音门禁。"""

        assets_by_id = {asset.assetId: asset for asset in self.assets}
        for asset in self.assets:
            if asset.featureDomain is None:
                raise ValueError("1.1 场景的每个素材都必须声明 featureDomain")
            if asset.duty == "keyframe" and asset.keyframeRole is None:
                raise ValueError("1.1 场景的 keyframe 素材必须声明 keyframeRole")

        has_seen_irreversible_mechanical_action = False
        for beat in self.beats:
            if not beat.actionUnits:
                raise ValueError("1.1 场景的每个镜头必须声明 actionUnits")
            if beat.actionComplexity == "legacy_unclassified":
                raise ValueError("1.1 场景不能使用 legacy_unclassified 动作复杂度")
            if beat.shotProgression is None:
                raise ValueError("1.1 场景的每个镜头必须声明 shotProgression")
            if beat.action != render_action_units(beat.actionUnits):
                raise ValueError("action 必须是 actionUnits 的确定性可读镜像")

            duration = beat.endSecond - beat.startSecond
            max_action_units = min(3, ceil(duration / 2))
            if len(beat.actionUnits) > max_action_units:
                raise ValueError(f"镜头 {beat.beatId} 的动作数量超过 {duration} 秒可执行上限")

            progression = beat.shotProgression
            scale_delta = abs(
                _SHOT_SIZE_RANK[progression.endShotSize]
                - _SHOT_SIZE_RANK[progression.startShotSize]
            )
            movement = beat.cameraMovement.lower()
            if progression.changeMode == "continuous" and scale_delta >= 3 and duration < 6:
                raise ValueError("短镜头不能连续跨越三个以上景别尺度")
            if (
                progression.changeMode == "continuous"
                and scale_delta >= 2
                and duration < 5
                and ("缓慢" in movement or "slow" in movement)
            ):
                raise ValueError("短镜头不能以缓慢连续运镜跨越多个景别尺度")

            is_irreversible_mechanical_action = is_irreversible_mechanical_beat(
                beat.actionComplexity,
                beat.actionUnits,
            )
            starts_initial_mechanical_sequence = (
                is_irreversible_mechanical_action
                and not has_seen_irreversible_mechanical_action
            )
            if starts_initial_mechanical_sequence:
                initial_keyframes = [
                    assets_by_id[asset_id]
                    for asset_id in beat.referencedAssetIds
                    if assets_by_id[asset_id].duty == "keyframe"
                    and assets_by_id[asset_id].bindingScope == "scene_direct"
                    and assets_by_id[asset_id].modality == "image"
                    and assets_by_id[asset_id].keyframeRole == "initial_state"
                ]
                if not initial_keyframes:
                    raise ValueError(
                        "全场首个不可逆机关动作必须引用 initial_state 关键帧"
                    )

            if self.output.generateAudio and not (beat.sound and beat.sound.strip()):
                raise ValueError("开启生成音频时每个镜头都必须声明同步声音")
            has_seen_irreversible_mechanical_action = (
                has_seen_irreversible_mechanical_action
                or is_irreversible_mechanical_action
            )

    def _validate_cinematography_and_lighting(self) -> None:
        """校验 1.2 起的逐拍摄影可达性与有动机灯光连续性。"""

        if self.cinematographyBase is None or self.lightingSetup is None:
            raise ValueError("1.2 场景必须声明 cinematographyBase 与 lightingSetup")

        previous_cue: ShotLightingCue | None = None
        speed_limit_meters_per_second = {
            "very_slow": 0.15,
            "slow": 0.5,
            "medium": 1.2,
            "fast": 2.5,
        }
        for index, beat in enumerate(self.beats):
            if beat.cameraSpec is None or beat.lightingCue is None:
                raise ValueError("1.2 场景的每个镜头必须声明 cameraSpec 与 lightingCue")

            duration = beat.endSecond - beat.startSecond
            camera = beat.cameraSpec
            focus = camera.focus
            if focus.rackDurationSeconds > duration:
                raise ValueError(f"镜头 {beat.beatId} 的拉焦时长不能超过镜头时长")

            movement = camera.movement
            if movement.speed != "static":
                max_distance = duration * speed_limit_meters_per_second[movement.speed]
                if movement.travelDistanceMeters > max_distance:
                    raise ValueError(
                        f"镜头 {beat.beatId} 的机位位移超过 {duration} 秒和当前速度可达范围"
                    )

            cue = beat.lightingCue
            if index == 0 and cue.continuityMode != "establish":
                raise ValueError("首个镜头必须以 establish 建立灯光")
            if index > 0 and cue.continuityMode == "establish":
                raise ValueError("只有首个镜头可以使用 establish 灯光模式")
            if cue.continuityMode == "inherit":
                if previous_cue is None:
                    raise ValueError("inherit 灯光必须存在上一拍")
                current_facts = cue.model_dump(exclude={"continuityMode", "motivatedChange"})
                previous_facts = previous_cue.model_dump(
                    exclude={"continuityMode", "motivatedChange"}
                )
                if current_facts != previous_facts:
                    raise ValueError("inherit 灯光不得静默改变光位、色温、光比或氛围")
            if cue.continuityMode == "motivated_change" and cue.motivatedChange in {
                "延续上一拍",
                "无",
                "没有",
            }:
                raise ValueError("灯光变化必须说明画面内可见的动机事件")
            previous_cue = cue

    def _validate_director_language_and_axis(self) -> None:
        """校验 1.3 的戏剧意图、表演调度、白平衡和轴线转换。"""

        if self.dramaticArc is None or not self.dramaticArc.strip():
            raise ValueError("1.3 场景必须声明 dramaticArc")
        if self.cinematographyBase is None or self.lightingSetup is None:
            # 正常情况下已由 1.2 门禁拒绝；保留本地窄化以便静态检查和单独调用。
            raise ValueError("1.3 场景必须声明 cinematographyBase 与 lightingSetup")
        if self.lightingSetup.cameraWhiteBalanceK is None:
            raise ValueError("1.3 场景必须声明 cameraWhiteBalanceK")

        for beat in self.beats:
            director_fields = {
                "dramaticPurpose": beat.dramaticPurpose,
                "performanceDirection": beat.performanceDirection,
                "blocking": beat.blocking,
                "cameraMotivation": beat.cameraMotivation,
            }
            for field_name, value in director_fields.items():
                if value is None or not value.strip():
                    raise ValueError(f"1.3 场景的每个镜头必须声明 {field_name}")
            if beat.axisTransition is None:
                raise ValueError("1.3 场景的每个镜头必须声明 axisTransition")

        character_asset_ids = {
            asset.assetId
            for asset in self.assets
            if asset.duty in {"identity", "costume", "voice"}
        }
        has_referenced_character = any(
            character_asset_ids.intersection(beat.referencedAssetIds) for beat in self.beats
        )
        if has_referenced_character and any(
            bans_required_character_performance(item) for item in self.negativeConstraints
        ):
            raise ValueError(
                "1.3 场景的全局负向约束不能禁止镜头已明确要求的人物表演"
            )

        first_transition = self.beats[0].axisTransition
        if first_transition != "hold":
            raise ValueError("1.3 场景首拍的 axisTransition 必须是 hold")

        axis_rule = self.cinematographyBase.axisRule
        if axis_rule == "maintain_180":
            self._validate_maintained_axis()
        elif axis_rule == "intentional_cross":
            self._validate_intentional_axis_crosses()
        else:
            self._validate_not_applicable_axis()

    def _validate_not_applicable_axis(self) -> None:
        """无人物轴线可管理时，拒绝伪造越轴或重置事件。"""

        if any(beat.axisTransition != "hold" for beat in self.beats):
            raise ValueError("axisRule 为 not_applicable 时每拍 axisTransition 必须是 hold")

    def _validate_maintained_axis(self) -> None:
        """维持 180 度规则时，不允许转换标记或在左右轴线侧之间跳切。"""

        non_axis_side: CameraAxisSide | None = None
        for beat in self.beats:
            if beat.axisTransition != "hold":
                raise ValueError("maintain_180 只允许 hold 轴线状态")
            camera = beat.cameraSpec
            if camera is None:
                raise ValueError("1.3 场景的每个镜头必须声明 cameraSpec")
            current_side = camera.position.axisSide
            if current_side == "on_axis":
                continue
            if non_axis_side is None:
                non_axis_side = current_side
            elif current_side != non_axis_side:
                raise ValueError("maintain_180 的所有非 on_axis 镜头必须保持同一轴线侧")

    def _validate_intentional_axis_crosses(self) -> None:
        """有意越轴必须留下连续越轴、正轴重置或插入镜头重置的可审核证据。"""

        previous_non_axis_side: CameraAxisSide | None = None
        reset_pending = False
        for beat in self.beats:
            camera = beat.cameraSpec
            progression = beat.shotProgression
            if camera is None or progression is None or beat.axisTransition is None:
                raise ValueError("1.3 场景的每个镜头必须声明完整摄影与轴线事实")

            transition = beat.axisTransition
            if transition == "continuous_cross" and (
                progression.changeMode != "continuous"
                or camera.movement.movementType == "locked_off"
            ):
                raise ValueError(
                    "continuous_cross 必须使用 continuous 镜头且主运镜不能是 locked_off"
                )
            if transition == "neutral_reset" and camera.position.axisSide != "on_axis":
                raise ValueError("neutral_reset 镜头必须位于 on_axis")
            if transition in {"neutral_reset", "cutaway_reset"}:
                reset_pending = True

            current_side = camera.position.axisSide
            # 插入镜头不建立人物轴线侧；下一支主体镜头才消费这次重置。
            if current_side == "on_axis" or transition == "cutaway_reset":
                continue
            if previous_non_axis_side is not None and current_side != previous_non_axis_side:
                if transition != "continuous_cross" and not reset_pending:
                    raise ValueError(
                        "intentional_cross 的左右轴线侧变化必须使用 "
                        "continuous_cross、neutral_reset 或 cutaway_reset"
                    )
            previous_non_axis_side = current_side
            reset_pending = False


class CompiledAssetBinding(VideoContractModel):
    """本次供应商请求中的局部素材编号映射。"""

    assetId: str
    mediaAssetId: str | None
    alias: str
    modality: AssetModality
    duty: PlannedAssetDuty
    bindingScope: AssetBindingScope
    settingReference: SettingReference | None
    featureDomain: AssetFeatureDomain | None = None
    keyframeRole: KeyframeRole | None = None
    targetEntity: str
    isFixture: bool


class SeedancePromptPackage(VideoContractModel):
    """可展示、可审核，并区分官方建议长度与产品安全上限。"""

    schemaVersion: Literal["1.0"] = "1.0"
    sceneId: str
    prompt: str
    promptCharacterCount: int = Field(ge=1, le=6_000)
    # 500 字符是方舟 API 的提示词质量建议，不代表供应商传输硬上限。
    recommendedPromptCharacters: int = Field(default=500, ge=1, le=6_000)
    # 新版编译以 2000 字符作为产品异常包络；字段上限保留 6000 以读取历史包。
    maxPromptCharacters: int = Field(default=2_000, ge=1, le=6_000)
    compileProfile: PromptCompileProfile = "legacy_single_prompt_v1"
    providerPrompt: str | None = None
    providerPromptCharacterCount: int | None = Field(default=None, ge=1, le=6_000)
    manifestPrompt: str | None = None
    manifestPromptCharacterCount: int | None = Field(default=None, ge=1)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    assetBindings: list[CompiledAssetBinding]
    output: SeedanceOutputSpec
    previewOnly: bool
    assetReady: bool
    submissionReady: bool
    fixtureOnly: bool

    @model_validator(mode="after")
    def validate_readiness(self) -> SeedancePromptPackage:
        """包状态必须由素材事实与预览边界唯一决定。"""

        expected_asset_ready = all(
            not binding.isFixture and binding.mediaAssetId is not None
            for binding in self.assetBindings
        )
        expected_fixture_only = all(
            binding.isFixture and binding.mediaAssetId is None for binding in self.assetBindings
        )
        if self.assetReady != expected_asset_ready:
            raise ValueError("assetReady 与编译素材事实不一致")
        if self.fixtureOnly != expected_fixture_only:
            raise ValueError("fixtureOnly 与编译素材事实不一致")
        if self.previewOnly and self.submissionReady:
            raise ValueError("预览包不能标记为可提交")
        if self.submissionReady != (self.assetReady and not self.previewOnly):
            raise ValueError("submissionReady 与预览及素材状态不一致")
        if self.compileProfile == "legacy_single_prompt_v1":
            if any(
                value is not None
                for value in (
                    self.providerPrompt,
                    self.providerPromptCharacterCount,
                    self.manifestPrompt,
                    self.manifestPromptCharacterCount,
                )
            ):
                raise ValueError("旧版合并提示词不能携带部分双层提示词字段")
            return self

        if (
            self.providerPrompt is None
            or self.providerPromptCharacterCount is None
            or self.manifestPrompt is None
            or self.manifestPromptCharacterCount is None
        ):
            raise ValueError("双层提示词包必须同时携带 Provider 与 Manifest 提示词")
        if self.prompt != self.providerPrompt:
            raise ValueError("prompt 必须逐字镜像 providerPrompt")
        if self.promptCharacterCount != self.providerPromptCharacterCount:
            raise ValueError("promptCharacterCount 必须镜像 Provider 提示词字数")
        if self.providerPromptCharacterCount != len(self.providerPrompt):
            raise ValueError("providerPromptCharacterCount 与 Provider 提示词不一致")
        if self.manifestPromptCharacterCount != len(self.manifestPrompt):
            raise ValueError("manifestPromptCharacterCount 与 Manifest 提示词不一致")
        if self.providerPromptCharacterCount > 6_000:
            raise ValueError("Provider 提示词不能超过 6000 字")
        if self.maxPromptCharacters > 6_000:
            raise ValueError("双层提示词包的 Provider 安全包络不能超过 6000 字")
        if self.providerPromptCharacterCount > self.maxPromptCharacters:
            raise ValueError("Provider 提示词超过当前编译包声明的安全包络")
        return self


class VideoPlanJobPayload(VideoContractModel):
    """Core 放入队列的最小视频规划任务载荷。"""

    projectId: str = Field(min_length=1)
    sceneId: str = Field(min_length=1)
    chapterId: str | None
    title: str = Field(min_length=1, max_length=120)
    sourceText: str = Field(min_length=1, max_length=2_000)
    revisionInstruction: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
        ]
        | None
    ) = None
    # 返工必须冻结当前待审方案，Agent 仅按阶段投影创意事实，不向模型暴露正式 ID。
    revisionBaseline: ScenePromptSpec | None = None
    durationSeconds: int = Field(ge=4, le=15)
    ratio: AspectRatio
    settingSnapshot: LongSerialSettingSnapshot
    # 缺少路由字段的历史载荷来自旧 strict 链，必须按 legacy 读取；只有 Core 新建的新任务
    # 才能显式写入 Responses，避免同一 active task 在部署后静默切换传输协议。
    planningRoute: VideoPlanningRoute = "legacy_strict_tool_v1"
    planningModel: VideoPlanningModel = "deepseek-v4-flash"
    directorDraftVersion: DirectorDraftVersion = "1.0"

    @model_validator(mode="after")
    def validate_revision_baseline(self) -> VideoPlanJobPayload:
        """返工基线必须与当前冻结场景、时长和画幅完全一致。"""

        baseline = self.revisionBaseline
        if baseline is None:
            return self
        if self.revisionInstruction is None:
            raise ValueError("只有返工任务可以携带 revisionBaseline")
        if (
            baseline.sceneId != self.sceneId
            or baseline.output.durationSeconds != self.durationSeconds
            or baseline.output.ratio != self.ratio
        ):
            raise ValueError("revisionBaseline 与当前冻结场景、时长或画幅不一致")
        return self


def calculate_video_plan_input_fingerprint(payload: VideoPlanJobPayload) -> str:
    """为完整冻结规划输入计算可跨服务复核的规范指纹。"""

    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def calculate_video_plan_business_input_fingerprint(payload: VideoPlanJobPayload) -> str:
    """计算可跨模型路由和草案协议升级复用 canonical checkpoint 的业务指纹。"""

    canonical = json.dumps(
        payload.model_dump(
            mode="json",
            exclude={"planningRoute", "planningModel", "directorDraftVersion"},
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class VideoPlanCompletionCallback(VideoContractModel):
    """Agent 将严格结构与编译结果回传 Core 的成功契约。"""

    protocolVersion: Literal["1.0"]
    eventId: str = Field(min_length=1)
    jobId: str = Field(min_length=1)
    runId: str = Field(min_length=1)
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    sceneId: str = Field(min_length=1)
    scenePlan: ScenePromptSpec
    promptPackage: SeedancePromptPackage


class VideoPlanFailureCallback(VideoContractModel):
    """Agent 将稳定错误码回传 Core 的失败契约。"""

    protocolVersion: Literal["1.0"]
    eventId: str = Field(min_length=1)
    jobId: str = Field(min_length=1)
    runId: str = Field(min_length=1)
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    sceneId: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1)
    recoverable: bool


class VideoPlanProgressQuery(VideoContractModel):
    """Agent 在 at-least-once 重放前查询视频规划耐久进度。"""

    protocolVersion: Literal["1.0"]
    jobId: str = Field(min_length=1)
    runId: str = Field(min_length=1)
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    sceneId: str = Field(min_length=1)


class VideoPlanAttemptState(VideoContractModel):
    """不依赖新表、随任务结果耐久保存的模型调用预留账本。"""

    reservedCalls: int = Field(ge=0, le=VIDEO_PLAN_MAX_EFFECTIVE_CALLS)
    # 只表示从旧 task canonical checkpoint 继承的已完成阶段，不是本任务预留记录。
    inheritedCalls: int = Field(default=0, ge=0, le=2)
    pendingStage: Literal["scene_assets", "story_beats", "cinematography"] | None

    @model_validator(mode="after")
    def validate_pending_requires_reservation(self) -> VideoPlanAttemptState:
        """零次预留不可能已经存在待确认的供应商调用。"""

        if self.reservedCalls == 0 and self.pendingStage is not None:
            raise ValueError("零次模型调用预留不能携带 pendingStage")
        if self.reservedCalls + self.inheritedCalls > VIDEO_PLAN_MAX_EFFECTIVE_CALLS:
            raise ValueError("当前任务预留与继承调用基线之和不能超过五次")
        return self


class VideoPlanCallReservationRequest(VideoContractModel):
    """Agent 在每次供应商调用前请求 Core 原子预留一次调用。"""

    protocolVersion: Literal["1.0"]
    eventId: str = Field(min_length=1)
    jobId: str = Field(min_length=1)
    runId: str = Field(min_length=1)
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    sceneId: str = Field(min_length=1)
    checkpointStage: Literal["empty", "scene_assets", "story"]
    stage: Literal["scene_assets", "story_beats", "cinematography"]
    expectedReservedCalls: int = Field(ge=0, le=VIDEO_PLAN_MAX_EFFECTIVE_CALLS - 1)
    inheritedCalls: int = Field(default=0, ge=0, le=2)

    @model_validator(mode="after")
    def validate_next_stage(self) -> VideoPlanCallReservationRequest:
        """预留只能指向当前 checkpoint 后唯一尚未完成的阶段。"""

        expected_stage = _next_model_stage(self.checkpointStage)
        if self.stage != expected_stage:
            raise ValueError(f"{self.checkpointStage} 检查点只能预留 {expected_stage} 阶段调用")
        _validate_active_attempt_state(
            checkpoint_stage=self.checkpointStage,
            attempt_state=VideoPlanAttemptState(
                reservedCalls=self.expectedReservedCalls + 1,
                inheritedCalls=self.inheritedCalls,
                pendingStage=self.stage,
            ),
            allow_pending=True,
        )
        return self


class VideoPlanCallReservationResponse(VideoContractModel):
    """Core 完成幂等预留后回显资源绑定与新的耐久账本。"""

    protocolVersion: Literal["1.0"]
    eventId: str = Field(min_length=1)
    jobId: str = Field(min_length=1)
    runId: str = Field(min_length=1)
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    sceneId: str = Field(min_length=1)
    checkpointStage: Literal["empty", "scene_assets", "story"]
    stage: Literal["scene_assets", "story_beats", "cinematography"]
    reservedCallsBefore: int = Field(ge=0, le=VIDEO_PLAN_MAX_EFFECTIVE_CALLS - 1)
    attemptState: VideoPlanAttemptState

    @model_validator(mode="after")
    def validate_reserved_state(self) -> VideoPlanCallReservationResponse:
        """成功回执必须恰好增加一次计数并把目标阶段标为 pending。"""

        expected_stage = _next_model_stage(self.checkpointStage)
        if self.stage != expected_stage:
            raise ValueError(f"{self.checkpointStage} 检查点只能预留 {expected_stage} 阶段调用")
        if self.attemptState.pendingStage != self.stage:
            raise ValueError("模型调用预留响应的 pendingStage 必须等于目标阶段")
        if self.attemptState.reservedCalls != self.reservedCallsBefore + 1:
            raise ValueError("模型调用预留响应必须恰好增加一次 reservedCalls")
        _validate_active_attempt_state(
            checkpoint_stage=self.checkpointStage,
            attempt_state=self.attemptState,
            allow_pending=True,
        )
        return self


class VideoStoryPlanCheckpointCallback(VideoContractModel):
    """任一 active 阶段推进或纠正预算变化的幂等耐久检查点。"""

    protocolVersion: Literal["1.0"]
    eventId: str = Field(min_length=1)
    jobId: str = Field(min_length=1)
    runId: str = Field(min_length=1)
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    sceneId: str = Field(min_length=1)
    checkpointStage: Literal["empty", "scene_assets", "story"]
    sceneAssetsPlan: SceneAssetsStageArguments | None = None
    storyPlan: StoryPlanStageArguments | None = None
    attemptState: VideoPlanAttemptState

    @model_validator(mode="after")
    def validate_checkpoint_stage(self) -> VideoStoryPlanCheckpointCallback:
        """active 检查点的阶段与唯一计划载荷必须严格对应。"""

        _validate_active_checkpoint_payload(
            checkpoint_stage=self.checkpointStage,
            scene_assets_plan=self.sceneAssetsPlan,
            story_plan=self.storyPlan,
        )
        _validate_active_attempt_state(
            checkpoint_stage=self.checkpointStage,
            attempt_state=self.attemptState,
            allow_pending=False,
        )
        return self


class VideoPlanProgressResponse(VideoContractModel):
    """Core 返回的视频规划任务状态与可恢复故事检查点。"""

    protocolVersion: Literal["1.0"]
    jobId: str = Field(min_length=1)
    runId: str = Field(min_length=1)
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    sceneId: str = Field(min_length=1)
    inputFingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["active", "completed", "failed"]
    checkpointStage: Literal["empty", "scene_assets", "story", "terminal"]
    sceneAssetsPlan: SceneAssetsStageArguments | None = None
    storyPlan: StoryPlanStageArguments | None = None
    attemptState: VideoPlanAttemptState

    @model_validator(mode="after")
    def validate_terminal_checkpoint(self) -> VideoPlanProgressResponse:
        """终态不能携带会诱导 Agent 继续生成的阶段检查点。"""

        if self.status == "active":
            if self.checkpointStage == "terminal":
                raise ValueError("active 视频规划进度不能使用 terminal 检查点阶段")
            _validate_active_checkpoint_payload(
                checkpoint_stage=self.checkpointStage,
                scene_assets_plan=self.sceneAssetsPlan,
                story_plan=self.storyPlan,
            )
            _validate_active_attempt_state(
                checkpoint_stage=self.checkpointStage,
                attempt_state=self.attemptState,
                allow_pending=True,
            )
        else:
            if self.checkpointStage != "terminal":
                raise ValueError("已完成或已失败的视频规划进度必须使用 terminal 阶段")
            if self.sceneAssetsPlan is not None or self.storyPlan is not None:
                raise ValueError("已完成或已失败的视频规划进度不能携带阶段计划")
            if self.attemptState.pendingStage is not None:
                raise ValueError("已完成或已失败的视频规划进度不能携带 pendingStage")
        return self


def json_schema_for_scene_assets_strict_tool(
    *,
    setting_snapshot: LongSerialSettingSnapshot,
) -> dict[str, JsonValue]:
    """生成第一阶段“场景元数据与素材”紧凑 strict 工具 schema。"""

    definitions: dict[str, Any] = {
        "AssetSlot": _planner_compact_asset_slot_schema(setting_snapshot),
    }
    asset_properties: dict[str, Any] = {
        "asset01": {
            "$ref": "#/$def/AssetSlot",
            "description": "首个必用素材。",
        },
        "additionalAssets": {
            "type": "array",
            "items": {"$ref": "#/$def/AssetSlot"},
            "description": "其余零至十项素材；上限由本地归一化器校验。",
        },
    }
    schema = _strict_object_schema(
        {
            "title": _strict_text_schema(80, "场景标题。"),
            "summary": _strict_text_schema(240, "单场景事件概述。"),
            "dramaticArc": _strict_text_schema(
                240,
                "用可见状态描述全场起点、转折与落点。",
            ),
            "visualStyle": _strict_text_schema(240, "场景视觉风格。"),
            "globalDirection": _strict_text_schema(240, "全场导演方向。"),
            "assets": _strict_object_schema(
                asset_properties,
                description="一至十一项素材；本阶段不决定逐拍引用。",
            ),
            "negativeConstraints": {
                "type": "array",
                "items": _strict_text_schema(120, "单项负向约束。"),
                "description": "一至十八项负向约束；数量由本地归一化器校验。",
            },
        },
        description="长篇小说单场景元数据与素材规划 V3 第一阶段。",
    )
    schema["$def"] = definitions
    return cast(dict[str, JsonValue], schema)


def json_schema_for_story_beats_strict_tool(
    *,
    scene_assets: SceneAssetsStageArguments,
    beat_ranges: Sequence[tuple[int, int]],
) -> dict[str, JsonValue]:
    """生成第二阶段“故事节拍与逐拍素材引用”紧凑 strict schema。"""

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_keys = _planner_beat_keys(ranges)
    definitions: dict[str, Any] = {
        "ActionUnit": _planner_action_unit_schema(),
    }
    definitions.update(
        _build_planner_compact_story_beat_definitions(
            ranges,
            asset_count=len(scene_assets.assets),
        )
    )
    beat_properties = {
        beat_key: {"$ref": f"#/$def/{_planner_beat_definition_name(index)}"}
        for index, beat_key in enumerate(beat_keys, start=1)
    }
    schema = _strict_object_schema(
        {
            "beats": _strict_object_schema(
                beat_properties,
                description="数量和顺序由任务时间表固定的故事节拍。",
            )
        },
        description="长篇小说单场景故事节拍规划 V3 第二阶段。",
    )
    schema["$def"] = definitions
    return cast(dict[str, JsonValue], schema)


def json_schema_for_story_strict_tool(
    *,
    setting_snapshot: LongSerialSettingSnapshot,
    beat_ranges: Sequence[tuple[int, int]],
) -> dict[str, JsonValue]:
    """生成第一阶段“叙事、调度与素材” strict 工具 schema。

    第一阶段只决定故事事实、演员调度、原子动作、同步声音和素材需求；摄影、
    灯光与转场留给第二阶段，避免单次工具调用同时生成两套高复杂度结构。
    """

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_keys = _planner_beat_keys(ranges)
    definitions: dict[str, Any] = {
        "AssetSlot": _planner_asset_slot_schema(
            setting_snapshot,
            beat_keys=beat_keys,
        ),
        "ActionUnit": _planner_action_unit_schema(),
        "IncludeFeatureSlots": _fixed_text_slots_schema(
            prefix="feature",
            count=_PLANNER_FEATURE_SLOT_COUNT,
            first_required=True,
            max_characters=200,
            description="至少一项采用特征，其余槽位填写 __UNUSED__。",
        ),
        "ExcludeFeatureSlots": _fixed_text_slots_schema(
            prefix="feature",
            count=_PLANNER_FEATURE_SLOT_COUNT,
            first_required=False,
            max_characters=200,
            description="不采用特征；没有内容的槽位填写 __UNUSED__。",
        ),
    }
    definitions.update(_build_planner_story_beat_definitions(ranges))

    asset_properties: dict[str, Any] = {
        "asset01": {
            "$ref": "#/$def/AssetSlot",
            "description": "首个必用素材。",
        },
        "additionalAssets": {
            "type": "array",
            "items": {"$ref": "#/$def/AssetSlot"},
            "description": "其余零至十项素材；上限由本地归一化器校验。",
        },
    }
    beat_properties = {
        beat_key: {"$ref": f"#/$def/{_planner_beat_definition_name(index)}"}
        for index, beat_key in enumerate(beat_keys, start=1)
    }
    negative_constraints = _strict_object_schema(
        {
            "constraint01": _strict_text_schema(500, "首项必填负向约束。"),
            "additionalConstraints": {
                "type": "array",
                "items": _strict_text_schema(500, "追加负向约束。"),
                "description": "其余零至十七项负向约束；上限由本地归一化器校验。",
            },
        },
        description="模型补充的负向约束；服务器另保留两项硬约束容量。",
    )
    schema = _strict_object_schema(
        {
            "title": _strict_text_schema(120, "场景标题。"),
            "summary": _strict_text_schema(500, "单场景事件概述。"),
            "dramaticArc": _strict_text_schema(
                500,
                "用可见节拍描述全场情绪、权力或信息状态的起点、转折与落点。",
            ),
            "visualStyle": _strict_text_schema(500, "场景视觉风格。"),
            "globalDirection": _strict_text_schema(500, "全场导演方向。"),
            "assets": _strict_object_schema(
                asset_properties,
                description="一至十一项模型素材，为服务器派生初始关键帧预留一项。",
            ),
            "beats": _strict_object_schema(
                beat_properties,
                description="数量和顺序由本次任务时长固定的叙事与调度节拍。",
            ),
            "negativeConstraints": negative_constraints,
        },
        description="长篇小说单场景叙事、调度与素材规划 V2 第一阶段。",
    )
    schema["$def"] = definitions
    return cast(dict[str, JsonValue], schema)


def json_schema_for_cinematography_strict_tool(
    *,
    beat_ranges: Sequence[tuple[int, int]],
) -> dict[str, JsonValue]:
    """生成第二阶段“摄影、灯光与转场” strict 工具 schema。"""

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_keys = _planner_beat_keys(ranges)
    definitions: dict[str, Any] = {
        "CinematographyBase": _planner_cinematography_base_schema(),
        "LightingSetup": _planner_lighting_setup_schema(),
        "CameraPosition": _planner_camera_position_schema(),
        "CameraComposition": _planner_camera_composition_schema(),
        "CameraMovement": _planner_camera_movement_schema(),
        "CameraFocus": _planner_camera_focus_schema(),
        "ShotCameraSpec": _planner_shot_camera_schema(),
        "LightSource": _planner_light_source_schema(),
        "EstablishLightingCue": _planner_shot_lighting_cue_schema(continuity_mode="establish"),
        "ShotProgression": _strict_object_schema(
            {
                "startShotSize": {"type": "string", "enum": list(_SHOT_SIZES)},
                "endShotSize": {"type": "string", "enum": list(_SHOT_SIZES)},
                "changeMode": {
                    "type": "string",
                    "enum": list(_SHOT_CHANGE_MODES),
                },
            },
            description="本拍起止景别及变化方式。",
        ),
    }
    definitions.update(_build_planner_cinematography_beat_definitions(ranges))

    beat_properties = {
        beat_key: {"$ref": f"#/$def/{_planner_beat_definition_name(index)}"}
        for index, beat_key in enumerate(beat_keys, start=1)
    }
    schema = _strict_object_schema(
        {
            "cinematographyBase": {"$ref": "#/$def/CinematographyBase"},
            "lightingSetup": {"$ref": "#/$def/LightingSetup"},
            "beats": _strict_object_schema(
                beat_properties,
                description="数量和顺序由本次任务时长固定的摄影、灯光与转场节拍。",
            ),
        },
        description="长篇小说单场景摄影、灯光与转场规划 V2 第二阶段。",
    )
    schema["$def"] = definitions
    return cast(dict[str, JsonValue], schema)


def json_schema_for_strict_tool(
    *,
    setting_snapshot: LongSerialSettingSnapshot,
    beat_ranges: Sequence[tuple[int, int]],
) -> dict[str, JsonValue]:
    """按冻结输入生成 DeepSeek strict 支持子集内的固定槽位 schema。

    DeepSeek strict 不支持数组和字符串的长度关键词。节拍和动作仍使用固定对象槽位；
    可变数量的素材及负向约束使用官方支持的数组，并由本地归一化器裁决上限。
    """

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_keys = _planner_beat_keys(ranges)
    asset_slot_schema = _planner_asset_slot_schema(
        setting_snapshot,
        beat_keys=beat_keys,
    )
    definitions: dict[str, Any] = {
        "AssetSlot": asset_slot_schema,
        "ActionUnit": _planner_action_unit_schema(),
        "CinematographyBase": _planner_cinematography_base_schema(),
        "LightingSetup": _planner_lighting_setup_schema(),
        "CameraPosition": _planner_camera_position_schema(),
        "CameraComposition": _planner_camera_composition_schema(),
        "CameraMovement": _planner_camera_movement_schema(),
        "CameraFocus": _planner_camera_focus_schema(),
        "ShotCameraSpec": _planner_shot_camera_schema(),
        "LightSource": _planner_light_source_schema(),
        "EstablishLightingCue": _planner_shot_lighting_cue_schema(continuity_mode="establish"),
        "ShotProgression": _strict_object_schema(
            {
                "startShotSize": {"type": "string", "enum": list(_SHOT_SIZES)},
                "endShotSize": {"type": "string", "enum": list(_SHOT_SIZES)},
                "changeMode": {
                    "type": "string",
                    "enum": list(_SHOT_CHANGE_MODES),
                },
            },
            description="本拍起止景别及变化方式。",
        ),
        "IncludeFeatureSlots": _fixed_text_slots_schema(
            prefix="feature",
            count=_PLANNER_FEATURE_SLOT_COUNT,
            first_required=True,
            max_characters=200,
            description="至少一项采用特征，其余槽位填写 __UNUSED__。",
        ),
        "ExcludeFeatureSlots": _fixed_text_slots_schema(
            prefix="feature",
            count=_PLANNER_FEATURE_SLOT_COUNT,
            first_required=False,
            max_characters=200,
            description="不采用特征；没有内容的槽位填写 __UNUSED__。",
        ),
    }

    definitions.update(_build_planner_beat_definitions(ranges))

    asset_properties: dict[str, Any] = {
        "asset01": {
            "$ref": "#/$def/AssetSlot",
            "description": "首个必用素材。",
        },
        "additionalAssets": {
            "type": "array",
            # DeepSeek 官方 strict 示例明确支持在 array.items 中使用普通 $ref。
            "items": {"$ref": "#/$def/AssetSlot"},
            "description": "其余零至十项素材；上限由本地归一化器校验。",
        },
    }

    beat_properties = {
        beat_key: {"$ref": f"#/$def/{_planner_beat_definition_name(index)}"}
        for index, beat_key in enumerate(beat_keys, start=1)
    }
    negative_constraints = _strict_object_schema(
        {
            "constraint01": _strict_text_schema(500, "首项必填负向约束。"),
            "additionalConstraints": {
                "type": "array",
                "items": _strict_text_schema(500, "追加负向约束。"),
                "description": "其余零至十七项负向约束；上限由本地归一化器校验。",
            },
        },
        description="模型补充的负向约束；服务器另保留两项硬约束容量。",
    )
    schema = _strict_object_schema(
        {
            "title": _strict_text_schema(120, "场景标题。"),
            "summary": _strict_text_schema(500, "单场景事件概述。"),
            "dramaticArc": _strict_text_schema(
                500,
                "用可见节拍描述全场情绪、权力或信息状态的起点、转折与落点。",
            ),
            "visualStyle": _strict_text_schema(500, "场景视觉风格。"),
            "globalDirection": _strict_text_schema(500, "全场导演方向。"),
            "cinematographyBase": {"$ref": "#/$def/CinematographyBase"},
            "lightingSetup": {"$ref": "#/$def/LightingSetup"},
            "assets": _strict_object_schema(
                asset_properties,
                description="一至十一项模型素材，为服务器派生初始关键帧预留一项。",
            ),
            "beats": _strict_object_schema(
                beat_properties,
                description="数量和顺序由本次任务时长固定的镜头节拍。",
            ),
            "negativeConstraints": negative_constraints,
        },
        description="长篇小说单场景视频导演规划 V2。",
    )
    schema["$def"] = definitions
    return cast(dict[str, JsonValue], schema)


def normalize_scene_assets_strict_tool_arguments(
    raw: Mapping[str, Any],
    *,
    setting_snapshot: LongSerialSettingSnapshot,
) -> SceneAssetsStageArguments:
    """把第一阶段紧凑 wire 归一化为场景与素材耐久规范。"""

    top_level_keys = [
        "title",
        "summary",
        "dramaticArc",
        "visualStyle",
        "globalDirection",
        "assets",
        "negativeConstraints",
    ]
    _require_exact_keys(raw, top_level_keys, "sceneAssets")
    asset_values = _require_object(raw.get("assets"), "assets")
    _require_exact_keys(asset_values, ["asset01", "additionalAssets"], "assets")
    additional_asset_values = _require_array(
        asset_values["additionalAssets"],
        "assets.additionalAssets",
    )
    if 1 + len(additional_asset_values) > _PLANNER_ASSET_SLOT_COUNT:
        raise ValueError("VIDEO_PLAN_ASSET_LIMIT_EXCEEDED：模型提交的素材总数不能超过11项")
    assets = [
        _normalize_compact_planner_asset(
            value,
            asset_key=_planner_asset_key(index),
            setting_snapshot=setting_snapshot,
        )
        for index, value in enumerate(
            [asset_values["asset01"], *additional_asset_values],
            start=1,
        )
    ]

    negative_values = _require_array(raw.get("negativeConstraints"), "negativeConstraints")
    if not 1 <= len(negative_values) <= _PLANNER_NEGATIVE_CONSTRAINT_LIMIT:
        raise ValueError("VIDEO_PLAN_NEGATIVE_CONSTRAINT_LIMIT：负向约束必须为1至18项")
    negative_constraints = [
        _require_strict_text(value, 120, f"negativeConstraints[{index}]")
        for index, value in enumerate(negative_values)
    ]
    return SceneAssetsStageArguments(
        title=_require_strict_text(raw.get("title"), 80, "title"),
        summary=_require_strict_text(raw.get("summary"), 240, "summary"),
        dramaticArc=_require_strict_text(raw.get("dramaticArc"), 240, "dramaticArc"),
        visualStyle=_require_strict_text(raw.get("visualStyle"), 240, "visualStyle"),
        globalDirection=_require_strict_text(
            raw.get("globalDirection"),
            240,
            "globalDirection",
        ),
        assets=assets,
        negativeConstraints=negative_constraints,
    )


def normalize_story_beats_strict_tool_arguments(
    raw: Mapping[str, Any],
    *,
    scene_assets: SceneAssetsStageArguments,
    beat_ranges: Sequence[tuple[int, int]],
) -> StoryBeatsStageArguments:
    """把第二阶段 wire 归一化为带逐拍素材引用的故事节拍规范。"""

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_keys = _planner_beat_keys(ranges)
    _require_exact_keys(raw, ["beats"], "storyBeats")
    beat_values = _require_object(raw.get("beats"), "beats")
    _require_exact_keys(beat_values, beat_keys, "beats")
    asset_ids = [asset.assetId for asset in scene_assets.assets]
    beats = [
        _normalize_compact_story_beat(
            beat_values[beat_key],
            beat_key=beat_key,
            beat_index=index,
            beat_range=beat_range,
            asset_ids=asset_ids,
        )
        for index, (beat_key, beat_range) in enumerate(
            zip(beat_keys, ranges, strict=True),
            start=1,
        )
    ]
    referenced_assets = {asset_id for beat in beats for asset_id in beat.referencedAssetIds}
    unused_assets = set(asset_ids) - referenced_assets
    if unused_assets:
        names = "、".join(sorted(unused_assets))
        raise ValueError(f"故事节拍阶段包含未被任何节拍使用的素材：{names}")
    return StoryBeatsStageArguments(beats=beats)


def merge_story_stage_arguments(
    scene_assets: SceneAssetsStageArguments,
    story_beats: StoryBeatsStageArguments,
    *,
    beat_ranges: Sequence[tuple[int, int]],
) -> StoryPlanStageArguments:
    """把两个 canonical 阶段确定性合并为既有完整故事规范。"""

    ranges = _validate_planner_beat_ranges(beat_ranges)
    if len(story_beats.beats) != len(ranges):
        raise ValueError("故事节拍规范的节拍数量与当前锁定时间表不一致")
    for index, (beat, beat_range) in enumerate(
        zip(story_beats.beats, ranges, strict=True),
        start=1,
    ):
        if beat.beatId != f"beat-{index:02d}" or (beat.startSecond, beat.endSecond) != beat_range:
            raise ValueError("故事节拍规范的节拍身份或时间与当前锁定时间表不一致")
    return StoryPlanStageArguments(
        schemaVersion=story_beats.schemaVersion,
        title=scene_assets.title,
        summary=scene_assets.summary,
        dramaticArc=scene_assets.dramaticArc,
        visualStyle=scene_assets.visualStyle,
        globalDirection=scene_assets.globalDirection,
        assets=scene_assets.assets,
        beats=story_beats.beats,
        negativeConstraints=scene_assets.negativeConstraints,
    )


def build_video_director_draft_skeleton(
    *,
    setting_snapshot: LongSerialSettingSnapshot,
    beat_ranges: Sequence[tuple[int, int]],
    scene_assets: SceneAssetsStageArguments | None = None,
    source_text: str | None = None,
) -> VideoDirectorDraftSkeletonV1:
    """从冻结设定、原文、服务器时间表和可选素材规范生成稳定短别名。"""

    ranges = _validate_planner_beat_ranges(beat_ranges)
    prefixes: dict[SettingKind, str] = {
        "character": "C",
        "relationship": "R",
        "location": "L",
        "item": "I",
        "world_setting": "W",
    }
    counters: dict[SettingKind, int] = {kind: 0 for kind in prefixes}
    source_aliases: list[DirectorSourceAliasV1] = []
    for entry in sorted(setting_snapshot.entries, key=lambda item: (item.kind, item.id)):
        counters[entry.kind] += 1
        if counters[entry.kind] > 99:
            raise ValueError(f"{entry.kind} 冻结设定超过短别名上限99项")
        allowed = [
            duty for duty in _PLANNER_ASSET_DUTIES if duty in _SETTING_DUTIES_BY_KIND[entry.kind]
        ]
        source_aliases.append(
            DirectorSourceAliasV1(
                alias=f"{prefixes[entry.kind]}{counters[entry.kind]:02d}",
                settingReference=SettingReference(kind=entry.kind, id=entry.id),
                name=entry.name,
                allowedDuties=allowed,
            )
        )

    asset_aliases = [
        DirectorAssetAliasV1(
            alias=f"A{index:02d}",
            ordinal=index,
            targetEntity=asset.targetEntity,
            duty=asset.duty,
        )
        for index, asset in enumerate(scene_assets.assets if scene_assets else [], start=1)
    ]
    beat_aliases = [
        DirectorBeatAliasV1(
            alias=f"B{index:02d}",
            ordinal=index,
            startSecond=start,
            endSecond=end,
        )
        for index, (start, end) in enumerate(ranges, start=1)
    ]
    source_event_aliases = source_event_aliases_for_text(source_text or "")
    return VideoDirectorDraftSkeletonV1(
        sourceAliases=source_aliases,
        assetAliases=asset_aliases,
        beatAliases=beat_aliases,
        sourceEventAliases=source_event_aliases,
    )


def json_schema_for_scene_assets_draft_response(
    *,
    skeleton: VideoDirectorDraftSkeletonV1,
) -> dict[str, JsonValue]:
    """生成第一阶段 Responses JSON Schema，并把设定引用锁成短别名。

    Responses 的 wire schema 不可靠地执行 ``maxItems``，因此素材不再以可扩展
    数组发送，而是使用一个固定的 A01..A11 槽位对象；空槽由服务端确定性移除。
    """

    schema = _responses_schema_for_model(SceneAssetsDraftV1)
    item = _draft_schema_definition(schema, "SceneAssetDraftItemV1")
    source_schema = cast(dict[str, Any], item["properties"])["sourceAlias"]
    source_aliases = [alias.alias for alias in skeleton.sourceAliases]
    _set_nullable_string_enum(
        cast(dict[str, Any], source_schema),
        source_aliases,
    )
    _set_scene_asset_source_choice_schema(
        item,
        source_aliases=skeleton.sourceAliases,
    )
    root_properties = cast(dict[str, Any], schema["properties"])
    asset_item_ref: dict[str, Any] = {"$ref": "#/$defs/SceneAssetDraftItemV1"}
    asset_slots: dict[str, Any] = {
        "asset01": asset_item_ref,
    }
    for index in range(2, 12):
        asset_slots[f"asset{index:02d}"] = {
            "anyOf": [
                {"$ref": "#/$defs/SceneAssetDraftItemV1"},
                {"type": "null"},
            ]
        }
    root_properties["assets"] = {
        "type": "object",
        "properties": asset_slots,
        "required": list(asset_slots),
        "additionalProperties": False,
    }
    return cast(dict[str, JsonValue], schema)


def normalize_scene_assets_draft_response(raw: dict[str, Any]) -> dict[str, Any]:
    """把固定 A 槽位 wire 形状还原为兼容的素材数组。

    只接受连续的 asset01..assetNN；空槽之后不能再出现素材，避免模型通过
    JSON 对象顺序或稀疏槽位制造第二套素材排序。
    """

    value = raw.get("assets")
    if not isinstance(value, dict):
        raise ValueError("VIDEO_DRAFT_ASSET_SLOTS_INVALID：素材槽位必须是固定对象")
    expected = [f"asset{index:02d}" for index in range(1, 12)]
    if set(value) != set(expected):
        raise ValueError("VIDEO_DRAFT_ASSET_SLOTS_INVALID：素材槽位集合不完整")
    assets: list[dict[str, Any]] = []
    seen_empty = False
    for alias in expected:
        slot = value[alias]
        if slot is None:
            seen_empty = True
            continue
        if seen_empty:
            raise ValueError("VIDEO_DRAFT_ASSET_SLOTS_INVALID：素材槽位不能跨空槽")
        if not isinstance(slot, dict):
            raise ValueError("VIDEO_DRAFT_ASSET_SLOTS_INVALID：素材槽位内容无效")
        normalized_slot = dict(slot)
        # 供应商偶尔会同时复述设定名称；sourceAlias 是冻结事实的唯一权威，
        # 相同职责下丢弃冗余 targetEntity，避免把等价回显误判为双重来源。
        if normalized_slot.get("sourceAlias") is not None:
            normalized_slot["targetEntity"] = None
        assets.append(normalized_slot)
    if not assets:
        raise ValueError("VIDEO_DRAFT_ASSET_SLOTS_EMPTY：至少需要一个素材槽位")
    normalized = dict(raw)
    normalized["assets"] = assets
    return normalized


def json_schema_for_story_beats_draft_response(
    *,
    skeleton: VideoDirectorDraftSkeletonV1,
    draft_version: Literal["2.0", "3.0", "4.0"] = "2.0",
) -> dict[str, JsonValue]:
    """生成第二阶段 Responses Schema；v4 由服务器闭合 B 与 E 身份。"""

    if not skeleton.assetAliases:
        raise ValueError("故事草案 Schema 需要至少一个已物化素材别名")
    model: type[VideoContractModel]
    item_name: str
    if draft_version == "4.0":
        model = StoryBeatsDraftV4
        item_name = "StoryBeatDraftItemV4"
    elif draft_version == "3.0":
        model = StoryBeatsDraftV3
        item_name = "StoryBeatDraftItemV3"
    else:
        model = StoryBeatsDraftV2
        item_name = "StoryBeatDraftItemV2"
    schema = _responses_schema_for_model(model)
    beat_aliases = [alias.alias for alias in skeleton.beatAliases]
    root_properties = cast(dict[str, Any], schema["properties"])
    if draft_version == "4.0":
        beats_schema = cast(dict[str, Any], root_properties["beatsByAlias"])
        beats_schema.clear()
        beats_schema.update(
            {
                "type": "object",
                "properties": {
                    alias: {"$ref": f"#/$defs/{item_name}"} for alias in beat_aliases
                },
                "required": beat_aliases,
                "additionalProperties": False,
            }
        )
    else:
        item = _draft_schema_definition(schema, item_name)
        properties = cast(dict[str, Any], item["properties"])
        cast(dict[str, Any], properties["beatAlias"])["enum"] = beat_aliases
        if draft_version == "3.0":
            event_aliases = [alias.alias for alias in skeleton.sourceEventAliases]
            for field_name in (
                "primarySourceEventAliases",
                "secondarySourceEventAliases",
            ):
                items = cast(dict[str, Any], properties[field_name])["items"]
                cast(dict[str, Any], items)["enum"] = event_aliases

    usage_item = _draft_schema_definition(schema, "StoryAssetUsageDraftV2")
    usage_properties = cast(dict[str, Any], usage_item["properties"])
    cast(dict[str, Any], usage_properties["primaryBeatAlias"])["enum"] = beat_aliases
    additional_items = cast(dict[str, Any], usage_properties["additionalBeatAliases"])["items"]
    cast(dict[str, Any], additional_items)["enum"] = beat_aliases

    usage_schema = cast(dict[str, Any], root_properties["assetUsageByAlias"])
    asset_aliases = [alias.alias for alias in skeleton.assetAliases]
    _set_nullable_string_enum(
        cast(dict[str, Any], usage_properties["anchorAssetAlias"]),
        asset_aliases,
    )
    # 动态闭合对象让每个当前 A 别名都成为 wire 必填属性，避免跨 beat 数组做隐藏覆盖校验。
    usage_schema.clear()
    usage_schema.update(
        {
            "type": "object",
            "properties": {
                alias: {"$ref": "#/$defs/StoryAssetUsageDraftV2"} for alias in asset_aliases
            },
            "required": asset_aliases,
            "additionalProperties": False,
        }
    )
    return cast(dict[str, JsonValue], schema)


def json_schema_for_cinematography_draft_response(
    *,
    skeleton: VideoDirectorDraftSkeletonV1,
) -> dict[str, JsonValue]:
    """生成按拍闭合的第三阶段 Schema，把首拍灯光规则直接送入供应商。"""

    if not skeleton.beatAliases:
        raise ValueError("摄影草案 Schema 需要至少一个节拍别名")
    schema = _responses_schema_for_model(CinematographyDraftV2)
    definitions = cast(dict[str, Any], schema["$defs"])
    cinematography_base = _draft_schema_definition(schema, "CinematographyBase")
    base_properties = cast(dict[str, Any], cinematography_base["properties"])
    cast(dict[str, Any], base_properties["axisRule"])["enum"] = ["maintain_180"]
    camera_position = _draft_schema_definition(schema, "CameraPositionSpec")
    position_properties = cast(dict[str, Any], camera_position["properties"])
    cast(dict[str, Any], position_properties["axisSide"])["enum"] = [
        "screen_left",
        "on_axis",
    ]
    base_camera = _draft_schema_definition(schema, "ShotCameraSpec")
    base_movement = _draft_schema_definition(schema, "CameraMovementSpec")
    movement_properties = cast(dict[str, Any], base_movement["properties"])
    movement_type = cast(dict[str, Any], movement_properties["movementType"])
    movement_values = cast(list[str], movement_type["enum"])

    fixed_movement = deepcopy(base_movement)
    fixed_movement_properties = cast(dict[str, Any], fixed_movement["properties"])
    cast(dict[str, Any], fixed_movement_properties["movementType"])["enum"] = [
        value for value in movement_values if value not in {"zoom_in", "zoom_out"}
    ]
    zoom_movement = deepcopy(base_movement)
    zoom_movement_properties = cast(dict[str, Any], zoom_movement["properties"])
    cast(dict[str, Any], zoom_movement_properties["movementType"])["enum"] = [
        "zoom_in",
        "zoom_out",
    ]
    cast(dict[str, Any], zoom_movement_properties["travelDistanceMeters"])["enum"] = [0]
    cast(dict[str, Any], zoom_movement_properties["rotationDegrees"])["enum"] = [0]
    definitions["FixedLensCameraMovementV2"] = fixed_movement
    definitions["ZoomLensCameraMovementV2"] = zoom_movement

    fixed_camera = deepcopy(base_camera)
    fixed_camera_properties = cast(dict[str, Any], fixed_camera["properties"])
    cast(dict[str, Any], fixed_camera_properties["lensType"])["enum"] = [
        "prime",
        "macro_prime",
    ]
    fixed_camera_properties["movement"] = {
        "$ref": "#/$defs/FixedLensCameraMovementV2"
    }
    zoom_camera = deepcopy(base_camera)
    zoom_camera_properties = cast(dict[str, Any], zoom_camera["properties"])
    cast(dict[str, Any], zoom_camera_properties["lensType"])["enum"] = ["zoom"]
    zoom_camera_properties["movement"] = {"$ref": "#/$defs/ZoomLensCameraMovementV2"}
    definitions["FixedLensCameraSpecV2"] = fixed_camera
    definitions["ZoomLensCameraSpecV2"] = zoom_camera
    definitions["ShotCameraSpec"] = {
        "anyOf": [
            {"$ref": "#/$defs/FixedLensCameraSpecV2"},
            {"$ref": "#/$defs/ZoomLensCameraSpecV2"},
        ]
    }

    base_item = _draft_schema_definition(schema, "CinematographyBeatDraftItemV1")
    base_progression = _draft_schema_definition(schema, "CameraShotProgression")
    base_lighting = _draft_schema_definition(schema, "ShotLightingCue")
    first_lighting = deepcopy(base_lighting)
    motivated_lighting = deepcopy(base_lighting)
    for lighting, mode in (
        (first_lighting, "establish"),
        (motivated_lighting, "motivated_change"),
    ):
        lighting_properties = cast(dict[str, Any], lighting["properties"])
        continuity = lighting_properties["continuityMode"]
        cast(dict[str, Any], continuity)["enum"] = [mode]
        motivated_change = cast(dict[str, Any], lighting_properties["motivatedChange"])
        motivated_change.clear()
        motivated_change.update(
            _strict_text_schema(
                160,
                (
                    "非空填写首拍建立灯光的画内来源。"
                    if mode == "establish"
                    else "非空填写触发灯光变化的画内可见事件。"
                ),
            )
        )
    for definition_name, lighting in (
        ("FirstShotLightingCueV2", first_lighting),
        ("MotivatedShotLightingCueV2", motivated_lighting),
    ):
        no_fill = deepcopy(lighting)
        no_fill_properties = cast(dict[str, Any], no_fill["properties"])
        cast(dict[str, Any], no_fill_properties["fillStrategy"])["enum"] = ["none"]
        no_fill_properties["fillDirection"] = {"type": "null"}
        no_fill_properties["fillRelativeStops"] = {"type": "number", "enum": [-8]}

        active_fill = deepcopy(lighting)
        active_fill_properties = cast(dict[str, Any], active_fill["properties"])
        cast(dict[str, Any], active_fill_properties["fillStrategy"])["enum"] = [
            "soft_fill",
            "bounce_fill",
            "negative_fill",
        ]
        active_fill_properties["fillDirection"] = {
            "type": "string",
            "enum": list(_LIGHT_DIRECTIONS),
        }
        definitions[definition_name] = {"anyOf": [no_fill, active_fill]}

    beat_properties: dict[str, Any] = {}
    for index, alias in enumerate(skeleton.beatAliases, start=1):
        definition_name = f"CinematographyBeatDraftV2_{index:02d}"
        item = deepcopy(base_item)
        properties = cast(dict[str, Any], item["properties"])
        cast(dict[str, Any], properties["beatAlias"])["enum"] = [alias.alias]
        cast(dict[str, Any], properties["axisTransition"])["enum"] = ["hold"]

        duration = alias.endSecond - alias.startSecond
        continuous_scale_limit = 1 if duration < 5 else 2 if duration < 6 else None
        if continuous_scale_limit is not None:
            cut_name = f"CutShotProgressionV2_{index:02d}"
            cut_progression = deepcopy(base_progression)
            cut_properties = cast(dict[str, Any], cut_progression["properties"])
            cast(dict[str, Any], cut_properties["changeMode"])["enum"] = [
                "cut",
                "match_cut",
                "impact_cut",
            ]
            definitions[cut_name] = cut_progression

            progression_branches: list[dict[str, str]] = [
                {"$ref": f"#/$defs/{cut_name}"}
            ]
            for start_index, start_size in enumerate(_SHOT_SIZES, start=1):
                continuous_name = (
                    f"ContinuousShotProgressionV2_{index:02d}_{start_index:02d}"
                )
                continuous_progression = deepcopy(base_progression)
                continuous_properties = cast(
                    dict[str, Any],
                    continuous_progression["properties"],
                )
                cast(dict[str, Any], continuous_properties["startShotSize"])["enum"] = [
                    start_size
                ]
                cast(dict[str, Any], continuous_properties["endShotSize"])["enum"] = [
                    end_size
                    for end_size in _SHOT_SIZES
                    if abs(_SHOT_SIZE_RANK[end_size] - _SHOT_SIZE_RANK[start_size])
                    <= continuous_scale_limit
                ]
                cast(dict[str, Any], continuous_properties["changeMode"])["enum"] = [
                    "continuous"
                ]
                definitions[continuous_name] = continuous_progression
                progression_branches.append(
                    {"$ref": f"#/$defs/{continuous_name}"}
                )
            progression_name = f"ShotProgressionV2_{index:02d}"
            definitions[progression_name] = {"anyOf": progression_branches}
            properties["shotProgression"] = {
                "$ref": f"#/$defs/{progression_name}"
            }
        if index == 1:
            properties["lightingCue"] = {"$ref": "#/$defs/FirstShotLightingCueV2"}
        else:
            properties["lightingCue"] = {
                "anyOf": [
                    {"$ref": "#/$defs/MotivatedShotLightingCueV2"},
                    {"type": "null"},
                ]
            }
        definitions[definition_name] = item
        beat_properties[alias.alias] = {"$ref": f"#/$defs/{definition_name}"}

    root_properties = cast(dict[str, Any], schema["properties"])
    root_properties["beatsByAlias"] = {
        "type": "object",
        "properties": beat_properties,
        "required": list(beat_properties),
        "additionalProperties": False,
    }
    return cast(dict[str, JsonValue], schema)


def materialize_scene_assets_draft(
    draft: SceneAssetsDraftV1,
    *,
    setting_snapshot: LongSerialSettingSnapshot,
) -> SceneAssetsStageArguments:
    """把轻量素材草案确定性物化为既有 canonical 素材检查点。"""

    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=setting_snapshot,
        beat_ranges=[(0, 1)],
    )
    sources = {item.alias: item for item in skeleton.sourceAliases}
    canon_labels_by_duty: dict[str, set[str]] = {}
    for entry in setting_snapshot.entries:
        labels = [entry.name]
        aliases = getattr(entry, "aliases", None)
        if isinstance(aliases, list):
            labels.extend(aliases)
        for duty in _SETTING_DUTIES_BY_KIND[entry.kind]:
            canon_labels_by_duty.setdefault(duty, set()).update(
                _normalize_draft_entity_label(label) for label in labels
            )
    assets: list[PlannedAssetArguments] = []
    semantic_keys: set[tuple[str, ...]] = set()
    for index, item in enumerate(draft.assets, start=1):
        label = f"assets[{index - 1}]"
        include_features = _validate_draft_texts(
            item.includeFeatures,
            max_characters=80,
            label=f"{label}.includeFeatures",
        )
        exclude_features = _validate_draft_texts(
            item.excludeFeatures,
            max_characters=80,
            label=f"{label}.excludeFeatures",
        )
        modality = _DEFAULT_DRAFT_MODALITY_BY_DUTY[item.duty]
        feature_domain = cast(AssetFeatureDomain, _FEATURE_DOMAIN_BY_DUTY[item.duty])
        semantic_key: tuple[str, str, str]
        if item.sourceAlias is not None:
            source = sources.get(item.sourceAlias)
            if source is None:
                raise ValueError(
                    f"VIDEO_DRAFT_UNKNOWN_SOURCE_ALIAS：未知设定别名 {item.sourceAlias}"
                )
            if item.duty not in source.allowedDuties:
                raise ValueError(
                    "VIDEO_DRAFT_SOURCE_DUTY_MISMATCH："
                    f"设定别名 {item.sourceAlias} 不支持职责 {item.duty}"
                )
            target_entity = source.name
            binding_scope: AssetBindingScope = "canon_slot"
            setting_reference: SettingReference | None = source.settingReference
            keyframe_role: KeyframeRole | None = None
            semantic_key = ("canon", item.sourceAlias, item.duty)
        else:
            target_entity = _require_strict_text(item.targetEntity, 80, f"{label}.targetEntity")
            if _normalize_draft_entity_label(target_entity) in canon_labels_by_duty.get(
                item.duty, set()
            ):
                raise ValueError(
                    "VIDEO_DRAFT_CANON_ALIAS_REQUIRED：本场素材目标命中冻结设定，"
                    "必须使用对应 sourceAlias"
                )
            binding_scope = "scene_direct"
            setting_reference = None
            keyframe_role = "initial_state" if item.duty == "keyframe" else None
            semantic_key = ("direct", item.duty, target_entity.casefold())
        if semantic_key in semantic_keys:
            raise ValueError("VIDEO_DRAFT_ASSET_DUPLICATED：素材草案包含重复语义素材")
        semantic_keys.add(semantic_key)
        assets.append(
            PlannedAssetArguments(
                assetId=f"asset{index:02d}",
                modality=modality,
                duty=item.duty,
                bindingScope=binding_scope,
                settingReference=setting_reference,
                featureDomain=feature_domain,
                keyframeRole=keyframe_role,
                targetEntity=target_entity,
                includeFeatures=include_features,
                excludeFeatures=exclude_features,
            )
        )

    return SceneAssetsStageArguments(
        title=_require_strict_text(draft.title, 80, "title"),
        summary=_require_strict_text(draft.summary, 240, "summary"),
        dramaticArc=_require_strict_text(draft.dramaticArc, 240, "dramaticArc"),
        visualStyle=_require_strict_text(draft.visualStyle, 240, "visualStyle"),
        globalDirection=_require_strict_text(
            draft.globalDirection,
            240,
            "globalDirection",
        ),
        assets=assets,
        negativeConstraints=_validate_draft_texts(
            draft.negativeConstraints,
            max_characters=120,
            label="negativeConstraints",
        ),
    )


def _normalize_draft_entity_label(value: str) -> str:
    """只用于精确识别冻结名称与别名，禁止模糊匹配或“最相近”猜测。"""

    return " ".join(value.split()).casefold()


def materialize_story_beats_draft(
    draft: StoryBeatsDraftV2 | StoryBeatsDraftV3 | StoryBeatsDraftV4,
    *,
    scene_assets: SceneAssetsStageArguments,
    beat_ranges: Sequence[tuple[int, int]],
    source_text: str | None = None,
) -> StoryBeatsStageArguments:
    """把故事草案映射为服务器锁定身份、事件槽、时间和素材引用。"""

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_aliases = {
        f"B{index:02d}": (index, beat_range) for index, beat_range in enumerate(ranges, 1)
    }
    if isinstance(draft, StoryBeatsDraftV4):
        if set(draft.beatsByAlias) != set(beat_aliases):
            raise ValueError("VIDEO_DRAFT_BEAT_SET_INVALID：故事草案节拍集合不完整")
        draft_by_alias: dict[
            str,
            StoryBeatDraftItemV2 | StoryBeatDraftItemV3 | StoryBeatDraftItemV4,
        ] = dict(draft.beatsByAlias)
    else:
        draft_by_alias = cast(
            dict[
                str,
                StoryBeatDraftItemV2 | StoryBeatDraftItemV3 | StoryBeatDraftItemV4,
            ],
            _index_draft_beats(
                draft.beats,
                expected_aliases=set(beat_aliases),
                label="故事草案",
            ),
        )
    source_event_schedule: dict[str, list[list[str]]] | None = None
    if isinstance(draft, StoryBeatsDraftV4):
        if source_text is None:
            raise ValueError("VIDEO_PLAN_SOURCE_EVENT_CONTEXT_MISSING：v4 故事草案缺少冻结原文")
        source_event_schedule = distribute_source_event_aliases(
            source_event_aliases_for_text(source_text),
            [
                DirectorBeatAliasV1(
                    alias=alias,
                    ordinal=index,
                    startSecond=beat_range[0],
                    endSecond=beat_range[1],
                )
                for alias, (index, beat_range) in beat_aliases.items()
            ],
        )
    asset_aliases = {
        f"A{index:02d}": asset.assetId for index, asset in enumerate(scene_assets.assets, start=1)
    }
    expected_asset_aliases = set(asset_aliases)
    actual_asset_aliases = set(draft.assetUsageByAlias)
    unknown_asset_aliases = actual_asset_aliases - expected_asset_aliases
    if unknown_asset_aliases:
        raise ValueError("VIDEO_DRAFT_UNKNOWN_ASSET_ALIAS：素材使用表包含未知 A 别名")
    missing_asset_aliases = expected_asset_aliases - actual_asset_aliases
    if missing_asset_aliases:
        names = "、".join(sorted(missing_asset_aliases))
        raise ValueError(f"VIDEO_DRAFT_ASSET_USAGE_MISSING：素材使用表缺少 {names}")

    referenced_assets_by_beat: dict[str, list[str]] = {alias: [] for alias in beat_aliases}
    assets_by_alias = {
        alias: asset for alias, asset in zip(asset_aliases, scene_assets.assets, strict=True)
    }
    usage_beats_by_alias: dict[str, list[str]] = {}
    for asset_alias, _asset_id in asset_aliases.items():
        asset = assets_by_alias[asset_alias]
        usage = draft.assetUsageByAlias[asset_alias]
        used_beat_aliases = [usage.primaryBeatAlias, *usage.additionalBeatAliases]
        if len(used_beat_aliases) != len(set(used_beat_aliases)):
            raise ValueError(
                f"VIDEO_DRAFT_ASSET_USAGE_DUPLICATED：素材 {asset_alias} 的节拍别名重复"
            )
        if set(used_beat_aliases) - set(beat_aliases):
            raise ValueError(
                f"VIDEO_DRAFT_UNKNOWN_BEAT_ALIAS：素材 {asset_alias} 引用了未知 B 别名"
            )
        ordinals = [beat_aliases[alias][0] for alias in used_beat_aliases]
        if ordinals != sorted(ordinals):
            raise ValueError(
                f"VIDEO_DRAFT_ASSET_USAGE_ORDER_INVALID：素材 {asset_alias} 必须先写首次使用拍，"
                "额外拍按时间递增"
            )
        usage_beats_by_alias[asset_alias] = used_beat_aliases

    # 机械序列的起始拍是初态关键帧的唯一时间锚点。只有全场没有机械动作时，
    # 才退回道具首次出现拍；不能因道具更早入画就把机械初态提前到普通故事拍。
    mechanical_aliases = [
        alias
        for alias, item in draft_by_alias.items()
        if is_irreversible_mechanical_beat(
            item.actionComplexity,
            [
                item.primaryAction,
                *([item.secondaryAction] if item.secondaryAction is not None else []),
            ],
        )
    ]
    mechanical_candidates = [alias for alias in mechanical_aliases if alias in beat_aliases]
    mechanical_start_alias: str | None
    if mechanical_candidates:
        mechanical_start_alias = min(
            mechanical_candidates,
            key=lambda alias: beat_aliases[alias][0],
        )
    else:
        prop_debut_candidates = [
            usage_beats_by_alias[asset_alias][0]
            for asset_alias, asset in assets_by_alias.items()
            if asset.duty == "prop" and usage_beats_by_alias[asset_alias]
        ]
        mechanical_start_alias = min(
            prop_debut_candidates,
            key=lambda alias: beat_aliases[alias][0],
            default=None,
        )

    for asset_alias, asset_id in asset_aliases.items():
        asset = assets_by_alias[asset_alias]
        usage = draft.assetUsageByAlias[asset_alias]
        anchor_alias = usage.anchorAssetAlias
        is_initial_keyframe = asset.duty == "keyframe" and asset.keyframeRole == "initial_state"
        if is_initial_keyframe:
            if anchor_alias is None:
                raise ValueError(
                    f"VIDEO_DRAFT_KEYFRAME_ANCHOR_REQUIRED：初态关键帧 {asset_alias} 必须锚定素材"
                )
            if anchor_alias not in assets_by_alias or anchor_alias == asset_alias:
                raise ValueError(
                    f"VIDEO_DRAFT_KEYFRAME_ANCHOR_INVALID：初态关键帧 {asset_alias} 的锚定素材无效"
                )
            anchor_usage = draft.assetUsageByAlias[anchor_alias]
            expected_primary = mechanical_start_alias or anchor_usage.primaryBeatAlias
            # 初态关键帧的有效拍点完全由锚定素材的首次使用拍决定；模型回传的
            # 位图可能漏填或多填，均不构成新的创意事实，服务端确定性收敛。
            usage_beats_by_alias[asset_alias] = [expected_primary]
        elif anchor_alias is not None:
            # 锚定关系只对初态关键帧有语义；普通素材的冗余锚定不进入 canonical。
            anchor_alias = None
        for beat_alias in usage_beats_by_alias[asset_alias]:
            referenced_assets_by_beat[beat_alias].append(asset_id)

    if mechanical_start_alias is not None:
        # 关键帧是机械序列的起始事实；即使模型漏回该 A/B 关联，也由服务端把
        # 已锁定的初态素材补到起始拍，避免在动作发生后才出现“初态”。
        for _asset_alias, asset in assets_by_alias.items():
            if asset.duty != "keyframe" or asset.keyframeRole != "initial_state":
                continue
            asset_id = asset.assetId
            if asset_id not in referenced_assets_by_beat[mechanical_start_alias]:
                referenced_assets_by_beat[mechanical_start_alias].append(asset_id)

    beats: list[StoryBeatPlanArguments] = []
    for alias, (index, beat_range) in beat_aliases.items():
        item = draft_by_alias[alias]
        actions = [item.primaryAction]
        if item.secondaryAction is not None:
            actions.append(item.secondaryAction)
        source_event_aliases_by_action: list[list[str]] = []
        if isinstance(item, StoryBeatDraftItemV3):
            if item.secondaryAction is None and item.secondarySourceEventAliases:
                raise ValueError(
                    "VIDEO_PLAN_SOURCE_EVENT_ASSIGNMENT_INVALID：没有 secondaryAction 时"
                    "secondarySourceEventAliases 必须为空"
                )
            source_event_aliases_by_action = [item.primarySourceEventAliases]
            if item.secondaryAction is not None:
                source_event_aliases_by_action.append(item.secondarySourceEventAliases)
        elif isinstance(item, StoryBeatDraftItemV4):
            if source_event_schedule is None:
                raise ValueError("VIDEO_PLAN_SOURCE_EVENT_CONTEXT_MISSING：v4 事件槽未生成")
            scheduled_slots = source_event_schedule[alias]
            if item.secondaryAction is None and len(scheduled_slots) > 1 and scheduled_slots[1]:
                required = "、".join(scheduled_slots[1])
                raise ValueError(
                    "VIDEO_PLAN_SOURCE_EVENT_ACTION_REQUIRED："
                    f"{alias}.secondaryAction 必须落地 {required}"
                )
            source_event_aliases_by_action = [scheduled_slots[0]]
            if item.secondaryAction is not None:
                source_event_aliases_by_action.append(
                    scheduled_slots[1] if len(scheduled_slots) > 1 else []
                )
        if len(actions) > _planner_action_capacity(*beat_range):
            raise ValueError(f"VIDEO_DRAFT_ACTION_CAPACITY_EXCEEDED：节拍 {alias} 动作数量超限")
        start, end = beat_range
        beats.append(
            StoryBeatPlanArguments(
                beatId=f"beat-{index:02d}",
                startSecond=start,
                endSecond=end,
                dramaticPurpose=_require_strict_text(
                    item.dramaticPurpose,
                    160,
                    f"{alias}.dramaticPurpose",
                ),
                performanceDirection=_require_strict_text(
                    item.performanceDirection,
                    200,
                    f"{alias}.performanceDirection",
                ),
                blocking=_require_strict_text(item.blocking, 200, f"{alias}.blocking"),
                actionUnits=actions,
                sourceEventAliasesByAction=source_event_aliases_by_action,
                actionComplexity=item.actionComplexity,
                sound=_require_strict_text(item.sound, 240, f"{alias}.sound"),
                referencedAssetIds=referenced_assets_by_beat[alias],
            )
        )

    # initial_state 已在上方根据 anchorAssetAlias 和最早机械起点收敛为唯一拍；
    # 后续道具首次出现不能重放另一项素材的初态关键帧。
    schema_version: Literal["1.0", "2.0"] = (
        "2.0" if isinstance(draft, (StoryBeatsDraftV3, StoryBeatsDraftV4)) else "1.0"
    )
    result = StoryBeatsStageArguments(schemaVersion=schema_version, beats=beats)
    if isinstance(draft, (StoryBeatsDraftV3, StoryBeatsDraftV4)):
        if source_text is None:
            raise ValueError("VIDEO_PLAN_SOURCE_EVENT_CONTEXT_MISSING：结构化故事草案缺少冻结原文")
        validate_source_event_sequence(
            source_text,
            result.beats,
            require_structured=True,
        )
    return result


def materialize_cinematography_draft(
    draft: CinematographyDraftV1 | CinematographyDraftV2,
    *,
    story: StoryPlanStageArguments,
    setting_snapshot: LongSerialSettingSnapshot,
    beat_ranges: Sequence[tuple[int, int]],
) -> ScenePlanToolArguments:
    """把摄影自然数组投影成旧兼容 wire，再由唯一归一化器生成正式参数。"""

    ranges = _validate_planner_beat_ranges(beat_ranges)
    aliases = [f"B{index:02d}" for index in range(1, len(ranges) + 1)]
    if isinstance(draft, CinematographyDraftV2):
        if set(draft.beatsByAlias) != set(aliases):
            raise ValueError("VIDEO_DRAFT_BEAT_SET_INVALID：摄影草案节拍集合不完整")
        for key, item in draft.beatsByAlias.items():
            if item.beatAlias != key:
                raise ValueError("VIDEO_DRAFT_BEAT_ALIAS_MISMATCH：摄影草案属性与别名不一致")
        draft_items = list(draft.beatsByAlias.values())
    else:
        draft_items = draft.beats
    draft_by_alias = _index_draft_beats(
        draft_items,
        expected_aliases=set(aliases),
        label="摄影草案",
    )
    raw_beats: dict[str, JsonValue] = {}
    for index, alias in enumerate(aliases, start=1):
        item = cast(CinematographyBeatDraftItemV1, draft_by_alias[alias])
        if index == 1 and item.lightingCue is None:
            raise ValueError("VIDEO_DRAFT_FIRST_LIGHTING_REQUIRED：摄影草案首拍必须建立灯光")
        if index == 1 and item.lightingCue is not None:
            if item.lightingCue.continuityMode != "establish":
                raise ValueError(
                    "VIDEO_DRAFT_FIRST_LIGHTING_INVALID：摄影草案首拍必须使用 establish"
                )
        if index > 1 and item.lightingCue is not None:
            if item.lightingCue.continuityMode != "motivated_change":
                raise ValueError(
                    "VIDEO_DRAFT_LIGHTING_CHANGE_INVALID：非首拍完整灯光必须使用 motivated_change"
                )
        raw_beats[f"beat{index:02d}"] = cast(
            dict[str, JsonValue],
            {
                "cameraSpec": item.cameraSpec.model_dump(mode="json"),
                "lightingCue": (
                    _PLANNER_INHERIT_LIGHTING_SENTINEL
                    if item.lightingCue is None
                    else _cinematography_lighting_draft_to_legacy_wire(item.lightingCue)
                ),
                "cameraMotivation": item.cameraMotivation,
                "axisTransition": item.axisTransition,
                "shotProgression": item.shotProgression.model_dump(mode="json"),
                "transition": item.transition or _PLANNER_UNUSED_SENTINEL,
            },
        )
    raw: dict[str, JsonValue] = {
        "cinematographyBase": cast(
            JsonValue,
            draft.cinematographyBase.model_dump(mode="json"),
        ),
        "lightingSetup": cast(JsonValue, draft.lightingSetup.model_dump(mode="json")),
        "beats": raw_beats,
    }
    return normalize_split_strict_tool_arguments(
        story,
        raw,
        setting_snapshot=setting_snapshot,
        beat_ranges=ranges,
    )


def _cinematography_lighting_draft_to_legacy_wire(
    cue: ShotLightingCue,
) -> dict[str, JsonValue]:
    """只在内部兼容投影中恢复旧 edgeLight 哨兵，草案 wire 始终使用 null。"""

    values = cue.model_dump(mode="json")
    if values["edgeLight"] is None:
        values["edgeLight"] = _PLANNER_UNUSED_SENTINEL
    return cast(dict[str, JsonValue], values)


def _responses_schema_for_model(model: type[VideoContractModel]) -> dict[str, Any]:
    """生成 Responses strict 可接受的全字段必填 Schema，不加入哨兵或位图。"""

    schema = model.model_json_schema()

    def normalize(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("default", None)
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["required"] = list(properties)
                value["additionalProperties"] = False
            for child in value.values():
                normalize(child)
        elif isinstance(value, list):
            for child in value:
                normalize(child)

    normalize(schema)
    return schema


def _draft_schema_definition(schema: Mapping[str, Any], name: str) -> dict[str, Any]:
    """读取 Pydantic 草案定义并在结构漂移时立即失败。"""

    definitions = schema.get("$defs")
    if not isinstance(definitions, dict) or not isinstance(definitions.get(name), dict):
        raise ValueError(f"Responses 草案 Schema 缺少定义 {name}")
    return cast(dict[str, Any], definitions[name])


def _set_nullable_string_enum(schema: dict[str, Any], values: list[str]) -> None:
    """只收紧 nullable string 的字符串分支，空目录时仅允许 null。"""

    branches = schema.get("anyOf")
    if not isinstance(branches, list):
        raise ValueError("Responses 草案 Schema 的可空字符串结构已漂移")
    string_branch = next(
        (
            branch
            for branch in branches
            if isinstance(branch, dict) and branch.get("type") == "string"
        ),
        None,
    )
    if string_branch is None:
        raise ValueError("Responses 草案 Schema 缺少字符串分支")
    if values:
        string_branch["enum"] = values
    else:
        schema["anyOf"] = [
            branch
            for branch in branches
            if isinstance(branch, dict) and branch.get("type") == "null"
        ]


def _set_scene_asset_source_choice_schema(
    item_schema: dict[str, Any],
    *,
    source_aliases: list[DirectorSourceAliasV1],
) -> None:
    """把来源二选一及设定别名允许职责写入供应商可见 Schema。"""

    properties = item_schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("Responses 场景素材定义缺少 properties")
    source_schema = properties.get("sourceAlias")
    target_schema = properties.get("targetEntity")
    duty_schema = properties.get("duty")
    if (
        not isinstance(source_schema, dict)
        or not isinstance(target_schema, dict)
        or not isinstance(duty_schema, dict)
    ):
        raise ValueError("Responses 场景素材定义缺少来源字段")

    def nullable_branch(schema: Mapping[str, Any], expected_type: str) -> dict[str, Any]:
        branches = schema.get("anyOf")
        if not isinstance(branches, list):
            raise ValueError("Responses 场景素材来源字段不再是可空字符串")
        branch = next(
            (
                candidate
                for candidate in branches
                if isinstance(candidate, dict) and candidate.get("type") == expected_type
            ),
            None,
        )
        if branch is None:
            raise ValueError(f"Responses 场景素材来源字段缺少 {expected_type} 分支")
        return deepcopy(branch)

    def closed_branch(
        *,
        source_choice: dict[str, Any],
        target_choice: dict[str, Any],
        duty_choice: dict[str, Any],
    ) -> dict[str, Any]:
        # 每个 anyOf 分支都复制完整对象字段，避免分支级 additionalProperties 误伤其他职责字段。
        branch_properties = deepcopy(properties)
        branch_properties["sourceAlias"] = source_choice
        branch_properties["targetEntity"] = target_choice
        branch_properties["duty"] = duty_choice
        return {
            "type": "object",
            "properties": branch_properties,
            "required": list(branch_properties),
            "additionalProperties": False,
        }

    branches: list[dict[str, Any]] = []
    if source_aliases:
        aliases_by_duties: dict[tuple[PlannerAssetDuty, ...], list[str]] = {}
        for source in source_aliases:
            duties = tuple(
                duty for duty in _PLANNER_ASSET_DUTIES if duty in source.allowedDuties
            )
            aliases_by_duties.setdefault(duties, []).append(source.alias)
        for duties, aliases in aliases_by_duties.items():
            source_choice = nullable_branch(source_schema, "string")
            source_choice["enum"] = aliases
            duty_choice = deepcopy(duty_schema)
            duty_choice["enum"] = list(duties)
            branches.append(
                closed_branch(
                    source_choice=source_choice,
                    target_choice=nullable_branch(target_schema, "null"),
                    duty_choice=duty_choice,
                )
            )
    branches.append(
        closed_branch(
            source_choice=nullable_branch(source_schema, "null"),
            target_choice=nullable_branch(target_schema, "string"),
            duty_choice=deepcopy(duty_schema),
        )
    )

    # 替换为两个互斥的完整对象分支；Pydantic 模型仍负责运行时的第二层相同校验。
    title = item_schema.get("title")
    description = item_schema.get("description")
    item_schema.clear()
    item_schema["anyOf"] = branches
    if isinstance(title, str):
        item_schema["title"] = title
    if isinstance(description, str):
        item_schema["description"] = description


def _validate_draft_texts(
    values: Sequence[str],
    *,
    max_characters: int,
    label: str,
) -> list[str]:
    """完整校验文本数组并拒绝重复，不摘要、不截断也不静默去重。"""

    result = [
        _require_strict_text(value, max_characters, f"{label}[{index}]")
        for index, value in enumerate(values)
    ]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} 不能包含重复文本")
    return result


def _index_draft_beats(
    beats: (
        Sequence[StoryBeatDraftItemV1]
        | Sequence[StoryBeatDraftItemV2]
        | Sequence[StoryBeatDraftItemV3]
        | Sequence[CinematographyBeatDraftItemV1]
    ),
    *,
    expected_aliases: set[str],
    label: str,
) -> dict[
    str,
    StoryBeatDraftItemV1
    | StoryBeatDraftItemV2
    | StoryBeatDraftItemV3
    | CinematographyBeatDraftItemV1,
]:
    """按短别名索引自然节拍数组，并明确拒绝重复、未知和缺拍。"""

    result: dict[
        str,
        StoryBeatDraftItemV1
        | StoryBeatDraftItemV2
        | StoryBeatDraftItemV3
        | CinematographyBeatDraftItemV1,
    ] = {}
    for item in beats:
        if item.beatAlias in result:
            raise ValueError(f"VIDEO_DRAFT_BEAT_ALIAS_DUPLICATED：{label}重复节拍 {item.beatAlias}")
        result[item.beatAlias] = item
    unknown = set(result) - expected_aliases
    if unknown:
        names = "、".join(sorted(unknown))
        raise ValueError(f"VIDEO_DRAFT_UNKNOWN_BEAT_ALIAS：{label}包含未知节拍 {names}")
    missing = expected_aliases - set(result)
    if missing:
        names = "、".join(sorted(missing))
        raise ValueError(f"VIDEO_DRAFT_BEAT_MISSING：{label}缺少节拍 {names}")
    return result


def normalize_story_strict_tool_arguments(
    raw: Mapping[str, Any],
    *,
    setting_snapshot: LongSerialSettingSnapshot,
    beat_ranges: Sequence[tuple[int, int]],
) -> StoryPlanStageArguments:
    """把第一阶段 strict wire 归一化为可交给第二阶段的规范 JSON。"""

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_keys = _planner_beat_keys(ranges)
    top_level_keys = [
        "title",
        "summary",
        "dramaticArc",
        "visualStyle",
        "globalDirection",
        "assets",
        "beats",
        "negativeConstraints",
    ]
    _require_exact_keys(raw, top_level_keys, "story")
    title = _require_strict_text(raw.get("title"), 120, "title")
    summary = _require_strict_text(raw.get("summary"), 500, "summary")
    dramatic_arc = _require_strict_text(raw.get("dramaticArc"), 500, "dramaticArc")
    visual_style = _require_strict_text(raw.get("visualStyle"), 500, "visualStyle")
    global_direction = _require_strict_text(
        raw.get("globalDirection"),
        500,
        "globalDirection",
    )

    asset_values = _require_object(raw.get("assets"), "assets")
    _require_exact_keys(asset_values, ["asset01", "additionalAssets"], "assets")
    additional_asset_values = _require_array(
        asset_values["additionalAssets"],
        "assets.additionalAssets",
    )
    if 1 + len(additional_asset_values) > _PLANNER_ASSET_SLOT_COUNT:
        raise ValueError("VIDEO_PLAN_ASSET_LIMIT_EXCEEDED：模型提交的素材总数不能超过11项")
    indexed_asset_values = [asset_values["asset01"], *additional_asset_values]
    references_by_beat: dict[str, list[str]] = {beat_key: [] for beat_key in beat_keys}
    assets: list[PlannedAssetArguments] = []
    for index, value in enumerate(indexed_asset_values, start=1):
        asset_key = _planner_asset_key(index)
        asset, used_in_beats = _normalize_planner_asset(
            value,
            asset_key=asset_key,
            beat_keys=beat_keys,
            setting_snapshot=setting_snapshot,
        )
        assets.append(asset)
        for beat_key, is_used in used_in_beats.items():
            if is_used:
                references_by_beat[beat_key].append(asset_key)

    beat_values = _require_object(raw.get("beats"), "beats")
    _require_exact_keys(beat_values, beat_keys, "beats")
    beats = [
        _normalize_planner_story_beat(
            beat_values[beat_key],
            beat_key=beat_key,
            beat_index=index,
            beat_range=beat_range,
            referenced_asset_ids=references_by_beat[beat_key],
        )
        for index, (beat_key, beat_range) in enumerate(
            zip(beat_keys, ranges, strict=True),
            start=1,
        )
    ]

    negative_values = _require_object(raw.get("negativeConstraints"), "negativeConstraints")
    _require_exact_keys(
        negative_values,
        ["constraint01", "additionalConstraints"],
        "negativeConstraints",
    )
    additional_negative_values = _require_array(
        negative_values["additionalConstraints"],
        "negativeConstraints.additionalConstraints",
    )
    if 1 + len(additional_negative_values) > _PLANNER_NEGATIVE_CONSTRAINT_LIMIT:
        raise ValueError(
            "VIDEO_PLAN_NEGATIVE_CONSTRAINT_LIMIT_EXCEEDED：模型提交的负向约束总数不能超过18项"
        )
    negative_constraints = [
        _require_strict_text(negative_values["constraint01"], 500, "constraint01")
    ]
    negative_constraints.extend(
        _require_strict_text(value, 500, f"additionalConstraints[{index}]")
        for index, value in enumerate(additional_negative_values)
    )
    return StoryPlanStageArguments(
        title=title,
        summary=summary,
        dramaticArc=dramatic_arc,
        visualStyle=visual_style,
        globalDirection=global_direction,
        assets=assets,
        beats=beats,
        negativeConstraints=negative_constraints,
    )


def normalize_split_strict_tool_arguments(
    story: StoryPlanStageArguments,
    cinematography_raw: Mapping[str, Any],
    *,
    setting_snapshot: LongSerialSettingSnapshot,
    beat_ranges: Sequence[tuple[int, int]],
) -> ScenePlanToolArguments:
    """精确合并两阶段输出，再交给现有完整归一化器执行全部门禁。

    第一阶段必须已经完成素材、设定和动作归一化。合并前锁定第二阶段顶层字段、
    节拍集合和逐拍字段，防止同名字段覆盖掩盖供应商多写或漏写；合并后不自行
    构造最终领域模型，确保完整契约仍是唯一裁决入口。
    """

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_keys = _planner_beat_keys(ranges)
    cinematography_keys = ["cinematographyBase", "lightingSetup", "beats"]
    _require_exact_keys(cinematography_raw, cinematography_keys, "cinematography")

    cinematography_beats = _require_object(
        cinematography_raw.get("beats"),
        "cinematography.beats",
    )
    _require_exact_keys(cinematography_beats, beat_keys, "cinematography.beats")
    story_raw = _story_stage_to_strict_wire(story, beat_ranges=ranges)
    story_beats = _require_object(story_raw["beats"], "story.beats")

    merged_beats: dict[str, JsonValue] = {}
    for beat_key in beat_keys:
        story_beat = _require_object(story_beats[beat_key], f"story.beats.{beat_key}")
        cinematography_beat = _require_object(
            cinematography_beats[beat_key],
            f"cinematography.beats.{beat_key}",
        )
        cinematography_beat_keys = [
            "cameraSpec",
            "lightingCue",
            "cameraMotivation",
            "axisTransition",
            "shotProgression",
            "transition",
        ]
        _require_exact_keys(
            cinematography_beat,
            cinematography_beat_keys,
            f"cinematography.beats.{beat_key}",
        )
        merged_beats[beat_key] = cast(
            dict[str, JsonValue],
            {**story_beat, **cinematography_beat},
        )

    merged: dict[str, Any] = {
        "title": story_raw["title"],
        "summary": story_raw["summary"],
        "dramaticArc": story_raw["dramaticArc"],
        "visualStyle": story_raw["visualStyle"],
        "globalDirection": story_raw["globalDirection"],
        "cinematographyBase": cinematography_raw["cinematographyBase"],
        "lightingSetup": cinematography_raw["lightingSetup"],
        "assets": story_raw["assets"],
        "beats": merged_beats,
        "negativeConstraints": story_raw["negativeConstraints"],
    }
    return normalize_strict_tool_arguments(
        merged,
        setting_snapshot=setting_snapshot,
        beat_ranges=ranges,
    )


def normalize_strict_tool_arguments(
    raw: Mapping[str, Any],
    *,
    setting_snapshot: LongSerialSettingSnapshot,
    beat_ranges: Sequence[tuple[int, int]],
) -> ScenePlanToolArguments:
    """把固定节拍与有界数组 V2 输出确定性投影为正式规划参数。

    模型不拥有时间、身份、特征域和引用 ID 等可由服务器确定的事实；本函数只按
    槽位顺序及冻结快照生成这些字段，不摘要、不截断，也不猜测缺失值。
    """

    ranges = _validate_planner_beat_ranges(beat_ranges)
    beat_keys = _planner_beat_keys(ranges)
    envelope = PlannerToolEnvelopeV2.model_validate(raw)
    title = _require_strict_text(envelope.title, 120, "title")
    summary = _require_strict_text(envelope.summary, 500, "summary")
    dramatic_arc = _require_strict_text(envelope.dramaticArc, 500, "dramaticArc")
    visual_style = _require_strict_text(envelope.visualStyle, 500, "visualStyle")
    global_direction = _require_strict_text(
        envelope.globalDirection,
        500,
        "globalDirection",
    )
    cinematography_base = _normalize_cinematography_base(envelope.cinematographyBase)
    lighting_setup = _normalize_lighting_setup(envelope.lightingSetup)

    asset_values = _require_object(envelope.assets, "assets")
    _require_exact_keys(asset_values, ["asset01", "additionalAssets"], "assets")
    additional_asset_values = _require_array(
        asset_values["additionalAssets"],
        "assets.additionalAssets",
    )
    if 1 + len(additional_asset_values) > _PLANNER_ASSET_SLOT_COUNT:
        raise ValueError("VIDEO_PLAN_ASSET_LIMIT_EXCEEDED：模型提交的素材总数不能超过11项")
    indexed_asset_values = [asset_values["asset01"], *additional_asset_values]
    references_by_beat: dict[str, list[str]] = {beat_key: [] for beat_key in beat_keys}
    assets: list[PlannedAssetArguments] = []
    for index, value in enumerate(indexed_asset_values, start=1):
        asset_key = _planner_asset_key(index)
        asset, used_in_beats = _normalize_planner_asset(
            value,
            asset_key=asset_key,
            beat_keys=beat_keys,
            setting_snapshot=setting_snapshot,
        )
        assets.append(asset)
        for beat_key, is_used in used_in_beats.items():
            if is_used:
                references_by_beat[beat_key].append(asset_key)

    beat_values = _require_object(envelope.beats, "beats")
    _require_exact_keys(beat_values, beat_keys, "beats")
    beats: list[CameraBeatPlanArguments] = []
    previous_lighting_cue: ShotLightingCue | None = None
    for index, (beat_key, beat_range) in enumerate(
        zip(beat_keys, ranges, strict=True),
        start=1,
    ):
        beat = _normalize_planner_beat(
            beat_values[beat_key],
            beat_key=beat_key,
            beat_index=index,
            beat_range=beat_range,
            referenced_asset_ids=references_by_beat[beat_key],
            previous_lighting_cue=previous_lighting_cue,
        )
        beats.append(beat)
        previous_lighting_cue = beat.lightingCue

    negative_values = _require_object(envelope.negativeConstraints, "negativeConstraints")
    _require_exact_keys(
        negative_values,
        ["constraint01", "additionalConstraints"],
        "negativeConstraints",
    )
    additional_negative_values = _require_array(
        negative_values["additionalConstraints"],
        "negativeConstraints.additionalConstraints",
    )
    if 1 + len(additional_negative_values) > _PLANNER_NEGATIVE_CONSTRAINT_LIMIT:
        raise ValueError(
            "VIDEO_PLAN_NEGATIVE_CONSTRAINT_LIMIT_EXCEEDED：模型提交的负向约束总数不能超过18项"
        )
    negative_constraints = [
        _require_strict_text(negative_values["constraint01"], 500, "constraint01")
    ]
    negative_constraints.extend(
        _require_strict_text(
            value,
            500,
            f"additionalConstraints[{index}]",
        )
        for index, value in enumerate(additional_negative_values)
    )
    return ScenePlanToolArguments(
        title=title,
        summary=summary,
        dramaticArc=dramatic_arc,
        visualStyle=visual_style,
        globalDirection=global_direction,
        cinematographyBase=cinematography_base,
        lightingSetup=lighting_setup,
        assets=assets,
        beats=beats,
        negativeConstraints=negative_constraints,
    )


def _planner_asset_slot_schema(
    setting_snapshot: LongSerialSettingSnapshot,
    *,
    beat_keys: Sequence[str],
) -> dict[str, Any]:
    """生成单一素材对象；跨字段合法性由本地归一化器严格裁决。"""

    setting_ids = sorted({entry.id for entry in setting_snapshot.entries})
    return _strict_object_schema(
        {
            "duty": {"type": "string", "enum": list(_PLANNER_ASSET_DUTIES)},
            "modality": {
                "type": "string",
                "enum": ["image", "video", "audio"],
            },
            "bindingScope": {
                "type": "string",
                "enum": ["canon_slot", "scene_direct"],
            },
            "settingId": {
                "type": "string",
                "enum": [*setting_ids, _PLANNER_NONE_SETTING_ID],
                "description": "canon_slot 选择冻结设定 ID；scene_direct 填写 __NONE__。",
            },
            "targetEntity": _strict_text_schema(
                200,
                "canon_slot 固定填写 __CANON__；scene_direct 填写本场目标名称。",
            ),
            "keyframeRole": {
                "type": "string",
                "enum": [*_KEYFRAME_ROLES, _PLANNER_NOT_APPLICABLE_KEYFRAME_ROLE],
                "description": "仅 keyframe 使用具体角色，其余职责填写 not_applicable。",
            },
            "include": {"$ref": "#/$def/IncludeFeatureSlots"},
            "exclude": {"$ref": "#/$def/ExcludeFeatureSlots"},
            "usedInBeats": {
                "type": "string",
                "pattern": _planner_beat_usage_pattern(beat_keys),
                "description": (
                    "与节拍数量等宽的 0/1 位图；从左到右对应 beat01...beatN，"
                    "1 表示引用、0 表示不引用。"
                ),
            },
        },
        description="统一素材需求槽；本地校验职责、作用域、设定类型及模态组合。",
    )


def _planner_compact_asset_slot_schema(
    setting_snapshot: LongSerialSettingSnapshot,
) -> dict[str, Any]:
    """生成不预判逐拍引用、使用紧凑特征数组的素材对象。"""

    setting_ids = sorted({entry.id for entry in setting_snapshot.entries})
    return _strict_object_schema(
        {
            "duty": {"type": "string", "enum": list(_PLANNER_ASSET_DUTIES)},
            "modality": {
                "type": "string",
                "enum": ["image", "video", "audio"],
            },
            "bindingScope": {
                "type": "string",
                "enum": ["canon_slot", "scene_direct"],
            },
            "settingId": {
                "type": "string",
                "enum": [*setting_ids, _PLANNER_NONE_SETTING_ID],
                "description": "canon_slot 选择冻结设定 ID；scene_direct 填写 __NONE__。",
            },
            "targetEntity": _strict_text_schema(
                80,
                "canon_slot 固定填写 __CANON__；scene_direct 填写本场目标名称。",
            ),
            "keyframeRole": {
                "type": "string",
                "enum": [*_KEYFRAME_ROLES, _PLANNER_NOT_APPLICABLE_KEYFRAME_ROLE],
                "description": "仅 keyframe 使用具体角色，其余职责填写 not_applicable。",
            },
            "include": {
                "type": "array",
                "items": _strict_text_schema(80, "必须保留的一项原子视觉或声音特征。"),
                "description": "一至十二项采用特征；数量由本地归一化器校验。",
            },
            "exclude": {
                "type": "array",
                "items": _strict_text_schema(80, "必须排除的一项原子特征。"),
                "description": "零至十二项排除特征；数量由本地归一化器校验。",
            },
        },
        description="统一紧凑素材需求；逐拍引用由下一阶段决定。",
    )


def _planner_cinematography_base_schema() -> dict[str, Any]:
    """生成全场摄影基线的 strict 对象。"""

    return _strict_object_schema(
        {
            "captureFormat": {"type": "string", "enum": list(_CAPTURE_FORMATS)},
            "lensProjection": {"type": "string", "enum": list(_LENS_PROJECTIONS)},
            "frameRateFps": {"type": "integer", "enum": [24, 25, 30]},
            "shutterAngleDegrees": {
                "type": "integer",
                "enum": [90, 144, 180, 270, 360],
            },
            "axisRule": {"type": "string", "enum": list(_CAMERA_AXIS_RULES)},
            "screenDirection": {
                "type": "string",
                "enum": list(_SCREEN_DIRECTIONS),
            },
        },
        description="全场成像面、镜头投影、帧率、快门角度与轴线基线。",
    )


def _planner_lighting_setup_schema() -> dict[str, Any]:
    """生成全场环境曝光和光比基线的 strict 对象。"""

    return _strict_object_schema(
        {
            "exposureStyle": {"type": "string", "enum": list(_EXPOSURE_STYLES)},
            "ambientSource": _strict_text_schema(160, "基础环境光的画面内动机来源。"),
            "ambientColorTemperatureK": _strict_integer_schema("基础环境光色温 Kelvin。"),
            "cameraWhiteBalanceK": _strict_integer_schema(
                "摄影机白平衡 Kelvin；用于解释光源相对画面的冷暖偏移。"
            ),
            "keyToFillStops": _strict_number_schema("主光相对补光的档位差。"),
            "negativeFillSide": {
                "type": "string",
                "enum": list(_NEGATIVE_FILL_SIDES),
            },
            "atmosphere": _strict_text_schema(200, "雾、烟、潮气和空气透视基线。"),
        },
        description="全场低调/高调曝光、基础色温、光比、负补光和氛围。",
    )


def _planner_camera_position_schema() -> dict[str, Any]:
    """生成相对主体的数值机位 schema。"""

    return _strict_object_schema(
        {
            "heightCm": _strict_integer_schema("摄影机离地高度，单位厘米。"),
            "azimuthDegrees": _strict_integer_schema("相对主体正面的水平角，左侧为负、右侧为正。"),
            "elevationDegrees": _strict_integer_schema(
                "光轴相对水平线的俯仰角，俯拍为负、仰拍为正。"
            ),
            "rollDegrees": _strict_integer_schema("画面滚转角；水平画面填写 0。"),
            "subjectDistanceMeters": _strict_number_schema("摄影机到主体的距离，单位米。"),
            "axisSide": {"type": "string", "enum": list(_CAMERA_AXIS_SIDES)},
        },
        description="可复核机位高度、方位、俯仰、滚转、距离和轴线侧。",
    )


def _planner_camera_composition_schema() -> dict[str, Any]:
    """生成构图、占比与前后景层次 schema。"""

    return _strict_object_schema(
        {
            "rule": {"type": "string", "enum": list(_COMPOSITION_RULES)},
            "subjectPlacement": {
                "type": "string",
                "enum": list(_SUBJECT_PLACEMENTS),
            },
            "subjectFramePercent": _strict_integer_schema("主体约占画面高度的百分比。"),
            "headroom": {"type": "string", "enum": list(_HEADROOMS)},
            "foregroundLayer": _strict_text_schema(160, "前景遮挡或引导层；没有时写无前景。"),
            "backgroundLayer": _strict_text_schema(160, "可见背景层及其叙事作用。"),
        },
        description="画面布局、主体位置、占比、头顶空间和纵深层次。",
    )


def _planner_camera_movement_schema() -> dict[str, Any]:
    """生成唯一主运镜及其位移、旋转、速度 schema。"""

    return _strict_object_schema(
        {
            "support": {"type": "string", "enum": list(_CAMERA_SUPPORTS)},
            "movementType": {
                "type": "string",
                "enum": list(_CAMERA_MOVEMENT_TYPES),
            },
            "travelDistanceMeters": _strict_number_schema(
                "摄影机实际位移米数；锁定、摇摄、变焦填 0。"
            ),
            "rotationDegrees": _strict_number_schema("摄影机旋转角；纯位移、锁定、变焦填 0。"),
            "speed": {"type": "string", "enum": list(_CAMERA_MOVEMENT_SPEEDS)},
            "easing": {"type": "string", "enum": list(_CAMERA_MOVEMENT_EASINGS)},
        },
        description="只允许一个主运镜，不得把推拉摇移环绕写进同一拍。",
    )


def _planner_camera_focus_schema() -> dict[str, Any]:
    """生成景深和起止焦点 schema。"""

    return _strict_object_schema(
        {
            "depthOfField": {"type": "string", "enum": list(_DEPTHS_OF_FIELD)},
            "startTarget": _strict_text_schema(120, "镜头开始时的清晰焦点对象。"),
            "endTarget": _strict_text_schema(
                120,
                "拉焦时的结束对象；locked 模式由服务器按 startTarget 归一化。",
            ),
            "transition": {"type": "string", "enum": list(_FOCUS_TRANSITIONS)},
            "rackDurationSeconds": _strict_number_schema(
                "拉焦持续秒数；locked 模式由服务器归一化为 0。"
            ),
        },
        description="浅/中/深景深及锁焦或拉焦计划。",
    )


def _planner_shot_camera_schema() -> dict[str, Any]:
    """生成单拍镜头、机位、构图、运动和焦点 schema。"""

    return _strict_object_schema(
        {
            "lensType": {"type": "string", "enum": list(_CAMERA_LENS_TYPES)},
            "focalLengthMm": _strict_integer_schema("起始焦距毫米数。"),
            "endFocalLengthMm": _strict_integer_schema(
                "结束焦距；定焦与起始值相同，变焦必须不同。"
            ),
            "tStop": _strict_number_schema("镜头 T 值。"),
            "position": {"$ref": "#/$def/CameraPosition"},
            "composition": {"$ref": "#/$def/CameraComposition"},
            "movement": {"$ref": "#/$def/CameraMovement"},
            "focus": {"$ref": "#/$def/CameraFocus"},
        },
        description="单拍专业摄影规格；数值用于表达导演意图并由本地门禁复核。",
    )


def _planner_light_source_schema(
    *,
    roles: Sequence[LightRole] = _LIGHT_ROLES,
) -> dict[str, Any]:
    """生成一盏动机灯及其可见结果 schema。"""

    return _strict_object_schema(
        {
            "role": {"type": "string", "enum": list(roles)},
            "motivatedBy": _strict_text_schema(160, "画面内可解释该灯的窗、灯或光束。"),
            "direction": {"type": "string", "enum": list(_LIGHT_DIRECTIONS)},
            "azimuthDegrees": _strict_integer_schema("灯相对主体正面的水平角。"),
            "elevationDegrees": _strict_integer_schema("灯相对主体水平面的高度角。"),
            "quality": {"type": "string", "enum": list(_LIGHT_QUALITIES)},
            "delivery": {"type": "string", "enum": list(_LIGHT_DELIVERIES)},
            "colorTemperatureK": _strict_integer_schema("光源色温 Kelvin。"),
            "relativeExposureStops": _strict_number_schema("相对场景基准曝光的档位。"),
            "beamAngleDegrees": _strict_integer_schema("光束角度；大面积软光可接近 180。"),
            "falloff": {"type": "string", "enum": list(_LIGHT_FALLOFFS)},
            "spillControl": _strict_text_schema(160, "遮扉、黑旗或限定溢光的方式。"),
            "visibleResult": _strict_text_schema(240, "这盏灯在主体、背景或雾中的可见结果。"),
        },
        description="一盏有角色、有动机、有光位与画面结果的灯。",
    )


def _planner_shot_lighting_cue_schema(
    *,
    continuity_mode: Literal["establish", "motivated_change"],
) -> dict[str, Any]:
    """生成建立或有动机变化拍的完整专业灯光 schema。"""

    return _strict_object_schema(
        {
            "continuityMode": {
                "type": "string",
                "enum": [continuity_mode],
            },
            "motivatedChange": _strict_text_schema(
                160,
                (
                    "说明首拍建立的画内光源。"
                    if continuity_mode == "establish"
                    else "说明触发灯光变化的画内可见事件。"
                ),
            ),
            "keyLight": {"$ref": "#/$def/LightSource"},
            "fillStrategy": {"type": "string", "enum": list(_FILL_STRATEGIES)},
            "fillDirection": {"type": "string", "enum": list(_LIGHT_DIRECTIONS)},
            "fillRelativeStops": _strict_number_schema("补光相对基准曝光；无补光固定填写 -8。"),
            "edgeLight": {
                "anyOf": [
                    _planner_light_source_schema(roles=("rim", "background", "practical")),
                    _unused_string_schema(),
                ],
                "description": "边缘/背景/实景光，未使用时填写 __UNUSED__。",
            },
            "atmosphere": _strict_text_schema(200, "本拍雾、烟、潮气和体积光状态。"),
            "visibleResult": _strict_text_schema(240, "整拍灯光在画面中的最终可见结果。"),
        },
        description=(
            "首拍完整建立有动机灯光。"
            if continuity_mode == "establish"
            else "仅在画内可见事件触发时完整声明变化后的专业灯光事实。"
        ),
    )


def _build_planner_compact_story_beat_definitions(
    beat_ranges: Sequence[tuple[int, int]],
    *,
    asset_count: int,
) -> dict[str, dict[str, Any]]:
    """为第二阶段生成紧凑故事节拍与素材位图定义。"""

    if not 1 <= asset_count <= _PLANNER_ASSET_SLOT_COUNT:
        raise ValueError("故事节拍 strict schema 的素材数量必须为1至11项")
    definitions: dict[str, dict[str, Any]] = {}
    for index, (start, end) in enumerate(beat_ranges, start=1):
        properties: dict[str, Any] = {
            "dramaticPurpose": _strict_text_schema(
                160,
                "本拍改变观众所知、人物权力或情绪状态的唯一戏剧任务。",
            ),
            "performanceDirection": _strict_text_schema(
                200,
                "可见、可表演的神态、呼吸、视线与身体反应。",
            ),
            "blocking": _strict_text_schema(
                200,
                "人物和关键物在画面空间中的起点、路径与落点。",
            ),
            "primaryAction": {"$ref": "#/$def/ActionUnit"},
        }
        if _planner_action_capacity(start, end) == 2:
            properties["secondaryAction"] = {
                "anyOf": [
                    _planner_action_unit_schema(),
                    _unused_string_schema(),
                ],
                "description": "第二动作单元；不需要时填写字符串 __UNUSED__。",
            }
        properties.update(
            {
                "actionComplexity": {
                    "type": "string",
                    "enum": list(_DIRECTOR_ACTION_COMPLEXITIES),
                },
                "sound": _strict_text_schema(240, "与本拍画面同步的声音，不写音乐。"),
                "assetUsage": {
                    "type": "string",
                    "pattern": rf"^[01]{{{asset_count}}}$",
                    "description": (
                        "与第一阶段素材数量等宽的0/1位图；从左到右对应asset01...assetN。"
                    ),
                },
            }
        )
        definitions[_planner_beat_definition_name(index)] = _strict_object_schema(
            properties,
            description=f"第 {index} 拍故事事实，服务器锁定时段为 {start}-{end} 秒。",
        )
    return definitions


def _build_planner_story_beat_definitions(
    beat_ranges: Sequence[tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    """为第一阶段生成逐拍叙事、调度、动作和声音定义。"""

    definitions: dict[str, dict[str, Any]] = {}
    for index, (start, end) in enumerate(beat_ranges, start=1):
        properties: dict[str, Any] = {
            "dramaticPurpose": _strict_text_schema(
                240,
                "本拍改变观众所知、人物权力或情绪状态的唯一戏剧任务。",
            ),
            "performanceDirection": _strict_text_schema(
                300,
                "可见、可表演的神态、呼吸、视线与身体反应，不写抽象内心。",
            ),
            "blocking": _strict_text_schema(
                300,
                "人物和关键物在画面空间中的起点、移动路径与落点。",
            ),
            "primaryAction": {"$ref": "#/$def/ActionUnit"},
        }
        if _planner_action_capacity(start, end) == 2:
            properties["secondaryAction"] = {
                "anyOf": [
                    _planner_action_unit_schema(),
                    _unused_string_schema(),
                ],
                "description": "第二动作单元；不需要时填写字符串 __UNUSED__。",
            }
        properties.update(
            {
                "actionComplexity": {
                    "type": "string",
                    "enum": list(_DIRECTOR_ACTION_COMPLEXITIES),
                },
                "sound": _strict_text_schema(500, "与本拍画面同步的声音，不写音乐。"),
            }
        )
        definitions[_planner_beat_definition_name(index)] = _strict_object_schema(
            properties,
            description=f"第 {index} 拍叙事与调度，服务器锁定时段为 {start}-{end} 秒。",
        )
    return definitions


def _build_planner_cinematography_beat_definitions(
    beat_ranges: Sequence[tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    """为第二阶段生成逐拍摄影、灯光、景别和转场定义。"""

    definitions: dict[str, dict[str, Any]] = {}
    for index, (start, end) in enumerate(beat_ranges, start=1):
        if index == 1:
            lighting_cue_schema: dict[str, Any] = {"$ref": "#/$def/EstablishLightingCue"}
        else:
            lighting_cue_schema = {
                "anyOf": [
                    {
                        "type": "string",
                        "enum": [_PLANNER_INHERIT_LIGHTING_SENTINEL],
                    },
                    # DeepSeek strict 的 anyOf 对象分支不能使用裸 $ref，必须内联完整形状。
                    _planner_shot_lighting_cue_schema(continuity_mode="motivated_change"),
                ],
                "description": ("灯光不变时填写 __INHERIT__；仅有画内可见触发事件时提交完整变化。"),
            }
        properties: dict[str, Any] = {
            "cameraSpec": {"$ref": "#/$def/ShotCameraSpec"},
            "lightingCue": lighting_cue_schema,
            "cameraMotivation": _strict_text_schema(
                240,
                "触发摄影机响应的画面内可见事件，以及该响应服务的叙事理由；"
                "不复述 cameraSpec 或结束落幅。",
            ),
            "axisTransition": {
                "type": "string",
                "enum": list(_AXIS_TRANSITIONS),
                "description": "首拍固定 hold；其余拍声明轴线保持或可审核的越轴重置。",
            },
            "shotProgression": {"$ref": "#/$def/ShotProgression"},
            "transition": _strict_text_schema(
                200,
                "进入下一拍的转场；没有转场时填写 __UNUSED__。",
            ),
        }
        definitions[_planner_beat_definition_name(index)] = _strict_object_schema(
            properties,
            description=f"第 {index} 拍摄影与灯光，服务器锁定时段为 {start}-{end} 秒。",
        )
    return definitions


def _build_planner_beat_definitions(
    beat_ranges: Sequence[tuple[int, int]],
) -> dict[str, dict[str, Any]]:
    """逐拍生成动作容量不同的固定对象定义。"""

    definitions: dict[str, dict[str, Any]] = {}
    for index, (start, end) in enumerate(beat_ranges, start=1):
        action_capacity = _planner_action_capacity(start, end)
        if index == 1:
            lighting_cue_schema: dict[str, Any] = {"$ref": "#/$def/EstablishLightingCue"}
        else:
            lighting_cue_schema = {
                "anyOf": [
                    {
                        "type": "string",
                        "enum": [_PLANNER_INHERIT_LIGHTING_SENTINEL],
                    },
                    # DeepSeek strict 的 anyOf 对象分支不能使用裸 $ref，必须内联完整形状。
                    _planner_shot_lighting_cue_schema(continuity_mode="motivated_change"),
                ],
                "description": ("灯光不变时填写 __INHERIT__；仅有画内可见触发事件时提交完整变化。"),
            }
        properties: dict[str, Any] = {
            # 1.3 不再让模型同时提交自由机位文字与结构化摄影两套事实。
            "cameraSpec": {"$ref": "#/$def/ShotCameraSpec"},
            "lightingCue": lighting_cue_schema,
            "dramaticPurpose": _strict_text_schema(
                240,
                "本拍改变观众所知、人物权力或情绪状态的唯一戏剧任务。",
            ),
            "performanceDirection": _strict_text_schema(
                300,
                "可见、可表演的神态、呼吸、视线与身体反应，不写抽象内心。",
            ),
            "blocking": _strict_text_schema(
                300,
                "人物和关键物在画面空间中的起点、移动路径与落点。",
            ),
            "cameraMotivation": _strict_text_schema(
                240,
                "触发摄影机响应的画面内可见事件，以及该响应服务的叙事理由；"
                "不复述 cameraSpec 或结束落幅。",
            ),
            "axisTransition": {
                "type": "string",
                "enum": list(_AXIS_TRANSITIONS),
                "description": "首拍固定 hold；其余拍声明轴线保持或可审核的越轴重置。",
            },
            "primaryAction": {"$ref": "#/$def/ActionUnit"},
        }
        if action_capacity == 2:
            properties["secondaryAction"] = {
                "anyOf": [
                    _planner_action_unit_schema(),
                    _unused_string_schema(),
                ],
                "description": "第二动作单元；不需要时填写字符串 __UNUSED__。",
            }
        properties.update(
            {
                "actionComplexity": {
                    "type": "string",
                    "enum": list(_DIRECTOR_ACTION_COMPLEXITIES),
                },
                "shotProgression": {"$ref": "#/$def/ShotProgression"},
                "sound": _strict_text_schema(500, "与本拍画面同步的声音，不写音乐。"),
                "transition": _strict_text_schema(
                    200,
                    "进入下一拍的转场；没有转场时填写 __UNUSED__。",
                ),
            }
        )
        definitions[_planner_beat_definition_name(index)] = _strict_object_schema(
            properties,
            description=f"第 {index} 拍，服务器锁定时段为 {start}-{end} 秒。",
        )
    return definitions


def _normalize_compact_planner_asset(
    value: JsonValue,
    *,
    asset_key: str,
    setting_snapshot: LongSerialSettingSnapshot,
) -> PlannedAssetArguments:
    """复用既有素材语义门禁，归一化不含逐拍引用的紧凑素材。"""

    item = _require_object(value, asset_key)
    expected_keys = [
        "duty",
        "modality",
        "bindingScope",
        "settingId",
        "targetEntity",
        "keyframeRole",
        "include",
        "exclude",
    ]
    _require_exact_keys(item, expected_keys, asset_key)
    include_values = _require_array(item.get("include"), f"{asset_key}.include")
    exclude_values = _require_array(item.get("exclude"), f"{asset_key}.exclude")
    if not 1 <= len(include_values) <= _PLANNER_FEATURE_SLOT_COUNT:
        raise ValueError(f"{asset_key}.include 必须为1至12项")
    if len(exclude_values) > _PLANNER_FEATURE_SLOT_COUNT:
        raise ValueError(f"{asset_key}.exclude 不能超过12项")
    include_features = [
        _require_strict_text(value, 80, f"{asset_key}.include[{index}]")
        for index, value in enumerate(include_values)
    ]
    exclude_features = [
        _require_strict_text(value, 80, f"{asset_key}.exclude[{index}]")
        for index, value in enumerate(exclude_values)
    ]
    _require_strict_text(item.get("targetEntity"), 80, f"{asset_key}.targetEntity")

    # 旧归一化器仍是职责、模态、作用域与冻结设定映射的唯一语义裁决入口。
    compatibility_wire: dict[str, JsonValue] = {
        **item,
        "include": _feature_values_to_strict_slots(include_features),
        "exclude": _feature_values_to_strict_slots(exclude_features),
        "usedInBeats": "1",
    }
    asset, _used_in_beats = _normalize_planner_asset(
        compatibility_wire,
        asset_key=asset_key,
        beat_keys=["beat01"],
        setting_snapshot=setting_snapshot,
    )
    return asset


def _normalize_planner_asset(
    value: JsonValue,
    *,
    asset_key: str,
    beat_keys: Sequence[str],
    setting_snapshot: LongSerialSettingSnapshot,
) -> tuple[PlannedAssetArguments, dict[str, bool]]:
    """归一化一个非空素材槽，并返回逐拍使用事实。"""

    item = _require_object(value, asset_key)
    _require_exact_keys(
        item,
        [
            "duty",
            "modality",
            "bindingScope",
            "settingId",
            "targetEntity",
            "keyframeRole",
            "include",
            "exclude",
            "usedInBeats",
        ],
        asset_key,
    )
    duty = cast(
        PlannerAssetDuty,
        _require_choice(item.get("duty"), _PLANNER_ASSET_DUTIES, f"{asset_key}.duty"),
    )
    scope = cast(
        PlannerAssetScope,
        _require_choice(
            item.get("bindingScope"),
            ("canon_slot", "scene_direct"),
            f"{asset_key}.bindingScope",
        ),
    )
    modality = cast(
        AssetModality,
        _require_choice(
            item.get("modality"),
            _ALLOWED_MODALITIES_BY_DUTY[duty],
            f"{asset_key}.modality",
        ),
    )
    setting_id = _require_enum_string(item.get("settingId"), f"{asset_key}.settingId")
    known_entries = [entry for entry in setting_snapshot.entries if entry.id == setting_id]
    if setting_id != _PLANNER_NONE_SETTING_ID and not known_entries:
        raise ValueError(f"设定引用不存在：{setting_id}")
    target_value = _require_strict_text(
        item.get("targetEntity"),
        200,
        f"{asset_key}.targetEntity",
    )
    role_value = _require_choice(
        item.get("keyframeRole"),
        (*_KEYFRAME_ROLES, _PLANNER_NOT_APPLICABLE_KEYFRAME_ROLE),
        f"{asset_key}.keyframeRole",
    )

    setting_reference: SettingReference | None = None
    keyframe_role: KeyframeRole | None = None
    if scope == "canon_slot":
        setting_kind = _SETTING_KIND_BY_CANON_DUTY.get(duty)
        if setting_kind is None:
            raise ValueError(f"{asset_key} 的 {duty} 职责不支持 canon_slot")
        if setting_id == _PLANNER_NONE_SETTING_ID:
            raise ValueError(f"{asset_key} 的 canon_slot 必须选择冻结设定 ID")
        if target_value != _PLANNER_CANON_TARGET:
            raise ValueError(f"{asset_key} 的 canon_slot targetEntity 必须是 __CANON__")
        if role_value != _PLANNER_NOT_APPLICABLE_KEYFRAME_ROLE:
            raise ValueError(f"{asset_key} 的 canon_slot keyframeRole 必须是 not_applicable")
        actual_kinds = {entry.kind for entry in known_entries}
        if setting_kind not in actual_kinds:
            raise ValueError(f"{asset_key} 的 {duty} 职责必须绑定 {setting_kind} 类型设定")
        setting_reference = SettingReference(kind=setting_kind, id=setting_id)
        setting = setting_snapshot.resolve(setting_reference)
        target_entity = setting.name
    else:
        if setting_id != _PLANNER_NONE_SETTING_ID:
            raise ValueError(f"{asset_key} 的 scene_direct settingId 必须是 __NONE__")
        if target_value in {
            _PLANNER_UNUSED_SENTINEL,
            _PLANNER_NONE_SETTING_ID,
            _PLANNER_CANON_TARGET,
        }:
            raise ValueError(f"{asset_key} 的 scene_direct 必须填写真实 targetEntity")
        if duty == "keyframe":
            if role_value == _PLANNER_NOT_APPLICABLE_KEYFRAME_ROLE:
                raise ValueError(f"{asset_key} 的 keyframe 必须声明具体 keyframeRole")
            keyframe_role = cast(
                KeyframeRole,
                role_value,
            )
        elif role_value != _PLANNER_NOT_APPLICABLE_KEYFRAME_ROLE:
            raise ValueError(f"{asset_key} 的非 keyframe 职责必须使用 not_applicable")
        target_entity = target_value

    include_features = _normalize_text_slots(
        item.get("include"),
        prefix="feature",
        count=_PLANNER_FEATURE_SLOT_COUNT,
        first_required=True,
        max_characters=200,
        label=f"{asset_key}.include",
    )
    exclude_features = _normalize_text_slots(
        item.get("exclude"),
        prefix="feature",
        count=_PLANNER_FEATURE_SLOT_COUNT,
        first_required=False,
        max_characters=200,
        label=f"{asset_key}.exclude",
    )
    used_in_beats = _normalize_beat_usage(
        item.get("usedInBeats"),
        beat_keys=beat_keys,
        label=f"{asset_key}.usedInBeats",
    )
    asset = PlannedAssetArguments(
        assetId=asset_key,
        modality=modality,
        duty=duty,
        bindingScope=scope,
        settingReference=setting_reference,
        featureDomain=cast(AssetFeatureDomain, _FEATURE_DOMAIN_BY_DUTY[duty]),
        keyframeRole=keyframe_role,
        targetEntity=target_entity,
        includeFeatures=include_features,
        excludeFeatures=exclude_features,
    )
    return asset, used_in_beats


def _normalize_cinematography_base(value: JsonValue) -> CinematographyBase:
    """把 strict 摄影基线投影为类型化领域值。"""

    item = _require_object(value, "cinematographyBase")
    keys = [
        "captureFormat",
        "lensProjection",
        "frameRateFps",
        "shutterAngleDegrees",
        "axisRule",
        "screenDirection",
    ]
    _require_exact_keys(item, keys, "cinematographyBase")
    return CinematographyBase(
        captureFormat=cast(
            CaptureFormat,
            _require_choice(item["captureFormat"], _CAPTURE_FORMATS, "captureFormat"),
        ),
        lensProjection=cast(
            LensProjection,
            _require_choice(item["lensProjection"], _LENS_PROJECTIONS, "lensProjection"),
        ),
        frameRateFps=cast(
            Literal[24, 25, 30],
            _require_int_choice(item["frameRateFps"], (24, 25, 30), "frameRateFps"),
        ),
        shutterAngleDegrees=cast(
            Literal[90, 144, 180, 270, 360],
            _require_int_choice(
                item["shutterAngleDegrees"],
                (90, 144, 180, 270, 360),
                "shutterAngleDegrees",
            ),
        ),
        axisRule=cast(
            CameraAxisRule,
            _require_choice(item["axisRule"], _CAMERA_AXIS_RULES, "axisRule"),
        ),
        screenDirection=cast(
            ScreenDirection,
            _require_choice(
                item["screenDirection"],
                _SCREEN_DIRECTIONS,
                "screenDirection",
            ),
        ),
    )


def _normalize_lighting_setup(value: JsonValue) -> LightingSetup:
    """把全场曝光、环境色温和光比基线投影为领域值。"""

    item = _require_object(value, "lightingSetup")
    keys = [
        "exposureStyle",
        "ambientSource",
        "ambientColorTemperatureK",
        "cameraWhiteBalanceK",
        "keyToFillStops",
        "negativeFillSide",
        "atmosphere",
    ]
    _require_exact_keys(item, keys, "lightingSetup")
    return LightingSetup(
        exposureStyle=cast(
            ExposureStyle,
            _require_choice(item["exposureStyle"], _EXPOSURE_STYLES, "exposureStyle"),
        ),
        ambientSource=_require_strict_text(
            item["ambientSource"], 160, "lightingSetup.ambientSource"
        ),
        ambientColorTemperatureK=_require_integer(
            item["ambientColorTemperatureK"],
            "lightingSetup.ambientColorTemperatureK",
        ),
        cameraWhiteBalanceK=_require_integer(
            item["cameraWhiteBalanceK"],
            "lightingSetup.cameraWhiteBalanceK",
        ),
        keyToFillStops=_require_number(item["keyToFillStops"], "lightingSetup.keyToFillStops"),
        negativeFillSide=cast(
            NegativeFillSide,
            _require_choice(
                item["negativeFillSide"],
                _NEGATIVE_FILL_SIDES,
                "lightingSetup.negativeFillSide",
            ),
        ),
        atmosphere=_require_strict_text(item["atmosphere"], 200, "lightingSetup.atmosphere"),
    )


def _normalize_shot_camera_spec(value: JsonValue | None, label: str) -> ShotCameraSpec:
    """校验单拍镜头、机位、构图、运动和焦点的固定对象。"""

    item = _require_object(value, label)
    keys = [
        "lensType",
        "focalLengthMm",
        "endFocalLengthMm",
        "tStop",
        "position",
        "composition",
        "movement",
        "focus",
    ]
    _require_exact_keys(item, keys, label)
    return ShotCameraSpec(
        lensType=cast(
            CameraLensType,
            _require_choice(item["lensType"], _CAMERA_LENS_TYPES, f"{label}.lensType"),
        ),
        focalLengthMm=_require_integer(item["focalLengthMm"], f"{label}.focalLengthMm"),
        endFocalLengthMm=_require_integer(item["endFocalLengthMm"], f"{label}.endFocalLengthMm"),
        tStop=_require_number(item["tStop"], f"{label}.tStop"),
        position=_normalize_camera_position(item["position"], f"{label}.position"),
        composition=_normalize_camera_composition(item["composition"], f"{label}.composition"),
        movement=_normalize_camera_movement(item["movement"], f"{label}.movement"),
        focus=_normalize_camera_focus(item["focus"], f"{label}.focus"),
    )


def _normalize_camera_position(value: JsonValue, label: str) -> CameraPositionSpec:
    """校验数值机位。"""

    item = _require_object(value, label)
    keys = [
        "heightCm",
        "azimuthDegrees",
        "elevationDegrees",
        "rollDegrees",
        "subjectDistanceMeters",
        "axisSide",
    ]
    _require_exact_keys(item, keys, label)
    return CameraPositionSpec(
        heightCm=_require_integer(item["heightCm"], f"{label}.heightCm"),
        azimuthDegrees=_require_integer(item["azimuthDegrees"], f"{label}.azimuthDegrees"),
        elevationDegrees=_require_integer(item["elevationDegrees"], f"{label}.elevationDegrees"),
        rollDegrees=_require_integer(item["rollDegrees"], f"{label}.rollDegrees"),
        subjectDistanceMeters=_require_number(
            item["subjectDistanceMeters"], f"{label}.subjectDistanceMeters"
        ),
        axisSide=cast(
            CameraAxisSide,
            _require_choice(item["axisSide"], _CAMERA_AXIS_SIDES, f"{label}.axisSide"),
        ),
    )


def _normalize_camera_composition(value: JsonValue, label: str) -> CameraCompositionSpec:
    """校验主体布局、占比和前后景层次。"""

    item = _require_object(value, label)
    keys = [
        "rule",
        "subjectPlacement",
        "subjectFramePercent",
        "headroom",
        "foregroundLayer",
        "backgroundLayer",
    ]
    _require_exact_keys(item, keys, label)
    return CameraCompositionSpec(
        rule=cast(
            CompositionRule,
            _require_choice(item["rule"], _COMPOSITION_RULES, f"{label}.rule"),
        ),
        subjectPlacement=cast(
            SubjectPlacement,
            _require_choice(
                item["subjectPlacement"],
                _SUBJECT_PLACEMENTS,
                f"{label}.subjectPlacement",
            ),
        ),
        subjectFramePercent=_require_integer(
            item["subjectFramePercent"], f"{label}.subjectFramePercent"
        ),
        headroom=cast(
            Headroom,
            _require_choice(item["headroom"], _HEADROOMS, f"{label}.headroom"),
        ),
        foregroundLayer=_require_strict_text(
            item["foregroundLayer"], 160, f"{label}.foregroundLayer"
        ),
        backgroundLayer=_require_strict_text(
            item["backgroundLayer"], 160, f"{label}.backgroundLayer"
        ),
    )


def _normalize_camera_movement(value: JsonValue, label: str) -> CameraMovementSpec:
    """校验支撑系统和唯一主运镜。"""

    item = _require_object(value, label)
    keys = [
        "support",
        "movementType",
        "travelDistanceMeters",
        "rotationDegrees",
        "speed",
        "easing",
    ]
    _require_exact_keys(item, keys, label)
    return CameraMovementSpec(
        support=cast(
            CameraSupport,
            _require_choice(item["support"], _CAMERA_SUPPORTS, f"{label}.support"),
        ),
        movementType=cast(
            CameraMovementType,
            _require_choice(
                item["movementType"],
                _CAMERA_MOVEMENT_TYPES,
                f"{label}.movementType",
            ),
        ),
        travelDistanceMeters=_require_number(
            item["travelDistanceMeters"], f"{label}.travelDistanceMeters"
        ),
        rotationDegrees=_require_number(item["rotationDegrees"], f"{label}.rotationDegrees"),
        speed=cast(
            CameraMovementSpeed,
            _require_choice(item["speed"], _CAMERA_MOVEMENT_SPEEDS, f"{label}.speed"),
        ),
        easing=cast(
            CameraMovementEasing,
            _require_choice(item["easing"], _CAMERA_MOVEMENT_EASINGS, f"{label}.easing"),
        ),
    )


def _normalize_camera_focus(value: JsonValue, label: str) -> CameraFocusSpec:
    """校验景深和焦点迁移。"""

    item = _require_object(value, label)
    keys = [
        "depthOfField",
        "startTarget",
        "endTarget",
        "transition",
        "rackDurationSeconds",
    ]
    _require_exact_keys(item, keys, label)
    transition = cast(
        FocusTransition,
        _require_choice(item["transition"], _FOCUS_TRANSITIONS, f"{label}.transition"),
    )
    start_target = _require_strict_text(item["startTarget"], 120, f"{label}.startTarget")
    if transition == "locked":
        # 固定 strict 对象要求模型提交终点和时长，但锁焦时它们不是新的导演事实。
        return CameraFocusSpec(
            depthOfField=cast(
                DepthOfField,
                _require_choice(
                    item["depthOfField"],
                    _DEPTHS_OF_FIELD,
                    f"{label}.depthOfField",
                ),
            ),
            startTarget=start_target,
            endTarget=start_target,
            transition="locked",
            rackDurationSeconds=0,
        )
    return CameraFocusSpec(
        depthOfField=cast(
            DepthOfField,
            _require_choice(item["depthOfField"], _DEPTHS_OF_FIELD, f"{label}.depthOfField"),
        ),
        startTarget=start_target,
        endTarget=_require_strict_text(item["endTarget"], 120, f"{label}.endTarget"),
        transition=transition,
        rackDurationSeconds=_require_number(
            item["rackDurationSeconds"], f"{label}.rackDurationSeconds"
        ),
    )


def _normalize_light_source(value: JsonValue, label: str) -> LightSourceSpec:
    """校验一盏灯的动机、方向、光质、色温和画面结果。"""

    item = _require_object(value, label)
    keys = [
        "role",
        "motivatedBy",
        "direction",
        "azimuthDegrees",
        "elevationDegrees",
        "quality",
        "delivery",
        "colorTemperatureK",
        "relativeExposureStops",
        "beamAngleDegrees",
        "falloff",
        "spillControl",
        "visibleResult",
    ]
    _require_exact_keys(item, keys, label)
    return LightSourceSpec(
        role=cast(
            LightRole,
            _require_choice(item["role"], _LIGHT_ROLES, f"{label}.role"),
        ),
        motivatedBy=_require_strict_text(item["motivatedBy"], 160, f"{label}.motivatedBy"),
        direction=cast(
            LightDirection,
            _require_choice(item["direction"], _LIGHT_DIRECTIONS, f"{label}.direction"),
        ),
        azimuthDegrees=_require_integer(item["azimuthDegrees"], f"{label}.azimuthDegrees"),
        elevationDegrees=_require_integer(item["elevationDegrees"], f"{label}.elevationDegrees"),
        quality=cast(
            LightQuality,
            _require_choice(item["quality"], _LIGHT_QUALITIES, f"{label}.quality"),
        ),
        delivery=cast(
            LightDelivery,
            _require_choice(item["delivery"], _LIGHT_DELIVERIES, f"{label}.delivery"),
        ),
        colorTemperatureK=_require_integer(item["colorTemperatureK"], f"{label}.colorTemperatureK"),
        relativeExposureStops=_require_number(
            item["relativeExposureStops"], f"{label}.relativeExposureStops"
        ),
        beamAngleDegrees=_require_integer(item["beamAngleDegrees"], f"{label}.beamAngleDegrees"),
        falloff=cast(
            LightFalloff,
            _require_choice(item["falloff"], _LIGHT_FALLOFFS, f"{label}.falloff"),
        ),
        spillControl=_require_strict_text(item["spillControl"], 160, f"{label}.spillControl"),
        visibleResult=_require_strict_text(item["visibleResult"], 240, f"{label}.visibleResult"),
    )


def _copy_previous_lighting_cue(
    inherited_from: ShotLightingCue | None,
    label: str,
) -> ShotLightingCue:
    """把紧凑哨兵或旧版 inherit 统一投影为上一拍的权威灯光事实。"""

    if inherited_from is None:
        raise ValueError(f"{label} 使用 inherit 时必须存在上一拍灯光")
    return inherited_from.model_copy(
        update={
            "continuityMode": "inherit",
            "motivatedChange": "延续上一拍全部灯光事实",
        },
        deep=True,
    )


def _normalize_shot_lighting_cue(
    value: JsonValue | None,
    label: str,
    *,
    inherited_from: ShotLightingCue | None,
) -> ShotLightingCue:
    """校验完整灯光；紧凑哨兵或旧版 inherit 都复制上一拍权威事实。"""

    if value == _PLANNER_INHERIT_LIGHTING_SENTINEL:
        return _copy_previous_lighting_cue(inherited_from, label)

    item = _require_object(value, label)
    keys = [
        "continuityMode",
        "motivatedChange",
        "keyLight",
        "fillStrategy",
        "fillDirection",
        "fillRelativeStops",
        "edgeLight",
        "atmosphere",
        "visibleResult",
    ]
    _require_exact_keys(item, keys, label)
    continuity_mode = cast(
        LightingContinuityMode,
        _require_choice(
            item["continuityMode"],
            _LIGHTING_CONTINUITY_MODES,
            f"{label}.continuityMode",
        ),
    )
    if continuity_mode == "inherit":
        # 兼容读取已经产生的完整 inherit wire；其中重复灯光字段仍不具权威性。
        return _copy_previous_lighting_cue(inherited_from, label)
    if inherited_from is None and continuity_mode != "establish":
        raise ValueError(f"{label} 首拍必须使用 establish 建立灯光")
    if inherited_from is not None and continuity_mode == "establish":
        raise ValueError(f"{label} 只有首拍可以使用 establish 灯光模式")

    edge_value = item["edgeLight"]
    edge_light = (
        None
        if _is_unused_slot(edge_value)
        else _normalize_light_source(edge_value, f"{label}.edgeLight")
    )
    fill_strategy = cast(
        FillStrategy,
        _require_choice(item["fillStrategy"], _FILL_STRATEGIES, f"{label}.fillStrategy"),
    )
    fill_direction = (
        None
        if fill_strategy == "none"
        else cast(
            LightDirection,
            _require_choice(item["fillDirection"], _LIGHT_DIRECTIONS, f"{label}.fillDirection"),
        )
    )
    return ShotLightingCue(
        continuityMode=continuity_mode,
        motivatedChange=_require_strict_text(
            item["motivatedChange"], 160, f"{label}.motivatedChange"
        ),
        keyLight=_normalize_light_source(item["keyLight"], f"{label}.keyLight"),
        fillStrategy=fill_strategy,
        fillDirection=fill_direction,
        fillRelativeStops=_require_number(item["fillRelativeStops"], f"{label}.fillRelativeStops"),
        edgeLight=edge_light,
        atmosphere=_require_strict_text(item["atmosphere"], 200, f"{label}.atmosphere"),
        visibleResult=_require_strict_text(item["visibleResult"], 240, f"{label}.visibleResult"),
    )


def _render_legacy_camera_angle(camera: ShotCameraSpec) -> str:
    """只为旧读取界面生成机位镜像，不参与新导演事实判断。"""

    position = camera.position
    return (
        f"机位高{position.heightCm}cm，方位{position.azimuthDegrees}°，"
        f"俯仰{position.elevationDegrees}°，轴线侧{position.axisSide}"
    )


def _render_legacy_camera_movement(camera: ShotCameraSpec) -> str:
    """只为旧读取界面生成主运镜镜像。"""

    movement = camera.movement
    return (
        f"{movement.support}上的{movement.movementType}，"
        f"位移{movement.travelDistanceMeters:g}m，旋转{movement.rotationDegrees:g}°，"
        f"速度{movement.speed}，{movement.easing}"
    )


def _normalize_compact_story_beat(
    value: JsonValue,
    *,
    beat_key: str,
    beat_index: int,
    beat_range: tuple[int, int],
    asset_ids: Sequence[str],
) -> StoryBeatPlanArguments:
    """归一化紧凑故事节拍，并从素材位图派生逐拍稳定引用。"""

    item = _require_object(value, beat_key)
    start, end = beat_range
    expected_keys = [
        "dramaticPurpose",
        "performanceDirection",
        "blocking",
        "primaryAction",
        "actionComplexity",
        "sound",
        "assetUsage",
    ]
    if _planner_action_capacity(start, end) == 2:
        expected_keys.append("secondaryAction")
    _require_exact_keys(item, expected_keys, beat_key)
    _require_strict_text(item.get("dramaticPurpose"), 160, f"{beat_key}.dramaticPurpose")
    _require_strict_text(
        item.get("performanceDirection"),
        200,
        f"{beat_key}.performanceDirection",
    )
    _require_strict_text(item.get("blocking"), 200, f"{beat_key}.blocking")
    _require_strict_text(item.get("sound"), 240, f"{beat_key}.sound")
    usage = item.get("assetUsage")
    if (
        not isinstance(usage, str)
        or len(usage) != len(asset_ids)
        or any(character not in {"0", "1"} for character in usage)
    ):
        raise ValueError(f"{beat_key}.assetUsage 必须是与素材数量等宽的0/1位图")
    referenced_asset_ids = [
        asset_id for index, asset_id in enumerate(asset_ids) if usage[index] == "1"
    ]
    compatibility_wire = {key: item[key] for key in expected_keys if key != "assetUsage"}
    return _normalize_planner_story_beat(
        compatibility_wire,
        beat_key=beat_key,
        beat_index=beat_index,
        beat_range=beat_range,
        referenced_asset_ids=referenced_asset_ids,
    )


def _normalize_planner_story_beat(
    value: JsonValue,
    *,
    beat_key: str,
    beat_index: int,
    beat_range: tuple[int, int],
    referenced_asset_ids: list[str],
) -> StoryBeatPlanArguments:
    """把第一阶段单拍投影为带服务器时间和素材引用的规范事实。"""

    item = _require_object(value, beat_key)
    start, end = beat_range
    action_capacity = _planner_action_capacity(start, end)
    expected_keys = [
        "dramaticPurpose",
        "performanceDirection",
        "blocking",
        "primaryAction",
        "actionComplexity",
        "sound",
    ]
    if action_capacity == 2:
        expected_keys.append("secondaryAction")
    _require_exact_keys(item, expected_keys, beat_key)

    actions = [_normalize_action_unit(item.get("primaryAction"), f"{beat_key}.primaryAction")]
    if action_capacity == 2:
        secondary = item.get("secondaryAction")
        if not _is_unused_slot(secondary):
            actions.append(_normalize_action_unit(secondary, f"{beat_key}.secondaryAction"))
    return StoryBeatPlanArguments(
        beatId=f"beat-{beat_index:02d}",
        startSecond=start,
        endSecond=end,
        dramaticPurpose=_require_strict_text(
            item.get("dramaticPurpose"),
            240,
            f"{beat_key}.dramaticPurpose",
        ),
        performanceDirection=_require_strict_text(
            item.get("performanceDirection"),
            300,
            f"{beat_key}.performanceDirection",
        ),
        blocking=_require_strict_text(item.get("blocking"), 300, f"{beat_key}.blocking"),
        actionUnits=actions,
        actionComplexity=cast(
            DirectorActionComplexity,
            _require_choice(
                item.get("actionComplexity"),
                _DIRECTOR_ACTION_COMPLEXITIES,
                f"{beat_key}.actionComplexity",
            ),
        ),
        sound=_require_strict_text(item.get("sound"), 500, f"{beat_key}.sound"),
        referencedAssetIds=referenced_asset_ids,
    )


def _normalize_planner_beat(
    value: JsonValue,
    *,
    beat_key: str,
    beat_index: int,
    beat_range: tuple[int, int],
    referenced_asset_ids: list[str],
    previous_lighting_cue: ShotLightingCue | None,
) -> CameraBeatPlanArguments:
    """把一个固定节拍槽投影为带服务器时间和引用的正式节拍。"""

    item = _require_object(value, beat_key)
    start, end = beat_range
    action_capacity = _planner_action_capacity(start, end)
    expected_keys = [
        "cameraSpec",
        "lightingCue",
        "dramaticPurpose",
        "performanceDirection",
        "blocking",
        "cameraMotivation",
        "axisTransition",
        "primaryAction",
        "actionComplexity",
        "shotProgression",
        "sound",
        "transition",
    ]
    if action_capacity == 2:
        expected_keys.append("secondaryAction")
    _require_exact_keys(item, expected_keys, beat_key)

    actions = [_normalize_action_unit(item.get("primaryAction"), f"{beat_key}.primaryAction")]
    if action_capacity == 2:
        secondary = item.get("secondaryAction")
        if not _is_unused_slot(secondary):
            actions.append(_normalize_action_unit(secondary, f"{beat_key}.secondaryAction"))
    complexity = cast(
        DirectorActionComplexity,
        _require_choice(
            item.get("actionComplexity"),
            _DIRECTOR_ACTION_COMPLEXITIES,
            f"{beat_key}.actionComplexity",
        ),
    )
    shot_progression = _normalize_shot_progression(
        item.get("shotProgression"),
        f"{beat_key}.shotProgression",
    )
    transition_value = item.get("transition")
    transition = (
        None
        if _is_unused_slot(transition_value)
        else _require_strict_text(transition_value, 200, f"{beat_key}.transition")
    )
    camera_spec = _normalize_shot_camera_spec(
        item.get("cameraSpec"),
        f"{beat_key}.cameraSpec",
    )
    lighting_cue = _normalize_shot_lighting_cue(
        item.get("lightingCue"),
        f"{beat_key}.lightingCue",
        inherited_from=previous_lighting_cue,
    )
    return CameraBeatPlanArguments(
        beatId=f"beat-{beat_index:02d}",
        startSecond=start,
        endSecond=end,
        cameraAngle=_render_legacy_camera_angle(camera_spec),
        cameraMovement=_render_legacy_camera_movement(camera_spec),
        dramaticPurpose=_require_strict_text(
            item.get("dramaticPurpose"), 240, f"{beat_key}.dramaticPurpose"
        ),
        performanceDirection=_require_strict_text(
            item.get("performanceDirection"),
            300,
            f"{beat_key}.performanceDirection",
        ),
        blocking=_require_strict_text(item.get("blocking"), 300, f"{beat_key}.blocking"),
        cameraMotivation=_require_strict_text(
            item.get("cameraMotivation"), 240, f"{beat_key}.cameraMotivation"
        ),
        axisTransition=cast(
            AxisTransition,
            _require_choice(
                item.get("axisTransition"),
                _AXIS_TRANSITIONS,
                f"{beat_key}.axisTransition",
            ),
        ),
        actionUnits=actions,
        actionComplexity=complexity,
        shotProgression=shot_progression,
        cameraSpec=camera_spec,
        lightingCue=lighting_cue,
        sound=_require_strict_text(item.get("sound"), 500, f"{beat_key}.sound"),
        transition=transition,
        referencedAssetIds=referenced_asset_ids,
    )


def _normalize_action_unit(value: JsonValue | None, label: str) -> CameraActionUnit:
    """校验一个动作对象，并保持字段原文。"""

    item = _require_object(value, label)
    _require_exact_keys(item, ["subject", "action", "visibleResult"], label)
    return CameraActionUnit(
        subject=_require_strict_text(item.get("subject"), 40, f"{label}.subject"),
        action=_require_strict_text(item.get("action"), 60, f"{label}.action"),
        visibleResult=_require_strict_text(
            item.get("visibleResult"),
            60,
            f"{label}.visibleResult",
        ),
    )


def _normalize_shot_progression(
    value: JsonValue | None,
    label: str,
) -> CameraShotProgression:
    """校验固定三字段的景别变化。"""

    item = _require_object(value, label)
    _require_exact_keys(item, ["startShotSize", "endShotSize", "changeMode"], label)
    return CameraShotProgression(
        startShotSize=cast(
            ShotSize,
            _require_choice(item.get("startShotSize"), _SHOT_SIZES, f"{label}.startShotSize"),
        ),
        endShotSize=cast(
            ShotSize,
            _require_choice(item.get("endShotSize"), _SHOT_SIZES, f"{label}.endShotSize"),
        ),
        changeMode=cast(
            ShotChangeMode,
            _require_choice(
                item.get("changeMode"),
                _SHOT_CHANGE_MODES,
                f"{label}.changeMode",
            ),
        ),
    )


def _normalize_beat_usage(
    value: JsonValue | None,
    *,
    beat_keys: Sequence[str],
    label: str,
) -> dict[str, bool]:
    """把固定宽度的节拍位图展开为完整逐拍事实。"""

    if (
        not isinstance(value, str)
        or len(value) != len(beat_keys)
        or any(character not in {"0", "1"} for character in value)
    ):
        raise ValueError(f"{label} 必须是与当前节拍数量等宽的 0/1 位图")
    if "1" not in value:
        raise ValueError(f"{label} 不能是全零位图，素材必须至少用于一个节拍")
    return {beat_key: value[index] == "1" for index, beat_key in enumerate(beat_keys)}


def _story_stage_to_strict_wire(
    story: StoryPlanStageArguments,
    *,
    beat_ranges: Sequence[tuple[int, int]],
) -> dict[str, JsonValue]:
    """把规范故事阶段无损还原成完整归一化器接受的 strict wire 子集。"""

    beat_keys = _planner_beat_keys(beat_ranges)
    if len(story.beats) != len(beat_ranges):
        raise ValueError("第一阶段规范的节拍数量与当前锁定时间表不一致")
    for index, (beat, beat_range) in enumerate(
        zip(story.beats, beat_ranges, strict=True),
        start=1,
    ):
        if beat.beatId != f"beat-{index:02d}" or (beat.startSecond, beat.endSecond) != beat_range:
            raise ValueError("第一阶段规范的节拍身份或时间与当前锁定时间表不一致")
        capacity = _planner_action_capacity(*beat_range)
        if len(beat.actionUnits) > capacity:
            raise ValueError("第一阶段规范的动作数量超过当前节拍时长容量")

    raw_assets: list[dict[str, JsonValue]] = []
    for asset in story.assets:
        setting_id = (
            asset.settingReference.id
            if asset.settingReference is not None
            else _PLANNER_NONE_SETTING_ID
        )
        target_entity = (
            _PLANNER_CANON_TARGET if asset.bindingScope == "canon_slot" else asset.targetEntity
        )
        keyframe_role = asset.keyframeRole or _PLANNER_NOT_APPLICABLE_KEYFRAME_ROLE
        used_in_beats = "".join(
            "1" if asset.assetId in beat.referencedAssetIds else "0" for beat in story.beats
        )
        raw_assets.append(
            cast(
                dict[str, JsonValue],
                {
                    "duty": asset.duty,
                    "modality": asset.modality,
                    "bindingScope": asset.bindingScope,
                    "settingId": setting_id,
                    "targetEntity": target_entity,
                    "keyframeRole": keyframe_role,
                    "include": _feature_values_to_strict_slots(asset.includeFeatures),
                    "exclude": _feature_values_to_strict_slots(asset.excludeFeatures),
                    "usedInBeats": used_in_beats,
                },
            )
        )

    raw_beats: dict[str, JsonValue] = {}
    for beat_key, beat, (start, end) in zip(
        beat_keys,
        story.beats,
        beat_ranges,
        strict=True,
    ):
        beat_wire: dict[str, JsonValue] = {
            "dramaticPurpose": beat.dramaticPurpose,
            "performanceDirection": beat.performanceDirection,
            "blocking": beat.blocking,
            "primaryAction": cast(
                dict[str, JsonValue],
                beat.actionUnits[0].model_dump(mode="json"),
            ),
            "actionComplexity": beat.actionComplexity,
            "sound": beat.sound,
        }
        if _planner_action_capacity(start, end) == 2:
            beat_wire["secondaryAction"] = (
                cast(
                    dict[str, JsonValue],
                    beat.actionUnits[1].model_dump(mode="json"),
                )
                if len(beat.actionUnits) == 2
                else _PLANNER_UNUSED_SENTINEL
            )
        raw_beats[beat_key] = beat_wire

    return cast(
        dict[str, JsonValue],
        {
            "title": story.title,
            "summary": story.summary,
            "dramaticArc": story.dramaticArc,
            "visualStyle": story.visualStyle,
            "globalDirection": story.globalDirection,
            "assets": {
                "asset01": raw_assets[0],
                "additionalAssets": raw_assets[1:],
            },
            "beats": raw_beats,
            "negativeConstraints": {
                "constraint01": story.negativeConstraints[0],
                "additionalConstraints": story.negativeConstraints[1:],
            },
        },
    )


def _feature_values_to_strict_slots(values: Sequence[str]) -> dict[str, JsonValue]:
    """把规范特征列表还原为十二个 strict 文本槽，不截断原值。"""

    return {
        _fixed_slot_key("feature", index): (
            values[index - 1] if index <= len(values) else _PLANNER_UNUSED_SENTINEL
        )
        for index in range(1, _PLANNER_FEATURE_SLOT_COUNT + 1)
    }


def _normalize_text_slots(
    value: JsonValue | None,
    *,
    prefix: str,
    count: int,
    first_required: bool,
    max_characters: int,
    label: str,
) -> list[str]:
    """按固定槽位顺序收集文本，``__UNUSED__`` 不产生领域值。"""

    item = _require_object(value, label)
    keys = [_fixed_slot_key(prefix, index) for index in range(1, count + 1)]
    _require_exact_keys(item, keys, label)
    values: list[str] = []
    for index, key in enumerate(keys, start=1):
        slot_value = item[key]
        if _is_unused_slot(slot_value):
            if first_required and index == 1:
                raise ValueError(f"{label}.{key} 是必用文本槽位，不能填写 __UNUSED__")
            continue
        values.append(_require_strict_text(slot_value, max_characters, f"{label}.{key}"))
    return values


def _fixed_text_slots_schema(
    *,
    prefix: str,
    count: int,
    first_required: bool,
    max_characters: int,
    description: str,
) -> dict[str, Any]:
    """用固定字符串属性表达供应商不支持长度约束的有界列表。"""

    properties: dict[str, Any] = {}
    for index in range(1, count + 1):
        key = _fixed_slot_key(prefix, index)
        slot_description = (
            "必用文本槽位。"
            if first_required and index == 1
            else "可用文本槽位；没有内容时填写 __UNUSED__。"
        )
        properties[key] = _strict_text_schema(max_characters, slot_description)
    return _strict_object_schema(properties, description=description)


def _unused_string_schema() -> dict[str, Any]:
    """生成 DeepSeek 容易稳定输出的字符串空槽哨兵。"""

    return {
        "type": "string",
        "enum": [_PLANNER_UNUSED_SENTINEL],
        "description": "明确表示该固定槽位没有内容。",
    }


def _planner_action_unit_schema() -> dict[str, Any]:
    """内联一个原子动作，避免 anyOf 分支只携带无类型的引用。"""

    return _strict_object_schema(
        {
            "subject": _strict_text_schema(40, "执行动作的唯一主体。"),
            "action": _strict_text_schema(60, "主体执行的单一动作。"),
            "visibleResult": _strict_text_schema(60, "动作造成的唯一可见结果。"),
        },
        description="一个主体、一个动作和一个可见结果。",
    )


def _strict_text_schema(
    max_characters: int,
    description: str | None = None,
) -> dict[str, Any]:
    """用 DeepSeek 支持的 pattern 同时表达非空与字符上限。"""

    schema: dict[str, Any] = {
        "type": "string",
        # 最后一位必须是非空白字符，因此空串、纯空白和尾随空白都会被拒绝。
        "pattern": rf"^[\s\S]{{0,{max_characters - 1}}}\S$",
    }
    if description is not None:
        schema["description"] = description
    return schema


def _strict_integer_schema(description: str) -> dict[str, Any]:
    """数值范围留给本地 Pydantic 校验，wire 只使用 strict 支持的整数类型。"""

    return {"type": "integer", "description": description}


def _strict_number_schema(description: str) -> dict[str, Any]:
    """生成 DeepSeek strict 支持的浮点数 schema。"""

    return {"type": "number", "description": description}


def _strict_object_schema(
    properties: Mapping[str, Any],
    *,
    description: str | None = None,
) -> dict[str, Any]:
    """生成所有属性必填且拒绝额外字段的 strict 对象。"""

    schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "required": list(properties),
        "additionalProperties": False,
    }
    if description is not None:
        schema["description"] = description
    return schema


def _validate_planner_beat_ranges(
    beat_ranges: Sequence[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    """锁定从零开始、连续且适配 V2 双动作槽的整数秒时间表。"""

    ranges = tuple(beat_ranges)
    if not 1 <= len(ranges) <= 5:
        raise ValueError("strict 工具的节拍数量必须在 1 至 5 之间")
    previous_end = 0
    for start, end in ranges:
        if type(start) is not int or type(end) is not int:
            raise ValueError("strict 工具的节拍边界必须是整数秒")
        if start != previous_end or end <= start or end > 30:
            raise ValueError("strict 工具的节拍必须从 0 秒开始、连续且正向")
        _planner_action_capacity(start, end)
        previous_end = end
    return ranges


def _next_model_stage(
    checkpoint_stage: Literal["empty", "scene_assets", "story"],
) -> Literal["scene_assets", "story_beats", "cinematography"]:
    """返回当前耐久 checkpoint 后唯一可以调用的模型阶段。"""

    stages: dict[
        Literal["empty", "scene_assets", "story"],
        Literal["scene_assets", "story_beats", "cinematography"],
    ] = {
        "empty": "scene_assets",
        "scene_assets": "story_beats",
        "story": "cinematography",
    }
    return stages[checkpoint_stage]


def _validate_active_checkpoint_payload(
    *,
    checkpoint_stage: Literal["empty", "scene_assets", "story"],
    scene_assets_plan: SceneAssetsStageArguments | None,
    story_plan: StoryPlanStageArguments | None,
) -> None:
    """要求 active 阶段与唯一 canonical 计划载荷严格对应。"""

    if checkpoint_stage == "empty":
        if scene_assets_plan is not None or story_plan is not None:
            raise ValueError("empty 检查点不能携带任何阶段计划")
    elif checkpoint_stage == "scene_assets":
        if scene_assets_plan is None or story_plan is not None:
            raise ValueError("scene_assets 检查点必须且只能携带 sceneAssetsPlan")
    elif story_plan is None or scene_assets_plan is not None:
        raise ValueError("story 检查点必须且只能携带 storyPlan")


def _validate_active_attempt_state(
    *,
    checkpoint_stage: Literal["empty", "scene_assets", "story"],
    attempt_state: VideoPlanAttemptState,
    allow_pending: bool,
) -> None:
    """按 checkpoint rank 校验全局两个纠正名额与下一阶段 pending。"""

    rank = {"empty": 0, "scene_assets": 1, "story": 2}[checkpoint_stage]
    if attempt_state.inheritedCalls > rank:
        raise ValueError("继承调用基线不能超过当前 checkpoint 已完成阶段数")
    pending = attempt_state.pendingStage
    if pending is not None:
        if not allow_pending:
            raise ValueError("阶段成功 checkpoint 必须清除 pendingStage")
        expected_stage = _next_model_stage(checkpoint_stage)
        if pending != expected_stage:
            raise ValueError(f"{checkpoint_stage} 检查点的 pendingStage 只能是 {expected_stage}")
    effective_calls = attempt_state.inheritedCalls + attempt_state.reservedCalls
    minimum_calls = rank + (1 if pending is not None else 0)
    # 三个阶段共享两个额外纠正名额；前序多用一次，后序自然少一次。
    correction_allowance = 2
    maximum_calls = minimum_calls + correction_allowance
    if checkpoint_stage == "empty" and pending is None:
        maximum_calls = 0
    if not minimum_calls <= effective_calls <= maximum_calls:
        raise ValueError("模型调用预留计数与 checkpoint/pending 不一致或重复消耗纠正预算")


def _planner_action_capacity(start: int, end: int) -> int:
    """返回当前 V2 每拍一至两个动作槽的时长预算。"""

    capacity = min(3, ceil((end - start) / 2))
    if capacity not in {1, 2}:
        raise ValueError("PlannerToolEnvelopeV2 只支持每拍一至两个动作单元")
    return capacity


def _planner_beat_keys(beat_ranges: Sequence[tuple[int, int]]) -> list[str]:
    """按时间表长度生成稳定节拍槽位键。"""

    return [f"beat{index:02d}" for index in range(1, len(beat_ranges) + 1)]


def _planner_beat_usage_pattern(beat_keys: Sequence[str]) -> str:
    """生成与本次节拍数量等宽的 0/1 位图 pattern。"""

    return rf"^[01]{{{len(beat_keys)}}}$"


def _planner_asset_key(index: int) -> str:
    """生成模型素材固定槽位键。"""

    return f"asset{index:02d}"


def _planner_beat_definition_name(index: int) -> str:
    """生成单拍 schema 定义名。"""

    return f"Beat{index:02d}"


def _fixed_slot_key(prefix: str, index: int) -> str:
    """生成固定文本槽位键。"""

    return f"{prefix}{index:02d}"


def _require_object(value: object, label: str) -> dict[str, JsonValue]:
    """要求原始值为字符串键 JSON 对象。"""

    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} 必须是对象")
    return cast(dict[str, JsonValue], value)


def _require_array(value: object, label: str) -> list[JsonValue]:
    """要求原始值为 JSON 数组，不把字符串或对象静默转换为序列。"""

    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是数组")
    return cast(list[JsonValue], value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: Sequence[str] | set[str],
    label: str,
) -> None:
    """拒绝固定槽位对象中的遗漏与额外字段。"""

    expected_keys = set(expected)
    actual_keys = set(value)
    if actual_keys == expected_keys:
        return
    missing = "、".join(sorted(expected_keys - actual_keys)) or "无"
    extra = "、".join(sorted(actual_keys - expected_keys)) or "无"
    raise ValueError(f"{label} 字段不完整：缺少={missing}，额外={extra}")


def _require_strict_text(value: object, max_characters: int, label: str) -> str:
    """执行与 strict pattern 相同的非空、尾字符和长度校验。"""

    if (
        not isinstance(value, str)
        or not value
        or value[-1].isspace()
        or len(value) > max_characters
    ):
        raise ValueError(f"{label} 必须是 1 至 {max_characters} 字且末尾非空白的字符串")
    return value


def _require_choice(
    value: object,
    choices: Sequence[str],
    label: str,
) -> str:
    """要求字符串精确命中当前 schema 的枚举。"""

    if not isinstance(value, str) or value not in choices:
        allowed = "、".join(choices)
        raise ValueError(f"{label} 必须是以下值之一：{allowed}")
    return value


def _require_int_choice(
    value: object,
    choices: Sequence[int],
    label: str,
) -> int:
    """要求整数精确命中枚举；布尔值不能冒充整数。"""

    if type(value) is not int or value not in choices:
        allowed = "、".join(str(item) for item in choices)
        raise ValueError(f"{label} 必须是以下整数之一：{allowed}")
    return value


def _require_integer(value: object, label: str) -> int:
    """要求 wire 数值确实是整数，禁止字符串或布尔值隐式转换。"""

    if type(value) is not int:
        raise ValueError(f"{label} 必须是整数")
    return value


def _require_number(value: object, label: str) -> float:
    """要求有限 JSON 数值，禁止布尔值及无穷值进入领域契约。"""

    if type(value) not in {int, float}:
        raise ValueError(f"{label} 必须是数值")
    number = float(cast(int | float, value))
    if number != number or number in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} 必须是有限数值")
    return number


def _require_enum_string(value: object, label: str) -> str:
    """要求动态 enum 值先满足非空字符串基本事实。"""

    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} 必须是冻结设定 ID")
    return value


def _is_unused_slot(value: object) -> bool:
    """只接受精确的 ``__UNUSED__`` 字符串哨兵。"""

    return isinstance(value, str) and value == _PLANNER_UNUSED_SENTINEL
