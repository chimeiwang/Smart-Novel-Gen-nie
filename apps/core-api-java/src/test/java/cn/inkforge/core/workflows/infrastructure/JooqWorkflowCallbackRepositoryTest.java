package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.EvidenceEvaluation;
import cn.inkforge.contracts.api.ExecutionCallbackReceipt;
import cn.inkforge.contracts.api.ExecutionStepFailure;
import cn.inkforge.contracts.api.ExecutionStepProgress;
import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.contracts.api.ModelProfileRef;
import cn.inkforge.contracts.api.PromptProfileRef;
import cn.inkforge.contracts.api.ResolvedModelRef;
import cn.inkforge.contracts.api.StepUsage;
import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
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
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
@Execution(ExecutionMode.SAME_THREAD)
class JooqWorkflowCallbackRepositoryTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T03:00:00.000");
    private static final OffsetDateTime API_NOW = OffsetDateTime.parse("2026-09-01T03:00:00Z");
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-01T03:00:00Z"), ZoneOffset.UTC);

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
    private static JooqWorkflowDispatchRepository dispatches;
    private static JooqWorkflowCallbackRepository callbacks;
    private static JooqWorkflowRunCancellationRepository cancellations;

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
        callbacks = new JooqWorkflowCallbackRepository(
                database, ids, CLOCK, json, registry, Duration.ofSeconds(30));
        cancellations =
                new JooqWorkflowRunCancellationRepository(
                        database, ids, CLOCK, json, registry);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void progress严格去重并在同一事务升格StepStarted和StepProgress() {
        Flow flow = runningFlow("callback-progress");

        ExecutionStepProgress duplicate = progress(flow.request(), unknownUsage());
        assertThat(callbacks.progress(duplicate).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        assertThat(eventTypes(flow.runId()))
                .containsExactly(
                        "run_accepted",
                        "evidence_ready",
                        "step_queued",
                        "step_started",
                        "step_progress");
        String startedPayload = database.dsl().fetchOne(
                        """
                        SELECT "payloadJson" FROM public."WorkflowEvent"
                        WHERE "runId" = ? AND "eventType" = 'step_started'
                        """,
                        flow.runId())
                .get("payloadJson", String.class);
        String progressPayload = database.dsl().fetchOne(
                        """
                        SELECT "payloadJson" FROM public."WorkflowEvent"
                        WHERE "runId" = ? AND "eventType" = 'step_progress'
                        """,
                        flow.runId())
                .get("payloadJson", String.class);
        var startedEvent = json.readTree(startedPayload);
        var progressEvent = json.readTree(progressPayload);
        ResolvedModelRef acceptedModel = apiResolved(flow.request());
        assertThat(startedEvent.path("modelProfile").path("profile").asText())
                .isEqualTo(flow.request().getModelProfile().getProfile());
        assertThat(startedEvent.has("resolvedModel")).isFalse();
        assertThat(progressEvent.path("modelProfile").path("profile").asText())
                .isEqualTo(flow.request().getModelProfile().getProfile());
        assertThat(progressEvent.path("resolvedModel").path("deploymentFingerprint").asText())
                .isEqualTo(acceptedModel.getDeploymentFingerprint());
        assertThat(progressEvent.path("resolvedModel").path("model").asText())
                .isEqualTo(acceptedModel.getModel());

        database.dsl().execute(
                """
                UPDATE public."WorkflowStep" SET "leaseExpiresAt" = ? WHERE id = ?
                """,
                NOW.minusSeconds(1),
                flow.request().getStepId());
        ExecutionStepRequest recovery = dispatches.claimNext().orElseThrow();
        assertThat(recovery.getFencingToken()).isEqualTo(2);
        assertThat(database.dsl().fetchOne(
                        "SELECT \"lastProgressSequence\" FROM public.\"WorkflowStep\" WHERE id = ?",
                        recovery.getStepId())
                .get("lastProgressSequence", Long.class))
                .isNull();
        assertThat(callbacks.progress(duplicate).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.STALE);
        accept(recovery);
        cancellations.request(flow.userId(), flow.runId(), "callback-progress-cleanup");
        callbacks.failure(preProviderFailure(recovery));
    }

    @Test
    void running租约换Fence后旧终态先保留等待并在Core终态后确认被取代() {
        Flow flow = runningFlow("callback-terminal-refence-race");
        ExecutionStepResult oldTerminal = outputResult(
                flow.request(), "旧 fence 已经取得但尚未送达的完整候选");
        database.dsl().execute(
                "UPDATE public.\"WorkflowStep\" SET \"leaseExpiresAt\" = ? WHERE id = ?",
                NOW.minusSeconds(1),
                flow.request().getStepId());

        ExecutionStepRequest recovery = dispatches.claimNext().orElseThrow();

        assertThat(recovery.getFencingToken()).isEqualTo(2);
        assertThat(callbacks.result(oldTerminal).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.STALE);
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status, \"resultHash\" FROM public.\"WorkflowStep\" WHERE id = ?",
                                flow.request().getStepId()))
                .satisfies(step -> {
                    assertThat(step.get("status", String.class)).isEqualTo("running");
                    assertThat(step.get("resultHash", String.class)).isNull();
                });

        accept(recovery);
        assertThat(callbacks.failure(preProviderFailure(recovery)).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.result(oldTerminal).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.SUPERSEDED);
    }

    @Test
    void preparing早于同步Accepted也在同一事务完成预留且迟到Accepted幂等() {
        Fixture fixture = fixture("callback-accepted-race");
        starts.start(plan(fixture, "callback-accepted-race-request-0001"));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        ExecutionStepProgress preparing = progress(request, unknownUsage());

        assertThat(callbacks.progress(preparing).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.progress(preparing).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvent\" WHERE \"runId\" = ? AND \"eventType\" = 'step_started'",
                        request.getRunId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ? AND status = 'reserved'",
                        request.getStepId()))
                .isEqualTo(1);

        // HTTP 202 可以晚于 preparing callback；它只能做同值冻结校验，不能新建第二份预留。
        accept(request);
        assertThat(callbacks.failure(preProviderFailure(request)).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(database.dsl().fetchOne(
                                "SELECT status FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                                request.getStepId())
                        .get("status", String.class))
                .isEqualTo("released");
    }

    @Test
    void 已预留Step的重复Preparing若授权快照漂移会稳定失败并释放零Attempt额度() {
        Flow flow = runningFlow("billing-preparing-drift");
        ResolvedModelRef alternate = apiResolved(flow.request(), "endpoint.deepseek-custom.v1");
        // 管理员级故障注入：正常写路径会先被 V2 resolved-model 一次冻结 trigger 拒绝。
        database.transactionResult(transaction -> {
            transaction.execute("SET LOCAL session_replication_role = replica");
            transaction.execute(
                    "UPDATE public.\"WorkflowStep\" SET \"resolvedModelJson\" = ? WHERE id = ?",
                    json.writeValueAsString(WorkflowCallbackValues.resolvedModelMap(alternate)),
                    flow.request().getStepId());
            return null;
        });
        ExecutionStepProgress repeated = progress(flow.request(), unknownUsage());
        repeated.setSequence(2);
        repeated.setProgressId("progress-drift-" + flow.request().getStepId());
        repeated.setResolvedModel(alternate);

        assertThat(callbacks.progress(repeated).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.STALE);
        assertThat(database.dsl().fetchOne(
                        "SELECT status FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                        flow.request().getStepId())
                .get("status", String.class))
                .isEqualTo("released");
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status, \"errorCode\" FROM public.\"WorkflowRun\" WHERE id = ?",
                                flow.runId())
                        .get("status", String.class))
                .isEqualTo("failed");
    }

    @Test
    void Preparing后当前Registry不再授权旧部署时Terminal仍按冻结价格结算() {
        Fixture fixture = fixture("billing-registry-upgrade");
        starts.start(plan(fixture, "billing-registry-upgrade-request"));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        cn.inkforge.contracts.agent.ResolvedModelRef fakeAgent = fakeAgentResolved(request);
        ResolvedModelRef fakeApi = fakeApiResolved(request);
        dispatches.recordAccepted(request, accepted(request, fakeAgent));
        ExecutionStepProgress preparing = progress(request, unknownUsage());
        preparing.setResolvedModel(fakeApi);
        assertThat(callbacks.progress(preparing).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);

        JooqWorkflowCallbackRepository afterUpgrade = new JooqWorkflowCallbackRepository(
                database,
                new CuidV1Generator(Clock.offset(CLOCK, Duration.ofMillis(1))),
                CLOCK,
                json,
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.PRODUCTION),
                Duration.ofSeconds(30));
        ExecutionStepResult terminal = outputResult(request, "升级后仍可结算的候选");
        terminal.setResolvedModel(fakeApi);
        terminal.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.resultHashMaterial(terminal)));
        assertThat(afterUpgrade.result(terminal).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(database.dsl().fetchOne(
                        "SELECT status, \"chargedMicros\" FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                        request.getStepId()))
                .satisfies(reservation -> {
                    assertThat(reservation.get("status", String.class)).isEqualTo("settled");
                    assertThat(reservation.get("chargedMicros", Long.class)).isZero();
                });
        cancellations.request(
                fixture.userId(), request.getRunId(), "billing-registry-upgrade-cleanup");
    }

    @Test
    void 已创建Run在当前Operation下线后仍完成生成和双Reviewer并等待用户() {
        Fixture fixture = fixture("registry-downline-full");
        var started = starts.start(plan(fixture, "registry-downline-full-request"));
        ExecutionRegistry downlined = ExecutionRegistryFixtures.selectionOperationDownlined(
                ExecutionRegistry.Environment.TEST);
        assertThatThrownBy(() -> downlined.resolve(
                        "long_serial.rewrite_chapter_selection", false))
                .hasMessageContaining("尚未启用");
        CuidV1Generator ids = new CuidV1Generator(Clock.offset(CLOCK, Duration.ofMillis(2)));
        JooqWorkflowDispatchRepository upgradedDispatch = new JooqWorkflowDispatchRepository(
                database, ids, CLOCK, json, downlined, Duration.ofSeconds(30), 3);
        JooqWorkflowCallbackRepository upgradedCallbacks = new JooqWorkflowCallbackRepository(
                database, ids, CLOCK, json, downlined, Duration.ofSeconds(30));

        ExecutionStepRequest generation = upgradedDispatch.claimNext().orElseThrow();
        upgradedDispatch.recordAccepted(generation, accepted(generation));
        assertThat(upgradedCallbacks.progress(progress(generation, unknownUsage())).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(upgradedCallbacks.result(outputResult(generation, "目录下线后的候选")).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);

        ExecutionStepRequest firstReviewer = upgradedDispatch.claimNext().orElseThrow();
        ExecutionStepRequest secondReviewer = upgradedDispatch.claimNext().orElseThrow();
        assertThat(List.of(
                        firstReviewer.getModelProfile().getProfile(),
                        secondReviewer.getModelProfile().getProfile()))
                .containsExactlyInAnyOrder(
                        "reviewer.consistency.v1", "reviewer.editorial.v1");
        for (ExecutionStepRequest reviewer : List.of(firstReviewer, secondReviewer)) {
            upgradedDispatch.recordAccepted(reviewer, accepted(reviewer));
            upgradedCallbacks.progress(progress(reviewer, unknownUsage()));
            upgradedCallbacks.result(reviewResult(reviewer));
        }

        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                                started.runId())
                        .get("status", String.class))
                .isEqualTo("waiting_user");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvaluation\" WHERE \"runId\" = ?",
                        started.runId()))
                .isEqualTo(2);
        cancellations.request(
                fixture.userId(), started.runId(), "registry-downline-full-cleanup");
    }

    @Test
    void generator原子创建V2ArtifactRevisionReviewer并在全部评审收敛后等待用户() throws Exception {
        Flow generation = runningFlow("callback-happy");
        ExecutionStepResult generated = outputResult(generation.request(), "改写后的完整选区");

        assertThat(callbacks.result(generated).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.result(generated).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT status, "chargedMicros" FROM public."WorkflowBillingReservation"
                        WHERE "stepId" = ?
                        """,
                        generation.request().getStepId()))
                .satisfies(reservation -> {
                    assertThat(reservation.get("status", String.class)).isEqualTo("settled");
                    assertThat(reservation.get("chargedMicros", Long.class)).isEqualTo(140_000L);
                });
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"runId\" = ?",
                        generation.runId()))
                .isEqualTo(1);

        Record artifact = database.dsl().fetchOne(
                """
                SELECT id, "workflowRunId", "taskId", revision, status::text AS status,
                       "payloadJson", "diffJson"
                FROM public."ReviewArtifact" WHERE "workflowRunId" = ?
                """,
                generation.runId());
        assertThat(artifact).isNotNull();
        assertThat(artifact.get("workflowRunId", String.class)).isEqualTo(generation.runId());
        assertThat(artifact.get("taskId", String.class)).isNull();
        assertThat(artifact.get("revision", Integer.class)).isEqualTo(1);
        assertThat(artifact.get("status", String.class)).isEqualTo("under_review");
        var storedPayload = json.readTree(artifact.get("payloadJson", String.class));
        var storedDiff = json.readTree(artifact.get("diffJson", String.class));
        assertThat(storedPayload.path("schema").asText())
                .isEqualTo("durable.chapter-selection-artifact.v1");
        assertThat(storedPayload.path("replacement").asText())
                .isEqualTo("改写后的完整选区");
        assertThat(storedPayload.path("candidateSha256").asText())
                .isEqualTo(sha256("甲改写后的完整选区乙"));
        assertThat(storedPayload.has("candidate")).isFalse();
        assertThat(storedPayload.has("candidatePrefix")).isFalse();
        assertThat(storedPayload.has("candidateSuffix")).isFalse();
        assertThat(storedDiff.has("before")).isFalse();
        assertThat(storedDiff.has("after")).isFalse();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?",
                        artifact.get("id", String.class)))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'review'",
                        generation.runId()))
                .isEqualTo(2);
        assertThat(eventTypes(generation.runId()))
                .endsWith("step_finished", "candidate_ready", "review_started");
        String reviewStartedPayload = database.dsl().fetchOne(
                        """
                        SELECT "payloadJson" FROM public."WorkflowEvent"
                        WHERE "runId" = ? AND "eventType" = 'review_started'
                        """,
                        generation.runId())
                .get("payloadJson", String.class);
        var reviewerSnapshots = json.readTree(reviewStartedPayload).path("reviewerSteps");
        assertThat(reviewerSnapshots.size()).isEqualTo(2);
        assertThat(reviewerSnapshots.get(0).path("status").asText()).isEqualTo("pending");
        assertThat(reviewerSnapshots.get(0).path("attemptCount").asInt()).isZero();
        assertThat(reviewerSnapshots.get(0).path("fencingToken").asInt()).isZero();
        assertThat(reviewerSnapshots.get(0).path("modelProfile").path("profile").asText())
                .isNotBlank();

        ExecutionStepRequest firstReview = dispatches.claimNext().orElseThrow();
        assertThat(firstReview.getPurpose()).isEqualTo("review");
        assertThat(firstReview.getEvidenceBundle().getId())
                .isEqualTo(generation.request().getEvidenceBundle().getId());
        assertThat(firstReview.getEvidenceBundle().getManifestSha256())
                .isEqualTo(generation.request().getEvidenceBundle().getManifestSha256());
        assertThat(firstReview.getEvidenceBundle().getPolicyVersion())
                .isEqualTo("evidence.review.same_bundle_artifact_revision.v1");
        // 同一 Run 的 reviewer fan-out 不受小说级跨 Run 互斥影响。
        ExecutionStepRequest secondReview = dispatches.claimNext().orElseThrow();
        assertThat(secondReview.getRunId()).isEqualTo(firstReview.getRunId());
        assertThat(secondReview.getPurpose()).isEqualTo("review");
        for (ExecutionStepRequest reviewer : List.of(firstReview, secondReview)) {
            assertThat(reviewer.getInput()).containsOnlyKeys("task", "candidate");
            assertThat(reviewer.getInput().get("task"))
                    .isInstanceOfSatisfying(Map.class, task -> assertThat(task)
                            .containsEntry("selectionStart", 1)
                            .containsEntry("selectionEnd", 2)
                            .containsEntry("userInstruction", "让语气更克制")
                            .containsEntry("selectedTextSha256", sha256("😀")));
            assertThat(reviewer.getInput()).doesNotContainKey("evidenceBundle");
            assertThat(reviewer.getEvidenceBundle().getId())
                    .isEqualTo(generation.request().getEvidenceBundle().getId());
        }
        // 两个 Reviewer 的 Accepted 并发进入 Core；Run 行锁必须把预算和逐 Step 预留串行核算。
        try (var pool = Executors.newFixedThreadPool(2)) {
            var firstAccepted = pool.submit(() -> accept(firstReview));
            var secondAccepted = pool.submit(() -> accept(secondReview));
            firstAccepted.get();
            secondAccepted.get();
        }
        assertThat(callbacks.progress(progress(firstReview, unknownUsage())).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.result(reviewResult(firstReview)).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        String firstReviewFinished = database.dsl().fetchOne(
                        """
                        SELECT "payloadJson" FROM public."WorkflowEvent"
                        WHERE "runId" = ? AND "eventType" = 'step_finished'
                          AND "payloadJson"::jsonb ->> 'stepId' = ?
                        """,
                        generation.runId(),
                        firstReview.getStepId())
                .get("payloadJson", String.class);
        assertThat(json.readTree(firstReviewFinished).path("status").asText())
                .isEqualTo("completed");

        callbacks.progress(progress(secondReview, unknownUsage()));
        assertThat(callbacks.failure(reviewFailure(secondReview)).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);

        Record run = database.dsl().fetchOne(
                """
                SELECT status::text AS status, "completedAt" FROM public."WorkflowRun" WHERE id = ?
                """,
                generation.runId());
        assertThat(run.get("status", String.class)).isEqualTo("waiting_user");
        assertThat(run.get("completedAt", LocalDateTime.class)).isNull();
        assertThat(database.dsl().fetchOne(
                        "SELECT status::text AS status FROM public.\"ReviewArtifact\" WHERE id = ?",
                        artifact.get("id", String.class))
                .get("status", String.class))
                .isEqualTo("awaiting_user");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvaluation\" WHERE \"runId\" = ?",
                        generation.runId()))
                .isEqualTo(2);
        assertThat(eventTypes(generation.runId()))
                .endsWith("review_completed", "awaiting_user");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvent\" WHERE \"runId\" = ? AND \"eventType\" = 'step_finished'",
                        generation.runId()))
                .isEqualTo(3);

        enqueueRevisionGeneration(
                generation.runId(),
                generation.request().getStepId(),
                artifact.get("id", String.class),
                1);
        ExecutionStepRequest revisionGeneration = dispatches.claimNext().orElseThrow();
        assertThat(revisionGeneration.getPurpose()).isEqualTo("generation");
        assertThat(revisionGeneration.getArtifactId()).isEqualTo(artifact.get("id", String.class));
        assertThat(revisionGeneration.getArtifactRevision()).isEqualTo(1);
        accept(revisionGeneration);
        callbacks.progress(progress(revisionGeneration, unknownUsage()));
        assertThat(callbacks.result(outputResult(revisionGeneration, "第二版完整选区")).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(database.dsl().fetchOne(
                                "SELECT revision FROM public.\"ReviewArtifact\" WHERE id = ?",
                                artifact.get("id", String.class))
                        .get("revision", Integer.class))
                .isEqualTo(2);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?",
                        artifact.get("id", String.class)))
                .isEqualTo(2);

        ExecutionStepRequest revisionReviewOne = dispatches.claimNext().orElseThrow();
        ExecutionStepRequest revisionReviewTwo = dispatches.claimNext().orElseThrow();
        assertThat(revisionReviewTwo.getRunId()).isEqualTo(revisionReviewOne.getRunId());
        accept(revisionReviewOne);
        callbacks.progress(progress(revisionReviewOne, unknownUsage()));
        callbacks.result(reviewResult(revisionReviewOne));
        accept(revisionReviewTwo);
        callbacks.progress(progress(revisionReviewTwo, unknownUsage()));
        callbacks.failure(reviewFailure(revisionReviewTwo));
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                                generation.runId())
                        .get("status", String.class))
                .isEqualTo("waiting_user");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvaluation\" WHERE \"runId\" = ? AND \"artifactRevision\" = 2",
                        generation.runId()))
                .isEqualTo(2);
        // 两轮 generation + 两组 Reviewer 都按低实际 token 结算；Run cost 维度仍按供应商未知上限保守占用。
        // 若误把每个 terminal Step 都永久按 token 上限占用，第二轮 revise 会在 recordAccepted 阶段被拒绝。
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"runId\" = ?",
                        generation.runId()))
                .isEqualTo(6);
        assertThat(eventTypes(generation.runId()))
                .endsWith("review_completed", "awaiting_user");

        cancellations.request(
                "callback-happy-user", generation.runId(), "cancel-waiting-user-0001");
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                                generation.runId())
                        .get("status", String.class))
                .isEqualTo("cancelled");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?",
                        artifact.get("id", String.class)))
                .isEqualTo(2);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvaluation\" WHERE \"runId\" = ?",
                        generation.runId()))
                .isEqualTo(4);
        assertThat(eventTypes(generation.runId())).endsWith("cancelled");
    }

    @Test
    void Reviewer并发预留不足只降级为部分评审且候选仍可决定() throws Exception {
        Flow generation = runningFlow("billing-reviewer-partial");
        callbacks.result(outputResult(generation.request(), "仍可决定的完整候选"));
        ExecutionStepRequest first = dispatches.claimNext().orElseThrow();
        ExecutionStepRequest second = dispatches.claimNext().orElseThrow();
        accept(first);
        accept(second);
        // 每个 Reviewer 最坏积分预留为 17m；模拟同用户其他链路已结算支出，只够其中一个。
        database.dsl().execute(
                "UPDATE public.\"User\" SET \"creditBalanceMicros\" = 17000000 WHERE id = ?",
                generation.userId());

        ExecutionCallbackReceipt.StatusEnum firstStatus;
        ExecutionCallbackReceipt.StatusEnum secondStatus;
        try (var pool = Executors.newFixedThreadPool(2)) {
            var left = pool.submit(() -> callbacks.progress(progress(first, unknownUsage())).getStatus());
            var right = pool.submit(() -> callbacks.progress(progress(second, unknownUsage())).getStatus());
            firstStatus = left.get();
            secondStatus = right.get();
        }
        assertThat(List.of(firstStatus, secondStatus))
                .containsExactlyInAnyOrder(
                        ExecutionCallbackReceipt.StatusEnum.ACCEPTED,
                        ExecutionCallbackReceipt.StatusEnum.STALE);
        ExecutionStepRequest accepted = firstStatus == ExecutionCallbackReceipt.StatusEnum.ACCEPTED
                ? first
                : second;
        ExecutionStepRequest unavailable = accepted == first ? second : first;
        assertThat(database.dsl().fetchOne(
                        "SELECT status::text AS status, \"errorCode\" FROM public.\"WorkflowStep\" WHERE id = ?",
                        unavailable.getStepId()))
                .satisfies(step -> {
                    assertThat(step.get("status", String.class)).isEqualTo("failed");
                    assertThat(step.get("errorCode", String.class)).isEqualTo("INSUFFICIENT_CREDITS");
                });
        assertThat(callbacks.result(reviewResult(accepted)).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);

        Record artifact = database.dsl().fetchOne(
                "SELECT id, status::text AS status FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                generation.runId());
        assertThat(artifact.get("status", String.class)).isEqualTo("awaiting_user");
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                                generation.runId())
                        .get("status", String.class))
                .isEqualTo("waiting_user");
        assertThat(database.dsl().fetch(
                        "SELECT \"executionStatus\" FROM public.\"WorkflowEvaluation\" WHERE \"runId\" = ?",
                        generation.runId())
                .getValues("executionStatus", String.class))
                .containsExactlyInAnyOrder("completed", "failed");
        assertThat(callbacks.failure(preProviderFailure(unavailable)).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.SUPERSEDED);
        String reviewPayload = database.dsl().fetchOne(
                        "SELECT \"payloadJson\" FROM public.\"WorkflowEvent\" WHERE \"runId\" = ? AND \"eventType\" = 'review_completed'",
                        generation.runId())
                .get("payloadJson", String.class);
        assertThat(json.readTree(reviewPayload).path("reviewAvailability").asText())
                .isEqualTo("partial");
        cancellations.request(
                generation.userId(), generation.runId(), "billing-reviewer-partial-cleanup");
    }

    @Test
    void pending前置Failure先于Accepted时冻结解析模型并收敛且迟到Accepted幂等() {
        Fixture fixture = fixture("callback-fast-terminal");
        var started = starts.start(plan(fixture, "callback-fast-terminal-request-0001"));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        ExecutionStepFailure terminal = preProviderFailure(request);
        assertThat(callbacks.failure(terminal).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        String frozen = database.dsl().fetchOne(
                        "SELECT \"resolvedModelJson\" FROM public.\"WorkflowStep\" WHERE id = ?",
                        request.getStepId())
                .get("resolvedModelJson", String.class);
        assertThat(frozen).isNotBlank();

        accept(request);
        assertThat(database.dsl().fetchOne(
                                "SELECT \"resolvedModelJson\" FROM public.\"WorkflowStep\" WHERE id = ?",
                                request.getStepId())
                        .get("resolvedModelJson", String.class))
                .isEqualTo(frozen);
        assertThat(callbacks.failure(terminal).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        assertThat(started.runId()).isEqualTo(request.getRunId());
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowBillingReservation\" WHERE \"runId\" = ?",
                        started.runId()))
                .isZero();
    }

    @Test
    void 非法候选整体回滚且取消中的迟到正常结果只收敛Usage() {
        Flow invalid = runningFlow("callback-invalid");
        ExecutionStepResult bad = outputResult(invalid.request(), "候选");
        bad.getOutput().get().put("contentSha256", "0".repeat(64));
        bad.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.resultHashMaterial(bad)));

        assertThatThrownBy(() -> callbacks.result(bad))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WORKFLOW_CALLBACK_INVALID"));
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                        invalid.runId()))
                .isZero();
        assertThat(database.dsl().fetchOne(
                        "SELECT status::text AS status, \"resultHash\" FROM public.\"WorkflowStep\" WHERE id = ?",
                        invalid.request().getStepId()))
                .satisfies(step -> {
                    assertThat(step.get("status", String.class)).isEqualTo("running");
                    assertThat(step.get("resultHash", String.class)).isNull();
                });

        Flow cancelled = runningFlow("callback-cancelled");
        var cancellation = cancellations.request(
                "callback-cancelled-user", cancelled.runId(), "cancel-request-0001");
        assertThat(cancellation.executorRequests()).singleElement().satisfies(request -> {
            assertThat(request.getRunId()).isEqualTo(cancelled.runId());
            assertThat(request.getStepId()).isEqualTo(cancelled.request().getStepId());
            assertThat(request.getJobId()).isEqualTo(cancelled.request().getJobId());
            assertThat(request.getFencingToken()).isEqualTo(cancelled.request().getFencingToken());
            assertThat(request.getCancelRequestId()).isEqualTo("cancel-request-0001");
        });
        assertThat(cancellations.request(
                                "callback-cancelled-user",
                                cancelled.runId(),
                                "cancel-request-0001")
                        .executorRequests())
                .hasSize(1);
        assertThatThrownBy(() -> cancellations.request(
                        "callback-cancelled-user", cancelled.runId(), "cancel-request-other"))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WORKFLOW_CANCEL_CONFLICT"));
        ExecutionStepResult late = outputResult(cancelled.request(), "不得物化的迟到候选");

        assertThat(callbacks.result(late).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.result(late).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                        cancelled.runId()))
                .isZero();
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT status::text AS status, "completedAt" FROM public."WorkflowRun" WHERE id = ?
                        """,
                        cancelled.runId()))
                .satisfies(run -> {
                    assertThat(run.get("status", String.class)).isEqualTo("cancelled");
                    assertThat(run.get("completedAt", LocalDateTime.class)).isEqualTo(NOW);
                });
        assertThat(eventTypes(cancelled.runId())).endsWith("cancelled");
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT status FROM public."WorkflowBillingReservation" WHERE "stepId" = ?
                        """,
                        cancelled.request().getStepId())
                .get("status", String.class))
                .isEqualTo("settled");
        cancellations.request(invalid.userId(), invalid.runId(), "callback-invalid-cleanup");
        callbacks.failure(preProviderFailure(invalid.request()));
    }

    @Test
    void 空白候选稳定拒绝而不是裸500且不产生任何业务副作用() {
        List<String> blankReplacements = List.of("", "   ", "\n\t", "\u3000");
        for (int index = 0; index < blankReplacements.size(); index++) {
            Flow flow = runningFlow("callback-blank-output-" + index);
            ExecutionStepResult result = outputResult(
                    flow.request(), blankReplacements.get(index));

            assertThatThrownBy(() -> callbacks.result(result))
                    .as("blank replacement index %s", index)
                    .isInstanceOfSatisfying(ApiException.class, error -> {
                        assertThat(error.statusCode()).isEqualTo(409);
                        assertThat(error.code()).isEqualTo("WORKFLOW_CALLBACK_INVALID");
                    });
            assertThat(count(
                            "SELECT count(*) AS count FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                            flow.runId()))
                    .isZero();
            assertThat(database.dsl().fetchOne(
                            """
                            SELECT status::text AS status, "resultHash"
                            FROM public."WorkflowStep" WHERE id = ?
                            """,
                            flow.request().getStepId()))
                    .satisfies(step -> {
                        assertThat(step.get("status", String.class)).isEqualTo("running");
                        assertThat(step.get("resultHash", String.class)).isNull();
                    });
            cancellations.request(
                    flow.userId(), flow.runId(), "blank-output-cleanup-" + index);
            assertThat(callbacks.failure(reviewFailure(flow.request())).getStatus())
                    .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        }
    }

    @Test
    void 零Attempt伪造供应商Usage稳定拒绝且不改变Step预留或事件() {
        Flow flow = runningFlow("callback-zero-attempt-usage");
        int eventCount = eventTypes(flow.runId()).size();
        StepUsage impossible = new StepUsage(
                        0, 0, StepUsage.UsageStatusEnum.COMPLETE, 0)
                .inputTokens(0)
                .cachedTokens(0)
                .promptCacheMissTokens(0)
                .completionTokens(0)
                .reasoningTokens(0)
                .visibleOutputTokens(0)
                .costMicros(0);
        ExecutionStepProgress malformed = progress(flow.request(), impossible);
        malformed.setSequence(2);
        malformed.setProgressId("progress-impossible-" + flow.request().getStepId());

        assertThatThrownBy(() -> callbacks.progress(malformed))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("WORKFLOW_CALLBACK_INVALID");
                });
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT status::text AS status, "lastProgressSequence", "resultHash"
                        FROM public."WorkflowStep" WHERE id = ?
                        """,
                        flow.request().getStepId()))
                .satisfies(step -> {
                    assertThat(step.get("status", String.class)).isEqualTo("running");
                    assertThat(step.get("lastProgressSequence", Long.class)).isEqualTo(1L);
                    assertThat(step.get("resultHash", String.class)).isNull();
                });
        assertThat(database.dsl().fetchOne(
                                "SELECT status FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                                flow.request().getStepId())
                        .get("status", String.class))
                .isEqualTo("reserved");
        assertThat(eventTypes(flow.runId())).hasSize(eventCount);

        cancellations.request(
                flow.userId(), flow.runId(), "callback-zero-attempt-usage-cleanup");
        callbacks.failure(preProviderFailure(flow.request()));
    }

    @Test
    void 超预算Result是零写入协议错误且不会物化候选() {
        Flow flow = runningFlow("callback-over-budget-result");
        ExecutionStepResult result = outputResult(flow.request(), "不得物化的超预算候选");
        result.setUsage(overBudgetUsage());
        result.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.resultHashMaterial(result)));

        assertThatThrownBy(() -> callbacks.result(result))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("WORKFLOW_CALLBACK_INVALID");
                });
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                        flow.runId()))
                .isZero();
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT status::text AS status, "resultHash" FROM public."WorkflowStep"
                        WHERE id = ?
                        """,
                        flow.request().getStepId()))
                .satisfies(step -> {
                    assertThat(step.get("status", String.class)).isEqualTo("running");
                    assertThat(step.get("resultHash", String.class)).isNull();
                });
        assertThat(database.dsl().fetchOne(
                                "SELECT status FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                                flow.request().getStepId())
                        .get("status", String.class))
                .isEqualTo("reserved");

        cancellations.request(
                flow.userId(), flow.runId(), "callback-over-budget-result-cleanup");
        callbacks.failure(preProviderFailure(flow.request()));
    }

    @Test
    void 明确超预算Failure保留真实Usage转人工对账并幂等阻断后续Step() {
        Flow flow = runningFlow("callback-over-budget-failure");
        ExecutionStepFailure failure = budgetFailure(flow.request());

        assertThat(callbacks.failure(failure).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.failure(failure).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT status::text AS status, "errorCode", "resultHash", "usageJson"
                        FROM public."WorkflowStep" WHERE id = ?
                        """,
                        flow.request().getStepId()))
                .satisfies(step -> {
                    assertThat(step.get("status", String.class)).isEqualTo("failed");
                    assertThat(step.get("errorCode", String.class))
                            .isEqualTo("STEP_BUDGET_EXCEEDED");
                    assertThat(step.get("resultHash", String.class))
                            .isEqualTo(failure.getResultHash());
                    assertThat(json.readTree(step.get("usageJson", String.class))
                                    .path("completionTokens")
                                    .asInt())
                            .isEqualTo(8_001);
                });
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT status::text AS status, "errorCode" FROM public."WorkflowRun"
                        WHERE id = ?
                        """,
                        flow.runId()))
                .satisfies(run -> {
                    assertThat(run.get("status", String.class)).isEqualTo("failed");
                    assertThat(run.get("errorCode", String.class))
                            .isEqualTo("STEP_BUDGET_EXCEEDED");
                });
        assertThat(database.dsl().fetchOne(
                                "SELECT status FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                                flow.request().getStepId())
                        .get("status", String.class))
                .isEqualTo("reconciliation_required");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                        flow.runId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'review'",
                        flow.runId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"runId\" = ?",
                        flow.runId()))
                .isZero();
        assertThat(eventTypes(flow.runId())).endsWith("failed");
    }

    @Test
    void 预算Failure声明与实际越界必须双向一致否则零写入拒绝() {
        Flow falseClaim = runningFlow("callback-false-budget-claim");
        ExecutionStepFailure withinBudget = budgetFailure(falseClaim.request());
        withinBudget.setUsage(partialUsage(false));
        withinBudget.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.failureHashMaterial(withinBudget)));

        assertThatThrownBy(() -> callbacks.failure(withinBudget))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WORKFLOW_CALLBACK_INVALID"));
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowStep\" WHERE id = ?",
                                falseClaim.request().getStepId())
                        .get("status", String.class))
                .isEqualTo("running");
        assertThat(database.dsl().fetchOne(
                                "SELECT status FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                                falseClaim.request().getStepId())
                        .get("status", String.class))
                .isEqualTo("reserved");
        cancellations.request(
                falseClaim.userId(), falseClaim.runId(), "callback-false-budget-cleanup");
        callbacks.failure(preProviderFailure(falseClaim.request()));

        Flow hiddenOverrun = runningFlow("callback-hidden-budget-overrun");
        ExecutionStepFailure wrongCode = budgetFailure(hiddenOverrun.request());
        wrongCode.setErrorCode("MODEL_OUTPUT_FILTERED");
        wrongCode.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.failureHashMaterial(wrongCode)));

        assertThatThrownBy(() -> callbacks.failure(wrongCode))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WORKFLOW_CALLBACK_INVALID"));
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowStep\" WHERE id = ?",
                                hiddenOverrun.request().getStepId())
                        .get("status", String.class))
                .isEqualTo("running");
        assertThat(database.dsl().fetchOne(
                                "SELECT status FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                                hiddenOverrun.request().getStepId())
                        .get("status", String.class))
                .isEqualTo("reserved");
        cancellations.request(
                hiddenOverrun.userId(),
                hiddenOverrun.runId(),
                "callback-hidden-budget-cleanup");
        callbacks.failure(preProviderFailure(hiddenOverrun.request()));
    }

    @Test
    void pending取消并发幂等且只写一个CancelledEvent() throws Exception {
        Fixture fixture = fixture("cancel-pending-concurrent");
        var started = starts.start(plan(fixture, "cancel-pending-concurrent-request"));
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch fire = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var first = pool.submit(() -> {
                ready.countDown();
                fire.await();
                return cancellations.request(
                        fixture.userId(), started.runId(), "cancel-concurrent-0001");
            });
            var second = pool.submit(() -> {
                ready.countDown();
                fire.await();
                return cancellations.request(
                        fixture.userId(), started.runId(), "cancel-concurrent-0001");
            });
            ready.await();
            fire.countDown();
            assertThat(first.get().executorRequests()).isEmpty();
            assertThat(second.get().executorRequests()).isEmpty();
        }
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT run.status::text AS run_status, step.status::text AS step_status
                        FROM public."WorkflowRun" AS run
                        JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                        WHERE run.id = ?
                        """,
                        started.runId()))
                .satisfies(value -> {
                    assertThat(value.get("run_status", String.class)).isEqualTo("cancelled");
                    assertThat(value.get("step_status", String.class)).isEqualTo("skipped");
                });
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowEvent\" WHERE \"runId\" = ? AND \"eventType\" = 'cancelled'",
                        started.runId()))
                .isEqualTo(1);
    }

    @Test
    void Accepted后尚未Preparing的queued取消不占额度且不写用量() {
        Fixture fixture = fixture("cancel-accepted-pending");
        var started = starts.start(plan(fixture, "cancel-accepted-pending-request"));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        accept(request);

        cancellations.request(fixture.userId(), started.runId(), "cancel-accepted-pending-0001");

        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?",
                        request.getStepId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"runId\" = ?",
                        started.runId()))
                .isZero();
        assertThat(eventTypes(started.runId())).endsWith("step_finished", "cancelled");
        int terminalEvents = eventTypes(started.runId()).size();
        assertThat(callbacks.failure(preProviderFailure(request)).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.SUPERSEDED);
        assertThat(callbacks.result(outputResult(request, "取消后不得物化")).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.SUPERSEDED);
        assertThat(eventTypes(started.runId())).hasSize(terminalEvents);
    }

    @Test
    void 取消中的运行Step租约过期按未知Usage收敛且不重派() {
        Flow flow = runningFlow("cancel-expired");
        cancellations.request("cancel-expired-user", flow.runId(), "cancel-expired-0001");
        database.dsl().execute(
                "UPDATE public.\"WorkflowStep\" SET \"leaseExpiresAt\" = ? WHERE id = ?",
                NOW.minusSeconds(1),
                flow.request().getStepId());

        assertThat(cancellations.settleExpired(10)).isEqualTo(1);
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT run.status::text AS run_status, step.status::text AS step_status,
                               step."usageJson"
                        FROM public."WorkflowRun" AS run
                        JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                        WHERE run.id = ? AND step.id = ?
                        """,
                        flow.runId(),
                        flow.request().getStepId()))
                .satisfies(value -> {
                    assertThat(value.get("run_status", String.class)).isEqualTo("cancelled");
                    assertThat(value.get("step_status", String.class)).isEqualTo("skipped");
                    assertThat(json.readTree(value.get("usageJson", String.class))
                                    .path("usageStatus")
                                    .asText())
                            .isEqualTo("unknown");
                });
        assertThat(eventTypes(flow.runId())).endsWith("step_finished", "cancelled");
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT status, "settledAt" FROM public."WorkflowBillingReservation"
                        WHERE "stepId" = ?
                        """,
                        flow.request().getStepId()))
                .satisfies(reservation -> {
                    assertThat(reservation.get("status", String.class))
                            .isEqualTo("reconciliation_required");
                    assertThat(reservation.get("settledAt", LocalDateTime.class)).isNull();
                });
        assertThat(dispatches.claimNext()).isEmpty();
    }

    @Test
    void 同一用户两个Run并发预留不会超卖且失败者零供应商调用() throws Exception {
        Fixture first = fixture("billing-race-a");
        Fixture second = fixtureForExistingUser("billing-race-b", first.userId());
        long oneGeneratorReservation = 46_000_000L;
        database.dsl().execute(
                "UPDATE public.\"User\" SET \"creditBalanceMicros\" = ? WHERE id = ?",
                oneGeneratorReservation,
                first.userId());
        var firstRun = starts.start(plan(first, "billing-race-a-request-0001"));
        var secondRun = starts.start(plan(second, "billing-race-b-request-0001"));
        ExecutionStepRequest firstRequest = dispatches.claimNext().orElseThrow();
        ExecutionStepRequest secondRequest = dispatches.claimNext().orElseThrow();

        accept(firstRequest);
        accept(secondRequest);
        ExecutionCallbackReceipt.StatusEnum firstOutcome;
        ExecutionCallbackReceipt.StatusEnum secondOutcome;
        try (var pool = Executors.newFixedThreadPool(2)) {
            var firstFuture = pool.submit(() ->
                    callbacks.progress(progress(firstRequest, unknownUsage())).getStatus());
            var secondFuture = pool.submit(() ->
                    callbacks.progress(progress(secondRequest, unknownUsage())).getStatus());
            firstOutcome = firstFuture.get();
            secondOutcome = secondFuture.get();
        }
        assertThat(List.of(firstOutcome, secondOutcome))
                .containsExactlyInAnyOrder(
                        ExecutionCallbackReceipt.StatusEnum.ACCEPTED,
                        ExecutionCallbackReceipt.StatusEnum.STALE);
        ExecutionStepRequest rejected = firstOutcome == ExecutionCallbackReceipt.StatusEnum.ACCEPTED
                ? secondRequest
                : firstRequest;

        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowBillingReservation\" WHERE \"userId\" = ? AND status = 'reserved'",
                        first.userId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"TokenUsage\" WHERE \"userId\" = ?",
                        first.userId()))
                .isZero();
        String rejectedRunId = rejected.getRunId();
        assertThat(rejectedRunId).isIn(firstRun.runId(), secondRun.runId());
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                        rejectedRunId)
                        .get("status", String.class))
                .isEqualTo("failed");
        ExecutionStepRequest acceptedRequest = firstOutcome == ExecutionCallbackReceipt.StatusEnum.ACCEPTED
                ? firstRequest
                : secondRequest;
        cancellations.request(
                first.userId(), acceptedRequest.getRunId(), "billing-race-cleanup-cancel");
        callbacks.failure(preProviderFailure(acceptedRequest));
    }

    @Test
    void running崩溃在journalStarted或ProviderAttempt边界都保留待对账预留() {
        Flow journalStarted = runningFlow("cancel-journal-started");
        Flow providerAttempt = runningFlow("cancel-provider-attempt");
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET "usageJson" = '{"usageStatus":"unknown","providerAttempts":1,"protocolCorrections":0,"wallTimeMillis":1000}'
                WHERE id = ?
                """,
                providerAttempt.request().getStepId());
        for (Flow flow : List.of(journalStarted, providerAttempt)) {
            cancellations.request(
                    flow.userId(),
                    flow.runId(),
                    "cancel-crash-" + flow.request().getStepId());
            database.dsl().execute(
                    "UPDATE public.\"WorkflowStep\" SET \"leaseExpiresAt\" = ? WHERE id = ?",
                    NOW.minusSeconds(1),
                    flow.request().getStepId());
        }

        assertThat(cancellations.settleExpired(10)).isEqualTo(2);
        for (Flow flow : List.of(journalStarted, providerAttempt)) {
            assertThat(database.dsl().fetchOne(
                            """
                            SELECT status FROM public."WorkflowBillingReservation"
                            WHERE "stepId" = ?
                            """,
                            flow.request().getStepId())
                    .get("status", String.class))
                    .isEqualTo("reconciliation_required");
        }
    }

    private static Flow runningFlow(String prefix) {
        Fixture fixture = fixture(prefix);
        var started = starts.start(plan(fixture, prefix + "-request-0001"));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        accept(request);
        assertThat(callbacks.progress(progress(request, unknownUsage())).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        return new Flow(started.runId(), fixture.userId(), request);
    }

    private static void enqueueRevisionGeneration(
            String runId, String sourceStepId, String artifactId, int artifactRevision) {
        String stepId = "revision-generation-" + artifactId;
        database.dsl().execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('running' AS "WorkflowRunStatus"), "updatedAt" = ?
                WHERE id = ?
                """,
                NOW,
                runId);
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt", ordinal,
                  purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken",
                  "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                  "artifactId", "artifactRevision", "modelProfile", "modelProfileVersion",
                  "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt"
                )
                SELECT ?, "runId", "agentId", "stepType", CAST('pending' AS "WorkflowStepStatus"),
                       input, ?, (SELECT max(ordinal) + 1 FROM public."WorkflowStep" WHERE "runId" = ?),
                       'generation', lane, 0, ?, 0, ?, ?, "inputHash", "evidenceBundleId",
                       ?, ?, "modelProfile", "modelProfileVersion", "outputSchema",
                       "outputSchemaVersion", "budgetJson", ?, ?
                FROM public."WorkflowStep" WHERE id = ? AND "runId" = ?
                """,
                stepId,
                NOW,
                runId,
                NOW,
                runId + "." + stepId,
                sha256(stepId),
                artifactId,
                artifactRevision,
                NOW,
                NOW,
                sourceStepId,
                runId);
    }

    private static void accept(ExecutionStepRequest request) {
        dispatches.recordAccepted(request, accepted(request));
    }

    private static ExecutionStepAccepted accepted(ExecutionStepRequest request) {
        return accepted(request, agentResolved(request));
    }

    private static ExecutionStepAccepted accepted(
            ExecutionStepRequest request,
            cn.inkforge.contracts.agent.ResolvedModelRef resolved) {
        return new ExecutionStepAccepted(
                API_NOW,
                request.getFencingToken(),
                request.getJobId(),
                request.getNovelId(),
                "2.0",
                request.getRequestHash(),
                resolved,
                request.getRunId(),
                ExecutionStepAccepted.StatusEnum.ACCEPTED,
                request.getStepId());
    }

    private static ExecutionStepProgress progress(
            ExecutionStepRequest request, StepUsage usage) {
        return new ExecutionStepProgress(
                0,
                request.getFencingToken(),
                request.getJobId(),
                request.getNovelId(),
                API_NOW,
                ExecutionStepProgress.PhaseEnum.PREPARING,
                "preparing",
                "progress-" + request.getJobId(),
                "2.0",
                request.getRequestHash(),
                apiResolved(request),
                request.getRunId(),
                1,
                request.getStepId(),
                usage,
                false);
    }

    private static ExecutionStepResult outputResult(
            ExecutionStepRequest request, String replacement) {
        Map<String, Object> output = new LinkedHashMap<>();
        output.put("replacement", replacement);
        output.put("contentSha256", sha256(replacement));
        ExecutionStepResult result = new ExecutionStepResult(
                API_NOW,
                request.getFencingToken(),
                request.getInputHash(),
                request.getJobId(),
                request.getNovelId(),
                "2.0",
                request.getRequestHash(),
                apiResolved(request),
                "0".repeat(64),
                ExecutionStepResult.ResultKindEnum.OUTPUT,
                request.getRunId(),
                request.getStepId(),
                partialUsage(request.getPurpose().equals("review")))
                .output(output);
        result.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
    }

    private static ExecutionStepResult reviewResult(ExecutionStepRequest request) {
        PromptProfileRef prompt = new PromptProfileRef()
                .name(request.getModelProfile().getPromptProfile().getName())
                .version(request.getModelProfile().getPromptProfile().getVersion())
                .sha256(request.getModelProfile().getPromptProfile().getSha256());
        ModelProfileRef profile = new ModelProfileRef()
                .deploymentProfileKey(request.getModelProfile().getDeploymentProfileKey())
                .profile(request.getModelProfile().getProfile())
                .promptProfile(prompt)
                .reasoningMode(ModelProfileRef.ReasoningModeEnum.fromValue(
                        request.getModelProfile().getReasoningMode().getValue()))
                .version(request.getModelProfile().getVersion());
        @SuppressWarnings("unchecked")
        Map<String, Object> task = (Map<String, Object>) request.getInput().get("task");
        EvidenceEvaluation evaluation = new EvidenceEvaluation(
                        EvidenceEvaluation.ContentVerdictEnum.PASS,
                        "evaluation-" + request.getStepId(),
                        profile,
                        request.getEvidenceBundle().getId(),
                        EvidenceEvaluation.ExecutionStatusEnum.COMPLETED,
                        apiResolved(request),
                        String.valueOf(task.get("rubricVersion")),
                        request.getRunId(),
                        request.getStepId())
                .artifactId(request.getArtifactId())
                .artifactRevision(request.getArtifactRevision())
                .findings(List.of());
        ExecutionStepResult result = new ExecutionStepResult(
                        API_NOW,
                        request.getFencingToken(),
                        request.getInputHash(),
                        request.getJobId(),
                        request.getNovelId(),
                        "2.0",
                        request.getRequestHash(),
                        apiResolved(request),
                        "0".repeat(64),
                        ExecutionStepResult.ResultKindEnum.EVALUATION,
                        request.getRunId(),
                        request.getStepId(),
                        partialUsage(true))
                .evaluation(evaluation);
        result.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
    }

    private static ExecutionStepFailure reviewFailure(ExecutionStepRequest request) {
        ExecutionStepFailure failure = new ExecutionStepFailure(
                ExecutionStepFailure.ErrorCategoryEnum.PROVIDER_TERMINAL,
                "MODEL_OUTPUT_FILTERED",
                API_NOW,
                request.getFencingToken(),
                request.getInputHash(),
                request.getJobId(),
                request.getNovelId(),
                false,
                "2.0",
                request.getRequestHash(),
                apiResolved(request),
                "0".repeat(64),
                false,
                request.getRunId(),
                request.getStepId(),
                partialUsage(true));
        failure.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.failureHashMaterial(failure)));
        return failure;
    }

    private static ExecutionStepFailure preProviderFailure(ExecutionStepRequest request) {
        ExecutionStepFailure failure = new ExecutionStepFailure(
                ExecutionStepFailure.ErrorCategoryEnum.PROVIDER_TERMINAL,
                "MODEL_PROFILE_UNAVAILABLE",
                API_NOW,
                request.getFencingToken(),
                request.getInputHash(),
                request.getJobId(),
                request.getNovelId(),
                false,
                "2.0",
                request.getRequestHash(),
                apiResolved(request),
                "0".repeat(64),
                false,
                request.getRunId(),
                request.getStepId(),
                unknownUsage());
        failure.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.failureHashMaterial(failure)));
        return failure;
    }

    private static ExecutionStepFailure budgetFailure(ExecutionStepRequest request) {
        ExecutionStepFailure failure = new ExecutionStepFailure(
                ExecutionStepFailure.ErrorCategoryEnum.VALIDATION,
                "STEP_BUDGET_EXCEEDED",
                API_NOW,
                request.getFencingToken(),
                request.getInputHash(),
                request.getJobId(),
                request.getNovelId(),
                false,
                "2.0",
                request.getRequestHash(),
                apiResolved(request),
                "0".repeat(64),
                false,
                request.getRunId(),
                request.getStepId(),
                overBudgetUsage());
        failure.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.failureHashMaterial(failure)));
        return failure;
    }

    private static cn.inkforge.contracts.agent.ResolvedModelRef agentResolved(
            ExecutionStepRequest request) {
        return agentResolved(request, "endpoint.deepseek-official.v1");
    }

    private static cn.inkforge.contracts.agent.ResolvedModelRef agentResolved(
            ExecutionStepRequest request, String endpointProfile) {
        String reasoning = request.getModelProfile().getReasoningMode().getValue();
        String deployment = request.getModelProfile().getDeploymentProfileKey();
        String fingerprint = WorkflowResolvedModel.fingerprint(
                deployment,
                "openai_compatible",
                "deepseek-v4-flash",
                "transport.deepseek-v4.v1",
                endpointProfile,
                "chat_json_output_v1",
                "capability.deepseek-v4.chat-json.v1",
                reasoning,
                false);
        return new cn.inkforge.contracts.agent.ResolvedModelRef(
                "capability.deepseek-v4.chat-json.v1",
                fingerprint,
                deployment,
                endpointProfile,
                "deepseek-v4-flash",
                "openai_compatible",
                cn.inkforge.contracts.agent.ResolvedModelRef.ReasoningModeEnum.fromValue(reasoning),
                cn.inkforge.contracts.agent.ResolvedModelRef.StructuredOutputRouteEnum.CHAT_JSON_OUTPUT_V1,
                false,
                "transport.deepseek-v4.v1");
    }

    private static ResolvedModelRef apiResolved(ExecutionStepRequest request) {
        return apiResolved(request, "endpoint.deepseek-official.v1");
    }

    private static ResolvedModelRef apiResolved(
            ExecutionStepRequest request, String endpointProfile) {
        cn.inkforge.contracts.agent.ResolvedModelRef value =
                agentResolved(request, endpointProfile);
        return new ResolvedModelRef(
                value.getCapabilityVersion(),
                value.getDeploymentFingerprint(),
                value.getDeploymentProfileKey(),
                value.getEndpointProfile(),
                value.getModel(),
                value.getProvider(),
                ResolvedModelRef.ReasoningModeEnum.fromValue(
                        value.getReasoningMode().getValue()),
                ResolvedModelRef.StructuredOutputRouteEnum.fromValue(
                        value.getStructuredOutputRoute().getValue()),
                value.getSupportsRequestIdempotency(),
                value.getTransportProfile());
    }

    private static cn.inkforge.contracts.agent.ResolvedModelRef fakeAgentResolved(
            ExecutionStepRequest request) {
        String reasoning = request.getModelProfile().getReasoningMode().getValue();
        String deployment = request.getModelProfile().getDeploymentProfileKey();
        String fingerprint = WorkflowResolvedModel.fingerprint(
                deployment,
                "fake",
                "fake",
                "transport.fake.v1",
                "endpoint.local-fake.v1",
                "responses_json_schema_v1",
                "capability.fake.structured-output.v1",
                reasoning,
                true);
        return new cn.inkforge.contracts.agent.ResolvedModelRef(
                "capability.fake.structured-output.v1",
                fingerprint,
                deployment,
                "endpoint.local-fake.v1",
                "fake",
                "fake",
                cn.inkforge.contracts.agent.ResolvedModelRef.ReasoningModeEnum.fromValue(reasoning),
                cn.inkforge.contracts.agent.ResolvedModelRef.StructuredOutputRouteEnum.RESPONSES_JSON_SCHEMA_V1,
                true,
                "transport.fake.v1");
    }

    private static ResolvedModelRef fakeApiResolved(ExecutionStepRequest request) {
        cn.inkforge.contracts.agent.ResolvedModelRef value = fakeAgentResolved(request);
        return new ResolvedModelRef(
                value.getCapabilityVersion(),
                value.getDeploymentFingerprint(),
                value.getDeploymentProfileKey(),
                value.getEndpointProfile(),
                value.getModel(),
                value.getProvider(),
                ResolvedModelRef.ReasoningModeEnum.fromValue(
                        value.getReasoningMode().getValue()),
                ResolvedModelRef.StructuredOutputRouteEnum.fromValue(
                        value.getStructuredOutputRoute().getValue()),
                value.getSupportsRequestIdempotency(),
                value.getTransportProfile());
    }

    private static StepUsage unknownUsage() {
        return new StepUsage(
                0, 0, StepUsage.UsageStatusEnum.UNKNOWN, 0);
    }

    private static StepUsage partialUsage(boolean review) {
        int reasoning = review ? 0 : 10;
        int visible = review ? 20 : 10;
        return new StepUsage(0, 1, StepUsage.UsageStatusEnum.PARTIAL, 1_000)
                .inputTokens(100)
                .cachedTokens(0)
                .promptCacheMissTokens(100)
                .completionTokens(20)
                .reasoningTokens(reasoning)
                .visibleOutputTokens(visible);
    }

    private static StepUsage overBudgetUsage() {
        return new StepUsage(0, 1, StepUsage.UsageStatusEnum.PARTIAL, 2_000)
                .inputTokens(30_001)
                .cachedTokens(0)
                .promptCacheMissTokens(30_001)
                .completionTokens(8_001)
                .reasoningTokens(4_000)
                .visibleOutputTokens(4_001);
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

    private static Fixture fixture(String prefix) {
        Fixture value = new Fixture(
                prefix + "-user",
                prefix + "-novel",
                prefix + "-chapter",
                prefix + "-session");
        database.dsl().execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'test', 500000000, ?, ?)
                """,
                value.userId(),
                value.userId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                value.novelId(),
                prefix,
                value.userId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', '甲😀乙', 1, 'drafting', ?, ?)
                """,
                value.chapterId(),
                value.novelId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                value.sessionId(),
                value.novelId(),
                value.chapterId(),
                NOW,
                NOW);
        return value;
    }

    private static Fixture fixtureForExistingUser(String prefix, String userId) {
        Fixture value = new Fixture(
                userId,
                prefix + "-novel",
                prefix + "-chapter",
                prefix + "-session");
        database.dsl().execute(
                """
                INSERT INTO public."Novel" (id, name, "userId", "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                value.novelId(),
                prefix,
                value.userId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', '甲😀乙', 1, 'drafting', ?, ?)
                """,
                value.chapterId(),
                value.novelId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                value.sessionId(),
                value.novelId(),
                value.chapterId(),
                NOW,
                NOW);
        return value;
    }

    private static List<String> eventTypes(String runId) {
        return database.dsl().fetch(
                        """
                        SELECT "eventType" FROM public."WorkflowEvent"
                        WHERE "runId" = ? ORDER BY sequence
                        """,
                        runId)
                .getValues("eventType", String.class);
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

    private record Flow(String runId, String userId, ExecutionStepRequest request) {}
}
