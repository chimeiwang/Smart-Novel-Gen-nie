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
  description: "读取结构化大纲。写作/评审上下文固定返回当前章节路径与完整当前章节组；大纲编辑上下文返回整棵树的层级元数据，不截取节点正文。",
  inputSchema: z.object({
    scope: z.enum(["current_chapter", "tree_index"]).optional(),
    include_full_summary: z.boolean().optional(),
  }),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const listOutlineSummaryExecutor: ToolExecutorFn = async (args, state) => {
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const localizedContext = d.writingOutlineContext;
  if (localizedContext && typeof localizedContext === "object") {
    return JSON.stringify({
      scope: "current_chapter",
      outlineContext: localizedContext,
      note: "写作与评审任务只返回当前章节相关大纲；未来章节详情未被选入，不是字符截断。",
    }, null, 2);
  }
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
    scope: "tree_index",
    ...(includeFullSummary ? { summary: outline?.content ?? d.outlineSummary } : {}),
    summaryIncluded: includeFullSummary,
    nodes: nodes.map((node) => ({
      id: node.id,
      title: node.title,
      kind: node.kind,
      status: node.status,
      order: node.order,
      parentId: node.parentId,
      chapterStartOrder: node.chapterStartOrder,
      chapterEndOrder: node.chapterEndOrder,
    })),
  }, null, 2);
};

export const GET_OUTLINE_NODE_DEF: ToolDefinition = {
  name: "get_outline_node",
  description: "获取指定大纲节点完整内容。优先传 node_id；兼容 node_title，但标题匹配多条时会返回候选而不随机选择。",
  inputSchema: z.object({
    node_id: z.string().min(1).optional(),
    node_title: z.string().min(1).optional(),
  }).refine((value) => Boolean(value.node_id || value.node_title), {
    message: "node_id 或 node_title 至少提供一个",
  }),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const getOutlineNodeExecutor: ToolExecutorFn = async (args, state) => {
  const nodeId = args.node_id as string | undefined;
  const nodeTitle = args.node_title as string | undefined;
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const include = {
    parent: { select: { id: true, title: true, kind: true, chapterStartOrder: true, chapterEndOrder: true } },
    children: { orderBy: { order: "asc" as const } },
  };
  if (novelId && nodeId) {
    const node = await prisma.outlineNode.findFirst({ where: { id: nodeId, novelId }, include });
    return node ? JSON.stringify(node, null, 2) : `未找到大纲节点 "${nodeId}"`;
  }
  if (novelId && nodeTitle) {
    const matches = await prisma.outlineNode.findMany({
      where: { novelId, title: { contains: nodeTitle } },
      include,
      orderBy: [{ kind: "asc" }, { order: "asc" }],
    });
    if (matches.length > 1) {
      return JSON.stringify({
        error: "OUTLINE_NODE_AMBIGUOUS",
        message: `标题“${nodeTitle}”匹配到多个大纲节点，请改用 node_id。`,
        candidates: matches.map((node) => ({ id: node.id, title: node.title, kind: node.kind })),
      }, null, 2);
    }
    return matches[0] ? JSON.stringify(matches[0], null, 2) : `未找到大纲节点 "${nodeTitle}"`;
  }
  const matches = ((d.outlineNodes as Record<string, unknown>[]) || []).filter((node) =>
    nodeId ? node.id === nodeId : nodeTitle && String(node.title).includes(nodeTitle)
  );
  if (matches.length > 1) {
    return JSON.stringify({ error: "OUTLINE_NODE_AMBIGUOUS", candidates: matches.map((node) => ({ id: node.id, title: node.title })) }, null, 2);
  }
  const node = matches[0];
  return node
    ? JSON.stringify(node, null, 2)
    : `未找到大纲节点 "${nodeId ?? nodeTitle}"`;
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
  description: "获取目标章节之前 N 章的完整正文。参数 count 默认 3、最大 5；通过减少章节数量控制上下文，不截断已选择正文。",
  inputSchema: z.object({
    count: z.number().min(1).max(5).optional(),
  }),
  permission: readOnlyPermission("plot.read"),
  toolKind: "read",
};

export const getRecentChaptersExecutor: ToolExecutorFn = async (args, state) => {
  const count = Math.min(Math.max(Number(args.count ?? 3) || 3, 1), 5);
  const d = state.novelData as Record<string, unknown>;
  const novelId = getNovelId(state);
  const targetChapterOrder = typeof d.targetChapterOrder === "number" ? d.targetChapterOrder : undefined;
  const chapterId = getChapterId(state);
  let selected: Array<{ id: string; title: string; order: number; content: string | null }> = [];

  if (novelId && chapterId) {
    const current = targetChapterOrder === undefined
      ? await prisma.chapter.findFirst({ where: { id: chapterId, novelId }, select: { order: true } })
      : null;
    const boundaryOrder = targetChapterOrder ?? current?.order;
    selected = await prisma.chapter.findMany({
      where: {
        novelId,
        ...(boundaryOrder !== undefined ? { order: { lt: boundaryOrder } } : {}),
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
    if (targetChapterOrder !== undefined) {
      selected = chapters.filter((chapter) => chapter.order < targetChapterOrder).slice(-count);
    } else {
      const endIndex = currentIndex >= 0 ? currentIndex + 1 : chapters.length;
      const startIndex = Math.max(0, endIndex - count);
      selected = chapters.slice(startIndex, endIndex);
    }
  }

  return JSON.stringify({
    count: selected.length,
    chapters: selected.map((ch) => ({
      id: ch.id,
      title: ch.title,
      order: ch.order,
      content: ch.content ?? "",
    })),
    note: "只按目标章节位置选择最近章节；返回内容完整，未做字符裁剪。",
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
