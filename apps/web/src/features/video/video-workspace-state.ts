export type VideoStage = "source" | "foundation" | "settings" | "direction" | "package";

export const VIDEO_STAGES: ReadonlyArray<{ value: VideoStage; label: string }> = [
  { value: "source", label: "原文事件" },
  { value: "foundation", label: "场景地基" },
  { value: "settings", label: "设定素材" },
  { value: "direction", label: "导演方案" },
  { value: "package", label: "提示词包" },
];

export type VideoPlanAssetView = {
  slotId: string;
  bindingScope: "canon_slot" | "scene_direct";
  modality: "image" | "video" | "audio";
  duty: string;
  targetEntity: string;
  includeFeatures: string[];
  excludeFeatures: string[];
  settingKind: string | null;
  settingSourceId: string | null;
};

export type VideoPlanBeatView = {
  beatId: string;
  startSecond: number;
  endSecond: number;
  dramaticPurpose: string;
  performanceDirection: string;
  blocking: string;
  cameraMotivation: string;
  axisTransition: string;
  shotSize: string;
  cameraMovement: string;
  lens: string;
  cameraPosition: string;
  composition: string;
  focus: string;
  lighting: string;
  sound: string;
  action: string;
};

export type VideoPlanTechnicalBaseView = {
  cinematography: string;
  lighting: string;
};

export type VideoFoundationVersion = "candidate" | "formal" | "none";

type VideoFoundationSceneState = {
  status: string;
  plan: unknown | null;
  candidatePlan: unknown | null;
  reviewArtifact: { status: string } | null;
};

const LABELS = {
  captureFormat: { super_35: "Super 35", full_frame: "全画幅" },
  lensProjection: { spherical: "球面镜头", anamorphic: "变形宽银幕镜头" },
  lensType: { prime: "定焦", zoom: "变焦", macro_prime: "微距定焦" },
  exposureStyle: { low_key: "低调光", balanced: "均衡曝光", high_key: "高调光" },
  axisRule: {
    maintain_180: "遵守180度轴线",
    intentional_cross: "仅在明确切点有意越轴",
    not_applicable: "无人物轴线",
  },
  screenDirection: {
    left_to_right: "由左向右",
    right_to_left: "由右向左",
    neutral: "方向中性",
  },
  composition: {
    centered: "中心构图",
    rule_of_thirds: "三分法构图",
    symmetrical: "对称构图",
    leading_lines: "引导线构图",
    frame_within_frame: "框中框构图",
    negative_space: "负空间构图",
  },
  placement: {
    left_third: "左三分之一",
    center: "中心",
    right_third: "右三分之一",
    lower_center: "下部中心",
    upper_center: "上部中心",
  },
  depthOfField: { shallow: "浅景深", medium: "中等景深", deep: "深景深" },
  lightQuality: { hard: "硬质", soft: "柔和" },
  lightDelivery: { direct: "直射", diffused: "柔化直射", bounced: "反射" },
  continuity: {
    establish: "建立灯光",
    inherit: "延续上一镜",
    motivated_change: "有动机变化",
  },
  negativeFill: {
    none: "无",
    camera_left: "机位左侧",
    camera_right: "机位右侧",
    both: "机位两侧",
  },
  support: {
    tripod: "三脚架",
    slider: "滑轨",
    dolly: "轨道车",
    gimbal: "手持稳定器",
    steadicam: "斯坦尼康",
    handheld: "手持",
    shoulder: "肩扛",
    jib: "小摇臂",
    crane: "摄影升降机",
  },
  movement: {
    locked_off: "锁定机位",
    dolly_in: "推进",
    dolly_out: "后退",
    truck_left: "向左横移",
    truck_right: "向右横移",
    pan_left: "向左摇摄",
    pan_right: "向右摇摄",
    tilt_up: "向上俯仰",
    tilt_down: "向下俯仰",
    pedestal_up: "垂直升高",
    pedestal_down: "垂直降低",
    arc_left: "向左环绕",
    arc_right: "向右环绕",
    boom_up: "摇臂上升",
    boom_down: "摇臂下降",
    zoom_in: "光学变焦推近",
    zoom_out: "光学变焦拉远",
    handheld_follow: "手持跟随",
  },
  speed: { static: "静止", very_slow: "极慢", slow: "缓慢", medium: "中速", fast: "快速" },
  easing: { none: "匀速", ease_in: "缓入", ease_out: "缓出", ease_in_out: "缓入缓出" },
  lightDirection: {
    front: "正面",
    front_left: "左前方",
    front_right: "右前方",
    side_left: "左侧",
    side_right: "右侧",
    back_left: "左后方",
    back_right: "右后方",
    back: "正后方",
    top: "正上方",
    bottom: "下方",
  },
  fillStrategy: {
    none: "无补光",
    soft_fill: "柔和补光",
    bounce_fill: "反射补光",
    negative_fill: "负补光",
  },
  axisTransition: {
    hold: "保持轴线侧",
    continuous_cross: "连续可见越轴",
    neutral_reset: "中性机位重置",
    cutaway_reset: "切出镜头重置",
  },
} as const;

export function parseVideoStage(value: unknown): VideoStage {
  return VIDEO_STAGES.some((stage) => stage.value === value) ? value as VideoStage : "source";
}

// 正式方案永远优先；候选只有处于作者待审状态时才可见，避免旧候选混入正式版本或返工中的画面。
export function resolveVideoFoundationVersion(
  scene: VideoFoundationSceneState | null,
): VideoFoundationVersion {
  if (!scene) return "none";
  if (scene.plan) return "formal";
  if (
    scene.status === "awaiting_review"
    && scene.candidatePlan
    && scene.reviewArtifact?.status === "awaiting_user"
  ) return "candidate";
  return "none";
}

export function readVideoPlanAssets(plan: unknown): VideoPlanAssetView[] {
  const record = asRecord(plan);
  if (!record || !Array.isArray(record.assets)) return [];
  return record.assets.flatMap((value) => {
    const asset = asRecord(value);
    const slotId = stringValue(asset?.assetId);
    const bindingScope = asset?.bindingScope;
    const modality = asset?.modality;
    if (
      !slotId
      || (bindingScope !== "canon_slot" && bindingScope !== "scene_direct")
      || (modality !== "image" && modality !== "video" && modality !== "audio")
    ) return [];
    const reference = asRecord(asset?.settingReference);
    return [{
      slotId,
      bindingScope,
      modality,
      duty: stringValue(asset?.duty),
      targetEntity: stringValue(asset?.targetEntity),
      includeFeatures: stringArray(asset?.includeFeatures),
      excludeFeatures: stringArray(asset?.excludeFeatures),
      settingKind: nullableString(reference?.kind),
      settingSourceId: nullableString(reference?.id),
    }];
  });
}

export function readVideoPlanBeats(plan: unknown): VideoPlanBeatView[] {
  const record = asRecord(plan);
  if (!record || !Array.isArray(record.beats)) return [];
  return record.beats.flatMap((value) => {
    const beat = asRecord(value);
    const beatId = stringValue(beat?.beatId);
    const startSecond = numberValue(beat?.startSecond);
    const endSecond = numberValue(beat?.endSecond);
    if (!beatId || startSecond === null || endSecond === null) return [];
    const camera = asRecord(beat?.cameraSpec);
    const position = asRecord(camera?.position);
    const composition = asRecord(camera?.composition);
    const focus = asRecord(camera?.focus);
    const lighting = asRecord(beat?.lightingCue);
    const keyLight = asRecord(lighting?.keyLight);
    return [{
      beatId,
      startSecond,
      endSecond,
      dramaticPurpose: stringValue(beat?.dramaticPurpose),
      performanceDirection: stringValue(beat?.performanceDirection),
      blocking: stringValue(beat?.blocking),
      cameraMotivation: stringValue(beat?.cameraMotivation),
      axisTransition: labelValue(LABELS.axisTransition, beat?.axisTransition),
      shotSize: stringValue(beat?.shotSize),
      cameraMovement: formatCameraMovement(camera, beat),
      lens: formatLens(camera),
      cameraPosition: formatCameraPosition(position),
      composition: formatComposition(composition),
      focus: formatFocus(focus),
      lighting: formatLighting(lighting, keyLight),
      sound: stringValue(beat?.sound),
      action: stringValue(beat?.action),
    }];
  });
}

export function readVideoPlanTechnicalBase(plan: unknown): VideoPlanTechnicalBaseView {
  const record = asRecord(plan);
  const camera = asRecord(record?.cinematographyBase);
  const lighting = asRecord(record?.lightingSetup);
  const captureFormat = labelValue(LABELS.captureFormat, camera?.captureFormat);
  const projection = labelValue(LABELS.lensProjection, camera?.lensProjection);
  const frameRate = numberValue(camera?.frameRateFps);
  const shutter = numberValue(camera?.shutterAngleDegrees);
  const axis = labelValue(LABELS.axisRule, camera?.axisRule);
  const direction = labelValue(LABELS.screenDirection, camera?.screenDirection);
  const cinematography = compactParts([
    captureFormat,
    projection,
    frameRate === null ? "" : `${frameRate}fps`,
    shutter === null ? "" : `${shutter}°快门`,
    axis,
    direction,
  ]);

  const exposure = labelValue(LABELS.exposureStyle, lighting?.exposureStyle);
  const ambientSource = stringValue(lighting?.ambientSource);
  const ambientCct = numberValue(lighting?.ambientColorTemperatureK);
  const whiteBalance = numberValue(lighting?.cameraWhiteBalanceK);
  const ratio = numberValue(lighting?.keyToFillStops);
  const negativeFill = labelValue(LABELS.negativeFill, lighting?.negativeFillSide);
  const atmosphere = stringValue(lighting?.atmosphere);
  return {
    cinematography,
    lighting: compactParts([
      exposure,
      whiteBalance === null ? "" : `白平衡 ${whiteBalance}K`,
      ambientSource && ambientCct !== null ? `${ambientSource} ${ambientCct}K` : ambientSource,
      ratio === null ? "" : `主补光差 ${ratio} 档`,
      negativeFill ? `负补光 ${negativeFill}` : "",
      atmosphere,
    ]),
  };
}

export function buildPreviewReadiness(
  assets: VideoPlanAssetView[],
  selections: Readonly<Record<string, string>>,
): { resolvedSlotIds: string[]; missingSlotIds: string[] } {
  const resolvedSlotIds: string[] = [];
  const missingSlotIds: string[] = [];
  for (const asset of assets) {
    if (selections[asset.slotId]) resolvedSlotIds.push(asset.slotId);
    else missingSlotIds.push(asset.slotId);
  }
  return { resolvedSlotIds, missingSlotIds };
}

export function buildVideoWorkspaceSearch(input: {
  currentSearch: string;
  projectId: string | null;
  sceneId: string | null;
  stage: VideoStage;
}): string {
  const params = new URLSearchParams(input.currentSearch);
  setOrDelete(params, "videoProjectId", input.projectId);
  setOrDelete(params, "videoSceneId", input.sceneId);
  params.set("videoStage", input.stage);
  return params.toString();
}

function formatLens(camera: Record<string, unknown> | null): string {
  const lensType = labelValue(LABELS.lensType, camera?.lensType);
  const start = numberValue(camera?.focalLengthMm);
  const end = numberValue(camera?.endFocalLengthMm);
  const tStop = numberValue(camera?.tStop);
  if (!lensType || start === null || end === null || tStop === null) return "";
  const focal = start === end ? `${start}mm` : `${start}→${end}mm`;
  return `${focal} ${lensType} · T${tStop}`;
}

function formatCameraPosition(position: Record<string, unknown> | null): string {
  const height = numberValue(position?.heightCm);
  const azimuth = numberValue(position?.azimuthDegrees);
  const elevation = numberValue(position?.elevationDegrees);
  const distance = numberValue(position?.subjectDistanceMeters);
  if ([height, azimuth, elevation, distance].some((value) => value === null)) return "";
  return `机位高 ${height}cm · 方位 ${azimuth}° · 俯仰 ${elevation}° · 距主体 ${distance}m`;
}

function formatCameraMovement(
  camera: Record<string, unknown> | null,
  beat: Record<string, unknown> | null,
): string {
  const movement = asRecord(camera?.movement);
  if (!movement) return stringValue(beat?.cameraMovement);
  const support = labelValue(LABELS.support, movement.support);
  const movementType = labelValue(LABELS.movement, movement.movementType);
  const speed = labelValue(LABELS.speed, movement.speed);
  const easing = labelValue(LABELS.easing, movement.easing);
  const travel = numberValue(movement.travelDistanceMeters);
  const rotation = numberValue(movement.rotationDegrees);
  return compactParts([
    support,
    speed,
    movementType,
    travel ? `位移 ${travel}m` : "",
    rotation ? `旋转 ${rotation}°` : "",
    easing,
  ]);
}

function formatComposition(composition: Record<string, unknown> | null): string {
  const rule = labelValue(LABELS.composition, composition?.rule);
  const placement = labelValue(LABELS.placement, composition?.subjectPlacement);
  const framePercent = numberValue(composition?.subjectFramePercent);
  const foreground = stringValue(composition?.foregroundLayer);
  const background = stringValue(composition?.backgroundLayer);
  return compactParts([
    rule,
    placement && framePercent !== null ? `主体 ${placement} / ${framePercent}%` : placement,
    foreground ? `前景 ${foreground}` : "",
    background ? `背景 ${background}` : "",
  ]);
}

function formatFocus(focus: Record<string, unknown> | null): string {
  const depth = labelValue(LABELS.depthOfField, focus?.depthOfField);
  const start = stringValue(focus?.startTarget);
  const end = stringValue(focus?.endTarget);
  const transition = stringValue(focus?.transition);
  const duration = numberValue(focus?.rackDurationSeconds);
  if (!depth || !start) return "";
  if (transition === "rack_focus" && end && duration !== null) {
    return `${depth} · ${duration}秒从${start}拉焦到${end}`;
  }
  return `${depth} · 锁焦${start}`;
}

function formatLighting(
  lighting: Record<string, unknown> | null,
  keyLight: Record<string, unknown> | null,
): string {
  if (!lighting || !keyLight) return "";
  const continuity = labelValue(LABELS.continuity, lighting.continuityMode);
  const motivation = stringValue(lighting.motivatedChange);
  const source = stringValue(keyLight.motivatedBy);
  const direction = labelValue(LABELS.lightDirection, keyLight.direction);
  const cct = numberValue(keyLight.colorTemperatureK);
  const quality = labelValue(LABELS.lightQuality, keyLight.quality);
  const delivery = labelValue(LABELS.lightDelivery, keyLight.delivery);
  const exposure = numberValue(keyLight.relativeExposureStops);
  const beam = numberValue(keyLight.beamAngleDegrees);
  const fill = labelValue(LABELS.fillStrategy, lighting.fillStrategy);
  const fillStops = numberValue(lighting.fillRelativeStops);
  const result = stringValue(lighting.visibleResult);
  return compactParts([
    motivation ? `${continuity}：${motivation}` : continuity,
    source,
    compactParts([
      cct === null ? "" : `${cct}K`,
      quality,
      delivery,
      direction,
      exposure === null ? "" : `${exposure >= 0 ? "+" : ""}${exposure}档`,
      beam === null ? "" : `束角${beam}°`,
    ]),
    fill && fillStops !== null ? `${fill} ${fillStops}档` : fill,
    result,
  ]);
}

function compactParts(parts: Array<string | null | undefined>): string {
  return parts.filter((part): part is string => Boolean(part)).join(" · ");
}

function labelValue(labels: Readonly<Record<string, string>>, value: unknown): string {
  return typeof value === "string" ? labels[value] ?? value : "";
}

function setOrDelete(params: URLSearchParams, key: string, value: string | null): void {
  if (value) params.set(key, value);
  else params.delete(key);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
