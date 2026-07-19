import type { components } from "@inkforge/api-client";

type ShortStoryAggregate = components["schemas"]["ShortStoryArtifactsResponse"];
type ShortStoryArtifact = components["schemas"]["ShortStoryArtifactResponse"];
type ShortStoryOutlineDraft = components["schemas"]["ShortStoryOutlineDraft"];
type ReviewArtifact = components["schemas"]["ReviewArtifactResponse"];

export type OutlineEditorBase = {
  artifactId: string;
  revision: number;
};

export function createOutlineEditorBase(
  artifact: Pick<ShortStoryArtifact, "id" | "revision">,
): OutlineEditorBase {
  return { artifactId: artifact.id, revision: artifact.revision };
}

export function shouldAdoptAggregateOutline({
  dirty,
  base,
  next,
}: {
  dirty: boolean;
  base: OutlineEditorBase | null;
  next: Pick<ShortStoryArtifact, "id" | "revision">;
}): boolean {
  if (dirty) return false;
  return base === null
    || base.artifactId !== next.id
    || base.revision !== next.revision;
}

function toShortStoryOutlineArtifact(saved: ReviewArtifact): ShortStoryArtifact {
  const payload = saved.payload;
  if (
    saved.kind !== "outline_draft"
    || payload.kind !== "outline_draft"
    || !Array.isArray(payload.sections)
  ) {
    throw new Error("保存大纲接口返回了非大纲产物");
  }

  return {
    ...saved,
    kind: "outline_draft",
    payload: payload as ShortStoryOutlineDraft,
  };
}

export function applySavedOutlineToAggregate(
  aggregate: ShortStoryAggregate,
  saved: ReviewArtifact,
): ShortStoryAggregate {
  return {
    ...aggregate,
    outline: toShortStoryOutlineArtifact(saved),
  };
}
