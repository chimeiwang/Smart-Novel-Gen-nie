package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.http.ApiException;
import java.util.Objects;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 视频 P2 应用边界；关闭视频时仍允许读取历史分镜和制作基线。 */
public final class VideoEpisodeProductionService {
    private final VideoEpisodeProductionRepository repository;
    private final boolean enabled;

    public VideoEpisodeProductionService(
            VideoEpisodeProductionRepository repository, boolean enabled) {
        this.repository = Objects.requireNonNull(repository);
        this.enabled = enabled;
    }

    public ObjectNode capabilities() {
        return repository.capabilities();
    }

    public ObjectNode getStoryboardDraft(String userId, String episodeId) {
        return repository.getStoryboardDraft(userId, episodeId);
    }

    public ObjectNode saveStoryboardDraft(String userId, String episodeId, JsonNode request) {
        requireEnabled();
        return repository.saveStoryboardDraft(userId, episodeId, request);
    }

    public ObjectNode prepareStoryboardConfirmation(
            String userId, String episodeId, JsonNode request) {
        requireEnabled();
        return repository.prepareStoryboardConfirmation(userId, episodeId, request);
    }

    public ObjectNode getStoryboardConfirmation(
            String userId, String episodeId, String artifactId) {
        return repository.getStoryboardConfirmation(userId, episodeId, artifactId);
    }

    public ObjectNode approveStoryboardConfirmation(
            String userId, String episodeId, String artifactId, JsonNode request) {
        requireEnabled();
        return repository.approveStoryboardConfirmation(userId, episodeId, artifactId, request);
    }

    public ObjectNode listStoryboardVersions(
            String userId, String episodeId, Integer beforeVersionNo, int limit) {
        return repository.listStoryboardVersions(userId, episodeId, beforeVersionNo, limit);
    }

    public ObjectNode getStoryboardVersion(String userId, String episodeId, String versionId) {
        return repository.getStoryboardVersion(userId, episodeId, versionId);
    }

    public ObjectNode createTakeAdoption(String userId, String episodeId, JsonNode request) {
        requireEnabled();
        return repository.createTakeAdoption(userId, episodeId, request);
    }

    public ObjectNode getTakeAdoption(String userId, String episodeId, String adoptionId) {
        return repository.getTakeAdoption(userId, episodeId, adoptionId);
    }

    public ObjectNode listTakeCandidates(
            String userId,
            String episodeId,
            String targetShotVersionId,
            String beforeTakeId,
            int limit) {
        return repository.listTakeCandidates(
                userId, episodeId, targetShotVersionId, beforeTakeId, limit);
    }

    public ObjectNode createProductionBaseline(
            String userId, String episodeId, JsonNode request) {
        requireEnabled();
        return repository.createProductionBaseline(userId, episodeId, request);
    }

    public ObjectNode listProductionBaselines(
            String userId, String episodeId, Integer beforeVersionNo, int limit) {
        return repository.listProductionBaselines(userId, episodeId, beforeVersionNo, limit);
    }

    public ObjectNode getProductionBaseline(
            String userId, String episodeId, String baselineId) {
        return repository.getProductionBaseline(userId, episodeId, baselineId);
    }

    private void requireEnabled() {
        if (!enabled) {
            throw new ApiException(403, "VIDEO_PREVIEW_DISABLED", "当前环境未开放视频制作");
        }
    }
}
