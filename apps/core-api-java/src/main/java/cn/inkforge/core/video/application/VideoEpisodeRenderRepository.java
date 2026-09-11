package cn.inkforge.core.video.application;

import java.util.List;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 独立剧集逐镜任务和不可变 Take 的 PostgreSQL 边界。 */
public interface VideoEpisodeRenderRepository {

    ObjectNode createTask(
            String userId,
            String episodeId,
            String baselineId,
            String shotId,
            JsonNode request,
            String executionMode,
            boolean referenceTransportConfigured);

    ObjectNode retryTask(
            String userId,
            String episodeId,
            String taskId,
            JsonNode request,
            String executionMode,
            boolean referenceTransportConfigured);

    ObjectNode getTask(String userId, String episodeId, String taskId);

    VideoAssetFile getTakeFile(String userId, String episodeId, String takeId);

    /** 只按短时令牌冻结的资产身份与哈希读取已确认参考图。 */
    VideoAssetFile getProviderAssetFile(String assetId, String sha256);

    List<VideoEpisodeRenderClaim> claimDue(int limit);

    void markSubmitted(String taskId, String providerTaskId);

    void markSubmissionUnknown(String taskId, String message);

    void markSubmissionRejected(String taskId, String code, String message);

    void markQueryProgress(String taskId, String status);

    void markQueryError(String taskId, String message);

    boolean beginArchiving(String taskId);

    void markProviderTerminal(String taskId, String status, String code, String message);

    boolean retryArchiving(String taskId, String message);

    void completeTake(String taskId, CompletedEpisodeVideoTake take);
}
