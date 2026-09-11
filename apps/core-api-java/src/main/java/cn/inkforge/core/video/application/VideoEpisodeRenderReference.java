package cn.inkforge.core.video.application;

/** 独立剧集任务从制作基线冻结的一份视觉参考，不含短时传输 URL。 */
public record VideoEpisodeRenderReference(
        int ordinal,
        String canonVersionId,
        String canonContentHash,
        String assetId,
        String sha256,
        String mimeType,
        String duty,
        int strength) {}
