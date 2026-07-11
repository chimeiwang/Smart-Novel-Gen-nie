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
 * - 后处理简化：不需要 JSON 字段提取
 */

import type { OpenAI } from "openai";
import type { WritingState, AgentOutput, CoreAgentId } from "../state";
import { AGENT_NAMES } from "../state";
import { buildActiveTaskContext, buildOperationSummaryIndex, buildConversationHistoryText } from "../context-builder";
import type { AgentDefinition } from "@/agents/runtime/agent-definition";
import { runAgent } from "@/agents/runtime/agent-runner";

const AGENT_ID: CoreAgentId = "写作";
const VALIDATOR_ID: CoreAgentId = "校验";
const MISSING_APPROVED_BEAT_PLAN_MESSAGE = "当前请求明确要求基于已批准章节计划生成正文，但本章尚无 approved Beat Plan。请先执行 @剧情 规划本章并批准章节计划草案，再重新发起正文生成。";
const UNMAPPED_OUTLINE_MESSAGE = "当前章节没有唯一可用的大纲章节组映射。请先修复结构化大纲的章节范围，或为本章创建并批准章节计划后再生成正文。";
const AMBIGUOUS_OUTLINE_MESSAGE = "当前章节同时匹配多个大纲章节组，系统不会随机选择。请先清理重叠大纲范围后再生成正文。";

export function getInvalidWritingOutlineMessage(
  state: Pick<WritingState, "novelData">
): string | null {
  const outlineStatus = state.novelData.writingOutlineContext?.status;
  if (outlineStatus === "ambiguous") return AMBIGUOUS_OUTLINE_MESSAGE;
  if (outlineStatus === "unmapped") return UNMAPPED_OUTLINE_MESSAGE;
  return null;
}

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

  toolCapabilities: ["novel.read", "character.read", "lore.read", "plot.read", "chapter.read", "style.read", "artifact.read", "control.artifact"],
  modelProfile: "normal",
  reasoningEffort: "medium",

  preGuard: (state) => {
    if (shouldBlockForMissingApprovedBeatPlan(state)) {
      return {
        skip: true,
        skipMessage: MISSING_APPROVED_BEAT_PLAN_MESSAGE,
        skipOutput: { errorMessage: MISSING_APPROVED_BEAT_PLAN_MESSAGE },
      };
    }
    const message = getInvalidWritingOutlineMessage(state);
    if (!message) return null;
    return {
      skip: true,
      skipMessage: message,
      skipOutput: { errorMessage: message },
    };
  },

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

    messages.push({ role: "system", content: buildAuthorSystemPrompt() });

    // 摘要索引
    const summaryIndex = buildOperationSummaryIndex(state);
    if (summaryIndex) {
      messages.push({
        role: "system",
        content: "## 当前小说设定索引\n\n" + summaryIndex +
          "\n\n按需查询详情；信息足够后直接写，不要输出查询过程说明。",
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

    const activeArtifactId = state.artifactReview?.activeArtifactId ?? state.activeArtifactId ?? null;
    const isArtifactRevision = Boolean(activeArtifactId && pendingAgentCall?.toAgent === AGENT_ID);

    if (shouldSubmitChapterDraft(state) && !isArtifactRevision) {
      messages.push({
        role: "system",
        content: buildAuthorChapterDraftInstruction({ hasApprovedBeatPlan: Boolean(novelData.approvedBeatPlan) }),
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
          content,
      });
    }

    const request = isArtifactRevision
      ? [
          `你正在返工当前待审核正文草案（artifactId：${activeArtifactId}）。`,
          "先调用 get_active_review_artifact 读取原草案，再按本轮直接任务里的 requiredChanges 修改。",
          buildAuthorChapterDraftInstruction({ hasApprovedBeatPlan: Boolean(novelData.approvedBeatPlan) }),
          userMessage ? `原始用户请求：${userMessage}` : "",
        ].filter(Boolean).join("\n")
      : userMessage || (rewriteRequest ? "请根据校验意见修改相关段落" : "请根据当前写作目标创作合适的文本");
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

export function shouldBlockForMissingApprovedBeatPlan(state: Pick<WritingState, "currentOperation" | "novelData" | "userMessage">): boolean {
  const kind = state.currentOperation?.kind;
  if (kind !== "write_chapter" && kind !== "rewrite_scene") return false;
  if (state.novelData.approvedBeatPlan) return false;
  const message = state.userMessage ?? "";
  const planTerm = "(?:已批准(?:的)?章节计划|批准的章节计划|approved\\s*beat\\s*plan|beat\\s*plan)";
  const negation = "(?:不需要|无需|无须|不用|不必|不要|忽略|即使没有|没有[^，。；]{0,8}也)";
  if (new RegExp(`${negation}[^，。；]{0,12}${planTerm}|${planTerm}[^，。；]{0,12}${negation}`, "i").test(message)) {
    return false;
  }
  return new RegExp(planTerm, "i").test(message);
}

/**
 * 检查是否有来自校验员的改写请求。
 *
 * Phase E 返工：新协议下通过 LangGraph review loop → pendingAgentCall 传递改写上下文，
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

export function buildAuthorSystemPrompt(): string {
  return [
    `你是${AGENT_NAMES[AGENT_ID]}，身份是小说正文创作者。`,
    "把用户指定的创作目标写成可读正文；目标可能是整章、续写、改写、对白、样稿或局部补段。",
    "需要事实依据时查工具，信息够了就直接写；不要输出“我先查一下”这类过程说明。",
    "正文要承接上下文，保持角色和设定一致，并让场景有目标、阻力、变化、代价或钩子，避免流水账。",
    "不要自行转交其他 Agent；缺设定或大纲依据时，在正文外简短说明缺口。",
  ].join("\n");
}

export function buildAuthorChapterDraftInstruction(input: { hasApprovedBeatPlan: boolean }): string {
  return [
    "## 正文草案提交",
    "本轮要提交 chapter_draft：先调用 begin_artifact_output；随后在 ARTIFACT_OUTPUT_START/END 内输出正文。",
    "标记块内只放正文，不放章节标题、草案说明、写作思路或备注。",
    input.hasApprovedBeatPlan
      ? ""
      : "本章没有已批准 Beat Plan；如需提示用户，只能写在 ARTIFACT_OUTPUT_END 之后，不能进入草案。",
  ].filter(Boolean).join("\n");
}

function shouldSubmitChapterDraft(state: Pick<WritingState, "currentOperation" | "pendingAgentCall" | "artifactReview" | "activeArtifactId">): boolean {
  const kind = state.currentOperation?.kind;
  if (kind === "write_chapter" || kind === "rewrite_scene") return true;
  const activeArtifactId = state.artifactReview?.activeArtifactId ?? state.activeArtifactId ?? null;
  return Boolean(activeArtifactId && state.pendingAgentCall?.toAgent === AGENT_ID);
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
