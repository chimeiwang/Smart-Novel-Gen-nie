package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.writing.domain.WritingRunCursor;
import cn.inkforge.core.writing.domain.WritingRunOutcomeProjector;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
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
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqWritingRunQueryRepositoryTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-08-25T01:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T07:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_query_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqWritingRunQueryRepository repository;
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
        ObjectMapper json = new ObjectMapper();
        repository = new JooqWritingRunQueryRepository(
                database,
                new WritingRunStatusProjector(json, new WritingRunOutcomeProjector(), CLOCK),
                new WritingRunCursor(json));
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
    void 单任务读取执行归属校验并返回统一状态() {
        Fixture owner = fixture("writing-query-owner");
        Fixture other = fixture("writing-query-other");
        insertTask(owner, "task-1", NOW, null);
        insertCommand("task-1", "command-1", "review_chapter", "pending", NOW);

        var status = repository.get(owner.userId(), "task-1");

        assertThat(status.getTaskId()).isEqualTo("task-1");
        assertThat(status.getOutcome().getState().getValue()).isEqualTo("queued");
        assertThatThrownBy(() -> repository.get(other.userId(), "task-1"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("WRITING_TASK_FORBIDDEN");
                });
    }

    @Test
    void 列表按创建时间和ID稳定倒序且保留无会话任务() {
        Fixture fixture = fixture("writing-query-list");
        insertTask(fixture, "task-older", NOW, "session-1");
        insertTask(fixture, "task-newer", NOW.plusSeconds(1), null);
        insertCommand("task-older", "command-older", "plan_chapter", "pending", NOW);
        insertCommand(
                "task-newer", "command-newer", "review_chapter", "pending", NOW.plusSeconds(1));

        var response = repository.list(
                fixture.userId(), fixture.novelId(), null, null, null, null, null, 10);

        assertThat(response.getItems())
                .extracting(item -> item.getTaskId())
                .containsExactly("task-newer", "task-older");
        assertThat(response.getItems().getFirst().getWritingSessionId()).isNull();
        assertThat(response.getNextCursor()).isNull();
    }

    @Test
    void 派生操作和结果过滤支持严格游标续页() {
        Fixture fixture = fixture("writing-query-filter");
        insertTask(fixture, "task-1", NOW, null);
        insertTask(fixture, "task-2", NOW.plusSeconds(1), null);
        insertTask(fixture, "task-3", NOW.plusSeconds(2), null);
        insertCommand("task-1", "command-1", "plan_chapter", "pending", NOW);
        insertCommand("task-2", "command-2", "plan_chapter", "pending", NOW.plusSeconds(1));
        insertCommand("task-3", "command-3", "review_chapter", "pending", NOW.plusSeconds(2));

        var first = repository.list(
                fixture.userId(),
                fixture.novelId(),
                null,
                null,
                "plan_chapter",
                "queued",
                null,
                1);
        assertThat(first.getItems()).extracting(item -> item.getTaskId()).containsExactly("task-2");
        assertThat(first.getNextCursor()).isNotNull();

        var second = repository.list(
                fixture.userId(),
                fixture.novelId(),
                null,
                null,
                "plan_chapter",
                "queued",
                first.getNextCursor(),
                1);
        assertThat(second.getItems()).extracting(item -> item.getTaskId()).containsExactly("task-1");
        assertThat(second.getNextCursor()).isNull();
    }

    @Test
    void 列表拒绝未知过滤值和非规范游标() {
        Fixture fixture = fixture("writing-query-invalid");
        assertThatThrownBy(() -> repository.list(
                        fixture.userId(), fixture.novelId(), null, null,
                        "unknown", null, null, 10))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("VALIDATION_ERROR"));
        assertThatThrownBy(() -> repository.list(
                        fixture.userId(), fixture.novelId(), null, null,
                        null, "unknown", null, 10))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("VALIDATION_ERROR"));
        assertThatThrownBy(() -> repository.list(
                        fixture.userId(), fixture.novelId(), null, null,
                        null, null, "e30=", 10))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_RUN_CURSOR_INVALID"));
    }

    private Fixture fixture(String prefix) {
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
                .set(CHAPTER.CONTENT, "正文")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, NOW)
                .set(CHAPTER.UPDATEDAT, NOW)
                .execute();
        return new Fixture(userId, novelId, chapterId);
    }

    private void insertTask(
            Fixture fixture, String taskId, LocalDateTime createdAt, String sessionId) {
        if (sessionId != null
                && database.dsl().fetchCount(WRITINGSESSION, WRITINGSESSION.ID.eq(sessionId)) == 0) {
            database.dsl().insertInto(WRITINGSESSION)
                    .set(WRITINGSESSION.ID, sessionId)
                    .set(WRITINGSESSION.NOVELID, fixture.novelId())
                    .set(WRITINGSESSION.CHAPTERID, fixture.chapterId())
                    .set(WRITINGSESSION.PHASE, "idle")
                    .set(WRITINGSESSION.CREATEDAT, createdAt)
                    .set(WRITINGSESSION.UPDATEDAT, createdAt)
                    .execute();
        }
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, fixture.novelId())
                .set(WRITINGTASK.CHAPTERID, fixture.chapterId())
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "写作,编辑")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.WRITINGSESSIONID, sessionId)
                .set(WRITINGTASK.CREATEDAT, createdAt)
                .set(WRITINGTASK.UPDATEDAT, createdAt)
                .execute();
    }

    private void insertCommand(
            String taskId,
            String commandId,
            String operation,
            String status,
            LocalDateTime createdAt) {
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, commandId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, new ObjectMapper().writeValueAsString(Map.of(
                        "_inkforgeCommand", Map.of("schemaVersion", 1),
                        "job", Map.of(
                                "workflow", "long_serial",
                                "operation", operation,
                                "target", Map.of("type", "chapter", "id", "ignored"),
                                "scope", Map.of("kind", "chapter", "chapterId", "ignored")))))
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, "key-" + commandId)
                .set(WRITINGRUNCOMMAND.STATUS, status)
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, createdAt)
                .set(WRITINGRUNCOMMAND.CREATEDAT, createdAt)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, createdAt)
                .execute();
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

    private record Fixture(String userId, String novelId, String chapterId) {}
}
