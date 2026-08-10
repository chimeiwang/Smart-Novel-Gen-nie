import type { components } from "@inkforge/api-client";

import {
  buildSelectionIdentity,
  sha256Text,
  sha256TextSync,
  type SelectionIdentity,
} from "../short-medium/selection-range";

export type SelectionResourceType = components["schemas"]["SelectionTarget"]["resourceType"];

export type SelectionAttachment = SelectionIdentity & {
  resourceType: SelectionResourceType;
  resourceId: string;
  sourceLabel: string;
  baseUpdatedAt: string;
  baseContentHash: string;
  stale?: boolean;
};

export type TransientSelection = SelectionAttachment & {
  content: string;
};

export type SelectionCaptureInput = Omit<BuildSelectionAttachmentInput, "utf16Start" | "utf16End"> & {
  utf16Start: number;
  utf16End: number;
};

export type SelectionBridge = {
  transientSelection: TransientSelection | null;
  attachedSelection: SelectionAttachment | null;
  captureSelection: (input: SelectionCaptureInput) => Promise<void>;
  attachSelection: () => void;
  clearTransientSelection: () => void;
  clearAllSelection: () => void;
  removeSelection: () => void;
  reselectSelection: () => void;
  markSelectionSourceChanged: (input: {
    resourceType: SelectionResourceType;
    resourceId: string;
    updatedAt: string;
    content: string;
  }) => void;
};

type BuildSelectionAttachmentInput = {
  resourceType: SelectionResourceType;
  resourceId: string;
  sourceLabel: string;
  baseUpdatedAt: string;
  content: string;
  utf16Start: number;
  utf16End: number;
};

export async function buildSelectionAttachment(
  input: BuildSelectionAttachmentInput,
): Promise<SelectionAttachment> {
  const identity = await buildSelectionIdentity(input.content, input.utf16Start, input.utf16End);
  return {
    ...identity,
    resourceType: input.resourceType,
    resourceId: input.resourceId,
    sourceLabel: input.sourceLabel,
    baseUpdatedAt: input.baseUpdatedAt,
    baseContentHash: await sha256Text(input.content),
  };
}

export function isSelectionAttachmentStale(
  attachment: SelectionAttachment,
  current: { updatedAt: string; content: string },
): boolean {
  return attachment.baseUpdatedAt !== current.updatedAt
    || attachment.baseContentHash !== sha256TextSync(current.content);
}

export async function selectionContentHash(content: string): Promise<string> {
  const hash = await sha256Text(content);
  return hash;
}

export async function isSelectionAttachmentStaleAsync(
  attachment: SelectionAttachment,
  current: { updatedAt: string; content: string },
): Promise<boolean> {
  return attachment.baseUpdatedAt !== current.updatedAt
    || attachment.baseContentHash !== await selectionContentHash(current.content);
}

export function buildSelectionRunRequest({
  attachment,
  novelId,
  chapterId,
  writingSessionId,
  targetWordCount,
  userInstruction,
}: {
  attachment: SelectionAttachment;
  novelId: string;
  chapterId: string;
  writingSessionId?: string | null;
  targetWordCount: number;
  userInstruction: string;
}): components["schemas"]["LongSerialStartWritingRunRequest"] {
  const operation = attachment.resourceType === "chapter_content"
    ? "rewrite_chapter_selection"
    : "rewrite_outline_selection";
  const scope = attachment.resourceType === "outline_node_content"
    ? { kind: "outline_node" as const, outlineNodeId: attachment.resourceId }
    : attachment.resourceType === "outline_content"
      ? { kind: "novel" as const }
      : { kind: "chapter" as const, chapterId };

  return {
    workflow: "long_serial",
    clientRequestId: crypto.randomUUID(),
    novelId,
    chapterId,
    writingSessionId: writingSessionId ?? null,
    operation,
    target: { type: "chapter", id: chapterId },
    scope,
    selectionTarget: {
      resourceType: attachment.resourceType,
      resourceId: attachment.resourceId,
      baseUpdatedAt: attachment.baseUpdatedAt,
      baseContentHash: attachment.baseContentHash,
      selectionStart: attachment.selectionStart,
      selectionEnd: attachment.selectionEnd,
      selectedTextHash: attachment.selectedTextHash,
    },
    selectionAttachmentMetadata: {
      resourceType: attachment.resourceType,
      resourceId: attachment.resourceId,
      sourceLabel: attachment.sourceLabel,
      baseUpdatedAt: attachment.baseUpdatedAt,
      baseContentHash: attachment.baseContentHash,
      selectionStart: attachment.selectionStart,
      selectionEnd: attachment.selectionEnd,
      selectedTextHash: attachment.selectedTextHash,
      selectionPreview: selectionPreview(attachment.selectedText),
    },
    targetWordCount,
    userInstruction: userInstruction.trim(),
  };
}

export function selectionSourceLabel(resourceType: SelectionResourceType): string {
  if (resourceType === "chapter_content") return "章节正文";
  if (resourceType === "outline_content") return "总纲";
  return "大纲节点";
}

export function selectionPreview(text: string, limit = 48): string {
  const points = Array.from(text);
  if (points.length <= limit) return text;
  const head = Math.ceil(limit / 2);
  const tail = Math.floor(limit / 2);
  return `${points.slice(0, head).join("")}…${points.slice(-tail).join("")}`;
}
