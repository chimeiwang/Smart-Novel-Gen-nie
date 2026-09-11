package cn.inkforge.core.video.api;

import cn.inkforge.contracts.api.*;
import cn.inkforge.core.generated.api.VideoproductionApi;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.VideoEpisodeProductionService;
import cn.inkforge.core.video.application.VideoEpisodeStoryboardCandidateService;
import cn.inkforge.core.video.application.VideoEpisodeStoryboardRunService;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.ObjectMapper;

/** 分镜与制作基线的生成契约投影；业务校验、CAS 与不可变写入统一留在 Core 服务。 */
@RestController
public final class VideoProductionController implements VideoproductionApi {
    private final Optional<VideoEpisodeProductionService> production;
    private final Optional<VideoEpisodeStoryboardRunService> runs;
    private final Optional<VideoEpisodeStoryboardCandidateService> candidates;
    private final Optional<CurrentUserAccess> users;
    private final ObjectMapper json;

    public VideoProductionController(
            Optional<VideoEpisodeProductionService> production,
            Optional<VideoEpisodeStoryboardRunService> runs,
            Optional<VideoEpisodeStoryboardCandidateService> candidates,
            Optional<CurrentUserAccess> users,
            ObjectMapper json) {
        this.production = production;
        this.runs = runs;
        this.candidates = candidates;
        this.users = users;
        this.json = json;
    }

    @Override
    public ResponseEntity<VideoStoryboardDraftResponse>
            adoptVideoStoryboardCandidateApiV1VideoEpisodesEpisodeIdStoryboardCandidatesArtifactIdAdoptPost(
                    String episodeId,
                    String artifactId,
                    AdoptVideoStoryboardCandidateRequest request,
                    String inkforgeToken) {
        return response(
                200,
                candidates()
                        .adopt(
                                user(inkforgeToken),
                                episodeId,
                                artifactId,
                                json.valueToTree(request)),
                VideoStoryboardDraftResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardVersionResponse>
            approveVideoStoryboardConfirmationApiV1VideoEpisodesEpisodeIdStoryboardConfirmationsArtifactIdApprovePost(
                    String episodeId,
                    String artifactId,
                    ApproveVideoStoryboardConfirmationRequest request,
                    String inkforgeToken) {
        return response(
                201,
                production()
                        .approveStoryboardConfirmation(
                                user(inkforgeToken),
                                episodeId,
                                artifactId,
                                json.valueToTree(request)),
                VideoStoryboardVersionResponse.class);
    }

    @Override
    public ResponseEntity<VideoProductionBaselineResponse>
            createVideoProductionBaselineApiV1VideoEpisodesEpisodeIdProductionBaselinesPost(
                    String episodeId,
                    CreateVideoProductionBaselineRequest request,
                    String inkforgeToken) {
        return response(
                201,
                production()
                        .createProductionBaseline(
                                user(inkforgeToken), episodeId, json.valueToTree(request)),
                VideoProductionBaselineResponse.class);
    }

    @Override
    public ResponseEntity<VideoTakeAdoptionResponse>
            createVideoTakeAdoptionApiV1VideoEpisodesEpisodeIdTakeAdoptionsPost(
                    String episodeId,
                    CreateVideoTakeAdoptionRequest request,
                    String inkforgeToken) {
        return response(
                201,
                production()
                        .createTakeAdoption(
                                user(inkforgeToken), episodeId, json.valueToTree(request)),
                VideoTakeAdoptionResponse.class);
    }

    @Override
    public ResponseEntity<VideoProductionBaselineResponse>
            getVideoProductionBaselineApiV1VideoEpisodesEpisodeIdProductionBaselinesBaselineIdGet(
                    String episodeId, String baselineId, String inkforgeToken) {
        return response(
                200,
                production()
                        .getProductionBaseline(user(inkforgeToken), episodeId, baselineId),
                VideoProductionBaselineResponse.class);
    }

    @Override
    public ResponseEntity<VideoProductionCapabilityResponse>
            getVideoProductionCapabilitiesApiV1VideoProductionCapabilitiesGet(
                    String inkforgeToken) {
        user(inkforgeToken);
        return response(
                200,
                production().capabilities(),
                VideoProductionCapabilityResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardConfirmationResponse>
            getVideoStoryboardConfirmationApiV1VideoEpisodesEpisodeIdStoryboardConfirmationsArtifactIdGet(
                    String episodeId, String artifactId, String inkforgeToken) {
        return response(
                200,
                production()
                        .getStoryboardConfirmation(
                                user(inkforgeToken), episodeId, artifactId),
                VideoStoryboardConfirmationResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardCandidateResponse>
            getVideoStoryboardCandidateApiV1VideoEpisodesEpisodeIdStoryboardCandidatesArtifactIdGet(
                    String episodeId, String artifactId, String inkforgeToken) {
        return response(
                200,
                candidates().get(user(inkforgeToken), episodeId, artifactId),
                VideoStoryboardCandidateResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardDraftResponse>
            getVideoStoryboardDraftApiV1VideoEpisodesEpisodeIdStoryboardDraftGet(
                    String episodeId, String inkforgeToken) {
        return response(
                200,
                production().getStoryboardDraft(user(inkforgeToken), episodeId),
                VideoStoryboardDraftResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardRunResponse>
            getVideoStoryboardRunApiV1VideoEpisodesEpisodeIdStoryboardRunsRunIdGet(
                    String episodeId, String runId, String inkforgeToken) {
        return response(
                200,
                runs().get(user(inkforgeToken), episodeId, runId),
                VideoStoryboardRunResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardVersionResponse>
            getVideoStoryboardVersionApiV1VideoEpisodesEpisodeIdStoryboardVersionsVersionIdGet(
                    String episodeId, String versionId, String inkforgeToken) {
        return response(
                200,
                production()
                        .getStoryboardVersion(user(inkforgeToken), episodeId, versionId),
                VideoStoryboardVersionResponse.class);
    }

    @Override
    public ResponseEntity<VideoTakeAdoptionResponse>
            getVideoTakeAdoptionApiV1VideoEpisodesEpisodeIdTakeAdoptionsAdoptionIdGet(
                    String episodeId, String adoptionId, String inkforgeToken) {
        return response(
                200,
                production().getTakeAdoption(user(inkforgeToken), episodeId, adoptionId),
                VideoTakeAdoptionResponse.class);
    }

    @Override
    public ResponseEntity<VideoProductionBaselineListResponse>
            listVideoProductionBaselinesApiV1VideoEpisodesEpisodeIdProductionBaselinesGet(
                    String episodeId,
                    Integer limit,
                    Integer beforeVersionNo,
                    String inkforgeToken) {
        return response(
                200,
                production()
                        .listProductionBaselines(
                                user(inkforgeToken), episodeId, beforeVersionNo, limit),
                VideoProductionBaselineListResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardRunListResponse>
            listVideoStoryboardRunsApiV1VideoEpisodesEpisodeIdStoryboardRunsGet(
                    String episodeId,
                    Integer limit,
                    String beforeRunId,
                    String inkforgeToken) {
        return response(
                200,
                runs().list(user(inkforgeToken), episodeId, beforeRunId, limit),
                VideoStoryboardRunListResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardVersionListResponse>
            listVideoStoryboardVersionsApiV1VideoEpisodesEpisodeIdStoryboardVersionsGet(
                    String episodeId,
                    Integer limit,
                    Integer beforeVersionNo,
                    String inkforgeToken) {
        return response(
                200,
                production()
                        .listStoryboardVersions(
                                user(inkforgeToken), episodeId, beforeVersionNo, limit),
                VideoStoryboardVersionListResponse.class);
    }

    @Override
    public ResponseEntity<VideoTakeCandidateListResponse>
            listVideoTakeCandidatesApiV1VideoEpisodesEpisodeIdTakesGet(
                    String episodeId,
                    String targetShotVersionId,
                    Integer limit,
                    String beforeTakeId,
                    String inkforgeToken) {
        return response(
                200,
                production()
                        .listTakeCandidates(
                                user(inkforgeToken),
                                episodeId,
                                targetShotVersionId,
                                beforeTakeId,
                                limit),
                VideoTakeCandidateListResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardConfirmationResponse>
            prepareVideoStoryboardConfirmationApiV1VideoEpisodesEpisodeIdStoryboardConfirmationsPost(
                    String episodeId,
                    PrepareVideoStoryboardConfirmationRequest request,
                    String inkforgeToken) {
        return response(
                201,
                production()
                        .prepareStoryboardConfirmation(
                                user(inkforgeToken), episodeId, json.valueToTree(request)),
                VideoStoryboardConfirmationResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardDraftResponse>
            saveVideoStoryboardDraftApiV1VideoEpisodesEpisodeIdStoryboardDraftPut(
                    String episodeId,
                    SaveVideoStoryboardDraftRequest request,
                    String inkforgeToken) {
        return response(
                200,
                production()
                        .saveStoryboardDraft(
                                user(inkforgeToken), episodeId, json.valueToTree(request)),
                VideoStoryboardDraftResponse.class);
    }

    @Override
    public ResponseEntity<VideoStoryboardRunResponse>
            startVideoStoryboardRunApiV1VideoEpisodesEpisodeIdStoryboardRunsPost(
                    String episodeId,
                    StartVideoStoryboardRunRequest request,
                    String inkforgeToken) {
        return response(
                202,
                runs().start(user(inkforgeToken), episodeId, json.valueToTree(request)),
                VideoStoryboardRunResponse.class);
    }

    private VideoEpisodeProductionService production() {
        return production.orElseThrow(
                () ->
                        new ApiException(
                                503,
                                "VIDEO_PRODUCTION_SERVICE_UNAVAILABLE",
                                "分镜与制作基线服务暂时不可用"));
    }

    private VideoEpisodeStoryboardRunService runs() {
        return runs.orElseThrow(
                () ->
                        new ApiException(
                                503,
                                "VIDEO_STORYBOARD_RUN_SERVICE_UNAVAILABLE",
                                "分镜执行服务暂时不可用"));
    }

    private VideoEpisodeStoryboardCandidateService candidates() {
        return candidates.orElseThrow(
                () ->
                        new ApiException(
                                503,
                                "VIDEO_STORYBOARD_CANDIDATE_SERVICE_UNAVAILABLE",
                                "分镜候选服务暂时不可用"));
    }

    private String user(String token) {
        return users.orElseThrow(
                        () -> new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token)
                .id();
    }

    private <T> ResponseEntity<T> response(
            int status, tools.jackson.databind.JsonNode body, Class<T> type) {
        return ResponseEntity.status(status).body(json.convertValue(body, type));
    }
}
