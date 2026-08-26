package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.CHAPTERWRITINGGOAL;
import static cn.inkforge.core.db.generated.Tables.FORESHADOWING;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Foreshadowingstatus;
import cn.inkforge.core.db.generated.enums.Outlinenodekind;
import cn.inkforge.core.db.generated.enums.Outlinenodestatus;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
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

@Testcontainers
class JooqWritingContextRepositoryTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-08-25T09:00:00.000");

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_context_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static ObjectMapper json;
    private static JooqWritingContextRepository repository;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void rebuildSchema() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        json = new ObjectMapper();
        repository = new JooqWritingContextRepository(database, json);
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 工具任务绑定和写命令活性必须同时匹配用户小说与任务() {
        Fixture fixture = fixture("context-auth");
        insertTask(fixture, "task-1", null);
        insertCommand(fixture, "task-1", "command-active", "processing", Map.of());

        repository.requireBinding(fixture.userId(), fixture.novelId(), "task-1");
        repository.requireWritingJob(
                fixture.userId(), fixture.novelId(), "task-1", "command-active");

        assertThatThrownBy(() -> repository.requireBinding(
                        "stranger", fixture.novelId(), "task-1"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("WRITING_TASK_FORBIDDEN");
                });
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .where(WRITINGRUNCOMMAND.ID.eq("command-active"))
                .execute();
        assertThatThrownBy(() -> repository.requireWritingJob(
                        fixture.userId(), fixture.novelId(), "task-1", "command-active"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("WRITING_JOB_MISMATCH");
                });
    }

    @Test
    void 规划上下文完整聚合权威计划冻结来源对话与活动草案() {
        Fixture fixture = fixture("context-full");
        String taskId = "context-full-task";
        Map<String, Object> graph = graph(fixture, taskId, "artifact-1");
        insertTask(fixture, taskId, graph);
        insertOutline(fixture);
        insertPlan(fixture);
        insertArtifact(fixture, taskId);
        Map<String, Object> binding = sourceBinding();
        insertCommand(
                fixture,
                taskId,
                "context-full-command",
                "processing",
                Map.of(
                        "version", 1,
                        "resume", false,
                        "sourceBindings", List.of(binding)));

        Map<String, Object> context = repository.planningContext(fixture.userId(), taskId);

        assertThat(context)
                .containsEntry("taskId", taskId)
                .containsEntry("novelId", fixture.novelId())
                .containsEntry("chapterId", fixture.chapterId())
                .containsEntry("chapterOrder", 3)
                .containsEntry("phase", "active")
                .containsEntry("targetWordCount", 4_000)
                .containsEntry("userMessage", "继续推进");
        assertThat(context.get("conversationHistory"))
                .isEqualTo(List.of(
                        Map.of("role", "user", "content", "旧问题"),
                        Map.of("role", "agent", "content", "旧回答")));
        assertThat(map(context.get("chapterGoal")))
                .containsEntry("narrativeGoal", "迫使主角做出选择");
        assertThat(list(map(context.get("approvedBeatPlan")).get("sceneBeats")))
                .singleElement()
                .satisfies(scene -> assertThat(map(scene))
                        .containsEntry("goal", "进入藏书楼")
                        .containsEntry("conflict", "守门人拒绝放行"));
        assertThat(map(context.get("chapterGroup")))
                .containsEntry("title", "第一幕")
                .containsEntry("content", "章节组完整内容");
        assertThat(list(context.get("outlinePath")))
                .singleElement()
                .satisfies(node -> assertThat(map(node)).containsEntry("title", "开端"));
        assertThat(list(context.get("foreshadowingSummaries")))
                .singleElement()
                .satisfies(value -> {
                    assertThat(map(value)).containsEntry("name", "断裂墨印");
                    assertThat(map(value)).doesNotContainKey("plantedContent");
                });
        assertThat(map(context.get("activeArtifact")))
                .containsEntry("id", "artifact-1")
                .containsEntry("payload", Map.of("kind", "chapter_draft", "content", "完整草案"));
        assertThat(context.get("sourceBindings")).isEqualTo(List.of(binding));
        assertThat(context.get("graphState")).isEqualTo(graph);
    }

    @Test
    void 重叠章节组必须阻断上下文而不是任意选择一个() {
        Fixture fixture = fixture("context-overlap");
        insertTask(fixture, "task-overlap", null);
        outlineNode("group-a", fixture.novelId(), null, "甲组", 2, 4, Outlinenodekind.chapter_group);
        outlineNode("group-b", fixture.novelId(), null, "乙组", 3, 5, Outlinenodekind.chapter_group);

        assertThatThrownBy(() -> repository.planningContext(
                        fixture.userId(), "task-overlap"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("CHAPTER_GROUP_MAPPING_CONFLICT");
                });
    }

    private Fixture fixture(String prefix) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        users.add(userId);
        database.dsl().insertInto(USER)
                .set(USER.ID, userId)
                .set(USER.USERNAME, userId)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREDITBALANCEMICROS, 1_000_000L)
                .set(USER.CREATEDAT, NOW)
                .set(USER.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, prefix)
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, NOW)
                .set(NOVEL.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第三章")
                .set(CHAPTER.CONTENT, "当前正文")
                .set(CHAPTER.ORDER, 3)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, NOW)
                .set(CHAPTER.UPDATEDAT, NOW)
                .execute();
        return new Fixture(userId, novelId, chapterId);
    }

    private void insertTask(Fixture fixture, String taskId, Map<String, Object> graph) {
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, fixture.novelId())
                .set(WRITINGTASK.CHAPTERID, fixture.chapterId())
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "设定,写作")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.CONVERSATIONHISTORY, json.writeValueAsString(List.of(
                        Map.of("role", "user", "content", "旧问题"),
                        Map.of("role", "agent", "content", "旧回答"),
                        Map.of("role", "user", "content", "继续推进"))))
                .set(
                        WRITINGTASK.GRAPHSTATEJSON,
                        graph == null ? null : json.writeValueAsString(graph))
                .set(WRITINGTASK.CREATEDAT, NOW)
                .set(WRITINGTASK.UPDATEDAT, NOW)
                .execute();
    }

    private void insertOutline(Fixture fixture) {
        outlineNode(
                "stage-1", fixture.novelId(), null, "开端", null, null, Outlinenodekind.stage);
        outlineNode(
                "group-1",
                fixture.novelId(),
                "stage-1",
                "第一幕",
                1,
                5,
                Outlinenodekind.chapter_group);
        database.dsl().insertInto(FORESHADOWING)
                .set(FORESHADOWING.ID, "foreshadowing-1")
                .set(FORESHADOWING.NOVELID, fixture.novelId())
                .set(FORESHADOWING.NAME, "断裂墨印")
                .set(FORESHADOWING.STATUS, Foreshadowingstatus.active)
                .set(FORESHADOWING.PLANTEDAT, "第一章")
                .set(FORESHADOWING.PLANTEDCONTENT, "完整埋伏正文")
                .set(FORESHADOWING.EXPECTEDPAYOFF, "第五章")
                .set(FORESHADOWING.CREATEDAT, NOW)
                .set(FORESHADOWING.UPDATEDAT, NOW)
                .execute();
    }

    private void outlineNode(
            String id,
            String novelId,
            String parentId,
            String title,
            Integer start,
            Integer end,
            Outlinenodekind kind) {
        database.dsl().insertInto(OUTLINENODE)
                .set(OUTLINENODE.ID, id)
                .set(OUTLINENODE.NOVELID, novelId)
                .set(OUTLINENODE.PARENTID, parentId)
                .set(OUTLINENODE.TITLE, title)
                .set(OUTLINENODE.CONTENT, kind == Outlinenodekind.chapter_group
                        ? "章节组完整内容"
                        : "阶段内容")
                .set(OUTLINENODE.ORDER, 1)
                .set(OUTLINENODE.STATUS, Outlinenodestatus.in_progress)
                .set(OUTLINENODE.KIND, kind)
                .set(OUTLINENODE.CHAPTERSTARTORDER, start)
                .set(OUTLINENODE.CHAPTERENDORDER, end)
                .set(OUTLINENODE.CREATEDAT, NOW)
                .set(OUTLINENODE.UPDATEDAT, NOW)
                .execute();
    }

    private void insertPlan(Fixture fixture) {
        database.dsl().insertInto(CHAPTERWRITINGGOAL)
                .set(CHAPTERWRITINGGOAL.ID, "goal-1")
                .set(CHAPTERWRITINGGOAL.NOVELID, fixture.novelId())
                .set(CHAPTERWRITINGGOAL.CHAPTERID, fixture.chapterId())
                .set(CHAPTERWRITINGGOAL.NARRATIVEGOAL, "迫使主角做出选择")
                .set(CHAPTERWRITINGGOAL.DESIREDEMOTION, "压迫")
                .set(CHAPTERWRITINGGOAL.WORDCOUNTMIN, 3_000)
                .set(CHAPTERWRITINGGOAL.WORDCOUNTMAX, 5_000)
                .set(CHAPTERWRITINGGOAL.CREATEDAT, NOW)
                .set(CHAPTERWRITINGGOAL.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(CHAPTERBEATPLAN)
                .set(CHAPTERBEATPLAN.ID, "plan-1")
                .set(CHAPTERBEATPLAN.CHAPTERID, fixture.chapterId())
                .set(CHAPTERBEATPLAN.GOALID, "goal-1")
                .set(CHAPTERBEATPLAN.STATUS, Beatplanstatus.approved)
                .set(CHAPTERBEATPLAN.CHAPTERGOAL, "进入藏书楼")
                .set(CHAPTERBEATPLAN.MAINPLOTCONNECTION, "接续追查")
                .set(CHAPTERBEATPLAN.CHAPTERACCEPTANCECRITERIA, "获得线索")
                .set(CHAPTERBEATPLAN.TOTALESTIMATEDWORDS, 4_000)
                .set(CHAPTERBEATPLAN.GENERATEDBY, "剧情")
                .set(CHAPTERBEATPLAN.CREATEDAT, NOW)
                .set(CHAPTERBEATPLAN.UPDATEDAT, NOW)
                .execute();
        database.dsl().insertInto(SCENEBEAT)
                .set(SCENEBEAT.ID, "scene-1")
                .set(SCENEBEAT.BEATPLANID, "plan-1")
                .set(SCENEBEAT.ORDER, 1)
                .set(SCENEBEAT.GOAL, "进入藏书楼")
                .set(SCENEBEAT.CONFLICT, "守门人拒绝放行")
                .set(SCENEBEAT.CHARACTERS, "[\"沈墨\"]")
                .set(SCENEBEAT.FORESHADOWINGREFS, "[\"断裂墨印\"]")
                .set(SCENEBEAT.ESTIMATEDWORDS, 800)
                .set(SCENEBEAT.ACCEPTANCECRITERIA, "成功进入")
                .execute();
    }

    private void insertArtifact(Fixture fixture, String taskId) {
        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, "artifact-1")
                .set(REVIEWARTIFACT.NOVELID, fixture.novelId())
                .set(REVIEWARTIFACT.CHAPTERID, fixture.chapterId())
                .set(REVIEWARTIFACT.TASKID, taskId)
                .set(REVIEWARTIFACT.ARTIFACTKEY, "chapter-draft")
                .set(REVIEWARTIFACT.KIND, Reviewartifactkind.chapter_draft)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.under_review)
                .set(REVIEWARTIFACT.TITLE, "正文草案")
                .set(REVIEWARTIFACT.SUMMARY, "首版")
                .set(
                        REVIEWARTIFACT.PAYLOADJSON,
                        json.writeValueAsString(Map.of(
                                "kind", "chapter_draft", "content", "完整草案")))
                .set(REVIEWARTIFACT.DIFFJSON, "{\"changed\":true}")
                .set(REVIEWARTIFACT.CREATEDBYAGENT, "写作")
                .set(REVIEWARTIFACT.REVIEWERAGENT, "校验")
                .set(REVIEWARTIFACT.REVISION, 2)
                .set(REVIEWARTIFACT.CREATEDAT, NOW)
                .set(REVIEWARTIFACT.UPDATEDAT, NOW)
                .execute();
    }

    private void insertCommand(
            Fixture fixture,
            String taskId,
            String commandId,
            String status,
            Map<String, Object> payload) {
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, commandId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, json.writeValueAsString(payload))
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, fixture.userId() + ":" + commandId)
                .set(WRITINGRUNCOMMAND.STATUS, status)
                .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, NOW)
                .set(WRITINGRUNCOMMAND.CREATEDAT, NOW)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, NOW)
                .execute();
    }

    private static Map<String, Object> graph(
            Fixture fixture, String taskId, String artifactId) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("taskId", taskId);
        value.put("userId", fixture.userId());
        value.put("novelId", fixture.novelId());
        value.put("chapterId", fixture.chapterId());
        value.put("targetWordCount", 4_000);
        value.put("conversationHistory", List.of());
        value.put("activeArtifactId", artifactId);
        value.put("eventSequence", 0);
        return value;
    }

    private static Map<String, Object> sourceBinding() {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("resourceType", "chapter");
        value.put("resourceId", "context-full-chapter");
        value.put("exists", true);
        value.put("updatedAt", "2026-08-25T09:00:00Z");
        value.put("contentSha256", "a".repeat(64));
        value.put("revision", null);
        value.put("absenceSentinel", null);
        return value;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) {
        return (Map<String, Object>) value;
    }

    private static List<?> list(Object value) {
        return (List<?>) value;
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

    private record Fixture(String userId, String novelId, String chapterId) {}
}
