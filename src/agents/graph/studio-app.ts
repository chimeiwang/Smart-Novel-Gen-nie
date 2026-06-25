/**
 * LangGraph Studio 入口。
 *
 * 这个文件只负责把现有 NovelWriter LangGraph 应用暴露给
 * @langchain/langgraph-cli。业务执行仍复用 graph-definition.ts，
 * 不在 Studio 入口中新增平行编排流程。
 */

import { getGraph } from "./graph-definition";
import { initLangSmithForStudio } from "@/agents/lib/langsmith-studio-init";

void initLangSmithForStudio();

export const graph = getGraph();
