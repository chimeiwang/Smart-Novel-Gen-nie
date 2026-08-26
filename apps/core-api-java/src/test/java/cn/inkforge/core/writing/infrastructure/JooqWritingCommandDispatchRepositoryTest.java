package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
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
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqWritingCommandDispatchRepositoryTest {

    private static final LocalDateTime NOW =
            LocalDateTime.parse("2026-08-25T08:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T08:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_dispatch_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static JooqWritingCommandDispatchRepository repository;
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
        repository = new JooqWritingCommandDispatchRepository(database, CLOCK, json);
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
    void 只领取到期Pending与过期活动命令并按稳定顺序返回() {
        Fixture fixture = fixture("dispatch-claim");
        insertCommand(fixture, "task-due", "command-due", "pending", NOW.minusSeconds(5), NOW);
        insertCommand(fixture, "task-future", "command-future", "pending", NOW.plusMinutes(1), NOW);
        insertCommand(
                fixture,
                "task-stale",
                "command-stale",
                "submitted",
                NOW.minusMinutes(20),
                NOW.minusMinutes(20));
        insertCommand(
                fixture,
                "task-fresh",
                "command-fresh",
                "processing",
                NOW.minusMinutes(20),
                NOW.minusMinutes(2));

        var claimed = repository.claimDue(20, NOW.minusMinutes(10));

        assertThat(claimed).extracting(record -> record.id())
                .containsExactly("command-stale", "command-due");
        assertThat(claimed.getFirst().userId()).isEqualTo(fixture.userId());
        assertThat(claimed.getFirst().job()).containsEntry("resume", false);
    }

    @Test
    void 提交标记与失败退避必须保留稳定命令身份() {
        Fixture fixture = fixture("dispatch-retry");
        insertCommand(fixture, "task-retry", "command-retry", "pending", NOW, NOW);

        var submitted = repository.markAgentActive("command-retry");
        var retried = repository.recordDispatchFailure(
                "command-retry", "错".repeat(140));

        assertThat(submitted.status()).isEqualTo("submitted");
        assertThat(retried.id()).isEqualTo("command-retry");
        assertThat(retried.attemptCount()).isEqualTo(1);
        var persisted = database.dsl().selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq("command-retry"))
                .fetchOne();
        assertThat(persisted.getSubmittedat()).isEqualTo(NOW);
        assertThat(persisted.getNextattemptat()).isEqualTo(NOW.plusSeconds(2));
        assertThat(persisted.getLasterror().codePointCount(
                        0, persisted.getLasterror().length()))
                .isEqualTo(128);
    }

    @Test
    void Agent终态与取消投递必须同时收敛命令和非终态任务() {
        Fixture fixture = fixture("dispatch-settle");
        insertCommand(
                fixture, "task-terminal", "command-terminal", "pending", NOW, NOW);
        insertCancel(fixture, "task-cancel", "command-cancel");

        var terminal = repository.settleDispatchTerminal(
                "command-terminal", WritingAgentJobStatus.FAILED);
        var cancelled = repository.settleCancelDispatch("command-cancel");

        assertThat(terminal.status()).isEqualTo("failed");
        assertThat(cancelled.status()).isEqualTo("succeeded");
        assertThat(database.dsl().select(WRITINGTASK.PHASE)
                        .from(WRITINGTASK)
                        .where(WRITINGTASK.ID.eq("task-terminal"))
                        .fetchOne(WRITINGTASK.PHASE))
                .isEqualTo(Writingtaskphase.error);
        assertThat(database.dsl().select(WRITINGTASK.PHASE)
                        .from(WRITINGTASK)
                        .where(WRITINGTASK.ID.eq("task-cancel"))
                        .fetchOne(WRITINGTASK.PHASE))
                .isEqualTo(Writingtaskphase.error);
        String cancelResult = database.dsl().select(WRITINGRUNCOMMAND.RESULTJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq("command-cancel"))
                .fetchOne(WRITINGRUNCOMMAND.RESULTJSON);
        assertThat(json.readTree(cancelResult).path("effective").asBoolean()).isTrue();
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

    private void insertCommand(
            Fixture fixture,
            String taskId,
            String commandId,
            String status,
            LocalDateTime nextAttemptAt,
            LocalDateTime updatedAt) {
        insertTask(fixture, taskId);
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, commandId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, "{\"resume\":false}")
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, fixture.userId() + ":" + commandId)
                .set(WRITINGRUNCOMMAND.STATUS, status)
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, nextAttemptAt)
                .set(WRITINGRUNCOMMAND.CREATEDAT, updatedAt)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, updatedAt)
                .execute();
    }

    private void insertCancel(Fixture fixture, String taskId, String commandId) {
        insertTask(fixture, taskId);
        String payload = json.writeValueAsString(Map.of(
                "_inkforgeCommand",
                Map.of(
                        "schemaVersion", 1,
                        "clientRequestId", "request-cancel-1234",
                        "commandKind", "cancel",
                        "resourceIdentity", Map.of("taskId", taskId),
                        "normalizedBody", Map.of(),
                        "requestFingerprint", "a".repeat(64)),
                "job",
                Map.of(
                        "cancelledCommandId", "source-command",
                        "cancelledJobId", "source-command")));
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, commandId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "resume")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, payload)
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, "v1:" + fixture.userId() + ":cancel")
                .set(WRITINGRUNCOMMAND.STATUS, "pending")
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, NOW)
                .set(WRITINGRUNCOMMAND.CREATEDAT, NOW)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, NOW)
                .execute();
    }

    private void insertTask(Fixture fixture, String taskId) {
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, fixture.novelId())
                .set(WRITINGTASK.CHAPTERID, fixture.chapterId())
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.GRAPHSTATEJSON, json.writeValueAsString(Map.of(
                        "taskId", taskId, "phase", "active")))
                .set(WRITINGTASK.CREATEDAT, NOW)
                .set(WRITINGTASK.UPDATEDAT, NOW)
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
