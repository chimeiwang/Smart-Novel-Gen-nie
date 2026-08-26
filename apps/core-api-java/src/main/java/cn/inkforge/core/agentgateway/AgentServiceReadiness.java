package cn.inkforge.core.agentgateway;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 对 Agent 内部就绪接口执行短超时、有限响应探测。 */
public final class AgentServiceReadiness {

    private static final String PATH = "/internal/v1/health/ready";
    private static final int MAX_RESPONSE_BYTES = 64 * 1024;

    private final HttpClient httpClient;
    private final URI baseUri;
    private final ObjectMapper objectMapper;
    private final Duration timeout;

    public AgentServiceReadiness(
            HttpClient httpClient,
            URI baseUri,
            ObjectMapper objectMapper,
            Duration timeout) {
        this.httpClient = java.util.Objects.requireNonNull(httpClient);
        this.baseUri = normalizeBaseUri(baseUri);
        this.objectMapper = java.util.Objects.requireNonNull(objectMapper);
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("Agent 就绪探测超时必须为正数");
        }
        this.timeout = timeout;
    }

    public boolean check() {
        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve(PATH))
                .timeout(timeout)
                .GET()
                .build();
        try {
            HttpResponse<InputStream> response =
                    httpClient.send(request, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                byte[] bytes = body.readNBytes(MAX_RESPONSE_BYTES + 1);
                if (response.statusCode() != 200 || bytes.length > MAX_RESPONSE_BYTES) {
                    return false;
                }
                JsonNode value = objectMapper.readTree(bytes);
                return value.isObject() && "ready".equals(value.path("status").asString());
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return false;
        } catch (Exception exception) {
            return false;
        }
    }

    @Override
    public String toString() {
        return "AgentServiceReadiness[endpoint=********]";
    }

    static URI normalizeBaseUri(URI value) {
        if (value == null
                || !("http".equals(value.getScheme()) || "https".equals(value.getScheme()))
                || value.getHost() == null
                || value.getRawUserInfo() != null
                || value.getRawQuery() != null
                || value.getRawFragment() != null) {
            throw new IllegalArgumentException("Agent 基础地址无效");
        }
        String rendered = value.toString();
        return URI.create(rendered.endsWith("/") ? rendered : rendered + "/");
    }
}
