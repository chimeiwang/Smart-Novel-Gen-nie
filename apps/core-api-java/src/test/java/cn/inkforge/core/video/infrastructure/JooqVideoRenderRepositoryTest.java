package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTRENDERTASK;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.video.support.VideoAdaptationFixtures.candidate;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ConfirmAdaptationPlanRequest;
import cn.inkforge.contracts.api.ConfirmShotTakeRequest;
import cn.inkforge.contracts.api.EpisodeAudioClipInput;
import cn.inkforge.contracts.api.EpisodeEditClipInput;
import cn.inkforge.contracts.api.EpisodeSubtitleCueInput;
import cn.inkforge.contracts.api.RetryShotRenderRequest;
import cn.inkforge.contracts.api.RetryEpisodeExportRequest;
import cn.inkforge.contracts.api.SaveEpisodePlanRequest;
import cn.inkforge.contracts.api.SaveEpisodeEditVersionRequest;
import cn.inkforge.contracts.api.SaveEpisodeMixVersionRequest;
import cn.inkforge.contracts.api.SaveShotKeyframeVersionRequest;
import cn.inkforge.contracts.api.SaveShotPromptRequest;
import cn.inkforge.contracts.api.PostProductionReadinessResponse;
import cn.inkforge.contracts.api.SeedanceShotPromptSpec;
import cn.inkforge.contracts.api.ShotPromptSpecBatch;
import cn.inkforge.contracts.api.ShotPromptSpecCandidate;
import cn.inkforge.contracts.api.StartPromptRunRequest;
import cn.inkforge.contracts.api.StartShotPlanRunRequest;
import cn.inkforge.contracts.api.StartShotRenderRequest;
import cn.inkforge.contracts.api.StartEpisodeExportRequest;
import cn.inkforge.contracts.api.VideoAdaptationPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationPromptCompletionCallback;
import cn.inkforge.contracts.api.VideoRenderReadinessResponse;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.CompletedVideoTake;
import cn.inkforge.core.video.application.CompletedTakeFrameExtraction;
import cn.inkforge.core.video.application.CompletedEpisodeExport;
import cn.inkforge.core.video.application.StoredVideoAsset;
import java.nio.file.Path;
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
class JooqVideoRenderRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T05:00:00.123Z"), ZoneOffset.UTC);
    private static final String OWNER = "render-owner";
    private static final String NOVEL_ID = "render-novel";
    private static final String PROJECT_ID = "render-project";
    private static final String ADAPTATION_ID = "render-adaptation";
    private static final String SOURCE = "甲😀乙";

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_render_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqVideoAdaptationTaskStore adaptationTasks;
    private static JooqVideoAdaptationDecisionStore decisions;
    private static JooqVideoAdaptationRepository adaptations;
    private static JooqVideoRenderRepository renders;
    private static JooqVideoPostProductionRepository postProduction;

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
        adaptationTasks = new JooqVideoAdaptationTaskStore(
                database, ids, CLOCK, json, visualCanons, "render-test");
        decisions = new JooqVideoAdaptationDecisionStore(
                database, ids, CLOCK, json, visualCanons);
        adaptations = new JooqVideoAdaptationRepository(
                database, ids, CLOCK, json, visualCanons);
        renders = new JooqVideoRenderRepository(database, ids, CLOCK, json);
        postProduction = new JooqVideoPostProductionRepository(database, ids, CLOCK, json);
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
    void 渲染任务必须冻结正式输入归档不可变Take并以命令确认Head() {
        FormalShot formal = formalShot();
        var request = new StartShotRenderRequest("render-request-0001", 5, 2);

        var created = renders.createTask(
                OWNER,
                ADAPTATION_ID,
                formal.shotId(),
                request,
                "doubao-seedance-2-5-test",
                false);
        var replay = renders.createTask(
                OWNER,
                ADAPTATION_ID,
                formal.shotId(),
                request,
                "doubao-seedance-2-5-test",
                false);

        assertThat(replay.getId()).isEqualTo(created.getId());
        assertThat(created.getManifest().getPromptText()).isEqualTo("作者确认的正式即梦提示词");
        assertThat(created.getManifest().getReferences()).isEmpty();
        assertThat(created.getManifest().getKeyframes()).isEmpty();
        assertThat(created.getInputHash()).hasSize(64);

        var claim = renders.claimDue(3).getFirst();
        assertThat(claim.submission()).isTrue();
        assertThat(claim.manifest().getPromptVersionId())
                .isEqualTo(created.getPromptVersionId());
        renders.markSubmitted(created.getId(), "provider-task-1");
        renders.markQueryProgress(created.getId(), "running");
        assertThat(renders.beginArchiving(created.getId())).isTrue();
        renders.completeTake(
                created.getId(),
                new CompletedVideoTake(
                        created.getId(),
                        new StoredVideoAsset(
                                PROJECT_ID + "/" + created.getId() + ".mp4",
                                Path.of("/tmp/" + created.getId() + ".mp4"),
                                "video/mp4",
                                1_024,
                                "d".repeat(64)),
                        Map.of("resolution", "720p", "framesPerSecond", 24),
                        5_000));
        // 数据库已经完成但归档响应丢失时，重放不能创建第二个 Take。
        renders.completeTake(
                created.getId(),
                new CompletedVideoTake(
                        created.getId(),
                        new StoredVideoAsset(
                                PROJECT_ID + "/" + created.getId() + ".mp4",
                                Path.of("/tmp/" + created.getId() + ".mp4"),
                                "video/mp4",
                                1_024,
                                "d".repeat(64)),
                        Map.of("resolution", "720p"),
                        5_000));

        var workspace = renders.getWorkspace(
                OWNER,
                ADAPTATION_ID,
                new VideoRenderReadinessResponse(true, true, "model", false));
        assertThat(workspace.getTakes()).singleElement().satisfies(take -> {
            assertThat(take.getTakeNo()).isOne();
            assertThat(take.getAsset().getDuty().getValue()).isEqualTo("motion");
            assertThat(take.getAsset().getLockedAt()).isNotNull();
        });
        String takeId = workspace.getTakes().getFirst().getId();
        var confirmation = new ConfirmShotTakeRequest("take-request-00001", 1);
        var confirmed = renders.confirmTake(
                OWNER, ADAPTATION_ID, formal.shotId(), takeId, confirmation);
        var confirmedReplay = renders.confirmTake(
                OWNER, ADAPTATION_ID, formal.shotId(), takeId, confirmation);
        assertThat(confirmed.getStatus().getValue()).isEqualTo("succeeded");
        assertThat(confirmed.getResultingRevision()).isEqualTo(2);
        assertThat(confirmedReplay.getCommandId()).isEqualTo(confirmed.getCommandId());

        var conflict = renders.confirmTake(
                OWNER,
                ADAPTATION_ID,
                formal.shotId(),
                takeId,
                new ConfirmShotTakeRequest("take-request-00002", 1));
        assertThat(conflict.getStatus().getValue()).isEqualTo("conflict");
        assertThat(conflict.getErrorCode()).isEqualTo("VIDEO_TAKE_REVISION_CONFLICT");
        assertThat(renders.getTakeFile(OWNER, takeId).storageKey())
                .isEqualTo(PROJECT_ID + "/" + created.getId() + ".mp4");

        var retry = renders.retryTask(
                OWNER,
                created.getId(),
                new RetryShotRenderRequest("render-retry-00001"),
                false);
        assertThat(retry.getRetryOfTaskId()).isEqualTo(created.getId());
        assertThat(retry.getInputHash()).isEqualTo(created.getInputHash());
        assertThat(retry.getManifest()).isEqualTo(created.getManifest());
    }

    @Test
    void 提交中断恢复必须进入未知终态而不能自动重提供应商() {
        FormalShot formal = formalShot();
        var task = renders.createTask(
                OWNER,
                ADAPTATION_ID,
                formal.shotId(),
                new StartShotRenderRequest("render-request-0002", 5, 2),
                "doubao-seedance-2-5-test",
                false);
        assertThat(renders.claimDue(1)).hasSize(1);
        database.dsl().update(VIDEOSHOTRENDERTASK)
                .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, INITIAL)
                .where(VIDEOSHOTRENDERTASK.ID.eq(task.getId()))
                .execute();

        assertThat(renders.claimDue(1)).isEmpty();
        assertThat(renders.getTask(OWNER, task.getId()).getStatus().getValue())
                .isEqualTo("submission_unknown");
        assertThat(renders.getTask(OWNER, task.getId()).getLastErrorCode())
                .isEqualTo("SEEDANCE_SUBMISSION_RECOVERY_UNKNOWN");
    }

    @Test
    void 关键帧版本必须锁定可信图片且支持清除与幂等重放() {
        FormalShot formal = formalShot();
        database.dsl().insertInto(VIDEOASSET)
                .set(VIDEOASSET.ID, "keyframe-image")
                .set(VIDEOASSET.PROJECTID, PROJECT_ID)
                .set(VIDEOASSET.NAME, "林岚初始状态")
                .set(VIDEOASSET.MODALITY, "image")
                .set(VIDEOASSET.DUTY, "keyframe")
                .set(VIDEOASSET.STORAGEKEY, PROJECT_ID + "/keyframe-image.png")
                .set(VIDEOASSET.MIMETYPE, "image/png")
                .set(VIDEOASSET.BYTESIZE, 512L)
                .set(VIDEOASSET.SHA256, "a".repeat(64))
                .set(VIDEOASSET.SOURCEKIND, "user_upload")
                .set(VIDEOASSET.RIGHTSSTATUS, "confirmed")
                .set(VIDEOASSET.LOCKEDAT, INITIAL)
                .set(VIDEOASSET.CREATEDAT, INITIAL)
                .set(VIDEOASSET.UPDATEDAT, INITIAL)
                .execute();
        var request = new SaveShotKeyframeVersionRequest(
                        "keyframe-request-0001",
                        1,
                        SaveShotKeyframeVersionRequest.RoleEnum.INITIAL_STATE)
                .assetId("keyframe-image");

        var saved = postProduction.saveKeyframe(
                OWNER, ADAPTATION_ID, formal.shotId(), request);
        var replay = postProduction.saveKeyframe(
                OWNER, ADAPTATION_ID, formal.shotId(), request);
        assertThat(saved.getRevision()).isEqualTo(2);
        assertThat(replay.getCurrentVersion().getId())
                .isEqualTo(saved.getCurrentVersion().getId());
        assertThat(saved.getCurrentVersion().getAsset().getSha256())
                .isEqualTo("a".repeat(64));

        var cleared = postProduction.saveKeyframe(
                OWNER,
                ADAPTATION_ID,
                formal.shotId(),
                new SaveShotKeyframeVersionRequest(
                        "keyframe-request-0002",
                        2,
                        SaveShotKeyframeVersionRequest.RoleEnum.INITIAL_STATE));
        assertThat(cleared.getRevision()).isEqualTo(3);
        assertThat(cleared.getCurrentVersion().getSourceKind().getValue())
                .isEqualTo("cleared");
        assertThat(cleared.getHistory()).hasSize(2);
        var keyframeWorkspace = postProduction.getWorkspace(
                OWNER,
                ADAPTATION_ID,
                new PostProductionReadinessResponse(List.of(), true, true));
        assertThat(keyframeWorkspace.getKeyframeAssets())
                .extracting(asset -> asset.getId())
                .containsExactly("keyframe-image");
        assertThat(keyframeWorkspace.getShots())
                .singleElement()
                .satisfies(shot -> assertThat(shot.getHeads())
                        .filteredOn(head -> "initial_state".equals(head.getRole().getValue()))
                        .singleElement()
                        .satisfies(head -> {
                            assertThat(head.getCurrentVersion().getSourceKind().getValue())
                                    .isEqualTo("cleared");
                            assertThat(head.getHistory()).hasSize(2);
                        }));

        assertCode(
                () -> postProduction.saveKeyframe(
                        OWNER,
                        ADAPTATION_ID,
                        formal.shotId(),
                        new SaveShotKeyframeVersionRequest(
                                "keyframe-request-0003",
                                2,
                                SaveShotKeyframeVersionRequest.RoleEnum.INITIAL_STATE)),
                "VIDEO_KEYFRAME_REVISION_CONFLICT");
    }

    @Test
    void Take抽帧来源事实可重放并能作为关键帧版本的证据() {
        FormalShot formal = formalShot();
        String takeId = renderTake(formal, "frame-render-request-01");
        var source = postProduction.getTakeFrameSource(OWNER, takeId, 1_250);
        String requestHash = "e".repeat(64);
        var completed = new CompletedTakeFrameExtraction(
                OWNER,
                source,
                "frame-extracted-asset",
                "林岚推门中间帧",
                1_250,
                "frame-extract-request-01",
                requestHash,
                new StoredVideoAsset(
                        PROJECT_ID + "/frame-extracted-asset.png",
                        Path.of("/tmp/frame-extracted-asset.png"),
                        "image/png",
                        512,
                        "f".repeat(64)));

        var asset = postProduction.completeExtractedFrame(completed);
        var replay = postProduction.completeExtractedFrame(completed);
        assertThat(replay.getId()).isEqualTo(asset.getId());
        assertThat(postProduction.getExtractionReplay(
                                OWNER, "frame-extract-request-01", requestHash)
                        .getSha256())
                .isEqualTo("f".repeat(64));

        var keyframe = postProduction.saveKeyframe(
                OWNER,
                ADAPTATION_ID,
                formal.shotId(),
                new SaveShotKeyframeVersionRequest(
                                "frame-keyframe-request-01",
                                1,
                                SaveShotKeyframeVersionRequest.RoleEnum.END_STATE)
                        .assetId(asset.getId())
                        .sourceTakeId(takeId)
                        .sourceTimeMs(1_250));
        assertThat(keyframe.getCurrentVersion().getSourceKind().getValue())
                .isEqualTo("take_frame");
        assertThat(keyframe.getCurrentVersion().getSourceTakeId()).isEqualTo(takeId);
    }

    @Test
    void 粗剪与声音字幕必须保存不可变版本并校验素材范围() {
        FormalShot formal = formalShot();
        String takeId = renderTake(formal, "timeline-render-request-01");
        EpisodeEditClipInput clip = new EpisodeEditClipInput(4_000, formal.shotId())
                .takeId(takeId)
                .sourceInMs(500)
                .sourceOutMs(4_500);
        var editRequest = new SaveEpisodeEditVersionRequest(
                "edit-version-request-01", List.of(clip), 1);

        var edit = postProduction.saveEditVersion(
                OWNER, ADAPTATION_ID, 1, editRequest);
        var editReplay = postProduction.saveEditVersion(
                OWNER, ADAPTATION_ID, 1, editRequest);
        assertThat(edit.getRevision()).isEqualTo(2);
        assertThat(editReplay.getCurrentVersion().getId())
                .isEqualTo(edit.getCurrentVersion().getId());
        assertThat(postProduction.getEditVersion(
                                OWNER, edit.getCurrentVersion().getId())
                        .getClips())
                .singleElement()
                .satisfies(saved -> {
                    assertThat(saved.getTimelineStartMs()).isZero();
                    assertThat(saved.getSourceInMs()).isEqualTo(500);
                    assertThat(saved.getSourceOutMs()).isEqualTo(4_500);
                });

        database.dsl().insertInto(VIDEOASSET)
                .set(VIDEOASSET.ID, "dialogue-audio")
                .set(VIDEOASSET.PROJECTID, PROJECT_ID)
                .set(VIDEOASSET.NAME, "林岚对白")
                .set(VIDEOASSET.MODALITY, "audio")
                .set(VIDEOASSET.DUTY, "voice")
                .set(VIDEOASSET.STORAGEKEY, PROJECT_ID + "/dialogue-audio.wav")
                .set(VIDEOASSET.MIMETYPE, "audio/wav")
                .set(VIDEOASSET.BYTESIZE, 2_048L)
                .set(VIDEOASSET.DURATIONMS, 5_000)
                .set(VIDEOASSET.SHA256, "6".repeat(64))
                .set(VIDEOASSET.SOURCEKIND, "user_upload")
                .set(VIDEOASSET.RIGHTSSTATUS, "confirmed")
                .set(VIDEOASSET.LOCKEDAT, INITIAL)
                .set(VIDEOASSET.CREATEDAT, INITIAL)
                .set(VIDEOASSET.UPDATEDAT, INITIAL)
                .execute();
        EpisodeAudioClipInput audio = new EpisodeAudioClipInput(
                        "dialogue-audio",
                        3_000,
                        0,
                        EpisodeAudioClipInput.TrackKindEnum.DIALOGUE)
                .shotId(formal.shotId());
        EpisodeSubtitleCueInput subtitle = new EpisodeSubtitleCueInput(
                        2_500, 200, "门终于开了")
                .shotId(formal.shotId())
                .speaker("林岚");
        var mixRequest = new SaveEpisodeMixVersionRequest(
                        "mix-version-request-001",
                        edit.getCurrentVersion().getId(),
                        1)
                .audioClips(List.of(audio))
                .subtitleCues(List.of(subtitle));

        var mix = postProduction.saveMixVersion(
                OWNER, ADAPTATION_ID, 1, mixRequest);
        var mixReplay = postProduction.saveMixVersion(
                OWNER, ADAPTATION_ID, 1, mixRequest);
        assertThat(mix.getRevision()).isEqualTo(2);
        assertThat(mixReplay.getCurrentVersion().getId())
                .isEqualTo(mix.getCurrentVersion().getId());
        assertThat(postProduction.getMixVersion(
                                OWNER, mix.getCurrentVersion().getId())
                        .getAudioClips())
                .singleElement()
                .satisfies(saved -> {
                    assertThat(saved.getAsset().getId()).isEqualTo("dialogue-audio");
                    assertThat(saved.getTrackKind().getValue()).isEqualTo("dialogue");
                });
        assertThat(mix.getCurrentVersion().getSubtitleCues())
                .singleElement()
                .satisfies(saved -> {
                    assertThat(saved.getSpeaker()).isEqualTo("林岚");
                    assertThat(saved.getText()).isEqualTo("门终于开了");
                });

        var exportRequest = new StartEpisodeExportRequest(
                "export-task-request-01",
                edit.getCurrentVersion().getId(),
                mix.getCurrentVersion().getId());
        var exportTask = postProduction.createExportTask(
                OWNER, ADAPTATION_ID, 1, exportRequest);
        var exportReplay = postProduction.createExportTask(
                OWNER, ADAPTATION_ID, 1, exportRequest);
        assertThat(exportReplay.getId()).isEqualTo(exportTask.getId());
        assertThat(exportTask.getInputHash()).hasSize(64);
        var exportClaim = postProduction.claimDueExportTasks(1).getFirst();
        assertThat(exportClaim.manifest().videoClips())
                .singleElement()
                .satisfies(frozen -> {
                    assertThat(frozen.takeId()).isEqualTo(takeId);
                    assertThat(frozen.asset().sha256()).isEqualTo("d".repeat(64));
                });
        assertThat(exportClaim.manifest().audioClips().getFirst().asset().sha256())
                .isEqualTo("6".repeat(64));
        assertThat(exportClaim.manifest().subtitleCues().getFirst().text())
                .isEqualTo("门终于开了");
        var completedExport = postProduction.completeExport(new CompletedEpisodeExport(
                exportTask.getId(),
                "export_" + exportTask.getId(),
                new StoredVideoAsset(
                        PROJECT_ID + "/export_" + exportTask.getId() + ".mp4",
                        Path.of("/tmp/export_" + exportTask.getId() + ".mp4"),
                        "video/mp4",
                        8_192,
                        "9".repeat(64)),
                4_000));
        assertThat(completedExport.getStatus().getValue()).isEqualTo("succeeded");
        assertThat(completedExport.getExport().getAsset().getContentUrl())
                .startsWith("/api/v1/video/exports/");
        assertThat(postProduction.getExportFile(
                                OWNER, completedExport.getExport().getId())
                        .storageKey())
                .isEqualTo(PROJECT_ID + "/export_" + exportTask.getId() + ".mp4");

        var failedTask = postProduction.createExportTask(
                OWNER,
                ADAPTATION_ID,
                1,
                new StartEpisodeExportRequest(
                        "export-task-request-02",
                        edit.getCurrentVersion().getId(),
                        mix.getCurrentVersion().getId()));
        postProduction.claimDueExportTasks(1);
        assertThat(postProduction.failExport(
                        failedTask.getId(),
                        "VIDEO_EPISODE_EXPORT_FAILED",
                        "测试失败"))
                .isTrue();
        var retried = postProduction.retryExportTask(
                OWNER,
                failedTask.getId(),
                new RetryEpisodeExportRequest("export-retry-request-01"));
        assertThat(retried.getRetryOfTaskId()).isEqualTo(failedTask.getId());
        assertThat(retried.getInputHash()).isEqualTo(failedTask.getInputHash());

        var workspace = postProduction.getWorkspace(
                OWNER,
                ADAPTATION_ID,
                new PostProductionReadinessResponse(List.of(), true, true));
        assertThat(workspace.getAudioAssets())
                .extracting(asset -> asset.getId())
                .containsExactly("dialogue-audio");
        assertThat(workspace.getContinuityIssues())
                .extracting(issue -> issue.getCode())
                .contains("VIDEO_CONTINUITY_HIGH_RISK_WITHOUT_KEYFRAME");
        assertThat(workspace.getEpisodes())
                .singleElement()
                .satisfies(episode -> {
                    assertThat(episode.getDefaultClips().getFirst().getTakeId()).isNull();
                    assertThat(episode.getEditHead().getCurrentVersion().getId())
                            .isEqualTo(edit.getCurrentVersion().getId());
                    assertThat(episode.getMixHead().getCurrentVersion().getId())
                            .isEqualTo(mix.getCurrentVersion().getId());
                    assertThat(episode.getExportTasks()).hasSize(3);
                    assertThat(episode.getSuggestedSubtitleCues()).isEmpty();
                });

        assertCode(
                () -> postProduction.saveEditVersion(
                        OWNER,
                        ADAPTATION_ID,
                        1,
                        new SaveEpisodeEditVersionRequest(
                                "edit-version-invalid-01",
                                List.of(new EpisodeEditClipInput(3_000, formal.shotId())
                                        .takeId(takeId)
                                        .sourceInMs(0)
                                        .sourceOutMs(4_000)),
                                2)),
                "VIDEO_EDIT_DURATION_MISMATCH");
    }

    private static FormalShot formalShot() {
        fixture();
        var plan = candidate(ADAPTATION_ID, SOURCE);
        var planTask = adaptationTasks.createPlanTask(
                OWNER, ADAPTATION_ID, new StartShotPlanRunRequest("plan-render-000001"));
        var planTaskResponse = adaptationTasks.getTask(OWNER, planTask.taskId());
        adaptationTasks.completePlan(new VideoAdaptationPlanCompletionCallback(
                ADAPTATION_ID,
                plan,
                "plan-render-event-1",
                planTaskResponse.getJobId(),
                NOVEL_ID,
                PROJECT_ID,
                "1.0",
                planTaskResponse.getId(),
                planTaskResponse.getId()));
        decisions.confirmPlan(
                OWNER,
                ADAPTATION_ID,
                new ConfirmAdaptationPlanRequest("confirm-render-0001", 1, 1, plan));
        var approved = adaptations.getDetail(OWNER, ADAPTATION_ID);
        String planId = approved.getCurrentPlan().getPlanVersionId();
        String shotId = approved.getCurrentPlan().getScenes().getFirst().getBeats().getFirst()
                .getShots().getFirst().getId();
        var promptTask = adaptationTasks.createPromptTask(
                OWNER,
                ADAPTATION_ID,
                new StartPromptRunRequest("prompt-render-0001", 2, planId));
        var promptTaskResponse = adaptationTasks.getTask(OWNER, promptTask.taskId());
        adaptationTasks.completePrompts(new VideoAdaptationPromptCompletionCallback(
                ADAPTATION_ID,
                "prompt-render-event-1",
                promptTaskResponse.getJobId(),
                NOVEL_ID,
                PROJECT_ID,
                promptBatch(),
                "1.0",
                promptTaskResponse.getId(),
                promptTaskResponse.getId()));
        decisions.savePrompt(
                OWNER,
                ADAPTATION_ID,
                shotId,
                new SaveShotPromptRequest("作者确认的正式即梦提示词", 1)
                        .candidateTaskId(promptTaskResponse.getId()));
        decisions.saveEpisodePlan(
                OWNER,
                ADAPTATION_ID,
                new SaveEpisodePlanRequest(
                                "episode-render-0001", approved.getHeadRevision(), planId)
                        .breakAfterShotIds(List.of()));
        return new FormalShot(planId, shotId);
    }

    private static String renderTake(FormalShot formal, String clientRequestId) {
        var task = renders.createTask(
                OWNER,
                ADAPTATION_ID,
                formal.shotId(),
                new StartShotRenderRequest(clientRequestId, 5, 2),
                "doubao-seedance-2-5-test",
                false);
        renders.claimDue(1);
        renders.markSubmitted(task.getId(), "provider-" + clientRequestId);
        assertThat(renders.beginArchiving(task.getId())).isTrue();
        renders.completeTake(
                task.getId(),
                new CompletedVideoTake(
                        task.getId(),
                        new StoredVideoAsset(
                                PROJECT_ID + "/" + task.getId() + ".mp4",
                                Path.of("/tmp/" + task.getId() + ".mp4"),
                                "video/mp4",
                                1_024,
                                "d".repeat(64)),
                        Map.of("resolution", "720p"),
                        5_000));
        return renders.getWorkspace(
                        OWNER,
                        ADAPTATION_ID,
                        new VideoRenderReadinessResponse(true, true, "model", false))
                .getTakes()
                .getFirst()
                .getId();
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

    private static ShotPromptSpecBatch promptBatch() {
        var spec = new SeedanceShotPromptSpec(
                "风声", "缓慢推近", "林岚站在门前", "她缓慢推门");
        return new ShotPromptSpecBatch(List.of(new ShotPromptSpecCandidate("S01", spec)));
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

    private record FormalShot(String planId, String shotId) {}
}
