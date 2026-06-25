/**
 * Agent 类型定义模块
 *
 * @module agents/types
 * @description 定义 Agent 接口和类型。数据模型类型统一从 graph/state.ts 导入。
 */

// 数据模型类型统一从 state.ts 导入（单一数据源）
export type {
  CharacterData,
  ItemData,
  LocationData,
  FactionData,
  GlossaryData,
  ForeshadowingData,
  ReferenceData,
  OutlineNodeData,
  PlotProgressData,
  CharacterRelationData,
  CharacterStatusType,
  RelationTypeValue,
  // Agent 更新相关
  AgentUpdates,
  CharacterAdjustment,
  LocationAdjustment,
  ItemAdjustment,
  FactionAdjustment,
  GlossaryAdjustment,
  ReferenceAdjustment,
  ForeshadowingUpdate,
  OutlineUpdate,
  OutlineAdjustment,
  FieldChange,
  QualityScores,
} from "./graph/state";

export type { AgentMeta } from "@/shared/contracts/agent";

/**
 * Agent 执行上下文
 */
export interface AgentContext {
  novelId: string;
  chapterId: string;
  targetWordCount: number;
  selectedAgents: string[];
  previousOutputs: Record<string, AgentResult>;
  novelData: NovelWithContext;
  hostIntent?: { target?: string } | null;
}

/**
 * 小说聚合数据结构（Phase 5：contract alias）
 * 聚合函数返回此类型，调用方 spread 补充 novelId/chapterId
 */
// 聚合函数返回值：novelId/chapterId 可选（lightweight 版本提供，full 版本不提供，由调用方补充）
import type { NovelContext } from "@/shared/contracts/novel-context";
export type NovelWithContext = Omit<NovelContext, "novelId" | "chapterId"> & {
  novelId?: string;
  chapterId?: string;
};

/**
 * Agent 执行结果
 */
export interface AgentResult {
  agentId: string;
  content: string;
  suggestions?: string[];
  scores?: import("./graph/state").QualityScores;
  qualityGate?: "pass" | "revise" | "rewrite";
  rewriteBrief?: string;
  intent?: HostIntent;
}

/**
 * 主持人意图
 */
export interface HostIntent {
  action: "discuss" | "generate" | "save" | "create_character" | "create_location" |
         "create_foreshadowing" | "create_outline" | "create_item" | "create_faction" |
         "create_glossary" | "create_reference" | "complete";
  target?: "character" | "location" | "foreshadowing" | "outline" | "item" | "faction" | "glossary" | "reference" | "world" | "background";
  description?: string;
}

/**
 * Agent 思考/操作状态事件
 */
export interface AgentStatusEvent {
  status: "understanding" | "thinking" | "asking" | "discussing" | "drafting" | "refining" | "querying" | "responding" | "parsing" | "suggestions" | "completed" | "done" | "error";
  message: string;
  question?: string;
  targetType?: string;
  targetName?: string;
  changes?: string;
  context?: string[];
  error?: string;
  toolName?: string;
  argsSummary?: string;
  detailsHidden?: boolean;
}

/**
 * HostAgent 编排事件类型
 */
export type OrchestrationEvent =
  | { type: 'phase_start'; phase: 'planning' | 'generation' | 'recording'; agents: string[] }
  | { type: 'agent_start'; agentId: string; agentName: string }
  | { type: 'agent_chunk'; agentId: string; chunk: string }
  | { type: 'agent_done'; agentId: string; result?: AgentResult; content?: string; scores?: import("./graph/state").QualityScores; qualityGate?: "pass" | "revise" | "rewrite"; rewriteBrief?: string }
  | { type: 'agent_status'; agentId: string } & Partial<AgentStatusEvent>
  | { type: 'user_input_required'; phase: string; content: string; generatedContent?: string; pendingUpdates?: import("./graph/state").AgentUpdates | null; options?: string[] }
  | { type: 'host_intent'; intent: { action: string; reason?: string } };

/**
 * HostAgent 编排结果类型
 */
export interface OrchestrationResult {
  outputs: Record<string, AgentResult>;
  finalContent: string;
}

/**
 * 角色变更描述（旧版，用于 lore-analyzer）
 */
export interface CharacterChange {
  characterId: string;
  changeType: string;
  description: string;
  beforeState?: string;
  afterState: string;
}

/**
 * 新地点描述（旧版）
 */
export interface LocationNew {
  name: string;
  type?: string;
  description?: string;
}
