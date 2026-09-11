package cn.inkforge.core.video.api;

import cn.inkforge.contracts.api.RetryVideoEpisodeShotRenderRequest;
import cn.inkforge.contracts.api.StartVideoEpisodeShotRenderRequest;
import cn.inkforge.contracts.api.VideoEpisodeRenderTaskResponse;
import cn.inkforge.core.generated.api.VideoepisoderendersApi;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.ResolvedVideoAsset;
import cn.inkforge.core.video.application.VideoEpisodeRenderService;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import tools.jackson.databind.ObjectMapper;

/** 独立剧集逐镜任务的 HTTP 投影；媒体内容始终从受控存储流式返回。 */
@RestController
public final class VideoEpisodeRenderController implements VideoepisoderendersApi {

    private final Optional<VideoEpisodeRenderService> renders;
    private final Optional<CurrentUserAccess> users;
    private final ObjectMapper json;

    public VideoEpisodeRenderController(
            Optional<VideoEpisodeRenderService> renders,
            Optional<CurrentUserAccess> users,
            ObjectMapper json) {
        this.renders = renders;
        this.users = users;
        this.json = json;
    }

    @Override
    public ResponseEntity<VideoEpisodeRenderTaskResponse>
            startVideoEpisodeShotRenderApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdShotsShotIdRenderTasksPost(
                    String episodeId,
                    String baselineId,
                    String shotId,
                    StartVideoEpisodeShotRenderRequest request,
                    String inkforgeToken) {
        return response(
                202,
                renders()
                        .createTask(
                                user(inkforgeToken),
                                episodeId,
                                baselineId,
                                shotId,
                                json.valueToTree(request)));
    }

    @Override
    public ResponseEntity<VideoEpisodeRenderTaskResponse>
            getVideoEpisodeRenderTaskApiV1VideoEpisodesEpisodeIdRenderTasksTaskIdGet(
                    String episodeId, String taskId, String inkforgeToken) {
        return response(
                200,
                renders().getTask(user(inkforgeToken), episodeId, taskId));
    }

    @Override
    public ResponseEntity<VideoEpisodeRenderTaskResponse>
            retryVideoEpisodeRenderTaskApiV1VideoEpisodesEpisodeIdRenderTasksTaskIdRetryPost(
                    String episodeId,
                    String taskId,
                    RetryVideoEpisodeShotRenderRequest request,
                    String inkforgeToken) {
        return response(
                202,
                renders()
                        .retryTask(
                                user(inkforgeToken),
                                episodeId,
                                taskId,
                                json.valueToTree(request)));
    }

    @Override
    public ResponseEntity<StreamingResponseBody>
            getVideoEpisodeTakeContentApiV1VideoEpisodesEpisodeIdTakesTakeIdContentGet(
                    String episodeId, String takeId, String inkforgeToken) {
        ResolvedVideoAsset file =
                renders().getTakeFile(user(inkforgeToken), episodeId, takeId);
        return VideoFileResponses.inline(file.path(), file.mimeType(), file.name());
    }

    private ResponseEntity<VideoEpisodeRenderTaskResponse> response(
            int status, tools.jackson.databind.JsonNode body) {
        return ResponseEntity.status(status)
                .body(json.convertValue(body, VideoEpisodeRenderTaskResponse.class));
    }

    private VideoEpisodeRenderService renders() {
        return renders.orElseThrow(
                () ->
                        new ApiException(
                                503,
                                "VIDEO_EPISODE_RENDER_SERVICE_UNAVAILABLE",
                                "独立剧集逐镜生成服务暂时不可用"));
    }

    private String user(String token) {
        return users.orElseThrow(
                        () -> new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token)
                .id();
    }
}
