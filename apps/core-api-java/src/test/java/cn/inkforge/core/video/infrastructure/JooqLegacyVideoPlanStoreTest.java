package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOGENERATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSCENE;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.CameraBeatSpec;
import cn.inkforge.contracts.api.SceneAssetsStageArguments;
import cn.inkforge.contracts.api.ScenePromptSpec;
import cn.inkforge.contracts.api.SeedanceOutputSpec;
import cn.inkforge.contracts.api.SeedancePromptPackage;
import cn.inkforge.contracts.api.VideoPlanAttemptState;
import cn.inkforge.contracts.api.VideoPlanCallReservationRequest;
import cn.inkforge.contracts.api.VideoPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoPlanFailureCallback;
import cn.inkforge.contracts.api.VideoPlanProgressQuery;
import cn.inkforge.contracts.api.VideoStoryPlanCheckpointCallback;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.video.application.LegacyVideoPlanDispatchStore;
import cn.inkforge.core.video.application.LegacyVideoPlanStore;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
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
class JooqLegacyVideoPlanStoreTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T05:00:00.123Z"), ZoneOffset.UTC);
    private static final String EMPTY_SETTING_HASH =
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945";

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_legacy_video_plan_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static LegacyVideoPlanStore store;
    private static LegacyVideoPlanDispatchStore dispatchStore;

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
        store = new JooqLegacyVideoPlanStore(
                database, new CuidV1Generator(CLOCK), CLOCK, json);
        dispatchStore = new JooqLegacyVideoPlanDispatchStore(
                database, CLOCK, json, "test");
    }

    @AfterEach
    void cleanup() {
        database.dsl().deleteFrom(NOVEL)
                .where(NOVEL.ID.like("legacy-video-%"))
                .execute();
        database.dsl().deleteFrom(USER)
                .where(USER.ID.like("legacy-video-%"))
                .execute();
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 历史任务的进度预留检查点失败终态和补投必须闭环() {
        Fixture fixture = fixture("failure");

        var empty = store.getProgress(progress(fixture));
        assertThat(empty.getStatus().getValue()).isEqualTo("active");
        assertThat(empty.getCheckpointStage().getValue()).isEqualTo("empty");
        assertThat(empty.getInputFingerprint()).matches("[0-9a-f]{64}");

        VideoPlanCallReservationRequest reservation = new VideoPlanCallReservationRequest(
                VideoPlanCallReservationRequest.CheckpointStageEnum.EMPTY,
                "reserve-assets-1",
                0,
                fixture.jobId(),
                fixture.novelId(),
                fixture.projectId(),
                "1.0",
                fixture.taskId(),
                fixture.sceneId(),
                VideoPlanCallReservationRequest.StageEnum.SCENE_ASSETS,
                fixture.taskId());
        var first = store.reserveCall(reservation);
        var replay = store.reserveCall(reservation);
        assertThat(replay).isEqualTo(first);
        assertThat(first.getAttemptState().getReservedCalls()).isOne();

        SceneAssetsStageArguments assets = assets();
        VideoPlanAttemptState completedAttempt = new VideoPlanAttemptState(null, 1);
        completedAttempt.setInheritedCalls(0);
        VideoStoryPlanCheckpointCallback checkpoint = new VideoStoryPlanCheckpointCallback(
                completedAttempt,
                VideoStoryPlanCheckpointCallback.CheckpointStageEnum.SCENE_ASSETS,
                "checkpoint-assets-1",
                fixture.jobId(),
                fixture.novelId(),
                fixture.projectId(),
                "1.0",
                fixture.taskId(),
                fixture.sceneId(),
                fixture.taskId());
        checkpoint.setSceneAssetsPlan(assets);
        store.saveCheckpoint(checkpoint);
        store.saveCheckpoint(checkpoint);
        assertThat(store.getProgress(progress(fixture)).getSceneAssetsPlan()).isEqualTo(assets);

        VideoPlanFailureCallback failure = new VideoPlanFailureCallback(
                "VIDEO_PLAN_FAILED",
                "failure-event-1",
                fixture.jobId(),
                "完整失败详情，不能截断",
                fixture.novelId(),
                fixture.projectId(),
                "1.0",
                false,
                fixture.taskId(),
                fixture.sceneId(),
                fixture.taskId());
        store.fail(failure);
        store.fail(failure);
        var terminal = store.getProgress(progress(fixture));
        assertThat(terminal.getStatus().getValue()).isEqualTo("failed");
        assertThat(terminal.getCheckpointStage().getValue()).isEqualTo("terminal");
        assertThat(terminal.getSceneAssetsPlan()).isNull();
        assertThat(terminal.getAttemptState().getReservedCalls()).isOne();
        assertThat(database.dsl().select(VIDEOGENERATIONTASK.LASTERRORMESSAGE)
                        .from(VIDEOGENERATIONTASK)
                        .where(VIDEOGENERATIONTASK.ID.eq(fixture.taskId()))
                        .fetchSingle(VIDEOGENERATIONTASK.LASTERRORMESSAGE))
                .isEqualTo("完整失败详情，不能截断");

        VideoPlanFailureCallback changed = new VideoPlanFailureCallback(
                "VIDEO_PLAN_FAILED",
                "failure-event-1",
                fixture.jobId(),
                "另一条失败",
                fixture.novelId(),
                fixture.projectId(),
                "1.0",
                false,
                fixture.taskId(),
                fixture.sceneId(),
                fixture.taskId());
        assertCode(() -> store.fail(changed), "VIDEO_PLAN_TERMINAL_CALLBACK_CONFLICT");

        Fixture due = fixture("dispatch");
        assertThat(dispatchStore.claimDue(10))
                .extracting(value -> value.taskId())
                .containsExactly(due.taskId());
        dispatchStore.markSubmitted(due.taskId());
        assertThat(database.dsl().select(VIDEOGENERATIONTASK.STATUS)
                        .from(VIDEOGENERATIONTASK)
                        .where(VIDEOGENERATIONTASK.ID.eq(due.taskId()))
                        .fetchSingle(VIDEOGENERATIONTASK.STATUS))
                .isEqualTo("submitted");
    }

    @Test
    void 历史成功回调必须创建唯一待审候选并精确重放() {
        Fixture fixture = fixture("completion");
        VideoPlanCompletionCallback completion = completion(fixture);

        store.complete(completion);
        store.complete(completion);

        assertThat(database.dsl().select(REVIEWARTIFACT.STATUS)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.VIDEOSCENEID.eq(fixture.sceneId()))
                        .fetchSingle(REVIEWARTIFACT.STATUS))
                .isEqualTo(Reviewartifactstatus.awaiting_user);
        assertThat(database.dsl().select(VIDEOSCENE.STATUS)
                        .from(VIDEOSCENE)
                        .where(VIDEOSCENE.ID.eq(fixture.sceneId()))
                        .fetchSingle(VIDEOSCENE.STATUS))
                .isEqualTo("awaiting_review");
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACT,
                        REVIEWARTIFACT.VIDEOSCENEID.eq(fixture.sceneId())))
                .isOne();
    }

    @Test
    void 历史成功回调遇到损坏冻结输入时保持Python错误码() {
        Fixture fixture = fixture("invalid-frozen-input");
        database.dsl().update(VIDEOGENERATIONTASK)
                .set(VIDEOGENERATIONTASK.REQUESTJSON, "{\"broken\":true}")
                .where(VIDEOGENERATIONTASK.ID.eq(fixture.taskId()))
                .execute();

        assertCode(
                () -> store.complete(completion(fixture)),
                "VIDEO_PLAN_SETTING_REFERENCE_INVALID");
    }

    private static VideoPlanCompletionCallback completion(Fixture fixture) {
        SeedanceOutputSpec output = new SeedanceOutputSpec(15);
        CameraBeatSpec beat = new CameraBeatSpec(
                "沈砚侧耳判断门外异响",
                "beat-01",
                "平视",
                "固定机位",
                15,
                CameraBeatSpec.ShotSizeEnum.fromValue("中景"),
                0);
        ScenePromptSpec plan = new ScenePromptSpec(
                List.of(),
                List.of(beat),
                "动作由雨声中的异响触发",
                List.of("禁止无动机移动"),
                output,
                fixture.sceneId(),
                "沈砚确认门外威胁",
                "雨夜对峙",
                "冷峻现实主义");
        SeedancePromptPackage prompt = new SeedancePromptPackage(
                List.of(),
                false,
                true,
                output,
                true,
                "雨夜门外传来异响",
                9,
                fixture.sceneId(),
                false);
        return new VideoPlanCompletionCallback(
                "complete-event-1",
                fixture.jobId(),
                fixture.novelId(),
                fixture.projectId(),
                prompt,
                "1.0",
                fixture.taskId(),
                fixture.sceneId(),
                plan,
                fixture.taskId());
    }

    private static SceneAssetsStageArguments assets() {
        return new SceneAssetsStageArguments(
                List.of(),
                "警觉逐步升级",
                "动作由声音触发",
                List.of("禁止无动机移动"),
                "沈砚在雨夜确认威胁",
                "雨夜对峙",
                "冷峻现实主义");
    }

    private static VideoPlanProgressQuery progress(Fixture fixture) {
        return new VideoPlanProgressQuery(
                fixture.jobId(),
                fixture.novelId(),
                fixture.projectId(),
                "1.0",
                fixture.taskId(),
                fixture.sceneId(),
                fixture.taskId());
    }

    private static Fixture fixture(String suffix) {
        String userId = "legacy-video-user-" + suffix;
        String novelId = "legacy-video-novel-" + suffix;
        String chapterId = "legacy-video-chapter-" + suffix;
        String projectId = "legacy-video-project-" + suffix;
        String sceneId = "legacy-video-scene-" + suffix;
        String taskId = "legacy-video-task-" + suffix;
        String jobId = "video-plan-test-" + taskId;
        String source = "沈砚听见门外异响。";
        database.dsl().insertInto(USER)
                .set(USER.ID, userId)
                .set(USER.USERNAME, userId)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, novelId)
                .set(NOVEL.USERID, userId)
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
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, source)
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(VIDEOPROJECT)
                .set(VIDEOPROJECT.ID, projectId)
                .set(VIDEOPROJECT.NOVELID, novelId)
                .set(VIDEOPROJECT.TITLE, "历史视频项目")
                .set(VIDEOPROJECT.MODE, "highlight")
                .set(VIDEOPROJECT.STATUS, "draft")
                .set(VIDEOPROJECT.TARGETASPECTRATIO, "16:9")
                .set(VIDEOPROJECT.TARGETLANGUAGE, "zh-CN")
                .set(VIDEOPROJECT.PROVIDER, "seedance_2_5")
                .set(VIDEOPROJECT.REVISION, 1)
                .set(VIDEOPROJECT.CREATEDAT, INITIAL)
                .set(VIDEOPROJECT.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(VIDEOSCENE)
                .set(VIDEOSCENE.ID, sceneId)
                .set(VIDEOSCENE.PROJECTID, projectId)
                .set(VIDEOSCENE.CHAPTERID, chapterId)
                .set(VIDEOSCENE.NOVELID, novelId)
                .set(VIDEOSCENE.ORDINAL, 1)
                .set(VIDEOSCENE.TITLE, "雨夜对峙")
                .set(VIDEOSCENE.SOURCETEXT, source)
                .set(VIDEOSCENE.SOURCEHASH, CommandIdempotency.sha256(
                        source.getBytes(StandardCharsets.UTF_8)))
                .set(VIDEOSCENE.DURATIONSECONDS, 15)
                .set(VIDEOSCENE.STATUS, "generating")
                .set(VIDEOSCENE.REVISION, 1)
                .set(VIDEOSCENE.CREATEDAT, INITIAL)
                .set(VIDEOSCENE.UPDATEDAT, INITIAL)
                .execute();
        String requestJson = """
                {
                  "projectId":"%s",
                  "sceneId":"%s",
                  "chapterId":"%s",
                  "title":"雨夜对峙",
                  "sourceText":"沈砚听见门外异响。",
                  "revisionInstruction":null,
                  "revisionBaseline":null,
                  "durationSeconds":15,
                  "ratio":"16:9",
                  "settingSnapshot":{"schemaVersion":"1.0","fingerprint":"%s","entries":[]},
                  "planningRoute":"legacy_strict_tool_v1",
                  "planningModel":"deepseek-v4-flash",
                  "directorDraftVersion":"1.0"
                }
                """.formatted(projectId, sceneId, chapterId, EMPTY_SETTING_HASH);
        database.dsl().insertInto(VIDEOGENERATIONTASK)
                .set(VIDEOGENERATIONTASK.ID, taskId)
                .set(VIDEOGENERATIONTASK.PROJECTID, projectId)
                .set(VIDEOGENERATIONTASK.SCENEID, sceneId)
                .set(VIDEOGENERATIONTASK.JOBID, jobId)
                .set(VIDEOGENERATIONTASK.KIND, "plan")
                .set(VIDEOGENERATIONTASK.PROVIDER, "deepseek")
                .set(VIDEOGENERATIONTASK.STATUS, "submitted")
                .set(VIDEOGENERATIONTASK.IDEMPOTENCYKEY, taskId + "-key")
                .set(VIDEOGENERATIONTASK.REQUESTJSON, requestJson)
                .set(VIDEOGENERATIONTASK.ATTEMPTCOUNT, 0)
                .set(VIDEOGENERATIONTASK.NEXTATTEMPTAT, INITIAL)
                .set(VIDEOGENERATIONTASK.CREATEDAT, INITIAL)
                .set(VIDEOGENERATIONTASK.UPDATEDAT, INITIAL)
                .execute();
        return new Fixture(userId, novelId, projectId, sceneId, taskId, jobId);
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

    private record Fixture(
            String userId,
            String novelId,
            String projectId,
            String sceneId,
            String taskId,
            String jobId) {}
}
