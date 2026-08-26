package cn.inkforge.core.references.api;

import cn.inkforge.contracts.api.CompleteReferenceIndexRequest;
import cn.inkforge.contracts.api.CreateReferenceRequest;
import cn.inkforge.contracts.api.CreateReferenceResponse;
import cn.inkforge.contracts.api.DeleteReferenceImpactResponse;
import cn.inkforge.contracts.api.DeleteReferenceRequest;
import cn.inkforge.contracts.api.FailReferenceIndexRequest;
import cn.inkforge.contracts.api.RagSearchRequest;
import cn.inkforge.contracts.api.RagSearchResult;
import cn.inkforge.contracts.api.ReferenceIndexContextRequest;
import cn.inkforge.contracts.api.ReferenceIndexContextResponse;
import cn.inkforge.contracts.api.ReferenceMaterialResponse;
import cn.inkforge.contracts.api.ReindexAcceptedResponse;
import cn.inkforge.contracts.api.ReindexReferenceRequest;
import cn.inkforge.contracts.api.UpdateReferenceRequest;
import cn.inkforge.core.generated.api.ReferencesApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.core.references.application.ReferenceService;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** 冻结的六个浏览器资料接口和三个受签名 Agent 索引接口。 */
@RestController
public final class ReferenceController implements ReferencesApi {

    private final Optional<ReferenceService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;
    private final Optional<InternalServiceAuthenticator> configuredAuthenticator;

    public ReferenceController(
            Optional<ReferenceService> configuredService,
            Optional<CurrentUserAccess> configuredUsers,
            Optional<InternalServiceAuthenticator> configuredAuthenticator) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
        this.configuredAuthenticator = configuredAuthenticator;
    }

    @Override
    public ResponseEntity<List<ReferenceMaterialResponse>>
            listReferencesApiV1NovelsNovelIdReferencesGet(
                    String novelId, String inkforgeToken) {
        return ResponseEntity.ok(service().list(user(inkforgeToken).id(), novelId));
    }

    @Override
    public ResponseEntity<CreateReferenceResponse>
            createReferenceApiV1NovelsNovelIdReferencesPost(
                    String novelId,
                    CreateReferenceRequest request,
                    String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(service().create(user(inkforgeToken).id(), novelId, request));
    }

    @Override
    public ResponseEntity<ReferenceMaterialResponse>
            updateReferenceApiV1NovelsNovelIdReferencesReferenceIdPatch(
                    String novelId,
                    String referenceId,
                    UpdateReferenceRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().update(
                user(inkforgeToken).id(), novelId, referenceId, request));
    }

    @Override
    public ResponseEntity<DeleteReferenceImpactResponse>
            deleteReferenceApiV1NovelsNovelIdReferencesReferenceIdDelete(
                    String novelId,
                    String referenceId,
                    DeleteReferenceRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().delete(
                user(inkforgeToken).id(), novelId, referenceId, request));
    }

    @Override
    public ResponseEntity<ReindexAcceptedResponse>
            reindexReferenceApiV1NovelsNovelIdReferencesReferenceIdReindexPost(
                    String novelId,
                    String referenceId,
                    ReindexReferenceRequest request,
                    String inkforgeToken) {
        return ResponseEntity.status(202)
                .body(service().reindex(
                        user(inkforgeToken).id(), novelId, referenceId, request));
    }

    @Override
    public ResponseEntity<List<RagSearchResult>>
            searchReferencesApiV1NovelsNovelIdReferencesSearchPost(
                    String novelId,
                    RagSearchRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().search(user(inkforgeToken).id(), novelId, request));
    }

    @Override
    public ResponseEntity<ReferenceMaterialResponse>
            completeReferenceIndexInternalV1NovelsNovelIdReferencesReferenceIdIndexSuccessPut(
                    String novelId,
                    String referenceId,
                    CompleteReferenceIndexRequest request) {
        authenticate(request.getTaskId(), request.getRunId(), novelId);
        return ResponseEntity.ok(service().completeIndex(novelId, referenceId, request));
    }

    @Override
    public ResponseEntity<ReferenceIndexContextResponse>
            getReferenceIndexContextInternalV1NovelsNovelIdReferencesReferenceIdIndexContextPost(
                    String novelId,
                    String referenceId,
                    ReferenceIndexContextRequest request) {
        authenticate(request.getTaskId(), request.getRunId(), novelId);
        return ResponseEntity.ok(service().indexContext(novelId, referenceId, request));
    }

    @Override
    public ResponseEntity<Void>
            failReferenceIndexInternalV1NovelsNovelIdReferencesReferenceIdIndexFailurePut(
                    String novelId,
                    String referenceId,
                    FailReferenceIndexRequest request) {
        authenticate(request.getTaskId(), request.getRunId(), novelId);
        service().failIndex(novelId, referenceId, request);
        return ResponseEntity.noContent().build();
    }

    private void authenticate(String taskId, String runId, String novelId) {
        InternalServiceAuthenticator authenticator = configuredAuthenticator.orElseThrow(() ->
                new ApiException(
                        503,
                        "RAG_CALLBACK_AUTH_UNAVAILABLE",
                        "索引回调认证暂时不可用"));
        authenticator.authenticate(
                currentRequest(),
                RawRequestBody.current(),
                ServiceScope.RAG_INDEX_WRITE,
                taskId,
                runId,
                novelId,
                "RAG_CALLBACK_AUTH_UNAVAILABLE",
                "索引回调认证暂时不可用");
    }

    private ReferenceService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503, "REFERENCE_SERVICE_UNAVAILABLE", "参考资料服务暂时不可用"));
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
        throw new ApiException(500, "REQUEST_CONTEXT_UNAVAILABLE", "内部请求上下文不可用");
    }
}
