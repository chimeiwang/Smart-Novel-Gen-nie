/**
 * 剧情顾问 Agent（Phase 4 重构：AgentDefinition + AgentRunner，Phase 4 迁移：新协议）
 *
 * @module agents/graph/nodes/plot-advisor-node
 * @description 讨论剧情走向、大纲管理、伏笔、故事结构。
 *
 * ## Phase 4 重构
 * - 删除 ~130 行模板代码
 * - 声明式 AgentDefinition + AgentRunner 统一封装
 *
 * ## Phase 4 迁移（Agent Runtime 协议重构）
 * - outputMode: "paragraph_text_with_control_tools"（首个迁移 Agent）
 * - 删除 JSON 输出格式要求
 * - 段落文本直接输出替代 JSON 信封
 */

import type { OpenAI } from "openai";
import type { CoreAgentId, WritingState } from "../state";
import { AGENT_NAMES } from "../state";
import { SELF_CHECK_PROMPT } from "../self-check-prompt";
import { buildActiveTaskContext, buildOperationSummaryIndex, buildConversationHistoryText, getOutlineStatusIcon } from "../context-builder";
import { PLOT_UPDATE_SCHEMA_PROMPT } from "../lore-update-schema";
import type { AgentDefinition } from "@/agents/runtime/agent-definition";
import { runAgent } from "@/agents/runtime/agent-runner";
import {
  ITEM_TEXT_BLOCK_TOOLS_CN_TEXT,
  UPDATE_BUILDER_TOOL_CHAIN_TEXT,
} from "@/shared/contracts/agent-update-channels";

const AGENT_ID: CoreAgentId = "剧情";

const plotAdvisorDefinition: AgentDefinition = {
  id: AGENT_ID,
  name: AGENT_NAMES[AGENT_ID],
  outputField: "plotAdvisorOutput",
  logTag: "PLOT_ADVISOR",

  // Phase 4：新协议模式（首个迁移 Agent）
  outputMode: "paragraph_text_with_control_tools",

  toolCapabilities: ["novel.read", "character.read", "plot.read", "chapter.read", "artifact.read", "proposal.plot", "control.proposal", "control.builder", "control.artifact", "control.beat"],

  allowedUpdateSections: ["outline", "outlineContent", "outlineAdjustments", "foreshadowing"],

  statusMessages: {
    understanding: "正在理解您的请求...",
    thinking: "正在分析剧情...",
    responding: "正在组织剧情建议...",
    parsing: "正在整理剧情结果...",
  },

  buildMessages: (state) => {
    const { userMessage, novelData, conversationHistory } = state;
    const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [];

    messages.push({ role: "system", content: buildSystemPrompt() });
    messages.push({ role: "system", content: SELF_CHECK_PROMPT });

    // 摘要索引（分层上下文）
    const contextIndex = buildOperationSummaryIndex(state);
    if (contextIndex) {
      messages.push({
        role: "system",
        content: "## 当前小说摘要索引\n\n" + contextIndex +
          "\n\n请先基于摘要判断相关性；只有摘要不足以支持剧情判断时，才使用详情工具。",
      });
    }

    // 对话历史
    if (conversationHistory.length > 0) {
      messages.push({
        role: "system",
        content: "## 对话历史\n\n" + buildConversationHistoryText(conversationHistory),
      });
    }

    const activeTaskContext = buildActiveTaskContext(state);
    if (activeTaskContext) {
      messages.push({ role: "system", content: activeTaskContext });
    }

    messages.push({ role: "user", content: userMessage });
    return messages;
  },
};

export async function plotAdvisorNode(
  state: WritingState
): Promise<Partial<WritingState>> {
  return runAgent(plotAdvisorDefinition, state);
}

function buildSystemPrompt(): string {
  return "你是" + AGENT_NAMES[AGENT_ID] + "，身份是小说剧情结构顾问。" +
    "\n\n## 身份边界" +
    "\n你不是固定的大纲管理器，也不只是伏笔工具的入口。" +
    "\n你从主线推进、章节职责、冲突递进、角色行动链、伏笔生命周期、信息释放和故事结构角度，帮助用户判断和设计剧情。" +
    "\n用户可能让你看大纲、讨论角色在剧情中的功能、判断世界观是否支撑冲突、规划章节节奏、调整伏笔、分析剧情走向或生成 beat plan。先理解任务目标，再行动。" +
    "\n\n## 核心原则" +
    "\n\n### 思考 → 行动 → 观察 → 调整" +
    "\n- 先判断用户要处理的剧情对象：整体故事、大纲节点、某条人物线、伏笔、章节目标、冲突链或节奏问题。" +
    "\n- 根据信息缺口选择工具；工具返回后重新判断是否还需要查询。" +
    "\n- 信息足够时停止查询并输出，不要为了固定流程批量读取详情。" +
    "\n- 用户意图不清时先简短澄清，不要把请求强行套成大纲修改。" +
    "\n\n### 索引优先，按需查询" +
    "\n系统会先给你摘要索引。你必须先依据摘要索引判断相关性。" +
    "\n- 摘要足够回答概览建议时，不调用详情工具" +
    "\n- 需要具体大纲、角色动机、伏笔细节或章节内容时，才调用对应详情工具" +
    "\n- 单轮最多读取 3 个详情；超过时先回答已确认部分" +
    "\n\n## 工具选择策略" +
    "\n- list_outline_summary：了解剧情结构全貌" +
    "\n- get_outline_node：查看具体节点内容和状态" +
    "\n- get_plot_progress：了解当前阶段和目标" +
    "\n- list_foreshadowings_summary：了解活跃伏笔" +
    "\n- get_foreshadowing_detail：只有具体伏笔影响剧情判断时使用" +
    "\n- get_recent_chapters：查看最近章节内容，评估剧情推进" +
    "\n- get_character_detail：当剧情判断依赖角色欲望、行动边界或关系张力时使用" +
    "\n\n## 剧情判断标准" +
    "\n- 主线：读者是否知道故事在追什么，阶段目标是否明确。" +
    "\n- 冲突：阻力是否逐步升级，是否有代价和不可逆变化。" +
    "\n- 角色行动链：角色是否因欲望主动选择，而不是只被事件推动。" +
    "\n- 伏笔：埋设、推进、回收是否服务期待管理。" +
    "\n- 节奏：铺垫、爆点、余波和悬念是否分布合理。" +
    "\n- 章节职责：每章是否承担清晰的推进、揭示、转折或情绪回报功能。" +
    "\n\n## 篇幅 Profile 策划规则" +
    "\n作品圣经会给出篇幅模式。必须按该模式规划，不要把中短篇默认展开成百万字长篇。" +
    "\n- 中短篇：适合从一句灵感开始。先多轮讨论故事种子、主角目标、核心矛盾、关键设定、结局承诺和读者情绪回报；大纲默认 3-10 万字、8-25 章、3-5 个剧情单元，设定只保留服务主线和结局兑现的必要内容。" +
    "\n- 长篇连载：先验证可持续连载能力。规划长期冲突源、多阶段主线、伏笔池、角色长期状态和可循环爽点；大纲可以展开为多阶段、多剧情单元和长期章节组。" +
    "\n- 如果用户只给一句灵感且作品是中短篇，信息不足时先提出最少必要澄清或给出可选方向，不要直接生成庞大世界观或多卷大纲。" +
    "\n\n## 主动协作" +
    "\n- 发现剧情缺口或矛盾 → 在回复中明确指出，并提出改进建议" +
    "\n- 发现伏笔回收机会 → 在回复中说明回收时机和方式" +
    "\n- 完成任务后 → 主动提出 1-3 个下一步建议" +
    `\n- 用户明确要求生成、修改、展开或重构大纲时 → 短小变更可用 propose_updates；批量大纲树、长总纲、复杂结构必须使用 ${UPDATE_BUILDER_TOOL_CHAIN_TEXT} 构建 agent_updates 草案；需要补充短小修补时才使用 append_update_batch；需要写章节组详细梗概时使用 ${ITEM_TEXT_BLOCK_TOOLS_CN_TEXT}` +
    "\n- 用户要求规划章节、生成本章计划、写前规划或 Beat Plan 时 → 必须使用 submit_beat_plan 提交结构化章节计划草案。sceneBeats 每项至少包含目标、阻力/冲突、涉及角色、预计字数和验收标准；正文可见输出可以说明计划思路，但正式可应用内容必须进入 submit_beat_plan 的结构化参数。" +
    "\n- 章节计划的场景节拍必须覆盖：目标、阻力、转折、代价、结果、余波；如果某项无法明确，写入 acceptanceCriteria 说明作者确认点。" +
    "\n- 提交或定位到需要用户查看的草案后，可调用 show_review_artifact 请求前端打开草案弹窗；新建草案时优先传本轮使用的 artifactKey，不需要知道服务端 artifactId；这只是展示请求，不代表已经应用" +
    "\n- 批量创建大纲树时 → 使用 append_outline_tree 提交 stage → plotUnits → chapterGroups 嵌套树；不要提供 parentId、parentKey、clientKey 或 content。服务端会自动生成合法 outlineAdjustments。不要把结构化大纲写成纯文本 outline_draft" +
    "\n- 用户明确要求调整章节结构或更新伏笔时 → 提交 outline/outlineAdjustments/foreshadowing 待审核草案。系统会创建 ReviewArtifact，只有用户最终确认应用后才写入正式库" +
    "\n- 用户要求“先审核、写入前审核、让编辑/校验复审、改到满意再写入”时 → 草案必须提供 artifactKey，并设置 reviewerAgent，把同一个草案交给 reviewer；不要直接要求用户保存" +
    "\n- 当你收到包含 artifactId 的返工任务时 → 先调用 get_active_review_artifact 或 get_review_artifact 读取当前待审核草案；修改后仍围绕同一个 artifactKey/任务提交新 revision" +
    "\n- 需要当前 Agent 职责外的成果时 → 在正文中说明缺口和建议的主责方向，不要提交越界草案" +
    "\n\n" + PLOT_UPDATE_SCHEMA_PROMPT;
}

// 保留辅助函数供外部使用
export function getPlotSummary(novelData: WritingState["novelData"]): string {
  const lines: string[] = [];
  lines.push("当前阶段：" + (novelData.plotProgress.currentStage || "未设置"));
  if (novelData.plotProgress.currentGoal) lines.push("当前目标：" + novelData.plotProgress.currentGoal);
  if (novelData.plotProgress.currentConflict) lines.push("核心冲突：" + novelData.plotProgress.currentConflict);
  const total = novelData.outlineNodes.length;
  const completed = novelData.outlineNodes.filter((n) => n.status === "completed").length;
  if (total > 0) lines.push("大纲进度：" + completed + "/" + total + " 节点已完成");
  const activeFs = novelData.foreshadowings.filter((f) => f.status === "active");
  if (activeFs.length > 0) lines.push("活跃伏笔：" + activeFs.length + " 个");
  return lines.join("\n");
}

export function formatOutlineTree(
  nodes: WritingState["novelData"]["outlineNodes"],
  parentId: string | null = null,
  indent: number = 0
): string {
  const result: string[] = [];
  const children = nodes.filter((n) => n.parentId === parentId);
  const prefix = "  ".repeat(indent);
  for (const node of children) {
    const kind = node.kind ?? "stage";
    result.push(prefix + "- " + node.title + " (" + kind + ") [" + node.status + "]");
    if (node.content) {
      const preview = node.content.slice(0, 50);
      result.push(prefix + "  " + preview + (node.content.length > 50 ? "..." : ""));
    }
    result.push(...formatOutlineTree(nodes, node.id, indent + 1));
  }
  return result.join("\n");
}
