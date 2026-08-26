/**
 * 一致性终检的 PostgreSQL 权威实现与 Spring 装配。
 *
 * <p>{@code WorkflowRun} 冻结本次检查输入，{@code ChapterQualityCheck} 只反映最新且来源仍有效的公开结果。
 * Redis 投递成功不代表检查完成；旧运行和旧正文的延迟回调只能收敛自身，不能覆盖当前检查项。
 */
package cn.inkforge.core.quality.infrastructure;
