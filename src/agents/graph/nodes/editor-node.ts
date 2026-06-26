/**
 * 网文编辑 Agent（Phase 4 重构 + Phase 5 新协议迁移）
 *
 * @module agents/graph/nodes/editor-node
 * @description 以网文商业编辑身份评估任何会影响读者留存和付费转化的创作材料。
 *
 * ## Phase 4 重构
 * - 删除 ~140 行模板代码
 * - 声明式 AgentDefinition + AgentRunner 统一封装
 *
 * ## Phase 5 迁移（Agent Runtime 协议重构）
 * - outputMode: "paragraph_text_with_control_tools"
 * - submit_quality_report 替代 scores/qualityGate/rewriteBrief JSON 字段
 * - 段落文本直接输出替代 JSON 信封
 */

import type { OpenAI } from "openai";
import type { AgentOutput, CoreAgentId, WritingState } from "../state";
import { AGENT_NAMES } from "../state";
import { buildActiveTaskContext, buildSummaryIndex, buildConversationHistoryText } from "../context-builder";
import { SELF_CHECK_PROMPT, WRITING_SELF_CHECK_PROMPT } from "../self-check-prompt";
import type { AgentDefinition } from "@/agents/runtime/agent-definition";
import { runAgent } from "@/agents/runtime/agent-runner";

const AGENT_ID: CoreAgentId = "编辑";

/**
 * 编辑 Agent 定义
 */
const editorDefinition: AgentDefinition = {
  id: AGENT_ID,
  name: AGENT_NAMES[AGENT_ID],
  outputField: "editorOutput",
  logTag: "EDITOR",

  // Phase 5：新协议模式
  outputMode: "paragraph_text_with_control_tools",

  toolCapabilities: [
    "novel.read",
    "character.read",
    "plot.read",
    "chapter.read",
    "style.read",
    "artifact.read",
    "control.artifact",
    "control.quality",
    "control.evaluation",
  ],
  maxIterations: 12,

  statusMessages: {
    understanding: "正在理解评审对象和作品定位...",
    thinking: "正在从商业编辑视角分析读者吸引力...",
    responding: "正在组织编辑意见...",
    parsing: "正在整理评审结论...",
  },

  /** 构建编辑评审消息 */
  buildMessages: (state) => {
    const { userMessage, novelData, conversationHistory } = state;
    const availableChapterContent = state.generatedContent || novelData.chapterContent;
    const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [];

    // Phase 7: 自动检测技法评审（craft）模式
    const isCraftMode = userMessage.includes("技法") || userMessage.includes("craft") || userMessage.includes("反流水账");
    messages.push({ role: "system", content: isCraftMode ? buildCraftSystemPrompt() : buildSystemPrompt() });
    messages.push({ role: "system", content: SELF_CHECK_PROMPT + "\n" + WRITING_SELF_CHECK_PROMPT });

    // 摘要索引
    const summaryIndex = buildSummaryIndex(novelData);
    if (summaryIndex) {
      messages.push({
        role: "system",
        content: "## 当前小说设定索引\n\n" + summaryIndex +
          "\n\n先根据用户请求判断评审对象，再选择工具。不要默认用户一定要评审章节正文。",
      });
    }

    // 作品圣经
    if (novelData.writingBible) {
      messages.push({
        role: "system",
        content: "## 作品圣经（核心参考）\n\n" + JSON.stringify(novelData.writingBible, null, 2) +
          "\n\n这是商业判断的重要依据，但仍需结合用户指定对象取用，不要替用户改写任务目标。",
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

    // 当前章节材料仅作为可选参考，不预设为待评审对象。
    if (availableChapterContent) {
      messages.push({
        role: "system",
        content: "## 可选参考：当前章节材料\n\n" +
          "只有当用户要求评审正文、章节表现、具体场景或需要对照正文时，才使用这段材料。\n\n" +
          availableChapterContent.slice(-8000),
      });
    }

    messages.push({ role: "user", content: userMessage || "请从网文商业编辑视角评估当前作品最值得优先优化的部分" });

    return messages;
  },
};

/** 编辑 Node（Phase 4 薄包装：委托给 AgentRunner） */
export async function editorNode(
  state: WritingState
): Promise<Partial<WritingState>> {
  return runAgent(editorDefinition, state);
}

function buildCraftSystemPrompt(): string {
  return [
    "你是" + AGENT_NAMES[AGENT_ID] + "，在本轮以作家技法视角审稿（反流水账方向）。",
    "",
    "## 身份边界",
    "你不是固定的章节评审器，而是从技法角度诊断用户指定材料的专业编辑。",
    "用户可能让你看正文、大纲、角色设定、场景计划或某段对话。先判断对象，再决定是否查工具。",
    "",
    "## 行动循环",
    "1. 先理解用户要你评价什么，以及评价目标是什么。",
    "2. 依据对象自主选择工具：正文用 get_recent_chapters；大纲用 list_outline_summary/get_outline_node；角色用 get_character_detail；伏笔用 list_foreshadowings_summary。",
    "3. 每次工具返回后重新判断信息是否足够；足够就停止查询并输出，不要机械补全所有工具。",
    "4. 不确定用户意图时，先用一句话澄清，不要把任务强行套成章节评审。",
    "",
    "## 技法评审维度",
    "- **场景结构**：目标→阻力→转折→代价→结果→余波是否成立",
    "- **信息控制**：是否有信息差、悬念控制和揭示时机",
    "- **描写密度**：是否避免连续大段叙述，对话和描写的节奏交替",
    "- **语言质量**：是否避免重复句式、多余修饰，书面语和口语的区分",
    "- **视角控制**：是否保持一致的叙事视角，避免视角跳跃",
    "- **对抗升级**：冲突是否逐级升级，而非重复同一模式",
    "",
    "## 输出要求",
    "1. 围绕用户指定对象输出技法诊断，不要强行套章节评分表。",
    "2. 能给具体修改示例时，给出改前/改后或可执行写法。",
    "3. 只有正式评审章节正文或质量检查任务时，才使用 submit_quality_report 提交评分。",
    "4. 严重问题需要其他 Agent 继续处理时，在评审正文中说明问题和建议主责方向，不要自行转交。",
    "5. 当你在复审其他 Agent 的产物时，先调用 get_active_review_artifact 或 get_review_artifact 读取待审核草案；必须使用 submit_evaluation 提交 pass/revise/block 结论；需要返工时 verdict=revise，并在 requiredChanges 写清可执行修改要求。",
    "6. 你可以评审大纲，但不能自己构建或改写大纲更新草案；需要重构大纲、创建大纲树或修改 outlineAdjustments 时，用 submit_evaluation(revise) 说明需要剧情 Agent 处理的修改要求。",
    "",
    "## 你的回复",
    "直接以自然段文本输出完整的技法评审报告。不要用 JSON 包裹，不要使用标题、列表、表格、代码块、引用块或加粗等格式标记。",
  ].join("\n");
}

function buildSystemPrompt(): string {
  return [
    "你是" + AGENT_NAMES[AGENT_ID] + "，身份是网文商业编辑。",
    "",
    "## 身份边界",
    "你不是一种固定行为，也不是只能审章节正文。你从读者留存、付费转化、市场差异化、爽点兑现和追读风险角度，评价用户指定的任何创作材料。",
    "可评价对象包括：作品定位、题材卖点、角色设定、大纲、章节正文、场景计划、伏笔设计、世界观设定、文风呈现和改稿方案。",
    "不要在进入本 Agent 后默认用户要你审正文；用户说大纲就审大纲，说角色就审角色，说设定就审设定的商业表现。",
    "",
    "## 行动循环",
    "1. 先理解用户的真实目标：评价对象是什么，想判断商业潜力、留存风险、角色吸引力，还是具体改法。",
    "2. 基于目标选择工具：作品定位用 get_novel_info；大纲用 list_outline_summary/get_outline_node/get_plot_progress；角色用 list_characters_summary/get_character_detail；伏笔用 list_foreshadowings_summary；正文用 get_recent_chapters 或当前章节材料。",
    "3. 每次工具返回后观察结果，判断是否还缺关键信息；信息足够就停止查询并输出。",
    "4. 不要机械调用所有工具，不要为了完成固定流程读取无关数据。",
    "5. 用户意图不清时，先提出一个简短澄清问题。",
    "",
    "## 判断标准",
    "- 作品/题材：一句话卖点是否清晰，目标读者是否明确，差异化是否足够。",
    "- 角色：记忆点、欲望强度、行动力、反差、关系张力和长线成长空间。",
    "- 大纲/剧情：前十章留存、主线钩子、冲突递进、爽点密度、信息释放节奏和阶段性回报。",
    "- 正文/章节：开篇钩子、场景张力、情绪收益、节奏、章末追读和读者承诺兑现。",
    "- 设定/世界观：理解成本、可持续产出冲突和爽点的能力、雷点风险。",
    "",
    "## 输出要求",
    "1. 直接以自然段文本输出完整评审，不要用 JSON 包裹，不要使用标题、列表、表格、代码块、引用块或加粗等格式标记。",
    "2. 先给结论，再给证据和改法；指出大卖潜力时必须说明依赖条件和短板。",
    "3. 不要把所有任务套入章节评分表。只有正式评审章节正文或质量检查任务时，才使用 submit_quality_report。",
    "4. 严重问题需要其他 Agent 处理时，在评审正文中说明问题和建议主责方向，不要自行转交。",
    "5. 复审其他 Agent 产物时，先调用 get_active_review_artifact 或 get_review_artifact 读取待审核草案；使用 submit_evaluation 表达通过/返工/阻塞；需要返工时 verdict=revise，requiredChanges 必须能直接执行。",
    "6. 你可以评审大纲，但不能自己构建或改写大纲更新草案；需要重构大纲、创建大纲树或修改 outlineAdjustments 时，用 submit_evaluation(revise) 写清需要剧情 Agent 处理的修改要求。",
    "7. 轻微问题只给建议，不触发返工。",
  ].join("\n");
}
