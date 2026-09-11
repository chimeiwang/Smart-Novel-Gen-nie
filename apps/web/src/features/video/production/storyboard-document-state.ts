import type {
  ShotReference,
  ProductionCapability,
  StoryboardDocument,
  StoryboardDraft,
  StoryboardShot,
} from "./types";

export type StoryboardWorkingDraft = Pick<
  StoryboardDraft,
  "scriptVersionId" | "baseStoryboardVersionId" | "document"
>;

export type NewStoryboardShot = {
  tempKey: string;
  scriptSceneId: string;
  title: string;
  action: string;
  prompt: string;
  references: ShotReference[];
  ratio: StoryboardShot["productionIntent"]["ratio"];
  capability: ProductionCapability;
  durationSeconds: number;
  feeConfirmed: boolean;
};

const copy = <T,>(value: T): T => structuredClone(value);

export function storyboardShotIdentity(shot: StoryboardShot): string {
  const identity = shot.id ?? shot.tempKey;
  if (!identity) throw new Error("镜头缺少稳定身份或临时身份");
  return identity;
}

/** Core 只映射新镜头身份，保存期间继续输入的镜头内容保持不变。 */
export function reconcileStoryboardShotIds(
  document: StoryboardDocument,
  mappings: Record<string, string>,
): StoryboardDocument {
  return {
    ...copy(document),
    shots: (document.shots ?? []).map((shot) => {
      if (!shot.tempKey || !mappings[shot.tempKey]) return copy(shot);
      return { ...copy(shot), id: mappings[shot.tempKey], tempKey: null };
    }),
  };
}

export function storyboardDraftFromResponse(draft: StoryboardDraft): StoryboardWorkingDraft {
  return {
    scriptVersionId: draft.scriptVersionId,
    baseStoryboardVersionId: draft.baseStoryboardVersionId,
    document: copy(draft.document),
  };
}

export function updateStoryboardShot(
  document: StoryboardDocument,
  identity: string,
  update: (shot: StoryboardShot) => StoryboardShot,
): StoryboardDocument {
  return {
    ...copy(document),
    shots: (document.shots ?? []).map((shot) => (
      storyboardShotIdentity(shot) === identity ? update(copy(shot)) : copy(shot)
    )),
  };
}

export function appendStoryboardShot(
  document: StoryboardDocument,
  input: NewStoryboardShot,
): StoryboardDocument {
  const durationSeconds = input.durationSeconds;
  const shot: StoryboardShot = {
    id: null,
    tempKey: input.tempKey,
    lineage: [],
    scriptSceneId: input.scriptSceneId,
    scriptLineIds: [],
    title: input.title,
    action: input.action,
    framing: "medium",
    cameraMovement: "static",
    durationMs: durationSeconds * 1_000,
    productionIntent: {
      provider: input.capability.provider,
      model: input.capability.model,
      generationMode: input.capability.generationMode,
      executionMode: input.capability.executionMode,
      feeConfirmed: input.feeConfirmed,
      prompt: input.prompt,
      ratio: input.ratio,
      durationSeconds,
      resolution: input.capability.allowedResolution,
      generateAudio: true,
      watermark: false,
      outputFormat: input.capability.allowedOutputFormat,
      references: copy(input.references),
    },
  };
  return { ...copy(document), shots: [...(document.shots ?? []).map(copy), shot] };
}

export function duplicateStoryboardShot(
  document: StoryboardDocument,
  identity: string,
  tempKey: string,
): StoryboardDocument | null {
  const shots = document.shots ?? [];
  const index = shots.findIndex((shot) => storyboardShotIdentity(shot) === identity);
  const source = shots[index];
  if (!source?.id) return null;
  const duplicate: StoryboardShot = {
    ...copy(source),
    id: null,
    tempKey,
    title: `${source.title}（副本）`,
    lineage: [{ sourceShotId: source.id, relation: "copy" }],
  };
  return {
    ...copy(document),
    shots: [...shots.slice(0, index + 1).map(copy), duplicate, ...shots.slice(index + 1).map(copy)],
  };
}

export function removeStoryboardShot(document: StoryboardDocument, identity: string): StoryboardDocument {
  return {
    ...copy(document),
    shots: (document.shots ?? [])
      .filter((shot) => storyboardShotIdentity(shot) !== identity)
      .map(copy),
  };
}

export function moveStoryboardShot(
  document: StoryboardDocument,
  identity: string,
  offset: -1 | 1,
): StoryboardDocument {
  const shots = (document.shots ?? []).map(copy);
  const from = shots.findIndex((shot) => storyboardShotIdentity(shot) === identity);
  const source = shots[from];
  if (from < 0 || !source) return { ...copy(document), shots };
  const siblings = shots
    .map((shot, index) => ({ shot, index }))
    .filter(({ shot }) => shot.scriptSceneId === source.scriptSceneId);
  const siblingIndex = siblings.findIndex(({ index }) => index === from);
  const target = siblings[siblingIndex + offset];
  if (!target) return { ...copy(document), shots };
  [shots[from], shots[target.index]] = [shots[target.index]!, shots[from]!];
  return { ...copy(document), shots };
}

export function storyboardDurationMs(document: StoryboardDocument): number {
  return (document.shots ?? []).reduce((total, shot) => total + shot.durationMs, 0);
}
