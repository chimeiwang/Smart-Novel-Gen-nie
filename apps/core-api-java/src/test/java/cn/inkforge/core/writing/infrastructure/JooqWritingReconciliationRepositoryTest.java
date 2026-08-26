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
import cn.inkforge.core.platform.id.CuidV1Generator;
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
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqWritingReconciliationRepositoryTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-08-25T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T10:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_reconcile_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static JooqWritingReconciliationRepository repository;
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
        repository = new JooqWritingReconciliationRepository(database, CLOCK, json);
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 只领取无活动命令的Active与WaitingCall旧任务() {
        Fixture fixture = fixture("reconcile-list");
        insertTask(fixture, "task-active", Writingtaskphase.active, "{}", NOW);
        insertTask(fixture, "task-wait", Writingtaskphase.waiting_call, "{}", NOW.plusSeconds(1));
        insertTask(fixture, "task-review", Writingtaskphase.awaiting_user_review, "{}", NOW);
        insertTask(fixture, "task-command", Writingtaskphase.active, "{}", NOW);
        insertCommand("task-command", "command-active", "pending");

        var tasks = repository.listReconcilable(10);

        assertThat(tasks).extracting(task -> task.id())
                .containsExactly("task-active", "task-wait");
    }

    @Test
    void 对账命令按快照生成稳定身份且同一任务只创建一次() {
        Fixture fixture = fixture("reconcile-create");
        String graph = "{\"eventSequence\":20,\"callbackJobId\":\"writing-old\"}";
        insertTask(fixture, "task-1", Writingtaskphase.active, graph, NOW);
        var expected = repository.listReconcilable(10).getFirst();

        boolean created = repository.createCommand(expected);
        boolean duplicate = repository.createCommand(expected);
        var command = database.dsl().selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.TASKID.eq("task-1"))
                .fetchOne();

        assertThat(created).isTrue();
        assertThat(duplicate).isFalse();
        assertThat(command.getId()).startsWith("writing-").hasSize(40);
        assertThat(command.getKind()).isEqualTo("resume");
        assertThat(command.getStatus()).isEqualTo("pending");
        assertThat(command.getIdempotencykey()).isEqualTo("reconcile:" + command.getId());
        assertThat(json.readTree(command.getPayloadjson()))
                .isEqualTo(json.readTree("""
                        {
                          "chapterId":"reconcile-create-chapter",
                          "force":true,
                          "resume":true,
                          "resumeInput":null,
                          "version":1,
                          "writingSessionId":null
                        }
                        """));
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
            Fixture fixture,
            String taskId,
            Writingtaskphase phase,
            String graph,
            LocalDateTime updatedAt) {
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, fixture.novelId())
                .set(WRITINGTASK.CHAPTERID, fixture.chapterId())
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "写作,编辑")
                .set(WRITINGTASK.PHASE, phase)
                .set(WRITINGTASK.GRAPHSTATEJSON, graph)
                .set(WRITINGTASK.CREATEDAT, NOW)
                .set(WRITINGTASK.UPDATEDAT, updatedAt)
                .execute();
    }

    private void insertCommand(String taskId, String commandId, String status) {
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, commandId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "resume")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, "{}")
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, "test:" + commandId)
                .set(WRITINGRUNCOMMAND.STATUS, status)
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, NOW)
                .set(WRITINGRUNCOMMAND.CREATEDAT, NOW)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, NOW)
                .execute();
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@" + POSTGRES.getHost() + ":" + POSTGRES.getFirstMappedPort()
                + "/" + POSTGRES.getDatabaseName();
    }

    private record Fixture(String userId, String novelId, String chapterId) {}
}
