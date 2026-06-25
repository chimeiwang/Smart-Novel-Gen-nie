/**
 * 设定/世界观只读工具
 *
 * @module agents/tools/read/lore-tools
 * @description 势力、地点、物品、术语、搜索、相似召回 — 10 个工具
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

function includesKeyword(value: string | null | undefined, keyword: string): boolean {
  return Boolean(value && value.toLowerCase().includes(keyword));
}

function getNovelId(state: Parameters<ToolExecutorFn>[1]): string {
  return state.novelId || String((state.novelData as Record<string, unknown>).novelId ?? "");
}

function asRecords(items: unknown[] | undefined): Record<string, unknown>[] {
  return (items ?? []) as Record<string, unknown>[];
}

// 摘要函数
function summarizeFaction(f: Record<string, unknown>) {
  return {
    name: f.name,
    aliases: f.aliases,
    type: f.type,
    base: (f.base as Record<string, unknown>)?.name,
    summary: compactText(f.description as string, 100),
  };
}

function summarizeLocation(l: Record<string, unknown>) {
  return {
    name: l.name,
    aliases: l.aliases,
    type: l.type,
    climate: l.climate,
    summary: compactText(l.description as string, 100),
  };
}

function summarizeItem(i: Record<string, unknown>) {
  return {
    name: i.name,
    aliases: i.aliases,
    type: i.type,
    owner: (i.owner as Record<string, unknown>)?.name,
    effect: compactText(i.effect as string, 90),
    summary: compactText(i.description as string, 90),
  };
}

function summarizeGlossary(g: Record<string, unknown>) {
  return {
    term: g.term,
    category: g.category,
    definition: compactText(g.definition as string, 100),
  };
}

// ============================================
// 势力工具
// ============================================

export const LIST_FACTIONS_SUMMARY_DEF: ToolDefinition = {
  name: "list_factions_summary",
  description: "列出所有势力摘要（名称、类型、基地、简介）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const listFactionsSummaryExecutor: ToolExecutorFn = async (_, state) => {
  const novelId = getNovelId(state);
  const factions = novelId
    ? await prisma.faction.findMany({
        where: { novelId },
        orderBy: { updatedAt: "desc" },
        include: { base: { select: { id: true, name: true } } },
      })
    : (state.novelData as Record<string, unknown>).factions as Record<string, unknown>[];
  return JSON.stringify(factions.map(summarizeFaction), null, 2);
};

export const GET_FACTION_DETAIL_DEF: ToolDefinition = {
  name: "get_faction_detail",
  description: "获取指定势力的完整详情",
  inputSchema: z.object({
    faction_name: z.string().min(1, "势力名称不能为空"),
  }),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const getFactionDetailExecutor: ToolExecutorFn = async (args, state) => {
  const factionName = args.faction_name as string;
  const novelId = getNovelId(state);
  const f = novelId
    ? await prisma.faction.findFirst({
        where: {
          novelId,
          OR: [
            { name: { contains: factionName } },
            { aliases: { contains: factionName } },
          ],
        },
        include: {
          base: { select: { id: true, name: true } },
          members: { select: { id: true, name: true, identity: true, currentStatus: true } },
          territories: { select: { id: true, name: true, type: true } },
        },
      })
    : findByName(
        ((state.novelData as Record<string, unknown>).factions as Array<{ name: string; aliases?: string }> | undefined) ?? [],
        factionName
      );
  return f ? JSON.stringify(f, null, 2) : `未找到势力 "${factionName}"`;
};

// ============================================
// 地点工具
// ============================================

export const LIST_LOCATIONS_SUMMARY_DEF: ToolDefinition = {
  name: "list_locations_summary",
  description: "列出所有地点摘要（名称、类型、气候、简介）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const listLocationsSummaryExecutor: ToolExecutorFn = async (_, state) => {
  const novelId = getNovelId(state);
  const locations = novelId
    ? await prisma.location.findMany({
        where: { novelId },
        orderBy: { updatedAt: "desc" },
      })
    : (state.novelData as Record<string, unknown>).locations as Record<string, unknown>[];
  return JSON.stringify(locations.map(summarizeLocation), null, 2);
};

export const GET_LOCATION_DETAIL_DEF: ToolDefinition = {
  name: "get_location_detail",
  description: "获取指定位点的完整详情",
  inputSchema: z.object({
    location_name: z.string().min(1, "地点名称不能为空"),
  }),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const getLocationDetailExecutor: ToolExecutorFn = async (args, state) => {
  const locName = args.location_name as string;
  const novelId = getNovelId(state);
  const l = novelId
    ? await prisma.location.findFirst({
        where: {
          novelId,
          OR: [
            { name: { contains: locName } },
            { aliases: { contains: locName } },
          ],
        },
        include: {
          parent: { select: { id: true, name: true } },
          children: { select: { id: true, name: true, type: true } },
          factionBases: { select: { id: true, name: true } },
          factionTerritories: { select: { id: true, name: true } },
        },
      })
    : findByName(
        ((state.novelData as Record<string, unknown>).locations as Array<{ name: string; aliases?: string }> | undefined) ?? [],
        locName
      );
  return l ? JSON.stringify(l, null, 2) : `未找到地点 "${locName}"`;
};

// ============================================
// 物品工具
// ============================================

export const LIST_ITEMS_SUMMARY_DEF: ToolDefinition = {
  name: "list_items_summary",
  description: "列出所有物品摘要（名称、类型、稀有度、效果、简介）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const listItemsSummaryExecutor: ToolExecutorFn = async (_, state) => {
  const novelId = getNovelId(state);
  const items = novelId
    ? await prisma.item.findMany({
        where: { novelId },
        orderBy: { updatedAt: "desc" },
        include: { owner: { select: { id: true, name: true } } },
      })
    : (state.novelData as Record<string, unknown>).items as Record<string, unknown>[];
  return JSON.stringify(items.map(summarizeItem), null, 2);
};

export const GET_ITEM_DETAIL_DEF: ToolDefinition = {
  name: "get_item_detail",
  description: "获取指定物品的完整详情",
  inputSchema: z.object({
    item_name: z.string().min(1, "物品名称不能为空"),
  }),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const getItemDetailExecutor: ToolExecutorFn = async (args, state) => {
  const itemName = args.item_name as string;
  const novelId = getNovelId(state);
  const item = novelId
    ? await prisma.item.findFirst({
        where: {
          novelId,
          OR: [
            { name: { contains: itemName } },
            { aliases: { contains: itemName } },
          ],
        },
        include: { owner: { select: { id: true, name: true } } },
      })
    : findByName(
        ((state.novelData as Record<string, unknown>).items as Array<{ name: string; aliases?: string }> | undefined) ?? [],
        itemName
      );
  return item ? JSON.stringify(item, null, 2) : `未找到物品 "${itemName}"`;
};

// ============================================
// 术语工具
// ============================================

export const LIST_GLOSSARIES_SUMMARY_DEF: ToolDefinition = {
  name: "list_glossaries_summary",
  description: "列出所有术语摘要（术语、分类、定义）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const listGlossariesSummaryExecutor: ToolExecutorFn = async (_, state) => {
  const novelId = getNovelId(state);
  const glossaries = novelId
    ? await prisma.glossary.findMany({
        where: { novelId },
        orderBy: { updatedAt: "desc" },
      })
    : (state.novelData as Record<string, unknown>).glossaries as Record<string, unknown>[];
  return JSON.stringify(glossaries.map(summarizeGlossary), null, 2);
};

export const GET_GLOSSARY_DETAIL_DEF: ToolDefinition = {
  name: "get_glossary_detail",
  description: "获取指定术语的完整定义",
  inputSchema: z.object({
    term: z.string().min(1, "术语名称不能为空"),
  }),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const getGlossaryDetailExecutor: ToolExecutorFn = async (args, state) => {
  const term = args.term as string;
  const novelId = getNovelId(state);
  const glossary = novelId
    ? await prisma.glossary.findFirst({
        where: {
          novelId,
          OR: [
            { term: { contains: term } },
            { definition: { contains: term } },
          ],
        },
      })
    : (((state.novelData as Record<string, unknown>).glossaries as Record<string, unknown>[]) ?? []).find(
        (g: Record<string, unknown>) =>
          (g.term as string).includes(term) || term.includes(g.term as string)
      );
  return glossary ? JSON.stringify(glossary, null, 2) : `未找到术语 "${term}"`;
};

// ============================================
// 搜索工具
// ============================================

export const SEARCH_LORE_DEF: ToolDefinition = {
  name: "search_lore",
  description: "跨所有设定内容搜索关键词。参数：keyword（搜索词）",
  inputSchema: z.object({
    keyword: z.string().min(1, "搜索关键词不能为空"),
  }),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const searchLoreExecutor: ToolExecutorFn = async (args, state) => {
  const rawKeyword = args.keyword as string;
  const keyword = rawKeyword.toLowerCase();
  const d = state.novelData as Record<string, unknown>;
  const results: Record<string, unknown[]> = {};

  const searchFields = [
    { key: "characters", fields: ["name", "aliases", "personality", "identity", "background", "coreDesire"] },
    { key: "factions", fields: ["name", "aliases", "type", "description"] },
    { key: "locations", fields: ["name", "aliases", "type", "description"] },
    { key: "items", fields: ["name", "aliases", "type", "effect", "description"] },
    { key: "glossaries", fields: ["term", "definition"] },
    { key: "foreshadowings", fields: ["name", "plantedContent", "expectedPayoff"] },
  ];

  const novelId = getNovelId(state);
  const dbItems: Record<string, unknown[]> = novelId
    ? {
        characters: await prisma.character.findMany({
          where: {
            novelId,
            OR: [
              { name: { contains: rawKeyword } },
              { aliases: { contains: rawKeyword } },
              { personality: { contains: rawKeyword } },
              { identity: { contains: rawKeyword } },
              { background: { contains: rawKeyword } },
              { coreDesire: { contains: rawKeyword } },
            ],
          },
          take: 20,
        }),
        factions: await prisma.faction.findMany({
          where: {
            novelId,
            OR: [
              { name: { contains: rawKeyword } },
              { aliases: { contains: rawKeyword } },
              { type: { contains: rawKeyword } },
              { description: { contains: rawKeyword } },
            ],
          },
          take: 20,
        }),
        locations: await prisma.location.findMany({
          where: {
            novelId,
            OR: [
              { name: { contains: rawKeyword } },
              { aliases: { contains: rawKeyword } },
              { type: { contains: rawKeyword } },
              { description: { contains: rawKeyword } },
            ],
          },
          take: 20,
        }),
        items: await prisma.item.findMany({
          where: {
            novelId,
            OR: [
              { name: { contains: rawKeyword } },
              { aliases: { contains: rawKeyword } },
              { type: { contains: rawKeyword } },
              { effect: { contains: rawKeyword } },
              { description: { contains: rawKeyword } },
            ],
          },
          take: 20,
        }),
        glossaries: await prisma.glossary.findMany({
          where: {
            novelId,
            OR: [
              { term: { contains: rawKeyword } },
              { definition: { contains: rawKeyword } },
            ],
          },
          take: 20,
        }),
        foreshadowings: await prisma.foreshadowing.findMany({
          where: {
            novelId,
            OR: [
              { name: { contains: rawKeyword } },
              { plantedContent: { contains: rawKeyword } },
              { expectedPayoff: { contains: rawKeyword } },
            ],
          },
          take: 20,
        }),
      }
    : {};

  for (const { key, fields } of searchFields) {
    const items = novelId ? asRecords(dbItems[key]) : ((d[key] as Record<string, unknown>[]) || []);
    const matched = items.filter((item) =>
      fields.some((f) => includesKeyword(item[f] as string, keyword))
    );
    if (matched.length > 0) {
      results[key] = matched.map((item) => ({
        name: item.name || item.term,
        matched: fields
          .filter((f) => includesKeyword(item[f] as string, keyword))
          .map((f) => `${f}: ${compactText(item[f] as string, 100)}`),
      }));
    }
  }

  return JSON.stringify({
    keyword,
    totalResults: Object.values(results).flat().length,
    results,
    note: "搜索结果基于索引摘要，可能存在遗漏；关键信息请用 get_xxx_detail 工具做全量比对。",
  }, null, 2);
};

export const FIND_SIMILAR_LORE_DEF: ToolDefinition = {
  name: "find_similar_lore",
  description: "查找相似的设定内容（去重辅助）。参数：keyword（搜索词）、threshold（相似度阈值 0-1，默认 0.3）",
  inputSchema: z.object({
    keyword: z.string().min(1, "搜索词不能为空"),
    threshold: z.number().min(0).max(1).optional(),
  }),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const findSimilarLoreExecutor: ToolExecutorFn = async (args, state) => {
  const keyword = (args.keyword as string).toLowerCase();
  const d = state.novelData as Record<string, unknown>;
  const results: Array<{ domain: string; name: string; similarity: number; note: string }> = [];

  const domains = [
    "characters",
    "factions",
    "locations",
    "items",
    "glossaries",
  ];

  const novelId = getNovelId(state);
  const dbItems: Record<string, unknown[]> = novelId
    ? {
        characters: await prisma.character.findMany({
          where: { novelId },
          select: { name: true },
          orderBy: { updatedAt: "desc" },
          take: 200,
        }),
        factions: await prisma.faction.findMany({
          where: { novelId },
          select: { name: true },
          orderBy: { updatedAt: "desc" },
          take: 200,
        }),
        locations: await prisma.location.findMany({
          where: { novelId },
          select: { name: true },
          orderBy: { updatedAt: "desc" },
          take: 200,
        }),
        items: await prisma.item.findMany({
          where: { novelId },
          select: { name: true },
          orderBy: { updatedAt: "desc" },
          take: 200,
        }),
        glossaries: await prisma.glossary.findMany({
          where: { novelId },
          select: { term: true },
          orderBy: { updatedAt: "desc" },
          take: 200,
        }),
      }
    : {};

  for (const domain of domains) {
    const items = novelId ? asRecords(dbItems[domain]) : ((d[domain] as Record<string, unknown>[]) || []);
    for (const item of items) {
      const name = (item.name || item.term || "") as string;
      const similarity = calcTextSimilarity(name.toLowerCase(), keyword);
      if (similarity > 0.3) {
        results.push({
          domain,
          name,
          similarity: Math.round(similarity * 100) / 100,
          note: similarity > 0.7 ? "⚠️ 高度相似，可能存在重复" : "相似度较低",
        });
      }
    }
  }

  results.sort((a, b) => b.similarity - a.similarity);
  return JSON.stringify({
    keyword,
    results: results.slice(0, 10),
    hint: "相似不等同于重复，请结合具体上下文判断是否需要合并。",
  }, null, 2);
};

/** 简易文本相似度计算（基于公共子串） */
function calcTextSimilarity(a: string, b: string): number {
  if (!a || !b) return 0;
  let matches = 0;
  const minLen = Math.min(a.length, b.length, 10);
  for (let i = 0; i < a.length - 1; i++) {
    const sub = a.slice(i, i + 2);
    if (b.includes(sub)) matches++;
  }
  return Math.min(1, matches / Math.max(a.length - 1, 1));
}

// ============================================
// 文风工具
// ============================================

export const GET_STYLE_PROFILE_DEF: ToolDefinition = {
  name: "get_style_profile",
  description: "获取当前小说的文风画像（如果已提取）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("style.read"),
  toolKind: "read",
};

export const getStyleProfileExecutor: ToolExecutorFn = async (_, state) => {
  const novelId = getNovelId(state);
  if (novelId) {
    const novel = await prisma.novel.findUnique({
      where: { id: novelId },
      select: { appliedStyle: { select: { portraitMarkdown: true } } },
    });
    if (!novel?.appliedStyle?.portraitMarkdown) return "暂无文风画像，请先在文风管理页面提取。";
    return novel.appliedStyle.portraitMarkdown;
  }

  const d = state.novelData as Record<string, unknown>;
  if (!d.styleProfile) return "暂无文风画像，请先在文风管理页面提取。";
  return String(d.styleProfile);
};

// ============================================
// 注册
// ============================================

registerTool(LIST_FACTIONS_SUMMARY_DEF, listFactionsSummaryExecutor);
registerTool(GET_FACTION_DETAIL_DEF, getFactionDetailExecutor);
registerTool(LIST_LOCATIONS_SUMMARY_DEF, listLocationsSummaryExecutor);
registerTool(GET_LOCATION_DETAIL_DEF, getLocationDetailExecutor);
registerTool(LIST_ITEMS_SUMMARY_DEF, listItemsSummaryExecutor);
registerTool(GET_ITEM_DETAIL_DEF, getItemDetailExecutor);
registerTool(LIST_GLOSSARIES_SUMMARY_DEF, listGlossariesSummaryExecutor);
registerTool(GET_GLOSSARY_DETAIL_DEF, getGlossaryDetailExecutor);
registerTool(SEARCH_LORE_DEF, searchLoreExecutor);
registerTool(FIND_SIMILAR_LORE_DEF, findSimilarLoreExecutor);
registerTool(GET_STYLE_PROFILE_DEF, getStyleProfileExecutor);
