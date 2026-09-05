package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ClarifyWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunResponse;
import cn.inkforge.contracts.api.WritingRunStartResponse;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.reviews.infrastructure.JooqChapterPlanEvidenceReader;
import cn.inkforge.core.reviews.infrastructure.JooqChapterWritingEvidenceReader;
import cn.inkforge.core.writing.application.DurableAgentExecutionReadiness;
import cn.inkforge.core.writing.application.LongSerialDurableRunStarter;
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.writing.application.WritingRunStartRequestParser;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.IntentExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowIntentSelection;
import cn.inkforge.core.workflows.domain.WorkflowIntentQuestion;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowExecutionContextReader;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.writing.domain.WritingRunCursor;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import cn.inkforge.core.writing.domain.WritingRunOutcomeProjector;
import jakarta.validation.Validation;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import org.jooq.Record;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class RoutingWritingRunStarterTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T03:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-09-01T03:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static WritingRunStartRequestParser parser;
    private static JooqWritingCommandRepository legacy;
    private static JooqLongSerialDurableRunStarter durable;
    private static ExecutionRegistry registry;

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
        json = JsonMapper.builder()
                .addModule(new JsonNullableJackson3Module())
                .build();
        parser = new WritingRunStartRequestParser(
                json, Validation.buildDefaultValidatorFactory().getValidator());
        CuidV1Generator ids = new CuidV1Generator(CLOCK);
        legacy = new JooqWritingCommandRepository(
                database,
                ids,
                CLOCK,
                json,
                new CommandIdempotencyStore(json, true));
        registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        DurableWorkflowService workflows = new DurableWorkflowService(
                new JooqWorkflowStartRepository(database, ids, CLOCK, json));
        durable = new JooqLongSerialDurableRunStarter(
                database,
                new LongSerialRunAssembler(json, new WritingSourceBindingCapture(json)),
                workflows,
                registry,
                ids,
                CLOCK,
                json,
                new JooqChapterPlanEvidenceReader(json),
                new JooqChapterWritingEvidenceReader(json), new JooqWorkflowExecutionContextReader(json));
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 自然启动只建同章意图Run并在路由关闭及离线时重放() {
        Fixture fixture = fixture("natural-start");
        var request = naturalRequest(fixture, "natural-start-request-001", "  请帮助当前章节😀\r\n");
        var response = (WritingRunV2Response) router(fixture, "allowlist").start(fixture.userId(), request);
        assertThat(response.getOperation()).isNull();
        assertThat(response.getCurrentStep().getPurpose()).isEqualTo("resolve_intent");
        assertThat(response.getCurrentStep().getModelProfile().getProfile()).isEqualTo("system.intent_resolver.v2");
        Record run = database.dsl().fetchOne("SELECT operation, \"targetType\", \"targetId\", \"modelPolicyJson\", input FROM public.\"WorkflowRun\" WHERE id = ?", response.getRunId());
        assertThat(run.get("operation")).isNull();
        assertThat(run.get("targetType", String.class)).isEqualTo("chapter");
        assertThat(run.get("targetId", String.class)).isEqualTo(fixture.chapterId());
        assertThat(json.readTree(run.get("modelPolicyJson", String.class)).path("planVersion").asText()).isEqualTo("2");
        assertThat(json.readTree(run.get("input", String.class)).path("userInstruction").asText()).isEqualTo("  请帮助当前章节😀\r\n");
        Record item = database.dsl().fetchOne("SELECT \"resourceType\", \"contentJson\" FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\" = (SELECT \"currentEvidenceBundleId\" FROM public.\"WorkflowRun\" WHERE id = ?)", response.getRunId());
        assertThat(item.get("resourceType", String.class)).isEqualTo("intent_context");
        var context = json.readTree(item.get("contentJson", String.class));
        assertThat(context.has("content")).isFalse();
        assertThat(context.path("availableOperations").size()).isEqualTo(5);
        assertThat(context.path("availableOperations").findValues("operation").stream()
                        .map(tools.jackson.databind.JsonNode::asText))
                .containsExactly("answer_question", "plan_chapter", "review_chapter", "rewrite_scene", "write_chapter");
        var queries = queries();
        assertThat(((WritingRunV2Response) queries.getPublic(fixture.userId(), response.getRunId())).getCurrentStep().getPurpose())
                .isEqualTo("resolve_intent");
        assertThat(queries.list(fixture.userId(), fixture.novelId(), null, null, null, null, null, 20).getItems())
                .hasSize(1).first().isInstanceOf(WritingRunV2Response.class);
        AtomicInteger probes = new AtomicInteger();
        var replay = (WritingRunV2Response) router(fixture, "off", () -> { probes.incrementAndGet(); return false; }).start(fixture.userId(), request);
        assertThat(replay.getRunId()).isEqualTo(response.getRunId());
        assertThat(probes).hasValue(0);
        assertThat(count("SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?", fixture.chapterId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?", fixture.chapterId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?", fixture.sessionId())).isEqualTo(1);
        assertThatThrownBy(() -> router("off").start(fixture.userId(), naturalRequest(fixture, "natural-start-request-001", "异内容")))
                .isInstanceOfSatisfying(ApiException.class, error -> assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 自然未授权请求明确拒绝且未解析Run仍阻塞同章写入() {
        Fixture off = fixture("natural-off");
        assertThatThrownBy(() -> router("off").start(off.userId(), naturalRequest(off, "natural-off-request-0001", "不得降级")))
                .isInstanceOfSatisfying(ApiException.class, error -> assertThat(error.code()).isEqualTo("DURABLE_NATURAL_ENTRY_NOT_ENABLED"));
        assertThat(workflowFacts(off.userId())).isZero();
        Fixture active = fixture("natural-lock");
        router(active, "allowlist").start(active.userId(), naturalRequest(active, "natural-lock-request-001", "尚未判断是否写"));
        assertThatThrownBy(() -> router(active, "allowlist").start(active.userId(), requestWithoutSession(active, "natural-lock-write-0001", "同章新写入")))
                .isInstanceOf(ApiException.class);
    }

    @Test
    void 整章审阅V2允许无会话并只冻结完整章节上下文() {
        Fixture fixture = fixture("review-chapter-v2");
        ParsedWritingRunStartRequest request = longSerialRequest(
                fixture, "review-chapter-request-001", "review_chapter", false);
        var response = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(), request);
        assertThat(response.getOperation()).isEqualTo("review_chapter");
        Record run = database.dsl().fetchOne("SELECT kind::text AS kind, \"writingSessionId\", \"targetType\", \"targetId\" FROM public.\"WorkflowRun\" WHERE id=?", response.getRunId());
        assertThat(run.get("kind", String.class)).isEqualTo("chat");
        assertThat(run.get("writingSessionId")).isNull();
        assertThat(run.get("targetType", String.class)).isEqualTo("chapter");
        assertThat(run.get("targetId", String.class)).isEqualTo(fixture.chapterId());
        Record step = database.dsl().fetchOne("SELECT input FROM public.\"WorkflowStep\" WHERE id=?", response.getCurrentStep().getStepId());
        assertThat(json.readTree(step.get("input", String.class)).properties().stream().map(Map.Entry::getKey).toList())
                .containsExactly("userInstruction");
        Record evidence = database.dsl().fetchOne("SELECT \"resourceType\", \"contentJson\" FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\"=(SELECT \"currentEvidenceBundleId\" FROM public.\"WorkflowRun\" WHERE id=?)", response.getRunId());
        assertThat(evidence.get("resourceType", String.class)).isEqualTo("chapter_writing_context");
        assertThat(json.readTree(evidence.get("contentJson", String.class)).path("currentChapter").path("content").asText())
                .isEqualTo(fixture.content());
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE metadata::jsonb->>'taskId'=?", response.getRunId())).isZero();

        String report = "  完整大报告😀\r\n第二段保留结尾  \n";
        completeReviewRun(response.getRunId(), response.getCurrentStep().getStepId(), report);
        assertThat(((WritingRunV2Response) queries().getPublic(fixture.userId(), response.getRunId()))
                        .getReviewReport())
                .isEqualTo(report);
        assertThat(queries().list(fixture.userId(), fixture.novelId(), null, null,
                        "review_chapter", "succeeded", null, 20).getItems())
                .singleElement()
                .satisfies(item -> assertThat(((WritingRunV2Response) item).getReviewReport())
                        .isNull());
        WritingRunV2Response replay = (WritingRunV2Response) router("off").start(
                fixture.userId(), request);
        assertThat(replay.getRunId()).isEqualTo(response.getRunId());
        assertThat(replay.getReviewReport()).isEqualTo(report);
    }

    @Test
    void 场景改写V2保留真实操作并生成完整整章输入而非选区() {
        Fixture fixture = fixture("rewrite-scene-v2");
        var response = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(), longSerialRequest(fixture, "rewrite-scene-request-001", "rewrite_scene", false));
        assertThat(response.getOperation()).isEqualTo("rewrite_scene");
        Record run = database.dsl().fetchOne("SELECT operation, \"targetType\", \"targetId\", input FROM public.\"WorkflowRun\" WHERE id=?", response.getRunId());
        assertThat(run.get("operation", String.class)).isEqualTo("rewrite_scene");
        assertThat(run.get("targetType", String.class)).isEqualTo("chapter");
        assertThat(json.readTree(run.get("input", String.class)).path("selectionTarget").isNull()).isTrue();
        Record step = database.dsl().fetchOne("SELECT input FROM public.\"WorkflowStep\" WHERE id=?", response.getCurrentStep().getStepId());
        assertThat(json.readTree(step.get("input", String.class)).properties().stream().map(Map.Entry::getKey).toList())
                .containsExactlyInAnyOrder("userInstruction", "targetWordCount");
        assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\"=(SELECT \"currentEvidenceBundleId\" FROM public.\"WorkflowRun\" WHERE id=?) AND \"resourceType\"='chapter_writing_context'", response.getRunId())).isEqualTo(1);
    }

    @Test
    void 整章审阅绑定会话时仅创建一次原始用户消息且幂等重放不重复() {
        Fixture fixture = fixture("review-chapter-session-v2");
        ParsedWritingRunStartRequest request = longSerialRequest(
                fixture, "review-chapter-session-request-001", "review_chapter", true);
        WritingRunV2Response first = (WritingRunV2Response) router(fixture, "allowlist")
                .start(fixture.userId(), request);
        WritingRunV2Response replay = (WritingRunV2Response) router("off")
                .start(fixture.userId(), request);

        assertThat(replay.getRunId()).isEqualTo(first.getRunId());
        assertThat(database.dsl().fetchOne(
                                "SELECT \"writingSessionId\" FROM public.\"WorkflowRun\" WHERE id = ?",
                                first.getRunId())
                        .get("writingSessionId", String.class))
                .isEqualTo(fixture.sessionId());
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE metadata::jsonb->>'taskId' = ?",
                        first.getRunId()))
                .isEqualTo(1);
    }

    @Test
    void 自然审阅的后续generation不依赖固定序号且GET与重放返回完整报告() {
        Fixture fixture = fixture("natural-review-report");
        ParsedWritingRunStartRequest request = naturalRequest(
                fixture, "natural-review-report-start-001", "  请判断并审阅当前章😀\r\n");
        WritingRunV2Response started = (WritingRunV2Response) router(fixture, "allowlist")
                .start(fixture.userId(), request);
        String report = "自然入口的完整审阅报告\r\n尾部空格  \n";
        completeNaturalReviewRun(
                started.getRunId(), started.getCurrentStep().getStepId(), report);

        Record run = database.dsl().fetchOne(
                "SELECT operation FROM public.\"WorkflowRun\" WHERE id = ?", started.getRunId());
        assertThat(run.get("operation")).isNull();
        WritingRunV2Response queried = (WritingRunV2Response) queries()
                .getPublic(fixture.userId(), started.getRunId());
        assertThat(queried.getOperation()).isEqualTo("review_chapter");
        assertThat(queried.getReviewReport()).isEqualTo(report);
        WritingRunV2Response replay = (WritingRunV2Response) router("off")
                .start(fixture.userId(), request);
        assertThat(replay.getRunId()).isEqualTo(started.getRunId());
        assertThat(replay.getReviewReport()).isEqualTo(report);
    }

    @Test
    void 大纲选区V2以真实总纲来源作为Run目标并冻结完整正文() {
        Fixture fixture = fixture("rewrite-outline-selection-v2");
        var response = (WritingRunV2Response) router(fixture, "allowlist").start(fixture.userId(),
                longSerialRequest(fixture, "rewrite-outline-request-001", "rewrite_outline_selection", true));
        assertThat(response.getOperation()).isEqualTo("rewrite_outline_selection");
        Record run = database.dsl().fetchOne("SELECT \"targetType\", \"targetId\" FROM public.\"WorkflowRun\" WHERE id=?", response.getRunId());
        assertThat(run.get("targetType", String.class)).isEqualTo("outline_content");
        assertThat(run.get("targetId", String.class)).isEqualTo(fixture.outlineId());
        Record step = database.dsl().fetchOne("SELECT input FROM public.\"WorkflowStep\" WHERE id=?", response.getCurrentStep().getStepId());
        var input = json.readTree(step.get("input", String.class));
        assertThat(input.properties().stream().map(Map.Entry::getKey).toList())
                .containsExactlyInAnyOrder("userInstruction", "selectionTarget");
        assertThat(input.path("selectionTarget").has("selectedText")).isFalse();
        Record evidence = database.dsl().fetchOne("SELECT \"resourceType\", \"resourceId\", \"contentText\", \"rangeJson\" FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\"=(SELECT \"currentEvidenceBundleId\" FROM public.\"WorkflowRun\" WHERE id=?)", response.getRunId());
        assertThat(evidence.get("resourceType", String.class)).isEqualTo("outline_content");
        assertThat(evidence.get("resourceId", String.class)).isEqualTo(fixture.outlineId());
        assertThat(evidence.get("contentText", String.class)).isEqualTo(fixture.outlineContent());
        assertThat(evidence.get("rangeJson", String.class)).isNotNull();
    }

    @Test
    void 大纲节点选区V2冻结节点身份完整正文与严格输入() {
        Fixture fixture = fixture("rewrite-outline-node-v2");
        String nodeId = fixture.novelId() + "-outline-node";
        String nodeContent = "节点甲😀乙丙";
        insertOutlineNode(fixture, nodeId, nodeContent);
        var response = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(),
                outlineSelectionRequest(
                        fixture,
                        "rewrite-outline-node-request-001",
                        fixture.chapterId(),
                        fixture.sessionId(),
                        "outline_node_content",
                        nodeId,
                        nodeContent));

        Record run = database.dsl().fetchOne(
                "SELECT \"targetType\", \"targetId\", input FROM public.\"WorkflowRun\" WHERE id = ?",
                response.getRunId());
        assertThat(run.get("targetType", String.class)).isEqualTo("outline_node_content");
        assertThat(run.get("targetId", String.class)).isEqualTo(nodeId);
        assertThat(json.readTree(run.get("input", String.class)).path("selectionTarget")
                        .path("resourceId").asText())
                .isEqualTo(nodeId);
        Record step = database.dsl().fetchOne(
                "SELECT input FROM public.\"WorkflowStep\" WHERE id = ?",
                response.getCurrentStep().getStepId());
        var input = json.readTree(step.get("input", String.class));
        assertThat(input.properties().stream().map(Map.Entry::getKey).toList())
                .containsExactlyInAnyOrder("userInstruction", "selectionTarget");
        assertThat(input.path("selectionTarget").has("selectedText")).isFalse();
        Record evidence = database.dsl().fetchOne(
                """
                SELECT "resourceType", "resourceId", "contentText", "metadataJson"
                FROM public."WorkflowEvidenceItem"
                WHERE "bundleId" = (
                  SELECT "currentEvidenceBundleId" FROM public."WorkflowRun" WHERE id = ?
                )
                """,
                response.getRunId());
        assertThat(evidence.get("resourceType", String.class)).isEqualTo("outline_node_content");
        assertThat(evidence.get("resourceId", String.class)).isEqualTo(nodeId);
        assertThat(evidence.get("contentText", String.class)).isEqualTo(nodeContent);
        assertThat(json.readTree(evidence.get("metadataJson", String.class)))
                .isEqualTo(json.valueToTree(Map.of(
                        "role", "selection_source",
                        "baseContentHash", sha256(nodeContent),
                        "selectedTextHash", sha256(codePointSlice(nodeContent, 1, 3)))));
    }

    @Test
    void 不同章节锚点改写同一大纲来源仍按真实资源互斥() {
        Fixture fixture = fixture("rewrite-outline-source-lock");
        String secondChapterId = fixture.novelId() + "-chapter-2";
        String secondSessionId = fixture.novelId() + "-session-2";
        insertChapterAndSession(fixture, secondChapterId, secondSessionId);
        router(fixture, "allowlist").start(
                fixture.userId(),
                outlineSelectionRequest(
                        fixture,
                        "rewrite-outline-source-first-001",
                        fixture.chapterId(),
                        fixture.sessionId(),
                        "outline_content",
                        fixture.outlineId(),
                        fixture.outlineContent()));

        assertThatThrownBy(() -> router(fixture, "allowlist").start(
                        fixture.userId(),
                        outlineSelectionRequest(
                                fixture,
                                "rewrite-outline-source-second-001",
                                secondChapterId,
                                secondSessionId,
                                "outline_content",
                                fixture.outlineId(),
                                fixture.outlineContent())))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY"));
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"novelId\" = ?",
                        fixture.novelId()))
                .isEqualTo(1);
    }

    private static ParsedWritingRunStartRequest naturalRequest(Fixture fixture, String id, String instruction) {
        return parser.parse(new WritingRunStartBody(json.valueToTree(Map.of("inputMode", "natural", "workflow", "long_serial",
                "clientRequestId", id, "novelId", fixture.novelId(), "chapterId", fixture.chapterId(),
                "writingSessionId", fixture.sessionId(), "userInstruction", instruction))));
    }

    @Test
    void 澄清回答同Run冻结完整历史和原回执且全局幂等不漂移() {
        Fixture fixture = fixture("natural-answer");
        String original = "  原始指令😀\r\n";
        var first = (WritingRunV2Response) router(fixture, "allowlist").start(fixture.userId(),
                naturalRequest(fixture, "natural-answer-start-001", original));
        String questionId = question(first.getRunId(), "  要规划还是写正文？\r\n");
        var waiting = (WritingRunV2Response) queries().getPublic(fixture.userId(), first.getRunId());
        assertThat(waiting.getClarification().getDecisionStepId()).isEqualTo(questionId);
        var answer = new ClarifyWritingRunRequest().clientRequestId("natural-answer-accepted-001")
                .expectedRevision(waiting.getRevision()).decisionStepId(questionId).userMessage("  请写完整正文😀\r\n".repeat(2000));
        var receipt = clarificationStore().accept(fixture.userId(), first.getRunId(), answer);
        assertThat(receipt.getRunId()).isEqualTo(first.getRunId());
        assertThat(receipt.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.PENDING);
        assertThat(receipt.getRevision()).isEqualTo(waiting.getRevision() + 1);
        assertThat(receipt.getClarification()).isNull();
        Record resolver = database.dsl().fetchOne("SELECT input, \"evidenceBundleId\" FROM public.\"WorkflowStep\" WHERE id = ?", receipt.getCurrentStep().getStepId());
        var input = json.readTree(resolver.get("input", String.class));
        assertThat(input.path("userInstruction").asText()).isEqualTo(original);
        assertThat(input.path("clarifications").get(0).path("prompt").asText()).isEqualTo("  要规划还是写正文？\r\n");
        assertThat(input.path("clarifications").get(0).path("userMessage").asText()).isEqualTo(answer.getUserMessage());
        Record control = database.dsl().fetchOne("SELECT id, input, output, \"inputHash\", \"resultHash\", \"fencingToken\", \"modelProfile\", \"budgetJson\", \"usageJson\" FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'intent_clarification_answer'", first.getRunId());
        assertThat(control.get("fencingToken", Long.class)).isEqualTo(1);
        assertThat(control.get("modelProfile")).isNull();
        assertThat(control.get("budgetJson")).isNull();
        assertThat(control.get("usageJson")).isNull();
        assertThat(control.get("resultHash", String.class)).isEqualTo(ExecutionCanonicalJson.sha256(json.readValue(control.get("output", String.class), Map.class)));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowBillingReservation\" WHERE \"stepId\" = ?", control.get("id", String.class))).isZero();
        String second = question(first.getRunId(), "请再明确一次");
        assertThat(clarificationStore().accept(fixture.userId(), first.getRunId(), answer)).isEqualTo(receipt);
        assertThat(((WritingRunV2Response) queries().getPublic(fixture.userId(), first.getRunId())).getClarification().getDecisionStepId()).isEqualTo(second);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?", fixture.chapterId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?", fixture.sessionId())).isEqualTo(2);
        assertThatThrownBy(() -> router("off").start(fixture.userId(), naturalRequest(fixture, answer.getClientRequestId(), "新请求不可复用回答ID")))
                .isInstanceOfSatisfying(ApiException.class, error -> assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 澄清回答越权过期取消及跨start幂等冲突均不追加事实() {
        Fixture fixture = fixture("natural-answer-reject");
        var first = (WritingRunV2Response) router(fixture, "allowlist").start(fixture.userId(),
                naturalRequest(fixture, "natural-reject-start-001", "待澄清"));
        String decision = question(first.getRunId(), "明确意图");
        int revision = ((WritingRunV2Response) queries().getPublic(fixture.userId(), first.getRunId())).getRevision();
        var answer = new ClarifyWritingRunRequest().clientRequestId("natural-answer-reject-001")
                .expectedRevision(revision).decisionStepId(decision).userMessage("写正文");
        int before = count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", first.getRunId());
        assertThatThrownBy(() -> clarificationStore().accept("other-user", first.getRunId(), answer)).isInstanceOf(ApiException.class);
        answer.expectedRevision(revision - 1);
        assertThatThrownBy(() -> clarificationStore().accept(fixture.userId(), first.getRunId(), answer)).isInstanceOf(ApiException.class);
        answer.expectedRevision(revision).clientRequestId("natural-reject-start-001");
        assertThatThrownBy(() -> clarificationStore().accept(fixture.userId(), first.getRunId(), answer))
                .isInstanceOfSatisfying(ApiException.class, error -> assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
        answer.clientRequestId("natural-answer-reject-001");
        database.dsl().execute("UPDATE public.\"WorkflowRun\" SET status='cancelled', \"cancelRequestId\"='natural-cancel-request-001', \"cancelRequestedAt\"=?, \"completedAt\"=?, \"updatedAt\"=? WHERE id=?", NOW, NOW, NOW, first.getRunId());
        assertThatThrownBy(() -> clarificationStore().accept(fixture.userId(), first.getRunId(), answer)).isInstanceOf(ApiException.class);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", first.getRunId())).isEqualTo(before);
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?", fixture.sessionId())).isEqualTo(1);
    }

    private static JooqWritingRunQueryRepository queries() {
        return new JooqWritingRunQueryRepository(database, new WritingRunStatusProjector(json, new WritingRunOutcomeProjector(), CLOCK),
                new WritingRunCursor(json), json, true, new JooqWorkflowExecutionContextReader(json));
    }

    @Test
    void 新启动互斥不等待持有Run锁的同Run业务准备() throws Exception {
        Fixture fixture = fixture("natural-lock-order");
        var started = (WritingRunV2Response) router(fixture, "allowlist").start(fixture.userId(),
                naturalRequest(fixture, "natural-lock-order-start-001", "待解析"));
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CompletableFuture<Void> preparing = CompletableFuture.runAsync(() -> database.transactionResult(transaction -> {
            transaction.fetchOne("SELECT id FROM public.\"WorkflowRun\" WHERE id=? FOR UPDATE", started.getRunId());
            locked.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) throw new IllegalStateException("未及时释放测试 Run 锁");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(error);
            }
            transaction.fetchOne("SELECT id FROM public.\"Novel\" WHERE id=? FOR UPDATE", fixture.novelId());
            return null;
        }));
        assertThat(locked.await(2, TimeUnit.SECONDS)).isTrue();
        CompletableFuture<Object> competing = CompletableFuture.supplyAsync(() -> captureFailure(() ->
                router(fixture, "allowlist").start(fixture.userId(), requestWithoutSession(fixture, "natural-lock-order-other-001", "竞争写入"))));
        try {
            assertThat(competing.get(2, TimeUnit.SECONDS)).isInstanceOf(ApiException.class);
        } finally {
            release.countDown();
        }
        preparing.get(3, TimeUnit.SECONDS);
    }

    @Test
    void 澄清回答并发只受理一次且两轮历史完整并拒绝旧决定() throws Exception {
        Fixture fixture = fixture("natural-answer-race");
        var started = (WritingRunV2Response) router(fixture, "allowlist").start(fixture.userId(),
                naturalRequest(fixture, "natural-answer-race-start-001", "原始指令"));
        String questionId = question(started.getRunId(), "第一问");
        int revision = ((WritingRunV2Response) queries().getPublic(fixture.userId(), started.getRunId())).getRevision();
        var answer = new ClarifyWritingRunRequest().clientRequestId("natural-answer-race-001")
                .expectedRevision(revision).decisionStepId(questionId).userMessage("第一答");
        CompletableFuture<WritingRunV2Response> first = CompletableFuture.supplyAsync(() -> clarificationStore().accept(fixture.userId(), started.getRunId(), answer));
        CompletableFuture<WritingRunV2Response> duplicate = CompletableFuture.supplyAsync(() -> clarificationStore().accept(fixture.userId(), started.getRunId(), answer));
        assertThat(first.get(5, TimeUnit.SECONDS)).isEqualTo(duplicate.get(5, TimeUnit.SECONDS));
        String secondQuestion = question(started.getRunId(), "第二问\r\n");
        int secondRevision = ((WritingRunV2Response) queries().getPublic(fixture.userId(), started.getRunId())).getRevision();
        var second = new ClarifyWritingRunRequest().clientRequestId("natural-answer-race-002")
                .expectedRevision(secondRevision).decisionStepId(secondQuestion).userMessage("第二答😀");
        var receipt = clarificationStore().accept(fixture.userId(), started.getRunId(), second);
        String inputJson = database.dsl().fetchOne("SELECT input FROM public.\"WorkflowStep\" WHERE id=?", receipt.getCurrentStep().getStepId()).get("input", String.class);
        assertThat(json.readTree(inputJson).path("clarifications").size()).isEqualTo(2);
        var third = new ClarifyWritingRunRequest().clientRequestId("natural-answer-race-003")
                .expectedRevision(receipt.getRevision()).decisionStepId(secondQuestion).userMessage("不得复用已答决定");
        assertThatThrownBy(() -> clarificationStore().accept(fixture.userId(), started.getRunId(), third)).isInstanceOf(ApiException.class);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\"=? AND purpose='intent_clarification_answer'", started.getRunId())).isEqualTo(2);
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\"=?", fixture.sessionId())).isEqualTo(3);
    }

    private static JooqWritingRunClarificationStore clarificationStore() {
        return new JooqWritingRunClarificationStore(database, new CuidV1Generator(CLOCK), CLOCK, json,
                new CommandIdempotencyStore(json, true), new JooqWorkflowExecutionContextReader(json), queries());
    }

    private static String question(String runId, String prompt) {
        Record resolver = database.dsl().fetchOne("SELECT id, \"evidenceBundleId\", ordinal FROM public.\"WorkflowStep\" WHERE \"runId\"=? AND purpose='resolve_intent' AND status='pending'", runId);
        database.dsl().execute("UPDATE public.\"WorkflowStep\" SET status='completed', \"resultHash\"=?, \"completedAt\"=?, \"nextAttemptAt\"=NULL WHERE id=?", "a".repeat(64), NOW, resolver.get("id", String.class));
        String id = new CuidV1Generator(CLOCK).next();
        var value = new WorkflowIntentQuestion(runId, resolver.get("id", String.class), "a".repeat(64), resolver.get("evidenceBundleId", String.class), "intent_ambiguous", prompt);
        database.dsl().execute("""
                INSERT INTO public."WorkflowStep" (id,"runId","stepType",status,input,"createdAt",ordinal,purpose,lane,
                  "attemptCount","fencingToken","idempotencyKey","requestHash","inputHash","evidenceBundleId","submittedAt","updatedAt","completedAt")
                VALUES (?,?,'user_confirmation','completed',?,?,?,'intent_clarification','control',0,1,?,?,?,?,?,?,?)
                """, id, runId, json.writeValueAsString(value.stored()), NOW, resolver.get("ordinal", Integer.class)+1,
                runId+"."+id, value.inputHash(), value.inputHash(), value.intentEvidenceBundleId(), NOW, NOW, NOW);
        database.dsl().execute("UPDATE public.\"WorkflowRun\" SET status='waiting_user', revision=revision+1 WHERE id=?", runId);
        return id;
    }

    @Test
    void V2路由冻结完整来源且开关关闭后仍幂等重放原引擎() {
        Fixture fixture = fixture("route-v2");
        RoutingWritingRunStarter all = router(fixture, "allowlist");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-route-v2-0001", "请让这句话更有压迫感");
        LocalDateTime sessionUpdatedBefore = sessionUpdatedAt(fixture.sessionId());

        var first = all.start(fixture.userId(), request);
        LocalDateTime sessionUpdatedAfterFirst = sessionUpdatedAt(fixture.sessionId());
        var refreshedAfterFirst = new JooqWritingSessionRepository(
                        database, new CuidV1Generator(CLOCK), CLOCK, json)
                .get(fixture.userId(), fixture.sessionId());
        var replayAfterRouteOff = router("off").start(fixture.userId(), request);
        LocalDateTime sessionUpdatedAfterReplay = sessionUpdatedAt(fixture.sessionId());
        var refreshedAfterReplay = new JooqWritingSessionRepository(
                        database, new CuidV1Generator(CLOCK), CLOCK, json)
                .get(fixture.userId(), fixture.sessionId());

        assertThat(first).isInstanceOf(WritingRunV2Response.class);
        WritingRunV2Response response = (WritingRunV2Response) first;
        assertThat(response.getEngineVersion()).isEqualTo(2);
        assertThat(response.getRunId()).isEqualTo(response.getTaskId());
        assertThat(response.getOperation()).isEqualTo("rewrite_chapter_selection");
        assertThat(response.getActiveSteps()).hasSize(1);
        assertThat(response.getCurrentStep()).isEqualTo(response.getActiveSteps().getFirst());
        assertThat(response.getCurrentStep().getPurpose()).isEqualTo("generation");
        assertThat(response.getCurrentStep().getModelProfile().getProfile())
                .isEqualTo("writer.chapter_selection.v1");
        assertThat(response.getCurrentStep().getResolvedModel()).isNull();
        assertThat(((WritingRunV2Response) replayAfterRouteOff).getRunId())
                .isEqualTo(response.getRunId());
        assertThat(((WritingRunV2Response) replayAfterRouteOff).getActiveSteps())
                .containsExactlyElementsOf(response.getActiveSteps());
        assertThat(((WritingRunV2Response) replayAfterRouteOff).getCurrentStep())
                .isEqualTo(response.getActiveSteps().getFirst());
        assertThat(sessionUpdatedAfterFirst).isAfter(sessionUpdatedBefore);
        assertThat(sessionUpdatedAfterReplay).isEqualTo(sessionUpdatedAfterFirst);
        assertThat(refreshedAfterFirst.getMessages())
                .singleElement()
                .satisfies(message -> {
                    assertThat(message.getRole()).isEqualTo("user");
                    assertThat(message.getContent()).isEqualTo("请让这句话更有压迫感");
                    @SuppressWarnings("unchecked")
                    Map<String, Object> metadata =
                            (Map<String, Object>) message.getMetadata().get();
                    assertThat(metadata)
                            .containsEntry("taskId", response.getRunId())
                            .containsEntry("eventType", "user");
                    Map<?, ?> source = (Map<?, ?>) metadata.get("source");
                    assertThat(source.get("engineVersion")).isEqualTo(2);
                    assertThat(source.get("runId")).isEqualTo(response.getRunId());
                    assertThat(source.get("operation"))
                            .isEqualTo("rewrite_chapter_selection");
                    assertThat(source.get("sourceLabel")).isEqualTo("章节正文");
                });
        assertThat(refreshedAfterReplay.getMessages()).hasSize(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?", fixture.userId()))
                .isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?", fixture.novelId()))
                .isZero();
        String purpose = database.dsl().fetchOne(
                        "SELECT purpose FROM public.\"WorkflowStep\" WHERE \"runId\" = ?",
                        response.getRunId())
                .get("purpose", String.class);
        assertThat(purpose).isEqualTo("generation");
        String evidence = database.dsl().fetchOne(
                        """
                        SELECT item."contentText"
                        FROM public."WorkflowEvidenceItem" AS item
                        JOIN public."WorkflowEvidenceBundle" AS bundle
                          ON bundle.id = item."bundleId"
                        WHERE bundle."runId" = ?
                        """,
                        response.getRunId())
                .get("contentText", String.class);
        assertThat(evidence).isEqualTo(fixture.content());

        ParsedWritingRunStartRequest changed = request(
                fixture, "request-route-v2-0001", "改成完全不同的要求");
        assertThatThrownBy(() -> all.start(fixture.userId(), changed))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 只读问答按Catalog路由V2并冻结唯一章节证据且重放不重复消息() {
        Fixture fixture = fixture("route-v2-answer");
        ParsedWritingRunStartRequest request = longSerialRequest(
                fixture,
                "request-route-v2-answer-01",
                "answer_question",
                true);

        WritingRunV2Response first = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(), request);
        AtomicInteger replayProbes = new AtomicInteger();
        WritingRunV2Response replay = (WritingRunV2Response) router(
                        fixture,
                        "allowlist",
                        () -> {
                            replayProbes.incrementAndGet();
                            return false;
                        })
                .start(fixture.userId(), request);

        assertThat(first.getOperation()).isEqualTo("answer_question");
        assertThat(first.getStatus()).isEqualTo(WritingRunV2Response.StatusEnum.PENDING);
        assertThat(first.getCurrentStep().getLane().getValue()).isEqualTo("interactive");
        assertThat(first.getCurrentStep().getModelProfile().getProfile())
                .isEqualTo("editor.answer.v1");
        assertThat(replay.getRunId()).isEqualTo(first.getRunId());
        assertThat(replayProbes).hasValue(0);
        Record facts = database.dsl().fetchOne(
                """
                SELECT run.kind::text AS kind,
                       bundle."policyVersion" AS policy,
                       item."resourceType" AS resource_type,
                       item."contentText" AS content_text,
                       item."rangeJson" AS range_json,
                       step.input::text AS step_input
                FROM public."WorkflowRun" AS run
                JOIN public."WorkflowEvidenceBundle" AS bundle ON bundle."runId" = run.id
                JOIN public."WorkflowEvidenceItem" AS item ON item."bundleId" = bundle.id
                JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                WHERE run.id = ?
                """,
                first.getRunId());
        assertThat(facts.get("kind", String.class)).isEqualTo("chat");
        assertThat(facts.get("policy", String.class))
                .isEqualTo("evidence.long_serial.answer.v1");
        assertThat(facts.get("resource_type", String.class)).isEqualTo("chapter_content");
        assertThat(facts.get("content_text", String.class)).isEqualTo(fixture.content());
        assertThat(facts.get("range_json", String.class)).isNull();
        assertThat(json.readTree(facts.get("step_input", String.class)))
                .isEqualTo(json.valueToTree(Map.of(
                        "userInstruction", "请执行 answer_question")));
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ? AND role = 'user'",
                        fixture.sessionId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\" = ?",
                        first.getRunId()))
                .isZero();
    }

    @Test
    void 只读问答缺少会话时在创建Run前稳定拒绝() {
        Fixture fixture = fixture("route-v2-answer-no-session");
        ParsedWritingRunStartRequest request = longSerialRequest(
                fixture,
                "request-route-v2-answer-no-session-01",
                "answer_question",
                false);
        AtomicInteger probes = new AtomicInteger();

        assertThatThrownBy(() -> router(
                                fixture,
                                "allowlist",
                                () -> {
                                    probes.incrementAndGet();
                                    return false;
                                })
                        .start(fixture.userId(), request))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("WRITING_SESSION_REQUIRED");
                });
        assertThat(probes).hasValue(0);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?",
                        fixture.userId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?",
                        fixture.sessionId()))
                .isZero();
    }

    @Test
    void 章节规划V2只创建Run并冻结最小上下文及缺失来源且幂等不重读() {
        Fixture fixture = fixture("route-v2-plan");
        ParsedWritingRunStartRequest request = longSerialRequest(
                fixture, "request-route-v2-plan-01", "plan_chapter", true);
        assertThat(durable.supportedOperationKeys()).contains("long_serial.plan_chapter");

        WritingRunV2Response first = (WritingRunV2Response) router(fixture, "allowlist")
                .start(fixture.userId(), request);
        Record facts = database.dsl().fetchOne(
                """
                SELECT run.kind::text AS kind, item."contentJson" AS context,
                       item."contentText" AS content_text, item."resourceType" AS resource_type,
                       item."metadataJson" AS metadata, step.input::text AS step_input
                FROM public."WorkflowRun" AS run
                JOIN public."WorkflowEvidenceBundle" AS bundle ON bundle."runId" = run.id
                JOIN public."WorkflowEvidenceItem" AS item ON item."bundleId" = bundle.id
                JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                WHERE run.id = ?
                """, first.getRunId());
        assertThat(first.getOperation()).isEqualTo("plan_chapter");
        assertThat(first.getCurrentStep().getModelProfile().getProfile())
                .isEqualTo("plot.chapter_plan.v1");
        assertThat(facts.get("kind", String.class)).isEqualTo("beat_plan");
        assertThat(facts.get("resource_type", String.class)).isEqualTo("chapter_plan_context");
        assertThat(facts.get("content_text", String.class)).isNull();
        var context = json.readTree(facts.get("context", String.class));
        assertThat(context.at("/chapter/id").textValue()).isEqualTo(fixture.chapterId());
        assertThat(context.at("/outline/content").textValue()).isEqualTo(fixture.outlineContent());
        assertThat(context.path("chapterGoal").isNull()).isTrue();
        assertThat(context.path("approvedBeatPlan").isNull()).isTrue();
        assertThat(context.path("outlinePath").isEmpty()).isTrue();
        assertThat(context.path("sourceBindings").findValues("resourceType"))
                .extracting(tools.jackson.databind.JsonNode::textValue)
                .contains("chapter", "chapter_goal", "approved_beat_plan", "chapter_group");
        assertThat(context.path("sourceBindings").findValues("exists"))
                .anySatisfy(value -> assertThat(value.booleanValue()).isFalse());
        assertThat(context.has("workspace")).isFalse();
        assertThat(json.readTree(facts.get("step_input", String.class)))
                .isEqualTo(json.valueToTree(Map.of(
                        "userInstruction", "请执行 plan_chapter", "targetWordCount", 1000)));
        assertThat(json.readTree(facts.get("metadata", String.class)).path("role").textValue())
                .isEqualTo("chapter_plan_context");
        database.dsl().execute("UPDATE public.\"Outline\" SET content = '后来修改' WHERE id = ?",
                fixture.outlineId());
        WritingRunV2Response replay = (WritingRunV2Response) router("off")
                .start(fixture.userId(), request);
        assertThat(replay.getRunId()).isEqualTo(first.getRunId());
        assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", first.getRunId()))
                .isEqualTo(1);
        assertThat(database.dsl().fetchOne("""
                SELECT item."contentJson" FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId"
                WHERE bundle."runId" = ?
                """, first.getRunId()).get("contentJson", String.class)).isEqualTo(facts.get("context", String.class));
        assertThat(count("SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?", fixture.novelId()))
                .isZero();
        assertThat(count("SELECT count(*) FROM public.\"WritingRunCommand\" WHERE \"taskId\" IN (SELECT id FROM public.\"WritingTask\" WHERE \"novelId\" = ?)", fixture.novelId()))
                .isZero();
        assertThat(count("SELECT count(*) FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ?", fixture.chapterId()))
                .isZero();
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?", fixture.sessionId()))
                .isEqualTo(1);
    }

    @Test
    void 正文写作V2冻结完整上下文但生成输入只保留指令字数且幂等不重读() {
        Fixture fixture = fixture("route-v2-chapter-writing");
        ParsedWritingRunStartRequest request = longSerialRequest(
                fixture, "request-route-v2-writing-01", "write_chapter", true);
        assertThat(durable.supportedOperationKeys()).contains("long_serial.write_chapter");
        WritingRunV2Response first = (WritingRunV2Response) router(fixture, "allowlist").start(fixture.userId(), request);
        Record facts = database.dsl().fetchOne("""
                SELECT run.kind::text AS kind, item."contentJson" AS context,
                       item."contentText" AS content_text, item."resourceType" AS resource_type,
                       item."metadataJson" AS metadata, step.input::text AS step_input,
                       item."rangeJson" AS range_json
                FROM public."WorkflowRun" run
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle."runId" = run.id
                JOIN public."WorkflowEvidenceItem" item ON item."bundleId" = bundle.id
                JOIN public."WorkflowStep" step ON step."runId" = run.id
                WHERE run.id = ?
                """, first.getRunId());
        assertThat(first.getOperation()).isEqualTo("write_chapter");
        assertThat(first.getCurrentStep().getModelProfile().getProfile()).isEqualTo("writer.chapter_draft.v1");
        assertThat(facts.get("kind", String.class)).isEqualTo("chapter_generation");
        assertThat(facts.get("resource_type", String.class)).isEqualTo("chapter_writing_context");
        assertThat(facts.get("content_text")).isNull();
        assertThat(facts.get("range_json")).isNull();
        var context = json.readTree(facts.get("context", String.class));
        assertThat(context.at("/currentChapter/id").textValue()).isEqualTo(fixture.chapterId());
        assertThat(context.at("/currentChapter/content").textValue()).isEqualTo(fixture.content());
        assertThat(context.path("sourceBindings").findValues("resourceType"))
                .extracting(tools.jackson.databind.JsonNode::textValue)
                .contains("chapter_content", "novel_context", "writing_style", "previous_chapter", "next_chapter");
        assertThat(json.readTree(facts.get("step_input", String.class))).isEqualTo(json.valueToTree(Map.of(
                "userInstruction", "请执行 write_chapter", "targetWordCount", 1000)));
        assertThat(json.readTree(facts.get("metadata", String.class)).path("role").textValue()).isEqualTo("chapter_writing_context");
        assertThat(context.has("workspace")).isFalse();
        assertThat(context.has("userInstruction")).isFalse();
        database.dsl().execute("UPDATE public.\"Chapter\" SET content = '后来修改完整正文' WHERE id = ?", fixture.chapterId());
        WritingRunV2Response replay = (WritingRunV2Response) router("off").start(fixture.userId(), request);
        assertThat(replay.getRunId()).isEqualTo(first.getRunId());
        assertThat(database.dsl().fetchOne("""
                SELECT item."contentJson" FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId" WHERE bundle."runId" = ?
                """, first.getRunId()).get("contentJson", String.class)).isEqualTo(facts.get("context", String.class));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", first.getRunId())).isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?", fixture.novelId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"WritingRunCommand\" WHERE \"taskId\" IN (SELECT id FROM public.\"WritingTask\" WHERE \"novelId\" = ?)", fixture.novelId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"ReviewArtifact\" WHERE \"novelId\" = ?", fixture.novelId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"ChapterBeatPlan\" WHERE \"chapterId\" = ?", fixture.chapterId())).isZero();
    }

    @Test
    void 章节规划V2章节组映射冲突时不留下任何耐久执行事实() {
        Fixture fixture = fixture("route-v2-plan-ambiguous");
        for (int index = 0; index < 2; index++) {
            database.dsl().execute(
                    """
                    INSERT INTO public."OutlineNode" (
                      id, "novelId", kind, title, "order", "chapterStartOrder", "chapterEndOrder", "createdAt", "updatedAt"
                    ) VALUES (?, ?, 'chapter_group', '冲突章节组', ?, 1, 2, ?, ?)
                    """, fixture.novelId() + "-group-" + index, fixture.novelId(), index, NOW, NOW);
        }
        assertThatThrownBy(() -> router(fixture, "allowlist").start(fixture.userId(),
                longSerialRequest(fixture, "request-plan-ambiguous-01", "plan_chapter", false)))
                .isInstanceOfSatisfying(ApiException.class,
                        error -> assertThat(error.code()).isEqualTo("CHAPTER_GROUP_MAPPING_CONFLICT"));
        assertThat(workflowFacts(fixture.userId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?", fixture.novelId()))
                .isZero();
    }

    @Test
    void Catalog启用操作缺少Core启动Handler时装配立即失败() {
        LongSerialDurableRunStarter incomplete = new LongSerialDurableRunStarter() {
            @Override
            public Set<String> supportedOperationKeys() {
                return Set.of("long_serial.rewrite_chapter_selection");
            }

            @Override
            public WritingRunV2Response replayExisting(
                    String userId,
                    cn.inkforge.contracts.api.LongSerialStartWritingRunRequest request) {
                throw new AssertionError("装配失败前不应调用 handler");
            }

            @Override
            public WritingRunV2Response startFresh(
                    String userId,
                    cn.inkforge.contracts.api.LongSerialStartWritingRunRequest request) {
                throw new AssertionError("装配失败前不应调用 handler");
            }
        };

        assertThatThrownBy(() -> new RoutingWritingRunStarter(
                        database,
                        legacy,
                        incomplete,
                        new CommandIdempotencyStore(json, true),
                        CoreSettings.from(Map.of(
                                "DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true",
                                "DURABLE_AGENT_EXECUTION_ROUTE_MODE", "off")),
                        () -> true,
                        json,
                        registry))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("long_serial.answer_question");
    }

    @Test
    void 冻结为只读的问答不会伪装成章节写入互斥() {
        Fixture fixture = fixture("route-v2-answer-read-only");
        WritingRunV2Response answer = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(),
                longSerialRequest(
                        fixture,
                        "request-answer-read-only-01",
                        "answer_question",
                        true));

        WritingRunV2Response rewrite = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(),
                requestWithoutSession(
                        fixture,
                        "request-rewrite-with-answer-01",
                        "并行冻结选区改写"));

        assertThat(answer.getOperation()).isEqualTo("answer_question");
        assertThat(rewrite.getOperation()).isEqualTo("rewrite_chapter_selection");
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(2);
    }

    @Test
    void V2重放返回按ordinal排序的全部活动Reviewer与冻结模型身份() {
        Fixture fixture = fixture("route-v2-active-reviewers");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-route-v2-reviewers-01", "请调整选区");
        WritingRunV2Response started = (WritingRunV2Response) router(fixture, "allowlist").start(
                fixture.userId(), request);
        ExecutionPlanSnapshot executionPlan = registry.freezePlan(
                "long_serial.rewrite_chapter_selection", false);

        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('completed' AS public."WorkflowStepStatus"),
                    "completedAt" = ?, "updatedAt" = ?
                WHERE id = ?
                """,
                NOW,
                NOW,
                started.getCurrentStep().getStepId());
        String evidenceBundleId = database.dsl().fetchOne(
                        "SELECT \"evidenceBundleId\" FROM public.\"WorkflowStep\" WHERE id = ?",
                        started.getCurrentStep().getStepId())
                .get("evidenceBundleId", String.class);
        insertPendingReviewer(
                started.getRunId(),
                "reviewer-step-ordinal-3",
                3,
                evidenceBundleId,
                executionPlan.reviewers().get(1));
        insertPendingReviewer(
                started.getRunId(),
                "reviewer-step-ordinal-2",
                2,
                evidenceBundleId,
                executionPlan.reviewers().getFirst());

        WritingRunV2Response replay = (WritingRunV2Response) router("off").start(
                fixture.userId(), request);

        assertThat(replay.getActiveSteps())
                .extracting(step -> step.getStepId())
                .containsExactly("reviewer-step-ordinal-2", "reviewer-step-ordinal-3");
        assertThat(replay.getActiveSteps())
                .extracting(step -> step.getOrdinal())
                .containsExactly(2, 3);
        assertThat(replay.getActiveSteps())
                .extracting(step -> step.getModelProfile().getProfile())
                .containsExactly("reviewer.consistency.v1", "reviewer.editorial.v1");
        assertThat(replay.getActiveSteps())
                .allSatisfy(step -> {
                    assertThat(step.getPurpose()).isEqualTo("review");
                    assertThat(step.getResolvedModel()).isNull();
                });
        assertThat(replay.getCurrentStep()).isSameAs(replay.getActiveSteps().getFirst());
    }

    @Test
    void V1已创建请求在打开V2后仍重放V1且跨引擎章节写入互斥() {
        Fixture legacyFixture = fixture("route-v1");
        ParsedWritingRunStartRequest legacyRequest = request(
                legacyFixture, "request-route-v1-0001", "请调整选区");

        var first = router("off").start(legacyFixture.userId(), legacyRequest);
        var replay = router(legacyFixture, "allowlist")
                .start(legacyFixture.userId(), legacyRequest);

        assertThat(first).isInstanceOf(WritingRunResponse.class);
        assertThat(((WritingRunResponse) first).getEngineVersion()).isEqualTo(1);
        assertThat(((WritingRunResponse) replay).getId())
                .isEqualTo(((WritingRunResponse) first).getId());

        Fixture durableFixture = fixture("route-busy");
        router(durableFixture, "allowlist").start(
                durableFixture.userId(),
                requestWithoutSession(
                        durableFixture, "request-route-busy-01", "先创建 V2"));
        assertThatThrownBy(() -> router("off").start(
                        durableFixture.userId(),
                        requestWithoutSession(
                                durableFixture,
                                "request-route-busy-02",
                                "再尝试 V1")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY"));
    }

    @ParameterizedTest(name = "V1 operation={0}")
    @MethodSource("mutatingV1Operations")
    void 活动V2阻断所有已支持V1写操作与保守legacy入口(String operation) {
        Fixture fixture = fixture("route-v1-mutation-" + operation.replace('_', '-'));
        router(fixture, "allowlist").start(
                fixture.userId(),
                requestWithoutSession(
                        fixture,
                        "request-v2-before-" + operation,
                        "先创建 V2 选区改写"));

        ParsedWritingRunStartRequest v1 = "legacy".equals(operation)
                ? legacyRequestWithoutSession(
                        fixture, "request-v1-after-legacy", "请继续处理这一章")
                : longSerialRequest(
                        fixture,
                        "request-v1-after-" + operation,
                        operation,
                        false);

        assertThatThrownBy(() -> router("off").start(fixture.userId(), v1))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY"));
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isZero();
    }

    @Test
    void 大纲选区跨引擎只阻断同一真实来源而不误锁章节正文() {
        Fixture sameSource = fixture("route-outline-cross-engine-same");
        router(sameSource, "allowlist").start(
                sameSource.userId(),
                longSerialRequest(
                        sameSource,
                        "request-outline-v2-before-v1-001",
                        "rewrite_outline_selection",
                        true));
        ParsedWritingRunStartRequest sameOutline = withWritingSession(
                longSerialRequest(
                        sameSource,
                        "request-outline-v1-after-v2-001",
                        "rewrite_outline_selection",
                        true),
                additionalSession(sameSource, "v1"));
        assertThatThrownBy(() -> router("off").start(sameSource.userId(), sameOutline))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY"));

        Fixture distinct = fixture("route-outline-cross-engine-distinct");
        String secondChapterId = distinct.novelId() + "-chapter-2";
        String secondSessionId = distinct.novelId() + "-session-2";
        insertChapterAndSession(distinct, secondChapterId, secondSessionId);
        router(distinct, "allowlist").start(
                distinct.userId(),
                requestWithoutSession(
                        distinct,
                        "request-chapter-v2-before-outline-v1-001",
                        "先改写章节正文"));
        WritingRunStartResponse outline = router("off").start(
                distinct.userId(),
                outlineSelectionRequest(
                        distinct,
                        "request-outline-v1-distinct-001",
                        secondChapterId,
                        secondSessionId,
                        "outline_content",
                        distinct.outlineId(),
                        distinct.outlineContent()));
        assertThat(outline).isInstanceOf(WritingRunResponse.class);

        Fixture reverse = fixture("route-outline-cross-engine-reverse");
        String reverseChapterId = reverse.novelId() + "-chapter-2";
        String reverseSessionId = reverse.novelId() + "-session-2";
        insertChapterAndSession(reverse, reverseChapterId, reverseSessionId);
        router("off").start(
                reverse.userId(),
                outlineSelectionRequest(
                        reverse,
                        "request-outline-v1-before-v2-001",
                        reverse.chapterId(),
                        reverse.sessionId(),
                        "outline_content",
                        reverse.outlineId(),
                        reverse.outlineContent()));
        assertThatThrownBy(() -> router(reverse, "allowlist").start(
                        reverse.userId(),
                        outlineSelectionRequest(
                                reverse,
                                "request-outline-v2-after-v1-001",
                                reverseChapterId,
                                reverseSessionId,
                                "outline_content",
                                reverse.outlineId(),
                                reverse.outlineContent())))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY"));
    }

    @ParameterizedTest(name = "V1只读 operation={0}")
    @MethodSource("readOnlyV1Operations")
    void 不同WritingSession的只读V1与V2章节写入双向并存(String operation) {
        String token = operation.equals("answer_question") ? "answer" : "review";
        Fixture fixture = fixture("route-v1-" + token + "-durable-first");
        String durableSessionId = additionalSession(fixture, "v2");
        router(fixture, "allowlist").start(
                fixture.userId(),
                withWritingSession(
                        requestWithoutSession(
                                fixture,
                                "request-v2-before-" + token + "-01",
                                "先创建 V2 选区改写"),
                        durableSessionId));

        WritingRunStartResponse readOnly = router("off").start(
                fixture.userId(),
                longSerialRequest(
                        fixture,
                        "request-v1-after-" + token + "-01",
                        operation,
                        true));

        assertThat(readOnly).isInstanceOf(WritingRunResponse.class);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?",
                        fixture.chapterId()))
                .isEqualTo(1);

        Fixture readFirst = fixture("route-v1-" + token + "-read-first");
        router("off").start(
                readFirst.userId(),
                longSerialRequest(
                        readFirst,
                        "request-v1-first-" + token + "-01",
                        operation,
                        true));
        String reverseDurableSessionId = additionalSession(readFirst, "v2");
        WritingRunStartResponse durable = router(readFirst, "allowlist").start(
                readFirst.userId(),
                withWritingSession(
                        requestWithoutSession(
                                readFirst,
                                "request-v2-after-" + token + "-01",
                                "只读运行期间创建独立 V2 写任务"),
                        reverseDurableSessionId));
        assertThat(durable).isInstanceOf(WritingRunV2Response.class);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"chapterId\" = ?",
                        readFirst.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ?",
                        readFirst.chapterId()))
                .isEqualTo(1);
    }

    @Test
    void 同WritingSession跨引擎只允许一个foreground且只读审核也不豁免() {
        Fixture v2First = fixture("route-session-v2-first");
        router(v2First, "allowlist").start(
                v2First.userId(),
                request(v2First, "request-session-v2-first-01", "先创建 V2"));
        assertThatThrownBy(() -> router("off").start(
                        v2First.userId(),
                        longSerialRequest(
                                v2First,
                                "request-session-v1-review-01",
                                "review_chapter",
                                true)))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_FOREGROUND_RUN_EXISTS"));

        Fixture v1First = fixture("route-session-v1-first");
        WritingRunStartResponse review = router("off").start(
                v1First.userId(),
                longSerialRequest(
                        v1First,
                        "request-session-v1-first-01",
                        "review_chapter",
                        true));
        assertThat(review).isInstanceOf(WritingRunResponse.class);
        assertThatThrownBy(() -> router(v1First, "allowlist").start(
                        v1First.userId(),
                        request(v1First, "request-session-v2-after-01", "再创建 V2")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("WORKFLOW_FOREGROUND_RUN_EXISTS"));
    }

    @Test
    void 已有V1和V2重放在Agent离线或manifest升级时不被阻断() {
        Fixture v2Fixture = fixture("route-replay-v2-offline");
        ParsedWritingRunStartRequest v2Request = request(
                v2Fixture, "request-replay-v2-offline-01", "请调整选区");
        WritingRunV2Response firstV2 = (WritingRunV2Response) router(v2Fixture, "allowlist").start(
                v2Fixture.userId(), v2Request);
        AtomicInteger v2Probes = new AtomicInteger();
        WritingRunV2Response replayV2 = (WritingRunV2Response) router(
                        v2Fixture,
                        "allowlist",
                        () -> {
                            v2Probes.incrementAndGet();
                            return false;
                        })
                .start(v2Fixture.userId(), v2Request);

        assertThat(replayV2.getRunId()).isEqualTo(firstV2.getRunId());
        assertThat(v2Probes).hasValue(0);

        Fixture v1Fixture = fixture("route-replay-v1-offline");
        ParsedWritingRunStartRequest v1Request = request(
                v1Fixture, "request-replay-v1-offline-01", "请调整选区");
        WritingRunResponse firstV1 = (WritingRunResponse) router("off").start(
                v1Fixture.userId(), v1Request);
        AtomicInteger v1Probes = new AtomicInteger();
        WritingRunResponse replayV1 = (WritingRunResponse) router(
                        v1Fixture,
                        "allowlist",
                        () -> {
                            v1Probes.incrementAndGet();
                            return false;
                        })
                .start(v1Fixture.userId(), v1Request);

        assertThat(replayV1.getId()).isEqualTo(firstV1.getId());
        assertThat(v1Probes).hasValue(0);
    }

    @Test
    void V1新建门禁位于幂等重放之后且早于readiness锁和任何写入() {
        Fixture existingFixture = fixture("route-v1-drain-replay");
        ParsedWritingRunStartRequest existingRequest = request(
                existingFixture, "request-v1-drain-replay-01", "先创建 V1");
        WritingRunResponse first = (WritingRunResponse) router("off").start(
                existingFixture.userId(), existingRequest);
        AtomicInteger replayProbes = new AtomicInteger();

        WritingRunResponse replay = (WritingRunResponse) router(
                        "off",
                        false,
                        () -> {
                            replayProbes.incrementAndGet();
                            return false;
                        })
                .start(existingFixture.userId(), existingRequest);

        assertThat(replay.getId()).isEqualTo(first.getId());
        assertThat(replayProbes).hasValue(0);

        Fixture freshFixture = fixture("route-v1-drain-fresh");
        ParsedWritingRunStartRequest freshRequest = request(
                freshFixture, "request-v1-drain-fresh-01", "不得创建 V1");
        AtomicInteger freshProbes = new AtomicInteger();
        long factsBefore = workflowFacts(freshFixture.userId());

        assertThatThrownBy(() -> router(
                                "off",
                                false,
                                () -> {
                                    freshProbes.incrementAndGet();
                                    return true;
                                })
                        .start(freshFixture.userId(), freshRequest))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code()).isEqualTo("AGENT_FRESH_STARTS_DRAINING");
                });

        assertThat(freshProbes).hasValue(0);
        assertThat(workflowFacts(freshFixture.userId())).isEqualTo(factsBefore);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?",
                        freshFixture.sessionId()))
                .isZero();
    }

    @Test
    void drain期间并发V1fresh请求全部封锁且不能留下幂等身份() throws Exception {
        Fixture fixture = fixture("route-v1-drain-concurrent");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-v1-drain-concurrent-01", "并发也不得创建");
        RoutingWritingRunStarter draining = router("off", false, () -> {
            throw new AssertionError("fresh V1 门禁之后不应探测 Agent");
        });

        CompletableFuture<Object> first = CompletableFuture.supplyAsync(() -> captureFailure(
                () -> draining.start(fixture.userId(), request)));
        CompletableFuture<Object> second = CompletableFuture.supplyAsync(() -> captureFailure(
                () -> draining.start(fixture.userId(), request)));

        assertThat(List.of(first.get(5, TimeUnit.SECONDS), second.get(5, TimeUnit.SECONDS)))
                .allSatisfy(value -> assertThat(value)
                        .isInstanceOfSatisfying(ApiException.class, error ->
                                assertThat(error.code())
                                        .isEqualTo("AGENT_FRESH_STARTS_DRAINING")));
        assertThat(workflowFacts(fixture.userId())).isZero();
    }

    @Test
    void 新V2在manifest握手失败时以503拒绝且零持久工作流事实() {
        Fixture fixture = fixture("route-manifest-mismatch");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-manifest-mismatch-01", "请调整选区");
        AtomicInteger probes = new AtomicInteger();

        assertThatThrownBy(() -> router(
                                fixture,
                                "allowlist",
                                () -> {
                                    probes.incrementAndGet();
                                    assertThat(workflowFacts(fixture.userId())).isZero();
                                    Boolean lockWasFree = database.transactionResult(transaction -> transaction
                                                    .fetchOne(
                                                            "SELECT pg_catalog.pg_try_advisory_xact_lock(?) AS free",
                                                            CommandIdempotency.advisoryLockKey(
                                                                    fixture.userId(),
                                                                    "request-manifest-mismatch-01"))
                                                    .get("free", Boolean.class));
                                    assertThat(lockWasFree).isTrue();
                                    return false;
                                })
                        .start(fixture.userId(), request))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code())
                            .isEqualTo("DURABLE_AGENT_EXECUTION_UNAVAILABLE");
                    assertThat(error.details()).isNull();
                });

        assertThat(probes).hasValue(1);
        assertThat(workflowFacts(fixture.userId())).isZero();
    }

    @Test
    void 并发同幂等标识均在无锁握手后仍只创建一个V2Run() throws Exception {
        Fixture fixture = fixture("route-concurrent-v2");
        ParsedWritingRunStartRequest request = request(
                fixture, "request-concurrent-v2-01", "请调整选区");
        CountDownLatch probesEntered = new CountDownLatch(2);
        CountDownLatch releaseProbes = new CountDownLatch(1);
        DurableAgentExecutionReadiness readiness = () -> {
            probesEntered.countDown();
            try {
                return releaseProbes.await(2, TimeUnit.SECONDS);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return false;
            }
        };
        RoutingWritingRunStarter router = router(fixture, "allowlist", readiness);

        CompletableFuture<WritingRunV2Response> first = CompletableFuture.supplyAsync(
                () -> (WritingRunV2Response) router.start(fixture.userId(), request));
        CompletableFuture<WritingRunV2Response> second = CompletableFuture.supplyAsync(
                () -> (WritingRunV2Response) router.start(fixture.userId(), request));
        assertThat(probesEntered.await(2, TimeUnit.SECONDS)).isTrue();
        assertThat(workflowFacts(fixture.userId())).isZero();
        releaseProbes.countDown();

        WritingRunV2Response firstResponse = first.get(5, TimeUnit.SECONDS);
        WritingRunV2Response secondResponse = second.get(5, TimeUnit.SECONDS);
        assertThat(secondResponse.getRunId()).isEqualTo(firstResponse.getRunId());
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?",
                        fixture.userId()))
                .isEqualTo(1);
    }

    @Test
    void 同章节无Session的不同幂等请求并发也只允许一个活动V2Run() throws Exception {
        Fixture fixture = fixture("route-v2-scope-busy");
        ParsedWritingRunStartRequest first = requestWithoutSession(
                fixture, "request-v2-scope-busy-01", "第一次选区改写");
        ParsedWritingRunStartRequest second = requestWithoutSession(
                fixture, "request-v2-scope-busy-02", "第二次选区改写");
        CountDownLatch probesEntered = new CountDownLatch(2);
        CountDownLatch releaseProbes = new CountDownLatch(1);
        RoutingWritingRunStarter all = router(fixture, "allowlist", () -> {
            probesEntered.countDown();
            try {
                return releaseProbes.await(2, TimeUnit.SECONDS);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return false;
            }
        });

        CompletableFuture<WritingRunStartResponse> firstStart = CompletableFuture.supplyAsync(
                () -> all.start(fixture.userId(), first));
        CompletableFuture<WritingRunStartResponse> secondStart = CompletableFuture.supplyAsync(
                () -> all.start(fixture.userId(), second));
        assertThat(probesEntered.await(2, TimeUnit.SECONDS)).isTrue();
        releaseProbes.countDown();
        Object firstOutcome = firstStart.handle((value, error) ->
                        error == null ? value : error.getCause())
                .get(5, TimeUnit.SECONDS);
        Object secondOutcome = secondStart.handle((value, error) ->
                        error == null ? value : error.getCause())
                .get(5, TimeUnit.SECONDS);

        assertThat(List.of(firstOutcome, secondOutcome))
                .anySatisfy(value -> assertThat(value).isInstanceOf(WritingRunV2Response.class))
                .anySatisfy(value -> assertThat(value)
                        .isInstanceOfSatisfying(ApiException.class, error ->
                                assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY")));
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"chapterId\" = ? AND status IN ('pending', 'running', 'waiting_user')",
                        fixture.chapterId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?",
                        fixture.sessionId()))
                .isZero();
    }

    @Test
    void 同章节V1V2真实并发时一个成功另一个稳定busy且不死锁() throws Exception {
        Fixture fixture = fixture("route-cross-engine-race");
        ParsedWritingRunStartRequest v1 = longSerialRequest(
                fixture,
                "request-cross-engine-v1-01",
                "plan_chapter",
                false);
        ParsedWritingRunStartRequest v2 = requestWithoutSession(
                fixture,
                "request-cross-engine-v2-01",
                "并发改写选区");
        CountDownLatch startersReady = new CountDownLatch(2);
        CountDownLatch releaseStart = new CountDownLatch(1);

        CompletableFuture<WritingRunStartResponse> v1Start = CompletableFuture.supplyAsync(
                () -> startAfterGate(router("off"), fixture.userId(), v1, startersReady, releaseStart));
        CompletableFuture<WritingRunStartResponse> v2Start = CompletableFuture.supplyAsync(
                () -> startAfterGate(
                        router(fixture, "allowlist"),
                        fixture.userId(),
                        v2,
                        startersReady,
                        releaseStart));
        assertThat(startersReady.await(2, TimeUnit.SECONDS)).isTrue();
        releaseStart.countDown();

        Object v1Outcome = v1Start.handle((value, error) ->
                        error == null ? value : error.getCause())
                .get(8, TimeUnit.SECONDS);
        Object v2Outcome = v2Start.handle((value, error) ->
                        error == null ? value : error.getCause())
                .get(8, TimeUnit.SECONDS);

        assertThat(List.of(v1Outcome, v2Outcome))
                .anySatisfy(value -> assertThat(value)
                        .isInstanceOfAny(WritingRunResponse.class, WritingRunV2Response.class))
                .anySatisfy(value -> assertThat(value)
                        .isInstanceOfSatisfying(ApiException.class, error ->
                                assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY")));
        assertThat(count(
                                """
                                SELECT (
                                  SELECT count(*) FROM public."WritingTask"
                                  WHERE "chapterId" = ? AND phase NOT IN ('completed', 'error')
                                ) + (
                                  SELECT count(*) FROM public."WorkflowRun"
                                  WHERE "chapterId" = ?
                                    AND status IN ('pending', 'running', 'waiting_user')
                                )
                                """,
                                fixture.chapterId(),
                                fixture.chapterId()))
                .isEqualTo(1);
    }

    private static RoutingWritingRunStarter router(String mode) {
        return router(mode, () -> true);
    }

    private static RoutingWritingRunStarter router(Fixture scope, String mode) {
        return router(scope, mode, () -> true);
    }

    private static void insertPendingReviewer(
            String runId,
            String stepId,
            int ordinal,
            String evidenceBundleId,
            ExecutionPlanSnapshot.Step reviewer) {
        String hashDigit = ordinal == 2 ? "b" : "c";
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken",
                  "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                  "modelProfile", "modelProfileVersion", "outputSchema",
                  "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt"
                ) VALUES (
                  ?, ?, ?, CAST('agent' AS public."WorkflowStepType"),
                  CAST('pending' AS public."WorkflowStepStatus"), '{}', ?, ?, 'review', ?,
                  0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                stepId,
                runId,
                reviewer.modelProfile().profile(),
                NOW,
                ordinal,
                reviewer.lane(),
                NOW,
                runId + "." + stepId,
                hashDigit.repeat(64),
                "d".repeat(64),
                evidenceBundleId,
                reviewer.modelProfile().profile(),
                Integer.toString(reviewer.modelProfile().version()),
                reviewer.outputSchema().name(),
                Integer.toString(reviewer.outputSchema().version()),
                json.writeValueAsString(reviewer.stepBudget().stored()),
                NOW,
                NOW);
    }

    private static void completeReviewRun(String runId, String stepId, String report) {
        ReviewCompletion completion = reviewCompletion(report);
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('completed' AS public."WorkflowStepStatus"),
                    output = ?, "resultHash" = ?, "resolvedModelJson" = ?, "usageJson" = ?,
                    "attemptCount" = 1, "fencingToken" = 1, "nextAttemptAt" = NULL,
                    "completedAt" = ?, "updatedAt" = ?
                WHERE id = ? AND "runId" = ?
                """,
                json.writeValueAsString(completion.output()),
                completion.resultHash(),
                json.writeValueAsString(completion.resolvedModel()),
                json.writeValueAsString(completion.usage()),
                NOW,
                NOW,
                stepId,
                runId);
        completeRun(runId);
    }

    private static void completeNaturalReviewRun(String runId, String resolverStepId, String report) {
        Record run = database.dsl().fetchOne(
                "SELECT \"modelPolicyJson\", input, \"chapterId\" FROM public.\"WorkflowRun\" WHERE id = ?",
                runId);
        IntentExecutionPlanSnapshot intent = IntentExecutionPlanSnapshot.fromStored(
                json.readValue(run.get("modelPolicyJson", String.class), new TypeReference<>() {}));
        ExecutionPlanSnapshot review = intent.requireOperationPlan("long_serial.review_chapter");
        String intentBundleId = database.dsl().fetchOne(
                        "SELECT \"evidenceBundleId\" FROM public.\"WorkflowStep\" WHERE id = ?",
                        resolverStepId)
                .get("evidenceBundleId", String.class);
        String resolverResultHash = "a".repeat(64);
        database.dsl().execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('completed' AS public."WorkflowStepStatus"),
                    "resultHash" = ?, "usageJson" = ?, "attemptCount" = 1,
                    "fencingToken" = 1, "nextAttemptAt" = NULL,
                    "completedAt" = ?, "updatedAt" = ?
                WHERE id = ? AND "runId" = ?
                """,
                resolverResultHash,
                json.writeValueAsString(Map.of(
                        "usageStatus", "unknown",
                        "providerAttempts", 1,
                        "protocolCorrections", 0,
                        "wallTimeMillis", 12)),
                NOW,
                NOW,
                resolverStepId,
                runId);
        WorkflowIntentSelection selection = new WorkflowIntentSelection(
                runId,
                review.operation().key(),
                review.sha256(),
                resolverStepId,
                resolverResultHash,
                intentBundleId,
                "chapter",
                run.get("chapterId", String.class),
                "chapter");
        String selectionStepId = "selection-" + runId;
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "fencingToken",
                  "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                  "submittedAt", "updatedAt", "completedAt"
                ) VALUES (
                  ?, ?, 'core', CAST('persistence' AS public."WorkflowStepType"),
                  CAST('completed' AS public."WorkflowStepStatus"), ?, ?, 2,
                  'intent_selection', 'control', 0, 0, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                selectionStepId,
                runId,
                json.writeValueAsString(selection.stored()),
                NOW,
                runId + "." + selectionStepId,
                selection.inputHash(),
                selection.inputHash(),
                intentBundleId,
                NOW,
                NOW,
                NOW);

        ReviewCompletion completion = reviewCompletion(report);
        Map<String, Object> normalizedInput = json.readValue(
                run.get("input", String.class), new TypeReference<>() {});
        Map<String, Object> generationInput = Map.of(
                "userInstruction", normalizedInput.get("userInstruction"));
        String generationStepId = "generation-" + runId;
        ExecutionPlanSnapshot.Step generator = review.generator();
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, output, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "fencingToken", "idempotencyKey",
                  "requestHash", "inputHash", "resultHash", "evidenceBundleId",
                  "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion",
                  "budgetJson", "resolvedModelJson", "usageJson", "submittedAt", "updatedAt", "completedAt"
                ) VALUES (
                  ?, ?, 'editor', CAST('agent' AS public."WorkflowStepType"),
                  CAST('completed' AS public."WorkflowStepStatus"), ?, ?, ?, 3,
                  'generation', ?, 1, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                generationStepId,
                runId,
                json.writeValueAsString(generationInput),
                json.writeValueAsString(completion.output()),
                NOW,
                generator.lane(),
                runId + "." + generationStepId,
                "b".repeat(64),
                ExecutionCanonicalJson.sha256(generationInput),
                completion.resultHash(),
                intentBundleId,
                generator.modelProfile().profile(),
                Integer.toString(generator.modelProfile().version()),
                generator.outputSchema().name(),
                Integer.toString(generator.outputSchema().version()),
                json.writeValueAsString(generator.stepBudget().stored()),
                json.writeValueAsString(completion.resolvedModel()),
                json.writeValueAsString(completion.usage()),
                NOW,
                NOW,
                NOW);
        completeRun(runId);
    }

    private static ReviewCompletion reviewCompletion(String report) {
        ExecutionPlanSnapshot.Step generator = registry
                .freezePlan("long_serial.review_chapter", false)
                .generator();
        String deploymentProfile = generator.modelProfile().deploymentProfileKey();
        String reasoningMode = generator.modelProfile().reasoningMode();
        Map<String, Object> resolvedModel = Map.of(
                "deploymentProfileKey", deploymentProfile,
                "deploymentFingerprint", WorkflowResolvedModel.fingerprint(
                        deploymentProfile,
                        "fake",
                        "fake",
                        "transport.fake.v1",
                        "endpoint.local-fake.v1",
                        "responses_json_schema_v1",
                        "capability.fake.structured-output.v1",
                        reasoningMode,
                        true),
                "provider", "fake",
                "model", "fake",
                "transportProfile", "transport.fake.v1",
                "endpointProfile", "endpoint.local-fake.v1",
                "structuredOutputRoute", "responses_json_schema_v1",
                "capabilityVersion", "capability.fake.structured-output.v1",
                "reasoningMode", reasoningMode,
                "supportsRequestIdempotency", true);
        Map<String, Object> usage = Map.ofEntries(
                Map.entry("usageStatus", "complete"),
                Map.entry("inputTokens", 10),
                Map.entry("cachedTokens", 0),
                Map.entry("promptCacheMissTokens", 10),
                Map.entry("completionTokens", 6),
                Map.entry("reasoningTokens", 0),
                Map.entry("visibleOutputTokens", 6),
                Map.entry("costMicros", 0),
                Map.entry("providerAttempts", 1),
                Map.entry("protocolCorrections", 0),
                Map.entry("wallTimeMillis", 12));
        Map<String, Object> output = Map.of("report", report);
        String resultHash = ExecutionCanonicalJson.sha256(Map.of(
                "resultKind", "output",
                "resolvedModel", resolvedModel,
                "usage", usage,
                "value", output));
        return new ReviewCompletion(output, resolvedModel, usage, resultHash);
    }

    private static void completeRun(String runId) {
        database.dsl().execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('completed' AS public."WorkflowRunStatus"),
                    "completedAt" = ?, "updatedAt" = ?, revision = revision + 1
                WHERE id = ?
                """,
                NOW,
                NOW,
                runId);
    }

    private record ReviewCompletion(
            Map<String, Object> output,
            Map<String, Object> resolvedModel,
            Map<String, Object> usage,
            String resultHash) {}

    private static RoutingWritingRunStarter router(
            String mode, DurableAgentExecutionReadiness readiness) {
        return router(null, mode, true, readiness);
    }

    private static RoutingWritingRunStarter router(
            Fixture scope,
            String mode,
            DurableAgentExecutionReadiness readiness) {
        return router(scope, mode, true, readiness);
    }

    private static RoutingWritingRunStarter router(
            String mode,
            boolean freshStartsEnabled,
            DurableAgentExecutionReadiness readiness) {
        return router(null, mode, freshStartsEnabled, readiness);
    }

    private static RoutingWritingRunStarter router(
            Fixture scope,
            String mode,
            boolean freshStartsEnabled,
            DurableAgentExecutionReadiness readiness) {
        Map<String, String> settings = new java.util.LinkedHashMap<>();
        settings.put("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true");
        settings.put("DURABLE_AGENT_EXECUTION_ROUTE_MODE", mode);
        settings.put(
                "V1_FRESH_AGENT_STARTS_ENABLED",
                Boolean.toString(freshStartsEnabled));
        if ("allowlist".equals(mode)) {
            if (scope == null) throw new IllegalArgumentException("allowlist 测试必须提供精确 scope");
            settings.put("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", scope.userId());
            settings.put("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", scope.novelId());
        }
        return new RoutingWritingRunStarter(
                database,
                legacy,
                durable,
                new CommandIdempotencyStore(json, true),
                CoreSettings.from(settings),
                readiness,
                json,
                registry,
                new JooqWorkflowExecutionContextReader(json));
    }

    private static Object captureFailure(java.util.concurrent.Callable<?> operation) {
        try {
            return operation.call();
        } catch (RuntimeException exception) {
            return exception;
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static ParsedWritingRunStartRequest request(
            Fixture fixture, String clientRequestId, String instruction) {
        String selected = codePointSlice(fixture.content(), 1, 3);
        String body = """
                {
                  "clientRequestId": "%s",
                  "workflow": "long_serial",
                  "novelId": "%s",
                  "chapterId": "%s",
                  "writingSessionId": "%s",
                  "operation": "rewrite_chapter_selection",
                  "target": {"type": "chapter", "id": "%s"},
                  "scope": {"kind": "chapter", "chapterId": "%s"},
                  "selectionTarget": {
                    "resourceType": "chapter_content",
                    "resourceId": "%s",
                    "baseUpdatedAt": "2026-09-01T03:00:00Z",
                    "baseContentHash": "%s",
                    "selectionStart": 1,
                    "selectionEnd": 3,
                    "selectedTextHash": "%s"
                  },
                  "selectionAttachmentMetadata": {
                    "resourceType": "chapter_content",
                    "resourceId": "%s",
                    "sourceLabel": "章节正文",
                    "baseUpdatedAt": "2026-09-01T03:00:00Z",
                    "baseContentHash": "%s",
                    "selectionStart": 1,
                    "selectionEnd": 3,
                    "selectedTextHash": "%s",
                    "selectionPreview": "%s"
                  },
                  "targetWordCount": 1000,
                  "userInstruction": "%s"
                }
                """.formatted(
                clientRequestId,
                fixture.novelId(),
                fixture.chapterId(),
                fixture.sessionId(),
                fixture.chapterId(),
                fixture.chapterId(),
                fixture.chapterId(),
                sha256(fixture.content()),
                sha256(selected),
                fixture.chapterId(),
                sha256(fixture.content()),
                sha256(selected),
                selected,
                instruction);
        return parser.parse(new WritingRunStartBody(json.readTree(body)));
    }

    private static ParsedWritingRunStartRequest requestWithoutSession(
            Fixture fixture, String clientRequestId, String instruction) {
        ParsedWritingRunStartRequest parsed = request(fixture, clientRequestId, instruction);
        ((ParsedWritingRunStartRequest.LongSerial) parsed)
                .request()
                .setWritingSessionId(null);
        return parsed;
    }

    private static ParsedWritingRunStartRequest withWritingSession(
            ParsedWritingRunStartRequest request, String writingSessionId) {
        ((ParsedWritingRunStartRequest.LongSerial) request)
                .request()
                .writingSessionId(writingSessionId);
        return request;
    }

    private static ParsedWritingRunStartRequest longSerialRequest(
            Fixture fixture,
            String clientRequestId,
            String operation,
            boolean withSession) {
        Map<String, Object> body = new java.util.LinkedHashMap<>();
        body.put("clientRequestId", clientRequestId);
        body.put("workflow", "long_serial");
        body.put("novelId", fixture.novelId());
        body.put("chapterId", fixture.chapterId());
        if (withSession) body.put("writingSessionId", fixture.sessionId());
        body.put("operation", operation);
        body.put("target", Map.of("type", "chapter", "id", fixture.chapterId()));
        body.put("targetWordCount", 1000);
        body.put("userInstruction", "请执行 " + operation);
        if ("rewrite_outline_selection".equals(operation)) {
            String selected = codePointSlice(fixture.outlineContent(), 1, 3);
            body.put("scope", Map.of("kind", "novel"));
            body.put(
                    "selectionTarget",
                    Map.of(
                            "resourceType", "outline_content",
                            "resourceId", fixture.outlineId(),
                            "baseUpdatedAt", "2026-09-01T03:00:00Z",
                            "baseContentHash", sha256(fixture.outlineContent()),
                            "selectionStart", 1,
                            "selectionEnd", 3,
                            "selectedTextHash", sha256(selected)));
        } else if ("rewrite_chapter_selection".equals(operation)) {
            String selected = codePointSlice(fixture.content(), 1, 3);
            body.put("scope", Map.of("kind", "chapter", "chapterId", fixture.chapterId()));
            body.put(
                    "selectionTarget",
                    Map.of(
                            "resourceType", "chapter_content",
                            "resourceId", fixture.chapterId(),
                            "baseUpdatedAt", "2026-09-01T03:00:00Z",
                            "baseContentHash", sha256(fixture.content()),
                            "selectionStart", 1,
                            "selectionEnd", 3,
                            "selectedTextHash", sha256(selected)));
        } else {
            body.put("scope", Map.of("kind", "chapter", "chapterId", fixture.chapterId()));
        }
        return parser.parse(new WritingRunStartBody(json.valueToTree(body)));
    }

    private static ParsedWritingRunStartRequest outlineSelectionRequest(
            Fixture fixture,
            String clientRequestId,
            String chapterId,
            String writingSessionId,
            String resourceType,
            String resourceId,
            String content) {
        String selected = codePointSlice(content, 1, 3);
        Map<String, Object> body = new java.util.LinkedHashMap<>();
        body.put("clientRequestId", clientRequestId);
        body.put("workflow", "long_serial");
        body.put("novelId", fixture.novelId());
        body.put("chapterId", chapterId);
        body.put("writingSessionId", writingSessionId);
        body.put("operation", "rewrite_outline_selection");
        body.put("target", Map.of("type", "chapter", "id", chapterId));
        body.put("scope", "outline_content".equals(resourceType)
                ? Map.of("kind", "novel")
                : Map.of("kind", "outline_node", "outlineNodeId", resourceId));
        body.put("selectionTarget", Map.of(
                "resourceType", resourceType,
                "resourceId", resourceId,
                "baseUpdatedAt", "2026-09-01T03:00:00Z",
                "baseContentHash", sha256(content),
                "selectionStart", 1,
                "selectionEnd", 3,
                "selectedTextHash", sha256(selected)));
        body.put("targetWordCount", 1000);
        body.put("userInstruction", "请改写大纲选区");
        return parser.parse(new WritingRunStartBody(json.valueToTree(body)));
    }

    private static void insertOutlineNode(Fixture fixture, String nodeId, String content) {
        database.dsl().execute(
                """
                INSERT INTO public."OutlineNode" (
                  id, "novelId", kind, title, content, "order", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'stage', '大纲节点', ?, 1, ?, ?)
                """,
                nodeId,
                fixture.novelId(),
                content,
                NOW,
                NOW);
    }

    private static void insertChapterAndSession(
            Fixture fixture, String chapterId, String sessionId) {
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第二章', '第二章正文', 2, 'drafting', ?, ?)
                """,
                chapterId,
                fixture.novelId(),
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                sessionId,
                fixture.novelId(),
                chapterId,
                NOW,
                NOW);
    }

    private static ParsedWritingRunStartRequest legacyRequestWithoutSession(
            Fixture fixture, String clientRequestId, String instruction) {
        Map<String, Object> body = Map.of(
                "clientRequestId", clientRequestId,
                "novelId", fixture.novelId(),
                "chapterId", fixture.chapterId(),
                "targetWordCount", 1000,
                "selectedAgents", List.of("写作"),
                "userMessage", instruction);
        return parser.parse(new WritingRunStartBody(json.valueToTree(body)));
    }

    private static WritingRunStartResponse startAfterGate(
            RoutingWritingRunStarter starter,
            String userId,
            ParsedWritingRunStartRequest request,
            CountDownLatch ready,
            CountDownLatch release) {
        ready.countDown();
        try {
            if (!release.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("并发启动门未及时释放");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("并发启动被中断", exception);
        }
        return starter.start(userId, request);
    }

    private static Stream<Arguments> mutatingV1Operations() {
        return Stream.of(
                Arguments.of("plan_chapter"),
                Arguments.of("write_chapter"),
                Arguments.of("rewrite_scene"),
                Arguments.of("rewrite_chapter_selection"),
                Arguments.of("rewrite_outline_selection"),
                Arguments.of("legacy"));
    }

    private static Stream<Arguments> readOnlyV1Operations() {
        return Stream.of(
                Arguments.of("answer_question"),
                Arguments.of("review_chapter"));
    }

    private static String additionalSession(Fixture fixture, String suffix) {
        String sessionId = fixture.sessionId() + "-" + suffix;
        database.dsl().execute(
                """
                INSERT INTO public."WritingSession" (
                  id, "novelId", "chapterId", phase, "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, 'idle', ?, ?)
                """,
                sessionId,
                fixture.novelId(),
                fixture.chapterId(),
                NOW,
                NOW);
        return sessionId;
    }

    private static Fixture fixture(String prefix) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        String sessionId = prefix + "-session";
        String content = "甲😀乙丙";
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
                INSERT INTO public."WritingBible" (
                  id, "novelId", "storyLengthProfile", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'long_serial', ?, ?)
                """,
                prefix + "-bible",
                novelId,
                NOW,
                NOW);
        database.dsl().execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '第一章', ?, 1, 'drafting', ?, ?)
                """,
                chapterId,
                novelId,
                content,
                NOW,
                NOW);
        String outlineId = prefix + "-outline";
        String outlineContent = "纲要甲乙";
        database.dsl().execute(
                """
                INSERT INTO public."Outline" (id, "novelId", content, "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                outlineId,
                novelId,
                outlineContent,
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
        return new Fixture(
                userId,
                novelId,
                chapterId,
                sessionId,
                content,
                outlineId,
                outlineContent);
    }

    private static int count(String sql, Object... bindings) {
        return database.dsl().fetchOne(sql, bindings).get(0, Integer.class);
    }

    private static LocalDateTime sessionUpdatedAt(String sessionId) {
        return database.dsl().fetchOne(
                        "SELECT \"updatedAt\" FROM public.\"WritingSession\" WHERE id = ?",
                        sessionId)
                .get("updatedAt", LocalDateTime.class);
    }

    private static int workflowFacts(String userId) {
        return count(
                        "SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?",
                        userId)
                + count(
                        """
                        SELECT count(*) FROM public."WorkflowStep"
                        WHERE "runId" IN (
                          SELECT id FROM public."WorkflowRun" WHERE "userId" = ?
                        )
                        """,
                        userId)
                + count(
                        """
                        SELECT count(*) FROM public."WorkflowEvidenceBundle"
                        WHERE "runId" IN (
                          SELECT id FROM public."WorkflowRun" WHERE "userId" = ?
                        )
                        """,
                        userId)
                + count(
                        """
                        SELECT count(*) FROM public."WorkflowEvent"
                        WHERE "runId" IN (
                          SELECT id FROM public."WorkflowRun" WHERE "userId" = ?
                        )
                        """,
                        userId);
    }

    private static String sha256(String value) {
        return CommandIdempotency.sha256(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String codePointSlice(String value, int start, int end) {
        return value.substring(
                value.offsetByCodePoints(0, start), value.offsetByCodePoints(0, end));
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
            String content,
            String outlineId,
            String outlineContent) {}
}
