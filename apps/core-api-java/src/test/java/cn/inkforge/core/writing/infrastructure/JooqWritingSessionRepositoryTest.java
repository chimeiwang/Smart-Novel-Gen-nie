package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGMESSAGE;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.CreateMessageRequest;
import cn.inkforge.contracts.api.CreateWritingSessionRequest;
import cn.inkforge.contracts.api.UpdateWritingSessionRequest;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullable;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqWritingSessionRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-25T01:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T07:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_writing_session_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqWritingSessionRepository repository;
    private static ObjectMapper json;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void rebuildSchema() throws Exception {
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
        json = new ObjectMapper();
        repository = new JooqWritingSessionRepository(
                database, new CuidV1Generator(CLOCK), CLOCK, json);
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            database.dsl().deleteFrom(NOVEL).where(NOVEL.USERID.in(users)).execute();
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 会话消息必须完整保存且列表用稳定顺序聚合最后消息() {
        Fixture fixture = fixture("writing-session-list");
        var session = repository.create(
                fixture.userId(),
                new CreateWritingSessionRequest(fixture.chapterId(), fixture.novelId())
                        .title("  第一章讨论  "));
        CreateMessageRequest first = new CreateMessageRequest(
                        "甲😀乙\n完整消息",
                        CreateMessageRequest.RoleEnum.USER)
                .metadata(Map.of("来源", List.of("章节", 1)));
        repository.addMessage(fixture.userId(), session.getId(), first);
        repository.addMessage(
                fixture.userId(),
                session.getId(),
                new CreateMessageRequest("最后消息", CreateMessageRequest.RoleEnum.AGENT)
                        .agentId("写作"));

        var listed = repository.list(fixture.userId(), fixture.novelId(), null);
        var detail = repository.get(fixture.userId(), session.getId());

        assertThat(session.getTitle()).isEqualTo("  第一章讨论  ");
        assertThat(listed).singleElement().satisfies(value -> {
            assertThat(value.getMessageCount()).isEqualTo(2);
            assertThat(value.getLastMessage().getContent()).isEqualTo("最后消息");
            assertThat(value.getLastMessage().getRole()).isEqualTo("agent");
            assertThat(value.getLastMessage().getAgentId()).isEqualTo("写作");
        });
        assertThat(detail.getMessages()).extracting(value -> value.getContent())
                .containsExactly("甲😀乙\n完整消息", "最后消息");
        assertThat(detail.getMessages().getFirst().getMetadata().get())
                .isEqualTo(Map.of("来源", List.of("章节", 1)));
    }

    @Test
    void 会话详情必须按阶段优先级恢复当前任务并返回最新历史任务() {
        Fixture fixture = fixture("writing-session-recovery");
        var session = repository.create(
                fixture.userId(),
                new CreateWritingSessionRequest(fixture.chapterId(), fixture.novelId()));
        insertTask(
                fixture,
                session.getId(),
                "task-active-newer",
                Writingtaskphase.active,
                INITIAL.plusSeconds(3),
                graph(fixture, "task-active-newer", "write_chapter", "drafting", null),
                null);
        insertTask(
                fixture,
                session.getId(),
                "task-review-older",
                Writingtaskphase.awaiting_user_review,
                INITIAL.plusSeconds(2),
                graph(
                        fixture,
                        "task-review-older",
                        "review_chapter",
                        "reviewing",
                        "artifact-1"),
                null);
        insertTask(
                fixture,
                session.getId(),
                "task-completed",
                Writingtaskphase.completed,
                INITIAL.plusSeconds(4),
                null,
                null);

        var detail = repository.get(fixture.userId(), session.getId());

        assertThat(detail.getCurrentTask().getId()).isEqualTo("task-review-older");
        assertThat(detail.getCurrentTask().getHasAwaitingReviewArtifact()).isTrue();
        assertThat(detail.getCurrentTask().getCurrentOperation())
                .containsEntry("kind", "review_chapter");
        assertThat(detail.getCurrentTask().getOperationStage()).isEqualTo("reviewing");
        assertThat(detail.getCurrentTask().getActiveArtifactId()).isEqualTo("artifact-1");
        assertThat(detail.getLastTask().getId()).isEqualTo("task-completed");
    }

    @Test
    void 显式null更新必须忽略而空补丁仍推进时间戳() {
        Fixture fixture = fixture("writing-session-update");
        var session = repository.create(
                fixture.userId(),
                new CreateWritingSessionRequest(fixture.chapterId(), fixture.novelId())
                        .title("保留标题"));
        UpdateWritingSessionRequest explicitNull = new UpdateWritingSessionRequest();
        explicitNull.setTitle(JsonNullable.of(null));

        var first = repository.update(fixture.userId(), session.getId(), explicitNull);
        var second = repository.update(
                fixture.userId(), session.getId(), new UpdateWritingSessionRequest());

        assertThat(first.getTitle()).isEqualTo("保留标题");
        assertThat(second.getTitle()).isEqualTo("保留标题");
        assertThat(second.getUpdatedAt()).isAfter(first.getUpdatedAt());
    }

    @Test
    void 损坏历史metadata只降级为null且删除会话不能删除正式章节() {
        Fixture fixture = fixture("writing-session-corrupt");
        var session = repository.create(
                fixture.userId(),
                new CreateWritingSessionRequest(fixture.chapterId(), fixture.novelId()));
        repository.addMessage(
                fixture.userId(),
                session.getId(),
                new CreateMessageRequest("消息", CreateMessageRequest.RoleEnum.SYSTEM));
        database.dsl().update(WRITINGMESSAGE)
                .set(WRITINGMESSAGE.METADATA, "{损坏")
                .where(WRITINGMESSAGE.SESSIONID.eq(session.getId()))
                .execute();

        assertThat(repository.get(fixture.userId(), session.getId())
                        .getMessages().getFirst().getMetadata().get())
                .isNull();
        repository.delete(fixture.userId(), session.getId());

        assertThat(database.dsl().fetchCount(
                        WRITINGSESSION, WRITINGSESSION.ID.eq(session.getId())))
                .isZero();
        assertThat(database.dsl().fetchCount(CHAPTER, CHAPTER.ID.eq(fixture.chapterId())))
                .isEqualTo(1);
    }

    @Test
    void 创建必须拒绝跨小说章节且会话接口隐藏其他用户资源() {
        Fixture fixture = fixture("writing-session-owner");
        Fixture other = fixture("writing-session-other");
        assertThatThrownBy(() -> repository.create(
                        fixture.userId(),
                        new CreateWritingSessionRequest(
                                other.chapterId(), fixture.novelId())))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("CHAPTER_NOT_FOUND"));
        var session = repository.create(
                fixture.userId(),
                new CreateWritingSessionRequest(fixture.chapterId(), fixture.novelId()));
        assertThatThrownBy(() -> repository.get(other.userId(), session.getId()))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_SESSION_FORBIDDEN"));
        assertThatThrownBy(() -> repository.list(
                        other.userId(), fixture.novelId(), null))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("NOVEL_FORBIDDEN"));
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
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, prefix)
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, "正文")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
        return new Fixture(userId, novelId, chapterId);
    }

    private void insertTask(
            Fixture fixture,
            String sessionId,
            String taskId,
            Writingtaskphase phase,
            LocalDateTime updatedAt,
            String graph,
            String generatedContent) {
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, fixture.novelId())
                .set(WRITINGTASK.CHAPTERID, fixture.chapterId())
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "[]")
                .set(WRITINGTASK.PHASE, phase)
                .set(WRITINGTASK.GRAPHSTATEJSON, graph)
                .set(WRITINGTASK.GENERATEDCONTENT, generatedContent)
                .set(WRITINGTASK.WRITINGSESSIONID, sessionId)
                .set(WRITINGTASK.CREATEDAT, INITIAL)
                .set(WRITINGTASK.UPDATEDAT, updatedAt)
                .execute();
    }

    private String graph(
            Fixture fixture,
            String taskId,
            String operation,
            String stage,
            String artifactId) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("taskId", taskId);
        value.put("userId", fixture.userId());
        value.put("novelId", fixture.novelId());
        value.put("chapterId", fixture.chapterId());
        value.put("targetWordCount", 4_000);
        value.put("conversationHistory", List.of());
        value.put("currentOperation", Map.of("kind", operation));
        value.put("operationStage", stage);
        Map<String, Object> review = new LinkedHashMap<>();
        review.put("activeArtifactId", artifactId);
        value.put("artifactReview", review);
        return json.writeValueAsString(value);
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
