package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.ChapterRenderWorkspaceResponse;
import cn.inkforge.contracts.api.ConfirmShotTakeRequest;
import cn.inkforge.contracts.api.RetryShotRenderRequest;
import cn.inkforge.contracts.api.ShotRenderTaskResponse;
import cn.inkforge.contracts.api.ShotTakeDecisionResponse;
import cn.inkforge.contracts.api.StartShotRenderRequest;
import cn.inkforge.contracts.api.VideoRenderReadinessResponse;
import java.util.List;

/** 逐镜 Seedance 任务、不可变 Take 与选片 Head 的 PostgreSQL 边界。 */
public interface VideoRenderRepository {

    ShotRenderTaskResponse createTask(
            String userId,
            String adaptationId,
            String shotId,
            StartShotRenderRequest request,
            String model,
            boolean referenceTransportConfigured);

    ShotRenderTaskResponse retryTask(
            String userId,
            String taskId,
            RetryShotRenderRequest request,
            boolean referenceTransportConfigured);

    ShotRenderTaskResponse getTask(String userId, String taskId);

    ChapterRenderWorkspaceResponse getWorkspace(
            String userId,
            String adaptationId,
            VideoRenderReadinessResponse readiness);

    ShotTakeDecisionResponse confirmTake(
            String userId,
            String adaptationId,
            String shotId,
            String takeId,
            ConfirmShotTakeRequest request);

    VideoAssetFile getTakeFile(String userId, String takeId);

    VideoAssetFile getProviderAssetFile(String assetId, String sha256);

    List<VideoRenderClaim> claimDue(int limit);

    void markSubmitted(String taskId, String providerTaskId);

    void markSubmissionUnknown(String taskId, String message);

    void markSubmissionRejected(String taskId, String code, String message);

    void markQueryProgress(String taskId, String status);

    void markQueryError(String taskId, String message);

    boolean beginArchiving(String taskId);

    void markProviderTerminal(String taskId, String status, String code, String message);

    boolean failArchiving(String taskId, String message);

    void completeTake(String taskId, CompletedVideoTake take);
}
