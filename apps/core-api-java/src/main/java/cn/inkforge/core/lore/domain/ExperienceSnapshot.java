package cn.inkforge.core.lore.domain;

import java.time.OffsetDateTime;

/** 人物经历的公共可观察快照。 */
public record ExperienceSnapshot(
        String id,
        String characterId,
        String chapterId,
        String content,
        int order,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
