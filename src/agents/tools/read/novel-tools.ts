/**
 * 小说信息只读工具
 *
 * @module agents/tools/read/novel-tools
 * @description get_novel_info, list_available_data — 基础小说信息查询
 *
 * @phase Phase 3 — 工具层重构
 */

import { z } from "zod";
import type { ToolDefinition } from "../registry";
import { registerTool } from "../registry";
import type { ToolExecutorFn } from "../registry";
import { readOnlyPermission } from "../permissions";
import { prisma } from "@/shared/db/prisma";

// ============================================
// 辅助函数（从 tools.ts 迁移）
// ============================================

function compactText(value: string | null | undefined, maxLength = 120): string {
  if (!value) return "";
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > maxLength ? text.slice(0, maxLength - 1) + "…" : text;
}

function getNovelId(state: Parameters<ToolExecutorFn>[1]): string {
  return state.novelId || String((state.novelData as Record<string, unknown>).novelId ?? "");
}

// ============================================
// 工具定义 & 注册
// ============================================

/** get_novel_info — 获取小说基本信息 */
export const GET_NOVEL_INFO_DEF: ToolDefinition = {
  name: "get_novel_info",
  description: "获取当前小说的基本信息（名称、章节、大纲摘要、世界观、作品圣经、剧情进度）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("novel.read"),
  toolKind: "read",
};

export const getNovelInfoExecutor: ToolExecutorFn = async (_, state) => {
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  if (novelId) {
    const novel = await prisma.novel.findUnique({
      where: { id: novelId },
      select: {
        name: true,
        storyProgress: true,
        storyBackground: { select: { content: true } },
        worldSetting: { select: { content: true } },
        outline: { select: { content: true } },
        writingBible: {
          select: {
            genre: true,
            targetReaders: true,
            coreSellingPoint: true,
            readerPromise: true,
            appealModel: true,
            taboo: true,
            comparableTitles: true,
            notes: true,
          },
        },
        chapters: {
          where: { id: String(d.chapterId ?? state.chapterId ?? "") },
          select: { title: true },
          take: 1,
        },
      },
    });

    if (novel) {
      return JSON.stringify({
        novelName: novel.name,
        chapterTitle: novel.chapters[0]?.title ?? d.chapterTitle,
        outlineSummary: novel.outline?.content ?? "",
        storyBackground: novel.storyBackground?.content ?? "",
        worldSetting: novel.worldSetting?.content ?? "",
        writingBible: novel.writingBible,
        storyProgress: novel.storyProgress ?? "",
      }, null, 2);
    }
  }

  return JSON.stringify({
    novelName: d.novelName,
    chapterTitle: d.chapterTitle,
    outlineSummary: d.outlineSummary,
    storyBackground: d.storyBackground,
    worldSetting: d.worldSetting,
    writingBible: d.writingBible,
    storyProgress: d.storyProgress,
  }, null, 2);
};

/** list_available_data — 列出所有可用数据概览 */
export const LIST_AVAILABLE_DATA_DEF: ToolDefinition = {
  name: "list_available_data",
  description: "列出当前可用的所有数据类型及其数量（角色、势力、地点、物品、术语、大纲节点、伏笔、参考资料）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("novel.read"),
  toolKind: "read",
};

export const listAvailableDataExecutor: ToolExecutorFn = async (_, state) => {
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  if (novelId) {
    const [
      characters,
      factions,
      locations,
      items,
      glossaries,
      outlineNodes,
      foreshadowings,
      references,
      novel,
    ] = await Promise.all([
      prisma.character.count({ where: { novelId } }),
      prisma.faction.count({ where: { novelId } }),
      prisma.location.count({ where: { novelId } }),
      prisma.item.count({ where: { novelId } }),
      prisma.glossary.count({ where: { novelId } }),
      prisma.outlineNode.count({ where: { novelId } }),
      prisma.foreshadowing.count({ where: { novelId } }),
      prisma.referenceMaterial.count({ where: { novelId } }),
      prisma.novel.findUnique({
        where: { id: novelId },
        select: { appliedStyleId: true },
      }),
    ]);

    return JSON.stringify({
      characters,
      factions,
      locations,
      items,
      glossaries,
      outlineNodes,
      foreshadowings,
      references,
      hasStyleProfile: !!novel?.appliedStyleId,
    }, null, 2);
  }

  const arr = (key: string) => (d[key] as unknown[])?.length ?? 0;
  return JSON.stringify({
    characters: arr("characters"),
    factions: arr("factions"),
    locations: arr("locations"),
    items: arr("items"),
    glossaries: arr("glossaries"),
    outlineNodes: arr("outlineNodes"),
    foreshadowings: arr("foreshadowings"),
    references: arr("references"),
    hasStyleProfile: !!d.styleProfile,
  }, null, 2);
};

// ============================================
// 注册
// ============================================

registerTool(GET_NOVEL_INFO_DEF, getNovelInfoExecutor);
registerTool(LIST_AVAILABLE_DATA_DEF, listAvailableDataExecutor);
