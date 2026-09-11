package cn.inkforge.core.video.application;

import java.util.Objects;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 分镜 AI 任务应用边界；完成只产生候选，采用与正式确认分别由独立命令处理。 */
public final class VideoEpisodeStoryboardRunService {
    private final VideoEpisodeStoryboardRunStore runs;

    public VideoEpisodeStoryboardRunService(VideoEpisodeStoryboardRunStore runs) {
        this.runs = Objects.requireNonNull(runs);
    }

    public ObjectNode start(String userId, String episodeId, JsonNode request) {
        return runs.start(userId, episodeId, request);
    }

    public ObjectNode get(String userId, String episodeId, String runId) {
        return runs.get(userId, episodeId, runId);
    }

    public ObjectNode list(String userId, String episodeId, String beforeRunId, int limit) {
        if (limit < 1 || limit > 50) {
            throw new IllegalArgumentException("分镜任务列表 limit 必须为 1 至 50");
        }
        return runs.list(userId, episodeId, beforeRunId, limit);
    }
}
