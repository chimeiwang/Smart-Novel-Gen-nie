package cn.inkforge.core.video.application;

/** 已持有 PostgreSQL 租约的一次整集 FFmpeg 导出工作。 */
public record EpisodeExportClaim(
        String taskId, String projectId, VideoEpisodeExportManifest manifest) {}
