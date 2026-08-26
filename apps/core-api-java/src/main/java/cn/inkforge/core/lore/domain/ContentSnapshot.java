package cn.inkforge.core.lore.domain;

import java.time.OffsetDateTime;

/** 单例文本或故事进展的公共可观察快照。 */
public record ContentSnapshot(
        String id,
        String content,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
