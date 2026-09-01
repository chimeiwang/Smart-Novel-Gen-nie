package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGMESSAGE;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.contracts.api.CancelWritingRunRequest;
import cn.inkforge.contracts.api.ResumeWritingRunRequest;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.writing.application.WritingRunStartRequestParser;
import jakarta.validation.Validation;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
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
class JooqWritingCommandRepositoryStartTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-08-25T01:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T07:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_start_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static WritingRunStartRequestParser parser;
    private static JooqWritingCommandRepository repository;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void rebuildSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql", "-v", "ON_ERROR_STOP=1",
                "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(),
                "-f", "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        json = JsonMapper.builder()
                .addModule(new JsonNullableJackson3Module())
                .build();
        parser = new WritingRunStartRequestParser(
                json, Validation.buildDefaultValidatorFactory().getValidator());
        repository = new JooqWritingCommandRepository(
                database,
                new CuidV1Generator(CLOCK),
                CLOCK,
                json,
                new CommandIdempotencyStore(json));
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            database.dsl().deleteFrom(NOVEL).where(NOVEL.USERID.in(users)).execute();
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 旧长篇启动原子创建任务命令和会话消息并可幂等重放() throws Exception {
        Fixture fixture = fixture("legacy-start", Storylengthprofile.long_serial, "章节正文");
        String sessionId = insertSession(fixture);
        ParsedWritingRunStartRequest request = parse("""
                {
                  "clientRequestId": "request-legacy-0001",
                  "novelId": "%s",
                  "chapterId": "%s",
                  "writingSessionId": "%s",
                  "userMessage": "请继续完整写作"
                }
                """.formatted(fixture.novelId(), fixture.chapterId(), sessionId));

        var first = repository.start(fixture.userId(), request);
        var replay = repository.start(fixture.userId(), request);

        assertThat(first.getEngineVersion()).isEqualTo(1);
        assertThat(first.getRunId()).isEqualTo(first.getTaskId());
        assertThat(first.getId()).isEqualTo(first.getTaskId());
        assertThat(replay.getId()).isEqualTo(first.getId());
        assertThat(replay.getCommandId()).isEqualTo(first.getCommandId());
        assertThat(first.getSelectedAgents())
                .containsExactly("设定", "剧情", "写作", "校验", "编辑");
        assertThat(database.dsl().fetchCount(
                        WRITINGTASK, WRITINGTASK.ID.eq(first.getId())))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        WRITINGRUNCOMMAND, WRITINGRUNCOMMAND.TASKID.eq(first.getId())))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        WRITINGMESSAGE, WRITINGMESSAGE.SESSIONID.eq(sessionId)))
                .isEqualTo(1);
        String payload = database.dsl().select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(first.getCommandId()))
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        assertThat(json.readTree(payload).path("sourceBindings").size()).isEqualTo(3);
    }

    @Test
    void 显式长篇启动冻结来源与幂等信封并阻止同章节并发写入() throws Exception {
        Fixture fixture = fixture("long-start", Storylengthprofile.long_serial, "雨😀夜正文");
        ParsedWritingRunStartRequest request = parse(longRequest(
                fixture, "request-long-000001", "write_chapter", null));

        var response = repository.start(fixture.userId(), request);
        var replay = repository.start(fixture.userId(), request);

        assertThat(replay.getId()).isEqualTo(response.getId());
        String payload = database.dsl().select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(response.getCommandId()))
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        var tree = json.readTree(payload);
        assertThat(tree.path("_inkforgeCommand").path("commandKind").asString())
                .isEqualTo("start");
        assertThat(tree.path("_inkforgeCommand").path("requestFingerprint").asString())
                .matches("[0-9a-f]{64}");
        assertThat(tree.path("job").path("sourceBindings").size()).isEqualTo(3);
        String graph = database.dsl().select(WRITINGTASK.GRAPHSTATEJSON)
                .from(WRITINGTASK)
                .where(WRITINGTASK.ID.eq(response.getId()))
                .fetchOne(WRITINGTASK.GRAPHSTATEJSON);
        assertThat(json.readTree(graph).path("phase").asString()).isEqualTo("active");
        assertThat(json.readTree(graph).path("taskId").asString()).isEqualTo(response.getId());

        ParsedWritingRunStartRequest concurrent = parse(longRequest(
                fixture, "request-long-000002", "write_chapter", null));
        assertThatThrownBy(() -> repository.start(fixture.userId(), concurrent))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TARGET_BUSY"));
    }

    @Test
    void 长篇选区使用Unicode码点冻结正文且校验来源哈希() throws Exception {
        Fixture fixture = fixture("long-selection", Storylengthprofile.long_serial, "甲😀乙");
        String selection = """
                ,
                  "selectionTarget": {
                    "resourceType": "chapter_content",
                    "resourceId": "%s",
                    "baseUpdatedAt": "2026-08-25T01:00:00Z",
                    "baseContentHash": "%s",
                    "selectionStart": 1,
                    "selectionEnd": 2,
                    "selectedTextHash": "%s"
                  }
                """.formatted(fixture.chapterId(), sha256("甲😀乙"), sha256("😀"));
        ParsedWritingRunStartRequest request = parse(longRequest(
                fixture, "request-select-0001", "rewrite_chapter_selection", selection));

        var response = repository.start(fixture.userId(), request);
        String graph = database.dsl().select(WRITINGTASK.GRAPHSTATEJSON)
                .from(WRITINGTASK)
                .where(WRITINGTASK.ID.eq(response.getId()))
                .fetchOne(WRITINGTASK.GRAPHSTATEJSON);

        assertThat(json.readTree(graph).path("selectionSnapshot").path("selectedText").asString())
                .isEqualTo("😀");
        assertThat(response.getTargetWordCount()).isEqualTo(1);
    }

    @Test
    void 中短篇启动只信任持久起始素材并阻止并发文档生成() throws Exception {
        Fixture fixture = fixture("short-start", Storylengthprofile.short_medium, "");
        insertShortSource(fixture, "idea", "一个完整灵感");
        ParsedWritingRunStartRequest request = parse("""
                {
                  "clientRequestId": "request-short-0001",
                  "workflow": "short_medium",
                  "novelId": "%s",
                  "operation": "generate_outline",
                  "documentType": "outline",
                  "userInstruction": "生成结构化蓝图"
                }
                """.formatted(fixture.novelId()));

        var response = repository.start(fixture.userId(), request);
        String payload = database.dsl().select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(response.getCommandId()))
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);

        assertThat(json.readTree(payload).path("sourceText").asString()).isEqualTo("一个完整灵感");
        assertThat(response.getTargetWordCount()).isEqualTo(20_000);
        assertThat(response.getSelectedAgents()).containsExactly("剧情");
        ParsedWritingRunStartRequest concurrent = parse("""
                {
                  "clientRequestId": "request-short-0002",
                  "workflow": "short_medium",
                  "novelId": "%s",
                  "operation": "generate_outline",
                  "documentType": "outline"
                }
                """.formatted(fixture.novelId()));
        assertThatThrownBy(() -> repository.start(fixture.userId(), concurrent))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("SHORT_MEDIUM_DOCUMENT_RUN_ACTIVE"));
    }

    @Test
    void 显式长篇拒绝中短篇作品和复用到其他请求的全局幂等标识() throws Exception {
        Fixture shortFixture = fixture("long-mismatch", Storylengthprofile.short_medium, "");
        ParsedWritingRunStartRequest mismatch = parse(longRequest(
                shortFixture, "request-mismatch-01", "review_chapter", null));
        assertThatThrownBy(() -> repository.start(shortFixture.userId(), mismatch))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("LONG_WORKFLOW_MISMATCH"));

        Fixture longFixture = fixture("long-idempotency", Storylengthprofile.long_serial, "正文");
        ParsedWritingRunStartRequest first = parse(longRequest(
                longFixture, "request-shared-0001", "review_chapter", null));
        repository.start(longFixture.userId(), first);
        ParsedWritingRunStartRequest reused = parse(longRequest(
                longFixture, "request-shared-0001", "write_chapter", null));
        assertThatThrownBy(() -> repository.start(longFixture.userId(), reused))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 显式长篇从可证明检查点恢复并幂等保留原始Job() throws Exception {
        Fixture fixture = fixture("long-resume", Storylengthprofile.long_serial, "正文");
        var started = repository.start(
                fixture.userId(),
                parse(longRequest(
                        fixture, "request-resume-start", "review_chapter", null)));
        markRecoverable(fixture, started.getId(), started.getCommandId(), "review_chapter");
        ResumeWritingRunRequest request =
                new ResumeWritingRunRequest("request-resume-0001");

        var first = repository.resume(fixture.userId(), started.getId(), request);
        var replay = repository.resume(fixture.userId(), started.getId(), request);

        assertThat(first.getEngineVersion()).isEqualTo(1);
        assertThat(first.getRunId()).isEqualTo(started.getId());
        assertThat(first.getTaskId()).isEqualTo(started.getId());
        assertThat(replay.getCommandId()).isEqualTo(first.getCommandId());
        String payload = database.dsl().select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(first.getCommandId()))
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        var job = json.readTree(payload).path("job");
        assertThat(job.path("resume").asBoolean()).isTrue();
        assertThat(job.path("operation").asString()).isEqualTo("review_chapter");
        assertThat(job.path("sourceBindings").size()).isEqualTo(3);
    }

    @Test
    void 有可见消息时兼容任务无需检查点且消息只在UI层去除首尾空白() throws Exception {
        Fixture fixture = fixture("legacy-resume", Storylengthprofile.long_serial, "正文");
        String sessionId = insertSession(fixture);
        var started = repository.start(fixture.userId(), parse("""
                {
                  "clientRequestId": "request-legacy-start2",
                  "novelId": "%s",
                  "chapterId": "%s",
                  "writingSessionId": "%s",
                  "userMessage": "开始"
                }
                """.formatted(fixture.novelId(), fixture.chapterId(), sessionId)));
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .where(WRITINGRUNCOMMAND.ID.eq(started.getCommandId()))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .where(WRITINGTASK.ID.eq(started.getId()))
                .execute();
        ResumeWritingRunRequest request = new ResumeWritingRunRequest("request-resume-0002")
                .writingSessionId(sessionId)
                .userMessage("  继续写作  ");

        var resumed = repository.resume(fixture.userId(), started.getId(), request);

        String latestMessage = database.dsl().select(WRITINGMESSAGE.CONTENT)
                .from(WRITINGMESSAGE)
                .where(WRITINGMESSAGE.SESSIONID.eq(sessionId))
                .orderBy(WRITINGMESSAGE.CREATEDAT.desc(), WRITINGMESSAGE.ID.desc())
                .limit(1)
                .fetchOne(WRITINGMESSAGE.CONTENT);
        assertThat(latestMessage).isEqualTo("继续写作");
        String payload = database.dsl().select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(resumed.getCommandId()))
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        assertThat(json.readTree(payload).path("job").path("resumeInput").path("userMessage").asString())
                .isEqualTo("  继续写作  ");
    }

    @Test
    void 恢复拒绝活动命令终态任务会话错配和待决草案() throws Exception {
        Fixture fixture = fixture("resume-conflict", Storylengthprofile.long_serial, "正文");
        var started = repository.start(
                fixture.userId(),
                parse(longRequest(
                        fixture, "request-conflict-start", "review_chapter", null)));
        ResumeWritingRunRequest visible =
                new ResumeWritingRunRequest("request-conflict-01").userMessage("继续");
        assertThatThrownBy(() -> repository.resume(fixture.userId(), started.getId(), visible))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_COMMAND_ACTIVE"));

        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .where(WRITINGRUNCOMMAND.ID.eq(started.getCommandId()))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.completed)
                .where(WRITINGTASK.ID.eq(started.getId()))
                .execute();
        assertThatThrownBy(() -> repository.resume(
                        fixture.userId(),
                        started.getId(),
                        new ResumeWritingRunRequest("request-conflict-02").userMessage("继续")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TASK_TERMINAL"));

        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.awaiting_user_review)
                .where(WRITINGTASK.ID.eq(started.getId()))
                .execute();
        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, "resume-conflict-artifact")
                .set(REVIEWARTIFACT.NOVELID, fixture.novelId())
                .set(REVIEWARTIFACT.CHAPTERID, fixture.chapterId())
                .set(REVIEWARTIFACT.TASKID, started.getId())
                .set(REVIEWARTIFACT.ARTIFACTKEY, "resume-conflict")
                .set(REVIEWARTIFACT.KIND, Reviewartifactkind.chapter_draft)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.awaiting_user)
                .set(REVIEWARTIFACT.PAYLOADJSON, "{}")
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.CREATEDAT, NOW)
                .set(REVIEWARTIFACT.UPDATEDAT, NOW)
                .execute();
        assertThatThrownBy(() -> repository.resume(
                        fixture.userId(),
                        started.getId(),
                        new ResumeWritingRunRequest("request-conflict-03").userMessage("继续")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("ARTIFACT_DECISION_REQUIRED"));
    }

    @Test
    void 活动任务取消会原子退役当前命令并可幂等重放() throws Exception {
        Fixture fixture = fixture("cancel-active", Storylengthprofile.long_serial, "正文");
        var started = repository.start(
                fixture.userId(),
                parse(longRequest(
                        fixture, "request-cancel-start-01", "review_chapter", null)));
        CancelWritingRunRequest request =
                new CancelWritingRunRequest("request-cancel-active-01");

        var first = repository.cancel(fixture.userId(), started.getId(), request);
        var replay = repository.cancel(fixture.userId(), started.getId(), request);

        assertThat(first.getEngineVersion()).isEqualTo(1);
        assertThat(first.getRunId()).isEqualTo(started.getId());
        assertThat(first.getTaskId()).isEqualTo(started.getId());
        assertThat(replay.getCommandId()).isEqualTo(first.getCommandId());
        assertThat(first.getEffective()).isTrue();
        assertThat(first.getAlreadyTerminal()).isFalse();
        assertThat(first.getCommandStatus().getValue()).isEqualTo("pending");
        assertThat(first.getCancelledCommandId()).isEqualTo(started.getCommandId());
        assertThat(first.getCancelledJobId()).isEqualTo(started.getCommandId());
        var retired = database.dsl().selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(started.getCommandId()))
                .fetchOne();
        assertThat(retired.getStatus()).isEqualTo("failed");
        assertThat(retired.getLasterror()).isEqualTo("WRITING_RUN_CANCELLED_BY_USER");
        assertThat(json.readTree(retired.getResultjson()).path("cancelCommandId").asString())
                .isEqualTo(first.getCommandId());
        String cancelPayload = database.dsl().select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(first.getCommandId()))
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        assertThat(json.readTree(cancelPayload).path("_inkforgeCommand")
                        .path("commandKind").asString())
                .isEqualTo("cancel");
        assertThat(database.dsl().fetchCount(
                        WRITINGRUNCOMMAND, WRITINGRUNCOMMAND.TASKID.eq(started.getId())))
                .isEqualTo(2);
    }

    @Test
    void 终态任务取消是保留既有成功结果的无操作命令() throws Exception {
        Fixture fixture = fixture("cancel-terminal", Storylengthprofile.long_serial, "正文");
        var started = repository.start(
                fixture.userId(),
                parse(longRequest(
                        fixture, "request-cancel-start-02", "review_chapter", null)));
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .set(WRITINGRUNCOMMAND.RESULTJSON, json.writeValueAsString(Map.of(
                        "_inkforgeTerminalCallbackResult",
                        Map.of("finalResponse", "审核通过"))))
                .set(WRITINGRUNCOMMAND.COMPLETEDAT, NOW)
                .where(WRITINGRUNCOMMAND.ID.eq(started.getCommandId()))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.completed)
                .where(WRITINGTASK.ID.eq(started.getId()))
                .execute();

        var cancelled = repository.cancel(
                fixture.userId(),
                started.getId(),
                new CancelWritingRunRequest("request-cancel-terminal-01"));

        assertThat(cancelled.getEffective()).isFalse();
        assertThat(cancelled.getAlreadyTerminal()).isTrue();
        assertThat(cancelled.getCommandStatus().getValue()).isEqualTo("succeeded");
        assertThat(cancelled.getCancelledCommandId()).isNull();
        String result = database.dsl().select(WRITINGRUNCOMMAND.RESULTJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(cancelled.getCommandId()))
                .fetchOne(WRITINGRUNCOMMAND.RESULTJSON);
        var prior = json.readTree(result).path("priorOutcome");
        assertThat(prior.path("state").asString()).isEqualTo("succeeded");
        assertThat(prior.path("result").path("kind").asString()).isEqualTo("final_message");
        assertThat(prior.path("result").path("ready").asBoolean()).isTrue();
        assertThat(prior.path("currentCommand").path("id").asString())
                .isEqualTo(started.getCommandId());
    }

    @Test
    void 取消拒绝待决草案和复用到启动请求的幂等标识() throws Exception {
        Fixture fixture = fixture("cancel-conflict", Storylengthprofile.long_serial, "正文");
        String startRequestId = "request-cancel-shared-01";
        var started = repository.start(
                fixture.userId(),
                parse(longRequest(fixture, startRequestId, "plan_chapter", null)));
        assertThatThrownBy(() -> repository.cancel(
                        fixture.userId(),
                        started.getId(),
                        new CancelWritingRunRequest(startRequestId)))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));

        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, "cancel-conflict-artifact")
                .set(REVIEWARTIFACT.NOVELID, fixture.novelId())
                .set(REVIEWARTIFACT.CHAPTERID, fixture.chapterId())
                .set(REVIEWARTIFACT.TASKID, started.getId())
                .set(REVIEWARTIFACT.ARTIFACTKEY, "cancel-conflict")
                .set(REVIEWARTIFACT.KIND, Reviewartifactkind.beat_plan)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.awaiting_user)
                .set(REVIEWARTIFACT.PAYLOADJSON, "{}")
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.CREATEDAT, NOW)
                .set(REVIEWARTIFACT.UPDATEDAT, NOW)
                .execute();
        assertThatThrownBy(() -> repository.cancel(
                        fixture.userId(),
                        started.getId(),
                        new CancelWritingRunRequest("request-cancel-artifact-01")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("ARTIFACT_DECISION_REQUIRED"));
        assertThat(database.dsl().fetchCount(
                        WRITINGRUNCOMMAND, WRITINGRUNCOMMAND.TASKID.eq(started.getId())))
                .isEqualTo(1);
    }

    private void markRecoverable(
            Fixture fixture, String taskId, String commandId, String operation) {
        String currentGraph = database.dsl().select(WRITINGTASK.GRAPHSTATEJSON)
                .from(WRITINGTASK)
                .where(WRITINGTASK.ID.eq(taskId))
                .fetchOne(WRITINGTASK.GRAPHSTATEJSON);
        Map<String, Object> graph = json.readValue(currentGraph, new tools.jackson.core.type.TypeReference<>() {});
        graph.put("phase", "active");
        graph.put("eventSequence", 1);
        graph.put("currentOperation", Map.of("kind", operation));
        graph.put("operationStage", "reviewing");
        graph.put("callbackJobId", commandId);
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .set(WRITINGRUNCOMMAND.COMPLETEDAT, NOW)
                .where(WRITINGRUNCOMMAND.ID.eq(commandId))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.GRAPHSTATEJSON, json.writeValueAsString(graph))
                .where(WRITINGTASK.ID.eq(taskId), WRITINGTASK.NOVELID.eq(fixture.novelId()))
                .execute();
    }

    private ParsedWritingRunStartRequest parse(String value) throws Exception {
        return parser.parse(new WritingRunStartBody(json.readTree(value)));
    }

    private Fixture fixture(String prefix, Storylengthprofile profile, String chapterContent) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        users.add(userId);
        database.dsl().insertInto(USER)
                .set(USER.ID, userId)
                .set(USER.USERNAME, userId)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREDITBALANCEMICROS, 1_000_000L)
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
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, chapterContent)
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, NOW)
                .set(CHAPTER.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(OUTLINE)
                .set(OUTLINE.ID, prefix + "-outline")
                .set(OUTLINE.NOVELID, novelId)
                .set(OUTLINE.CONTENT, "")
                .set(OUTLINE.CREATEDAT, NOW)
                .set(OUTLINE.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, prefix + "-bible")
                .set(WRITINGBIBLE.NOVELID, novelId)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, profile)
                .set(WRITINGBIBLE.TARGETTOTALWORDCOUNT,
                        profile == Storylengthprofile.short_medium ? 20_000 : null)
                .set(WRITINGBIBLE.CREATEDAT, NOW)
                .set(WRITINGBIBLE.UPDATEDAT, NOW)
                .execute();
        return new Fixture(userId, novelId, chapterId, prefix + "-outline");
    }

    private String insertSession(Fixture fixture) {
        String id = fixture.novelId() + "-session";
        database.dsl().insertInto(WRITINGSESSION)
                .set(WRITINGSESSION.ID, id)
                .set(WRITINGSESSION.NOVELID, fixture.novelId())
                .set(WRITINGSESSION.CHAPTERID, fixture.chapterId())
                .set(WRITINGSESSION.PHASE, "idle")
                .set(WRITINGSESSION.CREATEDAT, NOW)
                .set(WRITINGSESSION.UPDATEDAT, NOW)
                .execute();
        return id;
    }

    private void insertShortSource(Fixture fixture, String kind, String text) {
        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, fixture.novelId() + "-source")
                .set(REVIEWARTIFACT.NOVELID, fixture.novelId())
                .set(REVIEWARTIFACT.ARTIFACTKEY, "short-medium:source:" + fixture.novelId())
                .set(REVIEWARTIFACT.KIND, Reviewartifactkind.freeform_markdown)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.applied)
                .set(REVIEWARTIFACT.PAYLOADJSON, json.writeValueAsString(Map.of(
                        "sourceKind", kind, "sourceText", text)))
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.CREATEDAT, NOW)
                .set(REVIEWARTIFACT.UPDATEDAT, NOW)
                .set(REVIEWARTIFACT.APPLIEDAT, NOW)
                .execute();
    }

    private static String longRequest(
            Fixture fixture, String clientRequestId, String operation, String selectionSuffix) {
        String suffix = selectionSuffix == null ? "" : selectionSuffix;
        return """
                {
                  "clientRequestId": "%s",
                  "workflow": "long_serial",
                  "novelId": "%s",
                  "chapterId": "%s",
                  "operation": "%s",
                  "target": {"type": "chapter", "id": "%s"},
                  "scope": {"kind": "chapter", "chapterId": "%s"},
                  "userInstruction": "请按约束执行"%s
                }
                """.formatted(
                clientRequestId,
                fixture.novelId(),
                fixture.chapterId(),
                operation,
                fixture.chapterId(),
                fixture.chapterId(),
                suffix);
    }

    private static String sha256(String value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8)));
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

    private record Fixture(String userId, String novelId, String chapterId, String outlineId) {}
}
