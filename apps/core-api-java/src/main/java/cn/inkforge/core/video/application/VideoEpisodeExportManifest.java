package cn.inkforge.core.video.application;

import java.util.List;

/** 整集导出的不可变内部清单；只保存受控 storageKey，不保存服务器绝对路径。 */
public record VideoEpisodeExportManifest(
        String schemaVersion,
        String adaptationId,
        String videoEpisodeId,
        String productionBaselineId,
        String baselineContentHash,
        String scriptVersionId,
        String storyboardVersionId,
        String projectId,
        String novelId,
        String episodePlanVersionId,
        String shotPlanVersionId,
        Integer episodeNo,
        String editVersionId,
        String editContentHash,
        String mixVersionId,
        String mixContentHash,
        String targetAspectRatio,
        String resolution,
        int framesPerSecond,
        boolean burnSubtitles,
        int totalDurationMs,
        FfmpegSettings ffmpeg,
        List<FrozenVideoClip> videoClips,
        List<FrozenAudioClip> audioClips,
        List<FrozenSubtitleCue> subtitleCues) {

    public static final String SCHEMA_VERSION = "video-episode-export-manifest/1.0";
    public static final String NATIVE_SCHEMA_VERSION = "video-episode-native-export-manifest/1.0";

    public VideoEpisodeExportManifest {
        ffmpeg = ffmpeg == null ? FfmpegSettings.productionDefault() : ffmpeg;
        videoClips = List.copyOf(videoClips);
        audioClips = List.copyOf(audioClips);
        subtitleCues = List.copyOf(subtitleCues);
    }

    /** 保留旧章节改编清单的构造形状和字节级序列化，历史任务可以继续收敛。 */
    public VideoEpisodeExportManifest(
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
        this(
                schemaVersion,
                adaptationId,
                null,
                null,
                null,
                null,
                null,
                projectId,
                novelId,
                episodePlanVersionId,
                shotPlanVersionId,
                episodeNo,
                editVersionId,
                editContentHash,
                mixVersionId,
                mixContentHash,
                targetAspectRatio,
                resolution,
                framesPerSecond,
                burnSubtitles,
                totalDurationMs,
                FfmpegSettings.productionDefault(),
                videoClips,
                audioClips,
                subtitleCues);
    }

    public record FfmpegSettings(
            String videoCodec,
            String videoPreset,
            int videoCrf,
            String pixelFormat,
            String audioCodec,
            String audioBitrate,
            boolean fastStart) {

        public static FfmpegSettings productionDefault() {
            return new FfmpegSettings(
                    "libx264", "medium", 20, "yuv420p", "aac", "192k", true);
        }
    }

    public record FrozenAsset(
            String assetId,
            String storageKey,
            String sha256,
            String mimeType,
            Integer durationMs) {}

    public record FrozenVideoClip(
            int ordinal,
            String clipId,
            String adoptionId,
            String shotId,
            String shotVersionId,
            String takeId,
            FrozenAsset asset,
            Integer sourceInMs,
            Integer sourceOutMs,
            int outputDurationMs,
            String sourceAudioMode,
            String transitionAfter,
            int transitionDurationMs) {

        public FrozenVideoClip {
            sourceAudioMode = sourceAudioMode == null ? "keep" : sourceAudioMode;
        }

        public FrozenVideoClip(
                int ordinal,
                String shotId,
                String takeId,
                FrozenAsset asset,
                Integer sourceInMs,
                Integer sourceOutMs,
                int outputDurationMs,
                String transitionAfter,
                int transitionDurationMs) {
            this(
                    ordinal,
                    null,
                    null,
                    shotId,
                    null,
                    takeId,
                    asset,
                    sourceInMs,
                    sourceOutMs,
                    outputDurationMs,
                    "keep",
                    transitionAfter,
                    transitionDurationMs);
        }
    }

    public record FrozenAudioClip(
            int ordinal,
            String trackKind,
            String shotId,
            String shotVersionId,
            FrozenAsset asset,
            int timelineStartMs,
            int sourceInMs,
            int sourceOutMs,
            int gainMillibels,
            int fadeInMs,
            int fadeOutMs) {

        public FrozenAudioClip(
                int ordinal,
                String trackKind,
                String shotId,
                FrozenAsset asset,
                int timelineStartMs,
                int sourceInMs,
                int sourceOutMs,
                int gainMillibels,
                int fadeInMs,
                int fadeOutMs) {
            this(
                    ordinal,
                    trackKind,
                    shotId,
                    null,
                    asset,
                    timelineStartMs,
                    sourceInMs,
                    sourceOutMs,
                    gainMillibels,
                    fadeInMs,
                    fadeOutMs);
        }
    }

    public record FrozenSubtitleCue(
            int ordinal,
            String shotId,
            String shotVersionId,
            String scriptLineId,
            int startMs,
            int endMs,
            String speaker,
            String text) {

        public FrozenSubtitleCue(
                int ordinal,
                String shotId,
                int startMs,
                int endMs,
                String speaker,
                String text) {
            this(ordinal, shotId, null, null, startMs, endMs, speaker, text);
        }
    }
}
