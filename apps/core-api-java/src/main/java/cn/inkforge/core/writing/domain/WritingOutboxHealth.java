package cn.inkforge.core.writing.domain;

/** Outbox 阻塞和过期积压计数。 */
public record WritingOutboxHealth(long blockedCount, long staleUnpublishedCount) {}
