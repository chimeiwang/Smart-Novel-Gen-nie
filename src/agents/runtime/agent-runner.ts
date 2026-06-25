/**
 * Agent 执行引擎
 *
 * @module agents/runtime/agent-runner
 * @description Phase 4 核心：统一封装 Agent 执行管道。
 *  消除 5 个 Agent node 中重复的 ~200 行模板代码。
 *
 * 执行管道：
 *   1. sendStatus 设置
 *   2. preGuard 预检 → skip 则返回早期结果
 *   3. buildMessages 构建 LLM 消息
 *   4. createToolExecutor + registry 工具链
 *   5. AgentRuntime 执行段落文本 + tool_calls
 *   6. 日志 + 返回 state partial
 *
 * @phase Phase 4 — AgentDefinition + AgentRunner
 */

import type { AgentOutput, CoreAgentId, WritingState, AgentControlEvent } from "../graph/state";
import { createAgentOutput } from "../graph/state";
import { createToolExecutor, summarizeToolArgs } from "@/agents/lib/tools";
import { getToolsByCapabilities, getOpenAITools, type ToolDefinition } from "@/agents/tools/registry";
import { logger } from "@/shared/lib/logger";
import { AGENT_UPDATE_CHANNEL_RULES_PROMPT } from "@/shared/contracts/agent-update-channels";
import type { AgentDefinition } from "./agent-definition";
import { AgentRuntimeImpl } from "./agent-runtime";

// ============================================
// 新模式的 system prompt 附录（Phase 2）
// ============================================

/**
 * 追加到新模式下 system prompt 的指令。
 * 替换原有的「输出 JSON 对象」要求。
 */
const NEW_MODE_SYSTEM_APPENDIX = `
## 输出规则（重要）

你不是 JSON 输出机。你是专业创作助手。

- 你的正文回复必须是自然段文本，直接写给用户看。
- 不要使用标题标记、表格、代码块、引用块、加粗标记或列表符号来组织格式。
- 可以用普通自然段、短句分行、中文编号（例如“一、”“1.”）组织内容；这些符号只作为普通文本，不依赖前端格式转换。
- 不要在正文外用 JSON 包裹，不要输出 \`{"content": "..."}\` 这种结构。
- 需要调用其他 Agent 时，使用 route_to_agent 工具。
- 如果你判断自己的能力不足以完成当前任务，或任务主责可能属于另一个 Agent，先调用 get_agent_capability_cards 阅读角色能力卡，再决定是否调用 route_to_agent；不要静默转交。
- 需要提交质量评分时，使用 submit_quality_report 工具。
- 结构化大纲必须最终生成 outlineContent 和/或 outlineAdjustments；不要用 begin_artifact_output 替代结构化大纲节点树。
${AGENT_UPDATE_CHANNEL_RULES_PROMPT}
- 只有纯文本长文草稿才使用 begin_artifact_output，例如小说正文草案、纯文本大纲草稿、设定草案、返工稿、Beat Plan 正文。调用时提交短元数据，并把产物正文放在本轮 assistant 正文里；不要把长文本塞进工具 JSON 参数。
- 长文本产物正文必须用独立行 ARTIFACT_OUTPUT_START 和 ARTIFACT_OUTPUT_END 包住。只有这两个标记之间的文本会进入待审核草案；标记外可以写给用户看的说明，但不会入库。标记内只能放需要入库的纯正文，不要写“以下是草案”“以上草稿已提交”等说明性头尾。
- 需要提交 Beat Plan 时，使用 submit_beat_plan 工具。
- 需要提交校验结果时，使用 submit_validation_report 工具。
- 查询数据时，使用读工具。

示例：如果你想告诉用户“第一章大纲建议增加一个冲突节点”，直接写正文文本：

第一章大纲建议

建议在第一章中段增加一个冲突节点。

不要用 JSON 包起来。`;

/**
 * 将旧模式 system prompt 转换为新模式兼容。
 * 删除「输出格式（必须严格遵守）」开始的 JSON 输出指令，
 * 替换为段落文本 + tool 使用指引。
 */
function adaptSystemPromptForNewMode(messages: { role: string; content?: unknown }[]): void {
  const msg = messages.find((m) => m.role === "system" && typeof m.content === "string");
  if (!msg || typeof msg.content !== "string") {
    return;
  }

  let content = msg.content;

  // 删除 JSON 输出格式段落（从「## 输出格式」到文末）
  const jsonSectionIndex = content.search(/##\s*输出格式/);
  if (jsonSectionIndex >= 0) {
    content = content.slice(0, jsonSectionIndex).trimEnd();
  }

  if (!content.includes("## 输出规则（重要）")) {
    content += "\n\n" + NEW_MODE_SYSTEM_APPENDIX;
  }

  msg.content = content;
}

function isToolAllowedForAgent(tool: ToolDefinition, agentId: CoreAgentId): boolean {
  return !tool.permission.agentIds || tool.permission.agentIds.includes(agentId);
}

export function getToolNamesForAgent(definition: Pick<AgentDefinition, "id" | "toolCapabilities">): string[] {
  return Array.from(
    getToolsByCapabilities([...definition.toolCapabilities, "agent.card.read"])
  )
    .filter((tool) => isToolAllowedForAgent(tool, definition.id))
    .map((tool) => tool.name);
}

// ============================================
// runAgent — 统一执行入口
// ============================================

/**
 * 统一 Agent 执行函数
 *
 * 替代原来 5 个 Agent node 中的重复模板代码。
 * 每个 Agent 只需提供 AgentDefinition 配置即可。
 *
 * @param definition - Agent 声明式定义
 * @param state - 当前 WritingState
 * @returns Partial<WritingState> — 包含 Agent 输出和活跃 Agent ID
 */
export async function runAgent(
  definition: AgentDefinition,
  state: WritingState
): Promise<Partial<WritingState>> {
  const agentId: CoreAgentId = definition.id;

  logger.info(definition.logTag, `${definition.name}开始执行`, { taskId: state.taskId });

  // ---- 1. sendStatus 辅助 ----
  const sendStatus = (status: string, data: Record<string, unknown> = {}) => {
    const callback = state.eventCallbacks?.[agentId];
    if (callback) {
      callback("agent_status", { agentId, status, ...data });
    }
  };

  try {
    // ---- 2. preGuard 预检 ----
    if (definition.preGuard) {
      const guard = definition.preGuard(state);
      if (guard?.skip) {
        const output = createAgentOutput(
          agentId,
          guard.skipMessage ?? "当前条件不满足，跳过执行。"
        );
        const skipResult: Partial<WritingState> = {
          [definition.outputField]: output,
          activeAgent: agentId,
          ...guard.skipOutput,
        };
        return skipResult;
      }
    }

    // ---- 3. 状态通知：理解中 ----
    const msgs = definition.statusMessages ?? {};
    sendStatus("understanding", { message: msgs.understanding ?? "正在理解您的请求..." });

    // ---- 4. 构建消息 ----
    const messages = definition.buildMessages(state);

    // ---- 5. 单协议主路径：段落文本 + control tools ----
    return runAgentInNewMode(
      definition, state, agentId, messages,
      sendStatus
    );

  } catch (error) {
    // ---- 错误处理 ----
    const errorMsg = error instanceof Error ? error.message : "未知错误";
    logger.error(definition.logTag, `${definition.name}执行失败`, {
      taskId: state.taskId,
      error: errorMsg,
    });

    return {
      [definition.outputField]: createAgentOutput(
        agentId,
        `${definition.name}时发生错误：${errorMsg}`
      ),
      activeAgent: agentId,
      errorMessage: errorMsg,
    };
  }
}

// ============================================
// runAgentInNewMode — paragraph_text_with_control_tools 路径
// ============================================

/**
 * 新模式执行：段落文本直接输出 + control tools。
 *
 * 与旧模式的核心差异：
 * - 使用 AgentRuntimeImpl 拦截 control tools → AgentControlEvent
 * - 流式 chunk 直接透传给前端
 * - AgentOutput 仅由 visibleContent 构建
 */
async function runAgentInNewMode(
  definition: AgentDefinition,
  state: WritingState,
  agentId: CoreAgentId,
  messages: { role: string; content?: unknown }[],
  sendStatus: (status: string, data: Record<string, unknown>) => void
): Promise<Partial<WritingState>> {
  const startTime = Date.now();
  logger.info(definition.logTag, `${definition.name}开始执行（新模式）`, { taskId: state.taskId });

  try {
    // ---- 1. 适配 system prompt：删除 JSON 输出要求，追加工具使用指引 ----
    adaptSystemPromptForNewMode(messages as { role: string; content?: unknown }[]);

    // ---- 2. 工具链：按 Agent capability 暴露 read/proposal/control 工具 ----
    const toolExecutor = createToolExecutor(state);
    const toolNames = getToolNamesForAgent(definition);
    const tools = getOpenAITools(toolNames);

    const msgs = definition.statusMessages ?? {};
    let hasStartedResponding = false;

    // ---- 3. 使用 AgentRuntimeImpl 执行 ----
    const runtime = new AgentRuntimeImpl();
    const turnResult = await runtime.runTurn({
      messages: messages as unknown as import("openai").OpenAI.Chat.ChatCompletionMessageParam[],
      tools,
      toolExecutor,
      maxIterations: definition.maxIterations ?? 10,
      onChunk: (chunk) => {
        if (!hasStartedResponding) {
          sendStatus("responding", { message: msgs.responding ?? "正在生成回复..." });
          hasStartedResponding = true;
        }
        // 直接透传 chunk（不经过 JSON 字段提取）
        state.streamCallbacks?.[agentId]?.(chunk);
      },
      onToolCall: (toolName, args) => {
        sendStatus("querying", {
          message: msgs.querying ?? `正在调用工具: ${toolName}`,
          toolName,
          argsSummary: summarizeToolArgs(args),
          detailsHidden: true,
        });
      },
      metadata: {
        callType: `${definition.name}(new)`,
        agentId,
        userId: state.userId,
        novelId: state.novelId,
      },
    });

    // ---- 4. 状态通知：整理中 ----
    sendStatus("parsing", { message: msgs.parsing ?? "正在整理结果..." });

    // ---- 5. 构建 AgentOutput（段落文本，不解析 JSON） ----
    const output: AgentOutput = createAgentOutput(agentId, turnResult.visibleContent);

    // ---- 6. 处理 postProcess 钩子 ----
    let postResult: Partial<WritingState> = {};
    if (definition.postProcess) {
      postResult = await definition.postProcess(output, state);
    }

    // ---- 7. 日志 ----
    logger.info(definition.logTag, `${definition.name}执行完成（新模式）`, {
      taskId: state.taskId,
      durationMs: Date.now() - startTime,
      contentLength: turnResult.visibleContent.length,
      controlEventCount: turnResult.controlEvents.length,
      controlEventTypes: turnResult.controlEvents.map((e) => e.type),
      toolCallCount: turnResult.toolCalls.length,
    });

    // ---- 8. 返回状态（含 controlEvents） ----
    const baseResult: Partial<WritingState> = {
      [definition.outputField]: output,
      activeAgent: agentId,
      controlEvents: turnResult.controlEvents as AgentControlEvent[],
    };

    return { ...baseResult, ...postResult };

  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : "未知错误";
    logger.error(definition.logTag, `${definition.name}执行失败（新模式）`, {
      taskId: state.taskId,
      error: errorMsg,
    });

    return {
      [definition.outputField]: createAgentOutput(
        agentId,
        `${definition.name}时发生错误：${errorMsg}`
      ),
      activeAgent: agentId,
      errorMessage: errorMsg,
    };
  }
}
