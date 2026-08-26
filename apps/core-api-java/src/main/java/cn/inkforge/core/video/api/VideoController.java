package cn.inkforge.core.video.api;

import cn.inkforge.contracts.api.ApproveVisualCanonRequest;
import cn.inkforge.contracts.api.ChapterAdaptationListResponse;
import cn.inkforge.contracts.api.ChapterAdaptationResponse;
import cn.inkforge.contracts.api.ChapterAdaptationTaskAcceptedResponse;
import cn.inkforge.contracts.api.ChapterPostProductionWorkspaceResponse;
import cn.inkforge.contracts.api.ChapterRenderWorkspaceResponse;
import cn.inkforge.contracts.api.ConfirmAdaptationPlanRequest;
import cn.inkforge.contracts.api.ConfirmShotTakeRequest;
import cn.inkforge.contracts.api.ConfirmVideoAssetRequest;
import cn.inkforge.contracts.api.CreateChapterAdaptationRequest;
import cn.inkforge.contracts.api.CreateVideoProjectRequest;
import cn.inkforge.contracts.api.CreateVisualCanonCandidateRequest;
import cn.inkforge.contracts.api.DiscardAdaptationCandidateRequest;
import cn.inkforge.contracts.api.EpisodeEditHeadResponse;
import cn.inkforge.contracts.api.EpisodeEditVersionResponse;
import cn.inkforge.contracts.api.EpisodeExportTaskResponse;
import cn.inkforge.contracts.api.EpisodeMixHeadResponse;
import cn.inkforge.contracts.api.EpisodeMixVersionResponse;
import cn.inkforge.contracts.api.ExtractTakeFrameRequest;
import cn.inkforge.contracts.api.PostProductionAssetResponse;
import cn.inkforge.contracts.api.RetryEpisodeExportRequest;
import cn.inkforge.contracts.api.RetryShotRenderRequest;
import cn.inkforge.contracts.api.SaveEpisodeEditVersionRequest;
import cn.inkforge.contracts.api.SaveEpisodeMixVersionRequest;
import cn.inkforge.contracts.api.SaveEpisodePlanRequest;
import cn.inkforge.contracts.api.SaveShotKeyframeVersionRequest;
import cn.inkforge.contracts.api.SaveShotPromptRequest;
import cn.inkforge.contracts.api.SaveShotVisualReferencesRequest;
import cn.inkforge.contracts.api.ShotKeyframeHeadResponse;
import cn.inkforge.contracts.api.ShotRenderTaskResponse;
import cn.inkforge.contracts.api.ShotTakeDecisionResponse;
import cn.inkforge.contracts.api.ShotVisualReferenceSetResponse;
import cn.inkforge.contracts.api.StartEpisodeExportRequest;
import cn.inkforge.contracts.api.StartPromptRunRequest;
import cn.inkforge.contracts.api.StartShotPlanRunRequest;
import cn.inkforge.contracts.api.StartShotRenderRequest;
import cn.inkforge.contracts.api.VideoAdaptationCheckpointCallback;
import cn.inkforge.contracts.api.VideoAdaptationFailureCallback;
import cn.inkforge.contracts.api.VideoAdaptationPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationPromptCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressQuery;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressResponse;
import cn.inkforge.contracts.api.VideoAssetResponse;
import cn.inkforge.contracts.api.VideoPlanCallReservationRequest;
import cn.inkforge.contracts.api.VideoPlanCallReservationResponse;
import cn.inkforge.contracts.api.VideoPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoPlanFailureCallback;
import cn.inkforge.contracts.api.VideoPlanProgressQuery;
import cn.inkforge.contracts.api.VideoPlanProgressResponse;
import cn.inkforge.contracts.api.VideoProjectDetailResponse;
import cn.inkforge.contracts.api.VideoProjectListResponse;
import cn.inkforge.contracts.api.VideoProjectResponse;
import cn.inkforge.contracts.api.VideoStoryPlanCheckpointCallback;
import cn.inkforge.contracts.api.VisualCanonLibraryResponse;
import cn.inkforge.contracts.api.VisualCanonResponse;
import cn.inkforge.core.generated.api.VideoApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.core.video.application.LegacyVideoPlanService;
import cn.inkforge.core.video.application.ResolvedVideoAsset;
import cn.inkforge.core.video.application.ResolvedVideoFile;
import cn.inkforge.core.video.application.VideoAdaptationService;
import cn.inkforge.core.video.application.VideoPostProductionService;
import cn.inkforge.core.video.application.VideoProjectService;
import cn.inkforge.core.video.application.VideoRenderService;
import cn.inkforge.core.video.application.VideoVisualCanonService;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Objects;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/**
 * 冻结视频 OpenAPI 的 HTTP 投影。
 *
 * <p>控制器只做浏览器身份解析、内部回调的路径/正文绑定和响应流适配，产品规则、事务与媒体执行均委托应用端口。
 * 依赖使用 {@link Optional} 是为了让关闭视频或缺少数据库的健康上下文仍能启动；真正调用时统一返回稳定 503，
 * 绝不能因此绕过功能开关。
 */
@RestController
public final class VideoController implements VideoApi {

    private final Optional<VideoProjectService> configuredProjects;
    private final Optional<VideoAdaptationService> configuredAdaptations;
    private final Optional<VideoVisualCanonService> configuredCanons;
    private final Optional<VideoRenderService> configuredRenders;
    private final Optional<VideoPostProductionService> configuredPostProduction;
    private final Optional<LegacyVideoPlanService> configuredLegacyPlans;
    private final Optional<CurrentUserAccess> configuredUsers;
    private final Optional<InternalServiceAuthenticator> configuredAuthenticator;

    public VideoController(
            Optional<VideoProjectService> configuredProjects,
            Optional<VideoAdaptationService> configuredAdaptations,
            Optional<VideoVisualCanonService> configuredCanons,
            Optional<VideoRenderService> configuredRenders,
            Optional<VideoPostProductionService> configuredPostProduction,
            Optional<LegacyVideoPlanService> configuredLegacyPlans,
            Optional<CurrentUserAccess> configuredUsers,
            Optional<InternalServiceAuthenticator> configuredAuthenticator) {
        this.configuredProjects = configuredProjects;
        this.configuredAdaptations = configuredAdaptations;
        this.configuredCanons = configuredCanons;
        this.configuredRenders = configuredRenders;
        this.configuredPostProduction = configuredPostProduction;
        this.configuredLegacyPlans = configuredLegacyPlans;
        this.configuredUsers = configuredUsers;
        this.configuredAuthenticator = configuredAuthenticator;
    }

    @Override
    public ResponseEntity<VisualCanonResponse>
            approveVisualCanonApiV1VideoVisualCanonsCanonIdApprovePost(
                    String canonId,
                    ApproveVisualCanonRequest request,
                    String token) {
        return ResponseEntity.ok(canons().approve(user(token).id(), canonId, request));
    }

    @Override
    public ResponseEntity<Void>
            completePlanInternalV1VideoAdaptationsAdaptationIdPlanCompletePost(
                    String adaptationId,
                    VideoAdaptationPlanCompletionCallback callback) {
        verifyAdaptation(adaptationId, callback.getAdaptationId(),
                callback.getTaskId(), callback.getRunId(), callback.getNovelId());
        adaptations().completePlan(callback);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<Void> completePlanInternalV1VideoScenesSceneIdCompletePost(
            String sceneId, VideoPlanCompletionCallback callback) {
        verifyScene(sceneId, callback.getSceneId(),
                callback.getTaskId(), callback.getRunId(), callback.getNovelId());
        legacyPlans().complete(callback);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<Void>
            completePromptsInternalV1VideoAdaptationsAdaptationIdPromptsCompletePost(
                    String adaptationId,
                    VideoAdaptationPromptCompletionCallback callback) {
        verifyAdaptation(adaptationId, callback.getAdaptationId(),
                callback.getTaskId(), callback.getRunId(), callback.getNovelId());
        adaptations().completePrompts(callback);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<VideoAssetResponse> confirmAssetApiV1VideoAssetsAssetIdRightsPatch(
            String assetId, ConfirmVideoAssetRequest request, String token) {
        return ResponseEntity.ok(projects().confirmAsset(user(token).id(), assetId, request));
    }

    @Override
    public ResponseEntity<ChapterAdaptationResponse>
            confirmShotPlanApiV1VideoChapterAdaptationsAdaptationIdShotPlanConfirmPost(
                    String adaptationId,
                    ConfirmAdaptationPlanRequest request,
                    String token) {
        return ResponseEntity.ok(
                adaptations().confirmPlan(user(token).id(), adaptationId, request));
    }

    @Override
    public ResponseEntity<ShotTakeDecisionResponse>
            confirmShotTakeApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdTakesTakeIdConfirmPost(
                    String adaptationId,
                    String shotId,
                    String takeId,
                    ConfirmShotTakeRequest request,
                    String token) {
        return ResponseEntity.ok(renders().confirmTake(
                user(token).id(), adaptationId, shotId, takeId, request));
    }

    @Override
    public ResponseEntity<ChapterAdaptationResponse>
            createAdaptationApiV1VideoProjectsProjectIdChapterAdaptationsPost(
                    String projectId,
                    CreateChapterAdaptationRequest request,
                    String token) {
        return ResponseEntity.status(201)
                .body(adaptations().create(user(token).id(), projectId, request));
    }

    @Override
    public ResponseEntity<EpisodeExportTaskResponse>
            createEpisodeExportTaskApiV1VideoChapterAdaptationsAdaptationIdEpisodesEpisodeNoExportTasksPost(
                    String adaptationId,
                    Integer episodeNo,
                    StartEpisodeExportRequest request,
                    String token) {
        return ResponseEntity.accepted().body(postProduction().createExportTask(
                user(token).id(), adaptationId, episodeNo, request));
    }

    @Override
    public ResponseEntity<VideoProjectResponse> createProjectApiV1VideoNovelsNovelIdProjectsPost(
            String novelId, CreateVideoProjectRequest request, String token) {
        return ResponseEntity.status(201)
                .body(projects().createProject(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<ShotRenderTaskResponse>
            createRenderTaskApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdRenderTasksPost(
                    String adaptationId,
                    String shotId,
                    StartShotRenderRequest request,
                    String token) {
        return ResponseEntity.accepted().body(renders().createTask(
                user(token).id(), adaptationId, shotId, request));
    }

    @Override
    public ResponseEntity<ChapterAdaptationResponse>
            discardCandidateApiV1VideoChapterAdaptationsAdaptationIdCandidateDiscardPost(
                    String adaptationId,
                    DiscardAdaptationCandidateRequest request,
                    String token) {
        return ResponseEntity.ok(
                adaptations().discardCandidate(user(token).id(), adaptationId, request));
    }

    @Override
    public ResponseEntity<StreamingResponseBody> downloadAssetApiV1VideoAssetsAssetIdContentGet(
            String assetId, String token) {
        ResolvedVideoFile file = projects().getAssetFile(user(token).id(), assetId);
        return VideoFileResponses.attachment(
                file.path(), file.mimeType(), file.filename());
    }

    @Override
    public ResponseEntity<PostProductionAssetResponse> extractTakeFrameApiV1VideoTakesTakeIdFramesPost(
            String takeId, ExtractTakeFrameRequest request, String token) {
        return ResponseEntity.status(201)
                .body(postProduction().extractTakeFrame(user(token).id(), takeId, request));
    }

    @Override
    public ResponseEntity<Void> failPlanInternalV1VideoScenesSceneIdFailPost(
            String sceneId, VideoPlanFailureCallback callback) {
        verifyScene(sceneId, callback.getSceneId(),
                callback.getTaskId(), callback.getRunId(), callback.getNovelId());
        legacyPlans().fail(callback);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<Void> failTaskInternalV1VideoAdaptationsAdaptationIdFailPost(
            String adaptationId, VideoAdaptationFailureCallback callback) {
        verifyAdaptation(adaptationId, callback.getAdaptationId(),
                callback.getTaskId(), callback.getRunId(), callback.getNovelId());
        adaptations().fail(callback);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<ChapterAdaptationResponse>
            getAdaptationApiV1VideoChapterAdaptationsAdaptationIdGet(
                    String adaptationId, String token) {
        return ResponseEntity.ok(adaptations().get(user(token).id(), adaptationId));
    }

    @Override
    public ResponseEntity<EpisodeEditVersionResponse>
            getEpisodeEditVersionApiV1VideoEditVersionsVersionIdGet(
                    String versionId, String token) {
        return ResponseEntity.ok(
                postProduction().getEditVersion(user(token).id(), versionId));
    }

    @Override
    public ResponseEntity<StreamingResponseBody>
            getEpisodeExportContentApiV1VideoExportsExportIdContentGet(
                    String exportId, String token) {
        ResolvedVideoAsset file =
                postProduction().getExportFile(user(token).id(), exportId);
        return VideoFileResponses.inline(file.path(), file.mimeType(), file.name());
    }

    @Override
    public ResponseEntity<EpisodeExportTaskResponse>
            getEpisodeExportTaskApiV1VideoExportTasksTaskIdGet(
                    String taskId, String token) {
        return ResponseEntity.ok(
                postProduction().getExportTask(user(token).id(), taskId));
    }

    @Override
    public ResponseEntity<EpisodeMixVersionResponse>
            getEpisodeMixVersionApiV1VideoMixVersionsVersionIdGet(
                    String versionId, String token) {
        return ResponseEntity.ok(
                postProduction().getMixVersion(user(token).id(), versionId));
    }

    @Override
    public ResponseEntity<VideoPlanProgressResponse>
            getPlanProgressInternalV1VideoScenesSceneIdProgressPost(
                    String sceneId, VideoPlanProgressQuery query) {
        verifyScene(sceneId, query.getSceneId(),
                query.getTaskId(), query.getRunId(), query.getNovelId());
        return ResponseEntity.ok(legacyPlans().progress(query));
    }

    @Override
    public ResponseEntity<ChapterPostProductionWorkspaceResponse>
            getPostProductionWorkspaceApiV1VideoChapterAdaptationsAdaptationIdPostProductionGet(
                    String adaptationId, String token) {
        return ResponseEntity.ok(
                postProduction().getWorkspace(user(token).id(), adaptationId));
    }

    @Override
    public ResponseEntity<VideoAdaptationWorkflowProgressResponse>
            getProgressInternalV1VideoAdaptationsAdaptationIdProgressPost(
                    String adaptationId,
                    VideoAdaptationWorkflowProgressQuery query) {
        verifyAdaptation(adaptationId, query.getAdaptationId(),
                query.getTaskId(), query.getRunId(), query.getNovelId());
        return ResponseEntity.ok(adaptations().progress(query));
    }

    @Override
    public ResponseEntity<VideoProjectDetailResponse> getProjectApiV1VideoProjectsProjectIdGet(
            String projectId, String token) {
        return ResponseEntity.ok(projects().getProject(user(token).id(), projectId));
    }

    @Override
    public ResponseEntity<StreamingResponseBody> getProviderAssetApiV1VideoProviderAssetsTokenGet(
            String token) {
        ResolvedVideoAsset file = renders().getProviderAssetFile(token);
        return VideoFileResponses.bare(file.path(), file.mimeType());
    }

    @Override
    public ResponseEntity<ShotRenderTaskResponse> getRenderTaskApiV1VideoRenderTasksTaskIdGet(
            String taskId, String token) {
        return ResponseEntity.ok(renders().getTask(user(token).id(), taskId));
    }

    @Override
    public ResponseEntity<ChapterRenderWorkspaceResponse>
            getRenderWorkspaceApiV1VideoChapterAdaptationsAdaptationIdRendersGet(
                    String adaptationId, String token) {
        return ResponseEntity.ok(renders().getWorkspace(user(token).id(), adaptationId));
    }

    @Override
    public ResponseEntity<StreamingResponseBody> getTakeContentApiV1VideoTakesTakeIdContentGet(
            String takeId, String token) {
        ResolvedVideoAsset file = renders().getTakeFile(user(token).id(), takeId);
        return VideoFileResponses.inline(file.path(), file.mimeType(), file.name());
    }

    @Override
    public ResponseEntity<ChapterAdaptationListResponse>
            listAdaptationsApiV1VideoProjectsProjectIdChapterAdaptationsGet(
                    String projectId, String token) {
        return ResponseEntity.ok(adaptations().list(user(token).id(), projectId));
    }

    @Override
    public ResponseEntity<VideoProjectListResponse> listProjectsApiV1VideoNovelsNovelIdProjectsGet(
            String novelId, String token) {
        return ResponseEntity.ok(projects().listProjects(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<VisualCanonLibraryResponse>
            listVisualCanonsApiV1VideoProjectsProjectIdVisualCanonsGet(
                    String projectId, String token) {
        return ResponseEntity.ok(canons().list(user(token).id(), projectId));
    }

    @Override
    public ResponseEntity<StreamingResponseBody> previewAssetApiV1VideoAssetsAssetIdPreviewGet(
            String assetId, String token) {
        ResolvedVideoFile file = projects().getAssetFile(user(token).id(), assetId);
        return VideoFileResponses.bare(file.path(), file.mimeType());
    }

    @Override
    public ResponseEntity<VideoPlanCallReservationResponse>
            reservePlanCallInternalV1VideoScenesSceneIdCallReservationsPost(
                    String sceneId, VideoPlanCallReservationRequest request) {
        verifyScene(sceneId, request.getSceneId(),
                request.getTaskId(), request.getRunId(), request.getNovelId());
        return ResponseEntity.ok(legacyPlans().reserve(request));
    }

    @Override
    public ResponseEntity<EpisodeExportTaskResponse>
            retryEpisodeExportTaskApiV1VideoExportTasksTaskIdRetryPost(
                    String taskId,
                    RetryEpisodeExportRequest request,
                    String token) {
        return ResponseEntity.accepted().body(
                postProduction().retryExportTask(user(token).id(), taskId, request));
    }

    @Override
    public ResponseEntity<ShotRenderTaskResponse>
            retryRenderTaskApiV1VideoRenderTasksTaskIdRetryPost(
                    String taskId,
                    RetryShotRenderRequest request,
                    String token) {
        return ResponseEntity.accepted()
                .body(renders().retryTask(user(token).id(), taskId, request));
    }

    @Override
    public ResponseEntity<Void> saveCheckpointInternalV1VideoAdaptationsAdaptationIdCheckpointPost(
            String adaptationId, VideoAdaptationCheckpointCallback callback) {
        verifyAdaptation(adaptationId, callback.getAdaptationId(),
                callback.getTaskId(), callback.getRunId(), callback.getNovelId());
        adaptations().saveCheckpoint(callback);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<EpisodeEditHeadResponse>
            saveEpisodeEditVersionApiV1VideoChapterAdaptationsAdaptationIdEpisodesEpisodeNoEditVersionsPost(
                    String adaptationId,
                    Integer episodeNo,
                    SaveEpisodeEditVersionRequest request,
                    String token) {
        return ResponseEntity.status(201).body(postProduction().saveEditVersion(
                user(token).id(), adaptationId, episodeNo, request));
    }

    @Override
    public ResponseEntity<EpisodeMixHeadResponse>
            saveEpisodeMixVersionApiV1VideoChapterAdaptationsAdaptationIdEpisodesEpisodeNoMixVersionsPost(
                    String adaptationId,
                    Integer episodeNo,
                    SaveEpisodeMixVersionRequest request,
                    String token) {
        return ResponseEntity.status(201).body(postProduction().saveMixVersion(
                user(token).id(), adaptationId, episodeNo, request));
    }

    @Override
    public ResponseEntity<ChapterAdaptationResponse>
            saveEpisodePlanApiV1VideoChapterAdaptationsAdaptationIdEpisodePlanPut(
                    String adaptationId,
                    SaveEpisodePlanRequest request,
                    String token) {
        return ResponseEntity.ok(
                adaptations().saveEpisodePlan(user(token).id(), adaptationId, request));
    }

    @Override
    public ResponseEntity<ShotKeyframeHeadResponse>
            saveShotKeyframeVersionApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdKeyframeVersionsPost(
                    String adaptationId,
                    String shotId,
                    SaveShotKeyframeVersionRequest request,
                    String token) {
        return ResponseEntity.status(201).body(postProduction().saveKeyframe(
                user(token).id(), adaptationId, shotId, request));
    }

    @Override
    public ResponseEntity<ChapterAdaptationResponse>
            saveShotPromptApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdPromptPut(
                    String adaptationId,
                    String shotId,
                    SaveShotPromptRequest request,
                    String token) {
        return ResponseEntity.ok(adaptations().savePrompt(
                user(token).id(), adaptationId, shotId, request));
    }

    @Override
    public ResponseEntity<ShotVisualReferenceSetResponse>
            saveShotVisualReferencesApiV1VideoChapterAdaptationsAdaptationIdShotsShotIdVisualReferencesPut(
                    String adaptationId,
                    String shotId,
                    SaveShotVisualReferencesRequest request,
                    String token) {
        return ResponseEntity.ok(canons().saveShotReferences(
                user(token).id(), adaptationId, shotId, request));
    }

    @Override
    public ResponseEntity<Void> saveStoryPlanCheckpointInternalV1VideoScenesSceneIdStoryCheckpointPost(
            String sceneId, VideoStoryPlanCheckpointCallback callback) {
        verifyScene(sceneId, callback.getSceneId(),
                callback.getTaskId(), callback.getRunId(), callback.getNovelId());
        legacyPlans().saveCheckpoint(callback);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<VisualCanonResponse>
            setVisualCanonCandidateApiV1VideoProjectsProjectIdVisualCanonsPost(
                    String projectId,
                    CreateVisualCanonCandidateRequest request,
                    String token) {
        return ResponseEntity.status(201)
                .body(canons().setCandidate(user(token).id(), projectId, request));
    }

    @Override
    public ResponseEntity<ChapterAdaptationTaskAcceptedResponse>
            startPromptRunApiV1VideoChapterAdaptationsAdaptationIdPromptRunsPost(
                    String adaptationId,
                    StartPromptRunRequest request,
                    String token) {
        return ResponseEntity.accepted()
                .body(adaptations().startPrompts(user(token).id(), adaptationId, request));
    }

    @Override
    public ResponseEntity<ChapterAdaptationTaskAcceptedResponse>
            startShotPlanApiV1VideoChapterAdaptationsAdaptationIdShotPlanRunsPost(
                    String adaptationId,
                    StartShotPlanRunRequest request,
                    String token) {
        return ResponseEntity.accepted()
                .body(adaptations().startPlan(user(token).id(), adaptationId, request));
    }

    @Override
    public ResponseEntity<VideoAssetResponse> uploadAssetApiV1VideoProjectsProjectIdAssetsPost(
            String projectId,
            String duty,
            MultipartFile file,
            String modality,
            String name,
            String token,
            String sourceKind) {
        return ResponseEntity.status(201).body(projects().uploadAsset(
                user(token).id(), projectId, file, name, modality, duty, sourceKind));
    }

    private void verifyAdaptation(
            String pathId,
            String bodyId,
            String taskId,
            String runId,
            String novelId) {
        // 服务签名校验前先绑定路径资源，防止一个合法令牌把 A 改编的正文回调提交到 B 的 URL。
        if (!Objects.equals(pathId, bodyId)) {
            throw new ApiException(
                    403,
                    "VIDEO_ADAPTATION_CALLBACK_RESOURCE_MISMATCH",
                    "章节影视化回调路径与请求体不一致");
        }
        authenticate(taskId, runId, novelId);
    }

    private void verifyScene(
            String pathId,
            String bodyId,
            String taskId,
            String runId,
            String novelId) {
        if (!Objects.equals(pathId, bodyId)) {
            throw new ApiException(
                    403,
                    "VIDEO_CALLBACK_RESOURCE_MISMATCH",
                    "视频回调路径与请求体场景不一致");
        }
        authenticate(taskId, runId, novelId);
    }

    private void authenticate(String taskId, String runId, String novelId) {
        // 认证器同时绑定原始请求体、scope、task/run/novel；转发头不参与内部身份判断。
        configuredAuthenticator.orElseThrow(() -> new ApiException(
                        503,
                        "VIDEO_CALLBACK_AUTH_UNAVAILABLE",
                        "视频回调认证暂时不可用"))
                .authenticate(
                        currentRequest(),
                        RawRequestBody.current(),
                        ServiceScope.VIDEO_WRITE,
                        taskId,
                        runId,
                        novelId,
                        "VIDEO_CALLBACK_AUTH_UNAVAILABLE",
                        "视频回调认证暂时不可用");
    }

    private VideoProjectService projects() {
        return configuredProjects.orElseThrow(() -> new ApiException(
                503, "VIDEO_SERVICE_UNAVAILABLE", "视频制作服务暂时不可用"));
    }

    private VideoAdaptationService adaptations() {
        return configuredAdaptations.orElseThrow(() -> new ApiException(
                503, "VIDEO_SERVICE_UNAVAILABLE", "章节影视化服务暂时不可用"));
    }

    private VideoVisualCanonService canons() {
        return configuredCanons.orElseThrow(() -> new ApiException(
                503, "VIDEO_SERVICE_UNAVAILABLE", "视觉设定服务暂时不可用"));
    }

    private VideoRenderService renders() {
        return configuredRenders.orElseThrow(() -> new ApiException(
                503,
                "VIDEO_RENDER_SERVICE_UNAVAILABLE",
                "逐镜视频生成服务暂时不可用"));
    }

    private VideoPostProductionService postProduction() {
        return configuredPostProduction.orElseThrow(() -> new ApiException(
                503,
                "VIDEO_POST_PRODUCTION_UNAVAILABLE",
                "视频后期制作服务暂时不可用"));
    }

    private LegacyVideoPlanService legacyPlans() {
        return configuredLegacyPlans.orElseThrow(() -> new ApiException(
                503, "VIDEO_SERVICE_UNAVAILABLE", "历史视频任务收敛服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }

    private static HttpServletRequest currentRequest() {
        if (RequestContextHolder.getRequestAttributes()
                instanceof ServletRequestAttributes attributes) {
            return attributes.getRequest();
        }
        throw new ApiException(
                500,
                "REQUEST_CONTEXT_UNAVAILABLE",
                "内部请求上下文不可用");
    }
}
