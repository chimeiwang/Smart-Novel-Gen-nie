package cn.inkforge.core.video.application;

import java.util.List;
import java.util.Map;

/** 从 {@code VideoProductionBaselineShot.inputSnapshotJson} 完整恢复的不可变生成输入。 */
public record VideoEpisodeRenderInput(
        String schemaVersion,
        String shotId,
        String shotVersionId,
        int shotVersionNo,
        String shotContentHash,
        String scriptSceneId,
        List<String> scriptLineIds,
        String provider,
        String model,
        String generationMode,
        String executionMode,
        boolean feeConfirmed,
        String promptVersionId,
        String prompt,
        String ratio,
        int durationSeconds,
        String resolution,
        boolean generateAudio,
        boolean watermark,
        String outputFormat,
        List<VideoEpisodeRenderReference> references,
        List<VideoEpisodeRenderKeyframe> keyframes,
        Map<String, Object> snapshot) {

    public VideoEpisodeRenderInput {
        scriptLineIds = List.copyOf(scriptLineIds);
        references = List.copyOf(references);
        keyframes = List.copyOf(keyframes);
        snapshot = java.util.Collections.unmodifiableMap(new java.util.LinkedHashMap<>(snapshot));
    }
}
