package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
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
        var registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        var workflows = new DurableWorkflowService(
                new JooqWorkflowStartRepository(database, ids, clock, JSON));
        CoreSettings settings = CoreSettings.from(Map.of(
                "ENVIRONMENT", "test",
                "DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true",
                "DURABLE_AGENT_EXECUTION_ROUTE_MODE", "all",
                "V1_FRESH_AGENT_STARTS_ENABLED", "false",
                "VIDEO_PREVIEW_ENABLED", "true",
                "VIDEO_DISPATCH_ENABLED", "true",
                "VIDEO_DISPATCH_NAMESPACE", "episode-script-test"));
        runs = new JooqVideoEpisodeScriptRunStore(
                database, ids, settings, registry, () -> workflows, JSON);
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
