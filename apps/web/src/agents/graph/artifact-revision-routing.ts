import { CORE_AGENT_IDS, type CoreAgentId } from "./state";

export type ArtifactRevisionResumeInput = {
  artifactId: string;
  artifactKey: string | null;
  revision: number;
  createdByAgent: CoreAgentId | null;
  updatedByAgent: CoreAgentId | null;
  reviewerAgent: CoreAgentId | null;
  userMessage?: string | null;
};

export type ArtifactRevisionResume = {
  targetAgent: CoreAgentId;
  userMessage: string;
};

export function resolvePendingArtifactRevisionFromChat(input: {
  taskPhase?: string | null;
  taskGeneratedContent?: string | null;
  graphSnapshot?: {
    pendingUserResponse?: boolean;
    activeArtifactId?: string | null;
    artifactReview?: { status?: string | null; activeArtifactId?: string | null } | null;
  } | null;
  userMessage?: string | null;
}): { artifactId: string; userMessage: string } | null {
  const userMessage = input.userMessage?.trim();
  if (!userMessage || userMessage.startsWith("@")) return null;
  const snapshotReview = input.graphSnapshot?.artifactReview;
  const snapshotArtifactId = snapshotReview?.status === "awaiting_user"
    ? snapshotReview.activeArtifactId?.trim()
    : input.graphSnapshot?.pendingUserResponse
      ? input.graphSnapshot.activeArtifactId?.trim()
      : "";
  const taskArtifactId = input.taskPhase === "awaiting_user_review"
    ? input.taskGeneratedContent?.trim()
    : "";
  const artifactId = snapshotArtifactId || taskArtifactId;
  return artifactId ? { artifactId, userMessage } : null;
}

function isCoreAgentId(value: CoreAgentId | null | undefined): value is CoreAgentId {
  return Boolean(value && CORE_AGENT_IDS.includes(value));
}

export function buildArtifactRevisionResume(
  input: ArtifactRevisionResumeInput
): ArtifactRevisionResume | null {
  const targetAgent = isCoreAgentId(input.updatedByAgent)
    ? input.updatedByAgent
    : isCoreAgentId(input.createdByAgent)
      ? input.createdByAgent
      : null;

  if (!targetAgent || targetAgent === input.reviewerAgent) return null;

  const userInstruction = input.userMessage?.trim() || "继续修改待审核草案";
  const lines = [
    `@${targetAgent} 请继续修改待审核草案。`,
    `草案ID：${input.artifactId}`,
    input.artifactKey ? `产物标识：${input.artifactKey}` : "",
    `当前版本：${input.revision}`,
    `用户补充要求：${userInstruction}`,
    "请先调用 get_review_artifact 读取该草案，再围绕同一个 artifactKey 提交新的 revision；不要把草案当作正式小说事实。",
  ].filter(Boolean);

  return {
    targetAgent,
    userMessage: lines.join("\n"),
  };
}
