/**
 * 全局错误处理和请求监控
 *
 * @module shared/lib/monitoring
 * @description 全局异常捕获、内存监控、SSE 生命周期追踪
 */

import { logger } from "./logger";
import type { AgentUpdates } from "@/agents/types";

/** SSE 任务状态追踪 */
interface SSETaskTracker {
  taskId: string;
  startTime: number;
  phase: string;
  eventCount: number;
  lastEventTime: number;
  error?: string;
}

/** SSE 任务追踪器（内存中） */
const sseTasks = new Map<string, SSETaskTracker>();

/**
 * 追踪新的 SSE 任务
 */
export function trackSSEStart(
  taskId: string,
  initialPhase: string
): void {
  const tracker: SSETaskTracker = {
    taskId,
    startTime: Date.now(),
    phase: initialPhase,
    eventCount: 0,
    lastEventTime: Date.now(),
  };

  sseTasks.set(taskId, tracker);
}

/**
 * 记录 SSE 事件（仅更新内存中的 tracker，不打印日志）
 */
export function trackSSEEvent(
  taskId: string,
  eventType: string,
  data?: Record<string, unknown>
): void {
  const tracker = sseTasks.get(taskId);
  if (tracker) {
    tracker.eventCount++;
    tracker.lastEventTime = Date.now();

    if (eventType === "phase_change") {
      tracker.phase = String(data?.phase || "unknown");
    }
  }
}

/**
 * 追踪 SSE 任务完成
 */
export function trackSSEEnd(
  taskId: string,
  reason: "completed" | "error" | "cancelled" | "timeout"
): void {
  const tracker = sseTasks.get(taskId);
  if (tracker) {
    const duration = Date.now() - tracker.startTime;
    const idleTime = Date.now() - tracker.lastEventTime;

    // 如果任务完成但最后活动时间过长，记录警告
    if (idleTime > 60000 && reason !== "completed") {
      logger.warn("SSE", `SSE任务${taskId}长时间无活动但未正常结束`, {
        idleTimeMs: idleTime,
        eventCount: tracker.eventCount,
      });
    } else if (reason === "completed") {
      // 正常完成时记录开始时间和耗时
      logger.info("SSE", `SSE连接结束: ${reason}`, {
        taskId,
        eventCount: tracker.eventCount,
        durationMs: duration,
        startTime: new Date(tracker.startTime).toISOString(),
      });
    } else {
      // 其他原因结束时也记录
      logger.warn("SSE", `SSE连接结束: ${reason}`, {
        taskId,
        eventCount: tracker.eventCount,
        durationMs: duration,
        startTime: new Date(tracker.startTime).toISOString(),
      });
    }

    sseTasks.delete(taskId);
  }
}

/**
 * 追踪 SSE 错误
 */
export function trackSSEError(taskId: string, error: unknown): void {
  const tracker = sseTasks.get(taskId);
  if (tracker) {
    tracker.error = error instanceof Error ? error.message : String(error);
  }

  logger.sseError(taskId, error);
}

/**
 * 获取当前所有活跃的 SSE 任务状态
 */
export function getActiveSSETasks(): Array<{
  taskId: string;
  durationMs: number;
  phase: string;
  eventCount: number;
  lastEventAgo: number;
}> {
  const now = Date.now();
  const active: Array<{
    taskId: string;
    durationMs: number;
    phase: string;
    eventCount: number;
    lastEventAgo: number;
  }> = [];

  sseTasks.forEach((tracker) => {
    active.push({
      taskId: tracker.taskId,
      durationMs: now - tracker.startTime,
      phase: tracker.phase,
      eventCount: tracker.eventCount,
      lastEventAgo: now - tracker.lastEventTime,
    });
  });

  return active;
}

/**
 * 记录 Agent 执行
 */
export function logAgentStart(agentId: string, taskId: string): void {
  logger.info("AGENT", `Agent开始: ${agentId}`, { taskId });
}

export function logAgentEnd(
  agentId: string,
  taskId: string,
  success: boolean,
  outputLength?: number
): void {
  const msg = success
    ? `Agent完成: ${agentId}`
    : `Agent失败: ${agentId}`;
  logger.info("AGENT", msg, { taskId, outputLength });
}

export function logAgentError(agentId: string, taskId: string, error: unknown): void {
  logger.error("AGENT", `Agent错误: ${agentId}`, { taskId, error: error instanceof Error ? error.message : String(error) });
}

/**
 * 记录数据库操作
 */
export function logDbOperation(
  operation: string,
  table: string,
  durationMs: number,
  success: boolean,
  details?: Record<string, unknown>
): void {
  const level = success ? "INFO" : "ERROR";
  const msg = `${operation} ${table}`;
  if (durationMs > 1000) {
    logger.warn("DB", `慢查询: ${msg} (${durationMs}ms)`, details);
  } else {
    if (success) {
      logger.debug("DB", msg, { durationMs, ...details });
    } else {
      logger.error("DB", `${msg}失败`, { durationMs, ...details });
    }
  }
}

/**
 * 记录内存密集型操作
 */
export function logMemoryHeavyOperation(
  operation: string,
  context: Record<string, unknown>,
  beforeMem: { heapUsed: number; rss: number },
  afterMem: { heapUsed: number; rss: number }
): void {
  const heapDiff = afterMem.heapUsed - beforeMem.heapUsed;
  const rssDiff = afterMem.rss - beforeMem.rss;

  const diff = {
    heapUsedMB: Math.round(heapDiff / 1024 / 1024 * 100) / 100,
    rssMB: Math.round(rssDiff / 1024 / 1024 * 100) / 100,
  };

  if (Math.abs(diff.heapUsedMB) > 10 || Math.abs(diff.rssMB) > 10) {
    logger.warn("MEMORY", `内存大幅变化: ${operation}`, {
      ...context,
      ...diff,
    });
  } else {
    logger.debug("MEMORY", `操作: ${operation}`, { ...context, ...diff });
  }
}

/**
 * 获取当前内存状态摘要
 */
export function getMemoryStatus(): {
  heapUsed: number;
  heapTotal: number;
  rss: number;
  external: number;
  activeSseTasks: number;
} {
  const mem = process.memoryUsage();
  return {
    heapUsed: mem.heapUsed,
    heapTotal: mem.heapTotal,
    rss: mem.rss,
    external: mem.external,
    activeSseTasks: sseTasks.size,
  };
}

/**
 * 打印内存状态到日志
 */
export function printMemorySnapshot(label?: string): void {
  logger.memorySnapshot("SYSTEM", label);
  logger.info("SYSTEM", "活跃SSE任务", { count: sseTasks.size, tasks: getActiveSSETasks() });
}

/**
 * 检查是否有内存泄漏迹象
 *
 * 内存泄漏的常见迹象：
 * 1. RSS 持续增长
 * 2. Heap Used 不断增长且不回落
 * 3. SSE 任务未正确清理
 */
export function checkMemoryLeak(): {
  isHealthy: boolean;
  warnings: string[];
  memory: ReturnType<typeof getMemoryStatus>;
} {
  const mem = getMemoryStatus();
  const warnings: string[] = [];

  // 检查 RSS 是否过大（超过 2GB）
  const rssGB = mem.rss / 1024 / 1024 / 1024;
  if (rssGB > 2) {
    warnings.push(`RSS过高: ${rssGB.toFixed(2)}GB`);
  }

  // 检查 Heap 使用率（如果 heapTotal 接近系统限制）
  const heapUsageRatio = mem.heapUsed / mem.heapTotal;
  if (heapUsageRatio > 0.9) {
    warnings.push(`堆内存使用率过高: ${(heapUsageRatio * 100).toFixed(1)}%`);
  }

  // 检查是否有僵尸 SSE 任务
  const activeTasks = getActiveSSETasks();
  const staleTasks = activeTasks.filter((t) => t.lastEventAgo > 300000); // 5分钟无活动
  if (staleTasks.length > 0) {
    warnings.push(`${staleTasks.length}个SSE任务疑似僵尸 (超过5分钟无活动)`);
  }

  // 检查是否有 SSE 任务泄漏
  if (activeTasks.length > 10) {
    warnings.push(`活跃SSE任务过多: ${activeTasks.length}`);
  }

  return {
    isHealthy: warnings.length === 0,
    warnings,
    memory: mem,
  };
}

/**
 * 设置全局错误处理器
 *
 * 在 Next.js 服务器启动时调用一次
 */
export function setupGlobalErrorHandlers(): void {
  // 未捕获的异常
  process.on("uncaughtException", (error) => {
    logger.uncaughtException(error);
  });

  // 未处理的 Promise 拒绝
  process.on("unhandledRejection", (reason) => {
    logger.unhandledRejection(reason);
  });

  // 定期检查内存（每5分钟）
  setInterval(() => {
    const health = checkMemoryLeak();
    if (!health.isHealthy) {
      logger.warn("MEMORY", "内存健康检查发现问题", {
        warnings: health.warnings,
        memory: health.memory,
      });
    }
    printMemorySnapshot("定期检查");
  }, 5 * 60 * 1000);

  // 定期清理旧日志（每天）
  setInterval(() => {
    const deleted = logger.cleanOldLogs(7);
    if (deleted > 0) {
      logger.info("SYSTEM", `清理了${deleted}个旧日志文件`);
    }
  }, 24 * 60 * 60 * 1000);

  logger.info("SYSTEM", "全局错误处理器已设置");
}

/**
 * API 请求日志中间件（简化版，用于日志记录）
 */
export function logAPIRequest(
  method: string,
  path: string,
  durationMs: number,
  status: number,
  taskId?: string
): void {
  const level = status >= 500 ? "ERROR" : status >= 400 ? "WARN" : "INFO";
  const msg = `${method} ${path} ${status} (${durationMs}ms)`;

  if (level === "ERROR") {
    logger.error("API", msg, { taskId, status, durationMs });
  } else if (level === "WARN") {
    logger.warn("API", msg, { taskId, status, durationMs });
  } else {
    logger.debug("API", msg, { taskId, status, durationMs });
  }
}
