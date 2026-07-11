/**
 * 服务端初始化模块
 *
 * @module shared/lib/server-init
 * @description 在服务端首次启动时初始化全局处理器
 */

import { setupGlobalErrorHandlers } from "./monitoring";
import { initLangSmithTracer } from "@/agents/lib/langsmith-tracer";
import { logger } from "./logger";

// 标记是否已初始化
let initialized = false;

/**
 * 初始化服务端
 *
 * 在 Next.js 服务端首次导入时调用
 */
export async function initServer(): Promise<void> {
  if (initialized) return;

  // 设置全局错误处理器
  setupGlobalErrorHandlers();

  // 初始化 LangSmith 追踪器
  await initLangSmithTracer();

  // 记录启动信息
  logger.info("SYSTEM", "========== 服务端启动 ==========", {
    pid: process.pid,
    nodeVersion: process.version,
    platform: process.platform,
    cwd: process.cwd(),
  });

  // 记录初始内存状态
  const mem = process.memoryUsage();
  logger.info("SYSTEM", "初始内存状态", {
    heapUsedMB: Math.round(mem.heapUsed / 1024 / 1024 * 100) / 100,
    heapTotalMB: Math.round(mem.heapTotal / 1024 / 1024 * 100) / 100,
    rssMB: Math.round(mem.rss / 1024 / 1024 * 100) / 100,
  });

  initialized = true;
}

// 导出便捷访问
export { logger, logger as localLogger } from "./logger";
export {
  logger as log,
  logError,
  logInfo,
  logWarn,
  logDebug,
} from "./logger";
export {
  trackSSEStart,
  trackSSEEvent,
  trackSSEEnd,
  trackSSEError,
  logAgentStart,
  logAgentEnd,
  logAgentError,
  logDbOperation,
  printMemorySnapshot,
  getMemoryStatus,
  checkMemoryLeak,
  setupGlobalErrorHandlers,
} from "./monitoring";
