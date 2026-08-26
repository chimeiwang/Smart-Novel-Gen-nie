package cn.inkforge.core.video.infrastructure;

import cn.inkforge.contracts.api.ShotRenderKeyframeManifest;
import cn.inkforge.contracts.api.ShotRenderReferenceManifest;
import cn.inkforge.contracts.api.VideoShotRenderManifest;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import tools.jackson.databind.ObjectMapper;

/** 逐镜渲染清单的显式 JSON 投影，避免生成 DTO 的空值策略改变跨语言 inputHash。 */
final class VideoRenderManifestCodec {

    private final ObjectMapper json;

    VideoRenderManifestCodec(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    String serialize(VideoShotRenderManifest manifest) {
        validate(manifest);
        return json.writeValueAsString(map(manifest));
    }

    VideoShotRenderManifest parse(String serialized, String expectedHash) {
        try {
            VideoShotRenderManifest manifest =
                    json.readValue(serialized, VideoShotRenderManifest.class);
            validate(manifest);
            if (!hash(manifest).equals(expectedHash)) {
                throw new IllegalArgumentException("逐镜视频任务 manifest 哈希不一致");
            }
            return manifest;
        } catch (IllegalArgumentException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException("逐镜视频任务 manifest 已损坏", exception);
        }
    }

    String hash(VideoShotRenderManifest manifest) {
        validate(manifest);
        return CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(map(manifest), json));
    }

    Map<String, Object> map(VideoShotRenderManifest manifest) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("schemaVersion", manifest.getSchemaVersion().getValue());
        value.put("adaptationId", manifest.getAdaptationId());
        value.put("projectId", manifest.getProjectId());
        value.put("novelId", manifest.getNovelId());
        value.put("shotId", manifest.getShotId());
        value.put("shotKey", manifest.getShotKey());
        value.put("shotPlanVersionId", manifest.getShotPlanVersionId());
        value.put("promptVersionId", manifest.getPromptVersionId());
        value.put("promptContentHash", manifest.getPromptContentHash());
        value.put("promptText", manifest.getPromptText());
        value.put("providerPromptText", manifest.getProviderPromptText());
        value.put("sourceTimelineDurationMs", manifest.getSourceTimelineDurationMs());
        value.put("provider", manifest.getProvider());
        value.put("model", manifest.getModel());
        value.put("ratio", manifest.getRatio().getValue());
        value.put("durationSeconds", manifest.getDurationSeconds());
        value.put("resolution", manifest.getResolution().getValue());
        value.put("generateAudio", manifest.getGenerateAudio());
        value.put("watermark", manifest.getWatermark());
        value.put("references", list(manifest.getReferences()).stream()
                .map(VideoRenderManifestCodec::referenceMap)
                .toList());
        value.put("keyframes", list(manifest.getKeyframes()).stream()
                .map(VideoRenderManifestCodec::keyframeMap)
                .toList());
        return value;
    }

    private static void validate(VideoShotRenderManifest manifest) {
        if (manifest == null
                || manifest.getSchemaVersion() == null
                || manifest.getReferences() != null && manifest.getReferences().size() > 20
                || manifest.getKeyframes() != null && manifest.getKeyframes().size() > 3) {
            throw new IllegalArgumentException("逐镜视频任务 manifest 无效");
        }
        List<ShotRenderKeyframeManifest> keyframes = list(manifest.getKeyframes());
        if (manifest.getSchemaVersion()
                == VideoShotRenderManifest.SchemaVersionEnum.VIDEO_SHOT_RENDER_MANIFEST_1_0) {
            if (manifest.getProviderPromptText() != null || !keyframes.isEmpty()) {
                throw new IllegalArgumentException("1.0 清单不能携带 P1 关键帧字段");
            }
            return;
        }
        if (!keyframes.isEmpty() && manifest.getProviderPromptText() == null) {
            throw new IllegalArgumentException("带关键帧的 1.1 清单必须冻结 providerPromptText");
        }
        long roles = keyframes.stream().map(ShotRenderKeyframeManifest::getRole).distinct().count();
        if (roles != keyframes.size()) {
            throw new IllegalArgumentException("同一渲染清单中的关键帧角色不能重复");
        }
        if (list(manifest.getReferences()).size() + keyframes.size() > 20) {
            throw new IllegalArgumentException("Seedance 单次渲染最多使用 20 份图片输入");
        }
    }

    private static Map<String, Object> referenceMap(ShotRenderReferenceManifest reference) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("ordinal", reference.getOrdinal());
        value.put("canonVersionId", reference.getCanonVersionId());
        value.put("assetId", reference.getAssetId());
        value.put("sha256", reference.getSha256());
        value.put("mimeType", reference.getMimeType());
        value.put("duty", reference.getDuty().getValue());
        value.put("strength", reference.getStrength());
        return value;
    }

    private static Map<String, Object> keyframeMap(ShotRenderKeyframeManifest keyframe) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("ordinal", keyframe.getOrdinal());
        value.put("keyframeVersionId", keyframe.getKeyframeVersionId());
        value.put("role", keyframe.getRole().getValue());
        value.put("assetId", keyframe.getAssetId());
        value.put("sha256", keyframe.getSha256());
        value.put("mimeType", keyframe.getMimeType());
        value.put("duty", keyframe.getDuty().getValue());
        return value;
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : value;
    }
}
