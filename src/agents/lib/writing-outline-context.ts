import type {
  OutlineNodeData,
  WritingOutlineContext,
  WritingOutlineContextNode,
} from "@/agents/graph/state";

export function resolveWritingOutlineContext(input: {
  outlineNodes: OutlineNodeData[];
  targetChapter: { id: string | null; order: number; title: string };
  hasApprovedBeatPlan: boolean;
  hasChapterWritingGoal: boolean;
}): WritingOutlineContext {
  const source = input.hasApprovedBeatPlan
    ? "approved_beat_plan" as const
    : input.hasChapterWritingGoal
      ? "chapter_goal" as const
      : "chapter_group" as const;
  const candidates = input.outlineNodes.filter((node) =>
    node.kind === "chapter_group" &&
    node.chapterStartOrder !== undefined &&
    node.chapterEndOrder !== undefined &&
    node.chapterStartOrder <= input.targetChapter.order &&
    node.chapterEndOrder >= input.targetChapter.order
  );

  if (candidates.length > 1) {
    return {
      status: "ambiguous",
      targetChapter: input.targetChapter,
      source: null,
      path: [],
      candidateIds: candidates.map((node) => node.id),
    };
  }

  if (candidates.length === 0) {
    const exactSource = input.hasApprovedBeatPlan
      ? "approved_beat_plan" as const
      : input.hasChapterWritingGoal
        ? "chapter_goal" as const
        : null;
    return {
      status: exactSource ? "resolved" : "unmapped",
      targetChapter: input.targetChapter,
      source: exactSource,
      path: [],
      candidateIds: [],
    };
  }

  const group = candidates[0];
  const byId = new Map(input.outlineNodes.map((node) => [node.id, node]));
  const unit = group.parentId ? byId.get(group.parentId) : undefined;
  const stage = unit?.parentId ? byId.get(unit.parentId) : undefined;
  if (!unit || unit.kind !== "plot_unit" || !stage || stage.kind !== "stage") {
    return {
      status: "ambiguous",
      targetChapter: input.targetChapter,
      source: null,
      path: [],
      candidateIds: [group.id],
    };
  }

  const path = [
    toContextNode(stage, false),
    toContextNode(unit, false),
    toContextNode(group, source === "chapter_group"),
  ];
  return {
    status: "resolved",
    targetChapter: input.targetChapter,
    source,
    path,
    candidateIds: [group.id],
  };
}

function toContextNode(node: OutlineNodeData, includeContent: boolean): WritingOutlineContextNode {
  return {
    id: node.id,
    kind: node.kind as WritingOutlineContextNode["kind"],
    title: node.title,
    chapterStartOrder: node.chapterStartOrder ?? null,
    chapterEndOrder: node.chapterEndOrder ?? null,
    ...(includeContent && node.content ? { content: node.content } : {}),
  };
}
