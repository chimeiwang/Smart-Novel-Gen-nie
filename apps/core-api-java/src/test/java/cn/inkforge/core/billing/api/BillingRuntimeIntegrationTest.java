package cn.inkforge.core.billing.api;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.TOKENUSAGE;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.billing.domain.ModelGrantCodec;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.serviceauth.ServiceScope;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.KeyPairGenerator;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
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
        classes = {CoreApplication.class, BillingRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BillingRuntimeIntegrationTest {

    private static final AtomicReference<VerifiedCall> VERIFIED = new AtomicReference<>();

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_billing_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", BillingRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java计费运行时测试密钥-长度超过三十二字节-不可用于生产");
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
    private String taskId;

    @AfterEach
    void cleanup() {
        if (userId == null) return;
        database.dsl().deleteFrom(TOKENUSAGE).where(TOKENUSAGE.USERID.eq(userId)).execute();
        database.dsl().deleteFrom(CREDITLEDGER).where(CREDITLEDGER.USERID.eq(userId)).execute();
        if (taskId != null) {
            database.dsl().deleteFrom(WRITINGTASK).where(WRITINGTASK.ID.eq(taskId)).execute();
        }
        if (novelId != null) {
            database.dsl().deleteFrom(CHAPTER).where(CHAPTER.NOVELID.eq(novelId)).execute();
            database.dsl().deleteFrom(NOVEL).where(NOVEL.ID.eq(novelId)).execute();
        }
        database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        VERIFIED.set(null);
    }

    @Test
    void 五个冻结计费接口必须在真实HTTP数据库Redis与模型grant上闭环() throws Exception {
        String username = "billing_"
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
        createWritingTask();

        String authorizeBody = "{  \"userId\":\"" + userId
                + "\",\"novelId\":\"" + novelId
                + "\",\"taskId\":\"" + taskId
                + "\",\"runId\":\"billing-run-1\",\"agentId\":\"写作\""
                + ",\"provider\":\"openai_compatible\",\"model\":\"deepseek-v4-flash\""
                + ",\"estimatedPromptTokens\":10,\"requestedMaxOutputTokens\":512  }";
        HttpResponse<String> authorized = send(
                "POST", "/internal/v1/billing/authorize", authorizeBody, null, true);
        assertThat(authorized.statusCode()).as(authorized.body()).isEqualTo(200);
        JsonNode grant = json.readTree(authorized.body());
        assertThat(grant.get("maxOutputTokens").asInt()).isEqualTo(512);
        assertThat(grant.get("billable").asBoolean()).isTrue();
        assertThat(grant.get("grantToken").asText().split("\\.")).hasSize(3);
        assertThat(VERIFIED.get())
                .isEqualTo(new VerifiedCall(
                        authorizeBody.getBytes(StandardCharsets.UTF_8),
                        ServiceScope.BILLING_AUTHORIZE,
                        taskId,
                        "billing-run-1",
                        novelId));

        Map<String, Object> usage = new LinkedHashMap<>();
        usage.put("requestId", grant.get("requestId").asText());
        usage.put("taskId", taskId);
        usage.put("runId", "billing-run-1");
        usage.put("novelId", novelId);
        usage.put("grantToken", grant.get("grantToken").asText());
        usage.put("promptTokens", 10);
        usage.put("cachedTokens", 2);
        usage.put("promptCacheMissTokens", 8);
        usage.put("completionTokens", 5);
        usage.put("reasoningTokens", 1);
        usage.put("totalTokens", 15);
        String usageBody = json.writeValueAsString(usage);
        HttpResponse<String> charged = send(
                "POST", "/internal/v1/billing/usage", usageBody, null, true);
        assertThat(charged.statusCode()).as(charged.body()).isEqualTo(200);
        JsonNode chargedJson = json.readTree(charged.body());
        assertThat(chargedJson.get("chargedMicros").asText()).isEqualTo("18040");
        assertThat(chargedJson.get("idempotent").asBoolean()).isFalse();
        assertThat(VERIFIED.get())
                .isEqualTo(new VerifiedCall(
                        usageBody.getBytes(StandardCharsets.UTF_8),
                        ServiceScope.BILLING_USAGE_WRITE,
                        taskId,
                        "billing-run-1",
                        novelId));

        HttpResponse<String> replay = send(
                "POST", "/internal/v1/billing/usage", usageBody, null, true);
        assertThat(replay.statusCode()).as(replay.body()).isEqualTo(200);
        assertThat(json.readTree(replay.body()).get("idempotent").asBoolean()).isTrue();
        assertThat(database.dsl().fetchCount(
                        TOKENUSAGE, TOKENUSAGE.REQUESTID.eq(grant.get("requestId").asText())))
                .isEqualTo(1);

        HttpResponse<String> summary = send(
                "GET", "/api/v1/billing/summary", null, cookie, false);
        assertThat(summary.statusCode()).as(summary.body()).isEqualTo(200);
        assertThat(json.readTree(summary.body()).get("recentLedger").toString())
                .contains("ai_charge");

        HttpResponse<String> totalUsage = send(
                "GET", "/api/v1/billing/usage", null, cookie, false);
        assertThat(totalUsage.statusCode()).as(totalUsage.body()).isEqualTo(200);
        assertThat(json.readTree(totalUsage.body()).get("totalUsage").get("totalTokens").asInt())
                .isEqualTo(15);

        HttpResponse<String> taskUsage = send(
                "GET", "/api/v1/billing/usage/tasks/" + taskId, null, cookie, false);
        assertThat(taskUsage.statusCode()).as(taskUsage.body()).isEqualTo(200);
        JsonNode task = json.readTree(taskUsage.body());
        assertThat(task.get("requestCount").asInt()).isEqualTo(1);
        assertThat(task.get("tokenDetailsComplete").asBoolean()).isTrue();
        assertThat(task.get("visibleCompletionTokens").asInt()).isEqualTo(4);
        assertThat(task.get("calls").get(0).get("grantToken")).isNull();
    }

    private void createWritingTask() {
        novelId = "runtime-billing-novel-" + UUID.randomUUID();
        String chapterId = novelId + "-chapter";
        taskId = novelId + "-task";
        LocalDateTime now = LocalDateTime.parse("2026-08-25T00:00:00.000");
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, "计费运行时作品")
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, now)
                .set(NOVEL.UPDATEDAT, now)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, "正文")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, now)
                .set(CHAPTER.UPDATEDAT, now)
                .execute();
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, novelId)
                .set(WRITINGTASK.CHAPTERID, chapterId)
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "[]")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.CREATEDAT, now)
                .set(WRITINGTASK.UPDATEDAT, now)
                .execute();
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
            return java.util.Objects.hash(
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
        @Primary
        ModelGrantCodec testGrantCodec(ObjectMapper objectMapper) throws Exception {
            var keyPair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
            return new ModelGrantCodec(
                    keyPair.getPrivate(), keyPair.getPublic(), objectMapper);
        }
    }
}
