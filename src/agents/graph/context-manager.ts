/**
 * 对话上下文管理器
 *
 * @module agents/graph/context-manager
 * @description 支持对话历史共享、序列化存储、内存上限控制
 */

import { prisma } from "@/shared/db/prisma";
import type {
  WritingState,
  AgentMessage,
  AgentOutput,
  CoreAgentId,
  PendingAgentCall,
} from "./state";
import { AGENT_NAMES, generateMessageId } from "./state";
import { logger } from "@/shared/lib/logger";

// ============================================
// 常量配置
// ============================================

/** 对话历史最大条数（内存保护） */
const MAX_HISTORY_SIZE = 100;

/** 对话历史最大字符数（内存保护） */
const MAX_HISTORY_CHARS = 1_000_000;

/** 单条消息最大字符数 */
const MAX_MESSAGE_CHARS = 200_000;

// ============================================
// 内存边界控制
// ============================================

/**
 * 截断过长的消息内容
 */
function truncateMessage(content: string, maxChars: number = MAX_MESSAGE_CHARS): string {
  if (content.length <= maxChars) {
    return content;
  }
  return content.slice(0, maxChars) + `\n[...内容已截断，原长度 ${content.length} 字符]`;
}

/**
 * 截断过长的对话历史（保留最新消息，移除最旧消息）
 */
function truncateHistory(
  history: AgentMessage[],
  maxSize: number = MAX_HISTORY_SIZE
): AgentMessage[] {
  if (history.length <= maxSize) {
    return history;
  }
  // 保留最新的 maxSize 条消息
  return history.slice(-maxSize);
}

/**
 * 检查并压缩历史（如果超过字符数限制）
 */
function compressHistory(history: AgentMessage[]): AgentMessage[] {
  // 先检查总字符数
  let totalChars = 0;
  for (const msg of history) {
    totalChars += msg.content.length;
    if (msg.userMessage) {
      totalChars += msg.userMessage.length;
    }
  }

  // 如果超过限制，进行压缩
  if (totalChars > MAX_HISTORY_CHARS) {
    // 计算需要保留的比例
    const ratio = MAX_HISTORY_CHARS / totalChars;
    const targetChars = Math.floor(totalChars * ratio * 0.9); // 保留90%以留有余量

    let currentChars = 0;
    const compressed: AgentMessage[] = [];

    // 从最新开始保留
    for (let i = history.length - 1; i >= 0; i--) {
      const msg = history[i];
      const msgChars = msg.content.length + (msg.userMessage?.length ?? 0);

      if (currentChars + msgChars <= targetChars) {
        compressed.unshift(msg);
        currentChars += msgChars;
      } else {
        // 添加截断标记
        compressed.unshift({
          ...msg,
          content: msg.content.slice(0, Math.floor(msg.content.length * 0.5)) +
            `\n[历史压缩，此处省略 ${history.length - i} 条早期消息]`,
        });
        break;
      }
    }

    return compressed;
  }

  return history;
}

// ============================================
// 对话历史管理
// ============================================

/**
 * 添加用户消息到历史
 */
// @5.1
export function addUserMessage(
  state: WritingState,
  message: string
): WritingState {
  // 截断过长的消息
  const truncatedMessage = truncateMessage(message);

  const userMsg: AgentMessage = {
    id: generateMessageId(),
    agentId: "设定", // 用户没有agentId，用设定作为占位
    agentName: "用户",
    content: "",
    timestamp: Date.now(),
    userMessage: truncatedMessage,
  };

  // 添加消息并压缩历史
  let newHistory = [...state.conversationHistory, userMsg];
  newHistory = truncateHistory(newHistory);
  newHistory = compressHistory(newHistory);

  return {
    ...state,
    conversationHistory: newHistory,
  };
}

/**
 * 添加Agent输出到历史
 */
// @5.1
export function addAgentMessage(
  state: WritingState,
  output: AgentOutput,
  isCallMessage: boolean = false,
  callTarget?: CoreAgentId
): WritingState {
  // 截断过长的内容
  const truncatedContent = truncateMessage(output.content);

  const agentMsg: AgentMessage = {
    id: generateMessageId(),
    agentId: output.agentId,
    agentName: output.agentName,
    content: truncatedContent,
    timestamp: Date.now(),
    agentOutput: output,
    isCallMessage,
    callTarget: callTarget,
  };

  // 添加消息并压缩历史
  let newHistory = [...state.conversationHistory, agentMsg];
  newHistory = truncateHistory(newHistory);
  newHistory = compressHistory(newHistory);

  return {
    ...state,
    conversationHistory: newHistory,
  };
}

/**
 * 设置待处理的Agent调用
 */
export function setPendingAgentCall(
  state: WritingState,
  call: PendingAgentCall | null
): WritingState {
  return {
    ...state,
    pendingAgentCall: call,
  };
}

/**
 * 创建待处理的Agent调用
 */
export function createPendingAgentCall(
  fromAgent: CoreAgentId,
  toAgent: CoreAgentId,
  reason: string,
  options?: {
    specificQuestion?: string;
    contentToRewrite?: string;
  }
): PendingAgentCall {
  return {
    fromAgent,
    toAgent,
    reason,
    specificQuestion: options?.specificQuestion,
    contentToRewrite: options?.contentToRewrite,
    timestamp: Date.now(),
  };
}

// ============================================
// 上下文构建
// ============================================

/**
 * 构建带历史的提示词上下文
 * 用于给Agent提供完整的对话历史
 */
export function buildContextWithHistory(state: WritingState): string {
  const lines: string[] = [];

  lines.push("【对话历史】");
  lines.push("");

  if (state.conversationHistory.length === 0) {
    lines.push("(暂无历史记录)");
  } else {
    // 从最早到最新排列
    for (const msg of state.conversationHistory) {
      const time = new Date(msg.timestamp).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      });

      if (msg.userMessage) {
        // 用户消息
        lines.push(`[${time}] 用户: ${msg.userMessage}`);
      } else if (msg.agentOutput) {
        // Agent输出
        const prefix = msg.isCallMessage ? `[调用→${msg.callTarget}] ` : "";
        const MAX_DISPLAY = 50000;
        lines.push(`[${time}] ${msg.agentName}: ${prefix}${msg.content.slice(0, MAX_DISPLAY)}`);

        if (msg.content.length > MAX_DISPLAY) {
          lines.push(`    ... (内容过长已截断，全文 ${msg.content.length} 字符)`);
        }
      }
      lines.push("");
    }
  }

  return lines.join("\n");
}

/**
 * 构建简短的上下文摘要（用于日志和调试）
 */
export function buildContextSummary(state: WritingState): string {
  const count = state.conversationHistory.length;
  if (count === 0) {
    return "无历史";
  }

  const lastMsg = state.conversationHistory[state.conversationHistory.length - 1];
  const lastAgent = lastMsg?.agentName ?? "未知";
  const lastTime = lastMsg
    ? new Date(lastMsg.timestamp).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "未知";

  return `${count}条记录，最后: ${lastAgent}@${lastTime}`;
}

/**
 * 获取最近N条消息
 */
export function getRecentMessages(
  state: WritingState,
  count: number = 5
): AgentMessage[] {
  return state.conversationHistory.slice(-count);
}

// ============================================
// 持久化（数据库）
// ============================================

/**
 * 将对话历史序列化（用于存储到数据库）
 */
export function serializeHistory(history: AgentMessage[]): string {
  try {
    return JSON.stringify(history);
  } catch (error) {
    logger.error("CONTEXT", "序列化对话历史失败", { error: String(error) });
    // 返回空数组的序列化结果
    return "[]";
  }
}

/**
 * 将对话历史反序列化（从数据库恢复）
 */
export function deserializeHistory(serialized: string | null): AgentMessage[] {
  if (!serialized) {
    return [];
  }

  try {
    const parsed = JSON.parse(serialized);
    if (!Array.isArray(parsed)) {
      logger.warn("CONTEXT", "对话历史格式错误，非数组", { type: typeof parsed });
      return [];
    }

    // 验证每条消息的基本结构
    const validMessages: AgentMessage[] = [];
    for (const msg of parsed) {
      if (msg && typeof msg === "object" && typeof msg.id === "string" && typeof msg.content === "string") {
        validMessages.push(msg as AgentMessage);
      }
    }

    return validMessages;
  } catch (error) {
    logger.error("CONTEXT", "反序列化对话历史失败", { error: String(error) });
    return [];
  }
}

/**
 * 从数据库加载对话历史
 */
// @5.1
export async function loadHistoryFromDb(taskId: string): Promise<AgentMessage[]> {
  try {
    const task = await prisma.writingTask.findUnique({
      where: { id: taskId },
      select: { conversationHistory: true },
    });

    if (!task) {
      logger.warn("CONTEXT", "加载历史失败，任务不存在", { taskId });
      return [];
    }

    return deserializeHistory(task.conversationHistory);
  } catch (error) {
    logger.error("CONTEXT", "从数据库加载对话历史失败", { taskId, error: String(error) });
    return [];
  }
}

/**
 * 保存对话历史到数据库
 */
export async function saveHistoryToDb(
  taskId: string,
  history: AgentMessage[]
): Promise<boolean> {
  try {
    const serialized = serializeHistory(history);
    await prisma.writingTask.update({
      where: { id: taskId },
      data: { conversationHistory: serialized },
    });
    return true;
  } catch (error) {
    logger.error("CONTEXT", "保存对话历史到数据库失败", { taskId, error: String(error) });
    return false;
  }
}

/**
 * 清理过期的对话历史（定期调用）
 */
export async function cleanupOldHistory(novelId: string): Promise<number> {
  try {
    // 获取该小说的所有写作任务
    const tasks = await prisma.writingTask.findMany({
      where: { novelId },
      orderBy: { createdAt: "desc" },
      skip: 10, // 只保留最近10个任务的完整历史
    });

    let cleanedCount = 0;
    for (const task of tasks) {
      if (task.conversationHistory && task.conversationHistory.length > 10) {
        // 截断旧任务的历史
        await prisma.writingTask.update({
          where: { id: task.id },
          data: { conversationHistory: null }, // 释放空间
        });
        cleanedCount++;
      }
    }

    logger.info("CONTEXT", "清理过期对话历史", { novelId, cleanedCount });
    return cleanedCount;
  } catch (error) {
    logger.error("CONTEXT", "清理对话历史失败", { novelId, error: String(error) });
    return 0;
  }
}

// ============================================
// 状态初始化
// ============================================

/**
 * 创建空的对话历史
 */
export function createEmptyHistory(): AgentMessage[] {
  return [];
}

/**
 * 初始化状态中的对话历史
 */
export function initHistory(state: WritingState): WritingState {
  return {
    ...state,
    conversationHistory: createEmptyHistory(),
  };
}
