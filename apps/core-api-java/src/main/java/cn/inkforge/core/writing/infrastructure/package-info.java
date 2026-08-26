/**
 * 写作领域的 PostgreSQL、Redis 与 Spring 装配适配器。
 *
 * <p>PostgreSQL 中的任务、命令、Artifact 与 Outbox 是权威事实；Redis Stream 只承担短期观察和重放。
 * 跨表写入通过 {@code CoreDatabase} 加入线程内既有事务，不能在仓储之间自行提交。涉及写作运行的锁顺序固定为
 * 小说、章节/大纲、会话、任务、Artifact、命令和 Outbox，后续实现不得按单个仓储的查询便利调整顺序。
 */
package cn.inkforge.core.writing.infrastructure;
