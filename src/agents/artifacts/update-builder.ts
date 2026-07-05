/**
 * AgentUpdates builder helpers.
 *
 * @module agents/artifacts/update-builder
 * @description 合并分批提交的 AgentUpdates，并在完成构建时执行严格 proposal 校验。
 */

import type { AgentUpdates } from "@/shared/contracts/agent-updates";
import { AgentUpdatesProposalSchema } from "@/shared/contracts/agent-updates";
import type { OutlineTreeStage } from "@/shared/contracts/agent-control";
import {
  ARRAY_UPDATE_SECTIONS,
  TEXT_UPDATE_SECTIONS,
  isItemTextBlockFieldAllowed,
  isTextUpdateSection,
  type TextUpdateSection,
} from "@/shared/contracts/agent-update-channels";

export { TEXT_UPDATE_SECTIONS, isTextUpdateSection, type TextUpdateSection } from "@/shared/contracts/agent-update-channels";

export function mergeAgentUpdates(base: AgentUpdates | undefined, patch: AgentUpdates | undefined): AgentUpdates {
  const merged: AgentUpdates = { ...(base ?? {}) };
  if (!patch) return merged;

  if (patch.outlineTreeMode) merged.outlineTreeMode = patch.outlineTreeMode;

  for (const section of ARRAY_UPDATE_SECTIONS) {
    const incoming = patch[section];
    if (Array.isArray(incoming) && incoming.length > 0) {
      const existing = merged[section] as unknown[] | undefined;
      (merged as Record<string, unknown>)[section] = [...(existing ?? []), ...incoming];
    }
  }

  for (const section of TEXT_UPDATE_SECTIONS) {
    const incoming = patch[section];
    if (typeof incoming === "string" && incoming.trim()) {
      merged[section] = incoming.trim();
    }
  }

  return merged;
}

export function buildTextUpdate(section: TextUpdateSection, content: string): AgentUpdates {
  return { [section]: content.trim() } as AgentUpdates;
}

export interface ItemTextBlockTarget {
  section: string;
  field: string;
  targetId?: string;
  targetKey?: string;
  targetName?: string;
  content: string;
}

export type ItemTextBlockResult =
  | { success: true; updates: AgentUpdates }
  | { success: false; reason: string };

export function putItemTextBlock(updates: AgentUpdates, target: ItemTextBlockTarget): ItemTextBlockResult {
  if (!isItemTextBlockFieldAllowed(target.section, target.field)) {
    return { success: false, reason: "field_not_allowed" };
  }

  const items = (updates as Record<string, unknown>)[target.section];
  if (!Array.isArray(items)) {
    return { success: false, reason: "target_section_missing" };
  }

  const index = items.findIndex((item) => matchesItemTarget(item, target));
  if (index < 0) {
    return { success: false, reason: "target_item_not_found" };
  }

  const nextItems = items.slice();
  nextItems[index] = {
    ...(nextItems[index] as Record<string, unknown>),
    [target.field]: target.content.trim(),
  };

  return {
    success: true,
    updates: {
      ...updates,
      [target.section]: nextItems,
    } as AgentUpdates,
  };
}

export function buildOutlineTreeUpdate(input: {
  artifactKey: string;
  batchIndex: number;
  mode: "replace" | "patch";
  stages: OutlineTreeStage[];
}): AgentUpdates {
  const outlineAdjustments: NonNullable<AgentUpdates["outlineAdjustments"]> = [];
  const prefix = makeClientKeyPrefix(input.artifactKey, input.batchIndex);

  input.stages.forEach((stage, stageIndex) => {
    const stageKey = `${prefix}-s${stageIndex + 1}`;
    outlineAdjustments.push(removeUndefined({
      action: "create",
      kind: "stage",
      title: stage.title.trim(),
      chapterStartOrder: stage.chapterStartOrder,
      chapterEndOrder: stage.chapterEndOrder,
      estimatedWordCount: stage.estimatedWordCount,
      clientKey: stageKey,
    }));

    stage.plotUnits?.forEach((unit, unitIndex) => {
      const unitKey = `${stageKey}-u${unitIndex + 1}`;
      outlineAdjustments.push(removeUndefined({
        action: "create",
        kind: "plot_unit",
        title: unit.title.trim(),
        chapterStartOrder: unit.chapterStartOrder,
        chapterEndOrder: unit.chapterEndOrder,
        estimatedWordCount: unit.estimatedWordCount,
        clientKey: unitKey,
        parentKey: stageKey,
      }));

      unit.chapterGroups?.forEach((group, groupIndex) => {
        outlineAdjustments.push(removeUndefined({
          action: "create",
          kind: "chapter_group",
          title: group.title.trim(),
          chapterStartOrder: group.chapterStartOrder,
          chapterEndOrder: group.chapterEndOrder,
          estimatedWordCount: group.estimatedWordCount,
          clientKey: `${unitKey}-g${groupIndex + 1}`,
          parentKey: unitKey,
        }));
      });
    });
  });

  return { outlineTreeMode: input.mode, outlineAdjustments };
}

function makeClientKeyPrefix(artifactKey: string, batchIndex: number): string {
  const safeArtifactKey = artifactKey
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return `${safeArtifactKey || "outline-tree"}-b${batchIndex}`;
}

function removeUndefined<T extends Record<string, unknown>>(value: T): T {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined && item !== "")
  ) as T;
}

function matchesItemTarget(item: unknown, target: ItemTextBlockTarget): boolean {
  if (!item || typeof item !== "object") return false;
  const value = item as Record<string, unknown>;
  if (target.targetId) {
    const idCandidates = [
      value.id,
      value.characterId,
      value.locationId,
      value.itemId,
      value.factionId,
      value.glossaryId,
      value.nodeId,
      value.referenceId,
    ];
    if (idCandidates.some((candidate) => candidate === target.targetId)) return true;
  }
  if (target.targetKey) {
    const keyCandidates = [value.clientKey, value.parentKey];
    if (keyCandidates.some((candidate) => candidate === target.targetKey)) return true;
  }
  if (target.targetName) {
    const nameCandidates = [
      value.name,
      value.title,
      value.nodeTitle,
      value.term,
      value.characterName,
      value.chapterTitle,
    ];
    if (nameCandidates.some((candidate) => candidate === target.targetName)) return true;
  }
  return false;
}

export function validateAgentUpdatesForReview(updates: AgentUpdates): string[] {
  const result = AgentUpdatesProposalSchema.safeParse(updates);
  if (result.success) return [];
  return result.error.issues.map((issue) => {
    const path = issue.path.length > 0 ? issue.path.join(".") : "(root)";
    return `${path}: ${issue.message}`;
  });
}
