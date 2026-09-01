package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository.EventTailRequest;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository.RunKey;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.protocol.WorkflowEventPayloadCodec;
import jakarta.validation.Validation;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqWorkflowEventStreamRepositoryTest {

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
    private static jakarta.validation.ValidatorFactory validators;
    private static JooqWorkflowEventStreamRepository repository;
    private static JooqWorkflowStartRepository starts;
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
        validators = Validation.buildDefaultValidatorFactory();
        repository = new JooqWorkflowEventStreamRepository(
                database,
                new WorkflowEventPayloadCodec(json, validators.getValidator()),
                json);
        starts = new JooqWorkflowStartRepository(
                database, new CuidV1Generator(CLOCK), CLOCK, json);
        registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        operation = registry.resolve("long_serial.rewrite_chapter_selection", false);
    }

    @AfterAll
    static void closeResources() {
        if (validators != null) validators.close();
        if (database != null) database.close();
    }

    @Test
    void Snapshot基线和关联投影在只读事务形成且只回放更大序号() {
        Fixture fixture = fixture("sse-one");
        var started = starts.start(plan(fixture));

        var snapshot = repository.readSnapshot(fixture.userId(), started.runId())
                .orElseThrow()
                .frame();
        assertThat(snapshot.getBaseSequence()).isEqualTo(2);
        assertThat(snapshot.getSnapshot().getLastEventSequence()).isEqualTo(2);
        assertThat(snapshot.getSnapshot().getCurrentStep().getStepId())
                .isEqualTo(started.stepId());
        assertThat(repository.readAfter(fixture.userId(), started.runId(), 2, 100))
                .isEmpty();

        database.transactionResult(transaction -> {
            transaction.execute(
                    """
                    INSERT INTO public."WorkflowEvent" (
                      id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                    ) VALUES ('sse-event-3', ?, 3, 'step_queued', ?, 'sse:test:3', ?)
                    """,
                    started.runId(),
                    queuedPayload(),
                    NOW.plusSeconds(1));
            transaction.execute(
                    """
                    UPDATE public."WorkflowRun"
                    SET "lastEventSequence" = 3, revision = revision + 1, "updatedAt" = ?
                    WHERE id = ?
                    """,
                    NOW.plusSeconds(1),
                    started.runId());
            return null;
        });

        var replay = repository.readAfter(fixture.userId(), started.runId(), 2, 100);
        assertThat(replay).singleElement().satisfies(event -> {
            assertThat(event.getRunId()).isEqualTo(started.runId());
            assertThat(event.getSequence()).isEqualTo(3);
            assertThat(event.getEventType().getValue()).isEqualTo("step_queued");
        });
        assertThat(repository.readTail(fixture.userId(), started.runId()).lastEventSequence())
                .isEqualTo(3);
    }

    @Test
    void Snapshot从当前Fence的持久Progress恢复真实阶段且忽略旧Fence() {
        Fixture fixture = fixture("sse-progress-snapshot");
        var started = starts.start(plan(fixture));
        ExecutionRegistry.Profile profile = operation.generatorProfile();
        Map<String, Object> logical = modelProfile(profile);
        Map<String, Object> resolved = resolvedModel(profile);
        database.transactionResult(transaction -> {
            transaction.execute(
                    """
                    UPDATE public."WorkflowStep"
                    SET status = CAST('running' AS "WorkflowStepStatus"),
                        "attemptCount" = 1, "fencingToken" = 1,
                        "resolvedModelJson" = ?, "usageJson" = ?,
                        "lastProgressSequence" = 1,
                        "updatedAt" = ?
                    WHERE id = ? AND "runId" = ?
                    """,
                    json.writeValueAsString(resolved),
                    """
                    {"usageStatus":"partial","providerAttempts":1,
                     "protocolCorrections":0,"wallTimeMillis":17000}
                    """,
                    NOW.plusSeconds(1),
                    started.stepId(),
                    started.runId());
            transaction.execute(
                    """
                    INSERT INTO public."WorkflowEvent" (
                      id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                    ) VALUES ('sse-progress-event', ?, 3, 'step_progress', ?, 'progress:test:1', ?)
                    """,
                    started.runId(),
                    json.writeValueAsString(Map.of(
                            "stepId", started.stepId(),
                            "fencingToken", 1,
                            "progressSequence", 1,
                            "modelProfile", logical,
                            "resolvedModel", resolved,
                            "phase", "waiting_provider",
                            "elapsedSeconds", 17,
                            "waitingOnProvider", true,
                            "usageStatus", "partial")),
                    NOW.plusSeconds(1));
            transaction.execute(
                    """
                    UPDATE public."WorkflowRun"
                    SET status = CAST('running' AS "WorkflowRunStatus"),
                        "lastEventSequence" = 3, revision = revision + 1, "updatedAt" = ?
                    WHERE id = ?
                    """,
                    NOW.plusSeconds(1),
                    started.runId());
            return null;
        });

        var current = repository.readSnapshot(fixture.userId(), started.runId())
                .orElseThrow()
                .frame()
                .getSnapshot()
                .getCurrentStep();
        assertThat(current.getLatestProgress()).satisfies(progress -> {
            assertThat(progress.getProgressSequence()).isEqualTo(1);
            assertThat(progress.getPhase().getValue()).isEqualTo("waiting_provider");
            assertThat(progress.getElapsedSeconds()).isEqualTo(17);
            assertThat(progress.getWaitingOnProvider()).isTrue();
            assertThat(progress.getUsageStatus().getValue()).isEqualTo("partial");
        });

        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET "attemptCount" = 2, "fencingToken" = 2,
                    "lastProgressSequence" = NULL, "updatedAt" = ?
                WHERE id = ? AND "runId" = ?
                """,
                NOW.plusSeconds(2),
                started.stepId(),
                started.runId());
        assertThat(repository.readSnapshot(fixture.userId(), started.runId())
                        .orElseThrow()
                        .frame()
                        .getSnapshot()
                        .getCurrentStep()
                        .getLatestProgress())
                .isNull();
    }

    @Test
    void V2命中后越权不得回退且Run事件序号不一致必须失败关闭() {
        Fixture fixture = fixture("sse-two");
        var started = starts.start(plan(fixture));

        assertThatThrownBy(() -> repository.readSnapshot("other-user", started.runId()))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TASK_FORBIDDEN"));
        assertThat(repository.readSnapshot(fixture.userId(), "not-v2-id")).isEmpty();

        database.dsl().execute(
                "UPDATE public.\"WorkflowRun\" SET \"lastEventSequence\" = 3 WHERE id = ?",
                started.runId());
        assertThatThrownBy(() -> repository.readSnapshot(fixture.userId(), started.runId()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("WorkflowRun 与 WorkflowEvent 序号不一致");
    }

    @Test
    void Cancelled内部错误码不伪装成FailedSnapshot() {
        Fixture fixture = fixture("sse-cancelled");
        var started = starts.start(plan(fixture));
        database.transactionResult(transaction -> {
            // Step.cancelRequestId 通过复合 FK 绑定 Run，必须先在非终态 Run 上冻结取消身份。
            transaction.execute(
                    """
                    UPDATE public."WorkflowRun"
                    SET status = CAST('running' AS "WorkflowRunStatus"),
                        "cancelRequestId" = 'cancel-request-1',
                        "cancelRequestedAt" = ?, "updatedAt" = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    NOW.plusSeconds(1),
                    NOW.plusSeconds(1),
                    started.runId());
            transaction.execute(
                    """
                    UPDATE public."WorkflowStep"
                    SET status = CAST('skipped' AS "WorkflowStepStatus"),
                        "cancelRequestId" = 'cancel-request-1', "activeJobId" = NULL,
                        "leaseExpiresAt" = NULL, "completedAt" = ?, "updatedAt" = ?,
                        "errorCode" = 'RUN_CANCELLED'
                    WHERE id = ? AND "runId" = ? AND status = 'pending'
                    """,
                    NOW.plusSeconds(1),
                    NOW.plusSeconds(1),
                    started.stepId(),
                    started.runId());
            transaction.execute(
                    """
                    INSERT INTO public."WorkflowEvent" (
                      id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                    ) VALUES ('sse-cancelled-event', ?, 3, 'cancelled', ?, 'cancelled:test', ?)
                    """,
                    started.runId(),
                    """
                    {"cancelRequestId":"cancel-request-1","cancelledStepId":"%s"}
                    """.formatted(started.stepId()),
                    NOW.plusSeconds(1));
            transaction.execute(
                    """
                    UPDATE public."WorkflowRun"
                    SET status = CAST('cancelled' AS "WorkflowRunStatus"),
                        "cancelRequestId" = 'cancel-request-1',
                        "cancelRequestedAt" = ?, "completedAt" = ?,
                        "errorCode" = 'RUN_CANCELLED', "lastEventSequence" = 3,
                        revision = revision + 1, "updatedAt" = ?
                    WHERE id = ?
                    """,
                    NOW.plusSeconds(1),
                    NOW.plusSeconds(1),
                    NOW.plusSeconds(1),
                    started.runId());
            return null;
        });

        var snapshot = repository.readSnapshot(fixture.userId(), started.runId())
                .orElseThrow()
                .frame()
                .getSnapshot();
        assertThat(snapshot.getStatus()).isEqualTo(
                cn.inkforge.contracts.api.WorkflowRunSnapshot.StatusEnum.CANCELLED);
        assertThat(snapshot.getCancelRequestedAt()).isNotNull();
        assertThat(snapshot.getError()).isNull();
    }

    @Test
    void 多Run高水位与EventTail在一次PostgreSQL批次内公平返回() {
        Fixture firstFixture = fixture("sse-batch-first");
        Fixture secondFixture = fixture("sse-batch-second");
        var first = starts.start(plan(firstFixture));
        var second = starts.start(plan(secondFixture));
        RunKey firstKey = new RunKey(firstFixture.userId(), first.runId());
        RunKey secondKey = new RunKey(secondFixture.userId(), second.runId());

        Map<RunKey, cn.inkforge.core.workflows.application.WorkflowEventStreamRepository.TailState>
                initial = repository.readTails(List.of(firstKey, secondKey));
        assertThat(initial).containsOnlyKeys(firstKey, secondKey);
        assertThat(initial.values()).allSatisfy(tail ->
                assertThat(tail.lastEventSequence()).isEqualTo(2));

        database.transactionResult(transaction -> {
            insertQueuedEvent(transaction, "batch-first-event", first.runId(), "batch:first");
            insertQueuedEvent(transaction, "batch-second-event", second.runId(), "batch:second");
            transaction.execute(
                    """
                    UPDATE public."WorkflowRun"
                    SET "lastEventSequence" = 3, revision = revision + 1, "updatedAt" = ?
                    WHERE id IN (?, ?)
                    """,
                    NOW.plusSeconds(1),
                    first.runId(),
                    second.runId());
            return null;
        });

        var tails = repository.readTails(List.of(firstKey, secondKey));
        var events = repository.readEventTails(
                List.of(
                        new EventTailRequest(firstKey, 2, tails.get(firstKey).lastEventSequence()),
                        new EventTailRequest(secondKey, 2, tails.get(secondKey).lastEventSequence())),
                1);
        assertThat(events).containsOnlyKeys(firstKey, secondKey);
        assertThat(events.get(firstKey)).singleElement().satisfies(event ->
                assertThat(event.getSequence()).isEqualTo(3));
        assertThat(events.get(secondKey)).singleElement().satisfies(event ->
                assertThat(event.getSequence()).isEqualTo(3));
    }

    private static void insertQueuedEvent(
            org.jooq.DSLContext transaction,
            String eventId,
            String runId,
            String dedupeKey) {
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvent" (
                  id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                ) VALUES (?, ?, 3, 'step_queued', ?, ?, ?)
                """,
                eventId,
                runId,
                queuedPayload(),
                dedupeKey,
                NOW.plusSeconds(1));
    }

    private static String queuedPayload() {
        ExecutionRegistry.Profile profile =
                operation.reviewers().getFirst().profile();
        Map<String, Object> modelProfile = modelProfile(profile);
        return json.writeValueAsString(Map.of(
                "stepId", "step-test",
                "ordinal", 2,
                "purpose", "review",
                "lane", "interactive",
                "modelProfile", modelProfile,
                "attemptCount", 1,
                "fencingToken", 1,
                "reason", "review"));
    }

    private static Map<String, Object> modelProfile(ExecutionRegistry.Profile profile) {
        return Map.of(
                "profile", profile.key(),
                "version", profile.version(),
                "reasoningMode", profile.reasoningMode(),
                "deploymentProfileKey", profile.deploymentProfileKey(),
                "promptProfile", Map.of(
                        "name", profile.promptProfile().key(),
                        "version", profile.promptProfile().version(),
                        "sha256", profile.promptProfile().sha256()));
    }

    private static Map<String, Object> resolvedModel(ExecutionRegistry.Profile profile) {
        String fingerprint = WorkflowResolvedModel.fingerprint(
                profile.deploymentProfileKey(),
                "openai_compatible",
                "deepseek-v4-flash",
                "transport.deepseek-v4.v1",
                "endpoint.deepseek-official.v1",
                "chat_json_output_v1",
                "capability.deepseek-v4.chat-json.v1",
                profile.reasoningMode(),
                false);
        return Map.of(
                "deploymentProfileKey", profile.deploymentProfileKey(),
                "deploymentFingerprint", fingerprint,
                "provider", "openai_compatible",
                "model", "deepseek-v4-flash",
                "transportProfile", "transport.deepseek-v4.v1",
                "endpointProfile", "endpoint.deepseek-official.v1",
                "structuredOutputRoute", "chat_json_output_v1",
                "capabilityVersion", "capability.deepseek-v4.chat-json.v1",
                "reasoningMode", profile.reasoningMode(),
                "supportsRequestIdempotency", false);
    }

    private static WorkflowStartPlan plan(Fixture fixture) {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("selectionStart", 0);
        input.put("selectionEnd", 1);
        input.put("selectedTextSha256", "e".repeat(64));
        input.put("userInstruction", "改写");
        return new WorkflowStartPlan(
                fixture.userId(),
                "request-" + fixture.userId(),
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
                operation.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_content",
                        fixture.chapterId(),
                        true,
                        null,
                        OffsetDateTime.parse("2026-09-01T02:00:00Z"),
                        "甲乙",
                        null,
                        0,
                        1,
                        Map.of("source", "chapter"))),
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

    private static Fixture fixture(String prefix) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        String sessionId = prefix + "-session";
        database.dsl().execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'test', 1000000, ?, ?)
                """,
                userId, userId, NOW, NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                novelId, prefix, userId, NOW, NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', '甲乙', 1, 'drafting', ?, ?)
                """,
                chapterId, novelId, NOW, NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                sessionId, novelId, chapterId, NOW, NOW);
        return new Fixture(userId, novelId, chapterId, sessionId);
    }

    private static void executeSql(String path) throws Exception {
        ExecResult result = POSTGRES.execInContainer(
                "psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(), "-f", path);
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@" + POSTGRES.getHost() + ":" + POSTGRES.getFirstMappedPort()
                + "/" + POSTGRES.getDatabaseName();
    }

    private record Fixture(String userId, String novelId, String chapterId, String sessionId) {}
}
