package cn.inkforge.core.agentgateway;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 对 Agent 执行一次 POST 协议门禁，并持续检查内部就绪接口。 */
public final class AgentServiceReadiness {

    private static final String READY_PATH = "/internal/v1/health/ready";
    private static final String RUNS_PATH = "/internal/v1/runs";
    private static final int MAX_RESPONSE_BYTES = 64 * 1024;

    private final HttpClient httpClient;
    private final URI baseUri;
    private final ObjectMapper objectMapper;
    private final Duration timeout;
    private final Object postProbeMonitor = new Object();
    private volatile boolean postTransportVerified;

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
        try {
            if (!checkPostTransport()) {
                return false;
            }
            HttpRequest request = HttpRequest.newBuilder(baseUri.resolve(READY_PATH))
                    .timeout(timeout)
                    .GET()
                    .build();
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

    private boolean checkPostTransport() throws Exception {
        if (postTransportVerified) {
            return true;
        }
        synchronized (postProbeMonitor) {
            if (postTransportVerified) {
                return true;
            }
            // 空对象会在 FastAPI 参数校验或服务鉴权处以 422/401 被安全拒绝，不会进入队列写入；但它仍是
            // 带正文的真实 POST，能在部署冒烟阶段识别 Uvicorn 对 JDK h2c Upgrade 返回的协议级 400。
            HttpRequest request = HttpRequest.newBuilder(baseUri.resolve(RUNS_PATH))
                    .timeout(timeout)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString("{}", StandardCharsets.UTF_8))
                    .build();
            HttpResponse<Void> response =
                    httpClient.send(request, HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() != 401 && response.statusCode() != 422) {
                return false;
            }
            // HTTP 客户端版本在 Core 生命周期内固定；只探测一次，避免每 15 秒健康检查制造拒绝访问日志。
            postTransportVerified = true;
            return true;
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
