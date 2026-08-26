package cn.inkforge.core.novels.domain;

/** 创建小说时必须原子持久化的全部初始事实。 */
public record NovelCreation(
        String userId,
        String clientRequestId,
        String name,
        String summary,
        String storyProgress,
        String storyLengthProfile,
        int targetTotalWordCount,
        String genre,
        String coreSellingPoint,
        String readerPromise,
        String notes,
        String firstChapterTitle,
        int firstChapterOrder,
        String chapterContent,
        String outlineContent,
        String sourceKind,
        String sourceText,
        String currentStage,
        String currentGoal) {}
