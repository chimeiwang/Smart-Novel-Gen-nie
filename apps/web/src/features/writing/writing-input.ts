import type { components } from "@inkforge/api-client";

import { countTextLength } from "@/shared/lib/word-count";
import type { WorkflowRunUiState } from "./workflow-run-ui";

type NaturalRequest = components["schemas"]["NaturalStartWritingRunRequest"];
type ClarificationRequest = components["schemas"]["ClarifyWritingRunRequest"];

export function writingInputDisposition(input: {
  run: WorkflowRunUiState | null;
  legacyTaskId?: string | null;
  revisionArtifactId?: string | null;
}): "new_run" | "clarification" | "artifact_revision" | "blocked" {
  const { run, revisionArtifactId } = input;
  if (run?.status === "waiting_user" && run.clarification) return "clarification";
  if (revisionArtifactId) {
    if (!run || (run.status === "waiting_user" && run.artifact?.actionable
      && run.artifact.artifactId === revisionArtifactId)) return "artifact_revision";
    return "blocked";
  }
  if (run && ["pending", "running", "waiting_user"].includes(run.status)) return "blocked";
  // 遗留 taskId 只属于显式恢复动作，不能使下一条普通消息恢复旧任务。
  return "new_run";
}

export function buildNaturalRunRequest(input: Omit<NaturalRequest, "workflow" | "inputMode">): NaturalRequest {
  if (countTextLength(input.userInstruction) === 0) throw new Error("用户要求不能为空白");
  return {
    inputMode: "natural", workflow: "long_serial", clientRequestId: input.clientRequestId,
    novelId: input.novelId, chapterId: input.chapterId, writingSessionId: input.writingSessionId,
    userInstruction: input.userInstruction, targetWordCount: input.targetWordCount ?? 4000,
  };
}

export function buildClarificationRequest(
  run: WorkflowRunUiState, userMessage: string, clientRequestId: string,
): ClarificationRequest {
  if (run.status !== "waiting_user" || !run.clarification || run.artifact || run.cancelRequestedAt) {
    throw new Error("当前运行没有可回答的澄清问题，请刷新状态");
  }
  if (countTextLength(userMessage) === 0) throw new Error("澄清回答不能为空白");
  return {
    clientRequestId, expectedRevision: run.revision,
    decisionStepId: run.clarification.decisionStepId, userMessage,
  };
}
