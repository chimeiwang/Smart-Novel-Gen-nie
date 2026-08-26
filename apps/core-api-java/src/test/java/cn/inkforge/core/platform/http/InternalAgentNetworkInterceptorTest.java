package cn.inkforge.core.platform.http;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.config.CoreSettings;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class InternalAgentNetworkInterceptorTest {

    @Test
    void 未配置可信网段必须返回稳定503() {
        InternalAgentNetworkInterceptor interceptor = new InternalAgentNetworkInterceptor(
                CoreSettings.from(Map.of()));

        assertThatThrownBy(() -> interceptor.preHandle(
                        request("127.0.0.1"), new MockHttpServletResponse(), new Object()))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(503);
                    assertThat(exception.code()).isEqualTo("AGENT_SERVICE_NETWORK_UNAVAILABLE");
                });
    }

    @Test
    void 直接对端不可信时不得接受任何转发头伪造() {
        InternalAgentNetworkInterceptor interceptor = new InternalAgentNetworkInterceptor(
                CoreSettings.from(Map.of("TRUSTED_AGENT_CIDRS", "10.0.0.0/8")));
        MockHttpServletRequest request = request("198.51.100.10");
        request.addHeader("X-Real-IP", "10.1.2.3");
        request.addHeader("X-Forwarded-For", "10.1.2.3");

        assertThatThrownBy(() -> interceptor.preHandle(
                        request, new MockHttpServletResponse(), new Object()))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(403);
                    assertThat(exception.code()).isEqualTo("AGENT_SERVICE_NETWORK_FORBIDDEN");
                });
    }

    @Test
    void 只有直接对端位于可信网段时才允许进入内部控制器() {
        InternalAgentNetworkInterceptor interceptor = new InternalAgentNetworkInterceptor(
                CoreSettings.from(Map.of(
                        "TRUSTED_AGENT_CIDRS", "127.0.0.0/8,2001:db8::/32")));

        assertThat(interceptor.preHandle(
                        request("127.0.0.1"), new MockHttpServletResponse(), new Object()))
                .isTrue();
        assertThat(interceptor.preHandle(
                        request("2001:db8::42"), new MockHttpServletResponse(), new Object()))
                .isTrue();
    }

    private MockHttpServletRequest request(String peer) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRequestURI("/internal/v1/tools/read_novel");
        request.setRemoteAddr(peer);
        return request;
    }
}
