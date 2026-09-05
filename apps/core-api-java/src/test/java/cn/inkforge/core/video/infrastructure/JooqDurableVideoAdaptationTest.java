package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.*;
import static cn.inkforge.core.video.support.VideoAdaptationFixtures.candidate;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ConfirmAdaptationPlanRequest;
import cn.inkforge.contracts.api.BeatCoverageGoal;
import cn.inkforge.contracts.api.DramaticBeatCheckpoint;
import cn.inkforge.contracts.api.DramaticSceneCheckpoint;
import cn.inkforge.contracts.api.DramaticStructureCheckpoint;
import cn.inkforge.contracts.api.SaveShotPromptRequest;
import cn.inkforge.contracts.api.SeedanceShotPromptSpec;
import cn.inkforge.contracts.api.ShotPromptSpecBatch;
import cn.inkforge.contracts.api.ShotPromptSpecCandidate;
import cn.inkforge.contracts.api.StartPromptRunRequest;
import cn.inkforge.contracts.api.StartShotPlanRunRequest;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressQuery;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.domain.VideoAdaptationPlans;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.core.type.TypeReference;

/** 原任务、V2 执行和作者决定使用同一真实 PostgreSQL，不能用影子 taskId 替换业务外键。 */
@Testcontainers
class JooqDurableVideoAdaptationTest {
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-06T04:00:00Z"), ZoneOffset.UTC);
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-06T04:00:00");
    private static final String SOURCE = "甲😀乙";
    private static final ObjectMapper JSON = JsonMapper.builder().findAndAddModules().build();
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("isolated-test-only");
    private static CoreDatabase database;
    private static CuidV1Generator ids;
    private static ExecutionRegistry registry;
    private static JooqVideoVisualCanonRepository visuals;

    @BeforeAll
    static void prepare() throws Exception {
        for (String resource : List.of("db/novelwriterdev-schema.sql", "migrations/20260831_durable_agent_execution.sql")) {
            String path = "/tmp/" + resource.substring(resource.lastIndexOf('/') + 1);
            POSTGRES.copyFileToContainer(MountableFile.forClasspathResource(resource), path);
            var result = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(),
                    "-d", POSTGRES.getDatabaseName(), "-f", path);
            assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        }
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername()
                + ":" + POSTGRES.getPassword() + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName()));
        ids = new CuidV1Generator(CLOCK);
        registry = ExecutionRegistryFixtures.videoOperationsEnabled(ExecutionRegistry.Environment.TEST);
        visuals = new JooqVideoVisualCanonRepository(database, ids, CLOCK, JSON);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 新任务原子绑定完整来源且关路由重放不落旧引擎() {
        Fixture f = fixture("video-binding"); var tasks = tasks(f, true);
        var request = new StartShotPlanRunRequest("video-binding-request-0001");
        String taskId = tasks.createPlanTask(f.user(), f.adaptation(), request).taskId();
        var run = run(taskId);
        assertThat(run.get("chapterId")).isNull();
        assertThat(run.get("sourceType")).isEqualTo("video_adaptation_task_v2");
        assertThat(run.get("targetId")).isEqualTo(f.adaptation());
        assertThat(run.get("operation")).isEqualTo("chapter_cinematic_adaptation_v2");
        assertThat(JSON.readTree(run.get("input", String.class))).isEqualTo(JSON.valueToTree(Map.of("taskId", taskId)));
        var evidence = JSON.readTree(database.dsl().fetchOne("""
                SELECT i."contentJson" FROM public."WorkflowEvidenceItem" i
                JOIN public."WorkflowEvidenceBundle" b ON b.id=i."bundleId" WHERE b."runId"=?
                """, run.get("id")).get("contentJson", String.class));
        assertThat(evidence.size()).isEqualTo(3);
        assertThat(evidence.get("taskId").asText()).isEqualTo(taskId);
        assertThat(evidence.get("payload").get("sourceText").asText()).isEqualTo(SOURCE);
        assertThat(evidence.get("inheritedCheckpoint").isNull()).isTrue();
        assertThat(tasks(f, false).createPlanTask(f.user(), f.adaptation(), request).taskId()).isEqualTo(taskId);
        assertThat(tasks(f, false).claimDue(100)).noneMatch(value -> value.taskId().equals(taskId));
        var task = tasks.getTask(f.user(), taskId);
        var progress = new VideoAdaptationWorkflowProgressQuery(f.adaptation(), task.getJobId(), f.novel(), f.project(),
                "1.0", taskId, taskId, VideoAdaptationWorkflowProgressQuery.WorkflowEnum.fromValue(task.getWorkflow()));
        assertCode(() -> tasks(f, false).progress(progress), "VIDEO_ADAPTATION_V2_CALLBACK_REQUIRED");
        tasks(f, false).markSubmitted(taskId);
        tasks(f, false).recordDispatchFailure(taskId, "OLD", false);
        assertThat(tasks.getTask(f.user(), taskId).getStatus()).isEqualTo("pending");
        assertCode(() -> tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-another-request-01")),
                "VIDEO_ADAPTATION_TASK_ACTIVE");
    }

    @Test
    void Run登记异常回滚整个新任务而旧任务开启路由后继续V1() {
        Fixture f = fixture("video-atomic");
        var failing = tasks(f, true, () -> new DurableWorkflowService(plan -> {
            new JooqWorkflowStartRepository(database, ids, CLOCK, JSON).start(plan);
            throw new IllegalStateException("登记失败");
        }));
        assertThatThrownBy(() -> failing.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-atomic-request-01")))
                .isInstanceOf(IllegalStateException.class);
        assertThat(database.dsl().fetchCount(VIDEOADAPTATIONTASK, VIDEOADAPTATIONTASK.ADAPTATIONID.eq(f.adaptation()))).isZero();
        assertThat(database.dsl().fetchCount(WORKFLOWRUN, WORKFLOWRUN.NOVELID.eq(f.novel()))).isZero();
        String taskId = tasks(f, false).createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-legacy-request-01")).taskId();
        assertThat(tasks(f, true).claimDue(100)).anyMatch(value -> value.taskId().equals(taskId));
        assertThat(run(taskId)).isNull();
    }

    @Test
    void 最终候选仍由原Task外键审核确认且领域不篡改Run终态() {
        Fixture f = fixture("video-complete"); var tasks = tasks(f, true);
        String taskId = tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-complete-request-01")).taskId();
        String runId = run(taskId).get("id", String.class);
        var plan = candidate(f.adaptation(), SOURCE);
        var result = database.transactionResult(tx -> {
            tasks.markProcessing(tx, runId);
            return tasks.completePlan(tx, runId, VideoAdaptationPlans.candidateMap(plan));
        });
        assertThat(result.taskId()).isEqualTo(taskId);
        assertThat(result.terminal()).isEqualTo("completed");
        assertThat(tasks.getTask(f.user(), taskId).getStatus()).isEqualTo("completed");
        assertThat(run(taskId).get("status").toString()).isEqualTo("pending");
        assertThat(database.dsl().select(REVIEWARTIFACT.VIDEOADAPTATIONTASKID).from(REVIEWARTIFACT)
                .where(REVIEWARTIFACT.ID.eq(result.artifactId())).fetchSingle(REVIEWARTIFACT.VIDEOADAPTATIONTASKID)).isEqualTo(taskId);
        assertThat(database.dsl().fetchCount(VIDEOSHOTPLANVERSION, VIDEOSHOTPLANVERSION.ADAPTATIONID.eq(f.adaptation()))).isZero();
        var decisions = new JooqVideoAdaptationDecisionStore(database, ids, CLOCK, JSON, visuals);
        decisions.confirmPlan(f.user(), f.adaptation(), new ConfirmAdaptationPlanRequest("video-confirm-request-01", 1, 1, plan));
        assertThat(database.dsl().select(VIDEOSHOTPLANVERSION.SOURCETASKID).from(VIDEOSHOTPLANVERSION)
                .where(VIDEOSHOTPLANVERSION.ADAPTATIONID.eq(f.adaptation())).fetchSingle(VIDEOSHOTPLANVERSION.SOURCETASKID)).isEqualTo(taskId);
    }

    @Test
    void 失败继承完整戏剧检查点跳过分析且取消解除原跨类型互斥() {
        Fixture f = fixture("video-checkpoint"); var tasks = tasks(f, true);
        String first = tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-checkpoint-first-01")).taskId();
        String firstRun = run(first).get("id", String.class);
        Map<String, Object> checkpoint = checkpoint();
        database.transactionResult(tx -> {
            tasks.saveDramaticCheckpoint(tx, firstRun, checkpoint);
            tasks.saveDramaticCheckpoint(tx, firstRun, checkpoint);
            return tasks.finish(tx, firstRun, "failed", "MODEL_OUTPUT_INVALID", "模型输出无效");
        });
        assertThat(tasks.getTask(f.user(), first).getStatus()).isEqualTo("failed");
        assertThat(tasks.getTask(f.user(), first).getLastErrorCode()).isEqualTo("MODEL_OUTPUT_INVALID");
        String second = tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-checkpoint-second-01")).taskId();
        String secondRun = run(second).get("id", String.class);
        var input = JSON.readTree(database.dsl().fetchOne("SELECT input FROM public.\"WorkflowStep\" WHERE \"runId\"=?", secondRun)
                .get("input", String.class));
        assertThat(input.get("stageKey").asText()).isEqualTo("shot_design");
        assertThat(input.get("checkpoint")).isEqualTo(JSON.readTree(JSON.writeValueAsString(checkpoint)));
        assertThat(input.get("dependencies").isEmpty()).isTrue();
        assertThat(tasks.getTask(f.user(), second).getCheckpointStage()).isEqualTo("dramatic_structure");
        database.transactionResult(tx -> tasks.finish(tx, secondRun, "cancelled", "WORKFLOW_CANCELLED", "运行已取消"));
        assertThat(tasks.getTask(f.user(), second).getStatus()).isEqualTo("cancelled");
        assertThat(tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-checkpoint-third-01"))).isNotNull();
    }

    @Test
    void 提示词完整批次只存候选并由原保存入口引用Task() {
        Fixture f = fixture("video-prompt"); var tasks = tasks(f, true);
        var decisions = new JooqVideoAdaptationDecisionStore(database, ids, CLOCK, JSON, visuals);
        var adaptations = new JooqVideoAdaptationRepository(database, ids, CLOCK, JSON, visuals);
        var plan = candidate(f.adaptation(), SOURCE);
        String planTask = tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-prompt-plan-request")).taskId();
        database.transactionResult(tx -> tasks.completePlan(tx, run(planTask).get("id", String.class), VideoAdaptationPlans.candidateMap(plan)));
        decisions.confirmPlan(f.user(), f.adaptation(), new ConfirmAdaptationPlanRequest("video-prompt-confirm-plan", 1, 1, plan));
        var current = adaptations.getDetail(f.user(), f.adaptation());
        String planId = current.getCurrentPlan().getPlanVersionId();
        String shotId = current.getCurrentPlan().getScenes().getFirst().getBeats().getFirst().getShots().getFirst().getId();
        String taskId = tasks.createPromptTask(f.user(), f.adaptation(), new StartPromptRunRequest("video-prompt-start-request", 2, planId)).taskId();
        String runId = run(taskId).get("id", String.class);
        assertThat(run(taskId).get("targetType")).isEqualTo("video_shot_prompt");
        var response = database.transactionResult(tx -> tasks.completePrompts(tx, runId, promptBatch()));
        assertThat(response.artifactId()).isNull();
        var candidates = adaptations.getDetail(f.user(), f.adaptation());
        assertThat(candidates.getPromptVersions()).isEmpty();
        assertThat(candidates.getPromptCandidates()).singleElement().satisfies(value -> assertThat(value.getTaskId()).isEqualTo(taskId));
        decisions.savePrompt(f.user(), f.adaptation(), shotId,
                new SaveShotPromptRequest("作者保留的完整提示词", 1).candidateTaskId(taskId));
        assertThat(database.dsl().select(VIDEOSHOTPROMPTVERSION.SOURCETASKID).from(VIDEOSHOTPROMPTVERSION)
                .where(VIDEOSHOTPROMPTVERSION.SHOTID.eq(shotId)).fetchSingle(VIDEOSHOTPROMPTVERSION.SOURCETASKID)).isEqualTo(taskId);
    }

    @Test
    void 已冻结提示词不因作者确认新Plan而取消且旧候选不出现在新Head下() {
        Fixture f = fixture("video-prompt-head"); var tasks = tasks(f, true);
        var decisions = new JooqVideoAdaptationDecisionStore(database, ids, CLOCK, JSON, visuals);
        var adaptations = new JooqVideoAdaptationRepository(database, ids, CLOCK, JSON, visuals);
        var plan = candidate(f.adaptation(), SOURCE);
        String first = tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-head-first-request")).taskId();
        database.transactionResult(tx -> tasks.completePlan(tx, run(first).get("id", String.class), VideoAdaptationPlans.candidateMap(plan)));
        decisions.confirmPlan(f.user(), f.adaptation(), new ConfirmAdaptationPlanRequest("video-head-first-confirm", 1, 1, plan));
        String oldPlan = adaptations.getDetail(f.user(), f.adaptation()).getCurrentPlan().getPlanVersionId();
        String second = tasks.createPlanTask(f.user(), f.adaptation(),
                new StartShotPlanRunRequest("video-head-second-request").baseShotPlanVersionId(oldPlan)).taskId();
        database.transactionResult(tx -> tasks.completePlan(tx, run(second).get("id", String.class), VideoAdaptationPlans.candidateMap(plan)));
        String prompt = tasks.createPromptTask(f.user(), f.adaptation(), new StartPromptRunRequest("video-head-prompt-request", 2, oldPlan)).taskId();
        String promptRun = run(prompt).get("id", String.class);
        decisions.confirmPlan(f.user(), f.adaptation(), new ConfirmAdaptationPlanRequest("video-head-second-confirm", 2, 1, plan));
        assertThat(database.<Boolean>transactionResult(tx -> tasks.targetExists(tx, promptRun))).isTrue();
        database.transactionResult(tx -> tasks.completePrompts(tx, promptRun, promptBatch()));
        assertThat(tasks.getTask(f.user(), prompt).getStatus()).isEqualTo("completed");
        assertThat(adaptations.getDetail(f.user(), f.adaptation()).getPromptCandidates()).isEmpty();
    }

    @Test
    void 实时章节编辑和删除不使已经冻结的改编来源失效() {
        Fixture f = fixture("video-frozen-chapter", true); var tasks = tasks(f, true);
        String chapterId = f.novel() + "-chapter";
        String taskId = tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-frozen-chapter-start")).taskId();
        String runId = run(taskId).get("id", String.class);
        database.dsl().update(CHAPTER).set(CHAPTER.CONTENT, "作者后续编辑，与旧快照不同")
                .where(CHAPTER.ID.eq(chapterId)).execute();
        assertThat(database.<Boolean>transactionResult(tx -> tasks.targetExists(tx, runId))).isTrue();
        database.dsl().deleteFrom(CHAPTER).where(CHAPTER.ID.eq(chapterId)).execute();
        assertThat(database.<Boolean>transactionResult(tx -> tasks.targetExists(tx, runId))).isTrue();
        database.transactionResult(tx -> tasks.completePlan(tx, runId, VideoAdaptationPlans.candidateMap(candidate(f.adaptation(), SOURCE))));
        assertThat(tasks.getTask(f.user(), taskId).getStatus()).isEqualTo("completed");
        assertThat(run(taskId).get("chapterId")).isNull();
    }

    @Test
    void 新请求在账务锁之前不占业务锁并能在失败投影后继续() throws Exception {
        Fixture f = fixture("video-lock-order"); var tasks = tasks(f, true);
        String old = tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-lock-order-old-start")).taskId();
        String runId = run(old).get("id", String.class);
        CountDownLatch billingLocked = new CountDownLatch(1);
        CountDownLatch releaseBilling = new CountDownLatch(1);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var finish = executor.submit(() -> database.transactionResult(tx -> {
                tx.fetchOne("SELECT id FROM public.\"User\" WHERE id=? FOR UPDATE", f.user());
                billingLocked.countDown();
                try {
                    if (!releaseBilling.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("测试未释放账务锁");
                } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw new IllegalStateException(interrupted); }
                return tasks.finish(tx, runId, "failed", "MODEL_OUTPUT_INVALID", "模型输出无效");
            }));
            assertThat(billingLocked.await(5, TimeUnit.SECONDS)).isTrue();
            var next = executor.submit(() -> tasks.createPlanTask(f.user(), f.adaptation(), new StartShotPlanRunRequest("video-lock-order-new-start")));
            try {
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                boolean waiting = false;
                while (System.nanoTime() < deadline) {
                    waiting = Boolean.TRUE.equals(database.dsl().fetchOne("""
                            SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_stat_activity
                              WHERE datname=current_database() AND wait_event_type='Lock'
                                AND query LIKE '%FROM public."User"%') AS waiting
                            """).get("waiting", Boolean.class));
                    if (waiting) break;
                    Thread.sleep(10);
                }
                assertThat(waiting).as("新请求先等待 User 锁，不持有 Project/Task 反锁账务").isTrue();
            } finally { releaseBilling.countDown(); }
            assertThat(finish.get(5, TimeUnit.SECONDS)).isEqualTo("failed");
            assertThat(next.get(5, TimeUnit.SECONDS).taskId()).isNotEqualTo(old);
        } finally { releaseBilling.countDown(); }
    }

    private static JooqVideoAdaptationTaskStore tasks(Fixture f, boolean route) {
        return tasks(f, route, () -> new DurableWorkflowService(new JooqWorkflowStartRepository(database, ids, CLOCK, JSON)));
    }

    private static JooqVideoAdaptationTaskStore tasks(Fixture f, boolean route, Supplier<DurableWorkflowService> service) {
        Map<String, String> values = Map.of("APP_ENV", "test", "VIDEO_PREVIEW_ENABLED", "true",
                "DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true", "DURABLE_AGENT_EXECUTION_ROUTE_MODE", route ? "allowlist" : "off",
                "DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", f.user(), "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", f.novel());
        return new JooqVideoAdaptationTaskStore(database, ids, CLOCK, JSON, visuals, "test", CoreSettings.from(values), registry, service);
    }

    private static org.jooq.Record run(String taskId) {
        return database.dsl().fetchOne("SELECT * FROM public.\"WorkflowRun\" WHERE \"sourceType\"='video_adaptation_task_v2' AND \"sourceId\"=?", taskId);
    }

    private static Map<String, Object> checkpoint() {
        var goal = new BeatCoverageGoal("门后有人", "G01", BeatCoverageGoal.KindEnum.STORY_INFORMATION, BeatCoverageGoal.PriorityEnum.ESSENTIAL);
        var beat = new DramaticBeatCheckpoint("B01", List.of(goal), "疑虑转为确信", List.of("U01"), "发现", "从空镜切到人物反应");
        var scene = new DramaticSceneCheckpoint(List.of(beat), "人物发现异常", "室内", "揭示真相", "SC01", "夜晚", "场景");
        return JSON.convertValue(new DramaticStructureCheckpoint(List.of(scene)), new TypeReference<>() {});
    }

    private static Map<String, Object> promptBatch() {
        var spec = new SeedanceShotPromptSpec("风声与门轴声。", "缓慢推近。", "林岚站在门前。", "她缓慢推门。")
                .expressionAndGaze("警觉地看向门缝。").negativeConstraints(List.of("不要字幕。"));
        return JSON.convertValue(new ShotPromptSpecBatch(List.of(new ShotPromptSpecCandidate("S01", spec))), new TypeReference<>() {});
    }

    private static Fixture fixture(String prefix) {
        return fixture(prefix, false);
    }

    private static Fixture fixture(String prefix, boolean withChapter) {
        Fixture f = new Fixture(prefix + "-user", prefix + "-novel", prefix + "-project", prefix + "-adaptation");
        database.dsl().insertInto(USER).set(USER.ID, f.user()).set(USER.USERNAME, f.user()).set(USER.PASSWORDHASH, "test")
                .set(USER.CREATEDAT, NOW).set(USER.UPDATEDAT, NOW).execute();
        database.dsl().insertInto(NOVEL).set(NOVEL.ID, f.novel()).set(NOVEL.NAME, f.novel()).set(NOVEL.USERID, f.user())
                .set(NOVEL.CREATEDAT, NOW).set(NOVEL.UPDATEDAT, NOW).execute();
        database.dsl().insertInto(WRITINGBIBLE).set(WRITINGBIBLE.ID, prefix + "-bible").set(WRITINGBIBLE.NOVELID, f.novel())
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, Storylengthprofile.long_serial).set(WRITINGBIBLE.CREATEDAT, NOW).set(WRITINGBIBLE.UPDATEDAT, NOW).execute();
        if (withChapter) database.dsl().insertInto(CHAPTER).set(CHAPTER.ID, f.novel() + "-chapter").set(CHAPTER.NOVELID, f.novel())
                .set(CHAPTER.TITLE, "第一章").set(CHAPTER.CONTENT, SOURCE).set(CHAPTER.ORDER, 1)
                .set(CHAPTER.CREATEDAT, NOW).set(CHAPTER.UPDATEDAT, NOW).execute();
        database.dsl().insertInto(VIDEOPROJECT).set(VIDEOPROJECT.ID, f.project()).set(VIDEOPROJECT.NOVELID, f.novel())
                .set(VIDEOPROJECT.TITLE, "章节影视化").set(VIDEOPROJECT.MODE, "series").set(VIDEOPROJECT.STATUS, "draft")
                .set(VIDEOPROJECT.TARGETASPECTRATIO, "16:9").set(VIDEOPROJECT.TARGETLANGUAGE, "zh-CN").set(VIDEOPROJECT.PROVIDER, "seedance_2_5")
                .set(VIDEOPROJECT.REVISION, 1).set(VIDEOPROJECT.CREATEDAT, NOW).set(VIDEOPROJECT.UPDATEDAT, NOW).execute();
        database.dsl().insertInto(VIDEOCHAPTERADAPTATION).set(VIDEOCHAPTERADAPTATION.ID, f.adaptation())
                .set(VIDEOCHAPTERADAPTATION.PROJECTID, f.project()).set(VIDEOCHAPTERADAPTATION.NOVELID, f.novel())
                .set(VIDEOCHAPTERADAPTATION.CHAPTERID, withChapter ? f.novel() + "-chapter" : null)
                .set(VIDEOCHAPTERADAPTATION.CHAPTERTITLE, "第一章").set(VIDEOCHAPTERADAPTATION.CHAPTERUPDATEDAT, NOW)
                .set(VIDEOCHAPTERADAPTATION.SOURCETEXT, SOURCE).set(VIDEOCHAPTERADAPTATION.SOURCEHASH, candidate(f.adaptation(), SOURCE).getSourceHash())
                .set(VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS, "active").set(VIDEOCHAPTERADAPTATION.CREATEDAT, NOW).execute();
        database.dsl().insertInto(VIDEOCHAPTERADAPTATIONHEAD).set(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID, f.adaptation())
                .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, 1).set(VIDEOCHAPTERADAPTATIONHEAD.UPDATEDAT, NOW).execute();
        return f;
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(ApiException.class, failure -> assertThat(failure.code()).isEqualTo(code));
    }

    private record Fixture(String user, String novel, String project, String adaptation) {}
}
