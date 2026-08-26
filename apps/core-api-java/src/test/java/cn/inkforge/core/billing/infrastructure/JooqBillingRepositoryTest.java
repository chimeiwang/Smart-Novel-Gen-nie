package cn.inkforge.core.billing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.STYLEPORTRAITTASK;
import static cn.inkforge.core.db.generated.Tables.TOKENUSAGE;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.billing.application.ChargeUsage;
import cn.inkforge.core.billing.application.InsufficientCreditsException;
import cn.inkforge.core.billing.application.UsageConflictException;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Stylesourcetype;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

@Testcontainers
class JooqBillingRepositoryTest {

    private static final LocalDateTime INITIAL = LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T06:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_billing_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqBillingRepository repository;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void 重建冻结结构() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        repository = new JooqBillingRepository(
                database, new CuidV1Generator(CLOCK), CLOCK);
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
    void 授权上下文必须校验写作质量与文风任务的真实归属() {
        String owner = user("billing-owner-1", 1_000_000L);
        String stranger = user("billing-stranger-1", 2_000_000L);
        Project project = project("billing-novel-1", owner);
        writingTask("billing-task-1", project);
        qualityCheck("billing-quality-1", project.chapterId());
        styleTask("billing-style-1", "billing-style-task-1", owner);

        assertThat(repository.authorizationContext(owner, "billing-task-1", project.novelId()))
                .extracting(value -> value.balanceMicros(), value -> value.resourceKind())
                .containsExactly(1_000_000L, "default");
        assertThat(repository.authorizationContext(owner, "billing-quality-1", project.novelId()))
                .isNotNull();
        assertThat(repository.authorizationContext(
                        owner, "billing-style-task-1", "style:billing-style-1"))
                .isNotNull();
        assertThat(repository.authorizationContext(
                        stranger, "billing-style-task-1", "style:billing-style-1"))
                .isNull();
        assertThat(repository.authorizationContext(
                        stranger, "billing-task-1", project.novelId()))
                .isNull();
    }

    @Test
    void 正金额结算必须原子扣款双写并对完整身份安全重放() {
        String owner = user("billing-owner-2", 1_000_000L);
        Project project = project("billing-novel-2", owner);
        writingTask("billing-task-2", project);
        ChargeUsage usage = usage(
                "billing-request-2", owner, project.novelId(), "billing-task-2", 100, 20, 25, 125, 80, 5);

        var first = repository.charge(usage);
        var replay = repository.charge(usage);

        assertThat(first.chargedMicros()).isEqualTo(130_400L);
        assertThat(first.balanceAfterMicros()).isEqualTo(869_600L);
        assertThat(first.idempotent()).isFalse();
        assertThat(replay.idempotent()).isTrue();
        assertThat(database.dsl().select(USER.CREDITBALANCEMICROS)
                        .from(USER)
                        .where(USER.ID.eq(owner))
                        .fetchSingle(USER.CREDITBALANCEMICROS))
                .isEqualTo(869_600L);
        assertThat(database.dsl().fetchCount(
                        TOKENUSAGE, TOKENUSAGE.REQUESTID.eq("billing-request-2")))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        CREDITLEDGER, CREDITLEDGER.REQUESTID.eq("billing-request-2")))
                .isEqualTo(1);
        assertThatThrownBy(() -> repository.charge(usage(
                        "billing-request-2",
                        owner,
                        project.novelId(),
                        "billing-task-2",
                        100,
                        20,
                        25,
                        125,
                        null,
                        5)))
                .isInstanceOf(UsageConflictException.class);
    }

    @Test
    void 并发重试必须由事务级请求锁收敛为一次扣款() throws Exception {
        String owner = user("billing-owner-concurrent", 1_000_000L);
        Project project = project("billing-novel-concurrent", owner);
        writingTask("billing-task-concurrent", project);
        ChargeUsage usage = usage(
                "billing-request-concurrent",
                owner,
                project.novelId(),
                "billing-task-concurrent",
                100,
                20,
                25,
                125,
                80,
                5);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        var executor = Executors.newFixedThreadPool(2);
        try {
            var first = executor.submit(() -> {
                ready.countDown();
                start.await();
                return repository.charge(usage);
            });
            var second = executor.submit(() -> {
                ready.countDown();
                start.await();
                return repository.charge(usage);
            });
            ready.await();
            start.countDown();

            assertThat(List.of(first.get(), second.get()))
                    .extracting(value -> value.idempotent())
                    .containsExactlyInAnyOrder(false, true);
        } finally {
            executor.shutdownNow();
        }
        assertThat(database.dsl().select(USER.CREDITBALANCEMICROS)
                        .from(USER)
                        .where(USER.ID.eq(owner))
                        .fetchSingle(USER.CREDITBALANCEMICROS))
                .isEqualTo(869_600L);
        assertThat(database.dsl().fetchCount(
                        TOKENUSAGE, TOKENUSAGE.REQUESTID.eq("billing-request-concurrent")))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        CREDITLEDGER, CREDITLEDGER.REQUESTID.eq("billing-request-concurrent")))
                .isEqualTo(1);
    }

    @Test
    void 零金额仍写用量而历史单流水只重放不回填() {
        String owner = user("billing-owner-3", 500_000L);
        Project project = project("billing-novel-3", owner);
        writingTask("billing-task-3", project);
        ChargeUsage zero = usage(
                "billing-zero-3", owner, project.novelId(), "billing-task-3", 0, 0, 0, 0, 0, 0);

        var first = repository.charge(zero);
        database.dsl().update(USER)
                .set(USER.CREDITBALANCEMICROS, 600_000L)
                .where(USER.ID.eq(owner))
                .execute();
        var replay = repository.charge(zero);
        assertThat(first.chargedMicros()).isZero();
        assertThat(replay.balanceAfterMicros()).isEqualTo(600_000L);
        assertThat(database.dsl().fetchCount(
                        TOKENUSAGE, TOKENUSAGE.REQUESTID.eq("billing-zero-3")))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        CREDITLEDGER, CREDITLEDGER.REQUESTID.eq("billing-zero-3")))
                .isZero();

        legacyLedger(
                "billing-legacy-3", owner, project.novelId(), 10, 0, 5, 15, -20_000L, 580_000L);
        ChargeUsage legacy = usage(
                "billing-legacy-3", owner, project.novelId(), "billing-task-3", 10, 0, 5, 15, null, null);
        var legacyReplay = repository.charge(legacy);
        assertThat(legacyReplay.idempotent()).isTrue();
        assertThat(legacyReplay.balanceAfterMicros()).isEqualTo(580_000L);
        assertThat(database.dsl().fetchCount(
                        TOKENUSAGE, TOKENUSAGE.REQUESTID.eq("billing-legacy-3")))
                .isZero();
    }

    @Test
    void 摘要总月用量与任务明细必须稳定排序且越权隐藏() {
        String owner = user("billing-owner-4", 900_000L);
        String stranger = user("billing-stranger-4", 1L);
        Project project = project("billing-novel-4", owner);
        writingTask("billing-task-4", project);
        repository.charge(usage(
                "billing-call-a", owner, project.novelId(), "billing-task-4", 10, 2, 5, 15, 8, 1));
        database.dsl().update(USER)
                .set(USER.CREDITBALANCEMICROS, 900_000L)
                .where(USER.ID.eq(owner))
                .execute();
        repository.charge(usage(
                "billing-call-b", owner, project.novelId(), "billing-task-4", 20, 4, 6, 26, 16, 2));

        var summary = repository.summary(owner);
        var usage = repository.usage(
                owner, OffsetDateTime.parse("2026-08-01T00:00:00Z"));
        var calls = repository.taskUsage(owner, "billing-task-4");

        assertThat(summary.username()).isEqualTo(owner);
        assertThat(summary.entries()).hasSize(2);
        assertThat(usage.total().promptTokens()).isEqualTo(30);
        assertThat(usage.monthly()).isEqualTo(usage.total());
        assertThat(calls).extracting(value -> value.requestId())
                .containsExactly("billing-call-a", "billing-call-b");
        assertThat(calls.getFirst().promptCacheMissTokens()).isEqualTo(8);
        assertThat(repository.taskUsage(stranger, "billing-task-4")).isNull();
        assertThatThrownBy(() -> repository.charge(usage(
                        "billing-insufficient",
                        stranger,
                        project.novelId(),
                        "billing-task-4",
                        1,
                        0,
                        1,
                        2,
                        1,
                        0)))
                .isInstanceOf(InsufficientCreditsException.class);
    }

    private String user(String id, long balance) {
        users.add(id);
        database.dsl().insertInto(USER)
                .set(USER.ID, id)
                .set(USER.USERNAME, id)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREDITBALANCEMICROS, balance)
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private static Project project(String novelId, String owner) {
        String chapterId = novelId + "-chapter";
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, novelId)
                .set(NOVEL.USERID, owner)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, "正文")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
        return new Project(novelId, chapterId);
    }

    private static void writingTask(String id, Project project) {
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, id)
                .set(WRITINGTASK.NOVELID, project.novelId())
                .set(WRITINGTASK.CHAPTERID, project.chapterId())
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "[]")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.CREATEDAT, INITIAL)
                .set(WRITINGTASK.UPDATEDAT, INITIAL)
                .execute();
    }

    private static void qualityCheck(String id, String chapterId) {
        database.dsl().insertInto(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.ID, id)
                .set(CHAPTERQUALITYCHECK.CHAPTERID, chapterId)
                .set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.running)
                .set(CHAPTERQUALITYCHECK.TITLE, "一致性终检")
                .set(CHAPTERQUALITYCHECK.CREATEDAT, INITIAL)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, INITIAL)
                .execute();
    }

    private static void styleTask(String styleId, String taskId, String userId) {
        database.dsl().insertInto(WRITINGSTYLE)
                .set(WRITINGSTYLE.ID, styleId)
                .set(WRITINGSTYLE.USERID, userId)
                .set(WRITINGSTYLE.NAME, styleId)
                .set(WRITINGSTYLE.SOURCETYPE, Stylesourcetype.agent)
                .set(WRITINGSTYLE.CREATEDAT, INITIAL)
                .set(WRITINGSTYLE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(STYLEPORTRAITTASK)
                .set(STYLEPORTRAITTASK.ID, taskId)
                .set(STYLEPORTRAITTASK.STYLEID, styleId)
                .set(STYLEPORTRAITTASK.STATUS, "pending")
                .set(STYLEPORTRAITTASK.CREATEDAT, INITIAL)
                .set(STYLEPORTRAITTASK.UPDATEDAT, INITIAL)
                .execute();
    }

    private static ChargeUsage usage(
            String requestId,
            String userId,
            String novelId,
            String taskId,
            int prompt,
            int cached,
            int completion,
            int total,
            Integer cacheMiss,
            Integer reasoning) {
        return new ChargeUsage(
                requestId,
                userId,
                novelId,
                taskId,
                "run-1",
                "deepseek-v4-flash",
                "写作",
                prompt,
                cached,
                completion,
                total,
                cacheMiss,
                reasoning);
    }

    private static void legacyLedger(
            String requestId,
            String userId,
            String novelId,
            int prompt,
            int cached,
            int completion,
            int total,
            long amount,
            long balance) {
        database.dsl().insertInto(CREDITLEDGER)
                .set(CREDITLEDGER.ID, requestId + "-ledger")
                .set(CREDITLEDGER.USERID, userId)
                .set(CREDITLEDGER.TYPE, "ai_charge")
                .set(CREDITLEDGER.AMOUNTMICROS, amount)
                .set(CREDITLEDGER.BALANCEAFTERMICROS, balance)
                .set(CREDITLEDGER.MODEL, "deepseek-v4-flash")
                .set(CREDITLEDGER.PROMPTTOKENS, prompt)
                .set(CREDITLEDGER.CACHEDTOKENS, cached)
                .set(CREDITLEDGER.COMPLETIONTOKENS, completion)
                .set(CREDITLEDGER.TOTALTOKENS, total)
                .set(CREDITLEDGER.AGENTID, "写作")
                .set(CREDITLEDGER.NOVELID, novelId)
                .set(CREDITLEDGER.REQUESTID, requestId)
                .set(CREDITLEDGER.CREATEDAT, INITIAL)
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

    private record Project(String novelId, String chapterId) {}
}
