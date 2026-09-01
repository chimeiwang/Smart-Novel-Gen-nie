package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.WritingRunListItem;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.writing.domain.WritingRunCursor;
import cn.inkforge.core.writing.domain.WritingRunOutcomeProjector;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqWritingRunQueryRepositoryTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-08-25T01:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T07:00:00Z"), ZoneOffset.UTC);
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final ExecutionRegistry EXECUTION_REGISTRY =
            ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
    private static final ExecutionPlanSnapshot EXECUTION_PLAN =
            EXECUTION_REGISTRY.freezePlan(
                    "long_serial.rewrite_chapter_selection", false);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqWritingRunQueryRepository repository;
    private final List<String> users = new ArrayList<>();

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
        repository = new JooqWritingRunQueryRepository(
                database,
                new WritingRunStatusProjector(JSON, new WritingRunOutcomeProjector(), CLOCK),
                new WritingRunCursor(JSON),
                JSON,
                true);
    }

    @AfterEach
    void cleanup() {
        // V2 Run/Step 是数据库触发器保护的不可删除审计事实；使用唯一 fixture 留给临时容器整体销毁。
        // 只清理没有 V2 Run 的 V1 fixture，保证复用 task ID 的纯 V1 用例继续隔离。
        List<String> legacyUsers = users.stream()
                .filter(userId -> !Boolean.TRUE.equals(database.dsl().fetchValue(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM public."WorkflowRun"
                          WHERE "userId" = ? AND "engineVersion" = 2
                        )
                        """,
                        userId)))
                .toList();
        if (!legacyUsers.isEmpty()) {
            database.dsl().deleteFrom(NOVEL).where(NOVEL.USERID.in(legacyUsers)).execute();
            database.dsl().deleteFrom(USER).where(USER.ID.in(legacyUsers)).execute();
        }
        users.clear();
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 单任务读取执行归属校验并返回统一状态() {
        Fixture owner = fixture("writing-query-owner");
        Fixture other = fixture("writing-query-other");
        insertTask(owner, "task-1", NOW, null);
        insertCommand("task-1", "command-1", "review_chapter", "pending", NOW);

        var publicStatus = repository.getPublic(owner.userId(), "task-1");
        assertThat(publicStatus).isInstanceOf(WritingRunStatusResponse.class);
        WritingRunStatusResponse status = (WritingRunStatusResponse) publicStatus;

        assertThat(status.getEngineVersion()).isEqualTo(1);
        assertThat(status.getRunId()).isEqualTo("task-1");
        assertThat(status.getTaskId()).isEqualTo("task-1");
        assertThat(status.getOutcome().getState().getValue()).isEqualTo("queued");
        assertThatThrownBy(() -> repository.getPublic(other.userId(), "task-1"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("WRITING_TASK_FORBIDDEN");
                });
    }

    @Test
    void V2读取按持久身份投影完整生命周期且非法归属不回退V1() {
        Fixture owner = fixture("writing-query-v2-owner");
        Fixture other = fixture("writing-query-v2-other");
        insertV2Run(
                owner,
                "run-pending",
                "pending",
                "rewrite_chapter_selection",
                NOW,
                null,
                null,
                null);
        insertV2Step("run-pending", "step-pending", 1, "pending", NOW, null);
        insertV2Run(
                owner,
                "run-running",
                "running",
                "rewrite_chapter_selection",
                NOW.plusSeconds(1),
                owner.chapterId(),
                NOW.plusSeconds(2),
                null);
        insertV2Step(
                "run-running", "step-running", 1, "pending", NOW.plusSeconds(1), null);
        insertV2Step(
                "run-running", "step-completed", 2, "completed", NOW.plusSeconds(1), null);
        insertV2Run(
                owner,
                "run-waiting",
                "waiting_user",
                "rewrite_chapter_selection",
                NOW.plusSeconds(3),
                owner.chapterId(),
                null,
                null);
        insertV2Step(
                "run-waiting", "step-waiting", 1, "completed", NOW.plusSeconds(3), null);
        insertV2Artifact(
                owner, "run-waiting", "artifact-old", "under_review", 2, NOW.plusSeconds(3));
        insertV2Artifact(
                owner,
                "run-waiting",
                "artifact-waiting",
                "awaiting_user",
                3,
                NOW.plusSeconds(4));
        insertV2Run(
                owner,
                "run-completed",
                "completed",
                "rewrite_chapter_selection",
                NOW.plusSeconds(4),
                owner.chapterId(),
                null,
                null);
        insertV2Step(
                "run-completed", "step-completed-only", 1, "completed", NOW.plusSeconds(4), null);
        insertV2Run(
                owner,
                "run-failed",
                "failed",
                "rewrite_chapter_selection",
                NOW.plusSeconds(5),
                owner.chapterId(),
                null,
                "MODEL_OUTCOME_UNKNOWN");
        insertV2Step(
                "run-failed",
                "step-failed",
                1,
                "failed",
                NOW.plusSeconds(5),
                "MODEL_PROVIDER_TIMEOUT");
        insertV2Run(
                owner,
                "run-cancelled",
                "cancelled",
                "rewrite_chapter_selection",
                NOW.plusSeconds(6),
                owner.chapterId(),
                NOW.plusSeconds(7),
                null);
        insertV2Step(
                "run-cancelled", "step-cancelled", 1, "skipped", NOW.plusSeconds(6), null);
        insertV2Artifact(
                owner,
                "run-cancelled",
                "artifact-cancelled",
                "awaiting_user",
                1,
                NOW.plusSeconds(8));

        WritingRunV2Response pending = v2(owner.userId(), "run-pending");
        assertThat(pending.getEngineVersion()).isEqualTo(2);
        assertThat(pending.getRunId()).isEqualTo("run-pending");
        assertThat(pending.getTaskId()).isEqualTo("run-pending");
        assertThat(pending.getChapterId()).isNull();
        assertThat(pending.getCommandId()).isNull();
        assertThat(pending.getCommandStatus()).isNull();
        assertThat(pending.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.PENDING);
        assertThat(pending.getCurrentStep().getStepId()).isEqualTo("step-pending");
        var pendingJson = new ObjectMapper().valueToTree(pending);
        assertThat(pendingJson.has("chapterId")).isTrue();
        assertThat(pendingJson.get("chapterId").isNull()).isTrue();
        assertThat(pendingJson.has("commandId")).isTrue();
        assertThat(pendingJson.get("commandId").isNull()).isTrue();
        assertThat(pendingJson.has("commandStatus")).isTrue();
        assertThat(pendingJson.get("commandStatus").isNull()).isTrue();

        WritingRunV2Response running = v2(owner.userId(), "run-running");
        assertThat(running.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.RUNNING);
        assertThat(running.getCancelRequestedAt()).isNotNull();
        assertThat(running.getCurrentStep().getStepId()).isEqualTo("step-running");

        WritingRunV2Response waiting = v2(owner.userId(), "run-waiting");
        assertThat(waiting.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.WAITING_USER);
        assertThat(waiting.getArtifact().getArtifactId()).isEqualTo("artifact-waiting");
        assertThat(waiting.getArtifact().getArtifactRevision()).isEqualTo(3);
        assertThat(waiting.getArtifact().getActionable()).isTrue();
        assertThat(waiting.getArtifact().getReviewAvailability()).isNull();

        assertThat(v2(owner.userId(), "run-completed").getStatus())
                .isEqualTo(WritingRunV2Response.StatusEnum.COMPLETED);
        WritingRunV2Response failed = v2(owner.userId(), "run-failed");
        assertThat(failed.getError().getErrorCode()).isEqualTo("MODEL_OUTCOME_UNKNOWN");
        assertThat(failed.getError().getFailedStepId()).isEqualTo("step-failed");
        assertThat(failed.getError().getOutcomeUnknown()).isTrue();
        WritingRunV2Response cancelled = v2(owner.userId(), "run-cancelled");
        assertThat(cancelled.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.CANCELLED);
        assertThat(cancelled.getCancelRequestedAt()).isNotNull();
        assertThat(cancelled.getArtifact().getActionable()).isFalse();

        insertTask(owner, "identity-collision", NOW.minusSeconds(1), null);
        insertCommand(
                "identity-collision",
                "identity-collision-command",
                "plan_chapter",
                "pending",
                NOW.minusSeconds(1));
        insertV2Run(
                other,
                "identity-collision",
                "pending",
                "rewrite_chapter_selection",
                NOW,
                other.chapterId(),
                null,
                null);
        insertV2Step(
                "identity-collision",
                "identity-collision-step",
                1,
                "pending",
                NOW,
                null);
        assertThatThrownBy(() -> repository.getPublic(owner.userId(), "identity-collision"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("WRITING_TASK_FORBIDDEN");
                });
    }

    @Test
    void 混合列表按统一时间ID游标分页并映射V2过滤结果() {
        Fixture fixture = fixture("writing-query-mixed");
        insertTask(fixture, "task-v1", NOW, "session-mixed");
        insertCommand("task-v1", "command-v1", "review_chapter", "pending", NOW);
        insertV2Run(
                fixture,
                "z-run-completed-list",
                "completed",
                "rewrite_chapter_selection",
                NOW,
                fixture.chapterId(),
                null,
                null,
                "session-mixed");
        insertV2Step(
                "z-run-completed-list",
                "step-completed-list",
                1,
                "completed",
                NOW,
                null);
        insertV2Run(
                fixture,
                "run-pending-list",
                "pending",
                "rewrite_chapter_selection",
                NOW.plusSeconds(2),
                null,
                null,
                null);
        insertV2Step(
                "run-pending-list",
                "step-pending-list",
                1,
                "pending",
                NOW.plusSeconds(2),
                null);

        var first = repository.list(
                fixture.userId(), fixture.novelId(), null, null, null, null, null, 2);
        assertThat(first.getItems()).hasSize(2);
        assertThat(first.getItems().getFirst()).isInstanceOf(WritingRunV2Response.class);
        assertThat(((WritingRunV2Response) first.getItems().getFirst()).getRunId())
                .isEqualTo("run-pending-list");
        assertThat(((WritingRunV2Response) first.getItems().get(1)).getRunId())
                .isEqualTo("z-run-completed-list");
        assertThat(first.getNextCursor()).isNotNull();

        var second = repository.list(
                fixture.userId(),
                fixture.novelId(),
                null,
                null,
                null,
                null,
                first.getNextCursor(),
                2);
        assertThat(second.getItems()).singleElement().isInstanceOf(WritingRunListItem.class);
        assertThat(((WritingRunListItem) second.getItems().getFirst()).getTaskId())
                .isEqualTo("task-v1");
        assertThat(second.getNextCursor()).isNull();

        var queued = repository.list(
                fixture.userId(), fixture.novelId(), null, null,
                "rewrite_chapter_selection", "queued", null, 10);
        assertThat(queued.getItems())
                .singleElement()
                .satisfies(item -> assertThat(((WritingRunV2Response) item).getRunId())
                        .isEqualTo("run-pending-list"));
        var succeeded = repository.list(
                fixture.userId(), fixture.novelId(), fixture.chapterId(), null,
                "rewrite_chapter_selection", "succeeded", null, 10);
        assertThat(succeeded.getItems())
                .singleElement()
                .satisfies(item -> assertThat(((WritingRunV2Response) item).getRunId())
                        .isEqualTo("z-run-completed-list"));
        var sameSession = repository.list(
                fixture.userId(), fixture.novelId(), null, "session-mixed",
                null, null, null, 10);
        assertThat(sameSession.getItems())
                .extracting(item -> item instanceof WritingRunV2Response v2
                        ? v2.getRunId()
                        : ((WritingRunListItem) item).getTaskId())
                .containsExactly("z-run-completed-list", "task-v1");
    }

    @Test
    void 列表按创建时间和ID稳定倒序且保留无会话任务() {
        Fixture fixture = fixture("writing-query-list");
        insertTask(fixture, "task-older", NOW, "session-1");
        insertTask(fixture, "task-newer", NOW.plusSeconds(1), null);
        insertCommand("task-older", "command-older", "plan_chapter", "pending", NOW);
        insertCommand(
                "task-newer", "command-newer", "review_chapter", "pending", NOW.plusSeconds(1));

        var response = repository.list(
                fixture.userId(), fixture.novelId(), null, null, null, null, null, 10);

        assertThat(response.getItems())
                .allSatisfy(item -> assertThat(item).isInstanceOf(WritingRunListItem.class))
                .extracting(item -> ((WritingRunListItem) item).getTaskId())
                .containsExactly("task-newer", "task-older");
        WritingRunListItem first = (WritingRunListItem) response.getItems().getFirst();
        assertThat(first.getEngineVersion()).isEqualTo(1);
        assertThat(first.getRunId()).isEqualTo(first.getTaskId());
        assertThat(first.getWritingSessionId()).isNull();
        assertThat(response.getNextCursor()).isNull();
    }

    @Test
    void 派生操作和结果过滤支持严格游标续页() {
        Fixture fixture = fixture("writing-query-filter");
        insertTask(fixture, "task-1", NOW, null);
        insertTask(fixture, "task-2", NOW.plusSeconds(1), null);
        insertTask(fixture, "task-3", NOW.plusSeconds(2), null);
        insertCommand("task-1", "command-1", "plan_chapter", "pending", NOW);
        insertCommand("task-2", "command-2", "plan_chapter", "pending", NOW.plusSeconds(1));
        insertCommand("task-3", "command-3", "review_chapter", "pending", NOW.plusSeconds(2));

        var first = repository.list(
                fixture.userId(),
                fixture.novelId(),
                null,
                null,
                "plan_chapter",
                "queued",
                null,
                1);
        assertThat(first.getItems())
                .extracting(item -> ((WritingRunListItem) item).getTaskId())
                .containsExactly("task-2");
        assertThat(first.getNextCursor()).isNotNull();

        var second = repository.list(
                fixture.userId(),
                fixture.novelId(),
                null,
                null,
                "plan_chapter",
                "queued",
                first.getNextCursor(),
                1);
        assertThat(second.getItems())
                .extracting(item -> ((WritingRunListItem) item).getTaskId())
                .containsExactly("task-1");
        assertThat(second.getNextCursor()).isNull();
    }

    @Test
    void 列表拒绝未知过滤值和非规范游标() {
        Fixture fixture = fixture("writing-query-invalid");
        assertThatThrownBy(() -> repository.list(
                        fixture.userId(), fixture.novelId(), null, null,
                        "unknown", null, null, 10))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("VALIDATION_ERROR"));
        assertThatThrownBy(() -> repository.list(
                        fixture.userId(), fixture.novelId(), null, null,
                        null, "unknown", null, 10))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("VALIDATION_ERROR"));
        assertThatThrownBy(() -> repository.list(
                        fixture.userId(), fixture.novelId(), null, null,
                        null, null, "e30=", 10))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_RUN_CURSOR_INVALID"));
    }

    private Fixture fixture(String prefix) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        users.add(userId);
        database.dsl().insertInto(USER)
                .set(USER.ID, userId)
                .set(USER.USERNAME, userId)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREDITBALANCEMICROS, 1_000_000L)
                .set(USER.CREATEDAT, NOW)
                .set(USER.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, prefix)
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, NOW)
                .set(NOVEL.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, "正文")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, NOW)
                .set(CHAPTER.UPDATEDAT, NOW)
                .execute();
        return new Fixture(userId, novelId, chapterId);
    }

    private void insertTask(
            Fixture fixture, String taskId, LocalDateTime createdAt, String sessionId) {
        if (sessionId != null
                && database.dsl().fetchCount(WRITINGSESSION, WRITINGSESSION.ID.eq(sessionId)) == 0) {
            database.dsl().insertInto(WRITINGSESSION)
                    .set(WRITINGSESSION.ID, sessionId)
                    .set(WRITINGSESSION.NOVELID, fixture.novelId())
                    .set(WRITINGSESSION.CHAPTERID, fixture.chapterId())
                    .set(WRITINGSESSION.PHASE, "idle")
                    .set(WRITINGSESSION.CREATEDAT, createdAt)
                    .set(WRITINGSESSION.UPDATEDAT, createdAt)
                    .execute();
        }
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, fixture.novelId())
                .set(WRITINGTASK.CHAPTERID, fixture.chapterId())
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "写作,编辑")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.WRITINGSESSIONID, sessionId)
                .set(WRITINGTASK.CREATEDAT, createdAt)
                .set(WRITINGTASK.UPDATEDAT, createdAt)
                .execute();
    }

    private void insertCommand(
            String taskId,
            String commandId,
            String operation,
            String status,
            LocalDateTime createdAt) {
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, commandId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, new ObjectMapper().writeValueAsString(Map.of(
                        "_inkforgeCommand", Map.of("schemaVersion", 1),
                        "job", Map.of(
                                "workflow", "long_serial",
                                "operation", operation,
                                "target", Map.of("type", "chapter", "id", "ignored"),
                                "scope", Map.of("kind", "chapter", "chapterId", "ignored")))))
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, "key-" + commandId)
                .set(WRITINGRUNCOMMAND.STATUS, status)
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, createdAt)
                .set(WRITINGRUNCOMMAND.CREATEDAT, createdAt)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, createdAt)
                .execute();
    }

    private WritingRunV2Response v2(String userId, String runId) {
        var response = repository.getPublic(userId, runId);
        assertThat(response).isInstanceOf(WritingRunV2Response.class);
        return (WritingRunV2Response) response;
    }

    private void insertV2Run(
            Fixture fixture,
            String runId,
            String status,
            String operation,
            LocalDateTime createdAt,
            String chapterId,
            LocalDateTime cancelRequestedAt,
            String errorCode) {
        insertV2Run(
                fixture,
                runId,
                status,
                operation,
                createdAt,
                chapterId,
                cancelRequestedAt,
                errorCode,
                null);
    }

    private void insertV2Run(
            Fixture fixture,
            String runId,
            String status,
            String operation,
            LocalDateTime createdAt,
            String chapterId,
            LocalDateTime cancelRequestedAt,
            String errorCode,
            String writingSessionId) {
        if (!EXECUTION_PLAN.operation().operation().equals(operation)) {
            throw new IllegalArgumentException("V2 fixture operation 与冻结计划不一致");
        }
        boolean terminal = Set.of("completed", "failed", "cancelled").contains(status);
        String cancelRequestId = cancelRequestedAt == null ? null : "cancel-" + runId;
        String targetType = chapterId == null ? null : "chapter_content";
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowRun" (
                  id, "novelId", "chapterId", "userId", kind, status,
                  "createdAt", "updatedAt", "engineVersion", workflow, operation,
                  "operationCatalogVersion", "writingSessionId", "idempotencyKey", "requestHash",
                  "targetType", "targetId", "budgetJson", "modelPolicyJson",
                  "lastEventSequence", revision, "cancelRequestId",
                  "cancelRequestedAt", "completedAt", "errorCode"
                ) VALUES (
                  ?, ?, ?, ?, CAST('chapter_generation' AS public."WorkflowRunKind"),
                  CAST(? AS public."WorkflowRunStatus"), ?, ?, 2, ?, ?,
                  ?, ?, ?, ?, ?, ?, '{}', ?, 7, 3, ?, ?, ?, ?
                )
                """,
                runId,
                fixture.novelId(),
                chapterId,
                fixture.userId(),
                status,
                createdAt,
                createdAt,
                EXECUTION_PLAN.operation().workflow(),
                operation,
                EXECUTION_PLAN.operationCatalogVersion(),
                writingSessionId,
                "idempotency-" + runId,
                "a".repeat(64),
                targetType,
                chapterId,
                JSON.writeValueAsString(EXECUTION_PLAN.stored()),
                cancelRequestId,
                cancelRequestedAt,
                terminal ? createdAt.plusSeconds(1) : null,
                errorCode);
    }

    private void insertV2Step(
            String runId,
            String stepId,
            int ordinal,
            String status,
            LocalDateTime createdAt,
            String errorCode) {
        boolean terminal = Set.of("completed", "failed", "skipped").contains(status);
        LocalDateTime nextAttemptAt = "pending".equals(status) ? createdAt : null;
        ExecutionPlanSnapshot.Step generator = EXECUTION_PLAN.generator();
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "nextAttemptAt",
                  "fencingToken", "idempotencyKey", "requestHash", "inputHash",
                  "modelProfile", "modelProfileVersion", "outputSchema",
                  "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt",
                  "completedAt", "errorCode"
                ) VALUES (
                  ?, ?, 'writing', CAST('agent' AS public."WorkflowStepType"),
                  CAST(? AS public."WorkflowStepStatus"), '{}', ?, ?, ?,
                  ?, 1, ?, 7, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                stepId,
                runId,
                status,
                createdAt,
                ordinal,
                generator.purpose(),
                generator.lane(),
                nextAttemptAt,
                "idempotency-" + stepId,
                "b".repeat(64),
                "c".repeat(64),
                generator.modelProfile().profile(),
                Integer.toString(generator.modelProfile().version()),
                generator.outputSchema().name(),
                Integer.toString(generator.outputSchema().version()),
                JSON.writeValueAsString(generator.stepBudget().stored()),
                createdAt,
                createdAt,
                terminal ? createdAt.plusSeconds(1) : null,
                errorCode);
    }

    private void insertV2Artifact(
            Fixture fixture,
            String runId,
            String artifactId,
            String status,
            int revision,
            LocalDateTime updatedAt) {
        database.dsl().execute(
                """
                INSERT INTO public."ReviewArtifact" (
                  id, "novelId", "chapterId", "workflowRunId", kind, status,
                  "payloadJson", revision, "createdAt", "updatedAt"
                ) VALUES (
                  ?, ?, ?, ?, CAST('chapter_draft' AS public."ReviewArtifactKind"),
                  CAST(? AS public."ReviewArtifactStatus"), '{}', ?, ?, ?
                )
                """,
                artifactId,
                fixture.novelId(),
                fixture.chapterId(),
                runId,
                status,
                revision,
                updatedAt.minusSeconds(1),
                updatedAt);
    }

    private static void executeSql(String path) throws Exception {
        ExecResult result = POSTGRES.execInContainer(
                "psql", "-v", "ON_ERROR_STOP=1",
                "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(),
                "-f", path);
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

    private record Fixture(String userId, String novelId, String chapterId) {}
}
