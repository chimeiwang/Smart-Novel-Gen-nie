/**
 * LangGraph 状态定义
 *
 * @module agents/graph/state
 * @description 五Agent架构：设定顾问、剧情顾问、作家、校验员、编辑。
 *
 * ## 设计原则
 * - 通过 conversationHistory 实现Agent间上下文共享
 * - Agent可自主调用其他Agent，形成协作闭环
 * - streamCallbacks/eventCallbacks 不序列化到 DB，仅用于 SSE 流式传输
 */

// AgentUpdates 及其依赖类型在此文件中定义，不再从 types.ts 导入

import type { AgentControlEvent } from "@/shared/contracts/agent-control";
import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import {
  AGENT_META_MAP,
  ALL_CORE_AGENT_IDS,
  type CoreAgentId as ContractCoreAgentId,
} from "@/shared/contracts/agent";
export type { AgentControlEvent };

// ============================================
// 常量定义
// ============================================

/** 五Agent架构的Agent ID */
export const CORE_AGENT_IDS = ALL_CORE_AGENT_IDS;

/** 所有Agent ID列表 */
export const ALL_AGENT_IDS = [...CORE_AGENT_IDS] as const;

/** Agent ID联合类型 */
export type CoreAgentId = ContractCoreAgentId;

/** Agent ID映射到英文键名（用于状态字段） */
export const AGENT_ID_TO_KEY: Record<CoreAgentId, string> = {
  "设定": "loreAdvisor",
  "剧情": "plotAdvisor",
  "写作": "writer",
  "校验": "validator",
  "编辑": "editor",
};

/** 英文键名映射到Agent ID */
export const KEY_TO_AGENT_ID: Record<string, CoreAgentId> = {
  loreAdvisor: "设定",
  plotAdvisor: "剧情",
  writer: "写作",
  validator: "校验",
  editor: "编辑",
};

/** Agent中文名 */
export const AGENT_NAMES: Record<CoreAgentId, string> = Object.fromEntries(
  CORE_AGENT_IDS.map((id) => [id, AGENT_META_MAP[id].name])
) as Record<CoreAgentId, string>;

// ============================================
// 阶段枚举
// ============================================

/**
 * 工作流阶段
 * - idle: 初始空闲状态
 * - active: Agent正在处理中
 * - waiting_call: 等待用户确认Agent间调用
 * - completed: 已完成
 * - error: 发生错误
 */
export type WritingPhase =
  | "idle"
  | "active"
  | "waiting_call"
  | "awaiting_user_review"
  | "completed"
  | "error";

// ============================================
// Agent输出结构
// ============================================

/**
 * Agent 可见输出。
 *
 * 新协议主路径只应依赖这些字段：assistant content 是段落文本，
 * 控制信息通过 AgentControlEvent/tool_calls 传递。
 */
export interface AgentVisibleOutput {
  agentId: CoreAgentId;
  agentName: string;
  content: string;
  suggestions?: string[];
  /** 是否应该停止当前流程，等待用户输入 */
  waitingForUser?: boolean;
  /** 主动发现的洞察 */
  insights?: AgentInsight[];
  /** 主动建议的下一步 */
  proactiveSuggestions?: ProactiveSuggestion[];
}

/**
 * 质量检查元数据。
 *
 * 新协议中这些字段来自 submit_quality_report control tool；
 * 不再从 assistant 正文 JSON 中解析。
 */
export interface AgentQualityFields {
  scores?: QualityScores;
  qualityGate?: "pass" | "revise" | "rewrite";
  rewriteBrief?: string;
}

/** 新协议主输出类型。 */
export type AgentParagraphTextOutput = AgentVisibleOutput;

/**
 * Agent 输出聚合类型。
 *
 * 可见正文与质量元数据的聚合。控制信息必须走 AgentControlEvent/tool_calls。
 */
export type AgentOutput =
  AgentVisibleOutput &
  Partial<AgentQualityFields>;

export type AgentOutputOptions = Partial<
  Omit<AgentVisibleOutput, "agentId" | "agentName" | "content"> &
  AgentQualityFields
>;

/**
 * Agent 主动发现的洞察
 */
export interface AgentInsight {
  /** 类型：缺口/冲突/机会/观察 */
  type: "gap" | "conflict" | "opportunity" | "observation";
  /** 分类 */
  category: "character" | "plot" | "setting" | "world" | "style" | "foreshadowing" | "commercial" | "craft";
  /** 严重程度 */
  severity: "info" | "warning" | "critical";
  /** 标题 */
  title: string;
  /** 详细描述 */
  description: string;
  /** 建议行动 */
  suggestedAction?: string;
}

/**
 * Agent 主动建议的下一步
 */
export interface ProactiveSuggestion {
  /** 展示文本 */
  text: string;
  /** 对应的指令 */
  action: string;
  /** 目标 Agent ID */
  agentId?: CoreAgentId;
  /** 优先级 */
  priority: "high" | "medium" | "low";
}

/** 商业性/技法质量评分 */
export interface QualityScores {
  hook?: number;
  tension?: number;
  payoff?: number;
  pacing?: number;
  endingHook?: number;
  readerPromise?: number;
  overall?: number;
}

/**
 * 冲突详情
 */
export interface ConflictDetail {
  /** 冲突类型 */
  type: "character" | "setting" | "plot" | "logic" | "world";
  /** 冲突描述 */
  description: string;
  /** 文章中的内容 */
  articleContent: string;
  /** 正确的设定/背景 */
  correctContent: string;
  /** 建议的修改方案 */
  suggestion: string;
}

// ============================================
// 对话历史
// ============================================

/**
 * 对话历史中的单条消息
 */
export interface AgentMessage {
  /** 消息唯一ID */
  id: string;
  /** Agent ID */
  agentId: CoreAgentId;
  /** Agent中文名 */
  agentName: string;
  /** 消息内容 */
  content: string;
  /** 时间戳 */
  timestamp: number;
  /** 用户原始输入（仅用户消息时有值） */
  userMessage?: string;
  /** Agent输出（仅Agent消息时有值） */
  agentOutput?: AgentOutput;
  /** 是否是Agent间调用的消息 */
  isCallMessage?: boolean;
  /** 调用的目标Agent（仅调用消息时有值） */
  callTarget?: CoreAgentId;
}

/**
 * 待处理的Agent调用请求
 */
export interface PendingAgentCall {
  fromAgent: CoreAgentId;
  toAgent: CoreAgentId;
  reason: string;
  specificQuestion?: string;
  contentToRewrite?: string;
  timestamp: number;
}

// ============================================
// 完整状态定义
// ============================================

/**
 * 小说设定数据（从数据库聚合）
 */
export interface NovelData {
  novelId: string;
  chapterId: string;
  chapters?: { id: string; title: string; content: string | null; order?: number }[];
  novelName: string;
  chapterTitle: string;
  chapterContent: string;
  outlineSummary: string;
  outlineNodes: OutlineNodeData[];
  plotProgress: PlotProgressData;
  storyBackground: string;
  worldSetting: string;
  writingBible: WritingBibleData | null;
  storyProgress: string;
  characters: CharacterData[];
  items: ItemData[];
  locations: LocationData[];
  factions: FactionData[];
  glossaries: GlossaryData[];
  foreshadowings: ForeshadowingData[];
  references: ReferenceData[];
  styleProfile: string;
  approvedBeatPlan?: ApprovedBeatPlanContext | null;
}

/** 已批准的章节写作计划上下文 */
export interface ApprovedBeatPlanContext {
  id: string;
  chapterGoal: string;
  mainPlotConnection?: string;
  chapterAcceptanceCriteria?: string;
  totalEstimatedWords: number;
  sceneBeats: ApprovedSceneBeatContext[];
}

/** 已批准章节计划中的场景节拍 */
export interface ApprovedSceneBeatContext {
  order: number;
  goal: string;
  conflict?: string;
  characters: string[];
  foreshadowingRefs?: string[];
  estimatedWords: number;
  acceptanceCriteria: string;
}

/** 大纲节点数据 */
export interface OutlineNodeData {
  id: string;
  title: string;
  content?: string;
  kind?: "stage" | "plot_unit" | "chapter_group";
  status: "planned" | "in_progress" | "completed" | "skipped";
  order: number;
  parentId?: string;
}

/** 剧情进度数据 */
export interface PlotProgressData {
  currentStage: string;
  currentGoal?: string;
  currentConflict?: string;
  nextMilestone?: string;
}

/** 作品圣经数据 */
export interface WritingBibleData {
  genre?: string;
  targetReaders?: string;
  coreSellingPoint?: string;
  readerPromise?: string;
  appealModel?: string;
  taboo?: string;
  comparableTitles?: string;
  notes?: string;
}

/** 角色状态枚举 */
export type CharacterStatusType = "active" | "missing" | "dead" | "imprisoned" | "unknown";

/** 关系类型枚举 */
export type RelationTypeValue = "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";

/** 角色关系数据 */
export interface CharacterRelationData {
  id: string;
  targetId?: string;
  target?: { id: string; name: string };
  characterId?: string;
  character?: { id: string; name: string };
  relationType: RelationTypeValue;
  intimacy: number;
  description?: string;
  startDate?: string;
  endDate?: string;
}

/** 角色数据 */
export interface CharacterData {
  id: string;
  name: string;
  aliases?: string;
  gender?: string;
  age?: string;
  appearance?: string;
  personality?: string;
  identity?: string;
  background?: string;
  coreDesire?: string;
  behaviorBoundaries?: string;
  speechStyle?: string;
  relationshipPrinciples?: string;
  shortTermGoal?: string;
  faction?: { id: string; name: string };
  // 新增：实力相关
  powerLevel?: string;
  combatAbility?: string;
  specialSkills?: string;
  // 新增：当前状态
  currentStatus: CharacterStatusType;
  statusNote?: string;
  // 角色关系
  outgoingRelations?: CharacterRelationData[];
  incomingRelations?: CharacterRelationData[];
  experiences?: CharacterExperienceData[];
}

/** 角色经历数据 */
export interface CharacterExperienceData {
  id: string;
  characterId?: string;
  chapterId?: string;
  content: string;
  order: number;
}

/** 物品数据 */
export interface ItemData {
  id: string;
  name: string;
  aliases?: string;
  type?: string;
  rarity?: string;
  effect?: string;
  origin?: string;
  description?: string;
  ownerId?: string;
  owner?: { id: string; name: string };
}

/** 地点数据 */
export interface LocationData {
  id: string;
  name: string;
  aliases?: string;
  type?: string;
  parentId?: string;
  climate?: string;
  culture?: string;
  description?: string;
}

/** 势力数据 */
export interface FactionData {
  id: string;
  name: string;
  aliases?: string;
  type?: string;
  baseId?: string;
  base?: { id: string; name: string };
  description?: string;
}

/** 术语数据 */
export interface GlossaryData {
  id: string;
  term: string;
  definition: string;
  category?: string;
}

/** 伏笔数据 */
export interface ForeshadowingData {
  id: string;
  name: string;
  plantedAt?: string;
  plantedContent?: string;
  expectedPayoff?: string;
  payoffAt?: string;
  status: "active" | "paid_off" | "abandoned";
}

/** 参考资料数据 */
export interface ReferenceData {
  id: string;
  title: string;
  type: string;
  content: string;
}

// ============================================
// Agent 更新类型（原在 types.ts，现统一至此）
// ============================================

/** 字段变更描述 */
export interface FieldChange {
  field: string;
  operation: "add" | "remove" | "update";
  oldValue?: string;
  newValue?: string;
}

export interface CharacterAdjustment {
  action: 'create' | 'update' | 'delete';
  characterId?: string;
  id?: string;
  name: string;
  aliases?: string;
  gender?: string;
  age?: string;
  identity?: string;
  personality?: string;
  appearance?: string;
  background?: string;
  coreDesire?: string;
  behaviorBoundaries?: string;
  speechStyle?: string;
  relationshipPrinciples?: string;
  shortTermGoal?: string;
  factionId?: string;
  powerLevel?: string;
  combatAbility?: string;
  specialSkills?: string;
  currentStatus?: CharacterStatusType;
  statusNote?: string;
  fieldChanges?: FieldChange[];
}

export interface LocationAdjustment {
  action: 'create' | 'update' | 'delete';
  locationId?: string;
  id?: string;
  name: string;
  aliases?: string;
  type?: string;
  parentId?: string;
  description?: string;
  climate?: string;
  culture?: string;
  fieldChanges?: FieldChange[];
}

export interface ItemAdjustment {
  action: 'create' | 'update' | 'delete';
  itemId?: string;
  id?: string;
  name: string;
  aliases?: string;
  type?: string;
  rarity?: string;
  effect?: string;
  description?: string;
  origin?: string;
  ownerId?: string;
  fieldChanges?: FieldChange[];
}

export interface FactionAdjustment {
  action: 'create' | 'update' | 'delete';
  factionId?: string;
  id?: string;
  name: string;
  aliases?: string;
  type?: string;
  baseId?: string;
  description?: string;
  fieldChanges?: FieldChange[];
}

export interface GlossaryAdjustment {
  action: 'create' | 'update' | 'delete';
  glossaryId?: string;
  id?: string;
  term: string;
  definition: string;
  category?: string;
  fieldChanges?: FieldChange[];
}

export interface CharacterExperienceAdjustment {
  action: 'create' | 'update' | 'delete';
  id?: string;
  characterId?: string;
  characterName?: string;
  chapterId?: string;
  chapterTitle?: string;
  content: string;
  order?: number;
}

export interface ReferenceAdjustment {
  action: 'create' | 'update' | 'delete';
  referenceId?: string;
  title: string;
  type?: string;
  content?: string;
}

export interface ForeshadowingUpdate {
  action: 'create' | 'update' | 'payoff' | 'abandon';
  id?: string;
  name: string;
  plantedAt?: string;
  plantedContent?: string;
  expectedPayoff?: string;
  payoffAt?: string;
  payoffNote?: string;
}

export interface OutlineUpdate {
  nodeId: string;
  status: 'planned' | 'in_progress' | 'completed' | 'skipped';
  actualWordCount?: number;
}

export interface OutlineAdjustment {
  action: 'create' | 'update' | 'delete';
  nodeId?: string;
  nodeTitle?: string;
  title?: string;
  content?: string;
  kind?: 'stage' | 'plot_unit' | 'chapter_group';
  parentId?: string;
  status?: 'planned' | 'in_progress' | 'completed' | 'skipped';
  estimatedWordCount?: number;
  actualWordCount?: number;
}

/** Agent 建议的数据更新（P1-2：从共享契约导入） */
import type { AgentUpdates, AgentUpdateSection } from "@/shared/contracts/agent-updates";
export type { AgentUpdates, AgentUpdateSection };

// ============================================
// 完整状态定义
// ============================================

/**
 * LangGraph工作流完整状态（v5.3 五Agent架构）
 */
export interface WritingState {
  // === 任务元信息 ===
  taskId: string;
  userId: string;
  novelId: string;
  chapterId: string;
  targetWordCount: number;

  // === 当前阶段 ===
  phase: WritingPhase;

  // === 用户交互 ===
  userMessage: string;
  pendingUserResponse: boolean;

  // === 对话历史（核心新增，用于Agent间上下文共享）===
  conversationHistory: AgentMessage[];

  // === 当前活跃Agent ===
  activeAgent: CoreAgentId | null;

  // === 当前创作操作 ===
  currentOperation?: CreativeOperation | null;
  operationMode?: "legacy_agent_graph" | "operation_graph";
  operationStage?: string | null;

  // === 各Agent输出 ===
  loreAdvisorOutput: AgentOutput | null;  // 设定顾问
  plotAdvisorOutput: AgentOutput | null;   // 剧情顾问
  writerOutput: AgentOutput | null;       // 作家
  validatorOutput: AgentOutput | null;   // 校验员
  editorOutput: AgentOutput | null;      // 网文编辑

  // === 阶段产物 ===
  generatedContent: string;  // 作家生成的正文
  pendingUpdates: AgentUpdates | null;    // 待保存的变更

  // === 数据库上下文 ===
  novelData: NovelData;

  // === Agent间调用 ===
  pendingAgentCall: PendingAgentCall | null;

  // === 错误信息 ===
  errorMessage: string | null;

  // === 流式/事件回调（内部使用，不序列化） ===
  streamCallbacks: Record<string, (chunk: string) => void>;
  eventCallbacks?: Record<string, (type: string, payload: Record<string, unknown>) => void>;

  // === 质量检查（Phase 7 P1 修复：精确匹配 checkId） ===
  qualityCheckId?: string | null;

  // === 控制事件（Phase 2：AgentRuntime control tool 产出） ===
  controlEvents?: AgentControlEvent[];

  // === 待审核中间层（ReviewArtifact） ===
  activeArtifactId?: string | null;
  artifactMode?: "none" | "review_loop";
  reviewerAgent?: CoreAgentId | null;
  reviserAgent?: CoreAgentId | null;
  artifactIteration?: number;
  maxArtifactIterations?: number;
}

// ============================================
// 便捷类型
// ============================================

/** Agent输出字段映射 */
export type AgentOutputField = "loreAdvisorOutput" | "plotAdvisorOutput" | "writerOutput" | "validatorOutput" | "editorOutput";

/** Agent ID到输出字段的映射 */
export const AGENT_TO_OUTPUT_FIELD: Record<CoreAgentId, AgentOutputField> = {
  "设定": "loreAdvisorOutput",
  "剧情": "plotAdvisorOutput",
  "写作": "writerOutput",
  "校验": "validatorOutput",
  "编辑": "editorOutput",
};

/** 输出字段到Agent ID的反向映射 */
export const OUTPUT_FIELD_TO_AGENT: Record<AgentOutputField, CoreAgentId> = {
  loreAdvisorOutput: "设定",
  plotAdvisorOutput: "剧情",
  writerOutput: "写作",
  validatorOutput: "校验",
  editorOutput: "编辑",
};

// ============================================
// 辅助函数
// ============================================

/**
 * 获取Agent输出字段名
 */
export function getAgentOutputField(agentId: CoreAgentId): AgentOutputField {
  return AGENT_TO_OUTPUT_FIELD[agentId];
}

/**
 * 根据AgentId获取对应的输出字段值
 */
export function getAgentOutput(state: WritingState, agentId: CoreAgentId): AgentOutput | null {
  const field = getAgentOutputField(agentId);
  return state[field];
}

/**
 * 根据AgentId设置对应的输出字段值（返回新状态）
 */
export function setAgentOutput(
  state: WritingState,
  agentId: CoreAgentId,
  output: AgentOutput
): WritingState {
  const field = getAgentOutputField(agentId);
  return { ...state, [field]: output };
}

/**
 * 生成唯一ID
 */
export function generateMessageId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * 创建Agent输出
 */
export function createAgentOutput(
  agentId: CoreAgentId,
  content: string,
  options?: AgentOutputOptions
): AgentOutput {
  return {
    agentId,
    agentName: AGENT_NAMES[agentId],
    content,
    ...options,
  };
}

/**
 * 判断是否为有效的Agent ID
 */
export function isValidAgentId(id: string): id is CoreAgentId {
  return CORE_AGENT_IDS.includes(id as CoreAgentId);
}

/**
 * 获取Agent中文名
 */
export function getAgentName(agentId: CoreAgentId): string {
  return AGENT_NAMES[agentId];
}
