package cn.inkforge.core.video.application;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 跨集影响复核的事务端口；报告依据和作者决定均由 Core 校验。 */
public interface VideoEpisodeImpactRepository {
    ObjectNode list(
            String userId,
            String episodeId,
            String status,
            String beforeReviewId,
            int limit);

    ObjectNode get(String userId, String episodeId, String reviewId);

    ObjectNode decide(String userId, String episodeId, String reviewId, JsonNode request);
}
