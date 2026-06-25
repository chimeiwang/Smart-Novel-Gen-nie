/**
 * Creative operation executor.
 *
 * This layer reuses existing Agent nodes, while the operation graph owns
 * workflow routing, artifact submission, and review decisions.
 */

import type {
  AgentControlEvent,
  AgentOutput,
  CoreAgentId,
  WritingState,
} from "@/agents/graph/state";
import { AGENT_TO_OUTPUT_FIELD, createAgentOutput } from "@/agents/graph/state";
import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import { getCreativeOperationLabel } from "@/shared/contracts/creative-operation";
import type { ReviewArtifactDto } from "@/shared/contracts/review-artifact";
import { createOrUpdateTextArtifact } from "@/agents/artifacts/artifact-service";
import {
  processControlEvents,
  type ControlEventProcessorDeps,
} from "@/agents/graph/control-event-processor";
import { addAgentMessage } from "@/agents/graph/context-manager";
import { getOperationDefinition } from "./operation-definition";

export interface OperationExecutionResult {
  statePatch: Partial<WritingState>;
  output: AgentOutput | null;
  artifact?: ReviewArtifactDto | null;
  directReply?: string;
}

export interface OperationExecutionDeps extends Partial<ControlEventProcessorDeps> {
  runInternalAgent?: (
    agentId: CoreAgentId,
    state: WritingState
  ) => Promise<Partial<WritingState>>;
}

export async function executeCreativeOperation(
  state: WritingState,
  deps: OperationExecutionDeps = {}
): Promise<OperationExecutionResult> {
  const operation = state.currentOperation;
  if (!operation) {
    return {
      statePatch: {},
      output: null,
      directReply: "我还没有识别出要执行的创作操作，请再描述一下你的目标。",
    };
  }

  const def = getOperationDefinition(operation.kind);
  const activeAgent = state.pendingAgentCall?.toAgent ?? state.nextAgent ?? def.primaryAgent;
  const runAgent = deps.runInternalAgent ?? runInternalAgent;
  const agentResult = await runAgent(activeAgent, {
    ...state,
    activeAgent,
    nextAgent: null,
  });
  const output = readAgentOutput(activeAgent, agentResult);
  const controlEvents = agentResult.controlEvents as AgentControlEvent[] | undefined;

  const controlResult = output
    ? await processOperationControlEvents({
        state,
        agentResult,
        output,
        activeAgent,
        deps,
      })
    : null;

  if (controlResult && shouldCompleteWithControlResult(def, controlEvents, controlResult.statePatch)) {
    return controlResult;
  }

  const processedPatch = controlResult?.statePatch ?? {};

  if (!def.requiresArtifact) {
    return {
      statePatch: {
        ...agentResult,
        ...processedPatch,
        nextAgent: null,
        pendingAgentCall: null,
        controlEvents: undefined,
        generatedContent: state.generatedContent,
      },
      output,
      directReply: output?.content,
    };
  }

  if (def.artifactPolicy === "text" && def.textArtifactKind && output?.content.trim()) {
    const createTextArtifact = deps.createOrUpdateTextArtifact ?? createOrUpdateTextArtifact;
    const artifact = await createTextArtifact({
      novelId: state.novelId,
      chapterId: state.chapterId,
      taskId: state.taskId,
      artifactKey: buildOperationArtifactKey(state.taskId, operation.kind),
      kind: def.textArtifactKind,
      summary: `${getCreativeOperationLabel(operation.kind)}：${operation.userGoal}`,
      content: output.content.trim(),
      agentId: activeAgent,
      reviewerAgent: def.reviewers[0] ?? null,
    });

    return {
      statePatch: {
        ...agentResult,
        ...processedPatch,
        activeArtifactId: artifact.id,
        nextAgent: null,
        pendingAgentCall: null,
        controlEvents: undefined,
        generatedContent: state.generatedContent,
      },
      output,
      artifact,
    };
  }

  return {
    statePatch: {
      ...agentResult,
      ...processedPatch,
      nextAgent: null,
      pendingAgentCall: null,
      controlEvents: undefined,
      generatedContent: state.generatedContent,
    },
    output,
  };
}

function shouldCompleteWithControlResult(
  def: ReturnType<typeof getOperationDefinition>,
  controlEvents: AgentControlEvent[] | undefined,
  statePatch: Partial<WritingState>
): boolean {
  if (!controlEvents?.length) return false;
  if (!def.requiresArtifact || def.artifactPolicy === "agent_updates") return true;
  if (statePatch.nextAgent) return true;
  return controlEvents.some((event) =>
    event.type === "route_to_agent" ||
    event.type === "request_revision" ||
    event.type === "begin_artifact_output" ||
    event.type === "submit_beat_plan" ||
    event.type === "submit_evaluation"
  );
}

async function processOperationControlEvents(input: {
  state: WritingState;
  agentResult: Partial<WritingState>;
  output: AgentOutput;
  activeAgent: CoreAgentId;
  deps: OperationExecutionDeps;
}): Promise<OperationExecutionResult | null> {
  const { state, agentResult, output, activeAgent, deps } = input;
  const controlEvents = agentResult.controlEvents as AgentControlEvent[] | undefined;
  if (!controlEvents?.length) return null;

  const updatedHistory = addAgentMessage(
    { ...state, conversationHistory: state.conversationHistory },
    output,
    false
  ).conversationHistory;

  const processed = await processControlEvents(
    {
      events: controlEvents,
      state: {
        taskId: state.taskId,
        chapterId: state.chapterId,
        qualityCheckId: state.qualityCheckId,
        callChainDepth: state.callChainDepth ?? 0,
        novelData: state.novelData,
      },
      activeAgent,
      output,
      updatedHistory,
    },
    {
      emitEvent: deps.emitEvent ?? (() => undefined),
      interrupt: deps.interrupt,
      createOrUpdateAgentUpdatesArtifact: deps.createOrUpdateAgentUpdatesArtifact,
      createOrUpdateTextArtifact: deps.createOrUpdateTextArtifact,
      createOrUpdateBeatPlanArtifact: deps.createOrUpdateBeatPlanArtifact,
      submitArtifactEvaluation: deps.submitArtifactEvaluation,
      markTaskAwaitingUserReview: deps.markTaskAwaitingUserReview,
      saveQualityCheckResult: deps.saveQualityCheckResult,
      interruptOnUserApproval: false,
      now: deps.now,
      maxCallChainDepth: deps.maxCallChainDepth,
    }
  );

  return {
    statePatch: {
      ...agentResult,
      ...processed,
      pendingAgentCall: processed.pendingAgentCall ?? null,
      generatedContent: state.generatedContent,
    },
    output,
    directReply: output.content,
  };
}

function buildOperationArtifactKey(taskId: string, kind: CreativeOperation["kind"]): string {
  return `${taskId}:${kind}`;
}

async function runInternalAgent(
  agentId: CoreAgentId,
  state: WritingState
): Promise<Partial<WritingState>> {
  const nodes = await import("@/agents/graph/nodes");
  const map: Record<CoreAgentId, keyof typeof nodes> = {
    "设定": "loreAdvisorNode",
    "剧情": "plotAdvisorNode",
    "写作": "authorNode",
    "校验": "validatorNode",
    "编辑": "editorNode",
  };
  const node = nodes[map[agentId]] as (s: WritingState) => Promise<Partial<WritingState>>;
  return node({
    ...state,
    activeAgent: agentId,
    operationMode: "operation_graph",
  });
}

function readAgentOutput(
  agentId: CoreAgentId,
  patch: Partial<WritingState>
): AgentOutput | null {
  const field = AGENT_TO_OUTPUT_FIELD[agentId];
  return (patch as Record<string, unknown>)[field] as AgentOutput | null ?? null;
}

export function createOperationSystemOutput(
  state: WritingState,
  content: string
): AgentOutput {
  const agentId = state.currentOperation?.primaryAgent ?? "编辑";
  return createAgentOutput(agentId, content);
}
