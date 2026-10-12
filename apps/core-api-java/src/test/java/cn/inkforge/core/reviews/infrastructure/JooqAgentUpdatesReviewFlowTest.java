package cn.inkforge.core.reviews.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ArtifactSelectionRef;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.core.lore.infrastructure.JooqLoreRepository;
import cn.inkforge.core.outlines.infrastructure.JooqOutlineRepository;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.infrastructure.ReferenceRepositoryTestFactory;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.Source;
import cn.inkforge.core.reviews.application.AgentUpdatesExecutor;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.domain.DurableAgentUpdatesArtifact;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/** 使用冻结计划夹具验证真实审核读取/决定事务，不代表五项生产资产或 Agent 入口已启用。 */
@Testcontainers
class JooqAgentUpdatesReviewFlowTest {
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-05T05:00:00.123");
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-05T05:00:00.123Z"), ZoneOffset.UTC);
    private static final JsonMapper JSON = JsonMapper.builder().build();
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("test-only-password");
    private static CoreDatabase database;
    private static JooqReviewRepository reviews;
    private static JooqWorkflowStartRepository starts;
    private static ExecutionRegistry registry;
    private static ExecutionRegistry.OutputSchema outputSchema;

    @BeforeAll
    static void schema() throws Exception {
        for (String path : List.of("db/novelwriterdev-schema.sql", "migrations/20260831_durable_agent_execution.sql")) {
            POSTGRES.copyFileToContainer(MountableFile.forClasspathResource(path), "/tmp/test.sql");
            var result = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(), "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/test.sql");
            assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        }
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432) + "/" + POSTGRES.getDatabaseName()));
        registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        try (var stream = JooqAgentUpdatesReviewFlowTest.class.getResourceAsStream("/agent-execution/output-schema-registry.v1.json")) {
            Map<String, Object> document = JSON.readValue(stream, new TypeReference<>() {});
            for (Object raw : (List<?>) document.get("schemas")) {
                Map<?, ?> item = (Map<?, ?>) raw;
                if ("output.agent_updates.v2".equals(item.get("key"))) outputSchema = JSON.convertValue(item, ExecutionRegistry.OutputSchema.class);
            }
        }
        assertThat(outputSchema).isNotNull();
        var ids = new CuidV1Generator(CLOCK);
        var writer = new AgentUpdatesExecutor(new JooqLoreRepository(database, ids, CLOCK), new JooqOutlineRepository(database, ids, CLOCK),
                ReferenceRepositoryTestFactory.create(database, ids, CLOCK), ids, false);
        reviews = new JooqReviewRepository(database, ids, CLOCK, JSON, new JooqFormalArtifactWriter(database, ids, CLOCK, JSON, writer), registry, true);
        starts = new JooqWorkflowStartRepository(database, ids, CLOCK, JSON);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 五项草案均能从冻结来源读取完整Diff并通过原接口部分采用() {
        for (String operation : List.of("create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing")) {
            Fixture f = fixture(operation, false);
            var detail = reviews.getDetail(f.novel(), f.artifact(), 1, null).response();
            assertThat(detail.getSummary()).isEqualTo("原始说明");
            assertThat(detail.getDiff().orElse(null)).isInstanceOf(List.class);
            assertThat(JSON.writeValueAsString(detail.getDiff().orElse(null))).contains("旧人物原文", "第一项更新", "第二项更新");
            database.dsl().execute("UPDATE public.\"Character\" SET background = '作者改了未选项' WHERE id = ?", f.novel() + "-b");
            var request = decision(f, ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)
                    .selectedUpdateRefs(List.of(new ArtifactSelectionRef("characters").index(0)));
            var accepted = reviews.decide(f.novel(), f.artifact(), request);
            assertThat(JSON.valueToTree(accepted).path("status").asText()).isEqualTo("completed");
            assertThat(JSON.writeValueAsString(reviews.decide(f.novel(), f.artifact(), request))).isEqualTo(JSON.writeValueAsString(accepted));
            assertThat(content(f.novel() + "-a")).isEqualTo("第一项更新");
            assertThat(content(f.novel() + "-b")).isEqualTo("作者改了未选项");
            assertThat(database.dsl().fetchValue("SELECT status::text FROM public.\"ReviewArtifact\" WHERE id = ?", f.artifact())).isEqualTo("applied");
            assertThat(database.dsl().fetchValue("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'", f.run())).isEqualTo(1L);
        }
    }

    @Test
    void 所选来源冲突回滚决定Step和审核状态但历史详情仍可重建() {
        Fixture f = fixture("revise_lore", false);
        database.dsl().execute("UPDATE public.\"Character\" SET background = '作者更新了所选资料' WHERE id = ?", f.novel() + "-a");
        assertThat(JSON.writeValueAsString(reviews.getDetail(f.novel(), f.artifact(), 1, null).response().getDiff().orElse(null))).contains("旧人物原文");
        assertThatThrownBy(() -> reviews.decide(f.novel(), f.artifact(), decision(f, ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)))
                .isInstanceOfSatisfying(ApiException.class, error -> assertThat(error.code()).isEqualTo("AGENT_UPDATES_SOURCE_CHANGED"));
        assertThat(database.dsl().fetchValue("SELECT status::text FROM public.\"ReviewArtifact\" WHERE id = ?", f.artifact())).isEqualTo("awaiting_user");
        assertThat(database.dsl().fetchValue("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'", f.run())).isEqualTo(0L);
    }

    @Test
    void 候选摘要与生成完整结果不匹配时读取和采用都拒绝() {
        Fixture f = fixture("revise_lore", true);
        assertThatThrownBy(() -> reviews.getDetail(f.novel(), f.artifact(), 1, null)).isInstanceOfSatisfying(ApiException.class,
                error -> assertThat(error.code()).isEqualTo("ARTIFACT_REVISION_INTEGRITY_ERROR"));
        assertThatThrownBy(() -> reviews.decide(f.novel(), f.artifact(), decision(f, ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)))
                .isInstanceOf(ApiException.class);
        assertThat(content(f.novel() + "-a")).isEqualTo("旧人物原文");
    }

    @Test
    void 返工传递原始结构化候选且保留同Run不允许夹带采用选择() {
        Fixture invalid = fixture("revise_lore", false);
        assertThatThrownBy(() -> reviews.decide(invalid.novel(), invalid.artifact(), decision(invalid, ReviewArtifactDecisionRequest.DecisionEnum.REVISE)
                .userMessage("请修改动机").selectedUpdateRefs(List.of(new ArtifactSelectionRef("characters")))))
                .isInstanceOf(ApiException.class);
        Fixture f = fixture("revise_lore", false);
        var result = reviews.decide(f.novel(), f.artifact(), decision(f, ReviewArtifactDecisionRequest.DecisionEnum.REVISE).userMessage("请修改动机"));
        assertThat(JSON.valueToTree(result).path("runId").asText()).isEqualTo(f.run());
        var input = JSON.readTree(database.dsl().fetchOne("SELECT input FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation' ORDER BY ordinal DESC LIMIT 1", f.run()).get(0, String.class));
        assertThat(input.path("originalUserInstruction").asText()).isEqualTo("调整资料");
        assertThat(input.path("userInstruction").asText()).isEqualTo("请修改动机");
        assertThat(input.at("/previousCandidate/summary").asText()).isEqualTo("原始说明");
        assertThat(input.at("/previousCandidate/updates/characters/0/name").asText()).isEqualTo("甲");
        assertThat(content(f.novel() + "-a")).isEqualTo("旧人物原文");
    }

    private static Fixture fixture(String name, boolean changedSummary) {
        String n = "review-updates-" + UUID.randomUUID();
        database.dsl().execute("INSERT INTO public.\"User\" (id,username,\"passwordHash\",\"updatedAt\") VALUES (?, ?, 'test', ?)", n, n, NOW);
        database.dsl().execute("INSERT INTO public.\"Novel\" (id,name,\"userId\",\"updatedAt\") VALUES (?, '测试资料', ?, ?)", n, n, NOW);
        for (String suffix : List.of("a", "b")) database.dsl().execute("INSERT INTO public.\"Character\" (id,\"novelId\",name,background,\"updatedAt\") VALUES (?, ?, ?, '旧人物原文', ?)", n + "-" + suffix, n, suffix.equals("a") ? "甲" : "乙", NOW);
        var reader = new JooqAgentUpdatesEvidenceReader(JSON);
        List<WorkflowEvidenceItemPlan> items = database.transactionResult(tx -> {
            List<WorkflowEvidenceItemPlan> values = new ArrayList<>(reader.capture(tx, n, List.of(new Source(ResourceKind.CHARACTER, n + "-a"), new Source(ResourceKind.CHARACTER, n + "-b"))));
            values.add(reader.captureIndex(tx, n));
            return values;
        });
        // 仅为基础接线构造冻结计划，沿用已验证模型/预算夹具；不修改仓库 Catalog 或启用真实 Provider。
        var base = registry.resolve("long_serial.plan_chapter", false);
        var old = base.operation();
        var operation = new ExecutionRegistry.Operation("long_serial." + name, "long_serial", name, List.of("novel"), List.of("novel"),
                true, false, true, old.lane(), old.evidencePolicy(), old.generatorProfile(), old.generatorStepBudgetProfile(), outputSchema.key(),
                old.deterministicValidators(), old.reviewPolicy(), "apply.agent_updates.v1", old.runBudget());
        var resolved = new ExecutionRegistry.ResolvedOperation(operation, base.generatorProfile(), base.generatorStepBudget(), outputSchema, base.reviewers(), base.reviewerOutputSchema());
        var plan = ExecutionPlanSnapshot.freeze("1", registry.manifestFingerprint(), resolved);
        Map<String, Object> input = Map.of("userInstruction", "调整资料");
        var started = starts.start(new WorkflowStartPlan(n, n + "-request", ExecutionCanonicalJson.sha256(n), "long_serial", name, "1",
                "chapter_generation", n, null, null, "novel", n, input, old.evidencePolicy(), items, old.runBudget(), plan,
                new WorkflowInitialStepPlan("generation", old.lane(), input, base.generatorProfile(), base.generatorStepBudget(), outputSchema)));
        String bundle = database.dsl().fetchOne("SELECT \"currentEvidenceBundleId\" FROM public.\"WorkflowRun\" WHERE id = ?", started.runId()).get(0, String.class);
        String artifact = n + "-artifact";
        Map<String, Object> updates = Map.of("characters", List.of(Map.of("action", "update", "name", "甲", "background", "第一项更新"),
                Map.of("action", "update", "name", "乙", "background", "第二项更新")));
        Map<String, Object> output = Map.of("summary", "原始说明", "updates", updates, "updatesSha256", ExecutionCanonicalJson.sha256(updates));
        Map<String, Object> model = Map.of("provider", "test-fixture", "model", "no-provider-call");
        Map<String, Object> usage = new LinkedHashMap<>(Map.of("usageStatus", "complete", "providerAttempts", 1, "protocolCorrections", 0, "wallTimeMillis", 0));
        for (String field : List.of("inputTokens", "cachedTokens", "promptCacheMissTokens", "completionTokens", "reasoningTokens", "visibleOutputTokens", "costMicros")) usage.put(field, 0);
        String resultHash = ExecutionCanonicalJson.sha256(Map.of("resultKind", "output", "value", output, "resolvedModel", model, "usage", usage));
        Map<String, Object> candidate = new LinkedHashMap<>(output);
        if (changedSummary) candidate.put("summary", "错误的其他摘要");
        var stored = DurableAgentUpdatesArtifact.create(name, bundle,
                database.dsl().fetchOne("SELECT \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ?", bundle).get(0, String.class), n,
                candidate, started.stepId(), resultHash, outputSchema.jsonSchema());
        database.dsl().execute("""
                INSERT INTO public."ReviewArtifact" (id,"novelId","workflowRunId","artifactKey",kind,status,title,summary,"payloadJson","diffJson","createdByAgent","updatedByAgent",revision,"createdAt","updatedAt")
                VALUES (?, ?, ?, ?, 'agent_updates', 'awaiting_user', '资料建议', '不可信 head 摘要', ?, ?, ?, ?, 1, ?, ?)
                """, artifact, n, started.runId(), "workflow:" + started.runId() + ":candidate", JSON.writeValueAsString(stored.payload()), JSON.writeValueAsString(stored.diff()),
                base.generatorProfile().key(), base.generatorProfile().key(), NOW, NOW);
        database.dsl().execute("INSERT INTO public.\"ReviewArtifactRevision\" (id,\"artifactId\",revision,summary,\"payloadJson\",\"diffJson\",\"createdByAgent\",\"createdAt\") VALUES (?, ?, 1, '原始说明', ?, ?, ?, ?)",
                n + "-revision", artifact, JSON.writeValueAsString(stored.payload()), JSON.writeValueAsString(stored.diff()), base.generatorProfile().key(), NOW);
        database.dsl().execute("""
                UPDATE public."WorkflowStep" SET status = 'completed', output = ?, "resultHash" = ?, "artifactId" = ?, "artifactRevision" = 1,
                  "resolvedModelJson" = ?, "usageJson" = ?, "updatedAt" = ?, "completedAt" = ? WHERE id = ?
                """, JSON.writeValueAsString(Map.of("artifactId", artifact, "artifactRevision", 1, "updatesSha256", output.get("updatesSha256"))),
                resultHash, artifact, JSON.writeValueAsString(model), JSON.writeValueAsString(usage), NOW, NOW, started.stepId());
        database.dsl().execute("UPDATE public.\"WorkflowRun\" SET status = 'waiting_user', revision = 2, \"updatedAt\" = ? WHERE id = ?", NOW, started.runId());
        return new Fixture(n, started.runId(), artifact);
    }

    private static ReviewArtifactDecisionRequest decision(Fixture f, ReviewArtifactDecisionRequest.DecisionEnum decision) {
        return new ReviewArtifactDecisionRequest(f.artifact() + "-decision", decision, 1)
                .engineVersion(ReviewArtifactDecisionRequest.EngineVersionEnum.NUMBER_2);
    }

    private static String content(String id) { return database.dsl().fetchOne("SELECT background FROM public.\"Character\" WHERE id = ?", id).get(0, String.class); }
    private record Fixture(String novel, String run, String artifact) {}
}
