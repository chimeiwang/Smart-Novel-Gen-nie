import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import { CreativeOperationSchema } from "@/shared/contracts/creative-operation";
import type {
  AgentControlEvent,
  AgentMessage,
  AgentOutput,
  AgentUpdates,
  CoreAgentId,
  PendingAgentCall,
  WritingPhase,
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
  operationStage: string | null;
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
  controlEvents: AgentControlEvent[] | undefined;
  activeArtifactId: string | null;
  artifactMode: "none" | "review_loop";
  reviewerAgent: CoreAgentId | null;
  reviserAgent: CoreAgentId | null;
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
    operationStage: state.operationStage ?? null,
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
    controlEvents: state.controlEvents,
    activeArtifactId: state.activeArtifactId ?? null,
    artifactMode: state.artifactMode ?? "none",
    reviewerAgent: state.reviewerAgent ?? null,
    reviserAgent: state.reviserAgent ?? null,
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

    return {
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
      operationStage: parsed.operationStage ?? null,
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
      controlEvents: parsed.controlEvents,
      activeArtifactId: parsed.activeArtifactId ?? null,
      artifactMode: parsed.artifactMode ?? "none",
      reviewerAgent: parsed.reviewerAgent ?? null,
      reviserAgent: parsed.reviserAgent ?? null,
      artifactIteration: parsed.artifactIteration ?? 0,
      maxArtifactIterations: parsed.maxArtifactIterations ?? 5,
    };
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
  }
): GraphState {
  return {
    ...snapshot,
    userMessage: runtime.userMessage,
    novelData: runtime.novelData,
    streamCallbacks: runtime.streamCallbacks,
    eventCallbacks: runtime.eventCallbacks,
  };
}
