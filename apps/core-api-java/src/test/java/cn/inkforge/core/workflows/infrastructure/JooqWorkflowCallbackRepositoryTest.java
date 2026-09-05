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
import org.openapitools.jackson.nullable.JsonNullable;
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
    private static ExecutionRegistry.ResolvedOperation answerOperation;
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
        answerOperation = registry.resolve("long_serial.answer_question", false);
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
    void 结构化生成回调到真实复审详情与采用链路保存唯一原始候选() {
        Fixture f = fixture("structured-live-callback");
        var resolved = cn.inkforge.core.reviews.infrastructure.AgentUpdatesReviewTestSupport.operation(registry, json, "create_lore");
        var reader = new cn.inkforge.core.reviews.infrastructure.JooqAgentUpdatesEvidenceReader(json);
        Map<String, Object> input = Map.of("userInstruction", "创建资料", "target", Map.of("type", "novel", "id", f.novelId()), "scope", Map.of("kind", "novel"));
        WorkflowEvidenceItemPlan indexEvidence = database.transactionResult(tx -> reader.captureIndex(tx, f.novelId()));
        var plan = new WorkflowStartPlan(f.userId(), "structured-live-callback-request-0001", sha256("structured-live-callback-request-0001"),
                "long_serial", "create_lore", registry.catalogVersion(), "chapter_generation", f.novelId(), f.chapterId(), f.sessionId(),
                "novel", f.novelId(), input, resolved.operation().evidencePolicy(), List.of(indexEvidence),
                resolved.operation().runBudget(), ExecutionPlanSnapshot.freeze(registry.catalogVersion(), registry.manifestFingerprint(), resolved),
                new WorkflowInitialStepPlan("generation", resolved.operation().lane(), input, resolved.generatorProfile(), resolved.generatorStepBudget(), resolved.outputSchema()));
        var started = starts.start(plan);
        var realCallbacks = new JooqWorkflowCallbackRepository(database, new CuidV1Generator(CLOCK), CLOCK, json, registry, Duration.ofSeconds(30),
                new JooqWorkflowExecutionContextReader(json), () -> null,
                () -> cn.inkforge.core.reviews.infrastructure.AgentUpdatesReviewTestSupport.preparation(json));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(started.runId());
        accept(request);
        realCallbacks.progress(progress(request, unknownUsage()));
        Map<String, Object> updates = Map.of("characters", List.of(Map.of("action", "create", "name", "回调新人物", "background", "完整原始资料")));
        Map<String, Object> output = Map.of("summary", "完整原始说明", "updates", updates, "updatesSha256", ExecutionCanonicalJson.sha256(updates));
        ExecutionStepResult generation = outputResult(request, "占位后立即替换为严格结构化结果").output(output);
        generation.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(generation)));
        assertThat(realCallbacks.result(generation).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(realCallbacks.result(generation).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        String artifact = database.dsl().fetchOne("SELECT id FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", started.runId()).get(0, String.class);
        assertThat(database.dsl().fetchOne("SELECT output FROM public.\"WorkflowStep\" WHERE id = ?", request.getStepId()).get(0, String.class))
                .contains("updatesSha256").doesNotContain("完整原始资料");
        for (int index = 0; index < resolved.reviewers().size(); index++) {
            var reviewer = dispatches.claimNext().orElseThrow();
            assertThat(reviewer.getRunId()).isEqualTo(started.runId());
            assertThat(reviewer.getInput().get("candidate")).isEqualTo(output);
            accept(reviewer);
            realCallbacks.progress(progress(reviewer, unknownUsage()));
            realCallbacks.result(reviewResult(reviewer));
        }
        var reviewRepository = cn.inkforge.core.reviews.infrastructure.AgentUpdatesReviewTestSupport.repository(database, new CuidV1Generator(CLOCK), CLOCK, json, registry);
        var detail = reviewRepository.getDetail(f.userId(), artifact, 1, null).response();
        assertThat(detail.getSummary()).isEqualTo("完整原始说明");
        assertThat(json.writeValueAsString(detail.getDiff().orElse(null))).contains("完整原始资料");
        assertThat(count("SELECT count(*) FROM public.\"Character\" WHERE \"novelId\" = ?", f.novelId())).isZero();
        var decision = new cn.inkforge.contracts.api.ReviewArtifactDecisionRequest("structured-live-callback-approve-0001",
                cn.inkforge.contracts.api.ReviewArtifactDecisionRequest.DecisionEnum.APPROVE, 1)
                .engineVersion(cn.inkforge.contracts.api.ReviewArtifactDecisionRequest.EngineVersionEnum.NUMBER_2);
        var completed = reviewRepository.decide(f.userId(), artifact, decision);
        assertThat(json.valueToTree(completed).path("status").asText()).isEqualTo("completed");
        assertThat(count("SELECT count(*) FROM public.\"Character\" WHERE \"novelId\" = ? AND name = '回调新人物'", f.novelId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", started.runId())).isEqualTo(resolved.reviewers().size() + 2);
    }

    @Test
    void 五项真实资产按需补齐后在同Run完成生成复审与正式采用() {
        for (String name : List.of("create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing")) {
            ExpansionFlow flow = expansionFlow("expand-" + name, name);
            ExecutionStepRequest first = flow.request();
            String originalBundle = first.getEvidenceBundle().getId();
            String originalRows = evidenceRows(originalBundle);
            ExecutionStepResult requested = expansionResult(first, flow.characterIds().getFirst());
            assertThat(flow.callbacks().result(requested).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
            assertThat(flow.callbacks().result(requested).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
            assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", first.getRunId())).isEqualTo(1);
            assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", first.getRunId())).isEqualTo(2);
            assertThat(evidenceRows(originalBundle)).isEqualTo(originalRows);
            assertThat(count("SELECT count(*) FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", first.getRunId())).isZero();

            ExecutionStepRequest next = nextExpansionStep(flow);
            assertThat(next.getInput()).isEqualTo(first.getInput());
            assertThat(next.getInputHash()).isEqualTo(first.getInputHash());
            assertThat(next.getRequestHash()).isNotEqualTo(first.getRequestHash());
            assertThat(next.getModelProfile()).isEqualTo(first.getModelProfile());
            assertThat(next.getOutputSchema()).isEqualTo(first.getOutputSchema());
            assertThat(next.getBudget()).isEqualTo(first.getBudget());
            assertThat(next.getEvidenceBundle().getId()).isNotEqualTo(originalBundle);
            assertThat(next.getEvidenceBundle().getVersion()).isEqualTo(2);
            assertThat(next.getEvidenceBundle().getItems()).anySatisfy(item -> {
                assertThat(item.getResourceType()).isEqualTo("character");
                assertThat(json.writeValueAsString(item.getContentJson())).contains("完整旧人物原文");
            });
            Map<String, Object> updates = Map.of("characters", List.of(Map.of("action", "update", "id", flow.characterIds().getFirst(), "background", "补齐后生成的新资料")));
            Map<String, Object> output = Map.of("summary", "依据完整旧来源更新", "updates", updates, "updatesSha256", ExecutionCanonicalJson.sha256(updates));
            ExecutionStepResult generated = outputResult(next, "占位").output(output);
            generated.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(generated)));
            flow.callbacks().result(generated);
            String artifact = database.dsl().fetchOne("SELECT id FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", first.getRunId()).get(0, String.class);
            ExecutionStepRequest reviewer = nextExpansionStep(flow);
            assertThat(reviewer.getPurpose()).isEqualTo("review");
            assertThat(reviewer.getEvidenceBundle().getId()).isEqualTo(next.getEvidenceBundle().getId());
            assertThat(reviewer.getInput().get("candidate")).isEqualTo(output);
            flow.callbacks().result(reviewResult(reviewer));
            var reviews = cn.inkforge.core.reviews.infrastructure.AgentUpdatesReviewTestSupport.repository(database, new CuidV1Generator(CLOCK), CLOCK, json, registry);
            var detail = reviews.getDetail(flow.fixture().userId(), artifact, 1, null).response();
            assertThat(json.writeValueAsString(detail.getDiff().orElse(null))).contains("完整旧人物原文", "补齐后生成的新资料");
            reviews.decide(flow.fixture().userId(), artifact, new cn.inkforge.contracts.api.ReviewArtifactDecisionRequest(
                    "approve-" + name + "-after-expansion", cn.inkforge.contracts.api.ReviewArtifactDecisionRequest.DecisionEnum.APPROVE, 1)
                    .engineVersion(cn.inkforge.contracts.api.ReviewArtifactDecisionRequest.EngineVersionEnum.NUMBER_2));
            assertThat(database.dsl().fetchOne("SELECT status::text FROM public.\"WorkflowRun\" WHERE id = ?", first.getRunId()).get(0, String.class)).isEqualTo("completed");
            assertThat(database.dsl().fetchOne("SELECT background FROM public.\"Character\" WHERE id = ?", flow.characterIds().getFirst()).get(0, String.class)).isEqualTo("补齐后生成的新资料");
            assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", first.getRunId())).isEqualTo(3);
        }
    }

    @Test
    void 证据补齐无进展或实际来源冲突明确终止且保留已付费用量和旧Bundle() {
        for (boolean changed : List.of(false, true)) {
            ExpansionFlow flow = expansionFlow("expand-conflict-" + changed, "revise_lore");
            flow.callbacks().result(expansionResult(flow.request(), flow.characterIds().getFirst()));
            ExecutionStepRequest second = nextExpansionStep(flow);
            String bundle = second.getEvidenceBundle().getId();
            String original = evidenceRows(bundle);
            if (changed) database.dsl().execute("UPDATE public.\"Character\" SET background = '作者在外部修改' WHERE id = ?", flow.characterIds().getFirst());
            ExecutionStepResult repeated = expansionResult(second, flow.characterIds().getFirst());
            assertThat(flow.callbacks().result(repeated).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
            assertThat(flow.callbacks().result(repeated).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
            Record run = database.dsl().fetchOne("SELECT status::text, \"errorCode\" FROM public.\"WorkflowRun\" WHERE id = ?", second.getRunId());
            assertThat(run.get("status", String.class)).isEqualTo("failed");
            assertThat(run.get("errorCode", String.class)).isEqualTo(changed ? "AGENT_UPDATES_SOURCE_CHANGED" : "AGENT_UPDATES_EVIDENCE_NO_PROGRESS");
            assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", second.getRunId())).isEqualTo(2);
            assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", second.getRunId())).isEqualTo(2);
            assertThat(evidenceRows(bundle)).isEqualTo(original);
        }
    }

    @Test
    void 证据扩展必须为后续生成复审保留预算且取消后不补齐() {
        ExpansionFlow budget = expansionFlow("expand-budget", "create_outline");
        ExecutionStepRequest step = budget.request();
        for (int index = 0; index < 3; index++) {
            var result = expansionResult(step, budget.characterIds().get(index));
            // 本例只验证剩余调用次数；提供已知成本，避免先触发未知成本按预留上限核算的独立门禁。
            result.getUsage().costMicros(1).usageStatus(StepUsage.UsageStatusEnum.COMPLETE);
            result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
            assertThat(budget.callbacks().result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
            if (index < 2) step = nextExpansionStep(budget);
        }
        assertThat(database.dsl().fetchOne("SELECT \"errorCode\" FROM public.\"WorkflowRun\" WHERE id = ?", step.getRunId()).get(0, String.class)).isEqualTo("WORKFLOW_RUN_BUDGET_EXCEEDED");
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", step.getRunId())).isEqualTo(3);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", step.getRunId())).isEqualTo(3);
        assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", step.getRunId())).isEqualTo(3);

        ExpansionFlow cancelled = expansionFlow("expand-cancel", "manage_foreshadowing");
        cancellations.request(cancelled.fixture().userId(), cancelled.request().getRunId(), "expand-cancel-request-0001");
        cancelled.callbacks().result(expansionResult(cancelled.request(), cancelled.characterIds().getFirst()));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", cancelled.request().getRunId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", cancelled.request().getRunId())).isEqualTo(1);
        assertThat(eventTypes(cancelled.request().getRunId())).endsWith("step_finished", "cancelled");
    }

    private static ExpansionFlow expansionFlow(String prefix, String name) {
        Fixture f = fixture(prefix);
        List<String> characters = List.of(prefix + "-person-1", prefix + "-person-2", prefix + "-person-3");
        for (String id : characters) database.dsl().execute("INSERT INTO public.\"Character\" (id,\"novelId\",name,background,\"updatedAt\") VALUES (?, ?, ?, '完整旧人物原文', ?)", id, f.novelId(), id, NOW);
        var enabled = ExecutionRegistryFixtures.structuredOperationEnabled(ExecutionRegistry.Environment.TEST, "long_serial." + name);
        var resolved = enabled.resolve("long_serial." + name, false);
        assertThat(registry.requireKnownOperation("long_serial." + name).v2Enabled()).isFalse();
        assertThat(resolved.outputSchema().key()).isEqualTo("output.agent_updates_step.v1");
        var reader = new cn.inkforge.core.reviews.infrastructure.JooqAgentUpdatesEvidenceReader(json);
        var sources = database.transactionResult(tx -> List.of(reader.captureIndex(tx, f.novelId())));
        Map<String, Object> input = Map.of("userInstruction", "根据完整来源修改资料，不裁剪原文");
        Map<String, Object> normalized = new LinkedHashMap<>(input);
        normalized.put("target", Map.of("type", "novel", "id", f.novelId()));
        normalized.put("scope", Map.of("kind", "novel"));
        var started = starts.start(new WorkflowStartPlan(f.userId(), prefix + "-request-0001", sha256(prefix),
                "long_serial", name, enabled.catalogVersion(), "chapter_generation", f.novelId(), f.chapterId(), f.sessionId(),
                "novel", f.novelId(), normalized, resolved.operation().evidencePolicy(), sources, resolved.operation().runBudget(),
                ExecutionPlanSnapshot.freeze(enabled.catalogVersion(), enabled.manifestFingerprint(), resolved),
                new WorkflowInitialStepPlan("generation", resolved.operation().lane(), input, resolved.generatorProfile(), resolved.generatorStepBudget(), resolved.outputSchema())));
        var handler = new JooqWorkflowCallbackRepository(database, new CuidV1Generator(CLOCK), CLOCK, json, registry, Duration.ofSeconds(30),
                new JooqWorkflowExecutionContextReader(json), () -> null,
                () -> cn.inkforge.core.reviews.infrastructure.AgentUpdatesReviewTestSupport.preparation(json));
        var request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(started.runId());
        accept(request);
        handler.progress(progress(request, unknownUsage()));
        return new ExpansionFlow(f, characters, request, handler);
    }

    private static ExecutionStepRequest nextExpansionStep(ExpansionFlow flow) {
        var request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(flow.request().getRunId());
        accept(request);
        assertThat(flow.callbacks().progress(progress(request, unknownUsage())).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        return request;
    }

    private static ExecutionStepResult expansionResult(ExecutionStepRequest request, String character) {
        var need = new cn.inkforge.contracts.api.EvidenceExpansionItem().resourceType("character").resourceId(character).purposeCode("target");
        var expansion = new cn.inkforge.contracts.api.EvidenceExpansionRequest().items(List.of(need))
                .sourceBundleId(request.getEvidenceBundle().getId()).sourceBundleVersion(request.getEvidenceBundle().getVersion())
                .reasonCode("agent_updates_sources_required").maxAdditionalBytes(request.getBudget().getMaxInputTokens() * 4).requestId("temporary");
        var items = WorkflowCallbackValues.evidenceExpansionMap(expansion).get("items");
        expansion.setRequestId("evidence-" + ExecutionCanonicalJson.sha256(Map.of("stepId", request.getStepId(), "requestHash", request.getRequestHash(), "items", items)).substring(0, 32));
        var result = new ExecutionStepResult(API_NOW, request.getFencingToken(), request.getInputHash(), request.getJobId(), request.getNovelId(),
                "2.0", request.getRequestHash(), apiResolved(request), "0".repeat(64), ExecutionStepResult.ResultKindEnum.EVIDENCE_EXPANSION,
                request.getRunId(), request.getStepId(), partialUsage(false)).evidenceExpansion(expansion);
        result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
    }

    private static String evidenceRows(String bundle) {
        return database.dsl().fetch("SELECT row_to_json(item)::text FROM public.\"WorkflowEvidenceItem\" item WHERE \"bundleId\" = ? ORDER BY ordinal", bundle).formatJSON();
    }

    private record ExpansionFlow(Fixture fixture, List<String> characterIds, ExecutionStepRequest request, JooqWorkflowCallbackRepository callbacks) {}

    @Test
    void 审阅完整报告有无会话均只完成一次且不写正式数据或草案() {
        for (boolean withSession : List.of(true, false)) {
            Flow flow = runningChapterReviewFlow("chapter-report-" + withSession, withSession);
            String before = database.dsl().fetchOne("SELECT row_to_json(chapter)::text FROM public.\"Chapter\" chapter WHERE id = ?",
                    "chapter-report-" + withSession + "-chapter").get(0, String.class);
            String report = "  完整报告😀\r\n".repeat(10_000) + "最后一段，绝不截断。\n";
            var result = reportResult(flow.request(), report);
            assertThat(callbacks.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
            assertThat(callbacks.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
            assertThat(json.readTree(database.dsl().fetchOne("SELECT output FROM public.\"WorkflowStep\" WHERE id = ?",
                    flow.request().getStepId()).get(0, String.class)).get("report").asText()).isEqualTo(report);
            assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE id = ? AND status = 'completed'", flow.runId())).isEqualTo(1);
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(1);
            assertThat(count("SELECT count(*) FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", flow.runId())).isZero();
            assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(1);
            assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ? AND content = ?",
                    flow.sessionId(), report)).isEqualTo(withSession ? 1 : 0);
            assertThat(database.dsl().fetchOne("SELECT row_to_json(chapter)::text FROM public.\"Chapter\" chapter WHERE id = ?",
                    "chapter-report-" + withSession + "-chapter").get(0, String.class)).isEqualTo(before);
            var event = json.readTree(database.dsl().fetchOne("SELECT \"payloadJson\" FROM public.\"WorkflowEvent\" WHERE \"runId\" = ? AND \"eventType\" = 'completed'", flow.runId()).get(0, String.class));
            assertThat(event.get("outcomeType").asText()).isEqualTo("chapter_review_report");
            if (!withSession) assertThat(event.get("resultId").asText()).isEqualTo(flow.request().getStepId());
        }
    }

    @Test
    void 审阅拒绝空白报告且取消后的迟到报告只结算不发布() {
        Flow invalid = runningChapterReviewFlow("chapter-report-empty", false);
        assertThatThrownBy(() -> callbacks.result(reportResult(invalid.request(), " \n\t"))).isInstanceOf(ApiException.class);
        assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", invalid.runId())).isZero();
        callbacks.failure(preProviderFailure(invalid.request()));
        Flow cancelled = runningChapterReviewFlow("chapter-report-cancel", true);
        cancellations.request(cancelled.userId(), cancelled.runId(), "chapter-report-cancel-request");
        callbacks.result(reportResult(cancelled.request(), "迟到的完整审阅报告"));
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?", cancelled.sessionId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", cancelled.runId())).isEqualTo(1);
        assertThat(eventTypes(cancelled.runId())).endsWith("step_finished", "cancelled");
    }

    @Test
    void 场景改写完整生成及自动Patch始终保留真实Operation并再次双审() {
        Flow flow = runningChapterFlow("scene-patch", "rewrite_scene");
        callbacks.result(chapterResult(flow.request(), "开场\n甲😀乙\n结尾完整保留"));
        for (var reviewer : List.of(startNextPlanStep(flow), startNextPlanStep(flow))) {
            assertThat(reviewer.getOperation()).isEqualTo("rewrite_scene");
            assertThat((Map<String, Object>) reviewer.getInput().get("task")).containsEntry("operation", "rewrite_scene");
            callbacks.result(chapterReviewResult(reviewer, "patch", "😀", "场景完整新细节"));
        }
        var stored = json.readTree(database.dsl().fetchOne("SELECT \"payloadJson\" FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", flow.runId()).get(0, String.class));
        assertThat(stored.get("operation").asText()).isEqualTo("rewrite_scene");
        assertThat(stored.get("content").asText()).isEqualTo("开场\n甲场景完整新细节乙\n结尾完整保留");
        for (var reviewer : List.of(startNextPlanStep(flow), startNextPlanStep(flow))) {
            assertThat(reviewer.getOperation()).isEqualTo("rewrite_scene");
            assertThat(reviewer.getArtifactRevision()).isEqualTo(2);
            callbacks.result(reviewResult(reviewer));
        }
        assertThat(count("SELECT count(*) FROM public.\"WorkflowBillingReservation\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(5);
        assertThat(database.dsl().fetchOne("SELECT content FROM public.\"Chapter\" WHERE id = ?", "scene-patch-chapter").get(0, String.class)).isEqualTo("甲😀乙");
    }

    private static Flow runningChapterReviewFlow(String prefix, boolean withSession) {
        Fixture fixture = fixture(prefix);
        var op = registry.resolve("long_serial.review_chapter", false);
        Map<String, Object> input = Map.of("userInstruction", "完整审阅当前章节，不修改正文");
        var started = starts.start(new WorkflowStartPlan(fixture.userId(), prefix + "-request", sha256(prefix), "long_serial", "review_chapter", "1", "chat",
                fixture.novelId(), fixture.chapterId(), withSession ? fixture.sessionId() : null, "chapter", fixture.chapterId(), input, op.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan("chapter_writing_context", fixture.chapterId(), true, null, API_NOW, null,
                        Map.of("schemaVersion", 1, "novelId", fixture.novelId(), "currentChapter", Map.of("id", fixture.chapterId(), "content", "甲😀乙")), null, null, Map.of())),
                op.operation().runBudget(), ExecutionPlanSnapshot.freeze(registry.catalogVersion(), registry.manifestFingerprint(), op),
                new WorkflowInitialStepPlan("generation", op.operation().lane(), input, op.generatorProfile(), op.generatorStepBudget(), op.outputSchema())));
        var request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(started.runId());
        accept(request);
        callbacks.progress(progress(request, unknownUsage()));
        return new Flow(started.runId(), fixture.userId(), fixture.sessionId(), request);
    }

    @Test
    void 两种大纲选区同来源最多返工一次且每轮仅一个编辑复审() {
        for (String resourceType : List.of("outline_content", "outline_node_content")) {
            String prefix = "outline-callback-" + resourceType;
            Fixture fixture = fixture(prefix);
            var op = registry.resolve("long_serial.rewrite_outline_selection", false);
            String resourceId = prefix + "-source";
            Map<String, Object> selection = Map.of("resourceType", resourceType, "resourceId", resourceId,
                    "baseUpdatedAt", API_NOW.toString(), "baseContentHash", sha256("前😀后\r\n"),
                    "selectionStart", 1, "selectionEnd", 2, "selectedTextHash", sha256("😀"));
            Map<String, Object> input = Map.of("userInstruction", "补全这一段动机", "selectionTarget", selection);
            var started = starts.start(new WorkflowStartPlan(fixture.userId(), prefix + "-request", sha256(prefix), "long_serial", "rewrite_outline_selection", "1", "chapter_generation",
                    fixture.novelId(), fixture.chapterId(), fixture.sessionId(), resourceType, resourceId, input, op.operation().evidencePolicy(),
                    List.of(new WorkflowEvidenceItemPlan(resourceType, resourceId, true, null, API_NOW, "前😀后\r\n", null, 1, 2,
                            Map.of("role", "selection_source", "baseContentHash", sha256("前😀后\r\n"), "selectedTextHash", sha256("😀")))),
                    op.operation().runBudget(), ExecutionPlanSnapshot.freeze(registry.catalogVersion(), registry.manifestFingerprint(), op),
                    new WorkflowInitialStepPlan("generation", op.operation().lane(), input, op.generatorProfile(), op.generatorStepBudget(), op.outputSchema())));
            var generation = dispatches.claimNext().orElseThrow();
            assertThat(generation.getRunId()).isEqualTo(started.runId());
            accept(generation);
            callbacks.progress(progress(generation, unknownUsage()));
            var result = outputResult(generation, "完整改写动机😀\n尾部");
            callbacks.result(result);
            assertThat(callbacks.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
            var flow = new Flow(started.runId(), fixture.userId(), fixture.sessionId(), generation);
            var reviewer = startNextPlanStep(flow);
            assertThat(reviewer.getModelProfile().getProfile()).isEqualTo("reviewer.outline_selection_editorial.v1");
            assertThat(reviewer.getEvidenceBundle()).usingRecursiveComparison().ignoringFields("policyVersion")
                    .isEqualTo(generation.getEvidenceBundle());
            assertThat((Map<String, Object>) reviewer.getInput().get("task")).containsEntry("operation", "rewrite_outline_selection")
                    .containsEntry("selectionTarget", selection);
            callbacks.result(planReviewResult(reviewer, "outline_selection.local", 0.95));
            var revised = startNextPlanStep(flow);
            assertThat(revised.getPurpose()).isEqualTo("generation");
            assertThat(revised.getInput()).containsOnlyKeys("userInstruction", "selectionTarget", "originalUserInstruction", "previousCandidate");
            assertThat(revised.getInput()).containsEntry("originalUserInstruction", "补全这一段动机").containsEntry("selectionTarget", selection);
            assertThat((Map<String, Object>) revised.getInput().get("previousCandidate"))
                    .containsEntry("replacement", "完整改写动机😀\n尾部").containsEntry("artifactRevision", 1);
            callbacks.result(outputResult(revised, "完整改写动机😀\n尾部"));
            var secondReview = startNextPlanStep(flow);
            assertThat(secondReview.getModelProfile().getProfile()).isEqualTo("reviewer.outline_selection_editorial.v1");
            assertThat(secondReview.getArtifactRevision()).isEqualTo(2);
            assertThat(secondReview.getEvidenceBundle()).usingRecursiveComparison().ignoringFields("policyVersion")
                    .isEqualTo(generation.getEvidenceBundle());
            callbacks.result(planReviewResult(secondReview, "outline_selection.local", 0.95));
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'review'", flow.runId())).isEqualTo(2);
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'", flow.runId())).isEqualTo(2);
            assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE id = ? AND status = 'waiting_user'", flow.runId())).isEqualTo(1);
            var payload = json.readTree(database.dsl().fetchOne("SELECT \"payloadJson\" FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", flow.runId()).get(0, String.class));
            assertThat(payload.get("schema").asText()).isEqualTo("durable.outline-selection-artifact.v1");
            assertThat(payload.get("kind").asText()).isEqualTo("outline_draft");
            assertThat(payload.get("operation").asText()).isEqualTo("rewrite_outline_selection");
            assertThat(payload.get("resourceType").asText()).isEqualTo(resourceType);
            assertThat(payload.get("resourceId").asText()).isEqualTo(resourceId);
            assertThat(payload.get("replacement").asText()).isEqualTo("完整改写动机😀\n尾部");
            assertThat(payload.get("candidateSha256").asText()).isEqualTo(sha256("前完整改写动机😀\n尾部后\r\n"));
            assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(4);
            assertThat(database.dsl().fetchOne("SELECT content FROM public.\"Chapter\" WHERE id = ?", fixture.chapterId()).get(0, String.class)).isEqualTo("甲😀乙");
        }
    }

    private static ExecutionStepResult reportResult(ExecutionStepRequest request, String report) {
        var result = answerResult(request, "占位");
        result.setOutput(JsonNullable.of(Map.of("report", report)));
        result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
    }

    @Test
    void 自然业务准备被确定性拒绝时保留解析费用并以原业务错误结束() {
        Flow flow = runningIntentFlow("intent-preparation-rejected");
        var repository = new JooqWorkflowCallbackRepository(database, new CuidV1Generator(CLOCK), CLOCK, json,
                registry, Duration.ofSeconds(30), new JooqWorkflowExecutionContextReader(json),
                () -> (userId, novelId, chapterId, sessionId, instruction, words, plan) -> {
                    throw new ApiException(409, "CHAPTER_GROUP_MAPPING_CONFLICT", "章节结构需要先由作者修正");
                });
        var result = intentResult(flow.request(), new cn.inkforge.contracts.api.ProposedCommand(new java.math.BigDecimal("0.99"))
                .workflow("long_serial").operation("answer_question"));
        assertThat(repository.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(repository.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        assertThat(database.dsl().fetchOne("SELECT status::text AS status, \"errorCode\" FROM public.\"WorkflowRun\" WHERE id = ?", flow.runId())
                .intoMap()).containsEntry("status", "failed").containsEntry("errorCode", "CHAPTER_GROUP_MAPPING_CONFLICT");
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND status = 'completed'", flow.runId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowBillingReservation\" WHERE \"runId\" = ? AND status = 'settled'", flow.runId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(1);
        assertThat(eventTypes(flow.runId())).endsWith("step_finished", "failed");
    }

    @Test
    void 自然业务准备的临时或未知异常不伪装成业务终态() {
        List<RuntimeException> failures = List.of(new ApiException(503, "TEMPORARY_FAILURE", "暂时不可用"),
                new ApiException(429, "RATE_LIMITED", "稍后重试"), new IllegalStateException("准备程序异常"));
        for (int index = 0; index < failures.size(); index++) {
            var failure = failures.get(index);
            Flow flow = runningIntentFlow("intent-preparation-retry-" + index);
            var repository = new JooqWorkflowCallbackRepository(database, new CuidV1Generator(CLOCK), CLOCK, json,
                    registry, Duration.ofSeconds(30), new JooqWorkflowExecutionContextReader(json),
                    () -> (userId, novelId, chapterId, sessionId, instruction, words, plan) -> { throw failure; });
            var result = intentResult(flow.request(), new cn.inkforge.contracts.api.ProposedCommand(new java.math.BigDecimal("0.99"))
                    .workflow("long_serial").operation("answer_question"));
            assertThatThrownBy(() -> repository.result(result)).isSameAs(failure);
            assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE id = ? AND status = 'running'", flow.runId())).isEqualTo(1);
            assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", flow.runId())).isZero();
            cancellations.request(flow.userId(), flow.runId(), "intent-preparation-retry-cancel-" + index);
            assertThat(repository.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        }
    }

    @Test
    void 自然意图成功后同Run冻结业务来源且完整问答仅结算一次() {
        Flow flow = runningIntentFlow("intent-answer");
        var repository = intentCallbacks();
        var result = intentResult(flow.request(), new cn.inkforge.contracts.api.ProposedCommand(new java.math.BigDecimal("0.95"))
                .workflow("long_serial").operation("answer_question"));
        assertThat(repository.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(repository.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE id = ? AND operation IS NULL", flow.runId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'intent_selection'", flow.runId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(2);
        var generation = dispatches.claimNext().orElseThrow();
        assertThat(generation.getRunId()).isEqualTo(flow.runId());
        assertThat(generation.getOperation()).isEqualTo("answer_question");
        assertThat(generation.getInput()).containsEntry("userInstruction", "  分析这一章的视角\n");
        accept(generation);
        repository.progress(progress(generation, unknownUsage()));
        repository.result(answerResult(generation, "  完整的问答结果\n"));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE id = ? AND status = 'completed'", flow.runId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(2);
        assertThat(eventTypes(flow.runId())).containsSubsequence("step_finished", "intent_resolved", "evidence_ready", "step_queued", "completed");
    }

    @Test
    void 自然意图澄清保存完整问题并等待作者而不是生成候选() {
        Flow flow = runningIntentFlow("intent-question");
        var command = new cn.inkforge.contracts.api.ProposedCommand(new java.math.BigDecimal("0.5"))
                .clarification(new cn.inkforge.contracts.api.CommandClarification("need_intent", "  你想分析还是修改？\n"));
        var result = intentResult(flow.request(), command);
        assertThat(intentCallbacks().result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(intentCallbacks().result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        var clarification = new JooqWorkflowExecutionContextReader(json).pendingClarification(database.dsl(), flow.runId(), "waiting_user");
        assertThat(clarification.getPrompt()).isEqualTo("  你想分析还是修改？\n");
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND status IN ('pending','running')", flow.runId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", flow.runId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ? AND content = ?", flow.sessionId(), clarification.getPrompt())).isEqualTo(1);
        assertThat(eventTypes(flow.runId())).endsWith("step_finished", "clarification_required");
    }

    @Test
    void 自然意图非法目标零续接且确定性失败与取消不会创建业务Step() {
        Flow flow = runningIntentFlow("intent-invalid");
        var result = intentResult(flow.request(), new cn.inkforge.contracts.api.ProposedCommand(new java.math.BigDecimal("0.99"))
                .workflow("long_serial").operation("answer_question").targetType("chapter").targetId("other-chapter"));
        assertThatThrownBy(() -> intentCallbacks().result(result)).isInstanceOf(ApiException.class);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(1);
        assertThat(intentCallbacks().failure(preProviderFailure(flow.request())).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(eventTypes(flow.runId())).endsWith("step_finished", "failed");
        Flow cancelled = runningIntentFlow("intent-cancelled");
        cancellations.request(cancelled.userId(), cancelled.runId(), "intent-cancel-request-0001");
        var late = intentResult(cancelled.request(), new cn.inkforge.contracts.api.ProposedCommand(new java.math.BigDecimal("0.99"))
                .workflow("long_serial").operation("answer_question"));
        assertThat(intentCallbacks().result(late).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", cancelled.runId())).isEqualTo(1);
        assertThat(eventTypes(cancelled.runId())).endsWith("step_finished", "cancelled");
    }

    private static JooqWorkflowCallbackRepository intentCallbacks() {
        CuidV1Generator ids = new CuidV1Generator(CLOCK);
        return new JooqWorkflowCallbackRepository(database, ids, CLOCK, json, registry, Duration.ofSeconds(30),
                new JooqWorkflowExecutionContextReader(json), () -> (userId, novelId, chapterId, sessionId, instruction, words, plan) -> {
                    // 此处只提供派发/回调的业务准备夹具；真实写作端口由跨模块集成另验。
                    var chapter = database.dsl().fetchOne("SELECT content FROM public.\"Chapter\" WHERE id = ? AND \"novelId\" = ?", chapterId, novelId);
                    return new cn.inkforge.core.workflows.application.WorkflowIntentBusinessPreparation.Prepared(
                            Map.of("userInstruction", instruction), List.of(new WorkflowEvidenceItemPlan("chapter_content", chapterId,
                                    true, null, API_NOW, chapter.get("content", String.class), null, null, null, Map.of())), plan.generator());
                });
    }

    private static Flow runningIntentFlow(String prefix) {
        Fixture fixture = fixture(prefix);
        var intent = cn.inkforge.core.workflows.catalog.IntentExecutionPlanSnapshot.freeze(registry, List.of("long_serial.answer_question"));
        var system = registry.resolveSystemPurpose("resolve_intent");
        Map<String, Object> input = Map.of("userInstruction", "  分析这一章的视角\n", "clarifications", List.of());
        var initial = new WorkflowInitialStepPlan("resolve_intent", system.purpose().lane(), input,
                system.modelProfile(), system.stepBudget(), system.outputSchema());
        var started = starts.start(new WorkflowStartPlan(fixture.userId(), prefix + "-request-0001", sha256(prefix),
                "long_serial", null, registry.catalogVersion(), "chat", fixture.novelId(), fixture.chapterId(), fixture.sessionId(),
                "chapter", fixture.chapterId(), Map.of("inputMode", "natural", "userInstruction", input.get("userInstruction"), "targetWordCount", 4000),
                system.purpose().evidencePolicy(), List.of(new WorkflowEvidenceItemPlan("intent_context", fixture.chapterId(), true, null, API_NOW,
                        null, Map.of("workflow", "long_serial", "novelId", fixture.novelId(), "chapterId", fixture.chapterId(), "chapterTitle", "第一章",
                                "availableOperations", List.of(Map.of("operation", "answer_question", "description", "回答当前章节的问题", "targetType", "chapter", "scopeKind", "chapter"))),
                        null, null, Map.of())), intent.runBudget(), null, initial, intent));
        var request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(started.runId());
        assertThat(request.getOperation()).isNull();
        accept(request);
        assertThat(intentCallbacks().progress(progress(request, unknownUsage())).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        return new Flow(started.runId(), fixture.userId(), fixture.sessionId(), request);
    }

    private static ExecutionStepResult intentResult(ExecutionStepRequest request, cn.inkforge.contracts.api.ProposedCommand command) {
        var result = answerResult(request, "不会使用的输出");
        result.setOutput(JsonNullable.undefined());
        result.setResultKind(ExecutionStepResult.ResultKindEnum.PROPOSED_COMMAND);
        result.setProposedCommand(command);
        result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
    }

    @Test
    void 正文双复审一致局部Patch仅创建一个零模型Step并再次复审() {
        Flow flow = runningChapterFlow("chapter-patch");
        ExecutionStepResult generated = chapterResult(flow.request(), "甲😀乙丙丁");
        callbacks.result(generated);
        assertThat(callbacks.result(generated).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        List<ExecutionStepRequest> reviewers = List.of(startNextPlanStep(flow), startNextPlanStep(flow));
        assertThat(reviewers).extracting(request -> request.getModelProfile().getProfile())
                .containsExactlyInAnyOrder("reviewer.chapter_draft_consistency.v1", "reviewer.chapter_draft_editorial.v1");
        for (var reviewer : reviewers) {
            assertThat(reviewer.getInput().get("candidate")).isEqualTo(WorkflowCallbackValues.optional(generated.getOutput()));
            ExecutionStepResult result = chapterReviewResult(reviewer, "patch", "😀乙", "完整新段");
            callbacks.result(result);
            assertThat(callbacks.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        }
        Record control = database.dsl().fetchOne("SELECT \"stepType\"::text, lane, \"modelProfile\", \"usageJson\", \"artifactRevision\" FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'candidate_patch'", flow.runId());
        assertThat(control.get("stepType", String.class)).isEqualTo("persistence");
        assertThat(control.get("lane", String.class)).isEqualTo("control");
        assertThat(control.get("modelProfile")).isNull();
        assertThat(control.get("usageJson")).isNull();
        assertThat(control.get("artifactRevision", Integer.class)).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'", flow.runId())).isEqualTo(1);
        for (var reviewer : List.of(startNextPlanStep(flow), startNextPlanStep(flow))) {
            assertThat(reviewer.getArtifactRevision()).isEqualTo(2);
            assertThat((Map<String, Object>) reviewer.getInput().get("candidate")).containsEntry("content", "甲完整新段丙丁");
            callbacks.result(chapterReviewResult(reviewer, "patch", "丙", "第二次不得自动应用"));
        }
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'candidate_patch'", flow.runId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowBillingReservation\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(5);
        assertThat(database.dsl().fetchOne("SELECT status::text FROM public.\"WorkflowRun\" WHERE id = ?", flow.runId()).get(0, String.class)).isEqualTo("waiting_user");
        assertThat(database.dsl().fetchOne("SELECT content FROM public.\"Chapter\" WHERE \"novelId\" = ?", flow.request().getNovelId()).get(0, String.class)).isEqualTo("甲😀乙");
    }

    @Test
    void 正文无Patch的局部一致意见仅完整返工一次并保留输入AB() {
        Flow flow = runningChapterFlow("chapter-rewrite");
        callbacks.result(chapterResult(flow.request(), "首轮完整正文😀"));
        for (var reviewer : List.of(startNextPlanStep(flow), startNextPlanStep(flow))) callbacks.result(chapterReviewResult(reviewer, "rewrite", "", ""));
        var revision = startNextPlanStep(flow);
        assertThat(revision.getPurpose()).isEqualTo("generation");
        assertThat(revision.getInput()).containsOnlyKeys("userInstruction", "targetWordCount", "originalUserInstruction", "previousArtifact");
        assertThat(revision.getInput()).containsEntry("originalUserInstruction", "完成当前章节正文");
        callbacks.result(chapterResult(revision, "完整返工正文😀"));
        for (var reviewer : List.of(startNextPlanStep(flow), startNextPlanStep(flow))) {
            assertThat((Map<String, Object>) reviewer.getInput().get("task")).containsEntry("userInstruction", revision.getInput().get("userInstruction"))
                    .containsEntry("originalUserInstruction", "完成当前章节正文");
            callbacks.result(chapterReviewResult(reviewer, "rewrite", "", ""));
        }
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'", flow.runId())).isEqualTo(2);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowBillingReservation\" WHERE \"runId\" = ?", flow.runId())).isEqualTo(6);
    }

    @Test
    void 正文Patch混合分歧重叠多命中和结构问题都保留原候选() {
        for (String mode : List.of("mixed", "disagree", "conflict", "missing", "ambiguous", "structural", "uncertain", "unavailable")) {
            Flow flow = runningChapterFlow("chapter-reject-" + mode);
            callbacks.result(chapterResult(flow.request(), "甲乙甲"));
            var reviewers = List.of(startNextPlanStep(flow), startNextPlanStep(flow));
            for (int index = 0; index < reviewers.size(); index++) {
                var reviewer = reviewers.get(index);
                if ("unavailable".equals(mode) && index == 1) callbacks.failure(reviewFailure(reviewer));
                else if ("disagree".equals(mode) && index == 1) callbacks.result(reviewResult(reviewer));
                else callbacks.result(chapterReviewResult(reviewer,
                        "mixed".equals(mode) && index == 1 ? "rewrite" : mode,
                        "ambiguous".equals(mode) ? "甲" : "missing".equals(mode) ? "不存在" : "乙",
                        "conflict".equals(mode) && index == 1 ? "不同结果" : "统一结果"));
            }
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'candidate_patch'", flow.runId())).isZero();
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'", flow.runId())).isEqualTo(1);
            assertThat(database.dsl().fetchOne("SELECT revision FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", flow.runId()).get(0, Integer.class)).isEqualTo(1);
        }
    }

    private static Flow runningChapterFlow(String prefix) {
        return runningChapterFlow(prefix, "write_chapter");
    }

    private static Flow runningChapterFlow(String prefix, String operationKey) {
        Fixture fixture = fixture(prefix);
        var op = registry.resolve("long_serial." + operationKey, false);
        Map<String, Object> input = Map.of("userInstruction", "完成当前章节正文", "targetWordCount", 2500);
        Map<String, Object> normalized = new LinkedHashMap<>(input);
        normalized.putAll(Map.of("workflow", "long_serial", "operation", operationKey, "novelId", fixture.novelId(), "chapterId", fixture.chapterId()));
        var started = starts.start(new WorkflowStartPlan(fixture.userId(), prefix + "-request", sha256(prefix), "long_serial", operationKey, "1", "chapter_generation",
                fixture.novelId(), fixture.chapterId(), fixture.sessionId(), "chapter", fixture.chapterId(), normalized, op.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan("chapter_writing_context", fixture.chapterId(), true, null, API_NOW, null,
                        Map.of("schemaVersion", 1, "novelId", fixture.novelId(), "currentChapter", Map.of("id", fixture.chapterId(), "content", "甲😀乙")), null, null, Map.of("role", "chapter_writing_context"))),
                op.operation().runBudget(), ExecutionPlanSnapshot.freeze(registry.catalogVersion(), registry.manifestFingerprint(), op),
                new WorkflowInitialStepPlan("generation", op.operation().lane(), input, op.generatorProfile(), op.generatorStepBudget(), op.outputSchema())));
        var request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(started.runId());
        accept(request);
        callbacks.progress(progress(request, unknownUsage()));
        return new Flow(started.runId(), fixture.userId(), fixture.sessionId(), request);
    }

    private static ExecutionStepResult chapterResult(ExecutionStepRequest request, String content) {
        var result = outputResult(request, "占位");
        result.setOutput(org.openapitools.jackson.nullable.JsonNullable.of(
                cn.inkforge.core.workflows.domain.DurableChapterDraftArtifact.deriveOutput("完整正文摘要", content)));
        result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
    }

    private static ExecutionStepResult chapterReviewResult(ExecutionStepRequest request, String mode, String find, String replace) {
        var result = reviewResult(request);
        var item = request.getEvidenceBundle().getItems().getFirst();
        Map<String, Object> finding = new LinkedHashMap<>(Map.of("dimension", "structural".equals(mode) ? "chapter_draft.structural" : "chapter_draft.local",
                "severity", "warning", "confidence", "uncertain".equals(mode) ? 0.5 : 0.95,
                "claim", "需要改善这处细节", "suggestion", "这是说明，不得解析为替换文本",
                "evidence", List.of(Map.of("evidenceItemId", item.getId(), "contentSha256", item.getContentSha256()))));
        if (!"rewrite".equals(mode)) finding.put("candidatePatch", Map.of("kind", "text_replace", "find", find, "replace", replace));
        result.getEvaluation().setContentVerdict(EvidenceEvaluation.ContentVerdictEnum.ISSUES_FOUND);
        result.getEvaluation().setFindings(List.of(json.convertValue(finding, cn.inkforge.contracts.api.EvaluationFinding.class)));
        result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
    }

    @Test
    void 章节计划局部问题仅自动返工一次且同Evidence与不可变Revision贯穿完整链() {
        Flow flow = runningPlanFlow("plan-auto");
        ExecutionStepResult first = planResult(flow.request(), "首轮😀计划");
        assertThat(callbacks.result(first).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.result(first).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        Record artifact = database.dsl().fetchOne("SELECT id, kind::text AS kind, \"payloadJson\", \"diffJson\" FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", flow.runId());
        assertThat(artifact.get("kind", String.class)).isEqualTo("beat_plan");
        assertThat(json.readTree(artifact.get("diffJson", String.class)).has("after")).isFalse();
        assertThat(json.readTree(database.dsl().fetchOne("SELECT output FROM public.\"WorkflowStep\" WHERE id = ?", flow.request().getStepId()).get("output", String.class)).has("sceneBeats")).isFalse();
        ExecutionStepRequest review = startNextPlanStep(flow);
        assertThat(review.getInput().get("candidate")).isEqualTo(WorkflowCallbackValues.optional(first.getOutput()));
        ExecutionStepResult issues = planReviewResult(review, "chapter_plan.local", 0.95);
        callbacks.result(issues);
        assertThat(callbacks.result(issues).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        ExecutionStepRequest revision = startNextPlanStep(flow);
        assertThat(revision.getPurpose()).isEqualTo("generation");
        assertThat(revision.getArtifactRevision()).isEqualTo(1);
        assertThat(revision.getInput()).containsEntry("targetWordCount", 2500).containsEntry("originalUserInstruction", "规划完整章节");
        assertThat(revision.getInput()).containsOnlyKeys("userInstruction", "targetWordCount", "originalUserInstruction", "previousArtifact");
        assertThat(revision.getInput().get("previousArtifact")).isEqualTo(Map.of("artifactId", artifact.get("id", String.class),
                "artifactRevision", 1, "payload", WorkflowCallbackValues.optional(first.getOutput())));
        ExecutionStepResult second = planResult(revision, "第二轮完整计划");
        callbacks.result(second);
        assertThat(callbacks.result(second).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        ExecutionStepRequest secondReview = startNextPlanStep(flow);
        assertThat(secondReview.getArtifactRevision()).isEqualTo(2);
        assertThat((Map<String, Object>) secondReview.getInput().get("task"))
                .containsEntry("userInstruction", revision.getInput().get("userInstruction"))
                .containsEntry("originalUserInstruction", "规划完整章节");
        callbacks.result(planReviewResult(secondReview, "chapter_plan.local", 0.99));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'", flow.runId())).isEqualTo(2);
        assertThat(count("SELECT count(*) FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?", artifact.get("id", String.class))).isEqualTo(2);
        assertThat(database.dsl().fetchOne("SELECT status::text FROM public.\"WorkflowRun\" WHERE id = ?", flow.runId()).get(0, String.class)).isEqualTo("waiting_user");
        assertThat(count("SELECT count(*) FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" IN (SELECT id FROM public.\"Chapter\" WHERE \"novelId\" = ?)", flow.request().getNovelId())).isZero();
    }

    @Test
    void 章节计划作者返工后的编辑Reviewer同时收到原指令与本次要求() {
        Flow flow = runningPlanFlow("plan-author-revise");
        ExecutionStepResult initial = planResult(flow.request(), "首轮完整计划");
        callbacks.result(initial);
        ExecutionStepRequest firstReview = startNextPlanStep(flow);
        callbacks.result(reviewResult(firstReview));
        String artifactId = firstReview.getArtifactId();
        // 决定存储测试已验证相同输入由真实 revise 单事务写入；此处从其持久 Step 边界验证 callback。
        Map<String, Object> revisedInput = new LinkedHashMap<>(flow.request().getInput());
        revisedInput.put("originalUserInstruction", "规划完整章节");
        revisedInput.put("userInstruction", "让人物以更主动的选择解决问题");
        revisedInput.put("previousArtifact", Map.of("artifactId", artifactId, "artifactRevision", 1,
                "payload", WorkflowCallbackValues.optional(initial.getOutput())));
        enqueueRevisionGeneration(flow.runId(), flow.request().getStepId(), artifactId, 1, revisedInput);
        ExecutionStepRequest revision = startNextPlanStep(flow);
        callbacks.result(planResult(revision, "作者要求后的完整计划"));
        ExecutionStepRequest secondReview = startNextPlanStep(flow);
        assertThat((Map<String, Object>) secondReview.getInput().get("task"))
                .containsEntry("userInstruction", "让人物以更主动的选择解决问题")
                .containsEntry("originalUserInstruction", "规划完整章节");
        assertThat(secondReview.getArtifactRevision()).isEqualTo(2);
        callbacks.result(reviewResult(secondReview));
    }

    @Test
    void 章节计划结构问题低置信与不可用均直接交作者且畸形候选零写入() {
        for (String mode : List.of("structural", "uncertain", "unavailable")) {
            Flow flow = runningPlanFlow("plan-" + mode);
            ExecutionStepResult malformed = planResult(flow.request(), "计划");
            Map<String, Object> bad = new LinkedHashMap<>(WorkflowCallbackValues.optional(malformed.getOutput()));
            bad.put("beatCount", 4);
            malformed.setOutput(org.openapitools.jackson.nullable.JsonNullable.of(bad));
            malformed.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(malformed)));
            assertThatThrownBy(() -> callbacks.result(malformed)).isInstanceOf(ApiException.class);
            assertThat(count("SELECT count(*) FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?", flow.runId())).isZero();
            callbacks.result(planResult(flow.request(), "完整计划"));
            ExecutionStepRequest review = startNextPlanStep(flow);
            if ("unavailable".equals(mode)) callbacks.failure(reviewFailure(review));
            else callbacks.result(planReviewResult(review, "structural".equals(mode) ? "chapter_plan.structural" : "chapter_plan.local", "uncertain".equals(mode) ? 0.5 : 0.95));
            assertThat(database.dsl().fetchOne("SELECT status::text FROM public.\"WorkflowRun\" WHERE id = ?", flow.runId()).get(0, String.class)).isEqualTo("waiting_user");
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'", flow.runId())).isEqualTo(1);
        }
    }

    private static Flow runningPlanFlow(String prefix) {
        Fixture fixture = fixture(prefix);
        var op = registry.resolve("long_serial.plan_chapter", false);
        Map<String, Object> input = Map.of("userInstruction", "规划完整章节", "targetWordCount", 2500);
        Map<String, Object> normalizedBody = new LinkedHashMap<>(input);
        normalizedBody.putAll(Map.of("workflow", "long_serial", "operation", "plan_chapter", "novelId", fixture.novelId(),
                "chapterId", fixture.chapterId(), "target", Map.of("kind", "chapter"), "scope", Map.of("kind", "chapter")));
        var started = starts.start(new WorkflowStartPlan(fixture.userId(), prefix + "-request", sha256(prefix),
                "long_serial", "plan_chapter", "1", "chapter_generation", fixture.novelId(), fixture.chapterId(),
                fixture.sessionId(), "chapter", fixture.chapterId(), normalizedBody, op.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan("chapter_plan_context", fixture.chapterId(), true, null, API_NOW,
                        null, Map.of("chapter", Map.of("id", fixture.chapterId(), "content", "甲😀乙")), null, null, Map.of("role", "chapter_plan_context"))),
                op.operation().runBudget(), ExecutionPlanSnapshot.freeze(registry.catalogVersion(), registry.manifestFingerprint(), op),
                new WorkflowInitialStepPlan("generation", op.operation().lane(), input, op.generatorProfile(), op.generatorStepBudget(), op.outputSchema())));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(started.runId());
        accept(request);
        callbacks.progress(progress(request, unknownUsage()));
        return new Flow(started.runId(), fixture.userId(), fixture.sessionId(), request);
    }

    private static ExecutionStepRequest startNextPlanStep(Flow flow) {
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(flow.runId());
        assertThat(request.getEvidenceBundle().getId()).isEqualTo(flow.request().getEvidenceBundle().getId());
        accept(request);
        callbacks.progress(progress(request, unknownUsage()));
        return request;
    }

    private static ExecutionStepResult planResult(ExecutionStepRequest request, String title) {
        Map<String, Object> output = new LinkedHashMap<>(Map.of("title", title, "summary", "完整语义摘要", "chapterGoal", "推进主线",
                "sceneBeats", List.of(Map.of("order", 1, "goal", "角色抉择😀", "estimatedWords", 2500)), "beatCount", 1));
        output.put("contentSha256", ExecutionCanonicalJson.sha256(output));
        ExecutionStepResult result = outputResult(request, "占位");
        result.setOutput(org.openapitools.jackson.nullable.JsonNullable.of(output));
        result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
    }

    private static ExecutionStepResult planReviewResult(ExecutionStepRequest request, String dimension, double confidence) {
        ExecutionStepResult result = reviewResult(request);
        EvidenceEvaluation evaluation = result.getEvaluation();
        var item = request.getEvidenceBundle().getItems().getFirst();
        evaluation.setContentVerdict(EvidenceEvaluation.ContentVerdictEnum.ISSUES_FOUND);
        evaluation.setFindings(List.of(json.convertValue(Map.of("dimension", dimension,
                "severity", "warning", "confidence", confidence, "claim", "角色目标需要明确", "suggestion", "明确场景中的角色目标",
                "evidence", List.of(Map.of("evidenceItemId", item.getId(), "contentSha256", item.getContentSha256()))), cn.inkforge.contracts.api.EvaluationFinding.class)));
        result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
        return result;
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
    void 问答成功原子保存完整Agent消息并按序完成Step和Run且重放不重复() {
        Flow flow = runningAnswerFlow("callback-answer-happy");
        String answer = "  第一段完整回答。\n第二段也必须原样保留。  ";
        ExecutionStepResult result = answerResult(flow.request(), answer);

        assertThat(callbacks.result(result).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.result(result).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);

        Record message = database.dsl().fetchOne(
                """
                SELECT id, "sessionId", role, "agentId", content, metadata, "createdAt"
                FROM public."WritingMessage"
                WHERE "sessionId" = ? AND role = 'agent'
                """,
                flow.sessionId());
        assertThat(message).isNotNull();
        assertThat(message.get("sessionId", String.class)).isEqualTo(flow.sessionId());
        assertThat(message.get("role", String.class)).isEqualTo("agent");
        assertThat(message.get("agentId", String.class)).isEqualTo("编辑");
        assertThat(message.get("content", String.class)).isEqualTo(answer);
        assertThat(message.get("createdAt", LocalDateTime.class)).isEqualTo(NOW);
        var metadata = json.readTree(message.get("metadata", String.class));
        assertThat(metadata.path("taskId").asText()).isEqualTo(flow.runId());
        assertThat(metadata.path("eventType").asText()).isEqualTo("done");
        assertThat(metadata.path("agentId").asText()).isEqualTo("编辑");
        assertThat(metadata.path("source").path("engineVersion").asInt()).isEqualTo(2);
        assertThat(metadata.path("source").path("runId").asText()).isEqualTo(flow.runId());
        assertThat(metadata.path("source").path("stepId").asText())
                .isEqualTo(flow.request().getStepId());
        assertThat(metadata.path("source").path("modelProfile").asText())
                .isEqualTo("editor.answer.v1");
        assertThat(metadata.path("source").path("outcomeType").asText())
                .isEqualTo("chat_answer");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WritingMessage\" WHERE \"sessionId\" = ? AND role = 'agent'",
                        flow.sessionId()))
                .isEqualTo(1);

        Record step = database.dsl().fetchOne(
                """
                SELECT status::text AS status, output, "artifactId", "artifactRevision",
                       "resultHash", "completedAt"
                FROM public."WorkflowStep" WHERE id = ?
                """,
                flow.request().getStepId());
        assertThat(step.get("status", String.class)).isEqualTo("completed");
        assertThat(step.get("artifactId", String.class)).isNull();
        assertThat(step.get("artifactRevision", Integer.class)).isNull();
        assertThat(step.get("resultHash", String.class)).isEqualTo(result.getResultHash());
        assertThat(step.get("completedAt", LocalDateTime.class)).isEqualTo(NOW);
        assertThat(json.readTree(step.get("output", String.class)).path("answer").asText())
                .isEqualTo(answer);

        Record run = database.dsl().fetchOne(
                """
                SELECT status::text AS status, "completedAt", "errorCode", "lastEventSequence"
                FROM public."WorkflowRun" WHERE id = ?
                """,
                flow.runId());
        assertThat(run.get("status", String.class)).isEqualTo("completed");
        assertThat(run.get("completedAt", LocalDateTime.class)).isEqualTo(NOW);
        assertThat(run.get("errorCode", String.class)).isNull();
        assertThat(eventTypes(flow.runId())).endsWith("step_finished", "completed");
        String completedPayload = database.dsl().fetchOne(
                        """
                        SELECT "payloadJson" FROM public."WorkflowEvent"
                        WHERE "runId" = ? AND "eventType" = 'completed'
                        """,
                        flow.runId())
                .get("payloadJson", String.class);
        var completed = json.readTree(completedPayload);
        assertThat(completed.path("outcomeType").asText()).isEqualTo("chat_answer");
        assertThat(completed.path("resultId").asText())
                .isEqualTo(message.get("id", String.class));
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'review'",
                        flow.runId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                        flow.runId()))
                .isZero();
        assertThat(database.dsl().fetchOne(
                                "SELECT \"updatedAt\" FROM public.\"WritingSession\" WHERE id = ?",
                                flow.sessionId())
                        .get("updatedAt", LocalDateTime.class))
                .isEqualTo(NOW.plusNanos(1_000_000));
    }

    @Test
    void 问答空白或额外字段均按冻结Schema拒绝且事务不留下消息或终态() {
        List<Map<String, Object>> invalidOutputs = List.of(
                Map.of("answer", " \n\t　"),
                Map.of("answer", "不能夹带控制字段", "toolCall", Map.of("name", "forbidden")));
        int index = 0;
        for (Map<String, Object> invalidOutput : invalidOutputs) {
            Flow flow = runningAnswerFlow("callback-answer-invalid-" + ++index);
            int eventCount = eventTypes(flow.runId()).size();
            ExecutionStepResult result = answerResult(flow.request(), "占位回答");
            result.getOutput().get().clear();
            result.getOutput().get().putAll(invalidOutput);
            result.setResultHash(ExecutionCanonicalJson.sha256(
                    WorkflowCallbackValues.resultHashMaterial(result)));

            assertThatThrownBy(() -> callbacks.result(result))
                    .isInstanceOfSatisfying(ApiException.class, error -> {
                        assertThat(error.statusCode()).isEqualTo(409);
                        assertThat(error.code()).isEqualTo("WORKFLOW_CALLBACK_INVALID");
                    });
            assertThat(count(
                            "SELECT count(*) AS count FROM public.\"WritingMessage\" WHERE \"sessionId\" = ? AND role = 'agent'",
                            flow.sessionId()))
                    .isZero();
            assertThat(database.dsl().fetchOne(
                            """
                            SELECT status::text AS status, output, "resultHash", "completedAt"
                            FROM public."WorkflowStep" WHERE id = ?
                            """,
                            flow.request().getStepId()))
                    .satisfies(step -> {
                        assertThat(step.get("status", String.class)).isEqualTo("running");
                        assertThat(step.get("output", String.class)).isNull();
                        assertThat(step.get("resultHash", String.class)).isNull();
                        assertThat(step.get("completedAt", LocalDateTime.class)).isNull();
                    });
            assertThat(eventTypes(flow.runId())).hasSize(eventCount);
            assertThat(count(
                            "SELECT count(*) AS count FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                            flow.runId()))
                    .isZero();

            cancellations.request(
                    flow.userId(), flow.runId(), "callback-answer-invalid-cleanup-" + index);
            assertThat(callbacks.failure(preProviderFailure(flow.request())).getStatus())
                    .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        }
    }

    @Test
    void 问答失败和取消均收敛Run但绝不创建成功消息() {
        Flow failed = runningAnswerFlow("callback-answer-failed");
        assertThat(callbacks.failure(preProviderFailure(failed.request())).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                                failed.runId())
                        .get("status", String.class))
                .isEqualTo("failed");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WritingMessage\" WHERE \"sessionId\" = ? AND role = 'agent'",
                        failed.sessionId()))
                .isZero();

        Flow cancelled = runningAnswerFlow("callback-answer-cancelled");
        cancellations.request(
                cancelled.userId(), cancelled.runId(), "callback-answer-cancel-request-0001");
        assertThat(callbacks.result(answerResult(cancelled.request(), "取消后不得保存")).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(database.dsl().fetchOne(
                                "SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?",
                                cancelled.runId())
                        .get("status", String.class))
                .isEqualTo("cancelled");
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"WritingMessage\" WHERE \"sessionId\" = ? AND role = 'agent'",
                        cancelled.sessionId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) AS count FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" IN (?, ?)",
                        failed.runId(),
                        cancelled.runId()))
                .isZero();
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
        return new Flow(started.runId(), fixture.userId(), fixture.sessionId(), request);
    }

    private static Flow runningAnswerFlow(String prefix) {
        Fixture fixture = fixture(prefix);
        var started = starts.start(answerPlan(fixture, prefix + "-request-0001"));
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        assertThat(request.getOperation()).isEqualTo("answer_question");
        assertThat(request.getPurpose()).isEqualTo("generation");
        assertThat(request.getInput()).containsOnlyKeys("userInstruction");
        accept(request);
        assertThat(callbacks.progress(progress(request, unknownUsage())).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        return new Flow(started.runId(), fixture.userId(), fixture.sessionId(), request);
    }

    private static void enqueueRevisionGeneration(
            String runId, String sourceStepId, String artifactId, int artifactRevision) {
        enqueueRevisionGeneration(runId, sourceStepId, artifactId, artifactRevision, null);
    }

    private static void enqueueRevisionGeneration(
            String runId, String sourceStepId, String artifactId, int artifactRevision, Map<String, Object> input) {
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
                       coalesce(CAST(? AS text), input), ?, (SELECT max(ordinal) + 1 FROM public."WorkflowStep" WHERE "runId" = ?),
                       'generation', lane, 0, ?, 0, ?, ?, coalesce(CAST(? AS text), "inputHash"), "evidenceBundleId",
                       ?, ?, "modelProfile", "modelProfileVersion", "outputSchema",
                       "outputSchemaVersion", "budgetJson", ?, ?
                FROM public."WorkflowStep" WHERE id = ? AND "runId" = ?
                """,
                stepId,
                input == null ? null : json.writeValueAsString(input),
                NOW,
                runId,
                NOW,
                runId + "." + stepId,
                sha256(stepId),
                input == null ? null : ExecutionCanonicalJson.sha256(input),
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

    private static ExecutionStepResult answerResult(
            ExecutionStepRequest request, String answer) {
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
                        answerUsage())
                .output(new LinkedHashMap<>(Map.of("answer", answer)));
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

    private static StepUsage answerUsage() {
        return new StepUsage(0, 1, StepUsage.UsageStatusEnum.PARTIAL, 1_000)
                .inputTokens(100)
                .cachedTokens(0)
                .promptCacheMissTokens(100)
                .completionTokens(20)
                .reasoningTokens(0)
                .visibleOutputTokens(20);
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

    private static WorkflowStartPlan answerPlan(Fixture fixture, String requestId) {
        Map<String, Object> input = Map.of("userInstruction", "这一段的叙事视角是什么？");
        return new WorkflowStartPlan(
                fixture.userId(),
                requestId,
                sha256(requestId),
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
                answerOperation.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan(
                        "chapter_content",
                        fixture.chapterId(),
                        true,
                        null,
                        API_NOW,
                        "甲😀乙",
                        null,
                        null,
                        null,
                        Map.of("role", "chapter_source"))),
                answerOperation.operation().runBudget(),
                ExecutionPlanSnapshot.freeze(
                        registry.catalogVersion(),
                        registry.manifestFingerprint(),
                        answerOperation),
                new WorkflowInitialStepPlan(
                        "generation",
                        answerOperation.operation().lane(),
                        input,
                        answerOperation.generatorProfile(),
                        answerOperation.generatorStepBudget(),
                        answerOperation.outputSchema()));
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

    private static int count(String sql, Object... bindings) {
        return database.dsl().fetchOne(sql, bindings).get("count", Integer.class);
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

    private record Flow(
            String runId, String userId, String sessionId, ExecutionStepRequest request) {}
}
