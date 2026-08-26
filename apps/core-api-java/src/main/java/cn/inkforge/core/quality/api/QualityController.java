package cn.inkforge.core.quality.api;

import cn.inkforge.contracts.api.QualityCheckDto;
import cn.inkforge.contracts.api.QualityRunContextRequest;
import cn.inkforge.contracts.api.QualityRunContextResponse;
import cn.inkforge.contracts.api.QualityRunFailureRequest;
import cn.inkforge.contracts.api.QualityRunSuccessRequest;
import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.RunQualityCheckResponse;
import cn.inkforge.contracts.api.UpdateQualityCheckRequest;
import cn.inkforge.core.generated.api.QualityApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.core.quality.application.QualityService;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** 冻结的三个作者质量接口与三个受签名 Agent 接口。 */
@RestController
public final class QualityController implements QualityApi {

    private final Optional<QualityService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;
    private final Optional<InternalServiceAuthenticator> configuredAuthenticator;

    public QualityController(
            Optional<QualityService> configuredService,
            Optional<CurrentUserAccess> configuredUsers,
            Optional<InternalServiceAuthenticator> configuredAuthenticator) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
        this.configuredAuthenticator = configuredAuthenticator;
    }

    @Override
    public ResponseEntity<QualityCheckDto> getQualityCheckApiV1QualityChecksCheckIdGet(
            String checkId, String token) {
        return ResponseEntity.ok(service().get(user(token).id(), checkId));
    }

    @Override
    public ResponseEntity<QualityCheckDto> updateQualityCheckApiV1QualityChecksCheckIdPatch(
            String checkId, UpdateQualityCheckRequest request, String token) {
        return ResponseEntity.ok(service().update(user(token).id(), checkId, request));
    }

    @Override
    public ResponseEntity<RunQualityCheckResponse>
            runQualityCheckApiV1QualityChecksCheckIdRunPost(
                    String checkId, RunQualityCheckRequest request, String token) {
        return ResponseEntity.accepted()
                .body(service().run(user(token).id(), checkId, request));
    }

    @Override
    public ResponseEntity<QualityRunContextResponse>
            getQualityContextInternalV1QualityChecksCheckIdContextPost(
                    String checkId, QualityRunContextRequest request) {
        authenticate(request.getTaskId(), request.getRunId(), request.getNovelId());
        return ResponseEntity.ok(service().context(checkId, request));
    }

    @Override
    public ResponseEntity<Void> completeQualityInternalV1QualityChecksCheckIdSuccessPut(
            String checkId, QualityRunSuccessRequest request) {
        authenticate(request.getTaskId(), request.getRunId(), request.getNovelId());
        service().complete(checkId, request);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<Void> failQualityInternalV1QualityChecksCheckIdFailurePut(
            String checkId, QualityRunFailureRequest request) {
        authenticate(request.getTaskId(), request.getRunId(), request.getNovelId());
        service().fail(checkId, request);
        return ResponseEntity.noContent().build();
    }

    private void authenticate(String taskId, String runId, String novelId) {
        configuredAuthenticator.orElseThrow(() -> new ApiException(
                        503,
                        "QUALITY_CALLBACK_AUTH_UNAVAILABLE",
                        "质量检查回调认证暂时不可用"))
                .authenticate(
                        currentRequest(),
                        RawRequestBody.current(),
                        ServiceScope.QUALITY_WRITE,
                        taskId,
                        runId,
                        novelId,
                        "QUALITY_CALLBACK_AUTH_UNAVAILABLE",
                        "质量检查回调认证暂时不可用");
    }

    private QualityService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503,
                "QUALITY_SERVICE_UNAVAILABLE",
                "质量检查服务暂时不可用"));
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
