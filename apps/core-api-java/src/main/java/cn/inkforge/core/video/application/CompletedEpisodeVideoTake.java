package cn.inkforge.core.video.application;

import java.util.Map;

/** 独立剧集视频和可选尾帧均已归档，等待与唯一 Take 原子落库。 */
public record CompletedEpisodeVideoTake(
        String assetId,
        StoredVideoAsset stored,
        Map<String, Object> providerMetadata,
        int durationMs,
        ArchivedVideoFrame lastFrame) {

    public CompletedEpisodeVideoTake {
        providerMetadata = java.util.Collections.unmodifiableMap(
                new java.util.LinkedHashMap<>(providerMetadata));
        if (durationMs <= 0) throw new IllegalArgumentException("归档视频必须具有实测正时长");
    }
}
