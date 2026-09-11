package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.http.ApiException;
import java.util.Objects;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 独立分集后期用例；写入和 FFmpeg 调度继续服从视频开关与媒体工具门禁。 */
public final class VideoEpisodePostProductionService {
    private final VideoEpisodePostProductionRepository repository;
    private final VideoAssetStore storage;
    private final VideoPostProductionMediaProcessor media;
    private final boolean enabled;

    public VideoEpisodePostProductionService(
            VideoEpisodePostProductionRepository repository,
            VideoAssetStore storage,
            VideoPostProductionMediaProcessor media,
            boolean enabled) {
        this.repository = Objects.requireNonNull(repository);
        this.storage = Objects.requireNonNull(storage);
        this.media = Objects.requireNonNull(media);
        this.enabled = enabled;
    }

    public ObjectNode createEditVersion(
            String userId, String episodeId, String baselineId, JsonNode request) {
        requireEnabled();
        return repository.createEditVersion(userId, episodeId, baselineId, request);
    }

    public ObjectNode listEditVersions(
            String userId,
            String episodeId,
            String baselineId,
            Integer beforeVersionNo,
            int limit) {
        return repository.listEditVersions(
                userId, episodeId, baselineId, beforeVersionNo, limit);
    }

    public ObjectNode getEditVersion(
            String userId, String episodeId, String baselineId, String versionId) {
        return repository.getEditVersion(userId, episodeId, baselineId, versionId);
    }

    public ObjectNode createMixVersion(
            String userId, String episodeId, String baselineId, JsonNode request) {
        requireEnabled();
        return repository.createMixVersion(userId, episodeId, baselineId, request);
    }

    public ObjectNode listMixVersions(
            String userId,
            String episodeId,
            String baselineId,
            Integer beforeVersionNo,
            int limit) {
        return repository.listMixVersions(
                userId, episodeId, baselineId, beforeVersionNo, limit);
    }

    public ObjectNode getMixVersion(
            String userId, String episodeId, String baselineId, String versionId) {
        return repository.getMixVersion(userId, episodeId, baselineId, versionId);
    }

    public ObjectNode createExportTask(
            String userId, String episodeId, String baselineId, JsonNode request) {
        requireEnabled();
        requireMediaReady();
        return repository.createExportTask(userId, episodeId, baselineId, request);
    }

    public ObjectNode retryExportTask(
            String userId,
            String episodeId,
            String baselineId,
            String taskId,
            JsonNode request) {
        requireEnabled();
        requireMediaReady();
        return repository.retryExportTask(userId, episodeId, baselineId, taskId, request);
    }

    public ObjectNode getExportTask(
            String userId, String episodeId, String baselineId, String taskId) {
        return repository.getExportTask(userId, episodeId, baselineId, taskId);
    }

    public ObjectNode getDelivery(
            String userId, String episodeId, String baselineId, String exportId) {
        return repository.getDelivery(userId, episodeId, baselineId, exportId);
    }

    public ResolvedVideoAsset getDeliveryFile(
            String userId, String episodeId, String baselineId, String exportId) {
        VideoAssetFile asset =
                repository.getDeliveryFile(userId, episodeId, baselineId, exportId);
        return new ResolvedVideoAsset(
                storage.resolve(asset.storageKey()), asset.mimeType(), asset.name());
    }

    private void requireEnabled() {
        if (!enabled) {
            throw new ApiException(403, "VIDEO_PREVIEW_DISABLED", "当前环境未开放视频制作");
        }
    }

    private void requireMediaReady() {
        if (!media.readiness().ready()) {
            throw new ApiException(
                    503,
                    "VIDEO_MEDIA_TOOLS_UNAVAILABLE",
                    "当前环境缺少 ffmpeg 或 ffprobe，不能执行整集导出");
        }
    }
}
