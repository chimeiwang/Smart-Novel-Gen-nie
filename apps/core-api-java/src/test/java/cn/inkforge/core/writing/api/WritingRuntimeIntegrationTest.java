package cn.inkforge.core.writing.api;

import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.DurableAgentSchemaGate;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.workflows.api.WorkflowsController;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowCallbackRepository;
import cn.inkforge.core.workflows.application.WorkflowCancellationReconciler;
import cn.inkforge.core.workflows.application.WorkflowDispatchRepository;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository;
import cn.inkforge.core.workflows.application.WorkflowEventTailObserver;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationRepository;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationService;
import cn.inkforge.core.workflows.application.WorkflowStartRepository;
import cn.inkforge.core.workflows.application.WorkflowStepDispatcher;
import cn.inkforge.core.writing.application.LongSerialDurableRunStarter;
import cn.inkforge.core.writing.application.WritingCallbackService;
import cn.inkforge.core.writing.application.WritingCommandSubmitter;
import cn.inkforge.core.writing.application.WritingEventStreamService;
import cn.inkforge.core.writing.application.WritingRunCommandDispatcher;
import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;
import cn.inkforge.serviceauth.ServiceScope;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
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
        classes = {CoreApplication.class, WritingRuntimeIntegrationTest.TestPorts.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WritingRuntimeIntegrationTest {

    private static final CopyOnWriteArrayList<WritingDispatchRecord> SUBMITTED =
            new CopyOnWriteArrayList<>();
    private static final CopyOnWriteArrayList<WritingDispatchRecord> CANCELLED =
            new CopyOnWriteArrayList<>();
    private static final CopyOnWriteArrayList<VerifiedCall> VERIFIED =
            new CopyOnWriteArrayList<>();

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_runtime")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", WritingRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "Java写作运行时测试密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("TRUSTED_AGENT_CIDRS", () -> "127.0.0.1/32");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
        registry.add("DURABLE_AGENT_EXECUTION_SCHEMA_READY", () -> "false");
        registry.add("DURABLE_AGENT_EXECUTION_ROUTE_MODE", () -> "off");
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
    private WritingRunCommandDispatcher dispatcher;

    @Autowired
    private WritingCallbackService callbacks;

    @Autowired
    private WritingEventStreamService streams;

    @Autowired
    private ApplicationContext context;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private String userId;

    @AfterEach
    void cleanup() {
        if (userId != null) {
            database.dsl().deleteFrom(USER).where(USER.ID.eq(userId)).execute();
        }
        SUBMITTED.clear();
        CANCELLED.clear();
        VERIFIED.clear();
    }

    @Test
    void 写作会话运行工具回调和SSE必须在真实HTTP数据库与Redis上闭环() throws Exception {
        assertThat(dispatcher).isNotNull();
        assertThat(callbacks).isNotNull();
        assertThat(streams).isNotNull();
        assertThat(context.getBeansOfType(DurableWorkflowService.class)).isEmpty();
        assertThat(context.getBeansOfType(DurableAgentSchemaGate.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowStartRepository.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowCallbackRepository.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowDispatchRepository.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowEventStreamRepository.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowEventTailObserver.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowRunCancellationRepository.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowRunCancellationService.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowCancellationReconciler.class)).isEmpty();
        assertThat(context.getBeansOfType(
                                cn.inkforge.core.workflows.application.WorkflowEventStreamService
                                        .class))
                .isEmpty();
        assertThat(context.getBeansOfType(WorkflowStepDispatcher.class)).isEmpty();
        assertThat(context.getBeansOfType(LongSerialDurableRunStarter.class)).isEmpty();
        assertThat(context.getBeansOfType(WorkflowsController.class)).isEmpty();
        assertThat(context.containsBean("workflowCancellationReconcilerStarter")).isFalse();
        assertThat(context.containsBean("workflowStepDispatcherStarter")).isFalse();
        HttpResponse<String> disabledV2Callback = send(
                "PUT",
                "/internal/v1/workflow-runs/run-disabled/steps/step-disabled/progress",
                "{}",
                null,
                false);
        assertThat(disabledV2Callback.statusCode()).as(disabledV2Callback.body()).isEqualTo(404);
        HttpResponse<String> readiness = send(
                "GET", "/api/v1/health/ready", null, null, false);
        assertThat(readiness.statusCode()).as(readiness.body()).isEqualTo(200);
        assertThat(readiness.body()).contains("\"database\":\"ok\"");

        String username = "writing_"
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

        HttpResponse<String> novel = send(
                "POST",
                "/api/v1/novels",
                json.writeValueAsString(Map.of(
                        "name", "写作运行时长篇",
                        "storyLengthProfile", "long_serial",
                        "firstChapterGoal", "检查第一章完整性")),
                cookie,
                false);
        assertThat(novel.statusCode()).as(novel.body()).isEqualTo(201);
        String novelId = json.readTree(novel.body()).get("novelId").asText();
        String chapterId = json.readTree(novel.body()).get("chapterId").asText();

        HttpResponse<String> session = send(
                "POST",
                "/api/v1/writing/sessions",
                json.writeValueAsString(Map.of(
                        "novelId", novelId,
                        "chapterId", chapterId,
                        "title", "第一章复审")),
                cookie,
                false);
        assertThat(session.statusCode()).as(session.body()).isEqualTo(201);
        String sessionId = json.readTree(session.body()).get("id").asText();

        HttpResponse<String> message = send(
                "POST",
                "/api/v1/writing/sessions/" + sessionId + "/messages",
                "{\"role\":\"user\",\"content\":\"先阅读完整章节\"}",
                cookie,
                false);
        assertThat(message.statusCode()).as(message.body()).isEqualTo(201);
        assertThat(send(
                                "GET",
                                "/api/v1/writing/sessions?novelId=" + novelId,
                                null,
                                cookie,
                                false)
                        .statusCode())
                .isEqualTo(200);
        assertThat(send(
                                "GET",
                                "/api/v1/writing/sessions/" + sessionId,
                                null,
                                cookie,
                                false)
                        .body())
                .contains("先阅读完整章节");
        HttpResponse<String> renamed = send(
                "PATCH",
                "/api/v1/writing/sessions/" + sessionId,
                "{\"title\":\"完整复审会话\"}",
                cookie,
                false);
        assertThat(renamed.statusCode()).as(renamed.body()).isEqualTo(200);
        assertThat(json.readTree(renamed.body()).get("title").asText()).isEqualTo("完整复审会话");

        HttpResponse<String> disposable = send(
                "POST",
                "/api/v1/writing/sessions",
                json.writeValueAsString(Map.of("novelId", novelId, "chapterId", chapterId)),
                cookie,
                false);
        String disposableId = json.readTree(disposable.body()).get("id").asText();
        assertThat(send(
                                "DELETE",
                                "/api/v1/writing/sessions/" + disposableId,
                                null,
                                cookie,
                                false)
                        .statusCode())
                .isEqualTo(204);

        JsonNode firstRun = startReviewRun(
                novelId,
                chapterId,
                sessionId,
                "runtime-writing-start-0001",
                "完整复审第一章",
                cookie);
        String taskId = firstRun.get("id").asText();
        String commandId = firstRun.get("commandId").asText();
        assertThat(firstRun.get("engineVersion").asInt()).isEqualTo(1);
        assertThat(firstRun.get("runId").asText()).isEqualTo(taskId);
        assertThat(firstRun.get("taskId").asText()).isEqualTo(taskId);
        assertThat(SUBMITTED).anySatisfy(record -> {
            assertThat(record.id()).isEqualTo(commandId);
            assertThat(record.taskId()).isEqualTo(taskId);
            assertThat(record.job().get("operation")).isEqualTo("review_chapter");
        });

        HttpResponse<String> status = send(
                "GET", "/api/v1/writing/runs/" + taskId, null, cookie, false);
        assertThat(status.statusCode()).as(status.body()).isEqualTo(200);
        JsonNode statusBody = json.readTree(status.body());
        assertThat(statusBody.get("engineVersion").asInt()).isEqualTo(1);
        assertThat(statusBody.get("runId").asText()).isEqualTo(taskId);
        assertThat(statusBody.get("taskId").asText()).isEqualTo(taskId);
        assertThat(statusBody.get("operation").asText())
                .isEqualTo("review_chapter");
        HttpResponse<String> listed = send(
                "GET", "/api/v1/writing/runs?novelId=" + novelId, null, cookie, false);
        assertThat(listed.statusCode()).as(listed.body()).isEqualTo(200);
        JsonNode listedItem = json.readTree(listed.body()).path("items").get(0);
        assertThat(listedItem.get("engineVersion").asInt()).isEqualTo(1);
        assertThat(listedItem.get("runId").asText()).isEqualTo(taskId);
        assertThat(listedItem.get("taskId").asText()).isEqualTo(taskId);

        String toolBody = json.writeValueAsString(Map.of(
                "userId", userId,
                "novelId", novelId,
                "taskId", taskId,
                "runId", taskId,
                "jobId", commandId,
                "agentId", "编辑",
                "arguments", Map.of()));
        HttpResponse<String> context = send(
                "POST",
                "/internal/v1/tools/get_writing_context",
                toolBody,
                null,
                true);
        assertThat(context.statusCode()).as(context.body()).isEqualTo(200);
        assertThat(json.readTree(context.body())
                        .path("result")
                        .path("planning")
                        .path("taskId")
                        .asText())
                .isEqualTo(taskId);

        String eventBody = json.writeValueAsString(Map.of(
                "protocolVersion", "1.1",
                "eventId", "runtime-writing-event-1",
                "jobId", commandId,
                "runId", taskId,
                "taskId", taskId,
                "sequence", 1,
                "event", "agent_progress",
                "data", Map.of("agentId", "编辑", "message", "正在复审"),
                "occurredAt", "2026-08-25T04:00:00Z"));
        HttpResponse<String> event = send(
                "POST",
                "/internal/v1/writing/runs/" + taskId + "/events",
                eventBody,
                null,
                true);
        assertThat(event.statusCode()).as(event.body()).isEqualTo(200);

        String completionBody = json.writeValueAsString(Map.of(
                "protocolVersion", "1.1",
                "eventId", "runtime-writing-complete-2",
                "jobId", commandId,
                "runId", taskId,
                "taskId", taskId,
                "sequence", 2,
                "result", Map.of(
                        "finalResponse", "章节复审通过",
                        "agentOutputs", Map.of("编辑", "完整复审意见")),
                "occurredAt", "2026-08-25T04:00:01Z"));
        HttpResponse<String> completed = send(
                "PUT",
                "/internal/v1/writing/runs/" + taskId + "/complete",
                completionBody,
                null,
                true);
        assertThat(completed.statusCode()).as(completed.body()).isEqualTo(200);
        assertThat(json.readTree(completed.body()).get("disposition").asText())
                .isEqualTo("applied");

        HttpResponse<String> terminal = send(
                "GET", "/api/v1/writing/runs/" + taskId, null, cookie, false);
        assertThat(json.readTree(terminal.body()).path("outcome").path("state").asText())
                .isEqualTo("succeeded");
        HttpResponse<String> sse = sendSse(
                "/api/v1/writing/runs/" + taskId + "/events", cookie);
        assertThat(sse.statusCode()).as(sse.body()).isEqualTo(200);
        assertThat(sse.headers().firstValue("content-type").orElse(""))
                .startsWith("text/event-stream");
        assertThat(sse.body())
                .contains("event: run_outcome")
                .contains("\"state\":\"succeeded\"")
                .contains("agent_progress");

        JsonNode secondRun = startReviewRun(
                novelId,
                chapterId,
                sessionId,
                "runtime-writing-start-0002",
                "再次复审第一章",
                cookie);
        String secondTaskId = secondRun.get("id").asText();
        String secondCommandId = secondRun.get("commandId").asText();
        LocalDateTime now = LocalDateTime.parse("2026-08-25T04:10:00.000");
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .set(WRITINGRUNCOMMAND.COMPLETEDAT, now)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, now)
                .where(WRITINGRUNCOMMAND.ID.eq(secondCommandId))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.UPDATEDAT, now)
                .where(WRITINGTASK.ID.eq(secondTaskId))
                .execute();

        HttpResponse<String> resumed = send(
                "POST",
                "/api/v1/writing/runs/" + secondTaskId + "/resume",
                json.writeValueAsString(Map.of(
                        "clientRequestId", "runtime-writing-resume-0001",
                        "writingSessionId", sessionId,
                        "userMessage", "继续检查人物动机")),
                cookie,
                false);
        assertThat(resumed.statusCode()).as(resumed.body()).isEqualTo(202);
        JsonNode resumedBody = json.readTree(resumed.body());
        assertThat(resumedBody.get("engineVersion").asInt()).isEqualTo(1);
        assertThat(resumedBody.get("runId").asText()).isEqualTo(secondTaskId);
        assertThat(resumedBody.get("taskId").asText()).isEqualTo(secondTaskId);
        String resumeCommandId = resumedBody.get("commandId").asText();
        assertThat(SUBMITTED).anySatisfy(record -> assertThat(record.id())
                .isEqualTo(resumeCommandId));

        HttpResponse<String> cancelled = send(
                "POST",
                "/api/v1/writing/runs/" + secondTaskId + "/cancel",
                "{\"clientRequestId\":\"runtime-writing-cancel-0001\"}",
                cookie,
                false);
        assertThat(cancelled.statusCode()).as(cancelled.body()).isEqualTo(202);
        JsonNode cancelledBody = json.readTree(cancelled.body());
        assertThat(cancelledBody.get("engineVersion").asInt()).isEqualTo(1);
        assertThat(cancelledBody.get("runId").asText()).isEqualTo(secondTaskId);
        assertThat(cancelledBody.get("taskId").asText()).isEqualTo(secondTaskId);
        assertThat(CANCELLED).anySatisfy(record -> assertThat(record.taskId())
                .isEqualTo(secondTaskId));
        HttpResponse<String> cancelledStatus = send(
                "GET", "/api/v1/writing/runs/" + secondTaskId, null, cookie, false);
        assertThat(json.readTree(cancelledStatus.body())
                        .path("outcome")
                        .path("state")
                        .asText())
                .isEqualTo("cancelled");

        assertThat(VERIFIED).anySatisfy(call -> {
            assertThat(call.scope()).isEqualTo(ServiceScope.TOOL_READ);
            assertThat(call.body()).isEqualTo(toolBody.getBytes(StandardCharsets.UTF_8));
        });
        assertThat(VERIFIED).anySatisfy(call -> {
            assertThat(call.scope()).isEqualTo(ServiceScope.CALLBACK_EVENT);
            assertThat(call.taskId()).isEqualTo(taskId);
            assertThat(call.runId()).isEqualTo(taskId);
        });
        assertThat(VERIFIED).anySatisfy(call ->
                assertThat(call.scope()).isEqualTo(ServiceScope.CALLBACK_COMPLETE));
    }

    private JsonNode startReviewRun(
            String novelId,
            String chapterId,
            String sessionId,
            String clientRequestId,
            String instruction,
            String cookie) throws Exception {
        String body = json.writeValueAsString(Map.of(
                "workflow", "long_serial",
                "novelId", novelId,
                "chapterId", chapterId,
                "writingSessionId", sessionId,
                "clientRequestId", clientRequestId,
                "operation", "review_chapter",
                "target", Map.of("type", "chapter", "id", chapterId),
                "scope", Map.of("kind", "chapter", "chapterId", chapterId),
                "targetWordCount", 4_000,
                "userInstruction", instruction));
        HttpResponse<String> response = send(
                "POST", "/api/v1/writing/runs", body, cookie, false);
        assertThat(response.statusCode()).as(response.body()).isEqualTo(202);
        return json.readTree(response.body());
    }

    private HttpResponse<String> send(
            String method,
            String path,
            String body,
            String cookie,
            boolean internal) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path))
                .timeout(Duration.ofSeconds(15));
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

    private HttpResponse<String> sendSse(String path, String cookie) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri(path))
                .timeout(Duration.ofSeconds(15))
                .header("Cookie", cookie)
                .header("Accept", "text/event-stream")
                .GET()
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
                    && Objects.equals(taskId, value.taskId)
                    && Objects.equals(runId, value.runId)
                    && Objects.equals(novelId, value.novelId);
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
                VERIFIED.add(new VerifiedCall(body.clone(), scope, taskId, runId, novelId));
                return null;
            };
        }

        @Bean
        WritingCommandSubmitter writingCommandSubmitter() {
            return new WritingCommandSubmitter() {
                @Override
                public WritingAgentJobStatus submit(WritingDispatchRecord command) {
                    SUBMITTED.add(command);
                    return WritingAgentJobStatus.RUNNING;
                }

                @Override
                public void cancel(WritingDispatchRecord command) {
                    CANCELLED.add(command);
                }
            };
        }
    }
}
