package cn.inkforge.core.reviews.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTEVALUATION;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ArtifactConflictQuarantineRequest;
import cn.inkforge.contracts.api.ArtifactDecisionAcceptedResponse;
import cn.inkforge.contracts.api.CreateArtifactRequest;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.contracts.api.SubmitArtifactEvaluationRequest;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.domain.ReviewArtifactRules;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
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
import tools.jackson.databind.JsonNode;

@Testcontainers
class JooqReviewRepositoryTest {

    private static final LocalDateTime INITIAL = LocalDateTime.parse("2026-08-25T01:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T07:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_review_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqReviewRepository repository;
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
        repository = new JooqReviewRepository(
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
    void 迁移前结构显式V2决定必须在任何V2查询前稳定拒绝() {
        ReviewArtifactDecisionRequest request = new ReviewArtifactDecisionRequest(
                        "pre-schema-v2-decision-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.DISCARD,
                        1)
                .engineVersion(ReviewArtifactDecisionRequest.EngineVersionEnum.NUMBER_2);

        assertThatThrownBy(() -> repository.decide(
                        "pre-schema-user", "pre-schema-artifact", request))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code()).isEqualTo("DURABLE_WORKFLOW_SCHEMA_UNAVAILABLE");
                });
    }

    @Test
    void 创建与修订必须绑定当前job追加不可变历史并隐藏控制字段() throws Exception {
        Fixture fixture = fixture("review-lifecycle", "完整章节正文");
        CreateArtifactRequest createdRequest = request(
                fixture, "chapter:main", "初稿", null, "under_review");

        var created = repository.createOrRevise(createdRequest);
        CreateArtifactRequest revisedRequest = request(
                fixture, "chapter:main", "修订稿", created.getRevision(), "awaiting_user");
        var revised = repository.createOrRevise(revisedRequest);

        assertThat(created.getRevision()).isEqualTo(1);
        assertThat(created.getEngineVersion().getValue()).isEqualTo(1);
        assertThat(revised.getRevision()).isEqualTo(2);
        assertThat(revised.getPayload()).containsEntry("content", "修订稿");
        assertThat(revised.getPayload()).doesNotContainKey("_inkforgeControl");
        assertThat(revised.getSourceBindingStatus().getValue()).isEqualTo("verified");
        assertThat(revised.getSourceBindings()).singleElement()
                .extracting(value -> value.getResourceId())
                .isEqualTo(fixture.chapterId());
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACTREVISION,
                        REVIEWARTIFACTREVISION.ARTIFACTID.eq(created.getId())))
                .isEqualTo(2);
        assertThatThrownBy(() -> repository.createOrRevise(request(
                        fixture, "chapter:main", "过期修订", 1, "awaiting_user")))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("ARTIFACT_REVISION_CONFLICT"));
    }

    @Test
    void 选区草案必须从数据库权威正文按码点物化完整diff() throws Exception {
        Fixture fixture = fixture("review-selection", "甲😀乙丙");
        OffsetDateTime updatedAt = DatabaseTimestamp.api(INITIAL);
        Map<String, Object> target = new LinkedHashMap<>();
        target.put("mode", "replace_selection");
        target.put("resourceType", "chapter_content");
        target.put("resourceId", fixture.chapterId());
        target.put("baseUpdatedAt", updatedAt.toString());
        target.put("baseContentHash", ReviewArtifactRules.sha256("甲😀乙丙"));
        target.put("selectionStart", 1);
        target.put("selectionEnd", 3);
        target.put("selectedTextHash", ReviewArtifactRules.sha256("😀乙"));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", "chapter_draft");
        payload.put("target", target);
        payload.put("replacement", "新段");
        CreateArtifactRequest request = baseRequest(
                fixture, "chapter:selection", payload, "awaiting_user");

        var response = repository.createOrRevise(request);

        assertThat(response.getPayload())
                .containsEntry("selectedText", "😀乙")
                .containsEntry("candidate", "甲新段丙");
        assertThat(response.getDiff().isPresent()).isTrue();
        @SuppressWarnings("unchecked")
        Map<String, Object> diff = (Map<String, Object>) response.getDiff().get();
        assertThat(diff).containsEntry("before", "甲😀乙丙").containsEntry("after", "甲新段丙");
    }

    @Test
    void 复审必须幂等且冲突隔离不得增加修订号() throws Exception {
        Fixture fixture = fixture("review-evaluation", "正文");
        var artifact = repository.createOrRevise(request(
                fixture, "chapter:evaluation", "初稿", null, "under_review"));
        SubmitArtifactEvaluationRequest evaluation = new SubmitArtifactEvaluationRequest(
                SubmitArtifactEvaluationRequest.EvaluatorAgentEnum.fromValue("编辑"),
                fixture.jobId(),
                fixture.novelId(),
                1,
                "run-1",
                "需要调整节奏",
                fixture.taskId(),
                SubmitArtifactEvaluationRequest.VerdictEnum.REVISE)
                .requiredChanges("缩短开场");

        repository.submitEvaluation(artifact.getId(), evaluation);
        var replay = repository.submitEvaluation(artifact.getId(), evaluation);

        assertThat(replay.getEvaluations()).singleElement()
                .extracting(value -> value.getSummary())
                .isEqualTo("需要调整节奏");
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACTEVALUATION,
                        REVIEWARTIFACTEVALUATION.ARTIFACTID.eq(artifact.getId())))
                .isEqualTo(1);
        evaluation.setSummary("不同结论");
        assertThatThrownBy(() -> repository.submitEvaluation(artifact.getId(), evaluation))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("ARTIFACT_EVALUATION_CONFLICT"));

        var quarantined = repository.quarantine(
                artifact.getId(),
                new ArtifactConflictQuarantineRequest(
                        fixture.jobId(), fixture.novelId(), "run-1", fixture.taskId()));
        assertThat(quarantined.getStatus()).isEqualTo("awaiting_user");
        assertThat(quarantined.getRevision()).isEqualTo(1);
        assertThat(database.dsl().select(REVIEWARTIFACT.REVISION)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(artifact.getId()))
                        .fetchSingle(REVIEWARTIFACT.REVISION))
                .isEqualTo(1);
    }

    @Test
    void 读取分页与任务活动草案必须隔离用户并保持稳定顺序() throws Exception {
        Fixture fixture = fixture("review-list", "正文");
        String stranger = user("review-list-stranger");
        var first = repository.createOrRevise(request(
                fixture, "chapter:list:1", "第一份", null, "awaiting_user"));
        var second = repository.createOrRevise(request(
                fixture, "chapter:list:2", "第二份", null, "awaiting_user"));

        var page = repository.list(
                fixture.userId(), fixture.novelId(), null, null, null, null, null, 1);
        assertThat(page.getItems()).hasSize(1);
        assertThat(page.getNextCursor()).isNotBlank();
        var next = repository.list(
                fixture.userId(),
                fixture.novelId(),
                null,
                null,
                null,
                null,
                page.getNextCursor(),
                1);
        assertThat(next.getItems()).hasSize(1);
        assertThat(next.getItems().getFirst().getId())
                .isNotEqualTo(page.getItems().getFirst().getId());
        assertThat(repository.getTaskArtifact(fixture.userId(), fixture.taskId()))
                .isNotNull();
        assertThatThrownBy(() -> repository.get(stranger, first.getId()))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("REVIEW_ARTIFACT_FORBIDDEN"));
        assertThatThrownBy(() -> repository.getTaskArtifact(stranger, fixture.taskId()))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("WRITING_TASK_NOT_FOUND"));
        assertThat(List.of(first.getId(), second.getId())).doesNotHaveDuplicates();
    }

    @Test
    void 批准正文必须与正式写入和命令原子提交并支持精确重放() throws Exception {
        Fixture fixture = fixture("review-decision", "旧正文");
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, json.writeValueAsString(Map.of(
                        "job", Map.of(
                                "workflow", "long_serial",
                                "operation", "write_chapter",
                                "sourceBindings", realisticChapterBindings(fixture, "旧正文")))))
                .where(WRITINGRUNCOMMAND.ID.eq(fixture.jobId()))
                .execute();
        var artifact = repository.createOrRevise(request(
                fixture, "chapter:decision", "模型正文", null, "awaiting_user"));
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .where(WRITINGRUNCOMMAND.ID.eq(fixture.jobId()))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.awaiting_user_review)
                .where(WRITINGTASK.ID.eq(fixture.taskId()))
                .execute();
        ReviewArtifactDecisionRequest request = new ReviewArtifactDecisionRequest(
                        "review-decision-request-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.APPROVE,
                        artifact.getRevision())
                .editedContent("用户确认后的正文")
                .userMessage("继续写下一步");

        var accepted = (ArtifactDecisionAcceptedResponse)
                repository.decide(fixture.userId(), artifact.getId(), request);
        var replay = repository.decide(fixture.userId(), artifact.getId(), request);

        assertThat(replay).isEqualTo(accepted);
        assertThat(accepted.getStatus().getValue()).isEqualTo("pending");
        assertThat(accepted.getSavedCount()).isEqualTo(1);
        assertThat(database.dsl().select(CHAPTER.CONTENT)
                        .from(CHAPTER)
                        .where(CHAPTER.ID.eq(fixture.chapterId()))
                        .fetchSingle(CHAPTER.CONTENT))
                .isEqualTo("用户确认后的正文");
        assertThat(database.dsl().fetchCount(
                        CHAPTERQUALITYCHECK,
                        CHAPTERQUALITYCHECK.CHAPTERID.eq(fixture.chapterId())))
                .isEqualTo(1);
        assertThat(database.dsl().select(REVIEWARTIFACT.STATUS)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(artifact.getId()))
                        .fetchSingle(REVIEWARTIFACT.STATUS)
                        .getLiteral())
                .isEqualTo("applied");
        assertThat(database.dsl().fetchCount(
                        WRITINGRUNCOMMAND,
                        WRITINGRUNCOMMAND.ARTIFACTID.eq(artifact.getId())
                                .and(WRITINGRUNCOMMAND.KIND.eq("artifact_decision"))))
                .isEqualTo(1);

        ReviewArtifactDecisionRequest collision = new ReviewArtifactDecisionRequest(
                request.getClientRequestId(),
                ReviewArtifactDecisionRequest.DecisionEnum.REVISE,
                artifact.getRevision());
        assertThatThrownBy(() -> repository.decide(
                        fixture.userId(), artifact.getId(), collision))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
    }

    @Test
    void 批准选区必须按Unicode码点替换且不能退化为全文覆盖() throws Exception {
        Fixture fixture = fixture("review-selection-decision", "甲😀乙丙");
        OffsetDateTime updatedAt = DatabaseTimestamp.api(INITIAL);
        Map<String, Object> target = new LinkedHashMap<>();
        target.put("mode", "replace_selection");
        target.put("resourceType", "chapter_content");
        target.put("resourceId", fixture.chapterId());
        target.put("baseUpdatedAt", updatedAt.toString());
        target.put("baseContentHash", ReviewArtifactRules.sha256("甲😀乙丙"));
        target.put("selectionStart", 1);
        target.put("selectionEnd", 3);
        target.put("selectedTextHash", ReviewArtifactRules.sha256("😀乙"));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", "chapter_draft");
        payload.put("target", target);
        payload.put("replacement", "模型替换");
        var artifact = repository.createOrRevise(baseRequest(
                fixture, "chapter:selection-decision", payload, "awaiting_user"));
        readyForDecision(fixture);

        var accepted = (ArtifactDecisionAcceptedResponse) repository.decide(
                fixture.userId(),
                artifact.getId(),
                new ReviewArtifactDecisionRequest(
                                "selection-decision-request-0001",
                                ReviewArtifactDecisionRequest.DecisionEnum.APPROVE,
                                artifact.getRevision())
                        .editedReplacement("用户😀替换"));

        assertThat(accepted.getSavedCount()).isEqualTo(1);
        assertThat(database.dsl().select(CHAPTER.CONTENT)
                        .from(CHAPTER)
                        .where(CHAPTER.ID.eq(fixture.chapterId()))
                        .fetchSingle(CHAPTER.CONTENT))
                .isEqualTo("甲用户😀替换丙");
    }

    @Test
    void 批准大纲和结构化章节计划必须写入各自正式事实() throws Exception {
        Fixture outlineFixture = fixture("review-outline-decision", "正文");
        var outlineArtifact = repository.createOrRevise(baseRequest(
                outlineFixture,
                "outline:decision",
                Map.of("kind", "outline_draft", "content", "正式大纲"),
                "awaiting_user",
                CreateArtifactRequest.KindEnum.OUTLINE_DRAFT));
        readyForDecision(outlineFixture);
        repository.decide(
                outlineFixture.userId(),
                outlineArtifact.getId(),
                new ReviewArtifactDecisionRequest(
                        "outline-decision-request-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.APPROVE,
                        outlineArtifact.getRevision()));
        assertThat(database.dsl().select(OUTLINE.CONTENT)
                        .from(OUTLINE)
                        .where(OUTLINE.NOVELID.eq(outlineFixture.novelId()))
                        .fetchSingle(OUTLINE.CONTENT))
                .isEqualTo("正式大纲");

        Fixture planFixture = fixture("review-plan-decision", "正文");
        Map<String, Object> scene = new LinkedHashMap<>();
        scene.put("goal", "主角发现线索");
        scene.put("characters", "主角、店主");
        scene.put("estimatedWords", 800);
        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("chapterGoal", "拿到第一条关键线索");
        plan.put("totalEstimatedWords", 800);
        plan.put("sceneBeats", List.of(scene));
        var planArtifact = repository.createOrRevise(baseRequest(
                planFixture,
                "beat-plan:decision",
                Map.of("kind", "beat_plan", "beatPlan", plan),
                "awaiting_user",
                CreateArtifactRequest.KindEnum.BEAT_PLAN));
        readyForDecision(planFixture);
        repository.decide(
                planFixture.userId(),
                planArtifact.getId(),
                new ReviewArtifactDecisionRequest(
                        "beat-plan-decision-request-0001",
                        ReviewArtifactDecisionRequest.DecisionEnum.APPROVE,
                        planArtifact.getRevision()));
        assertThat(database.dsl().fetchCount(
                        CHAPTERBEATPLAN,
                        CHAPTERBEATPLAN.CHAPTERID.eq(planFixture.chapterId())
                                .and(CHAPTERBEATPLAN.STATUS.eq(Beatplanstatus.approved))))
                .isEqualTo(1);
        assertThat(database.dsl().select(SCENEBEAT.GOAL)
                        .from(SCENEBEAT)
                        .join(CHAPTERBEATPLAN)
                        .on(CHAPTERBEATPLAN.ID.eq(SCENEBEAT.BEATPLANID))
                        .where(CHAPTERBEATPLAN.CHAPTERID.eq(planFixture.chapterId()))
                        .fetchSingle(SCENEBEAT.GOAL))
                .isEqualTo("主角发现线索");
    }

    @Test
    void 决定命令必须继承显式长篇启动Job而不是降级为简化载荷() throws Exception {
        Fixture fixture = fixture("review-job-inheritance", "正文");
        database.dsl().insertInto(WRITINGSESSION)
                .set(WRITINGSESSION.ID, "writing-session-1")
                .set(WRITINGSESSION.NOVELID, fixture.novelId())
                .set(WRITINGSESSION.CHAPTERID, fixture.chapterId())
                .set(WRITINGSESSION.PHASE, "active")
                .set(WRITINGSESSION.CREATEDAT, INITIAL)
                .set(WRITINGSESSION.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.WRITINGSESSIONID, "writing-session-1")
                .where(WRITINGTASK.ID.eq(fixture.taskId()))
                .execute();
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("schemaVersion", 1);
        metadata.put("clientRequestId", "long-serial-start-request-0001");
        metadata.put("commandKind", "start");
        metadata.put("resourceIdentity", Map.of("taskId", fixture.taskId()));
        metadata.put("normalizedBody", Map.of("workflow", "long_serial"));
        metadata.put("requestFingerprint", "a".repeat(64));
        Map<String, Object> job = new LinkedHashMap<>();
        job.put("version", 1);
        job.put("workflow", "long_serial");
        job.put("operation", "write_chapter");
        job.put("resume", false);
        job.put("chapterId", fixture.chapterId());
        job.put("writingSessionId", "writing-session-1");
        job.put("target", Map.of("type", "chapter", "id", fixture.chapterId()));
        job.put("scope", Map.of("kind", "chapter", "chapterId", fixture.chapterId()));
        job.put("selectedAgents", List.of("写作"));
        job.put("sourceBindings", realisticChapterBindings(fixture, "正文"));
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, json.writeValueAsString(Map.of(
                        "_inkforgeCommand", metadata,
                        "job", job)))
                .where(WRITINGRUNCOMMAND.ID.eq(fixture.jobId()))
                .execute();
        var artifact = repository.createOrRevise(request(
                fixture, "chapter:job-inheritance", "正文草案", null, "awaiting_user"));
        readyForDecision(fixture);

        var accepted = (ArtifactDecisionAcceptedResponse) repository.decide(
                fixture.userId(),
                artifact.getId(),
                new ReviewArtifactDecisionRequest(
                                "job-inheritance-decision-0001",
                                ReviewArtifactDecisionRequest.DecisionEnum.REVISE,
                                artifact.getRevision())
                        .userMessage("请按意见重写"));

        String payloadJson = database.dsl().select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.ID.eq(accepted.getCommandId()))
                .fetchSingle(WRITINGRUNCOMMAND.PAYLOADJSON);
        JsonNode persistedJob = json.readTree(payloadJson).get("job");
        assertThat(persistedJob.get("workflow").asText()).isEqualTo("long_serial");
        assertThat(persistedJob.get("operation").asText()).isEqualTo("write_chapter");
        assertThat(persistedJob.get("selectedAgents").get(0).asText()).isEqualTo("写作");
        assertThat(persistedJob.get("sourceBindings").size()).isEqualTo(3);
        assertThat(persistedJob.get("resume").asBoolean()).isTrue();
        assertThat(persistedJob.get("resumeInput").get("artifactId").asText())
                .isEqualTo(artifact.getId());
        assertThat(persistedJob.get("resumeInput").get("userMessage").asText())
                .isEqualTo("请按意见重写");
    }

    private Fixture fixture(String prefix, String chapterContent) throws Exception {
        String userId = user(prefix + "-user");
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        String taskId = prefix + "-task";
        String jobId = prefix + "-job";
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
                .set(CHAPTER.CONTENT, chapterContent)
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, taskId)
                .set(WRITINGTASK.NOVELID, novelId)
                .set(WRITINGTASK.CHAPTERID, chapterId)
                .set(WRITINGTASK.TARGETWORDCOUNT, 4_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "[]")
                .set(WRITINGTASK.PHASE, Writingtaskphase.active)
                .set(WRITINGTASK.CREATEDAT, INITIAL)
                .set(WRITINGTASK.UPDATEDAT, INITIAL)
                .execute();
        Map<String, Object> binding = new LinkedHashMap<>();
        binding.put("resourceType", "chapter");
        binding.put("resourceId", chapterId);
        binding.put("exists", true);
        binding.put("updatedAt", DatabaseTimestamp.api(INITIAL).toString());
        binding.put("contentSha256", ReviewArtifactRules.sha256(chapterContent));
        binding.put("revision", null);
        binding.put("absenceSentinel", null);
        Map<String, Object> job = new LinkedHashMap<>();
        job.put("workflow", "long_serial");
        job.put("operation", "write_chapter");
        job.put("sourceBindings", List.of(binding));
        database.dsl().insertInto(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.ID, jobId)
                .set(WRITINGRUNCOMMAND.TASKID, taskId)
                .set(WRITINGRUNCOMMAND.KIND, "start")
                .set(WRITINGRUNCOMMAND.PAYLOADJSON, json.writeValueAsString(Map.of("job", job)))
                .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, prefix + "-client-request-0001")
                .set(WRITINGRUNCOMMAND.STATUS, "processing")
                .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, INITIAL)
                .set(WRITINGRUNCOMMAND.CREATEDAT, INITIAL)
                .set(WRITINGRUNCOMMAND.UPDATEDAT, INITIAL)
                .execute();
        return new Fixture(userId, novelId, chapterId, taskId, jobId);
    }

    private String user(String id) {
        users.add(id);
        database.dsl().insertInto(USER)
                .set(USER.ID, id)
                .set(USER.USERNAME, id)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREDITBALANCEMICROS, 1_000_000L)
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private static CreateArtifactRequest request(
            Fixture fixture,
            String artifactKey,
            String content,
            Integer expectedRevision,
            String status) {
        CreateArtifactRequest request = baseRequest(
                fixture,
                artifactKey,
                Map.of("kind", "chapter_draft", "content", content),
                status);
        if (expectedRevision != null) request.setExpectedRevision(JsonNullable.of(expectedRevision));
        return request;
    }

    private static CreateArtifactRequest baseRequest(
            Fixture fixture,
            String artifactKey,
            Map<String, Object> payload,
            String status) {
        return baseRequest(
                fixture,
                artifactKey,
                payload,
                status,
                CreateArtifactRequest.KindEnum.CHAPTER_DRAFT);
    }

    private static CreateArtifactRequest baseRequest(
            Fixture fixture,
            String artifactKey,
            Map<String, Object> payload,
            String status,
            CreateArtifactRequest.KindEnum kind) {
        return new CreateArtifactRequest(
                        CreateArtifactRequest.CreatedByAgentEnum.fromValue("写作"),
                        fixture.jobId(),
                        kind,
                        fixture.novelId(),
                        payload,
                        "run-1",
                        CreateArtifactRequest.StatusEnum.fromValue(status),
                        fixture.taskId())
                .chapterId(fixture.chapterId())
                .artifactKey(artifactKey)
                .title("章节草案")
                .summary("完整摘要");
    }

    private static void readyForDecision(Fixture fixture) {
        database.dsl().update(WRITINGRUNCOMMAND)
                .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                .where(WRITINGRUNCOMMAND.ID.eq(fixture.jobId()))
                .execute();
        database.dsl().update(WRITINGTASK)
                .set(WRITINGTASK.PHASE, Writingtaskphase.awaiting_user_review)
                .where(WRITINGTASK.ID.eq(fixture.taskId()))
                .execute();
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

    private static List<Map<String, Object>> realisticChapterBindings(
            Fixture fixture, String content) {
        Map<String, Object> chapter = new LinkedHashMap<>();
        chapter.put("resourceType", "chapter");
        chapter.put("resourceId", fixture.chapterId());
        chapter.put("exists", true);
        chapter.put("updatedAt", DatabaseTimestamp.api(INITIAL).toString());
        chapter.put("contentSha256", ReviewArtifactRules.sha256(content));
        chapter.put("revision", null);
        chapter.put("absenceSentinel", null);
        Map<String, Object> outline = new LinkedHashMap<>();
        outline.put("resourceType", "outline");
        outline.put("resourceId", "novel:" + fixture.novelId() + ":outline");
        outline.put("exists", false);
        outline.put("updatedAt", null);
        outline.put("contentSha256", null);
        outline.put("revision", null);
        outline.put("absenceSentinel", Map.of(
                "resourceType", "novel", "resourceId", fixture.novelId()));
        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("resourceType", "approved_beat_plan");
        plan.put(
                "resourceId",
                "chapter:" + fixture.chapterId() + ":approved_beat_plan");
        plan.put("exists", false);
        plan.put("updatedAt", null);
        plan.put("contentSha256", null);
        plan.put("revision", null);
        plan.put("absenceSentinel", Map.of(
                "resourceType", "chapter", "resourceId", fixture.chapterId()));
        return List.of(chapter, outline, plan);
    }

    private record Fixture(
            String userId, String novelId, String chapterId, String taskId, String jobId) {}
}
