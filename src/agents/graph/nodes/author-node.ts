/**
 * 作家 Agent（Phase 4 重构 + Phase 7 新协议迁移）
 *
 * @module agents/graph/nodes/author-node
 * @description 专注于小说正文创作：查询设定 → 写作 → 自检 → 可选校验。
 *
 * ## Phase 4 重构
 * - 删除 ~140 行模板代码
 * - AgentRunner 统一封装执行管道
 * - 保留作家特有的后处理（正文提取、草案准备、校验触发检测）
 *
 * ## Phase 7 迁移（Agent Runtime 协议重构）
 * - outputMode: "paragraph_text_with_control_tools"
 * - 正文直接输出段落文本（不经过 generatedContent JSON 字段）
 * - route_to_agent 替代 wantsToCall
 * - 后处理简化：不需要 JSON 字段提取
 */

import type { OpenAI } from "openai";
import type { WritingState, AgentOutput, CoreAgentId } from "../state";
import { AGENT_NAMES } from "../state";
import { buildActiveTaskContext, buildSummaryIndex, buildConversationHistoryText } from "../context-builder";
import { SELF_CHECK_PROMPT, WRITING_SELF_CHECK_PROMPT } from "../self-check-prompt";
import type { AgentDefinition } from "@/agents/runtime/agent-definition";
import { runAgent } from "@/agents/runtime/agent-runner";

const AGENT_ID: CoreAgentId = "写作";
const VALIDATOR_ID: CoreAgentId = "校验";

/**
 * 作家 Agent 定义
 */
const authorDefinition: AgentDefinition = {
  id: AGENT_ID,
  name: AGENT_NAMES[AGENT_ID],
  outputField: "writerOutput",
  logTag: "AUTHOR",

  // Phase 7：新协议模式
  outputMode: "paragraph_text_with_control_tools",

  toolCapabilities: ["novel.read", "character.read", "lore.read", "plot.read", "chapter.read", "style.read", "control.artifact", "control.route"],

  /** 作家后处理：正文只进入工作流草案，不直接写入正式章节正文 */
  postProcess: async (writerOutput, state) => {
    const newGeneratedContent = extractContentNewMode(writerOutput.content);
    const shouldPersist = shouldPersistAsChapterContent(state, newGeneratedContent);
    return {
      generatedContent: state.operationMode === "operation_graph"
        ? state.generatedContent
        : shouldPersist ? newGeneratedContent : state.generatedContent,
    };
  },

  statusMessages: {
    understanding: "正在读取章节、大纲和设定索引...",
    thinking: "正在分析写作场景，准备查询相关设定...",
    responding: "正在创作正文...",
    parsing: "正在整理正文...",
  },

  buildMessages: (state) => {
    const { userMessage, novelData, conversationHistory, generatedContent, validatorOutput, pendingAgentCall } = state;
    const rewriteRequest = checkRewriteRequest(validatorOutput, pendingAgentCall);
    const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [];

    messages.push({ role: "system", content: buildSystemPrompt() });
    messages.push({ role: "system", content: SELF_CHECK_PROMPT + "\n" + WRITING_SELF_CHECK_PROMPT });

    // 摘要索引
    const summaryIndex = buildSummaryIndex(novelData);
    if (summaryIndex) {
      messages.push({
        role: "system",
        content: "## 当前小说设定索引\n\n" + summaryIndex +
          "\n\n请基于此索引判断需要查询哪些设定的详情。写作前先查角色、查伏笔状态、查大纲节点——不要凭记忆写作。",
      });
    }

    // 对话历史
    if (conversationHistory.length > 0) {
      const historySection = buildConversationHistoryText(conversationHistory);
      if (historySection && historySection.trim()) {
        messages.push({ role: "system", content: "## 对话历史\n\n" + historySection });
      }
    }

    const activeTaskContext = buildActiveTaskContext(state);
    if (activeTaskContext) {
      messages.push({ role: "system", content: activeTaskContext });
    }

    if (novelData.approvedBeatPlan) {
      messages.push({
        role: "system",
        content: "## 写作结构约束：已批准章节计划\n\n" +
          "下面的 Beat Plan 是本章正文草案的结构约束，不是普通参考。写正文时必须按场景职责、冲突、验收标准组织内容；如需偏离，正文末尾必须说明原因。\n\n" +
          JSON.stringify(novelData.approvedBeatPlan, null, 2),
      });
    } else {
      messages.push({
        role: "system",
        content: "## 写作结构提示\n\n当前章节没有已批准 Beat Plan。你仍可生成正文草案，但必须在正文末尾用「---」分隔后简短标注：未基于已批准章节计划。",
      });
    }

    // 重写/跨Agent委托上下文
    if (pendingAgentCall?.toAgent === AGENT_ID) {
      let taskInfo = "## 来自 " + pendingAgentCall.fromAgent + " 的任务\n";
      taskInfo += "原因：" + pendingAgentCall.reason + "\n";
      if (pendingAgentCall.specificQuestion) taskInfo += "具体要求：" + pendingAgentCall.specificQuestion + "\n";
      if (pendingAgentCall.contentToRewrite) taskInfo += "需要处理的内容：\n---\n" + pendingAgentCall.contentToRewrite + "\n---\n";
      messages.push({ role: "system", content: taskInfo });
    }

    if (rewriteRequest) {
      let rewriteInfo = "## 重写请求（来自校验员）\n";
      for (const conflict of rewriteRequest.conflicts ?? []) {
        rewriteInfo += "【" + conflict.type + "冲突】" + conflict.description + "\n";
        rewriteInfo += "建议：" + conflict.suggestion + "\n\n";
      }
      messages.push({ role: "system", content: rewriteInfo });
    }

    // 已有内容仅作为可选参考，不代表本轮一定要续写或改写。
    const content = generatedContent || novelData.chapterContent;
    if (content) {
      messages.push({
        role: "system",
        content: "## 可选参考：已有章节内容\n\n" +
          "只有当用户要求续写、改写、补写、接续当前章节或需要保持上下文时，才使用这段内容。\n\n" +
          content.slice(-4000),
      });
    }

    const request = userMessage || (rewriteRequest ? "请根据校验意见修改相关段落" : "请根据当前写作目标创作合适的文本");
    messages.push({ role: "user", content: request });

    return messages;
  },
};

/**
 * 作家 Node（Phase 7：完全声明式，后处理收归 AgentDefinition.postProcess）
 */
export async function authorNode(
  state: WritingState
): Promise<Partial<WritingState>> {
  return runAgent(authorDefinition, state);
}

/**
 * 检查是否有来自校验员的改写请求。
 *
 * Phase E 返工：新协议下通过 route_to_agent → pendingAgentCall 传递改写上下文，
 *   不再读取旧 JSON wantsToCall/conflicts 字段。
 */
function checkRewriteRequest(
  validatorOutput: AgentOutput | null,
  pendingAgentCall?: { fromAgent?: string; toAgent?: string } | null
): { conflicts: Array<{ type?: string; description?: string; suggestion?: string }>; suggestions: string[] } | null {
  if (pendingAgentCall?.fromAgent === "校验" && pendingAgentCall?.toAgent === AGENT_ID) {
    return {
      conflicts: [],
      suggestions: validatorOutput?.suggestions ?? [],
    };
  }
  return null;
}

function buildSystemPrompt(): string {
  return [
    "你是" + AGENT_NAMES[AGENT_ID] + "，身份是小说正文创作者。",
    "",
    "## 身份边界",
    "你不是固定的整章生成器。你负责把用户指定的创作目标转化为可读的小说文本。",
    "用户可能要求你写整章、续写、改写某段、写角色对白、写场景样稿、把大纲转正文、补一个桥段或按返工 brief 修局部。",
    "先判断本轮要创作的文本类型，再决定是否需要参考已有章节内容。不要因为已有正文就拒绝执行。",
    "",
    "## 行动循环",
    "1. 先理解用户要写什么：整章、续写、片段、对白、改写、样稿还是局部补写。",
    "2. 基于写作对象选择工具：角色对白查 get_character_detail；场景查地点/势力/物品详情；大纲转正文查 outline；承接前文查 get_recent_chapters 或可选章节材料；涉及伏笔查 list_foreshadowings_summary。",
    "3. 每次工具返回后判断信息是否足够；足够就开始写，不要机械查完所有工具。",
    "4. 不确定设定时先查工具；仍不确定时在正文后简短标注待确认点。",
    "5. 如果用户只是要建议、分析或解释，不要伪装成正文输出。",
    "",
    "## 工具使用策略",
    "- 摘要工具（list_*_summary）成本低，用于判断需要详情的对象",
    "- 详情工具（get_*_detail）成本高，只查当前场景直接需要的",
    "- 写完一段后自检，发现不确定性时回头查工具或标注待确认",
    "- 单轮最多查 3-5 个详情",
    "",
    "## 写作纪律",
    "1. 基于设定写作，不自行补充未经确认的设定",
    "2. 角色行为必须符合 behaviorBoundaries、对话匹配 speechStyle",
    "3. 自然地融入伏笔，不突兀不强制",
    "4. 对不确定的设定，在正文后标明需要确认的内容",
    "5. 在创作操作工作流中，不要自行转交给其他 Agent；如发现需要补充设定或大纲依据，在正文后用中文说明缺口。",
    "6. 如果系统提供了已批准 Beat Plan，它是本章结构约束；按场景目标、阻力、转折、代价、结果、余波组织正文，不要把它当成可忽略的普通参考。",
    "7. 如果没有已批准 Beat Plan，仍可写正文，但正文末尾必须用「---」分隔后标注“未基于已批准章节计划”。",
    "",
    "## 你的输出",
    "直接以自然段文本输出本轮需要的文本。不要用 JSON 包裹，不要使用标题、列表、表格、代码块、引用块或加粗等格式标记。",
    "如果本轮是小说正文，回复主体就是正文内容本身，不要添加大段解释说明。",
    "如果本轮是样稿、对白片段或局部改写，可以在标题中标明用途。",
    "如果需要简要说明创作思路，放在正文末尾用「---」分隔后简要写。",
    "重要：生成正文草案或改写场景草案时，不要声称已经写入章节；正文只有用户确认待审核草案后才会应用到项目。",
  ].join("\n");
}

function shouldPersistAsChapterContent(state: WritingState, content: string): boolean {
  if (!content.trim()) return false;
  if (state.pendingAgentCall?.toAgent === AGENT_ID) return true;

  const message = state.userMessage || "";
  const asksForChapterBody = /正文|整章|生成|续写|接着写|继续写|补写|改写|重写|扩写/.test(message);
  const asksForNonPersistentSample = /样稿|示例|例子|对白|对话|片段|建议|分析|评价|说明|思路|brief/i.test(message);

  return asksForChapterBody && !asksForNonPersistentSample;
}

/**
 * 新模式：从段落文本正文中提取章节内容。
 *
 * 新协议下模型直接输出正文（段落文本），无需从 JSON 字段提取。
 * 如果正文末尾有「---」分隔的创作说明，只提取说明之前的内容。
 */
function extractContentNewMode(text: string): string {
  if (!text || !text.trim()) return "";

  // 移除末尾创作说明（「---」分隔符之后的内容）
  const separatorIndex = text.lastIndexOf("\n---\n");
  if (separatorIndex > 0) {
    const mainBody = text.slice(0, separatorIndex).trim();
    if (mainBody.length > 0) return mainBody;
  }

  // 移除 JSON 代码块（新模式不应出现，但做兜底清理）
  const cleaned = text.replace(/```json[\s\S]*?```/g, "").trim();
  return cleaned;
}

// Phase 9：旧 extractContent() 已删除（依赖 extractTextFieldFromJsonResponse）。
// 新协议下使用 extractContentNewMode() 替代。
