package cn.inkforge.core.styles.domain;

import java.time.OffsetDateTime;

/** 画像任务的耐久状态。 */
public record PortraitTaskSnapshot(
        String id,
        String styleId,
        PortraitSection section,
        String status,
        String errorMessage,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
