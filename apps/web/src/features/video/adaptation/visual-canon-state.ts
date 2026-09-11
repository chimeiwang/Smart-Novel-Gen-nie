import type {
  VisualCanon,
  VisualCanonVersion,
  VideoProject,
} from "./types";

/** 设定卡的界面投影；业务字段仍来自生成的公共契约。 */
export type VisualSetting = {
  id: string;
  kind: VisualCanon["settingKind"];
  name: string;
  summary: string;
};

export type VisualCandidateDraft = {
  clientRequestId: string;
  canonId: string | null;
  expectedRevision: number;
  duty: VisualCanon["duty"];
  variantKey: string;
  label: string;
  includeFeatures: string;
  excludeFeatures: string;
  defaultStrength: number;
};

export function createVisualCandidateDraft(duty: VisualCanon["duty"], requestId: string, canon?: VisualCanon): VisualCandidateDraft {
  const current = canon ? currentCanonVersion(canon) : null;
  return {
    clientRequestId: requestId,
    canonId: canon?.id ?? null,
    expectedRevision: canon?.revision ?? 0,
    duty,
    variantKey: canon?.variantKey ?? visualVariantKey(requestId),
    label: canon?.label ?? ({ identity: "标准定妆", costume: "日常服装", scene: "场景主视图", prop: "道具外形" }[duty]),
    includeFeatures: (canon?.candidateAsset ? canon.candidateIncludeFeatures : current?.includeFeatures ?? []).join("，"),
    excludeFeatures: (canon?.candidateAsset ? canon.candidateExcludeFeatures : current?.excludeFeatures ?? []).join("，"),
    defaultStrength: canon?.candidateDefaultStrength ?? current?.defaultStrength ?? 70,
  };
}

export function rebaseVisualCandidateDraft(draft: VisualCandidateDraft, latest: VisualCanon, requestId: string): VisualCandidateDraft {
  if (latest.duty !== draft.duty || latest.variantKey !== draft.variantKey || (draft.canonId !== null && latest.id !== draft.canonId)) {
    throw new Error("不能把候选修改保存到另一个定妆变体。");
  }
  return { ...draft, canonId: latest.id, expectedRevision: latest.revision, clientRequestId: requestId };
}

export function visualDuties(kind: VisualSetting["kind"]): VisualCanon["duty"][] {
  return kind === "character" ? ["identity", "costume"] : kind === "location" ? ["scene"] : ["prop"];
}

export function selectSeriesProject(projects: VideoProject[], selectedId?: string | null): VideoProject | null {
  const series = projects.filter((project) => project.mode === "series");
  return series.find((project) => project.id === selectedId) ?? series[0] ?? null;
}

export function visualVariantKey(requestId: string): string {
  return `variant_${requestId.replace(/[^a-z0-9]/gi, "").toLowerCase()}`;
}

export function parseVisualFeatures(value: string): string[] {
  const features = [...new Set(value.split(/[，,\n]/).map((part) => part.trim()).filter(Boolean))];
  if (features.length > 20) throw new Error("保留或排除特征各最多填写 20 项，请精简后保存。");
  if (features.some((feature) => Array.from(feature).length > 120)) throw new Error("每项视觉特征最多 120 字，请拆分或精简后保存。");
  return features;
}

export function currentCanonVersion(canon: VisualCanon): VisualCanonVersion | null {
  return canon.versions.find((version) => version.id === canon.currentVersionId) ?? null;
}

export function dutyLabel(duty: VisualCanon["duty"]): string {
  return {
    identity: "身份图",
    costume: "服装图",
    scene: "场景图",
    prop: "道具图",
  }[duty];
}

export function assetPreviewUrl(assetId: string): string {
  return `/api/v1/video/assets/${encodeURIComponent(assetId)}/preview`;
}
