/**
 * 创作操作路由器。
 *
 * 聊天入口先识别用户要做的创作操作，再由操作定义决定执行视角。
 */

import { callLLMStructured } from "@/agents/lib/llm-wrapper";
import { logger } from "@/shared/lib/logger";
import type { CoreAgentId } from "@/shared/contracts/agent";
import {
  createFallbackOperation,
  getDefaultOperationForAgent,
  getCreativeOperationLabel,
  type CreativeOperation,
} from "@/shared/contracts/creative-operation";
import { buildIntentClassifierSystemPrompt } from "@/shared/contracts/agent-capabilities";
import { IntentClassificationSchema } from "@/agents/graph/schemas";
import { getOperationDefinition } from "./operation-definition";

export interface OperationRouteResult {
  operation: CreativeOperation;
  usedCommand: boolean;
  reasoning: string;
}

const AGENT_COMMAND_ALIASES: Record<string, CoreAgentId> = {
  "设定": "设定",
  "设定顾问": "设定",
  "剧情": "剧情",
  "剧情顾问": "剧情",
  "写作": "写作",
  "作家": "写作",
  "校验": "校验",
  "校验员": "校验",
  "编辑": "编辑",
  "网文编辑": "编辑",
  "编辑顾问": "编辑",
};

export function parseAgentCommand(message: string): CoreAgentId | null {
  const match = message.match(/@([\u4e00-\u9fa5A-Za-z0-9_-]+)/);
  if (!match) return null;
  return AGENT_COMMAND_ALIASES[match[1]] ?? null;
}

export async function routeCreativeOperation(input: {
  userMessage: string;
  userId?: string;
  novelId?: string;
}): Promise<OperationRouteResult> {
  const message = input.userMessage.trim();
  const commandAgent = parseAgentCommand(message);
  if (commandAgent) {
    const operation = normalizeOperation(getDefaultOperationForAgent(commandAgent, input.userMessage));
    return {
      operation,
      usedCommand: true,
      reasoning: `用户点名${commandAgent}，已映射为${getCreativeOperationLabel(operation.kind)}。`,
    };
  }

  if (!message) {
    const operation = normalizeOperation(createFallbackOperation(input.userMessage));
    return { operation, usedCommand: false, reasoning: "用户输入为空，进入回答问题。" };
  }

  try {
    const { data } = await callLLMStructured(IntentClassificationSchema, {
      prompt: `用户消息：${input.userMessage}`,
      systemPrompt: buildIntentClassifierSystemPrompt(),
      metadata: { callType: "创作操作识别", userId: input.userId, novelId: input.novelId },
    });
    const operation = normalizeOperation(
      data.operation ??
      (data.targetAgent
        ? getDefaultOperationForAgent(data.targetAgent, input.userMessage, data.confidence, data.reasoning)
        : createFallbackOperation(input.userMessage))
    );
    return {
      operation,
      usedCommand: false,
      reasoning: data.reasoning || `已识别为${getCreativeOperationLabel(operation.kind)}。`,
    };
  } catch (error) {
    logger.warn("OPERATION_ROUTER", "创作操作识别失败，回退为回答问题", { error: String(error) });
    const operation = normalizeOperation(createFallbackOperation(input.userMessage));
    return { operation, usedCommand: false, reasoning: "识别失败，回退为回答问题。" };
  }
}

function normalizeOperation(operation: CreativeOperation): CreativeOperation {
  const def = getOperationDefinition(operation.kind);
  return {
    ...operation,
    targetType: operation.targetType === "unknown" ? def.targetType : operation.targetType,
    primaryAgent: def.primaryAgent,
    reviewers: def.reviewers,
    outputKind: def.outputKind,
    requiresArtifact: def.requiresArtifact,
    requiresUserApproval: def.requiresUserApproval,
    reasoning: operation.reasoning || def.executionBrief,
  };
}
