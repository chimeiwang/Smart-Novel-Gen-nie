package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.video.application.ArchivedVideoFrame;
import cn.inkforge.core.video.application.CompletedEpisodeVideoTake;
import cn.inkforge.core.video.application.StoredVideoAsset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** PostgreSQL 证明独立剧集渲染的幂等、分支隔离、未知提交和唯一 Take 约束。 */
@Testcontainers
class JooqVideoEpisodeRenderRepositoryTest {
    private static final String MODEL = "doubao-seedance-2-5-260628";
    private static final JsonMapper JSON = JsonMapper.builder().findAndAddModules().build();

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_production_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqVideoEpisodeRepository episodes;
    private static JooqVideoEpisodeProductionRepository production;
    private static JooqVideoEpisodeProductionRepository liveProduction;
    private static JooqVideoEpisodeRenderRepository renders;
    private static JooqVideoRenderRepository legacyRenders;
    private String userId;
    private String novelId;
    private String projectId;
    private String canonVersionId;
    private String canonAssetId;
    private String keyframeAssetId;

    @BeforeAll
    static void setupDatabase() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/base.sql");
        assertThat(sqlFile("/tmp/base.sql").getExitCode()).isZero();
        Path migration =
                Path.of("../../scripts/migrations/20260910_video_production_baseline_domain.sql");
        if (!Files.exists(migration)) {
            migration = Path.of("scripts/migrations/20260910_video_production_baseline_domain.sql");
        }
        POSTGRES.copyFileToContainer(
                MountableFile.forHostPath(migration.toAbsolutePath()), "/tmp/p2.sql");
        var migrated = sqlFile("/tmp/p2.sql");
        assertThat(migrated.getExitCode()).as(migrated.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(
                "postgresql://inkforge:test-only-password@"
                        + POSTGRES.getHost()
                        + ":"
                        + POSTGRES.getFirstMappedPort()
                        + "/"
                        + POSTGRES.getDatabaseName()));
        Clock clock = Clock.systemUTC();
        var ids = new CuidV1Generator(clock);
        episodes = new JooqVideoEpisodeRepository(database, ids, clock, JSON);
        production = new JooqVideoEpisodeProductionRepository(
                database,
                ids,
                clock,
                JSON,
                MODEL,
                "simulated",
                false,
                false,
                true);
        liveProduction = new JooqVideoEpisodeProductionRepository(
                database,
                ids,
                clock,
                JSON,
                MODEL,
                "live",
                true,
                true,
                true);
        renders = new JooqVideoEpisodeRenderRepository(database, ids, clock, JSON);
        legacyRenders = new JooqVideoRenderRepository(database, ids, clock, JSON);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @BeforeEach
    void fixture() {
        database.dsl().execute("TRUNCATE TABLE \"User\" CASCADE");
        userId = "owner-" + UUID.randomUUID();
        novelId = "novel-" + UUID.randomUUID();
        projectId = "project-" + UUID.randomUUID();
        canonVersionId = "canon-version-" + UUID.randomUUID();
        String characterId = "character-" + UUID.randomUUID();
        String assetId = "asset-" + UUID.randomUUID();
        canonAssetId = assetId;
        keyframeAssetId = null;
        String canonId = "canon-" + UUID.randomUUID();
        database.dsl().execute(
                "INSERT INTO \"User\"(id,username,\"passwordHash\",\"updatedAt\")"
                        + " VALUES (?,?,?,CURRENT_TIMESTAMP)",
                userId,
                userId,
                "test");
        database.dsl().execute(
                "INSERT INTO \"Novel\"(id,\"userId\",name,\"updatedAt\")"
                        + " VALUES (?,?,?,CURRENT_TIMESTAMP)",
                novelId,
                userId,
                "雨夜故事");
        database.dsl().execute(
                "INSERT INTO \"WritingBible\""
                        + " (id,\"novelId\",\"storyLengthProfile\",\"updatedAt\")"
                        + " VALUES (?,?,'long_serial',CURRENT_TIMESTAMP)",
                "bible-" + UUID.randomUUID(),
                novelId);
        database.dsl().execute(
                "INSERT INTO \"VideoProject\""
                        + " (id,\"novelId\",title,mode,status,\"targetAspectRatio\",\"targetLanguage\",provider,revision,\"updatedAt\")"
                        + " VALUES (?,?,'短剧','series','draft','16:9','zh-CN','seedance_2_5',1,CURRENT_TIMESTAMP)",
                projectId,
                novelId);
        database.dsl().execute(
                "INSERT INTO \"Character\"(id,\"novelId\",name,\"updatedAt\")"
                        + " VALUES (?,?,?,CURRENT_TIMESTAMP)",
                characterId,
                novelId,
                "林岚");
        database.dsl().execute(
                "INSERT INTO \"VideoAsset\""
                        + " (id,\"projectId\",name,modality,duty,\"storageKey\",\"mimeType\",\"byteSize\",sha256,\"sourceKind\",\"rightsStatus\",\"lockedAt\",\"updatedAt\")"
                        + " VALUES (?,?,'林岚定妆','image','identity',?,'image/png',128,?,'user_upload','confirmed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                assetId,
                projectId,
                projectId + "/canon.png",
                "a".repeat(64));
        database.dsl().execute(
                "INSERT INTO \"VideoVisualCanon\""
                        + " (id,\"projectId\",\"novelId\",\"settingKind\",\"settingId\",\"settingName\",\"variantKey\",duty,label,revision,\"updatedAt\")"
                        + " VALUES (?,?,?,'character',?,'林岚','default','identity','林岚定妆',1,CURRENT_TIMESTAMP)",
                canonId,
                projectId,
                novelId,
                characterId);
        database.dsl().execute(
                "INSERT INTO \"VideoVisualCanonVersion\""
                        + " (id,\"canonId\",\"projectId\",\"novelId\",\"versionNo\",\"assetId\",label,\"settingName\",\"includeFeaturesJson\",\"excludeFeaturesJson\",\"defaultStrength\",\"contentHash\",\"approvedByUserId\")"
                        + " VALUES (?,?,?,?,1,?,'林岚定妆','林岚','[]','[]',80,?,?)",
                canonVersionId,
                canonId,
                projectId,
                novelId,
                assetId,
                "b".repeat(64),
                userId);
        database.dsl().execute(
                "UPDATE \"VideoVisualCanon\" SET \"currentVersionId\"=? WHERE id=?",
                canonVersionId,
                canonId);
    }

    @Test
    void 同请求重放且旧协调器不会领取Episode任务() {
        Baseline fixture = baseline();
        ObjectNode request = object("clientRequestId", key(), "feeConfirmed", false);

        ObjectNode created = renders.createTask(
                userId,
                fixture.episodeId(),
                fixture.baselineId(),
                fixture.shotId(),
                request,
                "simulated",
                false);
        ObjectNode replay = renders.createTask(
                userId,
                fixture.episodeId(),
                fixture.baselineId(),
                fixture.shotId(),
                request,
                "simulated",
                false);

        assertThat(replay.path("id").asText()).isEqualTo(created.path("id").asText());
        assertThat(created.path("inputSnapshot")).isEqualTo(fixture.inputSnapshot());
        assertThat(legacyRenders.claimDue(10)).isEmpty();
        assertThat(renders.claimDue(10))
                .singleElement()
                .satisfies(claim -> {
                    assertThat(claim.submission()).isTrue();
                    assertThat(claim.episodeId()).isEqualTo(fixture.episodeId());
                    assertThat(claim.input().prompt())
                            .contains("参考图使用规则")
                            .endsWith("交出信件");
                });
    }

    @Test
    void 冻结权利声明被篡改时拒绝创建任务() {
        Baseline fixture = baseline();
        ObjectNode snapshot = (ObjectNode) fixture.inputSnapshot().deepCopy();
        JsonNode reference = snapshot.path("references").get(0);
        assertThat(reference.path("rightsStatus").asText()).isEqualTo("confirmed");
        assertThat(reference.path("lockedAt").asText()).endsWith("Z");
        ((ObjectNode) reference).put("rightsStatus", "unconfirmed");
        replaceSnapshot(fixture, snapshot);

        assertCode(
                () ->
                        renders.createTask(
                                userId,
                                fixture.episodeId(),
                                fixture.baselineId(),
                                fixture.shotId(),
                                object("clientRequestId", key(), "feeConfirmed", false),
                                "simulated",
                                false),
                "VIDEO_RENDER_REFERENCE_INVALID");
    }

    @Test
    void 视觉参考撤权和关键帧锁定时间变化均拒绝创建任务() {
        Baseline withdrawn = baseline();
        database.dsl().execute(
                "UPDATE \"VideoAsset\" SET \"rightsStatus\"='unconfirmed' WHERE id=?",
                canonAssetId);
        assertCode(
                () ->
                        renders.createTask(
                                userId,
                                withdrawn.episodeId(),
                                withdrawn.baselineId(),
                                withdrawn.shotId(),
                                object("clientRequestId", key(), "feeConfirmed", false),
                                "simulated",
                                false),
                "VIDEO_RENDER_REFERENCE_CHANGED");

        database.dsl().execute(
                "UPDATE \"VideoAsset\" SET \"rightsStatus\"='confirmed' WHERE id=?",
                canonAssetId);
        Baseline keyframed = baselineWithKeyframe();
        JsonNode keyframe = keyframed.inputSnapshot().path("keyframes").get(0);
        assertThat(keyframe.path("rightsStatus").asText()).isEqualTo("confirmed");
        assertThat(keyframe.path("lockedAt").asText()).endsWith("Z");
        database.dsl().execute(
                "UPDATE \"VideoAsset\" SET \"lockedAt\"=\"lockedAt\" + INTERVAL '1 second'"
                        + " WHERE id=?",
                keyframeAssetId);
        assertCode(
                () ->
                        renders.createTask(
                                userId,
                                keyframed.episodeId(),
                                keyframed.baselineId(),
                                keyframed.shotId(),
                                object("clientRequestId", key(), "feeConfirmed", false),
                                "simulated",
                                false),
                "VIDEO_RENDER_KEYFRAME_CHANGED");
    }

    @Test
    void 旧模拟基线仍可读取但旧live基线关闭失败() {
        Baseline simulated = baseline();
        ObjectNode legacySimulated = legacy11(simulated.inputSnapshot());
        replaceSnapshot(simulated, legacySimulated);
        assertThat(
                        renders.createTask(
                                        userId,
                                        simulated.episodeId(),
                                        simulated.baselineId(),
                                        simulated.shotId(),
                                        object("clientRequestId", key(), "feeConfirmed", false),
                                        "simulated",
                                        false)
                                .path("status")
                                .asText())
                .isEqualTo("pending");

        Baseline live = liveBaseline();
        ObjectNode legacyLive = legacy11(live.inputSnapshot());
        replaceSnapshot(live, legacyLive);
        assertCode(
                () ->
                        renders.createTask(
                                userId,
                                live.episodeId(),
                                live.baselineId(),
                                live.shotId(),
                                object("clientRequestId", key(), "feeConfirmed", true),
                                "live",
                                true),
                "VIDEO_RENDER_RIGHTS_SNAPSHOT_REQUIRED");
    }

    @Test
    void 提交未知阻止普通重试和跨基线同镜新建() {
        Baseline fixture = baseline();
        ObjectNode task = renders.createTask(
                userId,
                fixture.episodeId(),
                fixture.baselineId(),
                fixture.shotId(),
                object("clientRequestId", key(), "feeConfirmed", false),
                "simulated",
                false);
        assertThat(renders.claimDue(1)).hasSize(1);
        database.dsl().execute(
                "UPDATE \"VideoShotRenderTask\" SET \"nextAttemptAt\"=? WHERE id=?",
                LocalDateTime.parse("2000-01-01T00:00:00"),
                task.path("id").asText());

        assertThat(renders.claimDue(1)).isEmpty();
        assertThat(renders.getTask(userId, fixture.episodeId(), task.path("id").asText())
                        .path("status")
                        .asText())
                .isEqualTo("submission_unknown");
        assertCode(
                () -> renders.retryTask(
                        userId,
                        fixture.episodeId(),
                        task.path("id").asText(),
                        object("clientRequestId", key(), "feeConfirmed", false),
                        "simulated",
                        false),
                "VIDEO_RENDER_SUBMISSION_UNRESOLVED");

        Baseline next = nextBaseline(fixture);
        assertThat(next.shotId()).isEqualTo(fixture.shotId());
        assertCode(
                () -> renders.createTask(
                        userId,
                        next.episodeId(),
                        next.baselineId(),
                        next.shotId(),
                        object("clientRequestId", key(), "feeConfirmed", false),
                        "simulated",
                        false),
                "VIDEO_RENDER_SUBMISSION_UNRESOLVED");
        assertThat(database.dsl()
                        .fetchOne("SELECT count(*) n FROM \"VideoShotRenderTask\"")
                        .get("n", Integer.class))
                .isEqualTo(1);
    }

    @Test
    void 归档失败恢复原任务且成功只创建唯一Take和受控尾帧() {
        Baseline fixture = baseline();
        ObjectNode task = renders.createTask(
                userId,
                fixture.episodeId(),
                fixture.baselineId(),
                fixture.shotId(),
                object("clientRequestId", key(), "feeConfirmed", false),
                "simulated",
                false);
        String taskId = task.path("id").asText();
        renders.claimDue(1);
        renders.markSubmitted(taskId, "simulated-" + taskId);
        assertThat(renders.beginArchiving(taskId)).isTrue();
        assertThat(renders.retryArchiving(taskId, "模拟磁盘暂时不可写")).isTrue();
        database.dsl().execute(
                "UPDATE \"VideoShotRenderTask\" SET \"nextAttemptAt\"=? WHERE id=?",
                LocalDateTime.parse("2000-01-01T00:00:00"),
                taskId);

        var restored = new JooqVideoEpisodeRenderRepository(
                database, new CuidV1Generator(Clock.systemUTC()), Clock.systemUTC(), JSON);
        assertThat(restored.claimDue(1))
                .singleElement()
                .satisfies(claim -> {
                    assertThat(claim.submission()).isFalse();
                    assertThat(claim.providerTaskId()).isEqualTo("simulated-" + taskId);
                    assertThat(claim.taskId()).isEqualTo(taskId);
                });
        assertThat(restored.beginArchiving(taskId)).isTrue();
        String frameId = taskId + "-last-frame";
        ArchivedVideoFrame frame = new ArchivedVideoFrame(
                frameId,
                new StoredVideoAsset(
                        projectId + "/" + frameId + ".png",
                        Path.of("/tmp/" + frameId + ".png"),
                        "image/png",
                        512,
                        "e".repeat(64)));
        Map<String, Object> metadata = Map.of(
                "mediaKind",
                "simulated_placeholder",
                "executionMode",
                "simulated",
                "simulated",
                true,
                "usage",
                Map.of(),
                "lastFrame",
                Map.of(
                        "assetId", frameId,
                        "sha256", "e".repeat(64),
                        "mimeType", "image/png",
                        "byteSize", 512));
        CompletedEpisodeVideoTake completed = new CompletedEpisodeVideoTake(
                taskId,
                new StoredVideoAsset(
                        projectId + "/" + taskId + ".mp4",
                        Path.of("/tmp/" + taskId + ".mp4"),
                        "video/mp4",
                        4_096,
                        "d".repeat(64)),
                metadata,
                4_000,
                frame);
        // 这里显式用带尾帧的模拟完成输入验证数据库原子性；协调器会拒绝模拟供应商返回尾帧。
        assertThatThrownBy(() -> restored.completeTake(taskId, completed))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("模拟 Take");

        CompletedEpisodeVideoTake withoutFrame = new CompletedEpisodeVideoTake(
                taskId,
                completed.stored(),
                Map.of(
                        "mediaKind", "simulated_placeholder",
                        "executionMode", "simulated",
                        "simulated", true,
                        "usage", Map.of()),
                4_000,
                null);
        restored.completeTake(taskId, withoutFrame);
        restored.completeTake(taskId, withoutFrame);
        var facts = database.dsl().fetchOne(
                """
                SELECT count(*) OVER () "takeCount",take."lastFrameAssetId",asset."projectId",
                       asset."sourceKind",take."adaptationId",take."shotPlanVersionId"
                FROM "VideoShotTake" take
                JOIN "VideoAsset" asset ON asset.id=take."assetId"
                WHERE take."taskId"=?
                """,
                taskId);
        assertThat(facts.get("takeCount", Integer.class)).isEqualTo(1);
        assertThat(facts.get("lastFrameAssetId", String.class)).isNull();
        assertThat(facts.get("projectId", String.class)).isEqualTo(projectId);
        assertThat(facts.get("sourceKind", String.class)).isEqualTo("virtual");
        assertThat(facts.get("adaptationId", String.class)).isNull();
        assertThat(facts.get("shotPlanVersionId", String.class)).isNull();

        // 真实尾帧关系另以同一仓储完成路径验证 FK；将冻结模式改为 live 会破坏 inputHash，故复制一条 live 基线。
        Baseline live = liveBaseline();
        ObjectNode liveTask = renders.createTask(
                userId,
                live.episodeId(),
                live.baselineId(),
                live.shotId(),
                object("clientRequestId", key(), "feeConfirmed", true),
                "live",
                true);
        String liveTaskId = liveTask.path("id").asText();
        renders.claimDue(1);
        renders.markSubmitted(liveTaskId, "provider-" + liveTaskId);
        assertThat(renders.beginArchiving(liveTaskId)).isTrue();
        String liveFrameId = liveTaskId + "-last-frame";
        ArchivedVideoFrame liveFrame = new ArchivedVideoFrame(
                liveFrameId,
                new StoredVideoAsset(
                        projectId + "/" + liveFrameId + ".png",
                        Path.of("/tmp/" + liveFrameId + ".png"),
                        "image/png",
                        512,
                        "f".repeat(64)));
        CompletedEpisodeVideoTake liveCompleted = new CompletedEpisodeVideoTake(
                liveTaskId,
                new StoredVideoAsset(
                        projectId + "/" + liveTaskId + ".mp4",
                        Path.of("/tmp/" + liveTaskId + ".mp4"),
                        "video/mp4",
                        4_096,
                        "c".repeat(64)),
                Map.of(
                        "mediaKind", "provider_media",
                        "executionMode", "live",
                        "simulated", false,
                        "usage", Map.of("completion_tokens", 140, "total_tokens", 140),
                        "lastFrame", Map.of(
                                "assetId", liveFrameId,
                                "sha256", "f".repeat(64),
                                "mimeType", "image/png",
                                "byteSize", 512)),
                4_000,
                liveFrame);
        renders.completeTake(liveTaskId, liveCompleted);
        renders.completeTake(liveTaskId, liveCompleted);
        var liveFacts = database.dsl().fetchOne(
                """
                SELECT take."lastFrameAssetId",frame."projectId",frame.modality,frame.duty,
                       take."providerMetadataJson",
                       (SELECT count(*) FROM "VideoShotTake" WHERE "taskId"=?) "takeCount"
                FROM "VideoShotTake" take
                JOIN "VideoAsset" frame ON frame.id=take."lastFrameAssetId"
                WHERE take."taskId"=?
                """,
                liveTaskId,
                liveTaskId);
        assertThat(liveFacts.get("takeCount", Integer.class)).isEqualTo(1);
        assertThat(liveFacts.get("lastFrameAssetId", String.class)).isEqualTo(liveFrameId);
        assertThat(liveFacts.get("projectId", String.class)).isEqualTo(projectId);
        assertThat(liveFacts.get("modality", String.class)).isEqualTo("image");
        assertThat(liveFacts.get("duty", String.class)).isEqualTo("keyframe");
        JsonNode persisted = JSON.readTree(liveFacts.get("providerMetadataJson", String.class));
        assertThat(persisted.path("usage").path("completion_tokens").asInt()).isEqualTo(140);
        assertThat(persisted.has("lastFrameUrl")).isFalse();
    }

    private Baseline baseline() {
        return baseline("simulated", false, false);
    }

    private Baseline baselineWithKeyframe() {
        return baseline("simulated", false, true);
    }

    private Baseline liveBaseline() {
        return baseline("live", true, false);
    }

    private Baseline nextBaseline(Baseline previous) {
        ObjectNode response = production.createProductionBaseline(
                userId,
                previous.episodeId(),
                object(
                        "clientRequestId", key(),
                        "expectedEpisodeRevision", 4,
                        "expectedProductionRevision", 2,
                        "basedOnBaselineId", previous.baselineId(),
                        "scriptVersionId", previous.scriptVersionId(),
                        "storyboardVersionId", previous.storyboardVersionId(),
                        "shotAdoptions", List.of()));
        JsonNode shot = response.path("shots").get(0);
        return new Baseline(
                previous.episodeId(),
                response.path("id").asText(),
                previous.scriptVersionId(),
                previous.storyboardVersionId(),
                shot.path("shotId").asText(),
                shot.path("inputSnapshot"));
    }

    private Baseline baseline(String mode, boolean feeConfirmed, boolean withKeyframe) {
        JooqVideoEpisodeProductionRepository selectedProduction =
                "live".equals(mode) ? liveProduction : production;
        String episodeId = episodes.create(
                        userId,
                        projectId,
                        object("clientRequestId", key(), "title", "雨夜交信"))
                .path("id")
                .asText();
        ObjectNode savedScript = episodes.saveDraft(
                userId,
                episodeId,
                object(
                        "clientRequestId", key(),
                        "expectedRevision", 1,
                        "sourceSetVersionId", null,
                        "baseScriptVersionId", null,
                        "document", scriptDocument()));
        ObjectNode scriptConfirmation = episodes.prepareConfirmation(
                userId,
                episodeId,
                object(
                        "clientRequestId", key(),
                        "expectedDraftRevision", 2,
                        "expectedEpisodeRevision", 1));
        ObjectNode scriptVersion = episodes.approveConfirmation(
                userId,
                episodeId,
                scriptConfirmation.path("artifactId").asText(),
                object(
                        "clientRequestId", key(),
                        "expectedArtifactRevision", 1,
                        "expectedDraftRevision", 2,
                        "expectedEpisodeRevision", 1,
                        "confirmationHash", scriptConfirmation.path("confirmationHash").asText()));
        String sceneId = savedScript.path("document").path("scenes").get(0).path("id").asText();
        ObjectNode storyboard = storyboard(sceneId, mode, feeConfirmed);
        ObjectNode savedStoryboard = selectedProduction.saveStoryboardDraft(
                userId,
                episodeId,
                object(
                        "clientRequestId", key(),
                        "expectedRevision", 1,
                        "scriptVersionId", scriptVersion.path("id").asText(),
                        "baseStoryboardVersionId", null,
                        "document", storyboard));
        ObjectNode storyboardConfirmation = selectedProduction.prepareStoryboardConfirmation(
                userId,
                episodeId,
                object(
                        "clientRequestId", key(),
                        "expectedDraftRevision", 2,
                        "expectedEpisodeRevision", 2));
        ObjectNode storyboardVersion = selectedProduction.approveStoryboardConfirmation(
                userId,
                episodeId,
                storyboardConfirmation.path("artifactId").asText(),
                object(
                        "clientRequestId", key(),
                        "expectedArtifactRevision", 1,
                        "expectedDraftRevision", 2,
                        "expectedEpisodeRevision", 2,
                        "confirmationHash",
                        storyboardConfirmation.path("confirmationHash").asText()));
        List<ObjectNode> keyframes = List.of();
        if (withKeyframe) {
            keyframeAssetId = "keyframe-asset-" + UUID.randomUUID();
            database.dsl().execute(
                    "INSERT INTO \"VideoAsset\""
                            + " (id,\"projectId\",name,modality,duty,\"storageKey\",\"mimeType\",\"byteSize\",sha256,\"sourceKind\",\"rightsStatus\",\"lockedAt\",\"updatedAt\")"
                            + " VALUES (?,?,'起始关键帧','image','keyframe',?,'image/png',128,?,'user_upload','confirmed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                    keyframeAssetId,
                    projectId,
                    projectId + "/keyframe.png",
                    "f".repeat(64));
            keyframes =
                    List.of(
                            object(
                                    "shotVersionId",
                                    storyboardVersion.path("shots").get(0).path("id").asText(),
                                    "role",
                                    "initial_state",
                                    "assetId",
                                    keyframeAssetId));
        }
        ObjectNode baseline = selectedProduction.createProductionBaseline(
                userId,
                episodeId,
                object(
                        "clientRequestId", key(),
                        "expectedEpisodeRevision", 3,
                        "expectedProductionRevision", 1,
                        "basedOnBaselineId", null,
                        "scriptVersionId", scriptVersion.path("id").asText(),
                        "storyboardVersionId", storyboardVersion.path("id").asText(),
                        "shotAdoptions", List.of(),
                        "keyframes", keyframes));
        JsonNode shot = baseline.path("shots").get(0);
        assertThat(savedStoryboard.path("shotIdMappings").path("shot-new").asText())
                .isEqualTo(shot.path("shotId").asText());
        return new Baseline(
                episodeId,
                baseline.path("id").asText(),
                scriptVersion.path("id").asText(),
                storyboardVersion.path("id").asText(),
                shot.path("shotId").asText(),
                shot.path("inputSnapshot"));
    }

    private ObjectNode storyboard(String sceneId, String mode, boolean feeConfirmed) {
        return object(
                "schemaVersion", "video-episode-storyboard/1.0",
                "shots", List.of(object(
                        "id", null,
                        "tempKey", "shot-new",
                        "lineage", List.of(),
                        "scriptSceneId", sceneId,
                        "scriptLineIds", List.of(),
                        "title", "交出信件",
                        "action", "交出信件",
                        "framing", "medium",
                        "cameraMovement", "static",
                        "durationMs", 4_000,
                        "productionIntent", object(
                                "provider", "seedance",
                                "model", MODEL,
                                "generationMode", "reference",
                                "executionMode", mode,
                                "feeConfirmed", feeConfirmed,
                                "prompt", "交出信件",
                                "ratio", "16:9",
                                "durationSeconds", 4,
                                "resolution", "720p",
                                "generateAudio", true,
                                "watermark", false,
                                "outputFormat", "mp4",
                                "references", List.of(object(
                                        "canonVersionId", canonVersionId,
                                        "strength", 80))))));
    }

    private void replaceSnapshot(Baseline baseline, ObjectNode snapshot) {
        Map<String, Object> value =
                JSON.convertValue(snapshot, new TypeReference<Map<String, Object>>() {});
        String inputHash =
                CommandIdempotency.sha256(CommandIdempotency.canonicalJsonBytes(value, JSON));
        database.dsl().execute(
                "UPDATE \"VideoProductionBaselineShot\" SET \"inputSnapshotJson\"=?,"
                        + " \"inputHash\"=? WHERE \"baselineId\"=? AND \"shotId\"=?",
                snapshot.toString(),
                inputHash,
                baseline.baselineId(),
                baseline.shotId());
    }

    private static ObjectNode legacy11(JsonNode inputSnapshot) {
        ObjectNode legacy = (ObjectNode) inputSnapshot.deepCopy();
        legacy.put("schemaVersion", "video-production-shot-input/1.1");
        for (JsonNode reference : legacy.path("references")) {
            ((ObjectNode) reference).remove(List.of("rightsStatus", "lockedAt"));
        }
        for (JsonNode keyframe : legacy.path("keyframes")) {
            ((ObjectNode) keyframe).remove(List.of("rightsStatus", "lockedAt"));
        }
        return legacy;
    }

    private static ObjectNode scriptDocument() {
        return object(
                "schemaVersion", "video-episode-script/1.0",
                "overview", object(
                        "summary", "交接信件",
                        "creativeIntent", "",
                        "targetDurationSeconds", 60),
                "scenes", List.of(object(
                        "id", null,
                        "tempKey", "scene-new",
                        "title", "雨夜",
                        "locationLabel", "巷口",
                        "timeLabel", "夜",
                        "narrativeTime", "现在",
                        "characterIds", List.of(),
                        "lines", List.of(object(
                                "id", null,
                                "tempKey", "line-new",
                                "kind", "action",
                                "speakerId", null,
                                "text", "林岚交出信件",
                                "sourceRefs", List.of())))),
                "endingStates", List.of(),
                "dependencies", List.of());
    }

    private static ObjectNode object(Object... values) {
        ObjectNode result = JSON.createObjectNode();
        for (int index = 0; index < values.length; index += 2) {
            result.set((String) values[index], JSON.valueToTree(values[index + 1]));
        }
        return result;
    }

    private static String key() {
        return UUID.randomUUID().toString();
    }

    private static void assertCode(Runnable action, String expected) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> assertThat(error.code()).isEqualTo(expected));
    }

    private static org.testcontainers.containers.Container.ExecResult sqlFile(String path)
            throws Exception {
        return POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "inkforge",
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                path);
    }

    private record Baseline(
            String episodeId,
            String baselineId,
            String scriptVersionId,
            String storyboardVersionId,
            String shotId,
            JsonNode inputSnapshot) {}

}
