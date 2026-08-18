"""视频场景规划器的 Responses 草案与确定性编译测试。"""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.clients.core import CoreServiceError, RunResource
from inkforge_agents.jobs.video import (
    ModelVideoScenePlanner,
    VideoPlanGenerationError,
    VideoPromptJobHandler,
    _balanced_beat_ranges,
    _next_stage_correction,
    _revision_baseline_context_json,
    _safe_planner_error,
    _stable_slot_id,
    _story_source_event_checklist,
)
from inkforge_agents.providers.base import (
    ModelStructuredOutputDiagnostic,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)
from inkforge_agents.queue.consumer import NonRetryableJobError
from inkforge_agents.queue.repository import QueueJob
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_agents.video_prompt.compiler import SeedancePromptCompiler
from inkforge_agents.video_prompt.demo import build_demo_scene
from inkforge_contracts.video import (
    CameraActionUnit,
    CharacterSettingSnapshot,
    ItemSettingSnapshot,
    LocationSettingSnapshot,
    LongSerialSettingSnapshot,
    PlannedAsset,
    RelationshipSettingSnapshot,
    SceneAssetsStageArguments,
    ScenePromptSpec,
    ShotLightingCue,
    StoryBeatPlanArguments,
    StoryBeatsStageArguments,
    StoryPlanStageArguments,
    VideoPlanAttemptState,
    VideoPlanCallReservationRequest,
    VideoPlanCallReservationResponse,
    VideoPlanFailureCallback,
    VideoPlanJobPayload,
    VideoPlanProgressQuery,
    VideoPlanProgressResponse,
    VideoStoryPlanCheckpointCallback,
    build_video_director_draft_skeleton,
    calculate_video_plan_input_fingerprint,
    merge_story_stage_arguments,
    normalize_scene_assets_strict_tool_arguments,
    normalize_story_beats_strict_tool_arguments,
    validate_source_event_sequence,
)
from pydantic import ValidationError

PlanMutator = Callable[[dict[str, Any]], None]
_SCENE_ASSETS_FORMAT_NAME = "video_scene_assets_draft_v1"
_STORY_BEATS_FORMAT_NAME = "video_story_beats_draft_v4"
_CINEMATOGRAPHY_FORMAT_NAME = "video_cinematography_draft_v2"
_JSON_OBJECT_OUTPUT_RULE = (
    "响应只能是一个 JSON object；第一个非空字符必须是 {，最后一个非空字符必须是 }；"
    "不得 Markdown 围栏、解释或前后文字；字段名和嵌套形状严格由 Responses Schema 决定。"
)
_CLOCKTOWER_SOURCE = (
    "沈青拔下铜扣，插进黄铜匣侧面缺失的齿槽，铜扣立刻被机关咬碎。"
    "黄铜匣弹开，沈青触到匣内罗盘。整座钟楼的齿轮同时加速，"
    "牵引链将巨大钟摆提到最高处，随后钟摆轰然落下，砸碎海侧墙面。"
)


def _request_format_name(request: ModelTurnRequest) -> str:
    """返回结构化格式名，测试不得再从 legacy 工具名推断阶段。"""

    if request.structuredOutput is None:
        raise AssertionError("视频规划请求缺少 structuredOutput")
    return request.structuredOutput.name


def test_camera_schema_range_correction_explains_the_bound_without_echoing_value() -> None:
    """Schema 只给 minimum 时，摄影纠错还要补充静态范围且不回显草稿值。"""

    correction = _next_stage_correction(
        "story",
        "cinematography",
        VideoPlanAttemptState(reservedCalls=3, pendingStage="cinematography"),
        stage_label="摄影灯光",
        safe_error=(
            "VIDEO_PLAN_STAGE_STRUCTURED_OUTPUT_INVALID：摄影灯光阶段结构化草案无效；"
            "code=schema_violation, "
            "pointer=/beatsByAlias/B02/cameraSpec/movement/rotationDegrees, keyword=minimum"
        ),
    )

    assert "rotationDegrees 是非负幅度，必须在 0 到 360 之间" in correction
    assert "每个 B 拍点的摄影字段完整" in correction
    assert "zoom 镜头只用 zoom_in/zoom_out" in correction
    assert "不到 5 秒的拍内 continuous 最多跨一级景别" in correction
    assert "自动规划 wire 固定 axisRule=maintain_180" in correction
    assert "axisSide 只使用 screen_left 或 on_axis" in correction
    assert "keyLight.role=key" in correction
    assert "-30" not in correction


@pytest.mark.parametrize(
    ("mutate", "expected_rule"),
    [
        (
            lambda value: value.update({"motivatedChange": ""}),
            "LIGHTING_MOTIVATION_REQUIRED",
        ),
        (
            lambda value: value["keyLight"].update({"role": "fill"}),
            "KEY_LIGHT_ROLE_INVALID",
        ),
        (
            lambda value: value.update(
                {
                    "edgeLight": {
                        **value["keyLight"],
                        "role": "fill",
                    }
                }
            ),
            "EDGE_LIGHT_ROLE_INVALID",
        ),
        (
            lambda value: value.update(
                {
                    "fillStrategy": "none",
                    "fillRelativeStops": -4,
                }
            ),
            "FILL_OFF_EXPOSURE_INVALID",
        ),
        (
            lambda value: value.update(
                {
                    "fillStrategy": "soft_fill",
                    "fillDirection": None,
                }
            ),
            "ACTIVE_FILL_DIRECTION_REQUIRED",
        ),
    ],
)
def test_lighting_cross_field_errors_return_actionable_static_rules(
    mutate: Callable[[dict[str, Any]], None],
    expected_rule: str,
) -> None:
    """灯光 root 校验不能退化成没有修复方向的 value_error。"""

    cue = build_demo_scene().beats[0].lightingCue
    assert cue is not None
    payload = cue.model_dump(mode="json")
    mutate(payload)

    with pytest.raises(ValidationError) as caught:
        ShotLightingCue.model_validate(payload)

    safe_error = _safe_planner_error(caught.value)
    assert f"rule={expected_rule}" in safe_error
    assert "input_value" not in safe_error


class StructuredPlanProvider:
    """返回一次合法结构化草案，并保留请求供断言。"""

    billable = False
    provider_name = "openai_compatible"
    model_name = "deepseek-v4-flash"

    def __init__(
        self,
        *,
        character_reference_id: str = "character-shen-qing",
        duration_seconds: int = 15,
        mutator: PlanMutator | None = None,
        stage_mutators: dict[str, list[PlanMutator | None]] | None = None,
    ) -> None:
        self.requests: list[ModelTurnRequest] = []
        self.character_reference_id = character_reference_id
        self.duration_seconds = duration_seconds
        self.mutator = mutator
        self.stage_mutators = stage_mutators or {}
        self.stage_call_counts: dict[str, int] = {}

    def supports_structured_output(self, route: object) -> bool:
        """测试主 Provider 只声明 Responses 视频主链能力。"""

        return route == "responses_json_schema_v1"

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.requests.append(request)
        arguments = _valid_plan_arguments(self)
        structured = request.structuredOutput
        if structured is None:
            raise AssertionError("三阶段规划请求必须指定结构化输出")
        format_name = structured.name
        call_index = self.stage_call_counts.get(format_name, 0)
        self.stage_call_counts[format_name] = call_index + 1
        mutators = self.stage_mutators.get(format_name)
        if mutators is None:
            stage_mutator = self.mutator
        else:
            stage_mutator = mutators[call_index] if call_index < len(mutators) else None
        if stage_mutator is not None:
            stage_mutator(arguments)
        if format_name == _SCENE_ASSETS_FORMAT_NAME:
            stage_arguments = _scene_assets_draft_arguments(arguments)
        elif format_name == _STORY_BEATS_FORMAT_NAME:
            stage_arguments = _story_beats_draft_arguments(arguments)
        elif format_name == _CINEMATOGRAPHY_FORMAT_NAME:
            stage_arguments = _cinematography_draft_arguments(arguments)
        else:
            raise AssertionError(f"未预期的草案格式：{format_name}")
        return ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutput=stage_arguments,
            usage=ModelUsage(
                promptTokens=100,
                completionTokens=200,
                totalTokens=300,
            ),
            finishReason="stop",
            rawFinishReason="stop",
        )


class InvalidStructuredPlanProvider:
    """返回不含原始草案值的结构化诊断，供规划器错误边界测试。"""

    billable = False
    provider_name = "openai_compatible"
    model_name = "deepseek-v4-flash"

    def __init__(self, *, effective_max_output_tokens: int | None = None) -> None:
        self.requests: list[ModelTurnRequest] = []
        self.effective_max_output_tokens = effective_max_output_tokens

    def supports_structured_output(self, route: object) -> bool:
        """无效输出替身仍需先通过同一 Responses 能力预检。"""

        return route == "responses_json_schema_v1"

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.requests.append(request)
        return ModelTurnResult(
            content="",
            toolCalls=[],
            structuredOutputDiagnostic=ModelStructuredOutputDiagnostic(
                code="schema_violation",
                jsonPointer="/assets/0/sourceAlias",
                keyword="enum",
            ),
            usage=ModelUsage(
                promptTokens=8_000,
                completionTokens=(
                    min(1_998, self.effective_max_output_tokens - 1)
                    if self.effective_max_output_tokens is not None
                    else 1_998
                ),
                totalTokens=(
                    8_000 + min(1_998, self.effective_max_output_tokens - 1)
                    if self.effective_max_output_tokens is not None
                    else 9_998
                ),
            ),
            effectiveMaxOutputTokens=self.effective_max_output_tokens,
            finishReason="stop",
            rawFinishReason="stop",
        )


class UnsupportedStructuredPlanProvider(StructuredPlanProvider):
    """身份与模型匹配，但不具备冻结 Responses 路由。"""

    def supports_structured_output(self, route: object) -> bool:
        del route
        return False


def _valid_plan_arguments(provider: StructuredPlanProvider) -> dict[str, Any]:
    """构造完整导演事实，再按阶段投影成 Responses 草案。"""

    ranges = _balanced_beat_ranges(provider.duration_seconds)
    beat_keys = [f"beat{index:02d}" for index in range(1, len(ranges) + 1)]
    used_in_all_beats = "1" * len(beat_keys)
    assets: dict[str, Any] = {
        "asset01": {
            "modality": "image",
            "duty": "identity",
            "bindingScope": "canon_slot",
            "settingId": provider.character_reference_id,
            "targetEntity": "__CANON__",
            "keyframeRole": "not_applicable",
            "include": _text_slots("feature", ["清瘦脸型", "湿发"], 12),
            "exclude": _text_slots("feature", ["背景", "服装"], 12),
            "usedInBeats": used_in_all_beats,
        },
        "additionalAssets": [
            {
                "modality": "image",
                "duty": "costume",
                "bindingScope": "canon_slot",
                "settingId": provider.character_reference_id,
                "targetEntity": "__CANON__",
                "keyframeRole": "not_applicable",
                "include": _text_slots("feature", ["深青短褂", "旧蓑衣"], 12),
                "exclude": _text_slots("feature", ["脸型", "五官"], 12),
                "usedInBeats": used_in_all_beats,
            },
            {
                "modality": "image",
                "duty": "scene",
                "bindingScope": "canon_slot",
                "settingId": "location-medicine-shop",
                "targetEntity": "__CANON__",
                "keyframeRole": "not_applicable",
                "include": _text_slots("feature", ["木柜", "油灯"], 12),
                "exclude": _text_slots("feature", ["图中人物"], 12),
                "usedInBeats": used_in_all_beats,
            },
        ],
    }

    beats: dict[str, Any] = {}
    actions = ["推开木门", "走到柜前", "抬起目光", "辨认伤疤"]
    results = ["木门向内开启", "身影进入灯下", "视线落向对方", "神情发生变化"]
    dramatic_purposes = ["建立闯入", "推进接近", "制造认出前停顿", "完成身份确认"]
    performance_directions = [
        "少女推门后停顿半拍，先观察室内再迈步",
        "少女放轻脚步，靠近柜台后收住动作",
        "少女抬眼后屏住呼吸，等待对方转身",
        "少女看清伤疤后肩膀放松，呼出一口气",
    ]
    blockings = [
        "少女起于画面左侧门外，向右进入，止于左三分之一前景",
        "少女起于左侧前景，沿左至右方向走向柜台，止于画面中央",
        "少女保持画面中央，视线从下向上移动，身体不越过既定轴线",
        "少女止于画面中央，对方留在画面右侧，两人维持左至右关系",
    ]
    for index, ((start, end), beat_key) in enumerate(zip(ranges, beat_keys, strict=True)):
        action = actions[index]
        visible_result = results[index]
        beat: dict[str, Any] = {
            "dramaticPurpose": dramatic_purposes[index],
            "performanceDirection": performance_directions[index],
            "blocking": blockings[index],
            "cameraMotivation": (f"少女{action}是可见触发，叙事上需要强调{visible_result}"),
            "axisTransition": "hold",
            "cameraSpec": _camera_spec(),
            "lightingCue": (_establish_lighting_cue() if index == 0 else "__INHERIT__"),
            "primaryAction": {
                "subject": "少女",
                "action": action,
                "visibleResult": visible_result,
            },
            "actionComplexity": "simple",
            "shotProgression": {
                "startShotSize": "中景",
                "endShotSize": "中景",
                "changeMode": "continuous",
            },
            "sound": f"<同步拟音{index + 1}>",
            "transition": "__UNUSED__" if index == 0 else "硬切",
        }
        if (end - start) >= 3:
            beat["secondaryAction"] = "__UNUSED__"
        beats[beat_key] = beat

    return {
        "title": "雨夜药铺",
        "summary": "少女进门认出兄长。",
        "visualStyle": "写实冷调。",
        "globalDirection": "保持人物轴线稳定。",
        "dramaticArc": "少女闯入药铺，警觉接近，在停顿后认出失散兄长。",
        "cinematographyBase": {
            "captureFormat": "super_35",
            "lensProjection": "spherical",
            "frameRateFps": 24,
            "shutterAngleDegrees": 180,
            "axisRule": "maintain_180",
            "screenDirection": "left_to_right",
        },
        "lightingSetup": {
            "exposureStyle": "low_key",
            "ambientSource": "门外暴雨反射的冷色天光",
            "ambientColorTemperatureK": 4300,
            "cameraWhiteBalanceK": 4000,
            "keyToFillStops": 3.0,
            "negativeFillSide": "camera_right",
            "atmosphere": "薄雨雾与潮湿空气",
        },
        "assets": assets,
        "beats": beats,
        "negativeConstraints": {
            "constraint01": "人物身份漂移",
            "additionalConstraints": ["多余字幕", "镜头越轴"],
        },
    }


def _scene_assets_plan_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """从完整测试夹具投影 V3 第一阶段紧凑素材 wire。"""

    old_assets = [
        arguments["assets"]["asset01"],
        *arguments["assets"]["additionalAssets"],
    ]
    compact_assets = [
        {
            **{
                key: value
                for key, value in asset.items()
                if key not in {"include", "exclude", "usedInBeats"}
            },
            "include": [value for value in asset["include"].values() if value != "__UNUSED__"],
            "exclude": [value for value in asset["exclude"].values() if value != "__UNUSED__"],
        }
        for asset in old_assets
    ]
    return {
        "title": arguments["title"],
        "summary": arguments["summary"],
        "dramaticArc": arguments["dramaticArc"],
        "visualStyle": arguments["visualStyle"],
        "globalDirection": arguments["globalDirection"],
        "assets": {
            "asset01": compact_assets[0],
            "additionalAssets": compact_assets[1:],
        },
        "negativeConstraints": [
            arguments["negativeConstraints"]["constraint01"],
            *arguments["negativeConstraints"]["additionalConstraints"],
        ],
    }


def _story_beats_plan_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """从完整测试夹具投影 V3 第二阶段故事节拍与素材位图 wire。"""

    story_beat_keys = {
        "dramaticPurpose",
        "performanceDirection",
        "blocking",
        "primaryAction",
        "secondaryAction",
        "actionComplexity",
        "sound",
    }
    assets = [
        arguments["assets"]["asset01"],
        *arguments["assets"]["additionalAssets"],
    ]
    return {
        "beats": {
            beat_key: {
                **{key: value for key, value in beat.items() if key in story_beat_keys},
                "assetUsage": "".join(asset["usedInBeats"][index] for asset in assets),
            }
            for index, (beat_key, beat) in enumerate(arguments["beats"].items())
        }
    }


def _cinematography_plan_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """从完整测试夹具投影第二阶段 strict wire。"""

    cinematography_beat_keys = {
        "cameraMotivation",
        "axisTransition",
        "cameraSpec",
        "lightingCue",
        "shotProgression",
        "transition",
    }
    return {
        "cinematographyBase": arguments["cinematographyBase"],
        "lightingSetup": arguments["lightingSetup"],
        "beats": {
            beat_key: {key: value for key, value in beat.items() if key in cinematography_beat_keys}
            for beat_key, beat in arguments["beats"].items()
        },
    }


def _scene_assets_draft_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """把完整导演夹具投影为只含创意语义的第一阶段草案。"""

    assets = [
        arguments["assets"]["asset01"],
        *arguments["assets"]["additionalAssets"],
    ]
    asset_slots: dict[str, Any] = {}
    for index, asset in enumerate(assets, start=1):
        asset_slots[f"asset{index:02d}"] = {
            "sourceAlias": (
                _source_alias_for_setting(asset["settingId"])
                if asset["bindingScope"] == "canon_slot"
                else None
            ),
            "duty": asset["duty"],
            "targetEntity": (
                None if asset["bindingScope"] == "canon_slot" else asset["targetEntity"]
            ),
            "includeFeatures": [
                value for value in asset["include"].values() if value != "__UNUSED__"
            ],
            "excludeFeatures": [
                value for value in asset["exclude"].values() if value != "__UNUSED__"
            ],
        }
    for index in range(len(assets) + 1, 12):
        asset_slots[f"asset{index:02d}"] = None
    return {
        "title": arguments["title"],
        "summary": arguments["summary"],
        "dramaticArc": arguments["dramaticArc"],
        "visualStyle": arguments["visualStyle"],
        "globalDirection": arguments["globalDirection"],
        "assets": asset_slots,
        "negativeConstraints": [
            arguments["negativeConstraints"]["constraint01"],
            *arguments["negativeConstraints"]["additionalConstraints"],
        ],
    }


def _story_beats_draft_arguments(
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """把完整导演夹具投影为 v4 闭合 B 故事草案和素材使用表。"""

    assets = [
        arguments["assets"]["asset01"],
        *arguments["assets"]["additionalAssets"],
    ]
    beats: dict[str, dict[str, Any]] = {}
    for index, beat in enumerate(arguments["beats"].values()):
        secondary = beat.get("secondaryAction")
        secondary_action = secondary if isinstance(secondary, dict) else None
        beats[f"B{index + 1:02d}"] = {
            "dramaticPurpose": beat["dramaticPurpose"],
            "performanceDirection": beat["performanceDirection"],
            "blocking": beat["blocking"],
            "primaryAction": beat["primaryAction"],
            "secondaryAction": secondary_action,
            "actionComplexity": beat["actionComplexity"],
            "sound": beat["sound"],
        }
    asset_usage: dict[str, dict[str, object]] = {}
    for asset_index, asset in enumerate(assets, start=1):
        used_beat_aliases = [
            f"B{beat_index + 1:02d}"
            for beat_index, marker in enumerate(asset["usedInBeats"])
            if marker == "1"
        ]
        # 全零仅用于错误夹具：省略该 A 键，让动态 exact-object 门禁报告缺失。
        if not used_beat_aliases:
            continue
        asset_alias = f"A{asset_index:02d}"
        anchor_alias: str | None = None
        if asset.get("duty") == "keyframe" and asset.get("keyframeRole") == "initial_state":
            # 测试夹具用最近的非关键帧素材作为初态锚点，模拟模型可见的 A 别名关系。
            for previous_index in range(asset_index - 1, 0, -1):
                previous = assets[previous_index - 1]
                if previous.get("duty") != "keyframe":
                    anchor_alias = f"A{previous_index:02d}"
                    break
        asset_usage[asset_alias] = {
            "primaryBeatAlias": used_beat_aliases[0],
            "additionalBeatAliases": used_beat_aliases[1:],
            "anchorAssetAlias": anchor_alias,
        }
    return {"beatsByAlias": beats, "assetUsageByAlias": asset_usage}


def _cinematography_draft_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """把完整导演夹具投影为 B 短别名摄影灯光草案。"""

    beats: dict[str, dict[str, Any]] = {}
    for index, beat in enumerate(arguments["beats"].values(), start=1):
        lighting_cue = beat["lightingCue"]
        if lighting_cue == "__INHERIT__":
            draft_lighting_cue = None
        else:
            # 旧完整夹具用哨兵表达“没有轮廓光”；草案协议直接使用自然 null。
            draft_lighting_cue = dict(lighting_cue)
            if draft_lighting_cue.get("edgeLight") == "__UNUSED__":
                draft_lighting_cue["edgeLight"] = None
        alias = f"B{index:02d}"
        beats[alias] = {
            "beatAlias": alias,
            "cameraSpec": beat["cameraSpec"],
            "lightingCue": draft_lighting_cue,
            "cameraMotivation": beat["cameraMotivation"],
            "axisTransition": beat["axisTransition"],
            "shotProgression": beat["shotProgression"],
            "transition": None if beat["transition"] == "__UNUSED__" else beat["transition"],
        }
    return {
        "cinematographyBase": arguments["cinematographyBase"],
        "lightingSetup": arguments["lightingSetup"],
        "beatsByAlias": beats,
    }


def _source_alias_for_setting(setting_id: str) -> str:
    """按共享骨架规则把测试设定映射为短别名，未知角色保留非法别名供门禁测试。"""

    return {
        "character-shen-qing": "C01",
        "character-z-lin-lan": "C02",
        "location-medicine-shop": "L01",
        "item-mechanism-box": "I01",
        "relationship-allies": "R01",
    }.get(setting_id, "C99")


def _camera_spec() -> dict[str, Any]:
    """返回没有焦段、机位、运镜或焦点冲突的专业摄影规格。"""

    return {
        "lensType": "prime",
        "focalLengthMm": 35,
        "endFocalLengthMm": 35,
        "tStop": 2.8,
        "position": {
            "heightCm": 140,
            "azimuthDegrees": 20,
            "elevationDegrees": 0,
            "rollDegrees": 0,
            "subjectDistanceMeters": 3.0,
            "axisSide": "screen_left",
        },
        "composition": {
            "rule": "rule_of_thirds",
            "subjectPlacement": "left_third",
            "subjectFramePercent": 45,
            "headroom": "standard",
            "foregroundLayer": "雨水打湿的门框",
            "backgroundLayer": "木柜与柜台油灯",
        },
        "movement": {
            "support": "tripod",
            "movementType": "locked_off",
            "travelDistanceMeters": 0.0,
            "rotationDegrees": 0.0,
            "speed": "static",
            "easing": "none",
        },
        "focus": {
            "depthOfField": "medium",
            "startTarget": "少女眼睛",
            "endTarget": "少女眼睛",
            "transition": "locked",
            "rackDurationSeconds": 0.0,
        },
    }


def _establish_lighting_cue() -> dict[str, Any]:
    """返回首拍完整 establish 灯光对象；后续不变拍使用 compact 哨兵。"""

    return {
        "continuityMode": "establish",
        "motivatedChange": "由柜台油灯建立主光",
        "keyLight": {
            "role": "key",
            "motivatedBy": "柜台上的油灯",
            "direction": "front_right",
            "azimuthDegrees": 35,
            "elevationDegrees": 20,
            "quality": "soft",
            "delivery": "diffused",
            "colorTemperatureK": 2800,
            "relativeExposureStops": 0.0,
            "beamAngleDegrees": 70,
            "falloff": "fast",
            "spillControl": "右侧黑旗限制油灯溢光",
            "visibleResult": "暖光只勾出少女面部与湿衣边缘",
        },
        "fillStrategy": "negative_fill",
        "fillDirection": "side_right",
        "fillRelativeStops": -3.0,
        "edgeLight": "__UNUSED__",
        "atmosphere": "薄雨雾与潮湿空气",
        "visibleResult": "暖色面部从冷暗药铺背景中分离",
    }


def _add_bgm_to_first_sound(arguments: dict[str, Any]) -> None:
    """模拟模型把背景音乐混进镜头声音字段。"""

    arguments["beats"]["beat01"]["sound"] = "<门轴声>，BGM渐强"


def _chain_actions_inside_one_unit(arguments: dict[str, Any]) -> None:
    """模拟模型用连接词把多个动作藏回一个动作单元。"""

    arguments["beats"]["beat01"]["primaryAction"]["action"] = "抬手然后推开木门"


def _leak_costume_into_identity(arguments: dict[str, Any]) -> None:
    """模拟上一版常见的 identity 混入黑衣与衣袖。"""

    arguments["assets"]["asset01"]["include"]["feature03"] = "黑衣衣袖"


def _leak_identity_into_costume(arguments: dict[str, Any]) -> None:
    """模拟 costume 反向混入脸型。"""

    arguments["assets"]["additionalAssets"][0]["include"]["feature03"] = "清瘦脸型"


def _duplicate_no_bgm_hard_constraint(arguments: dict[str, Any]) -> None:
    """模拟模型重复提交仅句末标点不同的服务器硬约束。"""

    constraint = "禁止背景音乐；只使用各镜头明确写出的同步声音"
    constraints = arguments["negativeConstraints"]
    constraints["additionalConstraints"].extend([f"{constraint}。", constraint])


def _oversize_secret_title(arguments: dict[str, Any]) -> None:
    """模拟含敏感原始片段的超长字段，验证错误边界不回显输入。"""

    arguments["title"] = "RAW_STORY_ARGUMENT_SECRET" * 20


def _inject_secret_asset_values(arguments: dict[str, Any]) -> None:
    """让 Pydantic 原始异常持有秘密实体与特征，验证最终异常链完全断开。"""

    asset = arguments["assets"]["asset01"]
    asset["bindingScope"] = "scene_direct"
    asset["settingId"] = "__NONE__"
    asset["targetEntity"] = "SECRET_ENTITY" * 20
    asset["include"]["feature01"] = "SECRET_FEATURE" * 20


def _write_readable_text_in_action(arguments: dict[str, Any]) -> None:
    """模拟动作重新要求人物阅读原文中的银字。"""

    arguments["beats"]["beat01"]["primaryAction"]["action"] = "阅读盒盖银字"


def _write_readable_text_in_visible_result(arguments: dict[str, Any]) -> None:
    """模拟动作结果把符纹变成清晰可读字迹。"""

    arguments["beats"]["beat01"]["primaryAction"]["visibleResult"] = "银字清晰显现"


def _write_readable_text_in_performance(arguments: dict[str, Any]) -> None:
    """模拟表演指令要求演员辨认可读文字。"""

    arguments["beats"]["beat01"]["performanceDirection"] = "少女停顿半拍后逐字阅读铭文"


def _write_readable_text_in_blocking(arguments: dict[str, Any]) -> None:
    """模拟调度把可读文字当作明确落点。"""

    arguments["beats"]["beat01"]["blocking"] = "少女从画面左侧走到银字前，逐字辨认内容"


def _write_readable_text_in_lighting_result(arguments: dict[str, Any]) -> None:
    """模拟全拍灯光结果照清可读文字。"""

    arguments["beats"]["beat01"]["lightingCue"]["visibleResult"] = "盒盖银字被照亮"


def _write_readable_text_in_key_light_result(arguments: dict[str, Any]) -> None:
    """模拟主光结果照清可读文字。"""

    key_light = arguments["beats"]["beat01"]["lightingCue"]["keyLight"]
    key_light["visibleResult"] = "暖光照清盒盖字迹"


def _qualify_symbol_direction_as_unreadable(arguments: dict[str, Any]) -> None:
    """所有正向导演字段都明确把银字限定为不可辨识抽象符纹。"""

    beat = arguments["beats"]["beat01"]
    beat["primaryAction"]["action"] = "观察不可辨识银字"
    beat["primaryAction"]["visibleResult"] = "抽象符纹亮起但不可读"
    beat["performanceDirection"] = "少女停顿半拍，目光掠过不可辨认铭文后移开"
    beat["blocking"] = "少女从画面左侧走到抽象符纹旁，止于画面中央"
    beat["lightingCue"]["visibleResult"] = "暖光勾出不可识别字迹的起伏"
    beat["lightingCue"]["keyLight"]["visibleResult"] = "暖光扫过不可辨识符文"


def _remove_costume_slot(arguments: dict[str, Any]) -> None:
    """手部或背影场景可以只保留实际需要的 identity 原子槽。"""

    arguments["assets"]["additionalAssets"].pop(0)


def _use_slow_continuous_cross_scale(arguments: dict[str, Any]) -> None:
    """制造共享契约负责拒绝的短时慢推跨尺度镜头。"""

    beat = arguments["beats"]["beat01"]
    beat["cameraSpec"]["movement"] = {
        "support": "dolly",
        "movementType": "dolly_in",
        "travelDistanceMeters": 0.4,
        "rotationDegrees": 0.0,
        "speed": "slow",
        "easing": "ease_in_out",
    }
    beat["shotProgression"] = {
        "startShotSize": "全景",
        "endShotSize": "特写",
        "changeMode": "continuous",
    }


def _use_cut_cross_scale(arguments: dict[str, Any]) -> None:
    """同样的跨尺度需求改为显式切镜后应合法。"""

    _use_slow_continuous_cross_scale(arguments)
    arguments["beats"]["beat01"]["shotProgression"]["changeMode"] = "cut"


def _add_mechanical_item_assets(
    arguments: dict[str, Any],
    *,
    include_initial_keyframe: bool,
) -> None:
    """把冻结核心道具及可选初态关键帧加入机关节拍。"""

    # 位图第一位对应 beat01；机关初态只绑定连续序列起点。
    usage = "1" + "0" * (len(arguments["beats"]) - 1)
    arguments["assets"]["additionalAssets"].append(
        {
            "modality": "image",
            "duty": "prop",
            "bindingScope": "canon_slot",
            "settingId": "item-mechanism-box",
            "targetEntity": "__CANON__",
            "keyframeRole": "not_applicable",
            "include": _text_slots("feature", ["盒体材质", "转轮布局"], 12),
            "exclude": _text_slots("feature", ["手部"], 12),
            "usedInBeats": usage,
        }
    )
    beat = arguments["beats"]["beat01"]
    beat["actionComplexity"] = "mechanical_sequence"
    if include_initial_keyframe:
        arguments["assets"]["additionalAssets"].append(
            {
                "modality": "image",
                "duty": "keyframe",
                "bindingScope": "scene_direct",
                "settingId": "__NONE__",
                "targetEntity": "机关盒关闭初态",
                "keyframeRole": "initial_state",
                "include": _text_slots("feature", ["转轮初始方位", "盒盖闭合"], 12),
                "exclude": _text_slots("feature", ["手部", "可读文字"], 12),
                "usedInBeats": usage,
            }
        )


def _configure_clocktower_arguments(arguments: dict[str, Any]) -> None:
    """把四拍夹具改成与八个钟楼机关事件严格对齐的有效方案。"""

    _add_mechanical_item_assets(arguments, include_initial_keyframe=True)
    beat_values = list(arguments["beats"].values())
    actions = [
        (
            ("沈青", "将铜扣插进齿槽", "铜扣完全嵌入黄铜匣侧面"),
            ("机关", "咬碎铜扣", "铜扣碎裂成数片"),
        ),
        (
            ("黄铜匣盖", "弹开", "匣盖翻开并露出内部罗盘"),
            ("沈青指尖", "触碰罗盘表面", "指尖触及透明表盘"),
        ),
        (
            ("钟楼齿轮", "同时加速旋转", "所有齿轮转速骤增"),
            ("牵引链", "将巨大钟摆提到最高处", "钟摆被链索拉至顶点"),
        ),
        (
            ("巨大钟摆", "轰然落下", "钟摆疾速下坠"),
            ("海侧墙面", "被钟摆砸碎", "墙面碎裂并形成破口"),
        ),
    ]
    motivations = [
        "铜扣插入齿槽后被机关咬碎，锁机强调牺牲瞬间",
        "匣盖弹开且指尖触碰罗盘，拉焦强调发现与试探",
        "齿轮加速并由牵引链提起钟摆，机位强调机关失控",
        "钟摆落下并砸碎墙面，拉远展示冲击结果",
    ]
    performances = [
        "沈青肩膀轻颤，眼神短暂黯淡后恢复冷静",
        "沈青目光落向罗盘，指尖停顿后轻触表盘",
        "沈青手腕一僵，抬头扫视齿轮与钟摆",
        "沈青随撞击后退一步，目光紧盯墙面破口",
    ]
    focus_values = [
        ("沈青右手与铜扣", "沈青右手与铜扣", "locked", 0.0),
        ("黄铜匣盖", "沈青指尖与罗盘表盘", "rack_focus", 1.2),
        ("加速旋转的钟楼齿轮", "牵引链与巨大钟摆", "rack_focus", 1.0),
        ("钟摆与海侧墙面", "钟摆与海侧墙面", "locked", 0.0),
    ]
    for beat, beat_actions, motivation, performance, focus in zip(
        beat_values,
        actions,
        motivations,
        performances,
        focus_values,
        strict=True,
    ):
        primary, secondary = beat_actions
        beat["primaryAction"] = {
            "subject": primary[0],
            "action": primary[1],
            "visibleResult": primary[2],
        }
        beat["secondaryAction"] = {
            "subject": secondary[0],
            "action": secondary[1],
            "visibleResult": secondary[2],
        }
        beat["actionComplexity"] = "mechanical_sequence"
        beat["cameraMotivation"] = motivation
        beat["performanceDirection"] = performance
        beat["blocking"] = "沈青留在机关侧面，动作和视线跟随当前机关变化"
        beat["cameraSpec"]["focus"] = {
            "depthOfField": "medium",
            "startTarget": focus[0],
            "endTarget": focus[1],
            "transition": focus[2],
            "rackDurationSeconds": focus[3],
        }


def _text_slots(prefix: str, values: list[str], count: int) -> dict[str, Any]:
    """把测试文本填入固定槽位，其余位置使用字符串空槽哨兵。"""

    return {
        f"{prefix}{index:02d}": values[index - 1] if index <= len(values) else "__UNUSED__"
        for index in range(1, count + 1)
    }


def _resource() -> RunResource:
    """返回规划器测试共用的不可变任务身份。"""

    return RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )


def _payload(
    *,
    duration_seconds: int = 15,
    source_text: str = "她在暴雨中推开药铺的门，认出了柜台后的人。",
    revision_instruction: str | None = None,
    revision_baseline: ScenePromptSpec | None = None,
) -> VideoPlanJobPayload:
    """返回可按时长和原文定制的冻结长篇视频任务。"""

    return VideoPlanJobPayload(
        projectId="project-1",
        sceneId="scene-1",
        chapterId="chapter-1",
        title="雨夜药铺",
        sourceText=source_text,
        revisionInstruction=revision_instruction,
        revisionBaseline=revision_baseline,
        durationSeconds=duration_seconds,
        ratio="16:9",
        settingSnapshot=_setting_snapshot(),
        planningRoute="responses_json_schema_v1",
        planningModel="deepseek-v4-flash",
        directorDraftVersion="1.4",
    )


def _mechanical_story_beat(
    index: int,
    *units: tuple[str, str, str],
) -> StoryBeatPlanArguments:
    """构造只用于原文事件顺序门禁的最小故事拍。"""

    start = (index - 1) * 4
    return StoryBeatPlanArguments(
        beatId=f"beat-{index:02d}",
        startSecond=start,
        endSecond=start + 4,
        dramaticPurpose=f"推进第{index}拍",
        performanceDirection="人物对当前机关变化作出克制可见反应",
        blocking="人物保持在机关旁，不越过既定轴线",
        actionUnits=[
            CameraActionUnit(subject=subject, action=action, visibleResult=result)
            for subject, action, result in units
        ],
        actionComplexity="mechanical_sequence",
        sound="同步机关拟音",
        referencedAssetIds=[],
    )


def test_source_event_sequence_rejects_missing_and_reordered_mechanical_events() -> None:
    """同拍动作槽和跨拍都必须服从冻结原文的机关事件顺序。"""

    source = (
        "她把铜扣插进齿槽，铜扣被机关咬碎，黄铜匣弹开。"
        "她触到罗盘后齿轮加速，牵引链将钟摆提到最高处，随后落下并砸碎墙面。"
    )
    reordered = [
        _mechanical_story_beat(1, ("她", "插入铜扣", "铜扣进入齿槽")),
        _mechanical_story_beat(2, ("机关", "咬碎铜扣", "铜扣碎裂")),
        _mechanical_story_beat(
            3,
            ("她", "触碰罗盘", "指尖触及表盘"),
            ("黄铜匣", "弹开", "匣内罗盘显现"),
        ),
        _mechanical_story_beat(
            4,
            ("钟摆", "被提到最高后落下", "砸碎墙面"),
            ("齿轮", "加速", "转速明显提高"),
        ),
    ]
    with pytest.raises(
        ValueError,
        match=(
            "VIDEO_PLAN_SOURCE_EVENT_ORDER_INVALID.*"
            "插入 -> 咬碎 -> 弹开 -> 触碰 -> 加速 -> 提起 -> 落下 -> 砸碎"
        ),
    ):
        validate_source_event_sequence(source, reordered, require_structured=False)

    missing = [*reordered[:3], _mechanical_story_beat(4, ("钟摆", "落下", "砸碎墙面"))]
    with pytest.raises(ValueError, match="VIDEO_PLAN_REQUIRED_SOURCE_EVENT_MISSING"):
        validate_source_event_sequence(source, missing, require_structured=False)

    ordered = [
        *reordered[:2],
        _mechanical_story_beat(
            3,
            ("黄铜匣", "弹开", "匣内罗盘显现"),
            ("她", "触碰罗盘", "指尖触及表盘"),
        ),
        _mechanical_story_beat(
            4,
            ("齿轮", "加速", "转速明显提高"),
            ("钟摆", "被提到最高后落下", "砸碎墙面"),
        ),
    ]
    validate_source_event_sequence(source, ordered, require_structured=False)


def test_story_source_event_checklist_locks_balanced_action_slots() -> None:
    """四拍八事件必须在首次请求中得到可直接照填的主次动作槽清单。"""

    source = (
        "她把铜扣插进齿槽，铜扣被机关咬碎，黄铜匣弹开。"
        "她触到罗盘后齿轮加速，牵引链将钟摆提到最高处，随后落下并砸碎墙面。"
    )
    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=_setting_snapshot(),
        beat_ranges=[(0, 4), (4, 8), (8, 12), (12, 15)],
        source_text=source,
    )

    checklist = _story_source_event_checklist(skeleton)

    assert "B01：primaryAction 必须执行 E01(插入)" in checklist
    assert "secondaryAction 必须执行 E02(咬碎)" in checklist
    assert "B02：primaryAction 必须执行 E03(弹开)" in checklist
    assert "B03：primaryAction 必须执行 E05(加速)" in checklist
    assert "B04：primaryAction 必须执行 E07(落下)" in checklist
    assert "响应中不要提交 E 字段" in checklist


def _planner_progress(
    *,
    checkpoint_stage: str = "empty",
    scene_assets_plan: SceneAssetsStageArguments | None = None,
    story_plan: StoryPlanStageArguments | None = None,
    reserved_calls: int = 0,
    inherited_calls: int = 0,
    pending_stage: str | None = None,
) -> VideoPlanProgressResponse:
    """构造与固定规划资源绑定的 active 耐久进度。"""

    return _progress_response(
        VideoPlanProgressQuery(
            protocolVersion="1.0",
            jobId="job-1",
            runId="run-1",
            taskId="task-1",
            novelId="novel-1",
            projectId="project-1",
            sceneId="scene-1",
        ),
        payload=_payload(),
        checkpoint_stage=checkpoint_stage,
        scene_assets_plan=scene_assets_plan,
        story_plan=story_plan,
        reserved_calls=reserved_calls,
        inherited_calls=inherited_calls,
        pending_stage=pending_stage,
    )


def _reservation_response(
    *,
    checkpoint_stage: str,
    stage: str,
    expected_reserved_calls: int,
    inherited_calls: int = 0,
) -> VideoPlanCallReservationResponse:
    """按固定六重身份构造一次严格递增的模型调用预留回执。"""

    return VideoPlanCallReservationResponse.model_validate(
        {
            "protocolVersion": "1.0",
            "eventId": f"reserve-{expected_reserved_calls + 1}",
            "jobId": "job-1",
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "projectId": "project-1",
            "sceneId": "scene-1",
            "checkpointStage": checkpoint_stage,
            "stage": stage,
            "reservedCallsBefore": expected_reserved_calls,
            "attemptState": {
                "reservedCalls": expected_reserved_calls + 1,
                "inheritedCalls": inherited_calls,
                "pendingStage": stage,
            },
        }
    )


@pytest.mark.asyncio
async def test_planner_uses_responses_drafts_and_compiles_fixture_package() -> None:
    """模型只提交创意草案，服务器负责机械字段与最终 Seedance 提示词。"""

    provider = StructuredPlanProvider()
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)
    payload = _payload()

    scene, package = await planner.generate(_resource(), payload)

    assert len(provider.requests) == 3
    scene_request, story_request, camera_request = provider.requests
    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
    ]
    assert all(request.thinkingMode == "disabled" for request in provider.requests)
    assert all(request.tools == [] for request in provider.requests)
    assert all(request.requiredToolName is None for request in provider.requests)
    assert all(
        request.messages[0].content.startswith(_JSON_OBJECT_OUTPUT_RULE)
        for request in provider.requests
    )
    assert "sourceAlias 必须选择给定短别名" in scene_request.messages[0].content
    assert "targetEntity 必须为 null" in scene_request.messages[0].content
    assert "禁止两者同时非 null 或同时为 null" in scene_request.messages[0].content
    assert all(
        request.structuredOutput is not None
        and request.structuredOutput.route == "responses_json_schema_v1"
        for request in provider.requests
    )
    assert all("submit_video_" not in request.model_dump_json() for request in provider.requests)

    scene_format = scene_request.structuredOutput
    story_format = story_request.structuredOutput
    camera_format = camera_request.structuredOutput
    assert scene_format is not None
    assert story_format is not None
    assert camera_format is not None
    assert scene_format.jsonSchema["properties"]["assets"]["type"] == "object"
    assert scene_format.jsonSchema["properties"]["assets"]["required"] == [
        f"asset{index:02d}" for index in range(1, 12)
    ]
    story_beats = story_format.jsonSchema["properties"]["beatsByAlias"]
    assert story_beats["type"] == "object"
    assert story_beats["required"] == [f"B{index:02d}" for index in range(1, 5)]
    assert "primarySourceEventAliases" not in str(story_format.jsonSchema)
    camera_beats = camera_format.jsonSchema["properties"]["beatsByAlias"]
    assert camera_beats["type"] == "object"
    assert camera_beats["required"] == [f"B{index:02d}" for index in range(1, 5)]
    serialized_schemas = str(
        [
            scene_format.jsonSchema,
            story_format.jsonSchema,
            camera_format.jsonSchema,
        ]
    )
    for forbidden in ("settingId", "assetId", "beatId", '"assetUsage"', "usedInBeats"):
        assert forbidden not in serialized_schemas
    assert "assetUsageByAlias" in serialized_schemas

    scene_user = scene_request.messages[1].content
    story_user = story_request.messages[1].content
    camera_user = camera_request.messages[1].content
    assert "C01" in scene_user and "L01" in scene_user
    assert "沈青" in scene_user and "济世药铺" in scene_user
    assert payload.settingSnapshot.fingerprint not in scene_user
    assert "character-shen-qing" not in scene_user
    assert payload.sourceText in scene_user
    assert '"assetAlias":"A01"' in story_user
    assert '"beatAlias":"B01"' in story_user
    assert '"assetId"' not in story_user and '"beatId"' not in story_user
    assert payload.sourceText in story_user
    assert '"beatAlias":"B01"' in camera_user
    assert '"assetId"' not in camera_user and '"beatId"' not in camera_user
    assert payload.sourceText not in camera_user

    assert "短别名" in scene_request.messages[0].content
    assert "不得输出 settingId" in scene_request.messages[0].content
    assert "A 短别名" in story_request.messages[0].content
    assert "primary 表示本拍先发生" in story_request.messages[0].content
    assert "严格保持冻结原文先后顺序" in story_request.messages[0].content
    assert "negativeConstraints 只写最终生成画面或声音" in scene_request.messages[0].content
    assert "B 短别名" in camera_request.messages[0].content
    assert "lightingCue 必须填写 JSON null" in camera_request.messages[0].content
    assert '不能填字符串 "null"、"__INHERIT__"' in camera_request.messages[0].content
    assert "不能提交 continuityMode=inherit 对象" in camera_request.messages[0].content
    assert "zoom 镜头只用 zoom_in/zoom_out" in camera_request.messages[0].content
    assert "zoom_in 结束焦距更大" in camera_request.messages[0].content
    assert "不到 5 秒的拍内 continuous 最多跨一级景别" in camera_request.messages[0].content

    assert package.sceneId == scene.sceneId == "scene-1"
    assert package.promptCharacterCount <= package.maxPromptCharacters
    assert package.fixtureOnly is True
    assert package.previewOnly is True
    assert package.submissionReady is False
    assert package.compileProfile == "seedance_director_v3"
    assert scene.schemaVersion == "1.3"
    assert scene.dramaticArc == "少女闯入药铺，警觉接近，在停顿后认出失散兄长。"
    assert scene.cinematographyBase is not None
    assert scene.cinematographyBase.captureFormat == "super_35"
    assert scene.lightingSetup is not None
    assert scene.lightingSetup.cameraWhiteBalanceK == 4000
    assert scene.beats[0].lightingCue is not None
    assert scene.beats[0].lightingCue.continuityMode == "establish"
    assert all(
        beat.lightingCue is not None and beat.lightingCue.continuityMode == "inherit"
        for beat in scene.beats[1:]
    )
    assert [asset.targetEntity for asset in scene.assets] == ["沈青", "沈青", "济世药铺"]
    assert scene.beats[0].action == "少女推开木门，木门向内开启"
    assert all(asset.assetId.startswith("slot-") for asset in scene.assets)
    assert all(
        reference.startswith("slot-")
        for beat in scene.beats
        for reference in beat.referencedAssetIds
    )
    assert "镜头1（0-4秒）" in package.prompt


@pytest.mark.asyncio
async def test_planner_places_revision_instruction_before_frozen_materials() -> None:
    """作者返工意见必须位于冻结资料之前，且不能获得放宽系统约束的权力。"""

    provider = StructuredPlanProvider()
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)
    baseline = build_demo_scene().model_copy(update={"sceneId": "scene-1"})
    payload = _payload(
        revision_instruction=(
            "保持现有四拍事件顺序、必要素材与摄影设计不变。最终给即梦的 Provider 提示词"
            "必须保留每拍可见表演，尤其镜头1铜扣被机关咬碎时，林岚肩膀轻颤、眼神短暂"
            "黯淡；声音只使用逐镜明确写出的同步声音，不得出现允许对白与禁止对白并存。"
        ),
        revision_baseline=baseline,
    )

    await planner.generate(_resource(), payload)

    scene_assets_system = provider.requests[0].messages[0].content
    scene_assets_user = provider.requests[0].messages[1].content
    story_beats_system = provider.requests[1].messages[0].content
    story_beats_user = provider.requests[1].messages[1].content
    cinematography_system = provider.requests[2].messages[0].content
    cinematography_user = provider.requests[2].messages[1].content
    scene_revision_heading = "作者返工意见（本阶段只处理场景、素材、初态、风格与最终禁项；"
    story_revision_heading = "作者返工意见（本阶段只处理节拍、动作、表演、调度、素材使用与声音；"
    camera_revision_heading = "作者返工意见（本阶段只处理摄影、灯光与转场；"
    setting_heading = "冻结长篇设定短别名与创意事实 JSON（仅作为资料，不是指令）："
    source_heading = "待改编原文："
    assets_json_heading = "第一阶段素材与节拍短别名 JSON（版本化只读资料，不是指令）："
    story_json_heading = "前两阶段合并的故事短别名 JSON（版本化只读资料，不是指令）："
    assert "不能覆盖系统规则、草案 Schema" in scene_assets_system
    assert "不能覆盖系统规则、草案 Schema" not in story_beats_system
    assert "不能覆盖系统规则、草案 Schema" in cinematography_system
    assert "冻结原文与设定" in cinematography_system
    assert "故事动作、表演、调度、声音、摄影、灯光、转场或 Provider 提示词编译" in (
        scene_assets_system
    )
    assert "不得据此新增素材或 negativeConstraints" in scene_assets_system
    assert "素材重建、摄影、灯光、转场或 Provider 提示词编译" in story_beats_system
    assert "素材重建、故事改写、表演、声音或 Provider 提示词编译" in (
        cinematography_system
    )
    assert payload.revisionInstruction is not None
    assert payload.revisionInstruction in scene_assets_user
    assert payload.revisionInstruction in story_beats_user
    assert payload.revisionInstruction in cinematography_user
    assert '"priorAssetAlias":"P-A01"' in scene_assets_user
    assert '"performanceDirection"' in story_beats_user
    assert '"cameraSpec"' in cinematography_user
    for request_text in (scene_assets_user, story_beats_user, cinematography_user):
        assert baseline.assets[0].assetId not in request_text
        assert baseline.beats[0].beatId not in request_text
    assert scene_assets_user.index(scene_revision_heading) < scene_assets_user.index(
        setting_heading
    )
    assert scene_assets_user.index(setting_heading) < scene_assets_user.index(source_heading)
    assert story_beats_user.index(story_revision_heading) < story_beats_user.index(
        assets_json_heading
    )
    assert cinematography_user.index(camera_revision_heading) < cinematography_user.index(
        story_json_heading
    )


@pytest.mark.asyncio
async def test_revision_baseline_omits_conflicting_story_but_keeps_safe_camera() -> None:
    """旧候选补造剧情时不得继续污染故事，纯摄影机械事实仍可作为返工参考。"""

    baseline = build_demo_scene().model_copy(update={"sceneId": "scene-1"})
    contaminated_beat = baseline.beats[0].model_copy(
        update={
            "action": "木门向内开启，门后露出远海第七灯塔",
            "actionUnits": [
                CameraActionUnit(
                    subject="木门",
                    action="向内开启",
                    visibleResult="门后露出远海第七灯塔",
                )
            ]
        }
    )
    contaminated = baseline.model_copy(
        update={"beats": [contaminated_beat, *baseline.beats[1:]]}
    )
    provider = StructuredPlanProvider()

    await ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096).generate(
        _resource(),
        _payload(
            revision_instruction="保持不与原文冲突的摄影设计。",
            revision_baseline=contaminated,
        ),
    )

    story_user = provider.requests[1].messages[1].content
    camera_user = provider.requests[2].messages[1].content
    assert "上一版待审候选的本阶段事实 JSON" not in story_user
    assert "第七灯塔" not in story_user
    assert "上一版待审候选的本阶段事实 JSON" in camera_user
    assert '"cameraSpec"' in camera_user
    assert "第七灯塔" not in camera_user


@pytest.mark.asyncio
async def test_revision_baseline_keeps_camera_mechanics_but_omits_stale_focus_targets() -> None:
    """返工可继承焦段与拉焦方式，但错拍的起止焦点必须让当前摄影阶段重填。"""

    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [_configure_clocktower_arguments],
            _STORY_BEATS_FORMAT_NAME: [_configure_clocktower_arguments],
            _CINEMATOGRAPHY_FORMAT_NAME: [_configure_clocktower_arguments],
        }
    )
    baseline, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload(source_text=_CLOCKTOWER_SOURCE))

    stale_beats = list(baseline.beats)
    stale_focuses = [
        (1, "咬碎的铜扣碎片", "沈青右手与表情"),
        (2, "黄铜匣内罗盘", "沈青指尖与罗盘表盘"),
    ]
    for index, start_target, end_target in stale_focuses:
        camera_spec = stale_beats[index].cameraSpec
        assert camera_spec is not None
        stale_camera_spec = camera_spec.model_copy(
            update={
                "focus": camera_spec.focus.model_copy(
                    update={
                        "startTarget": start_target,
                        "endTarget": end_target,
                    }
                )
            }
        )
        stale_beats[index] = stale_beats[index].model_copy(
            update={"cameraSpec": stale_camera_spec}
        )
    stale_baseline = baseline.model_copy(update={"beats": stale_beats})
    payload = _payload(
        source_text=_CLOCKTOWER_SOURCE,
        revision_instruction="保留机械摄影设计，修正错拍焦点。",
        revision_baseline=stale_baseline,
    )

    context_text = _revision_baseline_context_json(payload, "cinematography")
    assert context_text is not None
    context = json.loads(context_text)
    second_camera = context["beats"][1]["cameraSpec"]
    third_camera = context["beats"][2]["cameraSpec"]
    baseline_second_camera = baseline.beats[1].cameraSpec
    assert baseline_second_camera is not None
    assert second_camera["focalLengthMm"] == baseline_second_camera.focalLengthMm
    assert second_camera["movement"] == baseline_second_camera.movement.model_dump(mode="json")
    assert second_camera["focus"]["transition"] == "rack_focus"
    assert "startTarget" not in second_camera["focus"]
    assert "endTarget" not in second_camera["focus"]
    assert "startTarget" not in third_camera["focus"]
    assert "endTarget" not in third_camera["focus"]
    stale_second_camera = stale_baseline.beats[1].cameraSpec
    assert stale_second_camera is not None
    assert stale_second_camera.focus.startTarget == "咬碎的铜扣碎片"


@pytest.mark.asyncio
async def test_planner_omits_revision_block_for_initial_jobs() -> None:
    """首次生成不能被伪造成作者提出过返工意见。"""

    provider = StructuredPlanProvider()
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)

    await planner.generate(_resource(), _payload())

    scene_assets_user = provider.requests[0].messages[1].content
    story_beats_user = provider.requests[1].messages[1].content
    cinematography_user = provider.requests[2].messages[1].content
    assert "作者返工意见" not in scene_assets_user
    assert "作者返工意见" not in story_beats_user
    assert "作者返工意见" not in cinematography_user
    assert "冻结长篇设定短别名" in scene_assets_user
    assert "待改编原文" in scene_assets_user
    assert "第一阶段素材与节拍短别名 JSON" in story_beats_user
    assert "前两阶段合并的故事短别名 JSON" in cinematography_user


@pytest.mark.asyncio
async def test_planner_reports_only_safe_structured_output_diagnostics() -> None:
    """结构失败只回显稳定 code、JSON Pointer 和 keyword。"""

    provider = InvalidStructuredPlanProvider()
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=2_000)

    with pytest.raises(RuntimeError) as exc_info:
        await planner.generate(_resource(), _payload())

    error_message = str(exc_info.value)
    assert len(provider.requests) == 3
    assert "code=schema_violation" in error_message
    assert "pointer=/assets/0/sourceAlias" in error_message
    assert "keyword=enum" in error_message
    assert "场景素材阶段" in error_message
    assert "RAW_ARGUMENT_SECRET" not in error_message
    assert "arguments=" not in error_message
    assert "completion/max tokens=" not in error_message
    assert "args=" not in error_message
    assert "error=" not in error_message


@pytest.mark.asyncio
async def test_planner_rejects_legacy_route_without_model_call() -> None:
    """旧活动任务只能显式重试，不能在同一 task 中切换模型协议。"""

    provider = StructuredPlanProvider()
    payload = _payload().model_copy(update={"planningRoute": "legacy_strict_tool_v1"})

    with pytest.raises(VideoPlanGenerationError, match="VIDEO_PLAN_LEGACY_ROUTE_RETRY_REQUIRED"):
        await ModelVideoScenePlanner(
            ModelRuntime(provider),
            max_output_tokens=2_000,
        ).generate(_resource(), payload)

    assert provider.requests == []


@pytest.mark.asyncio
async def test_planner_rejects_old_director_draft_version_without_model_call() -> None:
    """旧故事草案任务必须显式重试升级，不能在原 taskId 下静默改成 v2。"""

    provider = StructuredPlanProvider()
    payload = _payload().model_copy(update={"directorDraftVersion": "1.0"})

    with pytest.raises(
        VideoPlanGenerationError,
        match="VIDEO_PLAN_DRAFT_VERSION_RETRY_REQUIRED",
    ):
        await ModelVideoScenePlanner(
            ModelRuntime(provider),
            max_output_tokens=2_000,
        ).generate(_resource(), payload)

    assert provider.requests == []


@pytest.mark.asyncio
async def test_planner_rejects_frozen_model_mismatch_before_reservation() -> None:
    """运行时模型不等于任务冻结模型时，不能预留额度或调用供应商。"""

    provider = StructuredPlanProvider()
    provider.model_name = "deepseek-chat"
    reservations: list[tuple[object, object, int]] = []

    async def reserve_call(
        checkpoint_stage: object,
        stage: object,
        expected_reserved_calls: int,
        inherited_calls: int,
    ) -> VideoPlanCallReservationResponse:
        assert inherited_calls == 0
        reservations.append((checkpoint_stage, stage, expected_reserved_calls))
        raise AssertionError("冻结模型不一致时不应预留调用额度")

    with pytest.raises(VideoPlanGenerationError, match="VIDEO_PLAN_PROVIDER_MISMATCH"):
        await ModelVideoScenePlanner(
            ModelRuntime(provider),
            max_output_tokens=2_000,
        ).generate(_resource(), _payload(), reserve_call=reserve_call)

    assert reservations == []
    assert provider.requests == []


@pytest.mark.asyncio
async def test_planner_rejects_unavailable_responses_route_before_reservation() -> None:
    """供应商实例不支持冻结路由时，不能预留额度或尝试模型请求。"""

    provider = UnsupportedStructuredPlanProvider()
    reservations: list[tuple[object, object, int]] = []

    async def reserve_call(
        checkpoint_stage: object,
        stage: object,
        expected_reserved_calls: int,
        inherited_calls: int,
    ) -> VideoPlanCallReservationResponse:
        assert inherited_calls == 0
        reservations.append((checkpoint_stage, stage, expected_reserved_calls))
        raise AssertionError("路由不可用时不应预留调用额度")

    with pytest.raises(
        VideoPlanGenerationError,
        match="VIDEO_PLAN_STRUCTURED_ROUTE_UNAVAILABLE",
    ):
        await ModelVideoScenePlanner(
            ModelRuntime(provider),
            max_output_tokens=2_000,
        ).generate(_resource(), _payload(), reserve_call=reserve_call)

    assert reservations == []
    assert provider.requests == []


@pytest.mark.asyncio
async def test_chat_json_output_route_fails_before_model_call() -> None:
    """没有逐阶段最小实例前，Chat JSON fallback 不能进入视频主链。"""

    provider = StructuredPlanProvider()
    payload = _payload().model_copy(update={"planningRoute": "chat_json_output_v1"})

    with pytest.raises(
        VideoPlanGenerationError,
        match="VIDEO_PLAN_CHAT_FALLBACK_NOT_ENABLED",
    ):
        await ModelVideoScenePlanner(
            ModelRuntime(provider),
            max_output_tokens=4_096,
        ).generate(_resource(), payload)

    assert provider.requests == []


@pytest.mark.asyncio
async def test_story_correction_keeps_global_budget_and_then_runs_camera_once() -> None:
    """故事节拍首次失败只重做当前阶段，单次执行最坏仍为四次调用。"""

    provider = StructuredPlanProvider(
        stage_mutators={
            "video_story_beats_draft_v4": [_add_bgm_to_first_sound, None],
        }
    )
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        "video_scene_assets_draft_v1",
        "video_story_beats_draft_v4",
        "video_story_beats_draft_v4",
        "video_cinematography_draft_v2",
    ]
    assert "故事节拍阶段：VIDEO_PLAN_MUSIC_FORBIDDEN" in provider.requests[2].messages[1].content
    assert _JSON_OBJECT_OUTPUT_RULE in provider.requests[2].messages[1].content


@pytest.mark.asyncio
async def test_story_unused_asset_correction_uses_model_visible_alias() -> None:
    """故事返工只能报告模型认识的 A 别名，不能泄露 canonical assetId。"""

    def omit_last_asset(arguments: dict[str, Any]) -> None:
        assets = [
            arguments["assets"]["asset01"],
            *arguments["assets"]["additionalAssets"],
        ]
        assets[-1]["usedInBeats"] = "0" * len(arguments["beats"])

    provider = StructuredPlanProvider(
        stage_mutators={
            _STORY_BEATS_FORMAT_NAME: [omit_last_asset, None],
        }
    )
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    correction = provider.requests[2].messages[1].content
    assert "VIDEO_DRAFT_ASSET_USAGE_MISSING" in correction
    assert "素材使用表缺少 A" in correction
    assert "asset0" not in correction


@pytest.mark.asyncio
async def test_scene_asset_correction_repeats_source_target_exclusivity() -> None:
    """第一阶段返工必须明确重申设定别名与临时目标的两个合法形状。"""

    def duplicate_first_asset(arguments: dict[str, Any]) -> None:
        arguments["assets"]["additionalAssets"].append(dict(arguments["assets"]["asset01"]))

    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [duplicate_first_asset, None],
        }
    )
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
    ]
    correction = provider.requests[1].messages[1].content
    assert "sourceAlias 必须选择给定短别名" in correction
    assert "targetEntity 必须为 null" in correction
    assert "禁止两者同时非 null 或同时为 null" in correction
    assert "L 只用于 scene" in correction
    assert "I 只用于 prop" in correction


@pytest.mark.asyncio
async def test_scene_assets_can_use_both_shared_corrections_before_later_stages() -> None:
    """素材连续暴露两个不同错误时可第三次交稿，后续两阶段仍各有一次调用。"""

    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [
                _leak_costume_into_identity,
                _leak_identity_into_costume,
                None,
            ],
        }
    )
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _SCENE_ASSETS_FORMAT_NAME,
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
    ]
    assert "VIDEO_PLAN_IDENTITY_FEATURE_LEAK" in provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_COSTUME_FEATURE_LEAK" in provider.requests[2].messages[1].content


@pytest.mark.asyncio
async def test_scene_asset_correction_rejects_internal_workflow_negative_constraints() -> None:
    """返工过程和协议字段不能作为供应商禁止项污染最终提示词。"""

    def leak_internal_constraint(arguments: dict[str, Any]) -> None:
        arguments["negativeConstraints"]["additionalConstraints"].append(
            "镜头2不得引用R01或输出settingId"
        )

    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [leak_internal_constraint, None],
        }
    )

    scene, package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    correction = provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_NEGATIVE_CONSTRAINT_INTERNAL_LEAK" in correction
    assert "只能包含最终画面或声音禁项" in correction
    assert "只能通过省略对应槽位执行" in correction
    assert "不得把素材职责名" in correction
    assert "R01" not in package.prompt
    assert "settingId" not in package.prompt


@pytest.mark.asyncio
async def test_relation_asset_requires_both_participants_in_source() -> None:
    """关系素材不能把只在背景设定中存在、未在本场出场的人物硬塞进镜头。"""

    def add_background_relation(arguments: dict[str, Any]) -> None:
        arguments["assets"]["additionalAssets"].append(
            {
                "modality": "image",
                "duty": "relation_interaction",
                "bindingScope": "canon_slot",
                "settingId": "relationship-allies",
                "targetEntity": "__CANON__",
                "keyframeRole": "not_applicable",
                "include": _text_slots("feature", ["并肩守望", "互相信任"], 12),
                "exclude": _text_slots("feature", ["敌对姿态"], 12),
                "usedInBeats": "1" * len(arguments["beats"]),
            }
        )

    def remove_background_entries(arguments: dict[str, Any]) -> None:
        arguments["assets"]["additionalAssets"] = [
            asset
            for asset in arguments["assets"]["additionalAssets"]
            if asset["settingId"] not in {"character-z-lin-lan", "relationship-allies"}
        ]

    snapshot = LongSerialSettingSnapshot.from_entries(
        [
            *_setting_snapshot().entries,
            CharacterSettingSnapshot(
                id="character-z-lin-lan",
                contentHash="d" * 64,
                name="林岚",
                aliases=[],
                appearance="短发，左眉浅疤",
                identity="潮汐钟楼守护者",
            ),
            RelationshipSettingSnapshot(
                id="relationship-allies",
                contentHash="e" * 64,
                name="守望同盟",
                sourceCharacterId="character-shen-qing",
                targetCharacterId="character-z-lin-lan",
                relationType="盟友",
                description="共同守护潮汐记忆",
            ),
        ]
    )
    payload = _payload(source_text="沈青独自在暴雨中推开药铺的门。")
    payload = payload.model_copy(update={"settingSnapshot": snapshot})
    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [add_background_relation, remove_background_entries],
        }
    )

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), payload)

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
    ]
    system_prompt = provider.requests[0].messages[0].content
    correction = provider.requests[1].messages[1].content
    assert "关系两端人物都在本场原文逐字出现" in system_prompt
    assert "只有一端人物出现" in system_prompt
    assert "VIDEO_PLAN_RELATION_ASSET_PARTICIPANTS_MISSING" in correction
    assert "关系两端人物都在原文出现的本场互动" in correction


@pytest.mark.asyncio
async def test_character_asset_requires_character_mentioned_in_source() -> None:
    """背景快照人物未在原文出场时，不能生成其身份、服装或声线素材。"""

    def add_background_character(arguments: dict[str, Any]) -> None:
        arguments["assets"]["additionalAssets"].append(
            {
                "modality": "image",
                "duty": "identity",
                "bindingScope": "canon_slot",
                "settingId": "character-z-lin-lan",
                "targetEntity": "__CANON__",
                "keyframeRole": "not_applicable",
                "include": _text_slots("feature", ["短发", "左眉浅疤"], 12),
                "exclude": _text_slots("feature", ["现代妆容"], 12),
                "usedInBeats": "1" * len(arguments["beats"]),
            }
        )

    def remove_background_character(arguments: dict[str, Any]) -> None:
        arguments["assets"]["additionalAssets"] = [
            asset
            for asset in arguments["assets"]["additionalAssets"]
            if asset["settingId"] != "character-z-lin-lan"
        ]

    snapshot = LongSerialSettingSnapshot.from_entries(
        [
            *_setting_snapshot().entries,
            CharacterSettingSnapshot(
                id="character-z-lin-lan",
                contentHash="d" * 64,
                name="林岚",
                aliases=[],
                appearance="短发，左眉浅疤",
                identity="潮汐钟楼守护者",
            ),
        ]
    )
    payload = _payload(source_text="沈青独自在暴雨中推开药铺的门。")
    payload = payload.model_copy(update={"settingSnapshot": snapshot})
    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [add_background_character, remove_background_character]
        }
    )

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), payload)

    assert scene.sceneId == "scene-1"
    correction = provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_CHARACTER_ASSET_NOT_IN_SCENE" in correction
    assert "移除 C02 对应的 identity、costume、voice 素材" in correction
    assert "姓名或别名在本场原文出现" in correction


@pytest.mark.asyncio
async def test_scene_asset_rejects_foley_disguised_as_voice() -> None:
    """动作拟音不能为了占用音频槽伪装成人物 voice 素材。"""

    def add_foley_voice(arguments: dict[str, Any]) -> None:
        arguments["assets"]["additionalAssets"].append(
            {
                "modality": "audio",
                "duty": "voice",
                "bindingScope": "scene_direct",
                "settingId": "__NONE__",
                "targetEntity": "沈青动作触感声",
                "keyframeRole": "not_applicable",
                "include": _text_slots(
                    "feature",
                    ["门轴摩擦", "金属卡合", "机关碎裂", "指尖触碰"],
                    12,
                ),
                "exclude": _text_slots("feature", ["对白", "音乐"], 12),
                "usedInBeats": "1" * len(arguments["beats"]),
            }
        )

    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [add_foley_voice, None],
        }
    )

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert all(asset.duty != "voice" for asset in scene.assets)
    system_prompt = provider.requests[0].messages[0].content
    correction = provider.requests[1].messages[1].content
    assert "同步拟音直接写进逐拍 sound" in system_prompt
    assert "VIDEO_PLAN_VOICE_ASSET_INVALID" in correction


@pytest.mark.asyncio
async def test_scene_asset_rejects_camera_reference_owned_by_cinematography() -> None:
    """自动素材不能创建一套与逐拍 cameraSpec 竞争的全局运镜参考。"""

    def add_camera_reference(arguments: dict[str, Any]) -> None:
        arguments["assets"]["additionalAssets"].append(
            {
                "modality": "video",
                "duty": "camera",
                "bindingScope": "scene_direct",
                "settingId": "__NONE__",
                "targetEntity": "连续观察视角运镜",
                "keyframeRole": "not_applicable",
                "include": _text_slots("feature", ["缓慢推进", "单一观察视角"], 12),
                "exclude": _text_slots("feature", ["切镜"], 12),
                "usedInBeats": "1" * len(arguments["beats"]),
            }
        )

    provider = StructuredPlanProvider(
        stage_mutators={_SCENE_ASSETS_FORMAT_NAME: [add_camera_reference, None]}
    )

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert all(asset.duty != "camera" for asset in scene.assets)
    correction = provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_CAMERA_ASSET_FORBIDDEN" in correction


@pytest.mark.asyncio
async def test_scene_asset_rejects_negative_constraint_banning_required_foley() -> None:
    """不创建 voice 槽不能被模型曲解成禁止机关、金属和环境声音。"""

    def ban_required_foley(arguments: dict[str, Any]) -> None:
        arguments["negativeConstraints"]["additionalConstraints"].extend(
            [
                "不出现铜扣碎裂声或机关触发声",
                "禁止齿轮转动的环境音效",
            ]
        )

    provider = StructuredPlanProvider(
        stage_mutators={_SCENE_ASSETS_FORMAT_NAME: [ban_required_foley, None]}
    )

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    correction = provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_REQUIRED_SYNC_SOUND_BANNED" in correction


@pytest.mark.asyncio
async def test_scene_asset_rejects_negative_constraint_banning_source_events() -> None:
    """关键帧局部排除项不能扩散成禁止冻结原文事件的全片禁项。"""

    def ban_required_visual_events(arguments: dict[str, Any]) -> None:
        arguments["negativeConstraints"]["additionalConstraints"].append(
            "不得出现铜扣碎裂、匣盖弹开或钟摆落下等初态之后的画面"
        )

    provider = StructuredPlanProvider(
        stage_mutators={_SCENE_ASSETS_FORMAT_NAME: [ban_required_visual_events, None]}
    )
    payload = _payload(source_text="机关夹住铜扣，铜扣随即碎裂。")

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), payload)

    assert scene.sceneId == "scene-1"
    correction = provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_REQUIRED_VISUAL_EVENT_BANNED" in correction


@pytest.mark.asyncio
async def test_scene_asset_rejects_global_ban_on_required_character_performance() -> None:
    """素材阶段不生成表演字段，不能被扩散成与逐拍表演冲突的全片禁项。"""

    def ban_required_performance(arguments: dict[str, Any]) -> None:
        arguments["negativeConstraints"]["additionalConstraints"].append(
            "无角色表演或对白内容"
        )

    provider = StructuredPlanProvider(
        stage_mutators={_SCENE_ASSETS_FORMAT_NAME: [ban_required_performance, None]}
    )

    scene, package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    correction = provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_REQUIRED_PERFORMANCE_BANNED" in correction
    assert "需要无对白时只能精确禁止对白" in correction
    assert "无角色表演或对白内容" not in package.prompt
    assert all(beat.performanceDirection for beat in scene.beats)


@pytest.mark.asyncio
async def test_scene_asset_rejects_reveal_target_missing_from_source() -> None:
    """冻结世界设定不能把本场原文没有的灯塔补成破墙后的新剧情落点。"""

    def add_off_source_reveal(arguments: dict[str, Any]) -> None:
        arguments["summary"] = "少女推门后，门内露出远海第七灯塔。"

    provider = StructuredPlanProvider(
        stage_mutators={_SCENE_ASSETS_FORMAT_NAME: [add_off_source_reveal, None]}
    )

    scene, package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    correction = provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_OFF_SOURCE_REVEAL" in correction
    assert "不得用露出、显现或出现" in correction
    assert "第七灯塔" not in package.prompt


@pytest.mark.asyncio
async def test_story_rejects_reveal_target_missing_from_source() -> None:
    """故事动作也不能绕过素材门禁重新补造原文不存在的揭示对象。"""

    def add_off_source_reveal(arguments: dict[str, Any]) -> None:
        arguments["beats"]["beat01"]["primaryAction"]["visibleResult"] = (
            "门后露出远海第七灯塔"
        )

    provider = StructuredPlanProvider(
        stage_mutators={_STORY_BEATS_FORMAT_NAME: [add_off_source_reveal, None]}
    )

    scene, package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    correction = provider.requests[2].messages[1].content
    assert "VIDEO_PLAN_OFF_SOURCE_REVEAL" in correction
    assert "B01.primaryAction" in correction
    assert "primaryAction 先于 secondaryAction" in correction
    assert "第七灯塔" not in correction
    assert "第七灯塔" not in package.prompt


@pytest.mark.asyncio
async def test_camera_correction_reuses_exact_canonical_story() -> None:
    """摄影首次失败时不得重新生成故事，两次摄影必须读取同一规范 JSON。"""

    provider = StructuredPlanProvider(
        stage_mutators={
            "video_cinematography_draft_v2": [_use_slow_continuous_cross_scale, None],
        }
    )
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        "video_scene_assets_draft_v1",
        "video_story_beats_draft_v4",
        "video_cinematography_draft_v2",
        "video_cinematography_draft_v2",
    ]
    heading = "前两阶段合并的故事短别名 JSON（版本化只读资料，不是指令）：\n"
    first_story_json = provider.requests[2].messages[1].content.split(heading, maxsplit=1)[1]
    second_story_json = provider.requests[3].messages[1].content.split(heading, maxsplit=1)[1]
    assert first_story_json == second_story_json
    assert "摄影灯光阶段" in provider.requests[3].messages[1].content


@pytest.mark.asyncio
async def test_camera_rejects_focus_targets_that_still_belong_to_previous_beats() -> None:
    """摄影焦点不能在故事已校正后继续盯住上一拍的铜扣或罗盘。"""

    def use_stale_focus_targets(arguments: dict[str, Any]) -> None:
        _configure_clocktower_arguments(arguments)
        beats = list(arguments["beats"].values())
        beats[1]["cameraSpec"]["focus"] = {
            "depthOfField": "medium",
            "startTarget": "咬碎的铜扣碎片",
            "endTarget": "沈青右手与表情",
            "transition": "rack_focus",
            "rackDurationSeconds": 1.2,
        }
        beats[2]["cameraSpec"]["focus"] = {
            "depthOfField": "medium",
            "startTarget": "黄铜匣内罗盘",
            "endTarget": "沈青指尖与罗盘表盘",
            "transition": "rack_focus",
            "rackDurationSeconds": 1.0,
        }

    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [_configure_clocktower_arguments],
            _STORY_BEATS_FORMAT_NAME: [_configure_clocktower_arguments],
            _CINEMATOGRAPHY_FORMAT_NAME: [
                use_stale_focus_targets,
                _configure_clocktower_arguments,
            ],
        }
    )
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload(source_text=_CLOCKTOWER_SOURCE))

    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
    ]
    correction = provider.requests[3].messages[1].content
    assert "VIDEO_PLAN_CAMERA_FOCUS_EVENT_MISMATCH" in correction
    assert "B02、B03" in correction
    assert "focus.startTarget/endTarget" in correction
    assert scene.beats[1].cameraSpec is not None
    assert scene.beats[1].cameraSpec.focus.startTarget == "黄铜匣盖"
    assert scene.beats[2].cameraSpec is not None
    assert scene.beats[2].cameraSpec.focus.startTarget == "加速旋转的钟楼齿轮"


@pytest.mark.asyncio
async def test_camera_composition_allows_benign_appearance_wording() -> None:
    """构图层的“出现薄雾”是布景描述，不能套用剧情揭示句门禁误杀。"""

    def add_benign_composition_wording(arguments: dict[str, Any]) -> None:
        second = list(arguments["beats"].values())[1]
        second["cameraSpec"]["composition"]["foregroundLayer"] = (
            "前景出现潮湿薄雾与黄铜边缘"
        )

    provider = StructuredPlanProvider(
        stage_mutators={
            _CINEMATOGRAPHY_FORMAT_NAME: [add_benign_composition_wording],
        }
    )
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.beats[1].cameraSpec is not None
    assert "出现潮湿薄雾" in scene.beats[1].cameraSpec.composition.foregroundLayer
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_camera_composition_rejects_explicit_off_source_lighthouse() -> None:
    """焦点和构图仍不得把原文没有的第七灯塔重新塞回最终提示词。"""

    def add_off_source_lighthouse(arguments: dict[str, Any]) -> None:
        second = list(arguments["beats"].values())[1]
        second["cameraSpec"]["composition"]["backgroundLayer"] = (
            "破口后方的远海第七灯塔"
        )

    provider = StructuredPlanProvider(
        stage_mutators={
            _CINEMATOGRAPHY_FORMAT_NAME: [add_off_source_lighthouse, None],
        }
    )
    scene, package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    correction = provider.requests[3].messages[1].content
    assert "VIDEO_PLAN_OFF_SOURCE_REVEAL" in correction
    assert "B02" in correction
    assert "第七灯塔" not in package.prompt
    assert scene.sceneId == "scene-1"


@pytest.mark.asyncio
async def test_visible_light_change_requires_motivated_lighting_cue() -> None:
    """故事已经写出新光束时，摄影阶段不能继续用 null 继承上一拍灯光。"""

    def add_visible_light_change(arguments: dict[str, Any]) -> None:
        last_beat = next(reversed(arguments["beats"].values()))
        last_beat["primaryAction"]["visibleResult"] = "墙洞中冷白光束透入"

    def add_motivated_lighting_change(arguments: dict[str, Any]) -> None:
        last_beat = next(reversed(arguments["beats"].values()))
        cue = _establish_lighting_cue()
        cue.update(
                {
                    "continuityMode": "motivated_change",
                    "motivatedChange": "墙洞形成后冷白月光透入",
                "atmosphere": "冷白光束穿过墙洞与潮湿空气",
                "visibleResult": "冷白光束切开药铺原有暖暗层次",
            }
        )
        cue["keyLight"].update(
            {
                    "motivatedBy": "墙洞外射入的冷白月光",
                "colorTemperatureK": 6500,
                "visibleResult": "冷白光束落在墙洞边缘与少女侧脸",
            }
        )
        last_beat["lightingCue"] = cue

    provider = StructuredPlanProvider(
        stage_mutators={
            _STORY_BEATS_FORMAT_NAME: [add_visible_light_change],
            _CINEMATOGRAPHY_FORMAT_NAME: [None, add_motivated_lighting_change],
        }
    )

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
    ]
    correction = provider.requests[3].messages[1].content
    assert "VIDEO_PLAN_LIGHTING_CHANGE_REQUIRED" in correction
    assert "B04" in correction
    assert "lightingCue 必须使用 motivated_change" in correction
    assert scene.beats[-1].lightingCue is not None
    assert scene.beats[-1].lightingCue.continuityMode == "motivated_change"


@pytest.mark.asyncio
async def test_planner_saves_story_checkpoint_after_semantic_gate() -> None:
    """前两阶段仅在各自语义门禁通过后保存对应 canonical 检查点。"""

    provider = StructuredPlanProvider()
    checkpoints: list[
        tuple[
            str,
            SceneAssetsStageArguments | None,
            StoryPlanStageArguments | None,
            VideoPlanAttemptState,
            list[str | None],
        ]
    ] = []

    async def save_checkpoint(
        checkpoint_stage: str,
        scene_assets: SceneAssetsStageArguments | None,
        story: StoryPlanStageArguments | None,
        attempt_state: VideoPlanAttemptState,
    ) -> None:
        checkpoints.append(
            (
                checkpoint_stage,
                scene_assets,
                story,
                attempt_state,
                [_request_format_name(request) for request in provider.requests],
            )
        )

    await ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096).generate(
        _resource(),
        _payload(),
        save_checkpoint=save_checkpoint,  # type: ignore[arg-type]
    )

    assert len(checkpoints) == 2
    assets_stage, scene_assets, no_story, first_attempt, first_tools = checkpoints[0]
    assert assets_stage == "scene_assets"
    assert scene_assets is not None and scene_assets.schemaVersion == "1.0"
    assert no_story is None
    assert first_attempt == VideoPlanAttemptState(reservedCalls=1, pendingStage=None)
    assert first_tools == ["video_scene_assets_draft_v1"]
    story_stage, no_assets, story, second_attempt, second_tools = checkpoints[1]
    assert story_stage == "story"
    assert no_assets is None
    assert story is not None and story.schemaVersion == "2.0"
    assert second_attempt == VideoPlanAttemptState(reservedCalls=2, pendingStage=None)
    assert second_tools == ["video_scene_assets_draft_v1", "video_story_beats_draft_v4"]


@pytest.mark.asyncio
async def test_camera_correction_persists_used_budget_before_retry() -> None:
    """每次摄影调用前都先完成调用账本预留，第二次预留把总数推进到四。"""

    provider = StructuredPlanProvider(
        stage_mutators={
            "video_cinematography_draft_v2": [_use_slow_continuous_cross_scale, None],
        }
    )
    reservations: list[tuple[str, str, int, int]] = []

    async def reserve_call(
        checkpoint_stage: str,
        stage: str,
        expected_reserved_calls: int,
        inherited_calls: int,
    ) -> VideoPlanCallReservationResponse:
        assert inherited_calls == 0
        reservations.append(
            (checkpoint_stage, stage, expected_reserved_calls, len(provider.requests))
        )
        return _reservation_response(
            checkpoint_stage=checkpoint_stage,
            stage=stage,
            expected_reserved_calls=expected_reserved_calls,
            inherited_calls=inherited_calls,
        )

    await ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096).generate(
        _resource(),
        _payload(),
        reserve_call=reserve_call,  # type: ignore[arg-type]
    )

    assert reservations == [
        ("empty", "scene_assets", 0, 0),
        ("scene_assets", "story_beats", 1, 1),
        ("story", "cinematography", 2, 2),
        ("story", "cinematography", 3, 3),
    ]


@pytest.mark.asyncio
async def test_camera_may_use_two_corrections_within_five_call_limit() -> None:
    """摄影的多层门禁可先后暴露两个错误，但第五次仍是硬上限。"""

    provider = StructuredPlanProvider(
        stage_mutators={
            "video_cinematography_draft_v2": [
                _use_slow_continuous_cross_scale,
                _use_slow_continuous_cross_scale,
                None,
            ],
        }
    )

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        "video_scene_assets_draft_v1",
        "video_story_beats_draft_v4",
        "video_cinematography_draft_v2",
        "video_cinematography_draft_v2",
        "video_cinematography_draft_v2",
    ]


@pytest.mark.asyncio
async def test_planner_resumes_story_checkpoint_without_regenerating_story() -> None:
    """重放读取到故事检查点后必须直接进入摄影阶段。"""

    story = _story_checkpoint_fixture()

    replay_provider = StructuredPlanProvider()
    await ModelVideoScenePlanner(
        ModelRuntime(replay_provider),
        max_output_tokens=4096,
    ).generate(
        _resource(),
        _payload(),
        progress=_planner_progress(
            checkpoint_stage="story",
            story_plan=story,
            reserved_calls=2,
        ),
    )

    assert [_request_format_name(request) for request in replay_provider.requests] == [
        "video_cinematography_draft_v2"
    ]


@pytest.mark.asyncio
async def test_planner_uses_inherited_story_baseline_with_fresh_retry_ledger() -> None:
    """跨 task 重试从故事开始时，当前任务首次预留计数仍从零开始。"""

    provider = StructuredPlanProvider()
    reservations: list[tuple[str, str, int, int]] = []

    async def reserve_call(
        checkpoint_stage: str,
        stage: str,
        expected_reserved_calls: int,
        inherited_calls: int,
    ) -> VideoPlanCallReservationResponse:
        reservations.append(
            (checkpoint_stage, stage, expected_reserved_calls, inherited_calls)
        )
        return _reservation_response(
            checkpoint_stage=checkpoint_stage,
            stage=stage,
            expected_reserved_calls=expected_reserved_calls,
            inherited_calls=inherited_calls,
        )

    await ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096).generate(
        _resource(),
        _payload(),
        progress=_planner_progress(
            checkpoint_stage="story",
            story_plan=_story_checkpoint_fixture(),
            reserved_calls=0,
            inherited_calls=2,
        ),
        reserve_call=reserve_call,
    )

    assert reservations == [("story", "cinematography", 0, 2)]
    assert [_request_format_name(request) for request in provider.requests] == [
        "video_cinematography_draft_v2"
    ]


@pytest.mark.asyncio
async def test_planner_resumes_pending_camera_with_only_fourth_reservation() -> None:
    """摄影首调结果未知时，只允许预留全局第四次并重做摄影，不重跑前两阶段。"""

    provider = StructuredPlanProvider()
    reservations: list[tuple[str, str, int]] = []

    async def reserve_call(
        checkpoint_stage: str,
        stage: str,
        expected_reserved_calls: int,
        inherited_calls: int,
    ) -> VideoPlanCallReservationResponse:
        assert inherited_calls == 0
        reservations.append((checkpoint_stage, stage, expected_reserved_calls))
        return _reservation_response(
            checkpoint_stage=checkpoint_stage,
            stage=stage,
            expected_reserved_calls=expected_reserved_calls,
            inherited_calls=inherited_calls,
        )

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(
        _resource(),
        _payload(),
        progress=_planner_progress(
            checkpoint_stage="story",
            story_plan=_story_checkpoint_fixture(),
            reserved_calls=3,
            pending_stage="cinematography",
        ),
        reserve_call=reserve_call,  # type: ignore[arg-type]
    )

    assert scene.sceneId == "scene-1"
    assert reservations == [("story", "cinematography", 3)]
    assert [_request_format_name(request) for request in provider.requests] == [
        "video_cinematography_draft_v2"
    ]


@pytest.mark.asyncio
async def test_resumed_used_budget_never_creates_a_sixth_model_call() -> None:
    """已耐久到五次且摄影 pending 时必须零模型失败，不能重复供应商调用。"""

    replay_provider = StructuredPlanProvider()
    with pytest.raises(VideoPlanGenerationError, match="摄影灯光阶段"):
        await ModelVideoScenePlanner(
            ModelRuntime(replay_provider),
            max_output_tokens=4096,
        ).generate(
            _resource(),
            _payload(),
            progress=_planner_progress(
                checkpoint_stage="story",
                story_plan=_story_checkpoint_fixture(),
                reserved_calls=5,
                pending_stage="cinematography",
            ),
        )
    assert replay_provider.requests == []


@pytest.mark.asyncio
async def test_global_correction_budget_does_not_retry_camera_after_story_retry() -> None:
    """前序已消耗纠正时，摄影仍只剩一次纠正并收敛于五次。"""

    provider = StructuredPlanProvider(
        stage_mutators={
            "video_story_beats_draft_v4": [_add_bgm_to_first_sound, None],
            "video_cinematography_draft_v2": [_use_slow_continuous_cross_scale],
        }
    )
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)

    scene, _package = await planner.generate(_resource(), _payload())

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        "video_scene_assets_draft_v1",
        "video_story_beats_draft_v4",
        "video_story_beats_draft_v4",
        "video_cinematography_draft_v2",
        "video_cinematography_draft_v2",
    ]


@pytest.mark.asyncio
async def test_story_validation_error_does_not_echo_raw_arguments() -> None:
    """本地字段校验失败也只能返回安全字段路径，不能回显供应商原始值。"""

    provider = StructuredPlanProvider(mutator=_oversize_secret_title)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)

    with pytest.raises(RuntimeError) as exc_info:
        await planner.generate(_resource(), _payload())

    error_message = str(exc_info.value)
    assert "场景素材阶段" in error_message
    assert "RAW_STORY_ARGUMENT_SECRET" not in error_message
    assert "RAW_STORY_ARGUMENT_SECRET" not in provider.requests[1].messages[1].content


@pytest.mark.asyncio
async def test_planner_drops_raw_draft_exception_chain() -> None:
    """最终异常、traceback、cause 与 context 都不能保留供应商草案值。"""

    provider = StructuredPlanProvider(mutator=_inject_secret_asset_values)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4_096)

    with pytest.raises(VideoPlanGenerationError) as exc_info:
        await planner.generate(_resource(), _payload())

    failure = exc_info.value
    rendered = "".join(traceback.format_exception(failure))
    current: BaseException | None = failure
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        rendered += repr(current)
        current = current.__cause__ or current.__context__

    assert "SECRET_ENTITY" not in rendered
    assert "SECRET_FEATURE" not in rendered
    assert failure.__cause__ is None
    assert failure.__context__ is None


@pytest.mark.asyncio
async def test_planner_rejects_setting_reference_outside_frozen_snapshot() -> None:
    """模型引用不存在的设定时，两次纠正后仍失败并保留明确原因。"""

    provider = StructuredPlanProvider(character_reference_id="character-missing")
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)
    payload = VideoPlanJobPayload(
        projectId="project-1",
        sceneId="scene-1",
        chapterId="chapter-1",
        title="雨夜药铺",
        sourceText="她在暴雨中推开药铺的门。",
        durationSeconds=15,
        ratio="16:9",
        settingSnapshot=_setting_snapshot(),
        planningRoute="responses_json_schema_v1",
        planningModel="deepseek-v4-flash",
        directorDraftVersion="1.4",
    )

    with pytest.raises(RuntimeError, match="VIDEO_DRAFT_UNKNOWN_SOURCE_ALIAS"):
        await planner.generate(
            RunResource(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                jobId="job-1",
            ),
            payload,
        )

    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_planner_derives_stable_asset_ids_and_remaps_beats() -> None:
    """wire 固定槽 ID 不得泄漏为最终设定槽位身份。"""

    resource = RunResource(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        jobId="job-1",
    )
    payload = VideoPlanJobPayload(
        projectId="project-1",
        sceneId="scene-1",
        chapterId="chapter-1",
        title="雨夜药铺",
        sourceText="她在暴雨中推开药铺的门。",
        durationSeconds=15,
        ratio="16:9",
        settingSnapshot=_setting_snapshot(),
        planningRoute="responses_json_schema_v1",
        planningModel="deepseek-v4-flash",
        directorDraftVersion="1.4",
    )
    first, _ = await ModelVideoScenePlanner(
        ModelRuntime(StructuredPlanProvider()), max_output_tokens=4096
    ).generate(resource, payload)
    second, _ = await ModelVideoScenePlanner(
        ModelRuntime(StructuredPlanProvider()), max_output_tokens=4096
    ).generate(resource, payload)

    assert [asset.assetId for asset in first.assets] == [asset.assetId for asset in second.assets]
    assert [beat.referencedAssetIds for beat in first.beats] == [
        beat.referencedAssetIds for beat in second.beats
    ]


@pytest.mark.parametrize(
    ("mutator", "error_code", "failed_tool", "request_count"),
    [
        (
            _add_bgm_to_first_sound,
            "VIDEO_PLAN_MUSIC_FORBIDDEN",
            "video_story_beats_draft_v4",
            4,
        ),
        (
            _chain_actions_inside_one_unit,
            "VIDEO_PLAN_ACTION_UNIT_NOT_ATOMIC",
            "video_story_beats_draft_v4",
            4,
        ),
        (
            _leak_costume_into_identity,
            "VIDEO_PLAN_IDENTITY_FEATURE_LEAK",
            "video_scene_assets_draft_v1",
            3,
        ),
        (
            _leak_identity_into_costume,
            "VIDEO_PLAN_COSTUME_FEATURE_LEAK",
            "video_scene_assets_draft_v1",
            3,
        ),
    ],
)
@pytest.mark.asyncio
async def test_planner_retries_payload_aware_director_semantic_errors(
    mutator: PlanMutator,
    error_code: str,
    failed_tool: str,
    request_count: int,
) -> None:
    """结构合法但导演语义持续错误时，必须用完两个共享纠正名额再失败。"""

    provider = StructuredPlanProvider(mutator=mutator)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)

    with pytest.raises(RuntimeError, match=error_code):
        await planner.generate(_resource(), _payload())

    assert len(provider.requests) == request_count
    failed_requests = [
        request for request in provider.requests if _request_format_name(request) == failed_tool
    ]
    assert len(failed_requests) == 3
    assert all(error_code in request.messages[1].content for request in failed_requests[1:])


@pytest.mark.parametrize(
    ("mutator", "failed_tool", "request_count"),
    [
        (_write_readable_text_in_action, "video_story_beats_draft_v4", 4),
        (_write_readable_text_in_visible_result, "video_story_beats_draft_v4", 4),
        (_write_readable_text_in_performance, "video_story_beats_draft_v4", 4),
        (_write_readable_text_in_blocking, "video_story_beats_draft_v4", 4),
        (_write_readable_text_in_lighting_result, "video_cinematography_draft_v2", 5),
        (_write_readable_text_in_key_light_result, "video_cinematography_draft_v2", 5),
    ],
)
@pytest.mark.asyncio
async def test_planner_retries_readable_text_conflicts_from_unreadable_source(
    mutator: PlanMutator,
    failed_tool: str,
    request_count: int,
) -> None:
    """原文触发不可读要求后，所有正向导演字段都不能重新引入可读字迹。"""

    provider = StructuredPlanProvider(mutator=mutator)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)
    payload = _payload(source_text="盒盖上的银色小字随机关转动亮起。")

    with pytest.raises(RuntimeError, match="VIDEO_PLAN_READABLE_TEXT_CONFLICT"):
        await planner.generate(_resource(), payload)

    assert len(provider.requests) == request_count
    failed_requests = [
        request for request in provider.requests if _request_format_name(request) == failed_tool
    ]
    assert len(failed_requests) == 3
    assert all(
        "VIDEO_PLAN_READABLE_TEXT_CONFLICT" in request.messages[1].content
        for request in failed_requests[1:]
    )


@pytest.mark.asyncio
async def test_planner_accepts_explicitly_unreadable_symbol_direction() -> None:
    """同一字段写明不可读、不可辨识或抽象符纹时不应产生正负冲突。"""

    provider = StructuredPlanProvider(mutator=_qualify_symbol_direction_as_unreadable)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)
    payload = _payload(source_text="盒盖上的银色小字随机关转动亮起。")

    scene, _package = await planner.generate(_resource(), payload)

    assert len(provider.requests) == 3
    assert scene.beats[0].actionUnits[0].action == "观察不可辨识银字"
    assert "不可读" in scene.beats[0].actionUnits[0].visibleResult


@pytest.mark.asyncio
async def test_planner_only_applies_readable_text_gate_when_source_requires_it() -> None:
    """普通原文没有银色或发光文字时，不擅自扩大不可读符纹门禁。"""

    provider = StructuredPlanProvider(mutator=_write_readable_text_in_action)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)

    scene, _package = await planner.generate(_resource(), _payload())

    assert len(provider.requests) == 3
    assert scene.beats[0].actionUnits[0].action == "阅读盒盖银字"


@pytest.mark.asyncio
async def test_planner_does_not_require_costume_when_scene_only_needs_identity() -> None:
    """原子槽按画面需要建立，不能把 identity 与 costume 错做成强制成对。"""

    provider = StructuredPlanProvider(mutator=_remove_costume_slot)
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert [asset.duty for asset in scene.assets] == ["identity", "scene"]


@pytest.mark.asyncio
async def test_server_hard_negative_constraint_is_canonical_and_deduplicated() -> None:
    """模型重复或增加句末标点时，服务器仍只保留一条规范禁 BGM 约束。"""

    provider = StructuredPlanProvider(mutator=_duplicate_no_bgm_hard_constraint)
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    constraint = "禁止背景音乐；只使用各镜头明确写出的同步声音"
    assert scene.negativeConstraints.count(constraint) == 1
    assert all(item != f"{constraint}。" for item in scene.negativeConstraints)


@pytest.mark.parametrize("duration_seconds", range(4, 16))
def test_balanced_beat_ranges_follow_duration_without_fifteen_second_special_case(
    duration_seconds: int,
) -> None:
    """四至十五秒均生成二至四个连续、均衡的整数秒节拍。"""

    ranges = _balanced_beat_ranges(duration_seconds)
    lengths = [end - start for start, end in ranges]

    assert 2 <= len(ranges) <= 4
    assert ranges[0][0] == 0
    assert ranges[-1][1] == duration_seconds
    assert all(
        previous[1] == current[0] for previous, current in zip(ranges, ranges[1:], strict=False)
    )
    assert max(lengths) - min(lengths) <= 1


@pytest.mark.asyncio
async def test_shared_contract_rejects_slow_continuous_cross_scale() -> None:
    """慢推跨尺度由共享 ScenePromptSpec 统一拒绝，规划器不复制尺度算法。"""

    provider = StructuredPlanProvider(mutator=_use_slow_continuous_cross_scale)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)

    with pytest.raises(RuntimeError, match="SHOT_SCALE_CHANGE_REQUIRES_CUT"):
        await planner.generate(_resource(), _payload())

    assert len(provider.requests) == 5


@pytest.mark.asyncio
async def test_cross_scale_cut_is_compiled_as_explicit_cut() -> None:
    """跨尺度改为显式 cut 后应进入双层 Provider 提示词。"""

    provider = StructuredPlanProvider(mutator=_use_cut_cross_scale)
    _scene, package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(_resource(), _payload())

    assert "全景切至特写" in package.prompt


@pytest.mark.asyncio
async def test_later_prop_debut_does_not_require_repeating_initial_keyframe() -> None:
    """机械初态只属于首拍，后续另一道具入画不能触发同一张初态图重放。"""

    def include_keyframe_and_later_prop(arguments: dict[str, Any]) -> None:
        _add_mechanical_item_assets(arguments, include_initial_keyframe=True)
        beat_count = len(arguments["beats"])
        arguments["assets"]["additionalAssets"].append(
            {
                "modality": "image",
                "duty": "prop",
                "bindingScope": "scene_direct",
                "settingId": "__NONE__",
                "targetEntity": "第二拍才出现的罗盘",
                "keyframeRole": "not_applicable",
                "include": _text_slots("feature", ["黄铜外圈", "透明表盘"], 12),
                "exclude": _text_slots("feature", ["磁针"], 12),
                "usedInBeats": "0" + "1" + "0" * (beat_count - 2),
            }
        )

    provider = StructuredPlanProvider(mutator=include_keyframe_and_later_prop)
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(
        _resource(),
        _payload(source_text="沈青转动机关盒，随后看见罗盘。"),
    )

    keyframe_id = next(asset.assetId for asset in scene.assets if asset.duty == "keyframe")
    later_prop_id = next(
        asset.assetId for asset in scene.assets if asset.targetEntity == "第二拍才出现的罗盘"
    )
    assert keyframe_id in scene.beats[0].referencedAssetIds
    assert keyframe_id not in scene.beats[1].referencedAssetIds
    assert later_prop_id not in scene.beats[0].referencedAssetIds
    assert later_prop_id in scene.beats[1].referencedAssetIds
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_earlier_prop_debut_does_not_pull_initial_state_before_mechanical_beat() -> None:
    """道具先入画、后启动机关时，故事与最终契约必须共同把初态留在机械拍。"""

    def begin_mechanical_sequence_on_second_beat(arguments: dict[str, Any]) -> None:
        _add_mechanical_item_assets(arguments, include_initial_keyframe=True)
        beat_keys = list(arguments["beats"])
        arguments["beats"][beat_keys[0]]["actionComplexity"] = "simple"
        arguments["beats"][beat_keys[1]]["actionComplexity"] = "mechanical_sequence"
        beat_count = len(beat_keys)
        arguments["assets"]["additionalAssets"][-2]["usedInBeats"] = (
            "11" + "0" * (beat_count - 2)
        )
        arguments["assets"]["additionalAssets"][-1]["usedInBeats"] = (
            "1" + "0" * (beat_count - 1)
        )

    provider = StructuredPlanProvider(mutator=begin_mechanical_sequence_on_second_beat)
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(
        _resource(),
        _payload(source_text="沈青先拿起机关盒，停顿后才转动机关。"),
    )

    keyframe_id = next(asset.assetId for asset in scene.assets if asset.duty == "keyframe")
    assert scene.beats[0].actionComplexity == "simple"
    assert keyframe_id not in scene.beats[0].referencedAssetIds
    assert scene.beats[1].actionComplexity == "mechanical_sequence"
    assert keyframe_id in scene.beats[1].referencedAssetIds
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_simple_labeled_insert_still_anchors_initial_state_to_first_beat() -> None:
    """插进机关齿槽不能因模型误标 simple 而把初态图推迟到后续机械拍。"""

    def insert_before_impact(arguments: dict[str, Any]) -> None:
        _add_mechanical_item_assets(arguments, include_initial_keyframe=True)
        beat_keys = list(arguments["beats"])
        first = arguments["beats"][beat_keys[0]]
        first["actionComplexity"] = "simple"
        first["primaryAction"] = {
            "subject": "铜扣",
            "action": "插进黄铜匣侧面的齿槽",
            "visibleResult": "铜扣完全嵌入齿槽",
        }
        first["cameraMotivation"] = "铜扣插进黄铜匣齿槽，机位强调嵌入瞬间"
        second = arguments["beats"][beat_keys[1]]
        second["actionComplexity"] = "impact_transition"
        second["primaryAction"] = {
            "subject": "机关",
            "action": "咬碎铜扣",
            "visibleResult": "黄铜碎片从齿槽落下",
        }
        second["cameraMotivation"] = "机关咬碎铜扣，机位跟随碎片落下"
        beat_count = len(beat_keys)
        arguments["assets"]["additionalAssets"][-2]["usedInBeats"] = (
            "11" + "0" * (beat_count - 2)
        )
        arguments["assets"]["additionalAssets"][-1]["usedInBeats"] = (
            "0" + "1" + "0" * (beat_count - 2)
        )

    provider = StructuredPlanProvider(mutator=insert_before_impact)
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(
        _resource(),
        _payload(source_text="她把铜扣插进机关齿槽，机关随即咬碎铜扣。"),
    )

    keyframe_id = next(asset.assetId for asset in scene.assets if asset.duty == "keyframe")
    assert scene.beats[0].actionComplexity == "simple"
    assert keyframe_id in scene.beats[0].referencedAssetIds
    assert keyframe_id not in scene.beats[1].referencedAssetIds
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_scene_asset_rejects_later_result_disguised_as_initial_keyframe() -> None:
    """触碰罗盘等后续状态不能被命名为初态后强行锚到首个机械镜头。"""

    def valid_initial_keyframe(arguments: dict[str, Any]) -> None:
        _add_mechanical_item_assets(arguments, include_initial_keyframe=True)
        arguments["assets"]["additionalAssets"][-1]["targetEntity"] = (
            "铜扣对准齿槽前初态"
        )

    def later_state_keyframe(arguments: dict[str, Any]) -> None:
        valid_initial_keyframe(arguments)
        arguments["assets"]["additionalAssets"][-1]["targetEntity"] = (
            "林岚触碰罗盘瞬间初态"
        )

    provider = StructuredPlanProvider(
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [later_state_keyframe, valid_initial_keyframe],
            _STORY_BEATS_FORMAT_NAME: [valid_initial_keyframe],
        }
    )
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(
        _resource(),
        _payload(source_text="沈青转动机关盒，机关随即启动。"),
    )

    assert scene.sceneId == "scene-1"
    correction = provider.requests[1].messages[1].content
    assert "VIDEO_PLAN_INITIAL_KEYFRAME_LATER_STATE" in correction
    assert "只能描述首个不可逆机械动作发生前或临界起点" in correction


@pytest.mark.asyncio
async def test_scene_asset_accepts_imminent_mechanical_pre_state_keyframe() -> None:
    """“即将发生”仍是首个不可逆动作前的临界初态，不能误判为结果态。"""

    def imminent_initial_keyframe(arguments: dict[str, Any]) -> None:
        _add_mechanical_item_assets(arguments, include_initial_keyframe=True)
        arguments["assets"]["additionalAssets"][-1]["targetEntity"] = (
            "铜扣即将被机关咬碎的临界初态"
        )
        arguments["beats"]["beat01"]["primaryAction"] = {
            "subject": "机关",
            "action": "咬碎铜扣",
            "visibleResult": "铜扣碎裂并落下碎片",
        }
        arguments["beats"]["beat01"]["cameraMotivation"] = (
            "机关咬碎铜扣，机位强调铜扣碎裂"
        )

    provider = StructuredPlanProvider(mutator=imminent_initial_keyframe)
    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4096,
    ).generate(
        _resource(),
        _payload(source_text="沈青把铜扣放到机关盒前，机关随即将它咬碎。"),
    )

    keyframe = next(asset for asset in scene.assets if asset.duty == "keyframe")
    assert keyframe.keyframeRole == "initial_state"
    assert keyframe.targetEntity == "铜扣即将被机关咬碎的临界初态"
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_missing_mechanical_initial_state_fails_before_camera_call() -> None:
    """缺失机关初态不能由服务器猜测补齐，也不能浪费摄影模型调用。"""

    def omit_keyframe(arguments: dict[str, Any]) -> None:
        _add_mechanical_item_assets(arguments, include_initial_keyframe=False)
        for beat in arguments["beats"].values():
            beat["actionComplexity"] = "mechanical_sequence"
        arguments["assets"]["additionalAssets"][2]["usedInBeats"] = "1" * len(arguments["beats"])

    provider = StructuredPlanProvider(duration_seconds=6, mutator=omit_keyframe)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)
    payload = _payload(
        duration_seconds=6,
        source_text="她转动机关盒，盒盖上的银色小字随之亮起。",
    )
    checkpoint_stages: list[object] = []

    async def save_checkpoint(
        checkpoint_stage: object,
        scene_assets: object,
        story: object,
        attempt_state: object,
    ) -> None:
        del scene_assets, story, attempt_state
        checkpoint_stages.append(checkpoint_stage)

    with pytest.raises(VideoPlanGenerationError, match="VIDEO_PLAN_INITIAL_KEYFRAME_REQUIRED"):
        await planner.generate(
            _resource(),
            payload,
            save_checkpoint=save_checkpoint,  # type: ignore[arg-type]
        )

    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
    ]
    assert checkpoint_stages == ["scene_assets"]


@pytest.mark.asyncio
async def test_existing_initial_state_missing_first_beat_binding_retries_story_only() -> None:
    """已有精确初态但首拍漏绑时，只纠正故事阶段，通过后才保存 story checkpoint。"""

    def include_precise_keyframe(arguments: dict[str, Any]) -> None:
        _add_mechanical_item_assets(arguments, include_initial_keyframe=True)

    def omit_first_beat_keyframe_binding(arguments: dict[str, Any]) -> None:
        include_precise_keyframe(arguments)
        beat_count = len(arguments["beats"])
        arguments["assets"]["additionalAssets"][-1]["usedInBeats"] = "0" * (beat_count - 1) + "1"

    provider = StructuredPlanProvider(
        duration_seconds=6,
        stage_mutators={
            _SCENE_ASSETS_FORMAT_NAME: [include_precise_keyframe],
            _STORY_BEATS_FORMAT_NAME: [
                omit_first_beat_keyframe_binding,
                include_precise_keyframe,
            ],
        },
    )
    checkpoint_stages: list[object] = []

    async def save_checkpoint(
        checkpoint_stage: object,
        scene_assets: object,
        story: object,
        attempt_state: object,
    ) -> None:
        del scene_assets, story, attempt_state
        checkpoint_stages.append(checkpoint_stage)

    scene, _package = await ModelVideoScenePlanner(
        ModelRuntime(provider),
        max_output_tokens=4_096,
    ).generate(
        _resource(),
        _payload(
            duration_seconds=6,
            source_text="她转动机关盒，盒盖上的银色小字随之亮起。",
        ),
        save_checkpoint=save_checkpoint,  # type: ignore[arg-type]
    )

    assert scene.sceneId == "scene-1"
    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _CINEMATOGRAPHY_FORMAT_NAME,
    ]
    assert checkpoint_stages == ["scene_assets", "story"]


@pytest.mark.asyncio
async def test_misplaced_initial_state_correction_uses_only_model_aliases() -> None:
    """初态误绑的纠正只允许出现 B/A 别名，不能泄露 canonical 身份。"""

    def add_unneeded_keyframe(arguments: dict[str, Any]) -> None:
        beat_count = len(arguments["beats"])
        arguments["assets"]["additionalAssets"].append(
            {
                "modality": "image",
                "duty": "keyframe",
                "bindingScope": "scene_direct",
                "settingId": "__NONE__",
                "targetEntity": "无机关动作的关闭初态",
                "keyframeRole": "initial_state",
                "include": _text_slots("feature", ["关闭状态"], 12),
                "exclude": _text_slots("feature", ["人物"], 12),
                # 第二拍既不是机关起点，也没有道具首次入画，因此该初态引用必然错位。
                "usedInBeats": "0" + "1" + "0" * (beat_count - 2),
            }
        )

    provider = StructuredPlanProvider(mutator=add_unneeded_keyframe)
    with pytest.raises(VideoPlanGenerationError, match="VIDEO_PLAN_INITIAL_KEYFRAME_MISPLACED"):
        await ModelVideoScenePlanner(
            ModelRuntime(provider),
            max_output_tokens=4_096,
        ).generate(_resource(), _payload())

    correction = provider.requests[2].messages[1].content
    assert "VIDEO_PLAN_INITIAL_KEYFRAME_MISPLACED" in correction
    assert "B01" in correction
    assert "A04" in correction
    assert "A03" in correction
    assert "asset04" not in correction
    assert [_request_format_name(request) for request in provider.requests] == [
        _SCENE_ASSETS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
        _STORY_BEATS_FORMAT_NAME,
    ]


@pytest.mark.parametrize(
    "source_text",
    [
        "她转动机关盒，盒盖上的银色小字随之亮起。",
        "她转动机关盒，盒盖忽然浮现银字。",
    ],
)
@pytest.mark.asyncio
async def test_mechanical_keyframe_and_silver_small_text_compile_to_hard_constraints(
    source_text: str,
) -> None:
    """合法机关初态可编译，银色小字必须被服务器固定改成不可辨识符纹。"""

    def include_keyframe(arguments: dict[str, Any]) -> None:
        _add_mechanical_item_assets(arguments, include_initial_keyframe=True)

    provider = StructuredPlanProvider(duration_seconds=6, mutator=include_keyframe)
    planner = ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096)
    payload = _payload(
        duration_seconds=6,
        source_text=source_text,
    )

    scene, package = await planner.generate(_resource(), payload)

    no_bgm = "禁止背景音乐；只使用各镜头明确写出的同步声音"
    unreadable = (
        "银色或发光的道具文字只能表现为不可辨识符纹，不得形成可读文字、字母、数字或可解码符号"
    )
    assert scene.negativeConstraints.count(no_bgm) == 1
    assert scene.negativeConstraints.count(unreadable) == 1
    assert "银色符纹不可读，禁文字/字母/数字/可解码符号" in package.prompt
    assert unreadable in package.manifestPrompt
    assert any(asset.keyframeRole == "initial_state" for asset in scene.assets)


def test_stable_slot_id_separates_initial_and_end_keyframes() -> None:
    """同语义机关的初态与终态关键帧不能因稳定摘要碰撞。"""

    common = {
        "assetId": "model-keyframe",
        "modality": "image",
        "duty": "keyframe",
        "bindingScope": "scene_direct",
        "settingReference": None,
        "featureDomain": "keyframe",
        "targetEntity": "机关盒状态",
        "includeFeatures": ["转轮方位"],
        "excludeFeatures": ["手部"],
    }
    initial = PlannedAsset(**common, keyframeRole="initial_state")
    end = PlannedAsset(**common, keyframeRole="end_state")

    assert _stable_slot_id(initial, initial.targetEntity) != _stable_slot_id(
        end,
        end.targetEntity,
    )


def _progress_response(
    query: VideoPlanProgressQuery,
    *,
    payload: VideoPlanJobPayload | None = None,
    status: str = "active",
    checkpoint_stage: str = "empty",
    scene_assets_plan: SceneAssetsStageArguments | None = None,
    story_plan: StoryPlanStageArguments | None = None,
    reserved_calls: int = 0,
    inherited_calls: int = 0,
    pending_stage: str | None = None,
) -> VideoPlanProgressResponse:
    """按查询六重身份构造处理器测试使用的阶段计划与调用账本。"""

    effective_checkpoint_stage = "terminal" if status != "active" else checkpoint_stage
    frozen_payload = payload or _video_handler_payload()

    return VideoPlanProgressResponse.model_validate(
        {
            **query.model_dump(mode="json"),
            "inputFingerprint": calculate_video_plan_input_fingerprint(frozen_payload),
            "status": status,
            "checkpointStage": effective_checkpoint_stage,
            "sceneAssetsPlan": scene_assets_plan,
            "storyPlan": story_plan,
            "attemptState": {
                "reservedCalls": reserved_calls,
                "inheritedCalls": inherited_calls,
                "pendingStage": pending_stage,
            },
        }
    )


def _scene_assets_checkpoint_fixture() -> SceneAssetsStageArguments:
    """从 V3 紧凑 wire 生成处理器恢复测试使用的素材阶段规范。"""

    provider = StructuredPlanProvider()
    return normalize_scene_assets_strict_tool_arguments(
        _scene_assets_plan_arguments(_valid_plan_arguments(provider)),
        setting_snapshot=_setting_snapshot(),
    )


def _story_checkpoint_fixture() -> StoryPlanStageArguments:
    """合并 V3 前两阶段，生成处理器恢复测试使用的完整故事规范。"""

    provider = StructuredPlanProvider()
    arguments = _valid_plan_arguments(provider)
    scene_assets = normalize_scene_assets_strict_tool_arguments(
        _scene_assets_plan_arguments(arguments),
        setting_snapshot=_setting_snapshot(),
    )
    story_beats = normalize_story_beats_strict_tool_arguments(
        _story_beats_plan_arguments(arguments),
        scene_assets=scene_assets,
        beat_ranges=_balanced_beat_ranges(15),
    )
    story_beats = StoryBeatsStageArguments(
        schemaVersion="2.0",
        beats=[
            beat.model_copy(
                update={
                    "sourceEventAliasesByAction": [
                        [] for _action in beat.actionUnits
                    ]
                }
            )
            for beat in story_beats.beats
        ],
    )
    return merge_story_stage_arguments(
        scene_assets,
        story_beats,
        beat_ranges=_balanced_beat_ranges(15),
    )


class SuccessfulPlanner:
    """处理器测试不重复调用模型，只返回固定合法场景。"""

    async def generate(
        self,
        resource: object,
        payload: object,
        **kwargs: object,
    ) -> tuple[object, object]:
        del resource, payload, kwargs
        scene = build_demo_scene().model_copy(update={"sceneId": "scene-1"})
        return scene, SeedancePromptCompiler().compile(scene, preview_only=True)


class FailingPlanner:
    """模拟已经耗尽规划器内部纠正机会的稳定模型失败。"""

    async def generate(
        self,
        resource: object,
        payload: object,
        **kwargs: object,
    ) -> tuple[object, object]:
        del resource, payload, kwargs
        raise VideoPlanGenerationError("VIDEO_SCENE_PLAN_INVALID：草案结构仍不完整")


class NeverCalledPlanner:
    """终态进度必须在任何模型规划调用前短路。"""

    async def generate(self, *args: object, **kwargs: object) -> tuple[object, object]:
        del args, kwargs
        raise AssertionError("终态视频任务不应再次调用规划器")


class RecordingResumePlanner(SuccessfulPlanner):
    """记录处理器传入的故事检查点和纠正预算。"""

    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def generate(
        self,
        resource: object,
        payload: object,
        **kwargs: object,
    ) -> tuple[object, object]:
        self.kwargs = kwargs
        return await super().generate(resource, payload, **kwargs)


class RecordingCore:
    """记录成功回调，失败回调在此测试中属于异常。"""

    def __init__(self) -> None:
        self.completed = 0
        self.reservations: list[VideoPlanCallReservationRequest] = []
        self.checkpoints: list[VideoStoryPlanCheckpointCallback] = []

    async def get_video_plan_progress(
        self,
        resource: object,
        query: VideoPlanProgressQuery,
    ) -> VideoPlanProgressResponse:
        del resource
        return _progress_response(query)

    async def reserve_video_plan_call(
        self,
        resource: object,
        request: VideoPlanCallReservationRequest,
    ) -> VideoPlanCallReservationResponse:
        """模拟 Core 原子预留，并逐字段回显本次资源与调用账本。"""

        del resource
        self.reservations.append(request)
        response_identity = request.model_dump(
            mode="json",
            exclude={"expectedReservedCalls", "inheritedCalls"},
        )
        return VideoPlanCallReservationResponse.model_validate(
            {
                **response_identity,
                "reservedCallsBefore": request.expectedReservedCalls,
                "attemptState": {
                    "reservedCalls": request.expectedReservedCalls + 1,
                    "inheritedCalls": request.inheritedCalls,
                    "pendingStage": request.stage,
                },
            }
        )

    async def save_story_plan_checkpoint(
        self,
        resource: object,
        callback: VideoStoryPlanCheckpointCallback,
    ) -> None:
        del resource
        self.checkpoints.append(callback)

    async def complete_video_plan(self, resource: object, callback: object) -> None:
        self.completed += 1

    async def fail_video_plan(self, resource: object, callback: object) -> None:
        raise AssertionError("成功任务不应回调失败")


class RecordingFailureCore:
    """记录视频失败回调，验证回写成功后的队列终态语义。"""

    def __init__(self) -> None:
        self.callbacks: list[VideoPlanFailureCallback] = []
        self.reservations: list[VideoPlanCallReservationRequest] = []

    async def get_video_plan_progress(
        self,
        resource: object,
        query: VideoPlanProgressQuery,
    ) -> VideoPlanProgressResponse:
        del resource
        return _progress_response(query)

    async def reserve_video_plan_call(
        self,
        resource: object,
        request: VideoPlanCallReservationRequest,
    ) -> VideoPlanCallReservationResponse:
        """失败替身仍需实现模型调用前的耐久预留端口。"""

        del resource
        self.reservations.append(request)
        response_identity = request.model_dump(
            mode="json",
            exclude={"expectedReservedCalls"},
        )
        return VideoPlanCallReservationResponse.model_validate(
            {
                **response_identity,
                "reservedCallsBefore": request.expectedReservedCalls,
                "attemptState": {
                    "reservedCalls": request.expectedReservedCalls + 1,
                    "pendingStage": request.stage,
                },
            }
        )

    async def save_story_plan_checkpoint(
        self,
        resource: object,
        callback: VideoStoryPlanCheckpointCallback,
    ) -> None:
        del resource, callback
        raise AssertionError("失败规划器不应保存故事检查点")

    async def complete_video_plan(self, resource: object, callback: object) -> None:
        raise AssertionError("失败任务不应回调成功")

    async def fail_video_plan(
        self,
        resource: object,
        callback: VideoPlanFailureCallback,
    ) -> None:
        del resource
        self.callbacks.append(callback)


class ConfigurableProgressCore(RecordingCore):
    """按测试指定的耐久状态返回进度，并可模拟完成回调基础设施失败。"""

    def __init__(
        self,
        *,
        status: str = "active",
        checkpoint_stage: str = "empty",
        scene_assets_plan: SceneAssetsStageArguments | None = None,
        story_plan: StoryPlanStageArguments | None = None,
        reserved_calls: int = 0,
        pending_stage: str | None = None,
        complete_error: Exception | None = None,
        checkpoint_error: Exception | None = None,
        reservation_error: Exception | None = None,
        mismatched_scene_id: str | None = None,
        mismatched_input_fingerprint: str | None = None,
        mismatched_reservation_scene_id: str | None = None,
    ) -> None:
        super().__init__()
        self.status = status
        self.checkpoint_stage = checkpoint_stage
        self.scene_assets_plan = scene_assets_plan
        self.story_plan = story_plan
        self.reserved_calls = reserved_calls
        self.pending_stage = pending_stage
        self.complete_error = complete_error
        self.checkpoint_error = checkpoint_error
        self.reservation_error = reservation_error
        self.mismatched_scene_id = mismatched_scene_id
        self.mismatched_input_fingerprint = mismatched_input_fingerprint
        self.mismatched_reservation_scene_id = mismatched_reservation_scene_id
        self.failed_callbacks = 0

    async def get_video_plan_progress(
        self,
        resource: object,
        query: VideoPlanProgressQuery,
    ) -> VideoPlanProgressResponse:
        del resource
        progress = _progress_response(
            query,
            status=self.status,
            checkpoint_stage=self.checkpoint_stage,
            scene_assets_plan=self.scene_assets_plan,
            story_plan=self.story_plan,
            reserved_calls=self.reserved_calls,
            pending_stage=self.pending_stage,
        )
        updates: dict[str, object] = {}
        if self.mismatched_scene_id is not None:
            updates["sceneId"] = self.mismatched_scene_id
        if self.mismatched_input_fingerprint is not None:
            updates["inputFingerprint"] = self.mismatched_input_fingerprint
        return progress.model_copy(update=updates)

    async def reserve_video_plan_call(
        self,
        resource: object,
        request: VideoPlanCallReservationRequest,
    ) -> VideoPlanCallReservationResponse:
        if self.reservation_error is not None:
            raise self.reservation_error
        response = await super().reserve_video_plan_call(resource, request)
        if self.mismatched_reservation_scene_id is None:
            return response
        return response.model_copy(update={"sceneId": self.mismatched_reservation_scene_id})

    async def complete_video_plan(self, resource: object, callback: object) -> None:
        if self.complete_error is not None:
            raise self.complete_error
        await super().complete_video_plan(resource, callback)

    async def save_story_plan_checkpoint(
        self,
        resource: object,
        callback: VideoStoryPlanCheckpointCallback,
    ) -> None:
        if self.checkpoint_error is not None:
            raise self.checkpoint_error
        await super().save_story_plan_checkpoint(resource, callback)

    async def fail_video_plan(self, resource: object, callback: object) -> None:
        del resource, callback
        self.failed_callbacks += 1


class RecordingWorkflowLog:
    """最小日志替身用于验证视频任务也遵循开始—结束生命周期。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def start_run(self, **values: object) -> object:
        self.events.append(("start", str(values["chapter_id"])))
        return object()

    def record_state(self, run_id: str, node: str, changes: dict[str, object]) -> None:
        return None

    def finish_run(self, run_id: str, status: str) -> object:
        self.events.append(("finish", status))
        return object()


def _video_handler_payload() -> VideoPlanJobPayload:
    """返回处理器测试与假 Core 共同冻结的视频规划输入。"""

    return VideoPlanJobPayload(
        projectId="project-1",
        sceneId="scene-1",
        chapterId="chapter-1",
        title="测试场景",
        sourceText="她推开门。",
        durationSeconds=15,
        ratio="16:9",
        settingSnapshot=_setting_snapshot(),
        planningRoute="responses_json_schema_v1",
        planningModel="deepseek-v4-flash",
        directorDraftVersion="1.4",
    )


def _video_queue_job(*, job_id: str = "job-1") -> QueueJob:
    """构造处理器恢复测试共用的视频队列任务。"""

    return QueueJob(
        jobId=job_id,
        kind="video",
        runId="run-1",
        taskId="task-1",
        novelId="novel-1",
        userId="user-1",
        priority=10,
        payload=_video_handler_payload().model_dump(mode="json"),
        createdAt=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_video_handler_opens_log_before_model_observer_and_finishes_it() -> None:
    """防止真实模型观察器因视频运行尚未登记而中断任务。"""

    core = RecordingCore()
    workflow_log = RecordingWorkflowLog()
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        SuccessfulPlanner(),  # type: ignore[arg-type]
        workflow_log=workflow_log,
    )
    await handler(_video_queue_job())

    assert core.completed == 1
    assert workflow_log.events == [("start", "chapter-1"), ("finish", "完成")]


@pytest.mark.asyncio
async def test_video_handler_uses_explicit_terminal_error_after_failure_callback() -> None:
    """失败事实已落 Core 后不得用普通异常触发整个消费者监督周期重启。"""

    core = RecordingFailureCore()
    workflow_log = RecordingWorkflowLog()
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        FailingPlanner(),  # type: ignore[arg-type]
        workflow_log=workflow_log,
    )

    with pytest.raises(
        NonRetryableJobError,
        match="视频规划失败已上报核心服务",
    ) as exc_info:
        await handler(_video_queue_job(job_id="job-failed"))

    assert exc_info.value.retryable is False
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert len(core.callbacks) == 1
    assert core.callbacks[0].code == "VIDEO_PLAN_FAILED"
    assert core.callbacks[0].recoverable is True
    assert "VIDEO_SCENE_PLAN_INVALID" in core.callbacks[0].message
    assert workflow_log.events == [("start", "chapter-1"), ("finish", "错误")]


@pytest.mark.asyncio
async def test_video_handler_saves_story_checkpoint_with_six_resource_ids() -> None:
    """真实三阶段规划须保存两份 canonical 检查点与三次调用预留。"""

    core = RecordingCore()
    provider = StructuredPlanProvider()
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096),
    )

    await handler(_video_queue_job())

    assert len(core.checkpoints) == 2
    assert len(core.reservations) == 3
    for checkpoint in core.checkpoints:
        assert (
            checkpoint.jobId,
            checkpoint.runId,
            checkpoint.taskId,
            checkpoint.novelId,
            checkpoint.projectId,
            checkpoint.sceneId,
        ) == ("job-1", "run-1", "task-1", "novel-1", "project-1", "scene-1")
    assets_checkpoint, story_checkpoint = core.checkpoints
    assert assets_checkpoint.checkpointStage == "scene_assets"
    assert assets_checkpoint.sceneAssetsPlan is not None
    assert assets_checkpoint.storyPlan is None
    assert assets_checkpoint.attemptState == VideoPlanAttemptState(
        reservedCalls=1,
        pendingStage=None,
    )
    assert story_checkpoint.checkpointStage == "story"
    assert story_checkpoint.sceneAssetsPlan is None
    assert story_checkpoint.storyPlan is not None
    assert story_checkpoint.storyPlan.schemaVersion == "2.0"
    assert story_checkpoint.attemptState == VideoPlanAttemptState(
        reservedCalls=2,
        pendingStage=None,
    )
    assert [request.stage for request in core.reservations] == [
        "scene_assets",
        "story_beats",
        "cinematography",
    ]
    assert [request.expectedReservedCalls for request in core.reservations] == [0, 1, 2]
    assert [_request_format_name(request) for request in provider.requests] == [
        "video_scene_assets_draft_v1",
        "video_story_beats_draft_v4",
        "video_cinematography_draft_v2",
    ]


@pytest.mark.asyncio
async def test_video_handler_resumes_checkpoint_and_preserves_used_budget() -> None:
    """active 进度中的故事与调用账本必须原样传给规划器。"""

    story = _story_checkpoint_fixture()
    core = ConfigurableProgressCore(
        checkpoint_stage="story",
        story_plan=story,
        reserved_calls=3,
    )
    planner = RecordingResumePlanner()
    handler = VideoPromptJobHandler(core, planner)  # type: ignore[arg-type]

    await handler(_video_queue_job())

    progress = planner.kwargs["progress"]
    assert isinstance(progress, VideoPlanProgressResponse)
    assert progress.checkpointStage == "story"
    assert progress.storyPlan == story
    assert progress.attemptState == VideoPlanAttemptState(
        reservedCalls=3,
        pendingStage=None,
    )
    assert callable(planner.kwargs["reserve_call"])
    assert callable(planner.kwargs["save_checkpoint"])
    assert core.completed == 1


@pytest.mark.parametrize("status", ["completed", "failed"])
@pytest.mark.asyncio
async def test_video_handler_terminal_progress_uses_zero_model_calls(status: str) -> None:
    """Core 已有终态时不得重放任何模型或终态回调。"""

    core = ConfigurableProgressCore(status=status)
    workflow_log = RecordingWorkflowLog()
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        NeverCalledPlanner(),  # type: ignore[arg-type]
        workflow_log=workflow_log,
    )

    if status == "completed":
        await handler(_video_queue_job())
        assert workflow_log.events == [("start", "chapter-1"), ("finish", "完成")]
    else:
        with pytest.raises(NonRetryableJobError, match="已在核心服务收敛为失败"):
            await handler(_video_queue_job())
        assert workflow_log.events == [("start", "chapter-1"), ("finish", "错误")]
    assert core.completed == 0
    assert core.failed_callbacks == 0


@pytest.mark.asyncio
async def test_video_handler_complete_callback_error_never_becomes_failure_callback() -> None:
    """成功回调结果未知时必须保留原异常重试，不能伪造失败终态。"""

    callback_error = CoreServiceError("核心服务暂时不可用", recoverable=True)
    core = ConfigurableProgressCore(complete_error=callback_error)
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        SuccessfulPlanner(),  # type: ignore[arg-type]
    )

    with pytest.raises(CoreServiceError) as exc_info:
        await handler(_video_queue_job())

    assert exc_info.value is callback_error
    assert core.failed_callbacks == 0


@pytest.mark.asyncio
async def test_video_handler_checkpoint_error_never_becomes_failure_callback() -> None:
    """素材检查点未确认保存时必须停止后续阶段且不能写失败终态。"""

    checkpoint_error = CoreServiceError("核心服务暂时不可用", recoverable=True)
    core = ConfigurableProgressCore(checkpoint_error=checkpoint_error)
    provider = StructuredPlanProvider()
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096),
    )

    with pytest.raises(CoreServiceError) as exc_info:
        await handler(_video_queue_job())

    assert exc_info.value is checkpoint_error
    assert core.failed_callbacks == 0
    assert core.completed == 0
    assert [_request_format_name(request) for request in provider.requests] == [
        "video_scene_assets_draft_v1"
    ]
    assert [request.stage for request in core.reservations] == ["scene_assets"]


@pytest.mark.asyncio
async def test_video_handler_reservation_error_stops_before_model() -> None:
    """调用预留未确认时不得触发供应商，也不能把基础设施异常伪造成业务失败。"""

    reservation_error = CoreServiceError("调用预留暂时不可用", recoverable=True)
    core = ConfigurableProgressCore(reservation_error=reservation_error)
    provider = StructuredPlanProvider()
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096),
    )

    with pytest.raises(CoreServiceError) as exc_info:
        await handler(_video_queue_job())

    assert exc_info.value is reservation_error
    assert provider.requests == []
    assert core.checkpoints == []
    assert core.failed_callbacks == 0
    assert core.completed == 0


@pytest.mark.asyncio
async def test_video_handler_rejects_mismatched_reservation_identity_before_model() -> None:
    """Core 预留回执的六重资源身份串线时必须在模型调用前拒绝。"""

    core = ConfigurableProgressCore(
        mismatched_reservation_scene_id="scene-other",
    )
    provider = StructuredPlanProvider()
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        ModelVideoScenePlanner(ModelRuntime(provider), max_output_tokens=4096),
    )

    with pytest.raises(ValueError, match="VIDEO_PLAN_RESERVATION_MISMATCH"):
        await handler(_video_queue_job())

    assert provider.requests == []
    assert len(core.reservations) == 1
    assert core.failed_callbacks == 0
    assert core.completed == 0


@pytest.mark.asyncio
async def test_video_handler_rejects_mismatched_progress_identity_before_model() -> None:
    """即使响应可解析，场景身份不匹配也必须在模型调用前拒绝。"""

    core = ConfigurableProgressCore(mismatched_scene_id="scene-other")
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        NeverCalledPlanner(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="VIDEO_PLAN_PROGRESS_RESOURCE_MISMATCH"):
        await handler(_video_queue_job())

    assert core.failed_callbacks == 0


@pytest.mark.asyncio
async def test_video_handler_rejects_mismatched_frozen_input_before_reservation() -> None:
    """同一资源身份若冻结输入指纹不同，也必须在预留额度前拒绝恢复。"""

    core = ConfigurableProgressCore(mismatched_input_fingerprint="0" * 64)
    handler = VideoPromptJobHandler(
        core,  # type: ignore[arg-type]
        NeverCalledPlanner(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="VIDEO_PLAN_PROGRESS_INPUT_MISMATCH"):
        await handler(_video_queue_job())

    assert core.reservations == []
    assert core.failed_callbacks == 0


def _setting_snapshot() -> LongSerialSettingSnapshot:
    """规划测试使用的冻结长篇设定。"""

    return LongSerialSettingSnapshot.from_entries(
        [
            CharacterSettingSnapshot(
                id="character-shen-qing",
                contentHash="a" * 64,
                name="沈青",
                aliases=["阿青"],
                appearance="清瘦脸型，湿发",
                identity="药师学徒",
            ),
            LocationSettingSnapshot(
                id="location-medicine-shop",
                contentHash="b" * 64,
                name="济世药铺",
                aliases=[],
                locationType="药铺",
                parentLocationId=None,
                climate="暴雨",
                culture=None,
                description="木柜与暖色油灯",
            ),
            ItemSettingSnapshot(
                id="item-mechanism-box",
                contentHash="c" * 64,
                name="银纹机关盒",
                aliases=["机关盒"],
                itemType="机关道具",
                ownerCharacterId="character-shen-qing",
                description="盒盖刻有银色小字与联动转轮",
            ),
        ]
    )
