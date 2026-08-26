package cn.inkforge.core.video.application;

import java.util.List;

/** 整集导出的不可变内部清单；只保存受控 storageKey，不保存服务器绝对路径。 */
public record VideoEpisodeExportManifest(
        String schemaVersion,
        String adaptationId,
        String projectId,
        String novelId,
        String episodePlanVersionId,
        String shotPlanVersionId,
        int episodeNo,
        String editVersionId,
        String editContentHash,
        String mixVersionId,
        String mixContentHash,
        String targetAspectRatio,
        String resolution,
        int framesPerSecond,
        boolean burnSubtitles,
        int totalDurationMs,
        List<FrozenVideoClip> videoClips,
        List<FrozenAudioClip> audioClips,
        List<FrozenSubtitleCue> subtitleCues) {

    public static final String SCHEMA_VERSION = "video-episode-export-manifest/1.0";

    public VideoEpisodeExportManifest {
        videoClips = List.copyOf(videoClips);
        audioClips = List.copyOf(audioClips);
        subtitleCues = List.copyOf(subtitleCues);
    }

    public record FrozenAsset(
            String assetId,
            String storageKey,
            String sha256,
            String mimeType,
            Integer durationMs) {}

    public record FrozenVideoClip(
            int ordinal,
            String shotId,
            String takeId,
            FrozenAsset asset,
            Integer sourceInMs,
            Integer sourceOutMs,
            int outputDurationMs,
            String transitionAfter,
            int transitionDurationMs) {}

    public record FrozenAudioClip(
            int ordinal,
            String trackKind,
            String shotId,
            FrozenAsset asset,
            int timelineStartMs,
            int sourceInMs,
            int sourceOutMs,
            int gainMillibels,
            int fadeInMs,
            int fadeOutMs) {}

    public record FrozenSubtitleCue(
            int ordinal,
            String shotId,
            int startMs,
            int endMs,
            String speaker,
            String text) {}
}
