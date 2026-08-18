from __future__ import annotations

from copy import deepcopy

import pytest
from inkforge_agents.video_prompt.compiler import (
    PromptCompileError,
    SeedancePromptCompiler,
    materialize_scene_assets,
)
from inkforge_agents.video_prompt.contracts import (
    AssetBinding,
    CameraActionUnit,
    CameraBeatSpec,
    ScenePromptSpec,
    SeedancePromptPackage,
)
from inkforge_agents.video_prompt.demo import build_demo_scene
from pydantic import ValidationError


def test_compiles_demo_scene_to_bounded_seedance_prompt_package() -> None:
    package = SeedancePromptCompiler().compile(build_demo_scene())

    assert package.sceneId == "demo-wunianzai-final-kitchen"
    assert package.promptCharacterCount == len(package.prompt)
    assert package.recommendedPromptCharacters == 500
    assert 500 < package.promptCharacterCount <= package.maxPromptCharacters
    assert package.maxPromptCharacters == 2_000
    assert package.compileProfile == "seedance_director_v3_compat"
    assert package.providerPrompt == package.prompt
    assert package.providerPromptCharacterCount == package.promptCharacterCount
    assert package.manifestPrompt is not None
    assert package.manifestPromptCharacterCount == len(package.manifestPrompt)
    assert package.manifestPromptCharacterCount > package.providerPromptCharacterCount
    assert package.warnings == [
        "Provider 提示词超过产品中文可读性预警线 500 字；这不是供应商硬限制"
    ]
    assert package.previewOnly is True
    assert package.assetReady is False
    assert package.submissionReady is False
    assert package.fixtureOnly is True
    assert [binding.alias for binding in package.assetBindings] == [
        "@图片1",
        "@图片2",
        "@图片3",
        "@视频1",
        "@音频1",
    ]
    assert "摄影与动机光基线：采用Super 35球面成像" in package.prompt
    assert "摄影机以全景、40mm球面定焦、T4和轴线左侧起幅" in package.prompt
    assert "摄影机以近景、35mm球面定焦、T2.8和轴线左侧起幅" in package.prompt
    assert "低调光" in package.prompt
    assert "6500K环境光，暗侧比主光低4档" in package.prompt
    assert "叙事推进：先让灶石松动，继而碗落入后方手中，最终让众人动作停住" in package.prompt
    assert "镜头1（0-5秒）：参考@图片2、@图片3" in package.prompt
    assert "镜头3（10-15秒）：参考@图片1、@图片3、@音频1" in package.prompt
    assert "低声说{住手}" in package.prompt
    assert "<铁锅撞石><汤落泥地>" in package.prompt
    assert package.prompt.count("不使用BGM") == 1
    assert "声音：只使用各镜头明确写出的声音，不使用BGM。" in package.prompt
    assert "同步拟音和对白" not in package.prompt
    assert "@图片1锁定郎君的身份" in package.prompt
    assert "@图片1=" not in package.prompt
    assert "·身份·" not in package.prompt
    assert "/" not in package.prompt
    assert "→" not in package.prompt
    assert "机位高" not in package.prompt
    assert "方位" not in package.prompt
    assert "俯仰" not in package.prompt
    assert "距主体" not in package.prompt
    assert "%" not in package.prompt
    assert "束角" not in package.prompt
    assert "衰减" not in package.prompt
    assert "溢光" not in package.prompt
    assert "职责=identity" in package.manifestPrompt
    assert "机位高85cm、方位-25度、俯仰-4度，距主体4.5m" in package.manifestPrompt
    assert "束角80度、缓慢衰减，门框限制溢光" in package.manifestPrompt
    assert package.output.model == "doubao-seedance-2-5-260628"
    assert package.output.resolution == "720p"


def test_v13_compiles_natural_director_language_without_losing_manifest_facts() -> None:
    """1.3 只把可见导演意图发给模型，工程遥测仍无损保留在 Manifest。"""

    package = SeedancePromptCompiler().compile(_build_v13_demo_scene())

    assert package.compileProfile == "seedance_director_v3"
    assert package.maxPromptCharacters == 2_000
    assert package.providerPrompt is not None
    assert package.manifestPrompt is not None
    assert "戏剧弧：压迫升级，秩序崩裂，郎君夺回行动主动权。" in package.providerPrompt
    assert "摄影机白平衡4300K" in package.providerPrompt
    assert "镜头任务是建立差役对饥民的压迫，并让灶石松动成为失控前兆" in package.providerPrompt
    assert "表演与调度：差役发力短促粗暴" in package.providerPrompt
    assert "摄影动机：木杆挑住锅沿后，压迫从威胁转成不可逆行动。" in package.providerPrompt
    assert "摄影机以全景、40mm球面定焦、T4和轴线左侧，保持本侧轴线起幅" in package.providerPrompt
    assert "落幅为全景引导线构图" in package.providerPrompt
    assert "焦点锁在差役、铁锅与土灶关系平面" in package.providerPrompt
    assert package.providerPrompt.count("@图片1锁定郎君的身份") == 1

    inherited = package.providerPrompt.split("镜头2（5-10秒）：", 1)[1].split(
        "镜头3（10-15秒）：", 1
    )[0]
    assert inherited.count("灯光沿用上一镜") == 1
    assert "6500K" not in inherited
    assert "负补光" not in inherited
    assert "束角" not in inherited

    for telemetry in ("机位高", "方位", "俯仰", "距主体", "%", "束角", "衰减", "溢光"):
        assert telemetry not in package.providerPrompt
    for old_dsl in ("槽位=", "职责=", "特征域=", "→"):
        assert old_dsl not in package.providerPrompt

    assert "戏剧弧：压迫升级，秩序崩裂，郎君夺回行动主动权" in package.manifestPrompt
    assert "镜头任务=建立差役对饥民的压迫，并让灶石松动成为失控前兆" in package.manifestPrompt
    assert "摄影机白平衡4300K" in package.manifestPrompt
    assert "机位高85cm、方位-25度、俯仰-4度，距主体4.5m" in package.manifestPrompt
    assert "位移0.6m" in package.manifestPrompt
    assert "束角80度、缓慢衰减，门框限制溢光" in package.manifestPrompt
    assert package.providerPromptCharacterCount <= 2_000
    assert package.manifestPromptCharacterCount is not None
    assert package.providerPromptCharacterCount is not None
    assert package.providerPromptCharacterCount < package.manifestPromptCharacterCount * 0.75


def test_v13_uses_explicit_compact_projection_when_full_director_text_exceeds_limit() -> None:
    """长自由导演说明转入 Manifest，每拍动作和执行事实不能被字符截断。"""

    payload = _build_v13_demo_scene().model_dump(mode="json")
    payload["globalDirection"] = "全场连续性完整说明：" + "人物位置与道具状态保持连续，" * 12
    for index, beat in enumerate(payload["beats"], start=1):
        beat["dramaticPurpose"] = (
            f"第{index}拍戏剧任务完整说明：" + "推进压力并改变行动主动权，" * 6
        )
        beat["performanceDirection"] = (
            f"第{index}拍表演完整说明：" + "呼吸、停顿、视线和身体反应逐层变化，" * 7
        )
        beat["blocking"] = f"第{index}拍调度完整说明：" + "人物与道具沿既定屏幕方向移动，" * 7
        beat["cameraMotivation"] = (
            f"第{index}拍摄影动机完整说明：" + "摄影机只响应画面中的可见动作触发，" * 6
        )
    scene = ScenePromptSpec.model_validate(payload)

    package = SeedancePromptCompiler().compile(scene)

    assert package.providerPrompt is not None
    assert package.manifestPrompt is not None
    assert package.providerPromptCharacterCount is not None
    assert package.providerPromptCharacterCount <= 2_000
    assert (
        "Provider 提示词采用紧凑导演投影；完整导演语义保留在 Manifest，未做字符截断"
        in package.warnings
    )
    assert "全片基线：" in package.providerPrompt
    assert "第1拍表演完整说明" in package.providerPrompt
    assert "第1拍表演完整说明" in package.manifestPrompt
    assert "全场连续性完整说明" not in package.providerPrompt
    assert "全场连续性完整说明" in package.manifestPrompt
    for index, beat in enumerate(scene.beats, start=1):
        assert f"镜头{index}（{beat.startSecond}-{beat.endSecond}秒）" in package.providerPrompt
        for action_unit in beat.actionUnits:
            assert action_unit.to_text() in package.providerPrompt
    for binding in package.assetBindings:
        assert binding.alias in package.providerPrompt


def test_v13_compact_projection_keeps_concise_visible_performance() -> None:
    """常规紧凑投影仍要把可见表演交给 Provider，不能只留在 Manifest。"""

    payload = _build_v13_demo_scene().model_dump(mode="json")
    payload["globalDirection"] = "人物位置与道具状态保持连续，" * 80
    scene = ScenePromptSpec.model_validate(payload)

    package = SeedancePromptCompiler(max_prompt_characters=1_200).compile(scene)

    assert package.providerPrompt is not None
    assert package.providerPromptCharacterCount is not None
    assert package.providerPromptCharacterCount <= 1_200
    assert (
        "Provider 提示词采用紧凑导演投影；完整导演语义保留在 Manifest，未做字符截断"
        in package.warnings
    )
    assert not any("冗长表演说明仅保留" in warning for warning in package.warnings)
    for beat in scene.beats:
        assert beat.performanceDirection is not None
        assert f"表演：{beat.performanceDirection.rstrip('。；; ')}" in package.providerPrompt


def test_v13_minimal_compact_projection_never_drops_performance() -> None:
    """最小投影只能压缩重复摄影措辞，动作、表演与声音必须继续交给 Provider。"""

    payload = _build_v13_demo_scene().model_dump(mode="json")
    payload["globalDirection"] = "人物位置与道具状态保持连续，" * 80
    for index, beat in enumerate(payload["beats"], start=1):
        beat["performanceDirection"] = f"第{index}拍" + "呼吸停顿视线身体反应逐层变化" * 8
    scene = ScenePromptSpec.model_validate(payload)

    package = SeedancePromptCompiler(max_prompt_characters=1_200).compile(scene)

    assert package.providerPrompt is not None
    assert package.manifestPrompt is not None
    assert package.providerPromptCharacterCount is not None
    assert package.providerPromptCharacterCount <= 1_200
    assert (
        "Provider 提示词采用最小导演投影；动作、表演与逐拍声音完整保留，未做字符截断"
        in package.warnings
    )
    for beat in scene.beats:
        assert beat.performanceDirection is not None
        assert f"表演：{beat.performanceDirection.rstrip('。；; ')}" in package.providerPrompt
        assert beat.performanceDirection in package.manifestPrompt


def test_v13_fails_instead_of_dropping_performance_when_minimum_projection_is_too_long() -> None:
    """即使表演很长也不能伪装成功；最小投影仍超限时必须稳定失败。"""

    payload = _build_v13_demo_scene().model_dump(mode="json")
    for index, beat in enumerate(payload["beats"], start=1):
        beat["performanceDirection"] = f"第{index}拍" + "呼吸停顿视线身体反应逐层变化" * 18
    scene = ScenePromptSpec.model_validate(payload)

    with pytest.raises(PromptCompileError, match="超出产品安全上限"):
        SeedancePromptCompiler(max_prompt_characters=700).compile(scene)


def test_compat_nine_asset_four_beat_scene_stays_below_hard_envelope() -> None:
    """等价于 dev 灯塔规模的兼容场景也必须自然压缩，不能依赖截断过关。"""

    scene = _build_compat_stress_scene()
    package = SeedancePromptCompiler().compile(scene)

    assert len(scene.assets) == 9
    assert len(scene.beats) == 4
    assert package.compileProfile == "seedance_director_v3_compat"
    assert package.providerPromptCharacterCount is not None
    assert package.manifestPromptCharacterCount is not None
    assert package.providerPromptCharacterCount <= 2_000
    assert package.providerPromptCharacterCount < package.manifestPromptCharacterCount * 0.6
    assert "只用于 Manifest 的冗长场景概述" not in package.prompt
    assert "潮湿旧呢料在冷风中形成细密褶皱" not in package.prompt
    assert "潮湿旧呢料在冷风中形成细密褶皱" in (package.manifestPrompt or "")
    assert package.prompt.count("现代物件、服饰和设施") == 1
    assert package.prompt.count("换脸或人物身份漂移") == 1
    assert "现代道具" not in package.prompt
    assert "五官漂移" not in package.prompt


def test_materializes_real_assets_without_changing_stable_slot_references() -> None:
    """真实素材 ID 与稳定槽位 ID 分离，预览边界独立决定提交资格。"""

    scene = build_demo_scene()
    original_references = [beat.referencedAssetIds for beat in scene.beats]
    selections = {
        asset.assetId: f"media-{index}" for index, asset in enumerate(scene.assets, start=1)
    }

    materialized = materialize_scene_assets(scene, selections)
    preview = SeedancePromptCompiler().compile(materialized, preview_only=True)
    formal = SeedancePromptCompiler().compile(materialized, preview_only=False)

    assert [beat.referencedAssetIds for beat in materialized.beats] == original_references
    assert [asset.assetId for asset in materialized.assets] == [
        asset.assetId for asset in scene.assets
    ]
    assert [asset.mediaAssetId for asset in materialized.assets] == list(selections.values())
    assert preview.assetReady is True
    assert preview.previewOnly is True
    assert preview.submissionReady is False
    assert formal.assetReady is True
    assert formal.previewOnly is False
    assert formal.submissionReady is True


def test_rejects_materialization_for_unknown_slot() -> None:
    """Core 不能把不属于当前方案的真实素材偷偷塞入编译包。"""

    with pytest.raises(PromptCompileError, match="未知槽位"):
        materialize_scene_assets(build_demo_scene(), {"missing-slot": "media-1"})


def test_rejects_non_contiguous_timeline() -> None:
    payload = build_demo_scene().model_dump(mode="json")
    payload["beats"][1]["startSecond"] = 6

    with pytest.raises(ValidationError, match="镜头时间轴必须从 0 秒开始并保持连续"):
        ScenePromptSpec.model_validate(payload)


def test_rejects_provider_compile_for_unused_asset_slot() -> None:
    """未进入任何镜头的素材会污染参考权重，不能发送给供应商。"""

    scene = build_demo_scene()
    unused = scene.assets[0].model_copy(update={"assetId": "unused-identity"})
    scene = scene.model_copy(update={"assets": [*scene.assets, unused]})

    with pytest.raises(PromptCompileError, match="未被任何镜头引用"):
        SeedancePromptCompiler().compile(scene)


def test_rejects_unknown_asset_reference() -> None:
    payload = build_demo_scene().model_dump(mode="json")
    payload["beats"][0]["referencedAssetIds"].append("missing-asset")

    with pytest.raises(ValidationError, match="镜头引用了未声明素材"):
        ScenePromptSpec.model_validate(payload)


def test_rejects_incompatible_asset_duty_and_modality() -> None:
    with pytest.raises(ValidationError, match="素材职责 camera 不支持 audio 模态"):
        AssetBinding(
            assetId="invalid-camera-audio",
            modality="audio",
            duty="camera",
            targetEntity="镜头运动",
            includeFeatures=["轨迹"],
            excludeFeatures=[],
        )


def test_rejects_oversized_prompt_without_truncating() -> None:
    scene = build_demo_scene().model_copy(update={"visualStyle": "很长的视觉风格" * 2_000})

    with pytest.raises(PromptCompileError, match="Provider.*安全上限.*禁止静默截断"):
        SeedancePromptCompiler().compile(scene)


def test_keeps_prompt_over_recommendation_and_returns_warning() -> None:
    """500 字是产品预警线；编译器保留完整提示词并明确给出警告。"""

    scene = build_demo_scene().model_copy(update={"summary": "完整场景信息" * 15})

    package = SeedancePromptCompiler().compile(scene)

    assert 500 < package.promptCharacterCount <= package.maxPromptCharacters
    assert package.warnings == [
        "Provider 提示词超过产品中文可读性预警线 500 字；这不是供应商硬限制"
    ]


def test_manifest_remains_independent_and_longer_than_provider_prompt() -> None:
    """Manifest 与 Provider 分层计数，不因 Provider 包络而被截断。"""

    package = SeedancePromptCompiler().compile(build_demo_scene())

    assert package.manifestPromptCharacterCount is not None
    assert package.manifestPromptCharacterCount > package.providerPromptCharacterCount
    assert package.providerPromptCharacterCount is not None
    assert package.providerPromptCharacterCount <= package.maxPromptCharacters
    assert package.providerPromptCharacterCount < package.manifestPromptCharacterCount * 0.75
    assert "职责=identity" in (package.manifestPrompt or "")


def test_legacy_scene_and_package_parse_without_silent_prompt_rewrite() -> None:
    """旧版单层事实可读，但不会被伪装成新的双层提示词。"""

    legacy_scenes: dict[str, ScenePromptSpec] = {}
    for schema_version in ("1.0", "1.1"):
        scene_payload = build_demo_scene().model_dump(mode="json")
        scene_payload["schemaVersion"] = schema_version
        scene_payload.pop("cinematographyBase")
        scene_payload.pop("lightingSetup")
        for beat in scene_payload["beats"]:
            beat.pop("cameraSpec")
            beat.pop("lightingCue")
        if schema_version == "1.0":
            for asset in scene_payload["assets"]:
                asset.pop("featureDomain")
                asset.pop("keyframeRole")
            for beat in scene_payload["beats"]:
                beat.pop("actionUnits")
                beat.pop("actionComplexity")
                beat.pop("shotProgression")

        legacy_scene = ScenePromptSpec.model_validate(scene_payload)
        legacy_scenes[schema_version] = legacy_scene
        assert legacy_scene.schemaVersion == schema_version
        assert legacy_scene.cinematographyBase is None
        assert legacy_scene.beats[0].cameraSpec is None
        with pytest.raises(PromptCompileError, match="旧版 1.0/1.1 场景需重新规划"):
            SeedancePromptCompiler().compile(legacy_scene)

    assert legacy_scenes["1.0"].beats[0].actionUnits == []
    assert legacy_scenes["1.1"].beats[0].actionUnits

    current = SeedancePromptCompiler().compile(build_demo_scene()).model_dump(mode="json")
    original_prompt = current["prompt"]
    for field in (
        "compileProfile",
        "providerPrompt",
        "providerPromptCharacterCount",
        "manifestPrompt",
        "manifestPromptCharacterCount",
    ):
        current.pop(field)
    current["maxPromptCharacters"] = 2_000
    for binding in current["assetBindings"]:
        binding.pop("featureDomain")
        binding.pop("keyframeRole")

    legacy_package = SeedancePromptPackage.model_validate(current)

    assert legacy_package.compileProfile == "legacy_single_prompt_v1"
    assert legacy_package.prompt == original_prompt
    assert legacy_package.providerPrompt is None
    assert legacy_package.manifestPrompt is None


def test_v11_rejects_action_density_above_duration_budget() -> None:
    """四秒镜头最多承载两个结构化可见动作。"""

    payload = _single_beat_scene_payload()
    third = CameraActionUnit(
        subject="差役",
        action="抬起木杆",
        visibleResult="木杆离开铁锅",
    ).model_dump(mode="json")
    payload["beats"][0]["actionUnits"].append(third)
    payload["beats"][0]["action"] += "；差役抬起木杆，木杆离开铁锅"

    with pytest.raises(ValidationError, match="动作数量超过 4 秒可执行上限"):
        ScenePromptSpec.model_validate(payload)


def test_v11_rejects_short_cross_scale_continuous_move() -> None:
    """短时大全景到特写必须切镜，不能伪装成缓慢连续推镜。"""

    payload = _single_beat_scene_payload()
    beat = payload["beats"][0]
    beat["shotSize"] = "大全景"
    beat["cameraMovement"] = "缓慢推近"
    beat["shotProgression"] = {
        "startShotSize": "大全景",
        "endShotSize": "特写",
        "changeMode": "continuous",
    }

    with pytest.raises(ValidationError, match="短镜头不能连续跨越三个以上景别尺度"):
        ScenePromptSpec.model_validate(payload)


def test_v11_impact_cut_compiles_with_explicit_cut_wording() -> None:
    """同样的尺度变化在冲击切镜时必须明确编译成“切至”。"""

    payload = _single_beat_scene_payload()
    beat = payload["beats"][0]
    beat["shotSize"] = "大全景"
    beat["cameraMovement"] = "撞击瞬间转换视点"
    beat["shotProgression"] = {
        "startShotSize": "大全景",
        "endShotSize": "特写",
        "changeMode": "impact_cut",
    }
    scene = ScenePromptSpec.model_validate(payload)

    package = SeedancePromptCompiler().compile(scene)

    assert "大全景冲击切至特写" in package.prompt


@pytest.mark.parametrize(
    ("raw_transition", "director_wording"),
    [
        ("cut", "切至"),
        ("match_cut", "匹配切至"),
        ("impact_cut", "冲击切至"),
        ("尾帧保持手压锅沿的构图", "尾帧保持手压锅沿的构图"),
    ],
)
def test_provider_translates_transition_enums_to_director_language(
    raw_transition: str,
    director_wording: str,
) -> None:
    """内部切镜枚举不能泄漏给供应商，自由导演说明则逐字保留。"""

    payload = _single_beat_scene_payload()
    payload["beats"][0]["transition"] = raw_transition
    package = SeedancePromptCompiler().compile(ScenePromptSpec.model_validate(payload))

    assert f"转场：{director_wording}" in package.prompt
    if "_" in raw_transition:
        assert raw_transition not in package.prompt


def test_v11_rejects_cross_domain_identity_slot() -> None:
    """人物身份素材不能声明服装特征域。"""

    payload = build_demo_scene().model_dump(mode="json")
    payload["assets"][0]["featureDomain"] = "character_costume"

    with pytest.raises(ValidationError, match="identity.*character_identity"):
        ScenePromptSpec.model_validate(payload)


def test_v11_requires_initial_keyframe_for_mechanical_sequence() -> None:
    """机关镜头必须引用场次直绑的图片初态关键帧。"""

    payload = _single_beat_scene_payload()
    payload["beats"][0]["actionComplexity"] = "mechanical_sequence"
    with pytest.raises(ValidationError, match="initial_state 关键帧"):
        ScenePromptSpec.model_validate(payload)

    payload["assets"].append(
        {
            "assetId": "mechanism-initial-state",
            "modality": "image",
            "duty": "keyframe",
            "bindingScope": "scene_direct",
            "settingReference": None,
            "featureDomain": "keyframe",
            "keyframeRole": "initial_state",
            "targetEntity": "铁锅、木杆和土灶初始相对位置",
            "includeFeatures": ["手部位置", "道具位置", "土灶布局"],
            "excludeFeatures": ["后续翻倒状态"],
            "mediaAssetId": None,
            "isFixture": True,
        }
    )
    payload["beats"][0]["referencedAssetIds"].append("mechanism-initial-state")

    scene = ScenePromptSpec.model_validate(payload)
    assert scene.beats[0].actionComplexity == "mechanical_sequence"
    package = SeedancePromptCompiler().compile(scene)
    natural_binding = "@图片3只锁定铁锅、木杆和土灶初始相对位置初态"
    shot_binding = "参考@图片1、@图片2、@图片3"
    assert natural_binding in package.prompt
    assert shot_binding in package.prompt
    assert package.prompt.count(natural_binding) == 1
    assert package.prompt.count("铁锅、木杆和土灶初始相对位置初态") == 1
    assert "·初态帧·全片:" not in package.prompt


def test_v11_does_not_require_repeated_initial_state_after_non_mechanical_beat() -> None:
    """全场只有最早机关起点需要初态，中间普通拍不能重置这条时间线。"""

    payload = build_demo_scene().model_dump(mode="json")
    payload["assets"].append(
        {
            "assetId": "mechanism-initial-state",
            "modality": "image",
            "duty": "keyframe",
            "bindingScope": "scene_direct",
            "settingReference": None,
            "featureDomain": "keyframe",
            "keyframeRole": "initial_state",
            "targetEntity": "首个机关动作发生前的唯一初态",
            "includeFeatures": ["首拍道具位置", "机关尚未启动"],
            "excludeFeatures": ["后续结果态"],
            "mediaAssetId": None,
            "isFixture": True,
        }
    )
    payload["beats"][0]["actionComplexity"] = "mechanical_sequence"
    payload["beats"][0]["referencedAssetIds"].append("mechanism-initial-state")
    payload["beats"][1]["actionComplexity"] = "simple"
    payload["beats"][2]["actionComplexity"] = "mechanical_sequence"

    scene = ScenePromptSpec.model_validate(payload)

    assert "mechanism-initial-state" in scene.beats[0].referencedAssetIds
    assert "mechanism-initial-state" not in scene.beats[2].referencedAssetIds


def test_v11_requires_sound_for_every_audio_generating_beat() -> None:
    """开启生成音频时不能留下没有声画设计的镜头。"""

    payload = _single_beat_scene_payload()
    payload["beats"][0]["sound"] = None

    with pytest.raises(ValidationError, match="每个镜头都必须声明同步声音"):
        ScenePromptSpec.model_validate(payload)


def test_rejects_invalid_beat_time_range() -> None:
    with pytest.raises(ValidationError, match="结束时间必须晚于开始时间"):
        CameraBeatSpec(
            beatId="bad-beat",
            startSecond=5,
            endSecond=5,
            shotSize="近景",
            cameraAngle="平视",
            cameraMovement="固定",
            action="人物停住",
        )


def _build_compat_stress_scene() -> ScenePromptSpec:
    """构造九素材、四拍、长视觉圣经的 1.2 兼容压力场景。"""

    payload = build_demo_scene().model_dump(mode="json")
    payload["summary"] = "只用于 Manifest 的冗长场景概述。" * 80

    original_beats = payload["beats"]
    beats = [
        deepcopy(original_beats[0]),
        deepcopy(original_beats[1]),
        deepcopy(original_beats[2]),
        deepcopy(original_beats[2]),
    ]
    ranges = ((0, 4), (4, 8), (8, 12), (12, 15))
    for index, (beat, (start, end)) in enumerate(zip(beats, ranges, strict=True), start=1):
        beat["beatId"] = f"stress-beat-{index}"
        beat["startSecond"] = start
        beat["endSecond"] = end

    # 四秒拍最多两个动作，尾拍只保留最终制止动作。
    beats[1]["actionUnits"] = beats[1]["actionUnits"][:2]
    beats[2]["actionUnits"] = beats[2]["actionUnits"][:2]
    beats[3]["actionUnits"] = [beats[3]["actionUnits"][-1]]
    for beat in beats:
        beat["action"] = "；".join(
            f"{unit['subject']}{unit['action']}，{unit['visibleResult']}"
            for unit in beat["actionUnits"]
        )
    beats[2]["transition"] = None
    beats[3]["lightingCue"] = deepcopy(beats[2]["lightingCue"])
    beats[3]["lightingCue"]["continuityMode"] = "inherit"
    beats[3]["lightingCue"]["motivatedChange"] = "延续上一镜全部灯光事实"
    payload["beats"] = beats
    payload["output"]["durationSeconds"] = 15

    long_features = [
        "潮湿旧呢料在冷风中形成细密褶皱并保持连续磨损纹理",
        "肩线与袖口在所有镜头中维持同一剪裁和污渍位置",
        "不得把灾荒年代服装改成现代工业化成衣",
    ]
    payload["assets"].extend(
        [
            {
                "assetId": "fixture-langjun-costume-v1",
                "modality": "image",
                "duty": "costume",
                "bindingScope": "canon_slot",
                "settingReference": {"kind": "character", "id": "langjun"},
                "featureDomain": "character_costume",
                "keyframeRole": None,
                "targetEntity": "郎君",
                "includeFeatures": long_features,
                "excludeFeatures": ["五官", "人物身份"],
                "mediaAssetId": None,
                "isFixture": True,
            },
            {
                "assetId": "fixture-disaster-style-v1",
                "modality": "image",
                "duty": "style",
                "bindingScope": "scene_direct",
                "settingReference": None,
                "featureDomain": "style",
                "keyframeRole": None,
                "targetEntity": "灾荒写实影调",
                "includeFeatures": long_features,
                "excludeFeatures": ["现代广告质感"],
                "mediaAssetId": None,
                "isFixture": True,
            },
            {
                "assetId": "fixture-yard-storyboard-v1",
                "modality": "image",
                "duty": "storyboard",
                "bindingScope": "scene_direct",
                "settingReference": None,
                "featureDomain": "storyboard",
                "keyframeRole": None,
                "targetEntity": "院落动作轴故事板",
                "includeFeatures": long_features,
                "excludeFeatures": ["人物身份", "服装细节"],
                "mediaAssetId": None,
                "isFixture": True,
            },
            {
                "assetId": "fixture-yard-ambience-v1",
                "modality": "audio",
                "duty": "ambience",
                "bindingScope": "scene_direct",
                "settingReference": None,
                "featureDomain": "ambience",
                "keyframeRole": None,
                "targetEntity": "院落寒风环境声",
                "includeFeatures": ["寒风穿过门洞", "远处人群压抑呼吸", "无旋律底噪"],
                "excludeFeatures": ["背景音乐", "现代交通声"],
                "mediaAssetId": None,
                "isFixture": True,
            },
        ]
    )
    beats[0]["referencedAssetIds"].extend(
        ["fixture-langjun-costume-v1", "fixture-disaster-style-v1"]
    )
    beats[1]["referencedAssetIds"].append("fixture-yard-storyboard-v1")
    beats[2]["referencedAssetIds"].append("fixture-yard-ambience-v1")
    payload["negativeConstraints"].extend(
        [
            "人物身份漂移",
            "五官漂移",
            "现代物件",
            "现代道具",
            "现代设施",
            "违背物理",
        ]
    )
    return ScenePromptSpec.model_validate(payload)


def _build_v13_demo_scene() -> ScenePromptSpec:
    """在既有摄影演示数据上补齐 1.3 的戏剧、调度与摄影动机事实。"""

    payload = build_demo_scene().model_dump(mode="json")
    payload["schemaVersion"] = "1.3"
    payload["dramaticArc"] = "压迫升级，秩序崩裂，郎君夺回行动主动权"
    payload["lightingSetup"]["cameraWhiteBalanceK"] = 4_300
    director_beats = [
        {
            "dramaticPurpose": "建立差役对饥民的压迫，并让灶石松动成为失控前兆",
            "performanceDirection": "差役发力短促粗暴，围观家人本能后缩",
            "blocking": "差役和铁锅占画面右侧，家人退在院墙方向",
            "cameraMotivation": "木杆挑住锅沿后，压迫从威胁转成不可逆行动",
            "axisTransition": "hold",
        },
        {
            "dramaticPurpose": "把翻锅造成的生存损失变成连续、不可挽回的动作链",
            "performanceDirection": "差役动作不迟疑，接碗的人慌乱却不越过铁锅轴线",
            "blocking": "铁锅留在前景右侧，空碗沿同一方向传入背景",
            "cameraMotivation": "热汤泼地后，观众需要从破坏动作转向被夺走的食物",
            "axisTransition": "hold",
        },
        {
            "dramaticPurpose": "让郎君用按住锅沿的动作夺回场面控制，并终止暴力",
            "performanceDirection": "郎君忍痛起身，声音低而坚定，差役在住手声后僵住",
            "blocking": "郎君从画面左侧泥地进入前景，手压锅沿形成新的视觉中心",
            "cameraMotivation": "郎君的手接触锅沿后，叙事重心从翻锅转到他的反抗",
            "axisTransition": "hold",
        },
    ]
    for beat, director_fields in zip(payload["beats"], director_beats, strict=True):
        beat.update(director_fields)
    return ScenePromptSpec.model_validate(payload)


def _single_beat_scene_payload() -> dict[str, object]:
    """把演示场景收敛为一个合法四秒镜头，供语义门禁测试复用。"""

    payload = build_demo_scene().model_dump(mode="json")
    first_beat = payload["beats"][0]
    first_beat["endSecond"] = 4
    payload["beats"] = [first_beat]
    referenced = set(first_beat["referencedAssetIds"])
    payload["assets"] = [asset for asset in payload["assets"] if asset["assetId"] in referenced]
    payload["output"]["durationSeconds"] = 4
    return payload
