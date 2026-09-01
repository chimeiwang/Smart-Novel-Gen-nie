package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobCancelRequest;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.contracts.agent.ExecutionCancelAccepted;
import cn.inkforge.contracts.agent.ExecutionCancelRequest;
import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.contracts.agent.ResolvedModelRef;
import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryResponse;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitResponse;
import cn.inkforge.core.workflows.application.WorkflowExecutionAdmissionSaturatedException;
import cn.inkforge.core.workflows.application.WorkflowExecutionRejectedException;
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
    private static final String EXECUTIONS_PATH = "/internal/v1/executions";
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

    public ExecutionStepAccepted submitExecution(ExecutionStepRequest request) {
        requireExecutionStepRequest(request);
        byte[] body = objectMapper.writeValueAsBytes(request);
        SignedServiceRequest signed = signer.sign(new ServiceRequest(
                body,
                "POST",
                EXECUTIONS_PATH,
                new byte[0],
                request.getIdempotencyKey(),
                List.of(ServiceScope.EXECUTION_SUBMIT),
                request.getStepId(),
                request.getRunId(),
                request.getNovelId(),
                null,
                0,
                null));
        AgentHttpResponse response = send(
                signedRequest(EXECUTIONS_PATH, "POST", body, signed),
                "AGENT_EXECUTION_SUBMIT_FAILED",
                "智能体执行步骤提交失败");
        Duration admissionRetryAfter = executionAdmissionRetryAfter(response);
        if (admissionRetryAfter != null) {
            throw new WorkflowExecutionAdmissionSaturatedException(admissionRetryAfter);
        }
        if (isDefinitiveExecutionRejection(response.statusCode())) {
            throw new WorkflowExecutionRejectedException(
                    "EXECUTION_SUBMIT_REJECTED_" + response.statusCode());
        }
        if (response.statusCode() != 202) {
            throw executionSubmitFailed();
        }
        ExecutionStepAccepted accepted;
        try {
            accepted = objectMapper.readValue(response.body(), ExecutionStepAccepted.class);
        } catch (RuntimeException exception) {
            throw executionSubmitFailed();
        }
        if (!matchesExecutionStep(request, accepted)) {
            throw executionSubmitFailed();
        }
        return accepted;
    }

    private static boolean isDefinitiveExecutionRejection(int statusCode) {
        return switch (statusCode) {
            case 400, 401, 403, 404, 409, 422 -> true;
            default -> false;
        };
    }

    public ExecutionCancelAccepted cancelExecution(
            String jobId, ExecutionCancelRequest request) {
        String normalizedJobId = pathSegment(jobId);
        requireExecutionCancelRequest(normalizedJobId, request);
        String path = EXECUTIONS_PATH + "/" + normalizedJobId + "/cancel";
        byte[] body = objectMapper.writeValueAsBytes(request);
        SignedServiceRequest signed = signer.sign(new ServiceRequest(
                body,
                "PUT",
                path,
                new byte[0],
                request.getCancelRequestId(),
                List.of(ServiceScope.EXECUTION_CANCEL),
                request.getStepId(),
                request.getRunId(),
                request.getNovelId(),
                null,
                0,
                null));
        AgentHttpResponse response = send(
                signedRequest(path, "PUT", body, signed),
                "AGENT_EXECUTION_CANCEL_FAILED",
                "智能体执行取消投递失败");
        if (response.statusCode() != 202) {
            throw executionCancelFailed();
        }
        ExecutionCancelAccepted accepted;
        try {
            accepted = objectMapper.readValue(response.body(), ExecutionCancelAccepted.class);
        } catch (RuntimeException exception) {
            throw executionCancelFailed();
        }
        if (!matchesExecutionCancel(request, accepted)) {
            throw executionCancelFailed();
        }
        return accepted;
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
                return new AgentHttpResponse(
                        response.statusCode(),
                        bytes,
                        response.headers().firstValue("Retry-After").orElse(null));
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

    private static void requireExecutionStepRequest(ExecutionStepRequest request) {
        if (request == null
                || !"2.0".equals(request.getProtocolVersion())
                || !validResourceId(request.getJobId())
                || !validResourceId(request.getRunId())
                || !validResourceId(request.getStepId())
                || (request.getNovelId() != null && !validResourceId(request.getNovelId()))
                || request.getFencingToken() == null
                || request.getFencingToken() <= 0
                || request.getRequestHash() == null
                || !request.getRequestHash().matches("[0-9a-f]{64}")
                || !validResourceId(request.getIdempotencyKey())) {
            throw new IllegalArgumentException("智能体执行步骤资源身份无效");
        }
    }

    private static void requireExecutionCancelRequest(
            String jobId, ExecutionCancelRequest request) {
        if (request == null
                || !validResourceId(jobId)
                || !jobId.equals(request.getJobId())
                || !"2.0".equals(request.getProtocolVersion())
                || !validResourceId(request.getRunId())
                || !validResourceId(request.getStepId())
                || (request.getNovelId() != null && !validResourceId(request.getNovelId()))
                || request.getFencingToken() == null
                || request.getFencingToken() <= 0
                || request.getRequestHash() == null
                || !request.getRequestHash().matches("[0-9a-f]{64}")
                || !validResourceId(request.getCancelRequestId())) {
            throw new IllegalArgumentException("智能体执行取消资源身份无效");
        }
    }

    private static boolean matchesExecutionStep(
            ExecutionStepRequest request, ExecutionStepAccepted accepted) {
        // 202 只表示 Agent 已受理；资源回声必须逐项命中，避免把其他并发步骤的响应绑定到当前耐久 Step。
        return accepted != null
                && java.util.Objects.equals(
                        request.getProtocolVersion(), accepted.getProtocolVersion())
                && java.util.Objects.equals(request.getJobId(), accepted.getJobId())
                && java.util.Objects.equals(request.getRunId(), accepted.getRunId())
                && java.util.Objects.equals(request.getNovelId(), accepted.getNovelId())
                && java.util.Objects.equals(request.getStepId(), accepted.getStepId())
                && java.util.Objects.equals(
                        request.getFencingToken(), accepted.getFencingToken())
                && java.util.Objects.equals(request.getRequestHash(), accepted.getRequestHash())
                && accepted.getStatus() != null
                && accepted.getAcceptedAt() != null
                && validResolvedModel(accepted.getResolvedModel());
    }

    private static boolean matchesExecutionCancel(
            ExecutionCancelRequest request, ExecutionCancelAccepted accepted) {
        // 取消响应契约不回显 requestHash；它由原始正文签名保护，响应侧再以 cancelRequestId 和资源身份闭合。
        return accepted != null
                && java.util.Objects.equals(
                        request.getProtocolVersion(), accepted.getProtocolVersion())
                && java.util.Objects.equals(
                        request.getCancelRequestId(), accepted.getCancelRequestId())
                && java.util.Objects.equals(request.getJobId(), accepted.getJobId())
                && java.util.Objects.equals(request.getRunId(), accepted.getRunId())
                && java.util.Objects.equals(request.getNovelId(), accepted.getNovelId())
                && java.util.Objects.equals(request.getStepId(), accepted.getStepId())
                && java.util.Objects.equals(
                        request.getFencingToken(), accepted.getFencingToken())
                && accepted.getStatus() != null
                && accepted.getAcceptedAt() != null;
    }

    private static boolean validResolvedModel(ResolvedModelRef model) {
        return model != null
                && model.getDeploymentFingerprint() != null
                && model.getDeploymentFingerprint().matches("[0-9a-f]{64}")
                && model.getDeploymentProfileKey() != null
                && !model.getDeploymentProfileKey().isBlank()
                && model.getModel() != null
                && !model.getModel().isBlank()
                && model.getProvider() != null
                && !model.getProvider().isBlank()
                && model.getTransportProfile() != null
                && !model.getTransportProfile().isBlank()
                && model.getEndpointProfile() != null
                && !model.getEndpointProfile().isBlank()
                && model.getStructuredOutputRoute() != null
                && model.getCapabilityVersion() != null
                && !model.getCapabilityVersion().isBlank()
                && model.getReasoningMode() != null
                && model.getSupportsRequestIdempotency() != null;
    }

    private static boolean validResourceId(String value) {
        return value != null
                && value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    }

    private static AgentGatewayException executionSubmitFailed() {
        return new AgentGatewayException(
                "AGENT_EXECUTION_SUBMIT_FAILED", "智能体执行步骤提交失败");
    }

    private Duration executionAdmissionRetryAfter(AgentHttpResponse response) {
        if (response.statusCode() != 503 || response.retryAfter() == null) return null;
        try {
            JsonNode value = objectMapper.readTree(response.body());
            if (!value.isObject()
                    || value.size() != 4
                    || !"2.0".equals(value.path("protocolVersion").asText())
                    || !"EXECUTION_ADMISSION_SATURATED"
                            .equals(value.path("errorCode").asText())
                    || !value.path("retryable").isBoolean()
                    || !value.path("retryable").asBoolean()
                    || !value.path("retryAfterSeconds").canConvertToInt()) {
                return null;
            }
            int seconds = value.path("retryAfterSeconds").asInt();
            if (seconds < 1
                    || seconds > 60
                    || !Integer.toString(seconds).equals(response.retryAfter())) {
                return null;
            }
            return Duration.ofSeconds(seconds);
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private static AgentGatewayException executionCancelFailed() {
        return new AgentGatewayException(
                "AGENT_EXECUTION_CANCEL_FAILED", "智能体执行取消投递失败");
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

    private record AgentHttpResponse(int statusCode, byte[] body, String retryAfter) {

        private AgentHttpResponse {
            body = body.clone();
        }
    }
}
