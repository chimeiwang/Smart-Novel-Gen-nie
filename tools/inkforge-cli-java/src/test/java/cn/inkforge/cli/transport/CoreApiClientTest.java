package cn.inkforge.cli.transport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.stream.Stream;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.json.JsonMapper;

class CoreApiClientTest {

    private HttpServer server;
    private String origin;
    private final JsonMapper json = JsonMapper.builder().build();

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.start();
        origin = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
    }

    @Test
    void JSON请求保持Cookie和显式null但不开放内部路径() throws Exception {
        server.createContext("/api/v1/auth/me", exchange -> {
            assertThat(exchange.getRequestHeaders().getFirst("Cookie"))
                    .isEqualTo("inkforge-token=secret-session");
            respond(exchange, 200, "application/json", "{\"id\":\"u1\",\"nickname\":null}");
        });
        CoreApiClient client = new CoreApiClient(origin, "secret-session", json);

        assertThat(client.request("GET", "/api/v1/auth/me").get("nickname").isNull())
                .isTrue();
        assertThatThrownBy(() -> client.request("GET", "/internal/v1/secret"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> client.request("GET", "/not-public"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 查询参数按UTF8逐值编码且不允许调用方拼接查询串() throws Exception {
        server.createContext("/api/v1/review-artifacts", exchange -> {
            assertThat(exchange.getRequestURI().getRawQuery())
                    .isEqualTo("novelId=%E4%BD%9C%E5%93%81%2F1&status=draft&status=under_review");
            respond(exchange, 200, "application/json", "{\"items\":[]}");
        });
        CoreApiClient client = new CoreApiClient(origin, "token", json);

        Map<String, List<String>> query = new LinkedHashMap<>();
        query.put("novelId", List.of("作品/1"));
        query.put("status", List.of("draft", "under_review"));
        client.request(
                "GET",
                "/api/v1/review-artifacts",
                query,
                null);

        assertThatThrownBy(() -> client.request("GET", "/api/v1/auth/me?x=1"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 登录只从SetCookie提取会话且错误信封保留公共详情() throws Exception {
        server.createContext("/api/v1/auth/login", exchange -> {
            assertThat(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8))
                    .isEqualTo("{\"username\":\"nie\",\"password\":\"pw\"}");
            exchange.getResponseHeaders().add(
                    "Set-Cookie", "inkforge-token=login-token; Path=/; HttpOnly; SameSite=Lax");
            respond(exchange, 200, "application/json", "{\"id\":\"u1\",\"username\":\"nie\"}");
        });
        server.createContext("/api/v1/failure", exchange -> respond(
                exchange,
                409,
                "application/json",
                "{\"detail\":{\"code\":\"VERSION_CONFLICT\",\"message\":\"版本冲突\","
                        + "\"details\":{\"revision\":3},\"requestId\":\"req-1\"}}"));
        CoreApiClient client = new CoreApiClient(origin, null, json);

        LoginResult login = client.login("nie", "pw");
        assertThat(login.token()).isEqualTo("login-token");
        assertThat(login.user().get("username").textValue()).isEqualTo("nie");
        assertThatThrownBy(() -> client.request("GET", "/api/v1/failure"))
                .isInstanceOfSatisfying(CoreApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("VERSION_CONFLICT");
                    assertThat(error.publicMessage()).isEqualTo("版本冲突");
                    assertThat(error.details().get("revision").intValue()).isEqualTo(3);
                    assertThat(error.requestId()).isEqualTo("req-1");
                    assertThat(error.getMessage()).doesNotContain("login-token");
                });
    }

    @Test
    void 二进制响应流式原子写入且返回完整摘要(@TempDir Path directory) throws Exception {
        byte[] payload = new byte[128 * 1024 + 7];
        for (int index = 0; index < payload.length; index++) payload[index] = (byte) index;
        server.createContext("/api/v1/video/assets/a/content", exchange ->
                respond(exchange, 200, "video/mp4", payload));
        CoreApiClient client = new CoreApiClient(origin, "token", json);
        Path target = directory.resolve("take.mp4");

        FileDescriptor result = client.download(
                "GET", "/api/v1/video/assets/a/content", target);

        assertThat(Files.readAllBytes(target)).containsExactly(payload);
        assertThat(result.path()).isEqualTo(target.toAbsolutePath().normalize().toString());
        assertThat(result.bytes()).isEqualTo(payload.length);
        assertThat(result.mediaType()).isEqualTo("video/mp4");
        assertThat(result.sha256()).matches("[0-9a-f]{64}");
        try (Stream<Path> files = Files.list(directory)) {
            assertThat(files.filter(path -> path.getFileName().toString().endsWith(".tmp")))
                    .isEmpty();
        }
    }

    @Test
    void Multipart上传保留完整原始字节和表单且不把Cookie写入正文(@TempDir Path directory)
            throws Exception {
        byte[] payload = new byte[128 * 1024 + 13];
        for (int index = 0; index < payload.length; index++) payload[index] = (byte) (index * 31);
        Path source = directory.resolve("角色.png");
        Files.write(source, payload);
        server.createContext("/api/v1/video/projects/p1/assets", exchange -> {
            assertThat(exchange.getRequestHeaders().getFirst("Cookie"))
                    .isEqualTo("inkforge-token=upload-token");
            String contentType = exchange.getRequestHeaders().getFirst("Content-Type");
            assertThat(contentType).startsWith("multipart/form-data; boundary=inkforge-");
            byte[] body = exchange.getRequestBody().readAllBytes();
            assertThat(body).containsSubsequence(payload);
            String readable = new String(body, StandardCharsets.ISO_8859_1);
            assertThat(readable)
                    .contains("name=\"modality\"", "image", "filename=\"")
                    .doesNotContain("upload-token");
            respond(exchange, 200, "application/json", "{\"id\":\"asset-1\"}");
        });
        CoreApiClient client = new CoreApiClient(origin, "upload-token", json);

        assertThat(client.upload(
                                "/api/v1/video/projects/p1/assets",
                                source,
                                "image/png",
                                Map.of("name", "角色身份图", "modality", "image"))
                        .get("id")
                        .textValue())
                .isEqualTo("asset-1");
    }

    @Test
    void SSE解析多行JSON与纯文本并携带LastEventId() throws Exception {
        server.createContext("/api/v1/writing/runs/task-1/events", exchange -> {
            assertThat(exchange.getRequestHeaders().getFirst("Accept"))
                    .isEqualTo("text/event-stream");
            assertThat(exchange.getRequestHeaders().getFirst("Last-Event-ID"))
                    .isEqualTo("cursor-7");
            String events = "id: event-8\n"
                    + "event: progress\n"
                    + "data: {\"step\":8,\n"
                    + "data: \"tail\":\"尾部😀\"}\n\n"
                    + "data: plain text\n\n";
            respond(exchange, 200, "text/event-stream", events);
        });
        CoreApiClient client = new CoreApiClient(origin, "token", json);

        try (SseStream stream = client.openSse("task-1", "cursor-7")) {
            assertThat(stream.hasNext()).isTrue();
            assertThat(stream.next().at("/data/tail").textValue()).isEqualTo("尾部😀");
            assertThat(stream.hasNext()).isTrue();
            assertThat(stream.next().get("data").textValue()).isEqualTo("plain text");
            assertThat(stream.hasNext()).isFalse();
        }
    }

    private static void respond(
            HttpExchange exchange, int status, String mediaType, String body) throws IOException {
        respond(exchange, status, mediaType, body.getBytes(StandardCharsets.UTF_8));
    }

    private static void respond(
            HttpExchange exchange, int status, String mediaType, byte[] body) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", mediaType);
        exchange.sendResponseHeaders(status, body.length);
        exchange.getResponseBody().write(body);
        exchange.close();
    }
}
