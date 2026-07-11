/**
 * 角色只读工具
 *
 * @module agents/tools/read/character-tools
 * @description list_characters_summary, get_character_detail, get_character_list
 *
 * @phase Phase 3 — 工具层重构
 */

import { z } from "zod";
import type { ToolDefinition, ToolExecutorFn } from "../registry";
import { registerTool } from "../registry";
import { readOnlyPermission } from "../permissions";
import { prisma } from "@/shared/db/prisma";

// ============================================
// 辅助函数
// ============================================

function compactText(value: string | null | undefined, maxLength = 120): string {
  if (!value) return "";
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > maxLength ? text.slice(0, maxLength - 1) + "…" : text;
}

function findByName<T extends { name: string; aliases?: string }>(
  items: T[],
  query: string
): T | undefined {
  return items.find(
    (item) =>
      item.name.includes(query) ||
      query.includes(item.name) ||
      Boolean(item.aliases && (item.aliases.includes(query) || query.includes(item.aliases)))
  );
}

function findByNullableName<T extends { name: string; aliases?: string | null }>(
  items: T[],
  query: string
): T | undefined {
  return items.find(
    (item) =>
      item.name.includes(query) ||
      query.includes(item.name) ||
      Boolean(item.aliases && (item.aliases.includes(query) || query.includes(item.aliases)))
  );
}

function getNovelId(state: Parameters<ToolExecutorFn>[1]): string {
  return state.novelId || String((state.novelData as Record<string, unknown>).novelId ?? "");
}

function summarizeCharacter(c: Record<string, unknown>) {
  return {
    id: c.id,
    name: c.name,
    aliases: c.aliases,
    identity: c.identity,
    faction: (c.faction as Record<string, unknown>)?.name,
    personality: compactText(c.personality as string, 80),
    coreDesire: compactText(c.coreDesire as string, 80),
    behaviorBoundaries: compactText(c.behaviorBoundaries as string, 80),
    shortTermGoal: compactText(c.shortTermGoal as string, 80),
    status: c.statusNote || c.currentStatus,
    experienceCount: (c.experiences as unknown[])?.length ?? 0,
  };
}

// ============================================
// 工具定义 & 注册
// ============================================

export const LIST_CHARACTERS_SUMMARY_DEF: ToolDefinition = {
  name: "list_characters_summary",
  description: "列出所有角色摘要（名称、身份、势力、性格、核心欲望、行为边界、短期目标、状态），不返回完整详情",
  inputSchema: z.object({}),
  permission: readOnlyPermission("character.read"),
  toolKind: "read",
};

export const listCharactersSummaryExecutor: ToolExecutorFn = async (_, state) => {
  const novelId = getNovelId(state);
  if (!novelId) {
    const chars = (state.novelData as Record<string, unknown>).characters as Record<string, unknown>[];
    return JSON.stringify((chars ?? []).map(summarizeCharacter), null, 2);
  }

  const chars = await prisma.character.findMany({
    where: { novelId },
    orderBy: { updatedAt: "desc" },
    include: {
      faction: { select: { id: true, name: true } },
      experiences: { select: { id: true }, take: 1 },
    },
  });

  return JSON.stringify(chars.map((c) => summarizeCharacter(c as unknown as Record<string, unknown>)), null, 2);
};

async function findCharacterByName(novelId: string, charName: string) {
  const candidates = await prisma.character.findMany({
    where: {
      novelId,
      OR: [
        { name: { contains: charName } },
        { aliases: { contains: charName } },
      ],
    },
    orderBy: { updatedAt: "desc" },
    take: 20,
    include: {
      faction: { select: { id: true, name: true } },
      experiences: { orderBy: { order: "asc" } },
      outgoingRelations: {
        include: { target: { select: { id: true, name: true } } },
      },
      incomingRelations: {
        include: { character: { select: { id: true, name: true } } },
      },
    },
  });

  return findByNullableName(candidates, charName) ?? candidates[0];
}

export const GET_CHARACTER_DETAIL_DEF: ToolDefinition = {
  name: "get_character_detail",
  description: "获取指定角色的完整设定详情（含性格、身份、背景、实力、关系、经历等）",
  inputSchema: z.object({
    character_name: z.string().min(1, "角色名称不能为空"),
  }),
  permission: readOnlyPermission("character.read"),
  toolKind: "read",
};

export const getCharacterDetailExecutor: ToolExecutorFn = async (args, state) => {
  const charName = args.character_name as string;
  const novelId = getNovelId(state);
  if (!novelId) {
    const chars = (state.novelData as Record<string, unknown>).characters as Record<string, unknown>[];
    const c = findByName((chars ?? []) as Array<{ name: string; aliases?: string }>, charName);
    return c ? JSON.stringify(c, null, 2) : `未找到角色 "${charName}"`;
  }

  const c = await findCharacterByName(novelId, charName);
  return c ? JSON.stringify(c, null, 2) : `未找到角色 "${charName}"`;
};

export const GET_CHARACTER_LIST_DEF: ToolDefinition = {
  name: "get_character_list",
  description: "获取角色精简列表（仅 id + name + aliases + faction），用于快速了解有哪些角色",
  inputSchema: z.object({}),
  permission: readOnlyPermission("character.read"),
  toolKind: "read",
};

export const getCharacterListExecutor: ToolExecutorFn = async (_, state) => {
  const novelId = getNovelId(state);
  if (!novelId) {
    const chars = (state.novelData as Record<string, unknown>).characters as Record<string, unknown>[];
    const list = (chars ?? []).map((c) => ({
      name: c.name,
      aliases: c.aliases,
      gender: c.gender,
      identity: c.identity,
      faction: (c.faction as Record<string, unknown>)?.name,
      currentStatus: c.currentStatus,
    }));
    return JSON.stringify(list, null, 2);
  }

  const chars = await prisma.character.findMany({
    where: { novelId },
    orderBy: { updatedAt: "desc" },
    select: {
      name: true,
      aliases: true,
      gender: true,
      identity: true,
      currentStatus: true,
      faction: { select: { name: true } },
    },
  });

  const list = chars.map((c) => ({
    name: c.name,
    aliases: c.aliases,
    gender: c.gender,
    identity: c.identity,
    faction: c.faction?.name,
    currentStatus: c.currentStatus,
  }));
  return JSON.stringify(list, null, 2);
};

// ============================================
// 注册
// ============================================

registerTool(LIST_CHARACTERS_SUMMARY_DEF, listCharactersSummaryExecutor);
registerTool(GET_CHARACTER_DETAIL_DEF, getCharacterDetailExecutor);
registerTool(GET_CHARACTER_LIST_DEF, getCharacterListExecutor);
