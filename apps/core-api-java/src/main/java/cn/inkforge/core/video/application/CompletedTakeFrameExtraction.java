package cn.inkforge.core.video.application;

/** FFmpeg 已产出图片后，等待与来源事实原子落库的抽帧结果。 */
public record CompletedTakeFrameExtraction(
        String userId,
        TakeFrameSource source,
        String assetId,
        String name,
        int timestampMs,
        String clientRequestId,
        String requestHash,
        StoredVideoAsset stored) {}
