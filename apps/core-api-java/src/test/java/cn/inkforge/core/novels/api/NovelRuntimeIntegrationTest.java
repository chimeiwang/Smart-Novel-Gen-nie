package cn.inkforge.core.novels.api;

import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.db.CoreDatabase;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
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
class NovelRuntimeIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_novel_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", NovelRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java小说运行时测试密钥-长度超过三十二字节-不可用于生产");
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
    void 十个冻结小说接口必须在真实数据库Redis和HTTP上闭环() throws Exception {
        String username = "novel_"
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

        HttpResponse<String> created = send(
                "POST",
                "/api/v1/novels",
                json.writeValueAsString(Map.of(
                        "name", "  运行时长篇  ",
                        "summary", "初始简介",
                        "storyLengthProfile", "long_serial",
                        "firstChapterGoal", "建立冲突")),
                cookie);
        assertThat(created.statusCode()).isEqualTo(201);
        JsonNode createdJson = json.readTree(created.body());
        String novelId = createdJson.get("novelId").asText();
        String chapterId = createdJson.get("chapterId").asText();

        HttpResponse<String> dashboard = send("GET", "/api/v1/dashboard", null, cookie);
        assertThat(dashboard.statusCode()).isEqualTo(200);
        assertThat(json.readTree(dashboard.body()).get("novels").get(0).get("id").asText())
                .isEqualTo(novelId);

        HttpResponse<String> listed = send(
                "GET",
                "/api/v1/novels?storyLengthProfile=long_serial",
                null,
                cookie);
        assertThat(listed.statusCode()).isEqualTo(200);
        assertThat(json.readTree(listed.body()).size()).isEqualTo(1);

        HttpResponse<String> detail =
                send("GET", "/api/v1/novels/" + novelId, null, cookie);
        assertThat(detail.statusCode()).isEqualTo(200);
        JsonNode detailJson = json.readTree(detail.body());
        assertThat(detailJson.get("name").asText()).isEqualTo("运行时长篇");
        assertThat(detailJson.get("targetTotalWordCount").asInt()).isEqualTo(1_000_000);

        assertOk("/api/v1/novels/" + novelId + "/workspace?chapterId=" + chapterId, cookie);
        HttpResponse<String> bootstrap = assertOk(
                "/api/v1/novels/" + novelId + "/workspace/bootstrap", cookie);
        assertThat(json.readTree(bootstrap.body()).get("currentChapterId").asText())
                .isEqualTo(chapterId);
        assertOk("/api/v1/novels/" + novelId + "/workspace/lore", cookie);
        assertOk("/api/v1/novels/" + novelId + "/workspace/planning", cookie);
        assertOk("/api/v1/novels/" + novelId + "/workspace/resources", cookie);

        HttpResponse<String> updated = send(
                "PUT",
                "/api/v1/novels/" + novelId + "/summary",
                json.writeValueAsString(Map.of(
                        "summary", "更新简介",
                        "expectedUpdatedAt", detailJson.get("updatedAt").asText())),
                cookie);
        assertThat(updated.statusCode()).isEqualTo(200);
        assertThat(json.readTree(updated.body()).get("summary").asText())
                .isEqualTo("更新简介");

        String sourceText = "  完整开头\n😀  ";
        HttpResponse<String> shortCreated = send(
                "POST",
                "/api/v1/novels",
                json.writeValueAsString(Map.of(
                        "name", "短篇",
                        "storyLengthProfile", "short_medium",
                        "targetTotalWordCount", 12_000,
                        "clientRequestId", "runtime-short-request-0001",
                        "sourceKind", "opening",
                        "sourceText", sourceText)),
                cookie);
        assertThat(shortCreated.statusCode()).isEqualTo(201);
        HttpResponse<String> shortReplay = send(
                "POST",
                "/api/v1/novels",
                json.writeValueAsString(Map.of(
                        "name", "短篇",
                        "storyLengthProfile", "short_medium",
                        "targetTotalWordCount", 12_000,
                        "clientRequestId", "runtime-short-request-0001",
                        "sourceKind", "opening",
                        "sourceText", sourceText)),
                cookie);
        assertThat(shortReplay.statusCode()).isEqualTo(201);
        assertThat(json.readTree(shortReplay.body()))
                .isEqualTo(json.readTree(shortCreated.body()));
    }

    private HttpResponse<String> assertOk(String path, String cookie) throws Exception {
        HttpResponse<String> response = send("GET", path, null, cookie);
        assertThat(response.statusCode()).as(response.body()).isEqualTo(200);
        return response;
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
