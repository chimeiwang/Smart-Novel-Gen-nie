package cn.inkforge.core.video.application;

import java.util.Objects;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 单集剧本 AI 任务入口；候选完成、采用和正式确认仍由各自独立事务处理。 */
public final class VideoEpisodeScriptRunService {

    private final VideoEpisodeScriptRunStore runs;

    public VideoEpisodeScriptRunService(VideoEpisodeScriptRunStore runs) {
        this.runs = Objects.requireNonNull(runs);
    }

    public ObjectNode start(String userId, String episodeId, JsonNode request) {
        return runs.start(userId, episodeId, request);
    }

    public ObjectNode get(String userId, String episodeId, String runId) {
        return runs.get(userId, episodeId, runId);
    }
}
