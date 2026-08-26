package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.video.support.VideoAdaptationFixtures.candidate;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.BeatCoverageGoal;
import cn.inkforge.contracts.api.ConfirmAdaptationPlanRequest;
import cn.inkforge.contracts.api.DramaticBeatCheckpoint;
import cn.inkforge.contracts.api.DramaticSceneCheckpoint;
import cn.inkforge.contracts.api.DramaticStructureCheckpoint;
import cn.inkforge.contracts.api.SaveShotPromptRequest;
import cn.inkforge.contracts.api.SeedanceShotPromptSpec;
import cn.inkforge.contracts.api.ShotPromptSpecBatch;
import cn.inkforge.contracts.api.ShotPromptSpecCandidate;
import cn.inkforge.contracts.api.StartPromptRunRequest;
import cn.inkforge.contracts.api.StartShotPlanRunRequest;
import cn.inkforge.contracts.api.VideoAdaptationCheckpointCallback;
import cn.inkforge.contracts.api.VideoAdaptationFailureCallback;
import cn.inkforge.contracts.api.VideoAdaptationPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationPromptCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressQuery;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
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
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqVideoAdaptationTaskStoreTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T05:00:00.123Z"), ZoneOffset.UTC);
    private static final String OWNER = "task-owner";
    private static final String NOVEL_ID = "task-novel";
    private static final String PROJECT_ID = "task-project";
    private static final String ADAPTATION_ID = "task-adaptation";
    private static final String SOURCE = "甲😀乙";

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_task_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqVideoAdaptationTaskStore tasks;
    private static JooqVideoAdaptationDecisionStore decisions;
    private static JooqVideoAdaptationRepository adaptations;

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
        ObjectMapper json = JsonMapper.builder().findAndAddModules().build();
        var ids = new CuidV1Generator(CLOCK);
        var visualCanons = new JooqVideoVisualCanonRepository(database, ids, CLOCK, json);
        tasks = new JooqVideoAdaptationTaskStore(
                database, ids, CLOCK, json, visualCanons, "test");
        decisions = new JooqVideoAdaptationDecisionStore(
                database, ids, CLOCK, json, visualCanons);
        adaptations = new JooqVideoAdaptationRepository(
                database, ids, CLOCK, json, visualCanons);
    }

    @AfterEach
    void cleanup() {
        database.dsl().execute("TRUNCATE TABLE \"User\" CASCADE");
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 拆镜到提示词必须走完耐久任务回调审核与保存闭环() {
        fixture();
        var plan = candidate(ADAPTATION_ID, SOURCE);
        var accepted = tasks.createPlanTask(
                OWNER, ADAPTATION_ID, new StartShotPlanRunRequest("plan-request-000001"));
        var replay = tasks.createPlanTask(
                OWNER, ADAPTATION_ID, new StartShotPlanRunRequest("plan-request-000001"));
        assertThat(replay.taskId()).isEqualTo(accepted.taskId());

        var due = tasks.claimDue(10);
        assertThat(due).singleElement().satisfies(dispatch -> {
            assertThat(dispatch.taskId()).isEqualTo(accepted.taskId());
            assertThat(dispatch.jobId()).startsWith("video-adaptation-test-");
            assertThat(dispatch.payload().get("sourceText")).isEqualTo(SOURCE);
        });
        tasks.markSubmitted(accepted.taskId());
        var task = tasks.getTask(OWNER, accepted.taskId());
        var progress = tasks.progress(progress(task));
        assertThat(progress.getStatus().getValue()).isEqualTo("active");

        var checkpoint = checkpoint();
        tasks.saveCheckpoint(new VideoAdaptationCheckpointCallback(
                ADAPTATION_ID,
                checkpoint,
                "checkpoint-event-1",
                task.getJobId(),
                NOVEL_ID,
                PROJECT_ID,
                "1.0",
                task.getId(),
                task.getId()));
        tasks.completePlan(new VideoAdaptationPlanCompletionCallback(
                ADAPTATION_ID,
                plan,
                "plan-complete-event-1",
                task.getJobId(),
                NOVEL_ID,
                PROJECT_ID,
                "1.0",
                task.getId(),
                task.getId()));
        // 相同终态即使 JSON 字段顺序不同也必须语义幂等。
        tasks.completePlan(new VideoAdaptationPlanCompletionCallback(
                ADAPTATION_ID,
                plan,
                "plan-complete-event-1",
                task.getJobId(),
                NOVEL_ID,
                PROJECT_ID,
                "1.0",
                task.getId(),
                task.getId()));
        var awaiting = adaptations.getDetail(OWNER, ADAPTATION_ID);
        assertThat(awaiting.getState().getValue()).isEqualTo("awaiting_review");
        assertThat(awaiting.getReviewArtifact().getSummary())
                .isEqualTo("1 个场景 · 1 个戏剧节拍 · 1 个镜头 · 约 5 秒");

        decisions.confirmPlan(
                OWNER,
                ADAPTATION_ID,
                new ConfirmAdaptationPlanRequest("confirm-request-0001", 1, 1, plan));
        var approved = adaptations.getDetail(OWNER, ADAPTATION_ID);
        String planId = approved.getCurrentPlan().getPlanVersionId();
        String shotId = approved.getCurrentPlan().getScenes().getFirst().getBeats().getFirst()
                .getShots().getFirst().getId();

        var promptAccepted = tasks.createPromptTask(
                OWNER,
                ADAPTATION_ID,
                new StartPromptRunRequest("prompt-request-0001", 2, planId));
        assertThat(tasks.claimDue(10))
                .extracting(value -> value.taskId())
                .containsExactly(promptAccepted.taskId());
        var promptTask = tasks.getTask(OWNER, promptAccepted.taskId());
        ShotPromptSpecBatch batch = promptBatch();
        tasks.completePrompts(new VideoAdaptationPromptCompletionCallback(
                ADAPTATION_ID,
                "prompt-complete-event-1",
                promptTask.getJobId(),
                NOVEL_ID,
                PROJECT_ID,
                batch,
                "1.0",
                promptTask.getId(),
                promptTask.getId()));

        var withCandidate = adaptations.getDetail(OWNER, ADAPTATION_ID);
        assertThat(withCandidate.getPromptCandidates()).singleElement().satisfies(value -> {
            assertThat(value.getTaskId()).isEqualTo(promptTask.getId());
            assertThat(value.getCompiledPrompt())
                    .startsWith("16:9 画幅，5 秒。林岚站在门前");
            assertThat(value.getVisualReferences()).isEmpty();
        });
        decisions.savePrompt(
                OWNER,
                ADAPTATION_ID,
                shotId,
                new SaveShotPromptRequest("作者微调后的完整提示词", 1)
                        .candidateTaskId(promptTask.getId()));
        var saved = adaptations.getDetail(OWNER, ADAPTATION_ID);
        assertThat(saved.getPromptVersions()).hasSize(1);
        assertThat(saved.getPromptCandidates()).isEmpty();
    }

    @Test
    void 失败拆镜的戏剧结构检查点必须可继承且旧任务回调不能覆盖新任务() {
        fixture();
        var first = tasks.createPlanTask(
                OWNER, ADAPTATION_ID, new StartShotPlanRunRequest("plan-request-000002"));
        var firstTask = tasks.getTask(OWNER, first.taskId());
        tasks.saveCheckpoint(new VideoAdaptationCheckpointCallback(
                ADAPTATION_ID,
                checkpoint(),
                "checkpoint-event-2",
                firstTask.getJobId(),
                NOVEL_ID,
                PROJECT_ID,
                "1.0",
                firstTask.getId(),
                firstTask.getId()));
        var failure = new VideoAdaptationFailureCallback(
                ADAPTATION_ID,
                "MODEL_TIMEOUT",
                "failure-event-1",
                firstTask.getJobId(),
                "模型超时",
                NOVEL_ID,
                PROJECT_ID,
                "1.0",
                firstTask.getId(),
                firstTask.getId());
        tasks.fail(failure);
        tasks.fail(failure);

        var second = tasks.createPlanTask(
                OWNER, ADAPTATION_ID, new StartShotPlanRunRequest("plan-request-000003"));
        assertThat(tasks.getTask(OWNER, second.taskId()).getCheckpointStage())
                .isEqualTo("dramatic_structure");
        assertThat(tasks.progress(progress(tasks.getTask(OWNER, second.taskId())))
                        .getCheckpoint())
                .isNotNull();
        assertCode(() -> tasks.fail(failure), "VIDEO_ADAPTATION_CALLBACK_STALE");
    }

    private static void fixture() {
        var plan = candidate(ADAPTATION_ID, SOURCE);
        database.dsl().insertInto(USER)
                .set(USER.ID, OWNER)
                .set(USER.USERNAME, OWNER)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, NOVEL_ID)
                .set(NOVEL.NAME, NOVEL_ID)
                .set(NOVEL.USERID, OWNER)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, NOVEL_ID + "-bible")
                .set(WRITINGBIBLE.NOVELID, NOVEL_ID)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, Storylengthprofile.long_serial)
                .set(WRITINGBIBLE.CREATEDAT, INITIAL)
                .set(WRITINGBIBLE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(VIDEOPROJECT)
                .set(VIDEOPROJECT.ID, PROJECT_ID)
                .set(VIDEOPROJECT.NOVELID, NOVEL_ID)
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
        database.dsl().insertInto(VIDEOCHAPTERADAPTATION)
                .set(VIDEOCHAPTERADAPTATION.ID, ADAPTATION_ID)
                .set(VIDEOCHAPTERADAPTATION.PROJECTID, PROJECT_ID)
                .set(VIDEOCHAPTERADAPTATION.NOVELID, NOVEL_ID)
                .set(VIDEOCHAPTERADAPTATION.CHAPTERTITLE, "第一章")
                .set(VIDEOCHAPTERADAPTATION.CHAPTERUPDATEDAT, INITIAL)
                .set(VIDEOCHAPTERADAPTATION.SOURCETEXT, SOURCE)
                .set(VIDEOCHAPTERADAPTATION.SOURCEHASH, plan.getSourceHash())
                .set(VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS, "active")
                .set(VIDEOCHAPTERADAPTATION.CREATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(VIDEOCHAPTERADAPTATIONHEAD)
                .set(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID, ADAPTATION_ID)
                .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, 1)
                .set(VIDEOCHAPTERADAPTATIONHEAD.UPDATEDAT, INITIAL)
                .execute();
    }

    private static DramaticStructureCheckpoint checkpoint() {
        var goal = new BeatCoverageGoal(
                "门后有人",
                "G01",
                BeatCoverageGoal.KindEnum.STORY_INFORMATION,
                BeatCoverageGoal.PriorityEnum.ESSENTIAL);
        var beat = new DramaticBeatCheckpoint(
                "B01",
                List.of(goal),
                "疑虑转为确信",
                List.of("U01"),
                "发现",
                "从空镜切到人物反应");
        var scene = new DramaticSceneCheckpoint(
                List.of(beat),
                "人物发现异常",
                "室内",
                "揭示真相",
                "SC01",
                "夜晚",
                "场景");
        return new DramaticStructureCheckpoint(List.of(scene));
    }

    private static ShotPromptSpecBatch promptBatch() {
        var specification = new SeedanceShotPromptSpec(
                        "风声与门轴声。",
                        "缓慢推近。",
                        "林岚站在门前。",
                        "她缓慢推门。")
                .expressionAndGaze("警觉地看向门缝。")
                .negativeConstraints(List.of("不要字幕。"));
        return new ShotPromptSpecBatch(List.of(
                new ShotPromptSpecCandidate("S01", specification)));
    }

    private static VideoAdaptationWorkflowProgressQuery progress(
            cn.inkforge.contracts.api.ChapterAdaptationTaskResponse task) {
        return new VideoAdaptationWorkflowProgressQuery(
                ADAPTATION_ID,
                task.getJobId(),
                NOVEL_ID,
                PROJECT_ID,
                "1.0",
                task.getId(),
                task.getId(),
                VideoAdaptationWorkflowProgressQuery.WorkflowEnum.fromValue(task.getWorkflow()));
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code()).isEqualTo(code));
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
