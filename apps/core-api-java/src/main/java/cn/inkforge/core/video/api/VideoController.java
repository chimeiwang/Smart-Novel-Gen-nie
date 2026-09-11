package cn.inkforge.core.video.api;

import cn.inkforge.contracts.api.ApproveVisualCanonRequest;
import cn.inkforge.contracts.api.ConfirmVideoAssetRequest;
import cn.inkforge.contracts.api.CreateVideoProjectRequest;
import cn.inkforge.contracts.api.CreateVisualCanonCandidateRequest;
import cn.inkforge.contracts.api.VideoAssetResponse;
import cn.inkforge.contracts.api.VideoProjectDetailResponse;
import cn.inkforge.contracts.api.VideoProjectListResponse;
import cn.inkforge.contracts.api.VideoProjectResponse;
import cn.inkforge.contracts.api.VisualCanonLibraryResponse;
import cn.inkforge.contracts.api.VisualCanonResponse;
import cn.inkforge.core.generated.api.VideoApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.ResolvedVideoAsset;
import cn.inkforge.core.video.application.ResolvedVideoFile;
import cn.inkforge.core.video.application.VideoEpisodeRenderService;
import cn.inkforge.core.video.application.VideoProjectService;
import cn.inkforge.core.video.application.VideoVisualCanonService;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/**
 * 冻结视频 OpenAPI 的 HTTP 投影。
 *
 * <p>控制器只做浏览器身份解析、共享素材响应和文件流适配，产品规则、事务与媒体执行均委托应用端口。
 * 依赖使用 {@link Optional} 是为了让关闭视频或缺少数据库的健康上下文仍能启动；真正调用时统一返回稳定 503，
 * 绝不能因此绕过功能开关。
 */
@RestController
public final class VideoController implements VideoApi {

    private final Optional<VideoProjectService> configuredProjects;
    private final Optional<VideoVisualCanonService> configuredCanons;
    private final Optional<VideoEpisodeRenderService> configuredEpisodeRenders;
    private final Optional<CurrentUserAccess> configuredUsers;

    public VideoController(
            Optional<VideoProjectService> configuredProjects,
            Optional<VideoVisualCanonService> configuredCanons,
            Optional<VideoEpisodeRenderService> configuredEpisodeRenders,
            Optional<CurrentUserAccess> configuredUsers) {
        this.configuredProjects = configuredProjects;
        this.configuredCanons = configuredCanons;
        this.configuredEpisodeRenders = configuredEpisodeRenders;
        this.configuredUsers = configuredUsers;
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
    public ResponseEntity<VideoAssetResponse> confirmAssetApiV1VideoAssetsAssetIdRightsPatch(
            String assetId, ConfirmVideoAssetRequest request, String token) {
        return ResponseEntity.ok(projects().confirmAsset(user(token).id(), assetId, request));
    }

    @Override
    public ResponseEntity<VideoProjectResponse> createProjectApiV1VideoNovelsNovelIdProjectsPost(
            String novelId, CreateVideoProjectRequest request, String token) {
        return ResponseEntity.status(201)
                .body(projects().createProject(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<StreamingResponseBody> downloadAssetApiV1VideoAssetsAssetIdContentGet(
            String assetId, String token) {
        ResolvedVideoFile file = projects().getAssetFile(user(token).id(), assetId);
        return VideoFileResponses.attachment(
                file.path(), file.mimeType(), file.filename());
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
    public ResponseEntity<VisualCanonResponse>
            setVisualCanonCandidateApiV1VideoProjectsProjectIdVisualCanonsPost(
                    String projectId,
                    CreateVisualCanonCandidateRequest request,
                    String token) {
        return ResponseEntity.status(201)
                .body(canons().setCandidate(user(token).id(), projectId, request));
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

    private VideoProjectService projects() {
        return configuredProjects.orElseThrow(() -> new ApiException(
                503, "VIDEO_SERVICE_UNAVAILABLE", "视频制作服务暂时不可用"));
    }

    private VideoVisualCanonService canons() {
        return configuredCanons.orElseThrow(() -> new ApiException(
                503, "VIDEO_SERVICE_UNAVAILABLE", "视觉设定服务暂时不可用"));
    }

    private VideoEpisodeRenderService renders() {
        return configuredEpisodeRenders.orElseThrow(() -> new ApiException(
                503,
                "VIDEO_EPISODE_RENDER_SERVICE_UNAVAILABLE",
                "独立剧集逐镜生成服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }

}
