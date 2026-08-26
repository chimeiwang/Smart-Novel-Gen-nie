package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.PostProductionAssetResponse;
import cn.inkforge.contracts.api.ChapterPostProductionWorkspaceResponse;
import cn.inkforge.contracts.api.PostProductionReadinessResponse;
import cn.inkforge.contracts.api.EpisodeEditHeadResponse;
import cn.inkforge.contracts.api.EpisodeEditVersionResponse;
import cn.inkforge.contracts.api.EpisodeMixHeadResponse;
import cn.inkforge.contracts.api.EpisodeMixVersionResponse;
import cn.inkforge.contracts.api.EpisodeExportTaskResponse;
import cn.inkforge.contracts.api.RetryEpisodeExportRequest;
import cn.inkforge.contracts.api.StartEpisodeExportRequest;
import cn.inkforge.contracts.api.SaveEpisodeEditVersionRequest;
import cn.inkforge.contracts.api.SaveEpisodeMixVersionRequest;
import cn.inkforge.contracts.api.SaveShotKeyframeVersionRequest;
import cn.inkforge.contracts.api.ShotKeyframeHeadResponse;
import java.util.List;

/** P1–P3 后期制作不可变版本、来源事实和耐久导出任务的数据库边界。 */
public interface VideoPostProductionRepository {

    ChapterPostProductionWorkspaceResponse getWorkspace(
            String userId,
            String adaptationId,
            PostProductionReadinessResponse readiness);

    ShotKeyframeHeadResponse saveKeyframe(
            String userId,
            String adaptationId,
            String shotId,
            SaveShotKeyframeVersionRequest request);

    TakeFrameSource getTakeFrameSource(String userId, String takeId, int timestampMs);

    PostProductionAssetResponse getExtractionReplay(
            String userId, String clientRequestId, String requestHash);

    PostProductionAssetResponse completeExtractedFrame(CompletedTakeFrameExtraction extraction);

    EpisodeEditHeadResponse saveEditVersion(
            String userId,
            String adaptationId,
            int episodeNo,
            SaveEpisodeEditVersionRequest request);

    EpisodeEditVersionResponse getEditVersion(String userId, String versionId);

    EpisodeMixHeadResponse saveMixVersion(
            String userId,
            String adaptationId,
            int episodeNo,
            SaveEpisodeMixVersionRequest request);

    EpisodeMixVersionResponse getMixVersion(String userId, String versionId);

    EpisodeExportTaskResponse createExportTask(
            String userId,
            String adaptationId,
            int episodeNo,
            StartEpisodeExportRequest request);

    EpisodeExportTaskResponse retryExportTask(
            String userId, String taskId, RetryEpisodeExportRequest request);

    EpisodeExportTaskResponse getExportTask(String userId, String taskId);

    VideoAssetFile getExportFile(String userId, String exportId);

    List<EpisodeExportClaim> claimDueExportTasks(int limit);

    EpisodeExportTaskResponse completeExport(CompletedEpisodeExport completed);

    boolean failExport(String taskId, String code, String message);
}
