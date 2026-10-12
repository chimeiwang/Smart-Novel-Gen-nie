package cn.inkforge.core.video.application;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 单集分镜 V2 Run 的持久化入口；列表用于刷新、换设备和未知响应后的有界恢复。 */
public interface VideoEpisodeStoryboardRunStore {
    ObjectNode start(String userId, String episodeId, JsonNode request);

    ObjectNode get(String userId, String episodeId, String runId);

    ObjectNode list(String userId, String episodeId, String beforeRunId, int limit);
}
