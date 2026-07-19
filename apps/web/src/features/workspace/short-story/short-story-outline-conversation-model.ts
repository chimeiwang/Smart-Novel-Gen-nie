import type { components } from "@inkforge/api-client";

type Message = components["schemas"]["MessageResponse"];
type Revision = components["schemas"]["ReviewArtifactRevisionSummary"];

export type ShortStoryOutlineConversationEntry = {
  key: string;
  kind: "user_request" | "outline_result";
  content: string;
  createdAt: string | null;
  revision: number | null;
  state: "completed" | "processing" | "unchanged";
};

type BuildConversationInput = {
  artifactId: string;
  currentRevision: number;
  taskActive: boolean;
  messages: Message[];
  revisions: Revision[];
};

type RevisionRequest = {
  message: Message;
  sourceRevision: number;
};

function getRevisionRequest(message: Message, artifactId: string): RevisionRequest | null {
  if (message.intent !== "revision_focus" || message.role !== "user") return null;
  const metadata = message.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return null;
  const fields = metadata as Record<string, unknown>;
  if (fields.artifactId !== artifactId) return null;
  const sourceRevision = fields.sourceRevision;
  if (typeof sourceRevision !== "number" || !Number.isInteger(sourceRevision) || sourceRevision < 1) {
    return null;
  }
  return { message, sourceRevision };
}

function revisionEntry(revision: Revision): ShortStoryOutlineConversationEntry {
  return {
    key: `revision:${revision.revision}`,
    kind: "outline_result",
    content: revision.summary?.trim() || "已生成新的完整大纲",
    createdAt: revision.createdAt,
    revision: revision.revision,
    state: "completed",
  };
}

export function buildShortStoryOutlineConversation({
  artifactId,
  currentRevision,
  taskActive,
  messages,
  revisions,
}: BuildConversationInput): ShortStoryOutlineConversationEntry[] {
  const orderedRevisions = revisions
    .filter((revision) => revision.artifactId === artifactId)
    .sort((left, right) => left.revision - right.revision);
  const revisionByNumber = new Map(
    orderedRevisions.map((revision) => [revision.revision, revision]),
  );
  const requests = messages
    .map((message) => getRevisionRequest(message, artifactId))
    .filter((request): request is RevisionRequest => request !== null)
    .sort((left, right) => {
      const timeOrder = left.message.createdAt.localeCompare(right.message.createdAt);
      return timeOrder || left.message.id.localeCompare(right.message.id);
    });
  const consumedRevisions = new Set<number>();
  const entries: ShortStoryOutlineConversationEntry[] = [];

  const appendUnconsumedThrough = (revisionNumber: number) => {
    for (const revision of orderedRevisions) {
      if (revision.revision > revisionNumber || consumedRevisions.has(revision.revision)) continue;
      consumedRevisions.add(revision.revision);
      entries.push(revisionEntry(revision));
    }
  };

  for (const request of requests) {
    appendUnconsumedThrough(request.sourceRevision);
    entries.push({
      key: `request:${request.message.id}`,
      kind: "user_request",
      content: request.message.content,
      createdAt: request.message.createdAt,
      revision: request.sourceRevision,
      state: "completed",
    });

    const resultRevisionNumber = request.sourceRevision + 1;
    const resultRevision = revisionByNumber.get(resultRevisionNumber);
    if (resultRevision && !consumedRevisions.has(resultRevisionNumber)) {
      consumedRevisions.add(resultRevisionNumber);
      entries.push(revisionEntry(resultRevision));
      continue;
    }

    entries.push({
      key: `request-result:${request.message.id}`,
      kind: "outline_result",
      content: taskActive ? "正在根据这条要求修改完整大纲…" : "已处理，完整大纲内容未变化",
      createdAt: null,
      revision: null,
      state: taskActive ? "processing" : "unchanged",
    });
  }

  for (const revision of orderedRevisions) {
    if (consumedRevisions.has(revision.revision)) continue;
    consumedRevisions.add(revision.revision);
    entries.push(revisionEntry(revision));
  }

  if (entries.length === 0 && currentRevision > 0 && taskActive) {
    entries.push({
      key: "initial-outline:processing",
      kind: "outline_result",
      content: "正在根据原始灵感生成完整大纲…",
      createdAt: null,
      revision: null,
      state: "processing",
    });
  }

  return entries;
}
