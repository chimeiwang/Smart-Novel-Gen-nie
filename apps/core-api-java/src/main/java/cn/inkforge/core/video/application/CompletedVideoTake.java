package cn.inkforge.core.video.application;

import java.util.Map;

/** Seedance 结果已经安全归档、等待与任务在一个事务内形成不可变 Take。 */
public record CompletedVideoTake(
        String assetId,
        StoredVideoAsset stored,
        Map<String, Object> providerMetadata,
        Integer durationMs) {

    public CompletedVideoTake {
        providerMetadata = java.util.Collections.unmodifiableMap(
                new java.util.LinkedHashMap<>(providerMetadata));
    }
}
