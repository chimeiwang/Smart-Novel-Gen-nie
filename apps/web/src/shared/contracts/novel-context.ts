/**
 * NovelData / 聚合上下文契约（Phase 5：唯一字段来源）
 *
 * @module shared/contracts/novel-context
 * @description Phase 5：消除 NovelWithContext 可选字段差异。
 *  novelId/chapterId 在聚合函数返回值中必填，不再靠 as 强转。
 *
 * @phase Phase 5 — NovelData 聚合上下文统一
 */

import type { WritingState } from "@/agents/graph/state";

/**
 * 聚合上下文（不含 novelId/chapterId）。
 * novelId/chapterId 由 aggregateNovelContext 的参数传入，调用方通过 spread 合并补充。
 */
export type NovelAggregateResult = Omit<WritingState["novelData"], "novelId" | "chapterId">;

/**
 * 完整上下文 = WritingState["novelData"]。
 * novelId/chapterId 为必填。
 */
export type NovelContext = WritingState["novelData"];
