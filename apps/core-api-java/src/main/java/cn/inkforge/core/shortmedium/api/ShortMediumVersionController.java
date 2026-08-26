package cn.inkforge.core.shortmedium.api;

import cn.inkforge.contracts.api.DocumentType;
import cn.inkforge.contracts.api.ManualVersionRequest;
import cn.inkforge.contracts.api.VersionActionRequest;
import cn.inkforge.contracts.api.VersionDetailResponse;
import cn.inkforge.contracts.api.VersionDiffResponse;
import cn.inkforge.contracts.api.VersionListItem;
import cn.inkforge.contracts.api.VersionPreviewRequest;
import cn.inkforge.contracts.api.VersionPreviewResponse;
import cn.inkforge.core.generated.api.ShortmediumApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.shortmedium.application.ShortMediumVersionService;
import java.util.List;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

/** 冻结的 7 个中短篇不可变版本公共接口。 */
@RestController
public final class ShortMediumVersionController implements ShortmediumApi {

    private final Optional<ShortMediumVersionService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;

    public ShortMediumVersionController(
            Optional<ShortMediumVersionService> configuredService,
            Optional<CurrentUserAccess> configuredUsers) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
    }

    @Override
    public ResponseEntity<VersionDetailResponse>
            adoptCandidateVersionApiV1NovelsNovelIdVersionsVersionIdAdoptPost(
                    String novelId,
                    String versionId,
                    VersionActionRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().adopt(
                user(inkforgeToken).id(), novelId, versionId, request));
    }

    @Override
    public ResponseEntity<VersionDetailResponse>
            getVersionApiV1NovelsNovelIdVersionsVersionIdGet(
                    String novelId, String versionId, String inkforgeToken) {
        return ResponseEntity.ok(service().get(
                user(inkforgeToken).id(), novelId, versionId));
    }

    @Override
    public ResponseEntity<VersionDiffResponse>
            getVersionDiffApiV1NovelsNovelIdVersionDiffGet(
                    String novelId,
                    String fromVersionId,
                    String toVersionId,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().diffVersions(
                user(inkforgeToken).id(), novelId, fromVersionId, toVersionId));
    }

    @Override
    public ResponseEntity<List<VersionListItem>>
            listVersionsApiV1NovelsNovelIdVersionsGet(
                    String novelId,
                    DocumentType documentType,
                    String chapterId,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().list(
                user(inkforgeToken).id(), novelId, documentType, chapterId));
    }

    @Override
    public ResponseEntity<VersionPreviewResponse>
            previewVersionApiV1NovelsNovelIdVersionsPreviewPost(
                    String novelId,
                    VersionPreviewRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().preview(
                user(inkforgeToken).id(), novelId, request));
    }

    @Override
    public ResponseEntity<VersionDetailResponse>
            restoreHistoricalVersionApiV1NovelsNovelIdVersionsVersionIdRestorePost(
                    String novelId,
                    String versionId,
                    VersionActionRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().restore(
                user(inkforgeToken).id(), novelId, versionId, request));
    }

    @Override
    public ResponseEntity<VersionDetailResponse>
            submitManualVersionApiV1NovelsNovelIdVersionsPost(
                    String novelId,
                    ManualVersionRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().submitManual(
                user(inkforgeToken).id(), novelId, request));
    }

    private ShortMediumVersionService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503,
                "SHORT_MEDIUM_VERSION_SERVICE_UNAVAILABLE",
                "中短篇版本服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }
}
