package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobCancelRequest;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitResponse;
import cn.inkforge.serviceauth.ServiceRequest;
import cn.inkforge.serviceauth.ServiceScope;
import cn.inkforge.serviceauth.ServiceTokenSigner;
import cn.inkforge.serviceauth.SignedServiceRequest;
import java.io.InputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.DeserializationFeature;

/** Core 到 Python Agent 的受签名 HTTP 边界；不自动重试未知结果。 */
public final class AgentServiceClient {

    private static final String RUNS_PATH = "/internal/v1/runs";
    private static final String DEBUG_PATH = "/internal/v1/debug/workflow-runs";
    private static final String SEEDANCE_PATH = "/internal/v1/video/seedance/tasks";
    private static final Duration SEEDANCE_TIMEOUT = Duration.ofSeconds(40);
    private static final int MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

    private final HttpClient httpClient;
    private final URI baseUri;
    private final ServiceTokenSigner signer;
    private final ObjectMapper objectMapper;
    private final Duration requestTimeout;

    public AgentServiceClient(
            HttpClient httpClient,
            URI baseUri,
            ServiceTokenSigner signer,
            ObjectMapper objectMapper,
            Duration requestTimeout) {
        this.httpClient = java.util.Objects.requireNonNull(httpClient);
        this.baseUri = normalizeBaseUri(baseUri);
        this.signer = java.util.Objects.requireNonNull(signer);
        this.objectMapper = java.util.Objects.requireNonNull(objectMapper)
                .rebuild()
                .enable(
                        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
                        DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                .build();
        if (requestTimeout == null || requestTimeout.isZero() || requestTimeout.isNegative()) {
            throw new IllegalArgumentException("Agent 请求超时必须为正数");
        }
        this.requestTimeout = requestTimeout;
    }

    public AgentJobAccepted submit(AgentJobRequest request) {
        byte[] body = objectMapper.writeValueAsBytes(request);
        SignedServiceRequest signed = signer.sign(new ServiceRequest(
                body,
                "POST",
                RUNS_PATH,
                new byte[0],
                request.getJobId(),
                List.of(ServiceScope.AGENT_RUN),
                request.getTaskId(),
                request.getRunId(),
                request.getNovelId(),
                null,
                0,
                null));
        HttpRequest httpRequest = signedRequest(RUNS_PATH, "POST", body, signed);
        AgentHttpResponse response = send(httpRequest, "AGENT_RUN_SUBMIT_FAILED", "智能体运行提交失败");
        if (response.statusCode() != 202) {
            throw new AgentGatewayException("AGENT_RUN_SUBMIT_FAILED", "智能体运行提交失败");
        }
        try {
            return objectMapper.readValue(response.body(), AgentJobAccepted.class);
        } catch (RuntimeException exception) {
            throw new AgentGatewayException("AGENT_RUN_SUBMIT_FAILED", "智能体运行提交失败");
        }
    }

    public void cancel(String jobId, AgentJobCancelRequest request) {
        String path = RUNS_PATH + "/" + pathSegment(jobId);
        byte[] body = objectMapper.writeValueAsBytes(request);
        SignedServiceRequest signed = signer.sign(new ServiceRequest(
                body,
                "DELETE",
                path,
                new byte[0],
                jobId,
                List.of(ServiceScope.AGENT_CANCEL),
                request.getTaskId(),
                request.getRunId(),
                request.getNovelId(),
                null,
                0,
                null));
        AgentHttpResponse response = send(
                signedRequest(path, "DELETE", body, signed),
                "AGENT_RUN_CANCEL_FAILED",
                "智能体运行取消投递失败");
        if (response.statusCode() != 204) {
            throw new AgentGatewayException("AGENT_RUN_CANCEL_FAILED", "智能体运行取消投递失败");
        }
    }

    public Map<String, Object> getWorkflowRuns(String userId, String runId) {
        String normalizedUserId = nonBlank(userId, "Agent 调试 userId");
        String path = runId == null ? DEBUG_PATH : DEBUG_PATH + "/" + pathSegment(runId);
        String query = "userId=" + URLEncoder.encode(normalizedUserId, StandardCharsets.UTF_8);
        byte[] queryBytes = query.getBytes(StandardCharsets.US_ASCII);
        String identity = normalizedUserId + ":" + (runId == null ? "list" : runId);
        String idempotencyKey = "debug-" + sha256(identity).substring(0, 32);
        SignedServiceRequest signed = signer.sign(new ServiceRequest(
                new byte[0],
                "GET",
                path,
                queryBytes,
                idempotencyKey,
                List.of(ServiceScope.AGENT_DEBUG_READ),
                "debug",
                "debug",
                "debug",
                null,
                0,
                null));
        HttpRequest.Builder builder = HttpRequest.newBuilder(baseUri.resolve(path + "?" + query))
                .timeout(requestTimeout)
                .GET();
        signed.headers().forEach(builder::header);
        AgentHttpResponse response = send(
                builder.build(), "AGENT_DEBUG_READ_FAILED", "读取智能体工作流日志失败");
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new AgentGatewayException("AGENT_DEBUG_READ_FAILED", "读取智能体工作流日志失败");
        }
        try {
            JsonNode value = objectMapper.readTree(response.body());
            if (!value.isObject()) {
                throw new IllegalArgumentException();
            }
            return objectMapper.convertValue(value, new TypeReference<Map<String, Object>>() {});
        } catch (RuntimeException exception) {
            throw new AgentGatewayException("AGENT_DEBUG_READ_FAILED", "读取智能体工作流日志失败");
        }
    }

    public SeedanceRenderSubmitResponse submitSeedanceRender(
            SeedanceRenderSubmitRequest request) {
        byte[] body = objectMapper.writeValueAsBytes(request);
        SignedServiceRequest signed = signer.sign(new ServiceRequest(
                body,
                "POST",
                SEEDANCE_PATH,
                new byte[0],
                "render-submit-" + request.getTaskId(),
                List.of(ServiceScope.VIDEO_RENDER),
                request.getTaskId(),
                request.getTaskId(),
                request.getNovelId(),
                null,
                0,
                null));
        AgentHttpResponse response;
        try {
            response = send(
                    signedRequest(SEEDANCE_PATH, "POST", body, signed, SEEDANCE_TIMEOUT),
                    "SEEDANCE_SUBMISSION_UNKNOWN",
                    "Seedance 创建结果未知");
        } catch (AgentGatewayException exception) {
            throw new SeedanceSubmissionUnknownException();
        }
        if (response.statusCode() >= 500) {
            throw new SeedanceSubmissionUnknownException();
        }
        if (response.statusCode() >= 400) {
            throw new SeedanceGatewayRejectedException(
                    response.statusCode(), internalErrorDetail(response.body()));
        }
        try {
            return objectMapper.readValue(response.body(), SeedanceRenderSubmitResponse.class);
        } catch (RuntimeException exception) {
            throw new SeedanceSubmissionUnknownException();
        }
    }

    public SeedanceRenderQueryResponse querySeedanceRender(
            SeedanceRenderQueryRequest request) {
        String path = SEEDANCE_PATH + "/" + encodedPathSegment(request.getProviderTaskId()) + "/query";
        byte[] body = objectMapper.writeValueAsBytes(request);
        SignedServiceRequest signed = signer.sign(new ServiceRequest(
                body,
                "POST",
                path,
                new byte[0],
                "render-query-" + request.getTaskId() + "-" + request.getPollCount(),
                List.of(ServiceScope.VIDEO_RENDER),
                request.getTaskId(),
                request.getTaskId(),
                request.getNovelId(),
                null,
                0,
                null));
        try {
            AgentHttpResponse response = send(
                    signedRequest(path, "POST", body, signed, SEEDANCE_TIMEOUT),
                    "SEEDANCE_QUERY_FAILED",
                    "Seedance 查询暂时失败");
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new SeedanceGatewayQueryException();
            }
            return objectMapper.readValue(response.body(), SeedanceRenderQueryResponse.class);
        } catch (SeedanceGatewayQueryException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new SeedanceGatewayQueryException();
        }
    }

    private HttpRequest signedRequest(
            String path, String method, byte[] body, SignedServiceRequest signed) {
        return signedRequest(path, method, body, signed, requestTimeout);
    }

    private HttpRequest signedRequest(
            String path,
            String method,
            byte[] body,
            SignedServiceRequest signed,
            Duration timeout) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(baseUri.resolve(path))
                .timeout(timeout)
                .header("Content-Type", "application/json");
        signed.headers().forEach(builder::header);
        return builder.method(method, HttpRequest.BodyPublishers.ofByteArray(body)).build();
    }

    private AgentHttpResponse send(HttpRequest request, String code, String message) {
        try {
            HttpResponse<InputStream> response =
                    httpClient.send(request, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                byte[] bytes = body.readNBytes(MAX_RESPONSE_BYTES + 1);
                if (bytes.length > MAX_RESPONSE_BYTES) {
                    throw new AgentGatewayException(code, message);
                }
                return new AgentHttpResponse(response.statusCode(), bytes);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AgentGatewayException(code, message);
        } catch (Exception exception) {
            throw new AgentGatewayException(code, message);
        }
    }

    private String internalErrorDetail(byte[] body) {
        try {
            JsonNode value = objectMapper.readTree(body);
            JsonNode detail = value.isObject() ? value.get("detail") : null;
            if (detail != null && detail.isString() && !detail.asString().isEmpty()) {
                String text = detail.asString();
                return text.substring(0, Math.min(2_000, text.length()));
            }
        } catch (RuntimeException ignored) {
            // 远端错误体不是可信输入，解析失败时使用稳定内部诊断。
        }
        return "Seedance 内部网关拒绝请求";
    }

    private static URI normalizeBaseUri(URI value) {
        return AgentServiceReadiness.normalizeBaseUri(value);
    }

    private static String pathSegment(String value) {
        if (value == null || value.isBlank() || !value.matches("[A-Za-z0-9._:-]{1,256}")) {
            throw new IllegalArgumentException("Agent jobId 不能安全放入路径");
        }
        return value;
    }

    private static String encodedPathSegment(String value) {
        return URLEncoder.encode(nonBlank(value, "Agent 路径标识"), StandardCharsets.UTF_8)
                .replace("+", "%20");
    }

    private static String nonBlank(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + "不能为空");
        }
        return value;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    private record AgentHttpResponse(int statusCode, byte[] body) {

        private AgentHttpResponse {
            body = body.clone();
        }
    }
}
