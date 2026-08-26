package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGEVENTOUTBOX;
import static cn.inkforge.core.db.generated.Tables.WRITINGMESSAGE;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.writing.domain.WritingBoundaryEvent;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqWritingCallbackRepositoryTest {

    private static final LocalDateTime NOW =
            LocalDateTime.parse("2026-08-25T09:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T09:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_callback_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static JooqWritingCallbackRepository repository;
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
        json = JsonMapper.builder().build();
        repository = new JooqWritingCallbackRepository(
                database, new CuidV1Generator(CLOCK), CLOCK, json);
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
    void 检查点序号必须单调且完全相同重放才可幂等() {
        Fixture fixture = fixture("callback-checkpoint", false);
        insertTaskAndCommand(fixture, "task-checkpoint", "job-checkpoint", longPayload(), false);
        String checkpoint = json.writeValueAsString(longGraph(
                fixture, "task-checkpoint", "job-checkpoint", 1, "active"));

        var first = repository.saveCheckpoint(
                "task-checkpoint", "job-checkpoint", checkpoint, "active", 1, null);
        var replay = repository.saveCheckpoint(
                "task-checkpoint", "job-checkpoint", checkpoint, "active", 1, null);
        Map<String, Object> changed = longGraph(
                fixture, "task-checkpoint", "job-checkpoint", 1, "active");
        changed.put("operationStage", "changed");
        var conflict = repository.saveCheckpoint(
                "task-checkpoint",
                "job-checkpoint",
                json.writeValueAsString(changed),
                "active",
                1,
                null);
        var stale = repository.markProcessing("task-checkpoint", "job-checkpoint", 1);

        assertThat(first.accepted()).isTrue();
        assertThat(first.commandStatus()).isEqualTo("processing");
        assertThat(replay.accepted()).isTrue();
        assertThat(replay.alreadyApplied()).isTrue();
        assertThat(conflict.accepted()).isFalse();
        assertThat(conflict.rejectionCode()).isEqualTo("WRITING_CHECKPOINT_CONFLICT");
        assertThat(stale.rejectionCode()).isEqualTo("WRITING_CALLBACK_SEQUENCE_STALE");
    }

    @Test
    void 等待审核检查点必须与Outbox和命令终态原子提交() {
        Fixture fixture = fixture("callback-waiting", false);
        insertTaskAndCommand(fixture, "task-waiting", "job-waiting", longPayload(), false);
        String checkpoint = json.writeValueAsString(longGraph(
                fixture, "task-waiting", "job-waiting", 1, "awaiting_user_review"));
        WritingBoundaryEvent boundary = new WritingBoundaryEvent(
                "event-waiting",
                1,
                "writing:job-waiting:waiting:1",
                "artifact_awaiting_user_approval",
                Map.of("taskId", "task-waiting", "artifactId", "artifact-1"));

        var first = repository.saveCheckpoint(
                "task-waiting",
                "job-waiting",
                checkpoint,
                "awaiting_user_review",
                1,
                boundary);
        var replay = repository.saveCheckpoint(
                "task-waiting",
                "job-waiting",
                checkpoint,
                "awaiting_user_review",
                1,
                boundary);

        assertThat(first.accepted()).isTrue();
        assertThat(first.taskPhase()).isEqualTo("awaiting_user_review");
        assertThat(first.commandStatus()).isEqualTo("succeeded");
        assertThat(first.outboxEventId()).isNotBlank();
        assertThat(replay.outboxEventId()).isEqualTo(first.outboxEventId());
        assertThat(database.dsl().fetchCount(
                        WRITINGEVENTOUTBOX,
                        WRITINGEVENTOUTBOX.TASKID.eq("task-waiting")))
                .isEqualTo(1);
    }

    @Test
    void 完成回调必须原子保存完整结果可见消息和终态事件() {
        Fixture fixture = fixture("callback-complete", true);
        insertTaskAndCommand(fixture, "task-complete", "job-complete", longPayload(), true);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("finalResponse", "  完整审核结论  ");
        result.put("agentOutputs", Map.of("写作", "完整输出"));
        WritingBoundaryEvent boundary = terminalBoundary(
                "event-complete", 1, "job-complete", "completed");

        var first = repository.complete(
                "task-complete",
                "job-complete",
                result,
                "完整审核结论",
                1,
                boundary);
        var replay = repository.complete(
                "task-complete",
                "job-complete",
                result,
                "完整审核结论",
                1,
                boundary);
        Map<String, Object> changed = new LinkedHashMap<>(result);
        changed.put("finalResponse", "不同结论");
        var conflict = repository.complete(
                "task-complete",
                "job-complete",
                changed,
                "不同结论",
                1,
                boundary);

        assertThat(first.accepted()).isTrue();
        assertThat(first.taskPhase()).isEqualTo("completed");
        assertThat(replay.accepted()).isTrue();
        assertThat(replay.alreadyApplied()).isTrue();
        assertThat(conflict.rejectionCode()).isEqualTo("WRITING_CALLBACK_RESULT_CONFLICT");
        assertThat(database.dsl().select(WRITINGTASK.FINALCONTENT)
                        .from(WRITINGTASK)
                        .where(WRITINGTASK.ID.eq("task-complete"))
                        .fetchOne(WRITINGTASK.FINALCONTENT))
                .isEqualTo("  完整审核结论  ");
        assertThat(database.dsl().select(WRITINGMESSAGE.CONTENT)
                        .from(WRITINGMESSAGE)
                        .where(WRITINGMESSAGE.SESSIONID.eq(fixture.sessionId()))
                        .fetchOne(WRITINGMESSAGE.CONTENT))
                .isEqualTo("完整审核结论");
        String commandResult = database.dsl().select(WRITINGRUNCOMMAND.RESULTJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq("job-complete"))
                .fetchOne(WRITINGRUNCOMMAND.RESULTJSON);
        assertThat(json.readTree(commandResult)
                        .path("_inkforgeTerminalCallbackResult")
                        .path("agentOutputs")
                        .path("写作")
                        .asString())
                .isEqualTo("完整输出");
        assertThat(database.dsl().fetchCount(
                        WRITINGMESSAGE,
                        WRITINGMESSAGE.SESSIONID.eq(fixture.sessionId())))
                .isEqualTo(1);
    }

    @Test
    void 失败回调必须稳定收敛且相同终态可以安全重放() {
        Fixture fixture = fixture("callback-fail", false);
        insertTaskAndCommand(fixture, "task-fail", "job-fail", longPayload(), false);
        WritingBoundaryEvent boundary = terminalBoundary(
                "event-fail", 1, "job-fail", "error");

        var first = repository.fail(
                "task-fail", "job-fail", "MODEL_FAILED", 1, boundary);
        var replay = repository.fail(
                "task-fail", "job-fail", "MODEL_FAILED", 1, boundary);
        var conflict = repository.fail(
                "task-fail", "job-fail", "OTHER_FAILURE", 1, boundary);

        assertThat(first.accepted()).isTrue();
        assertThat(first.taskPhase()).isEqualTo("error");
        assertThat(first.commandStatus()).isEqualTo("failed");
        assertThat(replay.alreadyApplied()).isTrue();
        assertThat(conflict.rejectionCode()).isEqualTo("WRITING_CALLBACK_RESULT_CONFLICT");
        String graph = database.dsl().select(WRITINGTASK.GRAPHSTATEJSON)
                .from(WRITINGTASK)
                .where(WRITINGTASK.ID.eq("task-fail"))
                .fetchOne(WRITINGTASK.GRAPHSTATEJSON);
        assertThat(json.readTree(graph).path("errorMessage").asString())
                .isEqualTo("智能体运行失败：MODEL_FAILED");
    }

    @Test
    void 中短篇完成必须创建不可变候选和Revision且可按Job重放() {
        Fixture fixture = fixture("callback-short", false);
        Map<String, Object> payload = shortOutlinePayload();
        insertTaskAndCommand(fixture, "task-short", "job-short", payload, false);
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.GRAPHSTATEJSON, json.writeValueAsString(Map.of(
                        "workflow", "short_medium",
                        "operation", "generate_outline",
                        "phase", "active",
                        "eventSequence", 0)))
                .where(WRITINGTASK.ID.eq("task-short"))
                .execute();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("resultType", "short_medium_document");
        result.put("operation", "generate_outline");
        result.put("documentType", "outline");
        result.put("content", "第一幕\n\n第二幕");
        result.put("sourceOutlineVersionId", null);

        var completed = repository.complete(
                "task-short",
                "job-short",
                result,
                "",
                1,
                terminalBoundary("event-short", 1, "job-short", "completed"));

        assertThat(completed.accepted()).isTrue();
        String artifactId = database.dsl().select(WRITINGRUNCOMMAND.ARTIFACTID)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq("job-short"))
                .fetchOne(WRITINGRUNCOMMAND.ARTIFACTID);
        assertThat(artifactId).isNotBlank();
        assertThat(database.dsl().select(REVIEWARTIFACT.STATUS)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(artifactId))
                        .fetchOne(REVIEWARTIFACT.STATUS))
                .isEqualTo(Reviewartifactstatus.awaiting_user);
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACTREVISION,
                        REVIEWARTIFACTREVISION.ARTIFACTID.eq(artifactId)))
                .isEqualTo(1);
        String commandResult = database.dsl().select(WRITINGRUNCOMMAND.RESULTJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq("job-short"))
                .fetchOne(WRITINGRUNCOMMAND.RESULTJSON);
        assertThat(json.readTree(commandResult).path("candidateVersionId").asString())
                .isEqualTo(artifactId);
    }

    @Test
    void 中短篇结果身份字段类型错误必须归类为完成结果不匹配() {
        Fixture fixture = fixture("callback-short-mismatch", false);
        insertTaskAndCommand(
                fixture, "task-short-mismatch", "job-short-mismatch", shortOutlinePayload(), false);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("resultType", "short_medium_document");
        result.put("operation", "generate_outline");
        result.put("documentType", "outline");
        result.put("content", "第一幕");
        result.put("sourceOutlineVersionId", 1);

        assertThatThrownBy(() -> repository.complete(
                        "task-short-mismatch",
                        "job-short-mismatch",
                        result,
                        "",
                        1,
                        terminalBoundary(
                                "event-short-mismatch", 1, "job-short-mismatch", "completed")))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code())
                                .isEqualTo("SHORT_MEDIUM_COMPLETION_IDENTITY_MISMATCH"));
    }

    private Fixture fixture(String prefix, boolean withSession) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        String sessionId = withSession ? prefix + "-session" : null;
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
                .set(CHAPTER.CONTENT, "")
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
        if (sessionId != null) {
            database.dsl().insertInto(WRITINGSESSION)
                    .set(WRITINGSESSION.ID, sessionId)
                    .set(WRITINGSESSION.NOVELID, novelId)
                    .set(WRITINGSESSION.CHAPTERID, chapterId)
                    .set(WRITINGSESSION.PHASE, "idle")
                    .set(WRITINGSESSION.CREATEDAT, NOW)
                    .set(WRITINGSESSION.UPDATEDAT, NOW)
                    .execute();
        }
        return new Fixture(userId, novelId, chapterId, sessionId);
    }

    private void insertTaskAndCommand(
            Fixture fixture,
            String taskId,
            String jobId,
            Map<String, Object> payload,
            boolean withSession) {
        Map<String, Object> graph = longGraph(fixture, taskId, jobId, 0, "active");
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, fixture.novelId())
                .set(WRITINGTASK.CHAPTERID, fixture.chapterId())
                .set(WRITINGTASK.WRITINGSESSIONID, withSession ? fixture.sessionId() : null)
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "写作")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.GRAPHSTATEJSON, json.writeValueAsString(graph))
                .set(WRITINGTASK.CREATEDAT, NOW)
                .set(WRITINGTASK.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, jobId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, json.writeValueAsString(payload))
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, fixture.userId() + ":" + jobId)
                .set(WRITINGRUNCOMMAND.STATUS, "pending")
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, NOW)
                .set(WRITINGRUNCOMMAND.CREATEDAT, NOW)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, NOW)
                .execute();
    }

    private static Map<String, Object> longGraph(
            Fixture fixture,
            String taskId,
            String jobId,
            int sequence,
            String phase) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("taskId", taskId);
        value.put("userId", fixture.userId());
        value.put("novelId", fixture.novelId());
        value.put("chapterId", fixture.chapterId());
        value.put("targetWordCount", 4_000);
        value.put("conversationHistory", List.of());
        value.put("currentOperation", Map.of("kind", "review_chapter"));
        value.put("operationStage", "reviewing");
        value.put("callbackJobId", jobId);
        value.put("eventSequence", sequence);
        value.put("phase", phase);
        if ("awaiting_user_review".equals(phase)) {
            value.put("activeArtifactId", "artifact-1");
        }
        return value;
    }

    private static Map<String, Object> longPayload() {
        return Map.of(
                "version", 1,
                "resume", false,
                "chapterId", "ignored-by-callback",
                "writingSessionId", "none");
    }

    private static Map<String, Object> shortOutlinePayload() {
        Map<String, Object> value = new LinkedHashMap<>();
        for (String field : List.of(
                "workflow", "operation", "documentType", "chapterId",
                "baseVersionId", "baseContent", "baseContentHash",
                "sourceOutlineVersionId", "sourceOutlineContent",
                "sourceOutlineContentHash", "selectionStart", "selectionEnd",
                "selectedText", "selectedTextHash", "contextBefore", "contextAfter",
                "userInstruction", "targetTotalWordCount", "sourceKind", "sourceText")) {
            value.put(field, null);
        }
        value.put("workflow", "short_medium");
        value.put("operation", "generate_outline");
        value.put("documentType", "outline");
        value.put("userInstruction", "生成大纲");
        value.put("targetTotalWordCount", 20_000);
        value.put("sourceKind", "idea");
        value.put("sourceText", "一个关于选择的故事");
        return value;
    }

    private static WritingBoundaryEvent terminalBoundary(
            String eventId, int sequence, String jobId, String type) {
        return new WritingBoundaryEvent(
                eventId,
                sequence,
                "writing:" + jobId + ":terminal",
                type,
                Map.of("taskId", jobId));
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
            String userId, String novelId, String chapterId, String sessionId) {}
}
