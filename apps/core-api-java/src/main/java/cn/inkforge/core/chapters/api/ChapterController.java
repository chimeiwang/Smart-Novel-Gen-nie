package cn.inkforge.core.chapters.api;

import cn.inkforge.contracts.api.ChapterListResponse;
import cn.inkforge.contracts.api.ChapterMutationResponse;
import cn.inkforge.contracts.api.ChapterProgressRequest;
import cn.inkforge.contracts.api.ChapterStatusRequest;
import cn.inkforge.contracts.api.ChapterStatusResponse;
import cn.inkforge.contracts.api.CreateChapterResponse;
import cn.inkforge.contracts.api.UpdateChapterRequest;
import cn.inkforge.contracts.api.WorkspaceChapter;
import cn.inkforge.core.chapters.application.ChapterService;
import cn.inkforge.core.generated.api.ChaptersApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

/** 冻结的六个章节 HTTP 接口；认证和业务均通过应用接口进入。 */
@RestController
public final class ChapterController implements ChaptersApi {

    private final Optional<ChapterService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;

    public ChapterController(
            Optional<ChapterService> configuredService,
            Optional<CurrentUserAccess> configuredUsers) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
    }

    @Override
    public ResponseEntity<CreateChapterResponse>
            createChapterApiV1NovelsNovelIdChaptersPost(
                    String novelId, String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(service().create(user(inkforgeToken).id(), novelId));
    }

    @Override
    public ResponseEntity<WorkspaceChapter> getChapterApiV1ChaptersChapterIdGet(
            String chapterId, String inkforgeToken) {
        return ResponseEntity.ok(service().get(user(inkforgeToken).id(), chapterId));
    }

    @Override
    public ResponseEntity<ChapterListResponse>
            listChaptersApiV1NovelsNovelIdChaptersGet(
                    String novelId, String inkforgeToken) {
        return ResponseEntity.ok(service().list(user(inkforgeToken).id(), novelId));
    }

    @Override
    public ResponseEntity<ChapterMutationResponse>
            updateChapterApiV1ChaptersChapterIdPatch(
                    String chapterId,
                    UpdateChapterRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(
                service().update(user(inkforgeToken).id(), chapterId, request));
    }

    @Override
    public ResponseEntity<ChapterMutationResponse>
            updateChapterProgressApiV1ChaptersChapterIdProgressPut(
                    String chapterId,
                    ChapterProgressRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(
                service().updateProgress(user(inkforgeToken).id(), chapterId, request));
    }

    @Override
    public ResponseEntity<ChapterStatusResponse>
            updateChapterStatusApiV1ChaptersChapterIdStatusPatch(
                    String chapterId,
                    ChapterStatusRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(
                service().setStatus(user(inkforgeToken).id(), chapterId, request));
    }

    private ChapterService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503, "CHAPTER_SERVICE_UNAVAILABLE", "章节服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }
}
