package cn.inkforge.core.reviews.api;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.domain.ReviewArtifactRules;
import cn.inkforge.serviceauth.ServiceScope;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
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
        classes = {CoreApplication.class, ReviewRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReviewRuntimeIntegrationTest {

    private static final AtomicReference<VerifiedCall> VERIFIED = new AtomicReference<>();
    private static final LocalDateTime INITIAL = LocalDateTime.parse("2026-08-25T01:00:00.000");

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_review_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", ReviewRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java审核运行时测试密钥-长度超过三十二字节-不可用于生产");
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
        if (novelId != null) database.dsl().deleteFrom(NOVEL).where(NOVEL.ID.eq(novelId)).execute();
        if (userId != null) database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        VERIFIED.set(null);
    }

    @Test
    void 七个冻结审核接口必须在真实HTTP认证和数据库上闭环() throws Exception {
        String username = "review_"
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

        Map<String, Object> create = new LinkedHashMap<>();
        create.put("runId", "runtime-review-run-1");
        create.put("taskId", fixture.taskId());
        create.put("novelId", novelId);
        create.put("jobId", fixture.jobId());
        create.put("chapterId", fixture.chapterId());
        create.put("artifactKey", "chapter:runtime-review");
        create.put("kind", "chapter_draft");
        create.put("status", "under_review");
        create.put("title", "章节草案");
        create.put("summary", "待复审");
        create.put("payload", Map.of("kind", "chapter_draft", "content", "模型正文"));
        create.put("createdByAgent", "写作");
        String createBody = json.writeValueAsString(create);
        HttpResponse<String> created = send(
                "POST", "/internal/v1/review-artifacts", createBody, null, true);
        assertThat(created.statusCode()).as(created.body()).isEqualTo(200);
        JsonNode artifact = json.readTree(created.body());
        String artifactId = artifact.get("id").asText();
        assertThat(artifact.get("sourceBindingStatus").asText()).isEqualTo("verified");
        assertVerified(createBody, fixture, ServiceScope.TOOL_WRITE);

        Map<String, Object> evaluation = new LinkedHashMap<>();
        evaluation.put("runId", "runtime-review-run-1");
        evaluation.put("taskId", fixture.taskId());
        evaluation.put("novelId", novelId);
        evaluation.put("jobId", fixture.jobId());
        evaluation.put("revision", 1);
        evaluation.put("evaluatorAgent", "编辑");
        evaluation.put("verdict", "pass");
        evaluation.put("summary", "复审通过");
        String evaluationBody = json.writeValueAsString(evaluation);
        HttpResponse<String> evaluated = send(
                "POST",
                "/internal/v1/review-artifacts/" + artifactId + "/evaluations",
                evaluationBody,
                null,
                true);
        assertThat(evaluated.statusCode()).as(evaluated.body()).isEqualTo(200);
        assertThat(json.readTree(evaluated.body()).get("evaluations").size()).isEqualTo(1);

        Map<String, Object> quarantine = Map.of(
                "runId", "runtime-review-run-1",
                "taskId", fixture.taskId(),
                "novelId", novelId,
                "jobId", fixture.jobId());
        String quarantineBody = json.writeValueAsString(quarantine);
        HttpResponse<String> quarantined = send(
                "POST",
                "/internal/v1/review-artifacts/" + artifactId
                        + "/awaiting-user-after-conflict",
                quarantineBody,
                null,
                true);
        assertThat(quarantined.statusCode()).as(quarantined.body()).isEqualTo(200);
        assertThat(json.readTree(quarantined.body()).get("status").asText())
                .isEqualTo("awaiting_user");

        String query = "/api/v1/review-artifacts?novelId="
                + URLEncoder.encode(novelId, StandardCharsets.UTF_8);
        HttpResponse<String> listed = send("GET", query, null, cookie, false);
        assertThat(listed.statusCode()).as(listed.body()).isEqualTo(200);
        assertThat(json.readTree(listed.body()).get("items").size()).isEqualTo(1);

        HttpResponse<String> fetched = send(
                "GET", "/api/v1/review-artifacts/" + artifactId, null, cookie, false);
        assertThat(fetched.statusCode()).as(fetched.body()).isEqualTo(200);
        assertThat(json.readTree(fetched.body()).get("id").asText()).isEqualTo(artifactId);

        HttpResponse<String> taskArtifact = send(
                "GET",
                "/api/v1/writing/tasks/" + fixture.taskId() + "/artifact",
                null,
                cookie,
                false);
        assertThat(taskArtifact.statusCode()).as(taskArtifact.body()).isEqualTo(200);
        assertThat(json.readTree(taskArtifact.body()).get("id").asText()).isEqualTo(artifactId);

        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .where(WRITINGRUNCOMMAND.ID.eq(fixture.jobId()))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.awaiting_user_review)
                .where(WRITINGTASK.ID.eq(fixture.taskId()))
                .execute();
        String decisionBody = json.writeValueAsString(Map.of(
                "clientRequestId", "runtime-review-decision-0001",
                "expectedRevision", 1,
                "decision", "approve",
                "editedContent", "用户确认正文",
                "userMessage", "继续"));
        HttpResponse<String> decided = send(
                "POST",
                "/api/v1/review-artifacts/" + artifactId + "/decision",
                decisionBody,
                cookie,
                false);
        assertThat(decided.statusCode()).as(decided.body()).isEqualTo(202);
        JsonNode accepted = json.readTree(decided.body());
        assertThat(accepted.get("status").asText()).isEqualTo("pending");
        assertThat(accepted.get("savedCount").asInt()).isEqualTo(1);
        assertThat(database.dsl().select(CHAPTER.CONTENT)
                        .from(CHAPTER)
                        .where(CHAPTER.ID.eq(fixture.chapterId()))
                        .fetchSingle(CHAPTER.CONTENT))
                .isEqualTo("用户确认正文");
        assertThat(database.dsl().select(REVIEWARTIFACT.STATUS)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(artifactId))
                        .fetchSingle(REVIEWARTIFACT.STATUS)
                        .getLiteral())
                .isEqualTo("applied");

        String updatesTaskId = novelId + "-updates-task";
        String updatesJobId = novelId + "-updates-job";
        insertTask(fixture.chapterId(), updatesTaskId, updatesJobId);
        Map<String, Object> updateItem = Map.of(
                "action", "create",
                "clientRequestId", "runtime-character-create-0001",
                "name", "林砚");
        Map<String, Object> updatesCreate = new LinkedHashMap<>();
        updatesCreate.put("runId", "runtime-review-run-2");
        updatesCreate.put("taskId", updatesTaskId);
        updatesCreate.put("novelId", novelId);
        updatesCreate.put("jobId", updatesJobId);
        updatesCreate.put("chapterId", fixture.chapterId());
        updatesCreate.put("artifactKey", "agent-updates:runtime-review");
        updatesCreate.put("kind", "agent_updates");
        updatesCreate.put("status", "awaiting_user");
        updatesCreate.put("payload", Map.of(
                "kind", "agent_updates",
                "updates", Map.of("characters", List.of(updateItem))));
        updatesCreate.put("createdByAgent", "写作");
        HttpResponse<String> updatesArtifact = send(
                "POST",
                "/internal/v1/review-artifacts",
                json.writeValueAsString(updatesCreate),
                null,
                true);
        assertThat(updatesArtifact.statusCode()).as(updatesArtifact.body()).isEqualTo(200);
        String updatesArtifactId = json.readTree(updatesArtifact.body()).get("id").asText();
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .where(WRITINGRUNCOMMAND.ID.eq(updatesJobId))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.awaiting_user_review)
                .where(WRITINGTASK.ID.eq(updatesTaskId))
                .execute();
        String updatesDecision = json.writeValueAsString(Map.of(
                "clientRequestId", "runtime-updates-decision-0001",
                "expectedRevision", 1,
                "decision", "approve",
                "selectedUpdateRefs", List.of(Map.of("section", "characters", "index", 0))));
        HttpResponse<String> updatesAccepted = send(
                "POST",
                "/api/v1/review-artifacts/" + updatesArtifactId + "/decision",
                updatesDecision,
                cookie,
                false);
        assertThat(updatesAccepted.statusCode()).as(updatesAccepted.body()).isEqualTo(202);
        assertThat(json.readTree(updatesAccepted.body()).get("savedCount").asInt()).isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        CHARACTER,
                        CHARACTER.NOVELID.eq(novelId).and(CHARACTER.NAME.eq("林砚"))))
                .isEqualTo(1);
    }

    private Fixture fixture() {
        novelId = "runtime-review-novel-" + UUID.randomUUID();
        String chapterId = novelId + "-chapter";
        String taskId = novelId + "-task";
        String jobId = novelId + "-job";
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, "审核运行时作品")
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, "旧正文")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
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
        Map<String, Object> binding = new LinkedHashMap<>();
        binding.put("resourceType", "chapter");
        binding.put("resourceId", chapterId);
        binding.put("exists", true);
        binding.put("updatedAt", DatabaseTimestamp.api(INITIAL).toString());
        binding.put("contentSha256", ReviewArtifactRules.sha256("旧正文"));
        binding.put("revision", null);
        binding.put("absenceSentinel", null);
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, jobId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, json.writeValueAsString(Map.of(
                        "job", Map.of(
                                "workflow", "long_serial",
                                "operation", "write_chapter",
                                "sourceBindings", List.of(binding)))))
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, novelId + "-start-request")
                .set(WRITINGRUNCOMMAND.STATUS, "processing")
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, INITIAL)
                .set(WRITINGRUNCOMMAND.CREATEDAT, INITIAL)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, INITIAL)
                .execute();
        return new Fixture(chapterId, taskId, jobId);
    }

    private void insertTask(String chapterId, String taskId, String jobId) {
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
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, jobId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, "{\"job\":{}}")
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, taskId + "-start-request")
                .set(WRITINGRUNCOMMAND.STATUS, "processing")
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, INITIAL)
                .set(WRITINGRUNCOMMAND.CREATEDAT, INITIAL)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, INITIAL)
                .execute();
    }

    private void assertVerified(
            String body, Fixture fixture, ServiceScope scope) {
        assertThat(VERIFIED.get()).isEqualTo(new VerifiedCall(
                body.getBytes(StandardCharsets.UTF_8),
                scope,
                fixture.taskId(),
                "runtime-review-run-1",
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

    private record Fixture(String chapterId, String taskId, String jobId) {}

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
    }
}
