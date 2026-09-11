package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.CompletedEpisodeExport;
import cn.inkforge.core.video.application.StoredVideoAsset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** 在 PostgreSQL 中验证稳定镜头、人工确认、配置门禁与制作基线 CAS。 */
@Testcontainers
class JooqVideoEpisodeProductionRepositoryTest {
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
    private static JooqVideoEpisodePostProductionRepository postProduction;
    private String userId;
    private String novelId;
    private String projectId;
    private String canonVersionId;
    private String canonAssetId;

    @BeforeAll
    static void setupDatabase() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/base.sql");
        assertThat(sqlFile("/tmp/base.sql").getExitCode()).isZero();
        Path migration =
                Path.of("../../scripts/migrations/20260910_video_production_baseline_domain.sql");
        if (!Files.exists(migration)) {
            migration =
                    Path.of("scripts/migrations/20260910_video_production_baseline_domain.sql");
        }
        POSTGRES.copyFileToContainer(
                MountableFile.forHostPath(migration.toAbsolutePath()), "/tmp/p2.sql");
        var migrated = sqlFile("/tmp/p2.sql");
        assertThat(migrated.getExitCode()).as(migrated.getStderr()).isZero();
        database =
                CoreDatabase.connect(
                        PostgresConnectionSettings.parse(
                                "postgresql://inkforge:test-only-password@"
                                        + POSTGRES.getHost()
                                        + ":"
                                        + POSTGRES.getFirstMappedPort()
                                        + "/"
                                        + POSTGRES.getDatabaseName()));
        var ids = new CuidV1Generator(Clock.systemUTC());
        episodes =
                new JooqVideoEpisodeRepository(
                        database, ids, Clock.systemUTC(), JSON);
        production =
                new JooqVideoEpisodeProductionRepository(
                        database,
                        ids,
                        Clock.systemUTC(),
                        JSON,
                        MODEL,
                        "simulated",
                        false,
                        false,
                        true);
        postProduction =
                new JooqVideoEpisodePostProductionRepository(
                        database, ids, Clock.systemUTC(), JSON);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) {
            database.close();
        }
    }

    @BeforeEach
    void fixture() {
        userId = "owner-" + UUID.randomUUID();
        novelId = "novel-" + UUID.randomUUID();
        projectId = "project-" + UUID.randomUUID();
        canonVersionId = "canon-version-" + UUID.randomUUID();
        String characterId = "character-" + UUID.randomUUID();
        String assetId = "asset-" + UUID.randomUUID();
        canonAssetId = assetId;
        String canonId = "canon-" + UUID.randomUUID();
        database.dsl()
                .execute(
                        "INSERT INTO \"User\"(id,username,\"passwordHash\",\"updatedAt\")"
                                + " VALUES (?,?,?,CURRENT_TIMESTAMP)",
                        userId,
                        userId,
                        "test");
        database.dsl()
                .execute(
                        "INSERT INTO \"Novel\"(id,\"userId\",name,\"updatedAt\")"
                                + " VALUES (?,?,?,CURRENT_TIMESTAMP)",
                        novelId,
                        userId,
                        "雨夜故事");
        database.dsl()
                .execute(
                        "INSERT INTO \"WritingBible\""
                                + " (id,\"novelId\",\"storyLengthProfile\",\"updatedAt\")"
                                + " VALUES (?,?,'long_serial',CURRENT_TIMESTAMP)",
                        "bible-" + UUID.randomUUID(),
                        novelId);
        database.dsl()
                .execute(
                        "INSERT INTO \"VideoProject\""
                                + " (id,\"novelId\",title,mode,status,\"targetAspectRatio\",\"targetLanguage\",provider,revision,\"updatedAt\")"
                                + " VALUES (?,?,'短剧','series','draft','16:9','zh-CN','seedance_2_5',1,CURRENT_TIMESTAMP)",
                        projectId,
                        novelId);
        database.dsl()
                .execute(
                        "INSERT INTO \"Character\"(id,\"novelId\",name,\"updatedAt\")"
                                + " VALUES (?,?,?,CURRENT_TIMESTAMP)",
                        characterId,
                        novelId,
                        "林岚");
        database.dsl()
                .execute(
                        "INSERT INTO \"VideoAsset\""
                                + " (id,\"projectId\",name,modality,duty,\"storageKey\",\"mimeType\",\"byteSize\",sha256,\"sourceKind\",\"rightsStatus\",\"lockedAt\",\"updatedAt\")"
                                + " VALUES (?,?,'林岚定妆','image','identity',?,'image/png',128,?,'user_upload','confirmed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                        assetId,
                        projectId,
                        projectId + "/canon.png",
                        "a".repeat(64));
        database.dsl()
                .execute(
                        "INSERT INTO \"VideoVisualCanon\""
                                + " (id,\"projectId\",\"novelId\",\"settingKind\",\"settingId\",\"settingName\",\"variantKey\",duty,label,revision,\"updatedAt\")"
                                + " VALUES (?,?,?,'character',?,'林岚','default','identity','林岚定妆',1,CURRENT_TIMESTAMP)",
                        canonId,
                        projectId,
                        novelId,
                        characterId);
        database.dsl()
                .execute(
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
        database.dsl()
                .execute(
                        "UPDATE \"VideoVisualCanon\" SET \"currentVersionId\"=? WHERE id=?",
                        canonVersionId,
                        canonId);
    }

    @Test
    void 后期入口与剧本制作入口共享全局命令键() {
        String episodeId =
                episodes.create(
                                userId,
                                projectId,
                                object("clientRequestId", key(), "title", "命令锁"))
                        .path("id")
                        .asText();
        String sharedRequestId = key();
        episodes.update(
                userId,
                episodeId,
                object(
                        "clientRequestId",
                        sharedRequestId,
                        "expectedRevision",
                        1,
                        "title",
                        "命令锁已更新"));

        assertCode(
                () ->
                        postProduction.createExportTask(
                                userId,
                                episodeId,
                                "missing-baseline",
                                object(
                                        "clientRequestId",
                                        sharedRequestId,
                                        "editVersionId",
                                        "missing-edit",
                                        "mixVersionId",
                                        "missing-mix",
                                        "resolution",
                                        "720p",
                                        "framesPerSecond",
                                        24,
                                        "burnSubtitles",
                                        true)),
                "VIDEO_EPISODE_CLIENT_REQUEST_REUSED");
    }

    @Test
    void 稳定镜头确认替换和新基线均保留旧版本() {
        ScriptFixture fixture = confirmedScript();
        ObjectNode firstSave =
                production.saveStoryboardDraft(
                        userId,
                        fixture.episodeId(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedRevision",
                                1,
                                "scriptVersionId",
                                fixture.scriptVersionId(),
                                "baseStoryboardVersionId",
                                null,
                                "document",
                                storyboard(
                                        shot(null, "shot-a", List.of(), fixture.sceneId(), "交出信件"),
                                        shot(null, "shot-b", List.of(), fixture.sceneId(), "接住信件"))));
        String shotA = firstSave.path("shotIdMappings").path("shot-a").asText();
        String shotB = firstSave.path("shotIdMappings").path("shot-b").asText();

        ObjectNode confirmation = prepare(fixture.episodeId(), 2, 2);
        ObjectNode firstVersion = approve(fixture.episodeId(), confirmation, 2, 2);
        assertThat(firstVersion.path("shots")).hasSize(2);
        String baselineRequestId = key();
        ObjectNode baselineRequest =
                object(
                        "clientRequestId",
                        baselineRequestId,
                        "expectedEpisodeRevision",
                        3,
                        "expectedProductionRevision",
                        1,
                        "basedOnBaselineId",
                        null,
                        "scriptVersionId",
                        fixture.scriptVersionId(),
                        "storyboardVersionId",
                        firstVersion.path("id").asText(),
                        "shotAdoptions",
                        List.of(),
                        "keyframes",
                        List.of(
                                object(
                                        "shotVersionId",
                                        firstVersion.path("shots").get(0).path("id").asText(),
                                        "role",
                                        "initial_state",
                                        "assetId",
                                        canonAssetId)));
        ObjectNode baseline =
                production.createProductionBaseline(
                        userId, fixture.episodeId(), baselineRequest);
        assertThat(
                        production.createProductionBaseline(
                                userId, fixture.episodeId(), baselineRequest))
                .isEqualTo(baseline);
        JsonNode input = baseline.path("shots").get(0).path("inputSnapshot");
        assertThat(input.path("schemaVersion").asText())
                .isEqualTo("video-production-shot-input/1.2");
        assertThat(input.path("model").asText()).isEqualTo(MODEL);
        assertThat(input.path("generationMode").asText()).isEqualTo("reference");
        assertThat(input.path("executionMode").asText()).isEqualTo("simulated");
        assertThat(input.path("feeConfirmed").asBoolean()).isFalse();
        assertThat(input.path("outputFormat").asText()).isEqualTo("mp4");
        assertThat(input.path("promptVersionId").asText()).isNotBlank();
        assertThat(input.path("references").get(0).path("ordinal").asInt()).isEqualTo(1);
        assertThat(input.path("references").get(0).path("sha256").asText())
                .isEqualTo("a".repeat(64));
        assertThat(input.path("references").get(0).path("rightsStatus").asText())
                .isEqualTo("confirmed");
        assertThat(input.path("references").get(0).path("lockedAt").asText()).endsWith("Z");
        assertThat(input.path("keyframes")).hasSize(1);
        assertThat(input.path("keyframes").get(0).path("role").asText())
                .isEqualTo("initial_state");
        assertThat(input.path("keyframes").get(0).path("assetId").asText())
                .isEqualTo(canonAssetId);
        assertThat(input.path("keyframes").get(0).path("rightsStatus").asText())
                .isEqualTo("confirmed");
        assertThat(input.path("keyframes").get(0).path("lockedAt").asText())
                .isEqualTo(input.path("references").get(0).path("lockedAt").asText());
        String keyframeVersionId =
                input.path("keyframes").get(0).path("keyframeVersionId").asText();
        assertThat(
                        database.dsl()
                                .fetchOne(
                                        "SELECT \"productionBaselineId\" FROM"
                                                + " \"VideoShotKeyframeVersion\" WHERE id=?",
                                        keyframeVersionId)
                                .get("productionBaselineId", String.class))
                .isEqualTo(baseline.path("id").asText());
        String sourceShotVersionId = baseline.path("shots").get(0).path("shotVersionId").asText();
        String takeId = insertTake(fixture, baseline, input);
        ObjectNode candidates =
                production.listTakeCandidates(
                        userId, fixture.episodeId(), sourceShotVersionId, null, 20);
        assertThat(candidates.path("takes")).hasSize(1);
        JsonNode candidate = candidates.path("takes").get(0);
        assertThat(candidate.path("id").asText()).isEqualTo(takeId);
        assertThat(candidate.path("sourceBaselineId").asText())
                .isEqualTo(baseline.path("id").asText());
        assertThat(candidate.path("durationMs").asInt()).isEqualTo(4_000);
        assertThat(candidate.path("width").asInt()).isEqualTo(1_280);
        assertThat(candidate.path("height").asInt()).isEqualTo(720);
        assertThat(candidate.path("lastFrameAssetId").asText()).isNotBlank();
        assertThat(candidate.path("adopted").asBoolean()).isFalse();
        ObjectNode adoption =
                production.createTakeAdoption(
                        userId,
                        fixture.episodeId(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedProductionRevision",
                                2,
                                "targetShotVersionId",
                                sourceShotVersionId,
                                "sourceTakeId",
                                takeId,
                                "sourceBaselineId",
                                baseline.path("id").asText(),
                                "comparison",
                                object(
                                        "sourceBaselineId",
                                        baseline.path("id").asText(),
                                        "targetShotVersionId",
                                        sourceShotVersionId,
                                        "directInputsUnchanged",
                                        true,
                                        "referenceHashesChecked",
                                        List.of("a".repeat(64)),
                                        "summary",
                                        "同一镜头版本直接采用")));
        candidates =
                production.listTakeCandidates(
                        userId, fixture.episodeId(), sourceShotVersionId, null, 20);
        assertThat(candidates.path("takes").get(0).path("adoptionId").asText())
                .isEqualTo(adoption.path("id").asText());
        assertThat(candidates.path("takes").get(0).path("adopted").asBoolean()).isTrue();

        ObjectNode changed =
                production.saveStoryboardDraft(
                        userId,
                        fixture.episodeId(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedRevision",
                                3,
                                "scriptVersionId",
                                fixture.scriptVersionId(),
                                "baseStoryboardVersionId",
                                firstVersion.path("id").asText(),
                                "document",
                                storyboard(
                                        shot(shotA, null, List.of(), fixture.sceneId(), "仍交出信件"),
                                        shot(
                                                null,
                                                "shot-b-replacement",
                                                List.of(
                                                        object(
                                                                "sourceShotId",
                                                                shotB,
                                                                "relation",
                                                                "replacement")),
                                                fixture.sceneId(),
                                                "收回信件"))));
        String replacement =
                changed.path("shotIdMappings").path("shot-b-replacement").asText();
        assertThat(replacement).isNotEqualTo(shotB);
        ObjectNode secondConfirmation = prepare(fixture.episodeId(), 4, 4);
        ObjectNode secondVersion = approve(fixture.episodeId(), secondConfirmation, 4, 4);
        assertThat(secondVersion.path("shots").get(0).path("shotId").asText())
                .isEqualTo(shotA);
        assertThat(secondVersion.path("shots").get(0).path("versionNo").asInt())
                .isEqualTo(2);
        assertThat(
                        episodes.get(userId, fixture.episodeId())
                                .path("episode")
                                .path("currentProductionBaselineId")
                                .asText())
                .isEqualTo(baseline.path("id").asText());
        assertThat(
                        database.dsl()
                                .fetchOne(
                                        "SELECT count(*) n FROM \"VideoShotLineage\" WHERE"
                                                + " \"childShotId\"=? AND \"sourceShotId\"=?",
                                        replacement,
                                        shotB)
                                .get("n", Integer.class))
                .isEqualTo(1);
    }

    @Test
    void 多源合并保存完整沿袭且错误模型和时长均被Java拒绝() {
        ScriptFixture fixture = confirmedScript();
        ObjectNode initial =
                production.saveStoryboardDraft(
                        userId,
                        fixture.episodeId(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedRevision",
                                1,
                                "scriptVersionId",
                                fixture.scriptVersionId(),
                                "baseStoryboardVersionId",
                                null,
                                "document",
                                storyboard(
                                        shot(null, "left", List.of(), fixture.sceneId(), "左侧"),
                                        shot(null, "right", List.of(), fixture.sceneId(), "右侧"))));
        String left = initial.path("shotIdMappings").path("left").asText();
        String right = initial.path("shotIdMappings").path("right").asText();
        ObjectNode merged =
                production.saveStoryboardDraft(
                        userId,
                        fixture.episodeId(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedRevision",
                                2,
                                "scriptVersionId",
                                fixture.scriptVersionId(),
                                "baseStoryboardVersionId",
                                null,
                                "document",
                                storyboard(
                                        shot(
                                                null,
                                                "merged",
                                                List.of(
                                                        object(
                                                                "sourceShotId",
                                                                left,
                                                                "relation",
                                                                "merge"),
                                                        object(
                                                                "sourceShotId",
                                                                right,
                                                                "relation",
                                                                "merge")),
                                                fixture.sceneId(),
                                                "合并构图"))));
        assertThat(
                        database.dsl()
                                .fetchOne(
                                        "SELECT count(*) n FROM \"VideoShotLineage\" WHERE"
                                                + " \"childShotId\"=?",
                                        merged.path("shotIdMappings").path("merged").asText())
                                .get("n", Integer.class))
                .isEqualTo(2);

        ObjectNode badModel = storyboard(shot(null, "bad-model", List.of(), fixture.sceneId(), "坏模型"));
        ((ObjectNode) badModel.path("shots").get(0).path("productionIntent"))
                .put("model", "client-chosen-model");
        assertCode(
                () ->
                        production.saveStoryboardDraft(
                                userId,
                                fixture.episodeId(),
                                object(
                                        "clientRequestId",
                                        key(),
                                        "expectedRevision",
                                        3,
                                        "scriptVersionId",
                                        fixture.scriptVersionId(),
                                        "baseStoryboardVersionId",
                                        null,
                                        "document",
                                        badModel)),
                "VIDEO_STORYBOARD_INTENT_INVALID");
        ObjectNode badDuration =
                storyboard(shot(null, "bad-duration", List.of(), fixture.sceneId(), "坏时长"));
        ((ObjectNode) badDuration.path("shots").get(0)).put("durationMs", 5_000);
        assertCode(
                () ->
                        production.saveStoryboardDraft(
                                userId,
                                fixture.episodeId(),
                                object(
                                        "clientRequestId",
                                        key(),
                                        "expectedRevision",
                                        3,
                                        "scriptVersionId",
                                        fixture.scriptVersionId(),
                                        "baseStoryboardVersionId",
                                        null,
                                        "document",
                                        badDuration)),
                "VIDEO_STORYBOARD_DURATION_INVALID");
        assertThat(production.getStoryboardDraft(userId, fixture.episodeId()).path("revision").asInt())
                .isEqualTo(3);
    }

    @Test
    void 跨基线采用可拆成多段并冻结后期版本与重试清单() {
        ScriptFixture fixture = confirmedScript();
        ObjectNode firstShot =
                shot(null, "shot-a", List.of(), fixture.sceneId(), "交出信件");
        firstShot.set("scriptLineIds", JSON.valueToTree(List.of(fixture.lineId())));
        ObjectNode secondShot =
                shot(null, "shot-b", List.of(), fixture.sceneId(), "看向巷口");
        ObjectNode firstDraft =
                production.saveStoryboardDraft(
                        userId,
                        fixture.episodeId(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedRevision",
                                1,
                                "scriptVersionId",
                                fixture.scriptVersionId(),
                                "baseStoryboardVersionId",
                                null,
                                "document",
                                storyboard(firstShot, secondShot)));
        String shotA = firstDraft.path("shotIdMappings").path("shot-a").asText();
        String shotB = firstDraft.path("shotIdMappings").path("shot-b").asText();
        ObjectNode firstConfirmation = prepare(fixture.episodeId(), 2, 2);
        ObjectNode firstStoryboard =
                approve(fixture.episodeId(), firstConfirmation, 2, 2);
        ObjectNode baseline0 =
                production.createProductionBaseline(
                        userId,
                        fixture.episodeId(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedEpisodeRevision",
                                3,
                                "expectedProductionRevision",
                                1,
                                "basedOnBaselineId",
                                null,
                                "scriptVersionId",
                                fixture.scriptVersionId(),
                                "storyboardVersionId",
                                firstStoryboard.path("id").asText(),
                                "shotAdoptions",
                                List.of()));
        JsonNode sourceInput = baseline0.path("shots").get(0).path("inputSnapshot");
        String takeId = insertTake(fixture, baseline0, sourceInput);

        ObjectNode changedShot =
                shot(shotA, null, List.of(), fixture.sceneId(), "信件交到对方手中");
        changedShot.set("scriptLineIds", JSON.valueToTree(List.of(fixture.lineId())));
        ObjectNode unchangedShot =
                shot(shotB, null, List.of(), fixture.sceneId(), "仍看向巷口");
        production.saveStoryboardDraft(
                userId,
                fixture.episodeId(),
                object(
                        "clientRequestId",
                        key(),
                        "expectedRevision",
                        3,
                        "scriptVersionId",
                        fixture.scriptVersionId(),
                        "baseStoryboardVersionId",
                        firstStoryboard.path("id").asText(),
                        "document",
                        storyboard(changedShot, unchangedShot)));
        ObjectNode secondConfirmation = prepare(fixture.episodeId(), 4, 4);
        ObjectNode secondStoryboard =
                approve(fixture.episodeId(), secondConfirmation, 4, 4);
        String targetShotVersionId =
                secondStoryboard.path("shots").get(0).path("id").asText();
        String omittedShotVersionId =
                secondStoryboard.path("shots").get(1).path("id").asText();
        ObjectNode adoption =
                production.createTakeAdoption(
                        userId,
                        fixture.episodeId(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedProductionRevision",
                                2,
                                "targetShotVersionId",
                                targetShotVersionId,
                                "sourceTakeId",
                                takeId,
                                "sourceBaselineId",
                                baseline0.path("id").asText(),
                                "comparison",
                                object(
                                        "sourceBaselineId",
                                        baseline0.path("id").asText(),
                                        "targetShotVersionId",
                                        targetShotVersionId,
                                        "directInputsUnchanged",
                                        false,
                                        "referenceHashesChecked",
                                        List.of("a".repeat(64)),
                                        "summary",
                                        "动作变化不影响人物定妆与素材连续性")));
        ObjectNode baseline1Request =
                object(
                        "clientRequestId",
                        key(),
                        "expectedEpisodeRevision",
                        5,
                        "expectedProductionRevision",
                        2,
                        "basedOnBaselineId",
                        baseline0.path("id").asText(),
                        "scriptVersionId",
                        fixture.scriptVersionId(),
                        "storyboardVersionId",
                        secondStoryboard.path("id").asText(),
                        "shotAdoptions",
                        List.of(
                                object(
                                        "shotVersionId",
                                        targetShotVersionId,
                                        "adoptionId",
                                        adoption.path("id").asText())));
        ObjectNode baseline1 =
                production.createProductionBaseline(
                        userId, fixture.episodeId(), baseline1Request);

        ObjectNode editRequest =
                object(
                        "clientRequestId",
                        key(),
                        "expectedHeadRevision",
                        1,
                        "basedOnVersionId",
                        null,
                        "clips",
                        List.of(
                                object(
                                        "tempKey",
                                        "clip-a",
                                        "adoptionId",
                                        adoption.path("id").asText(),
                                        "takeId",
                                        takeId,
                                        "sourceInMs",
                                        0,
                                        "sourceOutMs",
                                        1_500,
                                        "sourceAudioMode",
                                        "keep",
                                        "transitionAfter",
                                        "cut",
                                        "transitionDurationMs",
                                        0),
                                object(
                                        "tempKey",
                                        "clip-b",
                                        "adoptionId",
                                        adoption.path("id").asText(),
                                        "takeId",
                                        takeId,
                                        "sourceInMs",
                                        1_500,
                                        "sourceOutMs",
                                        3_000,
                                        "sourceAudioMode",
                                        "mute",
                                        "transitionAfter",
                                        "fade_black",
                                        "transitionDurationMs",
                                        300)),
                        "omissions",
                        List.of(
                                object(
                                        "shotVersionId",
                                        omittedShotVersionId,
                                        "reason",
                                        "删去重复反应镜头")));
        ObjectNode edit =
                postProduction.createEditVersion(
                        userId,
                        fixture.episodeId(),
                        baseline1.path("id").asText(),
                        editRequest);
        ObjectNode replayedEdit =
                postProduction.createEditVersion(
                        userId,
                        fixture.episodeId(),
                        baseline1.path("id").asText(),
                        editRequest);
        assertThat(replayedEdit.toString()).isEqualTo(edit.toString());
        assertThat(edit.path("clips")).hasSize(2);
        assertThat(edit.path("clips").get(0).path("clipId").asText())
                .isNotEqualTo(edit.path("clips").get(1).path("clipId").asText());
        assertThat(edit.path("clips").get(0).path("sourceAudioMode").asText())
                .isEqualTo("keep");
        assertThat(edit.path("clips").get(1).path("sourceAudioMode").asText())
                .isEqualTo("mute");
        assertThat(edit.path("omissions").get(0).path("shotVersionId").asText())
                .isEqualTo(omittedShotVersionId);
        var scope =
                database.dsl()
                        .fetchOne(
                                "SELECT count(*)::int n,min(c.\"productionBaselineId\") baseline,"
                                        + "min(d.\"sourceBaselineId\") source FROM"
                                        + " \"VideoEpisodeEditClip\" c JOIN \"VideoTakeAdoption\" d"
                                        + " ON d.id=c.\"adoptionId\" WHERE c.\"editVersionId\"=?",
                                edit.path("id").asText());
        assertThat(scope.get("n", Integer.class)).isEqualTo(2);
        assertThat(scope.get("baseline", String.class))
                .isEqualTo(baseline1.path("id").asText());
        assertThat(scope.get("source", String.class))
                .isEqualTo(baseline0.path("id").asText());

        ObjectNode staleEdit = (ObjectNode) editRequest.deepCopy();
        staleEdit.put("clientRequestId", key());
        assertCode(
                () ->
                        postProduction.createEditVersion(
                                userId,
                                fixture.episodeId(),
                                baseline1.path("id").asText(),
                                staleEdit),
                "VIDEO_EDIT_HEAD_CONFLICT");
        ObjectNode outOfRange = (ObjectNode) editRequest.deepCopy();
        outOfRange.put("clientRequestId", key());
        outOfRange.put("expectedHeadRevision", 2);
        outOfRange.put("basedOnVersionId", edit.path("id").asText());
        ((ObjectNode) outOfRange.path("clips").get(1)).put("sourceOutMs", 4_001);
        assertCode(
                () ->
                        postProduction.createEditVersion(
                                userId,
                                fixture.episodeId(),
                                baseline1.path("id").asText(),
                                outOfRange),
                "VIDEO_EDIT_RANGE_INVALID");

        String audioAssetId = "audio-" + UUID.randomUUID();
        database.dsl()
                .execute(
                        "INSERT INTO \"VideoAsset\""
                                + " (id,\"projectId\",name,modality,duty,\"storageKey\",\"mimeType\","
                                + " \"byteSize\",\"durationMs\",sha256,\"sourceKind\",\"rightsStatus\","
                                + " \"lockedAt\",\"updatedAt\") VALUES"
                                + " (?,?,'对白','audio','voice',?,'audio/wav',2048,4000,?,"
                                + " 'user_upload','confirmed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                        audioAssetId,
                        projectId,
                        projectId + "/" + audioAssetId + ".wav",
                        "e".repeat(64));
        ObjectNode mixRequest =
                object(
                        "clientRequestId",
                        key(),
                        "expectedHeadRevision",
                        1,
                        "basedOnVersionId",
                        null,
                        "editVersionId",
                        edit.path("id").asText(),
                        "audioClips",
                        List.of(
                                object(
                                        "trackKind",
                                        "dialogue",
                                        "assetId",
                                        audioAssetId,
                                        "shotVersionId",
                                        targetShotVersionId,
                                        "timelineStartMs",
                                        0,
                                        "sourceInMs",
                                        0,
                                        "sourceOutMs",
                                        2_000,
                                        "gainMillibels",
                                        0,
                                        "fadeInMs",
                                        100,
                                        "fadeOutMs",
                                        100)),
                        "subtitleCues",
                        List.of(
                                object(
                                        "shotVersionId",
                                        targetShotVersionId,
                                        "scriptLineId",
                                        fixture.lineId(),
                                        "startMs",
                                        0,
                                        "endMs",
                                        2_500,
                                        "speaker",
                                        "林岚",
                                        "text",
                                        "交出信件")));
        ObjectNode mix =
                postProduction.createMixVersion(
                        userId,
                        fixture.episodeId(),
                        baseline1.path("id").asText(),
                        mixRequest);
        assertThat(mix.path("subtitleCues").get(0).path("scriptLineId").asText())
                .isEqualTo(fixture.lineId());
        ObjectNode staleMix = (ObjectNode) mixRequest.deepCopy();
        staleMix.put("clientRequestId", key());
        assertCode(
                () ->
                        postProduction.createMixVersion(
                                userId,
                                fixture.episodeId(),
                                baseline1.path("id").asText(),
                                staleMix),
                "VIDEO_MIX_HEAD_CONFLICT");
        ObjectNode wrongLine = (ObjectNode) mixRequest.deepCopy();
        wrongLine.put("clientRequestId", key());
        wrongLine.put("expectedHeadRevision", 2);
        wrongLine.put("basedOnVersionId", mix.path("id").asText());
        ((ObjectNode) wrongLine.path("subtitleCues").get(0))
                .put("scriptLineId", "line-from-another-shot");
        assertCode(
                () ->
                        postProduction.createMixVersion(
                                userId,
                                fixture.episodeId(),
                                baseline1.path("id").asText(),
                                wrongLine),
                "VIDEO_MIX_SUBTITLE_INVALID");

        production.createProductionBaseline(
                userId,
                fixture.episodeId(),
                object(
                        "clientRequestId",
                        key(),
                        "expectedEpisodeRevision",
                        6,
                        "expectedProductionRevision",
                        3,
                        "basedOnBaselineId",
                        baseline1.path("id").asText(),
                        "scriptVersionId",
                        fixture.scriptVersionId(),
                        "storyboardVersionId",
                        secondStoryboard.path("id").asText(),
                        "shotAdoptions",
                        List.of(
                                object(
                                        "shotVersionId",
                                        targetShotVersionId,
                                        "adoptionId",
                                        adoption.path("id").asText()))));
        ObjectNode exportRequest =
                object(
                        "clientRequestId",
                        key(),
                        "editVersionId",
                        edit.path("id").asText(),
                        "mixVersionId",
                        mix.path("id").asText(),
                        "resolution",
                        "720p",
                        "framesPerSecond",
                        24,
                        "burnSubtitles",
                        true);
        ObjectNode exportTask =
                postProduction.createExportTask(
                        userId,
                        fixture.episodeId(),
                        baseline1.path("id").asText(),
                        exportRequest);
        assertThat(
                        postProduction.createExportTask(
                                userId,
                                fixture.episodeId(),
                                baseline1.path("id").asText(),
                                exportRequest))
                .isEqualTo(exportTask);
        String manifestJson =
                database.dsl()
                        .fetchOne(
                                "SELECT \"requestManifestJson\" FROM"
                                        + " \"VideoEpisodeExportTask\" WHERE id=?",
                                exportTask.path("id").asText())
                        .get("requestManifestJson", String.class);
        JsonNode manifest = JSON.readTree(manifestJson);
        assertThat(manifest.path("videoEpisodeId").asText())
                .isEqualTo(fixture.episodeId());
        assertThat(manifest.path("productionBaselineId").asText())
                .isEqualTo(baseline1.path("id").asText());
        assertThat(manifest.has("adaptationId")).isFalse();
        assertThat(manifest.path("ffmpeg").path("videoCodec").asText())
                .isEqualTo("libx264");
        assertThat(manifest.path("videoClips").get(1).path("sourceAudioMode").asText())
                .isEqualTo("mute");

        var claim =
                postProduction.claimDueExportTasks(10).stream()
                        .filter(item -> item.taskId().equals(exportTask.path("id").asText()))
                        .findFirst()
                        .orElseThrow();
        assertThat(claim.manifest().productionBaselineId())
                .isEqualTo(baseline1.path("id").asText());
        assertThat(postProduction.failExport(claim.taskId(), "FFMPEG_FAILED", "测试失败"))
                .isTrue();
        ObjectNode retryRequest = object("clientRequestId", key());
        ObjectNode retry =
                postProduction.retryExportTask(
                        userId,
                        fixture.episodeId(),
                        baseline1.path("id").asText(),
                        exportTask.path("id").asText(),
                        retryRequest);
        assertThat(retry.path("retryOfTaskId").asText())
                .isEqualTo(exportTask.path("id").asText());
        assertThat(retry.path("inputHash").asText())
                .isEqualTo(exportTask.path("inputHash").asText());
        assertThat(
                        postProduction.retryExportTask(
                                userId,
                                fixture.episodeId(),
                                baseline1.path("id").asText(),
                                exportTask.path("id").asText(),
                                retryRequest))
                .isEqualTo(retry);

        ObjectNode beforeDelivery = episodes.get(userId, fixture.episodeId());
        assertThat(beforeDelivery.path("episode").path("latestDeliveryVersionId").isNull())
                .isTrue();
        int beforeEpisodeRevision = beforeDelivery.path("episode").path("revision").asInt();
        int beforeDeliveryRevision = deliveryRevision(fixture.episodeId());
        String retryTaskId = retry.path("id").asText();
        assertThat(postProduction.claimDueExportTasks(10))
                .extracting(item -> item.taskId())
                .contains(retryTaskId);
        CompletedEpisodeExport firstCompletion = completion(retryTaskId, "a");
        ObjectNode completed = postProduction.completeExport(firstCompletion);
        String firstDeliveryId = completed.path("export").path("id").asText();
        assertThat(completed.path("export").path("versionNo").asInt()).isEqualTo(1);
        assertThat(
                        episodes.get(userId, fixture.episodeId())
                                .path("episode")
                                .path("latestDeliveryVersionId")
                                .asText())
                .isEqualTo(firstDeliveryId);
        assertThat(
                        episodes.get(userId, fixture.episodeId())
                                .path("episode")
                                .path("revision")
                                .asInt())
                .isEqualTo(beforeEpisodeRevision + 1);
        assertThat(deliveryRevision(fixture.episodeId()))
                .isEqualTo(beforeDeliveryRevision + 1);

        assertThat(postProduction.completeExport(firstCompletion)).isEqualTo(completed);
        assertThat(deliveryRevision(fixture.episodeId()))
                .isEqualTo(beforeDeliveryRevision + 1);
        assertThat(
                        episodes.get(userId, fixture.episodeId())
                                .path("episode")
                                .path("revision")
                                .asInt())
                .isEqualTo(beforeEpisodeRevision + 1);

        ObjectNode secondTask =
                postProduction.createExportTask(
                        userId,
                        fixture.episodeId(),
                        baseline1.path("id").asText(),
                        object(
                                "clientRequestId",
                                key(),
                                "editVersionId",
                                edit.path("id").asText(),
                                "mixVersionId",
                                mix.path("id").asText(),
                                "resolution",
                                "720p",
                                "framesPerSecond",
                                24,
                                "burnSubtitles",
                                true));
        String secondTaskId = secondTask.path("id").asText();
        assertThat(postProduction.claimDueExportTasks(10))
                .extracting(item -> item.taskId())
                .contains(secondTaskId);
        ObjectNode second = postProduction.completeExport(completion(secondTaskId, "b"));
        assertThat(second.path("export").path("versionNo").asInt()).isEqualTo(2);
        assertThat(
                        episodes.get(userId, fixture.episodeId())
                                .path("episode")
                                .path("latestDeliveryVersionId")
                                .asText())
                .isEqualTo(second.path("export").path("id").asText());
        assertThat(deliveryRevision(fixture.episodeId()))
                .isEqualTo(beforeDeliveryRevision + 2);
    }

    private int deliveryRevision(String episodeId) {
        return database.dsl()
                .fetchOne(
                        "SELECT \"deliveryRevision\" FROM \"VideoEpisode\" WHERE id=?",
                        episodeId)
                .get("deliveryRevision", Integer.class);
    }

    private CompletedEpisodeExport completion(String taskId, String suffix) {
        return new CompletedEpisodeExport(
                taskId,
                "export_" + taskId,
                new StoredVideoAsset(
                        projectId + "/delivery-" + suffix + ".mp4",
                        Path.of("/tmp/delivery-" + suffix + ".mp4"),
                        "video/mp4",
                        8_192,
                        ("a".equals(suffix) ? "7" : "8").repeat(64)),
                8_000);
    }

    private ScriptFixture confirmedScript() {
        String episodeId =
                episodes.create(
                                userId,
                                projectId,
                                object("clientRequestId", key(), "title", "雨夜交信"))
                        .path("id")
                        .asText();
        ObjectNode saved =
                episodes.saveDraft(
                        userId,
                        episodeId,
                        object(
                                "clientRequestId",
                                key(),
                                "expectedRevision",
                                1,
                                "sourceSetVersionId",
                                null,
                                "baseScriptVersionId",
                                null,
                                "document",
                                scriptDocument()));
        String sceneId = saved.path("document").path("scenes").get(0).path("id").asText();
        ObjectNode prepared =
                episodes.prepareConfirmation(
                        userId,
                        episodeId,
                        object(
                                "clientRequestId",
                                key(),
                                "expectedDraftRevision",
                                2,
                                "expectedEpisodeRevision",
                                1));
        ObjectNode version =
                episodes.approveConfirmation(
                        userId,
                        episodeId,
                        prepared.path("artifactId").asText(),
                        object(
                                "clientRequestId",
                                key(),
                                "expectedArtifactRevision",
                                1,
                                "expectedDraftRevision",
                                2,
                                "expectedEpisodeRevision",
                                1,
                                "confirmationHash",
                                prepared.path("confirmationHash").asText()));
        String lineId =
                saved.path("document").path("scenes").get(0).path("lines").get(0).path("id").asText();
        return new ScriptFixture(episodeId, version.path("id").asText(), sceneId, lineId);
    }

    private String insertTake(
            ScriptFixture fixture, ObjectNode baseline, JsonNode inputSnapshot) {
        String baselineId = baseline.path("id").asText();
        String shotId = inputSnapshot.path("shotId").asText();
        String shotVersionId = inputSnapshot.path("shotVersionId").asText();
        String promptVersionId = inputSnapshot.path("promptVersionId").asText();
        String inputHash = baseline.path("shots").get(0).path("inputHash").asText();
        String taskId = "render-" + UUID.randomUUID();
        String takeId = "take-" + UUID.randomUUID();
        String assetId = "video-" + UUID.randomUUID();
        String lastFrameAssetId = "last-frame-" + UUID.randomUUID();
        database.dsl()
                .execute(
                        "INSERT INTO \"VideoAsset\""
                                + " (id,\"projectId\",name,modality,duty,\"storageKey\",\"mimeType\",\"byteSize\",\"durationMs\",sha256,\"sourceKind\",\"rightsStatus\",\"lockedAt\",\"updatedAt\")"
                                + " VALUES (?,?,'Take','video','motion',?,'video/mp4',4096,4000,?,'model_generated','confirmed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),"
                                + " (?,?,'尾帧','image','keyframe',?,'image/png',512,NULL,?,'model_generated','confirmed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                        assetId,
                        projectId,
                        projectId + "/" + assetId + ".mp4",
                        "c".repeat(64),
                        lastFrameAssetId,
                        projectId,
                        projectId + "/" + lastFrameAssetId + ".png",
                        "d".repeat(64));
        database.dsl()
                .execute(
                        "INSERT INTO \"VideoShotRenderTask\""
                                + " (id,\"projectId\",\"novelId\",\"promptVersionId\",provider,model,status,\"clientRequestId\",\"inputHash\",\"requestManifestJson\",\"providerTaskId\",\"updatedAt\",\"videoEpisodeId\",\"episodeShotId\",\"episodeShotVersionId\",\"productionBaselineId\")"
                                + " VALUES (?,?,?,?,'seedance',?,'succeeded',?,?,?, ?,CURRENT_TIMESTAMP,?,?,?,?)",
                        taskId,
                        projectId,
                        novelId,
                        promptVersionId,
                        MODEL,
                        key(),
                        inputHash,
                        "{}",
                        "provider-" + taskId,
                        fixture.episodeId(),
                        shotId,
                        shotVersionId,
                        baselineId);
        database.dsl()
                .execute(
                        "INSERT INTO \"VideoShotTake\""
                                + " (id,\"taskId\",\"projectId\",\"novelId\",\"promptVersionId\",\"assetId\",\"lastFrameAssetId\",\"takeNo\",provider,model,\"providerTaskId\",\"inputHash\",\"providerMetadataJson\",\"videoEpisodeId\",\"episodeShotId\",\"episodeShotVersionId\",\"productionBaselineId\")"
                                + " VALUES (?,?,?,?,?,?,?,1,'seedance',?,?,?,?,?,?,?,?)",
                        takeId,
                        taskId,
                        projectId,
                        novelId,
                        promptVersionId,
                        assetId,
                        lastFrameAssetId,
                        MODEL,
                        "provider-" + taskId,
                        inputHash,
                        "{\"media\":{\"width\":1280,\"height\":720}}",
                        fixture.episodeId(),
                        shotId,
                        shotVersionId,
                        baselineId);
        return takeId;
    }

    private ObjectNode prepare(String episodeId, int draftRevision, int episodeRevision) {
        return production.prepareStoryboardConfirmation(
                userId,
                episodeId,
                object(
                        "clientRequestId",
                        key(),
                        "expectedDraftRevision",
                        draftRevision,
                        "expectedEpisodeRevision",
                        episodeRevision));
    }

    private ObjectNode approve(
            String episodeId,
            ObjectNode confirmation,
            int draftRevision,
            int episodeRevision) {
        return production.approveStoryboardConfirmation(
                userId,
                episodeId,
                confirmation.path("artifactId").asText(),
                object(
                        "clientRequestId",
                        key(),
                        "expectedArtifactRevision",
                        1,
                        "expectedDraftRevision",
                        draftRevision,
                        "expectedEpisodeRevision",
                        episodeRevision,
                        "confirmationHash",
                        confirmation.path("confirmationHash").asText()));
    }

    private ObjectNode storyboard(ObjectNode... shots) {
        return object(
                "schemaVersion", "video-episode-storyboard/1.0", "shots", List.of(shots));
    }

    private ObjectNode shot(
            String id,
            String tempKey,
            List<ObjectNode> lineage,
            String sceneId,
            String action) {
        return object(
                "id",
                id,
                "tempKey",
                tempKey,
                "lineage",
                lineage,
                "scriptSceneId",
                sceneId,
                "scriptLineIds",
                List.of(),
                "title",
                action,
                "action",
                action,
                "framing",
                "medium",
                "cameraMovement",
                "static",
                "durationMs",
                4_000,
                "productionIntent",
                object(
                        "provider",
                        "seedance",
                        "model",
                        MODEL,
                        "generationMode",
                        "reference",
                        "executionMode",
                        "simulated",
                        "feeConfirmed",
                        false,
                        "prompt",
                        action,
                        "ratio",
                        "16:9",
                        "durationSeconds",
                        4,
                        "resolution",
                        "720p",
                        "generateAudio",
                        true,
                        "watermark",
                        false,
                        "outputFormat",
                        "mp4",
                        "references",
                        List.of(object("canonVersionId", canonVersionId, "strength", 80))));
    }

    private static ObjectNode scriptDocument() {
        return object(
                "schemaVersion",
                "video-episode-script/1.0",
                "overview",
                object("summary", "交接信件", "creativeIntent", "", "targetDurationSeconds", 60),
                "scenes",
                List.of(
                        object(
                                "id",
                                null,
                                "tempKey",
                                "scene-new",
                                "title",
                                "雨夜",
                                "locationLabel",
                                "巷口",
                                "timeLabel",
                                "夜",
                                "narrativeTime",
                                "现在",
                                "characterIds",
                                List.of(),
                                "lines",
                                List.of(
                                        object(
                                                "id",
                                                null,
                                                "tempKey",
                                                "line-new",
                                                "kind",
                                                "action",
                                                "speakerId",
                                                null,
                                                "text",
                                                "林岚交出信件",
                                                "sourceRefs",
                                                List.of())))),
                "endingStates",
                List.of(),
                "dependencies",
                List.of());
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

    private record ScriptFixture(
            String episodeId, String scriptVersionId, String sceneId, String lineId) {}

}
