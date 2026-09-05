package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.contracts.api.ExecutionCallbackReceipt;
import cn.inkforge.contracts.api.ExecutionStepProgress;
import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.contracts.api.ResolvedModelRef;
import cn.inkforge.contracts.api.StepUsage;
import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.identity.api.IdentityController;
import cn.inkforge.core.identity.domain.SessionTokens;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.workflows.application.WorkflowCallbackRepository;
import cn.inkforge.core.workflows.application.WorkflowDispatchRepository;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.writing.application.DurableAgentExecutionReadiness;
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
import org.junit.jupiter.api.Test;
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

/** 四项中短篇从公共 HTTP 到真实耐久回调、权威查询及版本采用的隔离闭环。 */
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(
        classes = {
            CoreApplication.class,
            WorkflowV2SseHttpIntegrationTest.TestIdentityConfiguration.class,
            ShortMediumDurableHttpIntegrationTest.LocalExecutionConfiguration.class
        },
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ShortMediumDurableHttpIntegrationTest {

    private static final String TEST_USER = "short-medium-http-author";
    private static final List<String> OPERATIONS = List.of(
            "generate_outline",
            "generate_manuscript",
            "replace_selection",
            "full_check");
    private static final String OUTLINE_BASE = "开头😀旧片段结尾";
    private static final String MANUSCRIPT_BASE = "旧正文😀\r\n尾部";

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("isolated-test-only")
                    .withCopyFileToContainer(
                            MountableFile.forClasspathResource(
                                    "db/novelwriterdev-schema.sql", 0644),
                            "/docker-entrypoint-initdb.d/01-schema.sql")
                    .withCopyFileToContainer(
                            MountableFile.forClasspathResource(
                                    "migrations/20260831_durable_agent_execution.sql", 0644),
                            "/docker-entrypoint-initdb.d/02-durable-agent.sql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add(
                "DATABASE_URL",
                () -> "postgresql://"
                        + POSTGRES.getUsername()
                        + ":"
                        + POSTGRES.getPassword()
                        + "@"
                        + POSTGRES.getHost()
                        + ":"
                        + POSTGRES.getMappedPort(5432)
                        + "/"
                        + POSTGRES.getDatabaseName());
        properties.add("REDIS_URL", () -> "false");
        properties.add(
                "JWT_SECRET", () -> "中短篇耐久HTTP隔离测试专用密钥-不可用于生产环境");
        properties.add("ENVIRONMENT", () -> "test");
        properties.add("VIDEO_PREVIEW_ENABLED", () -> "false");
        properties.add("DURABLE_AGENT_EXECUTION_SCHEMA_READY", () -> "true");
        properties.add("DURABLE_AGENT_EXECUTION_ROUTE_MODE", () -> "allowlist");
        properties.add("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", () -> TEST_USER);
        properties.add(
                "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST",
                () -> Stream.concat(
                                OPERATIONS.stream(),
                                Stream.of("dirty-completion", "cancel", "legacy-quality-isolation"))
                        .map(ShortMediumDurableHttpIntegrationTest::novelId)
                        .collect(java.util.stream.Collectors.joining(",")));
    }

    @LocalServerPort
    private int port;

    @Autowired
    private CoreDatabase database;

    @Autowired
    private ObjectMapper json;

    @Autowired
    private SessionTokens sessions;

    @Autowired
    private WorkflowDispatchRepository dispatches;

    @Autowired
    private WorkflowCallbackRepository callbacks;

    @Autowired
    private cn.inkforge.core.quality.application.QualityRepository legacyQuality;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    static Stream<Arguments> operations() {
        return Stream.of(
                Arguments.of("generate_outline", "outline", 1),
                Arguments.of("generate_manuscript", "manuscript", 2),
                Arguments.of("replace_selection", "outline", 1),
                Arguments.of("full_check", "manuscript", 1));
    }

    @ParameterizedTest
    @MethodSource("operations")
    void 四项HTTP启动回调查询与版本生命周期闭环(
            String operation, String documentType, int segmentCount) throws Exception {
        Fixture fixture = fixture(operation);
        String startRequestId = "short-http-start-" + UUID.randomUUID();
        Map<String, Object> startBody = startBody(
                fixture, operation, documentType, startRequestId);
        JsonNode started = send("POST", "/api/v1/writing/runs", startBody, 202);
        String runId = started.path("runId").asText();
        assertThat(started.path("engineVersion").asInt()).isEqualTo(2);
        assertThat(started.path("operation").asText()).isEqualTo(operation);
        assertThat(send("POST", "/api/v1/writing/runs", startBody, 202)
                        .path("runId")
                        .asText())
                .isEqualTo(runId);

        String expectedText = complete(runId, operation, segmentCount);
        JsonNode completed = send("GET", "/api/v1/writing/runs/" + runId, null, 200);
        assertThat(completed.path("status").asText()).isEqualTo("completed");
        assertThat(completed.path("operation").asText()).isEqualTo(operation);
        assertThat(completed.path("currentStep").isNull()).isTrue();

        if ("full_check".equals(operation)) {
            assertThat(completed.has("candidateVersionId")).isFalse();
            assertThat(completed.path("checkReport").path("text").asText())
                    .isEqualTo(expectedText);
            assertThat(count(
                            "SELECT count(*) FROM public.\"ReviewArtifact\" "
                                    + "WHERE \"workflowRunId\" = ?",
                            runId))
                    .isZero();
            JsonNode preview = preview(fixture, documentType, fixture.manuscriptVersionId());
            assertThat(preview.path("baseVersionId").asText())
                    .isEqualTo(fixture.manuscriptVersionId());
        } else {
            assertThat(completed.has("checkReport")).isFalse();
            String candidateId = completed.path("candidateVersionId").asText();
            assertThat(candidateId).isNotBlank();
            String baseVersionId = "manuscript".equals(documentType)
                    ? fixture.manuscriptVersionId()
                    : fixture.outlineVersionId();
            JsonNode preview = preview(fixture, documentType, baseVersionId);
            assertThat(preview.path("baseVersionId").asText())
                    .isEqualTo(baseVersionId);
            JsonNode candidate = send(
                    "GET",
                    "/api/v1/novels/"
                            + fixture.novelId()
                            + "/versions/"
                            + candidateId,
                    null,
                    200);
            assertThat(candidate.path("content").asText()).isEqualTo(expectedText);
            assertThat(candidate.path("status").asText()).isEqualTo("awaiting_user");
            assertThat(database.dsl().fetchOne(
                            "SELECT \"taskId\", \"workflowRunId\" "
                                    + "FROM public.\"ReviewArtifact\" WHERE id = ?",
                            candidateId))
                    .satisfies(row -> {
                        assertThat(row.get("taskId")).isNull();
                        assertThat(row.get("workflowRunId", String.class)).isEqualTo(runId);
                    });
            Map<String, Object> adoption = new LinkedHashMap<>();
            adoption.put("clientRequestId", "short-http-adopt-" + UUID.randomUUID());
            adoption.put("documentType", documentType);
            if ("manuscript".equals(documentType)) {
                adoption.put("chapterId", fixture.chapterId());
            }
            adoption.put("baseVersionId", baseVersionId);
            adoption.put(
                    "confirmationHash",
                    candidate.path("diff").path("confirmationHash").asText());
            String path = "/api/v1/novels/"
                    + fixture.novelId()
                    + "/versions/"
                    + candidateId
                    + "/adopt";
            JsonNode adopted = send("POST", path, adoption, 200);
            assertThat(adopted.path("status").asText()).isEqualTo("applied");
            assertThat(send("POST", path, adoption, 200)).isEqualTo(adopted);
            assertThat(appliedContent(fixture, documentType)).isEqualTo(expectedText);
            assertThat(send("GET", "/api/v1/writing/runs/" + runId, null, 200)
                            .path("status")
                            .asText())
                    .isEqualTo("completed");
            assertThat(count(
                            "SELECT count(*) FROM public.\"WorkflowStep\" "
                                    + "WHERE \"runId\" = ? AND purpose = 'user_decision'",
                            runId))
                    .isEqualTo(1);
        }
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?",
                        fixture.novelId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingRunCommand\" AS command "
                                + "JOIN public.\"WritingTask\" AS task "
                                + "ON task.id = command.\"taskId\" "
                                + "WHERE task.\"novelId\" = ?",
                        fixture.novelId()))
                .isZero();
    }

    @Test
    void 工作稿在模型完成前变化时保留用量并失败且不创建候选() throws Exception {
        Fixture fixture = fixture("dirty-completion");
        JsonNode started = send(
                "POST",
                "/api/v1/writing/runs",
                startBody(
                        fixture,
                        "generate_outline",
                        "outline",
                        "short-http-dirty-start-" + UUID.randomUUID()),
                202);
        String runId = started.path("runId").asText();
        ExecutionStepRequest step = claim(runId);
        String authorEdit = "  作者在运行期间修改的大纲\r\n  ";
        database.dsl().execute(
                "UPDATE public.\"Outline\" SET content = ?, \"updatedAt\" = ? "
                        + "WHERE \"novelId\" = ?",
                authorEdit,
                LocalDateTime.now(ZoneOffset.UTC),
                fixture.novelId());

        ExecutionStepResult terminal = result(step).output(Map.of(
                "content",
                "模型候选大纲",
                "contentSha256",
                ShortMediumText.sha256("模型候选大纲")));
        finish(terminal);

        JsonNode failed = send("GET", "/api/v1/writing/runs/" + runId, null, 200);
        assertThat(failed.path("status").asText()).isEqualTo("failed");
        assertThat(failed.path("error").path("errorCode").asText())
                .isEqualTo("SHORT_MEDIUM_WORK_DRAFT_DIRTY");
        assertThat(failed.has("candidateVersionId")).isFalse();
        assertThat(database.dsl().fetchOne(
                        "SELECT status::text AS status, \"usageJson\", \"resultHash\" "
                                + "FROM public.\"WorkflowStep\" WHERE id = ?",
                        step.getStepId()))
                .satisfies(row -> {
                    assertThat(row.get("status", String.class)).isEqualTo("completed");
                    assertThat(row.get("usageJson", String.class)).isNotBlank();
                    assertThat(row.get("resultHash", String.class))
                            .isEqualTo(terminal.getResultHash());
                });
        assertThat(count(
                        "SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?",
                        runId))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowBillingReservation\" "
                                + "WHERE \"runId\" = ? AND status = 'settled'",
                        runId))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifact\" "
                                + "WHERE \"workflowRunId\" = ?",
                        runId))
                .isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowStep\" "
                                + "WHERE \"runId\" = ? AND purpose = 'short_medium_manifest'",
                        runId))
                .isZero();
        assertThat(appliedContent(fixture, "outline")).isEqualTo(authorEdit);
    }

    @Test
    void 旧一致性终检调度器不能领取或改写中短篇V2全文检查() throws Exception {
        Fixture fixture = fixture("legacy-quality-isolation");
        JsonNode started = send("POST", "/api/v1/writing/runs",
                startBody(fixture, "full_check", "manuscript", "short-legacy-isolation-" + UUID.randomUUID()), 202);
        String runId = started.path("runId").asText();
        assertThat(legacyQuality.listDispatchable(20)).isEmpty();
        assertThat(send("GET", "/api/v1/writing/runs/" + runId, null, 200).path("status").asText())
                .isEqualTo("pending");
        assertThatThrownBy(() -> legacyQuality.markRunning(runId))
                .isInstanceOfSatisfying(cn.inkforge.core.platform.http.ApiException.class,
                        error -> assertThat(error.code()).isEqualTo("QUALITY_RUN_NOT_FOUND"));
        ExecutionStepRequest step = claim(runId);
        assertThat(legacyQuality.listDispatchable(20)).isEmpty();
        assertThat(send("GET", "/api/v1/writing/runs/" + runId, null, 200).path("status").asText())
                .isEqualTo("running");
        finish(result(step).output(Map.of("text", "完整报告", "textSha256", ShortMediumText.sha256("完整报告"))));
        JsonNode completed = send("GET", "/api/v1/writing/runs/" + runId, null, 200);
        assertThat(completed.path("status").asText()).isEqualTo("completed");
        assertThat(completed.path("checkReport").path("text").asText()).isEqualTo("完整报告");
    }

    @Test
    void 公开取消在Provider前立即跳过Step且不创建候选或用量() throws Exception {
        Fixture fixture = fixture("cancel");
        JsonNode started = send(
                "POST",
                "/api/v1/writing/runs",
                startBody(
                        fixture,
                        "generate_outline",
                        "outline",
                        "short-http-cancel-start-" + UUID.randomUUID()),
                202);
        String runId = started.path("runId").asText();
        Map<String, Object> cancelBody =
                Map.of("clientRequestId", "short-http-cancel-" + UUID.randomUUID());

        JsonNode cancelled = send(
                "POST", "/api/v1/writing/runs/" + runId + "/cancel", cancelBody, 202);
        assertThat(cancelled.path("engineVersion").asInt()).isEqualTo(2);
        assertThat(cancelled.path("runId").asText()).isEqualTo(runId);
        assertThat(cancelled.path("status").asText()).isEqualTo("cancelled");
        assertThat(cancelled.path("cancelRequestedAt").asText()).isNotBlank();
        assertThat(cancelled.path("currentStep").isNull()).isTrue();
        assertThat(send(
                        "POST",
                        "/api/v1/writing/runs/" + runId + "/cancel",
                        cancelBody,
                        202))
                .isEqualTo(cancelled);
        assertThat(send("GET", "/api/v1/writing/runs/" + runId, null, 200))
                .isEqualTo(cancelled);

        assertThat(database.dsl().fetchOne(
                        "SELECT status::text AS status, \"errorCode\", \"cancelRequestId\" "
                                + "FROM public.\"WorkflowRun\" WHERE id = ?",
                        runId))
                .satisfies(row -> {
                    assertThat(row.get("status", String.class)).isEqualTo("cancelled");
                    assertThat(row.get("errorCode", String.class)).isEqualTo("RUN_CANCELLED");
                    assertThat(row.get("cancelRequestId", String.class))
                            .isEqualTo(cancelBody.get("clientRequestId"));
                });
        assertThat(database.dsl().fetchOne(
                        "SELECT status::text AS status, \"errorCode\", \"usageJson\", "
                                + "\"resultHash\" FROM public.\"WorkflowStep\" "
                                + "WHERE \"runId\" = ? AND purpose = 'generation'",
                        runId))
                .satisfies(row -> {
                    assertThat(row.get("status", String.class)).isEqualTo("skipped");
                    assertThat(row.get("errorCode", String.class)).isEqualTo("RUN_CANCELLED");
                    assertThat(row.get("usageJson")).isNull();
                    assertThat(row.get("resultHash")).isNull();
                });
        assertThat(count(
                        "SELECT count(*) FROM public.\"TokenUsage\" WHERE \"runId\" = ?",
                        runId))
                .isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"ReviewArtifact\" "
                                + "WHERE \"workflowRunId\" = ?",
                        runId))
                .isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowStep\" "
                                + "WHERE \"runId\" = ? AND purpose = 'short_medium_manifest'",
                        runId))
                .isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?",
                        fixture.novelId()))
                .isZero();
    }

    private String complete(String runId, String operation, int segmentCount) {
        StringBuilder expected = new StringBuilder();
        String previousStepId = null;
        for (int index = 0; index < segmentCount; index++) {
            ExecutionStepRequest step = claim(runId);
            assertThat(step.getOperation()).isEqualTo(operation);
            assertThat(step.getPurpose()).isEqualTo("generation");
            assertThat(step.getInput())
                    .containsEntry("segmentIndex", index)
                    .containsEntry("segmentCount", segmentCount);
            if (index == 0) {
                assertThat(step.getEvidenceBundle().getItems()).hasSize(1);
                assertThat(step.getEvidenceBundle().getItems().getFirst().getResourceType())
                        .isEqualTo("short_medium_context");
            } else {
                assertThat(step.getEvidenceBundle().getItems()).hasSize(index + 1);
                var prefix = step.getEvidenceBundle().getItems().get(index);
                assertThat(prefix.getResourceType()).isEqualTo("short_medium_segment");
                assertThat(prefix.getResourceId()).isEqualTo(previousStepId);
                assertThat(json.valueToTree(prefix.getContentJson()).path("index").asInt())
                        .isEqualTo(index - 1);
                assertThat(json.valueToTree(prefix.getContentJson()).path("content").asText())
                        .isEqualTo(expected.toString());
            }
            String key;
            String text;
            if ("generate_manuscript".equals(operation)) {
                key = "content";
                text = (index == 0 ? "甲" : "乙").repeat(index == 0 ? 3_000 : 3_001);
            } else if ("generate_outline".equals(operation)) {
                key = "content";
                text = "  新大纲😀\r\n尾部  ";
            } else if ("replace_selection".equals(operation)) {
                key = "replacement";
                text = "新片段😀\n";
            } else {
                key = "text";
                text = "  完整检查报告😀\r\n尾部  ";
            }
            finish(result(step).output(Map.of(
                    key,
                    text,
                    key + "Sha256",
                    ShortMediumText.sha256(text))));
            expected.append(text);
            previousStepId = step.getStepId();
        }
        JsonNode manifest = json.readTree(database.dsl()
                .fetchOne(
                        "SELECT input FROM public.\"WorkflowStep\" "
                                + "WHERE \"runId\" = ? AND purpose = 'short_medium_manifest'",
                        runId)
                .get("input", String.class));
        assertThat(manifest.path("segmentCount").asInt()).isEqualTo(segmentCount);
        assertThat(manifest.path("segments").size()).isEqualTo(segmentCount);
        assertThat(manifest.path("contentSha256").asText())
                .isEqualTo(ShortMediumText.sha256(expected.toString()));
        if ("replace_selection".equals(operation)) {
            return "开头😀" + expected + "结尾";
        }
        return expected.toString();
    }

    private ExecutionStepRequest claim(String runId) {
        ExecutionStepRequest request = dispatches.claimNext().orElseThrow();
        assertThat(request.getRunId()).isEqualTo(runId);
        ResolvedModelRef resolved = resolved(request);
        dispatches.recordAccepted(
                request,
                new ExecutionStepAccepted(
                        OffsetDateTime.now(ZoneOffset.UTC),
                        request.getFencingToken(),
                        request.getJobId(),
                        request.getNovelId(),
                        "2.0",
                        request.getRequestHash(),
                        json.convertValue(
                                resolved,
                                cn.inkforge.contracts.agent.ResolvedModelRef.class),
                        runId,
                        ExecutionStepAccepted.StatusEnum.ACCEPTED,
                        request.getStepId()));
        var progress = new ExecutionStepProgress(
                0,
                request.getFencingToken(),
                request.getJobId(),
                request.getNovelId(),
                OffsetDateTime.now(ZoneOffset.UTC),
                ExecutionStepProgress.PhaseEnum.PREPARING,
                "preparing",
                "progress-" + request.getJobId(),
                "2.0",
                request.getRequestHash(),
                resolved,
                runId,
                1,
                request.getStepId(),
                new StepUsage(0, 0, StepUsage.UsageStatusEnum.UNKNOWN, 0),
                false);
        assertThat(callbacks.progress(progress).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        return request;
    }

    private ExecutionStepResult result(ExecutionStepRequest request) {
        StepUsage usage = new StepUsage(0, 1, StepUsage.UsageStatusEnum.COMPLETE, 100)
                .inputTokens(100)
                .cachedTokens(0)
                .promptCacheMissTokens(100)
                .completionTokens(20)
                .reasoningTokens(0)
                .visibleOutputTokens(20)
                .costMicros(0);
        return new ExecutionStepResult(
                OffsetDateTime.now(ZoneOffset.UTC),
                request.getFencingToken(),
                request.getInputHash(),
                request.getJobId(),
                request.getNovelId(),
                "2.0",
                request.getRequestHash(),
                resolved(request),
                "0".repeat(64),
                ExecutionStepResult.ResultKindEnum.OUTPUT,
                request.getRunId(),
                request.getStepId(),
                usage);
    }

    private void finish(ExecutionStepResult result) {
        result.setResultHash(ExecutionCanonicalJson.sha256(
                WorkflowCallbackValues.resultHashMaterial(result)));
        assertThat(callbacks.result(result).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        assertThat(callbacks.result(result).getStatus())
                .isEqualTo(ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
    }

    private static ResolvedModelRef resolved(ExecutionStepRequest request) {
        String deployment = request.getModelProfile().getDeploymentProfileKey();
        String reasoning = request.getModelProfile().getReasoningMode().getValue();
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
        return new ResolvedModelRef().capabilityVersion("capability.fake.structured-output.v1")
                .deploymentFingerprint(fingerprint).deploymentProfileKey(deployment).endpointProfile("endpoint.local-fake.v1")
                .model("fake").provider("fake").reasoningMode(ResolvedModelRef.ReasoningModeEnum.fromValue(reasoning))
                .structuredOutputRoute(ResolvedModelRef.StructuredOutputRouteEnum.RESPONSES_JSON_SCHEMA_V1)
                .supportsRequestIdempotency(true).transportProfile("transport.fake.v1");
    }

    private JsonNode preview(Fixture fixture, String documentType, String baseVersionId)
            throws Exception {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("documentType", documentType);
        if ("manuscript".equals(documentType)) body.put("chapterId", fixture.chapterId());
        body.put("baseVersionId", baseVersionId);
        return send(
                "POST",
                "/api/v1/novels/" + fixture.novelId() + "/versions/preview",
                body,
                200);
    }

    private Map<String, Object> startBody(
            Fixture fixture,
            String operation,
            String documentType,
            String clientRequestId) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("clientRequestId", clientRequestId);
        body.put("workflow", "short_medium");
        body.put("novelId", fixture.novelId());
        body.put("operation", operation);
        body.put("documentType", documentType);
        if ("manuscript".equals(documentType)) body.put("chapterId", fixture.chapterId());
        body.put(
                "baseVersionId",
                "manuscript".equals(documentType)
                        ? fixture.manuscriptVersionId()
                        : fixture.outlineVersionId());
        if ("generate_manuscript".equals(operation)) {
            body.put("sourceOutlineVersionId", fixture.outlineVersionId());
        }
        if ("replace_selection".equals(operation)) {
            body.put("selectionStart", 3);
            body.put("selectionEnd", 6);
            body.put("selectedTextHash", ShortMediumText.sha256("旧片段"));
        }
        body.put("userInstruction", "  保留完整请求😀\r\n尾部  ");
        return body;
    }

    private Fixture fixture(String operation) {
        String novelId = novelId(operation);
        String chapterId = novelId + "-chapter";
        String outlineVersionId = novelId + "-outline-version";
        String manuscriptVersionId = novelId + "-manuscript-version";
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        database.dsl().execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "updatedAt"
                ) VALUES (?, ?, 'test-only', 10000000, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                TEST_USER,
                TEST_USER,
                now);
        database.dsl().execute(
                "INSERT INTO public.\"Novel\" (id, name, \"userId\", \"updatedAt\") "
                        + "VALUES (?, '隔离中短篇测试', ?, ?)",
                novelId,
                TEST_USER,
                now);
        database.dsl().execute(
                "INSERT INTO public.\"WritingBible\" "
                        + "(id, \"novelId\", \"storyLengthProfile\", "
                        + "\"targetTotalWordCount\", \"updatedAt\") "
                        + "VALUES (?, ?, 'short_medium', 15001, ?)",
                novelId,
                novelId,
                now);
        database.dsl().execute(
                "INSERT INTO public.\"Chapter\" "
                        + "(id, \"novelId\", title, content, \"order\", status, \"updatedAt\") "
                        + "VALUES (?, ?, '全文', ?, 1, 'drafting', ?)",
                chapterId,
                novelId,
                MANUSCRIPT_BASE,
                now);
        database.dsl().execute(
                "INSERT INTO public.\"Outline\" (id, \"novelId\", content, \"updatedAt\") "
                        + "VALUES (?, ?, ?, ?)",
                novelId + "-outline",
                novelId,
                OUTLINE_BASE,
                now);
        database.dsl().execute(
                """
                INSERT INTO public."ReviewArtifact" (
                  id, "novelId", "artifactKey", kind, status, "payloadJson",
                  revision, "createdAt", "updatedAt", "appliedAt"
                ) VALUES (?, ?, ?, 'freeform_markdown', 'applied', ?, 1, ?, ?, ?)
                """,
                novelId + "-source",
                novelId,
                "short-medium:source:" + novelId,
                json.writeValueAsString(Map.of(
                        "sourceKind", "idea",
                        "sourceText", "  起始素材😀\r\n尾部  ")),
                now,
                now,
                now);
        insertAppliedVersion(
                novelId,
                null,
                outlineVersionId,
                "outline",
                OUTLINE_BASE,
                null,
                now);
        insertAppliedVersion(
                novelId,
                chapterId,
                manuscriptVersionId,
                "manuscript",
                MANUSCRIPT_BASE,
                outlineVersionId,
                now);
        return new Fixture(
                novelId, chapterId, outlineVersionId, manuscriptVersionId);
    }

    private void insertAppliedVersion(
            String novelId,
            String chapterId,
            String versionId,
            String documentType,
            String content,
            String sourceOutlineVersionId,
            LocalDateTime now) {
        ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                "outline".equals(documentType) ? "outline_draft" : "chapter_draft",
                documentType,
                1,
                null,
                documentType + "-base-manual-request-0001",
                "manual",
                content,
                ShortMediumText.sha256(content),
                null,
                null,
                sourceOutlineVersionId,
                "基础版本",
                null,
                null,
                null,
                false,
                null,
                null,
                null);
        database.dsl().execute(
                """
                INSERT INTO public."ReviewArtifact" (
                  id, "novelId", "chapterId", "artifactKey", kind, status,
                  "summary", "payloadJson", revision, "createdAt", "updatedAt", "appliedAt"
                ) VALUES (?, ?, ?, ?, CAST(? AS public."ReviewArtifactKind"),
                  'applied', '基础版本', ?, 1, ?, ?, ?)
                """,
                versionId,
                novelId,
                chapterId,
                "outline".equals(documentType)
                        ? "short-medium:outline:" + novelId
                        : "short-medium:manuscript:" + chapterId,
                "outline".equals(documentType) ? "outline_draft" : "chapter_draft",
                json.writeValueAsString(payload),
                now,
                now,
                now);
    }

    private String appliedContent(Fixture fixture, String documentType) {
        if ("outline".equals(documentType)) {
            return database.dsl()
                    .fetchOne(
                            "SELECT content FROM public.\"Outline\" WHERE \"novelId\" = ?",
                            fixture.novelId())
                    .get("content", String.class);
        }
        return database.dsl()
                .fetchOne(
                        "SELECT content FROM public.\"Chapter\" WHERE id = ?",
                        fixture.chapterId())
                .get("content", String.class);
    }

    private JsonNode send(String method, String path, Object body, int expected)
            throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header(
                        "Cookie",
                        IdentityController.COOKIE_NAME + "=" + sessions.create(TEST_USER));
        HttpResponse<String> response = http.send(
                request.method(
                                method,
                                body == null
                                        ? HttpRequest.BodyPublishers.noBody()
                                        : HttpRequest.BodyPublishers.ofString(
                                                json.writeValueAsString(body)))
                        .build(),
                HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).as(response.body()).isEqualTo(expected);
        return json.readTree(response.body());
    }

    private long count(String statement, Object... bindings) {
        return database.dsl().fetchOne(statement, bindings).get(0, Long.class);
    }

    private static String novelId(String operation) {
        return "short-http-" + operation.replace('_', '-');
    }

    private record Fixture(
            String novelId,
            String chapterId,
            String outlineVersionId,
            String manuscriptVersionId) {}

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalExecutionConfiguration {

        @Bean
        @Primary
        DurableAgentExecutionReadiness testShortMediumReadiness() {
            return () -> true;
        }

        @Bean
        @Primary
        ExecutionRegistry testShortMediumRegistry() {
            return ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        }
    }
}
