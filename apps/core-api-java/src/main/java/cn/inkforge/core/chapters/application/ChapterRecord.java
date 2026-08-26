package cn.inkforge.core.chapters.application;

import cn.inkforge.contracts.api.ChapterStatus;
import java.time.OffsetDateTime;

/** 状态迁移后返回给应用层的最小章节快照。 */
public record ChapterRecord(
        String id,
        String novelId,
        ChapterStatus status,
        OffsetDateTime completedAt,
        OffsetDateTime updatedAt) {}
