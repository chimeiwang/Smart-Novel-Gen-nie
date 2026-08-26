package cn.inkforge.core.quality.api;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.quality.application.QualityRunSubmitter;
import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import cn.inkforge.core.quality.domain.QualityDispatchStatus;
import cn.inkforge.serviceauth.ServiceScope;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
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
        classes = {CoreApplication.class, QualityRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QualityRuntimeIntegrationTest {

    private static final AtomicReference<VerifiedCall> VERIFIED = new AtomicReference<>();
    private static final CopyOnWriteArrayList<QualityDispatchRecord> SUBMITTED =
            new CopyOnWriteArrayList<>();
    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-25T01:00:00.000");

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_quality_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", QualityRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java质量运行时测试密钥-长度超过三十二字节-不可用于生产");
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

    @Autowired
    private BackgroundTaskManager backgroundTasks;

    private final HttpClient client = HttpClient.newHttpClient();
    private String userId;
    private String novelId;

    @AfterEach
    void cleanup() {
        if (novelId != null) database.dsl().deleteFrom(NOVEL).where(NOVEL.ID.eq(novelId)).execute();
        if (userId != null) database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        VERIFIED.set(null);
        SUBMITTED.clear();
    }

    @Test
    void 六个冻结质量接口必须在真实HTTP认证数据库和补投器上闭环() throws Exception {
        assertThat(backgroundTasks.isReady()).isTrue();
        String username = "quality_"
                + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        HttpResponse<String> registration = send(
                "POST",
                "/api/v1/auth/register",
                "{\"username\":\"" + username
                        + "\",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}",
                null,
                false);
        assertThat(registration.statusCode()).as(registration.body()).isEqualTo(201);
        userId = database.dsl().select(USER.ID)
                .from(USER)
                .where(USER.USERNAME.eq(username))
                .fetchSingle(USER.ID);
        String cookie = registration.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];
        Fixture fixture = fixture();

        HttpResponse<String> fetched = send(
                "GET", "/api/v1/quality-checks/" + fixture.checkId(), null, cookie, false);
        assertThat(fetched.statusCode()).as(fetched.body()).isEqualTo(200);
        JsonNode initial = json.readTree(fetched.body());
        assertThat(initial.get("status").asText()).isEqualTo("pending");

        String skippedBody = json.writeValueAsString(java.util.Map.of(
                "status", "skipped",
                "resetResult", false,
                "expectedUpdatedAt", initial.get("updatedAt").asText()));
        HttpResponse<String> skipped = send(
                "PATCH",
                "/api/v1/quality-checks/" + fixture.checkId(),
                skippedBody,
                cookie,
                false);
        assertThat(skipped.statusCode()).as(skipped.body()).isEqualTo(200);
        assertThat(json.readTree(skipped.body()).get("status").asText()).isEqualTo("skipped");

        String runBody = json.writeValueAsString(java.util.Map.of(
                "clientRequestId", "runtime-quality-run-0001",
                "taskId", fixture.taskId(),
                "message", "检查完整时间线"));
        HttpResponse<String> accepted = send(
                "POST",
                "/api/v1/quality-checks/" + fixture.checkId() + "/run",
                runBody,
                cookie,
                false);
        assertThat(accepted.statusCode()).as(accepted.body()).isEqualTo(202);
        String runId = json.readTree(accepted.body()).get("taskId").asText();
        assertThat(SUBMITTED).anySatisfy(record -> {
            assertThat(record.runId()).isEqualTo(runId);
            assertThat(record.sourceTaskId()).isEqualTo(fixture.taskId());
        });

        String contextBody = json.writeValueAsString(java.util.Map.of(
                "userId", userId,
                "novelId", novelId,
                "taskId", fixture.taskId(),
                "runId", runId,
                "sourceTaskId", fixture.taskId(),
                "message", "检查完整时间线"));
        HttpResponse<String> context = send(
                "POST",
                "/internal/v1/quality-checks/" + fixture.checkId() + "/context",
                contextBody,
                null,
                true);
        assertThat(context.statusCode()).as(context.body()).isEqualTo(200);
        assertThat(json.readTree(context.body()).get("chapterContent").asText())
                .isEqualTo("完整章节正文");
        assertVerified(contextBody, fixture.taskId(), runId);

        String successBody = json.writeValueAsString(java.util.Map.of(
                "userId", userId,
                "novelId", novelId,
                "taskId", fixture.taskId(),
                "runId", runId,
                "scores", java.util.Map.of(
                        "characterConsistency", 81,
                        "worldRuleConsistency", 82,
                        "timelineConsistency", 83,
                        "causalityConsistency", 84,
                        "foreshadowingConsistency", 88),
                "qualityGate", "revise",
                "issues", java.util.List.of(),
                "report", "完整一致性报告",
                "rewriteBrief", "修正时间线"));
        HttpResponse<String> completed = send(
                "PUT",
                "/internal/v1/quality-checks/" + fixture.checkId() + "/success",
                successBody,
                null,
                true);
        assertThat(completed.statusCode()).as(completed.body()).isEqualTo(204);
        assertThat(database.dsl().select(
                                CHAPTERQUALITYCHECK.STATUS,
                                CHAPTERQUALITYCHECK.SCOREOVERALL)
                        .from(CHAPTERQUALITYCHECK)
                        .where(CHAPTERQUALITYCHECK.ID.eq(fixture.checkId()))
                        .fetchSingle())
                .satisfies(row -> {
                    assertThat(row.value1()).isEqualTo(Qualitycheckstatus.completed);
                    assertThat(row.value2()).isEqualTo(84);
                });

        String secondRunBody = json.writeValueAsString(java.util.Map.of(
                "clientRequestId", "runtime-quality-run-0002"));
        HttpResponse<String> secondAccepted = send(
                "POST",
                "/api/v1/quality-checks/" + fixture.checkId() + "/run",
                secondRunBody,
                cookie,
                false);
        assertThat(secondAccepted.statusCode()).as(secondAccepted.body()).isEqualTo(202);
        String secondRunId = json.readTree(secondAccepted.body()).get("taskId").asText();
        String nullableContextBody = """
                {
                  "userId":"%s",
                  "novelId":"%s",
                  "taskId":"%s",
                  "runId":"%s",
                  "sourceTaskId":null,
                  "message":null
                }
                """.formatted(userId, novelId, secondRunId, secondRunId);
        HttpResponse<String> nullableContext = send(
                "POST",
                "/internal/v1/quality-checks/" + fixture.checkId() + "/context",
                nullableContextBody,
                null,
                true);
        assertThat(nullableContext.statusCode()).as(nullableContext.body()).isEqualTo(200);
        assertThat(json.readTree(nullableContext.body()).get("message").asText())
                .isEqualTo("检查本章一致性");
        String failureBody = json.writeValueAsString(java.util.Map.of(
                "userId", userId,
                "novelId", novelId,
                "taskId", secondRunId,
                "runId", secondRunId,
                "message", "模型暂时失败"));
        HttpResponse<String> failed = send(
                "PUT",
                "/internal/v1/quality-checks/" + fixture.checkId() + "/failure",
                failureBody,
                null,
                true);
        assertThat(failed.statusCode()).as(failed.body()).isEqualTo(204);
        assertThat(database.dsl().select(CHAPTERQUALITYCHECK.STATUS)
                        .from(CHAPTERQUALITYCHECK)
                        .where(CHAPTERQUALITYCHECK.ID.eq(fixture.checkId()))
                        .fetchSingle(CHAPTERQUALITYCHECK.STATUS))
                .isEqualTo(Qualitycheckstatus.failed);
    }

    private Fixture fixture() {
        novelId = "runtime-quality-novel-" + UUID.randomUUID();
        String chapterId = novelId + "-chapter";
        String checkId = novelId + "-check";
        String taskId = novelId + "-task";
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, "质量运行时作品")
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, "完整章节正文")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.review)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.ID, checkId)
                .set(CHAPTERQUALITYCHECK.CHAPTERID, chapterId)
                .set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                .set(CHAPTERQUALITYCHECK.TITLE, "一致性终检")
                .set(CHAPTERQUALITYCHECK.CREATEDAT, INITIAL)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, novelId)
                .set(WRITINGTASK.CHAPTERID, chapterId)
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "[]")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.CREATEDAT, INITIAL)
                .set(WRITINGTASK.UPDATEDAT, INITIAL)
                .execute();
        return new Fixture(chapterId, checkId, taskId);
    }

    private void assertVerified(String body, String taskId, String runId) {
        assertThat(VERIFIED.get()).isEqualTo(new VerifiedCall(
                body.getBytes(StandardCharsets.UTF_8),
                ServiceScope.QUALITY_WRITE,
                taskId,
                runId,
                novelId));
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

    private record Fixture(String chapterId, String checkId, String taskId) {}

    private record VerifiedCall(
            byte[] body,
            ServiceScope scope,
            String taskId,
            String runId,
            String novelId) {

        @Override
        public boolean equals(Object other) {
            return other instanceof VerifiedCall value
                    && java.util.Arrays.equals(body, value.body)
                    && scope == value.scope
                    && taskId.equals(value.taskId)
                    && runId.equals(value.runId)
                    && novelId.equals(value.novelId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(
                    java.util.Arrays.hashCode(body), scope, taskId, runId, novelId);
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestPorts {

        @Bean
        @Primary
        InternalServiceAuthenticator capturingAuthenticator() {
            return (request, body, scope, taskId, runId, novelId, code, message) -> {
                VERIFIED.set(new VerifiedCall(body.clone(), scope, taskId, runId, novelId));
                return null;
            };
        }

        @Bean
        QualityRunSubmitter qualityRunSubmitter() {
            return record -> {
                SUBMITTED.add(record);
                return QualityDispatchStatus.QUEUED;
            };
        }
    }
}
