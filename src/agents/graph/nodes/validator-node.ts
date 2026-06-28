/**
 * 校验员 Agent（Phase 4 重构 + Phase 5 新协议迁移）
 *
 * @module agents/graph/nodes/validator-node
 * @description 以一致性审计员身份检查正文、设定、大纲、角色、伏笔和世界观的冲突风险。
 *
 * ## Phase 4 重构
 * - 删除 ~130 行模板代码
 * - 声明式 AgentDefinition + AgentRunner 统一封装
 *
 * ## Phase 5 迁移（Agent Runtime 协议重构）
 * - outputMode: "paragraph_text_with_control_tools"
 * - submit_validation_report 替代 hasConflicts/conflicts JSON 字段
 * - 段落文本直接输出替代 JSON 信封
 */

import type { OpenAI } from "openai";
import type { AgentOutput, CoreAgentId, WritingState } from "../state";
import { AGENT_NAMES } from "../state";
import { buildContextWithHistory } from "../context-manager";
import { SELF_CHECK_PROMPT } from "../self-check-prompt";
import { buildActiveTaskContext, buildSummaryIndex } from "../context-builder";
import type { AgentDefinition } from "@/agents/runtime/agent-definition";
import { runAgent } from "@/agents/runtime/agent-runner";

const AGENT_ID: CoreAgentId = "校验";
type ConflictType = "character" | "setting" | "plot" | "logic" | "world";

const validatorDefinition: AgentDefinition = {
  id: AGENT_ID,
  name: AGENT_NAMES[AGENT_ID],
  outputField: "validatorOutput",
  logTag: "VALIDATOR",

  // Phase 5：新协议模式
  outputMode: "paragraph_text_with_control_tools",

  toolCapabilities: [
    "novel.read",
    "character.read",
    "plot.read",
    "lore.read",
    "artifact.read",
    "control.artifact",
    "control.validation",
    "control.evaluation",
  ],

  statusMessages: {
    understanding: "正在理解校验对象...",
    thinking: "正在审计一致性与冲突风险...",
    responding: "正在组织校验结论...",
    parsing: "正在分析校验结果...",
  },

  buildMessages: (state) => {
    const { userMessage, novelData, conversationHistory } = state;
    const availableContent = state.generatedContent || novelData.chapterContent;
    const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [];

    messages.push({ role: "system", content: buildSystemPrompt() });
    messages.push({ role: "system", content: SELF_CHECK_PROMPT });

    const summaryIndex = buildSummaryIndex(novelData);
    if (summaryIndex) {
      messages.push({
        role: "system",
        content: "## 当前小说摘要索引\n\n" + summaryIndex +
          "\n\n请先基于摘要识别高风险对象；只有摘要不足以完成校验时，才调用详情工具。",
      });
    }

    if (conversationHistory.length > 0) {
      messages.push({
        role: "system",
        content: "## 对话历史\n\n" + buildContextWithHistory({
          conversationHistory, userMessage, novelData,
        } as WritingState),
      });
    }

    const activeTaskContext = buildActiveTaskContext(state);
    if (activeTaskContext) {
      messages.push({ role: "system", content: activeTaskContext });
    }

    if (availableContent) {
      messages.push({
        role: "system",
        content: "## 可选参考：当前章节内容\n\n" +
          "只有当用户要求校验正文、章节事实、场景逻辑或需要对照当前章节时，才使用这段材料。\n\n---\n" +
          availableContent.slice(-8000) + "\n---",
      });
    }

    messages.push({ role: "user", content: userMessage || "请从一致性审计角度指出当前作品最需要校验的风险点" });

    return messages;
  },
};

export async function validatorNode(
  state: WritingState
): Promise<Partial<WritingState>> {
  return runAgent(validatorDefinition, state);
}

function buildSystemPrompt(): string {
  return "你是" + AGENT_NAMES[AGENT_ID] + "，身份是创作一致性审计员。" +
    "\n\n## 身份边界" +
    "\n你不是固定的正文校验器。你的职责是审计用户指定材料中的一致性、逻辑、设定边界和风险。" +
    "\n可校验对象包括：章节正文、角色设定、大纲、伏笔、世界观规则、势力关系、物品能力、剧情进度和跨 Agent 返工 brief。" +
    "\n不要因为进入校验员 Agent 就要求用户必须先提供正文；用户问角色设定是否自洽时，就审角色；用户问大纲逻辑是否冲突时，就审大纲。" +
    "\n\n## 行动循环" +
    "\n1. 先理解用户要校验什么，以及要防什么风险。" +
    "\n2. 基于对象选择工具：角色用 get_character_detail；大纲用 list_outline_summary/get_outline_node；伏笔用 list_foreshadowings_summary/get_foreshadowing_detail；世界和设定用对应 lore 工具；正文用当前章节材料或 get_recent_chapters。" +
    "\n3. 每次工具返回后重新判断风险是否已能确认；信息足够就停止查询并输出。" +
    "\n4. 不要机械读取所有详情；优先读取最可能产生严重冲突的对象。" +
    "\n5. 不确定校验对象时，先提出一个简短澄清问题。" +
    "\n\n## 校验标准" +
    "\n- 角色：核心欲望、行为边界、说话习惯、关键关系原则、短期目标是否互相冲突或被文本违背。" +
    "\n- 设定：世界规则、势力边界、物品能力、地点限制是否自洽。" +
    "\n- 剧情：因果链、时间线、角色动机、信息来源、冲突升级是否成立。" +
    "\n- 伏笔：埋设、推进、回收是否与已知状态一致。" +
    "\n- 作品圣经：是否偏离题材定位、读者承诺、爽点模型或触犯雷点。" +
    "\n\n## 校验方法" +
    "\n1. 先识别材料中的事实断言和高风险边界。" +
    "\n2. 用摘要索引判断相关对象，再读取必要详情。" +
    "\n3. 逐项对比，记录证据；没有证据时不要扩大问题。" +
    "\n4. 判断 OOC 时必须引用对应角色不变量或设定字段。" +
    "\n5. 对每个冲突提出具体修改建议。" +
    "\n\n## 你的回复" +
    "\n直接以自然段文本输出完整的校验报告。不要用 JSON 包裹，不要使用标题、列表、表格、代码块、引用块或加粗等格式标记。" +
    "\n每个冲突写明类型（角色/设定/剧情/逻辑/世界观）、原文内容、应正确内容、修改建议。" +
    "\n如果没有任何冲突，明确说明「校验通过」或「当前材料未发现明确冲突」。" +
    "\n\n## 提交校验结果" +
    "\n只有在完成正式冲突校验时，才使用 submit_validation_report 工具提交结构化冲突列表：" +
    "\n- 有冲突时：hasConflicts=true，conflicts 数组中每项包含 type/summary/evidence/suggestion" +
    "\n- 无冲突时：hasConflicts=false，conflicts 为空数组" +
    "\n- 需要其他 Agent 继续处理时：在校验报告中说明问题和建议主责方向，不要自行转交" +
    "\n- 复审其他 Agent 产物时：先调用 get_active_review_artifact 或 get_review_artifact 读取待审核草案；最终必须调用 submit_evaluation 提交 pass/revise/block，不能只输出自然语言校验报告。" +
    "\n- 复审结论可提交用户确认时：verdict=pass；需要返工时：verdict=revise，并在 requiredChanges 写清可执行修改要求；无法继续时：verdict=block。" +
    "\n- 可精确定位的小修用 revisionMode=patch；方向性或结构性大改用 revisionMode=rewrite。" +
    "\n- 如果你已经写出校验报告但还没调用 submit_evaluation，本轮复审仍视为未完成。";
}

// 保留辅助函数（非 Agent node 使用）
export function quickConflictCheck(
  content: string,
  novelData: WritingState["novelData"]
): Array<{ type: ConflictType; description: string; suggestion: string }> {
  const issues: Array<{ type: ConflictType; description: string; suggestion: string }> = [];
  for (const char of novelData.characters) {
    new RegExp(char.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g");
  }
  return issues;
}

export function getValidationSummary(output: AgentOutput): string {
  return output.content.trim() || "校验报告已生成。";
}
