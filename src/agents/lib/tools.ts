/**
 * Agent 工具执行辅助。
 *
 * @module agents/lib/tools
 * @description 工具定义、权限和 OpenAI schema 均由 `src/agents/tools/registry.ts` 管理。
 *  本文件只保留 AgentRuntime 需要的执行器和状态栏摘要。
 */

import type { WritingState } from "../graph/state";
import { executeTool } from "@/agents/tools";

// 触发工具注册副作用。
import "@/agents/tools";

/** 工具执行器类型 */
export type ToolExecutor = (
  toolName: string,
  arguments_: Record<string, unknown>
) => Promise<string>;

/**
 * 为前端状态栏生成工具参数摘要。
 * 不返回完整参数或工具结果，避免设定库/章节上下文刷到聊天界面。
 */
export function summarizeToolArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args).filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (entries.length === 0) return "无参数";

  return entries
    .slice(0, 3)
    .map(([key, value]) => {
      const text = typeof value === "string" ? value : JSON.stringify(value);
      const shortText = text.length > 24 ? text.slice(0, 24) + "..." : text;
      return `${key}: ${shortText}`;
    })
    .join("，");
}

function parseJsonResult(result: string): unknown {
  try {
    return JSON.parse(result);
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function shortText(value: string, maxLength = 18): string {
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function summarizeNamedArray(items: unknown[], unit: string): string {
  const names = items
    .map((item) => isRecord(item) ? asString(item.name) || asString(item.title) : "")
    .filter(Boolean)
    .slice(0, 3);
  const suffix = names.length > 0 ? `：${names.map((name) => shortText(name, 12)).join("、")}${items.length > names.length ? "等" : ""}` : "";
  return `读取 ${items.length} 个${unit}${suffix}`;
}

/**
 * 为前端过程栏生成工具结果短摘要。
 * 只暴露“查到了什么”的概览，不把章节正文、设定正文或 reasoning 刷到聊天界面。
 */
export function summarizeToolResult(toolName: string, result: string): string {
  const parsed = parseJsonResult(result);
  if (!parsed) return "";

  if (toolName === "get_novel_info" && isRecord(parsed)) {
    const novelName = asString(parsed.novelName);
    const chapterTitle = asString(parsed.chapterTitle);
    if (novelName && chapterTitle) return `作品《${shortText(novelName, 20)}》 · 当前章《${shortText(chapterTitle, 20)}》`;
    if (novelName) return `作品《${shortText(novelName, 24)}》`;
  }

  if (toolName === "list_available_data" && isRecord(parsed)) {
    const labels: Array<[string, string]> = [
      ["characters", "角色"],
      ["factions", "势力"],
      ["locations", "地点"],
      ["items", "物品"],
      ["glossaries", "术语"],
      ["outlineNodes", "大纲"],
      ["foreshadowings", "伏笔"],
      ["references", "参考"],
    ];
    const parts = labels
      .map(([key, label]) => {
        const count = Number(parsed[key] ?? 0);
        return count > 0 ? `${label}${count}` : "";
      })
      .filter(Boolean);
    if (parsed.hasStyleProfile) parts.push("文风画像");
    return parts.length > 0 ? `可用资料：${parts.join("、")}` : "暂无可用资料";
  }

  if (toolName === "list_outline_summary" && isRecord(parsed)) {
    const nodes = Array.isArray(parsed.nodes) ? parsed.nodes : [];
    return `读取 ${nodes.length} 个大纲节点${asString(parsed.summary) ? "，含总纲" : ""}`;
  }

  if (toolName === "get_plot_progress" && isRecord(parsed)) {
    const stage = asString(parsed.currentStage);
    const goal = asString(parsed.currentGoal);
    if (stage && goal) return `剧情进度：${shortText(stage, 18)} · ${shortText(goal, 24)}`;
    if (stage) return `剧情进度：${shortText(stage, 24)}`;
  }

  if (toolName === "get_recent_chapters" && isRecord(parsed)) {
    const chapters = Array.isArray(parsed.chapters) ? parsed.chapters : [];
    return summarizeNamedArray(chapters, "章节");
  }

  if (Array.isArray(parsed)) {
    if (toolName === "list_characters_summary") return summarizeNamedArray(parsed, "角色");
    if (toolName === "list_foreshadowings_summary") return summarizeNamedArray(parsed, "伏笔");
    return `读取 ${parsed.length} 条结果`;
  }

  if (isRecord(parsed)) {
    const name = asString(parsed.name) || asString(parsed.title) || asString(parsed.novelName) || asString(parsed.chapterTitle);
    if (name) return `读取：${shortText(name, 28)}`;
  }

  return "";
}

/**
 * 创建工具执行器。
 *
 * 所有工具查找、Zod 入参校验、权限和 mutating 工具保护均由 registry 负责。
 */
export function createToolExecutor(state: WritingState): ToolExecutor {
  return async (toolName: string, args: Record<string, unknown>): Promise<string> => {
    return executeTool(
      toolName,
      args,
      {
        novelData: state.novelData as unknown as Record<string, unknown>,
        novelId: state.novelId,
        chapterId: state.chapterId,
        taskId: state.taskId,
        activeArtifactId: state.activeArtifactId ?? null,
      }
    );
  };
}
