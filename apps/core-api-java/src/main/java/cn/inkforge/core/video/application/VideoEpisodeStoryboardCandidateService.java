package cn.inkforge.core.video.application;

import cn.inkforge.core.platform.http.ApiException;
import java.util.Objects;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 分镜候选的人工操作边界；视频关闭时可读历史候选，但不得采用。 */
public final class VideoEpisodeStoryboardCandidateService {
    private final VideoEpisodeStoryboardCandidateRepository candidates;
    private final boolean enabled;

    public VideoEpisodeStoryboardCandidateService(
            VideoEpisodeStoryboardCandidateRepository candidates, boolean enabled) {
        this.candidates = Objects.requireNonNull(candidates);
        this.enabled = enabled;
    }

    public ObjectNode get(String userId, String episodeId, String artifactId) {
        return candidates.get(userId, episodeId, artifactId);
    }

    public ObjectNode adopt(
            String userId, String episodeId, String artifactId, JsonNode request) {
        if (!enabled) {
            throw new ApiException(403, "VIDEO_PREVIEW_DISABLED", "当前环境未开放视频制作");
        }
        return candidates.adopt(userId, episodeId, artifactId, request);
    }
}
