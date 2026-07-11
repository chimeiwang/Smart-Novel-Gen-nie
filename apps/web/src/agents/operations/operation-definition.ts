/**
 * 创作操作定义。
 *
 * 这里是创作操作引擎的业务配置中心：每个操作都有中文名、执行视角、
 * 是否需要待审核草案、审核视角和用户决策策略。
 */

import type { CoreAgentId } from "@/shared/contracts/agent";
import type {
  CreativeOperationKind,
  CreativeOperationOutputKind,
  CreativeOperationTargetType,
} from "@/shared/contracts/creative-operation";
import {
  CREATIVE_OPERATION_LABELS,
  CreativeOperationKindSchema,
  getCreativeOperationLabel,
} from "@/shared/contracts/creative-operation";
import type { TextReviewArtifactKind } from "@/shared/contracts/review-artifact";

export type OperationContextStrategy =
  | "brief"
  | "lore"
  | "outline"
  | "chapter"
  | "review";

export type OperationArtifactPolicy = "none" | "agent_updates" | "text";

export interface OperationDefinition {
  kind: CreativeOperationKind;
  label: string;
  targetType: CreativeOperationTargetType;
  primaryAgent: CoreAgentId;
  reviewers: CoreAgentId[];
  outputKind: CreativeOperationOutputKind;
  contextStrategy: OperationContextStrategy;
  artifactPolicy: OperationArtifactPolicy;
  textArtifactKind?: TextReviewArtifactKind;
  requiresArtifact: boolean;
  requiresUserApproval: boolean;
  userDecisionLabels: string[];
  executionBrief: string;
}

const ALL_OPERATION_KINDS = CreativeOperationKindSchema.options;

export const OPERATION_DEFINITIONS: Record<CreativeOperationKind, OperationDefinition> = {
  answer_question: {
    kind: "answer_question",
    label: "回答问题",
    targetType: "unknown",
    primaryAgent: "编辑",
    reviewers: [],
    outputKind: "chat_answer",
    contextStrategy: "brief",
    artifactPolicy: "none",
    requiresArtifact: false,
    requiresUserApproval: false,
    userDecisionLabels: [],
    executionBrief: "直接回答用户问题，不生成待审核草案。",
  },
  create_lore: {
    kind: "create_lore",
    label: "新建设定",
    targetType: "lore",
    primaryAgent: "设定",
    reviewers: ["校验"],
    outputKind: "lore_proposal",
    contextStrategy: "lore",
    artifactPolicy: "agent_updates",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "生成可审核的设定新增草案，只能通过待审核草案应用到项目。",
  },
  revise_lore: {
    kind: "revise_lore",
    label: "修改设定",
    targetType: "lore",
    primaryAgent: "设定",
    reviewers: ["校验"],
    outputKind: "lore_proposal",
    contextStrategy: "lore",
    artifactPolicy: "agent_updates",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "生成可审核的设定修改草案，只能通过待审核草案应用到项目。",
  },
  create_outline: {
    kind: "create_outline",
    label: "创建大纲",
    targetType: "outline",
    primaryAgent: "剧情",
    reviewers: ["编辑"],
    outputKind: "outline_proposal",
    contextStrategy: "outline",
    artifactPolicy: "agent_updates",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "生成可审核的结构化大纲草案，包含总纲文本和三层大纲节点，只能通过待审核草案应用到项目。",
  },
  revise_outline: {
    kind: "revise_outline",
    label: "修改大纲",
    targetType: "outline",
    primaryAgent: "剧情",
    reviewers: ["编辑"],
    outputKind: "outline_proposal",
    contextStrategy: "outline",
    artifactPolicy: "agent_updates",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "生成可审核的大纲修改草案，只能通过待审核草案应用到项目。",
  },
  plan_chapter: {
    kind: "plan_chapter",
    label: "规划章节",
    targetType: "chapter",
    primaryAgent: "剧情",
    reviewers: ["编辑"],
    outputKind: "beat_plan",
    contextStrategy: "outline",
    artifactPolicy: "text",
    textArtifactKind: "beat_plan_draft",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "生成可审核的章节规划草案，作为后续正文创作依据。",
  },
  write_chapter: {
    kind: "write_chapter",
    label: "生成正文草案",
    targetType: "chapter",
    primaryAgent: "写作",
    reviewers: ["校验", "编辑"],
    outputKind: "chapter_text",
    contextStrategy: "chapter",
    artifactPolicy: "text",
    textArtifactKind: "chapter_draft",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "生成正文草案，不允许直接写入章节正文。",
  },
  rewrite_scene: {
    kind: "rewrite_scene",
    label: "改写场景草案",
    targetType: "scene",
    primaryAgent: "写作",
    reviewers: ["校验", "编辑"],
    outputKind: "chapter_text",
    contextStrategy: "chapter",
    artifactPolicy: "text",
    textArtifactKind: "chapter_draft",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "生成场景改写草案，不允许直接写入章节正文。",
  },
  review_chapter: {
    kind: "review_chapter",
    label: "审核章节",
    targetType: "chapter",
    primaryAgent: "编辑",
    reviewers: [],
    outputKind: "review_report",
    contextStrategy: "review",
    artifactPolicy: "none",
    requiresArtifact: false,
    requiresUserApproval: false,
    userDecisionLabels: [],
    executionBrief: "生成章节审核报告；如果需要修改，只给出返工建议，不直接改正文。",
  },
  sync_lore: {
    kind: "sync_lore",
    label: "同步设定",
    targetType: "lore",
    primaryAgent: "设定",
    reviewers: ["校验"],
    outputKind: "sync_proposal",
    contextStrategy: "lore",
    artifactPolicy: "agent_updates",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "从正文和最近章节提取已发生事实，生成可审核的设定同步草案。",
  },
  manage_foreshadowing: {
    kind: "manage_foreshadowing",
    label: "管理伏笔",
    targetType: "foreshadowing",
    primaryAgent: "剧情",
    reviewers: ["校验"],
    outputKind: "outline_proposal",
    contextStrategy: "outline",
    artifactPolicy: "agent_updates",
    requiresArtifact: true,
    requiresUserApproval: true,
    userDecisionLabels: ["应用到项目", "继续修改", "丢弃草案"],
    executionBrief: "生成可审核的伏笔新增、推进、回收或废弃草案。",
  },
};

export function getOperationDefinition(kind: CreativeOperationKind): OperationDefinition {
  return OPERATION_DEFINITIONS[kind];
}

export function assertOperationDefinitionsComplete(): void {
  for (const kind of ALL_OPERATION_KINDS) {
    const def = OPERATION_DEFINITIONS[kind];
    if (!def) throw new Error(`创作操作缺少定义：${getCreativeOperationLabel(kind)}`);
    if (def.label !== CREATIVE_OPERATION_LABELS[kind]) {
      throw new Error(`创作操作中文名不一致：${getCreativeOperationLabel(kind)}`);
    }
  }
}
