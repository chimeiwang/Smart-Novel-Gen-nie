package cn.inkforge.core.reviews.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.domain.ReviewArtifactRules;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.domain.DurableSelectionArtifact;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.jooq.Record;
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
class JooqDurableReviewDecisionStoreTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T05:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-09-01T05:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static ExecutionRegistry registry;
    private static JooqReviewRepository reviews;
    private static JooqWorkflowStartRepository starts;

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
        CuidV1Generator ids = new CuidV1Generator(CLOCK);
        JooqFormalArtifactWriter formal =
                new JooqFormalArtifactWriter(database, ids, CLOCK, json);
        reviews = new JooqReviewRepository(database, ids, CLOCK, json, formal, registry);
        starts = new JooqWorkflowStartRepository(database, ids, CLOCK, json);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 编辑后批准只替换Unicode选区并原子完成Run() {
        Fixture fixture = waitingArtifact("decision-approve", true);
        ReviewArtifactDecisionRequest request = decision(
                        "decision-approve-client-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)
                .editedReplacement("用户改写");

        WritingRunV2Response accepted = (WritingRunV2Response)
                reviews.decide(fixture.userId(), fixture.artifactId(), request);
        WritingRunV2Response replay = (WritingRunV2Response)
                reviews.decide(fixture.userId(), fixture.artifactId(), request);

        assertThat(replay).isEqualTo(accepted);
        assertThat(accepted.getEngineVersion()).isEqualTo(2);
        assertThat(accepted.getRunId()).isEqualTo(fixture.runId());
        assertThat(accepted.getTaskId()).isNull();
        assertThat(accepted.getCommandId()).isNull();
        assertThat(accepted.getCommandStatus()).isNull();
        assertThat(accepted.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.COMPLETED);
        assertThat(accepted.getArtifact().getArtifactRevision()).isEqualTo(2);
        assertThat(accepted.getArtifact().getStatus().getValue()).isEqualTo("applied");
        assertThat(accepted.getArtifact().getActionable()).isFalse();
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲用户改写乙");
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?",
                        fixture.artifactId()))
                .isEqualTo(2);
        assertThat(database.dsl().fetchOne(
                                """
                                SELECT "createdByAgent", "payloadJson" FROM public."ReviewArtifactRevision"
                                WHERE "artifactId" = ? AND revision = 2
                                """,
                                fixture.artifactId())
                        .get("createdByAgent", String.class))
                .isEqualTo("用户");
        assertThat(eventTypes(fixture.runId()))
                .endsWith("applying", "completed");
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'",
                        fixture.runId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingRunCommand\" WHERE \"taskId\" = ?",
                        fixture.runId()))
                .isZero();
    }

    @Test
    void 丢弃保留Artifact全部RevisionEvaluation并使Run终结() {
        Fixture fixture = waitingArtifact("decision-discard", true);

        WritingRunV2Response response = (WritingRunV2Response) reviews.decide(
                fixture.userId(),
                fixture.artifactId(),
                decision(
                        "decision-discard-client-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.DISCARD));

        assertThat(response.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.COMPLETED);
        assertThat(response.getArtifact().getStatus().getValue()).isEqualTo("draft");
        assertThat(response.getArtifact().getActionable()).isFalse();
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifact\" WHERE id = ?",
                        fixture.artifactId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?",
                        fixture.artifactId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowEvaluation\" WHERE \"artifactId\" = ?",
                        fixture.artifactId()))
                .isEqualTo(2);
        assertThat(reviews.list(
                                fixture.userId(),
                                fixture.novelId(),
                                fixture.chapterId(),
                                null,
                                "awaiting_user",
                                null,
                                null,
                                50)
                        .getItems())
                .noneMatch(item -> item.getId().equals(fixture.artifactId()));
        assertThat(reviews.getDetail(
                                fixture.userId(), fixture.artifactId(), 1, null)
                        .response()
                        .getStatus()
                        .getValue())
                .isEqualTo("draft");
        assertThat(eventTypes(fixture.runId())).endsWith("completed");
    }

    @Test
    void 返工创建同Evidence旧Revision绑定的新Generation且幂等不复制() {
        Fixture fixture = waitingArtifact("decision-revise", true);
        ReviewArtifactDecisionRequest request = decision(
                        "decision-revise-client-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.REVISE)
                .userMessage("保留含义但把动作写得更紧凑");

        WritingRunV2Response first = (WritingRunV2Response)
                reviews.decide(fixture.userId(), fixture.artifactId(), request);
        WritingRunV2Response replay = (WritingRunV2Response)
                reviews.decide(fixture.userId(), fixture.artifactId(), request);

        assertThat(replay).isEqualTo(first);
        assertThat(first.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.RUNNING);
        assertThat(first.getCurrentStep().getPurpose()).isEqualTo("generation");
        assertThat(first.getCurrentStep().getStatus().getValue()).isEqualTo("pending");
        assertThat(first.getArtifact().getStatus().getValue()).isEqualTo("draft");
        Record generation = database.dsl().fetchOne(
                """
                SELECT "evidenceBundleId", "artifactId", "artifactRevision", input
                FROM public."WorkflowStep"
                WHERE "runId" = ? AND purpose = 'generation'
                ORDER BY ordinal DESC LIMIT 1
                """,
                fixture.runId());
        assertThat(generation.get("evidenceBundleId", String.class))
                .isEqualTo(fixture.bundleId());
        assertThat(generation.get("artifactId", String.class)).isEqualTo(fixture.artifactId());
        assertThat(generation.get("artifactRevision", Integer.class)).isEqualTo(1);
        assertThat(json.readTree(generation.get("input", String.class))
                        .path("userInstruction").asText())
                .isEqualTo("保留含义但把动作写得更紧凑");
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'",
                        fixture.runId()))
                .isEqualTo(2);
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?",
                        fixture.artifactId()))
                .isEqualTo(1);

        ReviewArtifactDecisionRequest changed = decision(
                        "decision-revise-client-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.REVISE)
                .userMessage("换一条不同意见");
        assertThatThrownBy(() -> reviews.decide(
                        fixture.userId(), fixture.artifactId(), changed))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 当前Operation下线后旧Run仍可返工或批准而新解析被拒绝() {
        ExecutionRegistry downlined = ExecutionRegistryFixtures.selectionOperationDownlined(
                ExecutionRegistry.Environment.TEST);
        assertThatThrownBy(() -> downlined.resolve(
                        "long_serial.rewrite_chapter_selection", false))
                .hasMessageContaining("尚未启用");
        CuidV1Generator ids = new CuidV1Generator(Clock.offset(CLOCK, java.time.Duration.ofMillis(3)));
        JooqReviewRepository afterUpgrade = new JooqReviewRepository(
                database,
                ids,
                CLOCK,
                json,
                new JooqFormalArtifactWriter(database, ids, CLOCK, json),
                downlined);

        Fixture revised = waitingArtifact("decision-downlined-revise", true);
        WritingRunV2Response revision = (WritingRunV2Response) afterUpgrade.decide(
                revised.userId(),
                revised.artifactId(),
                decision(
                                "decision-downlined-revise-client-0001",
                                ReviewArtifactDecisionRequest.DecisionEnum.REVISE)
                        .userMessage("目录升级后继续返工"));
        assertThat(revision.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.RUNNING);
        assertThat(database.dsl().fetchOne(
                                """
                                SELECT "modelProfile", "outputSchema", "budgetJson"
                                FROM public."WorkflowStep"
                                WHERE "runId" = ? AND purpose = 'generation'
                                ORDER BY ordinal DESC LIMIT 1
                                """,
                                revised.runId()))
                .satisfies(step -> {
                    assertThat(step.get("modelProfile", String.class))
                            .isEqualTo("writer.chapter_selection.v1");
                    assertThat(step.get("outputSchema", String.class))
                            .isEqualTo("output.chapter_selection_replacement.v1");
                    assertThat(step.get("budgetJson", String.class))
                            .contains("step_budget.long_serial.rewrite_chapter_selection.generator.v1");
                });

        Fixture approved = waitingArtifact("decision-downlined-approve", true);
        WritingRunV2Response approval = (WritingRunV2Response) afterUpgrade.decide(
                approved.userId(),
                approved.artifactId(),
                decision(
                        "decision-downlined-approve-client-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.APPROVE));
        assertThat(approval.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.COMPLETED);
        assertThat(chapterContent(approved.chapterId())).isEqualTo("甲模型改写乙");
    }

    @Test
    void 来源漂移时不创建用户Revision决定StepEvent或正式写入() {
        Fixture fixture = waitingArtifact("decision-source-drift", true);
        int eventsBefore = eventTypes(fixture.runId()).size();
        database.dsl().execute(
                "UPDATE public.\"Chapter\" SET content = '漂移正文', \"updatedAt\" = ? WHERE id = ?",
                NOW.plusSeconds(1),
                fixture.chapterId());

        assertThatThrownBy(() -> reviews.decide(
                        fixture.userId(),
                        fixture.artifactId(),
                        decision(
                                        "decision-source-drift-client-0001",
                                        ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)
                                .editedReplacement("不得落库")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("ARTIFACT_SOURCE_VERSION_CONFLICT"));
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("漂移正文");
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?",
                        fixture.artifactId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'",
                        fixture.runId()))
                .isZero();
        assertThat(eventTypes(fixture.runId())).hasSize(eventsBefore);
    }

    @Test
    void 列表只返回有界摘要且精确Revision详情重建并支持强ETag() {
        Fixture fixture = waitingArtifact("decision-detail", true);

        var page = reviews.listSummaries(
                fixture.userId(),
                fixture.novelId(),
                fixture.chapterId(),
                null,
                "awaiting_user",
                null,
                null,
                50);
        assertThat(page.getItems()).singleElement().satisfies(summary -> {
            assertThat(summary.getEngineVersion().getValue()).isEqualTo(2);
            assertThat(summary.getId()).isEqualTo(fixture.artifactId());
            assertThat(summary.getRevision()).isEqualTo(1);
            assertThat(summary.getActionable()).isTrue();
        });

        var detail = reviews.getDetail(
                fixture.userId(), fixture.artifactId(), 1, null);
        assertThat(detail.etag()).matches("\"[0-9a-f]{64}\"");
        assertThat(detail.response().getEngineVersion().getValue()).isEqualTo(2);
        assertThat(detail.response().getPayload())
                .containsEntry("selectedText", "😀")
                .containsEntry("candidate", "甲模型改写乙");
        @SuppressWarnings("unchecked")
        Map<String, Object> diff =
                (Map<String, Object>) detail.response().getDiff().get();
        assertThat(diff)
                .containsEntry("before", "甲😀乙")
                .containsEntry("after", "甲模型改写乙");
        assertThat(detail.response().getEvaluations()).hasSize(2);
        assertThat(detail.response().getSourceBindingStatus().getValue())
                .isEqualTo("verified");

        var notModified = reviews.getDetail(
                fixture.userId(), fixture.artifactId(), 1, detail.etag());
        assertThat(notModified.notModified()).isTrue();
        assertThat(notModified.response()).isNull();
        assertThatThrownBy(() -> reviews.get(
                        fixture.userId(), fixture.artifactId()))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("ARTIFACT_REVISION_REQUIRED"));
    }

    @Test
    void 两个并发决定只有一个提交且终态不能翻转() throws Exception {
        Fixture fixture = waitingArtifact("decision-race", true);
        CountDownLatch gate = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Object> approve = executor.submit(() -> decideAfterGate(
                    gate,
                    fixture,
                    decision(
                            "decision-race-client-approve",
                            ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)));
            Future<Object> discard = executor.submit(() -> decideAfterGate(
                    gate,
                    fixture,
                    decision(
                            "decision-race-client-discard",
                            ReviewArtifactDecisionRequest.DecisionEnum.DISCARD)));
            gate.countDown();
            List<Object> results = List.of(approve.get(), discard.get());

            assertThat(results.stream().filter(WritingRunV2Response.class::isInstance).count())
                    .isEqualTo(1);
            assertThat(results.stream()
                            .filter(ApiException.class::isInstance)
                            .map(ApiException.class::cast)
                            .map(ApiException::code))
                    .containsExactly("RUN_TERMINAL");
            assertThat(count(
                            "SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'",
                            fixture.runId()))
                    .isEqualTo(1);
            assertThat(database.dsl().fetchOne(
                                    "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                                    fixture.runId())
                            .get("status", String.class))
                    .isEqualTo("completed");
        } finally {
            executor.shutdownNow();
        }
    }

    private static Object decideAfterGate(
            CountDownLatch gate,
            Fixture fixture,
            ReviewArtifactDecisionRequest request) throws InterruptedException {
        gate.await();
        try {
            return reviews.decide(fixture.userId(), fixture.artifactId(), request);
        } catch (ApiException exception) {
            return exception;
        }
    }

    private static Fixture waitingArtifact(String prefix, boolean reviewers) {
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
        ExecutionRegistry.ResolvedOperation operation = registry.resolve(
                "long_serial.rewrite_chapter_selection", false);
        String selectedHash = ReviewArtifactRules.sha256("😀");
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("selectionStart", 1);
        input.put("selectionEnd", 2);
        input.put("selectedTextSha256", selectedHash);
        input.put("userInstruction", "改写这个表情");
        var started = starts.start(new WorkflowStartPlan(
                userId,
                prefix + "-start-client-0001",
                ReviewArtifactRules.sha256(prefix),
                operation.operation().workflow(),
                operation.operation().operation(),
                "1",
                "chapter_generation",
                novelId,
                chapterId,
                sessionId,
                "chapter_content",
                chapterId,
                input,
                operation.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_content",
                        chapterId,
                        true,
                        null,
                        DatabaseTimestamp.api(NOW),
                        "甲😀乙",
                        null,
                        1,
                        2,
                        Map.of(
                                "role", "selection_source",
                                "baseContentHash", ReviewArtifactRules.sha256("甲😀乙"),
                                "selectedTextHash", selectedHash))),
                operation.operation().runBudget(),
                ExecutionPlanSnapshot.freeze(
                        registry.catalogVersion(), registry.manifestFingerprint(), operation),
                new WorkflowInitialStepPlan(
                        "generation",
                        operation.operation().lane(),
                        input,
                        operation.generatorProfile(),
                        operation.generatorStepBudget(),
                        operation.outputSchema())));
        String bundleId = database.dsl().fetchOne(
                        "SELECT \"currentEvidenceBundleId\" FROM public.\"WorkflowRun\" WHERE id = ?",
                        started.runId())
                .get("currentEvidenceBundleId", String.class);
        String artifactId = prefix + "-artifact";
        String evidenceItemId = database.dsl().fetchOne(
                        "SELECT id FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\" = ?",
                        bundleId)
                .get("id", String.class);
        DurableSelectionArtifact.Stored stored = DurableSelectionArtifact.create(
                bundleId,
                evidenceItemId,
                chapterId,
                DatabaseTimestamp.api(NOW),
                ReviewArtifactRules.sha256("甲😀乙"),
                1,
                2,
                selectedHash,
                "模型改写",
                ReviewArtifactRules.sha256("模型改写"),
                ReviewArtifactRules.sha256("甲模型改写乙"),
                started.stepId(),
                "a".repeat(64));
        database.dsl().execute(
                """
                INSERT INTO public."ReviewArtifact" (
                  id, "novelId", "chapterId", "taskId", "workflowRunId", "artifactKey",
                  kind, status, title, "payloadJson", "diffJson", "createdByAgent",
                  "updatedByAgent", revision, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, NULL, ?, ?, CAST('chapter_draft' AS "ReviewArtifactKind"),
                  CAST('awaiting_user' AS "ReviewArtifactStatus"), '章节选区改写', ?, ?,
                  'writer.chapter_selection.v1', 'writer.chapter_selection.v1', 1, ?, ?)
                """,
                artifactId,
                novelId,
                chapterId,
                started.runId(),
                "workflow:" + started.runId() + ":candidate",
                json.writeValueAsString(stored.payload()),
                json.writeValueAsString(stored.diff()),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."ReviewArtifactRevision" (
                  id, "artifactId", revision, "payloadJson", "diffJson", "createdByAgent", "createdAt"
                ) VALUES (?, ?, 1, ?, ?, 'writer.chapter_selection.v1', ?)
                """,
                prefix + "-revision-1",
                artifactId,
                json.writeValueAsString(stored.payload()),
                json.writeValueAsString(stored.diff()),
                NOW);
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('completed' AS "WorkflowStepStatus"), output = ?,
                    "resultHash" = ?, "artifactId" = ?, "artifactRevision" = 1,
                    "updatedAt" = ?, "completedAt" = ?
                WHERE id = ?
                """,
                json.writeValueAsString(Map.of(
                        "replacement", "模型改写",
                        "contentSha256", ReviewArtifactRules.sha256("模型改写"))),
                "a".repeat(64),
                artifactId,
                NOW,
                NOW,
                started.stepId());
        if (reviewers) {
            insertEvaluation(prefix, started.runId(), bundleId, artifactId, 2);
            insertEvaluation(prefix, started.runId(), bundleId, artifactId, 3);
        }
        database.dsl().execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('waiting_user' AS "WorkflowRunStatus"), revision = 2,
                    "updatedAt" = ? WHERE id = ?
                """,
                NOW,
                started.runId());
        return new Fixture(
                userId, novelId, chapterId, sessionId, started.runId(), bundleId, artifactId);
    }

    private static void insertEvaluation(
            String prefix,
            String runId,
            String bundleId,
            String artifactId,
            int ordinal) {
        String stepId = prefix + "-review-step-" + ordinal;
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, output, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "fencingToken", "idempotencyKey",
                  "requestHash", "inputHash", "resultHash", "evidenceBundleId", "artifactId",
                  "artifactRevision", "submittedAt", "updatedAt", "completedAt"
                ) VALUES (?, ?, 'reviewer', CAST('agent' AS "WorkflowStepType"),
                  CAST('completed' AS "WorkflowStepStatus"), '{}', '{}', ?, ?, 'review',
                  'interactive', 1, 1, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                stepId,
                runId,
                NOW,
                ordinal,
                runId + "." + stepId,
                Integer.toHexString(ordinal).repeat(64).substring(0, 64),
                Integer.toHexString(ordinal + 1).repeat(64).substring(0, 64),
                Integer.toHexString(ordinal + 2).repeat(64).substring(0, 64),
                bundleId,
                artifactId,
                NOW,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowEvaluation" (
                  id, "runId", "stepId", "evidenceBundleId", "artifactId", "artifactRevision",
                  "evaluatorProfile", "rubricVersion", "executionStatus", "contentVerdict",
                  "findingsJson", "createdAt"
                ) VALUES (?, ?, ?, ?, ?, 1, ?, 'rubric.chapter_selection.review.v1',
                  'completed', 'pass', '[]', ?)
                """,
                prefix + "-evaluation-" + ordinal,
                runId,
                stepId,
                bundleId,
                artifactId,
                "reviewer-" + ordinal,
                NOW);
    }

    private static ReviewArtifactDecisionRequest decision(
            String clientRequestId,
            ReviewArtifactDecisionRequest.DecisionEnum decision) {
        return new ReviewArtifactDecisionRequest(clientRequestId, decision, 1)
                .engineVersion(ReviewArtifactDecisionRequest.EngineVersionEnum.NUMBER_2);
    }

    private static String chapterContent(String chapterId) {
        return database.dsl().fetchOne(
                        "SELECT content FROM public.\"Chapter\" WHERE id = ?", chapterId)
                .get("content", String.class);
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
        return Math.toIntExact(database.dsl().fetchOne(sql, binding).get(0, Long.class));
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
            String runId,
            String bundleId,
            String artifactId) {}
}
