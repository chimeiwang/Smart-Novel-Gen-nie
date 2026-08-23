"""Core 与 Agent 共用的视频提示词确定性编译器。"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping

from .video import (
    AssetBinding,
    CameraBeatSpec,
    CompiledAssetBinding,
    LightSourceSpec,
    ScenePromptSpec,
    SeedancePromptPackage,
    ShotCameraSpec,
)

RECOMMENDED_CHINESE_PROMPT_CHARACTERS = 500
DEFAULT_MAX_PROVIDER_PROMPT_CHARACTERS = 2_000
# 保留旧常量名，含义收敛为 Provider 文本的本地安全包络。
DEFAULT_MAX_CHINESE_PROMPT_CHARACTERS = DEFAULT_MAX_PROVIDER_PROMPT_CHARACTERS
_ALIAS_PREFIX = {"image": "图片", "video": "视频", "audio": "音频"}
_CUT_LABEL = {
    "cut": "切至",
    "match_cut": "匹配切至",
    "impact_cut": "冲击切至",
}
_CAPTURE_FORMAT_LABEL = {"super_35": "Super 35", "full_frame": "全画幅"}
_LENS_PROJECTION_LABEL = {"spherical": "球面", "anamorphic": "变形宽银幕"}
_LENS_TYPE_LABEL = {"prime": "定焦", "zoom": "变焦", "macro_prime": "微距定焦"}
_AXIS_RULE_LABEL = {
    "maintain_180": "遵守180度轴线",
    "intentional_cross": "仅在明确切点有意越轴",
    "not_applicable": "无人物轴线",
}
_SCREEN_DIRECTION_LABEL = {
    "left_to_right": "主体运动方向保持由左向右",
    "right_to_left": "主体运动方向保持由右向左",
    "neutral": "主体运动方向中性",
}
_AXIS_SIDE_LABEL = {
    "screen_left": "轴线左侧",
    "screen_right": "轴线右侧",
    "on_axis": "轴线上",
}
_AXIS_TRANSITION_LABEL = {
    "hold": "保持本侧轴线",
    "continuous_cross": "连续运动中可见越轴",
    "neutral_reset": "经中性正轴镜头重置轴线",
    "cutaway_reset": "经切出镜头重置轴线",
}
_COMPOSITION_LABEL = {
    "centered": "中心构图",
    "rule_of_thirds": "三分法构图",
    "symmetrical": "对称构图",
    "leading_lines": "引导线构图",
    "frame_within_frame": "框中框构图",
    "negative_space": "负空间构图",
}
_PLACEMENT_LABEL = {
    "left_third": "左三分之一",
    "center": "画面中心",
    "right_third": "右三分之一",
    "lower_center": "画面下部中心",
    "upper_center": "画面上部中心",
}
_HEADROOM_LABEL = {
    "tight": "紧头顶空间",
    "standard": "标准头顶空间",
    "generous": "宽头顶空间",
    "not_applicable": "不适用头顶空间",
}
_SUPPORT_LABEL = {
    "tripod": "三脚架",
    "slider": "滑轨",
    "dolly": "轨道车",
    "gimbal": "手持稳定器",
    "steadicam": "斯坦尼康",
    "handheld": "手持",
    "shoulder": "肩扛",
    "jib": "小摇臂",
    "crane": "摄影升降机",
}
_MOVEMENT_LABEL = {
    "locked_off": "锁定机位",
    "dolly_in": "向主体推进",
    "dolly_out": "从主体后退",
    "truck_left": "向左横移",
    "truck_right": "向右横移",
    "pan_left": "向左摇摄",
    "pan_right": "向右摇摄",
    "tilt_up": "向上俯仰",
    "tilt_down": "向下俯仰",
    "pedestal_up": "机位垂直升高",
    "pedestal_down": "机位垂直降低",
    "arc_left": "向左环绕",
    "arc_right": "向右环绕",
    "boom_up": "摇臂上升",
    "boom_down": "摇臂下降",
    "zoom_in": "光学变焦推近",
    "zoom_out": "光学变焦拉远",
    "handheld_follow": "手持跟随",
}
_SPEED_LABEL = {
    "static": "静止",
    "very_slow": "极慢",
    "slow": "缓慢",
    "medium": "中速",
    "fast": "快速",
}
_EASING_LABEL = {
    "none": "匀速",
    "ease_in": "缓入",
    "ease_out": "缓出",
    "ease_in_out": "缓入缓出",
}
_DOF_LABEL = {"shallow": "浅景深", "medium": "中等景深", "deep": "深景深"}
_EXPOSURE_LABEL = {"low_key": "低调光", "balanced": "均衡曝光", "high_key": "高调光"}
_NEGATIVE_FILL_LABEL = {
    "none": "不使用负补光",
    "camera_left": "机位左侧负补光",
    "camera_right": "机位右侧负补光",
    "both": "机位两侧负补光",
}
_LIGHT_DIRECTION_LABEL = {
    "front": "正面",
    "front_left": "左前方",
    "front_right": "右前方",
    "side_left": "左侧",
    "side_right": "右侧",
    "back_left": "左后方",
    "back_right": "右后方",
    "back": "正后方",
    "top": "正上方",
    "bottom": "下方",
}
_LIGHT_QUALITY_LABEL = {"hard": "硬质", "soft": "柔和"}
_LIGHT_DELIVERY_LABEL = {"direct": "直射", "diffused": "柔化直射", "bounced": "反射"}
_LIGHT_FALLOFF_LABEL = {"fast": "快速衰减", "medium": "中等衰减", "slow": "缓慢衰减"}
_FILL_STRATEGY_LABEL = {
    "none": "无补光",
    "soft_fill": "柔和补光",
    "bounce_fill": "反射补光",
    "negative_fill": "负补光",
}
_DUTY_LABEL = {
    "identity": "身份",
    "costume": "服装",
    "scene": "场景",
    "prop": "道具",
    "style": "视觉风格",
    "storyboard": "故事板",
    "keyframe": "关键帧",
    "motion": "动作",
    "camera": "运镜",
    "voice": "音色",
    "ambience": "环境声",
    "music": "音乐",
    "relation_interaction": "关系",
}
_KEYFRAME_ROLE_LABEL = {
    "initial_state": "初态帧",
    "end_state": "尾帧",
    "transition_anchor": "转场帧",
}
_NO_BGM_MARKERS = ("bgm", "背景音乐", "配乐", "随机音乐")
_UNREADABLE_SYMBOL_PROVIDER_CONSTRAINT = "银色符纹不可读，禁文字/字母/数字/可解码符号"
_UNREADABLE_TEXT_MARKERS = (
    "不可读",
    "不可辨识",
    "可解码",
    "符纹",
    "字母",
    "数字",
)
_MODERN_OBJECT_MARKERS = ("现代物件", "现代物品", "现代道具", "现代服饰", "现代设施")
_MODERN_OBJECT_PROVIDER_CONSTRAINT = "现代物件、服饰和设施"
_IDENTITY_PROVIDER_CONSTRAINT = "换脸或人物身份漂移"
_CHARACTER_COUNT_PROVIDER_CONSTRAINT = "增减人物"
_PROP_DEFORMATION_PROVIDER_CONSTRAINT = "道具变形"
_PHYSICS_PROVIDER_CONSTRAINT = "逆重力或违背物理"
_COMPACT_PROVIDER_WARNING = (
    "Provider 提示词采用紧凑导演投影；完整导演语义保留在 Manifest，未做字符截断"
)
_MINIMAL_COMPACT_PROVIDER_WARNING = (
    "Provider 提示词采用最小导演投影；动作、表演与逐拍声音完整保留，未做字符截断"
)


class PromptCompileError(ValueError):
    """表示结构正确、但无法安全编译为供应商提示词。"""


def materialize_scene_assets(
    scene: ScenePromptSpec,
    selections: Mapping[str, str],
) -> ScenePromptSpec:
    """按稳定槽位 ID 装配真实素材，同时保留镜头对槽位的引用。"""

    known_slot_ids = {asset.assetId for asset in scene.assets}
    unknown_slot_ids = set(selections) - known_slot_ids
    if unknown_slot_ids:
        names = "、".join(sorted(unknown_slot_ids))
        raise PromptCompileError(f"素材选择引用了未知槽位：{names}")
    for slot_id, media_asset_id in selections.items():
        if not slot_id.strip() or not media_asset_id.strip():
            raise PromptCompileError("槽位 ID 与真实素材 ID 均不能为空")

    assets = []
    for asset in scene.assets:
        selected_media_asset_id = selections.get(asset.assetId)
        if selected_media_asset_id is None:
            assets.append(asset)
            continue
        assets.append(
            asset.model_copy(
                update={
                    "mediaAssetId": selected_media_asset_id,
                    "isFixture": False,
                }
            )
        )
    return scene.model_copy(update={"assets": assets})


class SeedancePromptCompiler:
    """从同一场景规范生成完整清单与紧凑 Provider 提示词。"""

    def __init__(
        self,
        max_prompt_characters: int = DEFAULT_MAX_PROVIDER_PROMPT_CHARACTERS,
    ) -> None:
        if max_prompt_characters <= 0 or max_prompt_characters > 6_000:
            raise ValueError("Provider 提示词长度上限必须位于 1 到 6000")
        self._max_prompt_characters = max_prompt_characters

    def compile(
        self,
        scene: ScenePromptSpec,
        *,
        preview_only: bool = True,
    ) -> SeedancePromptPackage:
        """编译双层提示词；任何一层都不做字符截断。"""

        if scene.schemaVersion not in {"1.2", "1.3"}:
            raise PromptCompileError("旧版 1.0/1.1 场景需重新规划后才能使用专业摄影编译器")

        used_asset_ids = {asset_id for beat in scene.beats for asset_id in beat.referencedAssetIds}
        unused_asset_ids = [
            asset.assetId for asset in scene.assets if asset.assetId not in used_asset_ids
        ]
        if unused_asset_ids:
            names = "、".join(unused_asset_ids)
            raise PromptCompileError(f"素材槽位未被任何镜头引用：{names}")

        aliases = self._assign_aliases(scene.assets)
        no_bgm = not any(asset.duty == "music" for asset in scene.assets)
        manifest_prompt = self._compile_manifest_prompt(scene, aliases, no_bgm=no_bgm)
        provider_prompt = self._compile_provider_prompt(scene, aliases, no_bgm=no_bgm)
        compact_projection = False
        minimal_compact_projection = False
        if (
            scene.schemaVersion == "1.3"
            and len(provider_prompt) > self._max_prompt_characters
        ):
            provider_prompt = self._compile_provider_prompt(
                scene,
                aliases,
                no_bgm=no_bgm,
                compact=True,
            )
            compact_projection = True
            if len(provider_prompt) > self._max_prompt_characters:
                provider_prompt = self._compile_provider_prompt(
                    scene,
                    aliases,
                    no_bgm=no_bgm,
                    compact=True,
                    minimal_compact=True,
                )
                minimal_compact_projection = True
        provider_length = len(provider_prompt)
        if provider_length > self._max_prompt_characters:
            raise PromptCompileError(
                "编译后的 Provider 中文提示词超出产品安全上限："
                f"{provider_length}/{self._max_prompt_characters} 字；禁止静默截断"
            )

        warnings: list[str] = []
        if compact_projection:
            warnings.append(_COMPACT_PROVIDER_WARNING)
        if minimal_compact_projection:
            warnings.append(_MINIMAL_COMPACT_PROVIDER_WARNING)
        if provider_length > RECOMMENDED_CHINESE_PROMPT_CHARACTERS:
            warnings.append("Provider 提示词超过产品中文可读性预警线 500 字；这不是供应商硬限制")

        bindings = [
            CompiledAssetBinding(
                assetId=asset.assetId,
                mediaAssetId=asset.mediaAssetId,
                alias=aliases[asset.assetId],
                modality=asset.modality,
                duty=asset.duty,
                bindingScope=asset.bindingScope,
                settingReference=asset.settingReference,
                featureDomain=asset.featureDomain,
                keyframeRole=asset.keyframeRole,
                targetEntity=asset.targetEntity,
                isFixture=asset.isFixture,
            )
            for asset in scene.assets
        ]
        asset_ready = all(not asset.isFixture for asset in scene.assets)
        return SeedancePromptPackage(
            sceneId=scene.sceneId,
            prompt=provider_prompt,
            promptCharacterCount=provider_length,
            recommendedPromptCharacters=RECOMMENDED_CHINESE_PROMPT_CHARACTERS,
            maxPromptCharacters=self._max_prompt_characters,
            compileProfile=(
                "seedance_director_v3"
                if scene.schemaVersion == "1.3"
                else "seedance_director_v3_compat"
            ),
            providerPrompt=provider_prompt,
            providerPromptCharacterCount=provider_length,
            manifestPrompt=manifest_prompt,
            manifestPromptCharacterCount=len(manifest_prompt),
            warnings=warnings,
            assetBindings=bindings,
            output=scene.output,
            previewOnly=preview_only,
            assetReady=asset_ready,
            submissionReady=asset_ready and not preview_only,
            fixtureOnly=all(asset.isFixture for asset in scene.assets),
        )

    def _compile_manifest_prompt(
        self,
        scene: ScenePromptSpec,
        aliases: dict[str, str],
        *,
        no_bgm: bool,
    ) -> str:
        """生成保留全部制作事实的可读清单。"""

        sections = [
            f"标题：{scene.title}",
            self._compile_manifest_assets(scene.assets, aliases),
            f"概述：{scene.summary}",
        ]
        if scene.schemaVersion == "1.3" and scene.dramaticArc is not None:
            sections.append(f"戏剧弧：{scene.dramaticArc}")
        sections.extend(
            [
                f"风格：{scene.visualStyle}",
                f"摄影基线：{self._compile_cinematography_base(scene)}",
                f"灯光基线：{self._compile_manifest_lighting_setup(scene)}",
            ]
        )
        sections.extend(
            self._compile_manifest_beat(index, beat, scene, aliases)
            for index, beat in enumerate(scene.beats, start=1)
        )
        sections.append(f"全片：{scene.globalDirection}")
        if no_bgm:
            sections.append("声音：无BGM。")
        sections.append(f"禁止：{'、'.join(scene.negativeConstraints)}。")
        sections.append(
            "输出："
            f"{scene.output.model}/{scene.output.resolution}/{scene.output.ratio}/"
            f"{scene.output.durationSeconds}秒/{scene.output.outputFormat}/"
            f"生成音频={scene.output.generateAudio}/水印={scene.output.watermark}。"
        )
        return "\n".join(sections)

    def _compile_provider_prompt(
        self,
        scene: ScenePromptSpec,
        aliases: dict[str, str],
        *,
        no_bgm: bool,
        compact: bool = False,
        minimal_compact: bool = False,
    ) -> str:
        """生成自然语言导演稿，只投影会直接影响画面的制作事实。"""

        if minimal_compact and not compact:
            raise PromptCompileError("最小导演投影必须建立在紧凑投影之上")

        asset_text = "；".join(
            self._compile_provider_asset(
                asset,
                aliases[asset.assetId],
                no_bgm=no_bgm,
            )
            for asset in scene.assets
        )
        sections = [
            (
                f"制作一支{scene.output.durationSeconds}秒的{scene.visualStyle}"
                f"长篇小说改编场景《{scene.title}》。"
            )
        ]
        if (
            scene.schemaVersion == "1.3"
            and scene.dramaticArc is not None
            and not minimal_compact
        ):
            # 1.3 以已审计的戏剧弧统领场景，不再把可能很长且重复的 summary 再发一遍。
            sections.append(f"戏剧弧：{scene.dramaticArc.rstrip('。；; ')}。")
        else:
            sections.append(self._compile_compat_narrative_intent(scene))
        sections.append(f"参考素材：{asset_text}。")
        if compact:
            sections.append(
                self._compile_minimal_provider_baseline(scene)
                if minimal_compact
                else self._compile_compact_provider_baseline(scene)
            )
            sections.extend(
                self._compile_compact_provider_beat(
                    index,
                    beat,
                    scene,
                    aliases,
                    minimal=minimal_compact,
                )
                for index, beat in enumerate(scene.beats, start=1)
            )
        else:
            sections.append(
                "摄影与动机光基线："
                f"{self._compile_provider_cinematography_base(scene)}；"
                f"{self._compile_provider_lighting_setup(scene)}。"
            )
            sections.extend(
                self._compile_provider_beat(index, beat, scene, aliases)
                for index, beat in enumerate(scene.beats, start=1)
            )
        # 声音事实单独编译一次，连续性句不再重复“无 BGM”。
        global_direction = self._without_no_bgm_clause(scene.globalDirection).rstrip("。；; ")
        if global_direction and not compact:
            sections.append(f"全片连续性：{global_direction}。")
        if no_bgm:
            sections.append("声音：只使用各镜头明确写出的声音，不使用BGM。")
        constraints = self._compile_provider_constraints(
            scene.negativeConstraints,
            no_bgm=no_bgm,
        )
        if constraints:
            sections.append(f"禁止：{'、'.join(constraints)}。")
        return "\n".join(sections)

    @staticmethod
    def _compile_compact_provider_baseline(scene: ScenePromptSpec) -> str:
        """用结构值生成短基线；氛围长说明仍完整保留在 Manifest。"""

        base = scene.cinematographyBase
        setup = scene.lightingSetup
        if base is None or setup is None:
            raise PromptCompileError("1.3 场景缺少摄影或灯光基线")
        white_balance = (
            f"，白平衡{setup.cameraWhiteBalanceK}K"
            if setup.cameraWhiteBalanceK is not None
            else ""
        )
        return (
            "全片基线："
            f"{_CAPTURE_FORMAT_LABEL[base.captureFormat]}"
            f"{_LENS_PROJECTION_LABEL[base.lensProjection]}，"
            f"{base.frameRateFps}fps/{base.shutterAngleDegrees}度快门，"
            f"{_AXIS_RULE_LABEL[base.axisRule]}，{_SCREEN_DIRECTION_LABEL[base.screenDirection]}；"
            f"{_EXPOSURE_LABEL[setup.exposureStyle]}{white_balance}，"
            f"{setup.ambientSource}{setup.ambientColorTemperatureK}K环境光，"
            f"暗侧低{setup.keyToFillStops:g}档。"
        )

    @staticmethod
    def _compile_minimal_provider_baseline(scene: ScenePromptSpec) -> str:
        """只保留跨镜头必须共享的成像、轴线、曝光和白平衡事实。"""

        base = scene.cinematographyBase
        setup = scene.lightingSetup
        if base is None or setup is None:
            raise PromptCompileError("1.3 场景缺少摄影或灯光基线")
        white_balance = (
            f"/白平衡{setup.cameraWhiteBalanceK}K"
            if setup.cameraWhiteBalanceK is not None
            else ""
        )
        return (
            "基线："
            f"{_CAPTURE_FORMAT_LABEL[base.captureFormat]}/"
            f"{base.frameRateFps}fps/{base.shutterAngleDegrees}度快门/"
            f"{_AXIS_RULE_LABEL[base.axisRule]}/"
            f"{_SCREEN_DIRECTION_LABEL[base.screenDirection]}；"
            f"{_EXPOSURE_LABEL[setup.exposureStyle]}{white_balance}。"
        )

    @staticmethod
    def _compile_compat_narrative_intent(scene: ScenePromptSpec) -> str:
        """用各拍最终可见结果概括 1.2 叙事，不发送冗长 summary 或虚构新事实。"""

        visible_results = [
            beat.actionUnits[-1].visibleResult.rstrip("。；; ")
            for beat in scene.beats
            if beat.actionUnits
        ]
        if not visible_results:
            return f"叙事围绕{scene.title}展开。"
        if len(visible_results) == 1:
            return f"叙事推进：最终让{visible_results[0]}。"
        sequence = "，继而".join(visible_results[1:-1])
        middle = f"，继而{sequence}" if sequence else ""
        return f"叙事推进：先让{visible_results[0]}{middle}，最终让{visible_results[-1]}。"

    @staticmethod
    def _compile_provider_asset(
        asset: AssetBinding,
        alias: str,
        *,
        no_bgm: bool,
    ) -> str:
        """Provider 只绑定素材对象与职责，完整视觉圣经和排除项留在 Manifest。"""

        duty = (
            _KEYFRAME_ROLE_LABEL[asset.keyframeRole]
            if asset.keyframeRole is not None
            else _DUTY_LABEL[asset.duty]
        )
        if asset.keyframeRole == "initial_state":
            initial_suffix = "" if "初态" in asset.targetEntity else "初态"
            return f"{alias}只锁定{asset.targetEntity}{initial_suffix}"
        if asset.keyframeRole is not None:
            return f"{alias}只锁定{asset.targetEntity}{duty}"
        if duty in asset.targetEntity:
            duty_suffix = ""
        elif asset.duty in {"identity", "costume"}:
            duty_suffix = f"的{duty}"
        else:
            duty_suffix = duty
        return f"{alias}锁定{asset.targetEntity}{duty_suffix}"

    @staticmethod
    def _without_no_bgm_clause(text: str) -> str:
        """删除 Provider 连续性句中的禁 BGM 分句，Manifest 仍保留原文。"""

        clauses = re.split(r"[，,；;。]+", text)
        kept = [
            clause.strip()
            for clause in clauses
            if clause.strip() and not any(marker in clause.casefold() for marker in _NO_BGM_MARKERS)
        ]
        return "，".join(kept)

    @staticmethod
    def _compile_provider_constraints(
        constraints: list[str],
        *,
        no_bgm: bool,
    ) -> list[str]:
        """把已知服务器硬约束转成等价短句，原文仍完整保存在 Manifest。"""

        result: list[str] = []
        seen: set[str] = set()
        for constraint in constraints:
            normalized = constraint.casefold()
            if no_bgm and any(marker in normalized for marker in _NO_BGM_MARKERS):
                continue
            family: str | None = None
            compact = constraint
            if any(marker in constraint for marker in _UNREADABLE_TEXT_MARKERS):
                family = "unreadable_text"
                compact = _UNREADABLE_SYMBOL_PROVIDER_CONSTRAINT
            elif any(marker in constraint for marker in _MODERN_OBJECT_MARKERS):
                family = "modern_object"
                compact = _MODERN_OBJECT_PROVIDER_CONSTRAINT
            elif any(marker in constraint for marker in ("换脸", "身份漂移", "五官漂移")):
                family = "identity_drift"
                compact = _IDENTITY_PROVIDER_CONSTRAINT
            elif any(marker in constraint for marker in ("增减人物", "多出人物", "人物数量")):
                family = "character_count"
                compact = _CHARACTER_COUNT_PROVIDER_CONSTRAINT
            elif any(marker in constraint for marker in ("道具变形", "物件变形", "道具漂移")):
                family = "prop_deformation"
                compact = _PROP_DEFORMATION_PROVIDER_CONSTRAINT
            elif any(marker in constraint for marker in ("逆重力", "违背物理", "物理错误")):
                family = "physics"
                compact = _PHYSICS_PROVIDER_CONSTRAINT
            dedupe_key = family or re.sub(r"[\s，,。；;、]+", "", normalized)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            result.append(compact)
        return result

    @staticmethod
    def _assign_aliases(assets: list[AssetBinding]) -> dict[str, str]:
        counters: defaultdict[str, int] = defaultdict(int)
        aliases: dict[str, str] = {}
        for asset in assets:
            counters[asset.modality] += 1
            aliases[asset.assetId] = f"@{_ALIAS_PREFIX[asset.modality]}{counters[asset.modality]}"
        return aliases

    @staticmethod
    def _compile_manifest_assets(
        assets: list[AssetBinding],
        aliases: dict[str, str],
    ) -> str:
        bindings: list[str] = []
        for asset in assets:
            include = "、".join(asset.includeFeatures)
            setting = (
                f"{asset.settingReference.kind}:{asset.settingReference.id}"
                if asset.settingReference is not None
                else "无"
            )
            media = asset.mediaAssetId or "待补"
            metadata = (
                f"槽位={asset.assetId}，绑定={asset.bindingScope}，设定={setting}，"
                f"媒体={media}，fixture={asset.isFixture}，职责={asset.duty}，"
                f"特征域={asset.featureDomain}"
            )
            if asset.keyframeRole is not None:
                metadata += f"，关键帧={asset.keyframeRole}"
            binding = (
                f"{aliases[asset.assetId]}={asset.targetEntity}（{metadata}），仅参考{include}"
            )
            if asset.excludeFeatures:
                binding += f"，不参考{'、'.join(asset.excludeFeatures)}"
            bindings.append(binding)
        return f"素材：{'；'.join(bindings)}。"

    @classmethod
    def _compile_manifest_beat(
        cls,
        index: int,
        beat: CameraBeatSpec,
        scene: ScenePromptSpec,
        aliases: dict[str, str],
    ) -> str:
        references = "、".join(aliases[asset_id] for asset_id in beat.referencedAssetIds)
        camera = cls._compile_camera(beat, scene)
        lighting = cls._compile_manifest_lighting(beat)
        parts: list[str] = []
        semantic_fields = (
            ("镜头任务", beat.dramaticPurpose),
            ("表演指导", beat.performanceDirection),
            ("场面调度", beat.blocking),
            ("摄影动机", beat.cameraMotivation),
            ("轴线转换", beat.axisTransition),
        )
        parts.extend(f"{label}={value}" for label, value in semantic_fields if value is not None)
        parts.extend([camera, lighting, beat.action, f"复杂度={beat.actionComplexity}"])
        if references:
            parts.append(f"参考{references}")
        if beat.sound:
            parts.append(beat.sound)
        if beat.transition:
            parts.append(beat.transition)
        return f"镜头{index}（{beat.startSecond}-{beat.endSecond}秒）：{'；'.join(parts)}。"

    @classmethod
    def _compile_provider_beat(
        cls,
        index: int,
        beat: CameraBeatSpec,
        scene: ScenePromptSpec,
        aliases: dict[str, str],
    ) -> str:
        """按任务、表演调度、摄影响应、焦点、灯光和声音编译单镜头。"""

        references: list[str] = []
        for asset_id in beat.referencedAssetIds:
            if asset_id not in aliases:
                raise PromptCompileError(f"镜头引用了未知素材槽位：{asset_id}")
            references.append(aliases[asset_id])

        action = "；".join(
            f"{unit.subject}{unit.action}，{unit.visibleResult}" for unit in beat.actionUnits
        )
        parts: list[str] = []
        purpose = beat.dramaticPurpose
        if scene.schemaVersion == "1.3" and purpose is not None:
            parts.append(f"镜头任务是{purpose.rstrip('。；; ')}")
        if references:
            parts.append(f"参考{'、'.join(references)}")

        if scene.schemaVersion == "1.3":
            performance_parts = [
                value.rstrip("。；; ")
                for value in (beat.performanceDirection, beat.blocking, action)
                if value
            ]
            if performance_parts:
                parts.append(f"表演与调度：{'；'.join(performance_parts)}")
        elif action:
            parts.append(f"动作：{action}")

        parts.append(cls._compile_provider_camera(beat, scene))
        parts.append(cls._compile_provider_lighting(beat))
        if beat.sound:
            parts.append(f"声音：{beat.sound}")
        if beat.transition:
            # strict 枚举转成中文导演口令；用户写入的自由转场说明保持原样。
            transition = _CUT_LABEL.get(beat.transition, beat.transition)
            parts.append(f"转场：{transition}")
        return f"镜头{index}（{beat.startSecond}-{beat.endSecond}秒）：{'。'.join(parts)}。"

    @classmethod
    def _compile_compact_provider_beat(
        cls,
        index: int,
        beat: CameraBeatSpec,
        scene: ScenePromptSpec,
        aliases: dict[str, str],
        *,
        minimal: bool = False,
    ) -> str:
        """保留每拍可见执行事实，去掉已进入 Manifest 的重复自由导演说明。"""

        references: list[str] = []
        for asset_id in beat.referencedAssetIds:
            if asset_id not in aliases:
                raise PromptCompileError(f"镜头引用了未知素材槽位：{asset_id}")
            references.append(aliases[asset_id])
        actions = "；".join(unit.to_text() for unit in beat.actionUnits)
        parts = [f"参考{'、'.join(references)}"] if references else []
        if actions:
            parts.append(f"动作：{actions}")
        if beat.performanceDirection:
            parts.append(f"表演：{beat.performanceDirection.rstrip('。；; ')}")
        parts.extend(
            [
                "摄影："
                + (
                    cls._compile_minimal_provider_camera(beat, scene)
                    if minimal
                    else cls._compile_compact_provider_camera(beat, scene)
                ),
                "灯光："
                + (
                    cls._compile_minimal_provider_lighting(beat)
                    if minimal
                    else cls._compile_compact_provider_lighting(beat)
                ),
            ]
        )
        if beat.sound:
            parts.append(f"声音：{beat.sound}")
        if beat.transition and not minimal:
            transition = _CUT_LABEL.get(beat.transition, beat.transition)
            parts.append(f"转场：{transition}")
        return f"镜头{index}（{beat.startSecond}-{beat.endSecond}秒）：{'；'.join(parts)}。"

    @staticmethod
    def _compile_cinematography_base(scene: ScenePromptSpec) -> str:
        """编译成像面、帧率、快门和轴线，避免把快门角与轴线混写。"""

        base = scene.cinematographyBase
        if base is None:
            raise PromptCompileError("1.2 场景缺少 cinematographyBase")
        return (
            f"{_CAPTURE_FORMAT_LABEL[base.captureFormat]}，"
            f"{_LENS_PROJECTION_LABEL[base.lensProjection]}镜头，"
            f"{base.frameRateFps}fps、{base.shutterAngleDegrees}度快门；"
            f"{_AXIS_RULE_LABEL[base.axisRule]}，"
            f"{_SCREEN_DIRECTION_LABEL[base.screenDirection]}"
        )

    @staticmethod
    def _compile_provider_cinematography_base(scene: ScenePromptSpec) -> str:
        """把全场摄影基线写成自然句，不向供应商暴露内部枚举标签。"""

        base = scene.cinematographyBase
        if base is None:
            raise PromptCompileError("1.2 场景缺少 cinematographyBase")
        axis = {
            "maintain_180": "人物互动始终保持在180度轴线同侧",
            "intentional_cross": "只有可见越轴或明确重置镜头才改变轴线侧",
            "not_applicable": "本场不建立人物互动轴线",
        }[base.axisRule]
        return (
            f"采用{_CAPTURE_FORMAT_LABEL[base.captureFormat]}"
            f"{_LENS_PROJECTION_LABEL[base.lensProjection]}成像，"
            f"{base.frameRateFps}fps、{base.shutterAngleDegrees}度快门；"
            f"{axis}，{_SCREEN_DIRECTION_LABEL[base.screenDirection]}"
        )

    @staticmethod
    def _compile_manifest_lighting_setup(scene: ScenePromptSpec) -> str:
        """把全场曝光、白平衡、环境色温与光比完整写入 Manifest。"""

        setup = scene.lightingSetup
        if setup is None:
            raise PromptCompileError("1.2 场景缺少 lightingSetup")
        white_balance = (
            f"摄影机白平衡{setup.cameraWhiteBalanceK}K，"
            if setup.cameraWhiteBalanceK is not None
            else ""
        )
        return (
            f"{_EXPOSURE_LABEL[setup.exposureStyle]}，"
            f"{white_balance}"
            f"环境光由{setup.ambientSource}驱动，{setup.ambientColorTemperatureK}K；"
            f"主光比补光高{setup.keyToFillStops:g}档，"
            f"{_NEGATIVE_FILL_LABEL[setup.negativeFillSide]}，{setup.atmosphere}"
        )

    @staticmethod
    def _compile_provider_lighting_setup(scene: ScenePromptSpec) -> str:
        """只向 Provider 投影能改变成像关系的白平衡、光源色温与暗侧档差。"""

        setup = scene.lightingSetup
        if setup is None:
            raise PromptCompileError("1.2 场景缺少 lightingSetup")
        parts = [_EXPOSURE_LABEL[setup.exposureStyle]]
        if setup.cameraWhiteBalanceK is not None:
            parts.append(f"摄影机白平衡{setup.cameraWhiteBalanceK}K")
        parts.extend(
            [
                f"{setup.ambientSource}形成{setup.ambientColorTemperatureK}K环境光",
                f"暗侧比主光低{setup.keyToFillStops:g}档",
                _NEGATIVE_FILL_LABEL[setup.negativeFillSide],
                setup.atmosphere,
            ]
        )
        return "，".join(parts)

    @classmethod
    def _compile_camera(cls, beat: CameraBeatSpec, scene: ScenePromptSpec) -> str:
        """把所有结构化摄影事实写入 Manifest，包含工程遥测参数。"""

        progression = beat.shotProgression
        camera = beat.cameraSpec
        base = scene.cinematographyBase
        if progression is None or camera is None or base is None:
            raise PromptCompileError("1.2 镜头缺少 shotProgression、cameraSpec 或摄影基线")

        if progression.changeMode == "continuous":
            if progression.startShotSize == progression.endShotSize:
                shot = f"以{progression.startShotSize}拍摄"
            else:
                shot = f"画面从{progression.startShotSize}连续变化到{progression.endShotSize}"
        else:
            shot = (
                f"从{progression.startShotSize}{_CUT_LABEL[progression.changeMode]}"
                f"{progression.endShotSize}"
            )

        lens = (
            f"{camera.focalLengthMm}mm"
            f"{_LENS_PROJECTION_LABEL[base.lensProjection]}"
            f"{_LENS_TYPE_LABEL[camera.lensType]}，T{camera.tStop:g}"
        )
        if camera.lensType == "zoom":
            lens = (
                f"{camera.focalLengthMm}mm变到{camera.endFocalLengthMm}mm的"
                f"{_LENS_PROJECTION_LABEL[base.lensProjection]}变焦镜头，T{camera.tStop:g}"
            )

        position = camera.position
        position_text = (
            f"机位高{position.heightCm}cm、方位{position.azimuthDegrees}度、"
            f"俯仰{position.elevationDegrees}度，距主体{position.subjectDistanceMeters:g}m，"
            f"保持{_AXIS_SIDE_LABEL[position.axisSide]}"
        )
        if position.rollDegrees:
            position_text += f"，滚转{position.rollDegrees}度"

        composition = camera.composition
        composition_text = (
            f"{_COMPOSITION_LABEL[composition.rule]}，主体位于"
            f"{_PLACEMENT_LABEL[composition.subjectPlacement]}、约占画面"
            f"{composition.subjectFramePercent}%，{_HEADROOM_LABEL[composition.headroom]}；"
            f"前景为{composition.foregroundLayer}，背景为{composition.backgroundLayer}"
        )
        movement_text = cls._compile_camera_movement(camera)
        focus = camera.focus
        if focus.transition == "locked":
            focus_text = f"{_DOF_LABEL[focus.depthOfField]}，焦点锁在{focus.startTarget}"
        else:
            focus_text = (
                f"{_DOF_LABEL[focus.depthOfField]}，用{focus.rackDurationSeconds:g}秒"
                f"从{focus.startTarget}拉焦到{focus.endTarget}"
            )
        return f"{shot}，{lens}；{position_text}；{composition_text}；{movement_text}；{focus_text}"

    @classmethod
    def _compile_provider_camera(cls, beat: CameraBeatSpec, scene: ScenePromptSpec) -> str:
        """把摄影事实改写为由动作触发、以落幅结束的导演句。"""

        progression = beat.shotProgression
        camera = beat.cameraSpec
        base = scene.cinematographyBase
        if progression is None or camera is None or base is None:
            raise PromptCompileError("1.2 镜头缺少 shotProgression、cameraSpec 或摄影基线")

        lens = (
            f"{camera.focalLengthMm}mm"
            f"{_LENS_PROJECTION_LABEL[base.lensProjection]}"
            f"{_LENS_TYPE_LABEL[camera.lensType]}、T{camera.tStop:g}"
        )
        if camera.lensType == "zoom":
            lens = (
                f"{camera.focalLengthMm}mm至{camera.endFocalLengthMm}mm"
                f"{_LENS_PROJECTION_LABEL[base.lensProjection]}变焦、T{camera.tStop:g}"
            )

        position = camera.position
        axis = _AXIS_SIDE_LABEL[position.axisSide]
        if beat.axisTransition is not None:
            axis += f"，{_AXIS_TRANSITION_LABEL[beat.axisTransition]}"

        movement = cls._compile_provider_camera_movement(camera)
        composition = camera.composition
        landing = (
            f"{progression.endShotSize}{_COMPOSITION_LABEL[composition.rule]}，"
            f"主体在{_PLACEMENT_LABEL[composition.subjectPlacement]}，"
            f"前景为{composition.foregroundLayer}"
        )
        if progression.changeMode == "continuous":
            transition = movement
        else:
            transition = (
                f"从{progression.startShotSize}{_CUT_LABEL[progression.changeMode]}"
                f"{progression.endShotSize}，随后{movement}"
            )

        motivation = beat.cameraMotivation
        motivation_text = (
            f"摄影动机：{motivation.rstrip('。；; ')}。" if motivation is not None else ""
        )
        focus = camera.focus
        if focus.transition == "locked":
            focus_text = f"{_DOF_LABEL[focus.depthOfField]}，焦点锁在{focus.startTarget}"
        else:
            focus_text = (
                f"{_DOF_LABEL[focus.depthOfField]}，用{focus.rackDurationSeconds:g}秒"
                f"从{focus.startTarget}拉焦到{focus.endTarget}"
            )
        return (
            f"{motivation_text}摄影机以{progression.startShotSize}、{lens}和{axis}起幅，"
            f"{transition}，落幅为{landing}；{focus_text}"
        )

    @classmethod
    def _compile_compact_provider_camera(
        cls,
        beat: CameraBeatSpec,
        scene: ScenePromptSpec,
    ) -> str:
        """用闭合结构生成短摄影句，不复制机位遥测和自由摄影动机。"""

        progression = beat.shotProgression
        camera = beat.cameraSpec
        base = scene.cinematographyBase
        if progression is None or camera is None or base is None:
            raise PromptCompileError("1.3 镜头缺少 shotProgression、cameraSpec 或摄影基线")

        if progression.changeMode == "continuous":
            shot = (
                progression.startShotSize
                if progression.startShotSize == progression.endShotSize
                else f"{progression.startShotSize}连续到{progression.endShotSize}"
            )
        else:
            shot = (
                f"{progression.startShotSize}{_CUT_LABEL[progression.changeMode]}"
                f"{progression.endShotSize}"
            )
        if camera.lensType == "zoom":
            lens = f"{camera.focalLengthMm}至{camera.endFocalLengthMm}mm变焦/T{camera.tStop:g}"
        else:
            lens = (
                f"{camera.focalLengthMm}mm"
                f"{_LENS_TYPE_LABEL[camera.lensType]}/T{camera.tStop:g}"
            )
        axis = _AXIS_SIDE_LABEL[camera.position.axisSide]
        if beat.axisTransition is not None:
            axis += f"/{_AXIS_TRANSITION_LABEL[beat.axisTransition]}"
        composition = camera.composition
        frame = (
            f"{_COMPOSITION_LABEL[composition.rule]}/"
            f"{_PLACEMENT_LABEL[composition.subjectPlacement]}"
        )
        focus = camera.focus
        if focus.transition == "locked":
            focus_text = f"{_DOF_LABEL[focus.depthOfField]}锁焦{focus.startTarget}"
        else:
            focus_text = (
                f"{_DOF_LABEL[focus.depthOfField]}用{focus.rackDurationSeconds:g}秒"
                f"由{focus.startTarget}拉焦至{focus.endTarget}"
            )
        return "，".join(
            (
                shot,
                lens,
                axis,
                cls._compile_provider_camera_movement(camera),
                frame,
                focus_text,
            )
        )

    @classmethod
    def _compile_minimal_provider_camera(
        cls,
        beat: CameraBeatSpec,
        scene: ScenePromptSpec,
    ) -> str:
        """保留景别、镜头、主运镜、构图和焦点，轴线公共事实只写一次。"""

        progression = beat.shotProgression
        camera = beat.cameraSpec
        if progression is None or camera is None or scene.cinematographyBase is None:
            raise PromptCompileError("1.3 镜头缺少 shotProgression、cameraSpec 或摄影基线")
        if progression.changeMode == "continuous":
            shot = (
                progression.startShotSize
                if progression.startShotSize == progression.endShotSize
                else f"{progression.startShotSize}到{progression.endShotSize}"
            )
        else:
            shot = (
                f"{progression.startShotSize}{_CUT_LABEL[progression.changeMode]}"
                f"{progression.endShotSize}"
            )
        lens = (
            f"{camera.focalLengthMm}至{camera.endFocalLengthMm}mm变焦/T{camera.tStop:g}"
            if camera.lensType == "zoom"
            else f"{camera.focalLengthMm}mm{_LENS_TYPE_LABEL[camera.lensType]}/T{camera.tStop:g}"
        )
        composition = camera.composition
        focus = camera.focus
        focus_text = (
            f"{_DOF_LABEL[focus.depthOfField]}锁焦{focus.startTarget}"
            if focus.transition == "locked"
            else f"{focus.rackDurationSeconds:g}秒由{focus.startTarget}拉焦至{focus.endTarget}"
        )
        parts = [
            shot,
            lens,
            cls._compile_provider_camera_movement(camera),
            f"{_COMPOSITION_LABEL[composition.rule]}/{_PLACEMENT_LABEL[composition.subjectPlacement]}",
            focus_text,
        ]
        axis_transition = beat.axisTransition
        if axis_transition is not None and axis_transition != "hold":
            parts.append(_AXIS_TRANSITION_LABEL[axis_transition])
        return "/".join(parts)

    @staticmethod
    def _compile_provider_camera_movement(camera: ShotCameraSpec) -> str:
        """Provider 只保留单一主运镜及其速度，不输出位移、旋转与缓动遥测。"""

        movement = camera.movement
        support = _SUPPORT_LABEL[movement.support]
        if movement.movementType == "locked_off":
            return f"{support}锁定机位"
        return f"{support}{_SPEED_LABEL[movement.speed]}{_MOVEMENT_LABEL[movement.movementType]}"

    @staticmethod
    def _compile_camera_movement(camera: ShotCameraSpec) -> str:
        """编译单一主运镜，不把变焦、位移和摇摄混成一串。"""

        # ShotCameraSpec 在共享契约已完成交叉校验，这里只负责自然语言投影。
        movement = camera.movement
        support = _SUPPORT_LABEL[movement.support]
        if movement.movementType == "locked_off":
            return f"{support}锁定机位"

        details = [
            f"{support}{_SPEED_LABEL[movement.speed]}{_MOVEMENT_LABEL[movement.movementType]}"
        ]
        if movement.travelDistanceMeters:
            details.append(f"位移{movement.travelDistanceMeters:g}m")
        if movement.rotationDegrees:
            details.append(f"旋转{movement.rotationDegrees:g}度")
        details.append(_EASING_LABEL[movement.easing])
        return "，".join(details)

    @classmethod
    def _compile_manifest_lighting(cls, beat: CameraBeatSpec) -> str:
        """把动机光的全部光位、束控与结果写进 Manifest。"""

        cue = beat.lightingCue
        if cue is None:
            raise PromptCompileError("1.2 镜头缺少 lightingCue")
        if cue.continuityMode == "inherit":
            inherited_key = cue.keyLight
            return (
                "灯光：完整延续上一镜的"
                f"{inherited_key.colorTemperatureK}K"
                f"{_LIGHT_QUALITY_LABEL[inherited_key.quality]}"
                f"{_LIGHT_DELIVERY_LABEL[inherited_key.delivery]}"
                f"{_LIGHT_DIRECTION_LABEL[inherited_key.direction]}主光、"
                f"{_FILL_STRATEGY_LABEL[cue.fillStrategy]}"
                f"{cue.fillRelativeStops:+g}档和{cue.atmosphere}；"
                "光位、光比、束角与溢光控制不变；"
                f"{cue.visibleResult}"
            )
        continuity = {
            "establish": cue.motivatedChange,
            "inherit": "灯光延续上一镜",
            "motivated_change": f"灯光因{cue.motivatedChange}发生变化",
        }[cue.continuityMode]
        key_text = cls._compile_light_source(cue.keyLight)
        if cue.fillStrategy == "none":
            fill = "无补光"
        elif cue.fillDirection is None:
            raise PromptCompileError("启用补光的镜头缺少 fillDirection")
        else:
            fill = (
                f"{_FILL_STRATEGY_LABEL[cue.fillStrategy]}从"
                f"{_LIGHT_DIRECTION_LABEL[cue.fillDirection]}作用，"
                f"相对曝光{cue.fillRelativeStops:+g}档"
            )
        parts = [continuity, key_text, fill]
        if cue.edgeLight is not None:
            parts.append(f"辅助光为{cls._compile_light_source(cue.edgeLight)}")
        parts.extend([cue.atmosphere, cue.visibleResult])
        return "灯光：" + "；".join(parts)

    @classmethod
    def _compile_provider_lighting(cls, beat: CameraBeatSpec) -> str:
        """继承镜头只声明延续；建立或变化镜头才重述可见的动机光。"""

        cue = beat.lightingCue
        if cue is None:
            raise PromptCompileError("1.2 镜头缺少 lightingCue")
        if cue.continuityMode == "inherit":
            return "灯光沿用上一镜"

        mode = "灯光建立" if cue.continuityMode == "establish" else "灯光变化"
        # 变化说明常同时复述动作与光效；Provider 只取首个可见触发分句。
        visible_trigger = re.split(r"[，,；;。]+", cue.motivatedChange, maxsplit=1)[0].strip()
        return (
            f"{mode}：{visible_trigger}；"
            f"{cls._compile_provider_light_source(cue.keyLight)}；"
            f"最终{cue.visibleResult}"
        )

    @classmethod
    def _compile_compact_provider_lighting(cls, beat: CameraBeatSpec) -> str:
        """保留灯光来源、变化触发和可见结果，工程光位留在 Manifest。"""

        cue = beat.lightingCue
        if cue is None:
            raise PromptCompileError("1.3 镜头缺少 lightingCue")
        if cue.continuityMode == "inherit":
            return "沿用上一镜"
        mode = "建立" if cue.continuityMode == "establish" else "变化"
        trigger = re.split(r"[，,；;。]+", cue.motivatedChange, maxsplit=1)[0].strip()
        key = cue.keyLight
        return (
            f"{mode}：{trigger}，{key.motivatedBy}自"
            f"{_LIGHT_DIRECTION_LABEL[key.direction]}形成"
            f"{key.colorTemperatureK}K{_LIGHT_QUALITY_LABEL[key.quality]}主光，"
            f"最终{cue.visibleResult}"
        )

    @staticmethod
    def _compile_minimal_provider_lighting(beat: CameraBeatSpec) -> str:
        """最小投影保留灯光连续性、可见触发和落幅结果。"""

        cue = beat.lightingCue
        if cue is None:
            raise PromptCompileError("1.3 镜头缺少 lightingCue")
        if cue.continuityMode == "inherit":
            return "沿前镜"
        mode = "建立" if cue.continuityMode == "establish" else "变化"
        trigger = re.split(r"[，,；;。]+", cue.motivatedChange, maxsplit=1)[0].strip()
        return f"{mode}{trigger}，最终{cue.visibleResult}"

    @staticmethod
    def _compile_provider_light_source(light: LightSourceSpec) -> str:
        """Provider 只保留主光的动机、方向、色温与软硬，不输出灯具遥测。"""

        role = {
            "key": "主光",
            "fill": "补光",
            "rim": "轮廓光",
            "background": "背景光",
            "practical": "实景光",
        }[light.role]
        return (
            f"{light.motivatedBy}自{_LIGHT_DIRECTION_LABEL[light.direction]}形成"
            f"{light.colorTemperatureK}K{_LIGHT_QUALITY_LABEL[light.quality]}"
            f"{role}"
        )

    @staticmethod
    def _compile_light_source(light: LightSourceSpec) -> str:
        """编译单灯的动机、方向、色温、曝光和束控。"""

        role = {
            "key": "主光",
            "fill": "补光",
            "rim": "轮廓光",
            "background": "背景光",
            "practical": "实景光",
        }[light.role]
        return (
            f"由{light.motivatedBy}驱动的{role}，从"
            f"{_LIGHT_DIRECTION_LABEL[light.direction]}方位{light.azimuthDegrees}度、"
            f"高度角{light.elevationDegrees}度照入；"
            f"{light.colorTemperatureK}K、{_LIGHT_QUALITY_LABEL[light.quality]}"
            f"{_LIGHT_DELIVERY_LABEL[light.delivery]}，相对曝光"
            f"{light.relativeExposureStops:+g}档，束角{light.beamAngleDegrees}度、"
            f"{_LIGHT_FALLOFF_LABEL[light.falloff]}，{light.spillControl}，"
            f"画面中{light.visibleResult}"
        )
