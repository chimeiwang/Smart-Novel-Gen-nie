package cn.inkforge.core.writing.domain;

import java.time.LocalDateTime;

/** 已领取租约的写作边界事件。 */
public record WritingOutboxRecord(
        String id,
        String taskId,
        String commandId,
        String sourceEventId,
        int sourceSequence,
        int durableBaseline,
        String dedupeKey,
        String eventType,
        Object payload,
        String deliveryState,
        int attemptCount,
        LocalDateTime nextAttemptAt,
        String leaseToken,
        LocalDateTime leaseExpiresAt) {}
