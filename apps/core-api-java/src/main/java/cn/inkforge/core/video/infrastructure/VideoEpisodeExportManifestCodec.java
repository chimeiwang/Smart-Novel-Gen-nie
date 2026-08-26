package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAsset;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAudioClip;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenSubtitleCue;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenVideoClip;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.ObjectMapper;

/** 与 Pydantic model_dump_json 字段顺序一致的整集导出清单编解码器。 */
final class VideoEpisodeExportManifestCodec {

    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private static final Set<String> RATIOS =
            Set.of("16:9", "4:3", "1:1", "3:4", "9:16", "21:9");

    private final ObjectMapper json;

    VideoEpisodeExportManifestCodec(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    String serialize(VideoEpisodeExportManifest manifest) {
        validate(manifest);
        return json.writeValueAsString(map(manifest));
    }

    String hash(VideoEpisodeExportManifest manifest) {
        return CommandIdempotency.sha256(
                serialize(manifest).getBytes(StandardCharsets.UTF_8));
    }

    VideoEpisodeExportManifest parse(String serialized, String expectedHash) {
        try {
            VideoEpisodeExportManifest manifest =
                    json.readValue(serialized, VideoEpisodeExportManifest.class);
            validate(manifest);
            if (!hash(manifest).equals(expectedHash)) {
                throw new IllegalArgumentException("整集导出任务清单哈希不一致");
            }
            return manifest;
        } catch (IllegalArgumentException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException("整集导出任务清单无效", exception);
        }
    }

    Map<String, Object> map(VideoEpisodeExportManifest manifest) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("schemaVersion", manifest.schemaVersion());
        value.put("adaptationId", manifest.adaptationId());
        value.put("projectId", manifest.projectId());
        value.put("novelId", manifest.novelId());
        value.put("episodePlanVersionId", manifest.episodePlanVersionId());
        value.put("shotPlanVersionId", manifest.shotPlanVersionId());
        value.put("episodeNo", manifest.episodeNo());
        value.put("editVersionId", manifest.editVersionId());
        value.put("editContentHash", manifest.editContentHash());
        value.put("mixVersionId", manifest.mixVersionId());
        value.put("mixContentHash", manifest.mixContentHash());
        value.put("targetAspectRatio", manifest.targetAspectRatio());
        value.put("resolution", manifest.resolution());
        value.put("framesPerSecond", manifest.framesPerSecond());
        value.put("burnSubtitles", manifest.burnSubtitles());
        value.put("totalDurationMs", manifest.totalDurationMs());
        value.put("videoClips", manifest.videoClips().stream()
                .map(VideoEpisodeExportManifestCodec::videoMap)
                .toList());
        value.put("audioClips", manifest.audioClips().stream()
                .map(VideoEpisodeExportManifestCodec::audioMap)
                .toList());
        value.put("subtitleCues", manifest.subtitleCues().stream()
                .map(VideoEpisodeExportManifestCodec::subtitleMap)
                .toList());
        return value;
    }

    private static Map<String, Object> assetMap(FrozenAsset asset) {
        if (asset == null) return null;
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("assetId", asset.assetId());
        value.put("storageKey", asset.storageKey());
        value.put("sha256", asset.sha256());
        value.put("mimeType", asset.mimeType());
        value.put("durationMs", asset.durationMs());
        return value;
    }

    private static Map<String, Object> videoMap(FrozenVideoClip clip) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("ordinal", clip.ordinal());
        value.put("shotId", clip.shotId());
        value.put("takeId", clip.takeId());
        value.put("asset", assetMap(clip.asset()));
        value.put("sourceInMs", clip.sourceInMs());
        value.put("sourceOutMs", clip.sourceOutMs());
        value.put("outputDurationMs", clip.outputDurationMs());
        value.put("transitionAfter", clip.transitionAfter());
        value.put("transitionDurationMs", clip.transitionDurationMs());
        return value;
    }

    private static Map<String, Object> audioMap(FrozenAudioClip clip) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("ordinal", clip.ordinal());
        value.put("trackKind", clip.trackKind());
        value.put("shotId", clip.shotId());
        value.put("asset", assetMap(clip.asset()));
        value.put("timelineStartMs", clip.timelineStartMs());
        value.put("sourceInMs", clip.sourceInMs());
        value.put("sourceOutMs", clip.sourceOutMs());
        value.put("gainMillibels", clip.gainMillibels());
        value.put("fadeInMs", clip.fadeInMs());
        value.put("fadeOutMs", clip.fadeOutMs());
        return value;
    }

    private static Map<String, Object> subtitleMap(FrozenSubtitleCue cue) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("ordinal", cue.ordinal());
        value.put("shotId", cue.shotId());
        value.put("startMs", cue.startMs());
        value.put("endMs", cue.endMs());
        value.put("speaker", cue.speaker());
        value.put("text", cue.text());
        return value;
    }

    private static void validate(VideoEpisodeExportManifest manifest) {
        if (manifest == null
                || !VideoEpisodeExportManifest.SCHEMA_VERSION.equals(manifest.schemaVersion())
                || blank(manifest.adaptationId())
                || blank(manifest.projectId())
                || blank(manifest.novelId())
                || blank(manifest.episodePlanVersionId())
                || blank(manifest.shotPlanVersionId())
                || manifest.episodeNo() < 1
                || blank(manifest.editVersionId())
                || !sha(manifest.editContentHash())
                || blank(manifest.mixVersionId())
                || !sha(manifest.mixContentHash())
                || manifest.targetAspectRatio() == null
                || !RATIOS.contains(manifest.targetAspectRatio())
                || manifest.resolution() == null
                || !Set.of("720p", "1080p").contains(manifest.resolution())
                || !Set.of(24, 25, 30).contains(manifest.framesPerSecond())
                || manifest.totalDurationMs() < 1
                || manifest.videoClips() == null
                || manifest.videoClips().isEmpty()
                || manifest.videoClips().size() > 500
                || manifest.audioClips() == null
                || manifest.audioClips().size() > 1_000
                || manifest.subtitleCues() == null
                || manifest.subtitleCues().size() > 2_000) {
            throw new IllegalArgumentException("整集导出任务清单无效");
        }
        for (int index = 0; index < manifest.videoClips().size(); index++) {
            FrozenVideoClip clip = manifest.videoClips().get(index);
            if (clip == null
                    || clip.ordinal() != index + 1
                    || blank(clip.shotId())
                    || clip.outputDurationMs() < 500
                    || clip.outputDurationMs() > 120_000
                    || clip.transitionAfter() == null
                    || !Set.of("cut", "fade_black").contains(clip.transitionAfter())
                    || clip.transitionDurationMs() < 0
                    || clip.transitionDurationMs() > 2_000) {
                throw new IllegalArgumentException("整集导出视频片段无效");
            }
            if (clip.asset() != null) validateAsset(clip.asset());
        }
        for (int index = 0; index < manifest.audioClips().size(); index++) {
            FrozenAudioClip clip = manifest.audioClips().get(index);
            if (clip == null || clip.ordinal() != index + 1) {
                throw new IllegalArgumentException("整集导出音频片段无效");
            }
            validateAsset(clip.asset());
        }
        for (int index = 0; index < manifest.subtitleCues().size(); index++) {
            FrozenSubtitleCue cue = manifest.subtitleCues().get(index);
            if (cue == null
                    || cue.ordinal() != index + 1
                    || cue.startMs() < 0
                    || cue.endMs() <= cue.startMs()
                    || blank(cue.text())) {
                throw new IllegalArgumentException("整集导出字幕无效");
            }
        }
    }

    private static void validateAsset(FrozenAsset asset) {
        if (asset == null
                || blank(asset.assetId())
                || blank(asset.storageKey())
                || !sha(asset.sha256())
                || blank(asset.mimeType())
                || asset.durationMs() != null && asset.durationMs() <= 0) {
            throw new IllegalArgumentException("整集导出素材事实无效");
        }
    }

    private static boolean sha(String value) {
        return value != null && SHA256.matcher(value).matches();
    }

    private static boolean blank(String value) {
        return value == null || value.isEmpty();
    }
}
