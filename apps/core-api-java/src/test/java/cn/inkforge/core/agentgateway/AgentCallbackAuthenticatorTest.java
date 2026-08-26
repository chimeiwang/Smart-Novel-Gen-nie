package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.serviceauth.ServiceScope;
import cn.inkforge.serviceauth.ServiceVerificationRequest;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

class AgentCallbackAuthenticatorTest {

    @Test
    void 必须把原始正文方法路径查询头和资源完整交给验签器() {
        AtomicReference<ServiceVerificationRequest> captured = new AtomicReference<>();
        AgentCallbackAuthenticator authenticator = new AgentCallbackAuthenticator(
                Optional.of(request -> {
                    captured.set(request);
                    return null;
                }));
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/internal/v1/tools/read_novel");
        request.setQueryString("mode=full%20text");
        request.addHeader("Authorization", "Bearer signed-token");
        request.addHeader("Idempotency-Key", "job-1");
        request.addHeader("X-InkForge-Timestamp", "1770000000");
        request.addHeader("X-InkForge-Body-SHA256", "a".repeat(64));
        byte[] body = "{\"完整\":true}".getBytes(StandardCharsets.UTF_8);

        authenticator.authenticate(
                request,
                body,
                ServiceScope.TOOL_READ,
                "task-1",
                "run-1",
                "novel-1",
                "TOOL_AUTH_UNAVAILABLE",
                "工具认证暂时不可用");

        ServiceVerificationRequest value = captured.get();
        assertThat(value.token()).isEqualTo("signed-token");
        assertThat(value.body()).isEqualTo(body);
        assertThat(value.httpMethod()).isEqualTo("POST");
        assertThat(value.httpPath()).isEqualTo("/internal/v1/tools/read_novel");
        assertThat(value.queryString()).isEqualTo("mode=full%20text".getBytes(StandardCharsets.US_ASCII));
        assertThat(value.idempotencyKey()).isEqualTo("job-1");
        assertThat(value.requiredScope()).isEqualTo(ServiceScope.TOOL_READ);
        assertThat(value.taskId()).isEqualTo("task-1");
    }

    @Test
    void 缺失Bearer和验签器不可用必须保留稳定业务错误() {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/internal/v1/tools/read_novel");
        AgentCallbackAuthenticator available = new AgentCallbackAuthenticator(
                Optional.of(value -> null));

        assertThatThrownBy(() -> available.authenticate(
                        request,
                        new byte[0],
                        ServiceScope.TOOL_READ,
                        "task-1",
                        "run-1",
                        "novel-1",
                        "TOOL_AUTH_UNAVAILABLE",
                        "工具认证暂时不可用"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(401);
                    assertThat(error.code()).isEqualTo("SERVICE_AUTHENTICATION_FAILED");
                });

        request.addHeader("Authorization", "Bearer signed-token");
        AgentCallbackAuthenticator unavailable = new AgentCallbackAuthenticator(Optional.empty());
        assertThatThrownBy(() -> unavailable.authenticate(
                        request,
                        new byte[0],
                        ServiceScope.TOOL_READ,
                        "task-1",
                        "run-1",
                        "novel-1",
                        "TOOL_AUTH_UNAVAILABLE",
                        "工具认证暂时不可用"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code()).isEqualTo("TOOL_AUTH_UNAVAILABLE");
                    assertThat(error.getMessage()).isEqualTo("工具认证暂时不可用");
                });
    }
}
