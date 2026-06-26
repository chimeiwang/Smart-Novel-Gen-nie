/**
 * Agent Control 契约（Phase 0：协议落地）
 *
 * @module shared/contracts/agent-control
 * @description 所有 Agent 控制事件的 Zod schema、TS 类型。
 *   替代 JSON 信封中的 wantsToCall / scores / qualityGate / updates / conflicts 字段。
 *   控制信息走标准 tool_calls arguments（短小、结构化），
 *   长篇正文仍保留在 assistant content 中。
 *
 *   Phase 8 新增对应的 SSE 事件后，前端通过 SSE 事件感知控制行为，
 *   而无需解析 assistant prose。
 *
 * @phase Phase 0 — 协议和接口落地
 */

import { z } from "zod";
import { CoreAgentIdSchema } from "./agent";
import { AgentUpdatesProposalSchema, AgentUpdatesSchema, OutlineNodeKindSchema } from "./agent-updates";
import { BeatPlanDraftSceneSchema } from "./beat-plan";
import {
  AGENT_UPDATE_CHANNEL_RULES_PROMPT,
  ForbiddenOutlineTreeToolFieldsShape,
  ForbiddenToolTextSectionsShape,
  ITEM_TEXT_BLOCK_TOOLS_TEXT,
  TEXT_UPDATE_SECTIONS_TEXT,
  TOOL_MEDIUM_TEXT_MAX,
  TOOL_SHORT_TEXT_MAX,
  ToolMediumTextSchema,
  ToolOptionalShortTextSchema,
  ToolShortTextSchema,
  UpdateBuilderItemTextFieldSchema,
  UpdateBuilderItemTextSectionSchema,
  UpdateBuilderTextSectionSchema,
  formatStringUnion,
} from "./agent-update-channels";
import { TextReviewArtifactKindSchema } from "./review-artifact";

// ============================================
// submit_quality_report — 替代 scores + qualityGate + rewriteBrief
// ============================================

export const QualityScoresSchema = z.object({
  hook: z.number().min(0).max(10).optional(),
  tension: z.number().min(0).max(10).optional(),
  payoff: z.number().min(0).max(10).optional(),
  pacing: z.number().min(0).max(10).optional(),
  endingHook: z.number().min(0).max(10).optional(),
  readerPromise: z.number().min(0).max(10).optional(),
  overall: z.number().min(0).max(10).optional(),
});
export type QualityScores = z.infer<typeof QualityScoresSchema>;

export const QualityReportEventSchema = z.object({
  type: z.literal("submit_quality_report"),
  scores: QualityScoresSchema,
  qualityGate: z.enum(["pass", "revise", "rewrite"]),
  rewriteBrief: z.string().max(1000).optional(),
});
export type QualityReportEvent = z.infer<typeof QualityReportEventSchema>;

/** submit_quality_report tool 的入参 schema */
export const QualityReportToolArgsSchema = QualityReportEventSchema.omit({ type: true });

// ============================================
// update builder — 分批构建 agent_updates 草案
// ============================================

const ToolFieldChangeSchema = z.object({
  field: z.string().trim().min(1).max(80),
  operation: z.enum(["add", "remove", "update"]),
  oldValue: ToolOptionalShortTextSchema,
  newValue: ToolOptionalShortTextSchema,
}).strict();
const ToolStatusEnum = z.enum(["active", "missing", "dead", "imprisoned", "unknown"]);
const ToolOutlineStatusEnum = z.enum(["planned", "in_progress", "completed", "skipped"]);
function requireCreateNameOrLocator(
  value: { action: "create" | "update" | "delete"; name?: string; id?: string; [key: string]: unknown },
  idKeys: string[],
  ctx: z.RefinementCtx,
  label: string
) {
  if (value.action === "create") {
    if (!value.name?.trim()) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["name"], message: `创建${label}必须提供 name` });
    }
    return;
  }

  const hasLocator = Boolean(
    value.id?.trim() ||
    value.name?.trim() ||
    idKeys.some((key) => typeof value[key] === "string" && (value[key] as string).trim())
  );
  if (!hasLocator) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["id"], message: `更新或删除${label}必须提供 id、专用 id 或 name 之一` });
  }
}

const ToolCharacterAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().max(200).optional(),
  characterId: z.string().max(200).optional(),
  name: z.string().trim().min(1).max(120).optional(),
  aliases: ToolOptionalShortTextSchema,
  gender: z.string().trim().max(40).optional(),
  age: z.string().trim().max(40).optional(),
  identity: ToolOptionalShortTextSchema,
  personality: ToolOptionalShortTextSchema,
  appearance: ToolOptionalShortTextSchema,
  background: ToolOptionalShortTextSchema,
  coreDesire: ToolOptionalShortTextSchema,
  behaviorBoundaries: ToolOptionalShortTextSchema,
  speechStyle: ToolOptionalShortTextSchema,
  relationshipPrinciples: ToolOptionalShortTextSchema,
  shortTermGoal: ToolOptionalShortTextSchema,
  factionId: z.string().max(200).optional(),
  powerLevel: ToolOptionalShortTextSchema,
  combatAbility: ToolOptionalShortTextSchema,
  specialSkills: ToolOptionalShortTextSchema,
  currentStatus: ToolStatusEnum.optional(),
  statusNote: ToolOptionalShortTextSchema,
  fieldChanges: z.array(ToolFieldChangeSchema).max(10).optional(),
}).strict().superRefine((value, ctx) => requireCreateNameOrLocator(value, ["characterId"], ctx, "角色"));
const ToolLocationAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().max(200).optional(),
  locationId: z.string().max(200).optional(),
  name: z.string().trim().min(1).max(120).optional(),
  aliases: ToolOptionalShortTextSchema,
  type: ToolOptionalShortTextSchema,
  parentId: z.string().max(200).optional(),
  description: ToolOptionalShortTextSchema,
  climate: ToolOptionalShortTextSchema,
  culture: ToolOptionalShortTextSchema,
  fieldChanges: z.array(ToolFieldChangeSchema).max(10).optional(),
}).strict().superRefine((value, ctx) => requireCreateNameOrLocator(value, ["locationId"], ctx, "地点"));
const ToolItemAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().max(200).optional(),
  itemId: z.string().max(200).optional(),
  name: z.string().trim().min(1).max(120).optional(),
  aliases: ToolOptionalShortTextSchema,
  type: ToolOptionalShortTextSchema,
  rarity: ToolOptionalShortTextSchema,
  effect: ToolOptionalShortTextSchema,
  origin: ToolOptionalShortTextSchema,
  description: ToolOptionalShortTextSchema,
  ownerId: z.string().max(200).optional(),
  fieldChanges: z.array(ToolFieldChangeSchema).max(10).optional(),
}).strict().superRefine((value, ctx) => requireCreateNameOrLocator(value, ["itemId"], ctx, "物品"));
const ToolFactionAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().max(200).optional(),
  factionId: z.string().max(200).optional(),
  name: z.string().trim().min(1).max(120).optional(),
  aliases: ToolOptionalShortTextSchema,
  type: ToolOptionalShortTextSchema,
  baseId: z.string().max(200).optional(),
  description: ToolOptionalShortTextSchema,
  fieldChanges: z.array(ToolFieldChangeSchema).max(10).optional(),
}).strict().superRefine((value, ctx) => requireCreateNameOrLocator(value, ["factionId"], ctx, "势力"));
const ToolGlossaryAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().max(200).optional(),
  glossaryId: z.string().max(200).optional(),
  term: z.string().trim().min(1).max(120).optional(),
  definition: ToolMediumTextSchema.optional(),
  category: ToolOptionalShortTextSchema,
  fieldChanges: z.array(ToolFieldChangeSchema).max(10).optional(),
}).strict().superRefine((value, ctx) => {
  if (value.action === "create") {
    if (!value.term?.trim()) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["term"], message: "创建术语必须提供 term" });
    }
    if (!value.definition?.trim()) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["definition"], message: "创建术语必须提供短 definition" });
    }
    return;
  }
  if (!value.id?.trim() && !value.glossaryId?.trim() && !value.term?.trim()) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["id"], message: "更新或删除术语必须提供 id、glossaryId 或 term 之一" });
  }
});
const ToolCharacterExperienceAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().max(200).optional(),
  characterId: z.string().max(200).optional(),
  characterName: z.string().trim().max(120).optional(),
  chapterId: z.string().max(200).optional(),
  chapterTitle: z.string().trim().max(200).optional(),
  content: ToolShortTextSchema,
  order: z.number().optional(),
}).strict();
const ToolOutlineUpdateSchema = z.object({
  nodeId: z.string().min(1).max(200),
  status: ToolOutlineStatusEnum,
  actualWordCount: z.number().optional(),
}).strict();
const ToolOutlineAdjustmentBaseSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  nodeId: z.string().max(200).optional(),
  nodeTitle: z.string().trim().max(200).optional(),
  clientKey: z.string().max(200).optional(),
  parentKey: z.string().max(200).optional(),
  title: z.string().trim().max(200).optional(),
  content: ToolOptionalShortTextSchema,
  kind: OutlineNodeKindSchema.optional(),
  parentId: z.string().max(200).optional(),
  status: ToolOutlineStatusEnum.optional(),
  estimatedWordCount: z.number().optional(),
  actualWordCount: z.number().optional(),
}).strict();
const ToolOutlineAdjustmentSchema = ToolOutlineAdjustmentBaseSchema.superRefine((adjustment, ctx) => {
  const hasTitle = Boolean(adjustment.title?.trim() || adjustment.nodeTitle?.trim());
  const hasIdentity = Boolean(adjustment.nodeId?.trim() || adjustment.nodeTitle?.trim() || adjustment.title?.trim());
  if (adjustment.action === "create" && !hasTitle) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["title"], message: "创建大纲节点必须提供 title 或 nodeTitle" });
  }
  if (adjustment.action === "create" && !adjustment.kind) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["kind"], message: "创建大纲节点必须提供 kind" });
  }
  if ((adjustment.action === "update" || adjustment.action === "delete") && !hasIdentity) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["nodeId"], message: "更新或删除大纲节点必须提供 nodeId、nodeTitle 或 title 之一" });
  }
});
const ToolForeshadowingUpdateSchema = z.object({
  action: z.enum(["create", "update", "payoff", "abandon"]),
  id: z.string().max(200).optional(),
  name: z.string().trim().min(1).max(160),
  plantedAt: ToolOptionalShortTextSchema,
  plantedContent: ToolOptionalShortTextSchema,
  expectedPayoff: ToolOptionalShortTextSchema,
  payoffAt: ToolOptionalShortTextSchema,
  payoffNote: ToolOptionalShortTextSchema,
}).strict();
const ToolReferenceAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  referenceId: z.string().max(200).optional(),
  id: z.string().max(200).optional(),
  title: z.string().trim().min(1).max(200),
  type: ToolOptionalShortTextSchema,
  content: ToolOptionalShortTextSchema,
}).strict();
const ToolAgentUpdatesSchema = z.object({
  characters: z.array(ToolCharacterAdjustmentSchema).max(20).optional(),
  locations: z.array(ToolLocationAdjustmentSchema).max(20).optional(),
  items: z.array(ToolItemAdjustmentSchema).max(20).optional(),
  factions: z.array(ToolFactionAdjustmentSchema).max(20).optional(),
  glossaries: z.array(ToolGlossaryAdjustmentSchema).max(30).optional(),
  characterExperiences: z.array(ToolCharacterExperienceAdjustmentSchema).max(30).optional(),
  outline: z.array(ToolOutlineUpdateSchema).max(50).optional(),
  outlineAdjustments: z.array(ToolOutlineAdjustmentSchema).max(50).optional(),
  foreshadowing: z.array(ToolForeshadowingUpdateSchema).max(50).optional(),
  references: z.array(ToolReferenceAdjustmentSchema).max(30).optional(),
  ...ForbiddenToolTextSectionsShape,
}).strict();
const ToolAgentUpdatesProposalSchema = ToolAgentUpdatesSchema.extend({
  outlineAdjustments: z.array(ToolOutlineAdjustmentSchema).max(10).optional(),
});

// ============================================
// propose_updates — 替代 updates JSON 字段
// ============================================

export const ProposalUpdatesEventSchema = z.object({
  type: z.literal("propose_updates"),
  summary: z.string().min(1).max(1000),
  artifactKey: z.string().min(1).max(200).optional(),
  reviewerAgent: CoreAgentIdSchema.optional(),
  submitForReview: z.boolean().optional(),
  /** LLM 工具入参只允许短结构化变更；长文本由 block 工具承载 */
  updates: ToolAgentUpdatesProposalSchema,
});
export type ProposalUpdatesEvent = z.infer<typeof ProposalUpdatesEventSchema>;

/** propose_updates tool 的入参 schema */
export const ProposalUpdatesToolArgsSchema = ProposalUpdatesEventSchema.omit({ type: true });
const OutlineTreeChapterGroupSchema = z.object({
  title: z.string().trim().min(1),
  estimatedWordCount: z.number().int().positive().optional(),
  ...ForbiddenOutlineTreeToolFieldsShape,
}).strict();
const OutlineTreePlotUnitSchema = z.object({
  title: z.string().trim().min(1),
  estimatedWordCount: z.number().int().positive().optional(),
  chapterGroups: z.array(OutlineTreeChapterGroupSchema).optional(),
  ...ForbiddenOutlineTreeToolFieldsShape,
}).strict();
const OutlineTreeStageSchema = z.object({
  title: z.string().trim().min(1),
  estimatedWordCount: z.number().int().positive().optional(),
  plotUnits: z.array(OutlineTreePlotUnitSchema).optional(),
  ...ForbiddenOutlineTreeToolFieldsShape,
}).strict();

export const StartUpdateBuilderEventSchema = z.object({
  type: z.literal("start_update_builder"),
  summary: z.string().min(1).max(1000),
  artifactKey: z.string().min(1).max(200),
  reviewerAgent: CoreAgentIdSchema.optional(),
  submitForReview: z.boolean().optional(),
});
export type StartUpdateBuilderEvent = z.infer<typeof StartUpdateBuilderEventSchema>;
export const StartUpdateBuilderToolArgsSchema = StartUpdateBuilderEventSchema.omit({ type: true });

export const AppendUpdateBatchEventSchema = z.object({
  type: z.literal("append_update_batch"),
  artifactKey: z.string().min(1).max(200),
  summary: z.string().min(1).max(1000).optional(),
  updates: ToolAgentUpdatesSchema,
});
export type AppendUpdateBatchEvent = z.infer<typeof AppendUpdateBatchEventSchema>;
export const AppendUpdateBatchToolArgsSchema = AppendUpdateBatchEventSchema.omit({ type: true });

export const AppendOutlineTreeEventSchema = z.object({
  type: z.literal("append_outline_tree"),
  artifactKey: z.string().min(1).max(200),
  summary: z.string().min(1).max(1000).optional(),
  stages: z.array(OutlineTreeStageSchema).min(1),
});
export type OutlineTreeChapterGroup = z.infer<typeof OutlineTreeChapterGroupSchema>;
export type OutlineTreePlotUnit = z.infer<typeof OutlineTreePlotUnitSchema>;
export type OutlineTreeStage = z.infer<typeof OutlineTreeStageSchema>;
export type AppendOutlineTreeEvent = z.infer<typeof AppendOutlineTreeEventSchema>;
export const AppendOutlineTreeToolArgsSchema = AppendOutlineTreeEventSchema.omit({ type: true });

export const PutUpdateTextBlockEventSchema = z.object({
  type: z.literal("put_update_text_block"),
  artifactKey: z.string().min(1).max(200),
  section: UpdateBuilderTextSectionSchema,
  summary: z.string().min(1).max(1000).optional(),
}).strict();
export type PutUpdateTextBlockEvent = z.infer<typeof PutUpdateTextBlockEventSchema>;
export const PutUpdateTextBlockToolArgsSchema = PutUpdateTextBlockEventSchema.omit({ type: true });

const PutUpdateItemTextBlockToolArgsBaseSchema = z.object({
  artifactKey: z.string().min(1).max(200),
  section: UpdateBuilderItemTextSectionSchema,
  field: UpdateBuilderItemTextFieldSchema,
  targetId: z.string().min(1).max(200).optional(),
  targetKey: z.string().min(1).max(200).optional(),
  targetName: z.string().min(1).max(200).optional(),
  summary: z.string().min(1).max(1000).optional(),
}).strict();
const hasItemTextTarget = (value: {
  targetId?: string;
  targetKey?: string;
  targetName?: string;
}) => Boolean(value.targetId || value.targetKey || value.targetName);
const itemTextTargetRefineOptions: { path: PropertyKey[]; message: string } = {
  path: ["targetId"],
  message: "必须提供 targetId、targetKey 或 targetName 之一用于定位数组 item",
};
export const PutUpdateItemTextBlockToolArgsSchema = PutUpdateItemTextBlockToolArgsBaseSchema.refine(
  hasItemTextTarget,
  itemTextTargetRefineOptions
);
export const PutUpdateItemTextBlockEventSchema = z.object({
  type: z.literal("put_update_item_text_block"),
}).merge(PutUpdateItemTextBlockToolArgsBaseSchema).refine(
  hasItemTextTarget,
  itemTextTargetRefineOptions
);
export type PutUpdateItemTextBlockEvent = z.infer<typeof PutUpdateItemTextBlockEventSchema>;

const PutUpdateItemTextBlockEntrySchema = PutUpdateItemTextBlockToolArgsBaseSchema
  .omit({ artifactKey: true })
  .refine(hasItemTextTarget, itemTextTargetRefineOptions);
export const PutUpdateItemTextBlocksToolArgsSchema = z.object({
  artifactKey: z.string().min(1).max(200),
  blocks: z.array(PutUpdateItemTextBlockEntrySchema).min(1).max(20),
}).strict();
export const PutUpdateItemTextBlocksEventSchema = z.object({
  type: z.literal("put_update_item_text_blocks"),
}).merge(PutUpdateItemTextBlocksToolArgsSchema);
export type PutUpdateItemTextBlocksEvent = z.infer<typeof PutUpdateItemTextBlocksEventSchema>;

export const FinishUpdateBuilderEventSchema = z.object({
  type: z.literal("finish_update_builder"),
  artifactKey: z.string().min(1).max(200),
  summary: z.string().min(1).max(1000),
  reviewerAgent: CoreAgentIdSchema.optional(),
  submitForReview: z.boolean().optional(),
});
export type FinishUpdateBuilderEvent = z.infer<typeof FinishUpdateBuilderEventSchema>;
export const FinishUpdateBuilderToolArgsSchema = FinishUpdateBuilderEventSchema.omit({ type: true });

// ============================================
// begin_artifact_output — 长文本产物意图
// ============================================

export const BeginArtifactOutputEventSchema = z.object({
  type: z.literal("begin_artifact_output"),
  kind: TextReviewArtifactKindSchema,
  summary: z.string().min(1).max(1000),
  artifactKey: z.string().min(1).max(200).optional(),
  reviewerAgent: CoreAgentIdSchema.optional(),
  submitForReview: z.boolean().optional(),
});
export type BeginArtifactOutputEvent = z.infer<typeof BeginArtifactOutputEventSchema>;

/** begin_artifact_output tool 的入参 schema */
export const BeginArtifactOutputToolArgsSchema = BeginArtifactOutputEventSchema.omit({ type: true });

// ============================================
// show_review_artifact — 请求前端展示草案
// ============================================

const ShowReviewArtifactTargetSchema = z.object({
  artifactId: z.string().min(1).max(200).optional(),
  artifactKey: z.string().min(1).max(200).optional(),
  reason: z.string().min(1).max(500).optional(),
}).refine((value) => Boolean(value.artifactId || value.artifactKey), {
  message: "artifactId 或 artifactKey 至少提供一个",
  path: ["artifactId"],
});

export const ShowReviewArtifactEventSchema = z.object({
  type: z.literal("show_review_artifact"),
  artifactId: z.string().min(1).max(200).optional(),
  artifactKey: z.string().min(1).max(200).optional(),
  reason: z.string().min(1).max(500).optional(),
}).refine((value) => Boolean(value.artifactId || value.artifactKey), {
  message: "artifactId 或 artifactKey 至少提供一个",
  path: ["artifactId"],
});
export type ShowReviewArtifactEvent = z.infer<typeof ShowReviewArtifactEventSchema>;
export const ShowReviewArtifactToolArgsSchema = ShowReviewArtifactTargetSchema;

// ============================================
// submit_beat_plan — Beat Plan 一等化
// ============================================

export const BeatPlanProposalEventSchema = z.object({
  type: z.literal("submit_beat_plan"),
  title: z.string().min(1).max(200),
  beatCount: z.number().int().min(1).max(50),
  summary: z.string().min(1).max(2000),
  artifactKey: z.string().min(1).max(200).optional(),
  reviewerAgent: CoreAgentIdSchema.optional(),
  submitForReview: z.boolean().optional(),
  chapterGoal: z.string().min(1).max(1000).optional(),
  mainPlotConnection: z.string().max(1000).optional(),
  chapterAcceptanceCriteria: z.string().max(1000).optional(),
  totalEstimatedWords: z.number().int().min(0).optional(),
  sceneBeats: z.array(BeatPlanDraftSceneSchema).min(1).max(50).optional(),
});
export type BeatPlanProposalEvent = z.infer<typeof BeatPlanProposalEventSchema>;

/** submit_beat_plan tool 的入参 schema */
export const BeatPlanProposalToolArgsSchema = BeatPlanProposalEventSchema.omit({ type: true });

// ============================================
// submit_validation_report — 结构化冲突列表
// ============================================

export const ConflictItemSchema = z.object({
  type: z.enum(["character", "setting", "plot", "logic", "world"]),
  summary: z.string().min(1).max(500),
  evidence: z.string().max(2000).optional(),
  suggestion: z.string().max(1000).optional(),
});
export type ConflictItem = z.infer<typeof ConflictItemSchema>;

export const ValidationReportEventSchema = z.object({
  type: z.literal("submit_validation_report"),
  hasConflicts: z.boolean(),
  conflicts: z.array(ConflictItemSchema).max(50),
});
export type ValidationReportEvent = z.infer<typeof ValidationReportEventSchema>;

/** submit_validation_report tool 的入参 schema */
export const ValidationReportToolArgsSchema = ValidationReportEventSchema.omit({ type: true });

// ============================================
// evaluator/reviser loop — 通用评估控制
// ============================================

export const EvaluationEventSchema = z.object({
  type: z.literal("submit_evaluation"),
  artifactId: z.string().min(1).max(200).optional(),
  artifactKey: z.string().min(1).max(200),
  verdict: z.enum(["pass", "revise", "block"]),
  summary: z.string().min(1).max(1000),
  requiredChanges: z.string().max(2000).optional(),
});
export type EvaluationEvent = z.infer<typeof EvaluationEventSchema>;

/** submit_evaluation tool 的入参 schema */
export const EvaluationToolArgsSchema = EvaluationEventSchema.omit({ type: true });

// ============================================
// Control Event Union
// ============================================

export const AgentControlEventSchema = z.discriminatedUnion("type", [
  QualityReportEventSchema,
  ProposalUpdatesEventSchema,
  StartUpdateBuilderEventSchema,
  AppendUpdateBatchEventSchema,
  AppendOutlineTreeEventSchema,
  PutUpdateTextBlockEventSchema,
  PutUpdateItemTextBlockEventSchema,
  PutUpdateItemTextBlocksEventSchema,
  FinishUpdateBuilderEventSchema,
  BeginArtifactOutputEventSchema,
  ShowReviewArtifactEventSchema,
  BeatPlanProposalEventSchema,
  ValidationReportEventSchema,
  EvaluationEventSchema,
]);
export type AgentControlEvent = z.infer<typeof AgentControlEventSchema>;

// ============================================
// 按类型获取 Schema
// ============================================

/** control tool name → Zod args schema 的映射 */
export const CONTROL_TOOL_ARGS_SCHEMAS: Record<string, z.ZodType<Record<string, unknown>>> = {
  submit_quality_report: QualityReportToolArgsSchema,
  propose_updates: ProposalUpdatesToolArgsSchema,
  start_update_builder: StartUpdateBuilderToolArgsSchema,
  append_update_batch: AppendUpdateBatchToolArgsSchema,
  append_outline_tree: AppendOutlineTreeToolArgsSchema,
  put_update_text_block: PutUpdateTextBlockToolArgsSchema,
  put_update_item_text_block: PutUpdateItemTextBlockToolArgsSchema,
  put_update_item_text_blocks: PutUpdateItemTextBlocksToolArgsSchema,
  finish_update_builder: FinishUpdateBuilderToolArgsSchema,
  begin_artifact_output: BeginArtifactOutputToolArgsSchema,
  show_review_artifact: ShowReviewArtifactToolArgsSchema,
  submit_beat_plan: BeatPlanProposalToolArgsSchema,
  submit_validation_report: ValidationReportToolArgsSchema,
  submit_evaluation: EvaluationToolArgsSchema,
};

/** 所有 control tool 名称 */
export const CONTROL_TOOL_NAMES = Object.keys(CONTROL_TOOL_ARGS_SCHEMAS);

export interface ControlToolValidationIssue {
  path: string;
  message: string;
  code?: string;
}

export interface ControlToolValidationError {
  toolName: string;
  issues: ControlToolValidationIssue[];
  expectedType: string;
  minimalExample: string;
}

export type ControlToolParseResult =
  | { success: true; event: AgentControlEvent }
  | { success: false; error: ControlToolValidationError };

const CONTROL_TOOL_REPAIR_HINTS: Record<string, { expectedType: string; minimalExample: string }> = {
  submit_quality_report: {
    expectedType: [
      "type SubmitQualityReportArgs = {",
      "  scores: {",
      "    hook?: number; tension?: number; payoff?: number; pacing?: number;",
      "    endingHook?: number; readerPromise?: number; overall?: number;",
      "  };",
      "  qualityGate: \"pass\" | \"revise\" | \"rewrite\";",
      "  rewriteBrief?: string; // optional, <= 1000 chars",
      "};",
    ].join("\n"),
    minimalExample: JSON.stringify({
      scores: { hook: 7, tension: 6, payoff: 6, pacing: 7, endingHook: 8, readerPromise: 7, overall: 7 },
      qualityGate: "revise",
      rewriteBrief: "中段冲突回报偏弱，建议补一个明确反转。",
    }, null, 2),
  },
  propose_updates: {
    expectedType: [
      "type ProposeUpdatesArgs = {",
      "  summary: string; // required, 1-1000 chars",
      "  artifactKey?: string; // optional stable key for review loops",
      "  reviewerAgent?: \"设定\" | \"剧情\" | \"写作\" | \"校验\" | \"编辑\";",
      "  submitForReview?: boolean;",
      "  updates: {",
      `    characters?: ShortCharacterUpdate[]; // text fields <= ${TOOL_SHORT_TEXT_MAX} chars`,
      `    locations?: ShortLocationUpdate[]; // text fields <= ${TOOL_SHORT_TEXT_MAX} chars`,
      `    items?: ShortItemUpdate[]; // text fields <= ${TOOL_SHORT_TEXT_MAX} chars`,
      `    factions?: ShortFactionUpdate[]; // text fields <= ${TOOL_SHORT_TEXT_MAX} chars`,
      `    glossaries?: ShortGlossaryUpdate[]; // definition <= ${TOOL_MEDIUM_TEXT_MAX} chars`,
      `    characterExperiences?: ShortCharacterExperienceUpdate[]; // content <= ${TOOL_SHORT_TEXT_MAX} chars`,
      "    outline?: OutlineStatusUpdate[];",
      `    outlineAdjustments?: ShortOutlineAdjustment[]; // max 10 items; content <= ${TOOL_SHORT_TEXT_MAX} chars`,
      `    foreshadowing?: ShortForeshadowingUpdate[]; // text fields <= ${TOOL_SHORT_TEXT_MAX} chars`,
      `    references?: ShortReferenceUpdate[]; // content <= ${TOOL_SHORT_TEXT_MAX} chars`,
      "  };",
      "};",
      "",
      `Do not include ${TEXT_UPDATE_SECTIONS_TEXT} here.`,
      `For long text, use start_update_builder + put_update_text_block / ${ITEM_TEXT_BLOCK_TOOLS_TEXT}.`,
    ].join("\n"),
    minimalExample: JSON.stringify({
      summary: "短小修补大纲节点",
      updates: {
        outlineAdjustments: [
          {
            action: "update",
            nodeId: "outline-node-id",
            title: "第1-3章 开篇任务",
            content: "用遗产任务建立职业卖点，并在章末抛出异常玉简线索。",
          },
        ],
      },
    }, null, 2),
  },
  start_update_builder: {
    expectedType: [
      "type StartUpdateBuilderArgs = {",
      "  summary: string; // required, 1-1000 chars",
      "  artifactKey: string; // required stable key for all builder calls",
      "  reviewerAgent?: \"设定\" | \"剧情\" | \"写作\" | \"校验\" | \"编辑\";",
      "  submitForReview?: boolean;",
      "};",
    ].join("\n"),
    minimalExample: JSON.stringify({
      summary: "批量重构结构化大纲",
      artifactKey: "outline-restructure-v1",
      reviewerAgent: "编辑",
      submitForReview: true,
    }, null, 2),
  },
  append_update_batch: {
    expectedType: [
      "type AppendUpdateBatchArgs = {",
      "  artifactKey: string; // required, same key as start_update_builder",
      "  summary?: string; // optional short note",
      "  updates: ShortAgentUpdates; // one or more short structured sections",
      "};",
      "",
      `Do not include ${TEXT_UPDATE_SECTIONS_TEXT} here.`,
      `Every text field in array items must be short; outlineAdjustments[].content <= ${TOOL_SHORT_TEXT_MAX} chars.`,
      `For long item text, call ${ITEM_TEXT_BLOCK_TOOLS_TEXT} after appending the target item.`,
    ].join("\n"),
    minimalExample: JSON.stringify({
      artifactKey: "outline-restructure-v1",
      updates: {
        outlineAdjustments: [
          { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage" },
          { action: "create", clientKey: "unit-1", parentKey: "stage-1", title: "遗产线索", kind: "plot_unit" },
        ],
      },
    }, null, 2),
  },
  append_outline_tree: {
    expectedType: [
      "type AppendOutlineTreeArgs = {",
      "  artifactKey: string; // required, same key as start_update_builder",
      "  summary?: string; // optional short note",
      "  stages: Array<{",
      "    title: string;",
      "    estimatedWordCount?: number;",
      "    plotUnits?: Array<{",
      "      title: string;",
      "      estimatedWordCount?: number;",
      "      chapterGroups?: Array<{",
      "        title: string;",
      "        estimatedWordCount?: number;",
      "      }>;",
      "    }>;",
      "  }>;",
      "};",
      "",
      "Do not provide parentId, parentKey, or clientKey in append_outline_tree.",
      "Do not provide content fields in append_outline_tree. It is structure-only.",
      "Put node synopsis/details in put_update_item_text_block(s) marker blocks after the tree exists.",
      "The server generates outlineAdjustments references.",
    ].join("\n"),
    minimalExample: JSON.stringify({
      artifactKey: "outline-restructure-v1",
      summary: "追加第一阶段大纲树",
      stages: [
        {
          title: "第一阶段 鹿溪镇暗流",
          plotUnits: [
            {
              title: "鹿溪镇的暗流",
              chapterGroups: [
                {
                  title: "裂痕",
                },
              ],
            },
          ],
        },
      ],
    }, null, 2),
  },
  put_update_text_block: {
    expectedType: [
      "type PutUpdateTextBlockArgs = {",
      "  artifactKey: string; // required, same key as start_update_builder",
      `  section: ${formatStringUnion(UpdateBuilderTextSectionSchema.options)};`,
      "  summary?: string;",
      "};",
      "",
      "Put the long text in assistant content between ARTIFACT_OUTPUT_START and ARTIFACT_OUTPUT_END.",
      "Do not put long text in tool arguments.",
    ].join("\n"),
    minimalExample: JSON.stringify({
      artifactKey: "outline-restructure-v1",
      section: "outlineContent",
      summary: "写入新版全书总纲",
    }, null, 2),
  },
  put_update_item_text_block: {
    expectedType: [
      "type PutUpdateItemTextBlockArgs = {",
      "  artifactKey: string; // required, same key as start_update_builder",
      `  section: ${formatStringUnion(UpdateBuilderItemTextSectionSchema.options)};`,
      `  field: ${formatStringUnion(UpdateBuilderItemTextFieldSchema.options)};`,
      "  targetId?: string; // existing db id/nodeId/referenceId/etc.",
      "  targetKey?: string; // clientKey for same builder draft items",
      "  targetName?: string; // fallback title/name/term lookup",
      "  summary?: string;",
      "};",
      "",
      "Put the long text in assistant content between ARTIFACT_OUTPUT_START and ARTIFACT_OUTPUT_END.",
      "The target item must already exist in this builder via append_update_batch or append_outline_tree.",
    ].join("\n"),
    minimalExample: JSON.stringify({
      artifactKey: "outline-restructure-v1",
      section: "outlineAdjustments",
      field: "content",
      targetKey: "outline-restructure-v1-b0-s1-u1-g1",
      summary: "写入第1-3章章节组详细梗概",
    }, null, 2),
  },
  put_update_item_text_blocks: {
    expectedType: [
      "type PutUpdateItemTextBlocksArgs = {",
      "  artifactKey: string; // required, same key as start_update_builder",
      "  blocks: Array<{",
      `    section: ${formatStringUnion(UpdateBuilderItemTextSectionSchema.options)};`,
      `    field: ${formatStringUnion(UpdateBuilderItemTextFieldSchema.options)};`,
      "    targetId?: string;",
      "    targetKey?: string;",
      "    targetName?: string;",
      "    summary?: string;",
      "  }>; // 1-20 entries",
      "};",
      "",
      "Provide one ARTIFACT_OUTPUT_START/END marker block in assistant content for each blocks[] entry, in the same order.",
      "The target items must already exist in this builder via append_update_batch or append_outline_tree.",
    ].join("\n"),
    minimalExample: JSON.stringify({
      artifactKey: "outline-restructure-v1",
      blocks: [
        {
          section: "outlineAdjustments",
          field: "content",
          targetKey: "outline-restructure-v1-b0-s1-u1-g1",
          summary: "写入第1-3章章节组详细梗概",
        },
      ],
    }, null, 2),
  },
  finish_update_builder: {
    expectedType: [
      "type FinishUpdateBuilderArgs = {",
      "  artifactKey: string; // required",
      "  summary: string; // required, final draft summary",
      "  reviewerAgent?: \"设定\" | \"剧情\" | \"写作\" | \"校验\" | \"编辑\";",
      "  submitForReview?: boolean;",
      "};",
    ].join("\n"),
    minimalExample: JSON.stringify({
      artifactKey: "outline-restructure-v1",
      summary: "批量大纲草案构建完成",
      reviewerAgent: "编辑",
      submitForReview: true,
    }, null, 2),
  },
  begin_artifact_output: {
    expectedType: [
      "type BeginArtifactOutputArgs = {",
      "  kind: \"outline_draft\" | \"chapter_draft\" | \"lore_draft\" | \"revision_brief\" | \"beat_plan_draft\";",
      "  summary: string; // required, 1-1000 chars",
      "  artifactKey?: string; // optional stable key for review loops",
      "  reviewerAgent?: \"设定\" | \"剧情\" | \"写作\" | \"校验\" | \"编辑\";",
      "  submitForReview?: boolean;",
      "};",
    ].join("\n"),
    minimalExample: JSON.stringify({
      kind: "outline_draft",
      artifactKey: "outline-revision-1",
      reviewerAgent: "编辑",
      submitForReview: true,
      summary: "前十章大纲修改草案。",
    }, null, 2),
  },
  show_review_artifact: {
    expectedType: [
      "type ShowReviewArtifactArgs = {",
      "  artifactId?: string; // ReviewArtifact id, if known",
      "  artifactKey?: string; // stable artifactKey used when creating/updating the draft",
      "  reason?: string; // optional, <= 500 chars",
      "};",
      "// artifactId or artifactKey is required",
    ].join("\n"),
    minimalExample: JSON.stringify({
      artifactKey: "outline-revision-1",
      reason: "草案已经生成，请展示给用户确认。",
    }, null, 2),
  },
  submit_beat_plan: {
    expectedType: [
      "type SubmitBeatPlanArgs = {",
      "  title: string; // required, 1-200 chars",
      "  beatCount: number; // integer, 1-50",
      "  summary: string; // required, 1-2000 chars",
      "  artifactKey?: string; // stable ReviewArtifact key, optional",
      "  reviewerAgent?: \"设定\" | \"剧情\" | \"写作\" | \"校验\" | \"编辑\";",
      "  submitForReview?: boolean; // default true",
      "  chapterGoal?: string;",
      "  mainPlotConnection?: string;",
      "  chapterAcceptanceCriteria?: string;",
      "  totalEstimatedWords?: number;",
      "  sceneBeats?: Array<{",
      "    order?: number;",
      "    goal: string;",
      "    conflict?: string;",
      "    characters?: string[];",
      "    foreshadowingRefs?: string[];",
      "    estimatedWords?: number;",
      "    acceptanceCriteria?: string;",
      "  }>; // 1-50 entries",
      "};",
    ].join("\n"),
    minimalExample: JSON.stringify({
      title: "第一章 Beat Plan",
      beatCount: 5,
      summary: "开场扫尾、理事会截胡、主角发现异常残片、同伴反应、章末悬念。",
      chapterGoal: "让主角发现异常残片，并用章末悬念把读者带入主线。",
      sceneBeats: [
        {
          order: 1,
          goal: "主角处理遗留事件，展示当前处境。",
          conflict: "理事会提前介入，压缩主角行动空间。",
          characters: ["主角"],
          estimatedWords: 1200,
          acceptanceCriteria: "读者能明确主角想保住线索，且阻力已经出现。",
        },
      ],
    }, null, 2),
  },
  submit_validation_report: {
    expectedType: [
      "type SubmitValidationReportArgs = {",
      "  hasConflicts: boolean;",
      "  conflicts: Array<{",
      "    type: \"character\" | \"setting\" | \"plot\" | \"logic\" | \"world\";",
      "    summary: string; // required, 1-500 chars",
      "    evidence?: string; // optional, <= 2000 chars",
      "    suggestion?: string; // optional, <= 1000 chars",
      "  }>;",
      "};",
    ].join("\n"),
    minimalExample: JSON.stringify({
      hasConflicts: false,
      conflicts: [],
    }, null, 2),
  },
  submit_evaluation: {
    expectedType: [
      "type SubmitEvaluationArgs = {",
      "  artifactId?: string; // required when available; active artifact is used as fallback",
      "  artifactKey: string; // required, stable key for the reviewed artifact",
      "  verdict: \"pass\" | \"revise\" | \"block\";",
      "  summary: string; // required, 1-1000 chars",
      "  requiredChanges?: string; // optional, <= 2000 chars",
      "};",
    ].join("\n"),
    minimalExample: JSON.stringify({
      artifactKey: "outline-revision-1",
      verdict: "revise",
      summary: "前三章仍缺少明确小胜利。",
      requiredChanges: "第 2 章补一个可见线索，让读者感到主角有阶段性收获。",
    }, null, 2),
  },
};

function issuesFromZod(error: z.ZodError): ControlToolValidationIssue[] {
  return error.issues.map((issue) => ({
    path: issue.path.length > 0 ? issue.path.join(".") : "(root)",
    message: issue.message,
    code: issue.code,
  }));
}

function buildValidationError(
  toolName: string,
  issues: ControlToolValidationIssue[]
): ControlToolValidationError {
  const hints = CONTROL_TOOL_REPAIR_HINTS[toolName] ?? {
    expectedType: "No repair hint is registered for this control tool.",
    minimalExample: "{}",
  };
  return {
    toolName,
    issues,
    expectedType: hints.expectedType,
    minimalExample: hints.minimalExample,
  };
}

export function parseControlEventArgsDetailed(
  toolName: string,
  args: Record<string, unknown>
): ControlToolParseResult {
  const schema = CONTROL_TOOL_ARGS_SCHEMAS[toolName];
  if (!schema) {
    return {
      success: false,
      error: buildValidationError(toolName, [
        { path: "(tool)", message: `Unknown control tool: ${toolName}`, code: "unknown_tool" },
      ]),
    };
  }

  const result = schema.safeParse(args);
  if (!result.success) {
    return {
      success: false,
      error: buildValidationError(toolName, issuesFromZod(result.error)),
    };
  }

  switch (toolName) {
    case "submit_quality_report":
      return { success: true, event: { type: "submit_quality_report", ...result.data } as QualityReportEvent };
    case "propose_updates":
      return { success: true, event: { type: "propose_updates", ...result.data } as ProposalUpdatesEvent };
    case "start_update_builder":
      return { success: true, event: { type: "start_update_builder", ...result.data } as StartUpdateBuilderEvent };
    case "append_update_batch":
      return { success: true, event: { type: "append_update_batch", ...result.data } as AppendUpdateBatchEvent };
    case "append_outline_tree":
      return { success: true, event: { type: "append_outline_tree", ...result.data } as AppendOutlineTreeEvent };
    case "put_update_text_block":
      return { success: true, event: { type: "put_update_text_block", ...result.data } as PutUpdateTextBlockEvent };
    case "put_update_item_text_block":
      return { success: true, event: { type: "put_update_item_text_block", ...result.data } as PutUpdateItemTextBlockEvent };
    case "put_update_item_text_blocks":
      return { success: true, event: { type: "put_update_item_text_blocks", ...result.data } as PutUpdateItemTextBlocksEvent };
    case "finish_update_builder":
      return { success: true, event: { type: "finish_update_builder", ...result.data } as FinishUpdateBuilderEvent };
    case "begin_artifact_output":
      return { success: true, event: { type: "begin_artifact_output", ...result.data } as BeginArtifactOutputEvent };
    case "show_review_artifact":
      return { success: true, event: { type: "show_review_artifact", ...result.data } as ShowReviewArtifactEvent };
    case "submit_beat_plan":
      return { success: true, event: { type: "submit_beat_plan", ...result.data } as BeatPlanProposalEvent };
    case "submit_validation_report":
      return { success: true, event: { type: "submit_validation_report", ...result.data } as ValidationReportEvent };
    case "submit_evaluation":
      return { success: true, event: { type: "submit_evaluation", ...result.data } as EvaluationEvent };
    default:
      return {
        success: false,
        error: buildValidationError(toolName, [
          { path: "(tool)", message: `Unknown control tool: ${toolName}`, code: "unknown_tool" },
        ]),
      };
  }
}

export function formatControlToolValidationMessage(
  error: ControlToolValidationError,
  attempt: number,
  maxAttempts: number,
  fatal = false
): string {
  const issueText = error.issues
    .map((issue) => `- ${issue.path}: ${issue.message}${issue.code ? ` (${issue.code})` : ""}`)
    .join("\n");
  const status = fatal
    ? `control tool "${error.toolName}" 参数连续 ${attempt} 次校验失败，已停止本轮工具循环。`
    : `control tool "${error.toolName}" 参数校验失败（第 ${attempt}/${maxAttempts} 次）。`;
  const nextStep = fatal
    ? "未保存任何变更。请重试或缩小修改范围。"
    : `请修正 tool arguments 后重试；${AGENT_UPDATE_CHANNEL_RULES_PROMPT.replace(/\n/g, " ")} 如果当前任务不属于你的职责，请在正文中说明边界并等待工作流重新分派。`;

  return [
    status,
    "",
    "Zod issues:",
    issueText || "- (root): 参数格式不合法",
    "",
    "Expected TypeScript shape:",
    "```ts",
    error.expectedType,
    "```",
    "",
    "Minimal valid example:",
    "```json",
    error.minimalExample,
    "```",
    "",
    nextStep,
  ].join("\n");
}

/** 根据 tool name 校验并返回 control event（含 type 字段） */
export function parseControlEventArgs(
  toolName: string,
  args: Record<string, unknown>
): AgentControlEvent | null {
  const result = parseControlEventArgsDetailed(toolName, args);
  return result.success ? result.event : null;
}
