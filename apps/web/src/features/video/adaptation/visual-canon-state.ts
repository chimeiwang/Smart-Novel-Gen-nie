import type {
  FormalPlan,
  FormalShot,
  ShotVisualReference,
  VisualCanon,
  VisualCanonVersion,
} from "./types";

export type VisualReferenceSelection = {
  canonVersionId: string;
  strength: number;
};

const DUTY_ORDER = { identity: 0, costume: 1, scene: 2, prop: 3 } as const;

export function currentCanonVersion(canon: VisualCanon): VisualCanonVersion | null {
  return canon.versions.find((version) => version.id === canon.currentVersionId) ?? null;
}

export function visualShotContext(plan: FormalPlan, shot: FormalShot): string {
  for (const scene of plan.scenes) {
    for (const beat of scene.beats) {
      if (!beat.shots.some((item) => item.id === shot.id)) continue;
      return [
        scene.title,
        scene.locationLabel,
        beat.title,
        beat.dramaticTurn,
        shot.title,
        shot.storyFunction,
        shot.audienceGain,
        shot.visualIntent,
        shot.spokenText ?? "",
        ...shot.sourceRanges.map((range) => range.sourceText),
      ].join("\n");
    }
  }
  return [shot.title, shot.storyFunction, shot.audienceGain, shot.visualIntent].join("\n");
}

export function recommendedVisualReferences(
  canons: VisualCanon[],
  context: string,
): VisualReferenceSelection[] {
  const normalized = normalize(context);
  return canons
    .map((canon) => ({ canon, version: currentCanonVersion(canon) }))
    .filter(({ canon, version }) => version && normalized.includes(normalize(canon.settingName)))
    .sort((left, right) => (
      DUTY_ORDER[left.canon.duty] - DUTY_ORDER[right.canon.duty]
      || left.canon.settingName.localeCompare(right.canon.settingName, "zh-CN")
      || left.canon.variantKey.localeCompare(right.canon.variantKey)
    ))
    .map(({ version }) => ({
      canonVersionId: version!.id,
      strength: version!.defaultStrength,
    }));
}

export function visualReferenceWarnings(
  canons: VisualCanon[],
  context: string,
  references: ShotVisualReference[],
): string[] {
  const normalized = normalize(context);
  const matched = canons.filter((canon) => normalized.includes(normalize(canon.settingName)));
  const warnings: string[] = [];
  for (const canon of matched) {
    const current = currentCanonVersion(canon);
    if (!current) {
      warnings.push(`${canon.settingName}的${dutyLabel(canon.duty)}还没有批准版本`);
      continue;
    }
    const bound = references.some((reference) => (
      reference.settingId === canon.settingId && reference.duty === canon.duty
    ));
    if (!bound && canon.duty !== "costume") {
      warnings.push(`${canon.settingName}的${dutyLabel(canon.duty)}尚未绑定到本镜`);
    }
  }
  return Array.from(new Set(warnings));
}

export function sameVisualReferences(
  left: ShotVisualReference[],
  right: ShotVisualReference[],
): boolean {
  if (left.length !== right.length) return false;
  return left.every((reference, index) => {
    const other = right[index];
    return Boolean(
      other
      && reference.canonVersionId === other.canonVersionId
      && reference.assetId === other.assetId
      && reference.strength === other.strength
    );
  });
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

function normalize(value: string): string {
  return value.replace(/\s+/g, "").toLocaleLowerCase("zh-CN");
}
