package cn.inkforge.core.agentgateway;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.serviceauth.ServiceScope;
import cn.inkforge.serviceauth.ServiceVerificationRequest;
import cn.inkforge.serviceauth.VerifiedServiceRequest;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

/** 从 Servlet 原始请求提取 Ed25519 绑定字段；直接对端网段由更早的拦截器校验。 */
public final class AgentCallbackAuthenticator implements InternalServiceAuthenticator {

    private final AgentCallbackVerifier verifier;

    public AgentCallbackAuthenticator(Optional<AgentCallbackVerifier> verifier) {
        this.verifier = verifier.orElse(null);
    }

    @Override
    public VerifiedServiceRequest authenticate(
            HttpServletRequest request,
            byte[] body,
            ServiceScope requiredScope,
            String taskId,
            String runId,
            String novelId,
            String unavailableCode,
            String unavailableMessage) {
        List<String> authorizations = Collections.list(request.getHeaders("Authorization"));
        if (authorizations.size() != 1
                || !authorizations.getFirst().startsWith("Bearer ")
                || authorizations.getFirst().substring("Bearer ".length()).isBlank()) {
            throw new ApiException(
                    401,
                    "SERVICE_AUTHENTICATION_FAILED",
                    "服务身份认证失败");
        }
        if (verifier == null) {
            throw new ApiException(503, unavailableCode, unavailableMessage);
        }
        String query = request.getQueryString();
        return verifier.verify(new ServiceVerificationRequest(
                authorizations.getFirst().substring("Bearer ".length()),
                body,
                request.getMethod(),
                request.getRequestURI(),
                query == null ? new byte[0] : query.getBytes(StandardCharsets.US_ASCII),
                header(request, "Idempotency-Key"),
                header(request, "X-InkForge-Timestamp"),
                header(request, "X-InkForge-Body-SHA256"),
                requiredScope,
                taskId,
                runId,
                novelId,
                null));
    }

    private static String header(HttpServletRequest request, String name) {
        String value = request.getHeader(name);
        return value == null ? "" : value;
    }
}
