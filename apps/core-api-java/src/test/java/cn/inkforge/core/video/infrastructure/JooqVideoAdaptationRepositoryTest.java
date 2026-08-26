package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOCINEMATICSCENE;
import static cn.inkforge.core.db.generated.Tables.VIDEODRAMATICBEAT;
import static cn.inkforge.core.db.generated.Tables.VIDEODRAMATICBEATSOURCEANCHOR;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTSOURCEANCHOR;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.CreateChapterAdaptationRequest;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HexFormat;
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
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqVideoAdaptationRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T05:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_adaptation_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqVideoAdaptationRepository repository;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void restoreSchema() throws Exception {
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
        var json = JsonMapper.builder().findAndAddModules().build();
        var ids = new CuidV1Generator(CLOCK);
        var visualCanons = new JooqVideoVisualCanonRepository(database, ids, CLOCK, json);
        repository = new JooqVideoAdaptationRepository(
                database, ids, CLOCK, json, visualCanons);
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            List<String> adaptationIds = database.dsl()
                    .select(VIDEOCHAPTERADAPTATION.ID)
                    .from(VIDEOCHAPTERADAPTATION)
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(VIDEOCHAPTERADAPTATION.NOVELID))
                    .where(NOVEL.USERID.in(users))
                    .fetch(VIDEOCHAPTERADAPTATION.ID);
            if (!adaptationIds.isEmpty()) {
                // 正式方案同时被 Head 指向、又反向绑定 Artifact；测试清理必须先断开 Head。
                database.dsl().update(VIDEOCHAPTERADAPTATIONHEAD)
                        .set(VIDEOCHAPTERADAPTATIONHEAD.CURRENTSHOTPLANVERSIONID, (String) null)
                        .set(VIDEOCHAPTERADAPTATIONHEAD.CURRENTEPISODEPLANVERSIONID, (String) null)
                        .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.in(adaptationIds))
                        .execute();
                database.dsl().deleteFrom(VIDEOSHOTPLANVERSION)
                        .where(VIDEOSHOTPLANVERSION.ADAPTATIONID.in(adaptationIds))
                        .execute();
            }
            database.dsl().deleteFrom(NOVEL).where(NOVEL.USERID.in(users)).execute();
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 必须冻结完整章节并按项目章节来源哈希幂等复用活动改编() throws Exception {
        String owner = user("adaptation-owner-1");
        fixture(owner, "adaptation-novel-1", "project-1", "chapter-1", "甲😀\n\n乙");
        var request = request("chapter-1", "request-adapt-0001", INITIAL);

        var created = repository.create(owner, "project-1", request);
        var replay = repository.create(
                owner,
                "project-1",
                request("chapter-1", "another-request-01", INITIAL));

        assertThat(replay.id()).isEqualTo(created.id());
        assertThat(created.sourceText()).isEqualTo("甲😀\n\n乙");
        assertThat(created.sourceHash()).isEqualTo(HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest("甲😀\n\n乙".getBytes(StandardCharsets.UTF_8))));
        assertThat(created.headRevision()).isOne();
        assertThat(database.dsl().fetchCount(VIDEOCHAPTERADAPTATION)).isOne();
        assertThat(repository.list(owner, "project-1"))
                .extracting(value -> value.id())
                .containsExactly(created.id());
    }

    @Test
    void 完整读模型必须从关系事实重建Unicode来源范围并兼容旧正式方案() {
        String owner = user("adaptation-owner-read-model");
        fixture(
                owner,
                "adaptation-novel-read-model",
                "project-read-model",
                "chapter-read-model",
                "甲😀\n\n乙");
        var created = repository.create(
                owner,
                "project-read-model",
                request("chapter-read-model", "request-read-model", INITIAL));
        formalShotPlan(
                owner,
                "adaptation-novel-read-model",
                "project-read-model",
                created.id());

        var response = repository.getDetail(owner, created.id());

        assertThat(response.getState().getValue()).isEqualTo("approved");
        assertThat(response.getCurrentPlan().getSchemaVersion())
                .isEqualTo("chapter_adaptation_plan_v3");
        var beat = response.getCurrentPlan().getScenes().getFirst().getBeats().getFirst();
        var shot = beat.getShots().getFirst();
        assertThat(beat.getCoverageGoals()).singleElement().satisfies(goal -> {
            assertThat(goal.getGoalKey()).isEqualTo("G01");
            assertThat(goal.getDescription()).isEqualTo("冲突升级");
        });
        assertThat(beat.getSourceRanges()).singleElement().satisfies(range -> {
            assertThat(range.getStart()).isZero();
            assertThat(range.getEnd()).isEqualTo(2);
            assertThat(range.getSourceText()).isEqualTo("甲😀");
        });
        assertThat(shot.getSourceRanges()).singleElement().satisfies(range -> {
            assertThat(range.getStart()).isOne();
            assertThat(range.getEnd()).isEqualTo(2);
            assertThat(range.getSourceText()).isEqualTo("😀");
        });
        assertThat(shot.getSourceRelation().getValue()).isEqualTo("direct");
        assertThat(shot.getSpeechMode().getValue()).isEqualTo("none");
        assertThat(response.getVisualReferenceSets()).singleElement().satisfies(referenceSet -> {
            assertThat(referenceSet.getShotId()).isEqualTo(shot.getId());
            assertThat(referenceSet.getRevision()).isZero();
            assertThat(referenceSet.getReferences()).isEmpty();
        });
        assertThat(repository.listDetails(owner, "project-read-model").getAdaptations())
                .extracting(value -> value.getId())
                .containsExactly(created.id());

        database.dsl().update(VIDEOSHOTSOURCEANCHOR)
                .set(VIDEOSHOTSOURCEANCHOR.ENDCODEPOINT, 99)
                .where(VIDEOSHOTSOURCEANCHOR.SHOTID.eq(shot.getId()))
                .execute();
        assertCode(
                () -> repository.getDetail(owner, created.id()),
                "VIDEO_ADAPTATION_PLAN_INVALID");
    }

    @Test
    void 章节版本归属空正文和超长Unicode正文必须在写入前拒绝() {
        String owner = user("adaptation-owner-2");
        fixture(owner, "adaptation-novel-2", "project-2", "chapter-2", "正文");

        assertCode(
                () -> repository.create(
                        owner,
                        "project-2",
                        request("chapter-2", "request-adapt-0002", INITIAL.plusSeconds(1))),
                "VIDEO_ADAPTATION_SOURCE_CHANGED");
        assertCode(
                () -> repository.create(
                        owner,
                        "project-2",
                        request("missing", "request-adapt-0003", INITIAL)),
                "VIDEO_ADAPTATION_CHAPTER_NOT_FOUND");

        database.dsl().update(CHAPTER)
                .set(CHAPTER.CONTENT, "  \n\t")
                .where(CHAPTER.ID.eq("chapter-2"))
                .execute();
        assertCode(
                () -> repository.create(
                        owner,
                        "project-2",
                        request("chapter-2", "request-adapt-0004", INITIAL)),
                "VIDEO_ADAPTATION_SOURCE_EMPTY");

        database.dsl().update(CHAPTER)
                .set(CHAPTER.CONTENT, "😀".repeat(120_001))
                .where(CHAPTER.ID.eq("chapter-2"))
                .execute();
        assertCode(
                () -> repository.create(
                        owner,
                        "project-2",
                        request("chapter-2", "request-adapt-0005", INITIAL)),
                "VIDEO_ADAPTATION_SOURCE_TOO_LONG");
        assertThat(database.dsl().fetchCount(VIDEOCHAPTERADAPTATION)).isZero();
    }

    @Test
    void 改编读取和列表必须隐藏跨用户资源并明确报告缺失Head() {
        String owner = user("adaptation-owner-3");
        String stranger = user("adaptation-stranger-3");
        fixture(owner, "adaptation-novel-3", "project-3", "chapter-3", "正文");
        var created = repository.create(
                owner,
                "project-3",
                request("chapter-3", "request-adapt-0006", INITIAL));

        assertCode(
                () -> repository.get(stranger, created.id()),
                "VIDEO_ADAPTATION_NOT_FOUND");
        assertCode(
                () -> repository.list(stranger, "project-3"),
                "VIDEO_PROJECT_NOT_FOUND");

        database.dsl().deleteFrom(VIDEOCHAPTERADAPTATIONHEAD)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(created.id()))
                .execute();
        assertCode(
                () -> repository.get(owner, created.id()),
                "VIDEO_ADAPTATION_HEAD_MISSING");
    }

    @Test
    void 非长篇项目不得创建章节改编() {
        String owner = user("adaptation-owner-4");
        fixture(
                owner,
                "adaptation-novel-4",
                "project-4",
                "chapter-4",
                "正文",
                Storylengthprofile.short_medium);
        assertCode(
                () -> repository.create(
                        owner,
                        "project-4",
                        request("chapter-4", "request-adapt-0007", INITIAL)),
                "VIDEO_LONG_SERIAL_REQUIRED");
    }

    private String user(String id) {
        users.add(id);
        database.dsl().insertInto(USER)
                .set(USER.ID, id)
                .set(USER.USERNAME, id)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private static void fixture(
            String owner,
            String novelId,
            String projectId,
            String chapterId,
            String content) {
        fixture(
                owner,
                novelId,
                projectId,
                chapterId,
                content,
                Storylengthprofile.long_serial);
    }

    private static void formalShotPlan(
            String owner,
            String novelId,
            String projectId,
            String adaptationId) {
        String taskId = adaptationId + "-task";
        String artifactId = adaptationId + "-artifact";
        String planId = adaptationId + "-plan";
        String sceneId = adaptationId + "-scene";
        String beatId = adaptationId + "-beat";
        String shotId = adaptationId + "-shot";
        database.dsl().insertInto(VIDEOADAPTATIONTASK)
                .set(VIDEOADAPTATIONTASK.ID, taskId)
                .set(VIDEOADAPTATIONTASK.ADAPTATIONID, adaptationId)
                .set(VIDEOADAPTATIONTASK.PROJECTID, projectId)
                .set(VIDEOADAPTATIONTASK.NOVELID, novelId)
                .set(VIDEOADAPTATIONTASK.JOBID, taskId + "-job")
                .set(VIDEOADAPTATIONTASK.KIND, "shot_plan")
                .set(VIDEOADAPTATIONTASK.WORKFLOW, "chapter_cinematic_adaptation_v2")
                .set(VIDEOADAPTATIONTASK.PROVIDER, "deepseek")
                .set(VIDEOADAPTATIONTASK.STATUS, "completed")
                .set(VIDEOADAPTATIONTASK.IDEMPOTENCYKEY, taskId + "-idempotency")
                .set(VIDEOADAPTATIONTASK.REQUESTJSON, "{}")
                .set(VIDEOADAPTATIONTASK.CHECKPOINTSTAGE, "none")
                .set(VIDEOADAPTATIONTASK.ATTEMPTCOUNT, 0)
                .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, INITIAL)
                .set(VIDEOADAPTATIONTASK.CREATEDAT, INITIAL)
                .set(VIDEOADAPTATIONTASK.UPDATEDAT, INITIAL)
                .set(VIDEOADAPTATIONTASK.COMPLETEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, artifactId)
                .set(REVIEWARTIFACT.NOVELID, novelId)
                .set(REVIEWARTIFACT.ARTIFACTKEY, artifactId)
                .set(REVIEWARTIFACT.KIND, Reviewartifactkind.video_adaptation_plan)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.applied)
                .set(REVIEWARTIFACT.PAYLOADJSON, "{}")
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.VIDEOADAPTATIONID, adaptationId)
                .set(REVIEWARTIFACT.VIDEOADAPTATIONTASKID, taskId)
                .set(REVIEWARTIFACT.CREATEDAT, INITIAL)
                .set(REVIEWARTIFACT.UPDATEDAT, INITIAL)
                .set(REVIEWARTIFACT.APPLIEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(VIDEOSHOTPLANVERSION)
                .set(VIDEOSHOTPLANVERSION.ID, planId)
                .set(VIDEOSHOTPLANVERSION.ADAPTATIONID, adaptationId)
                .set(VIDEOSHOTPLANVERSION.VERSIONNO, 1)
                .set(VIDEOSHOTPLANVERSION.SOURCETASKID, taskId)
                .set(VIDEOSHOTPLANVERSION.REVIEWARTIFACTID, artifactId)
                .set(VIDEOSHOTPLANVERSION.CREATEDBYUSERID, owner)
                .set(VIDEOSHOTPLANVERSION.CONTENTHASH, "c".repeat(64))
                .set(VIDEOSHOTPLANVERSION.CREATEDAT, INITIAL)
                .execute();
        database.dsl().update(VIDEOCHAPTERADAPTATIONHEAD)
                .set(VIDEOCHAPTERADAPTATIONHEAD.CURRENTSHOTPLANVERSIONID, planId)
                .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, 2)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId))
                .execute();
        database.dsl().insertInto(VIDEOCINEMATICSCENE)
                .set(VIDEOCINEMATICSCENE.ID, sceneId)
                .set(VIDEOCINEMATICSCENE.PLANVERSIONID, planId)
                .set(VIDEOCINEMATICSCENE.ADAPTATIONID, adaptationId)
                .set(VIDEOCINEMATICSCENE.SCENEKEY, "SC01")
                .set(VIDEOCINEMATICSCENE.ORDINAL, 1)
                .set(VIDEOCINEMATICSCENE.TITLE, "场景")
                .set(VIDEOCINEMATICSCENE.LOCATIONLABEL, "室内")
                .set(VIDEOCINEMATICSCENE.TIMELABEL, "白天")
                .set(VIDEOCINEMATICSCENE.OBJECTIVE, "推进冲突")
                .set(VIDEOCINEMATICSCENE.CHANGESUMMARY, "局势变化")
                .execute();
        database.dsl().insertInto(VIDEODRAMATICBEAT)
                .set(VIDEODRAMATICBEAT.ID, beatId)
                .set(VIDEODRAMATICBEAT.PLANVERSIONID, planId)
                .set(VIDEODRAMATICBEAT.SCENEID, sceneId)
                .set(VIDEODRAMATICBEAT.BEATKEY, "B01")
                .set(VIDEODRAMATICBEAT.ORDINAL, 1)
                .set(VIDEODRAMATICBEAT.TITLE, "节拍")
                .set(VIDEODRAMATICBEAT.DRAMATICTURN, "冲突升级")
                .set(VIDEODRAMATICBEAT.VISUALSTRATEGY, "近景压迫")
                .execute();
        database.dsl().insertInto(VIDEODRAMATICBEATSOURCEANCHOR)
                .set(VIDEODRAMATICBEATSOURCEANCHOR.BEATID, beatId)
                .set(VIDEODRAMATICBEATSOURCEANCHOR.ORDINAL, 1)
                .set(VIDEODRAMATICBEATSOURCEANCHOR.PLANVERSIONID, planId)
                .set(VIDEODRAMATICBEATSOURCEANCHOR.STARTCODEPOINT, 0)
                .set(VIDEODRAMATICBEATSOURCEANCHOR.ENDCODEPOINT, 2)
                .execute();
        database.dsl().insertInto(VIDEOSHOT)
                .set(VIDEOSHOT.ID, shotId)
                .set(VIDEOSHOT.PLANVERSIONID, planId)
                .set(VIDEOSHOT.SCENEID, sceneId)
                .set(VIDEOSHOT.BEATID, beatId)
                .set(VIDEOSHOT.SHOTKEY, "S01")
                .set(VIDEOSHOT.ORDINAL, 1)
                .set(VIDEOSHOT.TITLE, "镜头")
                .set(VIDEOSHOT.NARRATIVEPURPOSE, "reveal")
                .set(VIDEOSHOT.ADAPTATIONTYPE, "direct")
                .set(VIDEOSHOT.SHOTSCALE, "close")
                .set(VIDEOSHOT.CAMERAANGLE, "eye_level")
                .set(VIDEOSHOT.CAMERAMOVEMENT, "locked")
                .set(VIDEOSHOT.VISUALINTENT, "观察反应")
                .set(VIDEOSHOT.AUDIOMODE, "ambient")
                .set(VIDEOSHOT.AUDIOINTENT, "环境声")
                .set(VIDEOSHOT.CUTREASON, "信息变化")
                .set(VIDEOSHOT.TIMELINEDURATIONMS, 3_000)
                .execute();
        database.dsl().insertInto(VIDEOSHOTSOURCEANCHOR)
                .set(VIDEOSHOTSOURCEANCHOR.SHOTID, shotId)
                .set(VIDEOSHOTSOURCEANCHOR.ORDINAL, 1)
                .set(VIDEOSHOTSOURCEANCHOR.PLANVERSIONID, planId)
                .set(VIDEOSHOTSOURCEANCHOR.STARTCODEPOINT, 1)
                .set(VIDEOSHOTSOURCEANCHOR.ENDCODEPOINT, 2)
                .execute();
    }

    private static void fixture(
            String owner,
            String novelId,
            String projectId,
            String chapterId,
            String content,
            Storylengthprofile profile) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, novelId)
                .set(NOVEL.USERID, owner)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, novelId + "-bible")
                .set(WRITINGBIBLE.NOVELID, novelId)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, profile)
                .set(WRITINGBIBLE.CREATEDAT, INITIAL)
                .set(WRITINGBIBLE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(VIDEOPROJECT)
                .set(VIDEOPROJECT.ID, projectId)
                .set(VIDEOPROJECT.NOVELID, novelId)
                .set(VIDEOPROJECT.TITLE, "章节影视化")
                .set(VIDEOPROJECT.MODE, "series")
                .set(VIDEOPROJECT.STATUS, "draft")
                .set(VIDEOPROJECT.TARGETASPECTRATIO, "16:9")
                .set(VIDEOPROJECT.TARGETLANGUAGE, "zh-CN")
                .set(VIDEOPROJECT.PROVIDER, "seedance_2_5")
                .set(VIDEOPROJECT.REVISION, 1)
                .set(VIDEOPROJECT.CREATEDAT, INITIAL)
                .set(VIDEOPROJECT.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, content)
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
    }

    private static CreateChapterAdaptationRequest request(
            String chapterId, String clientRequestId, LocalDateTime expected) {
        return new CreateChapterAdaptationRequest(
                chapterId,
                clientRequestId,
                expected.atOffset(ZoneOffset.UTC));
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
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
}
