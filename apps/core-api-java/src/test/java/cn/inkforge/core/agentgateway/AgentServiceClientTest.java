package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.agent.AgentJobAccepted;
import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.contracts.agent.SeedanceRenderQueryRequest;
import cn.inkforge.contracts.agent.SeedanceRenderSubmitRequest;
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
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

class AgentServiceClientTest {

    @TempDir
    private Path temporaryDirectory;

    @Test
    void 提交必须发送受签名原始正文并解析严格响应() throws Exception {
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<String> receivedBody = new AtomicReference<>();
        HttpServer server = server(exchange -> {
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            receivedBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            respond(exchange, 202, """
                    {"protocolVersion":"1.0","jobId":"job-1","runId":"run-1",\
                    "taskId":"task-1","status":"queued"}
                    """);
        });
        try {
            AgentJobAccepted accepted = client(server, Duration.ofSeconds(2)).submit(job());

            assertThat(accepted.getStatus()).isEqualTo(AgentJobAccepted.StatusEnum.QUEUED);
            assertThat(authorization.get()).startsWith("Bearer eyJ");
            assertThat(receivedBody.get()).contains("\"jobId\":\"job-1\"");
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
