package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.catalog.HistoricalRegistryFixture;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;

import cn.inkforge.contracts.api.WritingRunResponse;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.writing.application.WritingRunQueryRepository;
import cn.inkforge.core.writing.application.WritingRunStartRequestParser;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowExecutionContextReader;
import jakarta.validation.Validation;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class RoutingWritingRunStarterTest {
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-01T03:00:00.000");
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-01T03:00:00Z"), ZoneOffset.UTC);
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("test-only-password");
    private static CoreDatabase database;
    private static ObjectMapper json;
    private static WritingRunStartRequestParser parser;
    private static JooqWritingCommandRepository legacy;

    @BeforeAll
    static void rebuildSchema() throws Exception {
        POSTGRES.copyFileToContainer(MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"), "/tmp/schema.sql");
        POSTGRES.copyFileToContainer(MountableFile.forClasspathResource("migrations/20260831_durable_agent_execution.sql"), "/tmp/durable.sql");
        executeSql("/tmp/schema.sql"); executeSql("/tmp/durable.sql");
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        json = JsonMapper.builder().addModule(new JsonNullableJackson3Module()).build();
        parser = new WritingRunStartRequestParser(json, Validation.buildDefaultValidatorFactory().getValidator());
        legacy = new JooqWritingCommandRepository(database, new CuidV1Generator(CLOCK), CLOCK, json, new CommandIdempotencyStore(json, true));
    }
    @AfterAll static void close() { if (database != null) database.close(); }

    @Test
    void 新任务只创建V1且幂等重放不重复正文与消息() {
        Fixture f = fixture("retired-v1");
        var req = request(f, "retired-v1-request");
        var first = (WritingRunResponse) router(true).start(f.userId(), req);
        assertThat(first.getEngineVersion()).isEqualTo(1);
        assertThat(router(false).start(f.userId(), req)).isEqualTo(first);
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"novelId\" = ? AND \"engineVersion\" = 2", f.novelId())).isZero();
        assertThat(database.dsl().fetchOne("SELECT content FROM public.\"Chapter\" WHERE id = ?", f.chapterId()).get(0, String.class)).isEqualTo(f.content());
        assertThat(count("SELECT count(*) FROM public.\"WritingMessage\" WHERE \"sessionId\" = ?", f.sessionId())).isEqualTo(1);
    }

    @Test
    void 新建关闭在写入前拒绝且不留下任务或幂等事实() {
        Fixture f = fixture("retired-drain");
        assertThatThrownBy(() -> router(false).start(f.userId(), request(f, "retired-drain-request")))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.code()).isEqualTo("AGENT_FRESH_STARTS_DRAINING"));
        assertThat(count("SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?", f.novelId())).isZero();
    }

    @Test
    void 旧自然入口在创建任何记录前明确退役() {
        Fixture f = fixture("retired-natural");
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("inputMode", "natural"); body.put("workflow", "long_serial"); body.put("novelId", f.novelId());
        body.put("chapterId", f.chapterId()); body.put("writingSessionId", f.sessionId());
        body.put("clientRequestId", "retired-natural-request"); body.put("userInstruction", "继续写作"); body.put("targetWordCount", 1000);
        var req = parser.parse(new WritingRunStartBody(json.valueToTree(body)));
        assertThatThrownBy(() -> router(true).start(f.userId(), req))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.code()).isEqualTo("EXECUTION_ENGINE_RETIRED"));
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"novelId\" = ?", f.novelId())).isZero();
        router(true).start(f.userId(), request(f, "retired-natural-request"));
        assertThatThrownBy(() -> router(true).start(f.userId(), req))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 历史请求只读重放保护指纹且阻止新V1覆盖活动来源() {
        Fixture f = fixture("historical-replay");
        var body = new LinkedHashMap<String, Object>();
        body.put("clientRequestId", "historical-request-0001"); body.put("workflow", "long_serial");
        body.put("novelId", f.novelId()); body.put("chapterId", f.chapterId()); body.put("writingSessionId", f.sessionId());
        body.put("operation", "plan_chapter"); body.put("target", Map.of("type", "chapter", "id", f.chapterId()));
        body.put("scope", Map.of("kind", "chapter", "chapterId", f.chapterId()));
        body.put("targetWordCount", 1000); body.put("userInstruction", "原始规划");
        var req = (ParsedWritingRunStartRequest.LongSerial) parser.parse(new WritingRunStartBody(json.valueToTree(body)));
        var normalized = new LongSerialRunAssembler(json, new WritingSourceBindingCapture(json)).normalize(req.request());
        var registry = HistoricalRegistryFixture.loadClasspath(HistoricalRegistryFixture.Environment.TEST);
        var resolved = registry.resolve("long_serial.plan_chapter", false);
        var plan = registry.freezePlan("long_serial.plan_chapter", false);
        var sources = List.of(new WorkflowEvidenceItemPlan("chapter", f.chapterId(), true, null, null, null,
                Map.of("content", f.content()), null, null, Map.of()));
        var old = new JooqWorkflowStartRepository(database, new CuidV1Generator(CLOCK), CLOCK, json).start(
                new WorkflowStartPlan(f.userId(), req.request().getClientRequestId(), normalized.fingerprint(),
                        "long_serial", "plan_chapter", "1", "chapter_generation", f.novelId(), f.chapterId(), f.sessionId(),
                        "chapter", f.chapterId(), normalized.body(), resolved.operation().evidencePolicy(), sources,
                        plan.runBudget(), plan, new WorkflowInitialStepPlan("generation", resolved.operation().lane(),
                        Map.of("userInstruction", "原始规划"), resolved.generatorProfile(), resolved.generatorStepBudget(), resolved.outputSchema())));
        var queries = mock(WritingRunQueryRepository.class);
        var expected = new WritingRunV2Response().engineVersion(2).runId(old.runId());
        when(queries.getPublic(f.userId(), old.runId())).thenReturn(expected);
        var router = new RoutingWritingRunStarter(database, legacy, new CommandIdempotencyStore(json, true),
                CoreSettings.from(Map.of("HISTORICAL_WORKFLOW_SCHEMA_READY", "true", "V1_FRESH_AGENT_STARTS_ENABLED", "false")),
                json, new JooqWorkflowExecutionContextReader(json), queries);
        assertThat(router.start(f.userId(), req)).isSameAs(expected);
        body.put("userInstruction", "改变原请求");
        var changed = parser.parse(new WritingRunStartBody(json.valueToTree(body)));
        assertThatThrownBy(() -> router.start(f.userId(), changed)).isInstanceOfSatisfying(ApiException.class,
                e -> assertThat(e.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
        assertThatThrownBy(() -> router(true).start(f.userId(), request(f, "new-v1-request-00001")))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.code()).isEqualTo("WORKFLOW_FOREGROUND_RUN_EXISTS"));
        assertThat(count("SELECT count(*) FROM public.\"WritingTask\" WHERE \"novelId\" = ?", f.novelId())).isZero();
        assertThat(count("SELECT count(*) FROM public.\"WorkflowRun\" WHERE \"novelId\" = ?", f.novelId())).isEqualTo(1);
    }

    private static ParsedWritingRunStartRequest request(Fixture f, String key) {
        return parser.parse(new WritingRunStartBody(json.valueToTree(Map.of("clientRequestId", key,
                "novelId", f.novelId(), "chapterId", f.chapterId(), "writingSessionId", f.sessionId(),
                "targetWordCount", 1000, "selectedAgents", List.of("写作"), "userMessage", "继续写作"))));
    }

    private static RoutingWritingRunStarter router(boolean enabled) {
        return new RoutingWritingRunStarter(database, legacy, new CommandIdempotencyStore(json, true),
                CoreSettings.from(Map.of("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true", "V1_FRESH_AGENT_STARTS_ENABLED", Boolean.toString(enabled))),
                json, new JooqWorkflowExecutionContextReader(json), mock(WritingRunQueryRepository.class));
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
