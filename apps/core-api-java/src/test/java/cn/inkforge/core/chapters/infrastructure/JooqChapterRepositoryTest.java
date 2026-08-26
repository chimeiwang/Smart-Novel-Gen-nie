package cn.inkforge.core.chapters.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.CHAPTERPROGRESS;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ChapterStatus;
import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.enums.Workflowrunstatus;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
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

@Testcontainers
class JooqChapterRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T00:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_chapters_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqChapterRepository repository;
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
        repository = new JooqChapterRepository(
                database, new CuidV1Generator(CLOCK), CLOCK);
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) {
            database.close();
        }
    }

    @Test
    void 读取必须保持归属稳定排序完整正文与批量聚合() {
        String owner = user("chapter-owner-1");
        String stranger = user("chapter-stranger-1");
        String novel = novel("chapter-novel-1", owner);
        String longContent = "😀 甲\n乙\ufeff".repeat(20_000);
        chapter("chapter-2", novel, 2, "第二章", longContent);
        chapter("chapter-1", novel, 1, "第一章", "正文");
        progress("progress-1", "chapter-1", "完整进展");
        quality("quality-1", "chapter-1", Qualitycheckstatus.completed, "报告", 9, "pass");
        beatPlan("plan-1", "chapter-1");
        beat("beat-1", "plan-1");

        var chapters = repository.list(novel, owner);

        assertThat(chapters).extracting(value -> value.getId())
                .containsExactly("chapter-1", "chapter-2");
        assertThat(chapters.get(1).getContent()).isEqualTo(longContent);
        assertThat(chapters.get(1).getWordCount()).isEqualTo(60_000);
        assertThat(chapters.getFirst().getProgress().getContent()).isEqualTo("完整进展");
        assertThat(chapters.getFirst().getQualityChecks()).hasSize(1);
        assertThat(chapters.getFirst().getApprovedBeatPlan().getSceneBeats()).hasSize(1);
        assertCode(() -> repository.list(novel, stranger), 403, "NOVEL_FORBIDDEN");
        assertCode(() -> repository.get("chapter-1", stranger), 403, "CHAPTER_FORBIDDEN");
        assertCode(() -> repository.get("missing", owner), 404, "CHAPTER_NOT_FOUND");
    }

    @Test
    void 创建和正文更新必须串行编号执行CAS并让旧质量任务失效() {
        String owner = user("chapter-owner-2");
        String novel = novel("chapter-novel-2", owner);
        chapter("chapter-existing", novel, 1, "第一章", "旧正文");

        var created = repository.create(novel, owner);
        assertThat(created.getTitle()).isEqualTo("第 2 章");
        assertThat(created.getOrder()).isEqualTo(2);

        quality("quality-2", "chapter-existing", Qualitycheckstatus.completed, "旧报告", 8, "pass");
        workflow("workflow-2", novel, "chapter-existing", owner, "quality-2");
        OffsetDateTime expected = INITIAL.atOffset(ZoneOffset.UTC);
        String fullContent = "  新正文\n".repeat(30_000);

        OffsetDateTime updated = repository.updateDraft(
                "chapter-existing", owner, "新标题", fullContent, expected);

        assertThat(updated).isEqualTo(OffsetDateTime.parse("2026-08-25T00:00:00.123Z"));
        var stored = database.dsl().selectFrom(CHAPTER)
                .where(CHAPTER.ID.eq("chapter-existing"))
                .fetchSingle();
        assertThat(stored.getContent()).isEqualTo(fullContent);
        var check = database.dsl().selectFrom(CHAPTERQUALITYCHECK)
                .where(CHAPTERQUALITYCHECK.ID.eq("quality-2"))
                .fetchSingle();
        assertThat(check.getStatus()).isEqualTo(Qualitycheckstatus.pending);
        assertThat(check.getResult()).isNull();
        assertThat(database.dsl().selectFrom(WORKFLOWRUN)
                        .where(WORKFLOWRUN.ID.eq("workflow-2"))
                        .fetchSingle()
                        .getStatus())
                .isEqualTo(Workflowrunstatus.cancelled);

        assertCode(
                () -> repository.updateDraft(
                        "chapter-existing", owner, "另一个标题", "覆盖", expected),
                409,
                "CHAPTER_VERSION_CONFLICT");
        assertThat(repository.updateDraft(
                        "chapter-existing",
                        owner,
                        "新标题",
                        fullContent,
                        expected))
                .isEqualTo(updated);
        assertThat(database.dsl().select(CHAPTER.CONTENT)
                        .from(CHAPTER)
                        .where(CHAPTER.ID.eq("chapter-existing"))
                        .fetchSingle(CHAPTER.CONTENT))
                .isEqualTo(fullContent);
    }

    @Test
    void 进展和状态机必须保持空版本前置终检门禁与幂等完成时间() {
        String owner = user("chapter-owner-3");
        String novel = novel("chapter-novel-3", owner);
        chapter("chapter-state", novel, 1, "第一章", "正文");

        assertCode(
                () -> repository.upsertProgress(
                        "chapter-state", owner, "首次", INITIAL.atOffset(ZoneOffset.UTC)),
                409,
                "CHAPTER_PROGRESS_VERSION_CONFLICT");
        OffsetDateTime progressAt =
                repository.upsertProgress("chapter-state", owner, "首次", null);
        assertThat(repository.upsertProgress(
                        "chapter-state", owner, "首次", INITIAL.atOffset(ZoneOffset.UTC)))
                .isEqualTo(progressAt);
        assertCode(
                () -> repository.upsertProgress(
                        "chapter-state", owner, "第二次", INITIAL.atOffset(ZoneOffset.UTC)),
                409,
                "CHAPTER_PROGRESS_VERSION_CONFLICT");

        assertCode(
                () -> repository.transitionStatus(
                        "chapter-state", owner, ChapterStatus.COMPLETED,
                        INITIAL.atOffset(ZoneOffset.UTC)),
                409,
                "INVALID_CHAPTER_STATUS_TRANSITION");
        var review = repository.transitionStatus(
                "chapter-state", owner, ChapterStatus.REVIEW,
                INITIAL.atOffset(ZoneOffset.UTC));
        assertThat(review.status()).isEqualTo(ChapterStatus.REVIEW);
        var check = database.dsl().selectFrom(CHAPTERQUALITYCHECK)
                .where(CHAPTERQUALITYCHECK.CHAPTERID.eq("chapter-state"))
                .fetchSingle();
        assertThat(check.getTitle()).isEqualTo(JooqChapterRepository.DEFAULT_QUALITY_TITLE);

        assertCode(
                () -> repository.transitionStatus(
                        "chapter-state", owner, ChapterStatus.COMPLETED, review.updatedAt()),
                409,
                "QUALITY_CHECK_REQUIRED");
        database.dsl().update(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.completed)
                .set(CHAPTERQUALITYCHECK.RESULT, "终检通过")
                .set(CHAPTERQUALITYCHECK.SCOREOVERALL, 9)
                .set(CHAPTERQUALITYCHECK.QUALITYGATE, "pass")
                .where(CHAPTERQUALITYCHECK.ID.eq(check.getId()))
                .execute();
        var completed = repository.transitionStatus(
                "chapter-state", owner, ChapterStatus.COMPLETED, review.updatedAt());
        var replay = repository.transitionStatus(
                "chapter-state", owner, ChapterStatus.COMPLETED, completed.updatedAt());
        assertThat(replay.completedAt()).isEqualTo(completed.completedAt());
        assertThat(replay.updatedAt()).isEqualTo(completed.updatedAt());
    }

    private String user(String id) {
        users.add(id);
        database.dsl().insertInto(USER)
                .set(USER.ID, id)
                .set(USER.USERNAME, id)
                .set(USER.PASSWORDHASH, "test-hash")
                .set(USER.CREDITBALANCEMICROS, 0L)
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private String novel(String id, String userId) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, id)
                .set(NOVEL.NAME, id)
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private void chapter(
            String id, String novelId, int order, String title, String content) {
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, id)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, title)
                .set(CHAPTER.CONTENT, content)
                .set(CHAPTER.ORDER, order)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
    }

    private void progress(String id, String chapterId, String content) {
        database.dsl().insertInto(CHAPTERPROGRESS)
                .set(CHAPTERPROGRESS.ID, id)
                .set(CHAPTERPROGRESS.CHAPTERID, chapterId)
                .set(CHAPTERPROGRESS.CONTENT, content)
                .set(CHAPTERPROGRESS.CREATEDAT, INITIAL)
                .set(CHAPTERPROGRESS.UPDATEDAT, INITIAL)
                .execute();
    }

    private void quality(
            String id,
            String chapterId,
            Qualitycheckstatus status,
            String result,
            Integer score,
            String gate) {
        database.dsl().insertInto(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.ID, id)
                .set(CHAPTERQUALITYCHECK.CHAPTERID, chapterId)
                .set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                .set(CHAPTERQUALITYCHECK.STATUS, status)
                .set(CHAPTERQUALITYCHECK.TITLE, "旧终检")
                .set(CHAPTERQUALITYCHECK.SUMMARY, "旧摘要")
                .set(CHAPTERQUALITYCHECK.RESULT, result)
                .set(CHAPTERQUALITYCHECK.SCOREOVERALL, score)
                .set(CHAPTERQUALITYCHECK.QUALITYGATE, gate)
                .set(CHAPTERQUALITYCHECK.CREATEDAT, INITIAL)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, INITIAL)
                .execute();
    }

    private void beatPlan(String id, String chapterId) {
        database.dsl().insertInto(CHAPTERBEATPLAN)
                .set(CHAPTERBEATPLAN.ID, id)
                .set(CHAPTERBEATPLAN.CHAPTERID, chapterId)
                .set(CHAPTERBEATPLAN.STATUS, Beatplanstatus.approved)
                .set(CHAPTERBEATPLAN.CHAPTERGOAL, "推进冲突")
                .set(CHAPTERBEATPLAN.TOTALESTIMATEDWORDS, 800)
                .set(CHAPTERBEATPLAN.CREATEDAT, INITIAL)
                .set(CHAPTERBEATPLAN.UPDATEDAT, INITIAL)
                .execute();
    }

    private void beat(String id, String planId) {
        database.dsl().insertInto(SCENEBEAT)
                .set(SCENEBEAT.ID, id)
                .set(SCENEBEAT.BEATPLANID, planId)
                .set(SCENEBEAT.ORDER, 1)
                .set(SCENEBEAT.GOAL, "进入现场")
                .set(SCENEBEAT.CHARACTERS, "主角")
                .set(SCENEBEAT.ESTIMATEDWORDS, 800)
                .set(SCENEBEAT.ACCEPTANCECRITERIA, "产生新冲突")
                .execute();
    }

    private void workflow(
            String id, String novelId, String chapterId, String userId, String checkId) {
        database.dsl().insertInto(WORKFLOWRUN)
                .set(WORKFLOWRUN.ID, id)
                .set(WORKFLOWRUN.NOVELID, novelId)
                .set(WORKFLOWRUN.CHAPTERID, chapterId)
                .set(WORKFLOWRUN.USERID, userId)
                .set(WORKFLOWRUN.KIND, Workflowrunkind.quality_check)
                .set(WORKFLOWRUN.STATUS, Workflowrunstatus.running)
                .set(WORKFLOWRUN.SOURCEID, checkId)
                .set(WORKFLOWRUN.CREATEDAT, INITIAL)
                .set(WORKFLOWRUN.UPDATEDAT, INITIAL)
                .execute();
    }

    private static void assertCode(
            Runnable action, int status, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(status);
                    assertThat(error.code()).isEqualTo(code);
                });
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
    }
}
