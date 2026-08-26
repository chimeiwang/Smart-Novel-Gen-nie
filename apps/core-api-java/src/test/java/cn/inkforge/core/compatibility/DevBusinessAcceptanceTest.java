package cn.inkforge.core.compatibility;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.writing.application.WritingCommandSubmitter;
import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import org.jooq.impl.DSL;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 在具名开发库上通过真实 Spring HTTP 入口验收代表性业务链路。
 *
 * <p>该测试不会访问 Agent、模型或 Seedance；测试用户和作品使用精确 ID 清理，禁止按前缀扫描删除。
 */
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@EnabledIfEnvironmentVariable(named = "INKFORGE_DEV_DATABASE_URL", matches = ".+")
@SpringBootTest(
        classes = {CoreApplication.class, DevBusinessAcceptanceTest.DevPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DevBusinessAcceptanceTest {

    private static final Path UPLOAD_ROOT = Path.of(
            System.getProperty("java.io.tmpdir"),
            "inkforge-java-dev-acceptance-" + UUID.randomUUID());
    private static final CopyOnWriteArrayList<WritingDispatchRecord> SUBMITTED =
            new CopyOnWriteArrayList<>();

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", DevBusinessAcceptanceTest::devDatabaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost() + ":" + REDIS.getMappedPort(6379) + "/0");
        registry.add("JWT_SECRET", () -> "Java开发库业务验收密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "dev");
        registry.add("TRUSTED_AGENT_CIDRS", () -> "127.0.0.1/32");
        registry.add("UPLOADS_ROOT", UPLOAD_ROOT::toString);
        registry.add("RAG_INDEX_ENABLED", () -> "false");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
        registry.add("VIDEO_DISPATCH_ENABLED", () -> "false");
        registry.add("SEEDANCE_CONFIGURED", () -> "false");
        registry.add("SEEDANCE_ENABLED", () -> "false");
    }

    @LocalServerPort
    private int port;

    @Autowired
    private CoreDatabase database;

    @Autowired
    private ObjectMapper json;

    private final HttpClient client = HttpClient.newHttpClient();
    private final List<String> novelIds = new ArrayList<>();
    private String username;
    private String userId;

    @BeforeEach
    void 写入前必须双重确认具名开发库() {
        SUBMITTED.clear();
        PostgresConnectionSettings parsed = PostgresConnectionSettings.parse(devDatabaseUrl());
        assertThat(parsed.databaseName()).isEqualTo("novelwriterdev");
        assertThat(database.dsl().fetchValue("select current_database()", String.class))
                .isEqualTo("novelwriterdev");
    }

    @AfterEach
    void 按精确标识清理并证明零残留() {
        if (username == null) {
            return;
        }
        String cleanupUserId = userId;
        if (cleanupUserId == null) {
            cleanupUserId = database.dsl().select(USER.ID)
                    .from(USER)
                    .where(USER.USERNAME.eq(username))
                    .fetchOne(USER.ID);
        }
        if (cleanupUserId == null) {
            assertThat(database.dsl().fetchCount(USER, USER.USERNAME.eq(username))).isZero();
            return;
        }

        String exactUserId = cleanupUserId;
        List<String> exactNovelIds = List.copyOf(novelIds);
        database.dsl().transaction(configuration -> {
            var transaction = DSL.using(configuration);
            if (!exactNovelIds.isEmpty()) {
                transaction.deleteFrom(NOVEL)
                        .where(NOVEL.ID.in(exactNovelIds).and(NOVEL.USERID.eq(exactUserId)))
                        .execute();
            }
            transaction.deleteFrom(USER)
                    .where(USER.ID.eq(exactUserId).and(USER.USERNAME.eq(username)))
                    .execute();
        });

        assertThat(database.dsl().fetchCount(
                        USER, USER.ID.eq(exactUserId).or(USER.USERNAME.eq(username))))
                .isZero();
        if (!exactNovelIds.isEmpty()) {
            assertThat(database.dsl().fetchCount(NOVEL, NOVEL.ID.in(exactNovelIds)))
                    .isZero();
        }
    }

    @Test
    void JavaCore必须在真实开发库完成长篇中短篇与视频事实闭环() throws Exception {
        String runId = UUID.randomUUID().toString().replace("-", "").substring(0, 20);
        username = "jacc_" + runId;
        HttpResponse<String> registration = send(
                "POST",
                "/api/v1/auth/register",
                json.writeValueAsString(Map.of(
                        "username", username,
                        "password", "密码1234",
                        "confirmPassword", "密码1234")),
                null);
        expect(201, registration);
        userId = database.dsl().select(USER.ID)
                .from(USER)
                .where(USER.USERNAME.eq(username))
                .fetchSingle(USER.ID);
        String cookie = registration.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];

        JsonNode longNovel = expectJson(
                201,
                send(
                        "POST",
                        "/api/v1/novels",
                        json.writeValueAsString(Map.of(
                                "name", "Java 开发库验收长篇",
                                "summary", "仅用于具名验收并在结束后清理",
                                "storyLengthProfile", "long_serial",
                                "firstChapterGoal", "在雨夜建立人物冲突")),
                        cookie));
        String longNovelId = trackedNovel(longNovel);
        String chapterId = longNovel.get("chapterId").asString();
        JsonNode chapter = expectJson(200, send("GET", "/api/v1/chapters/" + chapterId, null, cookie));
        JsonNode updatedChapter = expectJson(
                200,
                send(
                        "PATCH",
                        "/api/v1/chapters/" + chapterId,
                        json.writeValueAsString(Map.of(
                                "title", "第一章 雨夜来客",
                                "content", "雨幕压住街灯。沈砚停在门后，听见三次克制的敲门声。",
                                "expectedUpdatedAt", chapter.get("updatedAt").asString())),
                        cookie));

        expectJson(
                201,
                send(
                        "POST",
                        "/api/v1/novels/" + longNovelId + "/characters",
                        json.writeValueAsString(Map.of(
                                "clientRequestId", "jacc-character-" + runId,
                                "name", "沈砚",
                                "personality", "谨慎、观察力强，面对威胁时会先压低呼吸。")),
                        cookie));
        expectJson(
                201,
                send(
                        "POST",
                        "/api/v1/novels/" + longNovelId + "/outline-nodes",
                        json.writeValueAsString(Map.of(
                                "clientRequestId", "jacc-outline-node-" + runId,
                                "title", "雨夜来客",
                                "kind", "stage")),
                        cookie));
        expectJson(
                201,
                send(
                        "POST",
                        "/api/v1/novels/" + longNovelId + "/references",
                        json.writeValueAsString(Map.of(
                                "clientRequestId", "jacc-reference-" + runId,
                                "title", "雨夜视觉参考",
                                "type", "note",
                                "content", "冷色街灯、潮湿木门、人物呼吸形成的微弱白雾。")),
                        cookie));

        JsonNode shortNovel = expectJson(
                201,
                send(
                        "POST",
                        "/api/v1/novels",
                        json.writeValueAsString(Map.of(
                                "name", "Java 开发库验收短篇",
                                "storyLengthProfile", "short_medium",
                                "targetTotalWordCount", 12_000,
                                "clientRequestId", "jacc-short-create-" + runId,
                                "sourceKind", "outline",
                                "sourceText", "第一幕：陌生人到访。\n第二幕：门后的人发现旧日线索。")),
                        cookie));
        String shortNovelId = trackedNovel(shortNovel);
        JsonNode preview = expectJson(
                200,
                send(
                        "POST",
                        "/api/v1/novels/" + shortNovelId + "/versions/preview",
                        "{\"documentType\":\"outline\"}",
                        cookie));
        Map<String, Object> versionBody = new LinkedHashMap<>();
        versionBody.put("clientRequestId", "jacc-short-version-" + runId);
        versionBody.put("documentType", "outline");
        versionBody.put("baseVersionId", null);
        versionBody.put("expectedUpdatedAt", preview.get("expectedUpdatedAt").asString());
        versionBody.put("contentHash", preview.get("contentHash").asString());
        versionBody.put("confirmationHash", preview.get("confirmationHash").asString());
        JsonNode appliedOutlineVersion = expectJson(
                200,
                send(
                        "POST",
                        "/api/v1/novels/" + shortNovelId + "/versions",
                        json.writeValueAsString(versionBody),
                        cookie));

        JsonNode shortRun = expectJson(
                202,
                send(
                        "POST",
                        "/api/v1/writing/runs",
                        json.writeValueAsString(Map.of(
                                "clientRequestId", "jacc-short-run-" + runId,
                                "workflow", "short_medium",
                                "novelId", shortNovelId,
                                "operation", "generate_outline",
                                "documentType", "outline",
                                "baseVersionId", appliedOutlineVersion.get("id").asString(),
                                "userInstruction", "生成带转折点的三幕蓝图")),
                        cookie));
        String shortTaskId = shortRun.get("id").asString();
        String shortCommandId = shortRun.get("commandId").asString();
        assertThat(SUBMITTED).anySatisfy(record -> {
            assertThat(record.id()).isEqualTo(shortCommandId);
            assertThat(record.taskId()).isEqualTo(shortTaskId);
            assertThat(record.job().get("operation")).isEqualTo("generate_outline");
        });

        Map<String, Object> candidateResult = new LinkedHashMap<>();
        candidateResult.put("resultType", "short_medium_document");
        candidateResult.put("operation", "generate_outline");
        candidateResult.put("documentType", "outline");
        candidateResult.put("content", "第一幕：来客。\n\n第二幕：旧案重现。\n\n第三幕：门内的人作出选择。");
        candidateResult.put("sourceOutlineVersionId", null);
        expectJson(
                200,
                sendInternal(
                        "PUT",
                        "/internal/v1/writing/runs/" + shortTaskId + "/complete",
                        json.writeValueAsString(Map.of(
                                "protocolVersion", "1.1",
                                "eventId", "jacc-short-complete-" + runId,
                                "jobId", shortCommandId,
                                "runId", shortTaskId,
                                "taskId", shortTaskId,
                                "sequence", 1,
                                "result", candidateResult,
                                "occurredAt", "2026-08-25T08:00:00Z"))));
        JsonNode completedRun = expectJson(
                200,
                send("GET", "/api/v1/writing/runs/" + shortTaskId, null, cookie));
        String candidateId = completedRun.get("candidateVersionId").asString();
        assertThat(candidateId).isNotBlank();
        JsonNode candidate = expectJson(
                200,
                send("GET", "/api/v1/review-artifacts/" + candidateId, null, cookie));
        assertThat(candidate.get("status").asString()).isEqualTo("awaiting_user");
        assertThat(candidate.get("novelId").asString()).isEqualTo(shortNovelId);

        JsonNode project = expectJson(
                201,
                send(
                        "POST",
                        "/api/v1/video/novels/" + longNovelId + "/projects",
                        json.writeValueAsString(Map.of(
                                "title", "第一章影视化验收",
                                "mode", "series",
                                "targetAspectRatio", "9:16",
                                "targetLanguage", "zh-CN")),
                        cookie));
        String projectId = project.get("id").asString();
        JsonNode adaptation = expectJson(
                201,
                send(
                        "POST",
                        "/api/v1/video/projects/" + projectId + "/chapter-adaptations",
                        json.writeValueAsString(Map.of(
                                "chapterId", chapterId,
                                "clientRequestId", "jacc-video-adaptation-" + runId,
                                "expectedChapterUpdatedAt",
                                updatedChapter.get("updatedAt").asString())),
                        cookie));
        assertThat(adaptation.get("novelId").asString()).isEqualTo(longNovelId);
        expectJson(
                200,
                send(
                        "GET",
                        "/api/v1/video/projects/" + projectId + "/chapter-adaptations",
                        null,
                        cookie));
    }

    private String trackedNovel(JsonNode created) {
        String novelId = created.get("novelId").asString();
        novelIds.add(novelId);
        return novelId;
    }

    private JsonNode expectJson(int status, HttpResponse<String> response) {
        expect(status, response);
        return json.readTree(response.body());
    }

    private static void expect(int status, HttpResponse<String> response) {
        assertThat(response.statusCode()).as(response.body()).isEqualTo(status);
    }

    private HttpResponse<String> send(String method, String path, String body, String cookie)
            throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path));
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

    private HttpResponse<String> sendInternal(String method, String path, String body)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + path))
                .header("Authorization", "Bearer dev-acceptance-fake-agent")
                .header("Content-Type", "application/json")
                .method(method, HttpRequest.BodyPublishers.ofString(body))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    private static String devDatabaseUrl() {
        String value = System.getenv("INKFORGE_DEV_DATABASE_URL");
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("缺少 INKFORGE_DEV_DATABASE_URL");
        }
        return value;
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class DevPorts {

        @Bean
        @Primary
        InternalServiceAuthenticator acceptanceAuthenticator() {
            return (request, body, scope, taskId, runId, novelId, code, message) -> null;
        }

        @Bean
        WritingCommandSubmitter acceptanceWritingSubmitter() {
            return new WritingCommandSubmitter() {
                @Override
                public WritingAgentJobStatus submit(WritingDispatchRecord command) {
                    SUBMITTED.add(command);
                    return WritingAgentJobStatus.RUNNING;
                }

                @Override
                public void cancel(WritingDispatchRecord command) {
                    // 验收只覆盖生成与完成，不应触发远端取消。
                }
            };
        }
    }
}
