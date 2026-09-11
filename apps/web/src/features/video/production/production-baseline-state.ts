import type {
  ProductionCapability,
  ProductionKeyframeInput,
  ProductionKeyframeRole,
  StoryboardVersion,
} from "./types";

export const PRODUCTION_KEYFRAME_ROLES: readonly ProductionKeyframeRole[] = [
  "initial_state",
  "transition_anchor",
  "end_state",
];

export type ProductionKeyframeSelection = Record<
  string,
  Partial<Record<ProductionKeyframeRole, string>>
>;

/** 浏览器仅恢复可识别的镜头版本、角色和素材身份，不猜测损坏数据。 */
export function restoreProductionKeyframeSelection(value: unknown): ProductionKeyframeSelection {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const restored: ProductionKeyframeSelection = {};
  for (const [shotVersionId, rawRoles] of Object.entries(value)) {
    if (!shotVersionId || !rawRoles || typeof rawRoles !== "object" || Array.isArray(rawRoles)) continue;
    const roles: Partial<Record<ProductionKeyframeRole, string>> = {};
    for (const role of PRODUCTION_KEYFRAME_ROLES) {
      const assetId = (rawRoles as Record<string, unknown>)[role];
      if (typeof assetId === "string" && assetId.trim()) roles[role] = assetId;
    }
    if (Object.keys(roles).length) restored[shotVersionId] = roles;
  }
  return restored;
}

/** 请求顺序固定为正式分镜顺序和首帧、转折帧、尾帧，便于生成稳定清单。 */
export function productionKeyframeInputs(
  storyboard: StoryboardVersion,
  selection: ProductionKeyframeSelection,
): ProductionKeyframeInput[] {
  return storyboard.shots.flatMap((shot) => PRODUCTION_KEYFRAME_ROLES.flatMap((role) => {
    const assetId = selection[shot.id]?.[role];
    return assetId ? [{ shotVersionId: shot.id, role, assetId }] : [];
  }));
}

export function productionKeyframeProblems(
  storyboard: StoryboardVersion,
  selection: ProductionKeyframeSelection,
  availableAssetIds: ReadonlySet<string>,
  maxImages: number,
): string[] {
  return storyboard.shots.flatMap((shot, index) => {
    const selected = PRODUCTION_KEYFRAME_ROLES.flatMap((role) => {
      const assetId = selection[shot.id]?.[role];
      return assetId ? [{ role, assetId }] : [];
    });
    const problems: string[] = [];
    if (shot.content.productionIntent.references.length + selected.length > maxImages) {
      problems.push(`镜头 ${index + 1} 的视觉参考与关键帧合计超过 ${maxImages} 张`);
    }
    if (selected.some(({ assetId }) => !availableAssetIds.has(assetId))) {
      problems.push(`镜头 ${index + 1} 选择了已不在批准定妆版本中的关键帧素材`);
    }
    return problems;
  });
}

/** 正式分镜保留历史输入；只有精确符合当前服务端能力时才允许据此新建制作基线。 */
export function productionCapabilityProblems(
  storyboard: StoryboardVersion,
  capability: ProductionCapability,
): string[] {
  return storyboard.document.shots?.flatMap((shot, index) => {
    const intent = shot.productionIntent;
    const mismatched = intent.provider !== capability.provider
      || intent.model !== capability.model
      || intent.generationMode !== capability.generationMode
      || intent.executionMode !== capability.executionMode
      || intent.resolution !== capability.allowedResolution
      || intent.outputFormat !== capability.allowedOutputFormat
      || !capability.allowedDurationSeconds.includes(intent.durationSeconds)
      || intent.references.length > capability.maxImageReferences
      || (capability.feeConfirmationRequired && !intent.feeConfirmed)
      || (capability.executionMode === "live" && (!capability.providerConfigured || !capability.providerEnabled));
    return mismatched ? [`镜头 ${index + 1} 的冻结能力与服务端当前允许值不同`] : [];
  }) ?? [];
}
