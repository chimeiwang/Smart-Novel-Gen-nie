"""视频规划共享契约的边界测试。"""

from __future__ import annotations

import json
from math import ceil
from typing import Any, Literal

import jsonschema_rs
import pytest
from inkforge_contracts.jobs import AgentJobRequest
from inkforge_contracts.video import (
    CameraActionUnit,
    CharacterSettingSnapshot,
    CinematographyBeatDraftItemV1,
    CinematographyDraftV1,
    ItemSettingSnapshot,
    LocationSettingSnapshot,
    LongSerialSettingSnapshot,
    PlannedAsset,
    PlannerToolEnvelopeV2,
    RelationshipSettingSnapshot,
    SceneAssetDraftItemV1,
    SceneAssetsDraftV1,
    SceneAssetsStageArguments,
    ScenePromptSpec,
    StoryAssetUsageDraftV2,
    StoryBeatDraftItemV2,
    StoryBeatPlanArguments,
    StoryBeatsDraftV2,
    StoryBeatsStageArguments,
    StoryPlanStageArguments,
    VideoPlanAttemptState,
    VideoPlanCallReservationRequest,
    VideoPlanCallReservationResponse,
    VideoPlanJobPayload,
    VideoPlanProgressQuery,
    VideoPlanProgressResponse,
    VideoStoryPlanCheckpointCallback,
    WorldSettingSnapshot,
    action_unit_affirms_source_event,
    build_video_director_draft_skeleton,
    calculate_video_plan_input_fingerprint,
    distribute_source_event_aliases,
    json_schema_for_cinematography_draft_response,
    json_schema_for_cinematography_strict_tool,
    json_schema_for_scene_assets_draft_response,
    json_schema_for_scene_assets_strict_tool,
    json_schema_for_story_beats_draft_response,
    json_schema_for_story_beats_strict_tool,
    json_schema_for_story_strict_tool,
    json_schema_for_strict_tool,
    materialize_cinematography_draft,
    materialize_scene_assets_draft,
    materialize_story_beats_draft,
    merge_story_stage_arguments,
    normalize_scene_assets_strict_tool_arguments,
    normalize_split_strict_tool_arguments,
    normalize_story_beats_strict_tool_arguments,
    normalize_story_strict_tool_arguments,
    normalize_strict_tool_arguments,
    render_action_units,
    validate_source_event_sequence,
)
from inkforge_contracts.video_compiler import PromptCompileError, SeedancePromptCompiler
from pydantic import ValidationError

_PLAN_INPUT_FINGERPRINT = "a" * 64


def test_deepseek_strict_schema_requires_every_object_property() -> None:
    """strict 模式只使用 DeepSeek 官方支持关键词并锁定全部对象属性。"""

    schema = json_schema_for_strict_tool(
        setting_snapshot=_setting_snapshot(),
        beat_ranges=_balanced_ranges(15),
    )
    objects = _collect_object_schemas(schema)

    assert objects
    for item in objects:
        properties = item.get("properties")
        assert isinstance(properties, dict)
        assert item["additionalProperties"] is False
        assert set(item["required"]) == set(properties)

    _assert_strict_schema_keyword_allowlist(schema)
    _assert_any_of_branches_have_explicit_type(schema)
    _assert_object_types_have_non_empty_properties(schema)
    any_of_paths = _collect_any_of_paths(schema)
    assert any_of_paths
    assert all(
        (len(path) >= 5 and path[-3] == "properties" and path[-2] == "secondaryAction")
        or (len(path) >= 5 and path[-3] == "properties" and path[-2] == "edgeLight")
        or (len(path) >= 5 and path[-3] == "properties" and path[-2] == "lightingCue")
        for path in any_of_paths
    )
    serialized = str(schema)
    for forbidden in (
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "oneOf",
        "allOf",
        "discriminator",
        "'$defs'",
        "'type': 'null'",
        "'unused'",
    ):
        assert forbidden not in serialized

    assert "$def" in schema
    assert set(schema["properties"]) == {
        "title",
        "summary",
        "dramaticArc",
        "visualStyle",
        "globalDirection",
        "cinematographyBase",
        "lightingSetup",
        "assets",
        "beats",
        "negativeConstraints",
    }
    camera_spec = schema["$def"]["ShotCameraSpec"]
    assert list(camera_spec["properties"]) == [
        "lensType",
        "focalLengthMm",
        "endFocalLengthMm",
        "tStop",
        "position",
        "composition",
        "movement",
        "focus",
    ]
    assert camera_spec["required"] == list(camera_spec["properties"])
    assert camera_spec["additionalProperties"] is False
    composition = schema["$def"]["CameraComposition"]
    assert list(composition["properties"]) == [
        "rule",
        "subjectPlacement",
        "subjectFramePercent",
        "headroom",
        "foregroundLayer",
        "backgroundLayer",
    ]
    assert composition["required"] == list(composition["properties"])
    assert composition["additionalProperties"] is False


def test_split_deepseek_schemas_are_strict_and_have_disjoint_beat_responsibilities() -> None:
    """两阶段各自保持 strict，并且逐拍字段没有跨阶段重复。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    story_schema = json_schema_for_story_strict_tool(
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    cinematography_schema = json_schema_for_cinematography_strict_tool(
        beat_ranges=ranges,
    )

    for schema in (story_schema, cinematography_schema):
        for item in _collect_object_schemas(schema):
            properties = item.get("properties")
            assert isinstance(properties, dict)
            assert item["additionalProperties"] is False
            assert set(item["required"]) == set(properties)
        _assert_strict_schema_keyword_allowlist(schema)
        _assert_any_of_branches_have_explicit_type(schema)
        _assert_object_types_have_non_empty_properties(schema)

    assert set(story_schema["properties"]) == {
        "title",
        "summary",
        "dramaticArc",
        "visualStyle",
        "globalDirection",
        "assets",
        "beats",
        "negativeConstraints",
    }
    assert set(cinematography_schema["properties"]) == {
        "cinematographyBase",
        "lightingSetup",
        "beats",
    }
    story_beat_fields = set(story_schema["$def"]["Beat01"]["properties"])
    cinematography_beat_fields = set(cinematography_schema["$def"]["Beat01"]["properties"])
    assert story_beat_fields == {
        "dramaticPurpose",
        "performanceDirection",
        "blocking",
        "primaryAction",
        "secondaryAction",
        "actionComplexity",
        "sound",
    }
    assert cinematography_beat_fields == {
        "cameraSpec",
        "lightingCue",
        "cameraMotivation",
        "axisTransition",
        "shotProgression",
        "transition",
    }
    assert story_beat_fields.isdisjoint(cinematography_beat_fields)


def test_split_schema_and_wire_stay_below_per_stage_size_budgets() -> None:
    """量化两阶段 schema 与 wire，防止再次退化为单次超大请求。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    full_schema = json_schema_for_strict_tool(
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    story_schema = json_schema_for_story_strict_tool(
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    cinematography_schema = json_schema_for_cinematography_strict_tool(
        beat_ranges=ranges,
    )
    full_wire = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_wire, cinematography_wire = _split_v2_wire_fixture(full_wire)

    full_schema_bytes = _encoded_json_bytes(full_schema)
    story_schema_bytes = _encoded_json_bytes(story_schema)
    cinematography_schema_bytes = _encoded_json_bytes(cinematography_schema)
    full_wire_bytes = _encoded_json_bytes(full_wire)
    story_wire_bytes = _encoded_json_bytes(story_wire)
    cinematography_wire_bytes = _encoded_json_bytes(cinematography_wire)

    assert story_schema_bytes < full_schema_bytes
    assert cinematography_schema_bytes < full_schema_bytes
    assert story_schema_bytes < 24_000
    assert cinematography_schema_bytes < 32_000
    assert story_wire_bytes < full_wire_bytes
    assert cinematography_wire_bytes < full_wire_bytes
    assert story_wire_bytes < 6_000
    assert cinematography_wire_bytes < 7_000


def test_three_stage_story_schemas_use_compact_arrays_and_late_asset_usage() -> None:
    """素材阶段不猜逐拍引用，故事节拍阶段才提交紧凑素材位图。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    scene_assets_raw, _story_beats_raw = _compact_stage_wire_fixture(full_raw)
    scene_assets = normalize_scene_assets_strict_tool_arguments(
        scene_assets_raw,
        setting_snapshot=snapshot,
    )
    scene_schema = json_schema_for_scene_assets_strict_tool(setting_snapshot=snapshot)
    beats_schema = json_schema_for_story_beats_strict_tool(
        scene_assets=scene_assets,
        beat_ranges=ranges,
    )

    for schema in (scene_schema, beats_schema):
        for item in _collect_object_schemas(schema):
            properties = item.get("properties")
            assert isinstance(properties, dict)
            assert item["additionalProperties"] is False
            assert set(item["required"]) == set(properties)
        _assert_strict_schema_keyword_allowlist(schema)
        _assert_any_of_branches_have_explicit_type(schema)
        _assert_object_types_have_non_empty_properties(schema)

    asset_slot = scene_schema["$def"]["AssetSlot"]
    assert set(asset_slot["properties"]) == {
        "duty",
        "modality",
        "bindingScope",
        "settingId",
        "targetEntity",
        "keyframeRole",
        "include",
        "exclude",
    }
    assert asset_slot["properties"]["include"]["type"] == "array"
    assert asset_slot["properties"]["include"]["items"]["pattern"] == r"^[\s\S]{0,79}\S$"
    assert asset_slot["properties"]["exclude"]["type"] == "array"
    assert "usedInBeats" not in asset_slot["properties"]
    assert scene_schema["properties"]["negativeConstraints"]["type"] == "array"
    assert "IncludeFeatureSlots" not in scene_schema["$def"]

    beat = beats_schema["$def"]["Beat01"]
    assert beat["properties"]["assetUsage"] == {
        "type": "string",
        "pattern": r"^[01]{2}$",
        "description": "与第一阶段素材数量等宽的0/1位图；从左到右对应asset01...assetN。",
    }
    assert "cameraSpec" not in beat["properties"]
    assert set(beats_schema["properties"]) == {"beats"}


def test_three_stage_story_schema_and_wire_size_budgets() -> None:
    """量化 V3 前两阶段，防止故事对象再次增长到约 11K 字符。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    scene_assets_raw, story_beats_raw = _compact_stage_wire_fixture(full_raw)
    scene_assets = normalize_scene_assets_strict_tool_arguments(
        scene_assets_raw,
        setting_snapshot=snapshot,
    )
    legacy_story_schema = json_schema_for_story_strict_tool(
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    scene_schema = json_schema_for_scene_assets_strict_tool(setting_snapshot=snapshot)
    beats_schema = json_schema_for_story_beats_strict_tool(
        scene_assets=scene_assets,
        beat_ranges=ranges,
    )

    assert _encoded_json_bytes(scene_schema) < 8_000
    assert _encoded_json_bytes(beats_schema) < 10_000
    assert _encoded_json_bytes(scene_schema) < _encoded_json_bytes(legacy_story_schema)
    assert _encoded_json_bytes(beats_schema) < _encoded_json_bytes(legacy_story_schema)
    assert _encoded_json_bytes(scene_assets_raw) < 3_000
    assert _encoded_json_bytes(story_beats_raw) < 4_000


def test_responses_draft_schemas_use_closed_aliases_and_no_formal_ids() -> None:
    """新路由不再要求模型回传正式身份、时间、位图或哨兵。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    scene_draft = _scene_assets_draft_fixture()
    scene_assets = materialize_scene_assets_draft(
        scene_draft,
        setting_snapshot=snapshot,
    )
    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=snapshot,
        beat_ranges=ranges,
        scene_assets=scene_assets,
    )
    schemas = [
        json_schema_for_scene_assets_draft_response(skeleton=skeleton),
        json_schema_for_story_beats_draft_response(skeleton=skeleton),
        json_schema_for_cinematography_draft_response(skeleton=skeleton),
    ]
    camera_schema = schemas[2]
    assert camera_schema["$defs"]["CinematographyBase"]["properties"]["axisRule"][
        "enum"
    ] == ["maintain_180"]
    camera_beats = camera_schema["properties"]["beatsByAlias"]
    assert camera_beats["required"] == ["B01", "B02", "B03", "B04"]
    first_item = camera_schema["$defs"]["CinematographyBeatDraftV2_01"]
    second_item = camera_schema["$defs"]["CinematographyBeatDraftV2_02"]
    assert first_item["properties"]["lightingCue"] == {
        "$ref": "#/$defs/FirstShotLightingCueV2"
    }
    first_lighting_branches = camera_schema["$defs"]["FirstShotLightingCueV2"]["anyOf"]
    motivated_lighting_branches = camera_schema["$defs"]["MotivatedShotLightingCueV2"][
        "anyOf"
    ]
    assert all(
        branch["properties"]["continuityMode"]["enum"] == ["establish"]
        for branch in first_lighting_branches
    )
    assert second_item["properties"]["lightingCue"]["anyOf"] == [
        {"$ref": "#/$defs/MotivatedShotLightingCueV2"},
        {"type": "null"},
    ]
    assert all(
        branch["properties"]["continuityMode"]["enum"] == ["motivated_change"]
        for branch in motivated_lighting_branches
    )
    for branches in (first_lighting_branches, motivated_lighting_branches):
        assert branches[0]["properties"]["fillStrategy"]["enum"] == ["none"]
        assert branches[0]["properties"]["fillDirection"] == {"type": "null"}
        assert branches[0]["properties"]["fillRelativeStops"]["enum"] == [-8]
        assert branches[1]["properties"]["fillStrategy"]["enum"] == [
            "soft_fill",
            "bounce_fill",
            "negative_fill",
        ]
        assert branches[1]["properties"]["fillDirection"]["enum"] == [
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
    for definition_name in (
        "FirstShotLightingCueV2",
        "MotivatedShotLightingCueV2",
    ):
        definition = camera_schema["$defs"][definition_name]
        assert all(
            branch["properties"]["motivatedChange"]["pattern"]
            == r"^[\s\S]{0,159}\S$"
            for branch in definition["anyOf"]
        )
        lighting_schema = {
            "$defs": camera_schema["$defs"],
            "$ref": f"#/$defs/{definition_name}",
        }
        invalid_lighting = _lighting_cue_fixture(
            establish=definition_name == "FirstShotLightingCueV2"
        )
        invalid_lighting["motivatedChange"] = ""
        with pytest.raises(jsonschema_rs.ValidationError):
            jsonschema_rs.validate(lighting_schema, invalid_lighting)
    no_fill_lighting = _lighting_cue_fixture(establish=True)
    no_fill_lighting["edgeLight"] = None
    no_fill_lighting["fillStrategy"] = "none"
    no_fill_lighting["fillDirection"] = None
    no_fill_lighting["fillRelativeStops"] = -4
    first_lighting_schema = {
        "$defs": camera_schema["$defs"],
        "$ref": "#/$defs/FirstShotLightingCueV2",
    }
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(first_lighting_schema, no_fill_lighting)
    no_fill_lighting["fillRelativeStops"] = -8
    jsonschema_rs.validate(first_lighting_schema, no_fill_lighting)
    camera_choices = camera_schema["$defs"]["ShotCameraSpec"]["anyOf"]
    assert camera_choices == [
        {"$ref": "#/$defs/FixedLensCameraSpecV2"},
        {"$ref": "#/$defs/ZoomLensCameraSpecV2"},
    ]
    fixed_camera = camera_schema["$defs"]["FixedLensCameraSpecV2"]
    zoom_camera = camera_schema["$defs"]["ZoomLensCameraSpecV2"]
    assert fixed_camera["properties"]["lensType"]["enum"] == [
        "prime",
        "macro_prime",
    ]
    assert fixed_camera["properties"]["movement"] == {
        "$ref": "#/$defs/FixedLensCameraMovementV2"
    }
    assert zoom_camera["properties"]["lensType"]["enum"] == ["zoom"]
    assert zoom_camera["properties"]["movement"] == {
        "$ref": "#/$defs/ZoomLensCameraMovementV2"
    }
    zoom_movement = camera_schema["$defs"]["ZoomLensCameraMovementV2"]["properties"]
    assert zoom_movement["movementType"]["enum"] == ["zoom_in", "zoom_out"]
    assert zoom_movement["travelDistanceMeters"]["enum"] == [0]
    assert zoom_movement["rotationDegrees"]["enum"] == [0]
    assert camera_schema["$defs"]["CameraPositionSpec"]["properties"]["axisSide"][
        "enum"
    ] == ["screen_left", "on_axis"]

    shot_schema = {
        "$defs": camera_schema["$defs"],
        "$ref": "#/$defs/ShotCameraSpec",
    }
    valid_camera = _valid_v2_wire_fixture(
        snapshot=snapshot,
        beat_ranges=ranges,
    )["beats"]["beat01"]["cameraSpec"]
    jsonschema_rs.validate(shot_schema, valid_camera)

    zoom_with_fixed_movement = json.loads(json.dumps(valid_camera, ensure_ascii=False))
    zoom_with_fixed_movement["lensType"] = "zoom"
    zoom_with_fixed_movement["endFocalLengthMm"] = 60
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(shot_schema, zoom_with_fixed_movement)

    fixed_with_zoom_movement = json.loads(json.dumps(valid_camera, ensure_ascii=False))
    fixed_with_zoom_movement["movement"].update(
        {
            "movementType": "zoom_in",
            "speed": "slow",
        }
    )
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(shot_schema, fixed_with_zoom_movement)

    moving_zoom = json.loads(json.dumps(valid_camera, ensure_ascii=False))
    moving_zoom.update({"lensType": "zoom", "endFocalLengthMm": 60})
    moving_zoom["movement"].update(
        {
            "movementType": "zoom_in",
            "travelDistanceMeters": 1,
            "speed": "slow",
        }
    )
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(shot_schema, moving_zoom)

    first_axis = first_item["properties"]["axisTransition"]
    assert first_axis["enum"] == ["hold"]
    assert second_item["properties"]["axisTransition"]["enum"] == ["hold"]
    short_progression_schema = {
        "$defs": camera_schema["$defs"],
        "$ref": "#/$defs/ShotProgressionV2_01",
    }
    jsonschema_rs.validate(
        short_progression_schema,
        {
            "startShotSize": "中景",
            "endShotSize": "近景",
            "changeMode": "continuous",
        },
    )
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(
            short_progression_schema,
            {
                "startShotSize": "大全景",
                "endShotSize": "特写",
                "changeMode": "continuous",
            },
        )
    jsonschema_rs.validate(
        short_progression_schema,
        {
            "startShotSize": "大全景",
            "endShotSize": "特写",
            "changeMode": "impact_cut",
        },
    )

    for schema in schemas:
        for item in _collect_object_schemas(schema):
            properties = item.get("properties")
            assert isinstance(properties, dict)
            assert item["additionalProperties"] is False
            assert set(item["required"]) == set(properties)
        serialized = json.dumps(schema, ensure_ascii=False)
        for forbidden in (
            '"assetId"',
            '"beatId"',
            '"startSecond"',
            '"endSecond"',
            '"assetUsage"',
            '"schemaVersion"',
            "__UNUSED__",
            "__INHERIT__",
        ):
            assert forbidden not in serialized

    scene_item = schemas[0]["$defs"]["SceneAssetDraftItemV1"]
    canonical_source_aliases = {
        alias
        for branch in scene_item["anyOf"]
        if branch["properties"]["sourceAlias"].get("type") == "string"
        for alias in branch["properties"]["sourceAlias"]["enum"]
    }
    assert canonical_source_aliases == {item.alias for item in skeleton.sourceAliases}
    story_item = schemas[1]["$defs"]["StoryBeatDraftItemV2"]
    assert story_item["properties"]["beatAlias"]["enum"] == [
        "B01",
        "B02",
        "B03",
        "B04",
    ]
    usage_schema = schemas[1]["properties"]["assetUsageByAlias"]
    assert list(usage_schema["properties"]) == ["A01", "A02"]
    assert usage_schema["required"] == ["A01", "A02"]
    assert usage_schema["additionalProperties"] is False
    usage_item = schemas[1]["$defs"]["StoryAssetUsageDraftV2"]
    assert usage_item["properties"]["primaryBeatAlias"]["enum"] == [
        "B01",
        "B02",
        "B03",
        "B04",
    ]
    assert usage_item["properties"]["additionalBeatAliases"]["items"]["enum"] == [
        "B01",
        "B02",
        "B03",
        "B04",
    ]


def test_story_v3_schema_closes_source_event_aliases_from_frozen_text() -> None:
    """v3 wire 只能在主次动作旁选择服务器按原文生成的连续 E 别名。"""

    source = (
        "她把铜扣插进齿槽，铜扣被机关咬碎，黄铜匣弹开。"
        "她触到罗盘后齿轮加速，牵引链将钟摆提到最高处，随后落下并砸碎墙面。"
    )
    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=_setting_snapshot(),
        beat_ranges=[(0, 4), (4, 8), (8, 12), (12, 15)],
        scene_assets=materialize_scene_assets_draft(
            _scene_assets_draft_fixture(),
            setting_snapshot=_setting_snapshot(),
        ),
        source_text=source,
    )
    schema = json_schema_for_story_beats_draft_response(
        skeleton=skeleton,
        draft_version="3.0",
    )

    assert [event.alias for event in skeleton.sourceEventAliases] == [
        f"E{index:02d}" for index in range(1, 9)
    ]
    assert [event.label for event in skeleton.sourceEventAliases] == [
        "插入",
        "咬碎",
        "弹开",
        "触碰",
        "加速",
        "提起",
        "落下",
        "砸碎",
    ]
    item = schema["$defs"]["StoryBeatDraftItemV3"]
    for field_name in (
        "primarySourceEventAliases",
        "secondarySourceEventAliases",
    ):
        assert item["properties"][field_name]["items"]["enum"] == [
            f"E{index:02d}" for index in range(1, 9)
        ]


def test_story_v4_schema_closes_beats_and_keeps_event_ownership_on_server() -> None:
    """v4 wire 只让模型填写闭合 B 拍，E 归属由服务器固定且不进入 Schema。"""

    source = (
        "她把铜扣插进齿槽，铜扣被机关咬碎，黄铜匣弹开。"
        "她触到罗盘后齿轮加速，牵引链将钟摆提到最高处，随后落下并砸碎墙面。"
    )
    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=_setting_snapshot(),
        beat_ranges=[(0, 4), (4, 8), (8, 12), (12, 15)],
        scene_assets=materialize_scene_assets_draft(
            _scene_assets_draft_fixture(),
            setting_snapshot=_setting_snapshot(),
        ),
        source_text=source,
    )

    schema = json_schema_for_story_beats_draft_response(
        skeleton=skeleton,
        draft_version="4.0",
    )
    beats = schema["properties"]["beatsByAlias"]
    assert beats["required"] == ["B01", "B02", "B03", "B04"]
    assert beats["additionalProperties"] is False
    item = schema["$defs"]["StoryBeatDraftItemV4"]
    assert "beatAlias" not in item["properties"]
    assert "primarySourceEventAliases" not in str(schema)
    assert distribute_source_event_aliases(
        skeleton.sourceEventAliases,
        skeleton.beatAliases,
    ) == {
        "B01": [["E01"], ["E02"]],
        "B02": [["E03"], ["E04"]],
        "B03": [["E05"], ["E06"]],
        "B04": [["E07"], ["E08"]],
    }


def test_structured_source_event_sequence_ignores_unoccurred_keyword_context() -> None:
    """“尚未加速”等状态描述不能再把后续事件误判为已经提前发生。"""

    source = (
        "她把铜扣插进齿槽，铜扣被机关咬碎，黄铜匣弹开。"
        "她触到罗盘后齿轮加速，牵引链将钟摆提到最高处，随后落下并砸碎墙面。"
    )

    def beat(
        index: int,
        units: list[CameraActionUnit],
        aliases: list[list[str]],
    ) -> StoryBeatPlanArguments:
        start = (index - 1) * 4
        return StoryBeatPlanArguments(
            beatId=f"beat-{index:02d}",
            startSecond=start,
            endSecond=start + 4,
            dramaticPurpose=f"推进第{index}拍",
            performanceDirection="人物对机关变化作出克制可见反应",
            blocking="人物保持在机关旁并维持既定轴线",
            actionUnits=units,
            sourceEventAliasesByAction=aliases,
            actionComplexity="mechanical_sequence",
            sound="同步机关拟音",
            referencedAssetIds=[],
        )

    beats = [
        beat(
            1,
            [
                CameraActionUnit(
                    subject="林岚",
                    action="把铜扣插进齿槽",
                    visibleResult="铜扣被机关咬碎，远处齿轮尚未加速",
                )
            ],
            [["E02", "E01"]],
        ),
        beat(
            2,
            [
                CameraActionUnit(
                    subject="黄铜匣",
                    action="向上弹开",
                    visibleResult="匣盖完全打开",
                )
            ],
            [["E03"]],
        ),
        beat(
            3,
            [
                CameraActionUnit(
                    subject="林岚",
                    action="触碰罗盘",
                    visibleResult="整座钟楼齿轮同步加速",
                )
            ],
            [["E04", "E05"]],
        ),
        beat(
            4,
            [
                CameraActionUnit(
                    subject="牵引链",
                    action="把钟摆提到最高处",
                    visibleResult="钟摆抵达顶点",
                ),
                CameraActionUnit(
                    subject="钟摆",
                    action="轰然落下",
                    visibleResult="海侧墙面被砸碎",
                ),
            ],
            [["E06"], ["E08", "E07"]],
        ),
    ]

    # 同一动作槽内的数组只表达成员关系，wire 换序不应消耗模型纠错预算。
    validate_source_event_sequence(source, beats, require_structured=True)

    duplicated = list(beats)
    duplicated[1] = duplicated[1].model_copy(
        update={"sourceEventAliasesByAction": [["E03", "E02"]]}
    )
    with pytest.raises(
        ValueError,
        match=r"VIDEO_PLAN_SOURCE_EVENT_DUPLICATED.*重复 E02.*期望 E01 -> E02",
    ):
        validate_source_event_sequence(source, duplicated, require_structured=True)

    reordered = list(beats)
    reordered[1] = reordered[1].model_copy(
        update={"sourceEventAliasesByAction": [["E04"]]}
    )
    reordered[2] = reordered[2].model_copy(
        update={"sourceEventAliasesByAction": [["E03", "E05"]]}
    )
    with pytest.raises(
        ValueError,
        match=(
            r"VIDEO_PLAN_SOURCE_EVENT_ORDER_INVALID.*期望 E01 -> E02.*"
            r"实际 E01 -> E02 -> E04 -> E03"
        ),
    ):
        validate_source_event_sequence(source, reordered, require_structured=True)

    ungrounded = list(beats)
    ungrounded[0] = ungrounded[0].model_copy(
        update={
            "actionUnits": [
                CameraActionUnit(
                    subject="林岚",
                    action="把铜扣举到齿槽前",
                    visibleResult="铜扣被机关咬碎，远处齿轮尚未加速",
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="VIDEO_PLAN_SOURCE_EVENT_GROUNDING_INVALID"):
        validate_source_event_sequence(source, ungrounded, require_structured=True)

    assert action_unit_affirms_source_event(
        CameraActionUnit(
            subject="匣侧机关齿槽",
            action="突然闭合并挤压铜扣",
            visibleResult="铜扣断裂成碎片",
        ),
        "crush",
    )
    assert not action_unit_affirms_source_event(
        CameraActionUnit(
            subject="铜扣",
            action="自行晃动",
            visibleResult="铜扣断裂成碎片",
        ),
        "crush",
    )


def test_scene_assets_response_schema_enforces_source_target_exclusivity() -> None:
    """Schema 同时约束来源二选一和每类冻结设定允许的素材职责。"""

    snapshot = _setting_snapshot()
    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=snapshot,
        beat_ranges=[(0, 4)],
    )
    schema = json_schema_for_scene_assets_draft_response(skeleton=skeleton)
    item_branches = schema["$defs"]["SceneAssetDraftItemV1"]["anyOf"]

    direct_branch = next(
        branch
        for branch in item_branches
        if branch["properties"]["sourceAlias"]["type"] == "null"
    )
    canonical_branches = [branch for branch in item_branches if branch is not direct_branch]
    direct_properties = direct_branch["properties"]
    assert direct_properties["sourceAlias"]["type"] == "null"
    assert direct_properties["targetEntity"]["type"] == "string"
    expected_duties = {
        source.alias: set(source.allowedDuties) for source in skeleton.sourceAliases
    }
    seen_aliases: set[str] = set()
    for branch in canonical_branches:
        properties = branch["properties"]
        assert properties["sourceAlias"]["type"] == "string"
        assert properties["targetEntity"]["type"] == "null"
        aliases = properties["sourceAlias"]["enum"]
        duties = set(properties["duty"]["enum"])
        for alias in aliases:
            assert duties == expected_duties[alias]
            seen_aliases.add(alias)
    assert seen_aliases == set(expected_duties)
    for branch in item_branches:
        assert branch["additionalProperties"] is False
        assert set(branch["required"]) == set(branch["properties"])

    valid_fixture = _scene_assets_draft_fixture().model_dump(mode="json")
    valid = dict(valid_fixture)
    valid["assets"] = {
        f"asset{index:02d}": asset if index <= len(valid_fixture["assets"]) else None
        for index, asset in enumerate(
            [*valid_fixture["assets"], *([None] * 9)],
            start=1,
        )
    }
    jsonschema_rs.validate(schema, valid)
    both_non_null = json.loads(json.dumps(valid, ensure_ascii=False))
    both_non_null["assets"]["asset01"]["targetEntity"] = "林岚"
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(schema, both_non_null)
    both_null = json.loads(json.dumps(valid, ensure_ascii=False))
    both_null["assets"]["asset02"]["targetEntity"] = None
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(schema, both_null)
    wrong_source_duty = json.loads(json.dumps(valid, ensure_ascii=False))
    wrong_source_duty["assets"]["asset01"]["duty"] = "prop"
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(schema, wrong_source_duty)

    empty_skeleton = build_video_director_draft_skeleton(
        setting_snapshot=LongSerialSettingSnapshot.from_entries([]),
        beat_ranges=[(0, 4)],
    )
    empty_schema = json_schema_for_scene_assets_draft_response(skeleton=empty_skeleton)
    empty_branches = empty_schema["$defs"]["SceneAssetDraftItemV1"]["anyOf"]
    assert len(empty_branches) == 1
    assert empty_branches[0]["properties"]["sourceAlias"]["type"] == "null"


def test_responses_drafts_materialize_to_existing_canonical_plan() -> None:
    """三份轻量草案必须纯函数还原既有正式参数，模型不拥有服务器事实。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    expected = normalize_strict_tool_arguments(
        full_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    scene_assets = materialize_scene_assets_draft(
        _scene_assets_draft_fixture(),
        setting_snapshot=snapshot,
    )
    assert scene_assets.assets == expected.assets

    story_draft = StoryBeatsDraftV2(
        beats=[
            StoryBeatDraftItemV2(
                beatAlias=f"B{index:02d}",
                dramaticPurpose=beat.dramaticPurpose,
                performanceDirection=beat.performanceDirection,
                blocking=beat.blocking,
                primaryAction=beat.actionUnits[0],
                secondaryAction=beat.actionUnits[1] if len(beat.actionUnits) > 1 else None,
                actionComplexity=beat.actionComplexity,
                sound=beat.sound,
            )
            for index, beat in enumerate(expected.beats, start=1)
        ],
        assetUsageByAlias={
            alias: StoryAssetUsageDraftV2(
                primaryBeatAlias="B01",
                additionalBeatAliases=["B02", "B03", "B04"] if alias == "A01" else [],
                anchorAssetAlias="A01" if alias == "A02" else None,
            )
            for alias in ("A01", "A02")
        },
    )
    story_beats = materialize_story_beats_draft(
        story_draft,
        scene_assets=scene_assets,
        beat_ranges=ranges,
    )
    story = merge_story_stage_arguments(
        scene_assets,
        story_beats,
        beat_ranges=ranges,
    )
    cinematography_draft = CinematographyDraftV1(
        cinematographyBase=expected.cinematographyBase,
        lightingSetup=expected.lightingSetup,
        beats=[
            CinematographyBeatDraftItemV1(
                beatAlias=f"B{index:02d}",
                cameraSpec=beat.cameraSpec,
                lightingCue=beat.lightingCue if index == 1 else None,
                cameraMotivation=beat.cameraMotivation,
                axisTransition=beat.axisTransition,
                shotProgression=beat.shotProgression,
                transition=beat.transition,
            )
            for index, beat in enumerate(expected.beats, start=1)
        ],
    )
    actual = materialize_cinematography_draft(
        cinematography_draft,
        story=story,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    # 初态关键帧只在锚定素材的首次使用拍出现；后续拍不能重复伪造初态。
    expected = expected.model_copy(
        update={
            "beats": [
                beat.model_copy(
                    update={
                        "referencedAssetIds": ["asset01", "asset02"] if index == 0 else ["asset01"]
                    }
                )
                for index, beat in enumerate(expected.beats)
            ]
        }
    )
    assert actual == expected


def test_later_prop_debut_does_not_repeat_initial_state_keyframe() -> None:
    """另一项道具在后续拍首次出现时，不能把机关起始拍的初态图再次塞进镜头。"""

    snapshot = _setting_snapshot()
    base_assets = _scene_assets_draft_fixture()
    scene_assets = materialize_scene_assets_draft(
        base_assets.model_copy(
            update={
                "assets": [
                    *base_assets.assets,
                    SceneAssetDraftItemV1(
                        sourceAlias="I01",
                        duty="prop",
                        targetEntity=None,
                        includeFeatures=["黄铜齿轮", "黑水指针"],
                        excludeFeatures=["人物手部"],
                    ),
                ]
            }
        ),
        setting_snapshot=snapshot,
    )
    base_story = _story_draft_fixture(beat_count=2)
    story_draft = base_story.model_copy(
        update={
            "beats": [
                base_story.beats[0].model_copy(
                    update={"actionComplexity": "mechanical_sequence"}
                ),
                base_story.beats[1],
            ],
            "assetUsageByAlias": {
                **base_story.assetUsageByAlias,
                "A03": StoryAssetUsageDraftV2(
                    primaryBeatAlias="B02",
                    additionalBeatAliases=[],
                    anchorAssetAlias=None,
                ),
            },
        }
    )

    result = materialize_story_beats_draft(
        story_draft,
        scene_assets=scene_assets,
        beat_ranges=[(0, 4), (4, 8)],
    )

    assert "asset02" in result.beats[0].referencedAssetIds
    assert "asset03" not in result.beats[0].referencedAssetIds
    assert "asset03" in result.beats[1].referencedAssetIds
    assert "asset02" not in result.beats[1].referencedAssetIds


def test_initial_state_prefers_first_mechanical_beat_over_earlier_prop_debut() -> None:
    """道具可以先入画，但初态关键帧必须留到全场第一个真正的机械动作拍。"""

    snapshot = _setting_snapshot()
    base_assets = _scene_assets_draft_fixture()
    scene_assets = materialize_scene_assets_draft(
        base_assets.model_copy(
            update={
                "assets": [
                    SceneAssetDraftItemV1(
                        sourceAlias="I01",
                        duty="prop",
                        targetEntity=None,
                        includeFeatures=["黄铜齿轮", "黑水指针"],
                        excludeFeatures=["人物手部"],
                    ),
                    base_assets.assets[1],
                ]
            }
        ),
        setting_snapshot=snapshot,
    )
    base_story = _story_draft_fixture(beat_count=2)
    story_draft = base_story.model_copy(
        update={
            "beats": [
                base_story.beats[0],
                base_story.beats[1].model_copy(
                    update={"actionComplexity": "mechanical_sequence"}
                ),
            ],
            "assetUsageByAlias": {
                "A01": StoryAssetUsageDraftV2(
                    primaryBeatAlias="B01",
                    additionalBeatAliases=["B02"],
                    anchorAssetAlias=None,
                ),
                "A02": StoryAssetUsageDraftV2(
                    primaryBeatAlias="B01",
                    additionalBeatAliases=[],
                    anchorAssetAlias="A01",
                ),
            },
        }
    )

    result = materialize_story_beats_draft(
        story_draft,
        scene_assets=scene_assets,
        beat_ranges=[(0, 4), (4, 8)],
    )

    assert "asset01" in result.beats[0].referencedAssetIds
    assert "asset02" not in result.beats[0].referencedAssetIds
    assert "asset01" in result.beats[1].referencedAssetIds
    assert "asset02" in result.beats[1].referencedAssetIds


def test_initial_state_recognizes_simple_labeled_insert_as_mechanical_start() -> None:
    """模型即使误标 simple，“插进齿槽”仍必须成为初态关键帧的首个机关起点。"""

    snapshot = _setting_snapshot()
    base_assets = _scene_assets_draft_fixture()
    scene_assets = materialize_scene_assets_draft(
        base_assets.model_copy(
            update={
                "assets": [
                    SceneAssetDraftItemV1(
                        sourceAlias="I01",
                        duty="prop",
                        targetEntity=None,
                        includeFeatures=["黄铜齿轮", "黑水指针"],
                        excludeFeatures=["人物手部"],
                    ),
                    base_assets.assets[1],
                ]
            }
        ),
        setting_snapshot=snapshot,
    )
    base_story = _story_draft_fixture(beat_count=2)
    story_draft = base_story.model_copy(
        update={
            "beats": [
                base_story.beats[0].model_copy(
                    update={
                        "primaryAction": base_story.beats[0].primaryAction.model_copy(
                            update={
                                "subject": "铜扣",
                                "action": "插进黄铜匣齿槽",
                                "visibleResult": "铜扣完全嵌入齿槽",
                            }
                        ),
                        "actionComplexity": "simple",
                    }
                ),
                base_story.beats[1].model_copy(
                    update={
                        "primaryAction": base_story.beats[1].primaryAction.model_copy(
                            update={
                                "subject": "机关",
                                "action": "咬碎铜扣",
                                "visibleResult": "黄铜碎片掉落",
                            }
                        ),
                        "actionComplexity": "impact_transition",
                    }
                ),
            ],
            "assetUsageByAlias": {
                "A01": StoryAssetUsageDraftV2(
                    primaryBeatAlias="B01",
                    additionalBeatAliases=["B02"],
                    anchorAssetAlias=None,
                ),
                "A02": StoryAssetUsageDraftV2(
                    primaryBeatAlias="B02",
                    additionalBeatAliases=[],
                    anchorAssetAlias="A01",
                ),
            },
        }
    )

    result = materialize_story_beats_draft(
        story_draft,
        scene_assets=scene_assets,
        beat_ranges=[(0, 4), (4, 8)],
    )

    assert "asset02" in result.beats[0].referencedAssetIds
    assert "asset02" not in result.beats[1].referencedAssetIds


def test_scene_assets_draft_rejects_unknown_alias_mismatch_and_duplicate() -> None:
    """素材物化不猜测未知设定，也不修补职责错配或重复素材。"""

    snapshot = _setting_snapshot()
    base = _scene_assets_draft_fixture().model_dump(mode="json")
    invalid_cases = [
        ("Z99", "identity", "VIDEO_DRAFT_UNKNOWN_SOURCE_ALIAS"),
        ("C02", "prop", "VIDEO_DRAFT_SOURCE_DUTY_MISMATCH"),
    ]
    for source_alias, duty, message in invalid_cases:
        changed = json.loads(json.dumps(base, ensure_ascii=False))
        changed["assets"][0]["sourceAlias"] = source_alias
        changed["assets"][0]["duty"] = duty
        with pytest.raises(ValueError, match=message):
            materialize_scene_assets_draft(
                SceneAssetsDraftV1.model_validate(changed),
                setting_snapshot=snapshot,
            )

    duplicated = json.loads(json.dumps(base, ensure_ascii=False))
    duplicated["assets"].append(duplicated["assets"][0])
    with pytest.raises(ValueError, match="VIDEO_DRAFT_ASSET_DUPLICATED"):
        materialize_scene_assets_draft(
            SceneAssetsDraftV1.model_validate(duplicated),
            setting_snapshot=snapshot,
        )

    bypass = json.loads(json.dumps(base, ensure_ascii=False))
    bypass["assets"][0].update(
        {
            "sourceAlias": None,
            "targetEntity": "林岚",
            "duty": "identity",
        }
    )
    with pytest.raises(ValueError, match="VIDEO_DRAFT_CANON_ALIAS_REQUIRED"):
        materialize_scene_assets_draft(
            SceneAssetsDraftV1.model_validate(bypass),
            setting_snapshot=snapshot,
        )


def test_story_draft_rejects_duplicate_unknown_missing_and_overlong_values() -> None:
    """自然数组仍必须闭合所有别名，失败时不得截断或静默去重。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8)]
    scene_assets = materialize_scene_assets_draft(
        _scene_assets_draft_fixture(),
        setting_snapshot=snapshot,
    )
    valid = _story_draft_fixture(beat_count=2)

    duplicate = valid.model_copy(update={"beats": [valid.beats[0], valid.beats[0]]})
    with pytest.raises(ValueError, match="VIDEO_DRAFT_BEAT_ALIAS_DUPLICATED"):
        materialize_story_beats_draft(
            duplicate,
            scene_assets=scene_assets,
            beat_ranges=ranges,
        )

    unknown_usage = dict(valid.assetUsageByAlias)
    unknown_usage["A99"] = unknown_usage["A01"]
    unknown = valid.model_copy(update={"assetUsageByAlias": unknown_usage})
    with pytest.raises(ValueError, match="VIDEO_DRAFT_UNKNOWN_ASSET_ALIAS"):
        materialize_story_beats_draft(
            unknown,
            scene_assets=scene_assets,
            beat_ranges=ranges,
        )

    missing = valid.model_copy(update={"beats": [valid.beats[0]]})
    with pytest.raises(ValueError, match="VIDEO_DRAFT_BEAT_MISSING"):
        materialize_story_beats_draft(
            missing,
            scene_assets=scene_assets,
            beat_ranges=ranges,
        )

    missing_usage = dict(valid.assetUsageByAlias)
    missing_usage.pop("A02")
    uncovered = valid.model_copy(update={"assetUsageByAlias": missing_usage})
    with pytest.raises(ValueError) as uncovered_error:
        materialize_story_beats_draft(
            uncovered,
            scene_assets=scene_assets,
            beat_ranges=ranges,
        )
    assert "VIDEO_DRAFT_ASSET_USAGE_MISSING" in str(uncovered_error.value)
    assert "A02" in str(uncovered_error.value)
    assert "asset02" not in str(uncovered_error.value)

    duplicated_usage = dict(valid.assetUsageByAlias)
    duplicated_usage["A01"] = StoryAssetUsageDraftV2(
        primaryBeatAlias="B01",
        additionalBeatAliases=["B01"],
        anchorAssetAlias=None,
    )
    duplicated_alias = valid.model_copy(update={"assetUsageByAlias": duplicated_usage})
    with pytest.raises(ValueError, match="VIDEO_DRAFT_ASSET_USAGE_DUPLICATED"):
        materialize_story_beats_draft(
            duplicated_alias,
            scene_assets=scene_assets,
            beat_ranges=ranges,
        )

    reversed_usage = dict(valid.assetUsageByAlias)
    reversed_usage["A01"] = StoryAssetUsageDraftV2(
        primaryBeatAlias="B02",
        additionalBeatAliases=["B01"],
        anchorAssetAlias=None,
    )
    reversed_alias = valid.model_copy(update={"assetUsageByAlias": reversed_usage})
    with pytest.raises(ValueError, match="VIDEO_DRAFT_ASSET_USAGE_ORDER_INVALID"):
        materialize_story_beats_draft(
            reversed_alias,
            scene_assets=scene_assets,
            beat_ranges=ranges,
        )

    overlong = "长" * 161
    raw = valid.model_dump(mode="json")
    raw["beats"][0]["dramaticPurpose"] = overlong
    with pytest.raises(ValidationError):
        StoryBeatsDraftV2.model_validate(raw)
    assert raw["beats"][0]["dramaticPurpose"] == overlong


def test_deepseek_strict_schema_uses_compact_inherit_lighting_branch() -> None:
    """首拍提交完整建立灯光，后续拍只在真实变化时展开专业字段。"""

    schema = json_schema_for_strict_tool(
        setting_snapshot=_setting_snapshot(),
        beat_ranges=[(0, 4), (4, 8), (8, 12), (12, 15)],
    )
    definitions = schema["$def"]
    establish = definitions["EstablishLightingCue"]
    establish_properties = establish["properties"]

    assert definitions["Beat01"]["properties"]["lightingCue"] == {
        "$ref": "#/$def/EstablishLightingCue"
    }
    assert establish_properties["continuityMode"]["enum"] == ["establish"]
    assert set(establish["required"]) == set(establish_properties)

    expected_professional_fields = {
        "continuityMode",
        "motivatedChange",
        "keyLight",
        "fillStrategy",
        "fillDirection",
        "fillRelativeStops",
        "edgeLight",
        "atmosphere",
        "visibleResult",
    }
    for index in range(2, 5):
        lighting = definitions[f"Beat{index:02d}"]["properties"]["lightingCue"]
        inherit_branch, change_branch = lighting["anyOf"]
        assert inherit_branch == {"type": "string", "enum": ["__INHERIT__"]}
        assert change_branch["type"] == "object"
        assert change_branch["properties"]["continuityMode"]["enum"] == ["motivated_change"]
        assert set(change_branch["properties"]) == expected_professional_fields
        assert set(change_branch["required"]) == expected_professional_fields


@pytest.mark.parametrize("duration_seconds", range(4, 16))
def test_deepseek_strict_schema_matches_each_runtime_beat_budget(
    duration_seconds: int,
) -> None:
    """四至十五秒的节拍与逐拍动作容量必须由固定对象属性表达。"""

    ranges = _balanced_ranges(duration_seconds)
    schema = json_schema_for_strict_tool(
        setting_snapshot=_setting_snapshot(),
        beat_ranges=ranges,
    )

    beat_properties = schema["properties"]["beats"]["properties"]
    assert list(beat_properties) == [f"beat{index:02d}" for index in range(1, len(ranges) + 1)]
    for index, (start, end) in enumerate(ranges, start=1):
        beat = schema["$def"][f"Beat{index:02d}"]
        properties = beat["properties"]
        assert "cameraSpec" in properties
        assert "lightingCue" in properties
        assert "primaryAction" in properties
        assert ("secondaryAction" in properties) is (ceil((end - start) / 2) == 2)
        assert "cameraAngle" not in properties
        assert "cameraMovement" not in properties
        assert "beatId" not in properties
        assert "startSecond" not in properties
        assert "endSecond" not in properties
        assert "referencedAssetIds" not in properties

    asset_properties = schema["properties"]["assets"]["properties"]
    assert list(asset_properties) == ["asset01", "additionalAssets"]
    assert asset_properties["asset01"]["$ref"] == "#/$def/AssetSlot"
    assert asset_properties["additionalAssets"]["type"] == "array"
    assert asset_properties["additionalAssets"]["items"] == {"$ref": "#/$def/AssetSlot"}
    assert "minItems" not in asset_properties["additionalAssets"]
    assert "maxItems" not in asset_properties["additionalAssets"]

    negative_properties = schema["properties"]["negativeConstraints"]["properties"]
    assert list(negative_properties) == ["constraint01", "additionalConstraints"]
    assert negative_properties["additionalConstraints"]["type"] == "array"
    assert negative_properties["additionalConstraints"]["items"]["type"] == "string"
    assert "minItems" not in negative_properties["additionalConstraints"]
    assert "maxItems" not in negative_properties["additionalConstraints"]

    beat_usage = schema["$def"]["AssetSlot"]["properties"]["usedInBeats"]
    assert beat_usage["type"] == "string"
    assert beat_usage["pattern"] == rf"^[01]{{{len(beat_properties)}}}$"
    assert "enum" not in beat_usage
    assert "BeatUsage" not in schema["$def"]


def test_strict_asset_slot_is_unified_and_defers_cross_field_rules() -> None:
    """wire 只保留一个素材对象，并由本地派生领域字段与校验组合。"""

    snapshot = _setting_snapshot()
    schema = json_schema_for_strict_tool(
        setting_snapshot=snapshot,
        beat_ranges=_balanced_ranges(5),
    )
    definitions = schema["$def"]
    asset_slot = definitions["AssetSlot"]
    properties = asset_slot["properties"]

    assert set(properties) == {
        "duty",
        "modality",
        "bindingScope",
        "settingId",
        "targetEntity",
        "keyframeRole",
        "include",
        "exclude",
        "usedInBeats",
    }
    assert "featureDomain" not in properties
    assert "assetId" not in properties
    assert "music" not in properties["duty"]["enum"]
    assert properties["modality"]["enum"] == ["image", "video", "audio"]
    assert properties["keyframeRole"]["enum"] == [
        "initial_state",
        "end_state",
        "transition_anchor",
        "not_applicable",
    ]
    assert properties["settingId"]["enum"] == [
        "character-lin-lan",
        "character-shen-qing",
        "item-memory-compass",
        "location-medicine-shop",
        "relationship-allies",
        "world-visual-style",
        "__NONE__",
    ]


@pytest.mark.parametrize("duration_seconds", range(4, 16))
def test_normalize_strict_tool_arguments_is_total_for_valid_fixed_slots(
    duration_seconds: int,
) -> None:
    """任一试制时长的合法固定槽输出都能一次投影为正式参数。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(duration_seconds)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)

    envelope = PlannerToolEnvelopeV2.model_validate(raw)
    result = normalize_strict_tool_arguments(
        envelope.model_dump(mode="json"),
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    assert [asset.assetId for asset in result.assets] == ["asset01", "asset02"]
    assert result.assets[0].featureDomain == "character_identity"
    assert result.assets[0].targetEntity == "沈青"
    assert result.assets[0].settingReference is not None
    assert result.assets[0].settingReference.id == "character-shen-qing"
    assert result.assets[1].featureDomain == "keyframe"
    assert result.assets[1].keyframeRole == "initial_state"
    assert result.cinematographyBase.captureFormat == "super_35"
    assert result.cinematographyBase.frameRateFps == 24
    assert result.lightingSetup.ambientColorTemperatureK == 6_500
    assert result.lightingSetup.cameraWhiteBalanceK == 4_300
    assert result.lightingSetup.keyToFillStops == 2
    assert result.dramaticArc == "克制试探逐步升级为不可逆的机关启动。"
    assert [(beat.startSecond, beat.endSecond) for beat in result.beats] == ranges
    assert [beat.beatId for beat in result.beats] == [
        f"beat-{index:02d}" for index in range(1, len(ranges) + 1)
    ]
    for beat, (start, end) in zip(result.beats, ranges, strict=True):
        assert len(beat.actionUnits) == ceil((end - start) / 2)
        assert beat.referencedAssetIds == ["asset01", "asset02"]
        assert beat.cameraSpec.focalLengthMm == 40
        assert beat.cameraSpec.tStop == 2.8
        assert beat.lightingCue.keyLight.colorTemperatureK == 6_500
        assert beat.dramaticPurpose.startswith("推进第")
        assert beat.performanceDirection.startswith("林岚先屏息")
        assert beat.blocking.startswith("林岚位于画面左三分线")
        assert beat.cameraMotivation.startswith("机关齿轮")
        assert beat.axisTransition == "hold"
    assert result.beats[0].lightingCue.continuityMode == "establish"
    assert all(beat.lightingCue.continuityMode == "inherit" for beat in result.beats[1:])
    assert all(
        beat.lightingCue.motivatedChange == "延续上一拍全部灯光事实" for beat in result.beats[1:]
    )
    assert result.negativeConstraints == ["人物身份漂移", "现代物件"]


def test_story_normalizer_returns_versioned_canonical_json() -> None:
    """第一阶段先完成业务归一化，再把严格规范 JSON 交给摄影阶段。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_raw, _cinematography_raw = _split_v2_wire_fixture(full_raw)

    story = normalize_story_strict_tool_arguments(
        story_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    restored = StoryPlanStageArguments.model_validate_json(story.model_dump_json())

    assert restored.schemaVersion == "1.0"
    assert restored == story
    assert [asset.assetId for asset in story.assets] == ["asset01", "asset02"]
    assert story.assets[0].settingReference is not None
    assert story.assets[0].settingReference.id == "character-shen-qing"
    assert story.beats[0].referencedAssetIds == ["asset01", "asset02"]
    assert story.beats[0].startSecond == 0
    assert story.beats[-1].endSecond == 15


def test_three_stage_story_normalizers_merge_to_existing_canonical_contract() -> None:
    """V3 前两阶段合并后必须等于旧故事阶段产生的同一 canonical 结果。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    legacy_story_raw, _cinematography_raw = _split_v2_wire_fixture(full_raw)
    scene_assets_raw, story_beats_raw = _compact_stage_wire_fixture(full_raw)

    scene_assets = normalize_scene_assets_strict_tool_arguments(
        scene_assets_raw,
        setting_snapshot=snapshot,
    )
    story_beats = normalize_story_beats_strict_tool_arguments(
        story_beats_raw,
        scene_assets=scene_assets,
        beat_ranges=ranges,
    )
    merged = merge_story_stage_arguments(
        scene_assets,
        story_beats,
        beat_ranges=ranges,
    )
    legacy = normalize_story_strict_tool_arguments(
        legacy_story_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    assert SceneAssetsStageArguments.model_validate_json(scene_assets.model_dump_json()) == (
        scene_assets
    )
    assert StoryBeatsStageArguments.model_validate_json(story_beats.model_dump_json()) == (
        story_beats
    )
    assert merged.model_dump(mode="json") == legacy.model_dump(mode="json")


def test_story_beats_stage_maps_asset_usage_per_beat() -> None:
    """素材引用由故事节拍阶段逐拍决定，不能在素材阶段提前猜测。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    scene_assets_raw, story_beats_raw = _compact_stage_wire_fixture(full_raw)
    story_beats_raw["beats"]["beat01"]["assetUsage"] = "10"
    story_beats_raw["beats"]["beat02"]["assetUsage"] = "01"
    scene_assets = normalize_scene_assets_strict_tool_arguments(
        scene_assets_raw,
        setting_snapshot=snapshot,
    )

    story_beats = normalize_story_beats_strict_tool_arguments(
        story_beats_raw,
        scene_assets=scene_assets,
        beat_ranges=ranges,
    )

    assert story_beats.beats[0].referencedAssetIds == ["asset01"]
    assert story_beats.beats[1].referencedAssetIds == ["asset02"]
    assert story_beats.beats[2].referencedAssetIds == ["asset01", "asset02"]


def test_story_beats_stage_rejects_asset_never_used_across_beats() -> None:
    """逐拍位图可以为某拍全零，但合并前每个声明素材必须至少使用一次。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    scene_assets_raw, story_beats_raw = _compact_stage_wire_fixture(full_raw)
    for beat in story_beats_raw["beats"].values():
        beat["assetUsage"] = "10"
    scene_assets = normalize_scene_assets_strict_tool_arguments(
        scene_assets_raw,
        setting_snapshot=snapshot,
    )

    with pytest.raises(ValueError, match="未被任何节拍使用的素材：asset02"):
        normalize_story_beats_strict_tool_arguments(
            story_beats_raw,
            scene_assets=scene_assets,
            beat_ranges=ranges,
        )


def test_scene_assets_stage_rejects_overlong_feature_without_truncation() -> None:
    """紧凑文本超限必须原样失败，不能截断后继续形成 checkpoint。"""

    snapshot = _setting_snapshot()
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=_balanced_ranges(5))
    scene_assets_raw, _story_beats_raw = _compact_stage_wire_fixture(full_raw)
    overlong = "特" * 81
    scene_assets_raw["assets"]["asset01"]["include"] = [overlong]

    with pytest.raises(ValueError, match=r"asset01\.include\[0\].*1 至 80 字"):
        normalize_scene_assets_strict_tool_arguments(
            scene_assets_raw,
            setting_snapshot=snapshot,
        )
    assert scene_assets_raw["assets"]["asset01"]["include"] == [overlong]


def test_video_story_checkpoint_contract_keeps_six_resource_bindings() -> None:
    """查询、检查点和响应必须携带同一组资源身份，供 Agent 复核防串线。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_raw, _cinematography_raw = _split_v2_wire_fixture(full_raw)
    story = normalize_story_strict_tool_arguments(
        story_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    identity = {
        "protocolVersion": "1.0",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "projectId": "project-1",
        "sceneId": "scene-1",
    }

    query = VideoPlanProgressQuery.model_validate(identity)
    checkpoint = VideoStoryPlanCheckpointCallback.model_validate(
        {
            **identity,
            "eventId": "event-1",
            "checkpointStage": "story",
            "storyPlan": story.model_dump(mode="json"),
            "attemptState": {
                "reservedCalls": 2,
                "inheritedCalls": 0,
                "pendingStage": None,
            },
        }
    )
    response = VideoPlanProgressResponse.model_validate(
        {
            **identity,
            "inputFingerprint": _PLAN_INPUT_FINGERPRINT,
            "status": "active",
            "checkpointStage": "story",
            "storyPlan": story.model_dump(mode="json"),
            "attemptState": {
                "reservedCalls": 2,
                "inheritedCalls": 0,
                "pendingStage": None,
            },
        }
    )

    assert query.model_dump(mode="json") == identity
    assert checkpoint.storyPlan == story
    assert checkpoint.attemptState.reservedCalls == 2
    assert response.storyPlan == story
    assert response.attemptState.pendingStage is None
    assert response.model_dump(mode="json", exclude={"storyPlan"}) == {
        **identity,
        "inputFingerprint": _PLAN_INPUT_FINGERPRINT,
        "status": "active",
        "checkpointStage": "story",
        "sceneAssetsPlan": None,
        "attemptState": {
            "reservedCalls": 2,
            "inheritedCalls": 0,
            "pendingStage": None,
        },
    }


def test_checkpoint_can_persist_scene_assets_stage_and_must_clear_pending() -> None:
    """第一阶段成功后只保存素材 canonical，并在同一 checkpoint 清除 pending。"""

    snapshot = _setting_snapshot()
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=_balanced_ranges(5))
    scene_assets_raw, _story_beats_raw = _compact_stage_wire_fixture(full_raw)
    scene_assets = normalize_scene_assets_strict_tool_arguments(
        scene_assets_raw,
        setting_snapshot=snapshot,
    )
    identity = {
        "protocolVersion": "1.0",
        "eventId": "event-assets",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "projectId": "project-1",
        "sceneId": "scene-1",
    }

    checkpoint = VideoStoryPlanCheckpointCallback.model_validate(
        {
            **identity,
            "checkpointStage": "scene_assets",
            "sceneAssetsPlan": scene_assets.model_dump(mode="json"),
            "attemptState": {"reservedCalls": 1, "pendingStage": None},
        }
    )

    assert checkpoint.sceneAssetsPlan == scene_assets
    assert checkpoint.storyPlan is None
    with pytest.raises(ValidationError, match="必须清除 pendingStage"):
        VideoStoryPlanCheckpointCallback.model_validate(
            {
                **identity,
                "checkpointStage": "scene_assets",
                "sceneAssetsPlan": scene_assets.model_dump(mode="json"),
                "attemptState": {
                    "reservedCalls": 1,
                    "pendingStage": "story_beats",
                },
            }
        )


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_video_progress_terminal_status_rejects_story_checkpoint(
    status: Literal["completed", "failed"],
) -> None:
    """终态不能带故事检查点，避免重放任务误判为仍可继续。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_raw, _cinematography_raw = _split_v2_wire_fixture(full_raw)
    story = normalize_story_strict_tool_arguments(
        story_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    with pytest.raises(ValidationError, match="不能携带阶段计划"):
        VideoPlanProgressResponse(
            protocolVersion="1.0",
            jobId="job-1",
            runId="run-1",
            taskId="task-1",
            novelId="novel-1",
            projectId="project-1",
            sceneId="scene-1",
            inputFingerprint=_PLAN_INPUT_FINGERPRINT,
            status=status,
            checkpointStage="terminal",
            storyPlan=story,
            attemptState=VideoPlanAttemptState(reservedCalls=3, pendingStage=None),
        )


def test_video_progress_active_may_omit_checkpoint_and_all_contracts_forbid_extra() -> None:
    """尚未完成第一阶段时 active 可空；三个耐久契约都拒绝未知字段。"""

    identity = {
        "protocolVersion": "1.0",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "projectId": "project-1",
        "sceneId": "scene-1",
    }
    response = VideoPlanProgressResponse.model_validate(
        {
            **identity,
            "inputFingerprint": _PLAN_INPUT_FINGERPRINT,
            "status": "active",
            "checkpointStage": "empty",
            "attemptState": {"reservedCalls": 0, "pendingStage": None},
        }
    )

    assert response.storyPlan is None
    with pytest.raises(ValidationError, match="extra_forbidden"):
        VideoPlanProgressQuery.model_validate({**identity, "unknown": "value"})
    with pytest.raises(ValidationError, match="checkpointStage"):
        VideoStoryPlanCheckpointCallback.model_validate(
            {**identity, "eventId": "event-1", "storyPlan": None}
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        VideoPlanProgressResponse.model_validate(
            {
                **identity,
                "inputFingerprint": _PLAN_INPUT_FINGERPRINT,
                "status": "completed",
                "checkpointStage": "terminal",
                "attemptState": {"reservedCalls": 3, "pendingStage": None},
                "unknown": "value",
            }
        )


def test_video_call_reservation_is_atomic_bounded_and_stage_bound() -> None:
    """每次调用前恰好加一，目标只能是 checkpoint 后的下一阶段。"""

    identity = {
        "protocolVersion": "1.0",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "projectId": "project-1",
        "sceneId": "scene-1",
    }
    first_request = VideoPlanCallReservationRequest.model_validate(
        {
            **identity,
            "eventId": "reserve-1",
            "checkpointStage": "empty",
            "stage": "scene_assets",
            "expectedReservedCalls": 0,
        }
    )
    first_response = VideoPlanCallReservationResponse.model_validate(
        {
            **identity,
            "eventId": "reserve-1",
            "checkpointStage": "empty",
            "stage": "scene_assets",
            "reservedCallsBefore": 0,
            "attemptState": {
                "reservedCalls": 1,
                "pendingStage": "scene_assets",
            },
        }
    )

    assert first_request.expectedReservedCalls == 0
    assert first_response.attemptState.reservedCalls == 1
    with pytest.raises(ValidationError, match="只能预留 story_beats"):
        VideoPlanCallReservationRequest.model_validate(
            {
                **identity,
                "eventId": "bad-stage",
                "checkpointStage": "scene_assets",
                "stage": "cinematography",
                "expectedReservedCalls": 1,
            }
        )
    with pytest.raises(ValidationError, match="恰好增加一次"):
        VideoPlanCallReservationResponse.model_validate(
            {
                **identity,
                "eventId": "bad-count",
                "checkpointStage": "empty",
                "stage": "scene_assets",
                "reservedCallsBefore": 0,
                "attemptState": {
                    "reservedCalls": 2,
                    "pendingStage": "scene_assets",
                },
            }
        )


def test_attempt_ledger_shares_two_global_corrections_across_early_stages() -> None:
    """素材用掉一次后，故事还能用一次，但不能预留第三个额外纠正。"""

    identity = {
        "protocolVersion": "1.0",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "projectId": "project-1",
        "sceneId": "scene-1",
    }

    second_stage_first_call = VideoPlanCallReservationRequest.model_validate(
        {
            **identity,
            "eventId": "story-first",
            "checkpointStage": "scene_assets",
            "stage": "story_beats",
            "expectedReservedCalls": 2,
        }
    )
    assert second_stage_first_call.expectedReservedCalls == 2

    story_correction = VideoPlanCallReservationRequest.model_validate(
        {
            **identity,
            "eventId": "story-correction",
            "checkpointStage": "scene_assets",
            "stage": "story_beats",
            "expectedReservedCalls": 3,
        }
    )
    assert story_correction.expectedReservedCalls == 3

    with pytest.raises(ValidationError, match="重复消耗纠正预算"):
        VideoPlanCallReservationRequest.model_validate(
            {
                **identity,
                "eventId": "story-third-correction",
                "checkpointStage": "scene_assets",
                "stage": "story_beats",
                "expectedReservedCalls": 4,
            }
        )


def test_attempt_ledger_allows_two_camera_corrections_but_no_sixth_call() -> None:
    """摄影可在 story 检查点后连续预留三次，但总数不得超过五。"""

    identity = {
        "protocolVersion": "1.0",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "projectId": "project-1",
        "sceneId": "scene-1",
        "checkpointStage": "story",
        "stage": "cinematography",
    }

    for expected in (2, 3, 4):
        request = VideoPlanCallReservationRequest.model_validate(
            {
                **identity,
                "eventId": f"camera-{expected}",
                "expectedReservedCalls": expected,
            }
        )
        assert request.expectedReservedCalls == expected

    with pytest.raises(ValidationError):
        VideoPlanCallReservationRequest.model_validate(
            {
                **identity,
                "eventId": "camera-sixth",
                "expectedReservedCalls": 5,
            }
        )


def test_progress_pending_and_terminal_attempt_state_rules() -> None:
    """active 只允许下一阶段 pending，终态必须清除 pending 和计划。"""

    identity = {
        "protocolVersion": "1.0",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "projectId": "project-1",
        "sceneId": "scene-1",
    }
    pending = VideoPlanProgressResponse.model_validate(
        {
            **identity,
            "inputFingerprint": _PLAN_INPUT_FINGERPRINT,
            "status": "active",
            "checkpointStage": "empty",
            "attemptState": {
                "reservedCalls": 1,
                "pendingStage": "scene_assets",
            },
        }
    )
    terminal = VideoPlanProgressResponse.model_validate(
        {
            **identity,
            "inputFingerprint": _PLAN_INPUT_FINGERPRINT,
            "status": "completed",
            "checkpointStage": "terminal",
            "attemptState": {"reservedCalls": 3, "pendingStage": None},
        }
    )

    assert pending.attemptState.pendingStage == "scene_assets"
    assert terminal.checkpointStage == "terminal"
    with pytest.raises(ValidationError, match="不能携带 pendingStage"):
        VideoPlanProgressResponse.model_validate(
            {
                **identity,
                "inputFingerprint": _PLAN_INPUT_FINGERPRINT,
                "status": "failed",
                "checkpointStage": "terminal",
                "attemptState": {
                    "reservedCalls": 4,
                    "pendingStage": "cinematography",
                },
            }
        )


def test_split_normalizer_matches_existing_full_normalizer() -> None:
    """两阶段合并必须与同一合法 wire 的现有完整归一化结果完全一致。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_raw, cinematography_raw = _split_v2_wire_fixture(full_raw)
    story = normalize_story_strict_tool_arguments(
        story_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    split_result = normalize_split_strict_tool_arguments(
        story,
        cinematography_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    full_result = normalize_strict_tool_arguments(
        full_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    assert split_result.model_dump(mode="json") == full_result.model_dump(mode="json")


def test_story_normalizer_rejects_extra_top_level_field() -> None:
    """第一阶段本地规范化必须拒绝 schema 外字段，不能延迟到摄影阶段。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_raw, _cinematography_raw = _split_v2_wire_fixture(full_raw)
    story_raw["compositionNote"] = "不允许的旁路说明"

    with pytest.raises(ValueError, match="story 字段不完整.*额外=compositionNote"):
        normalize_story_strict_tool_arguments(
            story_raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_split_normalizer_rejects_cinematography_beat_mismatch() -> None:
    """摄影阶段的节拍集合必须与第一阶段锁定时间表完全一致。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_raw, cinematography_raw = _split_v2_wire_fixture(full_raw)
    story = normalize_story_strict_tool_arguments(
        story_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    cinematography_raw["beats"]["beat99"] = cinematography_raw["beats"].pop("beat05")

    with pytest.raises(
        ValueError,
        match="cinematography.beats 字段不完整.*缺少=beat05.*额外=beat99",
    ):
        normalize_split_strict_tool_arguments(
            story,
            cinematography_raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_split_normalizer_rejects_cinematography_extra_beat_field() -> None:
    """分阶段合并前必须拒绝额外摄影字段，不能被同名覆盖掩盖。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_raw, cinematography_raw = _split_v2_wire_fixture(full_raw)
    story = normalize_story_strict_tool_arguments(
        story_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    cinematography_raw["beats"]["beat01"]["compositionNote"] = "旁路构图说明"

    with pytest.raises(ValueError, match="额外=compositionNote"):
        normalize_split_strict_tool_arguments(
            story,
            cinematography_raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_split_normalizer_rejects_story_time_mismatch() -> None:
    """canonical 即使可反序列化，也不能换一份时间表继续进入摄影合并。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    full_raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    story_raw, cinematography_raw = _split_v2_wire_fixture(full_raw)
    story = normalize_story_strict_tool_arguments(
        story_raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )
    cinematography_raw["beats"].pop("beat05")

    with pytest.raises(ValueError, match="节拍数量与当前锁定时间表不一致"):
        normalize_split_strict_tool_arguments(
            story,
            cinematography_raw,
            setting_snapshot=snapshot,
            beat_ranges=[(0, 4), (4, 8), (8, 12), (12, 15)],
        )


def test_normalize_rejects_camera_spec_composition_note_side_channel() -> None:
    """构图说明不能绕过固定 composition 对象进入旁路字段。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat02"]["cameraSpec"]["composition_note"] = "强调潮湿前景层次"

    with pytest.raises(ValueError, match="额外=composition_note"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


@pytest.mark.parametrize("invalid_value", ["beat99", "", "101", "10x01"])
def test_normalize_rejects_invalid_width_or_character_beat_usage(
    invalid_value: str,
) -> None:
    """位图必须与当前节拍数量等宽并且只能包含 0/1。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["assets"]["asset01"]["usedInBeats"] = invalid_value

    with pytest.raises(ValueError, match="等宽的 0/1 位图"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_normalize_rejects_all_zero_beat_usage() -> None:
    """素材必须至少被一个节拍引用，不能用全零位图伪装空集合。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["assets"]["asset01"]["usedInBeats"] = "0" * len(ranges)

    with pytest.raises(ValueError, match="不能是全零位图"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_normalize_maps_beat_usage_bitmap_from_left_to_right() -> None:
    """位图第 N 位必须只映射 beatN，不能颠倒或压缩中间的零位。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["assets"]["asset01"]["usedInBeats"] = "10100"

    result = normalize_strict_tool_arguments(
        raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    assert ["asset01" in beat.referencedAssetIds for beat in result.beats] == [
        True,
        False,
        True,
        False,
        False,
    ]


def test_normalize_rejects_more_than_eleven_model_assets() -> None:
    """数组没有 wire 长度关键词，但本地必须稳定拒绝第十二项素材。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    template = raw["assets"]["asset01"]
    raw["assets"]["additionalAssets"] = [template for _index in range(11)]

    with pytest.raises(ValueError, match="VIDEO_PLAN_ASSET_LIMIT_EXCEEDED.*不能超过11项"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_normalize_rejects_more_than_eighteen_negative_constraints() -> None:
    """数组没有 wire 长度关键词，但本地必须稳定拒绝第十九项负约束。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(15)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["negativeConstraints"]["additionalConstraints"] = [f"约束{index}" for index in range(2, 20)]

    with pytest.raises(
        ValueError,
        match="VIDEO_PLAN_NEGATIVE_CONSTRAINT_LIMIT_EXCEEDED.*不能超过18项",
    ):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_normalize_rejects_setting_id_outside_frozen_snapshot() -> None:
    """归一化仍以传入的同一冻结快照校验动态 enum，不能接受悬空 ID。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["assets"]["asset01"]["settingId"] = "character-missing"

    with pytest.raises(ValueError, match="设定引用不存在"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


@pytest.mark.parametrize(
    ("asset_key", "updates", "message"),
    [
        ("asset01", {"modality": "audio"}, "modality"),
        (
            "asset01",
            {"settingId": "item-memory-compass"},
            "必须绑定 character 类型设定",
        ),
        ("asset01", {"targetEntity": "沈青"}, "targetEntity 必须是 __CANON__"),
        (
            "asset01",
            {"keyframeRole": "initial_state"},
            "keyframeRole 必须是 not_applicable",
        ),
        (
            "asset02",
            {"settingId": "item-memory-compass"},
            "settingId 必须是 __NONE__",
        ),
        ("asset02", {"targetEntity": "__CANON__"}, "真实 targetEntity"),
        (
            "asset02",
            {"keyframeRole": "not_applicable"},
            "必须声明具体 keyframeRole",
        ),
    ],
)
def test_normalize_rejects_invalid_unified_asset_combinations(
    asset_key: str,
    updates: dict[str, str],
    message: str,
) -> None:
    """统一素材 schema 放宽的跨字段组合必须全部在本地收紧。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    asset = (
        raw["assets"]["asset01"] if asset_key == "asset01" else raw["assets"]["additionalAssets"][0]
    )
    asset.update(updates)

    with pytest.raises(ValueError, match=message):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_normalize_accepts_string_sentinel_for_optional_action_and_transition() -> None:
    """可选动作与转场直接使用字符串哨兵，不再要求模型拼空对象。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat01"]["secondaryAction"] = "__UNUSED__"

    result = normalize_strict_tool_arguments(
        raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    assert len(result.beats[0].actionUnits) == 1
    assert result.beats[-1].transition is None


def test_normalize_rejects_locked_off_camera_with_translation() -> None:
    """锁定机位不能携带任何摄影机位移，避免文字与数值事实互相冲突。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat01"]["cameraSpec"]["movement"]["travelDistanceMeters"] = 0.5

    with pytest.raises(ValueError, match="locked_off 机位不能同时声明位移或旋转"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_normalize_rejects_prime_lens_with_zoom_movement() -> None:
    """定焦镜头不能通过修改结束焦距伪装成光学变焦。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    camera = raw["beats"]["beat01"]["cameraSpec"]
    camera["endFocalLengthMm"] = 70
    camera["movement"].update(
        {
            "movementType": "zoom_in",
            "speed": "slow",
            "easing": "ease_in_out",
        }
    )

    with pytest.raises(ValueError, match="定焦或微距定焦镜头不能声明焦距变化或 zoom 运镜"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_scene_v12_rejects_rack_focus_longer_than_beat() -> None:
    """wire 中合法的拉焦数值仍必须在 Scene 1.2 按实际拍长收紧。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    focus = raw["beats"]["beat01"]["cameraSpec"]["focus"]
    focus.update(
        {
            "startTarget": "林岚手中的铜扣",
            "endTarget": "匣内罗盘",
            "transition": "rack_focus",
            "rackDurationSeconds": 5,
        }
    )

    with pytest.raises(ValidationError, match="拉焦时长不能超过镜头时长"):
        _scene_v12_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)


def test_normalize_locked_focus_derives_non_authoritative_end_fields() -> None:
    """锁焦只保留起始焦点，忽略 strict 固定槽中的矛盾终点和拉焦时长。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    focus = raw["beats"]["beat01"]["cameraSpec"]["focus"]
    focus.update(
        {
            "startTarget": "林岚手中的铜扣",
            "endTarget": "远处灯塔",
            "transition": "locked",
            "rackDurationSeconds": 2.5,
        }
    )

    result = normalize_strict_tool_arguments(
        raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    normalized = result.beats[0].cameraSpec.focus
    assert normalized.startTarget == "林岚手中的铜扣"
    assert normalized.endTarget == normalized.startTarget
    assert normalized.transition == "locked"
    assert normalized.rackDurationSeconds == 0


def test_normalize_inherit_lighting_copies_previous_authoritative_facts() -> None:
    """旧版完整 inherit 即使携带矛盾值，也只读取上一拍权威事实。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat02"]["lightingCue"] = _lighting_cue_fixture(establish=False)
    inherited_wire = raw["beats"]["beat02"]["lightingCue"]
    inherited_wire["motivatedChange"] = ""
    inherited_wire["keyLight"]["colorTemperatureK"] = 5_600
    inherited_wire["fillStrategy"] = "none"
    inherited_wire["fillRelativeStops"] = -2

    result = normalize_strict_tool_arguments(
        raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    established = result.beats[0].lightingCue
    inherited = result.beats[1].lightingCue
    assert inherited.continuityMode == "inherit"
    assert inherited.motivatedChange == "延续上一拍全部灯光事实"
    assert inherited.model_dump(exclude={"continuityMode", "motivatedChange"}) == (
        established.model_dump(exclude={"continuityMode", "motivatedChange"})
    )
    _scene_v12_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)


def test_normalize_compact_inherit_lighting_copies_previous_facts() -> None:
    """紧凑 inherit 不让模型复述灯光，服务器仍生成完整连续事实。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)

    result = normalize_strict_tool_arguments(
        raw,
        setting_snapshot=snapshot,
        beat_ranges=ranges,
    )

    previous = result.beats[0].lightingCue
    for beat in result.beats[1:]:
        current = beat.lightingCue
        assert current.continuityMode == "inherit"
        assert current.motivatedChange == "延续上一拍全部灯光事实"
        assert current.model_dump(exclude={"continuityMode", "motivatedChange"}) == (
            previous.model_dump(exclude={"continuityMode", "motivatedChange"})
        )
        previous = current


def test_compact_inherit_keeps_four_beat_wire_below_size_budget() -> None:
    """四拍合法 wire 应稳定省掉三份非权威灯光对象。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4), (4, 8), (8, 12), (12, 15)]
    compact_wire = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    compact_size = len(
        json.dumps(compact_wire, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )

    legacy_wire = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    for index in range(2, 5):
        legacy_wire["beats"][f"beat{index:02d}"]["lightingCue"] = _lighting_cue_fixture(
            establish=False
        )
    legacy_size = len(
        json.dumps(legacy_wire, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )

    # 1.3 新增逐拍戏剧、表演、调度、摄影动机与轴线字段后，固定 wire 略有增长。
    assert compact_size < 10_000
    assert legacy_size - compact_size >= 2_000


def test_normalize_rejects_first_beat_inherit_without_previous_lighting() -> None:
    """首拍没有可继承来源，不能借服务器复制绕过 establish 门禁。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat01"]["lightingCue"]["continuityMode"] = "inherit"
    raw["beats"]["beat01"]["lightingCue"]["motivatedChange"] = ""

    with pytest.raises(ValueError, match="使用 inherit 时必须存在上一拍灯光"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_normalize_rejects_first_beat_compact_inherit() -> None:
    """首拍不能提交紧凑继承哨兵，必须完整建立灯光。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat01"]["lightingCue"] = "__INHERIT__"

    with pytest.raises(ValueError, match="使用 inherit 时必须存在上一拍灯光"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


@pytest.mark.parametrize(
    ("beat_key", "continuity_mode", "message"),
    [
        ("beat01", "motivated_change", "首拍必须使用 establish"),
        ("beat02", "establish", "只有首拍可以使用 establish"),
    ],
)
def test_normalize_rejects_authoritative_lighting_in_wrong_position(
    beat_key: str,
    continuity_mode: str,
    message: str,
) -> None:
    """绕过 strict schema 时也不能颠倒建立灯光与变化灯光的位置。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    cue = _lighting_cue_fixture(establish=continuity_mode == "establish")
    cue["continuityMode"] = continuity_mode
    raw["beats"][beat_key]["lightingCue"] = cue

    with pytest.raises(ValueError, match=message):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


@pytest.mark.parametrize(
    ("beat_key", "continuity_mode"),
    [("beat01", "establish"), ("beat02", "motivated_change")],
)
def test_normalize_keeps_authoritative_lighting_motivation_required(
    beat_key: str,
    continuity_mode: str,
) -> None:
    """服务器只允许 inherit 留空，建立或改变灯光仍必须声明可见动机。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    if beat_key != "beat01":
        raw["beats"][beat_key]["lightingCue"] = _lighting_cue_fixture(establish=False)
    cue = raw["beats"][beat_key]["lightingCue"]
    cue["continuityMode"] = continuity_mode
    cue["motivatedChange"] = ""

    with pytest.raises(ValueError, match="必须是 1 至 160 字"):
        normalize_strict_tool_arguments(
            raw,
            setting_snapshot=snapshot,
            beat_ranges=ranges,
        )


def test_scene_v12_accepts_motivated_lighting_change() -> None:
    """画面内事件解释色温变化时，Scene 1.2 应接受 motivated_change。"""

    snapshot = _setting_snapshot()
    ranges = _balanced_ranges(5)
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat02"]["lightingCue"] = _lighting_cue_fixture(establish=False)
    cue = raw["beats"]["beat02"]["lightingCue"]
    cue["continuityMode"] = "motivated_change"
    cue["motivatedChange"] = "破墙外的第七灯塔第一次点亮"
    cue["keyLight"]["colorTemperatureK"] = 5_600

    scene = _scene_v12_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)

    assert scene.beats[1].lightingCue is not None
    assert scene.beats[1].lightingCue.continuityMode == "motivated_change"
    assert scene.beats[1].lightingCue.keyLight.colorTemperatureK == 5_600


@pytest.mark.parametrize("schema_version", ["1.0", "1.1", "1.2"])
def test_scene_versions_before_v13_read_without_director_language(
    schema_version: str,
) -> None:
    """历史版本没有戏剧弧、白平衡和逐拍导演语言时仍可读取。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    payload = _scene_v12_from_wire(
        raw=_valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges),
        snapshot=snapshot,
        beat_ranges=ranges,
    ).model_dump(mode="json")
    payload["schemaVersion"] = schema_version
    payload.pop("dramaticArc")
    payload["lightingSetup"].pop("cameraWhiteBalanceK")
    for beat in payload["beats"]:
        for field_name in (
            "dramaticPurpose",
            "performanceDirection",
            "blocking",
            "cameraMotivation",
            "axisTransition",
        ):
            beat.pop(field_name)

    scene = ScenePromptSpec.model_validate(payload)

    assert scene.schemaVersion == schema_version
    assert scene.dramaticArc is None
    assert scene.lightingSetup is not None
    assert scene.lightingSetup.cameraWhiteBalanceK is None
    assert scene.beats[0].axisTransition is None


@pytest.mark.parametrize(
    ("missing_path", "message"),
    [
        ("dramaticArc", "dramaticArc"),
        ("cameraWhiteBalanceK", "cameraWhiteBalanceK"),
        ("dramaticPurpose", "dramaticPurpose"),
        ("performanceDirection", "performanceDirection"),
        ("blocking", "blocking"),
        ("cameraMotivation", "cameraMotivation"),
        ("axisTransition", "axisTransition"),
    ],
)
def test_scene_v13_requires_new_director_facts(
    missing_path: str,
    message: str,
) -> None:
    """1.3 不允许用可空兼容字段绕过新的导演语义契约。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    payload = _scene_v13_from_wire(
        raw=_valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges),
        snapshot=snapshot,
        beat_ranges=ranges,
    ).model_dump(mode="json")
    if missing_path == "dramaticArc":
        payload["dramaticArc"] = None
    elif missing_path == "cameraWhiteBalanceK":
        payload["lightingSetup"]["cameraWhiteBalanceK"] = None
    else:
        payload["beats"][0][missing_path] = None

    with pytest.raises(ValidationError, match=message):
        ScenePromptSpec.model_validate(payload)


def test_scene_v13_rejects_global_ban_on_referenced_character_performance() -> None:
    """人物素材已进入逐拍表演时，全局禁项不能再要求完全没有人物表演。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    payload = _scene_v13_from_wire(
        raw=_valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges),
        snapshot=snapshot,
        beat_ranges=ranges,
    ).model_dump(mode="json")
    payload["negativeConstraints"].append("无角色表演或对白内容")

    with pytest.raises(ValidationError, match="不能禁止镜头已明确要求的人物表演"):
        ScenePromptSpec.model_validate(payload)


def test_scene_v13_maintain_180_rejects_axis_marker_and_side_change() -> None:
    """维持 180 度规则时必须逐拍 hold 且始终处于同一人物轴线侧。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 3), (3, 5)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat02"]["axisTransition"] = "continuous_cross"

    with pytest.raises(ValidationError, match="maintain_180 只允许 hold"):
        _scene_v13_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)

    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["beats"]["beat02"]["cameraSpec"]["position"]["axisSide"] = "screen_right"
    with pytest.raises(ValidationError, match="必须保持同一轴线侧"):
        _scene_v13_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)


def test_scene_v13_not_applicable_axis_only_accepts_hold() -> None:
    """没有人物轴线时不能提交没有实际含义的越轴或重置标签。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 3), (3, 5)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["cinematographyBase"]["axisRule"] = "not_applicable"
    raw["beats"]["beat02"]["axisTransition"] = "cutaway_reset"

    with pytest.raises(ValidationError, match="not_applicable.*必须是 hold"):
        _scene_v13_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)


def test_scene_v13_intentional_cross_requires_declared_transition() -> None:
    """声明有意越轴不等于自动放行，左右换侧仍须给出可审核方法。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 3), (3, 5)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["cinematographyBase"]["axisRule"] = "intentional_cross"
    raw["beats"]["beat02"]["cameraSpec"]["position"]["axisSide"] = "screen_right"

    with pytest.raises(ValidationError, match="左右轴线侧变化必须使用"):
        _scene_v13_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)


def test_scene_v13_accepts_moving_continuous_cross() -> None:
    """连续且可见的摄影机运动可以承担一次有意越轴。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 3), (3, 5)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["cinematographyBase"]["axisRule"] = "intentional_cross"
    beat = raw["beats"]["beat02"]
    beat["axisTransition"] = "continuous_cross"
    beat["cameraSpec"]["position"]["axisSide"] = "screen_right"
    beat["cameraSpec"]["movement"].update(
        {
            "support": "dolly",
            "movementType": "truck_right",
            "travelDistanceMeters": 0.5,
            "speed": "medium",
            "easing": "ease_in_out",
        }
    )

    scene = _scene_v13_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)

    assert scene.beats[1].axisTransition == "continuous_cross"
    assert scene.beats[1].cameraSpec is not None
    assert scene.beats[1].cameraSpec.position.axisSide == "screen_right"


def test_scene_v13_rejects_locked_off_continuous_cross() -> None:
    """锁定机位不能只靠标签声称完成连续越轴。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 3), (3, 5)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["cinematographyBase"]["axisRule"] = "intentional_cross"
    beat = raw["beats"]["beat02"]
    beat["axisTransition"] = "continuous_cross"
    beat["cameraSpec"]["position"]["axisSide"] = "screen_right"

    with pytest.raises(ValidationError, match="主运镜不能是 locked_off"):
        _scene_v13_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)


def test_scene_v13_accepts_neutral_reset_before_side_change() -> None:
    """正轴中性镜头可以重建空间，再从另一侧继续主体覆盖。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 2), (2, 4), (4, 6)]
    raw = _valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges)
    raw["cinematographyBase"]["axisRule"] = "intentional_cross"
    raw["beats"]["beat02"]["axisTransition"] = "neutral_reset"
    raw["beats"]["beat02"]["cameraSpec"]["position"]["axisSide"] = "on_axis"
    raw["beats"]["beat03"]["cameraSpec"]["position"]["axisSide"] = "screen_right"

    scene = _scene_v13_from_wire(raw=raw, snapshot=snapshot, beat_ranges=ranges)

    assert scene.beats[1].axisTransition == "neutral_reset"
    assert scene.beats[2].cameraSpec is not None
    assert scene.beats[2].cameraSpec.position.axisSide == "screen_right"


@pytest.mark.parametrize("schema_version", ["1.0", "1.1"])
def test_legacy_scene_versions_remain_read_only_compatible(schema_version: str) -> None:
    """旧场景仍可解析查看，但不能冒充 1.2 进入专业摄影编译器。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    current = _scene_v12_from_wire(
        raw=_valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges),
        snapshot=snapshot,
        beat_ranges=ranges,
    ).model_dump(mode="json")
    current["schemaVersion"] = schema_version
    current.pop("cinematographyBase")
    current.pop("lightingSetup")
    for beat in current["beats"]:
        beat.pop("cameraSpec")
        beat.pop("lightingCue")

    legacy = ScenePromptSpec.model_validate(current)

    assert legacy.schemaVersion == schema_version
    assert legacy.cinematographyBase is None
    assert legacy.beats[0].cameraSpec is None
    with pytest.raises(PromptCompileError, match="旧版 1.0/1.1 场景需重新规划"):
        SeedancePromptCompiler().compile(legacy)


def test_provider_prompt_keeps_cinematic_facts_and_real_asset_aliases() -> None:
    """Provider 导演稿保留专业摄影事实与逐拍别名，但不泄漏旧素材 DSL。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    scene = _scene_v12_from_wire(
        raw=_valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges),
        snapshot=snapshot,
        beat_ranges=ranges,
    )

    package = SeedancePromptCompiler().compile(scene)
    prompt = package.providerPrompt

    assert prompt is not None
    assert package.compileProfile == "seedance_director_v3_compat"
    assert package.maxPromptCharacters == 2_000
    assert package.recommendedPromptCharacters == 500
    assert package.providerPromptCharacterCount == len(prompt)
    assert "@图片1" in prompt and "@图片2" in prompt
    assert "@图片1锁定沈青的身份" in prompt
    assert "40mm" in prompt
    assert "Super 35" in prompt
    assert "T2.8" in prompt
    assert "6500K" in prompt
    assert "暗侧比主光低2档" in prompt
    assert "@图片1=" not in prompt
    assert "职责=" not in prompt
    assert "·身份·" not in prompt
    assert "/" not in prompt
    assert package.warnings == [
        "Provider 提示词超过产品中文可读性预警线 500 字；这不是供应商硬限制"
    ]


def test_provider_prompt_warns_after_500_and_rejects_after_2000() -> None:
    """500 字是方舟质量建议，2000 字是新版产品异常包络。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    scene = _scene_v12_from_wire(
        raw=_valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges),
        snapshot=snapshot,
        beat_ranges=ranges,
    )
    warning_scene = scene.model_copy(
        update={"visualStyle": scene.visualStyle + "低饱和冷调与潮湿空气保持一致。" * 25}
    )

    warning_package = SeedancePromptCompiler().compile(warning_scene)

    assert 500 < warning_package.promptCharacterCount <= 2_000
    assert warning_package.warnings == [
        "Provider 提示词超过产品中文可读性预警线 500 字；这不是供应商硬限制"
    ]

    v13_scene = _scene_v13_from_wire(
        raw=_valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges),
        snapshot=snapshot,
        beat_ranges=ranges,
    )
    oversized_scene = v13_scene.model_copy(
        update={"visualStyle": "压迫逐级升级并在机关启动时转为不可逆后果。" * 800}
    )
    with pytest.raises(PromptCompileError, match="超出产品安全上限.*2000.*禁止静默截断"):
        SeedancePromptCompiler().compile(oversized_scene)


def test_video_job_validates_payload_before_entering_queue() -> None:
    """视频任务不能携带缺字段或越界时长的自由 JSON。"""

    payload = {
        "protocolVersion": "1.0",
        "jobId": "job-video-1",
        "kind": "video",
        "runId": "run-video-1",
        "taskId": "task-video-1",
        "novelId": "novel-1",
        "userId": "user-1",
        "priority": 10,
        "payload": {
            "projectId": "project-1",
            "sceneId": "scene-1",
            "chapterId": "chapter-1",
            "title": "厨房诀别",
            "sourceText": "她端起汤碗，又缓缓放下。",
            "durationSeconds": 15,
            "ratio": "16:9",
            "settingSnapshot": _setting_snapshot().model_dump(mode="json"),
        },
    }

    value = AgentJobRequest.model_validate(payload)
    assert value.kind == "video"

    payload["payload"]["durationSeconds"] = 16
    with pytest.raises(ValidationError):
        AgentJobRequest.model_validate(payload)


def test_video_job_revision_instruction_is_optional_for_legacy_payloads() -> None:
    """首次生成和历史任务没有返工意见时仍应按原契约解析。"""

    base_payload = {
        "projectId": "project-1",
        "sceneId": "scene-1",
        "chapterId": "chapter-1",
        "title": "厨房诀别",
        "sourceText": "她端起汤碗，又缓缓放下。",
        "durationSeconds": 15,
        "ratio": "16:9",
        "settingSnapshot": _setting_snapshot().model_dump(mode="json"),
    }

    missing = VideoPlanJobPayload.model_validate(base_payload)
    explicit_null = VideoPlanJobPayload.model_validate(
        {**base_payload, "revisionInstruction": None}
    )

    assert missing.revisionInstruction is None
    assert explicit_null.revisionInstruction is None
    dumped = missing.model_dump(mode="json")
    assert dumped["planningRoute"] == "legacy_strict_tool_v1"
    assert dumped["planningModel"] == "deepseek-v4-flash"
    assert dumped["directorDraftVersion"] == "1.0"


def test_video_job_freezes_supported_planning_routes() -> None:
    """任务载荷显式冻结规划路由，同时拒绝未知路由和草案版本。"""

    base_payload = {
        "projectId": "project-1",
        "sceneId": "scene-1",
        "chapterId": "chapter-1",
        "title": "厨房诀别",
        "sourceText": "她端起汤碗，又缓缓放下。",
        "durationSeconds": 15,
        "ratio": "16:9",
        "settingSnapshot": _setting_snapshot().model_dump(mode="json"),
    }
    for route in (
        "responses_json_schema_v1",
        "legacy_strict_tool_v1",
        "chat_json_output_v1",
    ):
        payload = VideoPlanJobPayload.model_validate(
            {
                **base_payload,
                "planningRoute": route,
                "planningModel": "deepseek-v4-flash",
                "directorDraftVersion": "1.0",
            }
        )
        assert payload.planningRoute == route
        assert payload.planningModel == "deepseek-v4-flash"

    current = VideoPlanJobPayload.model_validate(
        {
            **base_payload,
            "planningRoute": "responses_json_schema_v1",
            "planningModel": "deepseek-v4-flash",
            "directorDraftVersion": "1.1",
        }
    )
    assert current.directorDraftVersion == "1.1"

    with pytest.raises(ValidationError):
        VideoPlanJobPayload.model_validate({**base_payload, "planningRoute": "unknown"})
    with pytest.raises(ValidationError):
        VideoPlanJobPayload.model_validate({**base_payload, "directorDraftVersion": "2.0"})
    with pytest.raises(ValidationError):
        VideoPlanJobPayload.model_validate({**base_payload, "planningModel": "runtime-default"})


def test_video_plan_input_fingerprint_covers_route_and_frozen_source() -> None:
    """跨服务指纹必须覆盖传输协议和原文，防止队列载荷与任务事实漂移。"""

    base_payload = VideoPlanJobPayload(
        projectId="project-1",
        sceneId="scene-1",
        chapterId="chapter-1",
        title="厨房诀别",
        sourceText="她端起汤碗，又缓缓放下。",
        durationSeconds=15,
        ratio="16:9",
        settingSnapshot=_setting_snapshot(),
        planningRoute="responses_json_schema_v1",
        directorDraftVersion="1.1",
    )
    same_payload = VideoPlanJobPayload.model_validate_json(base_payload.model_dump_json())
    changed_route = base_payload.model_copy(update={"planningRoute": "legacy_strict_tool_v1"})
    changed_version = base_payload.model_copy(update={"directorDraftVersion": "1.0"})
    changed_source = base_payload.model_copy(update={"sourceText": "她没有端起汤碗。"})

    fingerprint = calculate_video_plan_input_fingerprint(base_payload)
    assert fingerprint == calculate_video_plan_input_fingerprint(same_payload)
    assert fingerprint != calculate_video_plan_input_fingerprint(changed_route)
    assert fingerprint != calculate_video_plan_input_fingerprint(changed_version)
    assert fingerprint != calculate_video_plan_input_fingerprint(changed_source)


def test_video_job_revision_instruction_requires_meaningful_bounded_text() -> None:
    """返工任务携带意见时拒绝空白和异常超长输入，并规范首尾空白。"""

    base_payload = {
        "projectId": "project-1",
        "sceneId": "scene-1",
        "chapterId": "chapter-1",
        "title": "厨房诀别",
        "sourceText": "她端起汤碗，又缓缓放下。",
        "durationSeconds": 15,
        "ratio": "16:9",
        "settingSnapshot": _setting_snapshot().model_dump(mode="json"),
    }

    revised = VideoPlanJobPayload.model_validate(
        {**base_payload, "revisionInstruction": "  强化人物停顿，减少无动机推镜。  "}
    )
    assert revised.revisionInstruction == "强化人物停顿，减少无动机推镜。"

    for invalid_instruction in (" \n\t ", "改" * 2_001):
        with pytest.raises(ValidationError):
            VideoPlanJobPayload.model_validate(
                {**base_payload, "revisionInstruction": invalid_instruction}
            )


def test_video_job_revision_baseline_is_frozen_and_bound_to_scene() -> None:
    """返工基线必须通过共享方案契约，并参与场景身份与输入指纹绑定。"""

    snapshot = _setting_snapshot()
    ranges = [(0, 4)]
    baseline = _scene_v13_from_wire(
        raw=_valid_v2_wire_fixture(snapshot=snapshot, beat_ranges=ranges),
        snapshot=snapshot,
        beat_ranges=ranges,
    )
    payload = VideoPlanJobPayload(
        projectId="project-1",
        sceneId=baseline.sceneId,
        chapterId="chapter-1",
        title=baseline.title,
        sourceText="她推开木门。",
        revisionInstruction="保持上一版摄影设计不变。",
        revisionBaseline=baseline,
        durationSeconds=4,
        ratio="16:9",
        settingSnapshot=snapshot,
        planningRoute="responses_json_schema_v1",
        directorDraftVersion="1.4",
    )
    without_baseline = payload.model_copy(update={"revisionBaseline": None})

    assert payload.revisionBaseline == baseline
    assert calculate_video_plan_input_fingerprint(
        payload
    ) != calculate_video_plan_input_fingerprint(without_baseline)

    invalid = payload.model_dump(mode="python")
    invalid["sceneId"] = "other-scene"
    with pytest.raises(ValidationError, match="revisionBaseline 与当前冻结场景"):
        VideoPlanJobPayload.model_validate(invalid)

    invalid = payload.model_dump(mode="python")
    invalid["revisionInstruction"] = None
    with pytest.raises(ValidationError, match="只有返工任务"):
        VideoPlanJobPayload.model_validate(invalid)


def test_setting_snapshot_rejects_content_drift_and_dangling_reference() -> None:
    """整体指纹和类型化引用共同阻止冻结输入被静默替换。"""

    snapshot = _setting_snapshot()
    changed = snapshot.model_dump(mode="json")
    changed["entries"][0]["name"] = "被篡改的人名"
    with pytest.raises(ValidationError, match="指纹与内容不一致"):
        LongSerialSettingSnapshot.model_validate(changed)

    with pytest.raises(ValidationError, match="canon_slot 素材必须引用冻结设定"):
        PlannedAsset(
            assetId="character.identity",
            modality="image",
            duty="identity",
            bindingScope="canon_slot",
            settingReference=None,
            targetEntity="沈青",
            includeFeatures=["脸型"],
            excludeFeatures=[],
        )


def test_video_job_rejects_oversized_pilot_source() -> None:
    """开发试制场景只接收 2000 字原文和最多 15 秒时长。"""

    with pytest.raises(ValidationError):
        AgentJobRequest.model_validate(
            {
                "protocolVersion": "1.0",
                "jobId": "job-video-long",
                "kind": "video",
                "runId": "run-video-long",
                "taskId": "task-video-long",
                "novelId": "novel-1",
                "userId": "user-1",
                "priority": 10,
                "payload": {
                    "projectId": "project-1",
                    "sceneId": "scene-1",
                    "chapterId": "chapter-1",
                    "title": "过长场景",
                    "sourceText": "长" * 2_001,
                    "durationSeconds": 15,
                    "ratio": "16:9",
                    "settingSnapshot": _setting_snapshot().model_dump(mode="json"),
                },
            }
        )


def _scene_assets_draft_fixture() -> SceneAssetsDraftV1:
    """构造只使用短设定别名和自然素材数组的合法草案。"""

    return SceneAssetsDraftV1(
        title="潮汐机关",
        summary="林岚在钟楼内触发潮汐机关。",
        dramaticArc="克制试探逐步升级为不可逆的机关启动。",
        visualStyle="低饱和写实冷调。",
        globalDirection="保持轴线和人物身份稳定。",
        assets=[
            SceneAssetDraftItemV1(
                sourceAlias="C02",
                duty="identity",
                targetEntity=None,
                includeFeatures=["清瘦脸型", "湿发"],
                excludeFeatures=["服装"],
            ),
            SceneAssetDraftItemV1(
                sourceAlias=None,
                duty="keyframe",
                targetEntity="机关动作开始前初态",
                includeFeatures=["手部与机关初始位置"],
                excludeFeatures=["动作完成状态"],
            ),
        ],
        negativeConstraints=["人物身份漂移", "现代物件"],
    )


def _story_draft_fixture(*, beat_count: int) -> StoryBeatsDraftV2:
    """构造完整引用两项素材的自然节拍数组。"""

    return StoryBeatsDraftV2(
        beats=[
            StoryBeatDraftItemV2(
                beatAlias=f"B{index:02d}",
                dramaticPurpose=f"推进第{index}拍的信息变化",
                performanceDirection=f"林岚以视线确认第{index}次机关响应",
                blocking=f"林岚位于画面左侧，机关在右侧完成第{index}次落点",
                primaryAction={
                    "subject": "林岚",
                    "action": f"完成动作{index}",
                    "visibleResult": f"形成结果{index}",
                },
                secondaryAction=None,
                actionComplexity="simple",
                sound=f"同步拟音{index}",
            )
            for index in range(1, beat_count + 1)
        ],
        assetUsageByAlias={
            alias: StoryAssetUsageDraftV2(
                primaryBeatAlias="B01",
                additionalBeatAliases=(
                    []
                    if alias == "A02"
                    else [f"B{index:02d}" for index in range(2, beat_count + 1)]
                ),
                anchorAssetAlias="A01" if alias == "A02" else None,
            )
            for alias in ("A01", "A02")
        },
    )


def _setting_snapshot() -> LongSerialSettingSnapshot:
    """构造覆盖五类长篇设定的合法冻结快照。"""

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
            CharacterSettingSnapshot(
                id="character-lin-lan",
                contentHash="c" * 64,
                name="林岚",
                aliases=[],
                appearance="短发，左眉浅疤",
                identity="潮汐钟楼守护者",
            ),
            RelationshipSettingSnapshot(
                id="relationship-allies",
                contentHash="d" * 64,
                name="守望同盟",
                sourceCharacterId="character-shen-qing",
                targetCharacterId="character-lin-lan",
                relationType="盟友",
                description="共同守护潮汐记忆",
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
                id="item-memory-compass",
                contentHash="e" * 64,
                name="潮汐记忆罗盘",
                aliases=["罗盘"],
                itemType="机关道具",
                ownerCharacterId="character-lin-lan",
                description="黄铜齿轮与黑水指针",
            ),
            WorldSettingSnapshot(
                id="world-visual-style",
                contentHash="f" * 64,
                name="潮汐世界视觉规范",
                content="冷灰雾海、氧化黄铜、低饱和写实光影",
            ),
        ]
    )


def _balanced_ranges(duration_seconds: int) -> list[tuple[int, int]]:
    """复制产品已冻结的二至五拍整数秒平衡规则。"""

    beat_count = min(5, max(2, ceil(duration_seconds / 3)))
    base_duration, longer_count = divmod(duration_seconds, beat_count)
    ranges: list[tuple[int, int]] = []
    start = 0
    for index in range(beat_count):
        end = start + base_duration + (1 if index < longer_count else 0)
        ranges.append((start, end))
        start = end
    return ranges


def _encoded_json_bytes(value: object) -> int:
    """按 Provider 实际使用的紧凑 JSON 口径计算 UTF-8 字节数。"""

    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _valid_v2_wire_fixture(
    *,
    snapshot: LongSerialSettingSnapshot,
    beat_ranges: list[tuple[int, int]],
) -> dict[str, Any]:
    """构造包含 canon 身份与场次初态关键帧的最小 V2 wire 输出。"""

    del snapshot
    beat_keys = [f"beat{index:02d}" for index in range(1, len(beat_ranges) + 1)]
    usage = "1" * len(beat_keys)
    asset01: dict[str, Any] = {
        "duty": "identity",
        "modality": "image",
        "bindingScope": "canon_slot",
        "settingId": "character-shen-qing",
        "targetEntity": "__CANON__",
        "keyframeRole": "not_applicable",
        "include": _text_slots("feature", 12, ["清瘦脸型", "湿发"]),
        "exclude": _text_slots("feature", 12, ["服装"]),
        "usedInBeats": usage,
    }
    additional_assets: list[dict[str, Any]] = [
        {
            "duty": "keyframe",
            "modality": "image",
            "bindingScope": "scene_direct",
            "settingId": "__NONE__",
            "targetEntity": "机关动作开始前初态",
            "keyframeRole": "initial_state",
            "include": _text_slots("feature", 12, ["手部与机关初始位置"]),
            "exclude": _text_slots("feature", 12, ["动作完成状态"]),
            "usedInBeats": usage,
        }
    ]
    assets: dict[str, Any] = {
        "asset01": asset01,
        "additionalAssets": additional_assets,
    }

    beats: dict[str, Any] = {}
    for index, ((start, end), beat_key) in enumerate(
        zip(beat_ranges, beat_keys, strict=True),
        start=1,
    ):
        beat: dict[str, Any] = {
            "cameraSpec": _camera_spec_fixture(),
            "lightingCue": (_lighting_cue_fixture(establish=True) if index == 1 else "__INHERIT__"),
            "dramaticPurpose": f"推进第{index}拍的信息变化",
            "performanceDirection": f"林岚先屏息，再以视线确认第{index}次机关响应",
            "blocking": f"林岚位于画面左三分线，机关在右侧完成第{index}次落点",
            "cameraMotivation": (f"机关齿轮第{index}次停转触发摄影机响应，让观众确认动作结果"),
            "axisTransition": "hold",
            "primaryAction": {
                "subject": "林岚",
                "action": f"完成动作{index}",
                "visibleResult": f"形成结果{index}",
            },
            "actionComplexity": "simple",
            "shotProgression": {
                "startShotSize": "中景",
                "endShotSize": "中景",
                "changeMode": "continuous",
            },
            "sound": f"同步拟音{index}",
            "transition": "__UNUSED__" if index == len(beat_ranges) else "硬切",
        }
        if ceil((end - start) / 2) == 2:
            beat["secondaryAction"] = {
                "subject": "机关",
                "action": f"产生反应{index}",
                "visibleResult": f"部件停在位置{index}",
            }
        beats[beat_key] = beat

    return {
        "title": "潮汐机关",
        "summary": "林岚在钟楼内触发潮汐机关。",
        "dramaticArc": "克制试探逐步升级为不可逆的机关启动。",
        "visualStyle": "低饱和写实冷调。",
        "globalDirection": "保持轴线和人物身份稳定。",
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
            "ambientSource": "海侧裂窗进入的冷色月光",
            "ambientColorTemperatureK": 6_500,
            "cameraWhiteBalanceK": 4_300,
            "keyToFillStops": 2,
            "negativeFillSide": "camera_right",
            "atmosphere": "低密度海雾与潮湿空气保持稳定",
        },
        "assets": assets,
        "beats": beats,
        "negativeConstraints": {
            "constraint01": "人物身份漂移",
            "additionalConstraints": ["现代物件"],
        },
    }


def _split_v2_wire_fixture(
    full_raw: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """按两个 strict 工具的职责无损拆分合法完整 wire。"""

    story_beat_fields = (
        "dramaticPurpose",
        "performanceDirection",
        "blocking",
        "primaryAction",
        "secondaryAction",
        "actionComplexity",
        "sound",
    )
    cinematography_beat_fields = (
        "cameraSpec",
        "lightingCue",
        "cameraMotivation",
        "axisTransition",
        "shotProgression",
        "transition",
    )
    story_beats = {
        beat_key: {
            field_name: value
            for field_name, value in beat.items()
            if field_name in story_beat_fields
        }
        for beat_key, beat in full_raw["beats"].items()
    }
    cinematography_beats = {
        beat_key: {
            field_name: value
            for field_name, value in beat.items()
            if field_name in cinematography_beat_fields
        }
        for beat_key, beat in full_raw["beats"].items()
    }
    story_raw = {
        "title": full_raw["title"],
        "summary": full_raw["summary"],
        "dramaticArc": full_raw["dramaticArc"],
        "visualStyle": full_raw["visualStyle"],
        "globalDirection": full_raw["globalDirection"],
        "assets": full_raw["assets"],
        "beats": story_beats,
        "negativeConstraints": full_raw["negativeConstraints"],
    }
    cinematography_raw = {
        "cinematographyBase": full_raw["cinematographyBase"],
        "lightingSetup": full_raw["lightingSetup"],
        "beats": cinematography_beats,
    }
    return story_raw, cinematography_raw


def _compact_stage_wire_fixture(
    full_raw: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """把合法完整 wire 转成 V3 场景素材与故事节拍两个紧凑阶段。"""

    old_assets = [
        full_raw["assets"]["asset01"],
        *full_raw["assets"]["additionalAssets"],
    ]
    compact_assets: list[dict[str, Any]] = []
    for asset in old_assets:
        compact_assets.append(
            {
                key: value
                for key, value in asset.items()
                if key not in {"include", "exclude", "usedInBeats"}
            }
            | {
                "include": [value for value in asset["include"].values() if value != "__UNUSED__"],
                "exclude": [value for value in asset["exclude"].values() if value != "__UNUSED__"],
            }
        )
    scene_assets_raw = {
        "title": full_raw["title"],
        "summary": full_raw["summary"],
        "dramaticArc": full_raw["dramaticArc"],
        "visualStyle": full_raw["visualStyle"],
        "globalDirection": full_raw["globalDirection"],
        "assets": {
            "asset01": compact_assets[0],
            "additionalAssets": compact_assets[1:],
        },
        "negativeConstraints": [
            full_raw["negativeConstraints"]["constraint01"],
            *full_raw["negativeConstraints"]["additionalConstraints"],
        ],
    }

    story_beat_fields = (
        "dramaticPurpose",
        "performanceDirection",
        "blocking",
        "primaryAction",
        "secondaryAction",
        "actionComplexity",
        "sound",
    )
    story_beats_raw = {
        "beats": {
            beat_key: {
                **{
                    field_name: value
                    for field_name, value in beat.items()
                    if field_name in story_beat_fields
                },
                "assetUsage": "".join(asset["usedInBeats"][index] for asset in old_assets),
            }
            for index, (beat_key, beat) in enumerate(full_raw["beats"].items())
        }
    }
    return scene_assets_raw, story_beats_raw


def _camera_spec_fixture() -> dict[str, Any]:
    """构造无物理冲突的 40mm Super 35 锁定机位。"""

    return {
        "lensType": "prime",
        "focalLengthMm": 40,
        "endFocalLengthMm": 40,
        "tStop": 2.8,
        "position": {
            "heightCm": 110,
            "azimuthDegrees": -35,
            "elevationDegrees": -10,
            "rollDegrees": 0,
            "subjectDistanceMeters": 2,
            "axisSide": "screen_left",
        },
        "composition": {
            "rule": "rule_of_thirds",
            "subjectPlacement": "left_third",
            "subjectFramePercent": 55,
            "headroom": "standard",
            "foregroundLayer": "湿信纸边缘",
            "backgroundLayer": "失焦的钟楼齿轮与石墙",
        },
        "movement": {
            "support": "tripod",
            "movementType": "locked_off",
            "travelDistanceMeters": 0,
            "rotationDegrees": 0,
            "speed": "static",
            "easing": "none",
        },
        "focus": {
            "depthOfField": "shallow",
            "startTarget": "林岚手中的铜扣",
            "endTarget": "林岚手中的铜扣",
            "transition": "locked",
            "rackDurationSeconds": 0,
        },
    }


def _lighting_cue_fixture(*, establish: bool) -> dict[str, Any]:
    """构造首拍建立、后续逐字段继承的动机灯光。"""

    return {
        "continuityMode": "establish" if establish else "inherit",
        "motivatedChange": "建立海侧裂窗月光" if establish else "延续上一拍",
        "keyLight": {
            "role": "key",
            "motivatedBy": "海侧裂窗进入的月光",
            "direction": "back_left",
            "azimuthDegrees": -135,
            "elevationDegrees": 35,
            "quality": "hard",
            "delivery": "direct",
            "colorTemperatureK": 6_500,
            "relativeExposureStops": 0,
            "beamAngleDegrees": 25,
            "falloff": "fast",
            "spillControl": "以黑旗限制石墙上的杂散光",
            "visibleResult": "手背和黄铜匣边缘出现窄而清晰的高光",
        },
        "fillStrategy": "bounce_fill",
        "fillDirection": "front_right",
        "fillRelativeStops": -2,
        "edgeLight": "__UNUSED__",
        "atmosphere": "低密度海雾只在裂窗光束内可见",
        "visibleResult": "主体暗部保留纹理，背景快速衰减而不死黑",
    }


def _scene_v12_from_wire(
    *,
    raw: dict[str, Any],
    snapshot: LongSerialSettingSnapshot,
    beat_ranges: list[tuple[int, int]],
) -> ScenePromptSpec:
    """把 strict wire 的派生结果装配成用于场景级门禁的 1.2 规范。"""

    plan = normalize_strict_tool_arguments(
        raw,
        setting_snapshot=snapshot,
        beat_ranges=beat_ranges,
    )
    beats: list[dict[str, Any]] = []
    for beat in plan.beats:
        payload = beat.model_dump(mode="json")
        payload["shotSize"] = beat.shotProgression.startShotSize
        payload["action"] = render_action_units(beat.actionUnits)
        beats.append(payload)

    return ScenePromptSpec.model_validate(
        {
            "schemaVersion": "1.2",
            "sceneId": "scene-tidal-clocktower",
            "title": plan.title,
            "summary": plan.summary,
            "dramaticArc": plan.dramaticArc,
            "visualStyle": plan.visualStyle,
            "globalDirection": plan.globalDirection,
            "cinematographyBase": plan.cinematographyBase.model_dump(mode="json"),
            "lightingSetup": plan.lightingSetup.model_dump(mode="json"),
            "assets": [asset.model_dump(mode="json") for asset in plan.assets],
            "beats": beats,
            "negativeConstraints": plan.negativeConstraints,
            "output": {
                "durationSeconds": beat_ranges[-1][1],
                "ratio": "16:9",
            },
        }
    )


def _scene_v13_from_wire(
    *,
    raw: dict[str, Any],
    snapshot: LongSerialSettingSnapshot,
    beat_ranges: list[tuple[int, int]],
) -> ScenePromptSpec:
    """复用同一正式投影，并启用 1.3 导演语言与轴线门禁。"""

    payload = _scene_v12_from_wire(
        raw=raw,
        snapshot=snapshot,
        beat_ranges=beat_ranges,
    ).model_dump(mode="json")
    payload["schemaVersion"] = "1.3"
    return ScenePromptSpec.model_validate(payload)


def _text_slots(prefix: str, count: int, values: list[str]) -> dict[str, Any]:
    """按固定顺序填充文本与字符串哨兵。"""

    return {
        f"{prefix}{index:02d}": values[index - 1] if index <= len(values) else "__UNUSED__"
        for index in range(1, count + 1)
    }


def _collect_any_of_paths(
    schema: object,
    path: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    """收集 anyOf 所在路径，保证复杂分支只出现在两个允许位置。"""

    found: list[tuple[str, ...]] = []
    if isinstance(schema, dict):
        if isinstance(schema.get("anyOf"), list):
            found.append((*path, "anyOf"))
        for key, value in schema.items():
            found.extend(_collect_any_of_paths(value, (*path, key)))
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            found.extend(_collect_any_of_paths(value, (*path, str(index))))
    return found


def _assert_any_of_branches_have_explicit_type(schema: object) -> None:
    """DeepSeek 实际校验要求 anyOf 的每个分支显式声明类型。"""

    if isinstance(schema, dict):
        choices = schema.get("anyOf")
        if isinstance(choices, list):
            assert all(isinstance(choice, dict) and "type" in choice for choice in choices)
        for value in schema.values():
            _assert_any_of_branches_have_explicit_type(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_any_of_branches_have_explicit_type(value)


def _assert_object_types_have_non_empty_properties(schema: object) -> None:
    """供应商拒绝只写 type/object 与引用、却没有 properties 的包装节点。"""

    if isinstance(schema, dict):
        if schema.get("type") == "object":
            properties = schema.get("properties")
            assert isinstance(properties, dict) and properties
        for value in schema.values():
            _assert_object_types_have_non_empty_properties(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_object_types_have_non_empty_properties(value)


def _assert_strict_schema_keyword_allowlist(schema: object) -> None:
    """递归校验 schema 只使用 DeepSeek strict 官方支持的结构关键词。"""

    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "pattern",
        "enum",
        "anyOf",
        "$ref",
        "$def",
        "description",
    }

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        assert set(node) <= allowed
        properties = node.get("properties")
        if isinstance(properties, dict):
            for value in properties.values():
                visit(value)
        definitions = node.get("$def")
        if isinstance(definitions, dict):
            for value in definitions.values():
                visit(value)
        choices = node.get("anyOf")
        if isinstance(choices, list):
            for value in choices:
                visit(value)
        items = node.get("items")
        if isinstance(items, dict):
            visit(items)

    visit(schema)


def _collect_object_schemas(node: object) -> list[dict[str, object]]:
    """递归收集 schema 中包含 properties 的对象节点。"""

    found: list[dict[str, object]] = []
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            found.append(node)
        for value in node.values():
            found.extend(_collect_object_schemas(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_collect_object_schemas(value))
    return found
