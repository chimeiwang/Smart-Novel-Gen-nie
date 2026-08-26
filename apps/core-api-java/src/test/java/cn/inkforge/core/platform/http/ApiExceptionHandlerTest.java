package cn.inkforge.core.platform.http;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest(
        classes = CoreApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(ApiExceptionHandlerTest.TestEndpoints.class)
class ApiExceptionHandlerTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    @Test
    void 业务异常必须保留状态码错误码详情和请求标识() throws Exception {
        HttpResponse<String> response = post("/test/errors/business", "{}", "error-request-1");

        assertThat(response.statusCode()).isEqualTo(409);
        assertThat(response.body()).isEqualTo(
                "{\"code\":\"NOVEL_VERSION_CONFLICT\",\"message\":\"小说已在其他位置更新，请刷新后重试\","
                        + "\"details\":{\"currentUpdatedAt\":\"2026-08-24T12:00:00Z\"},"
                        + "\"requestId\":\"error-request-1\"}");
    }

    @Test
    void 缺失字段与未知字段必须转换为Python兼容校验详情() throws Exception {
        HttpResponse<String> missing = post("/test/errors/validation", "{}", "validation-1");
        HttpResponse<String> extra = post(
                "/test/errors/validation",
                "{\"clientRequestId\":\"request-1\",\"unknown\":true}",
                "validation-2");

        assertThat(missing.statusCode()).isEqualTo(422);
        assertThat(missing.body()).isEqualTo(
                "{\"code\":\"VALIDATION_ERROR\",\"message\":\"请求参数校验失败\","
                        + "\"details\":[{\"path\":[\"body\",\"clientRequestId\"],"
                        + "\"message\":\"缺少必需字段\",\"type\":\"missing\"}],"
                        + "\"requestId\":\"validation-1\"}");
        assertThat(extra.statusCode()).isEqualTo(422);
        assertThat(extra.body()).isEqualTo(
                "{\"code\":\"VALIDATION_ERROR\",\"message\":\"请求参数校验失败\","
                        + "\"details\":[{\"path\":[\"body\",\"unknown\"],"
                        + "\"message\":\"包含不允许的字段\",\"type\":\"extra_forbidden\"}],"
                        + "\"requestId\":\"validation-2\"}");
    }

    @Test
    void 缺失查询参数和未处理异常必须安全收口() throws Exception {
        HttpResponse<String> missing = post("/test/errors/query", "{}", "query-1");
        HttpResponse<String> unexpected = post("/test/errors/unexpected", "{}", "unexpected-1");

        assertThat(missing.statusCode()).isEqualTo(422);
        assertThat(missing.body()).contains(
                "\"path\":[\"query\",\"requiredValue\"]",
                "\"message\":\"缺少必需字段\"",
                "\"type\":\"missing\"");
        assertThat(unexpected.statusCode()).isEqualTo(500);
        assertThat(unexpected.body()).isEqualTo(
                "{\"code\":\"INTERNAL_SERVER_ERROR\",\"message\":\"服务器内部错误\","
                        + "\"details\":null,\"requestId\":\"unexpected-1\"}");
        assertThat(unexpected.body()).doesNotContain("数据库密码");
    }

    private HttpResponse<String> post(String path, String body, String requestId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + path))
                .header("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .header("X-Request-ID", requestId)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestEndpoints {

        @Bean
        ErrorTestController errorTestController() {
            return new ErrorTestController();
        }
    }

    @RestController
    static class ErrorTestController {

        @PostMapping("/test/errors/business")
        void business() {
            throw new ApiException(
                    409,
                    "NOVEL_VERSION_CONFLICT",
                    "小说已在其他位置更新，请刷新后重试",
                    java.util.Map.of("currentUpdatedAt", "2026-08-24T12:00:00Z"));
        }

        @PostMapping("/test/errors/validation")
        void validation(@Valid @RequestBody ValidationBody body) {}

        @PostMapping("/test/errors/query")
        void query(@RequestParam String requiredValue) {}

        @PostMapping("/test/errors/unexpected")
        void unexpected() {
            throw new IllegalStateException("数据库密码=绝密");
        }
    }

    record ValidationBody(@NotBlank String clientRequestId) {}
}
