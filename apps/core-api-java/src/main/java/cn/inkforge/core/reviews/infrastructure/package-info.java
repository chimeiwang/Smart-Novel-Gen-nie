/**
 * ReviewArtifact 的 PostgreSQL 持久化与正式应用适配器。
 *
 * <p>用户决定必须在同一外层事务中完成来源复核、正式数据写入、Artifact 状态变化和耐久恢复命令创建。
 * Agent 恢复和 Redis/SSE 通知发生在提交之后，不得再次执行正式写入，也不能否定已经提交的决定。
 */
package cn.inkforge.core.reviews.infrastructure;
