package cn.inkforge.core.reviews.domain;

import java.time.OffsetDateTime;

/** 面向任务上下文的轻量草案摘要；不暴露正文、diff 或评审明细。 */
public record ReviewArtifactSummary(
        String id,
        String novelId,
        String chapterId,
        String taskId,
        String artifactKey,
        String kind,
        String status,
        String title,
        String summary,
        int revision,
        String updatedByAgent,
        String reviewerAgent,
        OffsetDateTime updatedAt) {}
