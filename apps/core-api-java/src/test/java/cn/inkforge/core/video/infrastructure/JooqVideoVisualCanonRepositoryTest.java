package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOCINEMATICSCENE;
import static cn.inkforge.core.db.generated.Tables.VIDEODRAMATICBEAT;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTVISUALREFERENCEBINDING;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTVISUALREFERENCESET;
import static cn.inkforge.core.db.generated.Tables.VIDEOVISUALCANON;
import static cn.inkforge.core.db.generated.Tables.VIDEOVISUALCANONVERSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.VisualCanonApproval;
import cn.inkforge.core.video.application.VisualCanonCandidateCommand;
import cn.inkforge.core.video.application.ShotVisualReferenceSelection;
import cn.inkforge.core.video.application.ShotVisualReferencesCommand;
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
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqVideoVisualCanonRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T05:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_visual_canon_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqVideoVisualCanonRepository repository;
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
        repository = new JooqVideoVisualCanonRepository(
                database, new CuidV1Generator(CLOCK), CLOCK, new ObjectMapper());
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            List<String> projectIds = database.dsl()
                    .select(VIDEOPROJECT.ID)
                    .from(VIDEOPROJECT)
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                    .where(NOVEL.USERID.in(users))
                    .fetch(VIDEOPROJECT.ID);
            if (!projectIds.isEmpty()) {
                // Head 反向引用当前不可变版本，素材又被版本 RESTRICT；测试按真实依赖顺序清理。
                database.dsl().deleteFrom(VIDEOSHOTVISUALREFERENCEBINDING)
                        .where(VIDEOSHOTVISUALREFERENCEBINDING.PROJECTID.in(projectIds))
                        .execute();
                database.dsl().deleteFrom(VIDEOSHOTVISUALREFERENCESET)
                        .where(VIDEOSHOTVISUALREFERENCESET.PROJECTID.in(projectIds))
                        .execute();
                List<String> adaptationIds = database.dsl()
                        .select(VIDEOCHAPTERADAPTATION.ID)
                        .from(VIDEOCHAPTERADAPTATION)
                        .where(VIDEOCHAPTERADAPTATION.PROJECTID.in(projectIds))
                        .fetch(VIDEOCHAPTERADAPTATION.ID);
                if (!adaptationIds.isEmpty()) {
                    database.dsl().update(VIDEOCHAPTERADAPTATIONHEAD)
                            .set(
                                    VIDEOCHAPTERADAPTATIONHEAD.CURRENTSHOTPLANVERSIONID,
                                    (String) null)
                            .set(
                                    VIDEOCHAPTERADAPTATIONHEAD.CURRENTEPISODEPLANVERSIONID,
                                    (String) null)
                            .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.in(adaptationIds))
                            .execute();
                    database.dsl().deleteFrom(VIDEOSHOTPLANVERSION)
                            .where(VIDEOSHOTPLANVERSION.ADAPTATIONID.in(adaptationIds))
                            .execute();
                }
                database.dsl().update(VIDEOVISUALCANON)
                        .set(VIDEOVISUALCANON.CURRENTVERSIONID, (String) null)
                        .where(VIDEOVISUALCANON.PROJECTID.in(projectIds))
                        .execute();
                database.dsl().deleteFrom(VIDEOVISUALCANONVERSION)
                        .where(VIDEOVISUALCANONVERSION.PROJECTID.in(projectIds))
                        .execute();
                database.dsl().deleteFrom(VIDEOVISUALCANON)
                        .where(VIDEOVISUALCANON.PROJECTID.in(projectIds))
                        .execute();
                database.dsl().deleteFrom(VIDEOASSET)
                        .where(VIDEOASSET.PROJECTID.in(projectIds))
                        .execute();
                database.dsl().deleteFrom(VIDEOPROJECT)
                        .where(VIDEOPROJECT.ID.in(projectIds))
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
    void 候选必须引用归属文字设定和已确认职责匹配图片且同值不推进revision() {
        String owner = user("canon-owner-1");
        fixture(owner, "canon-novel-1", "project-1", "character-1");
        asset("asset-1", "project-1", "identity", "confirmed", INITIAL);

        var first = repository.setCandidate(
                owner, "project-1", command("asset-1", "character-1"));
        var replay = repository.setCandidate(
                owner, "project-1", command("asset-1", "character-1"));

        assertThat(first.getRevision()).isOne();
        assertThat(replay.getRevision()).isOne();
        assertThat(replay.getCandidateAsset().getId()).isEqualTo("asset-1");
        assertThat(replay.getCandidateIncludeFeatures()).containsExactly("正脸", "黑发");
        assertThat(database.dsl().fetchCount(VIDEOVISUALCANON)).isOne();

        asset("asset-unconfirmed", "project-1", "identity", "unconfirmed", null);
        assertCode(
                () -> repository.setCandidate(
                        owner, "project-1", command("asset-unconfirmed", "character-1")),
                "VIDEO_VISUAL_CANON_ASSET_UNCONFIRMED");
        asset("asset-wrong-duty", "project-1", "costume", "confirmed", INITIAL);
        assertCode(
                () -> repository.setCandidate(
                        owner, "project-1", command("asset-wrong-duty", "character-1")),
                "VIDEO_VISUAL_CANON_ASSET_INVALID");
        var missingSetting = new VisualCanonCandidateCommand(
                "character",
                "missing",
                "identity",
                "default",
                "默认形象",
                "asset-1",
                List.of(),
                List.of(),
                70);
        assertCode(
                () -> repository.setCandidate(owner, "project-1", missingSetting),
                "VIDEO_VISUAL_SETTING_NOT_FOUND");
    }

    @Test
    void 批准必须创建不可变版本清空候选并支持成功响应丢失后的安全重放() throws Exception {
        String owner = user("canon-owner-2");
        fixture(owner, "canon-novel-2", "project-2", "character-2");
        asset("asset-2", "project-2", "identity", "confirmed", INITIAL);
        var candidate = repository.setCandidate(
                owner, "project-2", command("asset-2", "character-2"));

        var approved = repository.approve(
                owner, candidate.getId(), new VisualCanonApproval(1, "asset-2"));
        var replay = repository.approve(
                owner, candidate.getId(), new VisualCanonApproval(1, "asset-2"));

        assertThat(approved.getCandidateAsset()).isNull();
        assertThat(approved.getCurrentVersionId()).isNotNull();
        assertThat(approved.getRevision()).isEqualTo(2);
        assertThat(approved.getVersions()).hasSize(1);
        assertThat(replay.getRevision()).isEqualTo(2);
        assertThat(replay.getCurrentVersionId()).isEqualTo(approved.getCurrentVersionId());
        assertThat(database.dsl().fetchCount(VIDEOVISUALCANONVERSION)).isOne();

        String canonical = "{\"assetId\":\"asset-2\","
                + "\"assetSha256\":\"" + "a".repeat(64) + "\","
                + "\"canonId\":\"" + approved.getId() + "\","
                + "\"defaultStrength\":70,\"duty\":\"identity\","
                + "\"excludeFeatures\":[\"现代服装\"],"
                + "\"includeFeatures\":[\"正脸\",\"黑发\"],"
                + "\"label\":\"默认形象\",\"settingId\":\"character-2\","
                + "\"settingKind\":\"character\",\"variantKey\":\"default\","
                + "\"versionNo\":1}";
        assertThat(approved.getVersions().getFirst().getContentHash())
                .isEqualTo(sha256(canonical));
    }

    @Test
    void 候选变化必须推进revision且旧批准请求不得覆盖新候选() {
        String owner = user("canon-owner-3");
        fixture(owner, "canon-novel-3", "project-3", "character-3");
        asset("asset-3", "project-3", "identity", "confirmed", INITIAL);
        var first = repository.setCandidate(
                owner, "project-3", command("asset-3", "character-3"));
        var changed = new VisualCanonCandidateCommand(
                "character",
                "character-3",
                "identity",
                "default",
                "新版形象",
                "asset-3",
                List.of("侧脸"),
                List.of(),
                80);
        var second = repository.setCandidate(owner, "project-3", changed);

        assertThat(second.getRevision()).isEqualTo(first.getRevision() + 1);
        assertCode(
                () -> repository.approve(
                        owner,
                        second.getId(),
                        new VisualCanonApproval(first.getRevision(), "asset-3")),
                "VIDEO_VISUAL_CANON_REVISION_CONFLICT");
        assertThat(database.dsl().fetchCount(VIDEOVISUALCANONVERSION)).isZero();
    }

    @Test
    void 视觉设定库必须按项目私有并返回版本倒序() {
        String owner = user("canon-owner-4");
        String stranger = user("canon-stranger-4");
        fixture(owner, "canon-novel-4", "project-4", "character-4");
        asset("asset-4", "project-4", "identity", "confirmed", INITIAL);
        var candidate = repository.setCandidate(
                owner, "project-4", command("asset-4", "character-4"));
        repository.approve(owner, candidate.getId(), new VisualCanonApproval(1, "asset-4"));
        var secondCandidate = repository.setCandidate(
                owner, "project-4", command("asset-4", "character-4"));
        var second = repository.approve(
                owner,
                secondCandidate.getId(),
                new VisualCanonApproval(3, "asset-4"));

        assertThat(second.getVersions())
                .extracting(value -> value.getVersionNo())
                .containsExactly(2, 1);
        assertCode(
                () -> repository.list(stranger, "project-4"),
                "VIDEO_PROJECT_NOT_FOUND");
        assertCode(
                () -> repository.approve(
                        stranger,
                        candidate.getId(),
                        new VisualCanonApproval(3, "asset-4")),
                "VIDEO_VISUAL_CANON_NOT_FOUND");
    }

    @Test
    void 逐镜参考必须绑定当前正式镜头和同项目不可变版本并按完整集合CAS替换() {
        String owner = user("canon-owner-5");
        fixture(owner, "canon-novel-5", "project-5", "character-5");
        asset("asset-5", "project-5", "identity", "confirmed", INITIAL);
        var canon = repository.setCandidate(
                owner, "project-5", command("asset-5", "character-5"));
        var approved = repository.approve(
                owner, canon.getId(), new VisualCanonApproval(1, "asset-5"));
        String versionId = approved.getCurrentVersionId();
        formalShotPlan(owner, "canon-novel-5", "project-5", "adaptation-5", "shot-5");

        var first = repository.saveShotReferences(
                owner,
                "adaptation-5",
                "shot-5",
                new ShotVisualReferencesCommand(
                        0, List.of(new ShotVisualReferenceSelection(versionId, 80))));
        var replay = repository.saveShotReferences(
                owner,
                "adaptation-5",
                "shot-5",
                new ShotVisualReferencesCommand(
                        0, List.of(new ShotVisualReferenceSelection(versionId, 80))));

        assertThat(first.getRevision()).isOne();
        assertThat(replay.getRevision()).isOne();
        assertThat(first.getReferences()).hasSize(1);
        assertThat(first.getReferences().getFirst().getCanonVersionId()).isEqualTo(versionId);
        assertThat(first.getReferences().getFirst().getAssetSha256()).isEqualTo("a".repeat(64));
        assertThat(first.getReferences().getFirst().getIncludeFeatures())
                .containsExactly("正脸", "黑发");

        assertCode(
                () -> repository.saveShotReferences(
                        owner,
                        "adaptation-5",
                        "shot-5",
                        new ShotVisualReferencesCommand(
                                0,
                                List.of(new ShotVisualReferenceSelection(versionId, 60)))),
                "VIDEO_SHOT_VISUAL_REFERENCE_REVISION_CONFLICT");
        var changed = repository.saveShotReferences(
                owner,
                "adaptation-5",
                "shot-5",
                new ShotVisualReferencesCommand(
                        1, List.of(new ShotVisualReferenceSelection(versionId, 60))));
        assertThat(changed.getRevision()).isEqualTo(2);
        assertThat(changed.getReferences().getFirst().getStrength()).isEqualTo(60);

        var cleared = repository.saveShotReferences(
                owner,
                "adaptation-5",
                "shot-5",
                new ShotVisualReferencesCommand(2, List.of()));
        assertThat(cleared.getRevision()).isEqualTo(3);
        assertThat(cleared.getReferences()).isEmpty();
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
            String owner, String novelId, String projectId, String characterId) {
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
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, Storylengthprofile.long_serial)
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
        database.dsl().insertInto(CHARACTER)
                .set(CHARACTER.ID, characterId)
                .set(CHARACTER.NOVELID, novelId)
                .set(CHARACTER.NAME, "林岚")
                .set(CHARACTER.CREATEDAT, INITIAL)
                .set(CHARACTER.UPDATEDAT, INITIAL)
                .execute();
    }

    private static void asset(
            String id,
            String projectId,
            String duty,
            String rightsStatus,
            LocalDateTime lockedAt) {
        database.dsl().insertInto(VIDEOASSET)
                .set(VIDEOASSET.ID, id)
                .set(VIDEOASSET.PROJECTID, projectId)
                .set(VIDEOASSET.NAME, id)
                .set(VIDEOASSET.MODALITY, "image")
                .set(VIDEOASSET.DUTY, duty)
                .set(VIDEOASSET.STORAGEKEY, projectId + "/" + id + ".png")
                .set(VIDEOASSET.MIMETYPE, "image/png")
                .set(VIDEOASSET.BYTESIZE, 100L)
                .set(VIDEOASSET.SHA256, "a".repeat(64))
                .set(VIDEOASSET.SOURCEKIND, "user_upload")
                .set(VIDEOASSET.RIGHTSSTATUS, rightsStatus)
                .set(VIDEOASSET.LOCKEDAT, lockedAt)
                .set(VIDEOASSET.CREATEDAT, INITIAL)
                .set(VIDEOASSET.UPDATEDAT, INITIAL)
                .execute();
    }

    private static void formalShotPlan(
            String owner,
            String novelId,
            String projectId,
            String adaptationId,
            String shotId) {
        String taskId = adaptationId + "-task";
        String artifactId = adaptationId + "-artifact";
        String planId = adaptationId + "-plan";
        String sceneId = adaptationId + "-scene";
        String beatId = adaptationId + "-beat";
        database.dsl().insertInto(VIDEOCHAPTERADAPTATION)
                .set(VIDEOCHAPTERADAPTATION.ID, adaptationId)
                .set(VIDEOCHAPTERADAPTATION.PROJECTID, projectId)
                .set(VIDEOCHAPTERADAPTATION.NOVELID, novelId)
                .set(VIDEOCHAPTERADAPTATION.CHAPTERTITLE, "第一章")
                .set(VIDEOCHAPTERADAPTATION.CHAPTERUPDATEDAT, INITIAL)
                .set(VIDEOCHAPTERADAPTATION.SOURCETEXT, "正文")
                .set(VIDEOCHAPTERADAPTATION.SOURCEHASH, "b".repeat(64))
                .set(VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS, "active")
                .set(VIDEOCHAPTERADAPTATION.CREATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(VIDEOCHAPTERADAPTATIONHEAD)
                .set(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID, adaptationId)
                .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, 2)
                .set(VIDEOCHAPTERADAPTATIONHEAD.UPDATEDAT, INITIAL)
                .execute();
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
    }

    private static VisualCanonCandidateCommand command(String assetId, String settingId) {
        return new VisualCanonCandidateCommand(
                "character",
                settingId,
                "identity",
                "default",
                "默认形象",
                assetId,
                List.of("正脸", "黑发"),
                List.of("现代服装"),
                70);
    }

    private static String sha256(String value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8)));
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
