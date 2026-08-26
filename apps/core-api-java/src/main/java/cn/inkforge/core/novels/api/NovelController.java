package cn.inkforge.core.novels.api;

import cn.inkforge.contracts.api.CreateNovelRequest;
import cn.inkforge.contracts.api.CreateNovelResponse;
import cn.inkforge.contracts.api.DashboardResponse;
import cn.inkforge.contracts.api.NovelResponse;
import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.contracts.api.UpdateNovelSummaryRequest;
import cn.inkforge.contracts.api.WorkspaceBootstrapResponse;
import cn.inkforge.contracts.api.WorkspaceLoreResponse;
import cn.inkforge.contracts.api.WorkspacePlanningResponse;
import cn.inkforge.contracts.api.WorkspaceResourcesResponse;
import cn.inkforge.contracts.api.WorkspaceResponse;
import cn.inkforge.core.generated.api.NovelsApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.novels.application.NovelService;
import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

/** 冻结的十个小说、Dashboard 与工作区 HTTP 接口。 */
@RestController
public final class NovelController implements NovelsApi {

    private final Optional<NovelService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;

    public NovelController(
            Optional<NovelService> configuredService,
            Optional<CurrentUserAccess> configuredUsers) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
    }

    @Override
    public ResponseEntity<CreateNovelResponse> createNovelApiV1NovelsPost(
            CreateNovelRequest request, String token) {
        return ResponseEntity.status(201).body(service().create(user(token).id(), request));
    }

    @Override
    public ResponseEntity<DashboardResponse> getDashboardApiV1DashboardGet(String token) {
        return ResponseEntity.ok(service().dashboard(user(token).id()));
    }

    @Override
    public ResponseEntity<NovelResponse> getNovelApiV1NovelsNovelIdGet(
            String novelId, String token) {
        return ResponseEntity.ok(service().get(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<WorkspaceResponse> getWorkspaceApiV1NovelsNovelIdWorkspaceGet(
            String novelId, String chapterId, String token) {
        return ResponseEntity.ok(service().workspace(user(token).id(), novelId, chapterId));
    }

    @Override
    public ResponseEntity<WorkspaceBootstrapResponse>
            getWorkspaceBootstrapApiV1NovelsNovelIdWorkspaceBootstrapGet(
                    String novelId, String chapterId, String token) {
        return ResponseEntity.ok(
                service().workspaceBootstrap(user(token).id(), novelId, chapterId));
    }

    @Override
    public ResponseEntity<WorkspaceLoreResponse>
            getWorkspaceLoreApiV1NovelsNovelIdWorkspaceLoreGet(
                    String novelId, String token) {
        return ResponseEntity.ok(service().workspaceLore(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<WorkspacePlanningResponse>
            getWorkspacePlanningApiV1NovelsNovelIdWorkspacePlanningGet(
                    String novelId, String token) {
        return ResponseEntity.ok(service().workspacePlanning(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<WorkspaceResourcesResponse>
            getWorkspaceResourcesApiV1NovelsNovelIdWorkspaceResourcesGet(
                    String novelId, String token) {
        return ResponseEntity.ok(service().workspaceResources(user(token).id(), novelId));
    }

    @Override
    public ResponseEntity<List<NovelResponse>> listNovelsApiV1NovelsGet(
            StoryLengthProfile profile, String token) {
        return ResponseEntity.ok(service().list(user(token).id(), profile));
    }

    @Override
    public ResponseEntity<NovelResponse> updateNovelSummaryApiV1NovelsNovelIdSummaryPut(
            String novelId, UpdateNovelSummaryRequest request, String token) {
        return ResponseEntity.ok(
                service().updateSummary(user(token).id(), novelId, request));
    }

    private NovelService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503, "NOVEL_SERVICE_UNAVAILABLE", "小说服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }
}
