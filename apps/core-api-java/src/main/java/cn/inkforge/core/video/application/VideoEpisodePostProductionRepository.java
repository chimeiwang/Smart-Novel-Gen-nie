package cn.inkforge.core.video.application;

import java.util.List;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 独立分集粗剪、声音字幕和耐久导出的事务边界。 */
public interface VideoEpisodePostProductionRepository {

    ObjectNode createEditVersion(
            String userId, String episodeId, String baselineId, JsonNode request);

    ObjectNode listEditVersions(
            String userId,
            String episodeId,
            String baselineId,
            Integer beforeVersionNo,
            int limit);

    ObjectNode getEditVersion(
            String userId, String episodeId, String baselineId, String versionId);

    ObjectNode createMixVersion(
            String userId, String episodeId, String baselineId, JsonNode request);

    ObjectNode listMixVersions(
            String userId,
            String episodeId,
            String baselineId,
            Integer beforeVersionNo,
            int limit);

    ObjectNode getMixVersion(
            String userId, String episodeId, String baselineId, String versionId);

    ObjectNode createExportTask(
            String userId, String episodeId, String baselineId, JsonNode request);

    ObjectNode retryExportTask(
            String userId,
            String episodeId,
            String baselineId,
            String taskId,
            JsonNode request);

    ObjectNode getExportTask(
            String userId, String episodeId, String baselineId, String taskId);

    ObjectNode getDelivery(
            String userId, String episodeId, String baselineId, String exportId);

    VideoAssetFile getDeliveryFile(
            String userId, String episodeId, String baselineId, String exportId);

    List<EpisodeExportClaim> claimDueExportTasks(int limit);

    ObjectNode completeExport(CompletedEpisodeExport completed);

    boolean failExport(String taskId, String code, String message);
}
