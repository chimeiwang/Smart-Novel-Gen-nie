package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.http.ApiException;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

import java.util.Objects;

/** 影响报告始终可读；作者决定只在视频制作显式开放时写入。 */
public final class VideoEpisodeImpactService {
    private final VideoEpisodeImpactRepository repository;
    private final boolean enabled;

    public VideoEpisodeImpactService(VideoEpisodeImpactRepository repository, boolean enabled) {
        this.repository = Objects.requireNonNull(repository);
        this.enabled = enabled;
    }

    public ObjectNode list(
            String userId,
            String episodeId,
            String status,
            String beforeReviewId,
            int limit) {
        return repository.list(userId, episodeId, status, beforeReviewId, limit);
    }

    public ObjectNode get(String userId, String episodeId, String reviewId) {
        return repository.get(userId, episodeId, reviewId);
    }

    public ObjectNode decide(
            String userId, String episodeId, String reviewId, JsonNode request) {
        if (!enabled) {
            throw new ApiException(403, "VIDEO_PREVIEW_DISABLED", "当前环境未开放视频制作");
        }
        return repository.decide(userId, episodeId, reviewId, request);
    }
}
