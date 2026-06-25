/**
 * 数据库操作模块
 *
 * @module agents/lib/db-operations
 * @description 统一的数据库持久化操作，支持事务和回滚
 */

import { prisma } from "@/shared/db/prisma";
import type { Prisma } from "@prisma/client";
import type { AgentUpdates } from "../types";

/**
 * 操作结果
 */
export interface DbOperationResult {
  success: boolean;
  savedCount: number;
  summary: string;
  errors: string[];
}

/**
 * 操作记录（用于回滚）
 */
interface OperationRecord {
  type: string;
  action: string;
  entityId: string;
  entityType: string;
  data: Record<string, unknown>;
}

type OutlineNodeKind = "stage" | "plot_unit" | "chapter_group";
type OutlineNodeStatus = "planned" | "in_progress" | "completed" | "skipped";
type OutlineAdjustmentInput = NonNullable<AgentUpdates["outlineAdjustments"]>[number];

const OUTLINE_CREATE_KIND_ORDER: Record<OutlineNodeKind, number> = {
  stage: 0,
  plot_unit: 1,
  chapter_group: 2,
};

function normalizeOutlineNodeKind(value: unknown): OutlineNodeKind | undefined {
  return value === "stage" || value === "plot_unit" || value === "chapter_group" ? value : undefined;
}

async function inferOutlineNodeKind(
  tx: Prisma.TransactionClient,
  taskNovelId: string,
  parentId: string | null | undefined,
): Promise<OutlineNodeKind> {
  if (!parentId) return "stage";

  const parent = await tx.outlineNode.findFirst({
    where: { id: parentId, novelId: taskNovelId },
    select: { kind: true },
  });

  if (!parent) return "stage";
  if (parent.kind === "stage") return "plot_unit";
  return "chapter_group";
}

async function validateOutlineNodePlacement(
  tx: Prisma.TransactionClient,
  taskNovelId: string,
  kind: OutlineNodeKind,
  parentId: string | null | undefined,
): Promise<string | null> {
  if (kind === "stage") {
    return parentId ? "阶段/卷必须是顶层节点" : null;
  }

  if (!parentId) {
    return kind === "plot_unit" ? "剧情单元必须挂在阶段/卷下" : "章节组必须挂在剧情单元下";
  }

  const parent = await tx.outlineNode.findFirst({
    where: { id: parentId, novelId: taskNovelId },
    select: { kind: true },
  });

  if (!parent) return `大纲父节点 ${parentId} 不存在或不属于当前小说`;
  if (kind === "plot_unit" && parent.kind !== "stage") return "剧情单元只能挂在阶段/卷下";
  if (kind === "chapter_group" && parent.kind !== "plot_unit") return "章节组只能挂在剧情单元下";
  return null;
}

function getAllowedOutlineChildKind(kind: OutlineNodeKind): OutlineNodeKind | null {
  if (kind === "stage") return "plot_unit";
  if (kind === "plot_unit") return "chapter_group";
  return null;
}

async function validateOutlineChildrenPlacement(
  tx: Prisma.TransactionClient,
  nodeId: string,
  nextKind: OutlineNodeKind,
): Promise<string | null> {
  const childCount = await tx.outlineNode.count({ where: { parentId: nodeId } });
  if (childCount === 0) return null;

  const allowedChildKind = getAllowedOutlineChildKind(nextKind);
  if (!allowedChildKind) return "存在子节点的节点不能改为章节组";

  const invalidChild = await tx.outlineNode.findFirst({
    where: { parentId: nodeId, kind: { not: allowedChildKind } },
    select: { id: true },
  });
  return invalidChild ? "存在不兼容子节点，请先移动或删除子节点" : null;
}

function getOutlineNodeTitle(adj: OutlineAdjustmentInput): string {
  return adj.title || adj.nodeTitle || "未命名节点";
}

function getOutlineAdjustmentLabel(adj: OutlineAdjustmentInput): string {
  return adj.title || adj.nodeTitle || adj.nodeId || adj.clientKey || "未命名节点";
}

async function resolveOutlineCreateParentId(input: {
  tx: Prisma.TransactionClient;
  novelId: string;
  adj: OutlineAdjustmentInput;
  createdIdsByClientKey: Map<string, string>;
  errors: string[];
}): Promise<string | null | undefined> {
  const { tx, novelId, adj, createdIdsByClientKey, errors } = input;
  const hasParentId = typeof adj.parentId === "string" && adj.parentId.trim().length > 0;
  const hasParentKey = typeof adj.parentKey === "string" && adj.parentKey.trim().length > 0;

  if (hasParentId && hasParentKey) {
    errors.push(`大纲节点 ${getOutlineAdjustmentLabel(adj)} 不能同时提供 parentId 和 parentKey`);
    return undefined;
  }

  if (hasParentId) {
    const parentId = adj.parentId!.trim();
    const parent = await tx.outlineNode.findFirst({
      where: { id: parentId, novelId },
      select: { id: true },
    });
    if (!parent) {
      errors.push(`大纲节点 ${getOutlineAdjustmentLabel(adj)} 的父节点 ${parentId} 不存在或不属于当前小说`);
      return undefined;
    }
    return parentId;
  }

  if (hasParentKey) {
    const parentId = createdIdsByClientKey.get(adj.parentKey!.trim());
    if (!parentId) {
      errors.push(`大纲节点 ${getOutlineAdjustmentLabel(adj)} 找不到 parentKey=${adj.parentKey} 对应的同批父节点`);
      return undefined;
    }
    return parentId;
  }

  return null;
}

async function createOutlineNodeFromAdjustment(input: {
  tx: Prisma.TransactionClient;
  novelId: string;
  adj: OutlineAdjustmentInput;
  parentId: string | null;
  records: OperationRecord[];
}): Promise<boolean | "invalid"> {
  const { tx, novelId, adj, parentId, records } = input;
  const kind = normalizeOutlineNodeKind(adj.kind) ?? await inferOutlineNodeKind(tx, novelId, parentId);
  const placementError = await validateOutlineNodePlacement(tx, novelId, kind, parentId);
  if (placementError) throw new Error(placementError);

  const parentCount = parentId
    ? await tx.outlineNode.count({ where: { novelId, parentId } })
    : await tx.outlineNode.count({ where: { novelId, parentId: null } });
  const title = getOutlineNodeTitle(adj);
  const created = await tx.outlineNode.create({
    data: {
      novelId,
      parentId,
      title,
      content: adj.content ?? null,
      kind,
      status: (adj.status ?? "planned") as OutlineNodeStatus,
      estimatedWordCount: adj.estimatedWordCount ?? null,
      actualWordCount: adj.actualWordCount ?? null,
      order: parentCount,
    },
  });
  records.push({
    type: "outlineAdjustments",
    action: "create",
    entityId: created.id,
    entityType: "outlineNode",
    data: { novelId, title },
  });
  return true;
}

const CHARACTER_MUTABLE_FIELDS = new Set([
  "name",
  "aliases",
  "gender",
  "age",
  "appearance",
  "personality",
  "identity",
  "background",
  "coreDesire",
  "behaviorBoundaries",
  "speechStyle",
  "relationshipPrinciples",
  "shortTermGoal",
  "factionId",
  "powerLevel",
  "combatAbility",
  "specialSkills",
  "currentStatus",
  "statusNote",
]);

const LOCATION_MUTABLE_FIELDS = new Set([
  "name",
  "aliases",
  "type",
  "parentId",
  "climate",
  "culture",
  "description",
]);

const ITEM_MUTABLE_FIELDS = new Set([
  "name",
  "aliases",
  "type",
  "rarity",
  "effect",
  "origin",
  "description",
  "ownerId",
]);

const FACTION_MUTABLE_FIELDS = new Set([
  "name",
  "aliases",
  "type",
  "baseId",
  "description",
]);

const GLOSSARY_MUTABLE_FIELDS = new Set([
  "term",
  "definition",
  "category",
]);

function buildFieldChangeData(
  fieldChanges: { field: string; operation: "add" | "remove" | "update"; newValue?: string }[] | undefined,
  allowedFields: Set<string>
): Record<string, unknown> {
  const updateData: Record<string, unknown> = {};
  for (const change of fieldChanges ?? []) {
    if (!allowedFields.has(change.field)) continue;
    if (change.operation === "add" || change.operation === "update") {
      updateData[change.field] = change.newValue;
    } else if (change.operation === "remove") {
      updateData[change.field] = null;
    }
  }
  return updateData;
}

/**
 * 执行数据库持久化操作（带事务保护）
 *
 * @param taskId - 写作任务 ID
 * @param updates - Agent 提取的变更建议
 * @returns 操作结果
 */
export async function executeUpdates(
  taskId: string,
  updates: AgentUpdates
): Promise<DbOperationResult> {
  const errors: string[] = [];
  const records: OperationRecord[] = [];
  let savedCount = 0;

  const task = await prisma.writingTask.findUnique({
    where: { id: taskId },
  });

  if (!task) {
    return {
      success: false,
      savedCount: 0,
      summary: "任务不存在",
      errors: ["任务不存在"],
    };
  }

  try {
    await prisma.$transaction(async (tx) => {
      if (typeof updates.outlineContent === "string" && updates.outlineContent.trim()) {
        const existing = await tx.outline.findUnique({ where: { novelId: task.novelId } });
        const saved = await tx.outline.upsert({
          where: { novelId: task.novelId },
          update: { content: updates.outlineContent.trim() },
          create: {
            novelId: task.novelId,
            content: updates.outlineContent.trim(),
          },
        });
        records.push({
          type: "outlineContent",
          action: existing ? "update" : "create",
          entityId: saved.id,
          entityType: "outline",
          data: { novelId: task.novelId, original: existing },
        });
        savedCount++;
      }

      // 角色操作
      if (updates.characters) {
        for (const c of updates.characters) {
          try {
            if (c.action === "create") {
              const created = await tx.character.create({
                data: {
                  novelId: task.novelId,
                  name: c.name,
                  aliases: c.aliases ?? null,
                  identity: c.identity ?? null,
                  personality: c.personality ?? null,
                  appearance: c.appearance ?? null,
                  background: c.background ?? null,
                  coreDesire: c.coreDesire ?? null,
                  behaviorBoundaries: c.behaviorBoundaries ?? null,
                  speechStyle: c.speechStyle ?? null,
                  relationshipPrinciples: c.relationshipPrinciples ?? null,
                  shortTermGoal: c.shortTermGoal ?? null,
                  gender: c.gender ?? null,
                  age: c.age ?? null,
                  factionId: c.factionId ?? null,
                  powerLevel: c.powerLevel ?? null,
                  combatAbility: c.combatAbility ?? null,
                  specialSkills: c.specialSkills ?? null,
                  currentStatus: c.currentStatus ?? "active",
                  statusNote: c.statusNote ?? null,
                },
              });
              records.push({
                type: "character",
                action: "create",
                entityId: created.id,
                entityType: "character",
                data: { novelId: task.novelId, name: c.name },
              });
              savedCount++;
            } else if (c.action === "update") {
              // 优先使用 id，其次 characterId，最后用 name 查找
              const targetId = c.id || c.characterId;
              let existing = targetId
                ? await tx.character.findUnique({ where: { id: targetId } })
                : null;

              if (!existing && c.name) {
                existing = await tx.character.findFirst({
                  where: { novelId: task.novelId, name: { contains: c.name } },
                });
              }

              if (existing) {
                // 如果有 fieldChanges，使用增量更新
                if (c.fieldChanges && c.fieldChanges.length > 0) {
                  const updateData = buildFieldChangeData(c.fieldChanges, CHARACTER_MUTABLE_FIELDS);
                  if (Object.keys(updateData).length === 0) continue;
                  const updated = await tx.character.update({
                    where: { id: existing.id },
                    data: updateData,
                  });
                  records.push({
                    type: "character",
                    action: "update",
                    entityId: updated.id,
                    entityType: "character",
                    data: { original: existing, updated: updateData },
                  });
                  savedCount++;
                } else {
                  // 传统方式：整体覆盖字段
                  const updated = await tx.character.update({
                    where: { id: existing.id },
                    data: {
                      name: c.name ?? existing.name,
                      aliases: c.aliases ?? existing.aliases,
                      identity: c.identity ?? existing.identity,
                      personality: c.personality ?? existing.personality,
                      appearance: c.appearance ?? existing.appearance,
                      background: c.background ?? existing.background,
                      coreDesire: c.coreDesire ?? existing.coreDesire,
                      behaviorBoundaries: c.behaviorBoundaries ?? existing.behaviorBoundaries,
                      speechStyle: c.speechStyle ?? existing.speechStyle,
                      relationshipPrinciples: c.relationshipPrinciples ?? existing.relationshipPrinciples,
                      shortTermGoal: c.shortTermGoal ?? existing.shortTermGoal,
                      gender: c.gender ?? existing.gender,
                      age: c.age ?? existing.age,
                      factionId: c.factionId ?? existing.factionId,
                      powerLevel: c.powerLevel ?? existing.powerLevel,
                      combatAbility: c.combatAbility ?? existing.combatAbility,
                      specialSkills: c.specialSkills ?? existing.specialSkills,
                      currentStatus: c.currentStatus ?? existing.currentStatus,
                      statusNote: c.statusNote ?? existing.statusNote,
                    },
                  });
                  records.push({
                    type: "character",
                    action: "update",
                    entityId: updated.id,
                    entityType: "character",
                    data: {
                      original: existing,
                      updated: updated,
                    },
                  });
                  savedCount++;
                }
              }
            } else if (c.action === "delete") {
              const targetId = c.id || c.characterId;
              const existing = targetId
                ? await tx.character.findUnique({ where: { id: targetId } })
                : await tx.character.findFirst({
                    where: { novelId: task.novelId, name: { contains: c.name } },
                  });
              if (existing) {
                await tx.character.delete({ where: { id: existing.id } });
                records.push({
                  type: "character",
                  action: "delete",
                  entityId: existing.id,
                  entityType: "character",
                  data: { deleted: existing },
                });
                savedCount++;
              }
            }
          } catch (e) {
            const msg = `角色 ${c.name} (${c.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 角色经历操作
      if (updates.characterExperiences) {
        for (const exp of updates.characterExperiences) {
          try {
            if (exp.action === "create") {
              const character = exp.characterId
                ? await tx.character.findUnique({ where: { id: exp.characterId } })
                : exp.characterName
                  ? await tx.character.findFirst({
                      where: { novelId: task.novelId, name: { contains: exp.characterName } },
                    })
                  : null;

              if (!character) {
                errors.push(`角色经历 ${exp.characterName ?? exp.characterId ?? ""} (${exp.action}) 失败: 未找到角色`);
                continue;
              }

              const chapter = exp.chapterId
                ? await tx.chapter.findUnique({ where: { id: exp.chapterId } })
                : exp.chapterTitle
                  ? await tx.chapter.findFirst({
                      where: { novelId: task.novelId, title: { contains: exp.chapterTitle } },
                    })
                  : await tx.chapter.findUnique({ where: { id: task.chapterId } });

              const maxOrder = await tx.characterExperience.findFirst({
                where: { characterId: character.id },
                orderBy: { order: "desc" },
                select: { order: true },
              });

              const created = await tx.characterExperience.create({
                data: {
                  characterId: character.id,
                  chapterId: chapter?.id ?? null,
                  content: exp.content,
                  order: exp.order ?? (maxOrder?.order ?? -1) + 1,
                },
              });
              records.push({
                type: "characterExperience",
                action: "create",
                entityId: created.id,
                entityType: "characterExperience",
                data: { name: character.name, content: exp.content },
              });
              savedCount++;
            } else if (exp.action === "update") {
              if (!exp.id) continue;
              const existing = await tx.characterExperience.findUnique({ where: { id: exp.id } });
              if (existing) {
                const chapter = exp.chapterId
                  ? await tx.chapter.findUnique({ where: { id: exp.chapterId } })
                  : exp.chapterTitle
                    ? await tx.chapter.findFirst({
                        where: { novelId: task.novelId, title: { contains: exp.chapterTitle } },
                      })
                    : null;
                const updated = await tx.characterExperience.update({
                  where: { id: existing.id },
                  data: {
                    content: exp.content ?? existing.content,
                    chapterId: chapter?.id ?? exp.chapterId ?? existing.chapterId,
                    order: exp.order ?? existing.order,
                  },
                });
                records.push({
                  type: "characterExperience",
                  action: "update",
                  entityId: updated.id,
                  entityType: "characterExperience",
                  data: { original: existing, updated },
                });
                savedCount++;
              }
            } else if (exp.action === "delete") {
              if (!exp.id) continue;
              const existing = await tx.characterExperience.findUnique({ where: { id: exp.id } });
              if (existing) {
                await tx.characterExperience.delete({ where: { id: existing.id } });
                records.push({
                  type: "characterExperience",
                  action: "delete",
                  entityId: existing.id,
                  entityType: "characterExperience",
                  data: { original: existing },
                });
                savedCount++;
              }
            }
          } catch (e) {
            const msg = `角色经历 ${exp.characterName ?? exp.characterId ?? exp.id ?? ""} (${exp.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 伏笔操作
      if (updates.foreshadowing) {
        for (const f of updates.foreshadowing) {
          try {
            if (f.action === "create") {
              const created = await tx.foreshadowing.create({
                data: {
                  novelId: task.novelId,
                  name: f.name,
                  plantedContent: f.plantedContent ?? null,
                  expectedPayoff: f.expectedPayoff ?? null,
                  plantedAt: f.plantedAt ?? null,
                  status: "active",
                },
              });
              records.push({
                type: "foreshadowing",
                action: "create",
                entityId: created.id,
                entityType: "foreshadowing",
                data: { novelId: task.novelId, name: f.name },
              });
              savedCount++;
            } else if (f.action === "update") {
              const existing = f.id
                ? await tx.foreshadowing.findUnique({ where: { id: f.id } })
                : await tx.foreshadowing.findFirst({
                    where: { novelId: task.novelId, name: { contains: f.name } },
                  });
              if (existing) {
                const data: Record<string, unknown> = {};
                if (f.plantedContent !== undefined) data.plantedContent = f.plantedContent;
                if (f.expectedPayoff !== undefined) data.expectedPayoff = f.expectedPayoff;
                await tx.foreshadowing.update({ where: { id: existing.id }, data });
                savedCount++;
              }
            } else if (f.action === "payoff") {
              const existing = f.id
                ? await tx.foreshadowing.findUnique({ where: { id: f.id } })
                : await tx.foreshadowing.findFirst({
                    where: { novelId: task.novelId, name: { contains: f.name }, status: "active" },
                  });
              if (existing) {
                // Phase 3: 优先使用 payoffAt，回退 plantedAt
                const updated = await tx.foreshadowing.update({
                  where: { id: existing.id },
                  data: { status: "paid_off", payoffAt: f.payoffAt || f.plantedAt || null },
                });
                records.push({
                  type: "foreshadowing",
                  action: "payoff",
                  entityId: updated.id,
                  entityType: "foreshadowing",
                  data: { original: existing, updated: updated },
                });
                savedCount++;
              }
            } else if (f.action === "abandon") {
              const existing = f.id
                ? await tx.foreshadowing.findUnique({ where: { id: f.id } })
                : await tx.foreshadowing.findFirst({
                    where: { novelId: task.novelId, name: { contains: f.name }, status: "active" },
                  });
              if (existing) {
                const updated = await tx.foreshadowing.update({
                  where: { id: existing.id },
                  data: { status: "abandoned" },
                });
                records.push({
                  type: "foreshadowing",
                  action: "abandon",
                  entityId: updated.id,
                  entityType: "foreshadowing",
                  data: { original: existing, updated: updated },
                });
                savedCount++;
              }
            }
          } catch (e) {
            const msg = `伏笔 ${f.name} (${f.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 大纲节点状态更新
      if (updates.outline) {
        for (const n of updates.outline) {
          try {
            if (n.nodeId) {
              const existing = await tx.outlineNode.findFirst({ where: { id: n.nodeId, novelId: task.novelId } });
              if (existing) {
                const updated = await tx.outlineNode.update({
                  where: { id: n.nodeId },
                  data: {
                    status: n.status,
                    actualWordCount: n.actualWordCount ?? existing.actualWordCount,
                  },
                });
                records.push({
                  type: "outline",
                  action: "update",
                  entityId: updated.id,
                  entityType: "outlineNode",
                  data: { original: existing, updated: updated },
                });
                savedCount++;
              }
            }
          } catch (e) {
            const msg = `大纲节点 ${n.nodeId} 更新失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 大纲节点增删改
      if (updates.outlineAdjustments) {
        const createdIdsByClientKey = new Map<string, string>();
        const createAdjustments = updates.outlineAdjustments
          .filter((adj) => adj.action === "create")
          .map((adj, index) => ({ adj, index }))
          .sort((a, b) => {
            const ak = normalizeOutlineNodeKind(a.adj.kind);
            const bk = normalizeOutlineNodeKind(b.adj.kind);
            return (ak ? OUTLINE_CREATE_KIND_ORDER[ak] : 99) - (bk ? OUTLINE_CREATE_KIND_ORDER[bk] : 99) ||
              a.index - b.index;
          });

        for (const { adj } of createAdjustments) {
          try {
            const parentId = await resolveOutlineCreateParentId({
              tx,
              novelId: task.novelId,
              adj,
              createdIdsByClientKey,
              errors,
            });
            if (parentId === undefined) continue;
            const created = await createOutlineNodeFromAdjustment({
              tx,
              novelId: task.novelId,
              adj,
              parentId,
              records,
            });
            if (created === true) {
              savedCount++;
              if (adj.clientKey?.trim()) {
                const record = records[records.length - 1];
                createdIdsByClientKey.set(adj.clientKey.trim(), record.entityId);
              }
            }
          } catch (e) {
            const msg = `大纲节点 ${getOutlineAdjustmentLabel(adj)} (create) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }

        for (const adj of updates.outlineAdjustments.filter((item) => item.action !== "create")) {
          try {
            if (adj.action === "update") {
              // Phase 3: nodeId 优先，nodeTitle 回退
              let existing = adj.nodeId
                ? await tx.outlineNode.findFirst({ where: { id: adj.nodeId, novelId: task.novelId } })
                : null;
              if (!existing && (adj.nodeTitle || adj.title)) {
                existing = await tx.outlineNode.findFirst({
                  where: { novelId: task.novelId, title: { contains: adj.nodeTitle || adj.title || "" } },
                });
              }
              if (existing) {
                const nextParentId = adj.parentId !== undefined ? adj.parentId || null : existing.parentId;
                if (nextParentId === existing.id) {
                  errors.push(`大纲节点 ${existing.title} 不能设为自己的父节点`);
                  continue;
                }
                const nextKind = normalizeOutlineNodeKind(adj.kind) ?? (
                  adj.parentId !== undefined ? await inferOutlineNodeKind(tx, task.novelId, nextParentId) : existing.kind
                );
                const childrenPlacementError = await validateOutlineChildrenPlacement(tx, existing.id, nextKind);
                if (childrenPlacementError) {
                  errors.push(`大纲节点 ${existing.title} 更新失败：${childrenPlacementError}`);
                  continue;
                }
                const placementError = await validateOutlineNodePlacement(tx, task.novelId, nextKind, nextParentId);
                if (placementError) {
                  errors.push(placementError);
                  continue;
                }
                const updated = await tx.outlineNode.update({
                  where: { id: existing.id },
                  data: {
                    title: adj.title ?? existing.title,
                    content: adj.content ?? existing.content,
                    ...(adj.status && { status: adj.status as OutlineNodeStatus }),
                    kind: nextKind,
                    ...(adj.parentId !== undefined && { parentId: nextParentId }),
                    ...(adj.estimatedWordCount !== undefined && { estimatedWordCount: adj.estimatedWordCount }),
                    ...(adj.actualWordCount !== undefined && { actualWordCount: adj.actualWordCount }),
                  },
                });
                records.push({
                  type: "outlineAdjustments",
                  action: "update",
                  entityId: updated.id,
                  entityType: "outlineNode",
                  data: { original: existing, updated: updated },
                });
                savedCount++;
              }
            } else if (adj.action === "delete") {
              if (adj.nodeId) {
                const existing = await tx.outlineNode.findFirst({ where: { id: adj.nodeId, novelId: task.novelId } });
                if (existing) {
                  await tx.outlineNode.delete({ where: { id: adj.nodeId, novelId: task.novelId } });
                  records.push({
                    type: "outlineAdjustments",
                    action: "delete",
                    entityId: adj.nodeId,
                    entityType: "outlineNode",
                    data: { deleted: existing },
                  });
                  savedCount++;
                }
              }
            }
          } catch (e) {
            const msg = `大纲节点 ${getOutlineAdjustmentLabel(adj)} (${adj.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 地点操作
      if (updates.locations) {
        for (const l of updates.locations) {
          try {
            if (l.action === "create") {
              const created = await tx.location.create({
                data: {
                  novelId: task.novelId,
                  name: l.name,
                  aliases: l.aliases ?? null,
                  type: l.type ?? null,
                  parentId: l.parentId ?? null,
                  description: l.description ?? null,
                  climate: l.climate ?? null,
                  culture: l.culture ?? null,
                },
              });
              records.push({
                type: "location",
                action: "create",
                entityId: created.id,
                entityType: "location",
                data: { novelId: task.novelId, name: l.name },
              });
              savedCount++;
            } else if (l.action === "update") {
              const targetId = l.id || l.locationId;
              const existing = targetId
                ? await tx.location.findUnique({ where: { id: targetId } })
                : await tx.location.findFirst({
                    where: { novelId: task.novelId, name: { contains: l.name } },
                  });
              if (existing) {
                const fieldChangeData = buildFieldChangeData(l.fieldChanges, LOCATION_MUTABLE_FIELDS);
                const updated = await tx.location.update({
                  where: { id: existing.id },
                  data: Object.keys(fieldChangeData).length > 0 ? fieldChangeData : {
                    name: l.name ?? existing.name,
                    aliases: l.aliases ?? existing.aliases,
                    type: l.type ?? existing.type,
                    parentId: l.parentId ?? existing.parentId,
                    description: l.description ?? existing.description,
                    climate: l.climate ?? existing.climate,
                    culture: l.culture ?? existing.culture,
                  },
                });
                records.push({
                  type: "location",
                  action: "update",
                  entityId: updated.id,
                  entityType: "location",
                  data: { original: existing, updated: updated },
                });
                savedCount++;
              }
            } else if (l.action === "delete") {
              const targetId = l.id || l.locationId;
              const existing = targetId
                ? await tx.location.findUnique({ where: { id: targetId } })
                : await tx.location.findFirst({
                    where: { novelId: task.novelId, name: { contains: l.name } },
                  });
              if (existing) {
                await tx.location.delete({ where: { id: existing.id } });
                records.push({
                  type: "location",
                  action: "delete",
                  entityId: existing.id,
                  entityType: "location",
                  data: { deleted: existing },
                });
                savedCount++;
              }
            }
          } catch (e) {
            const msg = `地点 ${l.name} (${l.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 物品操作
      if (updates.items) {
        for (const i of updates.items) {
          try {
            if (i.action === "create") {
              const created = await tx.item.create({
                data: {
                  novelId: task.novelId,
                  name: i.name,
                  aliases: i.aliases ?? null,
                  type: i.type ?? null,
                  rarity: i.rarity ?? null,
                  effect: i.effect ?? null,
                  origin: i.origin ?? null,
                  description: i.description ?? null,
                  ownerId: i.ownerId ?? null,
                },
              });
              records.push({
                type: "item",
                action: "create",
                entityId: created.id,
                entityType: "item",
                data: { novelId: task.novelId, name: i.name },
              });
              savedCount++;
            } else if (i.action === "update") {
              const targetId = i.id || i.itemId;
              const existing = targetId
                ? await tx.item.findUnique({ where: { id: targetId } })
                : await tx.item.findFirst({
                    where: { novelId: task.novelId, name: { contains: i.name } },
                  });
              if (existing) {
                const fieldChangeData = buildFieldChangeData(i.fieldChanges, ITEM_MUTABLE_FIELDS);
                const updated = await tx.item.update({
                  where: { id: existing.id },
                  data: Object.keys(fieldChangeData).length > 0 ? fieldChangeData : {
                    name: i.name ?? existing.name,
                    aliases: i.aliases ?? existing.aliases,
                    type: i.type ?? existing.type,
                    rarity: i.rarity ?? existing.rarity,
                    effect: i.effect ?? existing.effect,
                    origin: i.origin ?? existing.origin,
                    description: i.description ?? existing.description,
                    ownerId: i.ownerId ?? existing.ownerId,
                  },
                });
                records.push({
                  type: "item",
                  action: "update",
                  entityId: updated.id,
                  entityType: "item",
                  data: { original: existing, updated: updated },
                });
                savedCount++;
              }
            } else if (i.action === "delete") {
              const targetId = i.id || i.itemId;
              const existing = targetId
                ? await tx.item.findUnique({ where: { id: targetId } })
                : await tx.item.findFirst({
                    where: { novelId: task.novelId, name: { contains: i.name } },
                  });
              if (existing) {
                await tx.item.delete({ where: { id: existing.id } });
                records.push({
                  type: "item",
                  action: "delete",
                  entityId: existing.id,
                  entityType: "item",
                  data: { deleted: existing },
                });
                savedCount++;
              }
            }
          } catch (e) {
            const msg = `物品 ${i.name} (${i.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 势力操作
      if (updates.factions) {
        for (const f of updates.factions) {
          try {
            if (f.action === "create") {
              const created = await tx.faction.create({
                data: {
                  novelId: task.novelId,
                  name: f.name,
                  aliases: f.aliases ?? null,
                  type: f.type ?? null,
                  baseId: f.baseId ?? null,
                  description: f.description ?? null,
                },
              });
              records.push({
                type: "faction",
                action: "create",
                entityId: created.id,
                entityType: "faction",
                data: { novelId: task.novelId, name: f.name },
              });
              savedCount++;
            } else if (f.action === "update") {
              const targetId = f.id || f.factionId;
              const existing = targetId
                ? await tx.faction.findUnique({ where: { id: targetId } })
                : await tx.faction.findFirst({
                    where: { novelId: task.novelId, name: { contains: f.name } },
                  });
              if (existing) {
                const fieldChangeData = buildFieldChangeData(f.fieldChanges, FACTION_MUTABLE_FIELDS);
                const updated = await tx.faction.update({
                  where: { id: existing.id },
                  data: Object.keys(fieldChangeData).length > 0 ? fieldChangeData : {
                    name: f.name ?? existing.name,
                    aliases: f.aliases ?? existing.aliases,
                    type: f.type ?? existing.type,
                    baseId: f.baseId ?? existing.baseId,
                    description: f.description ?? existing.description,
                  },
                });
                records.push({
                  type: "faction",
                  action: "update",
                  entityId: updated.id,
                  entityType: "faction",
                  data: { original: existing, updated: updated },
                });
                savedCount++;
              }
            } else if (f.action === "delete") {
              const targetId = f.id || f.factionId;
              const existing = targetId
                ? await tx.faction.findUnique({ where: { id: targetId } })
                : await tx.faction.findFirst({
                    where: { novelId: task.novelId, name: { contains: f.name } },
                  });
              if (existing) {
                await tx.faction.delete({ where: { id: existing.id } });
                records.push({
                  type: "faction",
                  action: "delete",
                  entityId: existing.id,
                  entityType: "faction",
                  data: { deleted: existing },
                });
                savedCount++;
              }
            }
          } catch (e) {
            const msg = `势力 ${f.name} (${f.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 术语操作
      if (updates.glossaries) {
        for (const g of updates.glossaries) {
          try {
            if (g.action === "create") {
              const created = await tx.glossary.create({
                data: {
                  novelId: task.novelId,
                  term: g.term,
                  definition: g.definition,
                  category: g.category ?? null,
                },
              });
              records.push({
                type: "glossary",
                action: "create",
                entityId: created.id,
                entityType: "glossary",
                data: { novelId: task.novelId, term: g.term },
              });
              savedCount++;
            } else if (g.action === "update") {
              const targetId = g.id || g.glossaryId;
              const existing = targetId
                ? await tx.glossary.findUnique({ where: { id: targetId } })
                : await tx.glossary.findFirst({
                    where: { novelId: task.novelId, term: { contains: g.term } },
                  });
              if (existing) {
                const fieldChangeData = buildFieldChangeData(g.fieldChanges, GLOSSARY_MUTABLE_FIELDS);
                const updated = await tx.glossary.update({
                  where: { id: existing.id },
                  data: Object.keys(fieldChangeData).length > 0 ? fieldChangeData : {
                    term: g.term ?? existing.term,
                    definition: g.definition ?? existing.definition,
                    category: g.category ?? existing.category,
                  },
                });
                records.push({
                  type: "glossary",
                  action: "update",
                  entityId: updated.id,
                  entityType: "glossary",
                  data: { original: existing, updated: updated },
                });
                savedCount++;
              }
            } else if (g.action === "delete") {
              const targetId = g.id || g.glossaryId;
              const existing = targetId
                ? await tx.glossary.findUnique({ where: { id: targetId } })
                : await tx.glossary.findFirst({
                    where: { novelId: task.novelId, term: { contains: g.term } },
                  });
              if (existing) {
                await tx.glossary.delete({ where: { id: existing.id } });
                records.push({
                  type: "glossary",
                  action: "delete",
                  entityId: existing.id,
                  entityType: "glossary",
                  data: { deleted: existing },
                });
                savedCount++;
              }
            }
          } catch (e) {
            const msg = `术语 ${g.term} (${g.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 参考资料操作
      if (updates.references) {
        for (const ref of updates.references) {
          try {
            if (ref.action === "create") {
              const created = await tx.referenceMaterial.create({
                data: {
                  novelId: task.novelId,
                  title: ref.title,
                  type: (ref.type as "note" | "web" | "book" | "image" | "custom") ?? "note",
                  content: ref.content ?? "",
                },
              });
              records.push({
                type: "reference",
                action: "create",
                entityId: created.id,
                entityType: "referenceMaterial",
                data: { novelId: task.novelId, title: ref.title },
              });
              savedCount++;
            } else if (ref.action === "update") {
              if (ref.referenceId) {
                const existing = await tx.referenceMaterial.findUnique({
                  where: { id: ref.referenceId },
                });
                if (existing) {
                  const updated = await tx.referenceMaterial.update({
                    where: { id: ref.referenceId },
                    data: {
                      title: ref.title ?? existing.title,
                      type: ((ref.type as "note" | "web" | "book" | "image" | "custom") ?? existing.type) as "note" | "web" | "book" | "image" | "custom",
                      content: ref.content ?? existing.content,
                    },
                  });
                  records.push({
                    type: "reference",
                    action: "update",
                    entityId: updated.id,
                    entityType: "referenceMaterial",
                    data: { original: existing, updated: updated },
                  });
                  savedCount++;
                }
              }
            } else if (ref.action === "delete") {
              if (ref.referenceId) {
                const existing = await tx.referenceMaterial.findUnique({
                  where: { id: ref.referenceId },
                });
                if (existing) {
                  await tx.referenceMaterial.delete({ where: { id: ref.referenceId } });
                  records.push({
                    type: "reference",
                    action: "delete",
                    entityId: ref.referenceId,
                    entityType: "referenceMaterial",
                    data: { deleted: existing },
                  });
                  savedCount++;
                }
              }
            }
          } catch (e) {
            const msg = `参考资料 ${ref.title} (${ref.action}) 失败: ${e instanceof Error ? e.message : String(e)}`;
            errors.push(msg);
          }
        }
      }

      // 世界设定
      if (updates.worldSetting && typeof updates.worldSetting === "string") {
        try {
          const existing = await tx.worldSetting.findUnique({
            where: { novelId: task.novelId },
          });
          const updated = await tx.worldSetting.upsert({
            where: { novelId: task.novelId },
            create: { novelId: task.novelId, content: updates.worldSetting },
            update: { content: updates.worldSetting },
          });
          records.push({
            type: "worldSetting",
            action: existing ? "update" : "create",
            entityId: updated.id,
            entityType: "worldSetting",
            data: { original: existing, updated: updated },
          });
          savedCount++;
        } catch (e) {
          const msg = `世界设定更新失败: ${e instanceof Error ? e.message : String(e)}`;
          errors.push(msg);
        }
      }

      // 故事背景
      if (updates.storyBackground && typeof updates.storyBackground === "string") {
        try {
          const existing = await tx.storyBackground.findUnique({
            where: { novelId: task.novelId },
          });
          const updated = await tx.storyBackground.upsert({
            where: { novelId: task.novelId },
            create: { novelId: task.novelId, content: updates.storyBackground },
            update: { content: updates.storyBackground },
          });
          records.push({
            type: "storyBackground",
            action: existing ? "update" : "create",
            entityId: updated.id,
            entityType: "storyBackground",
            data: { original: existing, updated: updated },
          });
          savedCount++;
        } catch (e) {
          const msg = `故事背景更新失败: ${e instanceof Error ? e.message : String(e)}`;
          errors.push(msg);
        }
      }

      if (errors.length > 0) {
        throw new Error(errors.join("; "));
      }
    });

    // 事务成功，更新任务记录
    await prisma.writingTask.update({
      where: { id: taskId },
      data: {
        foreshadowingUpdates: JSON.stringify(updates.foreshadowing ?? []),
        outlineUpdates: JSON.stringify(updates.outline ?? []),
        characterChanges: JSON.stringify(updates.characters ?? []),
      },
    });

    const summary = buildSummary(savedCount, records);
    return {
      success: errors.length === 0,
      savedCount,
      summary,
      errors,
    };
  } catch (e) {
    // 事务失败，已自动回滚
    return {
      success: false,
      savedCount: 0,
      summary: `事务执行失败，已自动回滚: ${e instanceof Error ? e.message : String(e)}`,
      errors: [String(e)],
    };
  }
}

/**
 * 回滚操作（基于操作记录）
 *
 * @param taskId - 写作任务 ID
 * @param records - 操作记录
 */
export async function rollbackUpdates(
  taskId: string,
  records: OperationRecord[]
): Promise<{ success: boolean; message: string }> {
  if (records.length === 0) {
    return { success: true, message: "没有需要回滚的操作" };
  }

  const errors: string[] = [];

  try {
    await prisma.$transaction(async (tx) => {
      // 逆序回滚（先创建的后删除，后创建的先删除）
      for (const record of [...records].reverse()) {
        try {
          await rollbackRecord(tx, record);
        } catch (e) {
          errors.push(`回滚 ${record.type} ${record.entityId} 失败: ${e instanceof Error ? e.message : String(e)}`);
        }
      }
    });

    if (errors.length === 0) {
      return { success: true, message: "回滚成功" };
    } else {
      return { success: false, message: `部分回滚失败: ${errors.join("; ")}` };
    }
  } catch (e) {
    return {
      success: false,
      message: `回滚事务失败: ${e instanceof Error ? e.message : String(e)}`,
    };
  }
}

/**
 * 回滚单条记录
 */
async function rollbackRecord(
  tx: Parameters<Parameters<typeof prisma.$transaction>[0]>[0],
  record: OperationRecord
): Promise<void> {
  switch (record.type) {
    case "character":
      if (record.action === "create") {
        await tx.character.delete({ where: { id: record.entityId } });
      } else if (record.action === "update" || record.action === "delete") {
        // 恢复原始数据
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.character.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "characterExperience":
      if (record.action === "create") {
        await tx.characterExperience.delete({ where: { id: record.entityId } });
      } else if (record.action === "delete") {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.characterExperience.create({
            data: original as Parameters<typeof tx.characterExperience.create>[0]["data"],
          });
        }
      } else {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.characterExperience.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "foreshadowing":
      if (record.action === "create") {
        await tx.foreshadowing.delete({ where: { id: record.entityId } });
      } else {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.foreshadowing.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "outline":
    case "outlineAdjustments":
      if (record.action === "create") {
        await tx.outlineNode.delete({ where: { id: record.entityId } });
      } else {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.outlineNode.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "location":
      if (record.action === "create") {
        await tx.location.delete({ where: { id: record.entityId } });
      } else {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.location.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "item":
      if (record.action === "create") {
        await tx.item.delete({ where: { id: record.entityId } });
      } else {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.item.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "faction":
      if (record.action === "create") {
        await tx.faction.delete({ where: { id: record.entityId } });
      } else {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.faction.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "glossary":
      if (record.action === "create") {
        await tx.glossary.delete({ where: { id: record.entityId } });
      } else {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.glossary.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "reference":
      if (record.action === "create") {
        await tx.referenceMaterial.delete({ where: { id: record.entityId } });
      } else {
        const original = record.data.original as Record<string, unknown>;
        if (original) {
          await tx.referenceMaterial.update({
            where: { id: record.entityId },
            data: original,
          });
        }
      }
      break;

    case "worldSetting":
      const wsOriginal = record.data.original as { content?: string } | undefined;
      if (record.action === "create" || !wsOriginal?.content) {
        // 如果之前不存在，删除新创建的
        await tx.worldSetting.delete({ where: { novelId: record.data.novelId as string } });
      } else {
        await tx.worldSetting.update({
          where: { id: record.entityId },
          data: { content: wsOriginal.content },
        });
      }
      break;

    case "storyBackground":
      const sbOriginal = record.data.original as { content?: string } | undefined;
      if (record.action === "create" || !sbOriginal?.content) {
        await tx.storyBackground.delete({ where: { novelId: record.data.novelId as string } });
      } else {
        await tx.storyBackground.update({
          where: { id: record.entityId },
          data: { content: sbOriginal.content },
        });
      }
      break;
  }
}

/**
 * 构建操作摘要
 */
function buildSummary(savedCount: number, records: OperationRecord[]): string {
  const parts: string[] = ["# 已保存的变更\n\n"];

  // 按类型分组
  const byType: Record<string, OperationRecord[]> = {};
  for (const r of records) {
    if (!byType[r.type]) byType[r.type] = [];
    byType[r.type].push(r);
  }

  // 生成摘要
  const labels: Record<string, string> = {
    character: "角色",
    characterExperience: "角色经历",
    foreshadowing: "伏笔",
    outlineContent: "总纲",
    outline: "大纲节点",
    outlineAdjustments: "大纲调整",
    location: "地点",
    item: "物品",
    faction: "势力",
    glossary: "术语",
    reference: "参考资料",
    worldSetting: "世界设定",
    storyBackground: "故事背景",
  };

  const actionLabels: Record<string, string> = {
    create: "新增",
    update: "更新",
    delete: "删除",
    payoff: "回收",
    abandon: "废弃",
  };

  for (const [type, recs] of Object.entries(byType)) {
    const label = labels[type] ?? type;
    for (const r of recs) {
      const actionLabel = actionLabels[r.action] ?? r.action;
      const name = getRecordName(r);
      parts.push(`- ${label}: ${name} (${actionLabel})`);
    }
  }

  parts.push(`\n---\n共保存 ${savedCount} 条变更。`);

  return parts.join("\n");
}

/**
 * 获取记录名称
 */
function getRecordName(record: OperationRecord): string {
  const data = record.data;
  switch (record.type) {
    case "character":
    case "characterExperience":
    case "location":
    case "item":
    case "faction":
    case "glossary":
      return (data.name || data.term || record.entityId) as string;
    case "foreshadowing":
      return (data.name || record.entityId) as string;
    case "reference":
      return (data.title || record.entityId) as string;
    case "worldSetting":
      return "世界设定";
    case "storyBackground":
      return "故事背景";
    default:
      return record.entityId;
  }
}

/**
 * 生成变更预览（用于前端展示）
 */
export function generatePreview(updates: AgentUpdates): string {
  const parts: string[] = ["# 变更预览\n\n"];

  if (updates.characters?.length) {
    parts.push("## 角色");
    for (const c of updates.characters) {
      parts.push(`- ${c.name} (${c.action === "create" ? "新增" : c.action === "update" ? "更新" : "删除"})`);
    }
    parts.push("");
  }

  if (updates.characterExperiences?.length) {
    parts.push("## 角色经历");
    for (const exp of updates.characterExperiences) {
      const name = exp.characterName || exp.characterId || exp.id || "未指定角色";
      parts.push(`- ${name}: ${exp.content} (${exp.action === "create" ? "新增" : exp.action === "update" ? "更新" : "删除"})`);
    }
    parts.push("");
  }

  if (updates.foreshadowing?.length) {
    parts.push("## 伏笔");
    for (const f of updates.foreshadowing) {
      const action = f.action === "create" ? "新增" : f.action === "payoff" ? "回收" : "废弃";
      parts.push(`- ${f.name} (${action})`);
    }
    parts.push("");
  }

  if (updates.outlineContent || updates.outline?.length || updates.outlineAdjustments?.length) {
    parts.push("## 大纲");
    if (updates.outlineContent) {
      parts.push("- 总纲（更新）");
    }
    for (const n of updates.outline ?? []) {
      parts.push(`- 节点 ${n.nodeId}: → ${n.status}`);
    }
    for (const adj of updates.outlineAdjustments ?? []) {
      const action = adj.action === "create" ? "新增" : adj.action === "update" ? "更新" : "删除";
      const kind = adj.kind ? ` · ${adj.kind}` : "";
      const parent = adj.parentKey ? ` · parentKey=${adj.parentKey}` : "";
      parts.push(`- ${getOutlineNodeTitle(adj)}${kind}${parent} (${action})`);
    }
    parts.push("");
  }

  if (updates.locations?.length) {
    parts.push("## 地点");
    for (const l of updates.locations) {
      parts.push(`- ${l.name} (${l.action === "create" ? "新增" : l.action === "update" ? "更新" : "删除"})`);
    }
    parts.push("");
  }

  if (updates.items?.length) {
    parts.push("## 物品");
    for (const i of updates.items) {
      parts.push(`- ${i.name} (${i.action === "create" ? "新增" : i.action === "update" ? "更新" : "删除"})`);
    }
    parts.push("");
  }

  if (updates.factions?.length) {
    parts.push("## 势力");
    for (const f of updates.factions) {
      parts.push(`- ${f.name} (${f.action === "create" ? "新增" : f.action === "update" ? "更新" : "删除"})`);
    }
    parts.push("");
  }

  if (updates.glossaries?.length) {
    parts.push("## 术语");
    for (const g of updates.glossaries) {
      parts.push(`- ${g.term} (${g.action === "create" ? "新增" : g.action === "update" ? "更新" : "删除"})`);
    }
    parts.push("");
  }

  if (updates.worldSetting) {
    parts.push("## 世界设定");
    parts.push("- 将更新世界设定内容");
    parts.push("");
  }

  if (updates.storyBackground) {
    parts.push("## 故事背景");
    parts.push("- 将更新故事背景内容");
    parts.push("");
  }

  return parts.join("\n");
}
