package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.http.ApiException;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

import java.util.Objects;

/** 独立剧集应用边界；关闭视频时保留历史只读，所有领域写入统一拒绝。 */
public final class VideoEpisodeService {
    private final VideoEpisodeRepository repository;
    private final boolean enabled;

    public VideoEpisodeService(VideoEpisodeRepository repository, boolean enabled) {
        this.repository = Objects.requireNonNull(repository);
        this.enabled = enabled;
    }

    public ObjectNode list(String userId, String projectId) {
        return repository.list(userId, projectId);
    }

    public ObjectNode get(String userId, String episodeId) {
        return repository.get(userId, episodeId);
    }

    public ObjectNode create(String userId, String projectId, JsonNode request) {
        requireEnabled();
        return repository.create(userId, projectId, request);
    }

    public ObjectNode update(String userId, String episodeId, JsonNode request) {
        requireEnabled();
        return repository.update(userId, episodeId, request);
    }

    public ObjectNode reorder(String userId, String projectId, JsonNode request) {
        requireEnabled();
        return repository.reorder(userId, projectId, request);
    }

    public ObjectNode createSourceSet(String userId, String episodeId, JsonNode request) {
        requireEnabled();
        return repository.createSourceSet(userId, episodeId, request);
    }

    public ObjectNode listSourceSets(String userId, String episodeId) {
        return repository.listSourceSets(userId, episodeId);
    }

    public ObjectNode getSourceSet(String userId, String episodeId, String versionId) {
        return repository.getSourceSet(userId, episodeId, versionId);
    }

    public ObjectNode getDraft(String userId, String episodeId) {
        return repository.getDraft(userId, episodeId);
    }

    public ObjectNode saveDraft(String userId, String episodeId, JsonNode request) {
        requireEnabled();
        return repository.saveDraft(userId, episodeId, request);
    }

    public ObjectNode prepareConfirmation(String userId, String episodeId, JsonNode request) {
        requireEnabled();
        return repository.prepareConfirmation(userId, episodeId, request);
    }

    public ObjectNode getConfirmation(String userId, String episodeId, String artifactId) {
        return repository.getConfirmation(userId, episodeId, artifactId);
    }

    public ObjectNode approveConfirmation(
            String userId, String episodeId, String artifactId, JsonNode request) {
        requireEnabled();
        return repository.approveConfirmation(userId, episodeId, artifactId, request);
    }

    public ObjectNode listVersions(String userId, String episodeId) {
        return repository.listVersions(userId, episodeId);
    }

    public ObjectNode getVersion(String userId, String episodeId, String versionId) {
        return repository.getVersion(userId, episodeId, versionId);
    }

    public ObjectNode getCommand(String userId, String episodeId, String clientRequestId) {
        return repository.getCommand(userId, episodeId, clientRequestId);
    }

    public ObjectNode getProjectCommand(String userId, String projectId, String clientRequestId) {
        return repository.getProjectCommand(userId, projectId, clientRequestId);
    }

    public ObjectNode adoptCandidate(
            String userId, String episodeId, String artifactId, JsonNode request) {
        requireEnabled();
        return repository.adoptCandidate(userId, episodeId, artifactId, request);
    }

    private void requireEnabled() {
        if (!enabled) throw new ApiException(403, "VIDEO_PREVIEW_DISABLED", "当前环境未开放视频制作");
    }
}
