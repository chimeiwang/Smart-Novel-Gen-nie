package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.contracts.api.EvidenceEvaluation;
import cn.inkforge.contracts.api.ExecutionCallbackReceipt;
import cn.inkforge.contracts.api.ExecutionStepProgress;
import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.contracts.api.ModelProfileRef;
import cn.inkforge.contracts.api.ProposedCommand;
import cn.inkforge.contracts.api.ResolvedModelRef;
import cn.inkforge.contracts.api.StepUsage;
import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.identity.api.IdentityController;
import cn.inkforge.core.identity.domain.SessionTokens;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.workflows.application.WorkflowCallbackRepository;
import cn.inkforge.core.workflows.application.WorkflowDispatchRepository;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.writing.application.DurableAgentExecutionReadiness;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 公共 HTTP 启动/详情/采用与真实 Core 回调事务集成；模型响应在隔离环境确定性提供，不访问供应商。 */
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(classes = {CoreApplication.class,
        WorkflowV2SseHttpIntegrationTest.TestIdentityConfiguration.class,
        StructuredAgentUpdatesHttpIntegrationTest.LocalExecutionConfiguration.class},
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StructuredAgentUpdatesHttpIntegrationTest {
    private static final String TEST_USER = "structured-http-author";
    private static final List<String> OPERATIONS = List.of("create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing");
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("isolated-test-only")
            .withCopyFileToContainer(MountableFile.forClasspathResource("db/novelwriterdev-schema.sql", 0644), "/docker-entrypoint-initdb.d/01-schema.sql")
            .withCopyFileToContainer(MountableFile.forClasspathResource("migrations/20260831_durable_agent_execution.sql", 0644), "/docker-entrypoint-initdb.d/02-durable-agent.sql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add("DATABASE_URL", () -> "postgresql://" + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432) + "/" + POSTGRES.getDatabaseName());
        properties.add("REDIS_URL", () -> "false");
        properties.add("JWT_SECRET", () -> "结构化资料HTTP隔离测试专用密钥-不可用于生产环境");
        properties.add("ENVIRONMENT", () -> "test");
        properties.add("VIDEO_PREVIEW_ENABLED", () -> "false");
        properties.add("DURABLE_AGENT_EXECUTION_SCHEMA_READY", () -> "true");
        properties.add("DURABLE_AGENT_EXECUTION_ROUTE_MODE", () -> "allowlist");
        properties.add("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", () -> TEST_USER);
        properties.add("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", () -> OPERATIONS.stream()
                .flatMap(operation -> Stream.of(novelId(operation, false), novelId(operation, true)))
                .collect(java.util.stream.Collectors.joining(",")));
    }

    @LocalServerPort private int port;
    @Autowired private CoreDatabase database;
    @Autowired private ObjectMapper json;
    @Autowired private SessionTokens sessions;
    @Autowired private WorkflowDispatchRepository dispatches;
    @Autowired private WorkflowCallbackRepository callbacks;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();

    static Stream<Arguments> operations() {
        return OPERATIONS.stream()
                .flatMap(operation -> Stream.of(Arguments.of(operation, false), Arguments.of(operation, true)));
    }

    @ParameterizedTest
    @MethodSource("operations")
    void 五项显式及自然HTTP请求同Run生成复审并仅在作者批准后写入(String operation, boolean natural) throws Exception {
        Fixture fixture = fixture(operation, natural);
        String requestId = "structured-start-" + UUID.randomUUID();
        Map<String, Object> body = new LinkedHashMap<>(Map.of("workflow", "long_serial", "novelId", fixture.novel(),
                "chapterId", fixture.chapter(), "writingSessionId", fixture.session(), "clientRequestId", requestId,
                "targetWordCount", 4000, "userInstruction", "请" + operation + "，保留完整原始内容😀"));
        String scope = "manage_foreshadowing".equals(operation) ? "chapter" : "novel";
        if (natural) body.put("inputMode", "natural");
        else {
            body.put("operation", operation);
            body.put("target", Map.of("type", "chapter", "id", fixture.chapter()));
            body.put("scope", scope.equals("novel") ? Map.of("kind", "novel") : Map.of("kind", "chapter", "chapterId", fixture.chapter()));
        }
        JsonNode started = send(fixture, "POST", "/api/v1/writing/runs", body, 202);
        String runId = started.path("runId").asText();
        assertThat(started.path("engineVersion").asInt()).isEqualTo(2);
        assertThat(send(fixture, "POST", "/api/v1/writing/runs", body, 202).path("runId").asText()).isEqualTo(runId);
        ExecutionStepRequest step = claim(runId);
        if (natural) {
            assertThat(step.getPurpose()).isEqualTo("resolve_intent");
            var result = result(step, ExecutionStepResult.ResultKindEnum.PROPOSED_COMMAND)
                    .proposedCommand(new ProposedCommand(new BigDecimal("0.99")).workflow("long_serial").operation(operation));
            finish(result);
            step = claim(runId);
            assertThat(database.dsl().fetchOne("SELECT operation, \"targetType\", \"targetId\" FROM public.\"WorkflowRun\" WHERE id = ?", runId))
                    .satisfies(run -> {
                        assertThat(run.get("operation")).isNull();
                        assertThat(run.get("targetType", String.class)).isEqualTo("chapter");
                        assertThat(run.get("targetId", String.class)).isEqualTo(fixture.chapter());
                    });
        }
        assertThat(step.getOperation()).isEqualTo(operation);
        assertThat(step.getPurpose()).isEqualTo("generation");
        if (operation.equals("revise_lore") || operation.equals("revise_outline")) {
            String type = operation.equals("revise_lore") ? "character" : "outline_node";
            String id = operation.equals("revise_lore") ? fixture.character() : fixture.node();
            var need = new cn.inkforge.contracts.api.EvidenceExpansionItem("target", id, type);
            List<Map<String, Object>> needs = List.of(Map.of("resourceType", type, "resourceId", id, "purposeCode", "target"));
            String expansionId = "evidence-" + ExecutionCanonicalJson.sha256(Map.of("stepId", step.getStepId(),
                    "requestHash", step.getRequestHash(), "items", needs)).substring(0, 32);
            var expansion = new cn.inkforge.contracts.api.EvidenceExpansionRequest(List.of(need), step.getBudget().getMaxInputTokens() * 4,
                    "agent_updates_sources_required", expansionId, step.getEvidenceBundle().getId(), step.getEvidenceBundle().getVersion());
            finish(result(step, ExecutionStepResult.ResultKindEnum.EVIDENCE_EXPANSION).evidenceExpansion(expansion));
            step = claim(runId);
        }
        Map<String, Object> updates = updates(operation, fixture);
        finish(result(step, ExecutionStepResult.ResultKindEnum.OUTPUT).output(Map.of("summary", "完整结构化建议😀",
                "updates", updates, "updatesSha256", ExecutionCanonicalJson.sha256(updates))));
        ExecutionStepRequest review = claim(runId);
        assertThat(review.getPurpose()).isEqualTo("review");
        assertThat(json.valueToTree(review.getInput().get("task")).path("scope").path("kind").asText()).isEqualTo(scope);
        assertThat(review.getEvidenceBundle().getId()).isEqualTo(step.getEvidenceBundle().getId());
        var evaluation = new EvidenceEvaluation(EvidenceEvaluation.ContentVerdictEnum.PASS, "evaluation-" + review.getStepId(),
                json.convertValue(review.getModelProfile(), ModelProfileRef.class), review.getEvidenceBundle().getId(),
                EvidenceEvaluation.ExecutionStatusEnum.COMPLETED, resolved(review),
                json.valueToTree(review.getInput().get("task")).path("rubricVersion").asText(), runId, review.getStepId())
                .artifactId(review.getArtifactId()).artifactRevision(review.getArtifactRevision()).findings(List.of());
        finish(result(review, ExecutionStepResult.ResultKindEnum.EVALUATION).evaluation(evaluation));
        JsonNode waiting = send(fixture, "GET", "/api/v1/writing/runs/" + runId, null, 200);
        assertThat(waiting.path("status").asText()).isEqualTo("waiting_user");
        assertThat(waiting.path("operation").asText()).isEqualTo(operation);
        String artifact = review.getArtifactId();
        JsonNode detail = send(fixture, "GET", "/api/v1/review-artifacts/" + artifact + "?revision=1", null, 200);
        assertThat(detail.path("sourceBindingStatus").asText()).isEqualTo("verified");
        assertThat(detail.path("payload").path("kind").asText()).isEqualTo("agent_updates");
        assertThat(detail.path("diff").isArray()).isTrue();
        assertBefore(fixture);
        Map<String, Object> decision = new LinkedHashMap<>(Map.of("clientRequestId", "approve-" + requestId,
                "engineVersion", 2, "expectedRevision", 1, "decision", "approve"));
        if (operation.equals("create_lore")) decision.put("selectedUpdateRefs", List.of(Map.of("section", "characters", "index", 1)));
        JsonNode approved = send(fixture, "POST", "/api/v1/review-artifacts/" + artifact + "/decision", decision, 202);
        assertThat(approved.path("status").asText()).isEqualTo("completed");
        assertThat(send(fixture, "POST", "/api/v1/review-artifacts/" + artifact + "/decision", decision, 202)).isEqualTo(approved);
        assertThat(send(fixture, "GET", "/api/v1/writing/runs/" + runId, null, 200).path("status").asText()).isEqualTo("completed");
        assertApplied(operation, fixture);
        assertThat(database.dsl().fetchOne("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"novelId\" = ?", fixture.novel()).get(0, Long.class)).isEqualTo(1);
        assertThat(database.dsl().fetchOne("SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?", fixture.novel()).get(0, Long.class)).isZero();
    }

    private Map<String, Object> updates(String operation, Fixture fixture) {
        return switch (operation) {
            case "create_lore" -> Map.of("characters", List.of(Map.of("action", "create", "name", "作者未选人物"),
                    Map.of("action", "create", "name", "作者选中人物", "background", "保留全文😀\n")));
            case "revise_lore" -> Map.of("characters", List.of(Map.of("action", "update", "id", fixture.character(), "background", "新版人物经历😀\n")));
            case "create_outline" -> Map.of("outlineContent", "新版总纲😀\n");
            case "revise_outline" -> Map.of("outlineAdjustments", List.of(Map.of("action", "update", "nodeId", fixture.node(), "content", "新版节点内容😀\n")));
            case "manage_foreshadowing" -> Map.of("foreshadowing", List.of(Map.of("action", "create", "name", "待回收伏笔", "plantedContent", "原始伏笔建议😀\n")));
            default -> throw new IllegalArgumentException(operation);
        };
    }

    private void assertBefore(Fixture f) {
        assertThat(database.dsl().fetchOne("SELECT count(*) FROM public.\"Character\" WHERE \"novelId\" = ?", f.novel()).get(0, Long.class)).isEqualTo(1);
        assertThat(database.dsl().fetchOne("SELECT background FROM public.\"Character\" WHERE id = ?", f.character()).get(0, String.class)).isEqualTo("旧人物经历");
        assertThat(database.dsl().fetchOne("SELECT content FROM public.\"Outline\" WHERE \"novelId\" = ?", f.novel()).get(0, String.class)).isEqualTo("旧总纲");
        assertThat(database.dsl().fetchOne("SELECT content FROM public.\"OutlineNode\" WHERE id = ?", f.node()).get(0, String.class)).isEqualTo("旧节点");
        assertThat(database.dsl().fetchOne("SELECT count(*) FROM public.\"Foreshadowing\" WHERE \"novelId\" = ?", f.novel()).get(0, Long.class)).isZero();
    }

    private void assertApplied(String operation, Fixture f) {
        switch (operation) {
            case "create_lore" -> {
                assertThat(database.dsl().fetchOne("SELECT count(*) FROM public.\"Character\" WHERE \"novelId\" = ? AND name = '作者未选人物'", f.novel()).get(0, Long.class)).isZero();
                assertThat(database.dsl().fetchOne("SELECT background FROM public.\"Character\" WHERE \"novelId\" = ? AND name = '作者选中人物'", f.novel()).get(0, String.class)).isEqualTo("保留全文😀\n");
            }
            case "revise_lore" -> assertThat(database.dsl().fetchOne("SELECT background FROM public.\"Character\" WHERE id = ?", f.character()).get(0, String.class)).isEqualTo("新版人物经历😀\n");
            case "create_outline" -> assertThat(database.dsl().fetchOne("SELECT content FROM public.\"Outline\" WHERE \"novelId\" = ?", f.novel()).get(0, String.class)).isEqualTo("新版总纲😀\n");
            case "revise_outline" -> assertThat(database.dsl().fetchOne("SELECT content FROM public.\"OutlineNode\" WHERE id = ?", f.node()).get(0, String.class)).isEqualTo("新版节点内容😀\n");
            case "manage_foreshadowing" -> assertThat(database.dsl().fetchOne("SELECT count(*) FROM public.\"Foreshadowing\" WHERE \"novelId\" = ? AND name = '待回收伏笔'", f.novel()).get(0, Long.class)).isEqualTo(1);
            default -> throw new IllegalArgumentException(operation);
        }
    }

    private ExecutionStepRequest claim(String runId) {
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(runId);
        ResolvedModelRef resolved = resolved(request);
        dispatches.recordAccepted(request, new ExecutionStepAccepted(OffsetDateTime.now(ZoneOffset.UTC), request.getFencingToken(), request.getJobId(),
                request.getNovelId(), "2.0", request.getRequestHash(), json.convertValue(resolved, cn.inkforge.contracts.agent.ResolvedModelRef.class),
                runId, ExecutionStepAccepted.StatusEnum.ACCEPTED, request.getStepId()));
        var preparing = new ExecutionStepProgress(0, request.getFencingToken(), request.getJobId(), request.getNovelId(), OffsetDateTime.now(ZoneOffset.UTC),
                ExecutionStepProgress.PhaseEnum.PREPARING, "preparing", "progress-" + request.getJobId(), "2.0", request.getRequestHash(), resolved,
                runId, 1, request.getStepId(), new StepUsage(0, 0, StepUsage.UsageStatusEnum.UNKNOWN, 0), false);
        assertThat(callbacks.progress(preparing).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        return request;
    }

    private ExecutionStepResult result(ExecutionStepRequest request, ExecutionStepResult.ResultKindEnum kind) {
        StepUsage usage = new StepUsage(0, 1, StepUsage.UsageStatusEnum.COMPLETE, 100)
                .inputTokens(100).cachedTokens(0).promptCacheMissTokens(100).completionTokens(20).reasoningTokens(0).visibleOutputTokens(20).costMicros(0);
        return new ExecutionStepResult(OffsetDateTime.now(ZoneOffset.UTC), request.getFencingToken(), request.getInputHash(), request.getJobId(),
                request.getNovelId(), "2.0", request.getRequestHash(), resolved(request), "0".repeat(64), kind, request.getRunId(), request.getStepId(), usage);
    }

    private void finish(ExecutionStepResult result) {
        result.setResultHash(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resultHashMaterial(result)));
        assertThat(callbacks.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.result(result).getStatus()).isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
    }

    private ResolvedModelRef resolved(ExecutionStepRequest request) {
        String deployment = request.getModelProfile().getDeploymentProfileKey();
        String reasoning = request.getModelProfile().getReasoningMode().getValue();
        String fingerprint = WorkflowResolvedModel.fingerprint(deployment, "fake", "fake", "transport.fake.v1", "endpoint.local-fake.v1",
                "responses_json_schema_v1", "capability.fake.structured-output.v1", reasoning, true);
        return new ResolvedModelRef("capability.fake.structured-output.v1", fingerprint, deployment, "endpoint.local-fake.v1", "fake", "fake",
                ResolvedModelRef.ReasoningModeEnum.fromValue(reasoning), ResolvedModelRef.StructuredOutputRouteEnum.RESPONSES_JSON_SCHEMA_V1, true, "transport.fake.v1");
    }

    private JsonNode send(Fixture fixture, String method, String path, Object body, int expected) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path)).timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json").header("Cookie", IdentityController.COOKIE_NAME + "=" + sessions.create(fixture.user()));
        var response = http.send(builder.method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).as(response.body()).isEqualTo(expected);
        return json.readTree(response.body());
    }

    private static String novelId(String operation, boolean natural) {
        return "structured-http-" + operation + (natural ? "-natural" : "-explicit");
    }

    private Fixture fixture(String operation, boolean natural) {
        String id = novelId(operation, natural);
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        database.dsl().execute("INSERT INTO public.\"User\" (id, username, \"passwordHash\", \"creditBalanceMicros\", \"updatedAt\") VALUES (?, ?, 'test-only', 1000000, ?) ON CONFLICT (id) DO NOTHING", TEST_USER, TEST_USER, now);
        database.dsl().execute("INSERT INTO public.\"Novel\" (id, name, \"userId\", \"updatedAt\") VALUES (?, '隔离结构化测试', ?, ?)", id, TEST_USER, now);
        database.dsl().execute("INSERT INTO public.\"WritingBible\" (id, \"novelId\", \"storyLengthProfile\", \"updatedAt\") VALUES (?, ?, 'long_serial', ?)", id, id, now);
        database.dsl().execute("INSERT INTO public.\"Chapter\" (id, \"novelId\", title, content, \"order\", status, \"updatedAt\") VALUES (?, ?, '第一章', '原章正文不得被资料采用覆盖', 1, 'drafting', ?)", id, id, now);
        database.dsl().execute("INSERT INTO public.\"WritingSession\" (id, \"novelId\", \"chapterId\", phase, \"updatedAt\") VALUES (?, ?, ?, 'idle', ?)", id, id, id, now);
        database.dsl().execute("INSERT INTO public.\"Outline\" (id, \"novelId\", content, \"updatedAt\") VALUES (?, ?, '旧总纲', ?)", id, id, now);
        database.dsl().execute("INSERT INTO public.\"OutlineNode\" (id, \"novelId\", kind, title, content, \"order\", \"updatedAt\") VALUES (?, ?, 'stage', '第一阶段', '旧节点', 1, ?)", id, id, now);
        database.dsl().execute("INSERT INTO public.\"Character\" (id, \"novelId\", name, background, \"updatedAt\") VALUES (?, ?, '旧人物', '旧人物经历', ?)", id, id, now);
        return new Fixture(TEST_USER, id, id, id, id, id);
    }

    private record Fixture(String user, String novel, String chapter, String session, String character, String node) {}

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalExecutionConfiguration {
        @Bean @Primary DurableAgentExecutionReadiness testStructuredReadiness() { return () -> true; }
    }
}
