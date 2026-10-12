package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.BillingReconciliationReceipt;
import cn.inkforge.contracts.api.BillingReconciliationRequest;
import cn.inkforge.contracts.api.StepUsage;
import cn.inkforge.core.billing.application.BillingRepository;
import cn.inkforge.core.billing.application.ChargeUsage;
import cn.inkforge.core.billing.application.UsageConflictException;
import cn.inkforge.core.billing.domain.BillingPricing;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.WorkflowBillingReconciliationService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import java.nio.charset.StandardCharsets;
import java.lang.reflect.Constructor;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import org.jooq.Record;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.openapitools.jackson.nullable.JsonNullable;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
@Execution(ExecutionMode.SAME_THREAD)
class JooqWorkflowBillingReconciliationRepositoryTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T06:00:00.000");
    private static final OffsetDateTime API_NOW = OffsetDateTime.parse("2026-09-01T06:00:00Z");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-09-01T06:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static ExecutionRegistry registry;
    private static ExecutionRegistry.ResolvedOperation operation;
    private static JooqWorkflowStartRepository starts;
    private static WorkflowBillingReconciliationService reconciliations;

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
        reconciliations = new WorkflowBillingReconciliationService(
                new JooqWorkflowBillingReconciliationRepository(
                        database, ids, CLOCK, json, registry));
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void exactUsage按冻结价格原子结算且相同请求并发幂等() throws Exception {
        State state = state("reconcile-exact", 5_000_000L, 500_000L, partialUsage());
        BillingReconciliationRequest request = exactRequest(state, "reconciliation-exact");
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var first = executor.submit(() -> {
                ready.countDown();
                start.await();
                return reconciliations.reconcile(request);
            });
            var second = executor.submit(() -> {
                ready.countDown();
                start.await();
                return reconciliations.reconcile(request);
            });
            ready.await();
            start.countDown();
            List<BillingReconciliationReceipt> receipts = List.of(first.get(), second.get());
            assertThat(receipts).extracting(BillingReconciliationReceipt::getDuplicate)
                    .containsExactlyInAnyOrder(false, true);
        }

        long expectedCharge = 180_400L;
        assertThat(reservation(state).get("status", String.class)).isEqualTo("settled");
        assertThat(reservation(state).get("chargedMicros", Long.class))
                .isEqualTo(expectedCharge);
        assertThat(balance(state.userId())).isEqualTo(5_000_000L - expectedCharge);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"requestId\" = ?",
                        state.reservationRequestId()))
                .isOne();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"CreditLedger\" WHERE \"requestId\" = ?",
                        state.reservationRequestId()))
                .isOne();
        Record token = database.dsl().fetchOne(
                """
                SELECT "promptTokens", "cachedTokens", "completionTokens", "runId", "taskId"
                FROM public."TokenUsage" WHERE "requestId" = ?
                """,
                state.reservationRequestId());
        assertThat(token.get("promptTokens", Integer.class)).isEqualTo(100);
        assertThat(token.get("cachedTokens", Integer.class)).isEqualTo(20);
        assertThat(token.get("completionTokens", Integer.class)).isEqualTo(50);
        assertThat(token.get("runId", String.class)).isEqualTo(state.runId());
        assertThat(token.get("taskId", String.class)).isEqualTo(state.stepId());
        Record audit = database.dsl().fetchOne(
                """
                SELECT
                  "usageJson"::jsonb #>> '{reconciliation,reconciliationId}' AS id,
                  "usageJson"::jsonb #>> '{reconciliation,supplierEvidenceRef}' AS evidence,
                  "usageJson"::jsonb #>> '{reconciliation,supplierReportSha256}' AS report_sha
                FROM public."WorkflowBillingReservation" WHERE "stepId" = ?
                """,
                state.stepId());
        assertThat(audit.get("id", String.class)).isEqualTo("reconciliation-exact");
        assertThat(audit.get("evidence", String.class))
                .isEqualTo(
                        "supplier-report://deepseek/" + state.runId().replace(':', '-'));
        assertThat(audit.get("report_sha", String.class)).isEqualTo("d".repeat(64));
        assertTerminalStateUnchanged(state);

        BillingReconciliationRequest drift = exactRequest(state, "reconciliation-exact");
        drift.setSupplierEvidenceRef("supplier-report://deepseek/drift");
        assertThatThrownBy(() -> reconciliations.reconcile(drift))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_BILLING_RECONCILIATION_CONFLICT"));
        assertThat(balance(state.userId())).isEqualTo(5_000_000L - expectedCharge);
        assertTerminalStateUnchanged(state);
    }

    @Test
    void provenZero只释放零尝试证据且不创建用量或账本() {
        State state = state("reconcile-zero", 5_000_000L, 500_000L, unknownUsage());
        BillingReconciliationRequest request = zeroRequest(state, "reconciliation-zero");

        BillingReconciliationReceipt receipt = reconciliations.reconcile(request);

        assertThat(receipt.getReservationStatus())
                .isEqualTo(BillingReconciliationReceipt.ReservationStatusEnum.RELEASED);
        assertThat(receipt.getChargedMicros()).isZero();
        assertThat(balance(state.userId())).isEqualTo(5_000_000L);
        assertThat(reservation(state).get("status", String.class)).isEqualTo("released");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"requestId\" = ?",
                        state.reservationRequestId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"CreditLedger\" WHERE \"requestId\" = ?",
                        state.reservationRequestId()))
                .isZero();
        assertTerminalStateUnchanged(state);
    }

    @Test
    void 证据不合法与用量倒退均保持ReconciliationRequired零副作用() {
        State invalidEvidence =
                state("reconcile-invalid-evidence", 5_000_000L, 500_000L, partialUsage());
        BillingReconciliationRequest invalid =
                exactRequest(invalidEvidence, "reconciliation-invalid-evidence");
        invalid.setSupplierReportSha256("invalid");
        assertThatThrownBy(() -> reconciliations.reconcile(invalid))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(422);
                    assertThat(error.code()).isEqualTo("VALIDATION_ERROR");
                });
        assertUnchanged(invalidEvidence, 5_000_000L);

        State regression =
                state("reconcile-regression", 5_000_000L, 500_000L, partialUsage(200));
        assertThatThrownBy(() -> reconciliations.reconcile(
                        exactRequest(regression, "reconciliation-regression")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_BILLING_RECONCILIATION_USAGE_REGRESSION"));
        assertUnchanged(regression, 5_000_000L);
    }

    @Test
    void 精确金额越过预留或余额不足时拒绝且不产生财务事实() {
        State overLimit = state("reconcile-limit", 5_000_000L, 100L, partialUsage());
        assertThatThrownBy(() -> reconciliations.reconcile(
                        exactRequest(overLimit, "reconciliation-limit")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_BILLING_RECONCILIATION_LIMIT_EXCEEDED"));
        assertUnchanged(overLimit, 5_000_000L);

        State insufficient =
                state("reconcile-balance", 100_000L, 500_000L, partialUsage());
        assertThatThrownBy(() -> reconciliations.reconcile(
                        exactRequest(insufficient, "reconciliation-balance")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_BILLING_RECONCILIATION_BALANCE_INSUFFICIENT"));
        assertUnchanged(insufficient, 100_000L);
    }

    @Test
    void 同一ReconciliationId不得跨Reservation复用() {
        State first = state("reconcile-cross-a", 5_000_000L, 500_000L, partialUsage());
        State second = state("reconcile-cross-b", 5_000_000L, 500_000L, partialUsage());
        reconciliations.reconcile(exactRequest(first, "reconciliation-cross-shared"));

        assertThatThrownBy(() -> reconciliations.reconcile(
                        exactRequest(second, "reconciliation-cross-shared")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_BILLING_RECONCILIATION_CONFLICT"));
        assertUnchanged(second, 5_000_000L);
    }

    @Test
    void V1Charge与V2对账并发时V2成功且V1稳定业务冲突() throws Exception {
        State state = state("reconcile-v1-race", 5_000_000L, 500_000L, partialUsage());
        BillingRepository legacy = legacyBillingRepository();
        BillingReconciliationRequest reconciliation =
                exactRequest(state, "reconciliation-v1-race");
        ChargeUsage legacyUsage = new ChargeUsage(
                state.reservationRequestId(),
                state.userId(),
                state.novelId(),
                state.stepId(),
                state.runId(),
                "deepseek-v4-flash",
                "writer.chapter_selection.v1",
                100,
                20,
                50,
                150,
                80,
                10);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var v2 = executor.submit(() -> {
                ready.countDown();
                start.await();
                return reconciliations.reconcile(reconciliation);
            });
            var v1 = executor.submit(() -> {
                ready.countDown();
                start.await();
                try {
                    return legacy.charge(legacyUsage);
                } catch (RuntimeException exception) {
                    return exception;
                }
            });
            ready.await();
            start.countDown();

            assertThat(v2.get().getReservationStatus())
                    .isEqualTo(BillingReconciliationReceipt.ReservationStatusEnum.SETTLED);
            assertThat(v1.get()).isInstanceOf(UsageConflictException.class);
        }
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"requestId\" = ?",
                        state.reservationRequestId()))
                .isOne();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"CreditLedger\" WHERE \"requestId\" = ?",
                        state.reservationRequestId()))
                .isOne();
        assertTerminalStateUnchanged(state);
    }

    private static State state(
            String prefix, long balance, long reservedMicros, Map<String, Object> usage) {
        Fixture fixture = fixture(prefix, balance);
        var started = starts.start(plan(fixture, prefix + "-request-0001"));
        String usageJson = json.writeValueAsString(usage);
        WorkflowResolvedModel resolved = resolvedModel();
        String resolvedJson = json.writeValueAsString(
                WorkflowCallbackValues.resolvedModelMap(resolved));
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('failed' AS "WorkflowStepStatus"), "usageJson" = ?,
                    "resolvedModelJson" = ?, "completedAt" = ?, "updatedAt" = ?,
                    "errorCode" = 'MODEL_OUTCOME_UNKNOWN'
                WHERE id = ?
                """,
                usageJson,
                resolvedJson,
                NOW,
                NOW,
                started.stepId());
        database.dsl().execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('failed' AS "WorkflowRunStatus"), "completedAt" = ?,
                    "updatedAt" = ?, "errorCode" = 'MODEL_OUTCOME_UNKNOWN'
                WHERE id = ?
                """,
                NOW,
                NOW,
                started.runId());
        String reservationRequestId = prefix + "-reservation-request";
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowBillingReservation" (
                  id, "runId", "stepId", "userId", "requestId", "pricingVersion",
                  "pricingJson", "reservedMicros", "chargedMicros", "usageJson", status,
                  "createdAt", "updatedAt", "settledAt"
                ) VALUES (?, ?, ?, ?, ?, 'credit-pricing.v1', ?, ?, 0, ?,
                          'reconciliation_required', ?, ?, NULL)
                """,
                prefix + "-reservation",
                started.runId(),
                started.stepId(),
                fixture.userId(),
                reservationRequestId,
                json.writeValueAsString(pricing(resolved)),
                reservedMicros,
                usageJson,
                NOW,
                NOW);
        return new State(
                fixture.userId(),
                fixture.novelId(),
                started.runId(),
                started.stepId(),
                reservationRequestId);
    }

    private static BillingRepository legacyBillingRepository() throws Exception {
        Class<?> type = Class.forName(
                "cn.inkforge.core.billing.infrastructure.JooqBillingRepository");
        Constructor<?> constructor = type.getDeclaredConstructor(
                CoreDatabase.class, CuidV1Generator.class, Clock.class);
        constructor.setAccessible(true);
        return (BillingRepository) constructor.newInstance(
                database, new CuidV1Generator(CLOCK), CLOCK);
    }

    private static BillingReconciliationRequest exactRequest(State state, String id) {
        StepUsage usage = new StepUsage(0, 1, StepUsage.UsageStatusEnum.COMPLETE, 2_000)
                .inputTokens(100)
                .cachedTokens(20)
                .promptCacheMissTokens(80)
                .completionTokens(50)
                .reasoningTokens(10)
                .visibleOutputTokens(40)
                .costMicros(1);
        return request(state, id, BillingReconciliationRequest.DecisionEnum.EXACT_USAGE, usage);
    }

    private static BillingReconciliationRequest zeroRequest(State state, String id) {
        return request(
                state,
                id,
                BillingReconciliationRequest.DecisionEnum.PROVEN_ZERO,
                new StepUsage(0, 0, StepUsage.UsageStatusEnum.UNKNOWN, 200));
    }

    private static BillingReconciliationRequest request(
            State state,
            String id,
            BillingReconciliationRequest.DecisionEnum decision,
            StepUsage usage) {
        BillingReconciliationRequest request = new BillingReconciliationRequest();
        request.setProtocolVersion("2.0");
        request.setReconciliationId(id);
        request.setRunId(state.runId());
        request.setNovelId(JsonNullable.of(state.novelId()));
        request.setStepId(state.stepId());
        request.setReservationRequestId(state.reservationRequestId());
        request.setSupplierEvidenceRef(
                "supplier-report://deepseek/" + state.runId().replace(':', '-'));
        request.setSupplierReportSha256("d".repeat(64));
        request.setDecision(decision);
        request.setUsage(usage);
        return request;
    }

    private static Map<String, Object> partialUsage() {
        return partialUsage(80);
    }

    private static Map<String, Object> partialUsage(long inputTokens) {
        Map<String, Object> usage = new LinkedHashMap<>();
        usage.put("usageStatus", "partial");
        usage.put("inputTokens", inputTokens);
        usage.put("cachedTokens", 20);
        usage.put("providerAttempts", 1);
        usage.put("protocolCorrections", 0);
        usage.put("wallTimeMillis", 1_000);
        return usage;
    }

    private static Map<String, Object> unknownUsage() {
        return Map.of(
                "usageStatus", "unknown",
                "providerAttempts", 0,
                "protocolCorrections", 0,
                "wallTimeMillis", 100);
    }

    private static WorkflowResolvedModel resolvedModel() {
        String deployment = "deployment.writer.chapter_selection.v1";
        return new WorkflowResolvedModel(
                deployment,
                WorkflowResolvedModel.fingerprint(
                        deployment,
                        "openai_compatible",
                        "deepseek-v4-flash",
                        "transport.deepseek-v4.v1",
                        "endpoint.deepseek-official.v1",
                        "chat_json_output_v1",
                        "capability.deepseek-v4.chat-json.v1",
                        "bounded",
                        false),
                "openai_compatible",
                "deepseek-v4-flash",
                "transport.deepseek-v4.v1",
                "endpoint.deepseek-official.v1",
                "chat_json_output_v1",
                "capability.deepseek-v4.chat-json.v1",
                "bounded",
                false);
    }

    private static Map<String, Object> pricing(WorkflowResolvedModel resolved) {
        return Map.of(
                "billable", true,
                "currency", "credit_micros",
                "pricingVersion", "credit-pricing.v1",
                "rates",
                        Map.of(
                                "cachedInputMicrosPerToken",
                                        BillingPricing.CACHED_INPUT_MICROS_PER_TOKEN,
                                "outputMicrosPerToken",
                                        BillingPricing.OUTPUT_MICROS_PER_TOKEN,
                                "uncachedInputMicrosPerToken",
                                        BillingPricing.UNCACHED_INPUT_MICROS_PER_TOKEN),
                "resolvedModel", WorkflowCallbackValues.resolvedModelMap(resolved));
    }

    private static WorkflowStartPlan plan(Fixture fixture, String requestId) {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("selectionStart", 1);
        input.put("selectionEnd", 2);
        input.put("selectedTextSha256", sha256("😀"));
        input.put("userInstruction", "让语气更克制");
        return new WorkflowStartPlan(
                fixture.userId(),
                requestId,
                sha256(requestId),
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
                        API_NOW,
                        "甲😀乙",
                        null,
                        1,
                        2,
                        Map.of())),
                operation.operation().runBudget(),
                ExecutionPlanSnapshot.freeze(
                        registry.catalogVersion(), registry.manifestFingerprint(), operation),
                new WorkflowInitialStepPlan(
                        "generation",
                        "creative",
                        input,
                        operation.generatorProfile(),
                        operation.generatorStepBudget(),
                        operation.outputSchema()));
    }

    private static Fixture fixture(String prefix, long balance) {
        Fixture fixture = new Fixture(
                prefix + "-user",
                prefix + "-novel",
                prefix + "-chapter",
                prefix + "-session");
        database.dsl().execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'test', ?, ?, ?)
                """,
                fixture.userId(),
                fixture.userId(),
                balance,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                fixture.novelId(),
                prefix,
                fixture.userId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', '甲😀乙', 1, 'drafting', ?, ?)
                """,
                fixture.chapterId(),
                fixture.novelId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                fixture.sessionId(),
                fixture.novelId(),
                fixture.chapterId(),
                NOW,
                NOW);
        return fixture;
    }

    private static void assertUnchanged(State state, long expectedBalance) {
        assertThat(reservation(state).get("status", String.class))
                .isEqualTo("reconciliation_required");
        assertThat(balance(state.userId())).isEqualTo(expectedBalance);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"requestId\" = ?",
                        state.reservationRequestId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"CreditLedger\" WHERE \"requestId\" = ?",
                        state.reservationRequestId()))
                .isZero();
        assertTerminalStateUnchanged(state);
    }

    private static void assertTerminalStateUnchanged(State state) {
        assertThat(database.dsl().fetchOne(
                        "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                        state.runId())
                .get("status", String.class))
                .isEqualTo("failed");
        assertThat(database.dsl().fetchOne(
                        "SELECT status::text AS status FROM public.\"WorkflowStep\" WHERE id = ?",
                        state.stepId())
                .get("status", String.class))
                .isEqualTo("failed");
    }

    private static Record reservation(State state) {
        return database.dsl().fetchOne(
                """
                SELECT status, "chargedMicros", "usageJson", "settledAt"
                FROM public."WorkflowBillingReservation" WHERE "stepId" = ?
                """,
                state.stepId());
    }

    private static long balance(String userId) {
        return database.dsl().fetchOne(
                        "SELECT \"creditBalanceMicros\" FROM public.\"User\" WHERE id = ?",
                        userId)
                .get("creditBalanceMicros", Long.class);
    }

    private static int count(String sql, Object binding) {
        return database.dsl().fetchOne(sql, binding).get("count", Integer.class);
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
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

    private record State(
            String userId,
            String novelId,
            String runId,
            String stepId,
            String reservationRequestId) {}
}
