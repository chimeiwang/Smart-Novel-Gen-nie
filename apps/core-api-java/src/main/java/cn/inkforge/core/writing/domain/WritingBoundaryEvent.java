package cn.inkforge.core.writing.domain;

import java.util.Map;

/** 必须与业务状态同事务登记、再异步投递到 Redis Stream 的边界事件。 */
public record WritingBoundaryEvent(
        String sourceEventId,
        int sourceSequence,
        String dedupeKey,
        String eventType,
        Map<String, Object> payload) {}
