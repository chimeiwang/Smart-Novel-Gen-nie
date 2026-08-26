package cn.inkforge.core.video.application;

/** 已校验归属、授权、锁定状态和时间范围的 Take 抽帧来源事实。 */
public record TakeFrameSource(
        String takeId,
        String shotId,
        String adaptationId,
        String projectId,
        String novelId,
        String storageKey,
        String sha256,
        Integer durationMs) {}
