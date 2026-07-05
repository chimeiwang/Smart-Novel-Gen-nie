/**
 * Control event processor
 *
 * @module agents/graph/control-event-processor
 * @description 将 AgentRuntime 产出的 controlEvents 映射为业务行为。
 * Graph 节点只负责调用本处理器，不再直接承载 control tool 的业务状态机。
 */

import { interrupt as langGraphInterrupt } from "@langchain/langgraph";
import type {
  AgentControlEvent,
  AgentMessage,
  AgentQualityFields,
  AgentVisibleOutput,
  AgentUpdates,
  CoreAgentId,
  NovelData,
} from "./state";
import type { GraphState } from "./graph-definition";
import { trySaveQualityCheckResult as defaultSaveQualityCheckResult } from "@/agents/lib/quality-check-service";
import { hasAgentUpdates } from "./lore-update-schema";
import { sanitizeAgentUpdates } from "@/shared/contracts/agent-updates";
import { logger } from "@/shared/lib/logger";
import type { AgentUpdateSection } from "@/shared/contracts/agent-updates";
import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import type { ShowReviewArtifactEvent } from "@/shared/contracts/agent-control";
import {
  createOrUpdateAgentUpdatesArtifact as defaultCreateOrUpdateAgentUpdatesArtifact,
  createOrUpdateBeatPlanArtifact as defaultCreateOrUpdateBeatPlanArtifact,
  createOrUpdateTextArtifact as defaultCreateOrUpdateTextArtifact,
  loadUpdateBuilderArtifactUpdates as defaultLoadUpdateBuilderArtifactUpdates,
  submitArtifactEvaluation as defaultSubmitArtifactEvaluation,
  toReviewArtifactDtoWithFreshDiff,
  upsertUpdateBuilderArtifact as defaultUpsertUpdateBuilderArtifact,
} from "@/agents/artifacts/artifact-service";
import { prisma } from "@/shared/db/prisma";
import type {
  ChapterDraftTarget,
  ReviewArtifactDto,
  ReviewArtifactEvaluationVerdict,
  TextReviewArtifactKind,
} from "@/shared/contracts/review-artifact";
import type { BeatPlanDraft } from "@/shared/contracts/beat-plan";
import { markTaskAwaitingUserReview as defaultMarkTaskAwaitingUserReview } from "./task-state";
import { createArtifactReviewInterrupt } from "@/shared/contracts/user-decision";
import {
  buildTextUpdate,
  buildOutlineTreeUpdate,
  isTextUpdateSection,
  mergeAgentUpdates,
  putItemTextBlock,
  validateAgentUpdatesForReview,
} from "@/agents/artifacts/update-builder";
import type { ReviewArtifactStatus } from "@/shared/contracts/review-artifact";

export const DEFAULT_MAX_CALL_CHAIN_DEPTH = 20;
export const ARTIFACT_OUTPUT_START_MARKER = "ARTIFACT_OUTPUT_START";
export const ARTIFACT_OUTPUT_END_MARKER = "ARTIFACT_OUTPUT_END";

const AGENT_ALLOWED_UPDATE_SECTIONS: Partial<Record<CoreAgentId, AgentUpdateSection[]>> = {
  "设定": [
    "characters", "locations", "items", "factions", "glossaries",
    "characterExperiences", "worldSetting", "storyBackground",
  ],
  "剧情": ["outline", "outlineContent", "outlineAdjustments", "foreshadowing"],
};

function sanitizeUpdatesForAgent(raw: unknown, agentId: CoreAgentId): AgentUpdates | undefined {
  return sanitizeAgentUpdates(raw, AGENT_ALLOWED_UPDATE_SECTIONS[agentId] ?? []);
}

function countExistingOutlineTreeBatches(artifactKey: string, updates: AgentUpdates | undefined): number {
  const safeArtifactKey = artifactKey
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "outline-tree";
  const prefix = `${safeArtifactKey}-b`;
  let maxBatch = -1;
  for (const adjustment of updates?.outlineAdjustments ?? []) {
    const key = adjustment.clientKey;
    if (!key?.startsWith(prefix)) continue;
    const match = /^(.+)-b(\d+)-/.exec(key);
    if (!match) continue;
    maxBatch = Math.max(maxBatch, Number(match[2]));
  }
  return maxBatch + 1;
}

export interface ControlEventProcessorState {
  taskId: string;
  chapterId: string;
  currentOperation?: CreativeOperation | null;
  chapterDraftTarget?: ChapterDraftTarget | null;
  qualityCheckId?: string | null;
  novelData?: NovelData;
}

export interface ControlEventProcessResult {
  conversationHistory: AgentMessage[];
  pendingUpdates?: AgentUpdates | null;
  activeArtifactId?: string | null;
  artifactIteration?: number;
  pendingUserResponse?: boolean;
  reviewerAgent?: CoreAgentId | null;
  reviserAgent?: CoreAgentId | null;
  controlEvents?: undefined;
  errorMessage?: string | null;
}

export interface ExecuteUpdatesResult {
  success: boolean;
  summary: string;
  errors?: string[];
  savedCount?: number;
}

export interface ControlEventProcessorDeps {
  emitEvent: (type: string, payload: Record<string, unknown>) => void;
  interrupt?: (payload: Record<string, unknown>) => unknown;
  createOrUpdateAgentUpdatesArtifact?: (input: {
    novelId: string;
    chapterId?: string | null;
    taskId?: string | null;
    workflowRunId?: string | null;
    artifactKey?: string | null;
    summary: string;
    updates: AgentUpdates;
    agentId: CoreAgentId;
    reviewerAgent?: CoreAgentId | null;
    novelData?: NovelData;
  }) => Promise<ReviewArtifactDto>;
  createOrUpdateTextArtifact?: (input: {
    novelId: string;
    chapterId?: string | null;
    taskId?: string | null;
    workflowRunId?: string | null;
    artifactKey?: string | null;
    kind: TextReviewArtifactKind;
    summary: string;
    content: string;
    agentId: CoreAgentId;
    reviewerAgent?: CoreAgentId | null;
    chapterDraftTarget?: ChapterDraftTarget | null;
  }) => Promise<ReviewArtifactDto>;
  createOrUpdateBeatPlanArtifact?: (input: {
    novelId: string;
    chapterId?: string | null;
    taskId?: string | null;
    workflowRunId?: string | null;
    artifactKey?: string | null;
    summary: string;
    beatPlan: BeatPlanDraft;
    agentId: CoreAgentId;
    reviewerAgent?: CoreAgentId | null;
  }) => Promise<ReviewArtifactDto>;
  loadUpdateBuilderArtifactUpdates?: (input: {
    novelId: string;
    artifactKey: string;
  }) => Promise<AgentUpdates | null>;
  upsertUpdateBuilderArtifact?: (input: {
    novelId: string;
    chapterId?: string | null;
    taskId?: string | null;
    workflowRunId?: string | null;
    artifactKey: string;
    summary: string;
    updates: AgentUpdates;
    agentId: CoreAgentId;
    reviewerAgent?: CoreAgentId | null;
    status: Extract<ReviewArtifactStatus, "draft" | "under_review">;
    novelData?: NovelData;
  }) => Promise<ReviewArtifactDto>;
  submitArtifactEvaluation?: (input: {
    artifactId: string;
    evaluatorAgent: CoreAgentId;
    verdict: ReviewArtifactEvaluationVerdict;
    summary: string;
    requiredChanges?: string;
    deferPassStatus?: boolean;
  }) => Promise<ReviewArtifactDto>;
  findOpenReviewArtifact?: (input: {
    artifactId?: string;
    artifactKey?: string;
    novelId: string;
  }) => Promise<ReviewArtifactDto | null>;
  markTaskAwaitingUserReview?: (input: {
    taskId: string;
    artifactId: string;
    state: GraphState;
    operationStage?: string;
  }) => Promise<void>;
  saveQualityCheckResult?: (
    agentId: CoreAgentId,
    output: AgentVisibleOutput & Partial<AgentQualityFields>,
    chapterId?: string,
    checkId?: string
  ) => Promise<unknown>;
  interruptOnUserApproval?: boolean;
  now?: () => number;
}

export interface ProcessControlEventsInput {
  events: AgentControlEvent[];
  state: ControlEventProcessorState;
  graphState?: GraphState;
  activeAgent: CoreAgentId;
  output: AgentVisibleOutput;
  updatedHistory: AgentMessage[];
}

export async function processControlEvents(
  input: ProcessControlEventsInput,
  deps: ControlEventProcessorDeps
): Promise<ControlEventProcessResult> {
  const {
    events,
    state,
    activeAgent,
    output,
    updatedHistory,
  } = input;
  const emitEvent = deps.emitEvent;
  const interrupt = deps.interrupt ?? langGraphInterrupt;
  const createOrUpdateAgentUpdatesArtifact = deps.createOrUpdateAgentUpdatesArtifact ?? defaultCreateOrUpdateAgentUpdatesArtifact;
  const createOrUpdateTextArtifact = deps.createOrUpdateTextArtifact ?? defaultCreateOrUpdateTextArtifact;
  const createOrUpdateBeatPlanArtifact = deps.createOrUpdateBeatPlanArtifact ?? defaultCreateOrUpdateBeatPlanArtifact;
  const loadUpdateBuilderArtifactUpdates = deps.loadUpdateBuilderArtifactUpdates ?? defaultLoadUpdateBuilderArtifactUpdates;
  const upsertUpdateBuilderArtifact = deps.upsertUpdateBuilderArtifact ?? defaultUpsertUpdateBuilderArtifact;
  const submitArtifactEvaluation = deps.submitArtifactEvaluation ?? defaultSubmitArtifactEvaluation;
  const findOpenReviewArtifact = deps.findOpenReviewArtifact ?? (async (input) => {
    if (!input.artifactId && !input.artifactKey) return null;
    const artifact = await prisma.reviewArtifact.findFirst({
      where: {
        novelId: input.novelId,
        OR: [
          ...(input.artifactId ? [{ id: input.artifactId }] : []),
          ...(input.artifactKey ? [{ artifactKey: input.artifactKey }] : []),
        ],
        status: { in: ["draft", "under_review", "awaiting_user"] },
      },
      include: { evaluations: { orderBy: { createdAt: "desc" } } },
      orderBy: [
        { updatedAt: "desc" },
        { createdAt: "desc" },
      ],
    });
    return artifact ? toReviewArtifactDtoWithFreshDiff(artifact) : null;
  });
  const markTaskAwaitingUserReview = deps.markTaskAwaitingUserReview ?? defaultMarkTaskAwaitingUserReview;
  const saveQualityCheckResult = deps.saveQualityCheckResult ?? defaultSaveQualityCheckResult;
  const interruptOnUserApproval = deps.interruptOnUserApproval ?? true;
  const now = deps.now ?? Date.now;

  logger.info("CONTROL_EVENTS", "处理 controlEvents", {
    count: events.length,
    types: events.map((e) => e.type),
    agentId: activeAgent,
  });

  let activeArtifactId: string | null = null;
  let artifactToReview: ReviewArtifactDto | null = null;
  let awaitingUserReview = false;
  let lastReviewerAgent: CoreAgentId | null = null;
  const builderStates = new Map<string, {
    artifactKey: string;
    summary: string;
    reviewerAgent: CoreAgentId | null;
    submitForReview: boolean;
    updates: AgentUpdates;
    finishRequested: boolean;
    outlineTreeBatchCount: number;
  }>();

  async function getBuilderState(artifactKey: string): Promise<{
    artifactKey: string;
    summary: string;
    reviewerAgent: CoreAgentId | null;
    submitForReview: boolean;
    updates: AgentUpdates;
    finishRequested: boolean;
    outlineTreeBatchCount: number;
  }> {
    const existing = builderStates.get(artifactKey);
    if (existing) return existing;
    const persisted = await loadUpdateBuilderArtifactUpdates({
      novelId: state.novelData?.novelId ?? "",
      artifactKey,
    });
    const allowedPersisted = sanitizeUpdatesForAgent(persisted, activeAgent);
    const created = {
      artifactKey,
      summary: "构建待审核更新草案",
      reviewerAgent: null,
      submitForReview: false,
      updates: allowedPersisted ?? {},
      finishRequested: false,
      outlineTreeBatchCount: countExistingOutlineTreeBatches(artifactKey, allowedPersisted),
    };
    builderStates.set(artifactKey, created);
    return created;
  }

  const artifactOutputBlocks = extractArtifactOutputBlocks(output.content);
  let nextArtifactOutputBlockIndex = 0;
  const takeNextArtifactOutputBlock = () => artifactOutputBlocks[nextArtifactOutputBlockIndex++]?.trim() ?? "";
  const pendingShowArtifactEvents: ShowReviewArtifactEvent[] = [];

  function buildBeatPlanDraftFromEvent(event: Extract<AgentControlEvent, { type: "submit_beat_plan" }>): BeatPlanDraft {
    const sceneBeats = event.sceneBeats?.length
      ? event.sceneBeats.map((beat, index) => ({
          order: beat.order ?? index + 1,
          goal: beat.goal,
          conflict: beat.conflict,
          characters: beat.characters,
          foreshadowingRefs: beat.foreshadowingRefs,
          estimatedWords: beat.estimatedWords,
          acceptanceCriteria: beat.acceptanceCriteria,
        }))
      : [{
          order: 1,
          goal: event.summary,
          characters: [],
          estimatedWords: 0,
          acceptanceCriteria: event.summary,
        }];
    return {
      title: event.title,
      summary: event.summary,
      chapterGoal: event.chapterGoal ?? event.title,
      mainPlotConnection: event.mainPlotConnection,
      chapterAcceptanceCriteria: event.chapterAcceptanceCriteria,
      totalEstimatedWords: event.totalEstimatedWords,
      sceneBeats,
    };
  }

  for (const event of events) {
    switch (event.type) {
      case "propose_updates": {
        const sanitized = sanitizeUpdatesForAgent(event.updates, activeAgent);

        if (!sanitized || !hasAgentUpdates(sanitized)) {
          logger.info("CONTROL_EVENTS", "propose_updates sanitize 后无有效数据", {
            agentId: activeAgent,
            summary: event.summary,
          });
          break;
        }

        const reviewerAgent = event.reviewerAgent ?? (event.submitForReview ? "编辑" : null);
        const artifact = await createOrUpdateAgentUpdatesArtifact({
          novelId: state.novelData?.novelId ?? "",
          chapterId: state.chapterId,
          taskId: state.taskId,
          artifactKey: event.artifactKey ?? null,
          summary: event.summary,
          updates: sanitized,
          agentId: activeAgent,
          reviewerAgent,
          novelData: state.novelData,
        });
        activeArtifactId = artifact.id;
        emitEvent("artifact_submitted", {
          agentId: activeAgent,
          artifact,
          artifactId: artifact.id,
          status: artifact.status,
          revision: artifact.revision,
        });
        if (artifact.status === "under_review" && artifact.reviewerAgent) {
          artifactToReview = artifact;
        }
        break;
      }

      case "start_update_builder": {
        const builder = builderStates.get(event.artifactKey) ?? {
          artifactKey: event.artifactKey,
          summary: event.summary,
          reviewerAgent: null,
          submitForReview: false,
          updates: {},
          finishRequested: false,
          outlineTreeBatchCount: 0,
        };
        builder.summary = event.summary;
        builder.reviewerAgent = event.reviewerAgent ?? builder.reviewerAgent;
        builder.submitForReview = event.submitForReview ?? builder.submitForReview;
        builderStates.set(event.artifactKey, builder);
        emitEvent("update_builder_started", {
          agentId: activeAgent,
          artifactKey: event.artifactKey,
          summary: event.summary,
        });
        break;
      }

      case "append_update_batch": {
        const builder = await getBuilderState(event.artifactKey);
        const sanitized = sanitizeUpdatesForAgent(event.updates, activeAgent);
        if (sanitized && hasAgentUpdates(sanitized)) {
          builder.updates = mergeAgentUpdates(builder.updates, sanitized);
          builder.summary = event.summary ?? builder.summary;
          builderStates.set(event.artifactKey, builder);
          emitEvent("update_builder_batch_appended", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            sectionNames: Object.keys(sanitized),
          });
        } else {
          emitEvent("update_builder_batch_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            reason: "no_allowed_updates",
          });
        }
        break;
      }

      case "append_outline_tree": {
        const builder = await getBuilderState(event.artifactKey);
        const outlineTreeUpdate = buildOutlineTreeUpdate({
          artifactKey: event.artifactKey,
          batchIndex: builder.outlineTreeBatchCount,
          stages: event.stages,
        });
        const sanitized = sanitizeUpdatesForAgent(outlineTreeUpdate, activeAgent);
        if (sanitized && hasAgentUpdates(sanitized)) {
          builder.updates = mergeAgentUpdates(builder.updates, sanitized);
          builder.summary = event.summary ?? builder.summary;
          builder.outlineTreeBatchCount += 1;
          builderStates.set(event.artifactKey, builder);
          emitEvent("update_builder_outline_tree_appended", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            stageCount: event.stages.length,
            nodeCount: outlineTreeUpdate.outlineAdjustments?.length ?? 0,
          });
        } else {
          emitEvent("update_builder_batch_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            reason: "outline_tree_not_allowed",
          });
        }
        break;
      }

      case "put_update_text_block": {
        const builder = await getBuilderState(event.artifactKey);
        if (!isTextUpdateSection(event.section)) {
          emitEvent("update_builder_text_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: event.section,
            reason: "invalid_text_section",
          });
          break;
        }
        const textContent = takeNextArtifactOutputBlock();
        if (!textContent) {
          emitEvent("update_builder_text_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: event.section,
            reason: "missing_marked_text",
          });
          break;
        }
        const sanitized = sanitizeUpdatesForAgent(buildTextUpdate(event.section, textContent), activeAgent);
        if (sanitized && hasAgentUpdates(sanitized)) {
          builder.updates = mergeAgentUpdates(builder.updates, sanitized);
          builder.summary = event.summary ?? builder.summary;
          builderStates.set(event.artifactKey, builder);
          emitEvent("update_builder_text_put", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: event.section,
          });
        } else {
          emitEvent("update_builder_text_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: event.section,
            reason: "section_not_allowed",
          });
        }
        break;
      }

      case "put_update_item_text_block": {
        const builder = await getBuilderState(event.artifactKey);
        const textContent = takeNextArtifactOutputBlock();
        if (!textContent) {
          emitEvent("update_builder_text_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: event.section,
            reason: "missing_marked_text",
          });
          break;
        }
        const result = putItemTextBlock(builder.updates, {
          section: event.section,
          field: event.field,
          targetId: event.targetId,
          targetKey: event.targetKey,
          targetName: event.targetName,
          content: textContent,
        });
        if (!result.success) {
          emitEvent("update_builder_text_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: event.section,
            reason: result.reason,
          });
          break;
        }
        const sanitized = sanitizeUpdatesForAgent(result.updates, activeAgent);
        if (sanitized && hasAgentUpdates(sanitized)) {
          builder.updates = sanitized;
          builder.summary = event.summary ?? builder.summary;
          builderStates.set(event.artifactKey, builder);
          emitEvent("update_builder_text_put", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: event.section,
            field: event.field,
          });
        } else {
          emitEvent("update_builder_text_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: event.section,
            reason: "section_not_allowed",
          });
        }
        break;
      }

      case "put_update_item_text_blocks": {
        const builder = await getBuilderState(event.artifactKey);
        let nextUpdates = builder.updates;
        let appliedCount = 0;

        for (const block of event.blocks) {
          const textContent = takeNextArtifactOutputBlock();
          if (!textContent) {
            emitEvent("update_builder_text_ignored", {
              agentId: activeAgent,
              artifactKey: event.artifactKey,
              section: block.section,
              reason: "missing_marked_text",
            });
            continue;
          }

          const result = putItemTextBlock(nextUpdates, {
            section: block.section,
            field: block.field,
            targetId: block.targetId,
            targetKey: block.targetKey,
            targetName: block.targetName,
            content: textContent,
          });
          if (!result.success) {
            emitEvent("update_builder_text_ignored", {
              agentId: activeAgent,
              artifactKey: event.artifactKey,
              section: block.section,
              reason: result.reason,
            });
            continue;
          }

          nextUpdates = result.updates;
          appliedCount += 1;
          emitEvent("update_builder_text_put", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: block.section,
            field: block.field,
          });
        }

        if (appliedCount <= 0) {
          break;
        }

        const sanitized = sanitizeUpdatesForAgent(nextUpdates, activeAgent);
        if (sanitized && hasAgentUpdates(sanitized)) {
          builder.updates = sanitized;
          builder.summary = event.blocks.find((block) => block.summary)?.summary ?? builder.summary;
          builderStates.set(event.artifactKey, builder);
        } else {
          emitEvent("update_builder_text_ignored", {
            agentId: activeAgent,
            artifactKey: event.artifactKey,
            section: "multiple",
            reason: "section_not_allowed",
          });
        }
        break;
      }

      case "finish_update_builder": {
        const builder = await getBuilderState(event.artifactKey);
        builder.summary = event.summary;
        builder.reviewerAgent = event.reviewerAgent ?? builder.reviewerAgent;
        builder.submitForReview = event.submitForReview ?? builder.submitForReview;
        builder.finishRequested = true;
        builderStates.set(event.artifactKey, builder);
        break;
      }

      case "begin_artifact_output": {
        const content = extractArtifactOutputContent(output.content);
        if (!content) {
          logger.warn("CONTROL_EVENTS", "begin_artifact_output 缺少可保存正文", {
            agentId: activeAgent,
            summary: event.summary,
            kind: event.kind,
          });
          break;
        }

        const reviewerAgent = event.reviewerAgent ?? (event.submitForReview ? "编辑" : null);
        const artifactKey = state.currentOperation
          ? `${state.taskId}:${state.currentOperation.kind}`
          : event.artifactKey ?? null;
        const artifact = await createOrUpdateTextArtifact({
          novelId: state.novelData?.novelId ?? "",
          chapterId: state.novelData?.chapterId ?? state.chapterId,
          taskId: state.taskId,
          artifactKey,
          kind: event.kind,
          summary: event.summary,
          content,
          agentId: activeAgent,
          reviewerAgent,
          chapterDraftTarget: event.kind === "chapter_draft" ? state.chapterDraftTarget ?? null : null,
        });
        activeArtifactId = artifact.id;
        emitEvent("artifact_submitted", {
          agentId: activeAgent,
          artifact,
          artifactId: artifact.id,
          status: artifact.status,
          revision: artifact.revision,
        });
        if (artifact.status === "under_review" && artifact.reviewerAgent) {
          artifactToReview = artifact;
        }
        break;
      }

      case "show_review_artifact": {
        pendingShowArtifactEvents.push(event);
        break;
      }

      case "submit_quality_report": {
        const qualityOutput: AgentVisibleOutput & Partial<AgentQualityFields> = {
          ...output,
          scores: event.scores,
          qualityGate: event.qualityGate,
          rewriteBrief: event.rewriteBrief,
        };
        saveQualityCheckResult(
          activeAgent,
          qualityOutput,
          state.chapterId,
          state.qualityCheckId ?? undefined
        ).catch((e) => {
          logger.warn("CONTROL_EVENTS", "质量检查结果保存异常", { error: String(e) });
        });
        emitEvent("quality_report_submitted", {
          agentId: activeAgent,
          qualityGate: event.qualityGate,
          overallScore: event.scores.overall,
        });
        break;
      }

      case "submit_validation_report": {
        emitEvent("validation_report_submitted", {
          agentId: activeAgent,
          hasConflicts: event.hasConflicts,
          conflictCount: event.conflicts.length,
        });
        logger.info("CONTROL_EVENTS", "校验报告已提交", {
          agentId: activeAgent,
          hasConflicts: event.hasConflicts,
          conflictCount: event.conflicts.length,
        });
        break;
      }

      case "submit_evaluation": {
        const artifactId = event.artifactId ?? activeArtifactId;
        let artifact: ReviewArtifactDto | null = null;
        if (artifactId) {
          artifact = await submitArtifactEvaluation({
            artifactId,
            evaluatorAgent: activeAgent,
            verdict: event.verdict,
            summary: event.summary,
            requiredChanges: event.requiredChanges,
          });
          activeArtifactId = artifact.id;
        }
        emitEvent("workflow_evaluation_submitted", {
          agentId: activeAgent,
          artifactId: artifact?.id ?? artifactId,
          artifactKey: event.artifactKey,
          verdict: event.verdict,
          summary: event.summary,
          requiredChanges: event.requiredChanges,
          revisionMode: event.revisionMode,
          patches: event.patches,
        });
        if (artifact && event.verdict === "pass") {
          if (!input.graphState) {
            throw new Error("markTaskAwaitingUserReview requires graphState to persist artifactReview.");
          }
          await markTaskAwaitingUserReview({
            taskId: state.taskId,
            artifactId: artifact.id,
            state: input.graphState,
          });
          awaitingUserReview = true;
          lastReviewerAgent = activeAgent;
          emitEvent("artifact_awaiting_user_approval", {
            agentId: activeAgent,
            artifact,
            artifactId: artifact.id,
          });
          if (interruptOnUserApproval) {
            const decision = interrupt(createArtifactReviewInterrupt({
              artifactId: artifact.id,
              artifact,
              content: output.content,
              summary: event.summary,
            }));
            if (decision) {
              return {
                conversationHistory: updatedHistory,
                activeArtifactId: artifact.id,
                pendingUserResponse: true,
                reviewerAgent: activeAgent,
                reviserAgent: null,
                controlEvents: undefined,
              };
            }
          }
        }
        logger.info("CONTROL_EVENTS", "工作流评估已提交", {
          agentId: activeAgent,
          artifactKey: event.artifactKey,
          verdict: event.verdict,
        });
        break;
      }

      case "submit_beat_plan": {
        const reviewerAgent = event.reviewerAgent ?? (event.submitForReview === false ? null : "编辑");
        const artifact = await createOrUpdateBeatPlanArtifact({
          novelId: state.novelData?.novelId ?? "",
          chapterId: state.novelData?.chapterId ?? state.chapterId,
          taskId: state.taskId,
          artifactKey: event.artifactKey ?? `${state.taskId}:plan_chapter`,
          summary: event.summary,
          beatPlan: buildBeatPlanDraftFromEvent(event),
          agentId: activeAgent,
          reviewerAgent,
        });
        activeArtifactId = artifact.id;
        logger.info("CONTROL_EVENTS", "Beat Plan 已提交", {
          agentId: activeAgent,
          title: event.title,
          beatCount: event.beatCount,
          summary: event.summary.slice(0, 200),
          artifactId: artifact.id,
        });
        emitEvent("artifact_submitted", {
          agentId: activeAgent,
          artifact,
          artifactId: artifact.id,
          status: artifact.status,
          revision: artifact.revision,
        });
        emitEvent("beat_plan_submitted", {
          agentId: activeAgent,
          title: event.title,
          beatCount: event.beatCount,
          artifactId: artifact.id,
        });
        if (artifact.status === "under_review" && artifact.reviewerAgent) {
          artifactToReview = artifact;
        }
        break;
      }

      default:
        break;
    }
  }

  for (const builder of builderStates.values()) {
    const allowedUpdates = sanitizeUpdatesForAgent(builder.updates, activeAgent);
    if (!allowedUpdates || !hasAgentUpdates(allowedUpdates)) {
      logger.info("CONTROL_EVENTS", "update builder 无有效 updates，跳过持久化", {
        agentId: activeAgent,
        artifactKey: builder.artifactKey,
      });
      continue;
    }

    let status: Extract<ReviewArtifactStatus, "draft" | "under_review"> = "draft";
    let reviewerAgent = builder.reviewerAgent;
    if (builder.finishRequested) {
      const validationErrors = validateAgentUpdatesForReview(allowedUpdates);
      if (validationErrors.length > 0) {
        emitEvent("update_builder_validation_failed", {
          agentId: activeAgent,
          artifactKey: builder.artifactKey,
          errors: validationErrors,
        });
      } else {
        reviewerAgent = reviewerAgent ?? (builder.submitForReview ? "编辑" : null);
        status = reviewerAgent ? "under_review" : "draft";
      }
    }

    const artifact = await upsertUpdateBuilderArtifact({
      novelId: state.novelData?.novelId ?? "",
      chapterId: state.chapterId,
      taskId: state.taskId,
      artifactKey: builder.artifactKey,
      summary: builder.summary,
      updates: allowedUpdates,
      agentId: activeAgent,
      reviewerAgent,
      status,
      novelData: state.novelData,
    });
    activeArtifactId = artifact.id;
    emitEvent("artifact_submitted", {
      agentId: activeAgent,
      artifact,
      artifactId: artifact.id,
      status: artifact.status,
      revision: artifact.revision,
    });
    if (artifact.status === "under_review" && artifact.reviewerAgent) {
      artifactToReview = artifact;
    }
  }

  for (const event of pendingShowArtifactEvents) {
    const artifact = await findOpenReviewArtifact({
      artifactId: event.artifactId,
      artifactKey: event.artifactKey,
      novelId: state.novelData?.novelId ?? "",
    });
    if (!artifact) {
      emitEvent("update_builder_text_ignored", {
        agentId: activeAgent,
        artifactKey: event.artifactKey ?? event.artifactId ?? "unknown",
        section: "review_artifact",
        reason: "artifact_not_found_or_not_open",
      });
      continue;
    }
    emitEvent("review_artifact_requested", {
      agentId: activeAgent,
      artifactId: artifact.id,
      artifact,
      reason: event.reason,
    });
  }

  return {
    conversationHistory: updatedHistory,
    activeArtifactId: activeArtifactId ?? artifactToReview?.id ?? null,
    pendingUserResponse: awaitingUserReview ? true : undefined,
    reviewerAgent: lastReviewerAgent,
    reviserAgent: awaitingUserReview ? null : undefined,
    controlEvents: undefined,
  };
}

export function extractArtifactOutputContent(rawContent: string): string {
  return extractArtifactOutputBlocks(rawContent)[0] ?? cleanUnmarkedArtifactOutput(rawContent);
}

export function extractArtifactOutputBlocks(rawContent: string): string[] {
  const blocks: string[] = [];
  let searchStart = 0;

  while (searchStart < rawContent.length) {
    const startIndex = rawContent.indexOf(ARTIFACT_OUTPUT_START_MARKER, searchStart);
    if (startIndex < 0) break;

    const contentStart = startIndex + ARTIFACT_OUTPUT_START_MARKER.length;
    const endIndex = rawContent.indexOf(ARTIFACT_OUTPUT_END_MARKER, contentStart);
    const selected = endIndex >= 0
      ? rawContent.slice(contentStart, endIndex)
      : rawContent.slice(contentStart);
    const cleaned = cleanMarkedArtifactOutput(selected);
    if (cleaned) blocks.push(cleaned);

    if (endIndex < 0) break;
    searchStart = endIndex + ARTIFACT_OUTPUT_END_MARKER.length;
  }

  return blocks;
}

function cleanMarkedArtifactOutput(content: string): string {
  return content
    .replace(/^\s*[\r\n]+/, "")
    .replace(/[\r\n]+\s*$/, "")
    .trim();
}

function cleanUnmarkedArtifactOutput(rawContent: string): string {
  const normalized = rawContent.replace(/\r\n/g, "\n").trim();
  const withoutPrelude = stripArtifactPrelude(normalized);
  const withoutProcessSections = stripArtifactProcessSections(withoutPrelude);
  return stripArtifactPostlude(withoutProcessSections).trim();
}

function stripArtifactPrelude(content: string): string {
  const candidates = [
    /^#\s+《.+?》.+$/m,
    /^#\s+.+?(?:大纲|草案|修订稿|修改稿|正文|设定|Beat Plan).+$/m,
    /^##\s*第[一二三四五六七八九十百\d]+[章节卷幕]\s+/m,
    /^第[一二三四五六七八九十百\d]+[章节卷幕]\s+/m,
  ];

  const firstMatch = candidates
    .map((pattern) => pattern.exec(content))
    .filter((match): match is RegExpExecArray => Boolean(match))
    .sort((a, b) => a.index - b.index)[0];

  return firstMatch ? content.slice(firstMatch.index).trimStart() : content;
}

function stripArtifactProcessSections(content: string): string {
  const lines = content.split("\n");
  const kept: string[] = [];
  let skipping = false;

  for (const line of lines) {
    const trimmed = line.trim();
    const isProcessSection =
      /^#{1,3}\s*(?:修订要点对照|整体节奏调整说明|编辑建议落实情况|修改说明)\s*$/.test(trimmed) ||
      /^\*\*(?:编辑建议落实情况|修改说明|修订说明|整体节奏调整说明)[:：]\*\*/.test(trimmed);

    if (isProcessSection) {
      skipping = true;
      continue;
    }

    if (skipping) {
      const isNextContentBoundary =
        /^#{1,3}\s*第[一二三四五六七八九十百\d]+[章节卷幕]\s+/.test(trimmed) ||
        /^第[一二三四五六七八九十百\d]+[章节卷幕]\s+/.test(trimmed) ||
        /^#{1,2}\s+《.+?》/.test(trimmed);
      if (!isNextContentBoundary) continue;
      skipping = false;
    }

    kept.push(line);
  }

  return kept.join("\n");
}

function stripArtifactPostlude(content: string): string {
  const lines = content.split("\n");
  while (lines.length > 0) {
    const trimmed = lines[lines.length - 1]?.trim() ?? "";
    if (!trimmed) {
      lines.pop();
      continue;
    }
    if (
      /^(?:以上|以上为|以上就是|接下来|请|可以给你审核了|你看看)/.test(trimmed) &&
      /(?:审核|复审|提交|确认|应用|写入|入库|调整)/.test(trimmed)
    ) {
      lines.pop();
      continue;
    }
    if (trimmed === "---" && !(lines[lines.length - 2] ?? "").trim()) {
      lines.pop();
      continue;
    }
    break;
  }
  return lines.join("\n");
}
