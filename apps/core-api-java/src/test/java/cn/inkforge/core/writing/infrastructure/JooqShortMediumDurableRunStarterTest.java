package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ShortMediumStartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.writing.application.LongSerialDurableRunStarter;
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowExecutionContextReader;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import cn.inkforge.core.writing.domain.WritingRunCursor;
import cn.inkforge.core.writing.domain.WritingRunOutcomeProjector;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;
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
class JooqShortMediumDurableRunStarterTest {

    private static final LocalDateTime NOW =
            LocalDateTime.parse("2026-09-05T16:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-09-05T16:00:00Z"), ZoneOffset.UTC);
    private static final List<String> CONTEXT_FIELDS = List.of(
            "workflow",
            "operation",
            "documentType",
            "chapterId",
            "baseVersionId",
            "baseContent",
            "baseContentHash",
            "sourceOutlineVersionId",
            "sourceOutlineContent",
            "sourceOutlineContentHash",
            "selectionStart",
            "selectionEnd",
            "selectedText",
            "selectedTextHash",
            "contextBefore",
            "contextAfter",
            "userInstruction",
            "targetTotalWordCount",
            "sourceKind",
            "sourceText");

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
                MountableFile.forClasspathResource(
                        "migrations/20260831_durable_agent_execution.sql"),
                "/tmp/20260831_durable_agent_execution.sql");
        executeSql("/tmp/novelwriterdev-schema.sql");
        executeSql("/tmp/20260831_durable_agent_execution.sql");
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        json = JsonMapper.builder()
                .addModule(new JsonNullableJackson3Module())
                .build();
        ids = new CuidV1Generator(CLOCK);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @ParameterizedTest
    @MethodSource("operations")
    void 四项启动冻结完整来源且不创建V1影子任务(
            String operation,
            String documentType,
            String expectedKind,
            String expectedTargetType,
            int expectedSegments) {
        Fixture fixture = fixture(operation, 32_000);
        String outlineVersion = null;
        String manuscriptVersion = null;
        if (!"generate_outline".equals(operation)) {
            outlineVersion = insertVersion(
                    fixture,
                    "outline",
                    "  已采用大纲😀\r\n尾部  ",
                    null,
                    null);
        }
        if ("full_check".equals(operation)) {
            manuscriptVersion = insertVersion(
                    fixture,
                    "manuscript",
                    "  已采用正文😀\r\n尾部  ",
                    null,
                    outlineVersion);
        }
        ShortMediumStartWritingRunRequest request = request(
                fixture,
                operation,
                documentType,
                operation + "-request-0001",
                outlineVersion,
                manuscriptVersion);
        ExecutionRegistry registry =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        JooqShortMediumDurableRunStarter starter = starter(registry);

        WritingRunV2Response first = starter.startFresh(fixture.userId(), request);

        assertThat(first.getEngineVersion()).isEqualTo(2);
        assertThat(first.getOperation()).isEqualTo(operation);
        assertThat(first.getCurrentStep().getPurpose()).isEqualTo("generation");
        Record run = database.dsl().fetchOne(
                """
                SELECT kind::text AS kind, "chapterId", "writingSessionId", "targetType",
                       "targetId", input, "requestHash"
                FROM public."WorkflowRun" WHERE id = ?
                """,
                first.getRunId());
        assertThat(run.get("kind", String.class)).isEqualTo(expectedKind);
        assertThat(run.get("chapterId", String.class))
                .isEqualTo("manuscript".equals(documentType) ? fixture.chapterId() : null);
        assertThat(run.get("writingSessionId")).isNull();
        assertThat(run.get("targetType", String.class)).isEqualTo(expectedTargetType);
        assertThat(run.get("targetId", String.class)).isEqualTo(
                "manuscript".equals(documentType)
                        ? fixture.chapterId()
                        : fixture.novelId());
        JsonNode runInput = json.readTree(run.get("input", String.class));
        assertThat(runInput.has("clientRequestId")).isFalse();
        assertThat(runInput.properties().stream().map(Map.Entry::getKey).toList())
                .containsExactlyInAnyOrder(
                        "workflow",
                        "novelId",
                        "operation",
                        "documentType",
                        "chapterId",
                        "baseVersionId",
                        "sourceOutlineVersionId",
                        "selectionStart",
                        "selectionEnd",
                        "selectedTextHash",
                        "userInstruction");
        assertThat(runInput.path("workflow").asText()).isEqualTo("short_medium");
        assertThat(runInput.path("userInstruction").asText())
                .isEqualTo("  保留原始要求😀\r\n尾部  ");
        assertThat(run.get("requestHash", String.class)).matches("^[0-9a-f]{64}$");

        Record step = database.dsl().fetchOne(
                """
                SELECT input, lane, "modelProfile", "outputSchema", "evidenceBundleId"
                FROM public."WorkflowStep" WHERE "runId" = ?
                """,
                first.getRunId());
        assertThat(json.readTree(step.get("input", String.class)))
                .isEqualTo(json.valueToTree(Map.of(
                        "segmentIndex", 0,
                        "segmentCount", expectedSegments)));
        ExecutionRegistry.ResolvedOperation resolved =
                registry.resolve("short_medium." + operation, false);
        assertThat(step.get("lane", String.class)).isEqualTo(resolved.operation().lane());
        assertThat(step.get("modelProfile", String.class))
                .isEqualTo(resolved.generatorProfile().key());
        assertThat(step.get("outputSchema", String.class))
                .isEqualTo(resolved.outputSchema().key());

        List<Record> evidence = database.dsl().fetch(
                """
                SELECT "resourceType", "resourceId", "resourceUpdatedAt", "contentType",
                       "contentJson", "rangeJson", "metadataJson"
                FROM public."WorkflowEvidenceItem"
                WHERE "bundleId" = ? ORDER BY ordinal
                """,
                step.get("evidenceBundleId", String.class));
        assertThat(evidence).singleElement();
        Record item = evidence.getFirst();
        assertThat(item.get("resourceType", String.class))
                .isEqualTo("short_medium_context");
        assertThat(item.get("resourceId", String.class)).isEqualTo(fixture.novelId());
        assertThat(item.get("resourceUpdatedAt")).isNull();
        assertThat(item.get("contentType", String.class)).isEqualTo("json");
        assertThat(item.get("rangeJson")).isNull();
        assertThat(json.readTree(item.get("metadataJson", String.class)))
                .isEqualTo(json.valueToTree(Map.of("role", "short_medium_context")));
        JsonNode context = json.readTree(item.get("contentJson", String.class));
        assertThat(context.properties().stream().map(Map.Entry::getKey).toList())
                .containsExactlyInAnyOrderElementsOf(CONTEXT_FIELDS);
        if (Set.of("generate_outline", "generate_manuscript").contains(operation)) {
            assertThat(context.path("sourceText").asText())
                    .isEqualTo("  起始素材😀\r\n尾部  ");
        } else {
            assertThat(context.path("sourceText").isNull()).isTrue();
        }

        database.dsl().execute(
                "UPDATE public.\"ReviewArtifact\" SET \"payloadJson\" = ? WHERE id = ?",
                json.writeValueAsString(Map.of("sourceKind", "idea", "sourceText", "已变化")),
                fixture.sourceArtifactId());
        WritingRunV2Response replay = starter.replayExisting(fixture.userId(), request);
        assertThat(replay.getRunId()).isEqualTo(first.getRunId());
        assertThat(count(
                        "SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?",
                        first.getRunId()))
                .isEqualTo(1);
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?",
                        fixture.novelId()))
                .isZero();
        assertThat(count(
                        "SELECT count(*) FROM public.\"WritingRunCommand\" command "
                                + "JOIN public.\"WritingTask\" task ON task.id=command.\"taskId\" "
                                + "WHERE task.\"novelId\" = ?",
                        fixture.novelId()))
                .isZero();

        ShortMediumStartWritingRunRequest changed = request(
                fixture,
                operation,
                documentType,
                operation + "-request-0001",
                outlineVersion,
                manuscriptVersion)
                .userInstruction("不同要求");
        assertThatThrownBy(() -> starter.replayExisting(fixture.userId(), changed))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.code())
                                .isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 路由按配置切换V1V2且同作品跨引擎互斥() {
        Fixture legacyFirst = fixture("route-legacy-first", 20_000);
        ExecutionRegistry registry =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        ShortMediumStartWritingRunRequest firstLegacy = request(
                legacyFirst,
                "generate_outline",
                "outline",
                "route-legacy-first-request-0001",
                null,
                null);
        assertThat(router(registry, "off", null).start(
                        legacyFirst.userId(),
                        new ParsedWritingRunStartRequest.ShortMedium(firstLegacy)))
                .isNotInstanceOf(WritingRunV2Response.class);
        assertThatThrownBy(() -> router(registry, "allowlist", legacyFirst).start(
                        legacyFirst.userId(),
                        new ParsedWritingRunStartRequest.ShortMedium(request(
                                legacyFirst,
                                "generate_outline",
                                "outline",
                                "route-legacy-first-request-0002",
                                null,
                                null))))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.code())
                                .isEqualTo("SHORT_MEDIUM_DOCUMENT_RUN_ACTIVE"));

        Fixture durableFirst = fixture("route-durable-first", 20_000);
        WritingRunV2Response durable = (WritingRunV2Response) router(
                        registry, "allowlist", durableFirst)
                .start(
                        durableFirst.userId(),
                        new ParsedWritingRunStartRequest.ShortMedium(request(
                                durableFirst,
                                "generate_outline",
                                "outline",
                                "route-durable-first-request-0001",
                                null,
                                null)));
        assertThat(durable.getOperation()).isEqualTo("generate_outline");
        WritingRunV2Response replay = (WritingRunV2Response) router(
                        registry, "off", null)
                .start(
                        durableFirst.userId(),
                        new ParsedWritingRunStartRequest.ShortMedium(request(
                                durableFirst,
                                "generate_outline",
                                "outline",
                                "route-durable-first-request-0001",
                                null,
                                null)));
        assertThat(replay.getRunId()).isEqualTo(durable.getRunId());
        assertThatThrownBy(() -> router(registry, "off", null).start(
                        durableFirst.userId(),
                        new ParsedWritingRunStartRequest.ShortMedium(request(
                                durableFirst,
                                "generate_outline",
                                "outline",
                                "route-durable-first-request-0002",
                                null,
                                null))))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.code())
                                .isEqualTo("SHORT_MEDIUM_DOCUMENT_RUN_ACTIVE"));
    }

    private static Stream<Arguments> operations() {
        return Stream.of(
                Arguments.of(
                        "generate_outline",
                        "outline",
                        "chapter_generation",
                        "short_medium_outline",
                        1),
                Arguments.of(
                        "generate_manuscript",
                        "manuscript",
                        "chapter_generation",
                        "short_medium_manuscript",
                        3),
                Arguments.of(
                        "replace_selection",
                        "outline",
                        "chapter_generation",
                        "short_medium_outline",
                        1),
                Arguments.of(
                        "full_check",
                        "manuscript",
                        "quality_check",
                        "short_medium_manuscript",
                        1));
    }

    private JooqShortMediumDurableRunStarter starter(ExecutionRegistry registry) {
        var executionContexts = new JooqWorkflowExecutionContextReader(json);
        var queries = new JooqWritingRunQueryRepository(
                database,
                new WritingRunStatusProjector(
                        json, new WritingRunOutcomeProjector(), CLOCK),
                new WritingRunCursor(json),
                json,
                true,
                executionContexts);
        return new JooqShortMediumDurableRunStarter(
                database,
                new ShortMediumRunAssembler(json),
                new DurableWorkflowService(
                        new JooqWorkflowStartRepository(database, ids, CLOCK, json)),
                registry,
                queries,
                json);
    }

    private RoutingWritingRunStarter router(
            ExecutionRegistry registry, String mode, Fixture allowlisted) {
        Map<String, String> settings = new java.util.LinkedHashMap<>();
        settings.put("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true");
        settings.put("DURABLE_AGENT_EXECUTION_ROUTE_MODE", mode);
        settings.put("V1_FRESH_AGENT_STARTS_ENABLED", "true");
        if ("allowlist".equals(mode)) {
            settings.put("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", allowlisted.userId());
            settings.put("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", allowlisted.novelId());
        }
        CommandIdempotencyStore idempotency = new CommandIdempotencyStore(json, true);
        var legacy = new JooqWritingCommandRepository(
                database, ids, CLOCK, json, idempotency);
        return new RoutingWritingRunStarter(
                database,
                legacy,
                longStarter(registry),
                starter(registry),
                idempotency,
                CoreSettings.from(settings),
                () -> true,
                json,
                registry,
                new JooqWorkflowExecutionContextReader(json));
    }

    private static LongSerialDurableRunStarter longStarter(
            ExecutionRegistry registry) {
        return new LongSerialDurableRunStarter() {
            @Override
            public java.util.Set<String> supportedOperationKeys() {
                return java.util.Set.copyOf(
                        registry.enabledOperationKeys("long_serial", false));
            }

            @Override
            public WritingRunV2Response replayExisting(
                    String userId,
                    cn.inkforge.contracts.api.LongSerialStartWritingRunRequest request) {
                throw new AssertionError("中短篇路由不应调用长篇重放");
            }

            @Override
            public WritingRunV2Response startFresh(
                    String userId,
                    cn.inkforge.contracts.api.LongSerialStartWritingRunRequest request) {
                throw new AssertionError("中短篇路由不应调用长篇启动");
            }
        };
    }

    private ShortMediumStartWritingRunRequest request(
            Fixture fixture,
            String operation,
            String documentType,
            String clientRequestId,
            String outlineVersion,
            String manuscriptVersion) {
        ShortMediumStartWritingRunRequest request = new ShortMediumStartWritingRunRequest(
                        clientRequestId,
                        ShortMediumStartWritingRunRequest.DocumentTypeEnum.fromValue(documentType),
                        fixture.novelId(),
                        ShortMediumStartWritingRunRequest.OperationEnum.fromValue(operation),
                        "short_medium")
                .userInstruction("  保留原始要求😀\r\n尾部  ");
        if ("manuscript".equals(documentType)) request.chapterId(fixture.chapterId());
        if ("generate_manuscript".equals(operation)) {
            request.sourceOutlineVersionId(outlineVersion);
        }
        if ("replace_selection".equals(operation)) {
            String content = "  已采用大纲😀\r\n尾部  ";
            String selected = codePointSlice(content, 2, 7);
            request.baseVersionId(outlineVersion)
                    .selectionStart(2)
                    .selectionEnd(7)
                    .selectedTextHash(ShortMediumText.sha256(selected));
        }
        if ("full_check".equals(operation)) request.baseVersionId(manuscriptVersion);
        return request;
    }

    private Fixture fixture(String prefix, int targetTotalWordCount) {
        String userId = "short-v2-" + prefix + "-user";
        String novelId = "short-v2-" + prefix + "-novel";
        String chapterId = "short-v2-" + prefix + "-chapter";
        String outlineId = "short-v2-" + prefix + "-outline";
        String sourceArtifactId = "short-v2-" + prefix + "-source";
        database.dsl().insertInto(USER)
                .set(USER.ID, userId)
                .set(USER.USERNAME, userId)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREDITBALANCEMICROS, 10_000_000L)
                .set(USER.CREATEDAT, NOW)
                .set(USER.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, prefix)
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, NOW)
                .set(NOVEL.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "全文")
                .set(CHAPTER.CONTENT, "")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, NOW)
                .set(CHAPTER.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(OUTLINE)
                .set(OUTLINE.ID, outlineId)
                .set(OUTLINE.NOVELID, novelId)
                .set(OUTLINE.CONTENT, "")
                .set(OUTLINE.CREATEDAT, NOW)
                .set(OUTLINE.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, novelId + "-bible")
                .set(WRITINGBIBLE.NOVELID, novelId)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, Storylengthprofile.short_medium)
                .set(WRITINGBIBLE.TARGETTOTALWORDCOUNT, targetTotalWordCount)
                .set(WRITINGBIBLE.CREATEDAT, NOW)
                .set(WRITINGBIBLE.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, sourceArtifactId)
                .set(REVIEWARTIFACT.NOVELID, novelId)
                .set(REVIEWARTIFACT.ARTIFACTKEY, "short-medium:source:" + novelId)
                .set(REVIEWARTIFACT.KIND, Reviewartifactkind.freeform_markdown)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.applied)
                .set(REVIEWARTIFACT.PAYLOADJSON, json.writeValueAsString(Map.of(
                        "sourceKind", "idea",
                        "sourceText", "  起始素材😀\r\n尾部  ")))
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.CREATEDAT, NOW)
                .set(REVIEWARTIFACT.UPDATEDAT, NOW)
                .set(REVIEWARTIFACT.APPLIEDAT, NOW)
                .execute();
        return new Fixture(userId, novelId, chapterId, outlineId, sourceArtifactId);
    }

    private String insertVersion(
            Fixture fixture,
            String documentType,
            String content,
            String baseVersionId,
            String sourceOutlineVersionId) {
        String id = fixture.novelId() + "-" + documentType + "-version";
        ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                "outline".equals(documentType) ? "outline_draft" : "chapter_draft",
                documentType,
                1,
                baseVersionId,
                documentType + "-manual-request-0001",
                "manual",
                content,
                ShortMediumText.sha256(content),
                null,
                null,
                sourceOutlineVersionId,
                "  人工版本要求  ",
                null,
                null,
                null,
                false,
                null,
                null,
                null);
        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, id)
                .set(REVIEWARTIFACT.NOVELID, fixture.novelId())
                .set(REVIEWARTIFACT.CHAPTERID,
                        "manuscript".equals(documentType) ? fixture.chapterId() : null)
                .set(REVIEWARTIFACT.ARTIFACTKEY,
                        "outline".equals(documentType)
                                ? "short-medium:outline:" + fixture.novelId()
                                : "short-medium:manuscript:" + fixture.chapterId())
                .set(REVIEWARTIFACT.KIND,
                        "outline".equals(documentType)
                                ? Reviewartifactkind.outline_draft
                                : Reviewartifactkind.chapter_draft)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.applied)
                .set(REVIEWARTIFACT.PAYLOADJSON, json.writeValueAsString(payload))
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.CREATEDAT, NOW)
                .set(REVIEWARTIFACT.UPDATEDAT, NOW)
                .set(REVIEWARTIFACT.APPLIEDAT, NOW)
                .execute();
        if ("outline".equals(documentType)) {
            database.dsl().update(OUTLINE)
                    .set(OUTLINE.CONTENT, content)
                    .where(OUTLINE.ID.eq(fixture.outlineId()))
                    .execute();
        } else {
            database.dsl().update(CHAPTER)
                    .set(CHAPTER.CONTENT, content)
                    .where(CHAPTER.ID.eq(fixture.chapterId()))
                    .execute();
        }
        return id;
    }

    private static String codePointSlice(String value, int start, int end) {
        return value.substring(
                value.offsetByCodePoints(0, start),
                value.offsetByCodePoints(0, end));
    }

    private static long count(String statement, Object... bindings) {
        return database.dsl().fetchOne(statement, bindings).get(0, Long.class);
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
            String outlineId,
            String sourceArtifactId) {}
}
