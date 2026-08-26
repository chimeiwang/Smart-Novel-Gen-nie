package cn.inkforge.core.references.domain;

import java.time.OffsetDateTime;

/** 资料正式事实和派生索引状态的公共快照。 */
public record ReferenceSnapshot(
        String id,
        String title,
        String type,
        String content,
        String sourceUrl,
        String ragStatus,
        String contentHash,
        String errorMessage,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
