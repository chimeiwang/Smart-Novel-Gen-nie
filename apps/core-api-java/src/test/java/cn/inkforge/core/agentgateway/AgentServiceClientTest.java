package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.contracts.agent.EvidenceBundle;
import cn.inkforge.contracts.agent.EvidenceManifest;
import cn.inkforge.contracts.agent.ExecutionCancelAccepted;
import cn.inkforge.contracts.agent.ExecutionCancelRequest;
import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.contracts.agent.ModelProfileRef;
import cn.inkforge.contracts.agent.OutputSchemaRef;
import cn.inkforge.contracts.agent.PromptProfileRef;
import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
import cn.inkforge.contracts.agent.StepBudget;
import cn.inkforge.core.workflows.application.WorkflowExecutionAdmissionSaturatedException;
import cn.inkforge.core.workflows.application.WorkflowExecutionRejectedException;
import cn.inkforge.serviceauth.ServiceScope;
import cn.inkforge.serviceauth.ServiceTokenSigner;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.KeyFactory;
import java.security.spec.EdECPrivateKeySpec;
import java.security.spec.NamedParameterSpec;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class AgentServiceClientTest {

    @TempDir
    private Path temporaryDirectory;

    @Test
    void 提交必须发送受签名原始正文并解析严格响应() throws Exception {
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<String> receivedBody = new AtomicReference<>();
        AtomicReference<String> upgrade = new AtomicReference<>();
        HttpServer server = server(exchange -> {
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            receivedBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            upgrade.set(exchange.getRequestHeaders().getFirst("Upgrade"));
            respond(exchange, 202, """
                    {"protocolVersion":"1.0","jobId":"job-1","runId":"run-1",\
                    "taskId":"task-1","status":"queued"}
                    """);
        });
        try {
            AgentJobAccepted accepted = productionClient(server, Duration.ofSeconds(2)).submit(job());

            assertThat(accepted.getStatus()).isEqualTo(AgentJobAccepted.StatusEnum.QUEUED);
            assertThat(authorization.get()).startsWith("Bearer eyJ");
            assertThat(receivedBody.get()).contains("\"jobId\":\"job-1\"");
            assertThat(upgrade.get()).isNull();
        } finally {
            server.stop(0);
        }
    }

    @Test
    void 超时与未知响应字段都必须稳定失败() throws Exception {
        HttpServer slow = server(exchange -> {
            try {
                Thread.sleep(150);
                respond(exchange, 202, "{}");
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            assertThatThrownBy(() -> client(slow, Duration.ofMillis(30)).submit(job()))
                    .isInstanceOf(AgentGatewayException.class)
                    .extracting(error -> ((AgentGatewayException) error).code())
                    .isEqualTo("AGENT_RUN_SUBMIT_FAILED");
        } finally {
            slow.stop(0);
        }

        HttpServer invalid = server(exchange -> respond(exchange, 202, """
                {"protocolVersion":"1.0","jobId":"job-1","runId":"run-1",\
                "taskId":"task-1","status":"queued","unknown":true}
                """));
        try {
            assertThatThrownBy(() -> client(invalid, Duration.ofSeconds(2)).submit(job()))
                    .isInstanceOf(AgentGatewayException.class)
                    .extracting(error -> ((AgentGatewayException) error).code())
                    .isEqualTo("AGENT_RUN_SUBMIT_FAILED");
        } finally {
            invalid.stop(0);
        }
    }

    @Test
    void V2步骤提交必须固定路径签名身份并允许空小说() throws Exception {
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<String> method = new AtomicReference<>();
        AtomicReference<String> path = new AtomicReference<>();
        AtomicReference<String> body = new AtomicReference<>();
        HttpServer server = server("/internal/v1/executions", exchange -> {
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            method.set(exchange.getRequestMethod());
            path.set(exchange.getRequestURI().getPath());
            body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            respond(exchange, 202, executionAcceptedJson(null));
        });
        try {
            ExecutionStepAccepted accepted = client(server, Duration.ofSeconds(2))
                    .submitExecution(executionStep(null));

            assertThat(accepted.getStatus()).isEqualTo(ExecutionStepAccepted.StatusEnum.QUEUED);
            assertThat(method.get()).isEqualTo("POST");
            assertThat(path.get()).isEqualTo("/internal/v1/executions");
            assertThat(body.get()).contains("\"stepId\":\"step-1\"");
            JsonNode claims = jwtClaims(authorization.get());
            assertThat(claims.path("scope").get(0).asString()).isEqualTo("execution:submit");
            assertThat(claims.path("task_id").asString()).isEqualTo("step-1");
            assertThat(claims.path("run_id").asString()).isEqualTo("run-1");
            assertThat(claims.path("novel_id").isNull()).isTrue();
            assertThat(claims.path("http_method").asString()).isEqualTo("POST");
            assertThat(claims.path("http_path").asString())
                    .isEqualTo("/internal/v1/executions");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void V2取消必须固定Put路径签名身份并回读取消状态() throws Exception {
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<String> method = new AtomicReference<>();
        AtomicReference<String> path = new AtomicReference<>();
        HttpServer server = server("/internal/v1/executions", exchange -> {
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            method.set(exchange.getRequestMethod());
            path.set(exchange.getRequestURI().getPath());
            respond(exchange, 202, executionCancelAcceptedJson());
        });
        try {
            ExecutionCancelAccepted accepted = client(server, Duration.ofSeconds(2))
                    .cancelExecution("job-1", executionCancel());

            assertThat(accepted.getStatus())
                    .isEqualTo(ExecutionCancelAccepted.StatusEnum.ALREADY_TERMINAL);
            assertThat(method.get()).isEqualTo("PUT");
            assertThat(path.get()).isEqualTo("/internal/v1/executions/job-1/cancel");
            JsonNode claims = jwtClaims(authorization.get());
            assertThat(claims.path("scope").get(0).asString()).isEqualTo("execution:cancel");
            assertThat(claims.path("task_id").asString()).isEqualTo("step-1");
            assertThat(claims.path("run_id").asString()).isEqualTo("run-1");
            assertThat(claims.path("novel_id").asString()).isEqualTo("novel-1");
            assertThat(claims.path("http_method").asString()).isEqualTo("PUT");
            assertThat(claims.path("http_path").asString())
                    .isEqualTo("/internal/v1/executions/job-1/cancel");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void V2提交必须逐项拒绝恶意错配响应且未知结果不重试() throws Exception {
        AtomicReference<String> responseBody = new AtomicReference<>();
        AtomicInteger requests = new AtomicInteger();
        HttpServer server = server("/internal/v1/executions", exchange -> {
            requests.incrementAndGet();
            respond(exchange, 202, responseBody.get());
        });
        try {
            AgentServiceClient client = client(server, Duration.ofSeconds(2));
            ExecutionStepRequest request = executionStep("novel-1");
            List<String> mismatches = List.of(
                    executionAcceptedJson("novel-1").replace("\"protocolVersion\":\"2.0\"", "\"protocolVersion\":\"1.0\""),
                    executionAcceptedJson("novel-1").replace("\"jobId\":\"job-1\"", "\"jobId\":\"job-evil\""),
                    executionAcceptedJson("novel-1").replace("\"runId\":\"run-1\"", "\"runId\":\"run-evil\""),
                    executionAcceptedJson("novel-1").replace("\"novelId\":\"novel-1\"", "\"novelId\":\"novel-evil\""),
                    executionAcceptedJson("novel-1").replace("\"stepId\":\"step-1\"", "\"stepId\":\"step-evil\""),
                    executionAcceptedJson("novel-1").replace("\"fencingToken\":7", "\"fencingToken\":8"),
                    executionAcceptedJson("novel-1").replace("\"requestHash\":\"" + "a".repeat(64) + "\"", "\"requestHash\":\"" + "b".repeat(64) + "\""),
                    executionAcceptedJson("novel-1").replace("\"status\":\"queued\"", "\"status\":null"),
                    executionAcceptedJson("novel-1").replace("}", ",\"unknown\":true}"));
            for (String mismatch : mismatches) {
                responseBody.set(mismatch);
                assertThatThrownBy(() -> client.submitExecution(request))
                        .isInstanceOf(AgentGatewayException.class)
                        .extracting(error -> ((AgentGatewayException) error).code())
                        .isEqualTo("AGENT_EXECUTION_SUBMIT_FAILED");
            }
            assertThat(requests.get()).isEqualTo(mismatches.size());
        } finally {
            server.stop(0);
        }

        AtomicInteger unknownRequests = new AtomicInteger();
        HttpServer unknown = server("/internal/v1/executions", exchange -> {
            unknownRequests.incrementAndGet();
            respond(exchange, 503, "{\"detail\":\"结果未知\"}");
        });
        try {
            assertThatThrownBy(() -> client(unknown, Duration.ofSeconds(2))
                            .submitExecution(executionStep("novel-1")))
                    .isInstanceOf(AgentGatewayException.class);
            assertThat(unknownRequests.get()).isEqualTo(1);
        } finally {
            unknown.stop(0);
        }

        HttpServer saturated = server("/internal/v1/executions", exchange -> {
            exchange.getResponseHeaders().set("Retry-After", "1");
            respond(exchange, 503, """
                    {"protocolVersion":"2.0",\
                    "errorCode":"EXECUTION_ADMISSION_SATURATED",\
                    "retryable":true,"retryAfterSeconds":1}
                    """);
        });
        try {
            assertThatThrownBy(() -> client(saturated, Duration.ofSeconds(2))
                            .submitExecution(executionStep("novel-1")))
                    .isInstanceOfSatisfying(
                            WorkflowExecutionAdmissionSaturatedException.class,
                            error -> assertThat(error.retryAfter())
                                    .isEqualTo(Duration.ofSeconds(1)));
        } finally {
            saturated.stop(0);
        }

        // 缺少 Retry-After 的普通 503 不能被猜成“journal 前饱和”，必须保留 lease。
        HttpServer ambiguousSaturated = server(
                "/internal/v1/executions",
                exchange -> respond(exchange, 503, """
                        {"protocolVersion":"2.0",\
                        "errorCode":"EXECUTION_ADMISSION_SATURATED",\
                        "retryable":true,"retryAfterSeconds":1}
                        """));
        try {
            assertThatThrownBy(() -> client(ambiguousSaturated, Duration.ofSeconds(2))
                            .submitExecution(executionStep("novel-1")))
                    .isInstanceOf(AgentGatewayException.class);
        } finally {
            ambiguousSaturated.stop(0);
        }

        HttpServer conflict = server(
                "/internal/v1/executions",
                exchange -> respond(exchange, 409, "{\"detail\":\"requestHash 冲突\"}"));
        try {
            assertThatThrownBy(() -> client(conflict, Duration.ofSeconds(2))
                            .submitExecution(executionStep("novel-1")))
                    .isInstanceOfSatisfying(WorkflowExecutionRejectedException.class, error ->
                            assertThat(error.errorCode())
                                    .isEqualTo("EXECUTION_SUBMIT_REJECTED_409"));
        } finally {
            conflict.stop(0);
        }

        HttpServer timeout = server("/internal/v1/executions", exchange -> {
            Thread.sleep(150);
            respond(exchange, 202, executionAcceptedJson("novel-1"));
        });
        try {
            assertThatThrownBy(() -> client(timeout, Duration.ofMillis(30))
                            .submitExecution(executionStep("novel-1")))
                    .isInstanceOf(AgentGatewayException.class)
                    .extracting(error -> ((AgentGatewayException) error).code())
                    .isEqualTo("AGENT_EXECUTION_SUBMIT_FAILED");
        } finally {
            timeout.stop(0);
        }
    }

    @Test
    void V2取消必须逐项拒绝恶意错配响应() throws Exception {
        AtomicReference<String> responseBody = new AtomicReference<>();
        HttpServer server = server("/internal/v1/executions", exchange ->
                respond(exchange, 202, responseBody.get()));
        try {
            AgentServiceClient client = client(server, Duration.ofSeconds(2));
            List<String> mismatches = List.of(
                    executionCancelAcceptedJson().replace("\"protocolVersion\":\"2.0\"", "\"protocolVersion\":\"1.0\""),
                    executionCancelAcceptedJson().replace("\"jobId\":\"job-1\"", "\"jobId\":\"job-evil\""),
                    executionCancelAcceptedJson().replace("\"runId\":\"run-1\"", "\"runId\":\"run-evil\""),
                    executionCancelAcceptedJson().replace("\"novelId\":\"novel-1\"", "\"novelId\":\"novel-evil\""),
                    executionCancelAcceptedJson().replace("\"stepId\":\"step-1\"", "\"stepId\":\"step-evil\""),
                    executionCancelAcceptedJson().replace("\"fencingToken\":7", "\"fencingToken\":8"),
                    executionCancelAcceptedJson().replace("\"cancelRequestId\":\"cancel-1\"", "\"cancelRequestId\":\"cancel-evil\""),
                    executionCancelAcceptedJson().replace("\"status\":\"already_terminal\"", "\"status\":null"));
            for (String mismatch : mismatches) {
                responseBody.set(mismatch);
                assertThatThrownBy(() -> client.cancelExecution("job-1", executionCancel()))
                        .isInstanceOf(AgentGatewayException.class)
                        .extracting(error -> ((AgentGatewayException) error).code())
                        .isEqualTo("AGENT_EXECUTION_CANCEL_FAILED");
            }
        } finally {
            server.stop(0);
        }
    }

    @Test
    void 调试查询必须绑定原始查询串并只接受对象响应() throws Exception {
        AtomicReference<String> rawQuery = new AtomicReference<>();
        AtomicReference<String> authorization = new AtomicReference<>();
        HttpServer server = server("/internal/v1/debug/workflow-runs", exchange -> {
            rawQuery.set(exchange.getRequestURI().getRawQuery());
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            respond(exchange, 200, "{\"runs\":[]}");
        });
        try {
            Map<String, Object> result = client(server, Duration.ofSeconds(2))
                    .getWorkflowRuns("user 1", null);

            assertThat(result).containsKey("runs");
            assertThat(rawQuery.get()).isEqualTo("userId=user+1");
            String payload = new String(
                    java.util.Base64.getUrlDecoder().decode(
                            authorization.get().substring("Bearer ".length()).split("\\.")[1]),
                    StandardCharsets.UTF_8);
            assertThat(payload).contains("\"http_path\":\"/internal/v1/debug/workflow-runs\"");
            assertThat(payload).contains("\"query_sha256\":\""
                    + sha256("userId=user+1")
                    + "\"");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void Seedance创建与查询必须区分明确拒绝和未知提交结果() throws Exception {
        HttpServer accepted = server("/internal/v1/video/seedance/tasks", exchange -> {
            if (exchange.getRequestURI().getPath().endsWith("/query")) {
                respond(exchange, 200, """
                        {"providerTaskId":"provider-1","status":"running","taskId":"task-1"}
                        """);
            } else {
                respond(exchange, 202, "{\"providerTaskId\":\"provider-1\",\"taskId\":\"task-1\"}");
            }
        });
        try {
            AgentServiceClient client = client(accepted, Duration.ofSeconds(2));
            assertThat(client.submitSeedanceRender(seedanceSubmit()).getProviderTaskId())
                    .isEqualTo("provider-1");
            assertThat(client.querySeedanceRender(
                            new SeedanceRenderQueryRequest("novel-1", 1, "provider-1", "task-1"))
                            .getStatus())
                    .isEqualTo(cn.inkforge.contracts.agent.SeedanceRenderQueryResponse.StatusEnum.RUNNING);
        } finally {
            accepted.stop(0);
        }

        HttpServer rejected = server(
                "/internal/v1/video/seedance/tasks",
                exchange -> respond(exchange, 400, "{\"detail\":\"参考图不符合供应商要求\"}"));
        try {
            assertThatThrownBy(() -> client(rejected, Duration.ofSeconds(2))
                            .submitSeedanceRender(seedanceSubmit()))
                    .isInstanceOfSatisfying(SeedanceGatewayRejectedException.class, error -> {
                        assertThat(error.statusCode()).isEqualTo(400);
                        assertThat(error.getMessage()).isEqualTo("参考图不符合供应商要求");
                    });
        } finally {
            rejected.stop(0);
        }

        HttpServer unknown = server(
                "/internal/v1/video/seedance/tasks",
                exchange -> respond(exchange, 503, "{\"detail\":\"内部失败\"}"));
        try {
            assertThatThrownBy(() -> client(unknown, Duration.ofSeconds(2))
                            .submitSeedanceRender(seedanceSubmit()))
                    .isInstanceOf(SeedanceSubmissionUnknownException.class);
        } finally {
            unknown.stop(0);
        }
    }

    private AgentServiceClient client(HttpServer server, Duration timeout) throws Exception {
        return new AgentServiceClient(
                HttpClient.newBuilder().connectTimeout(timeout).build(),
                URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                signer(),
                new ObjectMapper(),
                timeout);
    }

    private AgentServiceClient productionClient(HttpServer server, Duration timeout)
            throws Exception {
        return new AgentServiceClient(
                new AgentGatewayConfiguration().agentHttpClient(),
                URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                signer(),
                new ObjectMapper(),
                timeout);
    }

    private ServiceTokenSigner signer() throws Exception {
        byte[] seed = java.util.HexFormat.of()
                .parseHex("0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20");
        byte[] encoded = KeyFactory.getInstance("Ed25519")
                .generatePrivate(new EdECPrivateKeySpec(NamedParameterSpec.ED25519, seed))
                .getEncoded();
        Path privateKey = temporaryDirectory.resolve("core-service.pem");
        String pem = "-----BEGIN PRIVATE KEY-----\n"
                + java.util.Base64.getMimeEncoder(64, new byte[] {'\n'}).encodeToString(encoded)
                + "\n-----END PRIVATE KEY-----\n";
        Files.writeString(privateKey, pem, StandardCharsets.US_ASCII);
        Files.setPosixFilePermissions(privateKey, PosixFilePermissions.fromString("rw-------"));
        return ServiceTokenSigner.fromPkcs8File(
                privateKey,
                "core-api",
                "core-api",
                "agent-service",
                "core-v1",
                120,
                List.of(
                        ServiceScope.AGENT_RUN,
                        ServiceScope.AGENT_CANCEL,
                        ServiceScope.AGENT_DEBUG_READ,
                        ServiceScope.EXECUTION_SUBMIT,
                        ServiceScope.EXECUTION_CANCEL,
                        ServiceScope.VIDEO_RENDER));
    }

    private AgentJobRequest job() {
        return new AgentJobRequest(
                "job-1",
                AgentJobRequest.KindEnum.WRITING,
                "novel-1",
                Map.of("resume", false),
                10,
                "1.0",
                "run-1",
                "task-1",
                "user-1");
    }

    private SeedanceRenderSubmitRequest seedanceSubmit() {
        return new SeedanceRenderSubmitRequest(
                5,
                false,
                "a".repeat(64),
                "doubao-seedance-2-5-260628",
                "novel-1",
                "电影感镜头",
                SeedanceRenderSubmitRequest.RatioEnum._9_16,
                SeedanceRenderSubmitRequest.ResolutionEnum._720P,
                "task-1",
                false);
    }

    private ExecutionStepRequest executionStep(String novelId) {
        String bundleId = "evidence-1";
        EvidenceManifest manifest = new EvidenceManifest(bundleId, 1, 0, List.of());
        EvidenceBundle bundle = new EvidenceBundle(
                bundleId,
                List.of(),
                manifest,
                "c".repeat(64),
                "policy-v1",
                "run-1",
                0,
                1);
        StepBudget budget = new StepBudget(1000, 1000, 1000, 1, 1000, 0, 0, 1000, 1000, 60);
        ModelProfileRef model = new ModelProfileRef()
                .deploymentProfileKey("deepseek-v4")
                .profile("writing-primary")
                .promptProfile(new PromptProfileRef()
                        .name("prompt.writer.chapter_selection.v1")
                        .version(1)
                        .sha256("f".repeat(64)))
                .reasoningMode(ModelProfileRef.ReasoningModeEnum.BOUNDED)
                .version(1);
        OutputSchemaRef output = new OutputSchemaRef(
                Map.of("type", "object"), "writing_output", "d".repeat(64), 1);
        return new ExecutionStepRequest(
                budget,
                ExecutionStepRequest.DispatchModeEnum.INITIAL,
                bundle,
                7,
                "execution-step-1",
                Map.of("prompt", "完整正文"),
                "e".repeat(64),
                "job-1",
                ExecutionStepRequest.LaneEnum.CREATIVE,
                model,
                novelId,
                "write_chapter",
                output,
                "2.0",
                "生成章节正文",
                "a".repeat(64),
                "run-1",
                "step-1",
                OffsetDateTime.parse("2026-09-01T00:00:00Z"),
                "long_serial");
    }

    private ExecutionCancelRequest executionCancel() {
        return new ExecutionCancelRequest(
                "cancel-1",
                7,
                "job-1",
                "novel-1",
                "2.0",
                "a".repeat(64),
                OffsetDateTime.parse("2026-09-01T00:01:00Z"),
                "run-1",
                "step-1");
    }

    private static String executionAcceptedJson(String novelId) {
        String novel = novelId == null ? "null" : "\"" + novelId + "\"";
        return """
                {"acceptedAt":"2026-09-01T00:00:01Z","fencingToken":7,
                "jobId":"job-1","novelId":%s,"protocolVersion":"2.0",
                "requestHash":"%s","resolvedModel":{"deploymentFingerprint":"%s",
                "deploymentProfileKey":"deepseek-v4","model":"deepseek-v4-flash",
                "provider":"openai_compatible","transportProfile":"transport.deepseek-v4.v1",
                "endpointProfile":"endpoint.deepseek-official.v1",
                "structuredOutputRoute":"chat_json_output_v1",
                "capabilityVersion":"capability.deepseek-v4.chat-json.v1",
                "reasoningMode":"bounded",
                "supportsRequestIdempotency":true},"runId":"run-1",
                "status":"queued","stepId":"step-1"}
                """.formatted(novel, "a".repeat(64), "f".repeat(64));
    }

    private static String executionCancelAcceptedJson() {
        return """
                {"acceptedAt":"2026-09-01T00:01:01Z","cancelRequestId":"cancel-1",
                "fencingToken":7,"jobId":"job-1","novelId":"novel-1",
                "protocolVersion":"2.0","runId":"run-1",
                "status":"already_terminal","stepId":"step-1"}
                """;
    }

    private static JsonNode jwtClaims(String authorization) {
        String encoded = authorization.substring("Bearer ".length()).split("\\.")[1];
        byte[] decoded = java.util.Base64.getUrlDecoder().decode(encoded);
        return new ObjectMapper().readTree(decoded);
    }

    private static HttpServer server(ThrowingHandler handler) throws Exception {
        return server("/internal/v1/runs", handler);
    }

    private static HttpServer server(String path, ThrowingHandler handler) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(path, exchange -> {
            try {
                handler.handle(exchange);
            } catch (Exception exception) {
                exchange.close();
            }
        });
        server.start();
        return server;
    }

    private static String sha256(String value) throws Exception {
        return java.util.HexFormat.of().formatHex(
                java.security.MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8)));
    }

    private static void respond(HttpExchange exchange, int status, String body) throws Exception {
        byte[] response = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, response.length);
        exchange.getResponseBody().write(response);
        exchange.close();
    }

    @FunctionalInterface
    private interface ThrowingHandler {
        void handle(HttpExchange exchange) throws Exception;
    }
}
