package cn.inkforge.core.billing.api;

import cn.inkforge.contracts.api.AuthorizeModelCallRequest;
import cn.inkforge.contracts.api.AuthorizeModelCallResponse;
import cn.inkforge.contracts.api.BillingSummaryResponse;
import cn.inkforge.contracts.api.BillingUsageResponse;
import cn.inkforge.contracts.api.ReportModelUsageRequest;
import cn.inkforge.contracts.api.TaskModelUsageResponse;
import cn.inkforge.contracts.api.UsageChargeResponse;
import cn.inkforge.core.billing.application.BillingService;
import cn.inkforge.core.generated.api.BillingApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** 冻结的三个浏览器账单接口和两个 Agent 内部计费接口。 */
@RestController
public final class BillingController implements BillingApi {

    private final Optional<BillingService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;
    private final Optional<InternalServiceAuthenticator> configuredAuthenticator;

    public BillingController(
            Optional<BillingService> configuredService,
            Optional<CurrentUserAccess> configuredUsers,
            Optional<InternalServiceAuthenticator> configuredAuthenticator) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
        this.configuredAuthenticator = configuredAuthenticator;
    }

    @Override
    public ResponseEntity<AuthorizeModelCallResponse>
            authorizeModelCallInternalV1BillingAuthorizePost(
                    AuthorizeModelCallRequest request) {
        authenticate(
                ServiceScope.BILLING_AUTHORIZE,
                request.getTaskId(),
                request.getRunId(),
                request.getNovelId());
        return ResponseEntity.ok(service().authorize(request));
    }

    @Override
    public ResponseEntity<BillingSummaryResponse> getSummaryApiV1BillingSummaryGet(
            String inkforgeToken) {
        return ResponseEntity.ok(service().summary(user(inkforgeToken).id()));
    }

    @Override
    public ResponseEntity<TaskModelUsageResponse>
            getTaskUsageApiV1BillingUsageTasksTaskIdGet(
                    String taskId, String inkforgeToken) {
        return ResponseEntity.ok(service().taskUsage(user(inkforgeToken).id(), taskId));
    }

    @Override
    public ResponseEntity<BillingUsageResponse> getUsageApiV1BillingUsageGet(
            String inkforgeToken) {
        return ResponseEntity.ok(service().usage(user(inkforgeToken).id()));
    }

    @Override
    public ResponseEntity<UsageChargeResponse> reportModelUsageInternalV1BillingUsagePost(
            ReportModelUsageRequest request) {
        authenticate(
                ServiceScope.BILLING_USAGE_WRITE,
                request.getTaskId(),
                request.getRunId(),
                request.getNovelId());
        return ResponseEntity.ok(service().charge(request));
    }

    private void authenticate(
            ServiceScope scope, String taskId, String runId, String novelId) {
        InternalServiceAuthenticator authenticator = configuredAuthenticator.orElseThrow(() ->
                new ApiException(
                        503,
                        "RAG_CALLBACK_AUTH_UNAVAILABLE",
                        "索引回调认证暂时不可用"));
        authenticator.authenticate(
                currentRequest(),
                RawRequestBody.current(),
                scope,
                taskId,
                runId,
                novelId,
                "RAG_CALLBACK_AUTH_UNAVAILABLE",
                "索引回调认证暂时不可用");
    }

    private BillingService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503, "BILLING_UNAVAILABLE", "计费服务暂时不可用"));
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
