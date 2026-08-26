package cn.inkforge.core;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            // `false` 是 ConditionalOnProperty 的显式关闭值，避免 CI 的占位连接串污染最小健康上下文。
            "DATABASE_URL=false",
            "REDIS_URL=false"
        })
class HealthApiTest {

    private static final String REQUEST_ID = "java-migration-test-request";

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    @Test
    void 存活接口应保持Python响应与请求标识() throws Exception {
        HttpResponse<String> response = get("/api/v1/health/live", REQUEST_ID);

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue("content-type")).hasValue("application/json");
        assertThat(response.headers().firstValue("x-request-id")).hasValue(REQUEST_ID);
        assertThat(response.body()).isEqualTo("{\"status\":\"ok\",\"service\":\"core-api\"}");
    }

    @Test
    void 未知路径应返回统一中文错误() throws Exception {
        HttpResponse<String> response = get("/api/v1/not-present", REQUEST_ID);

        assertThat(response.statusCode()).isEqualTo(404);
        assertThat(response.headers().firstValue("x-request-id")).hasValue(REQUEST_ID);
        assertThat(response.body()).isEqualTo(
                "{\"code\":\"NOT_FOUND\",\"message\":\"请求的资源不存在\","
                        + "\"details\":null,\"requestId\":\"java-migration-test-request\"}");
    }

    @Test
    void 过长请求标识应替换为UUID() throws Exception {
        String invalidRequestId = "x".repeat(129);
        HttpResponse<String> response = get("/api/v1/health/live", invalidRequestId);

        String generated = response.headers().firstValue("x-request-id").orElseThrow();
        assertThat(generated).isNotEqualTo(invalidRequestId);
        assertThat(UUID.fromString(generated).version()).isEqualTo(4);
    }

    @Test
    void 未配置外部依赖的测试应用应保持就绪契约() throws Exception {
        HttpResponse<String> response = get("/api/v1/health/ready", REQUEST_ID);

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body())
                .isEqualTo("{\"status\":\"ready\",\"service\":\"core-api\",\"checks\":{}}");
    }

    private HttpResponse<String> get(String path, String requestId)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + path))
                .header("X-Request-ID", requestId)
                .GET()
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
