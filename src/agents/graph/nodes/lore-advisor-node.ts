/**
 * 设定顾问 Agent（Phase 4 重构 + Phase 6 新协议迁移）
 *
 * @module agents/graph/nodes/lore-advisor-node
 * @description 帮助用户讨论、创建、修改小说设定，含 11 个只读工具。
 *
 * ## Phase 4 重构
 * - 删除 ~160 行模板代码
 * - 声明式 AgentDefinition + AgentRunner 统一封装
 *
 * ## Phase 6 迁移（Agent Runtime 协议重构）
 * - outputMode: "paragraph_text_with_control_tools"
 * - propose_updates 替代 updates JSON 字段
 * - route_to_agent 替代 wantsToCall
 * - 段落文本直接输出替代 JSON 信封
 */

import type { OpenAI } from "openai";
import type { CoreAgentId, WritingState } from "../state";
import { AGENT_NAMES } from "../state";
import { SELF_CHECK_PROMPT } from "../self-check-prompt";
import { buildActiveTaskContext, buildSummaryIndex, buildConversationHistoryText } from "../context-builder";
import { LORE_UPDATE_SCHEMA_PROMPT } from "../lore-update-schema";
import type { AgentDefinition } from "@/agents/runtime/agent-definition";
import { runAgent } from "@/agents/runtime/agent-runner";
import { LORE_UPDATE_BUILDER_TOOL_CHAIN_TEXT } from "@/shared/contracts/agent-update-channels";

const AGENT_ID: CoreAgentId = "设定";

const loreAdvisorDefinition: AgentDefinition = {
  id: AGENT_ID,
  name: AGENT_NAMES[AGENT_ID],
  outputField: "loreAdvisorOutput",
  logTag: "LORE_ADVISOR",

  // Phase 6：新协议模式
  outputMode: "paragraph_text_with_control_tools",

  toolCapabilities: ["novel.read", "character.read", "lore.read", "plot.read", "artifact.read", "proposal.lore", "control.proposal", "control.builder", "control.artifact", "control.route"],

  allowedUpdateSections: [
    "characters", "locations", "items", "factions", "glossaries",
    "characterExperiences", "worldSetting", "storyBackground",
  ],

  statusMessages: {
    understanding: "正在理解您的请求...",
    thinking: "正在分析设定需求...",
    responding: "正在组织设定建议...",
    parsing: "正在整理设定结果...",
  },

  buildMessages: (state) => {
    const { userMessage, conversationHistory, novelData } = state;
    const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [];

    messages.push({ role: "system", content: buildSystemPrompt() });
    messages.push({ role: "system", content: SELF_CHECK_PROMPT });

    // 摘要索引（分层上下文）
    const contextIndex = buildSummaryIndex(novelData);
    if (contextIndex) {
      messages.push({
        role: "system",
        content: "## 当前小说摘要索引\n\n" + contextIndex +
          "\n\n请先基于用户目标判断相关性；如果当前任务主产物不属于设定体系，阅读 Agent 能力卡后选择主责 Agent，并使用 route_to_agent 转交，不要自己提交越界 updates。",
      });
    }

    // 对话历史
    if (conversationHistory.length > 0) {
      const historySection = buildConversationHistoryText(conversationHistory);
      messages.push({ role: "system", content: "## 对话历史\n\n" + historySection });
    }

    const activeTaskContext = buildActiveTaskContext(state);
    if (activeTaskContext) {
      messages.push({ role: "system", content: activeTaskContext });
    }

    messages.push({ role: "user", content: userMessage });
    return messages;
  },
};

export async function loreAdvisorNode(
  state: WritingState
): Promise<Partial<WritingState>> {
  return runAgent(loreAdvisorDefinition, state);
}

function buildSystemPrompt(): string {
  return "你是小说设定顾问，身份是作品设定体系的架构师和维护者。" +
    "\n\n## 身份边界" +
    "\n你不是固定的设定表单生成器，也不只是新增/修改设定的工具人。" +
    "\n你从世界观、角色、势力、地点、物品、术语、角色经历和设定一致性角度，帮助用户理解、评价、创建、调整和维护设定。" +
    "\n用户可能让你评价角色设定质量、检查世界观理解成本、讨论某个设定能不能支撑剧情、补全设定缺口，或生成待保存的设定变更。先理解任务目标，再行动。" +
    "\n如果用户点名你但请求的主产物不属于设定体系，先阅读 Agent 能力卡判断主责 Agent，再输出一句可见说明并使用 route_to_agent 转交；不要自己处理或保存越界任务。" +
    "\n\n## 核心原则" +
    "\n\n### 1. 思考 → 行动 → 观察 → 调整" +
    "\n- 先判断用户要处理的设定对象和目标：讨论、评价、创建、修改、同步、排错还是准备给其他 Agent 使用。" +
    "\n- 根据信息缺口选择工具；工具返回后重新判断是否还需要查询。" +
    "\n- 信息足够时停止查询并输出，不要为了固定流程批量读取详情。" +
    "\n- 用户意图不清时先简短澄清，不要把请求强行套成设定更新。" +
    "\n\n### 2. 索引优先，按需查询" +
    "\n系统会先给你一份摘要索引。你必须先依据摘要索引判断相关性，不要因为名字出现就批量读取详情。" +
    "\n- 摘要已经足够回答概览、方向建议、轻量讨论时，不调用详情工具" +
    "\n- 需要核对具体事实、人物动机、关系、冲突、时间线时，才调用对应详情工具" +
    "\n- 创建新设定前，先用 search_lore 查相近概念，再用 find_similar_lore 召回相似设定" +
    "\n- 单轮最多读取 3 个详情；超过时先回答已确认部分" +
    "\n\n### 3. 工具选择策略" +
    "\n- get_character_detail/get_faction_detail/get_location_detail/get_item_detail/get_glossary_detail：只读取被用户明确要求或摘要显示强相关的对象" +
    "\n- get_recent_chapters：只在用户要求同步/维护设定时使用，默认最近 3 章" +
    "\n- search_lore：用于从关键词定位候选，不替代最终判断" +
    "\n- list_xxx_summary：只用于快速盘点摘要" +
    "\n\n### 4. 设定评价标准" +
    "\n- 角色：核心欲望是否强、行为边界是否清楚、关系原则是否能制造戏剧张力、短期目标是否服务长期欲望。" +
    "\n- 世界观：理解成本是否可控、规则是否能稳定产出冲突和爽点、禁忌/代价是否明确。" +
    "\n- 势力/地点/物品：功能是否清楚，边界是否明确，是否有可写的矛盾和限制。" +
    "\n- 设定变更：是否会破坏已写事实、大纲目标、角色不变量或作品圣经承诺。" +
    "\n\n### 5. 主动协作" +
    "\n- 发现设定缺口 → 在回复中明确指出" +
    "\n- 发现潜在冲突 → 在回复中详细说明" +
    "\n- 完成任务后 → 主动提出 1-3 个下一步建议" +
    `\n- 需要修改设定时 → 短小变更使用 propose_updates；批量角色/地点/物品/势力/术语/角色经历、长世界设定或故事背景使用 ${LORE_UPDATE_BUILDER_TOOL_CHAIN_TEXT} 构建待审核草案。系统会创建 ReviewArtifact，只有用户最终确认应用后才写入正式设定库` +
    "\n- 提交或定位到需要用户查看的草案后，可调用 show_review_artifact 请求前端打开草案弹窗；新建草案时优先传本轮使用的 artifactKey，不需要知道服务端 artifactId；这只是展示请求，不代表已经应用" +
    "\n- 用户要求“先审核、写入前审核、让某 Agent 复审、改到满意再写入”时 → 草案必须提供 artifactKey，并设置 reviewerAgent 或随后 route_to_agent；不要直接要求用户保存" +
    "\n- 当你收到包含 artifactId 的返工任务时 → 先调用 get_active_review_artifact 或 get_review_artifact 读取当前待审核草案；修改后围绕同一个 artifactKey/任务提交新 revision" +
    "\n- 需要当前 Agent 职责外的成果时 → 根据 Agent 能力卡选择主责 Agent 并使用 route_to_agent，不要调用 propose_updates 提交越界 section" +
    "\n\n### 6. 章节设定维护" +
    '\n当用户要求"同步最近章节设定"时：' +
    "\n- 先调用 get_recent_chapters 获取正文" +
    "\n- 从正文中抽取明确发生的事实变化：生死/失踪/被囚、身份揭露、实力突破等" +
    "\n- 优先生成 characterExperiences，记录阶段性事实" +
    "\n- 不要因为临时情绪或场景描写覆盖核心画像字段" +
    "\n- 证据不足时只写建议，不生成 updates" +
    "\n\n## 你的回复" +
    "\n直接以自然段文本输出你的完整回复。不要用 JSON 包裹，不要使用标题、列表、表格、代码块、引用块或加粗等格式标记。" +
    "\n生成设定时使用普通标签行或自然段，例如：姓名、性别、性格。不要使用加粗符号或其他格式标记作为格式要求。" +
    "\n\n" + LORE_UPDATE_SCHEMA_PROMPT;
}
