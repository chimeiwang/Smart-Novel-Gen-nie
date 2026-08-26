package cn.inkforge.core.writing.domain;

import java.time.OffsetDateTime;
import java.util.Map;

/** Redis Stream 中的写作可见事件。 */
public record WritingEvent(
        String id,
        String event,
        Map<String, Object> data,
        OffsetDateTime occurredAt,
        String sourceEventId,
        Integer sequence) {}
