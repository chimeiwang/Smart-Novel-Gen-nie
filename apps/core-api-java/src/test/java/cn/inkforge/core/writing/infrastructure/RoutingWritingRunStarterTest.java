package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.WritingRunResponse;
import cn.inkforge.contracts.api.WritingRunStartResponse;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.writing.application.DurableAgentExecutionReadiness;
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.writing.application.WritingRunStartRequestParser;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import jakarta.validation.Validation;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class RoutingWritingRunStarterTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T03:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-09-01T03:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static WritingRunStartRequestParser parser;
    private static JooqWritingCommandRepository legacy;
    private static JooqLongSerialDurableRunStarter durable;
    private static ExecutionRegistry registry;

    @BeforeAll
    static void rebuildSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource(
                        "migrations/20260831_durable_agent_execution.sql"),
                "/tmp/20260831_durable_agent_execution.sql");
        executeSql("/tmp/novelwriterdev-schema.sql");
        executeSql("/tmp/20260831_durable_agent_execution.sql");
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        json = JsonMapper.builder()
                .addModule(new JsonNullableJackson3Module())
                .build();
        parser = new WritingRunStartRequestParser(
                json, Validation.buildDefaultValidatorFactory().getValidator());
        CuidV1Generator ids = new CuidV1Generator(CLOCK);
        legacy = new JooqWritingCommandRepository(
                database,
                ids,
                CLOCK,
                json,
                new CommandIdempotencyStore(json, true));
        registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        DurableWorkflowService workflows = new DurableWorkflowService(
                new JooqWorkflowStartRepository(database, ids, CLOCK, json));
        durable = new JooqLongSerialDurableRunStarter(
                database,
                new LongSerialRunAssembler(json, new WritingSourceBindingCapture(json)),
                workflows,
                registry,
                ids,
                CLOCK,
                json);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void V2路由冻结完整来源且开关关闭后仍幂等重放原引擎() {
        Fixture fixture = fixture("route-v2");
        RoutingWritingRunStarter all = router("all");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-route-v2-0001", "请让这句话更有压迫感");
        LocalDateTime sessionUpdatedBefore = sessionUpdatedAt(fixture.sessionId());

        var first = all.start(fixture.userId(), request);
        LocalDateTime sessionUpdatedAfterFirst = sessionUpdatedAt(fixture.sessionId());
        var refreshedAfterFirst = new JooqWritingSessionRepository(
                        database, new CuidV1Generator(CLOCK), CLOCK, json)
                .get(fixture.userId(), fixture.sessionId());
        var replayAfterRouteOff = router("off").start(fixture.userId(), request);
        LocalDateTime sessionUpdatedAfterReplay = sessionUpdatedAt(fixture.sessionId());
        var refreshedAfterReplay = new JooqWritingSessionRepository(
                        database, new CuidV1Generator(CLOCK), CLOCK, json)
                .get(fixture.userId(), fixture.sessionId());

        assertThat(first).isInstanceOf(WritingRunV2Response.class);
        WritingRunV2Response response = (WritingRunV2Response) first;
        assertThat(response.getEngineVersion()).isEqualTo(2);
        assertThat(response.getRunId()).isEqualTo(response.getTaskId());
        assertThat(response.getOperation()).isEqualTo("rewrite_chapter_selection");
        assertThat(response.getActiveSteps()).hasSize(1);
        assertThat(response.getCurrentStep()).isEqualTo(response.getActiveSteps().getFirst());
        assertThat(response.getCurrentStep().getPurpose()).isEqualTo("generation");
        assertThat(response.getCurrentStep().getModelProfile().getProfile())
                .isEqualTo("writer.chapter_selection.v1");
        assertThat(response.getCurrentStep().getResolvedModel()).isNull();
        assertThat(((WritingRunV2Response) replayAfterRouteOff).getRunId())
                .isEqualTo(response.getRunId());
        assertThat(((WritingRunV2Response) replayAfterRouteOff).getActiveSteps())
                .containsExactlyElementsOf(response.getActiveSteps());
        assertThat(((WritingRunV2Response) replayAfterRouteOff).getCurrentStep())
                .isEqualTo(response.getActiveSteps().getFirst());
        assertThat(sessionUpdatedAfterFirst).isAfter(sessionUpdatedBefore);
        assertThat(sessionUpdatedAfterReplay).isEqualTo(sessionUpdatedAfterFirst);
        assertThat(refreshedAfterFirst.getMessages())
                .singleElement()
                .satisfies(message -> {
                    assertThat(message.getRole()).isEqualTo("user");
                    assertThat(message.getContent()).isEqualTo("请让这句话更有压迫感");
                    @SuppressWarnings("unchecked")
                    Map<String, Object> metadata =
                            (Map<String, Object>) message.getMetadata().get();
                    assertThat(metadata)
                            .containsEntry("taskId", response.getRunId())
                            .containsEntry("eventType", "user");
                    Map<?, ?> source = (Map<?, ?>) metadata.get("source");
                    assertThat(source.get("engineVersion")).isEqualTo(2);
                    assertThat(source.get("runId")).isEqualTo(response.getRunId());
                    assertThat(source.get("operation"))
                            .isEqualTo("rewrite_chapter_selection");
                    assertThat(source.get("sourceLabel")).isEqualTo("章节正文");
                });
        assertThat(refreshedAfterReplay.getMessages()).hasSize(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?", fixture.userId()))
                .isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?", fixture.novelId()))
                .isZero();
        String purpose = database.dsl().fetchOne(
                        "SELECT purpose FROM public.\"WorkflowStep\" WHERE \"runId\" = ?",
                        response.getRunId())
                .get("purpose", String.class);
        assertThat(purpose).isEqualTo("generation");
        String evidence = database.dsl().fetchOne(
                        """
                        SELECT item."contentText"
                        FROM public."WorkflowEvidenceItem" AS item
                        JOIN public."WorkflowEvidenceBundle" AS bundle
                          ON bundle.id = item."bundleId"
                        WHERE bundle."runId" = ?
                        """,
                        response.getRunId())
                .get("contentText", String.class);
        assertThat(evidence).isEqualTo(fixture.content());

        ParsedWritingRunStartRequest changed = request(
                fixture, "request-route-v2-0001", "改成完全不同的要求");
        assertThatThrownBy(() -> all.start(fixture.userId(), changed))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void V2重放返回按ordinal排序的全部活动Reviewer与冻结模型身份() {
        Fixture fixture = fixture("route-v2-active-reviewers");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-route-v2-reviewers-01", "请调整选区");
        WritingRunV2Response started = (WritingRunV2Response) router("all").start(
                fixture.userId(), request);
        ExecutionPlanSnapshot executionPlan = registry.freezePlan(
                "long_serial.rewrite_chapter_selection", false);

        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('completed' AS public."WorkflowStepStatus"),
                    "completedAt" = ?, "updatedAt" = ?
                WHERE id = ?
                """,
                NOW,
                NOW,
                started.getCurrentStep().getStepId());
        String evidenceBundleId = database.dsl().fetchOne(
                        "SELECT \"evidenceBundleId\" FROM public.\"WorkflowStep\" WHERE id = ?",
                        started.getCurrentStep().getStepId())
                .get("evidenceBundleId", String.class);
        insertPendingReviewer(
                started.getRunId(),
                "reviewer-step-ordinal-3",
                3,
                evidenceBundleId,
                executionPlan.reviewers().get(1));
        insertPendingReviewer(
                started.getRunId(),
                "reviewer-step-ordinal-2",
                2,
                evidenceBundleId,
                executionPlan.reviewers().getFirst());

        WritingRunV2Response replay = (WritingRunV2Response) router("off").start(
                fixture.userId(), request);

        assertThat(replay.getActiveSteps())
                .extracting(step -> step.getStepId())
                .containsExactly("reviewer-step-ordinal-2", "reviewer-step-ordinal-3");
        assertThat(replay.getActiveSteps())
                .extracting(step -> step.getOrdinal())
                .containsExactly(2, 3);
        assertThat(replay.getActiveSteps())
                .extracting(step -> step.getModelProfile().getProfile())
                .containsExactly("reviewer.consistency.v1", "reviewer.editorial.v1");
        assertThat(replay.getActiveSteps())
                .allSatisfy(step -> {
                    assertThat(step.getPurpose()).isEqualTo("review");
                    assertThat(step.getResolvedModel()).isNull();
                });
        assertThat(replay.getCurrentStep()).isSameAs(replay.getActiveSteps().getFirst());
    }

    @Test
    void V1已创建请求在打开V2后仍重放V1且跨引擎章节写入互斥() {
        Fixture legacyFixture = fixture("route-v1");
        ParsedWritingRunStartRequest legacyRequest = request(
                legacyFixture, "request-route-v1-0001", "请调整选区");

        var first = router("off").start(legacyFixture.userId(), legacyRequest);
        var replay = router("all").start(legacyFixture.userId(), legacyRequest);

        assertThat(first).isInstanceOf(WritingRunResponse.class);
        assertThat(((WritingRunResponse) first).getEngineVersion()).isEqualTo(1);
        assertThat(((WritingRunResponse) replay).getId())
                .isEqualTo(((WritingRunResponse) first).getId());

        Fixture durableFixture = fixture("route-busy");
        router("all").start(
                durableFixture.userId(),
                requestWithoutSession(
                        durableFixture, "request-route-busy-01", "先创建 V2"));
        assertThatThrownBy(() -> router("off").start(
                        durableFixture.userId(),
                        requestWithoutSession(
                                durableFixture,
                                "request-route-busy-02",
                                "再尝试 V1")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY"));
    }

    @ParameterizedTest(name = "V1 operation={0}")
    @MethodSource("mutatingV1Operations")
    void 活动V2阻断所有已支持V1写操作与保守legacy入口(String operation) {
        Fixture fixture = fixture("route-v1-mutation-" + operation.replace('_', '-'));
        router("all").start(
                fixture.userId(),
                requestWithoutSession(
                        fixture,
                        "request-v2-before-" + operation,
                        "先创建 V2 选区改写"));

        ParsedWritingRunStartRequest v1 = "legacy".equals(operation)
                ? legacyRequestWithoutSession(
                        fixture, "request-v1-after-legacy", "请继续处理这一章")
                : longSerialRequest(
                        fixture,
                        "request-v1-after-" + operation,
                        operation,
                        false);

        assertThatThrownBy(() -> router("off").start(fixture.userId(), v1))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY"));
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isZero();
    }

    @Test
    void 无Session的只读V1审核与V2双向并存() {
        Fixture fixture = fixture("route-v1-review-readable");
        router("all").start(
                fixture.userId(),
                requestWithoutSession(
                        fixture,
                        "request-v2-review-readable-01",
                        "先创建 V2 选区改写"));

        WritingRunStartResponse review = router("off").start(
                fixture.userId(),
                longSerialRequest(
                        fixture,
                        "request-v1-review-readable-01",
                        "review_chapter",
                        false));

        assertThat(review).isInstanceOf(WritingRunResponse.class);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(1);

        Fixture reviewFirst = fixture("route-v1-review-first");
        router("off").start(
                reviewFirst.userId(),
                longSerialRequest(
                        reviewFirst,
                        "request-v1-review-first-01",
                        "review_chapter",
                        false));
        WritingRunStartResponse durable = router("all").start(
                reviewFirst.userId(),
                requestWithoutSession(
                        reviewFirst,
                        "request-v2-after-review-01",
                        "审核期间创建独立 V2 写任务"));
        assertThat(durable).isInstanceOf(WritingRunV2Response.class);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?",
                        reviewFirst.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        reviewFirst.chapterId()))
                .isEqualTo(1);
    }

    @Test
    void 同WritingSession跨引擎只允许一个foreground且只读审核也不豁免() {
        Fixture v2First = fixture("route-session-v2-first");
        router("all").start(
                v2First.userId(),
                request(v2First, "request-session-v2-first-01", "先创建 V2"));
        assertThatThrownBy(() -> router("off").start(
                        v2First.userId(),
                        longSerialRequest(
                                v2First,
                                "request-session-v1-review-01",
                                "review_chapter",
                                true)))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_FOREGROUND_RUN_EXISTS"));

        Fixture v1First = fixture("route-session-v1-first");
        WritingRunStartResponse review = router("off").start(
                v1First.userId(),
                longSerialRequest(
                        v1First,
                        "request-session-v1-first-01",
                        "review_chapter",
                        true));
        assertThat(review).isInstanceOf(WritingRunResponse.class);
        assertThatThrownBy(() -> router("all").start(
                        v1First.userId(),
                        request(v1First, "request-session-v2-after-01", "再创建 V2")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_FOREGROUND_RUN_EXISTS"));
    }

    @Test
    void 已有V1和V2重放在Agent离线或manifest升级时不被阻断() {
        Fixture v2Fixture = fixture("route-replay-v2-offline");
        ParsedWritingRunStartRequest v2Request = request(
                v2Fixture, "request-replay-v2-offline-01", "请调整选区");
        WritingRunV2Response firstV2 = (WritingRunV2Response) router("all").start(
                v2Fixture.userId(), v2Request);
        AtomicInteger v2Probes = new AtomicInteger();
        WritingRunV2Response replayV2 = (WritingRunV2Response) router(
                        "all",
                        () -> {
                            v2Probes.incrementAndGet();
                            return false;
                        })
                .start(v2Fixture.userId(), v2Request);

        assertThat(replayV2.getRunId()).isEqualTo(firstV2.getRunId());
        assertThat(v2Probes).hasValue(0);

        Fixture v1Fixture = fixture("route-replay-v1-offline");
        ParsedWritingRunStartRequest v1Request = request(
                v1Fixture, "request-replay-v1-offline-01", "请调整选区");
        WritingRunResponse firstV1 = (WritingRunResponse) router("off").start(
                v1Fixture.userId(), v1Request);
        AtomicInteger v1Probes = new AtomicInteger();
        WritingRunResponse replayV1 = (WritingRunResponse) router(
                        "all",
                        () -> {
                            v1Probes.incrementAndGet();
                            return false;
                        })
                .start(v1Fixture.userId(), v1Request);

        assertThat(replayV1.getId()).isEqualTo(firstV1.getId());
        assertThat(v1Probes).hasValue(0);
    }

    @Test
    void 新V2在manifest握手失败时以503拒绝且零持久工作流事实() {
        Fixture fixture = fixture("route-manifest-mismatch");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-manifest-mismatch-01", "请调整选区");
        AtomicInteger probes = new AtomicInteger();

        assertThatThrownBy(() -> router(
                                "all",
                                () -> {
                                    probes.incrementAndGet();
                                    assertThat(workflowFacts(fixture.userId())).isZero();
                                    Boolean lockWasFree = database.transactionResult(transaction -> transaction
                                                    .fetchOne(
                                                            "SELECT pg_catalog.pg_try_advisory_xact_lock(?) AS free",
                                                            CommandIdempotency.advisoryLockKey(
                                                                    fixture.userId(),
                                                                    "request-manifest-mismatch-01"))
                                                    .get("free", Boolean.class));
                                    assertThat(lockWasFree).isTrue();
                                    return false;
                                })
                        .start(fixture.userId(), request))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code())
                            .isEqualTo("DURABLE_AGENT_EXECUTION_UNAVAILABLE");
                    assertThat(error.details()).isNull();
                });

        assertThat(probes).hasValue(1);
        assertThat(workflowFacts(fixture.userId())).isZero();
    }

    @Test
    void 并发同幂等标识均在无锁握手后仍只创建一个V2Run() throws Exception {
        Fixture fixture = fixture("route-concurrent-v2");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-concurrent-v2-01", "请调整选区");
        CountDownLatch probesEntered = new CountDownLatch(2);
        CountDownLatch releaseProbes = new CountDownLatch(1);
        DurableAgentExecutionReadiness readiness = () -> {
            probesEntered.countDown();
            try {
                return releaseProbes.await(2, TimeUnit.SECONDS);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return false;
            }
        };
        RoutingWritingRunStarter router = router("all", readiness);

        CompletableFuture<WritingRunV2Response> first = CompletableFuture.supplyAsync(
                () -> (WritingRunV2Response) router.start(fixture.userId(), request));
        CompletableFuture<WritingRunV2Response> second = CompletableFuture.supplyAsync(
                () -> (WritingRunV2Response) router.start(fixture.userId(), request));
        assertThat(probesEntered.await(2, TimeUnit.SECONDS)).isTrue();
        assertThat(workflowFacts(fixture.userId())).isZero();
        releaseProbes.countDown();

        WritingRunV2Response firstResponse = first.get(5, TimeUnit.SECONDS);
        WritingRunV2Response secondResponse = second.get(5, TimeUnit.SECONDS);
        assertThat(secondResponse.getRunId()).isEqualTo(firstResponse.getRunId());
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?",
                        fixture.userId()))
                .isEqualTo(1);
    }

    @Test
    void 同章节无Session的不同幂等请求并发也只允许一个活动V2Run() throws Exception {
        Fixture fixture = fixture("route-v2-scope-busy");
        ParsedWritingRunStartRequest first = requestWithoutSession(
                fixture, "request-v2-scope-busy-01", "第一次选区改写");
        ParsedWritingRunStartRequest second = requestWithoutSession(
                fixture, "request-v2-scope-busy-02", "第二次选区改写");
        CountDownLatch probesEntered = new CountDownLatch(2);
        CountDownLatch releaseProbes = new CountDownLatch(1);
        RoutingWritingRunStarter all = router("all", () -> {
            probesEntered.countDown();
            try {
                return releaseProbes.await(2, TimeUnit.SECONDS);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return false;
            }
        });

        CompletableFuture<WritingRunStartResponse> firstStart = CompletableFuture.supplyAsync(
                () -> all.start(fixture.userId(), first));
        CompletableFuture<WritingRunStartResponse> secondStart = CompletableFuture.supplyAsync(
                () -> all.start(fixture.userId(), second));
        assertThat(probesEntered.await(2, TimeUnit.SECONDS)).isTrue();
        releaseProbes.countDown();
        Object firstOutcome = firstStart.handle((value, error) ->
                        error == null ? value : error.getCause())
                .get(5, TimeUnit.SECONDS);
        Object secondOutcome = secondStart.handle((value, error) ->
                        error == null ? value : error.getCause())
                .get(5, TimeUnit.SECONDS);

        assertThat(List.of(firstOutcome, secondOutcome))
                .anySatisfy(value -> assertThat(value).isInstanceOf(WritingRunV2Response.class))
                .anySatisfy(value -> assertThat(value)
                        .isInstanceOfSatisfying(ApiException.class, error ->
                                assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY")));
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ? AND status IN ('pending', 'running', 'waiting_user')",
                        fixture.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?",
                        fixture.sessionId()))
                .isZero();
    }

    @Test
    void 同章节V1V2真实并发时一个成功另一个稳定busy且不死锁() throws Exception {
        Fixture fixture = fixture("route-cross-engine-race");
        ParsedWritingRunStartRequest v1 = longSerialRequest(
                fixture,
                "request-cross-engine-v1-01",
                "plan_chapter",
                false);
        ParsedWritingRunStartRequest v2 = requestWithoutSession(
                fixture,
                "request-cross-engine-v2-01",
                "并发改写选区");
        CountDownLatch startersReady = new CountDownLatch(2);
        CountDownLatch releaseStart = new CountDownLatch(1);

        CompletableFuture<WritingRunStartResponse> v1Start = CompletableFuture.supplyAsync(
                () -> startAfterGate(router("off"), fixture.userId(), v1, startersReady, releaseStart));
        CompletableFuture<WritingRunStartResponse> v2Start = CompletableFuture.supplyAsync(
                () -> startAfterGate(router("all"), fixture.userId(), v2, startersReady, releaseStart));
        assertThat(startersReady.await(2, TimeUnit.SECONDS)).isTrue();
        releaseStart.countDown();

        Object v1Outcome = v1Start.handle((value, error) ->
                        error == null ? value : error.getCause())
                .get(8, TimeUnit.SECONDS);
        Object v2Outcome = v2Start.handle((value, error) ->
                        error == null ? value : error.getCause())
                .get(8, TimeUnit.SECONDS);

        assertThat(List.of(v1Outcome, v2Outcome))
                .anySatisfy(value -> assertThat(value)
                        .isInstanceOfAny(WritingRunResponse.class, WritingRunV2Response.class))
                .anySatisfy(value -> assertThat(value)
                        .isInstanceOfSatisfying(ApiException.class, error ->
                                assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY")));
        assertThat(count(
                                """
                                SELECT (
                                  SELECT count(*) FROM public."WritingTask"
                                  WHERE "chapterId" = ? AND phase NOT IN ('completed', 'error')
                                ) + (
                                  SELECT count(*) FROM public."WorkflowRun"
                                  WHERE "chapterId" = ?
                                    AND status IN ('pending', 'running', 'waiting_user')
                                )
                                """,
                                fixture.chapterId(),
                                fixture.chapterId()))
                .isEqualTo(1);
    }

    private static RoutingWritingRunStarter router(String mode) {
        return router(mode, () -> true);
    }

    private static void insertPendingReviewer(
            String runId,
            String stepId,
            int ordinal,
            String evidenceBundleId,
            ExecutionPlanSnapshot.Step reviewer) {
        String hashDigit = ordinal == 2 ? "b" : "c";
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken",
                  "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                  "modelProfile", "modelProfileVersion", "outputSchema",
                  "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt"
                ) VALUES (
                  ?, ?, ?, CAST('agent' AS public."WorkflowStepType"),
                  CAST('pending' AS public."WorkflowStepStatus"), '{}', ?, ?, 'review', ?,
                  0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                stepId,
                runId,
                reviewer.modelProfile().profile(),
                NOW,
                ordinal,
                reviewer.lane(),
                NOW,
                runId + "." + stepId,
                hashDigit.repeat(64),
                "d".repeat(64),
                evidenceBundleId,
                reviewer.modelProfile().profile(),
                Integer.toString(reviewer.modelProfile().version()),
                reviewer.outputSchema().name(),
                Integer.toString(reviewer.outputSchema().version()),
                json.writeValueAsString(reviewer.stepBudget().stored()),
                NOW,
                NOW);
    }

    private static RoutingWritingRunStarter router(
            String mode, DurableAgentExecutionReadiness readiness) {
        return new RoutingWritingRunStarter(
                database,
                legacy,
                durable,
                new CommandIdempotencyStore(json, true),
                CoreSettings.from(Map.of(
                        "DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true",
                        "DURABLE_AGENT_EXECUTION_ROUTE_MODE", mode)),
                readiness,
                json);
    }

    private static ParsedWritingRunStartRequest request(
            Fixture fixture, String clientRequestId, String instruction) {
        String selected = codePointSlice(fixture.content(), 1, 3);
        String body = """
                {
                  "clientRequestId": "%s",
                  "workflow": "long_serial",
                  "novelId": "%s",
                  "chapterId": "%s",
                  "writingSessionId": "%s",
                  "operation": "rewrite_chapter_selection",
                  "target": {"type": "chapter", "id": "%s"},
                  "scope": {"kind": "chapter", "chapterId": "%s"},
                  "selectionTarget": {
                    "resourceType": "chapter_content",
                    "resourceId": "%s",
                    "baseUpdatedAt": "2026-09-01T03:00:00Z",
                    "baseContentHash": "%s",
                    "selectionStart": 1,
                    "selectionEnd": 3,
                    "selectedTextHash": "%s"
                  },
                  "selectionAttachmentMetadata": {
                    "resourceType": "chapter_content",
                    "resourceId": "%s",
                    "sourceLabel": "章节正文",
                    "baseUpdatedAt": "2026-09-01T03:00:00Z",
                    "baseContentHash": "%s",
                    "selectionStart": 1,
                    "selectionEnd": 3,
                    "selectedTextHash": "%s",
                    "selectionPreview": "%s"
                  },
                  "targetWordCount": 1000,
                  "userInstruction": "%s"
                }
                """.formatted(
                clientRequestId,
                fixture.novelId(),
                fixture.chapterId(),
                fixture.sessionId(),
                fixture.chapterId(),
                fixture.chapterId(),
                fixture.chapterId(),
                sha256(fixture.content()),
                sha256(selected),
                fixture.chapterId(),
                sha256(fixture.content()),
                sha256(selected),
                selected,
                instruction);
        return parser.parse(new WritingRunStartBody(json.readTree(body)));
    }

    private static ParsedWritingRunStartRequest requestWithoutSession(
            Fixture fixture, String clientRequestId, String instruction) {
        ParsedWritingRunStartRequest parsed = request(fixture, clientRequestId, instruction);
        ((ParsedWritingRunStartRequest.LongSerial) parsed)
                .request()
                .setWritingSessionId(null);
        return parsed;
    }

    private static ParsedWritingRunStartRequest longSerialRequest(
            Fixture fixture,
            String clientRequestId,
            String operation,
            boolean withSession) {
        Map<String, Object> body = new java.util.LinkedHashMap<>();
        body.put("clientRequestId", clientRequestId);
        body.put("workflow", "long_serial");
        body.put("novelId", fixture.novelId());
        body.put("chapterId", fixture.chapterId());
        if (withSession) body.put("writingSessionId", fixture.sessionId());
        body.put("operation", operation);
        body.put("target", Map.of("type", "chapter", "id", fixture.chapterId()));
        body.put("targetWordCount", 1000);
        body.put("userInstruction", "请执行 " + operation);
        if ("rewrite_outline_selection".equals(operation)) {
            String selected = codePointSlice(fixture.outlineContent(), 1, 3);
            body.put("scope", Map.of("kind", "novel"));
            body.put(
                    "selectionTarget",
                    Map.of(
                            "resourceType", "outline_content",
                            "resourceId", fixture.outlineId(),
                            "baseUpdatedAt", "2026-09-01T03:00:00Z",
                            "baseContentHash", sha256(fixture.outlineContent()),
                            "selectionStart", 1,
                            "selectionEnd", 3,
                            "selectedTextHash", sha256(selected)));
        } else if ("rewrite_chapter_selection".equals(operation)) {
            String selected = codePointSlice(fixture.content(), 1, 3);
            body.put("scope", Map.of("kind", "chapter", "chapterId", fixture.chapterId()));
            body.put(
                    "selectionTarget",
                    Map.of(
                            "resourceType", "chapter_content",
                            "resourceId", fixture.chapterId(),
                            "baseUpdatedAt", "2026-09-01T03:00:00Z",
                            "baseContentHash", sha256(fixture.content()),
                            "selectionStart", 1,
                            "selectionEnd", 3,
                            "selectedTextHash", sha256(selected)));
        } else {
            body.put("scope", Map.of("kind", "chapter", "chapterId", fixture.chapterId()));
        }
        return parser.parse(new WritingRunStartBody(json.valueToTree(body)));
    }

    private static ParsedWritingRunStartRequest legacyRequestWithoutSession(
            Fixture fixture, String clientRequestId, String instruction) {
        Map<String, Object> body = Map.of(
                "clientRequestId", clientRequestId,
                "novelId", fixture.novelId(),
                "chapterId", fixture.chapterId(),
                "targetWordCount", 1000,
                "selectedAgents", List.of("写作"),
                "userMessage", instruction);
        return parser.parse(new WritingRunStartBody(json.valueToTree(body)));
    }

    private static WritingRunStartResponse startAfterGate(
            RoutingWritingRunStarter starter,
            String userId,
            ParsedWritingRunStartRequest request,
            CountDownLatch ready,
            CountDownLatch release) {
        ready.countDown();
        try {
            if (!release.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("并发启动门未及时释放");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("并发启动被中断", exception);
        }
        return starter.start(userId, request);
    }

    private static Stream<Arguments> mutatingV1Operations() {
        return Stream.of(
                Arguments.of("plan_chapter"),
                Arguments.of("write_chapter"),
                Arguments.of("rewrite_scene"),
                Arguments.of("rewrite_chapter_selection"),
                Arguments.of("rewrite_outline_selection"),
                Arguments.of("legacy"));
    }

    private static Fixture fixture(String prefix) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        String sessionId = prefix + "-session";
        String content = "甲😀乙丙";
        database.dsl().execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'test', 1000000, ?, ?)
                """,
                userId,
                userId,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                novelId,
                prefix,
                userId,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WritingBible" (
                  id, "novelId", "storyLengthProfile", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'long_serial', ?, ?)
                """,
                prefix + "-bible",
                novelId,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', ?, 1, 'drafting', ?, ?)
                """,
                chapterId,
                novelId,
                content,
                NOW,
                NOW);
        String outlineId = prefix + "-outline";
        String outlineContent = "纲要甲乙";
        database.dsl().execute(
                """
                INSERT INTO public."Outline" (id, "novelId", content, "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                outlineId,
                novelId,
                outlineContent,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                sessionId,
                novelId,
                chapterId,
                NOW,
                NOW);
        return new Fixture(
                userId,
                novelId,
                chapterId,
                sessionId,
                content,
                outlineId,
                outlineContent);
    }

    private static int count(String sql, Object... bindings) {
        return database.dsl().fetchOne(sql, bindings).get(0, Integer.class);
    }

    private static LocalDateTime sessionUpdatedAt(String sessionId) {
        return database.dsl().fetchOne(
                        "SELECT \"updatedAt\" FROM public.\"WritingSession\" WHERE id = ?",
                        sessionId)
                .get("updatedAt", LocalDateTime.class);
    }

    private static int workflowFacts(String userId) {
        return count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?",
                        userId)
                + count(
                        """
                        SELECT count(*) FROM public."WorkflowStep"
                        WHERE "runId" IN (
                          SELECT id FROM public."WorkflowRun" WHERE "userId" = ?
                        )
                        """,
                        userId)
                + count(
                        """
                        SELECT count(*) FROM public."WorkflowEvidenceBundle"
                        WHERE "runId" IN (
                          SELECT id FROM public."WorkflowRun" WHERE "userId" = ?
                        )
                        """,
                        userId)
                + count(
                        """
                        SELECT count(*) FROM public."WorkflowEvent"
                        WHERE "runId" IN (
                          SELECT id FROM public."WorkflowRun" WHERE "userId" = ?
                        )
                        """,
                        userId);
    }

    private static String sha256(String value) {
        return CommandIdempotency.sha256(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String codePointSlice(String value, int start, int end) {
        return value.substring(
                value.offsetByCodePoints(0, start), value.offsetByCodePoints(0, end));
    }

    private static void executeSql(String path) throws Exception {
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                path);
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getFirstMappedPort()
                + "/"
                + POSTGRES.getDatabaseName();
    }

    private record Fixture(
            String userId,
            String novelId,
            String chapterId,
            String sessionId,
            String content,
            String outlineId,
            String outlineContent) {}
}
