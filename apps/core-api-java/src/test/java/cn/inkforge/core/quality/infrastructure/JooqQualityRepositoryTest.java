package cn.inkforge.core.quality.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ConsistencyScores;
import cn.inkforge.contracts.api.QualityRunSuccessRequest;
import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.UpdateQualityCheckRequest;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Workflowrunstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullable;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqQualityRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-25T01:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T07:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_quality_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqQualityRepository repository;
    private static ObjectMapper json;
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
        json = new ObjectMapper();
        repository = new JooqQualityRepository(
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
    void 创建运行必须冻结完整正文并支持相同请求精确重放() throws Exception {
        Fixture fixture = fixture("quality-create", "甲😀乙\n完整正文");
        RunQualityCheckRequest request = new RunQualityCheckRequest(
                        "quality-create-request-0001")
                .taskId(fixture.taskId())
                .message("检查当前正文");

        var first = repository.createRun(fixture.userId(), fixture.checkId(), request);
        var replay = repository.createRun(fixture.userId(), fixture.checkId(), request);

        assertThat(first.created()).isTrue();
        assertThat(replay.created()).isFalse();
        assertThat(replay.record().runId()).isEqualTo(first.record().runId());
        assertThat(database.dsl().fetchCount(
                        WORKFLOWRUN,
                        WORKFLOWRUN.SOURCEID.eq(fixture.checkId())))
                .isEqualTo(1);
        JsonNode input = json.readTree(database.dsl().select(WORKFLOWRUN.INPUT)
                .from(WORKFLOWRUN)
                .where(WORKFLOWRUN.ID.eq(first.record().runId()))
                .fetchSingle(WORKFLOWRUN.INPUT));
        assertThat(input.get("_inkforgeCommand").get("commandKind").asText())
                .isEqualTo("quality_run");
        assertThat(input.get("job").get("chapterContent").asText())
                .isEqualTo("甲😀乙\n完整正文");
        assertThat(input.get("job").get("chapterContentSha256").asText())
                .hasSize(64);
        assertThat(repository.context(
                                fixture.userId(),
                                fixture.checkId(),
                                first.record().runId(),
                                fixture.taskId(),
                                "检查当前正文")
                        .getChapterContent())
                .isEqualTo("甲😀乙\n完整正文");

        request.setMessage(JsonNullable.of("复用标识但修改消息"));
        assertThatThrownBy(() -> repository.createRun(
                        fixture.userId(), fixture.checkId(), request))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 运行门禁必须拒绝非待审章节错误任务与第二个活动运行() {
        Fixture fixture = fixture("quality-gates", "正文");
        RunQualityCheckRequest request = new RunQualityCheckRequest(
                "quality-gates-request-0001");

        database.dsl().update(CHAPTER)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .where(CHAPTER.ID.eq(fixture.chapterId()))
                .execute();
        assertThatThrownBy(() -> repository.createRun(
                        fixture.userId(), fixture.checkId(), request))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("QUALITY_CHECK_CHAPTER_NOT_IN_REVIEW"));

        database.dsl().update(CHAPTER)
                .set(CHAPTER.STATUS, Chapterstatus.review)
                .where(CHAPTER.ID.eq(fixture.chapterId()))
                .execute();
        RunQualityCheckRequest wrongTask = new RunQualityCheckRequest(
                        "quality-gates-request-0002")
                .taskId("missing-task");
        assertThatThrownBy(() -> repository.createRun(
                        fixture.userId(), fixture.checkId(), wrongTask))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("QUALITY_TASK_MISMATCH"));

        repository.createRun(
                fixture.userId(),
                fixture.checkId(),
                new RunQualityCheckRequest("quality-gates-request-0003"));
        assertThatThrownBy(() -> repository.createRun(
                        fixture.userId(),
                        fixture.checkId(),
                        new RunQualityCheckRequest("quality-gates-request-0004")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("QUALITY_RUN_ACTIVE"));
    }

    @Test
    void 质量运行必须与写作命令共用用户级幂等命名空间() {
        Fixture fixture = fixture("quality-cross-command", "正文");
        String clientRequestId = "quality-cross-command-0001";
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, fixture.taskId() + "-command")
                .set(WRITINGRUNCOMMAND.TASKID, fixture.taskId())
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, json.writeValueAsString(java.util.Map.of(
                        "_inkforgeCommand", java.util.Map.of(
                                "schemaVersion", 1,
                                "clientRequestId", clientRequestId,
                                "commandKind", "start",
                                "resourceIdentity", java.util.Map.of("taskId", fixture.taskId()),
                                "normalizedBody", java.util.Map.of(),
                                "requestFingerprint", "a".repeat(64)),
                        "job", java.util.Map.of())))
                .set(
                        WRITINGRUNCOMMAND.IDEMPOTENCYKEY,
                        "v1:" + fixture.userId() + ":" + clientRequestId)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, INITIAL)
                .set(WRITINGRUNCOMMAND.CREATEDAT, INITIAL)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, INITIAL)
                .execute();

        assertThatThrownBy(() -> repository.createRun(
                        fixture.userId(),
                        fixture.checkId(),
                        new RunQualityCheckRequest(clientRequestId)))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
        assertThat(database.dsl().fetchCount(
                        WORKFLOWRUN,
                        WORKFLOWRUN.SOURCEID.eq(fixture.checkId())))
                .isZero();
        assertThat(database.dsl().select(CHAPTERQUALITYCHECK.STATUS)
                        .from(CHAPTERQUALITYCHECK)
                        .where(CHAPTERQUALITYCHECK.ID.eq(fixture.checkId()))
                        .fetchSingle(CHAPTERQUALITYCHECK.STATUS))
                .isEqualTo(Qualitycheckstatus.pending);
    }

    @Test
    void 公开状态修改必须CAS并在重置时一次清空全部旧结果() {
        Fixture fixture = fixture("quality-update", "正文");
        database.dsl().update(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.completed)
                .set(CHAPTERQUALITYCHECK.RESULT, "旧报告")
                .set(CHAPTERQUALITYCHECK.SCOREHOOK, 91)
                .set(CHAPTERQUALITYCHECK.SCOREOVERALL, 88)
                .set(CHAPTERQUALITYCHECK.QUALITYGATE, "pass")
                .set(CHAPTERQUALITYCHECK.REWRITEBRIEF, "旧返工摘要")
                .where(CHAPTERQUALITYCHECK.ID.eq(fixture.checkId()))
                .execute();
        UpdateQualityCheckRequest request = new UpdateQualityCheckRequest(
                        DatabaseTimestamp.api(INITIAL),
                        UpdateQualityCheckRequest.StatusEnum.PENDING)
                .resetResult(true);

        var result = repository.updateStatus(fixture.userId(), fixture.checkId(), request);

        assertThat(result.getStatus().getValue()).isEqualTo("pending");
        assertThat(result.getResult()).isNull();
        assertThat(result.getScoreHook()).isNull();
        assertThat(result.getScoreOverall()).isNull();
        assertThat(result.getQualityGate()).isNull();
        assertThat(result.getRewriteBrief()).isNull();
        assertThat(result.getUpdatedAt()).isAfter(DatabaseTimestamp.api(INITIAL));

        UpdateQualityCheckRequest stale = new UpdateQualityCheckRequest(
                DatabaseTimestamp.api(INITIAL),
                UpdateQualityCheckRequest.StatusEnum.SKIPPED);
        assertThatThrownBy(() -> repository.updateStatus(
                        fixture.userId(), fixture.checkId(), stale))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("QUALITY_CHECK_VERSION_CONFLICT"));
    }

    @Test
    void 最新成功回调必须保存完整报告并只写五维平均总分() throws Exception {
        Fixture fixture = fixture("quality-success", "完整正文");
        var creation = repository.createRun(
                fixture.userId(),
                fixture.checkId(),
                new RunQualityCheckRequest("quality-success-request-0001"));
        QualityRunSuccessRequest report = report(
                fixture, creation.record().runId(), "完整一致性报告");

        repository.completeRun(
                fixture.userId(),
                fixture.checkId(),
                creation.record().runId(),
                fixture.novelId(),
                report);
        repository.completeRun(
                fixture.userId(),
                fixture.checkId(),
                creation.record().runId(),
                fixture.novelId(),
                report);

        var check = database.dsl().selectFrom(CHAPTERQUALITYCHECK)
                .where(CHAPTERQUALITYCHECK.ID.eq(fixture.checkId()))
                .fetchSingle();
        assertThat(check.getStatus()).isEqualTo(Qualitycheckstatus.completed);
        assertThat(check.getResult()).isEqualTo("完整一致性报告");
        assertThat(check.getScoreoverall()).isEqualTo(84);
        assertThat(check.getScorehook()).isNull();
        assertThat(check.getQualitygate()).isEqualTo("revise");
        assertThat(check.getRewritebrief()).isEqualTo("修正时间线");
        assertThat(json.readTree(database.dsl().select(WORKFLOWRUN.OUTPUT)
                        .from(WORKFLOWRUN)
                        .where(WORKFLOWRUN.ID.eq(creation.record().runId()))
                        .fetchSingle(WORKFLOWRUN.OUTPUT))
                .get("report").asText())
                .isEqualTo("完整一致性报告");
    }

    @Test
    void 正文变化时过期结果必须取消运行并重置当前检查项() {
        Fixture fixture = fixture("quality-source-change", "发起时正文");
        var creation = repository.createRun(
                fixture.userId(),
                fixture.checkId(),
                new RunQualityCheckRequest("quality-source-request-0001"));
        database.dsl().update(CHAPTER)
                .set(CHAPTER.CONTENT, "运行期间修改后的正文")
                .set(CHAPTER.UPDATEDAT, INITIAL.plusSeconds(1))
                .where(CHAPTER.ID.eq(fixture.chapterId()))
                .execute();

        repository.completeRun(
                fixture.userId(),
                fixture.checkId(),
                creation.record().runId(),
                fixture.novelId(),
                report(fixture, creation.record().runId(), "旧正文报告"));

        assertThat(database.dsl().select(WORKFLOWRUN.STATUS, WORKFLOWRUN.ERRORMESSAGE)
                        .from(WORKFLOWRUN)
                        .where(WORKFLOWRUN.ID.eq(creation.record().runId()))
                        .fetchSingle())
                .satisfies(row -> {
                    assertThat(row.value1()).isEqualTo(Workflowrunstatus.cancelled);
                    assertThat(row.value2()).isEqualTo("QUALITY_SOURCE_CHANGED");
                });
        var check = database.dsl().selectFrom(CHAPTERQUALITYCHECK)
                .where(CHAPTERQUALITYCHECK.ID.eq(fixture.checkId()))
                .fetchSingle();
        assertThat(check.getStatus()).isEqualTo(Qualitycheckstatus.pending);
        assertThat(check.getResult()).isNull();
    }

    @Test
    void 旧运行失败只能收敛自身不能覆盖较新的检查状态() {
        Fixture fixture = fixture("quality-stale", "正文");
        var old = repository.createRun(
                fixture.userId(),
                fixture.checkId(),
                new RunQualityCheckRequest("quality-stale-request-0001"));
        database.dsl().update(WORKFLOWRUN)
                .set(WORKFLOWRUN.STATUS, Workflowrunstatus.failed)
                .where(WORKFLOWRUN.ID.eq(old.record().runId()))
                .execute();
        var current = repository.createRun(
                fixture.userId(),
                fixture.checkId(),
                new RunQualityCheckRequest("quality-stale-request-0002"));
        database.dsl().update(WORKFLOWRUN)
                .set(WORKFLOWRUN.STATUS, Workflowrunstatus.running)
                .where(WORKFLOWRUN.ID.eq(old.record().runId()))
                .execute();

        repository.failRun(
                fixture.userId(),
                fixture.checkId(),
                old.record().runId(),
                fixture.novelId());

        assertThat(database.dsl().select(CHAPTERQUALITYCHECK.STATUS)
                        .from(CHAPTERQUALITYCHECK)
                        .where(CHAPTERQUALITYCHECK.ID.eq(fixture.checkId()))
                        .fetchSingle(CHAPTERQUALITYCHECK.STATUS))
                .isEqualTo(Qualitycheckstatus.running);
        assertThat(database.dsl().select(WORKFLOWRUN.STATUS)
                        .from(WORKFLOWRUN)
                        .where(WORKFLOWRUN.ID.eq(old.record().runId()))
                        .fetchSingle(WORKFLOWRUN.STATUS))
                .isEqualTo(Workflowrunstatus.failed);
        assertThat(current.record().runId()).isNotEqualTo(old.record().runId());
    }

    private Fixture fixture(String prefix, String content) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        String checkId = prefix + "-check";
        String taskId = prefix + "-task";
        users.add(userId);
        database.dsl().insertInto(USER)
                .set(USER.ID, userId)
                .set(USER.USERNAME, userId)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREDITBALANCEMICROS, 1_000_000L)
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, prefix)
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, content)
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.review)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.ID, checkId)
                .set(CHAPTERQUALITYCHECK.CHAPTERID, chapterId)
                .set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                .set(CHAPTERQUALITYCHECK.TITLE, "一致性终检")
                .set(CHAPTERQUALITYCHECK.CREATEDAT, INITIAL)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, novelId)
                .set(WRITINGTASK.CHAPTERID, chapterId)
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "[]")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.CREATEDAT, INITIAL)
                .set(WRITINGTASK.UPDATEDAT, INITIAL)
                .execute();
        return new Fixture(userId, novelId, chapterId, checkId, taskId);
    }

    private static QualityRunSuccessRequest report(
            Fixture fixture, String runId, String report) {
        ConsistencyScores scores = new ConsistencyScores(
                BigDecimal.valueOf(84),
                BigDecimal.valueOf(81),
                BigDecimal.valueOf(88),
                BigDecimal.valueOf(83),
                BigDecimal.valueOf(82));
        return new QualityRunSuccessRequest(
                        List.of(),
                        fixture.novelId(),
                        QualityRunSuccessRequest.QualityGateEnum.REVISE,
                        report,
                        runId,
                        scores,
                        runId,
                        fixture.userId())
                .rewriteBrief("修正时间线");
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
            String userId, String novelId, String chapterId, String checkId, String taskId) {}
}
