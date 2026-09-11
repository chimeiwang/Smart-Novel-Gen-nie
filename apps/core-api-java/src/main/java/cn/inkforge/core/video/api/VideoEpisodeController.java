package cn.inkforge.core.video.api;

import cn.inkforge.contracts.api.*;
import cn.inkforge.core.generated.api.VideoepisodesApi;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.VideoEpisodeScriptRunService;
import cn.inkforge.core.video.application.VideoEpisodeService;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

import tools.jackson.databind.ObjectMapper;

import java.util.Optional;

/** 公共生成契约的 HTTP 投影；认证、业务门禁和持久化始终留在 Core。 */
@RestController
public final class VideoEpisodeController implements VideoepisodesApi {
    private final Optional<VideoEpisodeService> episodes;
    private final Optional<VideoEpisodeScriptRunService> runs;
    private final Optional<CurrentUserAccess> users;
    private final ObjectMapper json;

    public VideoEpisodeController(
            Optional<VideoEpisodeService> episodes,
            Optional<VideoEpisodeScriptRunService> runs,
            Optional<CurrentUserAccess> users,
            ObjectMapper json) {
        this.episodes = episodes;
        this.runs = runs;
        this.users = users;
        this.json = json;
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptDraftResponse>
            adoptVideoEpisodeScriptCandidateApiV1VideoEpisodesEpisodeIdScriptCandidatesArtifactIdAdoptPost(
                    String episodeId,
                    String artifactId,
                    AdoptVideoEpisodeScriptCandidateRequest adoptVideoEpisodeScriptCandidateRequest,
                    String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes()
                                        .adoptCandidate(
                                                user(inkforgeToken),
                                                episodeId,
                                                artifactId,
                                                json.valueToTree(
                                                        adoptVideoEpisodeScriptCandidateRequest)),
                                VideoEpisodeScriptDraftResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptVersionResponse>
            approveVideoEpisodeScriptConfirmationApiV1VideoEpisodesEpisodeIdScriptConfirmationsArtifactIdApprovePost(
                    String episodeId,
                    String artifactId,
                    ApproveVideoEpisodeScriptConfirmationRequest
                            approveVideoEpisodeScriptConfirmationRequest,
                    String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(
                        json.convertValue(
                                episodes()
                                        .approveConfirmation(
                                                user(inkforgeToken),
                                                episodeId,
                                                artifactId,
                                                json.valueToTree(
                                                        approveVideoEpisodeScriptConfirmationRequest)),
                                VideoEpisodeScriptVersionResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeResponse>
            createVideoEpisodeApiV1VideoProjectsProjectIdEpisodesPost(
                    String projectId,
                    CreateVideoEpisodeRequest createVideoEpisodeRequest,
                    String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(
                        json.convertValue(
                                episodes()
                                        .create(
                                                user(inkforgeToken),
                                                projectId,
                                                json.valueToTree(createVideoEpisodeRequest)),
                                VideoEpisodeResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeSourceSetResponse>
            createVideoEpisodeSourceSetApiV1VideoEpisodesEpisodeIdSourceSetsPost(
                    String episodeId,
                    CreateVideoEpisodeSourceSetRequest createVideoEpisodeSourceSetRequest,
                    String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(
                        json.convertValue(
                                episodes()
                                        .createSourceSet(
                                                user(inkforgeToken),
                                                episodeId,
                                                json.valueToTree(
                                                        createVideoEpisodeSourceSetRequest)),
                                VideoEpisodeSourceSetResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeDetailResponse> getVideoEpisodeApiV1VideoEpisodesEpisodeIdGet(
            String episodeId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes().get(user(inkforgeToken), episodeId),
                                VideoEpisodeDetailResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeCommandResponse>
            getVideoEpisodeCommandApiV1VideoEpisodesEpisodeIdCommandsClientRequestIdGet(
                    String episodeId, String clientRequestId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes()
                                        .getCommand(
                                                user(inkforgeToken), episodeId, clientRequestId),
                                VideoEpisodeCommandResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptConfirmationResponse>
            getVideoEpisodeScriptConfirmationApiV1VideoEpisodesEpisodeIdScriptConfirmationsArtifactIdGet(
                    String episodeId, String artifactId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes()
                                        .getConfirmation(
                                                user(inkforgeToken), episodeId, artifactId),
                                VideoEpisodeScriptConfirmationResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptDraftResponse>
            getVideoEpisodeScriptDraftApiV1VideoEpisodesEpisodeIdScriptDraftGet(
                    String episodeId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes().getDraft(user(inkforgeToken), episodeId),
                                VideoEpisodeScriptDraftResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptRunResponse>
            getVideoEpisodeScriptRunApiV1VideoEpisodesEpisodeIdScriptRunsRunIdGet(
                    String episodeId, String runId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                runs().get(user(inkforgeToken), episodeId, runId),
                                VideoEpisodeScriptRunResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptVersionResponse>
            getVideoEpisodeScriptVersionApiV1VideoEpisodesEpisodeIdScriptVersionsVersionIdGet(
                    String episodeId, String versionId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes().getVersion(user(inkforgeToken), episodeId, versionId),
                                VideoEpisodeScriptVersionResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeSourceSetResponse>
            getVideoEpisodeSourceSetApiV1VideoEpisodesEpisodeIdSourceSetsVersionIdGet(
                    String episodeId, String versionId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes().getSourceSet(user(inkforgeToken), episodeId, versionId),
                                VideoEpisodeSourceSetResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeCommandResponse>
            getVideoProjectEpisodeCommandApiV1VideoProjectsProjectIdEpisodeCommandsClientRequestIdGet(
                    String projectId, String clientRequestId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes()
                                        .getProjectCommand(
                                                user(inkforgeToken), projectId, clientRequestId),
                                VideoEpisodeCommandResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptVersionListResponse>
            listVideoEpisodeScriptVersionsApiV1VideoEpisodesEpisodeIdScriptVersionsGet(
                    String episodeId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes().listVersions(user(inkforgeToken), episodeId),
                                VideoEpisodeScriptVersionListResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeSourceSetListResponse>
            listVideoEpisodeSourceSetsApiV1VideoEpisodesEpisodeIdSourceSetsGet(
                    String episodeId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes().listSourceSets(user(inkforgeToken), episodeId),
                                VideoEpisodeSourceSetListResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeListResponse>
            listVideoEpisodesApiV1VideoProjectsProjectIdEpisodesGet(
                    String projectId, String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes().list(user(inkforgeToken), projectId),
                                VideoEpisodeListResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptConfirmationResponse>
            prepareVideoEpisodeScriptConfirmationApiV1VideoEpisodesEpisodeIdScriptConfirmationsPost(
                    String episodeId,
                    PrepareVideoEpisodeScriptConfirmationRequest
                            prepareVideoEpisodeScriptConfirmationRequest,
                    String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(
                        json.convertValue(
                                episodes()
                                        .prepareConfirmation(
                                                user(inkforgeToken),
                                                episodeId,
                                                json.valueToTree(
                                                        prepareVideoEpisodeScriptConfirmationRequest)),
                                VideoEpisodeScriptConfirmationResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeListResponse>
            reorderVideoEpisodesApiV1VideoProjectsProjectIdEpisodesReorderPost(
                    String projectId,
                    ReorderVideoEpisodesRequest reorderVideoEpisodesRequest,
                    String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes()
                                        .reorder(
                                                user(inkforgeToken),
                                                projectId,
                                                json.valueToTree(reorderVideoEpisodesRequest)),
                                VideoEpisodeListResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptDraftResponse>
            saveVideoEpisodeScriptDraftApiV1VideoEpisodesEpisodeIdScriptDraftPut(
                    String episodeId,
                    SaveVideoEpisodeScriptDraftRequest saveVideoEpisodeScriptDraftRequest,
                    String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes()
                                        .saveDraft(
                                                user(inkforgeToken),
                                                episodeId,
                                                json.valueToTree(
                                                        saveVideoEpisodeScriptDraftRequest)),
                                VideoEpisodeScriptDraftResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeScriptRunResponse>
            startVideoEpisodeScriptRunApiV1VideoEpisodesEpisodeIdScriptRunsPost(
                    String episodeId,
                    StartVideoEpisodeScriptRunRequest startVideoEpisodeScriptRunRequest,
                    String inkforgeToken) {
        return ResponseEntity.status(202)
                .body(
                        json.convertValue(
                                runs().start(
                                                user(inkforgeToken),
                                                episodeId,
                                                json.valueToTree(
                                                        startVideoEpisodeScriptRunRequest)),
                                VideoEpisodeScriptRunResponse.class));
    }

    @Override
    public ResponseEntity<VideoEpisodeResponse> updateVideoEpisodeApiV1VideoEpisodesEpisodeIdPatch(
            String episodeId,
            UpdateVideoEpisodeRequest updateVideoEpisodeRequest,
            String inkforgeToken) {
        return ResponseEntity.status(200)
                .body(
                        json.convertValue(
                                episodes()
                                        .update(
                                                user(inkforgeToken),
                                                episodeId,
                                                json.valueToTree(updateVideoEpisodeRequest)),
                                VideoEpisodeResponse.class));
    }

    private VideoEpisodeService episodes() {
        return episodes.orElseThrow(
                () -> new ApiException(503, "VIDEO_EPISODE_SERVICE_UNAVAILABLE", "剧集服务暂时不可用"));
    }

    private VideoEpisodeScriptRunService runs() {
        return runs.orElseThrow(
                () -> new ApiException(503, "VIDEO_EPISODE_RUN_UNAVAILABLE", "剧本执行服务暂时不可用"));
    }

    private String user(String token) {
        return users.orElseThrow(() -> new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token)
                .id();
    }
}
