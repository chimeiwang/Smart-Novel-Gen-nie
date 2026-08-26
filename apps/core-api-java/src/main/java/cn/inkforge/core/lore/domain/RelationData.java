package cn.inkforge.core.lore.domain;

/** 人物关系创建字段。 */
public record RelationData(
        String characterId,
        String targetId,
        String relationType,
        int intimacy,
        String description,
        String startDate,
        String endDate) {}
