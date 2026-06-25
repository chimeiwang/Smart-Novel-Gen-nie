/**
 * LangGraph Studio 专用 LangSmith 初始化。
 *
 * Studio 入口不会经过 Next.js API 路由的 initServer()，因此需要在图导出前
 * 显式初始化追踪器，确保本地 Studio 调试也能上报 trace。
 */

import { initLangSmithTracer } from "./langsmith-tracer";

export async function initLangSmithForStudio(): Promise<void> {
  await initLangSmithTracer();
}
