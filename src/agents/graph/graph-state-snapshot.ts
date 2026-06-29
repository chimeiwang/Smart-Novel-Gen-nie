import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import { CreativeOperationSchema } from "@/shared/contracts/creative-operation";
import type {
  AgentMessage,
  AgentOutput,
  AgentUpdates,
  ArtifactReviewState,
  CoreAgentId,
  OperationStep,
  PendingAgentCall,
  WritingPhase,
} from "./state";
import {
  collectAgentOutputs,
  createDefaultArtifactReviewState,
  normalizeArtifactReviewState,
} from "./state";
import type { GraphState } from "./graph-definition";

export type SerializableGraphStateSnapshot = {
  taskId: string;
  userId: string;
  novelId: string;
  chapterId: string;
  targetWordCount: number;
  phase: WritingPhase;
  userMessage: string;
  pendingUserResponse: boolean;
  conversationHistory: AgentMessage[];
  activeAgent: CoreAgentId | null;
  currentOperation: CreativeOperation | null;
  operationMode: GraphState["operationMode"];
  operationStep: OperationStep;
  operationStage: string | null;
  chapterDraftTarget: GraphState["chapterDraftTarget"];
  agentOutputs: Partial<Record<CoreAgentId, AgentOutput>>;
  loreAdvisorOutput: AgentOutput | null;
  plotAdvisorOutput: AgentOutput | null;
  writerOutput: AgentOutput | null;
  validatorOutput: AgentOutput | null;
  editorOutput: AgentOutput | null;
  generatedContent: string;
  pendingUpdates: AgentUpdates | null;
  pendingAgentCall: PendingAgentCall | null;
  errorMessage: string | null;
  qualityCheckId: string | null;
  artifactReview: ArtifactReviewState;
  activeArtifactId: string | null;
  artifactMode: "none" | "review_loop";
  reviewerAgent: CoreAgentId | null;
  reviserAgent: CoreAgentId | null;
  pendingArtifactRevision: GraphState["pendingArtifactRevision"];
  artifactIteration: number;
  maxArtifactIterations: number;
};

export function serializeGraphStateSnapshot(state: GraphState): string {
  const snapshot: SerializableGraphStateSnapshot = {
    taskId: state.taskId,
    userId: state.userId,
    novelId: state.novelId,
    chapterId: state.chapterId,
    targetWordCount: state.targetWordCount,
    phase: state.phase,
    userMessage: state.userMessage,
    pendingUserResponse: state.pendingUserResponse,
    conversationHistory: state.conversationHistory,
    activeAgent: state.activeAgent,
    currentOperation: state.currentOperation ?? null,
    operationMode: state.operationMode,
    operationStep: state.operationStep ?? "init",
    operationStage: state.operationStage ?? null,
    chapterDraftTarget: state.chapterDraftTarget ?? null,
    agentOutputs: collectAgentOutputs(state),
    loreAdvisorOutput: state.loreAdvisorOutput,
    plotAdvisorOutput: state.plotAdvisorOutput,
    writerOutput: state.writerOutput,
    validatorOutput: state.validatorOutput,
    editorOutput: state.editorOutput,
    generatedContent: state.generatedContent,
    pendingUpdates: state.pendingUpdates,
    pendingAgentCall: state.pendingAgentCall,
    errorMessage: state.errorMessage,
    qualityCheckId: state.qualityCheckId ?? null,
    artifactReview: normalizeArtifactReviewState(state),
    activeArtifactId: state.activeArtifactId ?? null,
    artifactMode: state.artifactMode ?? "none",
    reviewerAgent: state.reviewerAgent ?? null,
    reviserAgent: state.reviserAgent ?? null,
    pendingArtifactRevision: state.pendingArtifactRevision ?? null,
    artifactIteration: state.artifactIteration ?? 0,
    maxArtifactIterations: state.maxArtifactIterations ?? 5,
  };

  return JSON.stringify(snapshot);
}

export function deserializeGraphStateSnapshot(
  serialized: string | null | undefined
): SerializableGraphStateSnapshot | null {
  if (!serialized) return null;

  try {
    const parsed = JSON.parse(serialized) as Partial<SerializableGraphStateSnapshot>;
    if (!parsed || typeof parsed !== "object") return null;
    if (
      typeof parsed.taskId !== "string" ||
      typeof parsed.userId !== "string" ||
      typeof parsed.novelId !== "string" ||
      typeof parsed.chapterId !== "string" ||
      typeof parsed.targetWordCount !== "number" ||
      !Array.isArray(parsed.conversationHistory)
    ) {
      return null;
    }

    const operation = parsed.currentOperation ?? null;
    if (operation !== null && !CreativeOperationSchema.safeParse(operation).success) {
      return null;
    }

    const legacyCompatible = {
      taskId: parsed.taskId,
      userId: parsed.userId,
      novelId: parsed.novelId,
      chapterId: parsed.chapterId,
      targetWordCount: parsed.targetWordCount,
      phase: parsed.phase ?? "idle",
      userMessage: parsed.userMessage ?? "",
      pendingUserResponse: Boolean(parsed.pendingUserResponse),
      conversationHistory: parsed.conversationHistory,
      activeAgent: parsed.activeAgent ?? null,
      currentOperation: operation as CreativeOperation | null,
      operationMode: parsed.operationMode ?? "operation_graph",
      operationStep: parsed.operationStep ?? "init",
      operationStage: parsed.operationStage ?? null,
      chapterDraftTarget: parsed.chapterDraftTarget ?? null,
      agentOutputs: parsed.agentOutputs ?? {},
      loreAdvisorOutput: parsed.loreAdvisorOutput ?? null,
      plotAdvisorOutput: parsed.plotAdvisorOutput ?? null,
      writerOutput: parsed.writerOutput ?? null,
      validatorOutput: parsed.validatorOutput ?? null,
      editorOutput: parsed.editorOutput ?? null,
      generatedContent: parsed.generatedContent ?? "",
      pendingUpdates: parsed.pendingUpdates ?? null,
      pendingAgentCall: parsed.pendingAgentCall ?? null,
      errorMessage: parsed.errorMessage ?? null,
      qualityCheckId: parsed.qualityCheckId ?? null,
      artifactReview: parsed.artifactReview ?? createDefaultArtifactReviewState({
        status: parsed.pendingUserResponse && parsed.activeArtifactId
          ? "awaiting_user"
          : parsed.pendingArtifactRevision
            ? "revision_requested"
            : parsed.activeArtifactId
              ? "draft_submitted"
              : "none",
        activeArtifactId: parsed.activeArtifactId ?? null,
        reviewerAgent: parsed.reviewerAgent ?? null,
        reviserAgent: parsed.reviserAgent ?? null,
        pendingRevision: parsed.pendingArtifactRevision ?? null,
        iteration: parsed.artifactIteration ?? 0,
        maxIterations: parsed.maxArtifactIterations ?? 5,
      }),
      activeArtifactId: parsed.activeArtifactId ?? null,
      artifactMode: parsed.artifactMode ?? "none",
      reviewerAgent: parsed.reviewerAgent ?? null,
      reviserAgent: parsed.reviserAgent ?? null,
      pendingArtifactRevision: parsed.pendingArtifactRevision ?? null,
      artifactIteration: parsed.artifactIteration ?? 0,
      maxArtifactIterations: parsed.maxArtifactIterations ?? 5,
    };
    return legacyCompatible;
  } catch {
    return null;
  }
}

export function rehydrateGraphStateFromSnapshot(
  snapshot: SerializableGraphStateSnapshot,
  runtime: {
    userMessage: string;
    novelData: GraphState["novelData"];
    streamCallbacks: GraphState["streamCallbacks"];
    eventCallbacks?: GraphState["eventCallbacks"];
    chapterTargetDecision?: "current_chapter" | "next_chapter";
  }
): GraphState {
  return {
    ...snapshot,
    userMessage: runtime.userMessage,
    novelData: runtime.novelData,
    runtime: {
      streamCallbacks: runtime.streamCallbacks,
      eventCallbacks: runtime.eventCallbacks,
      chapterTargetDecision: runtime.chapterTargetDecision,
    },
    controlEvents: undefined,
    streamCallbacks: runtime.streamCallbacks,
    eventCallbacks: runtime.eventCallbacks,
  };
}
