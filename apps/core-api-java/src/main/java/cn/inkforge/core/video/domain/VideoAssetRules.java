package cn.inkforge.core.video.domain;

import cn.inkforge.core.platform.http.ApiException;
import java.util.Map;
import java.util.Set;

/** 上传素材职责与模态的共享业务矩阵；最终成片只能由受控导出器创建。 */
public final class VideoAssetRules {

    private static final Map<String, Set<String>> ALLOWED_MODALITIES = Map.ofEntries(
            Map.entry("identity", Set.of("image", "video")),
            Map.entry("costume", Set.of("image", "video")),
            Map.entry("scene", Set.of("image", "video")),
            Map.entry("prop", Set.of("image", "video")),
            Map.entry("style", Set.of("image", "video")),
            Map.entry("storyboard", Set.of("image")),
            Map.entry("keyframe", Set.of("image")),
            Map.entry("motion", Set.of("image", "video")),
            Map.entry("camera", Set.of("video")),
            Map.entry("voice", Set.of("audio")),
            Map.entry("ambience", Set.of("audio")),
            Map.entry("sfx", Set.of("audio")),
            Map.entry("music", Set.of("audio")),
            Map.entry("episode_export", Set.of("video")));

    private VideoAssetRules() {}

    public static void requireUploadCombination(String modality, String duty) {
        if ("episode_export".equals(duty)) {
            throw invalid("episode_export 只能由整集导出任务创建");
        }
        Set<String> allowed = ALLOWED_MODALITIES.get(duty);
        if (allowed == null || !allowed.contains(modality)) {
            throw invalid("素材职责 " + duty + " 不支持 " + modality + " 模态");
        }
    }

    private static ApiException invalid(String message) {
        return new ApiException(
                422,
                "VIDEO_ASSET_DUTY_MODALITY_INVALID",
                message);
    }
}
