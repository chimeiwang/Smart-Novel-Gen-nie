package cn.inkforge.core.workflows.infrastructure;

import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.contracts.api.RunSnapshot;
import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.identity.api.IdentityController;
import cn.inkforge.core.identity.domain.InvalidSessionTokenException;
import cn.inkforge.core.identity.domain.SessionTokens;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.application.WorkflowDispatchRepository;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository;
import cn.inkforge.core.workflows.application.WorkflowEventTailObserver;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationService;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.application.WorkflowStartRepository;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.writing.application.WritingEventStore;
import cn.inkforge.core.writing.application.WritingEventStreamService;
import cn.inkforge.core.writing.domain.WritingEvent;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.util.ReflectionTestUtils;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@SpringBootTest(
        classes = {
            CoreApplication.class,
            WorkflowV2SseHttpIntegrationTest.TestIdentityConfiguration.class
        },
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WorkflowV2SseHttpIntegrationTest {

    private static final Duration BOUNDARY_TIMEOUT = Duration.ofSeconds(5);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password")
                    .withCopyFileToContainer(
                            MountableFile.forClasspathResource(
                                    "db/novelwriterdev-schema.sql", 0644),
                            "/docker-entrypoint-initdb.d/01-schema.sql")
                    .withCopyFileToContainer(
                            MountableFile.forClasspathResource(
                                    "migrations/20260831_durable_agent_execution.sql", 0644),
                            "/docker-entrypoint-initdb.d/02-durable-agent.sql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", WorkflowV2SseHttpIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "false");
        registry.add("JWT_SECRET", () -> "Java-V2-SSE-真实HTTP测试密钥-长度超过三十二字节");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("TRUSTED_AGENT_CIDRS", () -> "127.0.0.1/32");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "false");
        registry.add("DURABLE_AGENT_EXECUTION_SCHEMA_READY", () -> "true");
        registry.add("DURABLE_AGENT_EXECUTION_ROUTE_MODE", () -> "off");
    }

    @LocalServerPort
    private int port;

    @Autowired
    private CoreDatabase database;

    @Autowired
    private SessionTokens sessionTokens;

    @Autowired
    private WorkflowStartRepository starts;

    @Autowired
    private WorkflowDispatchRepository dispatches;

    @Autowired
    private WorkflowRunCancellationService cancellations;

    @Autowired
    private WorkflowEventStreamRepository eventStreams;

    @Autowired
    private WorkflowEventTailObserver observer;

    @Autowired
    private WritingEventStreamService writingStreams;

    @Autowired
    private ExecutionRegistry registry;

    @Autowired
    private ObjectMapper json;

    @Test
    @Order(1)
    void 未认证与非归属用户必须在建立V2事件流前稳定拒绝() throws Exception {
        HttpClient client = client();
        HttpResponse<Void> unauthenticated = client.send(
                request("not-a-run", null, null),
                HttpResponse.BodyHandlers.discarding());
        assertThat(unauthenticated.statusCode()).isEqualTo(401);

        Fixture owner = fixture();
        RunningRun run = runningRun(owner);
        try {
            String otherUserId = "v2-sse-other-"
                    + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
            insertUser(otherUserId, now());
            HttpResponse<Void> forbidden = client.send(
                    request(run.runId(), otherUserId, null),
                    HttpResponse.BodyHandlers.discarding());
            assertThat(forbidden.statusCode()).isEqualTo(403);
        } finally {
            cancel(owner, run);
        }
    }

    @Test
    @Order(2)
    void 运行中V2首个Send必须立即提交EventStream响应头和逐字Snapshot() throws Exception {
        Fixture fixture = fixture();
        RunningRun run = runningRun(fixture);
        HttpResponse<InputStream> response = null;
        long started = System.nanoTime();
        try {
            response = client().send(
                    request(run.runId(), fixture.userId(), null),
                    HttpResponse.BodyHandlers.ofInputStream());
            long headersMillis = elapsedMillis(started);
            assertThat(response.statusCode()).isEqualTo(200);
            assertThat(response.headers().firstValue("content-type"))
                    .contains(MediaType.TEXT_EVENT_STREAM_VALUE);

            String raw = readRawFrame(response.body(), "V2 run_snapshot 首帧");
            long firstFrameMillis = elapsedMillis(started);
            RunSnapshot snapshot = eventStreams
                    .readSnapshot(fixture.userId(), run.runId())
                    .orElseThrow()
                    .frame();
            assertThat(raw).isEqualTo(formatSnapshot(snapshot));
            SseFrame frame = parseFrame(raw);
            assertThat(frame.event()).isEqualTo("run_snapshot");
            assertThat(frame.id()).isEqualTo(Long.toString(run.baseSequence()));
            JsonNode data = json.readTree(frame.data());
            assertThat(data.path("protocolVersion").asString()).isEqualTo("2.0");
            assertThat(data.path("engineVersion").asInt()).isEqualTo(2);
            assertThat(data.path("runId").asString()).isEqualTo(run.runId());
            assertThat(data.path("snapshot").path("status").asString())
                    .isEqualTo("running");
            assertThat(headersMillis).isLessThan(BOUNDARY_TIMEOUT.toMillis());
            assertThat(firstFrameMillis).isLessThan(BOUNDARY_TIMEOUT.toMillis());
        } finally {
            close(response);
            try {
                cancel(fixture, run);
            } finally {
                observer.wake();
                awaitNoConnection();
            }
        }
    }

    @Test
    @Order(3)
    void 运行中V2后续非终态Event的每次Send也必须立即Flush() throws Exception {
        Fixture fixture = fixture();
        RunningRun run = runningRun(fixture);
        HttpResponse<InputStream> response = null;
        try {
            response = client().send(
                    request(run.runId(), fixture.userId(), null),
                    HttpResponse.BodyHandlers.ofInputStream());
            assertThat(response.statusCode()).isEqualTo(200);
            readRawFrame(response.body(), "V2 首帧");

            ExecutionStepRequest claimed = dispatches.claimNext().orElseThrow();
            assertThat(claimed.getRunId()).isEqualTo(run.runId());
            observer.wake();

            String raw = readRawFrame(response.body(), "V2 非终态 step_queued 帧");
            WorkflowEventStreamRepository.RunKey key =
                    new WorkflowEventStreamRepository.RunKey(fixture.userId(), run.runId());
            WorkflowEventStreamRepository.TailState tail =
                    eventStreams.readTails(List.of(key)).get(key);
            List<WorkflowEventEnvelope> events = eventStreams
                    .readEventTails(
                            List.of(new WorkflowEventStreamRepository.EventTailRequest(
                                    key, run.baseSequence(), tail.lastEventSequence())),
                            100)
                    .get(key);
            assertThat(events).singleElement().satisfies(event -> {
                assertThat(event.getEventType().getValue()).isEqualTo("step_queued");
                assertThat(raw).isEqualTo(formatEvent(event));
            });
            assertThat(observerConnectionCount()).isEqualTo(1);
        } finally {
            close(response);
            try {
                cancel(fixture, run);
            } finally {
                observer.wake();
                awaitNoConnection();
            }
        }
    }

    @Test
    @Order(4)
    void 数字LastEventId重连必须返回新权威终态Snapshot并在最后一帧后EOF() throws Exception {
        Fixture fixture = fixture();
        RunningRun run = runningRun(fixture);
        String cursor;
        HttpResponse<InputStream> first = client().send(
                request(run.runId(), fixture.userId(), null),
                HttpResponse.BodyHandlers.ofInputStream());
        try {
            cursor = parseFrame(readRawFrame(first.body(), "断线前 V2 snapshot")).id();
        } finally {
            close(first);
            try {
                cancel(fixture, run);
            } finally {
                observer.wake();
                awaitNoConnection();
            }
        }

        HttpResponse<InputStream> reconnected = client().send(
                request(run.runId(), fixture.userId(), cursor),
                HttpResponse.BodyHandlers.ofInputStream());
        try {
            assertThat(reconnected.statusCode()).isEqualTo(200);
            assertThat(reconnected.headers().firstValue("content-type"))
                    .contains(MediaType.TEXT_EVENT_STREAM_VALUE);
            String raw = readRawFrame(reconnected.body(), "重连终态 snapshot");
            RunSnapshot snapshot = eventStreams
                    .readSnapshot(fixture.userId(), run.runId())
                    .orElseThrow()
                    .frame();
            assertThat(raw).isEqualTo(formatSnapshot(snapshot));
            SseFrame frame = parseFrame(raw);
            assertThat(Long.parseLong(frame.id())).isGreaterThan(Long.parseLong(cursor));
            assertThat(json.readTree(frame.data()).path("snapshot").path("status").asString())
                    .isEqualTo("cancelled");
            assertThat(readEof(reconnected.body(), "终态最后一帧后的 EOF")).isEqualTo(-1);
            awaitNoConnection();
        } finally {
            close(reconnected);
        }
    }

    @Test
    @Order(5)
    void 客户端主动断开后必须回收Subscription和连接Worker() throws Throwable {
        Fixture fixture = fixture();
        RunningRun run = runningRun(fixture);
        int workerBaseline = activeWorkerCount();
        try {
            RawSseSocket connection = openRawSseSocket(run.runId(), fixture.userId());
            assertThat(observerConnectionCount()).isEqualTo(1);
            assertThat(activeWorkerCount()).isEqualTo(workerBaseline + 1);

            connection.reset();
            ExecutionStepRequest claimed = dispatches.claimNext().orElseThrow();
            assertThat(claimed.getRunId()).isEqualTo(run.runId());
            observer.wake();

            awaitCondition(
                    () -> observerConnectionCount() == 0
                            && activeWorkerCount() == workerBaseline,
                    "客户端断开后的 subscription/worker 清理");
        } finally {
            cancel(fixture, run);
            observer.wake();
        }
    }

    @Test
    @Order(6)
    void V1同一路径必须保持原始RunOutcomeWire和EventStream媒体类型() throws Exception {
        Fixture fixture = fixture();
        String taskId = "v1-sse-task-" + suffix();
        insertV1Task(fixture, taskId);
        HttpResponse<InputStream> response = client().send(
                request(taskId, fixture.userId(), "3-0"),
                HttpResponse.BodyHandlers.ofInputStream());
        try {
            assertThat(response.statusCode()).isEqualTo(200);
            assertThat(response.headers().firstValue("content-type"))
                    .contains(MediaType.TEXT_EVENT_STREAM_VALUE);
            String raw = readRawFrame(response.body(), "V1 run_outcome 首帧");
            assertThat(raw)
                    .startsWith("event: run_outcome\ndata: {")
                    .endsWith("}\n\n")
                    .doesNotContain("event:run_outcome\n", "data:{");
            SseFrame frame = parseFrame(raw);
            assertThat(frame.event()).isEqualTo("run_outcome");
            JsonNode outcome = json.readTree(frame.data());
            assertThat(outcome.path("code").asString())
                    .isEqualTo("LEGACY_WRITING_RUN_SUCCEEDED");
            assertThat(outcome.path("state").asString()).isEqualTo("succeeded");
            assertThat(outcome.path("streamShouldClose").asBoolean()).isTrue();
            assertThat(readEof(response.body(), "V1 终态帧后的 EOF")).isEqualTo(-1);
        } finally {
            close(response);
        }
    }

    @Test
    @Order(99)
    void Handler已初始化后Bean关闭必须完成HTTP响应并回收全部Session() throws Exception {
        Fixture fixture = fixture();
        RunningRun run = runningRun(fixture);
        HttpResponse<InputStream> response = client().send(
                request(run.runId(), fixture.userId(), null),
                HttpResponse.BodyHandlers.ofInputStream());
        assertThat(response.statusCode()).isEqualTo(200);
        readRawFrame(response.body(), "bean close 前 V2 snapshot");
        assertThat(observerConnectionCount()).isEqualTo(1);
        assertThat(activeWorkerCount()).isEqualTo(1);

        writingStreams.close();

        assertThat(readEof(response.body(), "bean close 后 HTTP EOF")).isEqualTo(-1);
        awaitCondition(
                () -> observerConnectionCount() == 0 && activeWorkerCount() == 0,
                "bean close 后 subscription/worker 清理");
        assertThat(workerExecutorTerminated()).isTrue();
        close(response);
        cancellations.cancel(
                fixture.userId(),
                run.runId(),
                "v2-sse-close-cancel-" + UUID.randomUUID());
    }

    private Fixture fixture() {
        String suffix = suffix();
        String userId = "v2-sse-user-" + suffix;
        String novelId = "v2-sse-novel-" + suffix;
        String chapterId = "v2-sse-chapter-" + suffix;
        String sessionId = "v2-sse-session-" + suffix;
        LocalDateTime now = now();
        insertUser(userId, now);
        database.dsl().execute(
                """
                INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
                VALUES (?, 'V2 SSE HTTP 测试', ?, ?, ?)
                """,
                novelId,
                userId,
                now,
                now);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', '仅用于隔离测试的章节事实。', 1, 'drafting', ?, ?)
                """,
                chapterId,
                novelId,
                now,
                now);
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                sessionId,
                novelId,
                chapterId,
                now,
                now);
        assertThat(database.dsl().fetchCount(USER, USER.ID.eq(userId))).isEqualTo(1);
        return new Fixture(userId, novelId, chapterId, sessionId, now);
    }

    private void insertUser(String userId, LocalDateTime now) {
        database.dsl().execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'test-only', 1000000, ?, ?)
                """,
                userId,
                userId,
                now,
                now);
    }

    private void insertV1Task(Fixture fixture, String taskId) {
        database.dsl().execute(
                """
                INSERT INTO public."WritingTask" (
                  id, "novelId", "chapterId", phase, "targetWordCount", "selectedAgents",
                  "conversationHistory", "writingSessionId", "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'completed', 1000, '[]', '[]', ?, ?, ?)
                """,
                taskId,
                fixture.novelId(),
                fixture.chapterId(),
                fixture.sessionId(),
                fixture.updatedAt(),
                fixture.updatedAt());
    }

    private RunningRun runningRun(Fixture fixture) {
        var started = starts.start(plan(fixture));
        int updated = database.dsl().execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('running' AS "WorkflowRunStatus"),
                    revision = revision + 1,
                    "updatedAt" = ?
                WHERE id = ? AND status::text = 'pending' AND "engineVersion" = 2
                """,
                now(),
                started.runId());
        assertThat(updated).isEqualTo(1);
        long baseSequence = database.dsl()
                .fetchSingle(
                        """
                        SELECT "lastEventSequence" FROM public."WorkflowRun" WHERE id = ?
                        """,
                        started.runId())
                .get("lastEventSequence", Long.class);
        return new RunningRun(started.runId(), baseSequence);
    }

    private void cancel(Fixture fixture, RunningRun run) {
        cancellations.cancel(
                fixture.userId(),
                run.runId(),
                "v2-sse-cancel-" + UUID.randomUUID());
    }

    private WorkflowStartPlan plan(Fixture fixture) {
        ExecutionRegistry.ResolvedOperation operation =
                registry.resolve("long_serial.answer_question", false);
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("userInstruction", "只验证 SSE 传输边界");
        return new WorkflowStartPlan(
                fixture.userId(),
                "v2-sse-http-request-" + fixture.userId(),
                "a".repeat(64),
                "long_serial",
                "answer_question",
                registry.catalogVersion(),
                "chat",
                fixture.novelId(),
                fixture.chapterId(),
                fixture.sessionId(),
                "chapter",
                fixture.chapterId(),
                input,
                operation.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_content",
                        fixture.chapterId(),
                        true,
                        null,
                        fixture.updatedAt().atOffset(ZoneOffset.UTC),
                        "仅用于隔离测试的章节事实。",
                        null,
                        null,
                        null,
                        Map.of("role", "answer_context"))),
                operation.operation().runBudget(),
                ExecutionPlanSnapshot.freeze(
                        registry.catalogVersion(), registry.manifestFingerprint(), operation),
                new WorkflowInitialStepPlan(
                        "generation",
                        operation.operation().lane(),
                        input,
                        operation.generatorProfile(),
                        operation.generatorStepBudget(),
                        operation.outputSchema()));
    }

    private HttpClient client() {
        return HttpClient.newBuilder()
                .connectTimeout(BOUNDARY_TIMEOUT)
                .build();
    }

    private HttpRequest request(String runId, String userId, String lastEventId) {
        HttpRequest.Builder request = HttpRequest.newBuilder()
                .uri(eventsUri(runId))
                .timeout(BOUNDARY_TIMEOUT)
                .header("Accept", MediaType.TEXT_EVENT_STREAM_VALUE)
                .GET();
        if (userId != null) {
            request.header(
                    "Cookie",
                    IdentityController.COOKIE_NAME + "=" + sessionTokens.create(userId));
        }
        if (lastEventId != null) request.header("Last-Event-ID", lastEventId);
        return request.build();
    }

    private RawSseSocket openRawSseSocket(String runId, String userId) throws Throwable {
        Socket socket = new Socket();
        try {
            socket.connect(
                    new InetSocketAddress("127.0.0.1", port),
                    Math.toIntExact(BOUNDARY_TIMEOUT.toMillis()));
            socket.setSoTimeout(Math.toIntExact(BOUNDARY_TIMEOUT.toMillis()));
            OutputStream output = socket.getOutputStream();
            String request = "GET /api/v1/writing/runs/"
                    + runId
                    + "/events HTTP/1.1\r\nHost: 127.0.0.1:"
                    + port
                    + "\r\nAccept: text/event-stream\r\nCookie: "
                    + IdentityController.COOKIE_NAME
                    + "="
                    + sessionTokens.create(userId)
                    + "\r\nConnection: keep-alive\r\n\r\n";
            output.write(request.getBytes(StandardCharsets.US_ASCII));
            output.flush();

            ByteArrayOutputStream received = new ByteArrayOutputStream();
            InputStream input = socket.getInputStream();
            while (true) {
                int value = input.read();
                if (value < 0) throw new AssertionError("RST 测试在 V2 snapshot 前关闭");
                received.write(value);
                String wire = received.toString(StandardCharsets.UTF_8);
                int frameStart = wire.indexOf("event: run_snapshot\n");
                if (frameStart >= 0 && wire.indexOf("\n\n", frameStart) >= 0) {
                    String headers = wire.substring(0, wire.indexOf("\r\n\r\n"))
                            .toLowerCase(java.util.Locale.ROOT);
                    assertThat(headers)
                            .startsWith("http/1.1 200")
                            .contains("content-type: text/event-stream");
                    return new RawSseSocket(socket);
                }
            }
        } catch (Throwable failure) {
            try {
                socket.close();
            } catch (Throwable closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }

    private String formatSnapshot(RunSnapshot snapshot) {
        String id = snapshot.getBaseSequence() > 0
                ? "id: " + snapshot.getBaseSequence() + "\n"
                : "";
        return id + "event: run_snapshot\ndata: "
                + json.writeValueAsString(snapshot)
                + "\n\n";
    }

    private String formatEvent(WorkflowEventEnvelope event) {
        return "id: "
                + event.getSequence()
                + "\nevent: "
                + event.getEventType().getValue()
                + "\ndata: "
                + json.writeValueAsString(event)
                + "\n\n";
    }

    private static String readRawFrame(InputStream input, String boundary) throws Exception {
        return awaitIo(() -> {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            int previous = -1;
            while (true) {
                int current = input.read();
                if (current < 0) throw new AssertionError(boundary + " 前连接关闭");
                bytes.write(current);
                if (previous == '\n' && current == '\n') {
                    return bytes.toString(StandardCharsets.UTF_8);
                }
                previous = current;
            }
        }, input, boundary);
    }

    private static int readEof(InputStream input, String boundary) throws Exception {
        return awaitIo(input::read, input, boundary);
    }

    private static <T> T awaitIo(IoCallable<T> operation, InputStream input, String boundary)
            throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<T> future = executor.submit(operation::call);
            try {
                return future.get(BOUNDARY_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
            } catch (TimeoutException exception) {
                input.close();
                future.cancel(true);
                throw new AssertionError(
                        boundary + " 超过 " + BOUNDARY_TIMEOUT.toMillis() + "ms", exception);
            } catch (ExecutionException exception) {
                Throwable cause = exception.getCause();
                if (cause instanceof Exception checked) throw checked;
                if (cause instanceof Error error) throw error;
                throw new AssertionError(boundary + " 异常", cause);
            }
        }
    }

    private static SseFrame parseFrame(String raw) {
        String id = null;
        String event = null;
        StringBuilder data = new StringBuilder();
        for (String line : raw.split("\n", -1)) {
            if (line.isEmpty() || line.startsWith(":")) continue;
            int separator = line.indexOf(':');
            String field = separator < 0 ? line : line.substring(0, separator);
            String value = separator < 0 ? "" : line.substring(separator + 1);
            if (value.startsWith(" ")) value = value.substring(1);
            switch (field) {
                case "id" -> id = value;
                case "event" -> event = value;
                case "data" -> {
                    if (!data.isEmpty()) data.append('\n');
                    data.append(value);
                }
                default -> {
                    // 原始 wire 已逐字断言；解析器只提取公共 SSE 字段。
                }
            }
        }
        return new SseFrame(id, event, data.toString());
    }

    private void awaitNoConnection() throws Exception {
        awaitCondition(
                () -> observerConnectionCount() == 0,
                "Workflow SSE subscription 清理");
    }

    private static void awaitCondition(BooleanSupplier condition, String boundary)
            throws Exception {
        long deadline = System.nanoTime() + BOUNDARY_TIMEOUT.toNanos();
        while (!condition.getAsBoolean()) {
            if (System.nanoTime() >= deadline) {
                throw new AssertionError(boundary + " 超过 " + BOUNDARY_TIMEOUT.toMillis() + "ms");
            }
            Thread.sleep(5);
        }
    }

    private int observerConnectionCount() {
        Integer count = ReflectionTestUtils.invokeMethod(observer, "activeConnectionCount");
        return count == null ? -1 : count;
    }

    private int activeWorkerCount() {
        Integer count = ReflectionTestUtils.invokeMethod(writingStreams, "activeWorkerCount");
        return count == null ? -1 : count;
    }

    private boolean workerExecutorTerminated() {
        Boolean terminated =
                ReflectionTestUtils.invokeMethod(writingStreams, "workerExecutorTerminated");
        return Boolean.TRUE.equals(terminated);
    }

    private static void close(HttpResponse<InputStream> response) throws IOException {
        if (response != null) response.body().close();
    }

    private static long elapsedMillis(long started) {
        return Duration.ofNanos(System.nanoTime() - started).toMillis();
    }

    private URI eventsUri(String runId) {
        return URI.create("http://127.0.0.1:"
                + port
                + "/api/v1/writing/runs/"
                + runId
                + "/events");
    }

    private static LocalDateTime now() {
        return LocalDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MILLIS);
    }

    private static String suffix() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
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

    private record Fixture(
            String userId,
            String novelId,
            String chapterId,
            String sessionId,
            LocalDateTime updatedAt) {}

    private record SseFrame(String id, String event, String data) {}

    private record RunningRun(String runId, long baseSequence) {}

    private record RawSseSocket(Socket socket) {

        private void reset() throws IOException {
            socket.setSoLinger(true, 0);
            socket.close();
        }
    }

    @FunctionalInterface
    private interface IoCallable<T> {

        T call() throws Exception;
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestIdentityConfiguration {

        @Bean
        CurrentUserAccess currentUserAccess(SessionTokens sessions, CoreDatabase database) {
            return token -> {
                if (token == null) throw unauthenticated();
                final String userId;
                try {
                    userId = sessions.verify(token);
                } catch (InvalidSessionTokenException exception) {
                    throw unauthenticated();
                }
                var user = database.dsl().fetchOne(
                        """
                        SELECT id, username FROM public."User" WHERE id = ?
                        """,
                        userId);
                if (user == null) throw unauthenticated();
                return new AuthenticatedUser(
                        user.get("id", String.class), user.get("username", String.class));
            };
        }

        @Bean
        @Primary
        WritingEventStore emptyWritingEventStore() {
            return new EmptyWritingEventStore();
        }

        private static ApiException unauthenticated() {
            return new ApiException(401, "UNAUTHENTICATED", "请先登录");
        }
    }

    private static final class EmptyWritingEventStore implements WritingEventStore {

        @Override
        public boolean validateSource(
                String taskId,
                String sourceEventId,
                int sequence,
                String event,
                Map<String, Object> data) {
            return true;
        }

        @Override
        public boolean validate(
                String taskId,
                String sourceEventId,
                int sequence,
                String event,
                Map<String, Object> data,
                int durableBaseline,
                boolean allowRebase) {
            return true;
        }

        @Override
        public WritingEvent appendAgent(
                String taskId,
                String sourceEventId,
                int sequence,
                String event,
                Map<String, Object> data,
                int durableBaseline,
                boolean allowRebase) {
            throw new UnsupportedOperationException();
        }

        @Override
        public List<WritingEvent> replay(String taskId, String lastEventId) {
            return List.of();
        }
    }
}
