package cn.inkforge.core.video.application;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 分镜工作稿、不可变镜头版本与整集制作基线的事务端口。 */
public interface VideoEpisodeProductionRepository {
    ObjectNode capabilities();

    ObjectNode getStoryboardDraft(String userId, String episodeId);

    ObjectNode saveStoryboardDraft(String userId, String episodeId, JsonNode request);

    ObjectNode prepareStoryboardConfirmation(String userId, String episodeId, JsonNode request);

    ObjectNode getStoryboardConfirmation(String userId, String episodeId, String artifactId);

    ObjectNode approveStoryboardConfirmation(
            String userId, String episodeId, String artifactId, JsonNode request);

    ObjectNode listStoryboardVersions(
            String userId, String episodeId, Integer beforeVersionNo, int limit);

    ObjectNode getStoryboardVersion(String userId, String episodeId, String versionId);

    ObjectNode createTakeAdoption(String userId, String episodeId, JsonNode request);

    ObjectNode getTakeAdoption(String userId, String episodeId, String adoptionId);

    ObjectNode listTakeCandidates(
            String userId,
            String episodeId,
            String targetShotVersionId,
            String beforeTakeId,
            int limit);

    ObjectNode createProductionBaseline(String userId, String episodeId, JsonNode request);

    ObjectNode listProductionBaselines(
            String userId, String episodeId, Integer beforeVersionNo, int limit);

    ObjectNode getProductionBaseline(String userId, String episodeId, String baselineId);
}
