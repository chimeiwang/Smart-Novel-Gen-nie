package cn.inkforge.core.video.application;

import java.time.OffsetDateTime;

/** 不包含受控路径的浏览器可见视频素材快照。 */
public record VideoAssetSnapshot(
        String id,
        String projectId,
        String name,
        String modality,
        String duty,
        String mimeType,
        long byteSize,
        Integer durationMs,
        String sha256,
        String sourceKind,
        String rightsStatus,
        OffsetDateTime lockedAt,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
