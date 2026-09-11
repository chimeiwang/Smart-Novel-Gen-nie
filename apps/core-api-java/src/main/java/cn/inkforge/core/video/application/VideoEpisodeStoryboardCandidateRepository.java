package cn.inkforge.core.video.application;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 分镜候选读取与采用端口；采用只更新工作稿，不创建正式分镜版本。 */
public interface VideoEpisodeStoryboardCandidateRepository {
    ObjectNode get(String userId, String episodeId, String artifactId);

    ObjectNode adopt(String userId, String episodeId, String artifactId, JsonNode request);
}
