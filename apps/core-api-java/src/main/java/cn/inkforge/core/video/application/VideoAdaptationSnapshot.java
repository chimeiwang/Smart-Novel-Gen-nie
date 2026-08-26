package cn.inkforge.core.video.application;

import java.time.OffsetDateTime;

/** 章节改编根及其正式版本 Head 的基础快照。 */
public record VideoAdaptationSnapshot(
        String id,
        String projectId,
        String novelId,
        String chapterId,
        String chapterTitle,
        OffsetDateTime chapterUpdatedAt,
        String sourceText,
        String sourceHash,
        String lifecycleStatus,
        int headRevision,
        OffsetDateTime createdAt) {}
