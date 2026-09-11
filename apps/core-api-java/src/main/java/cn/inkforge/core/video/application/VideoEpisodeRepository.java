package cn.inkforge.core.video.application;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 独立剧集的事务端口；JSON 内容由公共强类型契约和领域校验共同约束。 */
public interface VideoEpisodeRepository {
    ObjectNode list(String userId, String projectId);

    ObjectNode get(String userId, String episodeId);

    ObjectNode create(String userId, String projectId, JsonNode request);

    ObjectNode update(String userId, String episodeId, JsonNode request);

    ObjectNode reorder(String userId, String projectId, JsonNode request);

    ObjectNode createSourceSet(String userId, String episodeId, JsonNode request);

    ObjectNode listSourceSets(String userId, String episodeId);

    ObjectNode getSourceSet(String userId, String episodeId, String versionId);

    ObjectNode getDraft(String userId, String episodeId);

    ObjectNode saveDraft(String userId, String episodeId, JsonNode request);

    ObjectNode prepareConfirmation(String userId, String episodeId, JsonNode request);

    ObjectNode getConfirmation(String userId, String episodeId, String artifactId);

    ObjectNode approveConfirmation(
            String userId, String episodeId, String artifactId, JsonNode request);

    ObjectNode listVersions(String userId, String episodeId);

    ObjectNode getVersion(String userId, String episodeId, String versionId);

    ObjectNode getCommand(String userId, String episodeId, String clientRequestId);

    ObjectNode getProjectCommand(String userId, String projectId, String clientRequestId);

    ObjectNode adoptCandidate(String userId, String episodeId, String artifactId, JsonNode request);
}
