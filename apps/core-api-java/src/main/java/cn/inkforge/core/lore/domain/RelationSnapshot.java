package cn.inkforge.core.lore.domain;

import java.time.OffsetDateTime;

/** 人物关系的公共可观察快照。 */
public record RelationSnapshot(
        String id,
        String characterId,
        String targetId,
        String relationType,
        int intimacy,
        String description,
        String startDate,
        String endDate,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
