from __future__ import annotations

import json

from inkforge_contracts.video import (
    CameraCompositionSpec,
    CameraFocusSpec,
    CameraMovementSpec,
    CameraPositionSpec,
    CinematographyBase,
    LightingSetup,
    LightSourceSpec,
    ShotCameraSpec,
    ShotLightingCue,
)

from .compiler import SeedancePromptCompiler
from .contracts import (
    AssetBinding,
    CameraActionUnit,
    CameraBeatSpec,
    CameraShotProgression,
    ScenePromptSpec,
    SeedanceOutputSpec,
    SettingReference,
)


def build_demo_scene() -> ScenePromptSpec:
    """构造包含可复核摄影和有动机灯光的《无年之灾》试拍场景。"""

    # 首镜建立院落冷天光；第二镜通过复制只改变连续性标签，保证灯光事实完全继承。
    established_cold_daylight = ShotLightingCue(
        continuityMode="establish",
        motivatedChange="院落左后方门洞外的阴冷天光建立空间方向",
        keyLight=LightSourceSpec(
            role="key",
            motivatedBy="左后方门洞外冷天光",
            direction="back_left",
            azimuthDegrees=-135,
            elevationDegrees=35,
            quality="soft",
            delivery="diffused",
            colorTemperatureK=6500,
            relativeExposureStops=0,
            beamAngleDegrees=80,
            falloff="slow",
            spillControl="门框限制溢光",
            visibleResult="铁锅湿边与人物肩线出现冷色高光",
        ),
        fillStrategy="negative_fill",
        fillDirection="front_right",
        fillRelativeStops=-4,
        edgeLight=None,
        atmosphere="低密度冷湿空气",
        visibleResult="土灶、铁锅和人物保持低调光层次",
    )
    inherited_cold_daylight = established_cold_daylight.model_copy(
        update={
            "continuityMode": "inherit",
            "motivatedChange": "延续上一镜的门洞外冷天光",
        }
    )

    return ScenePromptSpec(
        schemaVersion="1.2",
        sceneId="demo-wunianzai-final-kitchen",
        title="掀锅与按锅",
        summary="差役掀翻铁锅，郎君从泥地起身按住锅沿。",
        visualStyle="写实历史灾荒片，灰褐低饱和，阴冷天光，泥地铁器质感。",
        globalDirection="人物、衣着、土灶、动作轴一致，无背景音乐。",
        # Super 35 球面成像保持真实空间透视，统一动作方向并遵守 180 度轴线。
        cinematographyBase=CinematographyBase(
            captureFormat="super_35",
            lensProjection="spherical",
            frameRateFps=24,
            shutterAngleDegrees=180,
            axisRule="maintain_180",
            screenDirection="left_to_right",
        ),
        # 全场以 6500K 门洞外冷天光为基线，第三镜只增加有画内动机的轮廓光。
        lightingSetup=LightingSetup(
            exposureStyle="low_key",
            ambientSource="院落左后方门洞外冷天光",
            ambientColorTemperatureK=6500,
            keyToFillStops=4,
            negativeFillSide="camera_right",
            atmosphere="冷湿空气与汤汽保留轻微体积层次",
        ),
        assets=[
            AssetBinding(
                assetId="fixture-langjun-identity-v1",
                modality="image",
                duty="identity",
                bindingScope="canon_slot",
                settingReference=SettingReference(kind="character", id="langjun"),
                featureDomain="character_identity",
                targetEntity="郎君",
                includeFeatures=["五官", "发型", "体态"],
                excludeFeatures=["背景", "姿势"],
                isFixture=True,
            ),
            AssetBinding(
                assetId="fixture-yard-layout-v1",
                modality="image",
                duty="scene",
                bindingScope="canon_slot",
                settingReference=SettingReference(kind="location", id="yard"),
                featureDomain="location",
                targetEntity="院落土灶",
                includeFeatures=["布局", "土灶方位", "阴冷天光"],
                excludeFeatures=["图中人物"],
                isFixture=True,
            ),
            AssetBinding(
                assetId="fixture-pot-bowls-v1",
                modality="image",
                duty="prop",
                bindingScope="canon_slot",
                settingReference=SettingReference(kind="item", id="pot-bowls"),
                featureDomain="prop",
                targetEntity="铁锅和粗陶碗",
                includeFeatures=["外形", "材质"],
                excludeFeatures=["背景"],
                isFixture=True,
            ),
            AssetBinding(
                assetId="fixture-pot-motion-v1",
                modality="video",
                duty="motion",
                featureDomain="motion",
                targetEntity="掀锅动作",
                includeFeatures=["发力", "翻倒节奏"],
                excludeFeatures=["人物身份", "场景", "运镜"],
                isFixture=True,
            ),
            AssetBinding(
                assetId="fixture-langjun-voice-v1",
                modality="audio",
                duty="voice",
                bindingScope="canon_slot",
                settingReference=SettingReference(kind="character", id="langjun"),
                featureDomain="voice",
                targetEntity="郎君声音",
                includeFeatures=["低哑气声"],
                excludeFeatures=["原台词", "背景音乐"],
                isFixture=True,
            ),
        ],
        beats=[
            CameraBeatSpec(
                beatId="beat-1",
                startSecond=0,
                endSecond=5,
                shotSize="全景",
                cameraAngle="低机位",
                cameraMovement="缓慢前移",
                action="差役挑住锅沿，锅沿向外受力；差役踹松灶石，灶石松动",
                actionUnits=[
                    CameraActionUnit(
                        subject="差役",
                        action="挑住锅沿",
                        visibleResult="锅沿向外受力",
                    ),
                    CameraActionUnit(
                        subject="差役",
                        action="踹松灶石",
                        visibleResult="灶石松动",
                    ),
                ],
                actionComplexity="simple",
                shotProgression=CameraShotProgression(
                    startShotSize="全景",
                    endShotSize="全景",
                    changeMode="continuous",
                ),
                # 40mm 建立人物、土灶与铁锅关系，轨道车只执行一次缓慢推进。
                cameraSpec=ShotCameraSpec(
                    lensType="prime",
                    focalLengthMm=40,
                    endFocalLengthMm=40,
                    tStop=4,
                    position=CameraPositionSpec(
                        heightCm=85,
                        azimuthDegrees=-25,
                        elevationDegrees=-4,
                        rollDegrees=0,
                        subjectDistanceMeters=4.5,
                        axisSide="screen_left",
                    ),
                    composition=CameraCompositionSpec(
                        rule="leading_lines",
                        subjectPlacement="right_third",
                        subjectFramePercent=45,
                        headroom="standard",
                        foregroundLayer="泥地与松动灶石",
                        backgroundLayer="院墙和退后的家人",
                    ),
                    movement=CameraMovementSpec(
                        support="dolly",
                        movementType="dolly_in",
                        travelDistanceMeters=0.6,
                        rotationDegrees=0,
                        speed="slow",
                        easing="ease_in_out",
                    ),
                    focus=CameraFocusSpec(
                        depthOfField="medium",
                        startTarget="差役、铁锅与土灶关系平面",
                        endTarget="差役、铁锅与土灶关系平面",
                        transition="locked",
                        rackDurationSeconds=0,
                    ),
                ),
                lightingCue=established_cold_daylight,
                sound="<木杆刮铁><灶石松动>",
                referencedAssetIds=["fixture-yard-layout-v1", "fixture-pot-bowls-v1"],
            ),
            CameraBeatSpec(
                beatId="beat-2",
                startSecond=5,
                endSecond=10,
                shotSize="中景",
                cameraAngle="平视同轴",
                cameraMovement="小幅横移",
                action="铁锅向外翻倒，锅底离开土灶；热汤泼入泥地，泥地升起热气；空碗向后传递，碗落入后方手中",
                actionUnits=[
                    CameraActionUnit(
                        subject="铁锅",
                        action="向外翻倒",
                        visibleResult="锅底离开土灶",
                    ),
                    CameraActionUnit(
                        subject="热汤",
                        action="泼入泥地",
                        visibleResult="泥地升起热气",
                    ),
                    CameraActionUnit(
                        subject="空碗",
                        action="向后传递",
                        visibleResult="碗落入后方手中",
                    ),
                ],
                actionComplexity="transformation",
                shotProgression=CameraShotProgression(
                    startShotSize="中景",
                    endShotSize="中景",
                    changeMode="continuous",
                ),
                # 65mm 压缩动作关系，滑轨横移并把焦点从翻锅平面交给回传空碗。
                cameraSpec=ShotCameraSpec(
                    lensType="prime",
                    focalLengthMm=65,
                    endFocalLengthMm=65,
                    tStop=4,
                    position=CameraPositionSpec(
                        heightCm=110,
                        azimuthDegrees=-20,
                        elevationDegrees=0,
                        rollDegrees=0,
                        subjectDistanceMeters=3,
                        axisSide="screen_left",
                    ),
                    composition=CameraCompositionSpec(
                        rule="rule_of_thirds",
                        subjectPlacement="right_third",
                        subjectFramePercent=55,
                        headroom="standard",
                        foregroundLayer="翻倒的铁锅和汤汽",
                        backgroundLayer="沿固定方向回传的空碗",
                    ),
                    movement=CameraMovementSpec(
                        support="slider",
                        movementType="truck_right",
                        travelDistanceMeters=0.35,
                        rotationDegrees=0,
                        speed="slow",
                        easing="ease_out",
                    ),
                    focus=CameraFocusSpec(
                        depthOfField="medium",
                        startTarget="翻倒的铁锅缺沿",
                        endTarget="后方接住的粗陶空碗",
                        transition="rack_focus",
                        rackDurationSeconds=1.2,
                    ),
                ),
                lightingCue=inherited_cold_daylight,
                sound="<铁锅撞石><汤落泥地>",
                referencedAssetIds=["fixture-pot-bowls-v1", "fixture-pot-motion-v1"],
            ),
            CameraBeatSpec(
                beatId="beat-3",
                startSecond=10,
                endSecond=15,
                shotSize="近景",
                cameraAngle="平视",
                cameraMovement="跟随起身并推近手部",
                action="郎君撑地起身，身体进入近景；郎君按住锅沿，铁锅停止翻动；郎君低声说{住手}，众人动作停住",
                actionUnits=[
                    CameraActionUnit(
                        subject="郎君",
                        action="撑地起身",
                        visibleResult="身体进入近景",
                    ),
                    CameraActionUnit(
                        subject="郎君",
                        action="按住锅沿",
                        visibleResult="铁锅停止翻动",
                    ),
                    CameraActionUnit(
                        subject="郎君",
                        action="低声说{住手}",
                        visibleResult="众人动作停住",
                    ),
                ],
                actionComplexity="simple",
                shotProgression=CameraShotProgression(
                    startShotSize="近景",
                    endShotSize="特写",
                    changeMode="continuous",
                ),
                # 35mm 稳定器单次跟随起身，拉焦把叙事重心从受伤手背交到郎君眼睛。
                cameraSpec=ShotCameraSpec(
                    lensType="prime",
                    focalLengthMm=35,
                    endFocalLengthMm=35,
                    tStop=2.8,
                    position=CameraPositionSpec(
                        heightCm=75,
                        azimuthDegrees=-15,
                        elevationDegrees=-2,
                        rollDegrees=0,
                        subjectDistanceMeters=2.2,
                        axisSide="screen_left",
                    ),
                    composition=CameraCompositionSpec(
                        rule="rule_of_thirds",
                        subjectPlacement="left_third",
                        subjectFramePercent=65,
                        headroom="tight",
                        foregroundLayer="撑在泥地上的受伤手",
                        backgroundLayer="铁锅与回头的差役",
                    ),
                    movement=CameraMovementSpec(
                        support="gimbal",
                        movementType="handheld_follow",
                        travelDistanceMeters=0.9,
                        rotationDegrees=0,
                        speed="medium",
                        easing="ease_out",
                    ),
                    focus=CameraFocusSpec(
                        depthOfField="shallow",
                        startTarget="郎君按住锅沿的受伤手背",
                        endTarget="郎君抬起的眼睛",
                        transition="rack_focus",
                        rackDurationSeconds=1.6,
                    ),
                ),
                # 云层裂开是画内可见动机，只新增 5600K 轮廓光和汤汽体积光。
                lightingCue=ShotLightingCue(
                    continuityMode="motivated_change",
                    motivatedChange="云层裂开，院门外冷光穿过翻锅汤汽",
                    keyLight=established_cold_daylight.keyLight,
                    fillStrategy="negative_fill",
                    fillDirection="front_right",
                    fillRelativeStops=-4,
                    edgeLight=LightSourceSpec(
                        role="rim",
                        motivatedBy="云层裂开后的院门外冷光",
                        direction="back_right",
                        azimuthDegrees=140,
                        elevationDegrees=25,
                        quality="hard",
                        delivery="direct",
                        colorTemperatureK=5600,
                        relativeExposureStops=0.5,
                        beamAngleDegrees=24,
                        falloff="medium",
                        spillControl="院门和汤汽限制光束范围",
                        visibleResult="郎君肩线、手背与汤汽出现窄轮廓和体积光",
                    ),
                    atmosphere="汤汽被门洞窄光束短暂勾亮",
                    visibleResult="郎君从泥地起身的轮廓与按锅动作清晰分离",
                ),
                sound="<寒风><铁锅余响>，低哑气声",
                transition="尾帧保持手压锅沿的构图",
                referencedAssetIds=[
                    "fixture-langjun-identity-v1",
                    "fixture-pot-bowls-v1",
                    "fixture-langjun-voice-v1",
                ],
            ),
        ],
        negativeConstraints=["换脸", "增减人物", "道具变形", "逆重力", "字幕", "水印", "随机音乐"],
        output=SeedanceOutputSpec(durationSeconds=15),
    )


def main() -> None:
    package = SeedancePromptCompiler().compile(build_demo_scene())
    print(json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
