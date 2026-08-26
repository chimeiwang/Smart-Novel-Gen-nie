package cn.inkforge.core.video.application;

import java.time.OffsetDateTime;

/** 视频项目的持久化快照。 */
public record VideoProjectSnapshot(
        String id,
        String novelId,
        String title,
        String mode,
        String status,
        String targetAspectRatio,
        String targetLanguage,
        String provider,
        int revision,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
