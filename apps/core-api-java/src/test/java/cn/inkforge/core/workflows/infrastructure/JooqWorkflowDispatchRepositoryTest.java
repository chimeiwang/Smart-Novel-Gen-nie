package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.contracts.agent.ResolvedModelRef;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import org.jooq.Record;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
@Execution(ExecutionMode.SAME_THREAD)
class JooqWorkflowDispatchRepositoryTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T02:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-09-01T02:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static JooqWorkflowStartRepository starts;
    private static JooqWorkflowDispatchRepository dispatches;
    private static ExecutionRegistry registry;
    private static ExecutionRegistry.ResolvedOperation operation;

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
        json = new ObjectMapper();
        registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        operation = registry.resolve("long_serial.rewrite_chapter_selection", false);
        CuidV1Generator ids = new CuidV1Generator(CLOCK);
        starts = new JooqWorkflowStartRepository(database, ids, CLOCK, json);
        dispatches = new JooqWorkflowDispatchRepository(
                database, ids, CLOCK, json, registry, Duration.ofSeconds(30), 3);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @BeforeEach
    void releasePreviousTestCapacity() {
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('skipped' AS "WorkflowStepStatus"),
                    "activeJobId" = NULL, "leaseExpiresAt" = NULL,
                    "completedAt" = COALESCE("completedAt", GREATEST("createdAt", ?)),
                    "updatedAt" = GREATEST("createdAt", ?)
                WHERE status IN ('pending', 'running')
                """,
                NOW,
                NOW);
        database.dsl().execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('failed' AS "WorkflowRunStatus"),
                    "errorCode" = COALESCE("errorCode", 'TEST_CAPACITY_RELEASE'),
                    "completedAt" = COALESCE("completedAt", GREATEST("createdAt", ?)),
                    "updatedAt" = GREATEST("createdAt", ?)
                WHERE "engineVersion" = 2 AND status IN ('pending', 'running', 'waiting_user')
                """,
                NOW,
                NOW);
        database.dsl().execute(
                """
                UPDATE public."WritingRunCommand"
                SET status = 'failed', "updatedAt" = ?
                WHERE status IN ('pending', 'submitted', 'processing')
                """,
                NOW);
    }

    @Test
    void 首次领取与两类租约恢复原子换Fence且保持逻辑请求不变() throws Exception {
        Fixture fixture = fixture();
        var started = starts.start(plan(fixture));

        ExecutionStepRequest initial = dispatches.claimNext().orElseThrow();

        assertThat(initial.getDispatchMode())
                .isEqualTo(ExecutionStepRequest.DispatchModeEnum.INITIAL);
        assertThat(initial.getFencingToken()).isEqualTo(1);
        assertThat(initial.getJobId()).isNotBlank();
        assertThat(initial.getRunId()).isEqualTo(started.runId());
        assertThat(initial.getStepId()).isEqualTo(started.stepId());
        assertThat(initial.getNovelId()).isEqualTo(fixture.novelId());
        assertThat(initial.getRequestHash()).matches("[0-9a-f]{64}");
        assertThat(initial.getEvidenceBundle().getItems()).hasSize(2);
        assertThat(initial.getEvidenceBundle().getItems().getFirst().getContentText())
                .isEqualTo("甲😀乙");
        assertThat(initial.getEvidenceBundle().getItems().get(1).getExists()).isFalse();
        assertRequestHashes(initial);
        String initialQueuedPayload = database.dsl().fetchOne(
                        """
                        SELECT "payloadJson" FROM public."WorkflowEvent"
                        WHERE "runId" = ? AND "eventType" = 'step_queued'
                        ORDER BY sequence DESC LIMIT 1
                        """,
                        started.runId())
                .get("payloadJson", String.class);
        var initialQueued = json.readTree(initialQueuedPayload);
        assertThat(initialQueued.path("modelProfile").path("profile").asText())
                .isEqualTo(initial.getModelProfile().getProfile());
        assertThat(initialQueued.path("modelProfile").path("version").asInt())
                .isEqualTo(initial.getModelProfile().getVersion());
        assertThat(initialQueued.path("modelProfile").path("promptProfile").path("sha256").asText())
                .isEqualTo(initial.getModelProfile().getPromptProfile().getSha256());
        assertThat(initialQueued.has("resolvedModel")).isFalse();
        assertThat(dispatches.claimNext()).isEmpty();

        String fingerprint = WorkflowResolvedModel.fingerprint(
                "deployment.writer.chapter_selection.v1",
                "openai_compatible",
                "deepseek-v4-flash",
                "transport.deepseek-v4.v1",
                "endpoint.deepseek-official.v1",
                "chat_json_output_v1",
                "capability.deepseek-v4.chat-json.v1",
                "bounded",
                false);
        ResolvedModelRef resolved = new ResolvedModelRef()
                .capabilityVersion("capability.deepseek-v4.chat-json.v1")
                .deploymentFingerprint(fingerprint)
                .deploymentProfileKey("deployment.writer.chapter_selection.v1")
                .endpointProfile("endpoint.deepseek-official.v1")
                .model("deepseek-v4-flash")
                .provider("openai_compatible")
                .reasoningMode(ResolvedModelRef.ReasoningModeEnum.BOUNDED)
                .structuredOutputRoute(
                        ResolvedModelRef.StructuredOutputRouteEnum.CHAT_JSON_OUTPUT_V1)
                .supportsRequestIdempotency(false)
                .transportProfile("transport.deepseek-v4.v1");
        ExecutionStepAccepted accepted = new ExecutionStepAccepted(
                OffsetDateTime.parse("2026-09-01T02:00:00Z"),
                initial.getFencingToken(),
                initial.getJobId(),
                initial.getNovelId(),
                "2.0",
                initial.getRequestHash(),
                resolved,
                initial.getRunId(),
                ExecutionStepAccepted.StatusEnum.ACCEPTED,
                initial.getStepId());
        dispatches.recordAccepted(initial, accepted);
        String resolvedJson = database.dsl().fetchOne(
                        "SELECT \"resolvedModelJson\" FROM public.\"WorkflowStep\" WHERE id = ?",
                        started.stepId())
                .get("resolvedModelJson", String.class);
        assertThat(json.readTree(resolvedJson).path("supportsRequestIdempotency").asBoolean())
                .isFalse();

        expireLease(started.stepId(), "pending");
        ExecutionStepRequest pendingRecovery = dispatches.claimNext().orElseThrow();
        assertThat(pendingRecovery.getDispatchMode())
                .isEqualTo(ExecutionStepRequest.DispatchModeEnum.PENDING_RECOVERY);
        assertThat(pendingRecovery.getFencingToken()).isEqualTo(2);
        assertThat(pendingRecovery.getJobId()).isNotEqualTo(initial.getJobId());
        assertThat(pendingRecovery.getRequestHash()).isEqualTo(initial.getRequestHash());
        assertThat(pendingRecovery.getIdempotencyKey()).isEqualTo(initial.getIdempotencyKey());

        // 旧 accepted 在新 fence 后到达只能成为无操作，不得覆盖当前租约。
        dispatches.recordAccepted(initial, accepted);
        expireLease(started.stepId(), "running");
        ExecutionStepRequest runningRecovery = dispatches.claimNext().orElseThrow();
        assertThat(runningRecovery.getDispatchMode())
                .isEqualTo(ExecutionStepRequest.DispatchModeEnum.RUNNING_RECOVERY);
        assertThat(runningRecovery.getFencingToken()).isEqualTo(3);
        assertThat(runningRecovery.getRequestHash()).isEqualTo(initial.getRequestHash());

        var step = database.dsl().fetchOne(
                """
                SELECT "attemptCount", "fencingToken", "activeJobId"
                FROM public."WorkflowStep" WHERE id = ?
                """,
                started.stepId());
        assertThat(step.get("attemptCount", Integer.class)).isEqualTo(3);
        assertThat(step.get("fencingToken", Long.class)).isEqualTo(3L);
        assertThat(step.get("activeJobId", String.class)).isEqualTo(runningRecovery.getJobId());
        assertThat(database.dsl().fetch(
                        """
                        SELECT "eventType" FROM public."WorkflowEvent"
                        WHERE "runId" = ? ORDER BY sequence
                        """,
                        started.runId())
                .getValues("eventType", String.class))
                .containsExactly(
                        "run_accepted",
                        "evidence_ready",
                        "step_queued",
                        "step_queued",
                        "step_queued");
        for (Record event : database.dsl().fetch(
                """
                SELECT "payloadJson" FROM public."WorkflowEvent"
                WHERE "runId" = ? AND "eventType" = 'step_queued'
                ORDER BY sequence
                """,
                started.runId())) {
            var payload = json.readTree(event.get("payloadJson", String.class));
            assertThat(payload.path("modelProfile").path("profile").asText())
                    .isEqualTo(initial.getModelProfile().getProfile());
        }
    }

    @Test
    void Registry切换后旧Run保持旧计划而新Run冻结新计划() {
        Fixture oldFixture = fixture("registry-old");
        Fixture newFixture = fixture("registry-new");
        var oldRun = starts.start(plan(oldFixture, "registry-old-request", "creative"));
        var newRun = starts.start(plan(newFixture, "registry-new-request", "interactive"));
        ExecutionRegistry newRegistry = ExecutionRegistryFixtures.selectionOperationWithLane(
                ExecutionRegistry.Environment.TEST, "interactive");
        JooqWorkflowDispatchRepository switched = new JooqWorkflowDispatchRepository(
                database,
                new CuidV1Generator(CLOCK),
                CLOCK,
                json,
                newRegistry,
                Duration.ofSeconds(30),
                3);

        List<ExecutionStepRequest> requests = List.of(
                switched.claimNext().orElseThrow(), switched.claimNext().orElseThrow());
        assertThat(requests)
                .filteredOn(request -> request.getRunId().equals(oldRun.runId()))
                .singleElement()
                .extracting(request -> request.getLane().getValue())
                .isEqualTo("creative");
        assertThat(requests)
                .filteredOn(request -> request.getRunId().equals(newRun.runId()))
                .singleElement()
                .extracting(request -> request.getLane().getValue())
                .isEqualTo("interactive");
        assertThat(database.dsl().fetchOne(
                                """
                                SELECT "modelPolicyJson"::jsonb #>>
                                         '{plan,executionManifestFingerprint}' AS fingerprint
                                FROM public."WorkflowRun" WHERE id = ?
                                """,
                                newRun.runId())
                        .get("fingerprint", String.class))
                .isEqualTo(newRegistry.manifestFingerprint());
        assertThat(database.dsl().fetchOne(
                                """
                                SELECT "modelPolicyJson"::jsonb #>>
                                         '{plan,executionManifestFingerprint}' AS fingerprint
                                FROM public."WorkflowRun" WHERE id = ?
                                """,
                                oldRun.runId())
                        .get("fingerprint", String.class))
                .isNotEqualTo(newRegistry.manifestFingerprint());
    }

    @Test
    void 同小说不同Run并发只领取一个而不同小说仍可领取() throws Exception {
        Fixture first = fixture("mutex-first");
        Fixture second = sameNovelFixture(first, "mutex-second");
        var firstRun = starts.start(plan(first, "request-mutex-first"));
        var secondRun = starts.start(plan(second, "request-mutex-second"));
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch fire = new CountDownLatch(1);
        Optional<ExecutionStepRequest> left;
        Optional<ExecutionStepRequest> right;
        try (var pool = Executors.newFixedThreadPool(2)) {
            var leftFuture = pool.submit(() -> {
                ready.countDown();
                fire.await();
                return dispatches.claimNext();
            });
            var rightFuture = pool.submit(() -> {
                ready.countDown();
                fire.await();
                return dispatches.claimNext();
            });
            ready.await();
            fire.countDown();
            left = leftFuture.get();
            right = rightFuture.get();
        }
        assertThat(List.of(left, right).stream().filter(Optional::isPresent)).hasSize(1);
        String claimedRun = left.or(() -> right).orElseThrow().getRunId();
        assertThat(claimedRun).isIn(firstRun.runId(), secondRun.runId());

        Fixture otherNovel = fixture("mutex-other-novel");
        var otherRun = starts.start(plan(otherNovel, "request-mutex-other"));
        assertThat(dispatches.claimNext().orElseThrow().getRunId())
                .isEqualTo(otherRun.runId());
    }

    @Test
    void 两个Dispatcher竞争时全局ActiveLease不超过三且Creative最多两个()
            throws Exception {
        JooqWorkflowDispatchRepository other = new JooqWorkflowDispatchRepository(
                database,
                new CuidV1Generator(Clock.offset(CLOCK, Duration.ofMillis(1))),
                CLOCK,
                json,
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST),
                Duration.ofSeconds(30),
                3);
        starts.start(plan(fixture("capacity-interactive"), "capacity-interactive", "interactive"));
        starts.start(plan(fixture("capacity-creative-a"), "capacity-creative-a", "creative"));
        starts.start(plan(fixture("capacity-creative-b"), "capacity-creative-b", "creative"));
        starts.start(plan(fixture("capacity-creative-c"), "capacity-creative-c", "creative"));
        starts.start(plan(fixture("capacity-batch-a"), "capacity-batch-a", "batch_media"));
        starts.start(plan(fixture("capacity-batch-b"), "capacity-batch-b", "batch_media"));

        CountDownLatch ready = new CountDownLatch(6);
        CountDownLatch fire = new CountDownLatch(1);
        List<Optional<ExecutionStepRequest>> claimed = new java.util.ArrayList<>();
        try (var pool = Executors.newFixedThreadPool(6)) {
            var futures = java.util.stream.IntStream.range(0, 6)
                    .mapToObj(index -> pool.submit(() -> {
                        ready.countDown();
                        fire.await();
                        return (index % 2 == 0 ? dispatches : other).claimNext();
                    }))
                    .toList();
            ready.await();
            fire.countDown();
            for (var future : futures) claimed.add(future.get());
        }

        assertThat(claimed.stream().filter(Optional::isPresent)).hasSize(3);
        Record capacity = database.dsl().fetchOne(
                """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE lane = 'creative') AS creative
                FROM public."WorkflowStep"
                WHERE "activeJobId" IS NOT NULL AND "leaseExpiresAt" > ?
                """,
                NOW);
        assertThat(capacity.get("total", Long.class)).isEqualTo(3L);
        assertThat(capacity.get("creative", Long.class)).isLessThanOrEqualTo(2L);
    }

    @Test
    void 并发配置为一时所有车道与Reviewer共享唯一ActiveLease() {
        JooqWorkflowDispatchRepository serial = new JooqWorkflowDispatchRepository(
                database,
                new CuidV1Generator(CLOCK),
                CLOCK,
                json,
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST),
                Duration.ofSeconds(30),
                1);
        starts.start(plan(fixture("serial-interactive"), "serial-interactive", "interactive"));
        starts.start(plan(
                fixture("serial-creative"), "serial-creative-request", "creative"));
        starts.start(reviewPlan(fixture("serial-review"), "serial-review-request"));

        assertThat(serial.claimNext()).isPresent();
        assertThat(serial.claimNext()).isEmpty();
        assertThat(database.dsl()
                        .fetchOne(
                                """
                                SELECT count(*)::int AS count
                                FROM public."WorkflowStep"
                                WHERE "activeJobId" IS NOT NULL AND "leaseExpiresAt" > ?
                                """,
                                NOW)
                        .get("count", Integer.class))
                .isEqualTo(1);
    }

    @Test
    void 明确Admission饱和只对MatchingFence清Lease并按RetryAfter快速回队() {
        var started = starts.start(plan(
                fixture("admission-saturated"),
                "admission-saturated-request"));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();

        dispatches.recordAdmissionSaturated(request, Duration.ofSeconds(1));

        Record deferred = database.dsl().fetchOne(
                """
                SELECT "activeJobId", "leaseExpiresAt", "nextAttemptAt",
                       "attemptCount", "fencingToken"
                FROM public."WorkflowStep" WHERE id = ?
                """,
                started.stepId());
        assertThat(deferred.get("activeJobId", String.class)).isNull();
        assertThat(deferred.get("leaseExpiresAt", LocalDateTime.class)).isNull();
        assertThat(deferred.get("nextAttemptAt", LocalDateTime.class))
                .isEqualTo(NOW.plusSeconds(1));
        assertThat(deferred.get("attemptCount", Integer.class)).isEqualTo(1);
        assertThat(deferred.get("fencingToken", Long.class)).isEqualTo(1L);
        assertThat(dispatches.claimNext()).isEmpty();

        Clock afterRetry = Clock.offset(CLOCK, Duration.ofSeconds(2));
        JooqWorkflowDispatchRepository retrying = new JooqWorkflowDispatchRepository(
                database,
                new CuidV1Generator(afterRetry),
                afterRetry,
                json,
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST),
                Duration.ofSeconds(30),
                3);
        ExecutionStepRequest retried = retrying.claimNext().orElseThrow();
        assertThat(retried.getStepId()).isEqualTo(started.stepId());
        assertThat(retried.getFencingToken()).isEqualTo(2);
        assertThat(retried.getDispatchMode())
                .isEqualTo(ExecutionStepRequest.DispatchModeEnum.PENDING_RECOVERY);

        dispatches.recordAdmissionSaturated(request, Duration.ofSeconds(1));
        assertThat(database.dsl()
                        .fetchOne(
                                "SELECT \"activeJobId\" FROM public.\"WorkflowStep\" WHERE id = ?",
                                started.stepId())
                        .get("activeJobId", String.class))
                .isEqualTo(retried.getJobId());
    }

    @Test
    void Creative可借空槽但Interactive到达后下个释放槽优先归还() {
        starts.start(plan(fixture("borrow-creative-a"), "borrow-creative-a"));
        starts.start(plan(fixture("borrow-creative-b"), "borrow-creative-b"));
        starts.start(plan(fixture("borrow-creative-c"), "borrow-creative-c"));
        starts.start(plan(fixture("borrow-creative-d"), "borrow-creative-d"));

        List<ExecutionStepRequest> borrowed = java.util.stream.IntStream.range(0, 3)
                .mapToObj(ignored -> dispatches.claimNext().orElseThrow())
                .toList();
        assertThat(borrowed)
                .allSatisfy(value -> assertThat(value.getLane().getValue()).isEqualTo("creative"));
        assertThat(dispatches.claimNext()).isEmpty();

        starts.start(plan(
                fixture("borrow-interactive"), "borrow-interactive", "interactive"));
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('skipped' AS "WorkflowStepStatus"),
                    "activeJobId" = NULL, "leaseExpiresAt" = NULL,
                    "completedAt" = ?, "updatedAt" = ?
                WHERE id = ?
                """,
                NOW,
                NOW,
                borrowed.getFirst().getStepId());

        ExecutionStepRequest returned = dispatches.claimNext().orElseThrow();

        assertThat(returned.getLane().getValue()).isEqualTo("interactive");
    }

    @Test
    void 被小说互斥阻断的Interactive不妨碍其他小说Creative借满空槽() {
        Fixture activeNovel = fixture("blocked-waiter-active");
        starts.start(plan(activeNovel, "blocked-waiter-active"));
        assertThat(dispatches.claimNext()).isPresent();

        Fixture blocked = sameNovelFixture(activeNovel, "blocked-waiter-interactive");
        var blockedRun = starts.start(
                plan(blocked, "blocked-waiter-interactive", "interactive"));
        var firstBorrower = starts.start(
                plan(fixture("blocked-waiter-borrow-a"), "blocked-waiter-borrow-a"));
        var secondBorrower = starts.start(
                plan(fixture("blocked-waiter-borrow-b"), "blocked-waiter-borrow-b"));

        List<String> borrowedRunIds = List.of(
                dispatches.claimNext().orElseThrow().getRunId(),
                dispatches.claimNext().orElseThrow().getRunId());

        assertThat(borrowedRunIds)
                .containsExactlyInAnyOrder(firstBorrower.runId(), secondBorrower.runId());
        assertThat(borrowedRunIds).doesNotContain(blockedRun.runId());
    }

    @Test
    void Reviewer扇出最多占两个槽并给Creative留下领取机会() {
        starts.start(reviewPlan(fixture("review-cap-a"), "review-capacity-a"));
        starts.start(reviewPlan(fixture("review-cap-b"), "review-capacity-b"));
        starts.start(reviewPlan(fixture("review-cap-c"), "review-capacity-c"));
        starts.start(plan(
                fixture("review-cap-creative"), "review-capacity-creative"));

        List<ExecutionStepRequest> requests = java.util.stream.IntStream.range(0, 3)
                .mapToObj(ignored -> dispatches.claimNext().orElseThrow())
                .toList();

        assertThat(requests).filteredOn(value -> "review".equals(value.getPurpose())).hasSize(2);
        assertThat(requests)
                .filteredOn(value -> "generation".equals(value.getPurpose()))
                .singleElement()
                .extracting(value -> value.getLane().getValue())
                .isEqualTo("creative");
    }

    @Test
    void 等待超过五秒的Batch会在新前台任务之前获得共享槽() {
        var aged = starts.start(
                plan(fixture("aged-batch"), "aged-batch-request", "batch_media"));
        Clock later = Clock.offset(CLOCK, Duration.ofSeconds(6));
        JooqWorkflowStartRepository laterStarts = new JooqWorkflowStartRepository(
                database, new CuidV1Generator(later), later, json);
        var fresh = laterStarts.start(
                plan(fixture("fresh-interactive"), "fresh-interactive", "interactive"));
        JooqWorkflowDispatchRepository agedDispatcher = new JooqWorkflowDispatchRepository(
                database,
                new CuidV1Generator(later),
                later,
                json,
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST),
                Duration.ofSeconds(30),
                3);

        ExecutionStepRequest claimed = agedDispatcher.claimNext().orElseThrow();

        assertThat(claimed.getStepId()).isEqualTo(aged.stepId());
        assertThat(claimed.getLane().getValue()).isEqualTo("batch_media");
    }

    @Test
    void 活动V1命令阻止同小说V2派发() {
        Fixture fixture = fixture("mutex-legacy");
        database.dsl().execute(
                """
                INSERT INTO public."WritingTask" (
                  id, "novelId", "chapterId", "targetWordCount", "selectedAgents",
                  phase, "createdAt", "updatedAt", "writingSessionId"
                ) VALUES (?, ?, ?, 1000, '[]', CAST('idle' AS "WritingTaskPhase"), ?, ?, ?)
                """,
                "legacy-task-mutex",
                fixture.novelId(),
                fixture.chapterId(),
                NOW,
                NOW,
                fixture.sessionId());
        database.dsl().execute(
                """
                INSERT INTO public."WritingRunCommand" (
                  id, "taskId", kind, "payloadJson", "idempotencyKey", status,
                  "attemptCount", "nextAttemptAt", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'start', '{}', ?, 'pending', 0, ?, ?, ?)
                """,
                "legacy-command-mutex",
                "legacy-task-mutex",
                "legacy-idempotency-mutex",
                NOW,
                NOW,
                NOW);
        starts.start(plan(fixture, "request-v2-blocked-by-v1"));

        assertThat(dispatches.claimNext()).isEmpty();
    }

    @Test
    void 确定性提交拒绝同事务终结GenerationStep和Run() {
        Fixture fixture = fixture("dispatch-rejected");
        var started = starts.start(plan(fixture, "request-dispatch-rejected"));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();

        dispatches.recordRejected(request, "EXECUTION_SUBMIT_REJECTED_409");

        assertThat(database.dsl().fetchOne(
                        """
                        SELECT run.status::text AS run_status, run."errorCode" AS run_error,
                               step.status::text AS step_status, step."errorCode" AS step_error,
                               step."activeJobId"
                        FROM public."WorkflowRun" AS run
                        JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                        WHERE run.id = ? AND step.id = ?
                        """,
                        started.runId(),
                        started.stepId()))
                .satisfies(value -> {
                    assertThat(value.get("run_status", String.class)).isEqualTo("failed");
                    assertThat(value.get("step_status", String.class)).isEqualTo("failed");
                    assertThat(value.get("run_error", String.class))
                            .isEqualTo("EXECUTION_SUBMIT_REJECTED_409");
                    assertThat(value.get("step_error", String.class))
                            .isEqualTo("EXECUTION_SUBMIT_REJECTED_409");
                    assertThat(value.get("activeJobId", String.class)).isNull();
                });
        assertThat(database.dsl().fetch(
                                "SELECT \"eventType\" FROM public.\"WorkflowEvent\" WHERE \"runId\" = ? ORDER BY sequence",
                                started.runId())
                        .getValues("eventType", String.class))
                .endsWith("failed");
    }

    private static WorkflowStartPlan plan(Fixture fixture) {
        return plan(fixture, "request-v2-dispatch-0001");
    }

    private static WorkflowStartPlan plan(Fixture fixture, String requestId) {
        return plan(fixture, requestId, "creative");
    }

    private static WorkflowStartPlan plan(Fixture fixture, String requestId, String lane) {
        ExecutionRegistry planRegistry = ExecutionRegistryFixtures.selectionOperationWithLane(
                ExecutionRegistry.Environment.TEST, lane);
        ExecutionRegistry.ResolvedOperation planOperation =
                planRegistry.resolve("long_serial.rewrite_chapter_selection", false);
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("selectionStart", 1);
        input.put("selectionEnd", 2);
        input.put("userInstruction", null);
        return new WorkflowStartPlan(
                fixture.userId(),
                requestId,
                "a".repeat(64),
                "long_serial",
                "rewrite_chapter_selection",
                "1",
                "chapter_generation",
                fixture.novelId(),
                fixture.chapterId(),
                fixture.sessionId(),
                "chapter_content",
                fixture.chapterId(),
                input,
                planOperation.operation().evidencePolicy(),
                List.of(
                        new WorkflowEvidenceItemPlan(
                                "chapter_content",
                                fixture.chapterId(),
                                true,
                                null,
                                OffsetDateTime.parse("2026-09-01T02:00:00Z"),
                                "甲😀乙",
                                null,
                                1,
                                2,
                                Map.of()),
                        new WorkflowEvidenceItemPlan(
                                "chapter_outline",
                                fixture.chapterId() + ":outline",
                                false,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                Map.of("absenceReason", "not_created"))),
                planOperation.operation().runBudget(),
                ExecutionPlanSnapshot.freeze(
                        planRegistry.catalogVersion(),
                        planRegistry.manifestFingerprint(),
                        planOperation),
                new WorkflowInitialStepPlan(
                        "generation",
                        lane,
                        input,
                        planOperation.generatorProfile(),
                        planOperation.generatorStepBudget(),
                        planOperation.outputSchema()));
    }

    private static WorkflowStartPlan reviewPlan(Fixture fixture, String requestId) {
        ExecutionRegistry.ResolvedReviewer reviewer = operation.reviewers().getFirst();
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("selectionStart", 1);
        input.put("selectionEnd", 2);
        input.put("userInstruction", null);
        WorkflowStartPlan generation = plan(fixture, requestId, "interactive");
        return new WorkflowStartPlan(
                generation.userId(),
                generation.clientRequestId(),
                generation.requestHash(),
                generation.workflow(),
                generation.operation(),
                generation.operationCatalogVersion(),
                generation.runKind(),
                generation.novelId(),
                generation.chapterId(),
                generation.writingSessionId(),
                generation.targetType(),
                generation.targetId(),
                generation.normalizedInput(),
                operation.operation().reviewPolicy().evidencePolicy(),
                generation.evidenceItems(),
                generation.runBudget(),
                generation.executionPlan(),
                new WorkflowInitialStepPlan(
                        "review",
                        "interactive",
                        input,
                        reviewer.profile(),
                        reviewer.stepBudget(),
                        operation.reviewerOutputSchema()));
    }

    private static Fixture fixture() {
        return fixture("dispatch");
    }

    private static Fixture fixture(String prefix) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        String sessionId = prefix + "-session";
        database.dsl().execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'test', 500000000, ?, ?)
                """,
                userId,
                userId,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
                VALUES (?, '测试小说', ?, ?, ?)
                """,
                novelId,
                userId,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', '甲😀乙', 1, 'drafting', ?, ?)
                """,
                chapterId,
                novelId,
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
        return new Fixture(userId, novelId, chapterId, sessionId);
    }

    private static Fixture sameNovelFixture(Fixture base, String prefix) {
        String chapterId = prefix + "-chapter";
        String sessionId = prefix + "-session";
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '并行章节', '甲😀乙', 2, 'drafting', ?, ?)
                """,
                chapterId,
                base.novelId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                sessionId,
                base.novelId(),
                chapterId,
                NOW,
                NOW);
        return new Fixture(base.userId(), base.novelId(), chapterId, sessionId);
    }

    private static void expireLease(String stepId, String status) {
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST(? AS "WorkflowStepStatus"), "leaseExpiresAt" = ?
                WHERE id = ?
                """,
                status,
                NOW.minusSeconds(1),
                stepId);
    }

    private static void assertRequestHashes(ExecutionStepRequest request) {
        assertThat(request.getInputHash())
                .isEqualTo(ExecutionCanonicalJson.sha256(request.getInput()));
        Map<String, Object> requestMaterial = new LinkedHashMap<>();
        requestMaterial.put("runId", request.getRunId());
        requestMaterial.put("novelId", request.getNovelId());
        requestMaterial.put("stepId", request.getStepId());
        requestMaterial.put("idempotencyKey", request.getIdempotencyKey());
        requestMaterial.put("inputHash", request.getInputHash());
        requestMaterial.put("workflow", request.getWorkflow());
        requestMaterial.put("operation", request.getOperation());
        requestMaterial.put("purpose", request.getPurpose());
        requestMaterial.put("lane", request.getLane().getValue());
        requestMaterial.put(
                "evidenceManifest",
                Map.of(
                        "bundleId", request.getEvidenceBundle().getId(),
                        "bundleVersion", request.getEvidenceBundle().getVersion(),
                        "policyVersion", request.getEvidenceBundle().getPolicyVersion(),
                        "manifestSha256", request.getEvidenceBundle().getManifestSha256()));
        requestMaterial.put(
                "modelProfile",
                Map.of(
                        "profile", request.getModelProfile().getProfile(),
                        "version", request.getModelProfile().getVersion(),
                        "reasoningMode", request.getModelProfile().getReasoningMode().getValue(),
                        "deploymentProfileKey",
                        request.getModelProfile().getDeploymentProfileKey(),
                        "promptProfile",
                        Map.of(
                                "name",
                                request.getModelProfile().getPromptProfile().getName(),
                                "version",
                                request.getModelProfile().getPromptProfile().getVersion(),
                                "sha256",
                                request.getModelProfile().getPromptProfile().getSha256())));
        requestMaterial.put(
                "outputSchema",
                Map.of(
                        "name", request.getOutputSchema().getName(),
                        "version", request.getOutputSchema().getVersion(),
                        "sha256", request.getOutputSchema().getSha256(),
                        "jsonSchema", request.getOutputSchema().getJsonSchema()));
        requestMaterial.put(
                "budget",
                Map.of(
                        "maxModelCalls", request.getBudget().getMaxModelCalls(),
                        "maxInputTokens", request.getBudget().getMaxInputTokens(),
                        "maxPromptCacheMissTokens",
                        request.getBudget().getMaxPromptCacheMissTokens(),
                        "maxCompletionTokens", request.getBudget().getMaxCompletionTokens(),
                        "maxReasoningTokens", request.getBudget().getMaxReasoningTokens(),
                        "maxVisibleOutputTokens",
                        request.getBudget().getMaxVisibleOutputTokens(),
                        "maxCostMicros", request.getBudget().getMaxCostMicros(),
                        "maxWallClockSeconds",
                        request.getBudget().getMaxWallClockSeconds(),
                        "maxProviderRetries", request.getBudget().getMaxProviderRetries(),
                        "maxProtocolCorrections",
                        request.getBudget().getMaxProtocolCorrections()));
        requestMaterial.put("artifact", null);
        assertThat(request.getRequestHash())
                .isEqualTo(ExecutionCanonicalJson.sha256(requestMaterial));
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

    private record Fixture(String userId, String novelId, String chapterId, String sessionId) {}
}
