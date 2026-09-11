package cn.inkforge.core.video.application;

/** 独立剧集任务从制作基线冻结的一份关键帧，不含供应商临时传输地址。 */
public record VideoEpisodeRenderKeyframe(
        int ordinal,
        String keyframeVersionId,
        String role,
        String assetId,
        String sha256,
        String mimeType,
        String duty,
        String contentHash) {}
