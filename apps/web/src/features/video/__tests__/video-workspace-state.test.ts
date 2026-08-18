import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildPreviewReadiness,
  buildVideoWorkspaceSearch,
  parseVideoStage,
  readVideoPlanAssets,
  readVideoPlanBeats,
  readVideoPlanTechnicalBase,
  resolveVideoFoundationVersion,
} from "../video-workspace-state";

describe("长篇视频预览工作台状态", () => {
  it("只解析声明过的五个阶段", () => {
    assert.equal(parseVideoStage("settings"), "settings");
    assert.equal(parseVideoStage("render"), "source");
    assert.equal(parseVideoStage(["package"]), "source");
  });

  it("把设定槽位和场次引用分成类型化视图", () => {
    const assets = readVideoPlanAssets({
      assets: [
        {
          assetId: "setting:character:1:identity",
          bindingScope: "canon_slot",
          modality: "image",
          duty: "identity",
          targetEntity: "阿宁",
          includeFeatures: ["五官"],
          excludeFeatures: ["背景"],
          settingReference: { kind: "character", id: "character-1" },
        },
        {
          assetId: "scene:camera:1",
          bindingScope: "scene_direct",
          modality: "video",
          duty: "camera",
          targetEntity: "推轨参考",
          includeFeatures: ["轨迹"],
          excludeFeatures: [],
          settingReference: null,
        },
      ],
    });

    assert.equal(assets.length, 2);
    assert.equal(assets[0]?.settingKind, "character");
    assert.equal(assets[1]?.bindingScope, "scene_direct");
    assert.equal(assets[1]?.settingSourceId, null);
  });

  it("完整列出预览中已解析和缺失的槽位", () => {
    const assets = readVideoPlanAssets({
      assets: [
        {
          assetId: "slot-a",
          bindingScope: "canon_slot",
          modality: "image",
          duty: "identity",
          targetEntity: "阿宁",
          includeFeatures: ["五官"],
          excludeFeatures: [],
          settingReference: { kind: "character", id: "character-1" },
        },
        {
          assetId: "slot-b",
          bindingScope: "scene_direct",
          modality: "audio",
          duty: "ambience",
          targetEntity: "雨声",
          includeFeatures: ["远近变化"],
          excludeFeatures: [],
          settingReference: null,
        },
      ],
    });

    assert.deepEqual(buildPreviewReadiness(assets, { "slot-a": "asset-1" }), {
      resolvedSlotIds: ["slot-a"],
      missingSlotIds: ["slot-b"],
    });
  });

  it("把专业摄影与灯光事实转换为可审核的中文摘要", () => {
    const plan = {
      cinematographyBase: {
        captureFormat: "super_35",
        lensProjection: "spherical",
        frameRateFps: 24,
        shutterAngleDegrees: 180,
        axisRule: "maintain_180",
        screenDirection: "left_to_right",
      },
      lightingSetup: {
        exposureStyle: "low_key",
        ambientSource: "雨窗冷光",
        ambientColorTemperatureK: 6500,
        cameraWhiteBalanceK: 4300,
        keyToFillStops: 2,
        negativeFillSide: "camera_right",
        atmosphere: "薄雾",
      },
      beats: [{
        beatId: "beat-01",
        startSecond: 0,
        endSecond: 4,
        dramaticPurpose: "把迟疑转成不可逆的决定",
        performanceDirection: "林岚先屏住呼吸半拍，再稳定地抬手",
        blocking: "她从画面左侧进入，停在右三分之一位置",
        cameraMotivation: "她握紧铜扣时才推进，以强调决定的代价",
        axisTransition: "hold",
        shotSize: "近景",
        action: "林岚拔下铜扣",
        sound: "纸张吸水声",
        cameraSpec: {
          lensType: "prime",
          focalLengthMm: 40,
          endFocalLengthMm: 40,
          tStop: 2.8,
          position: {
            heightCm: 110,
            azimuthDegrees: -45,
            elevationDegrees: -8,
            subjectDistanceMeters: 1.4,
          },
          composition: {
            rule: "rule_of_thirds",
            subjectPlacement: "right_third",
            subjectFramePercent: 45,
            foregroundLayer: "湿绳",
            backgroundLayer: "齿轮",
          },
          movement: {
            support: "tripod",
            movementType: "locked_off",
            travelDistanceMeters: 0,
            rotationDegrees: 0,
            speed: "static",
            easing: "none",
          },
          focus: {
            depthOfField: "shallow",
            startTarget: "铜扣",
            endTarget: "铜扣",
            transition: "locked",
            rackDurationSeconds: 0,
          },
        },
        lightingCue: {
          continuityMode: "establish",
          motivatedChange: "建立窗外月光",
          keyLight: {
            motivatedBy: "雨窗月光",
            direction: "back_left",
            colorTemperatureK: 6500,
            quality: "hard",
            delivery: "direct",
            relativeExposureStops: 0,
            beamAngleDegrees: 25,
          },
          fillStrategy: "negative_fill",
          fillRelativeStops: -2,
          visibleResult: "湿纸和黄铜出现冷亮轮廓",
        },
      }],
    };

    const base = readVideoPlanTechnicalBase(plan);
    const [beat] = readVideoPlanBeats(plan);

    assert.match(base.cinematography, /Super 35.*24fps.*180°快门/);
    assert.match(base.lighting, /低调光.*白平衡 4300K.*6500K.*主补光差 2 档/);
    assert.match(beat?.lens ?? "", /40mm 定焦.*T2.8/);
    assert.equal(beat?.dramaticPurpose, "把迟疑转成不可逆的决定");
    assert.equal(beat?.performanceDirection, "林岚先屏住呼吸半拍，再稳定地抬手");
    assert.equal(beat?.blocking, "她从画面左侧进入，停在右三分之一位置");
    assert.equal(beat?.cameraMotivation, "她握紧铜扣时才推进，以强调决定的代价");
    assert.equal(beat?.axisTransition, "保持轴线侧");
    assert.match(beat?.cameraPosition ?? "", /机位高 110cm.*方位 -45°/);
    assert.match(beat?.lighting ?? "", /6500K.*硬质.*负补光 -2档/);
  });

  it("更新视频定位参数时保留章节和工作区参数", () => {
    assert.equal(
      buildVideoWorkspaceSearch({
        currentSearch: "chapterId=chapter-1&view=video",
        projectId: "project-1",
        sceneId: "scene-1",
        stage: "package",
      }),
      "chapterId=chapter-1&view=video&videoProjectId=project-1&videoSceneId=scene-1&videoStage=package",
    );
  });

  it("只展示当前待审候选，并让正式版本优先于残留候选", () => {
    assert.equal(resolveVideoFoundationVersion({
      status: "awaiting_review",
      plan: null,
      candidatePlan: { schemaVersion: "1.3" },
      reviewArtifact: { status: "awaiting_user" },
    }), "candidate");
    assert.equal(resolveVideoFoundationVersion({
      status: "generating",
      plan: null,
      candidatePlan: { schemaVersion: "1.2" },
      reviewArtifact: { status: "draft" },
    }), "none");
    assert.equal(resolveVideoFoundationVersion({
      status: "approved",
      plan: { schemaVersion: "1.3" },
      candidatePlan: { schemaVersion: "1.2" },
      reviewArtifact: { status: "awaiting_user" },
    }), "formal");
  });
});
