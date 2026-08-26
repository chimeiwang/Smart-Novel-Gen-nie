package cn.inkforge.core.shortmedium.api;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.shortmedium.application.ShortMediumVersionRepository;
import cn.inkforge.core.shortmedium.application.VersionCreation;
import cn.inkforge.core.shortmedium.domain.DocumentDiffEngine;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersion;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.shortmedium.domain.VersionDocumentBinding;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
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
class ShortMediumRuntimeIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_short_medium_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", ShortMediumRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java中短篇运行时测试密钥-长度超过三十二字节-不可用于生产");
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
    private ShortMediumVersionRepository repository;

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
    void 七个冻结版本接口必须在真实HTTP数据库和Redis环境闭环() throws Exception {
        String username = "short_"
                + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        HttpResponse<String> registration = send(
                "POST",
                "/api/v1/auth/register",
                "{\"username\":\"" + username
                        + "\",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}",
                null);
        assertThat(registration.statusCode()).as(registration.body()).isEqualTo(201);
        userId = database.dsl().select(USER.ID)
                .from(USER)
                .where(USER.USERNAME.eq(username))
                .fetchSingle(USER.ID);
        String cookie = registration.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];

        String firstContent = "第一段😀\n\n完整大纲尾部";
        HttpResponse<String> createdNovel = send(
                "POST",
                "/api/v1/novels",
                json.writeValueAsString(Map.of(
                        "name", "运行时中短篇",
                        "storyLengthProfile", "short_medium",
                        "targetTotalWordCount", 12_000,
                        "clientRequestId", "runtime-short-create-0001",
                        "sourceKind", "outline",
                        "sourceText", firstContent)),
                cookie);
        assertThat(createdNovel.statusCode()).as(createdNovel.body()).isEqualTo(201);
        JsonNode createdNovelJson = json.readTree(createdNovel.body());
        novelId = createdNovelJson.get("novelId").asString();
        String chapterId = createdNovelJson.get("chapterId").asString();

        JsonNode firstPreview = expectJson(
                200,
                send(
                        "POST",
                        "/api/v1/novels/" + novelId + "/versions/preview",
                        "{\"documentType\":\"outline\"}",
                        cookie));
        JsonNode first = expectJson(
                200,
                send(
                        "POST",
                        "/api/v1/novels/" + novelId + "/versions",
                        manualBody("runtime-manual-0001", null, firstPreview),
                        cookie));
        String firstId = first.get("id").asString();
        assertThat(first.get("content").asString()).isEqualTo(firstContent);

        JsonNode listed = expectJson(
                200,
                send(
                        "GET",
                        "/api/v1/novels/" + novelId + "/versions?documentType=outline",
                        null,
                        cookie));
        assertThat(listed.get(0).get("id").asString()).isEqualTo(firstId);
        JsonNode detail = expectJson(
                200,
                send(
                        "GET",
                        "/api/v1/novels/" + novelId + "/versions/" + firstId,
                        null,
                        cookie));
        assertThat(detail.get("content").asString()).isEqualTo(firstContent);

        String secondContent = firstContent + "\n\n第二版不可截断尾部";
        LocalDateTime currentUpdatedAt = database.dsl().select(OUTLINE.UPDATEDAT)
                .from(OUTLINE)
                .where(OUTLINE.NOVELID.eq(novelId))
                .fetchSingle(OUTLINE.UPDATEDAT);
        database.dsl().update(OUTLINE)
                .set(OUTLINE.CONTENT, secondContent)
                .set(OUTLINE.UPDATEDAT, currentUpdatedAt.plusNanos(1_000_000))
                .where(OUTLINE.NOVELID.eq(novelId))
                .execute();
        JsonNode secondPreview = expectJson(
                200,
                send(
                        "POST",
                        "/api/v1/novels/" + novelId + "/versions/preview",
                        "{\"documentType\":\"outline\",\"baseVersionId\":\""
                                + firstId + "\"}",
                        cookie));
        JsonNode second = expectJson(
                200,
                send(
                        "POST",
                        "/api/v1/novels/" + novelId + "/versions",
                        manualBody("runtime-manual-0002", firstId, secondPreview),
                        cookie));
        String secondId = second.get("id").asString();

        JsonNode restoreDiff = expectJson(
                200,
                send(
                        "GET",
                        "/api/v1/novels/" + novelId + "/version-diff?fromVersionId="
                                + secondId + "&toVersionId=" + firstId,
                        null,
                        cookie));
        assertThat(restoreDiff.toString()).contains("第二版不可截断尾部");
        JsonNode restored = expectJson(
                200,
                send(
                        "POST",
                        "/api/v1/novels/" + novelId + "/versions/" + firstId + "/restore",
                        actionBody(
                                "runtime-restore-0001",
                                secondId,
                                restoreDiff.get("confirmationHash").asString()),
                        cookie));
        String restoredId = restored.get("id").asString();
        assertThat(restored.get("restoredFromVersionId").asString()).isEqualTo(firstId);

        String taskId = "runtime-short-task-0001";
        writingTask(taskId, chapterId);
        ShortMediumVersion candidate = candidate(
                restoredId, taskId, "runtime-short-job-0001", "候选大纲😀最终完整尾部");
        JsonNode candidateDetail = expectJson(
                200,
                send(
                        "GET",
                        "/api/v1/novels/" + novelId + "/versions/" + candidate.id(),
                        null,
                        cookie));
        JsonNode adopted = expectJson(
                200,
                send(
                        "POST",
                        "/api/v1/novels/" + novelId + "/versions/" + candidate.id() + "/adopt",
                        actionBody(
                                "runtime-adopt-00001",
                                restoredId,
                                candidateDetail.get("diff").get("confirmationHash").asString()),
                        cookie));
        assertThat(adopted.get("status").asString()).isEqualTo("applied");
        assertThat(database.dsl().select(OUTLINE.CONTENT)
                        .from(OUTLINE)
                        .where(OUTLINE.NOVELID.eq(novelId))
                        .fetchSingle(OUTLINE.CONTENT))
                .isEqualTo("候选大纲😀最终完整尾部");
    }

    private String manualBody(String requestId, String baseVersionId, JsonNode preview) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("clientRequestId", requestId);
        body.put("documentType", "outline");
        body.put("baseVersionId", baseVersionId);
        body.put("expectedUpdatedAt", preview.get("expectedUpdatedAt").asString());
        body.put("contentHash", preview.get("contentHash").asString());
        body.put("confirmationHash", preview.get("confirmationHash").asString());
        return json.writeValueAsString(body);
    }

    private String actionBody(String requestId, String baseVersionId, String confirmationHash) {
        return json.writeValueAsString(Map.of(
                "clientRequestId", requestId,
                "documentType", "outline",
                "baseVersionId", baseVersionId,
                "confirmationHash", confirmationHash));
    }

    private ShortMediumVersion candidate(
            String baseVersionId, String taskId, String jobId, String content) {
        VersionDocumentBinding binding = new VersionDocumentBinding("outline", null);
        ShortMediumVersion base = repository.requireVersion(userId, novelId, baseVersionId);
        return repository.inDocument(userId, novelId, binding, transaction -> {
            ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                    "outline_draft",
                    "outline",
                    transaction.versions().stream()
                                    .mapToInt(ShortMediumVersion::versionNumber)
                                    .max()
                                    .orElse(0)
                            + 1,
                    base.id(),
                    null,
                    "agent",
                    content,
                    ShortMediumText.sha256(content),
                    taskId,
                    jobId,
                    null,
                    "运行时候选",
                    null,
                    null,
                    null,
                    false,
                    null,
                    null,
                    null);
            ShortMediumVersion created = transaction.create(new VersionCreation(
                    payload,
                    DocumentDiffEngine.build(base.content(), content, base.id(), null),
                    "awaiting_user",
                    "运行时候选",
                    "剧情",
                    taskId,
                    jobId));
            return transaction.saveInitialDiff(
                    created,
                    DocumentDiffEngine.bind(
                            created.diff(),
                            "outline",
                            null,
                            base.id(),
                            base.payload().contentHash(),
                            created.id()));
        });
    }

    private void writingTask(String taskId, String chapterId) {
        LocalDateTime now = LocalDateTime.parse("2026-08-25T00:00:00.000");
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, novelId)
                .set(WRITINGTASK.CHAPTERID, chapterId)
                .set(WRITINGTASK.TARGETWORDCOUNT, 12_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "[]")
                .set(WRITINGTASK.PHASE, Writingtaskphase.waiting_call)
                .set(WRITINGTASK.CREATEDAT, now)
                .set(WRITINGTASK.UPDATEDAT, now)
                .execute();
    }

    private JsonNode expectJson(int status, HttpResponse<String> response) {
        assertThat(response.statusCode()).as(response.body()).isEqualTo(status);
        return json.readTree(response.body());
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
