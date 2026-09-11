package cn.inkforge.core.video.api;

import cn.inkforge.contracts.api.DecideVideoImpactReviewRequest;
import cn.inkforge.contracts.api.VideoImpactReviewListResponse;
import cn.inkforge.contracts.api.VideoImpactReviewResponse;
import cn.inkforge.core.generated.api.VideoepisodeimpactsApi;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.VideoEpisodeImpactService;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 剧本变化影响报告的 HTTP 投影；过期判定和逐项决定由 Core 事务保证。 */
@RestController
public final class VideoEpisodeImpactController implements VideoepisodeimpactsApi {
    private final Optional<VideoEpisodeImpactService> impacts;
    private final Optional<CurrentUserAccess> users;
    private final ObjectMapper json;

    public VideoEpisodeImpactController(
            Optional<VideoEpisodeImpactService> impacts,
            Optional<CurrentUserAccess> users,
            ObjectMapper json) {
        this.impacts = impacts;
        this.users = users;
        this.json = json;
    }

    @Override
    public ResponseEntity<VideoImpactReviewResponse>
            decideVideoImpactReviewApiV1VideoEpisodesEpisodeIdImpactReviewsReviewIdDecisionsPost(
                    String episodeId,
                    String reviewId,
                    DecideVideoImpactReviewRequest request,
                    String inkforgeToken) {
        return response(
                200,
                impacts()
                        .decide(
                                user(inkforgeToken),
                                episodeId,
                                reviewId,
                                json.valueToTree(request)),
                VideoImpactReviewResponse.class);
    }

    @Override
    public ResponseEntity<VideoImpactReviewResponse>
            getVideoImpactReviewApiV1VideoEpisodesEpisodeIdImpactReviewsReviewIdGet(
                    String episodeId, String reviewId, String inkforgeToken) {
        return response(
                200,
                impacts().get(user(inkforgeToken), episodeId, reviewId),
                VideoImpactReviewResponse.class);
    }

    @Override
    public ResponseEntity<VideoImpactReviewListResponse>
            listVideoImpactReviewsApiV1VideoEpisodesEpisodeIdImpactReviewsGet(
                    String episodeId,
                    String status,
                    Integer limit,
                    String beforeReviewId,
                    String inkforgeToken) {
        return response(
                200,
                impacts()
                        .list(
                                user(inkforgeToken),
                                episodeId,
                                status,
                                beforeReviewId,
                                limit),
                VideoImpactReviewListResponse.class);
    }

    private VideoEpisodeImpactService impacts() {
        return impacts.orElseThrow(
                () ->
                        new ApiException(
                                503,
                                "VIDEO_IMPACT_SERVICE_UNAVAILABLE",
                                "视频影响复核服务暂时不可用"));
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
