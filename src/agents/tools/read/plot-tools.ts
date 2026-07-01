/**
 * 剧情只读工具
 *
 * @module agents/tools/read/plot-tools
 * @description 大纲、剧情进度、伏笔、章节查询 — 6 个工具
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

function summarizeForeshadowing(f: Record<string, unknown>) {
  return {
    name: f.name,
    status: f.status,
    plantedAt: f.plantedAt,
    plantedContent: compactText(f.plantedContent as string, 90),
    expectedPayoff: compactText(f.expectedPayoff as string, 90),
    payoffAt: f.payoffAt,
  };
}

function getNovelId(state: Parameters<ToolExecutorFn>[1]): string {
  return state.novelId || String((state.novelData as Record<string, unknown>).novelId ?? "");
}

function getChapterId(state: Parameters<ToolExecutorFn>[1]): string {
  return state.chapterId || String((state.novelData as Record<string, unknown>).chapterId ?? "");
}

// ============================================
// 大纲工具
// ============================================

export const LIST_OUTLINE_SUMMARY_DEF: ToolDefinition = {
  name: "list_outline_summary",
  description: "列出大纲节点短摘要（标题、状态、排序、短摘要）。默认不返回长总纲全文；确需全文时传 include_full_summary=true。",
  inputSchema: z.object({
    include_full_summary: z.boolean().optional(),
  }),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const listOutlineSummaryExecutor: ToolExecutorFn = async (args, state) => {
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const includeFullSummary = args.include_full_summary === true;
  const [outline, nodes] = novelId
    ? await Promise.all([
        prisma.outline.findUnique({ where: { novelId } }),
        prisma.outlineNode.findMany({
          where: { novelId },
          orderBy: [{ order: "asc" }, { updatedAt: "desc" }],
        }),
      ])
    : [null, (d.outlineNodes as Record<string, unknown>[]) || []];

  return JSON.stringify({
    summary: includeFullSummary
      ? outline?.content ?? d.outlineSummary
      : compactText((outline?.content ?? d.outlineSummary) as string, 500),
    summaryTruncated: !includeFullSummary,
    nodes: nodes.map((node) => ({
      id: node.id,
      title: node.title,
      kind: node.kind,
      status: node.status,
      order: node.order,
      parentId: node.parentId,
      summary: compactText(node.content as string, 80),
    })),
  }, null, 2);
};

export const GET_OUTLINE_NODE_DEF: ToolDefinition = {
  name: "get_outline_node",
  description: "获取指定大纲节点的完整内容。参数：node_title（节点标题）",
  inputSchema: z.object({
    node_title: z.string().min(1, "节点标题不能为空"),
  }),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const getOutlineNodeExecutor: ToolExecutorFn = async (args, state) => {
  const nodeTitle = args.node_title as string;
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const node = novelId
    ? await prisma.outlineNode.findFirst({
        where: {
          novelId,
          title: { contains: nodeTitle },
        },
        include: {
          parent: { select: { id: true, title: true, kind: true } },
          children: { orderBy: { order: "asc" } },
        },
      })
    : ((d.outlineNodes as Record<string, unknown>[]) || []).find(
        (n: Record<string, unknown>) =>
          (n.title as string).includes(nodeTitle) || nodeTitle.includes(n.title as string)
      );
  return node
    ? JSON.stringify(node, null, 2)
    : `未找到大纲节点 "${nodeTitle}"`;
};

// ============================================
// 剧情进度工具
// ============================================

export const GET_PLOT_PROGRESS_DEF: ToolDefinition = {
  name: "get_plot_progress",
  description: "获取当前剧情进度（当前阶段、目标、冲突、下一里程碑）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const getPlotProgressExecutor: ToolExecutorFn = async (_, state) => {
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const pp = novelId
    ? await prisma.plotProgress.findUnique({ where: { novelId } })
    : (d.plotProgress as Record<string, unknown> || {});

  return JSON.stringify({
    currentStage: pp?.currentStage ?? "未设置",
    currentGoal: pp?.currentGoal,
    currentConflict: pp?.currentConflict,
    nextMilestone: pp?.nextMilestone,
  }, null, 2);
};

// ============================================
// 伏笔工具
// ============================================

export const LIST_FORESHADOWINGS_SUMMARY_DEF: ToolDefinition = {
  name: "list_foreshadowings_summary",
  description: "列出所有伏笔摘要（名称、状态、埋设时机、埋设内容摘要、预期回收方式）",
  inputSchema: z.object({}),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const listForeshadowingsSummaryExecutor: ToolExecutorFn = async (_, state) => {
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const foreshadowings = novelId
    ? await prisma.foreshadowing.findMany({
        where: { novelId },
        orderBy: { createdAt: "desc" },
      })
    : (d.foreshadowings as Record<string, unknown>[]) || [];
  return JSON.stringify(foreshadowings.map(summarizeForeshadowing), null, 2);
};

export const GET_FORESHADOWING_DETAIL_DEF: ToolDefinition = {
  name: "get_foreshadowing_detail",
  description: "获取指定伏笔的完整详情。参数：foreshadowing_name（伏笔名称）",
  inputSchema: z.object({
    foreshadowing_name: z.string().min(1, "伏笔名称不能为空"),
  }),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const getForeshadowingDetailExecutor: ToolExecutorFn = async (args, state) => {
  const fsName = args.foreshadowing_name as string;
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const f = novelId
    ? await prisma.foreshadowing.findFirst({
        where: {
          novelId,
          name: { contains: fsName },
        },
      })
    : ((d.foreshadowings as Record<string, unknown>[]) || []).find(
        (f: Record<string, unknown>) =>
          (f.name as string).includes(fsName) || fsName.includes(f.name as string)
      );
  return f ? JSON.stringify(f, null, 2) : `未找到伏笔 "${fsName}"`;
};

// ============================================
// 章节工具
// ============================================

export const GET_RECENT_CHAPTERS_DEF: ToolDefinition = {
  name: "get_recent_chapters",
  description: "获取当前章节及前 N 章的内容摘要。参数：count（章数，默认 3，最大 5）、max_chars_per_chapter（每章最大字符数，默认 2000）",
  inputSchema: z.object({
    count: z.number().min(1).max(5).optional(),
    max_chars_per_chapter: z.number().min(500).max(12000).optional(),
  }),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const getRecentChaptersExecutor: ToolExecutorFn = async (args, state) => {
  const count = Math.min(Math.max(Number(args.count ?? 3) || 3, 1), 5);
  const maxCharsPerChapter = Math.min(Math.max(Number(args.max_chars_per_chapter ?? 2000) || 2000, 500), 12000);
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const chapterId = getChapterId(state);
  let selected: Array<{ id: string; title: string; order: number; content: string | null }> = [];

  if (novelId && chapterId) {
    const current = await prisma.chapter.findFirst({
      where: { id: chapterId, novelId },
      select: { order: true },
    });
    selected = await prisma.chapter.findMany({
      where: {
        novelId,
        ...(current ? { order: { lte: current.order } } : {}),
      },
      orderBy: { order: "desc" },
      take: count,
      select: { id: true, title: true, order: true, content: true },
    });
    selected.sort((a, b) => a.order - b.order);
  } else {
    const rawChapters = (d.chapters ?? []) as Record<string, unknown>[];
    const chapters = rawChapters
      .map((ch, index) => ({
        id: ch.id as string,
        title: ch.title as string,
        order: (ch.order as number) ?? index,
        content: ch.content as string | null,
      }))
      .sort((a, b) => a.order - b.order);

    const currentIndex = chapters.findIndex((ch) => ch.id === d.chapterId);
    const endIndex = currentIndex >= 0 ? currentIndex + 1 : chapters.length;
    const startIndex = Math.max(0, endIndex - count);
    selected = chapters.slice(startIndex, endIndex);
  }

  return JSON.stringify({
    count: selected.length,
    chapters: selected.map((ch) => ({
      id: ch.id,
      title: ch.title,
      order: ch.order,
      content: compactText(ch.content, maxCharsPerChapter),
    })),
    note: "只返回当前章节及其前若干章，用于阶段性设定维护；不要把短期描写直接覆盖长期设定。",
  }, null, 2);
};

// ============================================
// 注册
// ============================================

registerTool(LIST_OUTLINE_SUMMARY_DEF, listOutlineSummaryExecutor);
registerTool(GET_OUTLINE_NODE_DEF, getOutlineNodeExecutor);
registerTool(GET_PLOT_PROGRESS_DEF, getPlotProgressExecutor);
registerTool(LIST_FORESHADOWINGS_SUMMARY_DEF, listForeshadowingsSummaryExecutor);
registerTool(GET_FORESHADOWING_DETAIL_DEF, getForeshadowingDetailExecutor);
registerTool(GET_RECENT_CHAPTERS_DEF, getRecentChaptersExecutor);
