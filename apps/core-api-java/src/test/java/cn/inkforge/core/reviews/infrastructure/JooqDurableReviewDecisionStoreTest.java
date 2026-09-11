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
import cn.inkforge.core.workflows.domain.DurableBeatPlanArtifact;
import cn.inkforge.core.workflows.domain.DurableChapterDraftArtifact;
import cn.inkforge.core.workflows.domain.DurableOutlineSelectionArtifact;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowExecutionContextReader;
import cn.inkforge.core.workflows.infrastructure.IntentSelectedRunTestFixture;
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
import tools.jackson.core.type.TypeReference;
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
        reviews = new JooqReviewRepository(database, ids, CLOCK, json, formal, registry, true,
                new JooqWorkflowExecutionContextReader(json));
        starts = new JooqWorkflowStartRepository(database, ids, CLOCK, json);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 自然规划采用合成澄清指令的来源并投影所选操作() {
        Fixture fixture = waitingArtifact("natural-plan-approve", false, true, false, false, true);
        var request = decision("natural-plan-approve-request-1", ReviewArtifactDecisionRequest.DecisionEnum.APPROVE);
        var response = (WritingRunV2Response) reviews.decide(fixture.userId(), fixture.artifactId(), request);
        assertThat(response.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.COMPLETED);
        assertThat(response.getOperation()).isEqualTo("plan_chapter");
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
        assertThat(database.dsl().fetchOne("SELECT operation FROM public.\"WorkflowRun\" WHERE id = ?", fixture.runId()).get(0, String.class)).isNull();
    }

    @Test
    void 自然正文批准使用首生成完整指令而不是Run未决原文() {
        Fixture fixture = waitingArtifact("natural-draft-approve", false, false, true, false, true);
        var request = decision("natural-draft-approve-request-1", ReviewArtifactDecisionRequest.DecisionEnum.APPROVE);
        var response = (WritingRunV2Response) reviews.decide(fixture.userId(), fixture.artifactId(), request);
        assertThat(response.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.COMPLETED);
        assertThat(response.getOperation()).isEqualTo("write_chapter");
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("完整模型正文😀");
        assertThat(reviews.decide(fixture.userId(), fixture.artifactId(), request)).isEqualTo(response);
    }

    @Test
    void 自然正文返工保留六次业务额度并在请求哈希中使用有效操作() {
        Fixture fixture = waitingArtifact("natural-draft-revise", true, false, true, false, true);
        var request = decision("natural-draft-revise-request-1", ReviewArtifactDecisionRequest.DecisionEnum.REVISE).userMessage("保留完整来源继续修订");
        var response = (WritingRunV2Response) reviews.decide(fixture.userId(), fixture.artifactId(), request);
        assertThat(response.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.RUNNING);
        assertThat(response.getOperation()).isEqualTo("write_chapter");
        assertThat(response.getActiveSteps()).hasSize(1);
        Record generation = database.dsl().fetchOne("SELECT input, \"requestHash\", \"evidenceBundleId\" FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation' ORDER BY ordinal DESC LIMIT 1", fixture.runId());
        assertThat(json.readTree(generation.get("input", String.class)).path("originalUserInstruction").asText()).contains("initialInstruction", "clarifications");
        assertThat(generation.get("evidenceBundleId", String.class)).isEqualTo(fixture.bundleId());
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'resolve_intent'", fixture.runId())).isEqualTo(1);
        assertThat(reviews.decide(fixture.userId(), fixture.artifactId(), request)).isEqualTo(response);
    }

    @Test
    void 场景候选详情返工与编辑批准始终保留真实操作() {
        Fixture revise = waitingSceneArtifact("scene-revise", true);
        var detail = reviews.getDetail(revise.userId(), revise.artifactId(), 1, null);
        assertThat(detail.response().getPayload())
                .containsEntry("operation", "rewrite_scene")
                .containsEntry("content", "完整模型正文😀");
        var revised = (WritingRunV2Response) reviews.decide(
                revise.userId(), revise.artifactId(),
                decision("scene-revise-request-001", ReviewArtifactDecisionRequest.DecisionEnum.REVISE)
                        .userMessage("重写场景冲突"));
        assertThat(revised.getOperation()).isEqualTo("rewrite_scene");
        Record next = database.dsl().fetchOne(
                "SELECT input FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation' ORDER BY ordinal DESC LIMIT 1",
                revise.runId());
        assertThat(json.readTree(next.get("input", String.class))
                        .path("previousArtifact").path("payload").path("content").asText())
                .isEqualTo("完整模型正文😀");

        Fixture approve = waitingSceneArtifact("scene-approve", false);
        var accepted = (WritingRunV2Response) reviews.decide(
                approve.userId(), approve.artifactId(),
                decision("scene-approve-request-01", ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)
                        .editedContent("作者完整场景🚀"));
        assertThat(accepted.getOperation()).isEqualTo("rewrite_scene");
        assertThat(chapterContent(approve.chapterId())).isEqualTo("作者完整场景🚀");
        assertThat(database.dsl().fetchOne(
                        "SELECT \"chapterGoal\" FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ?",
                        approve.chapterId()).get(0, String.class))
                .isEqualTo("旧正式计划");
    }

    @Test
    void 总纲和节点选区编辑批准只替换目标范围() {
        for (String type : List.of("outline_content", "outline_node_content")) {
            Fixture fixture = waitingOutlineArtifact("outline-approve-" + type, type, false);
            var detail = reviews.getDetail(fixture.userId(), fixture.artifactId(), 1, null);
            assertThat(detail.response().getPayload())
                    .containsEntry("operation", "rewrite_outline_selection")
                    .containsEntry("resourceType", type)
                    .containsEntry("selectedText", "😀");
            var response = (WritingRunV2Response) reviews.decide(
                    fixture.userId(), fixture.artifactId(),
                    decision("outline-approve-request-" + type,
                            ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)
                            .editedReplacement("用户🚀"));
            assertThat(response.getOperation()).isEqualTo("rewrite_outline_selection");
            assertThat(outlineContent(fixture, type)).isEqualTo("纲用户🚀要");
            assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
        }
    }

    @Test
    void 大纲选区返工与丢弃保留来源且来源漂移零副作用() {
        Fixture revise = waitingOutlineArtifact("outline-revise", "outline_node_content", true);
        var response = (WritingRunV2Response) reviews.decide(
                revise.userId(), revise.artifactId(),
                decision("outline-revise-request-1", ReviewArtifactDecisionRequest.DecisionEnum.REVISE)
                        .userMessage("让节点转折更清晰"));
        assertThat(response.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.RUNNING);
        Record next = database.dsl().fetchOne(
                "SELECT input, \"evidenceBundleId\" FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation' ORDER BY ordinal DESC LIMIT 1",
                revise.runId());
        assertThat(json.readTree(next.get("input", String.class)).path("previousCandidate")
                        .path("replacement").asText())
                .isEqualTo("模型改写");
        assertThat(next.get("evidenceBundleId", String.class)).isEqualTo(revise.bundleId());

        Fixture discard = waitingOutlineArtifact("outline-discard", "outline_content", false);
        reviews.decide(discard.userId(), discard.artifactId(),
                decision("outline-discard-request-1", ReviewArtifactDecisionRequest.DecisionEnum.DISCARD));
        assertThat(outlineContent(discard, "outline_content")).isEqualTo("纲😀要");

        Fixture conflict = waitingOutlineArtifact("outline-conflict", "outline_content", false);
        database.dsl().execute(
                "UPDATE public.\"Outline\" SET content = '漂移', \"updatedAt\" = ? WHERE id = ?",
                NOW.plusSeconds(1), conflict.novelId() + "-outline");
        assertThatThrownBy(() -> reviews.decide(
                        conflict.userId(), conflict.artifactId(),
                        decision("outline-conflict-request-1",
                                ReviewArtifactDecisionRequest.DecisionEnum.APPROVE)))
                .isInstanceOfSatisfying(ApiException.class,
                        error -> assertThat(error.code())
                                .isEqualTo("ARTIFACT_SOURCE_VERSION_CONFLICT"));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'", conflict.runId())).isZero();
    }

    @Test
    void 整章详情重建完整正文来源和强ETag且批准只应用正文() {
        Fixture fixture = waitingArtifact("draft-approve", false, false, true);
        var detail = reviews.getDetail(fixture.userId(), fixture.artifactId(), 1, null);
        assertThat(detail.response().getPayload()).containsEntry("operation", "write_chapter")
                .containsEntry("target", Map.of("mode", "existing_chapter", "chapterId", fixture.chapterId()))
                .containsEntry("content", "完整模型正文😀");
        assertThat(detail.response().getDiff().get()).isEqualTo(Map.of("type", "chapter_content", "before", "甲😀乙", "after", "完整模型正文😀"));
        assertThat(detail.response().getSourceBindings()).isNotEmpty();
        assertThat(reviews.getDetail(fixture.userId(), fixture.artifactId(), 1, detail.etag()).notModified()).isTrue();
        var request = decision("draft-approve-request-0001", ReviewArtifactDecisionRequest.DecisionEnum.APPROVE);
        var accepted = (WritingRunV2Response) reviews.decide(fixture.userId(), fixture.artifactId(), request);
        assertThat(reviews.decide(fixture.userId(), fixture.artifactId(), request)).isEqualTo(accepted);
        assertThat(accepted.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.COMPLETED);
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("完整模型正文😀");
        assertThat(count("SELECT count(*) FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?", fixture.artifactId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"Chapter\" WHERE \"novelId\" = ?", fixture.novelId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ? AND status = 'approved' AND \"chapterGoal\" = '旧正式计划'", fixture.chapterId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'", fixture.runId())).isEqualTo(1);
    }

    @Test
    void 整章编辑批准保留完整Unicode用户修订和零模型决定且同文仍重置章节状态() {
        for (boolean unchanged : List.of(false, true)) {
            Fixture fixture = waitingArtifact("draft-edited-" + unchanged, false, false, true);
            String content = unchanged ? "甲😀乙" : "全量用户文本😀\n".repeat(15000);
            var request = decision("draft-edited-request-" + unchanged, ReviewArtifactDecisionRequest.DecisionEnum.APPROVE).editedContent(content);
            var accepted = (WritingRunV2Response) reviews.decide(fixture.userId(), fixture.artifactId(), request);
            assertThat(reviews.decide(fixture.userId(), fixture.artifactId(), request)).isEqualTo(accepted);
            assertThat(chapterContent(fixture.chapterId())).isEqualTo(content);
            assertThat(accepted.getArtifact().getArtifactRevision()).isEqualTo(2);
            Record chapter = database.dsl().fetchOne("SELECT status::text, \"completedAt\" FROM public.\"Chapter\" WHERE id = ?", fixture.chapterId());
            assertThat(chapter.get("status", String.class)).isEqualTo("drafting");
            assertThat(chapter.get("completedAt")).isNull();
            assertThat(count("SELECT count(*) FROM public.\"ChapterQualityCheck\" WHERE \"chapterId\" = ? AND status = 'pending'", fixture.chapterId())).isEqualTo(1);
            Record stored = database.dsl().fetchOne("SELECT \"payloadJson\", \"diffJson\", \"createdByAgent\" FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ? AND revision = 2", fixture.artifactId());
            var payload = json.readTree(stored.get("payloadJson", String.class));
            assertThat(payload.path("content").asText()).isEqualTo(content);
            assertThat(payload.has("before")).isFalse();
            assertThat(json.readTree(stored.get("diffJson", String.class)).has("after")).isFalse();
            assertThat(stored.get("createdByAgent", String.class)).isEqualTo("用户");
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE id = ? AND purpose = 'user_decision' AND \"modelProfile\" IS NULL", payload.path("producingStepId").asText())).isEqualTo(1);
            assertThat(reviews.getDetail(fixture.userId(), fixture.artifactId(), 1, null).response().getPayload()).containsEntry("content", "完整模型正文😀");
            assertThat(reviews.getDetail(fixture.userId(), fixture.artifactId(), 2, null).response().getPayload()).containsEntry("content", content);
        }
    }

    @Test
    void 整章显式返工保留同Evidence完整候选和输入AB且丢弃不改正式内容() {
        Fixture fixture = waitingArtifact("draft-revise", true, false, true);
        var request = decision("draft-revise-request-0001", ReviewArtifactDecisionRequest.DecisionEnum.REVISE).userMessage("本次返工指令B");
        var accepted = reviews.decide(fixture.userId(), fixture.artifactId(), request);
        assertThat(reviews.decide(fixture.userId(), fixture.artifactId(), request)).isEqualTo(accepted);
        Record step = database.dsl().fetchOne("SELECT input, \"evidenceBundleId\", \"artifactRevision\" FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation' ORDER BY ordinal DESC LIMIT 1", fixture.runId());
        var input = json.readTree(step.get("input", String.class));
        assertThat(input.path("userInstruction").asText()).isEqualTo("本次返工指令B");
        assertThat(input.path("originalUserInstruction").asText()).isEqualTo("完整正文原始指令A");
        assertThat(input.path("targetWordCount").asInt()).isEqualTo(2500);
        assertThat(input.path("previousArtifact").path("artifactRevision").asInt()).isEqualTo(1);
        assertThat(input.path("previousArtifact").path("payload")).isEqualTo(json.valueToTree(DurableChapterDraftArtifact.deriveOutput("完整正文摘要", "完整模型正文😀")));
        assertThat(step.get("evidenceBundleId", String.class)).isEqualTo(fixture.bundleId());
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
        Fixture discarded = waitingArtifact("draft-discard", true, false, true);
        reviews.decide(discarded.userId(), discarded.artifactId(), decision("draft-discard-request-0001", ReviewArtifactDecisionRequest.DecisionEnum.DISCARD));
        assertThat(chapterContent(discarded.chapterId())).isEqualTo("甲😀乙");
        assertThat(count("SELECT count(*) FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?", discarded.artifactId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowEvaluation\" WHERE \"runId\" = ?", discarded.runId())).isEqualTo(2);
    }

    @Test
    void 整章作者返工在整轮任何剩余预算不足时提前原子拒绝() {
        for (String dimension : List.of("input", "completion", "reasoning", "visible", "cost", "wall", "wall_long")) {
            Fixture fixture = waitingArtifact("draft-budget-" + dimension, true, false, true, true);
            var steps = database.dsl().fetch("SELECT id, ordinal, \"budgetJson\" FROM public.\"WorkflowStep\" WHERE \"runId\" = ? ORDER BY ordinal", fixture.runId());
            for (Record step : steps) {
                boolean generator = step.get("ordinal", Integer.class) == 1;
                Map<String, Object> frozenBudget = json.readValue(
                        step.get("budgetJson", String.class), new TypeReference<>() {});
                long inputBudget = ((Number) ((Map<?, ?>) frozenBudget.get("budget"))
                        .get("maxInputTokens")).longValue();
                Map<String, Object> usage = new LinkedHashMap<>(Map.of("usageStatus", "complete", "inputTokens", inputBudget,
                        "cachedTokens", 0, "promptCacheMissTokens", inputBudget, "completionTokens", generator ? 16_000 : 2_000,
                        "reasoningTokens", generator ? 8_000 : 0, "visibleOutputTokens", generator ? 8_000 : 2_000,
                        "costMicros", generator ? 600_000 : 200_000, "providerAttempts", 1, "protocolCorrections", 0));
                usage.put("wallTimeMillis", generator ? 300_000 : 75_000);
                if (step.get("ordinal", Integer.class) == 2) {
                    switch (dimension) {
                        case "input" -> { usage.put("inputTokens", inputBudget + 1); usage.put("promptCacheMissTokens", inputBudget + 1); }
                        case "completion", "visible" -> { usage.put("completionTokens", 2_001); usage.put("visibleOutputTokens", 2_001); }
                        case "reasoning" -> { usage.put("completionTokens", 2_001); usage.put("reasoningTokens", 1); }
                        case "cost" -> usage.put("costMicros", 200_001);
                        case "wall" -> usage.put("wallTimeMillis", 75_001);
                        case "wall_long" -> usage.put("wallTimeMillis", 3_000_000_000L);
                        default -> throw new AssertionError(dimension);
                    }
                } else if ("cost".equals(dimension)) {
                    usage.clear();
                    usage.putAll(Map.of("usageStatus", "unknown", "providerAttempts", 1, "protocolCorrections", 0,
                            "wallTimeMillis", generator ? 300_000 : 75_000));
                }
                database.dsl().execute("UPDATE public.\"WorkflowStep\" SET \"usageJson\" = ? WHERE id = ?", json.writeValueAsString(usage), step.get("id", String.class));
            }
            var request = decision("draft-budget-request-" + dimension, ReviewArtifactDecisionRequest.DecisionEnum.REVISE).userMessage("再次完整生成并复审");
            assertThatThrownBy(() -> reviews.decide(fixture.userId(), fixture.artifactId(), request))
                    .isInstanceOf(ApiException.class).satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo("WORKFLOW_REVISION_BUDGET_EXCEEDED"));
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'", fixture.runId())).isEqualTo(1);
            assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'", fixture.runId())).isZero();
            assertThat(count("SELECT count(*) FROM public.\"ReviewArtifact\" WHERE id = ? AND status = 'awaiting_user' AND revision = 1", fixture.artifactId())).isEqualTo(1);
            assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
        }
    }

    @Test
    void 整章未知供应商用量按Step上限保留且恰好够完整一轮时允许返工() {
        Fixture fixture = waitingArtifact("draft-budget-boundary", true, false, true);
        for (Record step : database.dsl().fetch("SELECT id, ordinal FROM public.\"WorkflowStep\" WHERE \"runId\" = ? ORDER BY ordinal", fixture.runId())) {
            Map<String, Object> usage = Map.of("usageStatus", "unknown", "providerAttempts", 1, "protocolCorrections", 0,
                    "wallTimeMillis", step.get("ordinal", Integer.class) == 1 ? 300_000 : 75_000);
            database.dsl().execute("UPDATE public.\"WorkflowStep\" SET \"usageJson\" = ? WHERE id = ?", json.writeValueAsString(usage), step.get("id", String.class));
        }
        var request = decision("draft-budget-boundary-request", ReviewArtifactDecisionRequest.DecisionEnum.REVISE).userMessage("恰好覆盖完整生成和双复审");
        var response = (WritingRunV2Response) reviews.decide(fixture.userId(), fixture.artifactId(), request);
        assertThat(response.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.RUNNING);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation'", fixture.runId())).isEqualTo(2);
    }

    @Test
    void 整章拒绝错误编辑字段空白正文旧修订和完整来源漂移() {
        Fixture fixture = waitingArtifact("draft-conflict", false, false, true);
        var approve = decision("draft-conflict-request-0001", ReviewArtifactDecisionRequest.DecisionEnum.APPROVE);
        for (String content : List.of("", "\u0085\uFEFF　")) {
            assertThatThrownBy(() -> reviews.decide(fixture.userId(), fixture.artifactId(), approve.editedContent(content)))
                    .isInstanceOf(ApiException.class).satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo("VALIDATION_ERROR"));
        }
        approve.setEditedContent(org.openapitools.jackson.nullable.JsonNullable.undefined());
        assertThatThrownBy(() -> reviews.decide(fixture.userId(), fixture.artifactId(), approve.editedReplacement("错误字段")))
                .isInstanceOf(ApiException.class).satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo("VALIDATION_ERROR"));
        approve.setEditedReplacement(org.openapitools.jackson.nullable.JsonNullable.undefined());
        approve.setExpectedRevision(2);
        assertThatThrownBy(() -> reviews.decide(fixture.userId(), fixture.artifactId(), approve)).isInstanceOf(ApiException.class);
        approve.setExpectedRevision(1);
        database.dsl().execute("UPDATE public.\"ChapterBeatPlan\" SET \"chapterGoal\" = '已改变但timestamp相同' WHERE \"chapterId\" = ?", fixture.chapterId());
        assertThatThrownBy(() -> reviews.decide(fixture.userId(), fixture.artifactId(), approve))
                .isInstanceOf(ApiException.class).satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo("ARTIFACT_SOURCE_VERSION_CONFLICT"));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'", fixture.runId())).isZero();
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
    }

    @Test
    void 章节计划批准单事务替换正式计划且重复请求不增场景不改正文() {
        Fixture fixture = waitingArtifact("plan-approve", false, true);
        var request = decision("plan-approve-request-0001", ReviewArtifactDecisionRequest.DecisionEnum.APPROVE);
        var response = reviews.decide(fixture.userId(), fixture.artifactId(), request);
        assertThat(reviews.decide(fixture.userId(), fixture.artifactId(), request)).isEqualTo(response);
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
        assertThat(count("SELECT count(*) FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ? AND status = 'approved'", fixture.chapterId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ? AND status = 'superseded'", fixture.chapterId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"SceneBeat\" WHERE \"beatPlanId\" IN (SELECT id FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ? AND status = 'approved')", fixture.chapterId())).isEqualTo(2);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'", fixture.runId())).isEqualTo(1);
        assertThat(eventTypes(fixture.runId())).endsWith("applying", "completed");
    }

    @Test
    void 章节计划详情从最小Revision重建完整计划来源与强ETag() {
        Fixture fixture = waitingArtifact("plan-detail", false, true);
        var detail = reviews.getDetail(fixture.userId(), fixture.artifactId(), 1, null);
        assertThat(detail.response().getKind().getValue()).isEqualTo("beat_plan");
        assertThat(detail.response().getPayload()).containsEntry("beatPlan", DurableBeatPlanArtifact.validateOutput(planOutput()));
        assertThat(detail.response().getSourceBindings()).isNotEmpty();
        assertThat(detail.response().getSourceBindings()).anySatisfy(source -> assertThat(source.getResourceType()).isEqualTo("chapter"));
        assertThat(reviews.getDetail(fixture.userId(), fixture.artifactId(), 1, detail.etag()).notModified()).isTrue();
        var stored = json.readTree(database.dsl().fetchOne("SELECT \"payloadJson\", \"diffJson\" FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?", fixture.artifactId()).get("payloadJson", String.class));
        assertThat(stored.has("source")).isFalse();
        assertThat(stored.has("before")).isFalse();
        assertThat(stored.has("plan")).isTrue();
    }

    @Test
    void 章节计划显式返工绑定同Evidence完整计划和原始指令且丢弃保留审计() {
        Fixture revise = waitingArtifact("plan-revise", false, true);
        var request = decision("plan-revise-request-0001", ReviewArtifactDecisionRequest.DecisionEnum.REVISE).userMessage("让第二个场景更清晰");
        var response = reviews.decide(revise.userId(), revise.artifactId(), request);
        assertThat(reviews.decide(revise.userId(), revise.artifactId(), request)).isEqualTo(response);
        Record step = database.dsl().fetchOne("SELECT input, \"evidenceBundleId\", \"artifactId\", \"artifactRevision\" FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation' ORDER BY ordinal DESC LIMIT 1", revise.runId());
        assertThat(step.get("evidenceBundleId", String.class)).isEqualTo(revise.bundleId());
        assertThat(json.readTree(step.get("input", String.class)).path("previousArtifact").path("payload")).isEqualTo(json.valueToTree(planOutput()));
        assertThat(json.readTree(step.get("input", String.class)).path("targetWordCount").asInt()).isEqualTo(2500);
        assertThat(json.readTree(step.get("input", String.class)).path("originalUserInstruction").asText()).isEqualTo("规划完整章节");
        Fixture discard = waitingArtifact("plan-discard", false, true);
        reviews.decide(discard.userId(), discard.artifactId(), decision("plan-discard-request-0001", ReviewArtifactDecisionRequest.DecisionEnum.DISCARD));
        assertThat(count("SELECT count(*) FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ?", discard.artifactId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ? AND status = 'approved'", discard.chapterId())).isEqualTo(1);
        assertThat(chapterContent(discard.chapterId())).isEqualTo("甲😀乙");
    }

    @Test
    void 章节计划来源漂移旧修订与正文编辑字段均拒绝且无正式副作用() {
        Fixture fixture = waitingArtifact("plan-conflict", false, true);
        var approve = decision("plan-conflict-request-0001", ReviewArtifactDecisionRequest.DecisionEnum.APPROVE);
        assertThatThrownBy(() -> reviews.decide(fixture.userId(), fixture.artifactId(), approve.editedReplacement("绕过计划")))
                .isInstanceOf(ApiException.class).satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo("VALIDATION_ERROR"));
        approve.setEditedReplacement(org.openapitools.jackson.nullable.JsonNullable.undefined());
        approve.setExpectedRevision(2);
        assertThatThrownBy(() -> reviews.decide(fixture.userId(), fixture.artifactId(), approve)).isInstanceOf(ApiException.class);
        approve.setExpectedRevision(1);
        database.dsl().execute("UPDATE public.\"ChapterBeatPlan\" SET \"chapterGoal\" = '来源已变化但保留同timestamp' WHERE \"chapterId\" = ?", fixture.chapterId());
        assertThatThrownBy(() -> reviews.decide(fixture.userId(), fixture.artifactId(), approve))
                .isInstanceOf(ApiException.class).satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo("ARTIFACT_SOURCE_VERSION_CONFLICT"));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'", fixture.runId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ?", fixture.chapterId())).isEqualTo(1);
        assertThat(chapterContent(fixture.chapterId())).isEqualTo("甲😀乙");
    }

    private static Map<String, Object> planOutput() {
        Map<String, Object> firstScene = new LinkedHashMap<>(Map.of("order", 1, "goal", "面对冲突😀", "estimatedWords", 1000));
        firstScene.put("acceptanceCriteria", null);
        firstScene.put("conflict", null);
        firstScene.put("foreshadowingRefs", null);
        Map<String, Object> output = new LinkedHashMap<>(Map.of("title", "完整章节😀计划", "summary", "保留完整计划摘要",
                "chapterGoal", "围绕角色抉择推动章节", "totalEstimatedWords", 2500, "beatCount", 2,
                "sceneBeats", List.of(firstScene,
                        Map.of("order", 2, "goal", "作出抉择", "estimatedWords", 1500, "acceptanceCriteria", "明确付出代价"))));
        output.put("contentSha256", ExecutionCanonicalJson.sha256(output));
        return output;
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
        return waitingArtifact(prefix, reviewers, false);
    }

    private static Fixture waitingArtifact(String prefix, boolean reviewers, boolean beatPlan) {
        return waitingArtifact(prefix, reviewers, beatPlan, false);
    }

    private static Fixture waitingArtifact(String prefix, boolean reviewers, boolean beatPlan, boolean chapterDraft) {
        return waitingArtifact(prefix, reviewers, beatPlan, chapterDraft, false);
    }

    private static Fixture waitingArtifact(String prefix, boolean reviewers, boolean beatPlan, boolean chapterDraft, boolean failedReviewer) {
        return waitingArtifact(prefix, reviewers, beatPlan, chapterDraft, failedReviewer, false);
    }

    private static Fixture waitingArtifact(String prefix, boolean reviewers, boolean beatPlan, boolean chapterDraft, boolean failedReviewer, boolean natural) {
        return waitingArtifact(prefix, reviewers, beatPlan, chapterDraft, failedReviewer,
                natural, null, null);
    }

    private static Fixture waitingSceneArtifact(String prefix, boolean reviewers) {
        return waitingArtifact(
                prefix, reviewers, false, true, false, false,
                "rewrite_scene", null);
    }

    private static Fixture waitingOutlineArtifact(
            String prefix, String resourceType, boolean reviewers) {
        return waitingArtifact(
                prefix, reviewers, false, false, false, false,
                "rewrite_outline_selection", resourceType);
    }

    private static Fixture waitingArtifact(
            String prefix,
            boolean reviewers,
            boolean beatPlan,
            boolean chapterDraft,
            boolean failedReviewer,
            boolean natural,
            String requestedOperation,
            String outlineResourceType) {
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
        boolean outlineSelection = "rewrite_outline_selection".equals(requestedOperation);
        boolean sceneRewrite = "rewrite_scene".equals(requestedOperation);
        String outlineId = novelId + "-outline";
        String outlineNodeId = novelId + "-node";
        if (outlineSelection) {
            database.dsl().execute(
                    """
                    INSERT INTO public."Outline" (id, "novelId", content, "createdAt", "updatedAt")
                    VALUES (?, ?, '纲😀要', ?, ?)
                    """,
                    outlineId, novelId, NOW, NOW);
            database.dsl().execute(
                    """
                    INSERT INTO public."OutlineNode" (
                      id, "novelId", kind, title, "order", content, "createdAt", "updatedAt"
                    ) VALUES (?, ?, 'plot_unit', '转折节点', 1, '纲😀要', ?, ?)
                    """,
                    outlineNodeId, novelId, NOW, NOW);
        }
        String operationKey = requestedOperation != null
                ? "long_serial." + requestedOperation
                : chapterDraft
                        ? "long_serial.write_chapter"
                        : beatPlan
                                ? "long_serial.plan_chapter"
                                : "long_serial.rewrite_chapter_selection";
        ExecutionRegistry.ResolvedOperation operation = registry.resolve(
                operationKey, false);
        String selectedHash = ReviewArtifactRules.sha256("😀");
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("selectionStart", 1);
        input.put("selectionEnd", 2);
        input.put("selectedTextSha256", selectedHash);
        input.put("userInstruction", "改写这个表情");
        if (beatPlan || chapterDraft) {
            input.clear();
            input.put("userInstruction", chapterDraft
                    ? sceneRewrite ? "改写章节中的冲突场景" : "完整正文原始指令A"
                    : "规划完整章节");
            input.put("targetWordCount", 2500);
            database.dsl().execute("""
                    INSERT INTO public."ChapterBeatPlan" (id, "chapterId", status, "chapterGoal", "createdAt", "updatedAt")
                    VALUES (?, ?, 'approved', '旧正式计划', ?, ?)
                    """, prefix + "-previous-plan", chapterId, NOW, NOW);
            if (chapterDraft) database.dsl().execute("UPDATE public.\"Chapter\" SET status = 'completed', \"completedAt\" = ? WHERE id = ?", NOW, chapterId);
        }
        if (natural) input.put("userInstruction", new String(ExecutionCanonicalJson.bytes(Map.of(
                "initialInstruction", "原始未明确的请求", "clarifications", List.of(Map.of("prompt", "请明确要处理本章哪一层", "userMessage", chapterDraft ? "生成正文草案" : "规划本章")))), java.nio.charset.StandardCharsets.UTF_8));
        if (outlineSelection) {
            input.clear();
            String resourceId = "outline_content".equals(outlineResourceType)
                    ? outlineId
                    : outlineNodeId;
            input.put("userInstruction", "改写大纲转折");
            input.put("selectionTarget", Map.of(
                    "resourceType", outlineResourceType,
                    "resourceId", resourceId,
                    "baseUpdatedAt", DatabaseTimestamp.api(NOW).toString(),
                    "baseContentHash", ReviewArtifactRules.sha256("纲😀要"),
                    "selectionStart", 1,
                    "selectionEnd", 2,
                    "selectedTextHash", selectedHash));
        }
        String outlineResourceId = "outline_content".equals(outlineResourceType)
                ? outlineId
                : outlineNodeId;
        List<WorkflowEvidenceItemPlan> evidenceItems = outlineSelection
                ? List.of(new WorkflowEvidenceItemPlan(
                        outlineResourceType, outlineResourceId, true, null,
                        DatabaseTimestamp.api(NOW), "纲😀要", null, 1, 2,
                        Map.of(
                                "role", "selection_source",
                                "baseContentHash", ReviewArtifactRules.sha256("纲😀要"),
                                "selectedTextHash", selectedHash)))
                : chapterDraft
                ? List.of(new WorkflowEvidenceItemPlan("chapter_writing_context", chapterId, true, null,
                        DatabaseTimestamp.api(NOW), null,
                        new JooqChapterWritingEvidenceReader(json).capture(database.dsl(), novelId, chapterId, (String) input.get("userInstruction")).context(),
                        null, null, Map.of("role", "chapter_writing_context")))
                : beatPlan
                ? List.of(new WorkflowEvidenceItemPlan("chapter_plan_context", chapterId, true, null,
                        DatabaseTimestamp.api(NOW), null,
                        new JooqChapterPlanEvidenceReader(json).capture(database.dsl(), novelId, chapterId, (String) input.get("userInstruction")).context(),
                        null, null, Map.of("role", "chapter_plan_context")))
                : List.of(new WorkflowEvidenceItemPlan("chapter_content", chapterId, true, null,
                        DatabaseTimestamp.api(NOW), "甲😀乙", null, 1, 2, Map.of("role", "selection_source",
                        "baseContentHash", ReviewArtifactRules.sha256("甲😀乙"), "selectedTextHash", selectedHash)));
        var startPlan = new WorkflowStartPlan(
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
                outlineSelection ? outlineResourceType : chapterDraft || beatPlan ? "chapter" : "chapter_content",
                outlineSelection ? outlineResourceId : chapterId,
                input,
                operation.operation().evidencePolicy(),
                evidenceItems,
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
        var started = natural ? IntentSelectedRunTestFixture.start(database, new CuidV1Generator(CLOCK), CLOCK, json, registry, startPlan)
                : starts.start(startPlan);
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
        Map<String, Object> storedPayload = stored.payload();
        Map<String, Object> storedDiff = stored.diff();
        if (outlineSelection) {
            var outline = DurableOutlineSelectionArtifact.create(
                    bundleId,
                    evidenceItemId,
                    outlineResourceType,
                    outlineResourceId,
                    DatabaseTimestamp.api(NOW),
                    ReviewArtifactRules.sha256("纲😀要"),
                    1,
                    2,
                    selectedHash,
                    "模型改写",
                    ReviewArtifactRules.sha256("模型改写"),
                    ReviewArtifactRules.sha256("纲模型改写要"),
                    started.stepId(),
                    "a".repeat(64));
            storedPayload = outline.payload();
            storedDiff = outline.diff();
        }
        if (beatPlan) {
            String manifestHash = database.dsl().fetchOne("SELECT \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ?", bundleId).get(0, String.class);
            var plan = DurableBeatPlanArtifact.create(bundleId, manifestHash, chapterId, planOutput(), started.stepId(), "a".repeat(64));
            storedPayload = plan.payload();
            storedDiff = plan.diff();
        }
        if (chapterDraft) {
            String manifestHash = database.dsl().fetchOne("SELECT \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ?", bundleId).get(0, String.class);
            var draft = DurableChapterDraftArtifact.create(
                    sceneRewrite ? "rewrite_scene" : "write_chapter",
                    bundleId, manifestHash, chapterId,
                    DurableChapterDraftArtifact.deriveOutput("完整正文摘要", "完整模型正文😀"), started.stepId(), "a".repeat(64));
            storedPayload = draft.payload();
            storedDiff = draft.diff();
        }
        database.dsl().execute(
                """
                INSERT INTO public."ReviewArtifact" (
                  id, "novelId", "chapterId", "taskId", "workflowRunId", "artifactKey",
                  kind, status, title, "payloadJson", "diffJson", "createdByAgent",
                  "updatedByAgent", revision, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, NULL, ?, ?, CAST(? AS "ReviewArtifactKind"),
                  CAST('awaiting_user' AS "ReviewArtifactStatus"), '章节选区改写', ?, ?,
                  'writer.chapter_selection.v1', 'writer.chapter_selection.v1', 1, ?, ?)
                """,
                artifactId,
                novelId,
                chapterId,
                started.runId(),
                "workflow:" + started.runId() + ":candidate",
                beatPlan ? "beat_plan" : outlineSelection ? "outline_draft" : "chapter_draft",
                json.writeValueAsString(storedPayload),
                json.writeValueAsString(storedDiff),
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
                json.writeValueAsString(storedPayload),
                json.writeValueAsString(storedDiff),
                NOW);
        Map<String, Object> generationOutput = beatPlan
                ? planOutput()
                : chapterDraft
                        ? DurableChapterDraftArtifact.deriveOutput(
                                "完整正文摘要", "完整模型正文😀")
                        : Map.of(
                                "replacement", "模型改写",
                                "contentSha256", ReviewArtifactRules.sha256("模型改写"));
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('completed' AS "WorkflowStepStatus"), output = ?,
                    "resultHash" = ?, "artifactId" = ?, "artifactRevision" = 1,
                    "updatedAt" = ?, "completedAt" = ?
                WHERE id = ?
                """,
                json.writeValueAsString(generationOutput),
                "a".repeat(64),
                artifactId,
                NOW,
                NOW,
                started.stepId());
        if (reviewers) {
            var frozen = ExecutionPlanSnapshot.freeze(registry.catalogVersion(), registry.manifestFingerprint(), operation);
            for (int index = 0; index < frozen.reviewers().size(); index++) {
                insertEvaluation(prefix, started.runId(), bundleId, artifactId,
                        (natural ? 4 : 2) + index,
                        frozen.reviewers().get(index).stepBudget().stored(),
                        failedReviewer && index == 0);
            }
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
            int ordinal, Map<String, Object> budget, boolean failed) {
        String stepId = prefix + "-review-step-" + ordinal;
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, output, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "fencingToken", "idempotencyKey",
                  "requestHash", "inputHash", "resultHash", "evidenceBundleId", "artifactId",
                  "artifactRevision", "submittedAt", "updatedAt", "completedAt", "budgetJson", "errorCode"
                ) VALUES (?, ?, 'reviewer', CAST('agent' AS "WorkflowStepType"),
                  CAST(? AS "WorkflowStepStatus"), '{}', '{}', ?, ?, 'review',
                  'interactive', 1, 1, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                stepId,
                runId,
                failed ? "failed" : "completed",
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
                NOW,
                json.writeValueAsString(budget),
                failed ? "STEP_BUDGET_EXCEEDED" : null);
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowEvaluation" (
                  id, "runId", "stepId", "evidenceBundleId", "artifactId", "artifactRevision",
                  "evaluatorProfile", "rubricVersion", "executionStatus", "contentVerdict",
                  "findingsJson", "createdAt"
                ) VALUES (?, ?, ?, ?, ?, 1, ?, 'rubric.chapter_selection.review.v1',
                  ?, ?, '[]', ?)
                """,
                prefix + "-evaluation-" + ordinal,
                runId,
                stepId,
                bundleId,
                artifactId,
                "reviewer-" + ordinal,
                failed ? "failed" : "completed",
                failed ? "cannot_assess" : "pass",
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

    private static String outlineContent(Fixture fixture, String resourceType) {
        String table = "outline_content".equals(resourceType)
                ? "Outline"
                : "OutlineNode";
        String id = fixture.novelId()
                + ("outline_content".equals(resourceType) ? "-outline" : "-node");
        return database.dsl().fetchOne(
                        "SELECT content FROM public.\"" + table + "\" WHERE id = ?", id)
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
