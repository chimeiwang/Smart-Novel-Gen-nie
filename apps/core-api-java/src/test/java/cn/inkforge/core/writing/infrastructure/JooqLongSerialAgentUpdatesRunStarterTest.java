package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ChapterScope;
import cn.inkforge.contracts.api.ChapterTarget;
import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.NaturalStartWritingRunRequest;
import cn.inkforge.contracts.api.NovelScope;
import cn.inkforge.contracts.api.OutlineNodeScope;
import cn.inkforge.contracts.api.Scope;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.reviews.infrastructure.JooqAgentUpdatesEvidenceReader;
import cn.inkforge.core.reviews.infrastructure.JooqChapterPlanEvidenceReader;
import cn.inkforge.core.reviews.infrastructure.JooqChapterWritingEvidenceReader;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowIntentBusinessPreparation;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowExecutionContextReader;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
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
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqLongSerialAgentUpdatesRunStarterTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-05T14:00:00.000");
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-05T14:00:00Z"), ZoneOffset.UTC);
    private static final String OUTLINE_CONTENT = "  总纲全文😀\r\n尾部  ";
    private static final String WORLD_SETTING = "  世界设定全文😀\r\n尾部  ";
    private static final String STORY_BACKGROUND = "  故事背景全文😀\r\n尾部  ";

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static CuidV1Generator ids;

    @BeforeAll
    static void rebuildSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("migrations/20260831_durable_agent_execution.sql"),
                "/tmp/20260831_durable_agent_execution.sql");
        executeSql("/tmp/novelwriterdev-schema.sql");
        executeSql("/tmp/20260831_durable_agent_execution.sql");
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        json = JsonMapper.builder().addModule(new JsonNullableJackson3Module()).build();
        ids = new CuidV1Generator(CLOCK);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @ParameterizedTest
    @MethodSource("novelScopeOperations")
    void 五项小说范围启动保存严格输入与各自最小来源(
            String operation,
            String profile,
            String evidencePolicy,
            List<String> operationSources) {
        Fixture fixture = fixture(operation);
        ExecutionRegistry registry = enabled(operation);
        JooqLongSerialDurableRunStarter starter = starter(registry);
        LongSerialStartWritingRunRequest request = request(
                fixture, operation, new NovelScope("novel"), operation + "-request-0001");

        WritingRunV2Response first = starter.startFresh(fixture.userId(), request);
        WritingRunV2Response replay = starter.startFresh(fixture.userId(), request);

        assertThat(replay.getRunId()).isEqualTo(first.getRunId());
        Record run = database.dsl().fetchOne(
                """
                SELECT kind::text AS kind, operation, "targetType", "targetId", input
                FROM public."WorkflowRun" WHERE id = ?
                """,
                first.getRunId());
        assertThat(run.get("kind", String.class)).isEqualTo("chapter_generation");
        assertThat(run.get("operation", String.class)).isEqualTo(operation);
        assertThat(run.get("targetType", String.class)).isEqualTo("novel");
        assertThat(run.get("targetId", String.class)).isEqualTo(fixture.novelId());
        assertThat(json.readTree(run.get("input", String.class)).path("target").path("type").asText())
                .isEqualTo("chapter");
        assertThat(json.readTree(run.get("input", String.class)).path("scope"))
                .isEqualTo(json.valueToTree(Map.of("kind", "novel")));

        Record step = database.dsl().fetchOne(
                """
                SELECT input, "modelProfile", "outputSchema", "evidenceBundleId"
                FROM public."WorkflowStep" WHERE "runId" = ?
                """,
                first.getRunId());
        assertThat(json.readTree(step.get("input", String.class)))
                .isEqualTo(json.valueToTree(Map.of("userInstruction", "  完整要求😀\r\n" + operation)));
        assertThat(step.get("modelProfile", String.class)).isEqualTo(profile);
        assertThat(step.get("outputSchema", String.class)).isEqualTo("output.agent_updates_step.v1");
        assertThat(database.dsl().fetchOne(
                                "SELECT \"policyVersion\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ?",
                                step.get("evidenceBundleId", String.class))
                        .get("policyVersion", String.class))
                .isEqualTo(evidencePolicy);

        List<Record> evidence = evidence(first.getRunId());
        assertThat(evidence).extracting(value -> value.get("resourceType", String.class))
                .containsExactlyElementsOf(operationSources);
        assertRunContext(evidence, fixture, Map.of("kind", "novel"));
        assertChapterAnchorOnly(evidence, fixture);
        if (operationSources.contains("world_setting")) {
            assertThat(content(evidence, "world_setting").path("content").asText())
                    .isEqualTo(WORLD_SETTING);
            assertThat(content(evidence, "story_background").path("content").asText())
                    .isEqualTo(STORY_BACKGROUND);
        } else {
            assertThat(content(evidence, "outline_content").path("content").asText())
                    .isEqualTo(OUTLINE_CONTENT);
        }
        assertThat(serialized(evidence)).doesNotContain(fixture.chapterContent(), fixture.nodeContent());
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE id = ?", first.getRunId()))
                .isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", first.getRunId()))
                .isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", first.getRunId()))
                .isEqualTo(1);
    }

    @ParameterizedTest
    @MethodSource("naturalStructuredOperations")
    void 自然启动只暴露冻结操作的默认范围与明确说明(
            String operation, String expectedScope, String descriptionFragment) {
        Fixture fixture = fixture("natural-" + operation);
        ExecutionRegistry registry = enabled(operation);
        WritingRunV2Response response = starter(registry).startNatural(
                fixture.userId(),
                new NaturalStartWritingRunRequest(
                                fixture.chapterId(),
                                "natural-" + operation + "-request-0001",
                                "natural",
                                fixture.novelId(),
                                "请按自然语言判断并执行" + operation,
                                "long_serial",
                                fixture.sessionId())
                        .targetWordCount(1234));

        assertThat(response.getOperation()).isNull();
        assertThat(response.getCurrentStep().getModelProfile().getProfile())
                .isEqualTo("system.intent_resolver.v3");
        JsonNode context = content(evidence(response.getRunId()), "intent_context");
        assertThat(context.path("availableOperations").size()).isEqualTo(10);
        JsonNode selected = null;
        for (JsonNode candidate : context.path("availableOperations")) {
            assertThat(candidate.path("targetType").asText()).isEqualTo("chapter");
            assertThat(candidate.path("description").asText()).contains("默认范围");
            if (operation.equals(candidate.path("operation").asText())) selected = candidate;
        }
        assertThat(selected).isNotNull();
        assertThat(selected.path("scopeKind").asText()).isEqualTo(expectedScope);
        assertThat(selected.path("description").asText()).contains(descriptionFragment);
        assertThat(context.path("availableOperations").findValues("operation").stream()
                        .map(JsonNode::asText))
                .contains(operation)
                .doesNotContain("rewrite_chapter_selection", "rewrite_outline_selection");
    }

    @ParameterizedTest
    @MethodSource("naturalPreparationOperations")
    void 自然业务准备只依赖冻结子计划并复用显式来源规划(
            String operation, String expectedScope) {
        Fixture fixture = fixture("prepare-" + operation);
        ExecutionPlanSnapshot frozen = enabled(operation).freezePlan("long_serial." + operation, false);
        JooqLongSerialDurableRunStarter preparation =
                starter(ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST));

        WorkflowIntentBusinessPreparation.Prepared prepared = preparation.prepare(
                fixture.userId(),
                fixture.novelId(),
                fixture.chapterId(),
                fixture.sessionId(),
                "  自然准备原文😀\r\n" + operation,
                1234,
                frozen);

        assertThat(prepared.input())
                .isEqualTo(Map.of("userInstruction", "  自然准备原文😀\r\n" + operation));
        assertThat(prepared.initialStep()).isEqualTo(frozen.generator());
        JsonNode runContext = json.valueToTree(prepared.evidenceItems().stream()
                .filter(item -> "run_context".equals(item.resourceType()))
                .findFirst()
                .orElseThrow()
                .contentJson());
        assertThat(runContext.path("scope").path("kind").asText()).isEqualTo(expectedScope);
        assertThat(prepared.evidenceItems())
                .extracting(item -> item.resourceType())
                .contains("agent_updates_index", "run_context", "chapter_reference");
        assertThat(workflowFacts(fixture.userId())).isZero();
    }

    @Test
    void 节点与章节范围映射为内部真实目标且不读取章节正文() {
        Fixture outline = fixture("outline-node-scope");
        WritingRunV2Response outlineRun = starter(enabled("revise_outline")).startFresh(
                outline.userId(),
                request(
                        outline,
                        "revise_outline",
                        new OutlineNodeScope("outline_node", outline.nodeId()),
                        "outline-node-scope-request-01"));
        Record outlineIdentity = runIdentity(outlineRun.getRunId());
        assertThat(outlineIdentity.get("targetType", String.class)).isEqualTo("outline_node");
        assertThat(outlineIdentity.get("targetId", String.class)).isEqualTo(outline.nodeId());
        List<Record> outlineEvidence = evidence(outlineRun.getRunId());
        assertThat(outlineEvidence).extracting(value -> value.get("resourceType", String.class))
                .contains("agent_updates_index", "run_context", "chapter_reference", "outline_content", "outline_node")
                .doesNotContain("world_setting", "story_background", "chapter_content");
        assertThat(content(outlineEvidence, "outline_node").path("content").asText())
                .isEqualTo(outline.nodeContent());
        assertRunContext(
                outlineEvidence,
                outline,
                Map.of("kind", "outline_node", "outlineNodeId", outline.nodeId()));
        assertThat(serialized(outlineEvidence)).doesNotContain(outline.chapterContent());

        Fixture chapter = fixture("foreshadowing-chapter-scope");
        WritingRunV2Response chapterRun = starter(enabled("manage_foreshadowing")).startFresh(
                chapter.userId(),
                request(
                        chapter,
                        "manage_foreshadowing",
                        new ChapterScope(chapter.chapterId(), "chapter"),
                        "foreshadow-chapter-request-01"));
        Record chapterIdentity = runIdentity(chapterRun.getRunId());
        assertThat(chapterIdentity.get("targetType", String.class)).isEqualTo("chapter");
        assertThat(chapterIdentity.get("targetId", String.class)).isEqualTo(chapter.chapterId());
        List<Record> chapterEvidence = evidence(chapterRun.getRunId());
        assertThat(chapterEvidence).extracting(value -> value.get("resourceType", String.class))
                .containsExactly(
                        "agent_updates_index",
                        "run_context",
                        "chapter_reference",
                        "outline_content");
        assertRunContext(
                chapterEvidence,
                chapter,
                Map.of("kind", "chapter", "chapterId", chapter.chapterId()));
        assertThat(serialized(chapterEvidence)).doesNotContain(chapter.chapterContent());
    }

    @ParameterizedTest
    @MethodSource("invalidScopes")
    void 五项拒绝未授权范围且不留下工作流事实(String operation, Scope scope) {
        Fixture fixture = fixture("invalid-" + operation + "-" + scope.getClass().getSimpleName());
        LongSerialStartWritingRunRequest request = request(
                fixture, operation, scopeForFixture(scope, fixture), "invalid-scope-request-0001");

        assertThatThrownBy(() -> starter(enabled(operation)).startFresh(fixture.userId(), request))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> {
                            assertThat(error.statusCode()).isEqualTo(409);
                            assertThat(error.code()).isEqualTo("LONG_SCOPE_NOT_SUPPORTED");
                        });
        assertThat(workflowFacts(fixture.userId())).isZero();
    }

    @Test
    void 节点焦点必须属于同一小说且公共目标仍须匹配章节锚点() {
        Fixture fixture = fixture("owned-focus");
        Fixture other = fixture("owned-focus-other");
        LongSerialStartWritingRunRequest crossNovel = request(
                fixture,
                "revise_outline",
                new OutlineNodeScope("outline_node", other.nodeId()),
                "cross-novel-scope-request-01");
        assertThatThrownBy(() -> starter(enabled("revise_outline")).startFresh(fixture.userId(), crossNovel))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.code()).isEqualTo("LONG_SCOPE_NOT_SUPPORTED"));

        LongSerialStartWritingRunRequest wrongTarget = request(
                fixture,
                "create_lore",
                new NovelScope("novel"),
                "wrong-public-target-request-01");
        wrongTarget.setTarget(new ChapterTarget(other.chapterId(), "chapter"));
        assertThatThrownBy(() -> starter(enabled("create_lore")).startFresh(fixture.userId(), wrongTarget))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.code()).isEqualTo("LONG_SCOPE_NOT_SUPPORTED"));
        assertThat(workflowFacts(fixture.userId())).isZero();
    }

    @Test
    void 兼容V1组装器沿用相同节点范围归属而不放宽旧操作() {
        Fixture fixture = fixture("legacy-outline-focus");
        Fixture other = fixture("legacy-outline-focus-other");
        LongSerialRunAssembler assembler =
                new LongSerialRunAssembler(json, new WritingSourceBindingCapture(json));
        LongSerialStartWritingRunRequest valid = request(
                fixture,
                "revise_outline",
                new OutlineNodeScope("outline_node", fixture.nodeId()),
                "legacy-valid-outline-request-01");
        LongSerialRunAssembler.Normalized normalized = assembler.normalize(valid);
        LongSerialRunAssembler.Assembled assembled = database.transactionResult(
                transaction -> assembler.assemble(
                        transaction, fixture.userId(), valid, normalized.definition()));
        assertThat(assembled.selectedAgents()).containsExactly("剧情", "编辑");
        assertThat(assembled.job().get("scope"))
                .isEqualTo(Map.of("kind", "outline_node", "outlineNodeId", fixture.nodeId()));

        LongSerialStartWritingRunRequest crossNovel = request(
                fixture,
                "revise_outline",
                new OutlineNodeScope("outline_node", other.nodeId()),
                "legacy-cross-outline-request-01");
        LongSerialRunAssembler.Normalized crossNormalized = assembler.normalize(crossNovel);
        assertThatThrownBy(() -> database.transactionResult(transaction -> assembler.assemble(
                        transaction,
                        fixture.userId(),
                        crossNovel,
                        crossNormalized.definition())))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.code()).isEqualTo("LONG_SCOPE_NOT_SUPPORTED"));
    }

    @Test
    void 缺席的必要设定单例保留小说绑定哨兵而不是伪造空正文() {
        Fixture fixture = fixture("missing-lore-singletons");
        database.dsl().execute("DELETE FROM public.\"WorldSetting\" WHERE \"novelId\" = ?", fixture.novelId());
        database.dsl().execute("DELETE FROM public.\"StoryBackground\" WHERE \"novelId\" = ?", fixture.novelId());

        WritingRunV2Response response = starter(enabled("create_lore")).startFresh(
                fixture.userId(),
                request(
                        fixture,
                        "create_lore",
                        new NovelScope("novel"),
                        "missing-lore-sources-request-01"));
        List<Record> evidence = evidence(response.getRunId());
        for (String resourceType : List.of("story_background", "world_setting")) {
            Record item = item(evidence, resourceType);
            assertThat(item.get("exists", Boolean.class)).isFalse();
            assertThat(item.get("contentJson")).isNull();
            assertThat(json.readTree(item.get("metadataJson", String.class))
                            .path("absenceSentinel")
                            .path("resourceId")
                            .asText())
                    .isEqualTo(fixture.novelId());
        }
    }

    @Test
    void 未注入资料Reader的兼容构造器不虚报五项Handler() {
        ExecutionRegistry registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        var old = new JooqLongSerialDurableRunStarter(
                database,
                new LongSerialRunAssembler(json, new WritingSourceBindingCapture(json)),
                new DurableWorkflowService(new JooqWorkflowStartRepository(database, ids, CLOCK, json)),
                registry,
                ids,
                CLOCK,
                json,
                new JooqChapterPlanEvidenceReader(json),
                new JooqChapterWritingEvidenceReader(json),
                new JooqWorkflowExecutionContextReader(json));
        assertThat(old.supportedOperationKeys())
                .contains("long_serial.plan_chapter")
                .doesNotContainAnyElementsOf(AgentUpdatesStartPlanner.OPERATION_KEYS);
        assertThat(starter(enabled("create_lore")).supportedOperationKeys())
                .containsAll(AgentUpdatesStartPlanner.OPERATION_KEYS);
    }

    private static Stream<Arguments> novelScopeOperations() {
        return Stream.of(
                Arguments.of(
                        "create_lore",
                        "lore.generator.v3",
                        "evidence.long_serial.lore_create.v1",
                        List.of(
                                "agent_updates_index",
                                "run_context",
                                "chapter_reference",
                                "story_background",
                                "world_setting")),
                Arguments.of(
                        "revise_lore",
                        "lore.reviser.v3",
                        "evidence.long_serial.lore_revision.v1",
                        List.of(
                                "agent_updates_index",
                                "run_context",
                                "chapter_reference",
                                "story_background",
                                "world_setting")),
                Arguments.of(
                        "create_outline",
                        "plot.outline_generator.v3",
                        "evidence.long_serial.outline_create.v1",
                        List.of(
                                "agent_updates_index",
                                "run_context",
                                "chapter_reference",
                                "outline_content")),
                Arguments.of(
                        "revise_outline",
                        "plot.outline_reviser.v3",
                        "evidence.long_serial.outline_revision.v1",
                        List.of(
                                "agent_updates_index",
                                "run_context",
                                "chapter_reference",
                                "outline_content")),
                Arguments.of(
                        "manage_foreshadowing",
                        "plot.foreshadowing.v3",
                        "evidence.long_serial.foreshadowing.v1",
                        List.of(
                                "agent_updates_index",
                                "run_context",
                                "chapter_reference",
                                "outline_content")));
    }

    private static Stream<Arguments> invalidScopes() {
        return Stream.of(
                Arguments.of("create_lore", new ChapterScope("placeholder", "chapter")),
                Arguments.of("revise_lore", new OutlineNodeScope("outline_node", "placeholder")),
                Arguments.of("create_outline", new ChapterScope("placeholder", "chapter")),
                Arguments.of("revise_outline", new ChapterScope("placeholder", "chapter")),
                Arguments.of("manage_foreshadowing", new OutlineNodeScope("outline_node", "placeholder")));
    }

    private static Stream<Arguments> naturalStructuredOperations() {
        return Stream.of(
                Arguments.of("create_lore", "novel", "整部小说"),
                Arguments.of("revise_lore", "novel", "整部小说"),
                Arguments.of("create_outline", "novel", "整部小说"),
                Arguments.of("revise_outline", "novel", "指定节点请使用显式入口"),
                Arguments.of("manage_foreshadowing", "chapter", "当前章节"));
    }

    private static Stream<Arguments> naturalPreparationOperations() {
        return Stream.of(
                Arguments.of("create_lore", "novel"),
                Arguments.of("revise_lore", "novel"),
                Arguments.of("create_outline", "novel"),
                Arguments.of("revise_outline", "novel"),
                Arguments.of("manage_foreshadowing", "chapter"));
    }

    private static Scope scopeForFixture(Scope scope, Fixture fixture) {
        if (scope instanceof ChapterScope) return new ChapterScope(fixture.chapterId(), "chapter");
        if (scope instanceof OutlineNodeScope) {
            return new OutlineNodeScope("outline_node", fixture.nodeId());
        }
        return scope;
    }

    private static ExecutionRegistry enabled(String operation) {
        return ExecutionRegistryFixtures.structuredOperationEnabled(
                ExecutionRegistry.Environment.TEST, "long_serial." + operation);
    }

    private static JooqLongSerialDurableRunStarter starter(ExecutionRegistry registry) {
        return new JooqLongSerialDurableRunStarter(
                database,
                new LongSerialRunAssembler(json, new WritingSourceBindingCapture(json)),
                new DurableWorkflowService(new JooqWorkflowStartRepository(database, ids, CLOCK, json)),
                registry,
                ids,
                CLOCK,
                json,
                new JooqChapterPlanEvidenceReader(json),
                new JooqChapterWritingEvidenceReader(json),
                new JooqWorkflowExecutionContextReader(json),
                new JooqAgentUpdatesEvidenceReader(json));
    }

    private static LongSerialStartWritingRunRequest request(
            Fixture fixture, String operation, Scope scope, String clientRequestId) {
        return new LongSerialStartWritingRunRequest(
                        fixture.chapterId(),
                        clientRequestId,
                        fixture.novelId(),
                        LongSerialStartWritingRunRequest.OperationEnum.fromValue(operation),
                        scope,
                        new ChapterTarget(fixture.chapterId(), "chapter"),
                        "  完整要求😀\r\n" + operation,
                        "long_serial")
                .targetWordCount(1000);
    }

    private static void assertRunContext(
            List<Record> evidence, Fixture fixture, Map<String, Object> expectedScope) {
        Record item = item(evidence, "run_context");
        assertThat(item.get("resourceId", String.class)).isEqualTo(fixture.novelId());
        assertThat(item.get("resourceUpdatedAt", LocalDateTime.class)).isEqualTo(NOW);
        JsonNode content = json.readTree(item.get("contentJson", String.class));
        assertThat(content.path("scope")).isEqualTo(json.valueToTree(expectedScope));
        assertThat(content.path("novel"))
                .isEqualTo(json.valueToTree(Map.of(
                        "id", fixture.novelId(),
                        "name", fixture.novelName(),
                        "summary", fixture.summary(),
                        "storyProgress", fixture.storyProgress())));
    }

    private static void assertChapterAnchorOnly(List<Record> evidence, Fixture fixture) {
        JsonNode chapter = content(evidence, "chapter_reference");
        assertThat(chapter.path("id").asText()).isEqualTo(fixture.chapterId());
        assertThat(chapter.path("title").asText()).isEqualTo("章节锚点");
        assertThat(chapter.has("content")).isFalse();
    }

    private static Record runIdentity(String runId) {
        return database.dsl().fetchOne(
                "SELECT \"targetType\", \"targetId\" FROM public.\"WorkflowRun\" WHERE id = ?",
                runId);
    }

    private static List<Record> evidence(String runId) {
        return database.dsl().fetch(
                """
                SELECT item.ordinal, item."resourceType", item."resourceId", item.exists,
                       item."resourceUpdatedAt", item."contentJson", item."metadataJson"
                FROM public."WorkflowEvidenceItem" AS item
                JOIN public."WorkflowEvidenceBundle" AS bundle ON bundle.id = item."bundleId"
                WHERE bundle."runId" = ?
                ORDER BY item.ordinal
                """,
                runId);
    }

    private static Record item(List<Record> evidence, String resourceType) {
        return evidence.stream()
                .filter(value -> resourceType.equals(value.get("resourceType", String.class)))
                .findFirst()
                .orElseThrow();
    }

    private static JsonNode content(List<Record> evidence, String resourceType) {
        return json.readTree(item(evidence, resourceType).get("contentJson", String.class));
    }

    private static String serialized(List<Record> evidence) {
        return evidence.stream()
                .map(value -> value.get("contentJson", String.class))
                .filter(Objects::nonNull)
                .reduce("", String::concat);
    }

    private static Fixture fixture(String prefix) {
        String suffix = UUID.randomUUID().toString();
        String userId = prefix + "-user-" + suffix;
        String novelId = prefix + "-novel-" + suffix;
        String chapterId = prefix + "-chapter-" + suffix;
        String sessionId = prefix + "-session-" + suffix;
        String nodeId = prefix + "-node-" + suffix;
        String novelName = "作品😀" + prefix;
        String summary = "  完整简介\r\n" + prefix;
        String storyProgress = "故事推进至雨夜";
        String chapterContent = "章节正文绝不能进入结构化资料初始 Evidence😀";
        String nodeContent = "节点焦点完整内容😀\r\n尾部  ";
        var tx = database.dsl();
        tx.execute(
                """
                INSERT INTO public."User" (
                  id, username, "passwordHash", "creditBalanceMicros", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'test', 1000000, ?, ?)
                """,
                userId,
                userId,
                NOW,
                NOW);
        tx.execute(
                """
                INSERT INTO public."Novel" (
                  id, name, summary, "storyProgress", "userId", "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                novelId,
                novelName,
                summary,
                storyProgress,
                userId,
                NOW,
                NOW);
        tx.execute(
                """
                INSERT INTO public."WritingBible" (
                  id, "novelId", "storyLengthProfile", "createdAt", "updatedAt"
                ) VALUES (?, ?, 'long_serial', ?, ?)
                """,
                prefix + "-bible-" + suffix,
                novelId,
                NOW,
                NOW);
        tx.execute(
                """
                INSERT INTO public."Chapter" (
                  id, "novelId", title, content, "order", status, "createdAt", "updatedAt"
                ) VALUES (?, ?, '章节锚点', ?, 1, 'drafting', ?, ?)
                """,
                chapterId,
                novelId,
                chapterContent,
                NOW,
                NOW);
        tx.execute(
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
        tx.execute(
                """
                INSERT INTO public."Outline" (id, "novelId", content, "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                prefix + "-outline-" + suffix,
                novelId,
                OUTLINE_CONTENT,
                NOW,
                NOW);
        tx.execute(
                """
                INSERT INTO public."WorldSetting" (id, "novelId", content, "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                prefix + "-world-" + suffix,
                novelId,
                WORLD_SETTING,
                NOW,
                NOW);
        tx.execute(
                """
                INSERT INTO public."StoryBackground" (id, "novelId", content, "createdAt", "updatedAt")
                VALUES (?, ?, ?, ?, ?)
                """,
                prefix + "-background-" + suffix,
                novelId,
                STORY_BACKGROUND,
                NOW,
                NOW);
        tx.execute(
                """
                INSERT INTO public."OutlineNode" (
                  id, "novelId", title, content, kind, "order", "createdAt", "updatedAt"
                ) VALUES (?, ?, '节点焦点', ?, 'stage', 0, ?, ?)
                """,
                nodeId,
                novelId,
                nodeContent,
                NOW,
                NOW);
        return new Fixture(
                userId,
                novelId,
                chapterId,
                sessionId,
                nodeId,
                novelName,
                summary,
                storyProgress,
                chapterContent,
                nodeContent);
    }

    private static int count(String sql, Object... bindings) {
        return database.dsl().fetchOne(sql, bindings).get(0, Integer.class);
    }

    private static int workflowFacts(String userId) {
        return count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"userId\" = ?", userId)
                + count(
                        """
                        SELECT count(*) FROM public."WorkflowStep"
                        WHERE "runId" IN (SELECT id FROM public."WorkflowRun" WHERE "userId" = ?)
                        """,
                        userId)
                + count(
                        """
                        SELECT count(*) FROM public."WorkflowEvidenceBundle"
                        WHERE "runId" IN (SELECT id FROM public."WorkflowRun" WHERE "userId" = ?)
                        """,
                        userId);
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
            String nodeId,
            String novelName,
            String summary,
            String storyProgress,
            String chapterContent,
            String nodeContent) {}
}
