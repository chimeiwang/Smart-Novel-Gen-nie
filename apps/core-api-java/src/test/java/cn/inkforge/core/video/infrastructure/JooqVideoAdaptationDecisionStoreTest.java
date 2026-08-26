package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONDECISIONCOMMAND;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTVERSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.video.support.VideoAdaptationFixtures.candidate;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ConfirmAdaptationPlanRequest;
import cn.inkforge.contracts.api.DiscardAdaptationCandidateRequest;
import cn.inkforge.contracts.api.SaveEpisodePlanRequest;
import cn.inkforge.contracts.api.SaveShotPromptRequest;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.video.domain.VideoAdaptationPlans;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
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
class JooqVideoAdaptationDecisionStoreTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T05:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_decision_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
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
        json = JsonMapper.builder().findAndAddModules().build();
        var ids = new CuidV1Generator(CLOCK);
        var visualCanons = new JooqVideoVisualCanonRepository(database, ids, CLOCK, json);
        decisions = new JooqVideoAdaptationDecisionStore(
                database, ids, CLOCK, json, visualCanons);
        adaptations = new JooqVideoAdaptationRepository(
                database, ids, CLOCK, json, visualCanons);
    }

    @AfterEach
    void cleanup() {
        // 仅作用于该 Testcontainers 临时库；CASCADE 可可靠清除视频版本链中的循环外键。
        database.dsl().execute("TRUNCATE TABLE \"User\" CASCADE");
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 批准必须原子物化完整关系方案且同一命令可重放() {
        var plan = fixture("decision-owner-1", "adaptation-1");
        var request = new ConfirmAdaptationPlanRequest(
                "confirm-request-0001", 1, 1, plan);

        String first = decisions.confirmPlan("decision-owner-1", "adaptation-1", request);
        String replay = decisions.confirmPlan("decision-owner-1", "adaptation-1", request);

        assertThat(first).isEqualTo("adaptation-1");
        assertThat(replay).isEqualTo("adaptation-1");
        assertThat(database.dsl().fetchCount(VIDEOSHOTPLANVERSION)).isOne();
        assertThat(database.dsl().fetchCount(VIDEOADAPTATIONDECISIONCOMMAND)).isOne();
        assertThat(database.dsl().fetchCount(VIDEOSHOT)).isOne();
        assertThat(database.dsl().fetchCount(VIDEOSHOTPROMPTHEAD)).isOne();
        assertThat(database.dsl().selectFrom(REVIEWARTIFACT).fetchOne().getStatus())
                .isEqualTo(Reviewartifactstatus.applied);
        var response = adaptations.getDetail("decision-owner-1", "adaptation-1");
        assertThat(response.getHeadRevision()).isEqualTo(2);
        assertThat(response.getCurrentPlan().getScenes()).hasSize(1);
        assertThat(response.getCurrentPlan().getScenes().getFirst().getBeats().getFirst()
                        .getShots().getFirst().getSourceRanges().getFirst().getSourceText())
                .isEqualTo("甲😀");

        plan.getScenes().getFirst().setTitle("不同方案");
        assertCode(
                () -> decisions.confirmPlan("decision-owner-1", "adaptation-1", request),
                "VIDEO_ADAPTATION_DECISION_IDEMPOTENCY_CONFLICT");
    }

    @Test
    void 分集保存必须内容幂等且校验当前正式镜头范围() {
        var plan = fixture("decision-owner-2", "adaptation-2");
        decisions.confirmPlan(
                "decision-owner-2",
                "adaptation-2",
                new ConfirmAdaptationPlanRequest("confirm-request-0002", 1, 1, plan));
        String planId = database.dsl().select(VIDEOCHAPTERADAPTATIONHEAD.CURRENTSHOTPLANVERSIONID)
                .from(VIDEOCHAPTERADAPTATIONHEAD)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq("adaptation-2"))
                .fetchOne(VIDEOCHAPTERADAPTATIONHEAD.CURRENTSHOTPLANVERSIONID);
        var request = new SaveEpisodePlanRequest("episode-request-0001", 2, planId)
                .breakAfterShotIds(List.of());

        decisions.saveEpisodePlan("decision-owner-2", "adaptation-2", request);
        decisions.saveEpisodePlan("decision-owner-2", "adaptation-2", request);

        assertThat(database.dsl().fetchCount(VIDEOEPISODEPLANVERSION)).isOne();
        assertThat(adaptations.getDetail("decision-owner-2", "adaptation-2")
                        .getHeadRevision())
                .isEqualTo(3);
        String onlyShot = database.dsl().select(VIDEOSHOT.ID)
                .from(VIDEOSHOT)
                .where(VIDEOSHOT.PLANVERSIONID.eq(planId))
                .fetchOne(VIDEOSHOT.ID);
        var invalid = new SaveEpisodePlanRequest("episode-request-0002", 3, planId)
                .breakAfterShotIds(List.of(onlyShot));
        assertCode(
                () -> decisions.saveEpisodePlan(
                        "decision-owner-2", "adaptation-2", invalid),
                "VIDEO_EPISODE_BOUNDARY_INVALID");
    }

    @Test
    void 放弃候选只删除待审Artifact并推进Head版本() {
        fixture("decision-owner-3", "adaptation-3");

        decisions.discardCandidate(
                "decision-owner-3",
                "adaptation-3",
                new DiscardAdaptationCandidateRequest("discard-request-01", 1, 1));

        assertThat(database.dsl().fetchCount(REVIEWARTIFACT)).isZero();
        assertThat(adaptations.getDetail("decision-owner-3", "adaptation-3")
                        .getHeadRevision())
                .isEqualTo(2);
    }

    @Test
    void 保存提示词候选必须编译即梦文本并形成不可变版本() {
        var plan = fixture("decision-owner-4", "adaptation-4");
        decisions.confirmPlan(
                "decision-owner-4",
                "adaptation-4",
                new ConfirmAdaptationPlanRequest("confirm-request-0004", 1, 1, plan));
        String planId = database.dsl().select(VIDEOCHAPTERADAPTATIONHEAD.CURRENTSHOTPLANVERSIONID)
                .from(VIDEOCHAPTERADAPTATIONHEAD)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq("adaptation-4"))
                .fetchOne(VIDEOCHAPTERADAPTATIONHEAD.CURRENTSHOTPLANVERSIONID);
        String shotId = database.dsl().select(VIDEOSHOT.ID)
                .from(VIDEOSHOT)
                .where(VIDEOSHOT.PLANVERSIONID.eq(planId))
                .fetchOne(VIDEOSHOT.ID);
        String promptTaskId = "adaptation-4-prompt-task";
        String payload = VideoAdaptationTaskPayload.prompt(
                json,
                "adaptation-4",
                "project-adaptation-4",
                planId,
                "甲😀乙",
                plan.getSourceHash(),
                plan,
                List.of(),
                List.of("S01"),
                "16:9",
                "zh-CN",
                emptySettingSnapshot(),
                List.of(new VideoAdaptationTaskPayload.VisualReferenceBundle(
                        "S01", List.of())));
        database.dsl().insertInto(VIDEOADAPTATIONTASK)
                .set(VIDEOADAPTATIONTASK.ID, promptTaskId)
                .set(VIDEOADAPTATIONTASK.ADAPTATIONID, "adaptation-4")
                .set(VIDEOADAPTATIONTASK.PROJECTID, "project-adaptation-4")
                .set(VIDEOADAPTATIONTASK.NOVELID, "novel-adaptation-4")
                .set(VIDEOADAPTATIONTASK.BASESHOTPLANVERSIONID, planId)
                .set(VIDEOADAPTATIONTASK.JOBID, promptTaskId + "-job")
                .set(VIDEOADAPTATIONTASK.KIND, "shot_prompt")
                .set(VIDEOADAPTATIONTASK.WORKFLOW, "chapter_shot_prompt_v2")
                .set(VIDEOADAPTATIONTASK.PROVIDER, "deepseek")
                .set(VIDEOADAPTATIONTASK.STATUS, "completed")
                .set(VIDEOADAPTATIONTASK.IDEMPOTENCYKEY, promptTaskId + "-key")
                .set(VIDEOADAPTATIONTASK.REQUESTJSON, payload)
                .set(VIDEOADAPTATIONTASK.RESULTJSON, promptResult())
                .set(VIDEOADAPTATIONTASK.CHECKPOINTSTAGE, "none")
                .set(VIDEOADAPTATIONTASK.ATTEMPTCOUNT, 0)
                .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, INITIAL)
                .set(VIDEOADAPTATIONTASK.CREATEDAT, INITIAL.plusSeconds(1))
                .set(VIDEOADAPTATIONTASK.UPDATEDAT, INITIAL.plusSeconds(1))
                .set(VIDEOADAPTATIONTASK.COMPLETEDAT, INITIAL.plusSeconds(1))
                .execute();
        var request = new SaveShotPromptRequest("用户微调后的完整提示词", 1)
                .candidateTaskId(promptTaskId);

        decisions.savePrompt("decision-owner-4", "adaptation-4", shotId, request);
        decisions.savePrompt("decision-owner-4", "adaptation-4", shotId, request);

        assertThat(database.dsl().fetchCount(VIDEOSHOTPROMPTVERSION)).isOne();
        var version = database.dsl().selectFrom(VIDEOSHOTPROMPTVERSION).fetchOne();
        assertThat(version.getGeneratedtext())
                .isEqualTo(
                        "16:9 画幅，5 秒。林岚站在门前。她缓慢推门。"
                                + "表情与视线：警觉地看向门缝。摄影机：缓慢推近。"
                                + "声音：风声与门轴声。禁止：不要字幕。");
        assertThat(version.getCurrenttext()).isEqualTo("用户微调后的完整提示词");
        assertThat(database.dsl().selectFrom(VIDEOSHOTPROMPTHEAD).fetchOne().getRevision())
                .isEqualTo(2);
        assertThat(adaptations.getDetail("decision-owner-4", "adaptation-4")
                        .getPromptVersions())
                .singleElement()
                .satisfies(value -> {
                    assertThat(value.getGeneratedText()).isEqualTo(version.getGeneratedtext());
                    assertThat(value.getPromptEdited()).isTrue();
                });
    }

    private static cn.inkforge.contracts.api.ChapterAdaptationPlanCandidate fixture(
            String owner, String adaptationId) {
        String novelId = "novel-" + adaptationId;
        String projectId = "project-" + adaptationId;
        String taskId = adaptationId + "-task";
        String artifactId = adaptationId + "-artifact";
        var plan = candidate(adaptationId, "甲😀乙");
        database.dsl().insertInto(USER)
                .set(USER.ID, owner)
                .set(USER.USERNAME, owner)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
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
        database.dsl().insertInto(VIDEOCHAPTERADAPTATION)
                .set(VIDEOCHAPTERADAPTATION.ID, adaptationId)
                .set(VIDEOCHAPTERADAPTATION.PROJECTID, projectId)
                .set(VIDEOCHAPTERADAPTATION.NOVELID, novelId)
                .set(VIDEOCHAPTERADAPTATION.CHAPTERTITLE, "第一章")
                .set(VIDEOCHAPTERADAPTATION.CHAPTERUPDATEDAT, INITIAL)
                .set(VIDEOCHAPTERADAPTATION.SOURCETEXT, "甲😀乙")
                .set(VIDEOCHAPTERADAPTATION.SOURCEHASH, plan.getSourceHash())
                .set(VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS, "active")
                .set(VIDEOCHAPTERADAPTATION.CREATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(VIDEOCHAPTERADAPTATIONHEAD)
                .set(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID, adaptationId)
                .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, 1)
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
                .set(VIDEOADAPTATIONTASK.IDEMPOTENCYKEY, taskId + "-key")
                .set(VIDEOADAPTATIONTASK.REQUESTJSON, "{}")
                .set(VIDEOADAPTATIONTASK.RESULTJSON, "{}")
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
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.awaiting_user)
                .set(
                        REVIEWARTIFACT.PAYLOADJSON,
                        json.writeValueAsString(Map.of(
                                "applyTarget", Map.of(
                                        "type", "video_adaptation_plan",
                                        "adaptationId", adaptationId),
                                "candidate", VideoAdaptationPlans.candidateMap(plan))))
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.VIDEOADAPTATIONID, adaptationId)
                .set(REVIEWARTIFACT.VIDEOADAPTATIONTASKID, taskId)
                .set(REVIEWARTIFACT.CREATEDAT, INITIAL)
                .set(REVIEWARTIFACT.UPDATEDAT, INITIAL)
                .execute();
        return plan;
    }

    private static Map<String, Object> emptySettingSnapshot() {
        String fingerprint = CommandIdempotency.sha256("[]".getBytes(StandardCharsets.UTF_8));
        return Map.of("schemaVersion", "1.0", "fingerprint", fingerprint, "entries", List.of());
    }

    private static String promptResult() {
        Map<String, Object> specification = Map.of(
                "subjectAndScene", "林岚站在门前。",
                "visibleAction", "她缓慢推门。",
                "expressionAndGaze", "警觉地看向门缝。",
                "camera", "缓慢推近。",
                "audio", "风声与门轴声。",
                "negativeConstraints", List.of("不要字幕。"));
        Map<String, Object> prompt = Map.of(
                "shotKey", "S01",
                "spec", specification,
                "qualityWarnings", List.of());
        Map<String, Object> batch = Map.of(
                "schemaVersion", "shot_prompt_spec_batch_v2",
                "prompts", List.of(prompt));
        return json.writeValueAsString(Map.of(
                "eventId", "prompt-event-1",
                "workflow", "chapter_shot_prompt_v2",
                "promptBatch", batch));
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
