package cn.inkforge.core.styles.api;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterAll;
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
        classes = {CoreApplication.class, StyleRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StyleRuntimeIntegrationTest {

    private static final AtomicReference<byte[]> CALLBACK_BODY = new AtomicReference<>();
    private static final Path UPLOAD_ROOT = Path.of(
            System.getProperty("java.io.tmpdir"),
            "inkforge-style-runtime-" + UUID.randomUUID());

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_style_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", StyleRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java文风运行时测试密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("TRUSTED_AGENT_CIDRS", () -> "127.0.0.1/32");
        registry.add("UPLOADS_ROOT", UPLOAD_ROOT::toString);
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

    @AfterAll
    static void cleanupUploads() throws Exception {
        if (!Files.exists(UPLOAD_ROOT)) return;
        try (var paths = Files.walk(UPLOAD_ROOT)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
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
    void cleanupRows() {
        if (novelId != null) {
            database.dsl().deleteFrom(NOVEL).where(NOVEL.ID.eq(novelId)).execute();
        }
        if (userId != null) {
            database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        }
    }

    @Test
    void 十四个冻结文风接口必须在真实HTTP文件数据库Redis和回调上闭环() throws Exception {
        String username = "style_"
                + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        HttpResponse<String> registration = jsonRequest(
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
        novelId = "runtime-style-novel-" + UUID.randomUUID();
        LocalDateTime now = LocalDateTime.parse("2026-08-25T00:00:00.000");
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, "文风运行时作品")
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, now)
                .set(NOVEL.UPDATEDAT, now)
                .execute();

        HttpResponse<String> created = jsonRequest(
                "POST", "/api/v1/styles", "{\"name\":\"  运行时文风  \"}", cookie, false);
        assertThat(created.statusCode()).as(created.body()).isEqualTo(201);
        String styleId = json.readTree(created.body()).get("id").asText();
        HttpResponse<String> listed = jsonRequest("GET", "/api/v1/styles", null, cookie, false);
        assertThat(json.readTree(listed.body()).get(0).get("id").asText()).isEqualTo(styleId);

        String source = "  第一段\r\n😀完整来源  ";
        HttpResponse<String> uploaded = multipart(
                "/api/v1/styles/" + styleId + "/references",
                "作品.txt",
                source.getBytes(StandardCharsets.UTF_8),
                cookie);
        assertThat(uploaded.statusCode()).as(uploaded.body()).isEqualTo(201);
        JsonNode uploadedJson = json.readTree(uploaded.body());
        String referenceId = uploadedJson.get("id").asText();
        assertThat(uploadedJson.get("charCount").asInt()).isEqualTo(8);

        HttpResponse<String> portrait = jsonRequest(
                "POST", "/api/v1/styles/" + styleId + "/portrait", null, cookie, false);
        assertThat(portrait.statusCode()).as(portrait.body()).isEqualTo(202);
        String fullTaskId = json.readTree(portrait.body()).get("taskId").asText();
        assertThat(jsonRequest(
                                "GET",
                                "/api/v1/portrait-tasks/" + fullTaskId,
                                null,
                                cookie,
                                false)
                        .statusCode())
                .isEqualTo(200);

        String contextBody = "{  \"runId\":\"" + fullTaskId + "\"  }";
        HttpResponse<String> context = jsonRequest(
                "POST",
                "/internal/v1/styles/" + styleId + "/portrait-tasks/" + fullTaskId
                        + "/portrait-context",
                contextBody,
                null,
                true);
        assertThat(context.statusCode()).as(context.body()).isEqualTo(200);
        assertThat(CALLBACK_BODY.get()).isEqualTo(contextBody.getBytes(StandardCharsets.UTF_8));
        assertThat(json.readTree(context.body()).get("sourceText").asText()).endsWith(source);

        assertThat(jsonRequest(
                                "PUT",
                                "/internal/v1/styles/" + styleId + "/portrait-tasks/" + fullTaskId
                                        + "/processing",
                                "{\"runId\":\"" + fullTaskId + "\"}",
                                null,
                                true)
                        .statusCode())
                .isEqualTo(200);
        String successBody = json.writeValueAsString(java.util.Map.ofEntries(
                java.util.Map.entry("mode", "full"),
                java.util.Map.entry("runId", fullTaskId),
                java.util.Map.entry("creativeMethodology", "方法"),
                java.util.Map.entry("uniqueMarkers", "标记"),
                java.util.Map.entry("generationStyle", "生成"),
                java.util.Map.entry("expressionFeatures", "表达"),
                java.util.Map.entry("styleTraits", "特质"),
                java.util.Map.entry("originalCharCount", 8),
                java.util.Map.entry("usedCharCount", 8),
                java.util.Map.entry("truncated", false)));
        HttpResponse<String> completed = jsonRequest(
                "PUT",
                "/internal/v1/styles/" + styleId + "/portrait-tasks/" + fullTaskId + "/success",
                successBody,
                null,
                true);
        assertThat(completed.statusCode()).as(completed.body()).isEqualTo(200);
        assertThat(json.readTree(completed.body()).get("status").asText()).isEqualTo("success");

        HttpResponse<String> edited = jsonRequest(
                "PATCH",
                "/api/v1/styles/" + styleId + "/sections/styleTraits",
                "{\"content\":\"  新特质  \"}",
                cookie,
                false);
        assertThat(edited.statusCode()).as(edited.body()).isEqualTo(200);
        assertThat(json.readTree(edited.body()).get("styleTraits").asText()).isEqualTo("新特质");

        HttpResponse<String> applied = jsonRequest(
                "PATCH",
                "/api/v1/novels/" + novelId + "/applied-style",
                "{\"styleId\":\"" + styleId + "\",\"expectedStyleId\":null}",
                cookie,
                false);
        assertThat(applied.statusCode()).as(applied.body()).isEqualTo(200);
        assertThat(json.readTree(applied.body()).get("effective").asBoolean()).isTrue();

        HttpResponse<String> sectionPortrait = jsonRequest(
                "POST",
                "/api/v1/styles/" + styleId + "/sections/uniqueMarkers/portrait",
                null,
                cookie,
                false);
        String sectionTaskId = json.readTree(sectionPortrait.body()).get("taskId").asText();
        transition(styleId, sectionTaskId, "processing", "{\"runId\":\"" + sectionTaskId + "\"}");
        String sectionSuccess = json.writeValueAsString(java.util.Map.of(
                "mode", "section",
                "runId", sectionTaskId,
                "section", "uniqueMarkers",
                "content", "新标记",
                "originalCharCount", 8,
                "usedCharCount", 8,
                "truncated", false));
        transition(styleId, sectionTaskId, "success", sectionSuccess);

        String failureTaskId = json.readTree(jsonRequest(
                        "POST", "/api/v1/styles/" + styleId + "/portrait", null, cookie, false)
                .body()).get("taskId").asText();
        transition(styleId, failureTaskId, "processing", "{\"runId\":\"" + failureTaskId + "\"}");
        HttpResponse<String> failed = transition(
                styleId,
                failureTaskId,
                "failure",
                "{\"runId\":\"" + failureTaskId + "\",\"message\":\"供应商敏感详情\"}");
        assertThat(json.readTree(failed.body()).get("errorMessage").asText())
                .isEqualTo("画像生成失败");
        assertThat(failed.body()).doesNotContain("供应商敏感详情");

        assertThat(jsonRequest(
                                "DELETE",
                                "/api/v1/styles/" + styleId + "/references/" + referenceId,
                                null,
                                cookie,
                                false)
                        .statusCode())
                .isEqualTo(204);
        assertThat(jsonRequest(
                                "DELETE", "/api/v1/styles/" + styleId, null, cookie, false)
                        .statusCode())
                .isEqualTo(204);
        assertThat(database.dsl().select(NOVEL.APPLIEDSTYLEID)
                        .from(NOVEL)
                        .where(NOVEL.ID.eq(novelId))
                        .fetchSingle(NOVEL.APPLIEDSTYLEID))
                .isNull();
    }

    private HttpResponse<String> transition(
            String styleId, String taskId, String action, String body) throws Exception {
        return jsonRequest(
                "PUT",
                "/internal/v1/styles/" + styleId + "/portrait-tasks/" + taskId + "/" + action,
                body,
                null,
                true);
    }

    private HttpResponse<String> jsonRequest(
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

    private HttpResponse<String> multipart(
            String path, String filename, byte[] content, String cookie) throws Exception {
        String boundary = "InkForgeBoundary" + UUID.randomUUID().toString().replace("-", "");
        byte[] prefix = ("--" + boundary + "\r\n"
                        + "Content-Disposition: form-data; name=\"file\"; filename=\""
                        + filename
                        + "\"\r\nContent-Type: text/plain\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8);
        byte[] suffix = ("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8);
        byte[] body = new byte[prefix.length + content.length + suffix.length];
        System.arraycopy(prefix, 0, body, 0, prefix.length);
        System.arraycopy(content, 0, body, prefix.length, content.length);
        System.arraycopy(suffix, 0, body, prefix.length + content.length, suffix.length);
        HttpRequest request = HttpRequest.newBuilder(uri(path))
                .header("Cookie", cookie)
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
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
    static class TestPorts {

        @Bean
        @Primary
        InternalServiceAuthenticator capturingAuthenticator() {
            return (request, body, scope, taskId, runId, novelId, code, message) -> {
                CALLBACK_BODY.set(body.clone());
                return null;
            };
        }

        @Bean
        @Primary
        PortraitRunSubmitter portraitRunSubmitter() {
            return (userId, styleId, taskId, runId, section) -> PortraitDispatchStatus.QUEUED;
        }
    }
}
