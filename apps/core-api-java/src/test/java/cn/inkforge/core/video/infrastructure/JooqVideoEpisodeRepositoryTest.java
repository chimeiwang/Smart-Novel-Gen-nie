package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;

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

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;

/** PostgreSQL 中验证独立身份、来源、作者确认与并发；不使用内存数据库证明事务。 */
@Testcontainers
class JooqVideoEpisodeRepositoryTest {
    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_episode_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static final JsonMapper JSON = JsonMapper.builder().findAndAddModules().build();
    private static CoreDatabase db;
    private static JooqVideoEpisodeRepository repo;
    private static JooqVideoEpisodeImpactRepository impacts;
    private String user, novel, project, chapter;

    @BeforeAll
    static void setup() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/base.sql");
        var restored =
                POSTGRES.execInContainer(
                        "psql",
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-U",
                        "inkforge",
                        "-d",
                        POSTGRES.getDatabaseName(),
                        "-f",
                        "/tmp/base.sql");
        assertThat(restored.getExitCode()).as(restored.getStderr()).isZero();
        db =
                CoreDatabase.connect(
                        PostgresConnectionSettings.parse(
                                "postgresql://inkforge:test-only-password@"
                                        + POSTGRES.getHost()
                                        + ":"
                                        + POSTGRES.getFirstMappedPort()
                                        + "/"
                                        + POSTGRES.getDatabaseName()));
        var ids = new CuidV1Generator(Clock.systemUTC());
        repo = new JooqVideoEpisodeRepository(db, ids, Clock.systemUTC(), JSON);
        impacts = new JooqVideoEpisodeImpactRepository(db, ids, Clock.systemUTC(), JSON);
    }

    @AfterAll
    static void close() {
        if (db != null) db.close();
    }

    @BeforeEach
    void fixture() {
        user = "owner-" + UUID.randomUUID();
        novel = "novel-" + UUID.randomUUID();
        project = "project-" + UUID.randomUUID();
        chapter = "chapter-" + UUID.randomUUID();
        db.dsl()
                .execute(
                        "INSERT INTO \"User\"(id,username,\"passwordHash\",\"updatedAt\") VALUES"
                            + " (?,?,?,CURRENT_TIMESTAMP)",
                        user,
                        user,
                        "test");
        db.dsl()
                .execute(
                "INSERT INTO \"Novel\"(id,\"userId\",name,\"updatedAt\") VALUES"
                            + " (?,?,?,CURRENT_TIMESTAMP)",
                        novel,
                        user,
                        "雨夜故事");
        db.dsl()
                .execute(
                        "INSERT INTO"
                            + " \"WritingBible\"(id,\"novelId\",\"storyLengthProfile\",\"updatedAt\")"
                            + " VALUES (?,?,'long_serial',CURRENT_TIMESTAMP)",
                        "bible-" + UUID.randomUUID(),
                        novel);
        db.dsl()
                .execute(
                        "INSERT INTO"
                            + " \"VideoProject\"(id,\"novelId\",title,mode,status,\"targetAspectRatio\",\"targetLanguage\",provider,revision,\"updatedAt\")"
                            + " VALUES"
                            + " (?,?,'剧集','series','draft','16:9','zh-CN','seedance_2_5',1,CURRENT_TIMESTAMP)",
                        project,
                        novel);
        db.dsl()
                .execute(
                        "INSERT INTO"
                            + " \"Chapter\"(id,\"novelId\",title,content,\"order\",\"updatedAt\")"
                            + " VALUES (?,?,'雨夜','甲😀乙\n"
                            + "交信',1,'2026-09-10 00:00:00')",
                        chapter,
                        novel);
    }

    @Test
    void 创建重放和排序保持身份并拒绝命令键复用() {
        ObjectNode request = obj("clientRequestId", key(), "title", "雨夜交信");
        ObjectNode a = repo.create(user, project, request);
        ObjectNode replay = repo.create(user, project, request);
        assertThat(replay).isEqualTo(a);
        String id = a.path("id").asText();
        assertThat(
                        repo.getProjectCommand(
                                        user, project, request.path("clientRequestId").asText())
                                .path("resultId")
                                .asText())
                .isEqualTo(id);
        var receipt =
                JSON.convertValue(
                        repo.getProjectCommand(
                                user, project, request.path("clientRequestId").asText()),
                        cn.inkforge.contracts.api.VideoEpisodeCommandResponse.class);
        assertThat(receipt.getCreatedAt()).isNotNull();
        ObjectNode b = episode("拆信");
        ObjectNode sorted =
                repo.reorder(
                        user,
                        project,
                        obj(
                                "clientRequestId",
                                key(),
                                "expectedProjectRevision",
                                3,
                                "episodeIds",
                                List.of(b.path("id").asText(), id)));
        assertThat(sorted.path("episodes").get(1).path("id").asText()).isEqualTo(id);
        request.put("title", "另一集");
        code(() -> repo.create(user, project, request), "VIDEO_EPISODE_CLIENT_REQUEST_REUSED");
        code(() -> repo.get("other", id), "VIDEO_PROJECT_NOT_FOUND");
    }

    @Test
    void 完整来源永久冻结且只给系统初始空稿自动绑定() {
        String id = episode("取材").path("id").asText();
        ObjectNode source = repo.createSourceSet(user, id, sourceRequest(1));
        assertThat(repo.getDraft(user, id).path("revision").asInt()).isEqualTo(2);
        assertThat(repo.getDraft(user, id).path("sourceSetVersionId").asText())
                .isEqualTo(source.path("id").asText());
        assertThat(source.path("sources").get(0).path("sourceText").asText()).isEqualTo("甲😀乙\n交信");
        db.dsl()
                .execute(
                        "UPDATE \"Chapter\" SET content='另一版',\"updatedAt\"='2026-09-10 01:00:00'"
                            + " WHERE id=?",
                        chapter);
        ObjectNode historical = repo.getSourceSet(user, id, source.path("id").asText());
        assertThat(historical.path("sources").get(0).path("sourceText").asText())
                .isEqualTo("甲😀乙\n交信");
        assertThat(historical.path("sources").get(0).path("sourceStatus").asText())
                .isEqualTo("updated");
        db.dsl().execute("DELETE FROM \"Chapter\" WHERE id=?", chapter);
        assertThat(
                        repo.getSourceSet(user, id, source.path("id").asText())
                                .path("sources")
                                .get(0)
                                .path("sourceStatus")
                                .asText())
                .isEqualTo("missing");
    }

    @Test
    void 已有手写稿取材不得隐式替换来源和版本() {
        String id = episode("手写").path("id").asText();
        save(id, 1, document("交信"), null);
        repo.createSourceSet(user, id, sourceRequest(1));
        ObjectNode draft = repo.getDraft(user, id);
        assertThat(draft.path("revision").asInt()).isEqualTo(2);
        assertThat(draft.path("sourceSetVersionId").isNull()).isTrue();
    }

    @Test
    void 来源哈希和Unicode码点范围必须匹配() {
        String id = episode("坏取材").path("id").asText();
        ObjectNode request = sourceRequest(1);
        ((ObjectNode) request.path("sources").get(0)).put("sourceHash", "0".repeat(64));
        code(() -> repo.createSourceSet(user, id, request), "VIDEO_SOURCE_CHANGED");
        ObjectNode outside = sourceRequest(1);
        ((ObjectNode) outside.path("sources").get(0).path("ranges").get(0)).put("end", 99);
        code(() -> repo.createSourceSet(user, id, outside), "VIDEO_SOURCE_RANGE_INVALID");
        assertThat(repo.listSourceSets(user, id).path("sourceSets")).isEmpty();
    }

    @Test
    void 节点由Core分配并拒绝伪造身份和旧草稿覆盖() {
        String id = episode("节点").path("id").asText();
        ObjectNode saved = save(id, 1, document("交信"), null);
        String scene = saved.path("document").path("scenes").get(0).path("id").asText();
        assertThat(scene).isNotBlank();
        assertThat(saved.path("nodeIdMappings").path("scene-new").asText()).isEqualTo(scene);
        code(() -> save(id, 1, document("旧窗口"), null), "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT");
        ObjectNode changed = (ObjectNode) saved.path("document").deepCopy();
        ((ObjectNode) changed.path("scenes").get(0)).put("title", "改名");
        assertThat(
                        save(id, 2, changed, null)
                                .path("document")
                                .path("scenes")
                                .get(0)
                                .path("id")
                                .asText())
                .isEqualTo(scene);
        ObjectNode forged = changed.deepCopy();
        ((ObjectNode) forged.path("scenes").get(0)).put("id", "foreign-scene");
        code(() -> save(id, 3, forged, null), "VIDEO_SCRIPT_NODE_ID_INVALID");
    }

    @Test
    void 来源重叠区间拒绝但允许相邻且不改作者选取顺序() {
        String id = episode("选区").path("id").asText();
        ObjectNode overlapping = sourceRequest(1);
        ((ObjectNode) overlapping.path("sources").get(0))
                .set(
                        "ranges",
                        JSON.valueToTree(
                                List.of(obj("start", 1, "end", 3), obj("start", 0, "end", 2))));
        code(() -> repo.createSourceSet(user, id, overlapping), "VIDEO_SOURCE_RANGE_OVERLAP");
        ObjectNode adjacent = sourceRequest(1);
        ((ObjectNode) adjacent.path("sources").get(0))
                .set(
                        "ranges",
                        JSON.valueToTree(
                                List.of(obj("start", 2, "end", 3), obj("start", 0, "end", 2))));
        assertThat(
                        repo.createSourceSet(user, id, adjacent)
                                .path("sources")
                                .get(0)
                                .path("ranges")
                                .get(0)
                                .path("start")
                                .asInt())
                .isEqualTo(2);
    }

    @Test
    void 两个窗口同revision只能一个提交并且失败不留下回执() throws Exception {
        String id = episode("竞争").path("id").asText();
        CountDownLatch ready = new CountDownLatch(1);
        try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
            var a =
                    pool.submit(
                            () -> {
                                ready.await();
                                return attemptSave(id, "甲");
                            });
            var b =
                    pool.submit(
                            () -> {
                                ready.await();
                                return attemptSave(id, "乙");
                            });
            ready.countDown();
            assertThat(List.of(a.get(), b.get()))
                    .containsExactlyInAnyOrder("saved", "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT");
        }
        assertThat(repo.getDraft(user, id).path("revision").asInt()).isEqualTo(2);
    }

    @Test
    void 手工确认与草稿保存分离且批准重放只产生一个正式版本() {
        String id = episode("正式").path("id").asText();
        save(id, 1, document("交信"), null);
        assertThat(repo.listVersions(user, id).path("versions")).isEmpty();
        ObjectNode confirmation = prepare(id, 2, 1);
        ObjectNode approval = approval(confirmation);
        ObjectNode version =
                repo.approveConfirmation(
                        user, id, confirmation.path("artifactId").asText(), approval);
        assertThat(
                        repo.approveConfirmation(
                                user, id, confirmation.path("artifactId").asText(), approval))
                .isEqualTo(version);
        assertThat(repo.listVersions(user, id).path("versions")).hasSize(1);
        assertThat(repo.getDraft(user, id).path("baseScriptVersionId").asText())
                .isEqualTo(version.path("id").asText());
        assertThat(repo.getDraft(user, id).path("revision").asInt()).isEqualTo(3);
        assertThatThrownBy(() -> db.dsl().execute("DELETE FROM \"VideoEpisode\" WHERE id=?", id))
                .isInstanceOf(org.jooq.exception.DataAccessException.class);
    }

    @Test
    void 审核快照过期必须重新准备且不能作为AI候选采用() {
        String id = episode("过期").path("id").asText();
        ObjectNode saved = save(id, 1, document("交信"), null);
        ObjectNode prepared = prepare(id, 2, 1);
        code(
                () ->
                        repo.adoptCandidate(
                                user,
                                id,
                                prepared.path("artifactId").asText(),
                                obj(
                                        "clientRequestId",
                                        key(),
                                        "expectedArtifactRevision",
                                        1,
                                        "expectedDraftRevision",
                                        2)),
                "VIDEO_SCRIPT_ARTIFACT_TARGET_INVALID");
        ObjectNode changed = (ObjectNode) saved.path("document").deepCopy();
        ((ObjectNode) changed.path("scenes").get(0).path("lines").get(0)).put("text", "收回信");
        save(id, 2, changed, null);
        code(
                () ->
                        repo.approveConfirmation(
                                user, id, prepared.path("artifactId").asText(), approval(prepared)),
                "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT");
        assertThat(repo.listVersions(user, id).path("versions")).isEmpty();
    }

    @Test
    void 跨集承接冻结版本且前集改稿只新增影响事实不改后集() {
        String a = episode("交信").path("id").asText();
        ObjectNode firstDoc = document("交信");
        firstDoc.set(
                "endingStates",
                JSON.valueToTree(
                        List.of(
                                obj(
                                        "key",
                                        "letter-owner",
                                        "description",
                                        "顾舟持信未拆",
                                        "entityIds",
                                        List.of(),
                                        "narrativeTime",
                                        "雨夜"))));
        ObjectNode firstSaved = save(a, 1, firstDoc, null);
        ObjectNode av = approve(a, 2, 1);
        String b = episode("拆信").path("id").asText();
        ObjectNode second = document("拆信");
        second.set(
                "dependencies",
                JSON.valueToTree(
                        List.of(
                                obj(
                                        "producerEpisodeId",
                                        a,
                                        "producerScriptVersionId",
                                        av.path("id").asText(),
                                        "producerStateKey",
                                        "letter-owner",
                                        "consumerSceneId",
                                        "scene-new",
                                        "consumerLineId",
                                        null,
                                        "narrativeTime",
                                        "翌日",
                                        "description",
                                        "承接持信状态"))));
        save(b, 1, second, null);
        ObjectNode bv = approve(b, 2, 1);
        ObjectNode modified = (ObjectNode) firstSaved.path("document").deepCopy();
        ((ObjectNode) modified.path("endingStates").get(0)).put("description", "林岚收回信");
        save(a, 3, modified, null);
        approve(a, 4, 2);
        assertThat(
                        repo.getVersion(user, b, bv.path("id").asText())
                                .path("document")
                                .path("dependencies")
                                .get(0)
                                .path("producerScriptVersionId")
                                .asText())
                .isEqualTo(av.path("id").asText());
        assertThat(
                        db.dsl()
                                .fetchOne(
                                        "SELECT count(*) n FROM \"VideoImpactReview\" WHERE"
                                            + " \"targetEpisodeId\"=?",
                                        b)
                                .get("n", Integer.class))
                .isEqualTo(1);

        ObjectNode page = impacts.list(user, b, "pending", null, 20);
        assertThat(page.path("reviews")).hasSize(1);
        String reviewId = page.path("reviews").get(0).path("id").asText();
        ObjectNode review = impacts.get(user, b, reviewId);
        assertThat(review.path("report").path("items")).hasSize(1);
        assertThat(
                        review.path("report")
                                .path("items")
                                .get(0)
                                .path("changeType")
                                .asText())
                .isEqualTo("changed");
        assertThat(
                        review.path("report")
                                .path("items")
                                .get(0)
                                .path("afterState")
                                .path("description")
                                .asText())
                .isEqualTo("林岚收回信");
        ObjectNode decision =
                obj(
                        "clientRequestId",
                        key(),
                        "expectedRevision",
                        1,
                        "decisions",
                        List.of(
                                obj(
                                        "itemId",
                                        review.path("report")
                                                .path("items")
                                                .get(0)
                                                .path("itemId")
                                                .asText(),
                                        "action",
                                        "revise_target",
                                        "note",
                                        "第二集改为追信")));
        ObjectNode resolved = impacts.decide(user, b, reviewId, decision);
        assertThat(resolved.path("status").asText()).isEqualTo("resolved");
        assertThat(impacts.decide(user, b, reviewId, decision)).isEqualTo(resolved);

        db.dsl()
                .execute(
                        "UPDATE \"VideoEpisode\" SET \"productionRevision\"="
                                + " \"productionRevision\"+1 WHERE id=?",
                        b);
        code(
                () ->
                        impacts.decide(
                                user,
                                b,
                                reviewId,
                                obj(
                                        "clientRequestId",
                                        key(),
                                        "expectedRevision",
                                        2,
                                        "decisions",
                                        decision.path("decisions"))),
                "VIDEO_IMPACT_REVIEW_STALE");
    }

    @Test
    void 上游结尾状态未变化时不制造无依据的影响报告() {
        String a = episode("交信").path("id").asText();
        ObjectNode first = document("交信");
        first.set(
                "endingStates",
                JSON.valueToTree(
                        List.of(
                                obj(
                                        "key",
                                        "letter-owner",
                                        "description",
                                        "顾舟持信未拆",
                                        "entityIds",
                                        List.of(),
                                        "narrativeTime",
                                        "雨夜"))));
        save(a, 1, first, null);
        ObjectNode av = approve(a, 2, 1);
        String b = episode("拆信").path("id").asText();
        ObjectNode second = document("拆信");
        second.set(
                "dependencies",
                JSON.valueToTree(
                        List.of(
                                obj(
                                        "producerEpisodeId",
                                        a,
                                        "producerScriptVersionId",
                                        av.path("id").asText(),
                                        "producerStateKey",
                                        "letter-owner",
                                        "consumerSceneId",
                                        "scene-new",
                                        "consumerLineId",
                                        null,
                                        "narrativeTime",
                                        "翌日",
                                        "description",
                                        "承接持信状态"))));
        save(b, 1, second, null);
        approve(b, 2, 1);
        ObjectNode wordingOnly = (ObjectNode) first.deepCopy();
        ((ObjectNode) wordingOnly.path("scenes").get(0)).put("title", "同一状态下的交信");
        save(a, 3, wordingOnly, null);
        approve(a, 4, 2);

        assertThat(impacts.list(user, b, null, null, 20).path("reviews")).isEmpty();
    }

    private String attemptSave(String id, String text) {
        try {
            save(id, 1, document(text), null);
            return "saved";
        } catch (ApiException e) {
            return e.code();
        }
    }

    private ObjectNode episode(String title) {
        return repo.create(user, project, obj("clientRequestId", key(), "title", title));
    }

    private ObjectNode sourceRequest(int revision) {
        return obj(
                "clientRequestId",
                key(),
                "expectedRevision",
                revision,
                "basedOnVersionId",
                null,
                "sources",
                List.of(
                        obj(
                                "chapterId",
                                chapter,
                                "expectedUpdatedAt",
                                "2026-09-10T00:00:00Z",
                                "sourceHash",
                                sha("甲😀乙\n交信"),
                                "ranges",
                                List.of(obj("start", 1, "end", 2)))));
    }

    private ObjectNode save(String id, int revision, JsonNode document, String source) {
        return repo.saveDraft(
                user,
                id,
                obj(
                        "clientRequestId",
                        key(),
                        "expectedRevision",
                        revision,
                        "sourceSetVersionId",
                        source,
                        "baseScriptVersionId",
                        repo.getDraft(user, id).path("baseScriptVersionId"),
                        "document",
                        document));
    }

    private ObjectNode prepare(String id, int draft, int episode) {
        return repo.prepareConfirmation(
                user,
                id,
                obj(
                        "clientRequestId",
                        key(),
                        "expectedDraftRevision",
                        draft,
                        "expectedEpisodeRevision",
                        episode));
    }

    private ObjectNode approve(String id, int draft, int episode) {
        ObjectNode p = prepare(id, draft, episode);
        return repo.approveConfirmation(user, id, p.path("artifactId").asText(), approval(p));
    }

    private ObjectNode approval(JsonNode p) {
        return obj(
                "clientRequestId",
                key(),
                "expectedArtifactRevision",
                p.path("artifactRevision"),
                "expectedDraftRevision",
                p.path("draftRevision"),
                "expectedEpisodeRevision",
                p.path("episodeRevision"),
                "confirmationHash",
                p.path("confirmationHash"));
    }

    private static ObjectNode document(String text) {
        return obj(
                "schemaVersion",
                "video-episode-script/1.0",
                "overview",
                obj("summary", "交接信件", "creativeIntent", "", "targetDurationSeconds", null),
                "scenes",
                List.of(
                        obj(
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
                                        obj(
                                                "id",
                                                null,
                                                "tempKey",
                                                "line-new",
                                                "kind",
                                                "action",
                                                "speakerId",
                                                null,
                                                "text",
                                                text,
                                                "sourceRefs",
                                                List.of())))),
                "endingStates",
                List.of(),
                "dependencies",
                List.of());
    }

    private static ObjectNode obj(Object... values) {
        ObjectNode result = JSON.createObjectNode();
        for (int i = 0; i < values.length; i += 2)
            result.set((String) values[i], JSON.valueToTree(values[i + 1]));
        return result;
    }

    private static String key() {
        return UUID.randomUUID().toString();
    }

    private static String sha(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static void code(Runnable action, String expected) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(
                        ApiException.class, e -> assertThat(e.code()).isEqualTo(expected));
    }
}
