package cn.inkforge.core.references.api;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.references.domain.RagJobIdentity;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
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
        classes = {CoreApplication.class, ReferenceRuntimeIntegrationTest.AuthCapture.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReferenceRuntimeIntegrationTest {

    private static final AtomicReference<byte[]> CALLBACK_BODY = new AtomicReference<>();

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_reference_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", ReferenceRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java资料运行时测试密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("TRUSTED_AGENT_CIDRS", () -> "127.0.0.1/32");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
    }

    @BeforeAll
    static void restoreSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql", "-v", "ON_ERROR_STOP=1",
                "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(),
                "-f", "/tmp/novelwriterdev-schema.sql");
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
    private String novelId;

    @AfterEach
    void cleanup() {
        if (novelId != null) {
            database.dsl().deleteFrom(NOVEL).where(NOVEL.ID.eq(novelId)).execute();
        }
        if (userId != null) {
            database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        }
    }

    @Test
    void 九个冻结资料与索引接口必须在真实HTTP数据库Redis和pgvector闭环() throws Exception {
        String username = "reference_"
                + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        HttpResponse<String> registration = send(
                "POST",
                "/api/v1/auth/register",
                "{\"username\":\"" + username
                        + "\",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}",
                null,
                false);
        assertThat(registration.statusCode()).isEqualTo(201);
        userId = database.dsl().select(USER.ID)
                .from(USER)
                .where(USER.USERNAME.eq(username))
                .fetchSingle(USER.ID);
        String cookie = registration.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];
        novelId = "runtime-reference-novel-" + UUID.randomUUID();
        LocalDateTime now = LocalDateTime.parse("2026-08-25T00:00:00.000");
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, "资料运行时作品")
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, now)
                .set(NOVEL.UPDATEDAT, now)
                .execute();

        String content = "  完整正文\r\n😀  ";
        String createBody = json.writeValueAsString(java.util.Map.of(
                "clientRequestId", "runtime-reference-request-0001",
                "title", "  原标题  ",
                "type", "note",
                "content", content,
                "sourceUrl", "https://example.test/source"));
        HttpResponse<String> created = send(
                "POST", "/api/v1/novels/" + novelId + "/references", createBody, cookie, false);
        assertThat(created.statusCode()).as(created.body()).isEqualTo(201);
        JsonNode createdJson = json.readTree(created.body());
        String referenceId = createdJson.get("id").asText();
        String contentHash = createdJson.get("contentHash").asText();
        OffsetDateTime generation = OffsetDateTime.parse(createdJson.get("createdAt").asText());
        assertThat(createdJson.get("content").asText()).isEqualTo(content);
        assertThat(createdJson.get("effective").asBoolean()).isTrue();

        HttpResponse<String> replay = send(
                "POST", "/api/v1/novels/" + novelId + "/references", createBody, cookie, false);
        assertThat(json.readTree(replay.body()).get("effective").asBoolean()).isFalse();

        HttpResponse<String> listed = send(
                "GET", "/api/v1/novels/" + novelId + "/references", null, cookie, false);
        assertThat(listed.statusCode()).isEqualTo(200);
        assertThat(json.readTree(listed.body()).size()).isEqualTo(1);

        HttpResponse<String> updated = send(
                "PATCH",
                "/api/v1/novels/" + novelId + "/references/" + referenceId,
                json.writeValueAsString(java.util.Map.of(
                        "title", "新标题",
                        "expectedUpdatedAt", createdJson.get("updatedAt").asText())),
                cookie,
                false);
        assertThat(updated.statusCode()).as(updated.body()).isEqualTo(200);
        JsonNode updatedJson = json.readTree(updated.body());

        HttpResponse<String> unavailable = send(
                "POST",
                "/api/v1/novels/" + novelId + "/references/" + referenceId + "/reindex",
                "{\"expectedContentHash\":\"" + contentHash + "\"}",
                cookie,
                false);
        assertThat(unavailable.statusCode()).isEqualTo(503);
        assertThat(json.readTree(unavailable.body()).get("code").asText())
                .isEqualTo("RAG_INDEX_UNAVAILABLE");

        RagJobIdentity identity = RagJobIdentity.create(referenceId, contentHash, generation);
        String contextBody = "{  \"userId\":\"" + userId
                + "\",\"taskId\":\"" + identity.taskId()
                + "\",\"runId\":\"" + identity.runId()
                + "\",\"expectedContentHash\":\"" + contentHash
                + "\"  }";
        HttpResponse<String> context = send(
                "POST",
                "/internal/v1/novels/" + novelId + "/references/" + referenceId + "/index-context",
                contextBody,
                null,
                true);
        assertThat(context.statusCode()).as(context.body()).isEqualTo(200);
        assertThat(CALLBACK_BODY.get()).isEqualTo(contextBody.getBytes(StandardCharsets.UTF_8));
        assertThat(json.readTree(context.body()).get("chunks").get(0).asText()).isEqualTo(content);

        String successBody = json.writeValueAsString(java.util.Map.of(
                "taskId", identity.taskId(),
                "runId", identity.runId(),
                "expectedContentHash", contentHash,
                "embeddings", java.util.List.of(java.util.List.of(1.0, 0.0))));
        HttpResponse<String> completed = send(
                "PUT",
                "/internal/v1/novels/" + novelId + "/references/" + referenceId + "/index-success",
                successBody,
                null,
                true);
        assertThat(completed.statusCode()).as(completed.body()).isEqualTo(200);
        assertThat(json.readTree(completed.body()).get("ragStatus").asText()).isEqualTo("ready");

        HttpResponse<String> search = send(
                "POST",
                "/api/v1/novels/" + novelId + "/references/search",
                "{\"queryEmbedding\":[1.0,0.0],\"topK\":5}",
                cookie,
                false);
        assertThat(search.statusCode()).as(search.body()).isEqualTo(200);
        JsonNode hit = json.readTree(search.body()).get(0);
        assertThat(hit.get("sourceId").asText()).isEqualTo(referenceId);
        assertThat(hit.get("text").asText()).isEqualTo(content);

        String failureBody = json.writeValueAsString(java.util.Map.of(
                "taskId", identity.taskId(),
                "runId", identity.runId(),
                "expectedContentHash", contentHash,
                "message", "供应商内部敏感详情"));
        HttpResponse<String> terminalConflict = send(
                "PUT",
                "/internal/v1/novels/" + novelId + "/references/" + referenceId + "/index-failure",
                failureBody,
                null,
                true);
        assertThat(terminalConflict.statusCode()).isEqualTo(409);
        assertThat(terminalConflict.body()).doesNotContain("供应商内部敏感详情");

        HttpResponse<String> deleted = send(
                "DELETE",
                "/api/v1/novels/" + novelId + "/references/" + referenceId,
                "{\"expectedUpdatedAt\":\"" + updatedJson.get("updatedAt").asText() + "\"}",
                cookie,
                false);
        assertThat(deleted.statusCode()).as(deleted.body()).isEqualTo(200);
        JsonNode affected = json.readTree(deleted.body()).get("affected");
        assertThat(affected.get("ragDocuments").asInt()).isEqualTo(1);
        assertThat(affected.get("ragChunks").asInt()).isEqualTo(1);
    }

    private HttpResponse<String> send(
            String method,
            String path,
            String body,
            String cookie,
            boolean internal) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path));
        if (cookie != null) request.header("Cookie", cookie);
        if (internal) request.header("Authorization", "Bearer captured-by-test");
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

    @TestConfiguration(proxyBeanMethods = false)
    static class AuthCapture {

        @Bean
        @Primary
        InternalServiceAuthenticator capturingAuthenticator() {
            return (request, body, scope, taskId, runId, novelId, code, message) -> {
                CALLBACK_BODY.set(body.clone());
                return null;
            };
        }
    }
}
