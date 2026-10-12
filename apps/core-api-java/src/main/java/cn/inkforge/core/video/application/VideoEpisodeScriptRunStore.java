package cn.inkforge.core.video.application;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 冻结单集剧本上下文并创建、回读 Core 权威 V2 Run。 */
public interface VideoEpisodeScriptRunStore {

    ObjectNode start(String userId, String episodeId, JsonNode request);

    ObjectNode get(String userId, String episodeId, String runId);
}
