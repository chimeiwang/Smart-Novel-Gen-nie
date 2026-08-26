package cn.inkforge.core.outlines.api;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.db.CoreDatabase;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(
        classes = CoreApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OutlineRuntimeIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_outline_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", OutlineRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java大纲运行时测试密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
    }

    @BeforeAll
    static void restoreSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    @LocalServerPort
    private int port;

    @Autowired
    private CoreDatabase database;

    @Autowired
    private ObjectMapper json;

    private final HttpClient client = HttpClient.newHttpClient();
    private String userId;

    @AfterEach
    void cleanup() {
        if (userId != null) {
            database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        }
    }

    @Test
    void 十个冻结大纲接口必须在真实运行时闭环() throws Exception {
        String username = "outline_"
                + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        HttpResponse<String> registration = send(
                "POST",
                "/api/v1/auth/register",
                "{\"username\":\"" + username
                        + "\",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}",
                null);
        assertThat(registration.statusCode()).isEqualTo(201);
        userId = database.dsl().select(USER.ID)
                .from(USER)
                .where(USER.USERNAME.eq(username))
                .fetchSingle(USER.ID);
        String cookie = registration.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];
        String novelId = "runtime-outline-" + UUID.randomUUID();
        LocalDateTime initial = LocalDateTime.parse("2026-08-25T01:00:00.000");
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, "运行时作品")
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, initial)
                .set(NOVEL.UPDATEDAT, initial)
                .execute();
        database.dsl().insertInto(OUTLINE)
                .set(OUTLINE.ID, novelId + "-outline")
                .set(OUTLINE.NOVELID, novelId)
                .set(OUTLINE.CONTENT, "旧大纲")
                .set(OUTLINE.CREATEDAT, initial)
                .set(OUTLINE.UPDATEDAT, initial)
                .execute();

        String fullOutline = "  第一幕\n\n第二幕  ".repeat(1_000);
        HttpResponse<String> outline = send(
                "PUT",
                "/api/v1/novels/" + novelId + "/outline",
                json.writeValueAsString(Map.of(
                        "content", fullOutline,
                        "expectedUpdatedAt", "2026-08-25T01:00:00Z")),
                cookie);
        assertThat(outline.statusCode()).isEqualTo(200);
        assertThat(json.readTree(outline.body()).get("content").asText())
                .isEqualTo(fullOutline);

        HttpResponse<String> missingPlotVersion = send(
                "PUT",
                "/api/v1/novels/" + novelId + "/plot-progress",
                "{\"currentStage\":\"第一幕\"}",
                cookie);
        assertThat(missingPlotVersion.statusCode()).isEqualTo(422);
        assertThat(missingPlotVersion.body()).contains("\"type\":\"missing\"");
        HttpResponse<String> plot = send(
                "PUT",
                "/api/v1/novels/" + novelId + "/plot-progress",
                "{\"currentStage\":\"第一幕\",\"expectedUpdatedAt\":null}",
                cookie);
        assertThat(plot.statusCode()).isEqualTo(200);

        HttpResponse<String> createdNode = send(
                "POST",
                "/api/v1/novels/" + novelId + "/outline-nodes",
                "{\"title\":\"第一卷\",\"kind\":\"stage\","
                        + "\"clientRequestId\":\"outline-runtime-node-0001\"}",
                cookie);
        assertThat(createdNode.statusCode()).isEqualTo(201);
        JsonNode node = json.readTree(createdNode.body());
        String nodeId = node.get("id").asText();
        String nodeVersion = node.get("updatedAt").asText();
        HttpResponse<String> nodes = send(
                "GET", "/api/v1/novels/" + novelId + "/outline-nodes", null, cookie);
        assertThat(nodes.statusCode()).isEqualTo(200);
        assertThat(json.readTree(nodes.body()).size()).isEqualTo(1);
        HttpResponse<String> updatedNode = send(
                "PATCH",
                "/api/v1/novels/" + novelId + "/outline-nodes/" + nodeId,
                json.writeValueAsString(Map.of(
                        "title", "第一卷·新",
                        "expectedUpdatedAt", nodeVersion)),
                cookie);
        assertThat(updatedNode.statusCode()).isEqualTo(200);
        String updatedNodeVersion =
                json.readTree(updatedNode.body()).get("updatedAt").asText();

        HttpResponse<String> createdForeshadowing = send(
                "POST",
                "/api/v1/novels/" + novelId + "/foreshadowings",
                "{\"name\":\"门上的划痕\",\"plantedContent\":\"  原文\\r\\n  \"}",
                cookie);
        assertThat(createdForeshadowing.statusCode()).isEqualTo(201);
        String foreshadowingId =
                json.readTree(createdForeshadowing.body()).get("id").asText();
        HttpResponse<String> foreshadowings = send(
                "GET", "/api/v1/novels/" + novelId + "/foreshadowings", null, cookie);
        assertThat(foreshadowings.statusCode()).isEqualTo(200);
        assertThat(json.readTree(foreshadowings.body()).size()).isEqualTo(1);
        HttpResponse<String> updatedForeshadowing = send(
                "PATCH",
                "/api/v1/novels/" + novelId + "/foreshadowings/" + foreshadowingId,
                "{\"status\":\"paid_off\"}",
                cookie);
        assertThat(updatedForeshadowing.statusCode()).isEqualTo(200);

        assertThat(send(
                                "DELETE",
                                "/api/v1/novels/" + novelId + "/foreshadowings/"
                                        + foreshadowingId,
                                null,
                                cookie)
                        .statusCode())
                .isEqualTo(204);
        HttpResponse<String> deletedNode = send(
                "DELETE",
                "/api/v1/novels/" + novelId + "/outline-nodes/" + nodeId,
                json.writeValueAsString(Map.of("expectedUpdatedAt", updatedNodeVersion)),
                cookie);
        assertThat(deletedNode.statusCode()).isEqualTo(200);
    }

    private HttpResponse<String> send(
            String method, String path, String body, String cookie) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path));
        if (cookie != null) request.header("Cookie", cookie);
        if (body == null) {
            request.method(method, HttpRequest.BodyPublishers.noBody());
        } else {
            request.header("Content-Type", "application/json")
                    .method(method, HttpRequest.BodyPublishers.ofString(body));
        }
        return client.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
    }
}
