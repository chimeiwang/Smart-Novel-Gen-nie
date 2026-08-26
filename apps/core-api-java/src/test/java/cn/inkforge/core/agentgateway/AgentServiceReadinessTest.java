package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
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
                HttpClient.newHttpClient(),
                URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                new ObjectMapper(),
                Duration.ofSeconds(1));
    }

    private static HttpServer server(int status, String body) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/health/ready", exchange -> {
            byte[] response = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
        return server;
    }
}
