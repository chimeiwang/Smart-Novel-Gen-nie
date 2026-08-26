package cn.inkforge.core.video.application;

/** FFmpeg 已完成后等待与导出任务原子登记的成片事实。 */
public record CompletedEpisodeExport(
        String taskId, String assetId, StoredVideoAsset stored, int durationMs) {}
