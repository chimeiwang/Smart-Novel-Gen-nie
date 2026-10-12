package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.jooq.Record;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqWorkflowStartRepositoryTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T01:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-09-01T01:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static JooqWorkflowStartRepository repository;
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
        repository = new JooqWorkflowStartRepository(
                database, new CuidV1Generator(CLOCK), CLOCK, json);
        registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        operation = registry.resolve("long_serial.rewrite_chapter_selection", false);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 单事务创建Run证据首Step和权威事件并保留显式Null() throws Exception {
        Fixture fixture = fixture("v2-start-one");
        WorkflowStartPlan plan = plan(
                fixture, "request-v2-start-0001", "a".repeat(64));

        var started = repository.start(plan);

        assertThat(started.replayed()).isFalse();
        assertThat(started.status()).isEqualTo("pending");
        assertThat(started.lastEventSequence()).isEqualTo(2);
        assertThat(started.revision()).isEqualTo(1);
        Record run = database.dsl().fetchOne(
                """
                SELECT "engineVersion", workflow, operation, status::text AS status,
                       input, "currentEvidenceBundleId", "lastEventSequence", revision
                FROM public."WorkflowRun" WHERE id = ?
                """,
                started.runId());
        assertThat(run).isNotNull();
        assertThat(run.get("engineVersion", Integer.class)).isEqualTo(2);
        assertThat(run.get("workflow", String.class)).isEqualTo("long_serial");
        assertThat(run.get("operation", String.class))
                .isEqualTo("rewrite_chapter_selection");
        assertThat(json.readTree(run.get("input", String.class))
                        .path("userInstruction").isNull())
                .isTrue();

        String bundleId = run.get("currentEvidenceBundleId", String.class);
        Record bundle = database.dsl().fetchOne(
                """
                SELECT "manifestJson", "manifestSha256", "totalBytes"
                FROM public."WorkflowEvidenceBundle" WHERE id = ?
                """,
                bundleId);
        JsonNode manifest = json.readTree(bundle.get("manifestJson", String.class));
        assertThat(manifest.path("itemCount").asInt()).isEqualTo(2);
        assertThat(manifest.path("items").get(1).path("exists").asBoolean()).isFalse();
        assertThat(bundle.get("manifestSha256", String.class)).matches("[0-9a-f]{64}");
        assertThat(bundle.get("totalBytes", Long.class)).isPositive();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvidenceItem\" "
                                + "WHERE \"bundleId\" = ?",
                        bundleId))
                .isEqualTo(2);

        Record step = database.dsl().fetchOne(
                """
                SELECT ordinal, purpose, lane, status::text AS status, "requestHash",
                       "inputHash", "outputSchema", "outputSchemaVersion", "fencingToken"
                FROM public."WorkflowStep" WHERE id = ?
                """,
                started.stepId());
        assertThat(step.get("ordinal", Integer.class)).isEqualTo(1);
        assertThat(step.get("purpose", String.class)).isEqualTo("generation");
        assertThat(step.get("lane", String.class)).isEqualTo("creative");
        assertThat(step.get("status", String.class)).isEqualTo("pending");
        assertThat(step.get("requestHash", String.class)).matches("[0-9a-f]{64}");
        assertThat(step.get("inputHash", String.class)).matches("[0-9a-f]{64}");
        assertThat(step.get("outputSchema", String.class))
                .isEqualTo("output.chapter_selection_replacement.v1");
        assertThat(step.get("outputSchemaVersion", String.class)).isEqualTo("1");
        assertThat(step.get("fencingToken", Long.class)).isZero();

        List<String> eventTypes = database.dsl().fetch(
                        """
                        SELECT "eventType" FROM public."WorkflowEvent"
                        WHERE "runId" = ? ORDER BY sequence
                        """,
                        started.runId())
                .getValues("eventType", String.class);
        assertThat(eventTypes).containsExactly("run_accepted", "evidence_ready");
    }

    @Test
    void 幂等重放不复制状态且冲突请求与前台并发均被拒绝() {
        Fixture fixture = fixture("v2-start-two");
        WorkflowStartPlan original = plan(
                fixture, "request-v2-start-0002", "b".repeat(64));

        var first = repository.start(original);
        var replay = repository.start(original);

        assertThat(replay.runId()).isEqualTo(first.runId());
        assertThat(replay.stepId()).isEqualTo(first.stepId());
        assertThat(replay.replayed()).isTrue();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowRun\" "
                                + "WHERE \"userId\" = ?",
                        fixture.userId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvent\" "
                                + "WHERE \"runId\" = ?",
                        first.runId()))
                .isEqualTo(2);

        WorkflowStartPlan changed = plan(
                fixture, "request-v2-start-0002", "c".repeat(64));
        assertThatThrownBy(() -> repository.start(changed))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));

        WorkflowStartPlan concurrent = plan(
                fixture, "request-v2-start-0003", "d".repeat(64));
        assertThatThrownBy(() -> repository.start(concurrent))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WORKFLOW_FOREGROUND_RUN_EXISTS"));
    }

    private static WorkflowStartPlan plan(
            Fixture fixture, String clientRequestId, String requestHash) {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("selectionStart", 1);
        input.put("selectionEnd", 2);
        input.put("selectedTextSha256", "e".repeat(64));
        input.put("userInstruction", null);
        return new WorkflowStartPlan(
                fixture.userId(),
                clientRequestId,
                requestHash,
                operation.operation().workflow(),
                operation.operation().operation(),
                "1",
                "chapter_generation",
                fixture.novelId(),
                fixture.chapterId(),
                fixture.sessionId(),
                "chapter_content",
                fixture.chapterId(),
                input,
                operation.operation().evidencePolicy(),
                List.of(
                        new WorkflowEvidenceItemPlan(
                                "chapter_content",
                                fixture.chapterId(),
                                true,
                                null,
                                OffsetDateTime.parse("2026-09-01T01:00:00Z"),
                                "甲😀乙",
                                null,
                                1,
                                2,
                                Map.of("source", "chapter")),
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

    private static int count(String sql, Object binding) {
        return database.dsl().fetchOne(sql, binding).get("count", Integer.class);
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
