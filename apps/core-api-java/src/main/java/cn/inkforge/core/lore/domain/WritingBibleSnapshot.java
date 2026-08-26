package cn.inkforge.core.lore.domain;

import java.time.OffsetDateTime;

/** 长篇作品圣经的公共可观察快照。 */
public record WritingBibleSnapshot(
        String id,
        String storyLengthProfile,
        Integer targetTotalWordCount,
        String genre,
        String targetReaders,
        String coreSellingPoint,
        String readerPromise,
        String appealModel,
        String taboo,
        String comparableTitles,
        String notes,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
