export type WritingProductActionKind =
  | "open_artifacts"
  | "plan_beat"
  | "write_draft"
  | "review_chapter"
  | "consistency_check"
  | "rewrite_scene"
  | "ooc_check";

export type WritingProductAction = {
  kind: WritingProductActionKind;
  label: string;
  description: string;
  prompt?: string;
};

export type WritingNextActionSnapshot = {
  chapterStatus?: string;
  wordCount: number;
  awaitingArtifactCount: number;
  hasApprovedBeatPlan: boolean;
  hasOpenConsistencyCheck: boolean;
};

export const WRITING_ACTION_PROMPTS: Record<Exclude<WritingProductActionKind, "open_artifacts">, string> = {
  plan_beat:
    "@剧情 请为当前章节生成一份可应用的章节计划。请拆成场景节拍，明确每场的目标、冲突、涉及角色、伏笔、预估字数和验收标准。",
  write_draft:
    "@写作 请根据当前章节、已确认章节计划（如有）、大纲、设定和文风，生成当前章节正文草案。正文进入待审核草案，先不要直接写入正式章节。",
  review_chapter:
    "@编辑 请从网文追读角度审核当前章节，重点看钩子、爽点、节奏、章节尾钩和读者承诺是否成立，并给出可执行修改建议。",
  consistency_check:
    "@校验 请检查当前章节正文与角色设定、世界规则、大纲和伏笔是否冲突，重点指出 OOC 和逻辑断裂。",
  rewrite_scene:
    "@写作 请找出当前章节最需要加强的一场戏并重写，重点补足目标、阻力、转折、代价和余波。重写内容进入待审核草案。",
  ooc_check:
    "@校验 请重点检查当前章节是否存在角色 OOC：对照角色核心欲望、行为边界、说话习惯、关系原则和短期目标，列出风险和修改建议。",
};

export const WRITING_SHORTCUT_ACTIONS: WritingProductAction[] = [
  {
    kind: "plan_beat",
    label: "规划本章",
    description: "生成章节计划",
    prompt: WRITING_ACTION_PROMPTS.plan_beat,
  },
  {
    kind: "write_draft",
    label: "生成正文",
    description: "提交正文草案",
    prompt: WRITING_ACTION_PROMPTS.write_draft,
  },
  {
    kind: "rewrite_scene",
    label: "重写场景",
    description: "加强冲突和余波",
    prompt: WRITING_ACTION_PROMPTS.rewrite_scene,
  },
  {
    kind: "review_chapter",
    label: "审核追读",
    description: "编辑视角检查",
    prompt: WRITING_ACTION_PROMPTS.review_chapter,
  },
  {
    kind: "ooc_check",
    label: "检查 OOC",
    description: "校验角色一致性",
    prompt: WRITING_ACTION_PROMPTS.ooc_check,
  },
];

export function getWritingNextActions(snapshot: WritingNextActionSnapshot): WritingProductAction[] {
  const actions: WritingProductAction[] = [];

  if (snapshot.awaitingArtifactCount > 0) {
    actions.push({
      kind: "open_artifacts",
      label: `处理 ${snapshot.awaitingArtifactCount} 条变更`,
      description: "应用、继续修改或丢弃",
    });
  }

  if (snapshot.chapterStatus === "review") {
    actions.push(snapshot.hasOpenConsistencyCheck
      ? {
          kind: "consistency_check",
          label: "预检一致性",
          description: "送审终检前先查风险",
          prompt: WRITING_ACTION_PROMPTS.consistency_check,
        }
      : {
          kind: "review_chapter",
          label: "审核追读",
          description: "检查章节商业性",
          prompt: WRITING_ACTION_PROMPTS.review_chapter,
        });
  } else if (snapshot.chapterStatus === "completed") {
    actions.push({
      kind: "review_chapter",
      label: "审核追读",
      description: "复盘已完成章节",
      prompt: WRITING_ACTION_PROMPTS.review_chapter,
    });
  } else if (!snapshot.hasApprovedBeatPlan) {
    actions.push({
      kind: "plan_beat",
      label: "规划本章",
      description: "先确认章节计划",
      prompt: WRITING_ACTION_PROMPTS.plan_beat,
    });
  } else if (snapshot.wordCount === 0) {
    actions.push({
      kind: "write_draft",
      label: "按计划写正文",
      description: "使用已确认章节计划",
      prompt: WRITING_ACTION_PROMPTS.write_draft,
    });
  } else {
    actions.push({
      kind: "review_chapter",
      label: "审核追读",
      description: "找出下一轮修改点",
      prompt: WRITING_ACTION_PROMPTS.review_chapter,
    });
  }

  return actions.slice(0, 3);
}
