/**
 * 写作闭环工作流服务（Phase 7）
 *
 * @module agents/lib/writing-workflow-service
 * @description Phase 7 核心：从聊天式协作升级为受控生产流水线。
 *
 * 标准流水线：
 *   本章目标 → Beat Plan（剧情顾问）→ 作者确认 → 作家生成 →
 *   校验员检查 → 编辑商业评审 → 编辑技法评审 → 质量门禁 → 同步设定
 *
 * @phase Phase 7 — 写作闭环工作流
 */

import type { CoreAgentId, AgentOutput, WritingState } from "../graph/state";

// ============================================
// Beat Plan 类型
// ============================================

/** 节拍（一个剧情单元） */
export interface StoryBeat {
  /** 序号 */
  order: number;
  /** 节拍目标（本拍要达成的叙事目标） */
  goal: string;
  /** 冲突设计 */
  conflict?: string;
  /** 涉及角色 */
  characters: string[];
  /** 预期字数 */
  estimatedWords: number;
  /** 涉及伏笔 */
  foreshadowingRefs?: string[];
  /** 验收标准 */
  acceptanceCriteria: string;
}

/** Beat Plan — 本章的剧情节拍规划 */
export interface BeatPlan {
  /** 本章写作目标 */
  chapterGoal: string;
  /** 与主线的关系 */
  mainPlotConnection: string;
  /** 节拍列表 */
  beats: StoryBeat[];
  /** 本章整体验收标准 */
  chapterAcceptanceCriteria: string;
  /** 预计总字数 */
  totalEstimatedWords: number;
  /** 剧情顾问生成时间 */
  generatedAt: number;
}

// ============================================
// 写作目标
// ============================================

/** 本章写作目标（作者输入） */
export interface ChapterWritingGoal {
  /** 本章要完成的叙事目标 */
  narrativeGoal: string;
  /** 希望传达的情绪/体验 */
  desiredEmotion?: string;
  /** 必须处理的伏笔 */
  requiredForeshadowing?: string[];
  /** 必须出场的角色 */
  requiredCharacters?: string[];
  /** 字数范围 */
  wordCountRange?: { min: number; max: number };
  /** 特殊要求 */
  specialNotes?: string;
}

// ============================================
// 质量门禁
// ============================================

/** 质量门禁配置 */
export interface QualityGateConfig {
  /** overall >= passThreshold → pass */
  passThreshold: number;
  /** overall >= reviseThreshold → revise */
  reviseThreshold: number;
  /** 单维度最低分（低于此分视为严重问题） */
  minimumDimensionScore: number;
  /** 是否启用自动重新生成 */
  autoRewrite: boolean;
  /** 最大重试次数 */
  maxRetries: number;
}

/** 默认质量门禁配置 */
export const DEFAULT_QUALITY_GATE: QualityGateConfig = {
  passThreshold: 7,
  reviseThreshold: 5,
  minimumDimensionScore: 4,
  autoRewrite: false,
  maxRetries: 2,
};

/**
 * 判断质量门禁结果
 */
export function evaluateQualityGate(
  scores: {
    hook?: number;
    tension?: number;
    payoff?: number;
    pacing?: number;
    endingHook?: number;
    readerPromise?: number;
    overall?: number;
  },
  config: QualityGateConfig = DEFAULT_QUALITY_GATE
): { verdict: "pass" | "revise" | "rewrite"; reasons: string[] } {
  const reasons: string[] = [];
  const overall = scores.overall ?? 0;

  // 单维度最低分检查
  const dimensions = [
    { key: "hook", name: "开篇钩子", value: scores.hook },
    { key: "tension", name: "冲突张力", value: scores.tension },
    { key: "payoff", name: "爽点兑现", value: scores.payoff },
    { key: "pacing", name: "节奏控制", value: scores.pacing },
    { key: "endingHook", name: "章节尾钩", value: scores.endingHook },
    { key: "readerPromise", name: "读者承诺", value: scores.readerPromise },
  ];

  for (const dim of dimensions) {
    if (dim.value !== undefined && dim.value < config.minimumDimensionScore) {
      reasons.push(`${dim.name}: ${dim.value}（低于最低分 ${config.minimumDimensionScore}）`);
    }
  }

  if (overall >= config.passThreshold && reasons.length === 0) {
    return { verdict: "pass", reasons: [] };
  }

  if (overall >= config.reviseThreshold) {
    reasons.unshift(`整体评分 ${overall}，需修改（阈值 ${config.passThreshold}）`);
    return { verdict: "revise", reasons };
  }

  reasons.unshift(`整体评分 ${overall}，需重写（阈值 ${config.reviseThreshold}）`);
  return { verdict: "rewrite", reasons };
}

// ============================================
// 工作流阶段
// ============================================

/** 写作流水线阶段 */
export type WorkflowStage =
  | "idle"
  | "goal_defined"        // 作者已定义本章目标
  | "beat_plan_generating" // 剧情顾问生成 beat plan
  | "beat_plan_review"     // 等待作者确认 beat plan
  | "writing"              // 作家生成正文
  | "consistency_check"    // 校验员检查
  | "editorial_review"     // 编辑商业评审
  | "craft_review"         // 编辑技法评审
  | "quality_gate"         // 质量门禁判断
  | "done"                 // 通过
  | "revising"             // 返工修改中
  | "lore_sync";           // 同步设定/伏笔/进度

/** 工作流状态 */
export interface WorkflowState {
  currentStage: WorkflowStage;
  writingGoal?: ChapterWritingGoal;
  beatPlan?: BeatPlan;
  retryCount: number;
  stageResults: Record<string, AgentOutput>;
  qualityGateConfig: QualityGateConfig;
}

// ============================================
// 管道编排
// ============================================

/**
 * 获取下一阶段
 */
export function getNextStage(current: WorkflowStage): WorkflowStage | null {
  const pipeline: WorkflowStage[] = [
    "goal_defined",
    "beat_plan_generating",
    "beat_plan_review",
    "writing",
    "consistency_check",
    "editorial_review",
    "craft_review",
    "quality_gate",
    "done",
  ];

  const idx = pipeline.indexOf(current);
  if (idx < 0 || idx >= pipeline.length - 1) return null;
  return pipeline[idx + 1];
}

/**
 * 获取当前阶段应调用的 Agent
 */
export function getAgentForStage(stage: WorkflowStage): CoreAgentId | null {
  const map: Partial<Record<WorkflowStage, CoreAgentId>> = {
    beat_plan_generating: "剧情",
    writing: "写作",
    consistency_check: "校验",
    editorial_review: "编辑",
    craft_review: "编辑",
    lore_sync: "设定",
  };
  return map[stage] ?? null;
}

/**
 * 生成 Beat Plan 专用提示词
 */
export function buildBeatPlanPrompt(goal: ChapterWritingGoal): string {
  let prompt = "@剧情 ";
  prompt += `请为此章生成 Beat Plan（节拍规划）。\n\n`;
  prompt += `## 本章目标\n${goal.narrativeGoal}\n\n`;

  if (goal.desiredEmotion) {
    prompt += `## 期望情绪\n${goal.desiredEmotion}\n\n`;
  }

  if (goal.requiredForeshadowing && goal.requiredForeshadowing.length > 0) {
    prompt += `## 必须处理的伏笔\n${goal.requiredForeshadowing.join("、")}\n\n`;
  }

  if (goal.requiredCharacters && goal.requiredCharacters.length > 0) {
    prompt += `## 必须出场的角色\n${goal.requiredCharacters.join("、")}\n\n`;
  }

  if (goal.wordCountRange) {
    prompt += `## 字数范围\n${goal.wordCountRange.min}-${goal.wordCountRange.max} 字\n\n`;
  }

  prompt += `## 输出格式\n请在 content 中输出以下结构的 Beat Plan：\n`;
  prompt += `- 本章目标（1 句话）\n`;
  prompt += `- 与主线的关联\n`;
  prompt += `- 节拍列表（每个节拍包含：目标、冲突、涉及角色、预计字数、验收标准）\n`;
  prompt += `- 本章整体验收标准\n`;
  prompt += `- 预计总字数\n`;

  return prompt;
}

/**
 * 生成技法评审（craft）专用提示词
 */
export function buildCraftReviewPrompt(): string {
  return `@编辑 从作家技法和反流水账角度评审当前章节。

## 评审维度
1. **场景结构**：每个主要场景是否有 目标→阻力→转折→代价→结果→余波（6 要素）
2. **信息控制**：是否有信息差、悬念控制和揭示时机
3. **描写密度**：是否避免连续大段叙述、对话和描写的节奏交替
4. **语言质量**：是否避免重复句式、多余修饰、书面语和口语的区分
5. **视角控制**：是否保持一致的叙事视角，避免视角跳跃
6. **对抗升级**：冲突是否逐级升级而非重复同一模式

## 输出要求
1. 每个维度给出优劣分析和具体建议
2. 严重问题需要其他 Agent 继续处理时，在评审意见中说明问题和建议主责方向，不要自行转交
3. 轻微问题只给建议，不触发返工
4. 给出具体的修改示例（改前 vs 改后）`;
}
