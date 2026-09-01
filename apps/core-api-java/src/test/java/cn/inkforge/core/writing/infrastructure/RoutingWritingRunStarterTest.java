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
import cn.inkforge.core.writing.application.LongSerialDurableRunStarter;
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
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import org.jooq.Record;
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
        RoutingWritingRunStarter all = router(fixture, "allowlist");
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
    void 只读问答按Catalog路由V2并冻结唯一章节证据且重放不重复消息() {
        Fixture fixture = fixture("route-v2-answer");
        ParsedWritingRunStartRequest request = longSerialRequest(
                fixture,
                "request-route-v2-answer-01",
                "answer_question",
                true);

        WritingRunV2Response first = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(), request);
        AtomicInteger replayProbes = new AtomicInteger();
        WritingRunV2Response replay = (WritingRunV2Response) router(
                        fixture,
                        "allowlist",
                        () -> {
                            replayProbes.incrementAndGet();
                            return false;
                        })
                .start(fixture.userId(), request);

        assertThat(first.getOperation()).isEqualTo("answer_question");
        assertThat(first.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.PENDING);
        assertThat(first.getCurrentStep().getLane().getValue()).isEqualTo("interactive");
        assertThat(first.getCurrentStep().getModelProfile().getProfile())
                .isEqualTo("editor.answer.v1");
        assertThat(replay.getRunId()).isEqualTo(first.getRunId());
        assertThat(replayProbes).hasValue(0);
        Record facts = database.dsl().fetchOne(
                """
                SELECT run.kind::text AS kind,
                       bundle."policyVersion" AS policy,
                       item."resourceType" AS resource_type,
                       item."contentText" AS content_text,
                       item."rangeJson" AS range_json,
                       step.input::text AS step_input
                FROM public."WorkflowRun" AS run
                JOIN public."WorkflowEvidenceBundle" AS bundle ON bundle."runId" = run.id
                JOIN public."WorkflowEvidenceItem" AS item ON item."bundleId" = bundle.id
                JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                WHERE run.id = ?
                """,
                first.getRunId());
        assertThat(facts.get("kind", String.class)).isEqualTo("chat");
        assertThat(facts.get("policy", String.class))
                .isEqualTo("evidence.long_serial.answer.v1");
        assertThat(facts.get("resource_type", String.class)).isEqualTo("chapter_content");
        assertThat(facts.get("content_text", String.class)).isEqualTo(fixture.content());
        assertThat(facts.get("range_json", String.class)).isNull();
        assertThat(json.readTree(facts.get("step_input", String.class)))
                .isEqualTo(json.valueToTree(Map.of(
                        "userInstruction", "请执行 answer_question")));
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ? AND role = 'user'",
                        fixture.sessionId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                        first.getRunId()))
                .isZero();
    }

    @Test
    void 只读问答缺少会话时在创建Run前稳定拒绝() {
        Fixture fixture = fixture("route-v2-answer-no-session");
        ParsedWritingRunStartRequest request = longSerialRequest(
                fixture,
                "request-route-v2-answer-no-session-01",
                "answer_question",
                false);
        AtomicInteger probes = new AtomicInteger();

        assertThatThrownBy(() -> router(
                                fixture,
                                "allowlist",
                                () -> {
                                    probes.incrementAndGet();
                                    return false;
                                })
                        .start(fixture.userId(), request))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("WRITING_SESSION_REQUIRED");
                });
        assertThat(probes).hasValue(0);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?",
                        fixture.userId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?",
                        fixture.sessionId()))
                .isZero();
    }

    @Test
    void Catalog启用操作缺少Core启动Handler时装配立即失败() {
        LongSerialDurableRunStarter incomplete = new LongSerialDurableRunStarter() {
            @Override
            public Set<String> supportedOperationKeys() {
                return Set.of("long_serial.rewrite_chapter_selection");
            }

            @Override
            public WritingRunV2Response replayExisting(
                    String userId,
                    cn.inkforge.contracts.api.LongSerialStartWritingRunRequest request) {
                throw new AssertionError("装配失败前不应调用 handler");
            }

            @Override
            public WritingRunV2Response startFresh(
                    String userId,
                    cn.inkforge.contracts.api.LongSerialStartWritingRunRequest request,
                    Runnable finalFreshStartAuthorization) {
                throw new AssertionError("装配失败前不应调用 handler");
            }
        };

        assertThatThrownBy(() -> new RoutingWritingRunStarter(
                        database,
                        legacy,
                        incomplete,
                        new CommandIdempotencyStore(json, true),
                        (userId, novelId) -> {},
                        CoreSettings.from(Map.of(
                                "DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true",
                                "DURABLE_AGENT_EXECUTION_ROUTE_MODE", "off")),
                        () -> true,
                        json,
                        registry))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("long_serial.answer_question");
    }

    @Test
    void 冻结为只读的问答不会伪装成章节写入互斥() {
        Fixture fixture = fixture("route-v2-answer-read-only");
        WritingRunV2Response answer = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(),
                longSerialRequest(
                        fixture,
                        "request-answer-read-only-01",
                        "answer_question",
                        true));

        WritingRunV2Response rewrite = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(),
                requestWithoutSession(
                        fixture,
                        "request-rewrite-with-answer-01",
                        "并行冻结选区改写"));

        assertThat(answer.getOperation()).isEqualTo("answer_question");
        assertThat(rewrite.getOperation()).isEqualTo("rewrite_chapter_selection");
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(2);
    }

    @Test
    void V2重放返回按ordinal排序的全部活动Reviewer与冻结模型身份() {
        Fixture fixture = fixture("route-v2-active-reviewers");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-route-v2-reviewers-01", "请调整选区");
        WritingRunV2Response started = (WritingRunV2Response) router(fixture, "allowlist").start(
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
        var replay = router(legacyFixture, "allowlist")
                .start(legacyFixture.userId(), legacyRequest);

        assertThat(first).isInstanceOf(WritingRunResponse.class);
        assertThat(((WritingRunResponse) first).getEngineVersion()).isEqualTo(1);
        assertThat(((WritingRunResponse) replay).getId())
                .isEqualTo(((WritingRunResponse) first).getId());

        Fixture durableFixture = fixture("route-busy");
        router(durableFixture, "allowlist").start(
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
        router(fixture, "allowlist").start(
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

    @ParameterizedTest(name = "V1只读 operation={0}")
    @MethodSource("readOnlyV1Operations")
    void 不同WritingSession的只读V1与V2章节写入双向并存(String operation) {
        String token = operation.equals("answer_question") ? "answer" : "review";
        Fixture fixture = fixture("route-v1-" + token + "-durable-first");
        String durableSessionId = additionalSession(fixture, "v2");
        router(fixture, "allowlist").start(
                fixture.userId(),
                withWritingSession(
                        requestWithoutSession(
                                fixture,
                                "request-v2-before-" + token + "-01",
                                "先创建 V2 选区改写"),
                        durableSessionId));

        WritingRunStartResponse readOnly = router("off").start(
                fixture.userId(),
                longSerialRequest(
                        fixture,
                        "request-v1-after-" + token + "-01",
                        operation,
                        true));

        assertThat(readOnly).isInstanceOf(WritingRunResponse.class);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(1);

        Fixture readFirst = fixture("route-v1-" + token + "-read-first");
        router("off").start(
                readFirst.userId(),
                longSerialRequest(
                        readFirst,
                        "request-v1-first-" + token + "-01",
                        operation,
                        true));
        String reverseDurableSessionId = additionalSession(readFirst, "v2");
        WritingRunStartResponse durable = router(readFirst, "allowlist").start(
                readFirst.userId(),
                withWritingSession(
                        requestWithoutSession(
                                readFirst,
                                "request-v2-after-" + token + "-01",
                                "只读运行期间创建独立 V2 写任务"),
                        reverseDurableSessionId));
        assertThat(durable).isInstanceOf(WritingRunV2Response.class);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?",
                        readFirst.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        readFirst.chapterId()))
                .isEqualTo(1);
    }

    @Test
    void 同WritingSession跨引擎只允许一个foreground且只读审核也不豁免() {
        Fixture v2First = fixture("route-session-v2-first");
        router(v2First, "allowlist").start(
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
        assertThatThrownBy(() -> router(v1First, "allowlist").start(
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
        WritingRunV2Response firstV2 = (WritingRunV2Response) router(v2Fixture, "allowlist").start(
                v2Fixture.userId(), v2Request);
        AtomicInteger v2Probes = new AtomicInteger();
        WritingRunV2Response replayV2 = (WritingRunV2Response) router(
                        v2Fixture,
                        "allowlist",
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
                        v1Fixture,
                        "allowlist",
                        () -> {
                            v1Probes.incrementAndGet();
                            return false;
                        })
                .start(v1Fixture.userId(), v1Request);

        assertThat(replayV1.getId()).isEqualTo(firstV1.getId());
        assertThat(v1Probes).hasValue(0);
    }

    @Test
    void V1新建门禁位于幂等重放之后且早于readiness锁和任何写入() {
        Fixture existingFixture = fixture("route-v1-drain-replay");
        ParsedWritingRunStartRequest existingRequest = request(
                existingFixture, "request-v1-drain-replay-01", "先创建 V1");
        WritingRunResponse first = (WritingRunResponse) router("off").start(
                existingFixture.userId(), existingRequest);
        AtomicInteger replayProbes = new AtomicInteger();

        WritingRunResponse replay = (WritingRunResponse) router(
                        "off",
                        false,
                        () -> {
                            replayProbes.incrementAndGet();
                            return false;
                        })
                .start(existingFixture.userId(), existingRequest);

        assertThat(replay.getId()).isEqualTo(first.getId());
        assertThat(replayProbes).hasValue(0);

        Fixture freshFixture = fixture("route-v1-drain-fresh");
        ParsedWritingRunStartRequest freshRequest = request(
                freshFixture, "request-v1-drain-fresh-01", "不得创建 V1");
        AtomicInteger freshProbes = new AtomicInteger();
        long factsBefore = workflowFacts(freshFixture.userId());

        assertThatThrownBy(() -> router(
                                "off",
                                false,
                                () -> {
                                    freshProbes.incrementAndGet();
                                    return true;
                                })
                        .start(freshFixture.userId(), freshRequest))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code()).isEqualTo("AGENT_FRESH_STARTS_DRAINING");
                });

        assertThat(freshProbes).hasValue(0);
        assertThat(workflowFacts(freshFixture.userId())).isEqualTo(factsBefore);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?",
                        freshFixture.sessionId()))
                .isZero();
    }

    @Test
    void drain期间并发V1fresh请求全部封锁且不能留下幂等身份() throws Exception {
        Fixture fixture = fixture("route-v1-drain-concurrent");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-v1-drain-concurrent-01", "并发也不得创建");
        RoutingWritingRunStarter draining = router("off", false, () -> {
            throw new AssertionError("fresh V1 门禁之后不应探测 Agent");
        });

        CompletableFuture<Object> first = CompletableFuture.supplyAsync(() -> captureFailure(
                () -> draining.start(fixture.userId(), request)));
        CompletableFuture<Object> second = CompletableFuture.supplyAsync(() -> captureFailure(
                () -> draining.start(fixture.userId(), request)));

        assertThat(List.of(first.get(5, TimeUnit.SECONDS), second.get(5, TimeUnit.SECONDS)))
                .allSatisfy(value -> assertThat(value)
                        .isInstanceOfSatisfying(ApiException.class, error ->
                                assertThat(error.code())
                                        .isEqualTo("AGENT_FRESH_STARTS_DRAINING")));
        assertThat(workflowFacts(fixture.userId())).isZero();
    }

    @Test
    void 新V2在manifest握手失败时以503拒绝且零持久工作流事实() {
        Fixture fixture = fixture("route-manifest-mismatch");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-manifest-mismatch-01", "请调整选区");
        AtomicInteger probes = new AtomicInteger();

        assertThatThrownBy(() -> router(
                                fixture,
                                "allowlist",
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
    void freshV2发布Guard失败早于readiness且绝不回退V1() {
        Fixture fixture = fixture("route-release-guard-closed");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-release-guard-closed-01", "不得创建 V2");
        AtomicInteger guardChecks = new AtomicInteger();
        AtomicInteger readinessChecks = new AtomicInteger();
        DurableAgentReleaseGuard missingGuard = new FileDurableAgentReleaseGuard(
                null, CLOCK, registry.manifestFingerprint());

        assertThatThrownBy(() -> router(
                                fixture,
                                "allowlist",
                                true,
                                () -> {
                                    readinessChecks.incrementAndGet();
                                    return true;
                                },
                                (userId, novelId) -> {
                                    guardChecks.incrementAndGet();
                                    missingGuard.requireFreshStart(userId, novelId);
                                })
                        .start(fixture.userId(), request))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code())
                            .isEqualTo("DURABLE_AGENT_RELEASE_GUARD_UNAVAILABLE");
                    assertThat(error.details()).isNull();
                });

        assertThat(guardChecks).hasValue(1);
        assertThat(readinessChecks).hasValue(0);
        assertThat(workflowFacts(fixture.userId())).isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?",
                        fixture.novelId()))
                .isZero();
    }

    @Test
    void freshV2关键事务内二次Guard漂移时零写入() {
        Fixture fixture = fixture("route-release-guard-drift");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-release-guard-drift-01", "二检前替换 guard");
        AtomicInteger guardChecks = new AtomicInteger();
        AtomicInteger readinessChecks = new AtomicInteger();

        assertThatThrownBy(() -> router(
                                fixture,
                                "allowlist",
                                true,
                                () -> {
                                    readinessChecks.incrementAndGet();
                                    return true;
                                },
                                (userId, novelId) -> {
                                    if (guardChecks.incrementAndGet() == 2) {
                                        throw releaseGuardUnavailable();
                                    }
                                })
                        .start(fixture.userId(), request))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("DURABLE_AGENT_RELEASE_GUARD_UNAVAILABLE"));

        assertThat(guardChecks).hasValue(2);
        assertThat(readinessChecks).hasValue(1);
        assertThat(workflowFacts(fixture.userId())).isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?",
                        fixture.sessionId()))
                .isZero();
    }

    @Test
    void freshV2首检后等待数据库锁期间Guard关闭则最终校验零写入且不回退V1()
            throws Exception {
        Fixture fixture = fixture("route-release-guard-lock-wait");
        String clientRequestId = "request-release-guard-lock-wait-01";
        ParsedWritingRunStartRequest request = request(
                fixture, clientRequestId, "锁等待后不得穿透 guard");
        CountDownLatch lockHeld = new CountDownLatch(1);
        CountDownLatch releaseLock = new CountDownLatch(1);
        CountDownLatch readinessReached = new CountDownLatch(1);
        AtomicBoolean guardOpen = new AtomicBoolean(true);
        AtomicInteger guardChecks = new AtomicInteger();
        CompletableFuture<Void> blocker = CompletableFuture.runAsync(() ->
                database.transactionResult(transaction -> {
                    transaction.fetchOne(
                            "SELECT id FROM public.\"Novel\" WHERE id = ? FOR UPDATE",
                            fixture.novelId());
                    lockHeld.countDown();
                    try {
                        if (!releaseLock.await(2, TimeUnit.SECONDS)) {
                            throw new IllegalStateException("测试 advisory 锁未及时释放");
                        }
                    } catch (InterruptedException exception) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException("测试 advisory 锁等待被中断", exception);
                    }
                    return null;
                }));
        assertThat(lockHeld.await(2, TimeUnit.SECONDS)).isTrue();

        RoutingWritingRunStarter starter = router(
                fixture,
                "allowlist",
                true,
                () -> {
                    readinessReached.countDown();
                    return true;
                },
                (userId, novelId) -> {
                    guardChecks.incrementAndGet();
                    if (!guardOpen.get()) throw releaseGuardUnavailable();
                });
        CompletableFuture<Object> start = CompletableFuture.supplyAsync(() ->
                captureFailure(() -> starter.start(fixture.userId(), request)));
        assertThat(readinessReached.await(2, TimeUnit.SECONDS)).isTrue();
        assertThat(guardChecks).hasValue(1);
        long waitDeadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        boolean waitingOnOwnedResource = false;
        while (System.nanoTime() < waitDeadline) {
            int waiters = database.dsl()
                    .fetchOne(
                            """
                            SELECT count(*) AS count
                            FROM pg_catalog.pg_stat_activity
                            WHERE datname = pg_catalog.current_database()
                              AND wait_event_type = 'Lock'
                              AND query LIKE '%SELECT id FROM public."Novel"%'
                            """)
                    .get("count", Integer.class);
            if (waiters > 0) {
                waitingOnOwnedResource = true;
                break;
            }
            Thread.sleep(10);
        }
        assertThat(waitingOnOwnedResource).isTrue();
        guardOpen.set(false);
        releaseLock.countDown();

        blocker.get(2, TimeUnit.SECONDS);
        Object failure = start.get(2, TimeUnit.SECONDS);
        assertThat(failure)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("DURABLE_AGENT_RELEASE_GUARD_UNAVAILABLE"));
        assertThat(guardChecks).hasValue(2);
        assertThat(workflowFacts(fixture.userId())).isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?",
                        fixture.novelId()))
                .isZero();
    }

    @Test
    void 既有V2幂等重放早于失效发布Guard() {
        Fixture fixture = fixture("route-release-guard-replay");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-release-guard-replay-01", "先创建再重放");
        WritingRunV2Response first = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(), request);
        AtomicInteger guardChecks = new AtomicInteger();

        WritingRunV2Response replay = (WritingRunV2Response) router(
                        fixture,
                        "allowlist",
                        true,
                        () -> {
                            throw new AssertionError("幂等重放不应探测 Agent");
                        },
                        (userId, novelId) -> {
                            guardChecks.incrementAndGet();
                            throw releaseGuardUnavailable();
                        })
                .start(fixture.userId(), request);

        assertThat(replay.getRunId()).isEqualTo(first.getRunId());
        assertThat(guardChecks).hasValue(0);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?",
                        fixture.userId()))
                .isEqualTo(1);
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
        RoutingWritingRunStarter router = router(fixture, "allowlist", readiness);

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
        RoutingWritingRunStarter all = router(fixture, "allowlist", () -> {
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
                () -> startAfterGate(
                        router(fixture, "allowlist"),
                        fixture.userId(),
                        v2,
                        startersReady,
                        releaseStart));
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

    private static RoutingWritingRunStarter router(Fixture scope, String mode) {
        return router(scope, mode, () -> true);
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
        return router(null, mode, true, readiness, (userId, novelId) -> {});
    }

    private static RoutingWritingRunStarter router(
            Fixture scope,
            String mode,
            DurableAgentExecutionReadiness readiness) {
        return router(scope, mode, true, readiness, (userId, novelId) -> {});
    }

    private static RoutingWritingRunStarter router(
            String mode,
            boolean freshStartsEnabled,
            DurableAgentExecutionReadiness readiness) {
        return router(
                null,
                mode,
                freshStartsEnabled,
                readiness,
                (userId, novelId) -> {});
    }

    private static RoutingWritingRunStarter router(
            Fixture scope,
            String mode,
            boolean freshStartsEnabled,
            DurableAgentExecutionReadiness readiness,
            DurableAgentReleaseGuard releaseGuard) {
        Map<String, String> settings = new java.util.LinkedHashMap<>();
        settings.put("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true");
        settings.put("DURABLE_AGENT_EXECUTION_ROUTE_MODE", mode);
        settings.put(
                "V1_FRESH_AGENT_STARTS_ENABLED",
                Boolean.toString(freshStartsEnabled));
        if ("allowlist".equals(mode)) {
            if (scope == null) throw new IllegalArgumentException("allowlist 测试必须提供精确 scope");
            settings.put("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", scope.userId());
            settings.put("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", scope.novelId());
        }
        return new RoutingWritingRunStarter(
                database,
                legacy,
                durable,
                new CommandIdempotencyStore(json, true),
                releaseGuard,
                CoreSettings.from(settings),
                readiness,
                json,
                registry);
    }

    private static ApiException releaseGuardUnavailable() {
        return new ApiException(
                503,
                "DURABLE_AGENT_RELEASE_GUARD_UNAVAILABLE",
                "耐久 Agent 发布保护当前不可用");
    }

    private static Object captureFailure(java.util.concurrent.Callable<?> operation) {
        try {
            return operation.call();
        } catch (RuntimeException exception) {
            return exception;
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
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

    private static ParsedWritingRunStartRequest withWritingSession(
            ParsedWritingRunStartRequest request, String writingSessionId) {
        ((ParsedWritingRunStartRequest.LongSerial) request)
                .request()
                .writingSessionId(writingSessionId);
        return request;
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

    private static Stream<Arguments> readOnlyV1Operations() {
        return Stream.of(
                Arguments.of("answer_question"),
                Arguments.of("review_chapter"));
    }

    private static String additionalSession(Fixture fixture, String suffix) {
        String sessionId = fixture.sessionId() + "-" + suffix;
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                sessionId,
                fixture.novelId(),
                fixture.chapterId(),
                NOW,
                NOW);
        return sessionId;
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
