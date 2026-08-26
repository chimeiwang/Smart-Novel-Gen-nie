package cn.inkforge.core.quality.domain;

/** 已耐久保存、可重复投递的质量检查身份与最小路由上下文。 */
public record QualityDispatchRecord(
        String runId,
        String checkId,
        String userId,
        String novelId,
        String chapterId,
        String sourceTaskId,
        String message) {}
