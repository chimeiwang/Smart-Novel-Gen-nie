/**
 * Agent 能力卡契约。
 *
 * @module shared/contracts/agent-capabilities
 * @description 初始创作操作路由使用。运行中 Agent 不再读取能力卡自行转交。
 */

import type { AgentUpdateSection } from "./agent-updates";
import type { CoreAgentId } from "./agent";

export interface AgentCapabilityCard {
  id: CoreAgentId;
  name: string;
  mission: string;
  canHandle: string[];
  cannotHandle: string[];
  updateSections: AgentUpdateSection[];
  routingNotes: string[];
}

export const AGENT_CAPABILITY_CARDS: Record<CoreAgentId, AgentCapabilityCard> = {
  "设定": {
    id: "设定",
    name: "设定顾问",
    mission: "维护作品设定体系，处理角色、世界观、势力、地点、物品、术语、角色经历等设定问题。",
    canHandle: [
      "讨论、评价、创建、修改角色设定和角色不变量",
      "维护世界观规则、势力、地点、物品、术语和角色经历",
      "检查设定是否自洽，判断新设定是否会破坏已有事实",
      "为其他 Agent 补充设定约束、人物动机和设定边界",
    ],
    cannotHandle: [
      "不主责调整大纲结构、章节顺序、剧情节奏或伏笔生命周期",
      "不主责生成小说正文",
      "不主责提交章节商业评分或正式一致性校验报告",
    ],
    updateSections: [
      "characters",
      "locations",
      "items",
      "factions",
      "glossaries",
      "characterExperiences",
      "worldSetting",
      "storyBackground",
    ],
    routingNotes: [
      "任务主产物是大纲、伏笔或章节节奏时，选择更适合的 Agent 承接",
      "任务主产物是角色字段、世界规则或设定条目时，由设定顾问承接",
    ],
  },
  "剧情": {
    id: "剧情",
    name: "剧情顾问",
    mission: "设计和维护故事结构，处理大纲、章节职责、冲突链、角色行动链、伏笔与节奏。",
    canHandle: [
      "讨论、评价、创建、修改大纲节点和章节结构",
      "设计剧情走向、主线推进、冲突升级、节奏分布和情绪回报",
      "管理伏笔的埋设、推进、回收和废弃",
      "生成或评估 beat plan，拆分章节任务",
    ],
    cannotHandle: [
      "不主责直接修改角色核心设定字段，除非只是剧情层面的使用建议",
      "不主责生成最终小说正文",
      "不主责提交商业质量评分或正式一致性校验报告",
    ],
    updateSections: ["outline", "outlineContent", "outlineAdjustments", "foreshadowing"],
    routingNotes: [
      "任务主产物是剧情结构、章节安排或伏笔变更时，由剧情顾问承接",
      "剧情方案需要落到角色不变量或世界规则时，入口路由应选择设定顾问补充",
    ],
  },
  "写作": {
    id: "写作",
    name: "作家",
    mission: "把已确认的设定、大纲、beat plan 或返工 brief 写成可读的小说正文、片段或对白。",
    canHandle: [
      "生成整章、续写、改写、扩写、补写、桥段、场景样稿和角色对白",
      "按剧情 brief、编辑 brief 或校验 brief 重写局部正文",
      "把大纲或 beat plan 转化为具体叙事文本",
    ],
    cannotHandle: [
      "不主责做大纲结构设计或伏笔生命周期管理",
      "不主责保存设定、大纲或伏笔变更",
      "不主责提交商业评分或一致性校验报告",
    ],
    updateSections: [],
    routingNotes: [
      "任务主产物是正文文本时，由作家承接",
      "写作前缺少结构方案时，入口路由应选择剧情顾问；缺少设定依据时，入口路由应选择设定顾问",
    ],
  },
  "校验": {
    id: "校验",
    name: "校验员",
    mission: "审计正文、设定、大纲、伏笔和世界观的一致性、逻辑冲突与 OOC 风险。",
    canHandle: [
      "检查角色不变量、设定规则、时间线、因果链和伏笔状态是否冲突",
      "对章节正文、角色设定、大纲、世界观或跨 Agent brief 做一致性审计",
      "提交结构化冲突报告，给出可执行修正建议",
    ],
    cannotHandle: [
      "不主责创作正文",
      "不主责规划大纲或保存剧情变更",
      "不主责维护设定字段，除非只是指出应由谁修正",
    ],
    updateSections: [],
    routingNotes: [
      "任务目标是查错、审计、一致性、冲突、OOC 或逻辑风险时，由校验员承接",
      "发现需要改写正文时，入口路由应选择作家；发现设定缺口时，入口路由应选择设定顾问",
    ],
  },
  "编辑": {
    id: "编辑",
    name: "网文编辑",
    mission: "从读者留存、付费转化、市场差异化、爽点兑现和追读风险角度评价创作材料。",
    canHandle: [
      "评价作品定位、题材卖点、角色吸引力、大纲商业潜力和世界观商业性",
      "评审正文钩子、冲突、爽点、节奏、章末追读和读者承诺兑现",
      "给出商业性改法、返工 brief 和质量评分",
      "做技法评审，诊断流水账、场景结构和语言问题",
    ],
    cannotHandle: [
      "不主责保存大纲、伏笔或设定变更",
      "不主责生成最终正文",
      "不主责做正式一致性冲突审计",
    ],
    updateSections: [],
    routingNotes: [
      "任务目标是商业判断、读者兴趣、钩子、爽点、节奏、追读或技法评审时，由编辑承接",
      "评审后需要具体结构修改时，入口路由应选择剧情顾问；需要正文返工时，入口路由应选择作家；需要补设定时，入口路由应选择设定顾问",
    ],
  },
};

export function formatAgentCapabilityCards(): string {
  return Object.values(AGENT_CAPABILITY_CARDS)
    .map((card) => formatSingleAgentCapabilityCard(card.id))
    .join("\n\n");
}

export function formatSingleAgentCapabilityCard(agentId: CoreAgentId): string {
  const card = AGENT_CAPABILITY_CARDS[agentId];
  const updateText = card.updateSections.length > 0 ? card.updateSections.join(", ") : "无保存型 updates";
  return [
    `### ${card.id}（${card.name}）`,
    `职责：${card.mission}`,
    `能处理：${card.canHandle.join("；")}`,
    `不主责：${card.cannotHandle.join("；")}`,
    `可保存 updates section：${updateText}`,
    `路由提示：${card.routingNotes.join("；")}`,
  ].join("\n");
}

function buildAgentCapabilityRoutingGuide(): string {
  return [
    "## Agent 能力卡（入口路由依据）",
    "你需要像阅读 skills 一样阅读下面的能力卡，再判断哪个 Agent 是当前任务的主责方。",
    "",
    formatAgentCapabilityCards(),
    "",
    "## 路由原则",
    "- 选择最能产出本轮主要成果的 Agent，而不是只根据关键词匹配。",
    "- 混合任务优先选择主产物所属 Agent。",
    "- 不要把运行中转交作为默认方案；需要跨角色协作时，由 LangGraph 的 operationWorkflow 和审核/返工边控制。",
    "- 不要在职责外强行保存不属于当前 Agent 的 updates。",
    "- 代码会继续校验工具参数和可保存 section；你只负责做清晰的入口任务归属判断。",
  ].join("\n");
}

export function buildIntentClassifierSystemPrompt(): string {
  return [
    "你是小说写作助手的创作操作路由器。根据用户消息和 Agent 能力卡，先判断本轮 CreativeOperation，再选择最适合执行该操作的主责 Agent。",
    "",
    buildAgentCapabilityRoutingGuide(),
    "",
    "## 创作操作类型",
    "- 回答问题：回答创作相关问题、解释当前状态、做普通讨论，不直接产生待保存草案。",
    "- 新建设定 / 修改设定：新增或修改角色、世界观、势力、地点、物品、术语、角色经历等设定。",
    "- 创建大纲 / 修改大纲：新增或修改总纲、结构化大纲节点、章节职责、剧情结构。",
    "- 规划章节：生成章节计划、场景功能、章节目标。",
    "- 生成正文草案：按已有设定、大纲或计划生成正文草案。",
    "- 改写场景草案：根据返工要求、校验意见或编辑意见改写正文片段草案。",
    "- 审核章节：做一致性、商业性、技法或章节质量评审。",
    "- 同步设定：从正文或最近章节提取已发生事实，生成设定同步草案。",
    "- 管理伏笔：埋设、推进、回收或废弃伏笔。",
    "",
    "## Operation 字段规则",
    "- primaryAgent 必须等于最适合执行该操作的 Agent。",
    "- outputKind 按主产物填写：chat_answer、lore_proposal、outline_proposal、beat_plan、chapter_text、review_report、revision_brief、sync_proposal。",
    "- 会改变项目状态的创作操作必须 requiresArtifact=true 且 requiresUserApproval=true。",
    "- 回答问题和审核章节通常不需要草案；生成正文草案和改写场景草案必须进入待审核草案。",
    "- 用户要求生成、搭建、展开或重构大纲时，使用 create_outline/revise_outline，主产物是结构化 outline_proposal。",
    "- reviewers 用于表达自然需要后续审核的角色，例如 write_chapter 可建议 [\"校验\", \"编辑\"]。",
    "",
    "只返回 JSON，不要有其他内容：",
    "{",
    '  "targetAgent": "设定" | "剧情" | "写作" | "校验" | "编辑" | null,',
    '  "operation": {',
    '    "kind": "answer_question" | "create_lore" | "revise_lore" | "create_outline" | "revise_outline" | "plan_chapter" | "write_chapter" | "rewrite_scene" | "review_chapter" | "sync_lore" | "manage_foreshadowing",',
    '    "targetType": "novel" | "chapter" | "character" | "lore" | "outline" | "foreshadowing" | "scene" | "artifact" | "unknown",',
    '    "targetId": "可选目标ID",',
    '    "userGoal": "用一句话复述用户要完成的创作目标",',
    '    "primaryAgent": "设定" | "剧情" | "写作" | "校验" | "编辑",',
    '    "reviewers": ["校验", "编辑"],',
    '    "outputKind": "chat_answer" | "lore_proposal" | "outline_proposal" | "beat_plan" | "chapter_text" | "review_report" | "revision_brief" | "sync_proposal",',
    '    "requiresArtifact": true,',
    '    "requiresUserApproval": true,',
    '    "confidence": 0.0-1.0,',
    '    "reasoning": "简短说明为什么识别为该操作"',
    "  },",
    '  "action": "call_agent" | "discuss" | "generate" | "check" | "review" | "status" | "unknown",',
    '  "confidence": 0.0-1.0,',
    '  "reasoning": "简短说明你如何依据能力卡选择主责 Agent"',
    "}",
    "",
    "如果用户只是闲聊、目标不清或不需要 Agent 处理，targetAgent 可以为 null，operation.kind 使用 answer_question，action 为 status 或 unknown。",
    "confidence 表示你对 CreativeOperation 和主责 Agent 判断的整体把握程度。",
  ].join("\n");
}
