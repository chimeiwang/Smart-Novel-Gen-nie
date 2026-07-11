/**
 * 参考资料 RAG 只读工具。
 *
 * @module agents/tools/read/reference-tools
 */

import { z } from "zod";
import type { ToolDefinition, ToolExecutorFn } from "../registry";
import { registerTool } from "../registry";
import { readOnlyPermission } from "../permissions";
import { semanticSearchReferenceChunks } from "@/shared/lib/rag-service";

function getNovelId(state: Parameters<ToolExecutorFn>[1]): string {
  return state.novelId || String((state.novelData as Record<string, unknown>).novelId ?? "");
}

export const SEMANTIC_SEARCH_REFERENCES_DEF: ToolDefinition = {
  name: "semantic_search_references",
  description: "按语义召回当前小说已上传参考资料片段。参数：query（查询文本）、topK（返回片段数，默认 5，最大 20）。",
  inputSchema: z.object({
    query: z.string().min(1, "查询文本不能为空"),
    topK: z.number().int().min(1).max(20).optional(),
  }),
  permission: readOnlyPermission("lore.read"),
  toolKind: "read",
};

export const semanticSearchReferencesExecutor: ToolExecutorFn = async (args, state) => {
  const novelId = getNovelId(state);
  if (!novelId) {
    return JSON.stringify({
      error: "NOVEL_ID_REQUIRED",
      message: "语义召回参考资料需要当前小说 ID。",
    }, null, 2);
  }

  const result = await semanticSearchReferenceChunks({
    novelId,
    query: args.query as string,
    topK: args.topK as number | undefined,
  });

  if (!result.enabled) {
    return JSON.stringify({
      enabled: false,
      message: result.error ?? "RAG 索引未启用。",
      results: [],
    }, null, 2);
  }

  return JSON.stringify({
    enabled: true,
    count: result.results.length,
    results: result.results,
    note: "结果来自当前小说参考资料 RAG chunk；如需写入正式设定或正文，仍需走待审核草案或正文草案流程。",
  }, null, 2);
};

registerTool(SEMANTIC_SEARCH_REFERENCES_DEF, semanticSearchReferencesExecutor);
