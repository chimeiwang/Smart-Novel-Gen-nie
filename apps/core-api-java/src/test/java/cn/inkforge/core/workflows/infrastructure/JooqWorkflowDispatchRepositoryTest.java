package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.contracts.agent.ResolvedModelRef;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.application.WorkflowExecutionRejectedException;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.IntentExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowExecutionContext;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.domain.WorkflowIntentQuestion;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.protocol.ExecutionProtocolDateTime;
import cn.inkforge.core.workflows.protocol.WorkflowEventPayloadCodec;
import jakarta.validation.Validation;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
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
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.core.type.TypeReference;
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
    void 旧视频任务表退役后普通V2仍可领取且不查询已删表() {
        Fixture fixture = fixture("dispatch-post-video-retirement");
        starts.start(plan(fixture, "dispatch-post-video-retirement-request"));
        database.dsl().execute(
                "ALTER TABLE public.\"VideoAdaptationTask\" RENAME TO \"RetiredVideoAdaptationTaskForTest\"");
        try {
            ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
            assertThat(request.getWorkflow()).isEqualTo("long_serial");
            assertThat(request.getOperation()).isEqualTo("rewrite_chapter_selection");
        } finally {
            database.dsl().execute(
                    "ALTER TABLE public.\"RetiredVideoAdaptationTaskForTest\" RENAME TO \"VideoAdaptationTask\"");
        }
    }

    @Test
    void 自然SSE快照恢复未解析模型和完整待澄清问题() {
        String prefix = "intent-sse-question";
        IntentFixture fixture = intentFixture(prefix, null, "valid");
        try (var validators = Validation.buildDefaultValidatorFactory()) {
            var events = new JooqWorkflowEventStreamRepository(database,
                    new WorkflowEventPayloadCodec(json, validators.getValidator()), json);
            var first = events.readSnapshot(prefix + "-user", fixture.runId()).orElseThrow().frame().getSnapshot();
            assertThat(first.getOperation()).isNull();
            assertThat(first.getCurrentStep().getPurpose()).isEqualTo("resolve_intent");
            completeIntentResolverAndWait(fixture);
            insertQuestion(fixture, prefix + "-question", 2, "  确认生成草案？😀\n完整问题  ", "a".repeat(64), false);
            var waiting = events.readSnapshot(prefix + "-user", fixture.runId()).orElseThrow().frame().getSnapshot();
            assertThat(waiting.getActiveSteps()).isEmpty();
            assertThat(waiting.getArtifact()).isNull();
            assertThat(waiting.getClarification().getPrompt()).isEqualTo("  确认生成草案？😀\n完整问题  ");
            assertThat(waiting.getClarification().getDecisionStepId()).isEqualTo(prefix + "-question");
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"answer_question", "plan_chapter", "write_chapter"})
    void 自然SSE快照投影唯一已选业务操作但不改Run原身份(String operationName) {
        String prefix = "intent-sse-" + operationName;
        IntentFixture fixture = intentFixture(prefix, operationName, "valid");
        try (var validators = Validation.buildDefaultValidatorFactory()) {
            var events = new JooqWorkflowEventStreamRepository(database,
                    new WorkflowEventPayloadCodec(json, validators.getValidator()), json);
            var snapshot = events.readSnapshot(prefix + "-user", fixture.runId()).orElseThrow().frame().getSnapshot();
            assertThat(snapshot.getOperation()).isEqualTo(operationName);
            assertThat(snapshot.getCurrentStep().getPurpose()).isEqualTo("generation");
            assertThat(snapshot.getClarification()).isNull();
            assertThat(database.dsl().fetchValue("SELECT operation FROM public.\"WorkflowRun\" WHERE id = ?", fixture.runId())).isNull();
        }
    }

    @Test
    void 调用前业务六调用预算不被三次解析挤占且外层保留全部模型() {
        IntentFixture fixture = budgetFixture("intent-budget-six", 3, 6);
        reserveIntentGeneration(fixture);
        assertThat(database.dsl().fetchOne("SELECT count(*) FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                fixture.activeStepId()).get(0, Long.class)).isEqualTo(1L);
    }

    @Test
    void 外层仍有额度时第七个业务模型调用也必须被子预算拒绝() {
        IntentFixture fixture = budgetFixture("intent-budget-seven", 1, 7);
        assertThatThrownBy(() -> reserveIntentGeneration(fixture))
                .isInstanceOfSatisfying(WorkflowExecutionRejectedException.class,
                        error -> assertThat(error.errorCode()).isEqualTo("WORKFLOW_RUN_BUDGET_EXCEEDED"));
        assertThat(database.dsl().fetchOne("SELECT count(*) FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                fixture.activeStepId()).get(0, Long.class)).isEqualTo(0L);
    }

    @Test
    void 解析模型已发生超额用量不能从外层总预算中消失() {
        IntentFixture fixture = budgetFixture("intent-budget-outer", 1, 1);
        long overBudgetInputTokens = frozenRunMaxInputTokens(fixture) + 1;
        database.dsl().execute("UPDATE public.\"WorkflowStep\" SET \"usageJson\" = ? WHERE \"runId\" = ? AND purpose = 'resolve_intent'",
                json.writeValueAsString(Map.of("usageStatus", "partial", "inputTokens", overBudgetInputTokens,
                        "providerAttempts", 1, "protocolCorrections", 0, "wallTimeMillis", 1000)), fixture.runId());
        assertThatThrownBy(() -> reserveIntentGeneration(fixture))
                .isInstanceOfSatisfying(WorkflowExecutionRejectedException.class,
                        error -> assertThat(error.errorCode()).isEqualTo("WORKFLOW_RUN_BUDGET_EXCEEDED"));
    }

    @Test
    void 待澄清Reader完整恢复唯一问题并忽略非等待状态() {
        IntentFixture fixture = intentFixture("intent-reader-question", null, "valid");
        completeIntentResolverAndWait(fixture);
        String prompt = "  请确认是讨论还是生成正文？😀\r\n保留问题原文。  ";
        insertQuestion(fixture, "intent-reader-question-control", 2, prompt, "a".repeat(64), false);
        JooqWorkflowExecutionContextReader reader = new JooqWorkflowExecutionContextReader(json);
        assertThat(reader.pendingClarification(database.dsl(), fixture.runId(), "running")).isNull();
        var snapshot = reader.pendingClarification(database.dsl(), fixture.runId(), "waiting_user");
        assertThat(snapshot.getDecisionStepId()).isEqualTo("intent-reader-question-control");
        assertThat(snapshot.getClarificationCode()).isEqualTo("intent_ambiguous");
        assertThat(snapshot.getPrompt()).isEqualTo(prompt);
    }

    @ParameterizedTest
    @ValueSource(strings = {"duplicate", "bad_hash", "wrong_source"})
    void 待澄清Reader拒绝重复问题与损坏来源(String variant) {
        IntentFixture fixture = intentFixture("intent-reader-question-" + variant, null, "valid");
        completeIntentResolverAndWait(fixture);
        insertQuestion(fixture, fixture.runId() + "-question", 2, "请确认你的意图", "wrong_source".equals(variant) ? "b".repeat(64) : "a".repeat(64),
                "bad_hash".equals(variant));
        if ("duplicate".equals(variant)) insertQuestion(fixture, fixture.runId() + "-question-2", 3, "第二个问题", "a".repeat(64), false);
        JooqWorkflowExecutionContextReader reader = new JooqWorkflowExecutionContextReader(json);
        assertThatThrownBy(() -> reader.pendingClarification(database.dsl(), fixture.runId(), "waiting_user"))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 没有问题事实的作者等待不被误报为澄清() {
        IntentFixture fixture = intentFixture("intent-reader-artifact-only", null, "valid");
        completeIntentResolverAndWait(fixture);
        assertThat(new JooqWorkflowExecutionContextReader(json)
                .pendingClarification(database.dsl(), fixture.runId(), "waiting_user")).isNull();
    }

    @ParameterizedTest
    @ValueSource(strings = {"create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing"})
    void 新选择Reader从真实完整授权来源恢复结构化默认范围(String operation) {
        String key = "long_serial." + operation;
        ExecutionRegistry structured = ExecutionRegistryFixtures.structuredOperationEnabled(ExecutionRegistry.Environment.TEST, key);
        var intent = IntentExecutionPlanSnapshot.freeze(structured, List.of("long_serial.answer_question", key));
        IntentFixture fixture = intentFixture("intent-reader-structured-" + operation, operation, "valid", intent);
        WorkflowExecutionContext context = loadIntentContext(database.dsl(), fixture);
        assertThat(context.selection().schema()).isEqualTo("durable.intent-selection.v2");
        assertThat(context.selectedScope()).isEqualTo("manage_foreshadowing".equals(operation)
                ? Map.of("kind", "chapter", "chapterId", "intent-reader-structured-" + operation + "-chapter")
                : Map.of("kind", "novel"));
        assertThat(context.requireBusinessPlan().runBudget().maxModelCalls()).isEqualTo(4);
    }

    @ParameterizedTest
    @ValueSource(strings = {"content", "manifest", "metadata"})
    void 新选择Reader拒绝授权来源完整性漂移(String variant) {
        IntentFixture fixture = intentFixture("intent-reader-integrity-" + variant, "answer_question", "valid");
        assertThatThrownBy(() -> database.transactionResult(tx -> {
            // 仅在隔离 PostgreSQL 事务模拟存储损坏；预期异常回滚原行，不更改不可变触发器。
            tx.execute("SET LOCAL session_replication_role = replica");
            if ("manifest".equals(variant)) {
                tx.execute("UPDATE public.\"WorkflowEvidenceBundle\" SET \"manifestJson\" = '{}' WHERE id = ?", fixture.intentBundleId());
            } else {
                String column = "content".equals(variant) ? "contentJson" : "metadataJson";
                tx.execute("UPDATE public.\"WorkflowEvidenceItem\" SET \"" + column + "\" = '{}' WHERE \"bundleId\" = ?", fixture.intentBundleId());
            }
            return loadIntentContext(tx, fixture);
        })).isInstanceOf(IllegalStateException.class);
        assertThat(loadIntentContext(database.dsl(), fixture).effectiveOperation()).isEqualTo("answer_question");
    }

    @ParameterizedTest
    @ValueSource(strings = {"scope", "omitted", "duplicate", "foreign_novel"})
    void 授权内容即使自带正确哈希也不能扩大或遗漏冻结范围(String variant) {
        IntentFixture fixture = intentFixture("intent-reader-authorized-" + variant, "answer_question", "valid");
        assertThatThrownBy(() -> database.transactionResult(tx -> {
            // 仅测试故障注入重新计算存储指纹，验证语义身份检查不是只检查哈希格式。
            tx.execute("SET LOCAL session_replication_role = replica");
            var evidence = tx.fetchOne("SELECT \"contentJson\" FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\" = ?", fixture.intentBundleId());
            Map<String, Object> content = json.readValue(evidence.get("contentJson", String.class), new TypeReference<>() {});
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> available = (List<Map<String, Object>>) content.get("availableOperations");
            switch (variant) {
                case "scope" -> available.getFirst().put("scopeKind", "novel");
                case "omitted" -> available.removeFirst();
                case "duplicate" -> available.add(new LinkedHashMap<>(available.getFirst()));
                case "foreign_novel" -> content.put("novelId", "other-novel");
                default -> throw new AssertionError(variant);
            }
            rewriteIntentContent(tx, fixture, content);
            return loadIntentContext(tx, fixture);
        })).isInstanceOf(IllegalStateException.class);
    }

    private static WorkflowExecutionContext loadIntentContext(org.jooq.DSLContext tx, IntentFixture fixture) {
        Record run = tx.fetchOne("SELECT id, workflow, operation, \"operationCatalogVersion\", \"chapterId\", \"targetType\", \"targetId\", \"modelPolicyJson\" FROM public.\"WorkflowRun\" WHERE id = ?", fixture.runId());
        return new JooqWorkflowExecutionContextReader(json).load(tx, new WorkflowExecutionContext.RunIdentity(
                run.get("id", String.class), run.get("workflow", String.class), run.get("operation", String.class),
                run.get("operationCatalogVersion", String.class), run.get("chapterId", String.class),
                run.get("targetType", String.class), run.get("targetId", String.class)),
                json.readValue(run.get("modelPolicyJson", String.class), new TypeReference<>() {}));
    }

    private static void rewriteIntentContent(org.jooq.DSLContext tx, IntentFixture fixture, Map<String, Object> content) {
        String contentHash = ExecutionCanonicalJson.sha256(content);
        long byteCount = ExecutionCanonicalJson.bytes(content).length;
        Record bundle = tx.fetchOne("SELECT \"manifestJson\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ?", fixture.intentBundleId());
        Map<String, Object> manifest = json.readValue(bundle.get("manifestJson", String.class), new TypeReference<>() {});
        Map<String, Object> manifestItem = object(((List<?>) manifest.get("items")).getFirst());
        manifestItem.put("contentSha256", contentHash);
        manifestItem.put("byteCount", byteCount);
        tx.execute("UPDATE public.\"WorkflowEvidenceItem\" SET \"contentJson\" = ?, \"contentSha256\" = ?, \"byteCount\" = ? WHERE \"bundleId\" = ?",
                json.writeValueAsString(content), contentHash, byteCount, fixture.intentBundleId());
        tx.execute("UPDATE public.\"WorkflowEvidenceBundle\" SET \"manifestJson\" = ?, \"manifestSha256\" = ?, \"totalBytes\" = ? WHERE id = ?",
                json.writeValueAsString(manifest), ExecutionCanonicalJson.sha256(manifest), byteCount, fixture.intentBundleId());
    }

    @Test
    void 自然解析Step派发空操作且租约恢复保留输入和请求身份() {
        IntentFixture fixture = intentFixture("intent-dispatch-resolver", null, "valid");
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(fixture.runId());
        assertThat(request.getPurpose()).isEqualTo("resolve_intent");
        assertThat(request.getOperation()).isNull();
        assertThat(request.getModelProfile().getProfile()).isEqualTo("system.intent_resolver.v3");
        assertThat(request.getBudget().getMaxInputTokens()).isEqualTo(8000);
        assertThat(request.getEvidenceBundle().getId()).isEqualTo(fixture.intentBundleId());
        assertRequestHashes(request);

        expireLease(request.getStepId(), "pending");
        ExecutionStepRequest replay = dispatches.claimNext().orElseThrow();
        assertThat(replay.getDispatchMode().getValue()).isEqualTo("pending_recovery");
        assertThat(replay.getInputHash()).isEqualTo(request.getInputHash());
        assertThat(replay.getRequestHash()).isEqualTo(request.getRequestHash());
        assertThat(replay.getOperation()).isNull();
        assertThat(replay.getFencingToken()).isEqualTo(2);
    }

    @Test
    void 历史v1解析器持久后首次派发与租约恢复仍使用原冻结依赖() {
        IntentExecutionPlanSnapshot historical = historicalIntentPlan();
        IntentFixture fixture = intentFixture(
                "intent-dispatch-historical-v1", null, "valid", historical);

        ExecutionStepRequest initial = dispatches.claimNext().orElseThrow();
        assertThat(initial.getDispatchMode()).isEqualTo(ExecutionStepRequest.DispatchModeEnum.INITIAL);
        assertThat(initial.getOperation()).isNull();
        assertThat(initial.getModelProfile().getProfile()).isEqualTo("system.intent_resolver.v1");
        assertThat(initial.getModelProfile().getVersion()).isEqualTo(1);
        assertThat(initial.getModelProfile().getDeploymentProfileKey())
                .isEqualTo("deployment.system.intent_resolver.v1");
        assertThat(initial.getModelProfile().getPromptProfile().getName())
                .isEqualTo("prompt.system.intent_resolver.v1");
        assertThat(initial.getModelProfile().getPromptProfile().getVersion()).isEqualTo(1);
        assertThat(initial.getModelProfile().getPromptProfile().getSha256())
                .isEqualTo("4ebf30f06de85e21db42275f10e88a9ce309ee037dfebfd0fc921bfc77796f63");
        assertThat(initial.getOutputSchema().getName()).isEqualTo("output.proposed_command.v1");
        assertThat(initial.getOutputSchema().getVersion()).isEqualTo(1);
        assertThat(initial.getEvidenceBundle().getPolicyVersion()).isEqualTo("evidence.system.intent.v1");
        assertRequestHashes(initial);

        expireLease(initial.getStepId(), "pending");
        ExecutionStepRequest recovery = dispatches.claimNext().orElseThrow();
        assertThat(recovery.getDispatchMode())
                .isEqualTo(ExecutionStepRequest.DispatchModeEnum.PENDING_RECOVERY);
        assertThat(recovery.getFencingToken()).isEqualTo(2);
        assertThat(recovery.getInput()).isEqualTo(initial.getInput());
        assertThat(recovery.getInputHash()).isEqualTo(initial.getInputHash());
        assertThat(recovery.getRequestHash()).isEqualTo(initial.getRequestHash());
        assertThat(recovery.getModelProfile()).isEqualTo(initial.getModelProfile());
        assertThat(recovery.getOutputSchema()).isEqualTo(initial.getOutputSchema());
        assertRequestHashes(recovery);
    }

    @ParameterizedTest
    @ValueSource(strings = {"answer_question", "plan_chapter", "write_chapter"})
    void 同Run选择后的业务派发取所选子计划且数据库操作保持空(String selectedOperation) {
        IntentFixture fixture = intentFixture("intent-dispatch-" + selectedOperation, selectedOperation, "valid");
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        ExecutionPlanSnapshot business = registry.freezePlan("long_serial." + selectedOperation, false);
        assertThat(request.getRunId()).isEqualTo(fixture.runId());
        assertThat(request.getOperation()).isEqualTo(selectedOperation);
        assertThat(request.getPurpose()).isEqualTo("generation");
        assertThat(request.getModelProfile().getProfile()).isEqualTo(business.generator().modelProfile().profile());
        assertThat(request.getBudget().getMaxInputTokens()).isEqualTo(Math.toIntExact(business.generator().stepBudget().budget().maxInputTokens()));
        assertThat(request.getEvidenceBundle().getId()).isNotEqualTo(fixture.intentBundleId());
        assertRequestHashes(request);
        assertThat(database.dsl().fetchOne("SELECT operation FROM public.\"WorkflowRun\" WHERE id = ?", fixture.runId())
                .get("operation", String.class)).isNull();
    }

    @ParameterizedTest
    @ValueSource(strings = {"missing", "duplicate", "bad_hash", "wrong_target", "wrong_plan", "wrong_resolver", "pending_selection"})
    void 非唯一或绑定不符的选择不能派发且领取变更回滚(String variant) {
        IntentFixture fixture = intentFixture("intent-dispatch-invalid-" + variant, "write_chapter", variant);
        assertThatThrownBy(dispatches::claimNext).isInstanceOf(IllegalStateException.class);
        Record unchanged = database.dsl().fetchOne(
                "SELECT \"attemptCount\", \"fencingToken\", \"activeJobId\" FROM public.\"WorkflowStep\" WHERE id = ?",
                fixture.activeStepId());
        assertThat(unchanged.get("attemptCount", Integer.class)).isZero();
        assertThat(unchanged.get("fencingToken", Long.class)).isZero();
        assertThat(unchanged.get("activeJobId", String.class)).isNull();
        assertThat(database.dsl().fetchCount(database.dsl().selectFrom("public.\"WorkflowEvent\"")
                .where("\"runId\" = ?", fixture.runId()))).isZero();
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

    @Test
    @EnabledIfSystemProperty(named = "inkforge.execution.fixture.path", matches = ".+")
    void 输出AnswerQuestion实际ExecutionStepRequest跨语言临时Fixture() throws Exception {
        Fixture fixture = fixture("wire-golden-answer");
        ExecutionRegistry.ResolvedOperation answer =
                registry.resolve("long_serial.answer_question", false);
        Map<String, Object> input = Map.of("userInstruction", "这一段的叙事视角是什么？");
        WorkflowStartPlan plan = new WorkflowStartPlan(
                fixture.userId(),
                "wire-golden-answer-request-0001",
                "b".repeat(64),
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
                answer.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_content",
                        fixture.chapterId(),
                        true,
                        null,
                        OffsetDateTime.parse("2026-09-01T02:00:00.123Z"),
                        "甲😀乙",
                        null,
                        null,
                        null,
                        Map.of("role", "chapter_source"))),
                answer.operation().runBudget(),
                ExecutionPlanSnapshot.freeze(
                        registry.catalogVersion(), registry.manifestFingerprint(), answer),
                new WorkflowInitialStepPlan(
                        "generation",
                        answer.operation().lane(),
                        input,
                        answer.generatorProfile(),
                        answer.generatorStepBudget(),
                        answer.outputSchema()));
        starts.start(plan);
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        Path fixturePath = Path.of(System.getProperty("inkforge.execution.fixture.path"));

        Files.write(fixturePath, json.writeValueAsBytes(request));

        assertThat(Files.size(fixturePath)).isPositive();
        assertThat(request.getOperation()).isEqualTo("answer_question");
    }

    private static IntentFixture intentFixture(String prefix, String selectedOperation, String variant) {
        return intentFixture(
                prefix,
                selectedOperation,
                variant,
                IntentExecutionPlanSnapshot.freeze(registry,
                        List.of("long_serial.answer_question", "long_serial.plan_chapter", "long_serial.write_chapter")));
    }

    private static IntentFixture intentFixture(
            String prefix,
            String selectedOperation,
            String variant,
            IntentExecutionPlanSnapshot plan) {
        Fixture owner = fixture(prefix);
        String runId = prefix + "-run";
        String intentBundleId = prefix + "-intent-bundle";
        String resolverId = prefix + "-resolver";
        Map<String, Object> original = Map.of("userInstruction", "请帮我处理本章😀", "targetWordCount", 4000);
        database.dsl().execute("""
                INSERT INTO public."WorkflowRun" (
                  id, "novelId", "chapterId", "userId", kind, status, input, "sourceType", "sourceId",
                  "createdAt", "updatedAt", "engineVersion", workflow, operation, "operationCatalogVersion",
                  "writingSessionId", "idempotencyKey", "requestHash", "targetType", "targetId",
                  "budgetJson", "modelPolicyJson", "lastEventSequence", revision
                ) VALUES (?, ?, ?, ?, 'chat', 'pending', ?, 'chapter', ?, ?, ?, 2, 'long_serial', NULL,
                  ?, ?, ?, ?, 'chapter', ?, ?, ?, 0, 1)
                """, runId, owner.novelId(), owner.chapterId(), owner.userId(), json.writeValueAsString(original), owner.chapterId(),
                NOW, NOW, registry.catalogVersion(), owner.sessionId(), prefix + "-request", ExecutionCanonicalJson.sha256(original),
                owner.chapterId(), json.writeValueAsString(plan.runBudgetStored()), json.writeValueAsString(plan.stored()));
        Map<String, Object> intentContext = Map.of("workflow", "long_serial", "novelId", owner.novelId(),
                "chapterId", owner.chapterId(), "chapterTitle", "第一章", "availableOperations", plan.operationPlans().stream()
                        .map(child -> Map.of("operation", child.operation().operation(), "description", "当前授权创作操作",
                                "targetType", "chapter", "scopeKind", plan.scopeKindForOperation(child.operation().key()))).toList());
        String intentManifestHash = insertIntentEvidence(runId, intentBundleId, 1, owner.chapterId(),
                "intent_context", plan.resolver().evidencePolicy(), intentContext);
        insertIntentModelStep(runId, owner.novelId(), resolverId, 1, plan.resolver(),
                Map.of("userInstruction", "请帮我处理本章😀", "clarifications", List.of()),
                intentBundleId, 1, intentManifestHash, null, selectedOperation == null ? "pending" : "completed");
        if (selectedOperation == null) return new IntentFixture(runId, resolverId, intentBundleId);

        ExecutionPlanSnapshot business = plan.requireOperationPlan("long_serial." + selectedOperation);
        Map<String, Object> selection = new LinkedHashMap<>();
        selection.put("schema", plan.supportsNovelScopes() ? "durable.intent-selection.v2" : "durable.intent-selection.v1");
        selection.put("runId", runId);
        selection.put("operationKey", "long_serial." + selectedOperation);
        selection.put("operationPlanSha256", "wrong_plan".equals(variant) ? "0".repeat(64) : business.sha256());
        selection.put("resolverStepId", "wrong_resolver".equals(variant) ? "nonexistent-resolver" : resolverId);
        selection.put("resolverResultHash", "a".repeat(64));
        selection.put("intentEvidenceBundleId", intentBundleId);
        selection.put("targetType", "chapter");
        selection.put("targetId", "wrong_target".equals(variant) ? "other-chapter" : owner.chapterId());
        selection.put("scopeKind", plan.scopeKindForOperation(business.operation().key()));
        int controls = "missing".equals(variant) ? 0 : "duplicate".equals(variant) ? 2 : 1;
        for (int index = 0; index < controls; index++) {
            String id = prefix + "-selection-" + index;
            String status = "pending_selection".equals(variant) ? "pending" : "completed";
            database.dsl().execute("""
                    INSERT INTO public."WorkflowStep" (
                      id, "runId", "agentId", "stepType", status, input, "createdAt", ordinal, purpose, lane,
                      "attemptCount", "nextAttemptAt", "fencingToken", "idempotencyKey", "requestHash", "inputHash",
                      "submittedAt", "updatedAt", "completedAt"
                    ) VALUES (?, ?, 'core', 'persistence', CAST(? AS "WorkflowStepStatus"), ?, ?, ?, 'intent_selection',
                      'control', 0, ?, 0, ?, ?, ?, ?, ?, ?)
                    """, id, runId, status, json.writeValueAsString(selection), NOW, 2 + index, NOW, runId + "." + id,
                    ExecutionCanonicalJson.sha256(selection), "bad_hash".equals(variant) ? "0".repeat(64) : ExecutionCanonicalJson.sha256(selection),
                    NOW, NOW, "completed".equals(status) ? NOW : null);
        }
        String bundleId = prefix + "-business-bundle";
        String manifestHash = insertIntentEvidence(runId, bundleId, 2, owner.chapterId(), "business_context",
                business.generator().evidencePolicy(), Map.of("fixture", "业务来源由生产Evidence Planner冻结，此处只验派发选择"));
        String generationId = prefix + "-generation";
        insertIntentModelStep(runId, owner.novelId(), generationId, 4, business.generator(), original,
                bundleId, 2, manifestHash, selectedOperation, "pending");
        return new IntentFixture(runId, generationId, intentBundleId);
    }

    private static IntentExecutionPlanSnapshot historicalIntentPlan() {
        try (InputStream input = JooqWorkflowDispatchRepositoryTest.class.getResourceAsStream(
                "/historical-fixtures/intent-execution-plan-94a5298.json")) {
            if (input == null) throw new IllegalStateException("缺少 94a5298 历史自然计划向量");
            Map<String, Object> fixture = json.readValue(input, new TypeReference<>() {});
            return IntentExecutionPlanSnapshot.fromStored(object(fixture.get("snapshot")));
        } catch (IOException exception) {
            throw new IllegalStateException("读取 94a5298 历史自然计划向量失败", exception);
        }
    }

    private static String insertIntentEvidence(String runId, String bundleId, int version, String chapterId,
            String resourceType, String policy, Map<String, Object> content) {
        String itemId = bundleId + "-item";
        Map<String, Object> metadata = Map.of("role", resourceType);
        int bytes = ExecutionCanonicalJson.bytes(content).length;
        Map<String, Object> item = Map.of("itemId", itemId, "ordinal", 1, "resourceType", resourceType,
                "resourceId", chapterId, "exists", true, "contentType", "json", "contentSha256", ExecutionCanonicalJson.sha256(content),
                "byteCount", bytes, "metadata", metadata, "resourceUpdatedAt", ExecutionProtocolDateTime.format(NOW.atOffset(ZoneOffset.UTC)));
        Map<String, Object> manifest = Map.of("bundleId", bundleId, "bundleVersion", version, "itemCount", 1, "items", List.of(item));
        String hash = ExecutionCanonicalJson.sha256(manifest);
        database.dsl().execute("""
                INSERT INTO public."WorkflowEvidenceBundle" (id, "runId", version, "policyVersion", "manifestJson", "manifestSha256", "totalBytes", "createdAt")
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, bundleId, runId, version, policy, json.writeValueAsString(manifest), hash, bytes, NOW);
        database.dsl().execute("""
                INSERT INTO public."WorkflowEvidenceItem" (id, "bundleId", ordinal, "resourceType", "resourceId", exists,
                  "resourceUpdatedAt", "contentType", "contentJson", "contentSha256", "byteCount", "metadataJson")
                VALUES (?, ?, 1, ?, ?, TRUE, ?, 'json', ?, ?, ?, ?)
                """, itemId, bundleId, resourceType, chapterId, NOW, json.writeValueAsString(content), ExecutionCanonicalJson.sha256(content), bytes,
                json.writeValueAsString(metadata));
        return hash;
    }

    private static void insertIntentModelStep(String runId, String novelId, String stepId, int ordinal,
            ExecutionPlanSnapshot.Step step, Map<String, Object> input, String bundleId, int bundleVersion,
            String manifestHash, String operationName, String status) {
        String inputHash = ExecutionCanonicalJson.sha256(input);
        Map<String, Object> material = new LinkedHashMap<>();
        material.put("runId", runId);
        material.put("novelId", novelId);
        material.put("stepId", stepId);
        material.put("idempotencyKey", runId + "." + stepId);
        material.put("inputHash", inputHash);
        material.put("workflow", "long_serial");
        material.put("operation", operationName);
        material.put("purpose", step.purpose());
        material.put("lane", step.lane());
        material.put("evidenceManifest", Map.of("bundleId", bundleId, "bundleVersion", bundleVersion,
                "policyVersion", step.evidencePolicy(), "manifestSha256", manifestHash));
        material.put("modelProfile", step.modelProfile().toMap());
        material.put("outputSchema", step.outputSchema().toMap());
        material.put("budget", step.stepBudget().budgetMap());
        material.put("artifact", null);
        database.dsl().execute("""
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt", ordinal, purpose, lane,
                  "attemptCount", "nextAttemptAt", "fencingToken", "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                  "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt", "completedAt", "resultHash"
                ) VALUES (?, ?, ?, 'agent', CAST(? AS "WorkflowStepStatus"), ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, stepId, runId, step.modelProfile().profile(), status, json.writeValueAsString(input), NOW, ordinal, step.purpose(), step.lane(),
                NOW, runId + "." + stepId, ExecutionCanonicalJson.sha256(material), inputHash, bundleId,
                step.modelProfile().profile(), Integer.toString(step.modelProfile().version()), step.outputSchema().name(), Integer.toString(step.outputSchema().version()),
                json.writeValueAsString(step.stepBudget().stored()), NOW, NOW, "completed".equals(status) ? NOW : null,
                "completed".equals(status) ? "a".repeat(64) : null);
    }

    private record IntentFixture(String runId, String activeStepId, String intentBundleId) {}

    private static IntentFixture budgetFixture(String prefix, int resolverCount, int businessCount) {
        IntentFixture fixture = intentFixture(prefix, "write_chapter", "valid");
        var intent = IntentExecutionPlanSnapshot.freeze(registry, List.of("long_serial.answer_question", "long_serial.plan_chapter", "long_serial.write_chapter"));
        var business = intent.requireOperationPlan("long_serial.write_chapter");
        String novelId = prefix + "-novel";
        String intentHash = database.dsl().fetchOne("SELECT \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ?", fixture.intentBundleId()).get(0, String.class);
        String businessBundle = prefix + "-business-bundle";
        String businessHash = database.dsl().fetchOne("SELECT \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ?", businessBundle).get(0, String.class);
        for (int index = 1; index < resolverCount; index++) {
            insertIntentModelStep(fixture.runId(), novelId, prefix + "-extra-resolver-" + index, 10 + index,
                    intent.resolver(), Map.of("userInstruction", "完整意图", "clarifications", List.of()), fixture.intentBundleId(), 1, intentHash, null, "completed");
        }
        for (int index = 1; index < businessCount; index++) {
            // 保留真实 Writer/双 Reviewer 配比；第六个业务之外只增加一个 Reviewer，验证子预算独立生效。
            var step = index == 1 ? business.generator() : business.reviewers().get((index - 2) % 2);
            insertIntentModelStep(fixture.runId(), novelId, prefix + "-extra-business-" + index, 20 + index,
                    step, Map.of("fixture", "只验证已冻结Step的预算汇总"), businessBundle, 2, businessHash, "write_chapter", "completed");
        }
        database.dsl().execute("UPDATE public.\"WorkflowStep\" SET \"usageJson\" = ? WHERE \"runId\" = ? AND status = 'completed' AND \"modelProfile\" IS NOT NULL",
                json.writeValueAsString(Map.of("usageStatus", "unknown", "providerAttempts", 1, "protocolCorrections", 0, "wallTimeMillis", 1000)), fixture.runId());
        return fixture;
    }

    private static void reserveIntentGeneration(IntentFixture fixture) {
        var profile = registry.freezePlan("long_serial.write_chapter", false).generator().modelProfile();
        String fingerprint = WorkflowResolvedModel.fingerprint(profile.deploymentProfileKey(), "fake", "fake", "transport.fake.v1",
                "endpoint.local-fake.v1", "responses_json_schema_v1", "capability.fake.structured-output.v1", profile.reasoningMode(), true);
        var resolved = new WorkflowResolvedModel(profile.deploymentProfileKey(), fingerprint, "fake", "fake", "transport.fake.v1",
                "endpoint.local-fake.v1", "responses_json_schema_v1", "capability.fake.structured-output.v1", profile.reasoningMode(), true);
        database.dsl().execute("UPDATE public.\"WorkflowStep\" SET \"resolvedModelJson\" = ? WHERE id = ?",
                json.writeValueAsString(WorkflowCallbackValues.resolvedModelMap(resolved)), fixture.activeStepId());
        var coordinator = new WorkflowBillingCoordinator(new CuidV1Generator(CLOCK), json, registry);
        database.transactionResult(tx -> { coordinator.reserve(tx, fixture.runId(), fixture.activeStepId(), resolved, NOW); return null; });
    }

    private static long frozenRunMaxInputTokens(IntentFixture fixture) {
        String budgetJson = database.dsl().fetchOne(
                "SELECT \"budgetJson\" FROM public.\"WorkflowRun\" WHERE id = ?",
                fixture.runId()).get("budgetJson", String.class);
        Map<String, Object> budget = json.readValue(budgetJson, new TypeReference<>() {});
        return ((Number) budget.get("maxInputTokens")).longValue();
    }

    private static void completeIntentResolverAndWait(IntentFixture fixture) {
        database.dsl().execute("""
                UPDATE public."WorkflowStep" SET status = 'completed', "resultHash" = ?, "completedAt" = ? WHERE id = ?
                """, "a".repeat(64), NOW, fixture.activeStepId());
        database.dsl().execute("UPDATE public.\"WorkflowRun\" SET status = 'waiting_user' WHERE id = ?", fixture.runId());
    }

    private static void insertQuestion(IntentFixture fixture, String questionId, int ordinal, String prompt, String resultHash, boolean invalidHash) {
        WorkflowIntentQuestion question = new WorkflowIntentQuestion(fixture.runId(), fixture.activeStepId(), resultHash,
                fixture.intentBundleId(), "intent_ambiguous", prompt);
        database.dsl().execute("""
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt", ordinal, purpose, lane,
                  "attemptCount", "fencingToken", "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                  "submittedAt", "updatedAt", "completedAt"
                ) VALUES (?, ?, 'core', 'user_confirmation', 'completed', ?, ?, ?, 'intent_clarification', 'control',
                  0, 0, ?, ?, ?, ?, ?, ?, ?)
                """, questionId, fixture.runId(), json.writeValueAsString(question.stored()), NOW, ordinal,
                fixture.runId() + "." + questionId, question.inputHash(), invalidHash ? "0".repeat(64) : question.inputHash(),
                fixture.intentBundleId(), NOW, NOW, NOW);
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

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }

    private record Fixture(String userId, String novelId, String chapterId, String sessionId) {}
}
