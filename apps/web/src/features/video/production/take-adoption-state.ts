import type {
  BaselineAdoptionInput,
  ProductionBaseline,
  StoryboardVersion,
  TakeCandidate,
} from "./types";

type SourceShot = ProductionBaseline["shots"][number];
type TargetShot = StoryboardVersion["shots"][number];

const same = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

/** 采用前只比较 Core 已冻结且会直接送入生成器的字段，语境变化仍由作者在说明中判断。 */
export function takeDirectInputDifferences(source: SourceShot, target: TargetShot): string[] {
  const sourceInput = source.inputSnapshot;
  const targetInput = target.content.productionIntent;
  const fields: Array<[string, unknown, unknown]> = [
    ["剧本场次", sourceInput.scriptSceneId, target.scriptSceneId],
    ["剧本节点", sourceInput.scriptLineIds, target.scriptLineIds],
    ["供应商", sourceInput.provider, targetInput.provider],
    ["模型", sourceInput.model, targetInput.model],
    ["生成模式", sourceInput.generationMode, targetInput.generationMode],
    ["执行模式", sourceInput.executionMode, targetInput.executionMode],
    ["费用确认", sourceInput.feeConfirmed, targetInput.feeConfirmed],
    ["提示词", sourceInput.prompt, targetInput.prompt],
    ["画幅", sourceInput.ratio, targetInput.ratio],
    ["时长", sourceInput.durationSeconds, targetInput.durationSeconds],
    ["分辨率", sourceInput.resolution, targetInput.resolution],
    ["原生声音", sourceInput.generateAudio, targetInput.generateAudio],
    ["水印", sourceInput.watermark, targetInput.watermark],
    ["输出格式", sourceInput.outputFormat, targetInput.outputFormat],
  ];
  return fields.filter(([, left, right]) => !same(left, right)).map(([label]) => label);
}

export function takeReferenceHashesForReview(source: SourceShot): string[] {
  return [...new Set(source.inputSnapshot.references.flatMap((reference) => (
    reference.sha256 && /^[0-9a-f]{64}$/.test(reference.sha256) ? [reference.sha256] : []
  )))];
}

export function takeCandidateMatchesSource(
  candidate: TakeCandidate,
  baseline: ProductionBaseline,
  source: SourceShot | null,
): boolean {
  return candidate.sourceBaselineId === baseline.id
    && source !== null
    && source.shotVersionId === candidate.sourceShotVersionId
    && source.shotId === candidate.sourceShotId
    && source.inputHash === candidate.inputHash;
}

export function baselineAdoptionInputs(
  storyboard: StoryboardVersion,
  adoptionIds: Readonly<Record<string, string>>,
): BaselineAdoptionInput[] {
  return storyboard.shots.flatMap((shot) => {
    const adoptionId = adoptionIds[shot.id];
    return adoptionId
      ? [{ shotVersionId: shot.id, adoptionId }]
      : [];
  });
}
