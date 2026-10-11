package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.HexFormat;
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
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** 新剧本启动必须冻结选中片段，并与命令回执在同一事务提交。 */
@Testcontainers
class JooqVideoEpisodeScriptRunStoreTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static final JsonMapper JSON = JsonMapper.builder().findAndAddModules().build();
    private static CoreDatabase database;
    private static JooqVideoEpisodeRepository episodes;
    private static JooqVideoEpisodeScriptRunStore runs;
    private static VideoEpisodeTaskCoordinator tasks;

    private String userId;
    private String novelId;
    private String projectId;
    private String chapterId;

    @BeforeAll
    static void setUpDatabase() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/base.sql");
        assertThat(sqlFile("/tmp/base.sql").getExitCode()).isZero();
        Path migration = Path.of("../../scripts/migrations/20260831_durable_agent_execution.sql");
        if (!Files.exists(migration)) {
            migration = Path.of("scripts/migrations/20260831_durable_agent_execution.sql");
        }
        POSTGRES.copyFileToContainer(
                MountableFile.forHostPath(migration.toAbsolutePath()),
                "/tmp/durable.sql");
        var migrated = sqlFile("/tmp/durable.sql");
        assertThat(migrated.getExitCode()).as(migrated.getStderr()).isZero();

        database = CoreDatabase.connect(PostgresConnectionSettings.parse(
                "postgresql://inkforge:test-only-password@"
                        + POSTGRES.getHost()
                        + ":"
                        + POSTGRES.getFirstMappedPort()
                        + "/"
                        + POSTGRES.getDatabaseName()));
        Clock clock = Clock.systemUTC();
        CuidV1Generator ids = new CuidV1Generator(clock);
        episodes = new JooqVideoEpisodeRepository(database, ids, clock, JSON);
        CoreSettings settings = CoreSettings.from(Map.of(
                "ENVIRONMENT", "test",
                                                                "VIDEO_PREVIEW_ENABLED", "true",
                "VIDEO_DISPATCH_ENABLED", "true",
                "VIDEO_DISPATCH_NAMESPACE", "episode-script-test"));
        tasks = new VideoEpisodeTaskCoordinator(database,ids,JSON,settings,()->null,episodes,
                new JooqVideoEpisodeStoryboardCandidateRepository(database,ids,clock,JSON));
        runs = new JooqVideoEpisodeScriptRunStore(database, ids, settings, tasks, JSON);
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @BeforeEach
    void createFixture() {
        userId = "owner-" + UUID.randomUUID();
        novelId = "novel-" + UUID.randomUUID();
        projectId = "project-" + UUID.randomUUID();
        chapterId = "chapter-" + UUID.randomUUID();
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
                        + "(id,\"novelId\",\"storyLengthProfile\",\"updatedAt\")"
                        + " VALUES (?,?,'long_serial',CURRENT_TIMESTAMP)",
                "bible-" + UUID.randomUUID(),
                novelId);
        database.dsl().execute(
                "INSERT INTO \"VideoProject\""
                        + "(id,\"novelId\",title,mode,status,\"targetAspectRatio\","
                        + "\"targetLanguage\",provider,revision,\"updatedAt\")"
                        + " VALUES (?,?,'剧集','series','draft','16:9','zh-CN',"
                        + "'seedance_2_5',1,CURRENT_TIMESTAMP)",
                projectId,
                novelId);
        database.dsl().execute(
                "INSERT INTO \"Chapter\""
                        + "(id,\"novelId\",title,content,\"order\",\"updatedAt\")"
                        + " VALUES (?,?,?,?,1,'2026-09-10 00:00:00')",
                chapterId,
                novelId,
                "雨夜",
                "甲😀乙\n交信");
        database.dsl().execute(
                "INSERT INTO \"Character\""
                        + "(id,\"novelId\",name,identity,\"speechStyle\",\"updatedAt\")"
                        + " VALUES (?,?,?,'送信人','简短克制',CURRENT_TIMESTAMP)",
                "character-" + UUID.randomUUID(),
                novelId,
                "顾舟");
    }

    @Test
    void 起草只冻结选中片段并原子写入Run与命令回执() {
        ObjectNode episode = episode("雨夜交信");
        String episodeId = episode.path("id").asText();
        episodes.createSourceSet(userId, episodeId, sourceRequest(1));
        ObjectNode request = runRequest(2, "episode_script_generate", List.of(), "改编为短剧剧本");

        ObjectNode started = runs.start(userId, episodeId, request);
        ObjectNode replayed = runs.start(userId, episodeId, request);

        assertThat(replayed).isEqualTo(started);
        database.dsl().execute("UPDATE \"VideoEpisodeCommand\" SET \"resultJson\"=(\"resultJson\"::jsonb-'revision')::text WHERE \"actorUserId\"=? AND \"clientRequestId\"=?",
                userId,request.path("clientRequestId").asText());
        assertThat(runs.start(userId,episodeId,request).path("revision").asInt()).isEqualTo(1);
        assertThat(started.path("status").asText()).isEqualTo("pending");
        String runId = started.path("runId").asText();
        JsonNode context = JSON.readTree(database.dsl().fetchOne(
                        """
                        SELECT item."contentJson"
                        FROM "WorkflowEvidenceItem" item
                        JOIN "WorkflowEvidenceBundle" bundle
                          ON bundle.id = item."bundleId"
                        WHERE bundle."runId" = ?
                          AND item."resourceType" = 'video_episode_script_context'
                        """,
                        runId)
                .get("contentJson", String.class));
        JsonNode source = context.path("sources").get(0);
        assertThat(source.has("sourceText")).isFalse();
        assertThat(source.path("sourceHash").asText()).isEqualTo(sha("甲😀乙\n交信"));
        JsonNode selected = source.path("selectedRanges").get(0);
        assertThat(selected.path("start").asInt()).isEqualTo(1);
        assertThat(selected.path("end").asInt()).isEqualTo(2);
        assertThat(selected.path("text").asText()).isEqualTo("😀");
        assertThat(selected.path("textHash").asText()).isEqualTo(sha("😀"));
        assertThat(context.path("characters").get(0).path("description").asText())
                .contains("身份：送信人", "说话方式：简短克制");
        assertThat(database.dsl().fetchOne(
                        "SELECT input FROM \"WorkflowRun\" WHERE id=?", runId)
                .get("input", String.class))
                .contains("episode-script-test");
        var receipt = JSON.convertValue(
                episodes.getCommand(
                        userId, episodeId, request.path("clientRequestId").asText()),
                cn.inkforge.contracts.api.VideoEpisodeCommandResponse.class);
        assertThat(receipt.getResultType().getValue()).isEqualTo("script_run");
        assertThat(receipt.getResultId()).isEqualTo(runId);
        assertThat(database.dsl().fetchOne(
                        "SELECT count(*) AS n FROM \"WorkflowRun\" WHERE id = ?", runId)
                .get("n", Integer.class))
                .isEqualTo(1);

        request.put("instruction", "同一请求键的另一份说明");
        assertCode(
                () -> runs.start(userId, episodeId, request),
                "VIDEO_EPISODE_CLIENT_REQUEST_REUSED");
    }

    @Test
    void 完整检查点形成唯一候选并经作者采用到工作稿() {
        String episodeId=episode("普通队列闭环").path("id").asText();
        episodes.createSourceSet(userId,episodeId,sourceRequest(1));
        String runId=runs.start(userId,episodeId,runRequest(2,"episode_script_generate",List.of(),"改编")).path("runId").asText();
        ObjectNode candidate=document("交信");
        ObjectNode review=object("decision","pass","summary","完整审阅","requiredChanges",List.of(),"findings",List.of());
        ObjectNode state=object("phase","generate_started","cycle",0,"candidate",null,"review",null);
        tasks.checkpoint(userId,novelId,runId,state);
        state.put("phase","review");state.set("candidate",candidate);tasks.checkpoint(userId,novelId,runId,state);
        state.put("phase","review_started");tasks.checkpoint(userId,novelId,runId,state);
        state.put("phase","complete");state.set("review",review);tasks.checkpoint(userId,novelId,runId,state);
        ObjectNode result=object("candidate",candidate,"review",review);
        tasks.complete(userId,novelId,runId,result);tasks.complete(userId,novelId,runId,result);
        ObjectNode completed=runs.get(userId,episodeId,runId);
        assertThat(completed.path("status").asText()).isEqualTo("completed");
        assertThat(database.dsl().fetchOne("SELECT count(*) n FROM \"ReviewArtifact\" WHERE \"workflowRunId\"=?",runId).get("n",Integer.class)).isEqualTo(1);
        ObjectNode adopted=episodes.adoptCandidate(userId,episodeId,completed.path("artifactId").asText(),
                object("clientRequestId",key(),"expectedArtifactRevision",1,"expectedDraftRevision",2));
        assertThat(adopted.path("revision").asInt()).isEqualTo(3);
        assertThat(adopted.path("document").path("scenes").get(0).path("lines").get(0).path("text").asText()).isEqualTo("交信");
        assertThat(episodes.listVersions(userId,episodeId).path("versions")).isEmpty();
    }

    @Test
    void 局部修订只更新冻结选中场次并保留其他场次() {
        String episodeId=episode("局部闭环").path("id").asText();
        String sourceSet=episodes.createSourceSet(userId,episodeId,sourceRequest(1)).path("id").asText();
        ObjectNode draft=document("原句");
        ObjectNode second=(ObjectNode)draft.path("scenes").get(0).deepCopy();
        second.put("tempKey","scene-second");((ObjectNode)second.path("lines").get(0)).put("tempKey","line-second");
        ((ObjectNode)second.path("lines").get(0)).put("text","范围外原句");
        ((tools.jackson.databind.node.ArrayNode)draft.path("scenes")).add(second);
        ObjectNode saved=episodes.saveDraft(userId,episodeId,object("clientRequestId",key(),"expectedRevision",2,
                "sourceSetVersionId",sourceSet,"baseScriptVersionId",null,"document",draft));
        ObjectNode first=(ObjectNode)saved.path("document").path("scenes").get(0).deepCopy();
        String selected=first.path("id").asText();
        ((ObjectNode)first.path("lines").get(0)).put("text","局部修改句");
        ObjectNode candidate=object("scenes",List.of(first));
        String runId=runs.start(userId,episodeId,runRequest(3,"episode_script_revise",List.of(selected),"只修改首场")).path("runId").asText();
        ObjectNode review=object("decision","pass","summary","范围正确","requiredChanges",List.of(),"findings",List.of());
        ObjectNode state=object("phase","generate_started","cycle",0,"candidate",null,"review",null);
        tasks.checkpoint(userId,novelId,runId,state);
        state.put("phase","review");state.set("candidate",candidate);tasks.checkpoint(userId,novelId,runId,state);
        state.put("phase","review_started");tasks.checkpoint(userId,novelId,runId,state);
        state.put("phase","complete");state.set("review",review);tasks.checkpoint(userId,novelId,runId,state);
        tasks.complete(userId,novelId,runId,object("candidate",candidate,"review",review));
        ObjectNode completed=runs.get(userId,episodeId,runId);
        assertThat(completed.path("status").asText()).isEqualTo("completed");
        ObjectNode adopted=episodes.adoptCandidate(userId,episodeId,completed.path("artifactId").asText(),
                object("clientRequestId",key(),"expectedArtifactRevision",1,"expectedDraftRevision",3));
        assertThat(adopted.path("document").path("scenes").get(1)).isEqualTo(saved.path("document").path("scenes").get(1));
        assertThat(adopted.path("document").path("scenes").get(0).path("lines").get(0).path("text").asText()).isEqualTo("局部修改句");
    }

    @Test
    void 普通任务使用真实来源章且检查点取消与迟到回调保持幂等() {
        String episodeId=episode("普通队列").path("id").asText();
        episodes.createSourceSet(userId,episodeId,sourceRequest(1));
        ObjectNode started=runs.start(userId,episodeId,runRequest(2,"episode_script_generate",List.of(),"改编"));
        String runId=started.path("runId").asText();
        var row=database.dsl().fetchOne("SELECT * FROM \"WorkflowRun\" WHERE id=?",runId);
        assertThat(row.get("engineVersion",Integer.class)).isEqualTo(1);
        assertThat(row.get("chapterId",String.class)).isEqualTo(chapterId);
        assertThat(database.dsl().fetchOne("SELECT count(*) n FROM \"WorkflowStep\" WHERE \"runId\"=?",runId).get("n",Integer.class)).isZero();
        ObjectNode checkpoint=object("phase","review","cycle",0,"candidate",object("scenes",List.of()),"review",null);
        tasks.checkpoint(userId,novelId,runId,object("phase","generate_started","cycle",0,"candidate",null,"review",null));
        tasks.checkpoint(userId,novelId,runId,checkpoint);
        assertThat(tasks.progress(userId,novelId,runId).path("checkpoint")).isEqualTo(checkpoint);
        tasks.checkpoint(userId,novelId,runId,checkpoint);
        assertThat(runs.get(userId,episodeId,runId).path("revision").asInt()).isEqualTo(3);
        assertCode(() -> tasks.checkpoint(userId,novelId,runId,
                object("phase","generate","cycle",0,"candidate",null,"review",null)),
                "VIDEO_EPISODE_CHECKPOINT_CONFLICT");
        String cancelKey=key();
        ObjectNode cancelled=tasks.cancel(userId,episodeId,runId,cancelKey,3);
        assertThat(cancelled.path("revision").asInt()).isEqualTo(4);
        assertThat(tasks.cancel(userId,episodeId,runId,cancelKey,3)).isEqualTo(cancelled);
        assertThat(runs.get(userId,episodeId,runId).path("status").asText()).isEqualTo("running");
        assertThat(tasks.progress(userId,novelId,runId).path("status").asText()).isEqualTo("cancelled");
        assertCode(() -> tasks.checkpoint(userId,novelId,runId,
                object("phase","review_started","cycle",0,"candidate",checkpoint.path("candidate"),"review",null)),
                "VIDEO_EPISODE_TASK_CANCELLED");
        assertThat(tasks.progress(userId,novelId,runId).path("checkpoint")).isEqualTo(checkpoint);
        tasks.complete(userId,novelId,runId,object("candidate",object(),"review",object()));
        assertThat(runs.get(userId,episodeId,runId).path("status").asText()).isEqualTo("cancelled");
        tasks.fail(userId,novelId,runId,"LATE_ERROR","迟到失败",false);
        assertThat(runs.get(userId,episodeId,runId).path("status").asText()).isEqualTo("cancelled");
    }

    @Test
    void 剧本与分镜审阅分别遵守现有业务协议的数量上限() {
        Map<String,Object> thirty=Map.of("decision","revise","summary","分镜逐镜意见",
                "requiredChanges",java.util.Collections.nCopies(30,"明确修改"),
                "findings",java.util.Collections.nCopies(200,Map.of("description","完整问题")));
        tasks.requireReview("video_episode_storyboard",thirty);
        assertCode(() -> tasks.requireReview("video_episode_script",thirty),"VIDEO_EPISODE_TASK_INVALID");
        Map<String,Object> tooManyChanges=new java.util.LinkedHashMap<>(thirty);
        tooManyChanges.put("requiredChanges",java.util.Collections.nCopies(31,"明确修改"));
        assertCode(() -> tasks.requireReview("video_episode_storyboard",tooManyChanges),"VIDEO_EPISODE_TASK_INVALID");
        Map<String,Object> tooManyFindings=new java.util.LinkedHashMap<>(thirty);
        tooManyFindings.put("findings",java.util.Collections.nCopies(201,Map.of("description","完整问题")));
        assertCode(() -> tasks.requireReview("video_episode_storyboard",tooManyFindings),"VIDEO_EPISODE_TASK_INVALID");
    }

    @Test
    void 局部修订必须引用当前稿稳定场次且草稿变化后拒绝启动() {
        String episodeId = episode("拆信").path("id").asText();
        String sourceSetId = episodes.createSourceSet(userId, episodeId, sourceRequest(1))
                .path("id")
                .asText();
        ObjectNode saved = episodes.saveDraft(
                userId,
                episodeId,
                object(
                        "clientRequestId", key(),
                        "expectedRevision", 2,
                        "sourceSetVersionId", sourceSetId,
                        "baseScriptVersionId", null,
                        "document", document("拆开信件")));
        String sceneId = saved.path("document").path("scenes").get(0).path("id").asText();
        ObjectNode request = runRequest(
                3, "episode_script_revise", List.of(sceneId), "只修改所选场次");

        assertThat(runs.start(userId, episodeId, request).path("runId").asText())
                .isNotBlank();
        ObjectNode wrong = runRequest(
                3, "episode_script_revise", List.of("foreign-scene"), "修改错误场次");
        assertCode(
                () -> runs.start(userId, episodeId, wrong),
                "VIDEO_SCRIPT_SCENE_SCOPE_INVALID");
        ObjectNode stale = runRequest(
                2, "episode_script_generate", List.of(), "使用过期工作稿");
        assertCode(
                () -> runs.start(userId, episodeId, stale),
                "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT");
    }

    @Test
    void 超量来源明确拒绝且不创建Run或命令回执() {
        String episodeId = episode("超长取材").path("id").asText();
        String firstText = "甲".repeat(110_000);
        String secondText = "乙".repeat(110_000);
        String secondChapter = "chapter-" + UUID.randomUUID();
        database.dsl().execute(
                "UPDATE \"Chapter\" SET content=? WHERE id=?", firstText, chapterId);
        database.dsl().execute(
                "INSERT INTO \"Chapter\""
                        + "(id,\"novelId\",title,content,\"order\",\"updatedAt\")"
                        + " VALUES (?,?,'长章二',?,2,'2026-09-10 00:00:00')",
                secondChapter,
                novelId,
                secondText);
        ObjectNode sourceRequest = object(
                "clientRequestId", key(),
                "expectedRevision", 1,
                "basedOnVersionId", null,
                "sources", List.of(
                        sourceSelection(chapterId, firstText),
                        sourceSelection(secondChapter, secondText)));
        episodes.createSourceSet(userId, episodeId, sourceRequest);
        ObjectNode request = runRequest(
                2, "episode_script_generate", List.of(), "完整保留取材，不得截断");

        assertCode(
                () -> runs.start(userId, episodeId, request),
                "VIDEO_SCRIPT_CONTEXT_TOO_LARGE");
        assertThat(database.dsl().fetchOne(
                        "SELECT count(*) AS n FROM \"WorkflowRun\" WHERE \"userId\" = ?",
                        userId)
                .get("n", Integer.class))
                .isZero();
        assertThat(database.dsl().fetchOne(
                        """
                        SELECT count(*) AS n
                        FROM "VideoEpisodeCommand"
                        WHERE "actorUserId" = ? AND "clientRequestId" = ?
                        """,
                        userId,
                        request.path("clientRequestId").asText())
                .get("n", Integer.class))
                .isZero();
    }

    private ObjectNode episode(String title) {
        return episodes.create(
                userId,
                projectId,
                object("clientRequestId", key(), "title", title));
    }

    private ObjectNode sourceRequest(int revision) {
        return object(
                "clientRequestId", key(),
                "expectedRevision", revision,
                "basedOnVersionId", null,
                "sources", List.of(object(
                        "chapterId", chapterId,
                        "expectedUpdatedAt", "2026-09-10T00:00:00Z",
                        "sourceHash", sha("甲😀乙\n交信"),
                        "ranges", List.of(object("start", 1, "end", 2)))));
    }

    private ObjectNode sourceSelection(String id, String text) {
        return object(
                "chapterId", id,
                "expectedUpdatedAt", "2026-09-10T00:00:00Z",
                "sourceHash", sha(text),
                "ranges", List.of(object("start", 0, "end", text.codePointCount(0, text.length()))));
    }

    private ObjectNode runRequest(
            int revision, String operation, List<String> sceneIds, String instruction) {
        return object(
                "clientRequestId", key(),
                "expectedDraftRevision", revision,
                "operation", operation,
                "selectedSceneIds", sceneIds,
                "instruction", instruction);
    }

    private static ObjectNode document(String text) {
        return object(
                "schemaVersion", "video-episode-script/1.0",
                "overview", object(
                        "summary", "信件承接",
                        "creativeIntent", "",
                        "targetDurationSeconds", null),
                "scenes", List.of(object(
                        "id", null,
                        "tempKey", "scene-new",
                        "title", "室内",
                        "locationLabel", "旧屋",
                        "timeLabel", "翌日",
                        "narrativeTime", "现在",
                        "characterIds", List.of(),
                        "lines", List.of(object(
                                "id", null,
                                "tempKey", "line-new",
                                "kind", "action",
                                "speakerId", null,
                                "text", text,
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

    private static String sha(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static void assertCode(Runnable action, String expected) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(
                        ApiException.class,
                        exception -> assertThat(exception.code()).isEqualTo(expected));
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
}
