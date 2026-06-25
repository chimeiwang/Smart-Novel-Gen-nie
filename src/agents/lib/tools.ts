/**
 * Agent 工具执行辅助。
 *
 * @module agents/lib/tools
 * @description 工具定义、权限和 OpenAI schema 均由 `src/agents/tools/registry.ts` 管理。
 *  本文件只保留 AgentRuntime 需要的执行器和状态栏参数摘要。
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
