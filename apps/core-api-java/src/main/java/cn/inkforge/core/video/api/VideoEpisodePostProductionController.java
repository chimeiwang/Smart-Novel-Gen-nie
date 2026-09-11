package cn.inkforge.core.video.api;

import cn.inkforge.contracts.api.CreateVideoEpisodeEditVersionRequest;
import cn.inkforge.contracts.api.CreateVideoEpisodeMixVersionRequest;
import cn.inkforge.contracts.api.RetryVideoEpisodeExportRequest;
import cn.inkforge.contracts.api.StartVideoEpisodeExportRequest;
import cn.inkforge.contracts.api.VideoEpisodeDeliveryResponse;
import cn.inkforge.contracts.api.VideoEpisodeEditVersionListResponse;
import cn.inkforge.contracts.api.VideoEpisodeEditVersionResponse;
import cn.inkforge.contracts.api.VideoEpisodeExportTaskResponse;
import cn.inkforge.contracts.api.VideoEpisodeMixVersionListResponse;
import cn.inkforge.contracts.api.VideoEpisodeMixVersionResponse;
import cn.inkforge.core.generated.api.VideoepisodepostproductionApi;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.ResolvedVideoAsset;
import cn.inkforge.core.video.application.VideoEpisodePostProductionService;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 独立剧集粗剪、声音字幕和交付的 HTTP 投影；不可变写入与归属校验统一由 Core 服务处理。 */
@RestController
public final class VideoEpisodePostProductionController
        implements VideoepisodepostproductionApi {

    private final Optional<VideoEpisodePostProductionService> postProduction;
    private final Optional<CurrentUserAccess> users;
    private final ObjectMapper json;

    public VideoEpisodePostProductionController(
            Optional<VideoEpisodePostProductionService> postProduction,
            Optional<CurrentUserAccess> users,
            ObjectMapper json) {
        this.postProduction = postProduction;
        this.users = users;
        this.json = json;
    }

    @Override
    public ResponseEntity<VideoEpisodeEditVersionResponse>
            createVideoEpisodeEditVersionApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdEditVersionsPost(
                    String episodeId,
                    String baselineId,
                    CreateVideoEpisodeEditVersionRequest request,
                    String inkforgeToken) {
        return response(
                201,
                service()
                        .createEditVersion(
                                user(inkforgeToken),
                                episodeId,
                                baselineId,
                                json.valueToTree(request)),
                VideoEpisodeEditVersionResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeEditVersionListResponse>
            listVideoEpisodeEditVersionsApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdEditVersionsGet(
                    String episodeId,
                    String baselineId,
                    Integer limit,
                    Integer beforeVersionNo,
                    String inkforgeToken) {
        return response(
                200,
                service()
                        .listEditVersions(
                                user(inkforgeToken),
                                episodeId,
                                baselineId,
                                beforeVersionNo,
                                limit),
                VideoEpisodeEditVersionListResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeEditVersionResponse>
            getVideoEpisodeEditVersionApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdEditVersionsVersionIdGet(
                    String episodeId,
                    String baselineId,
                    String versionId,
                    String inkforgeToken) {
        return response(
                200,
                service()
                        .getEditVersion(
                                user(inkforgeToken), episodeId, baselineId, versionId),
                VideoEpisodeEditVersionResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeMixVersionResponse>
            createVideoEpisodeMixVersionApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdMixVersionsPost(
                    String episodeId,
                    String baselineId,
                    CreateVideoEpisodeMixVersionRequest request,
                    String inkforgeToken) {
        return response(
                201,
                service()
                        .createMixVersion(
                                user(inkforgeToken),
                                episodeId,
                                baselineId,
                                json.valueToTree(request)),
                VideoEpisodeMixVersionResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeMixVersionListResponse>
            listVideoEpisodeMixVersionsApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdMixVersionsGet(
                    String episodeId,
                    String baselineId,
                    Integer limit,
                    Integer beforeVersionNo,
                    String inkforgeToken) {
        return response(
                200,
                service()
                        .listMixVersions(
                                user(inkforgeToken),
                                episodeId,
                                baselineId,
                                beforeVersionNo,
                                limit),
                VideoEpisodeMixVersionListResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeMixVersionResponse>
            getVideoEpisodeMixVersionApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdMixVersionsVersionIdGet(
                    String episodeId,
                    String baselineId,
                    String versionId,
                    String inkforgeToken) {
        return response(
                200,
                service()
                        .getMixVersion(
                                user(inkforgeToken), episodeId, baselineId, versionId),
                VideoEpisodeMixVersionResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeExportTaskResponse>
            startVideoEpisodeExportApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdExportTasksPost(
                    String episodeId,
                    String baselineId,
                    StartVideoEpisodeExportRequest request,
                    String inkforgeToken) {
        return response(
                202,
                service()
                        .createExportTask(
                                user(inkforgeToken),
                                episodeId,
                                baselineId,
                                json.valueToTree(request)),
                VideoEpisodeExportTaskResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeExportTaskResponse>
            getVideoEpisodeExportTaskApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdExportTasksTaskIdGet(
                    String episodeId,
                    String baselineId,
                    String taskId,
                    String inkforgeToken) {
        return response(
                200,
                service()
                        .getExportTask(
                                user(inkforgeToken), episodeId, baselineId, taskId),
                VideoEpisodeExportTaskResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeExportTaskResponse>
            retryVideoEpisodeExportApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdExportTasksTaskIdRetryPost(
                    String episodeId,
                    String baselineId,
                    String taskId,
                    RetryVideoEpisodeExportRequest request,
                    String inkforgeToken) {
        return response(
                202,
                service()
                        .retryExportTask(
                                user(inkforgeToken),
                                episodeId,
                                baselineId,
                                taskId,
                                json.valueToTree(request)),
                VideoEpisodeExportTaskResponse.class);
    }

    @Override
    public ResponseEntity<VideoEpisodeDeliveryResponse>
            getVideoEpisodeDeliveryApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdExportsExportIdGet(
                    String episodeId,
                    String baselineId,
                    String exportId,
                    String inkforgeToken) {
        return response(
                200,
                service()
                        .getDelivery(
                                user(inkforgeToken), episodeId, baselineId, exportId),
                VideoEpisodeDeliveryResponse.class);
    }

    @Override
    public ResponseEntity<StreamingResponseBody>
            getVideoEpisodeDeliveryContentApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdExportsExportIdContentGet(
                    String episodeId,
                    String baselineId,
                    String exportId,
                    String inkforgeToken) {
        ResolvedVideoAsset file =
                service()
                        .getDeliveryFile(
                                user(inkforgeToken), episodeId, baselineId, exportId);
        return VideoFileResponses.inline(file.path(), file.mimeType(), file.name());
    }

    private VideoEpisodePostProductionService service() {
        return postProduction.orElseThrow(
                () ->
                        new ApiException(
                                503,
                                "VIDEO_EPISODE_POST_PRODUCTION_SERVICE_UNAVAILABLE",
                                "独立剧集后期服务暂时不可用"));
    }

    private String user(String token) {
        return users.orElseThrow(
                        () -> new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token)
                .id();
    }

    private <T> ResponseEntity<T> response(int status, JsonNode body, Class<T> type) {
        return ResponseEntity.status(status).body(json.convertValue(body, type));
    }
}
