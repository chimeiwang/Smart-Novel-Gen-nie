package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class AgentServiceReadinessTest {

    @Test
    void 只有Agent明确返回ready才可通过() throws Exception {
        HttpServer server = server(200, "{\"status\":\"ready\",\"checks\":{}}");
        try {
            AgentServiceReadiness readiness = readiness(server);
            assertThat(readiness.check()).isTrue();
        } finally {
            server.stop(0);
        }

        HttpServer notReady = server(503, "{\"status\":\"not_ready\"}");
        try {
            assertThat(readiness(notReady).check()).isFalse();
        } finally {
            notReady.stop(0);
        }
    }

    @Test
    void 首次检查必须先通过无写入POST协议探针且成功后不重复() throws Exception {
        List<String> paths = new CopyOnWriteArrayList<>();
        AtomicReference<String> method = new AtomicReference<>();
        AtomicReference<String> body = new AtomicReference<>();
        AtomicReference<String> upgrade = new AtomicReference<>();
        HttpServer server = server(
                200,
                "{\"status\":\"ready\",\"checks\":{}}",
                exchange -> {
                    paths.add(exchange.getRequestURI().getPath());
                    method.set(exchange.getRequestMethod());
                    body.set(new String(
                            exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
                    upgrade.set(exchange.getRequestHeaders().getFirst("Upgrade"));
                    respond(exchange, 422, "{}");
                },
                paths);
        try {
            AgentServiceReadiness readiness = readiness(server);

            assertThat(readiness.check()).isTrue();
            assertThat(readiness.check()).isTrue();

            assertThat(paths).containsExactly(
                    "/internal/v1/runs",
                    "/internal/v1/health/ready",
                    "/internal/v1/health/ready");
            assertThat(method.get()).isEqualTo("POST");
            assertThat(body.get()).isEqualTo("{}");
            assertThat(upgrade.get()).isNull();
        } finally {
            server.stop(0);
        }
    }

    @Test
    void POST协议探针被服务器以400拒绝时不得报告就绪() throws Exception {
        HttpServer server = server(
                200,
                "{\"status\":\"ready\",\"checks\":{}}",
                exchange -> respond(exchange, 400, "{}"),
                new CopyOnWriteArrayList<>());
        try {
            assertThat(readiness(server).check()).isFalse();
        } finally {
            server.stop(0);
        }
    }

    @Test
    void 超时无效JSON和网络失败都必须收敛为false() throws Exception {
        HttpServer invalid = server(200, "[]");
        try {
            assertThat(readiness(invalid).check()).isFalse();
        } finally {
            invalid.stop(0);
        }

        AgentServiceReadiness unavailable = new AgentServiceReadiness(
                HttpClient.newBuilder().connectTimeout(Duration.ofMillis(100)).build(),
                URI.create("http://127.0.0.1:1"),
                new ObjectMapper(),
                Duration.ofMillis(100));
        assertThat(unavailable.check()).isFalse();
        assertThat(unavailable.toString()).doesNotContain("127.0.0.1");
    }

    private AgentServiceReadiness readiness(HttpServer server) {
        return new AgentServiceReadiness(
                new AgentGatewayConfiguration().agentHttpClient(),
                URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                new ObjectMapper(),
                Duration.ofSeconds(1));
    }

    private static HttpServer server(int status, String body) throws Exception {
        return server(
                status,
                body,
                exchange -> respond(exchange, 422, "{}"),
                new CopyOnWriteArrayList<>());
    }

    private static HttpServer server(
            int status,
            String body,
            HttpHandler runHandler,
            List<String> paths) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/health/ready", exchange -> {
            paths.add(exchange.getRequestURI().getPath());
            respond(exchange, status, body);
        });
        server.createContext("/internal/v1/runs", runHandler);
        server.start();
        return server;
    }

    private static void respond(HttpExchange exchange, int status, String body)
            throws IOException {
        byte[] response = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, response.length);
        exchange.getResponseBody().write(response);
        exchange.close();
    }
}
