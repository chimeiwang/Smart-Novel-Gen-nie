package cn.inkforge.core.video.application;

import java.nio.file.Path;

/** 只接受数据库冻结路径与哈希的抽帧、整集渲染媒体边界。 */
public interface VideoPostProductionMediaProcessor {

    MediaToolReadiness readiness();

    StoredVideoAsset extractFrame(
            Path sourcePath,
            String expectedSha256,
            int timestampMs,
            VideoAssetStore storage,
            String projectId,
            String assetId);

    StoredVideoAsset renderEpisode(
            VideoEpisodeExportManifest manifest,
            VideoAssetStore storage,
            String assetId);
}
