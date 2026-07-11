/**
 * LangGraph 运行时结构化 schema。
 *
 * @module agents/graph/schemas
 * @description 仅保留服务端内部结构化输出，例如意图分类。
 *  Agent 正文不再使用 JSON 信封 schema；可见输出是段落文本，控制信息走 tool_calls。
 */

import { z } from "zod";
import { CoreAgentIdSchema } from "@/shared/contracts/agent";
import { CreativeOperationSchema } from "@/shared/contracts/creative-operation";

/**
 * 意图分类输出 Schema。
 *
 * 用于 router 的内部 LLM 分类，不是 Agent 回复协议。
 */
export const IntentClassificationSchema = z.object({
  targetAgent: CoreAgentIdSchema.nullable(),
  operation: CreativeOperationSchema.nullable().optional(),
  action: z.enum([
    "call_agent",
    "discuss",
    "generate",
    "check",
    "review",
    "status",
    "unknown",
  ]),
  confidence: z.number().min(0).max(1),
  reasoning: z.string(),
  suggestedAgent: CoreAgentIdSchema.optional(),
});
