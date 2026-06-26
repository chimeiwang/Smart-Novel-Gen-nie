/**
 * 创作操作契约。
 *
 * CreativeOperation 是聊天入口的主抽象：先识别用户要完成的创作操作，
 * 再选择内部执行角色。Agent 仍是执行层身份，不再是入口层唯一分类结果。
 */

import { z } from "zod";
import { CoreAgentIdSchema, type CoreAgentId } from "./agent";

export const CreativeOperationKindSchema = z.enum([
  "answer_question",
  "create_lore",
  "revise_lore",
  "create_outline",
  "revise_outline",
  "plan_chapter",
  "write_chapter",
  "rewrite_scene",
  "review_chapter",
  "sync_lore",
  "manage_foreshadowing",
]);

export type CreativeOperationKind = z.infer<typeof CreativeOperationKindSchema>;

export const CreativeOperationTargetTypeSchema = z.enum([
  "novel",
  "chapter",
  "character",
  "lore",
  "outline",
  "foreshadowing",
  "scene",
  "artifact",
  "unknown",
]);

export type CreativeOperationTargetType = z.infer<typeof CreativeOperationTargetTypeSchema>;

export const CreativeOperationOutputKindSchema = z.enum([
  "chat_answer",
  "lore_proposal",
  "outline_proposal",
  "beat_plan",
  "chapter_text",
  "review_report",
  "revision_brief",
  "sync_proposal",
]);

export type CreativeOperationOutputKind = z.infer<typeof CreativeOperationOutputKindSchema>;

export const CreativeOperationSchema = z.object({
  kind: CreativeOperationKindSchema,
  targetType: CreativeOperationTargetTypeSchema,
  targetId: z.preprocess((value) => value === null ? undefined : value, z.string().optional()),
  userGoal: z.string().min(1),
  primaryAgent: CoreAgentIdSchema,
  reviewers: z.array(CoreAgentIdSchema).default([]),
  outputKind: CreativeOperationOutputKindSchema,
  requiresArtifact: z.boolean(),
  requiresUserApproval: z.boolean(),
  confidence: z.number().min(0).max(1),
  reasoning: z.string(),
});

export type CreativeOperation = z.infer<typeof CreativeOperationSchema>;

const OPERATION_LABELS: Record<CreativeOperationKind, string> = {
  answer_question: "回答问题",
  create_lore: "新建设定",
  revise_lore: "修改设定",
  create_outline: "创建大纲",
  revise_outline: "修改大纲",
  plan_chapter: "规划章节",
  write_chapter: "生成正文草案",
  rewrite_scene: "改写场景草案",
  review_chapter: "审核章节",
  sync_lore: "同步设定",
  manage_foreshadowing: "管理伏笔",
};

const OUTPUT_LABELS: Record<CreativeOperationOutputKind, string> = {
  chat_answer: "聊天答复",
  lore_proposal: "设定草案",
  outline_proposal: "大纲草案",
  beat_plan: "章节计划",
  chapter_text: "正文",
  review_report: "评审报告",
  revision_brief: "返工 brief",
  sync_proposal: "同步草案",
};

export function getCreativeOperationLabel(kind: CreativeOperationKind): string {
  return OPERATION_LABELS[kind];
}

export function getCreativeOperationOutputLabel(kind: CreativeOperationOutputKind): string {
  return OUTPUT_LABELS[kind];
}

export const CREATIVE_OPERATION_LABELS = OPERATION_LABELS;

export const CREATIVE_OPERATION_KINDS = CreativeOperationKindSchema.options;

export function formatCreativeOperationForDisplay(operation: CreativeOperation): string {
  return [
    getCreativeOperationLabel(operation.kind),
    operation.userGoal,
  ].filter(Boolean).join("：");
}

export function getDefaultOperationForAgent(
  agentId: CoreAgentId,
  userGoal: string,
  confidence = 0.72,
  reasoning = "用户使用 @Agent 前缀，按该 Agent 的默认创作操作处理。"
): CreativeOperation {
  const goal = userGoal.trim() || "继续处理当前创作请求";

  if (agentId === "设定") {
    return {
      kind: "revise_lore",
      targetType: "lore",
      userGoal: goal,
      primaryAgent: "设定",
      reviewers: [],
      outputKind: "lore_proposal",
      requiresArtifact: true,
      requiresUserApproval: true,
      confidence,
      reasoning,
    };
  }

  if (agentId === "剧情") {
    return {
      kind: "revise_outline",
      targetType: "outline",
      userGoal: goal,
      primaryAgent: "剧情",
      reviewers: [],
      outputKind: "outline_proposal",
      requiresArtifact: true,
      requiresUserApproval: true,
      confidence,
      reasoning,
    };
  }

  if (agentId === "写作") {
    return {
      kind: "write_chapter",
      targetType: "chapter",
      userGoal: goal,
      primaryAgent: "写作",
      reviewers: ["校验", "编辑"],
      outputKind: "chapter_text",
      requiresArtifact: true,
      requiresUserApproval: true,
      confidence,
      reasoning,
    };
  }

  if (agentId === "校验") {
    return {
      kind: "review_chapter",
      targetType: "chapter",
      userGoal: goal,
      primaryAgent: "校验",
      reviewers: [],
      outputKind: "review_report",
      requiresArtifact: false,
      requiresUserApproval: false,
      confidence,
      reasoning,
    };
  }

  return {
    kind: "review_chapter",
    targetType: "chapter",
    userGoal: goal,
    primaryAgent: "编辑",
    reviewers: [],
    outputKind: "review_report",
    requiresArtifact: false,
    requiresUserApproval: false,
    confidence,
    reasoning,
  };
}

export function createFallbackOperation(userGoal: string): CreativeOperation {
  return {
    kind: "answer_question",
    targetType: "unknown",
    userGoal: userGoal.trim() || "继续对话",
    primaryAgent: "编辑",
    reviewers: [],
    outputKind: "chat_answer",
    requiresArtifact: false,
    requiresUserApproval: false,
    confidence: 0.35,
    reasoning: "无法稳定识别具体创作操作，回退为普通创作问答。",
  };
}
