package cn.inkforge.core.chapters.api;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.db.CoreDatabase;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.LocalDateTime;
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
class ChapterRuntimeIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_chapter_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", ChapterRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java章节运行时测试密钥-长度超过三十二字节-不可用于生产");
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
    void 六个冻结章节接口必须在真实数据库Redis和HTTP上闭环() throws Exception {
        String username = "chapter_"
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
        String novelId = "runtime-novel-" + UUID.randomUUID();
        LocalDateTime now = LocalDateTime.parse("2026-08-25T00:00:00.000");
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, "运行时作品")
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, now)
                .set(NOVEL.UPDATEDAT, now)
                .execute();

        HttpResponse<String> created =
                send("POST", "/api/v1/novels/" + novelId + "/chapters", null, cookie);
        assertThat(created.statusCode()).isEqualTo(201);
        JsonNode createdJson = json.readTree(created.body());
        String chapterId = createdJson.get("chapter").get("id").asText();
        String initialUpdatedAt =
                createdJson.get("chapter").get("updatedAt").asText();

        HttpResponse<String> listed =
                send("GET", "/api/v1/novels/" + novelId + "/chapters", null, cookie);
        assertThat(listed.statusCode()).isEqualTo(200);
        assertThat(json.readTree(listed.body()).get("chapters").size()).isEqualTo(1);

        String fullContent = "  第一行\n\n最后一行  ".repeat(500);
        HttpResponse<String> updated = send(
                "PATCH",
                "/api/v1/chapters/" + chapterId,
                json.writeValueAsString(java.util.Map.of(
                        "title", "   ",
                        "content", fullContent,
                        "expectedUpdatedAt", initialUpdatedAt)),
                cookie);
        assertThat(updated.statusCode()).isEqualTo(200);
        String updatedAt = json.readTree(updated.body()).get("updatedAt").asText();

        HttpResponse<String> progress = send(
                "PUT",
                "/api/v1/chapters/" + chapterId + "/progress",
                "{\"content\":\"完整进展\",\"expectedUpdatedAt\":null}",
                cookie);
        assertThat(progress.statusCode()).isEqualTo(200);

        HttpResponse<String> review = send(
                "PATCH",
                "/api/v1/chapters/" + chapterId + "/status",
                "{\"status\":\"review\",\"expectedUpdatedAt\":\""
                        + updatedAt
                        + "\"}",
                cookie);
        assertThat(review.statusCode()).isEqualTo(200);
        assertThat(review.body()).contains("\"status\":\"review\"");

        HttpResponse<String> detail =
                send("GET", "/api/v1/chapters/" + chapterId, null, cookie);
        assertThat(detail.statusCode()).isEqualTo(200);
        JsonNode detailJson = json.readTree(detail.body());
        assertThat(detailJson.get("title").asText()).isEqualTo("未命名章节");
        assertThat(detailJson.get("content").asText()).isEqualTo(fullContent);
        assertThat(detailJson.get("progress").get("content").asText()).isEqualTo("完整进展");
        assertThat(detailJson.get("qualityChecks").size()).isEqualTo(1);
    }

    private HttpResponse<String> send(
            String method, String path, String body, String cookie) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path));
        if (cookie != null) {
            request.header("Cookie", cookie);
        }
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
