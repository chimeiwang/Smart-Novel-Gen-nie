package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGEVENTOUTBOX;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.writing.domain.WritingEvent;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
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
class JooqWritingOutboxRepositoryTest {

    private static final LocalDateTime NOW =
            LocalDateTime.parse("2026-08-25T11:00:00.000");
    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T11:00:00Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_outbox_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static JooqWritingOutboxRepository repository;
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
        repository = new JooqWritingOutboxRepository(
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
    void 同一任务后续事件必须等待前序发布且SSE可见性跟随投递状态() {
        Fixture fixture = fixture("outbox-order");
        insertOutbox(fixture, "outbox-1", 1, "completed", NOW.minusSeconds(2));
        insertOutbox(fixture, "outbox-2", 2, "error", NOW.minusSeconds(1));

        var firstBatch = repository.claimDue(NOW, 20, 30);

        assertThat(firstBatch).extracting(record -> record.id()).containsExactly("outbox-1");
        assertThat(repository.markPublished(
                        "outbox-1", firstBatch.getFirst().leaseToken(), "redis-1"))
                .isTrue();
        var secondBatch = repository.claimDue(NOW, 20, 30);
        assertThat(secondBatch).extracting(record -> record.id()).containsExactly("outbox-2");

        List<WritingEvent> events = List.of(
                event("redis-1", "event-1", 1, "completed"),
                event("redis-2", "event-2", 2, "error"),
                event("redis-3", null, 3, "agent_status"));
        assertThat(repository.replayDispositions(events))
                .containsEntry("redis-1", "emit")
                .containsEntry("redis-2", "wait")
                .containsEntry("redis-3", "emit");
    }

    @Test
    void 过期等待通知在任务终态后必须释放租约并标记superseded() {
        Fixture fixture = fixture("outbox-stale");
        insertOutbox(
                fixture,
                "outbox-waiting",
                1,
                "artifact_awaiting_user_approval",
                NOW);
        var claimed = repository.claimDue(NOW, 20, 30).getFirst();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.completed)
                .where(WRITINGTASK.ID.eq(fixture.taskId()))
                .execute();

        assertThat(repository.supersedeWaitingIfStale(
                        claimed.id(), claimed.leaseToken(), NOW))
                .isTrue();
        var row = database.dsl().selectFrom(WRITINGEVENTOUTBOX)
                .where(WRITINGEVENTOUTBOX.ID.eq(claimed.id()))
                .fetchOne();
        assertThat(row.getDeliverystate()).isEqualTo("superseded");
        assertThat(row.getLeasetoken()).isNull();
        assertThat(row.getLasterrorcode()).isEqualTo("OUTBOX_WAITING_SUPERSEDED");
    }

    @Test
    void 失败租约可退避重领阻塞状态进入readiness且旧终态可清理() {
        Fixture fixture = fixture("outbox-health");
        insertOutbox(fixture, "outbox-retry", 1, "completed", NOW);
        var first = repository.claimDue(NOW, 20, 30).getFirst();
        assertThat(repository.scheduleRetry(
                        first.id(), first.leaseToken(), NOW.plusSeconds(5), "REDIS_DOWN"))
                .isTrue();
        assertThat(repository.claimDue(NOW.plusSeconds(4), 20, 30)).isEmpty();
        var retried = repository.claimDue(NOW.plusSeconds(5), 20, 30).getFirst();
        assertThat(retried.attemptCount()).isEqualTo(2);
        assertThat(repository.markBlocked(
                        retried.id(), retried.leaseToken(), "OUTBOX_EVENT_SEQUENCE_GAP"))
                .isTrue();

        var health = repository.health(NOW.plusMinutes(10), Duration.ofMinutes(5));
        assertThat(health.blockedCount()).isEqualTo(1);

        database.dsl().update(WRITINGEVENTOUTBOX)
                .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "published")
                .set(WRITINGEVENTOUTBOX.REDISEVENTID, "redis-old")
                .set(WRITINGEVENTOUTBOX.PUBLISHEDAT, NOW.minusDays(8))
                .setNull(WRITINGEVENTOUTBOX.LASTERRORCODE)
                .setNull(WRITINGEVENTOUTBOX.LEASETOKEN)
                .setNull(WRITINGEVENTOUTBOX.LEASEEXPIRESAT)
                .where(WRITINGEVENTOUTBOX.ID.eq("outbox-retry"))
                .execute();
        assertThat(repository.cleanupTerminal(NOW.minusDays(7))).isEqualTo(1);
    }

    private Fixture fixture(String prefix) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        String taskId = prefix + "-task";
        String commandId = prefix + "-command";
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
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, novelId)
                .set(WRITINGTASK.CHAPTERID, chapterId)
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "写作")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.CREATEDAT, NOW)
                .set(WRITINGTASK.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, commandId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, "{\"resume\":false}")
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, userId + ":command")
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, NOW)
                .set(WRITINGRUNCOMMAND.COMPLETEDAT, NOW)
                .set(WRITINGRUNCOMMAND.CREATEDAT, NOW)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, NOW)
                .execute();
        return new Fixture(userId, taskId, commandId);
    }

    private void insertOutbox(
            Fixture fixture,
            String id,
            int sequence,
            String type,
            LocalDateTime createdAt) {
        database.dsl().insertInto(WRITINGEVENTOUTBOX)
                .set(WRITINGEVENTOUTBOX.ID, id)
                .set(WRITINGEVENTOUTBOX.TASKID, fixture.taskId())
                .set(WRITINGEVENTOUTBOX.COMMANDID, fixture.commandId())
                .set(WRITINGEVENTOUTBOX.SOURCEEVENTID, "event-" + sequence)
                .set(WRITINGEVENTOUTBOX.SOURCESEQUENCE, sequence)
                .set(WRITINGEVENTOUTBOX.DURABLEBASELINE, sequence - 1)
                .set(WRITINGEVENTOUTBOX.DEDUPEKEY, "dedupe-" + sequence)
                .set(WRITINGEVENTOUTBOX.EVENTTYPE, type)
                .set(WRITINGEVENTOUTBOX.PAYLOADJSON, json.writeValueAsString(Map.of(
                        "taskId", fixture.taskId())))
                .set(WRITINGEVENTOUTBOX.DELIVERYSTATE, "pending")
                .set(WRITINGEVENTOUTBOX.ATTEMPTCOUNT, 0)
                .set(WRITINGEVENTOUTBOX.NEXTATTEMPTAT, createdAt)
                .set(WRITINGEVENTOUTBOX.CREATEDAT, createdAt)
                .set(WRITINGEVENTOUTBOX.UPDATEDAT, createdAt)
                .execute();
    }

    private static WritingEvent event(
            String id, String sourceId, int sequence, String event) {
        return new WritingEvent(
                id,
                event,
                Map.of(),
                OffsetDateTime.now(CLOCK),
                sourceId,
                sequence);
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

    private record Fixture(String userId, String taskId, String commandId) {}
}
