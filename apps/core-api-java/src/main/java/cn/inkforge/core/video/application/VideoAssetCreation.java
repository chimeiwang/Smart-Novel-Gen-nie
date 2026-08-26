package cn.inkforge.core.video.application;

/** 文件安全落盘后写入 VideoAsset 的完整创建事实。 */
public record VideoAssetCreation(
        String id,
        String name,
        String modality,
        String duty,
        String sourceKind,
        Integer durationMs,
        StoredVideoAsset stored) {}
