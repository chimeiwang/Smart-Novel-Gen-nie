package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.shortmedium.domain.DocumentDiffEngine;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.workflows.application.WorkflowShortMediumCompletion;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.jooq.Record;
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
class JooqWorkflowShortMediumCompletionTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-09-05T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-09-05T03:00:00.123Z"), ZoneOffset.UTC);
    private static final ObjectMapper JSON = new ObjectMapper();

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqWorkflowShortMediumCompletion completion;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void 重建耐久结构() throws Exception {
        for (String path : List.of(
                "db/novelwriterdev-schema.sql",
                "migrations/20260831_durable_agent_execution.sql")) {
            String target = "/tmp/" + path.substring(path.lastIndexOf('/') + 1);
            POSTGRES.copyFileToContainer(
                    MountableFile.forClasspathResource(path), target);
            ExecResult result = POSTGRES.execInContainer(
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    POSTGRES.getUsername(),
                    "-d",
                    POSTGRES.getDatabaseName(),
                    "-f",
                    target);
            assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        }
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        completion = new JooqWorkflowShortMediumCompletion(
                new CuidV1Generator(CLOCK), CLOCK, JSON);
    }

    @AfterEach
    void cleanup() {
        // V2 Run/Step 是数据库触发器保护的不可删除审计事实；对应 fixture 留给临时容器整体销毁。
        List<String> legacyUsers = users.stream()
                .filter(userId -> !Boolean.TRUE.equals(database.dsl().fetchValue(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM public."WorkflowRun"
                          WHERE "userId" = ? AND "engineVersion" = 2
                        )
                        """,
                        userId)))
                .toList();
        if (!legacyUsers.isEmpty()) {
            database.dsl().deleteFrom(NOVEL).where(NOVEL.USERID.in(legacyUsers)).execute();
            database.dsl().deleteFrom(USER).where(USER.ID.in(legacyUsers)).execute();
        }
        users.clear();
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 大纲完成创建唯一V2候选并以真实Run和生产Step保存来源() {
        Project project = project("sm-v2-outline", "基础大纲", "");
        String baseId = appliedVersion(project, "outline", 1, null, "基础大纲");
        String runId = insertRun(project, "generate_outline", null, "running");
        Map<String, Object> context = context(
                "generate_outline",
                "outline",
                null,
                baseId,
                "基础大纲",
                null,
                null,
                null,
                null,
                null,
                "生成一份完整蓝图",
                "idea",
                "起始素材全文");
        WorkflowShortMediumCompletion.CompletionRequest request = request(
                project, runId, null, "outline-producer-step", context, "候选大纲😀完整尾部");

        WorkflowShortMediumCompletion.Completion first = database.transactionResult(tx -> {
            tx.fetchOne("SELECT id FROM public.\"WorkflowRun\" WHERE id = ? FOR UPDATE", runId);
            return completion.complete(tx, request);
        });
        WorkflowShortMediumCompletion.Completion replay = database.transactionResult(tx -> {
            tx.fetchOne("SELECT id FROM public.\"WorkflowRun\" WHERE id = ? FOR UPDATE", runId);
            return completion.complete(tx, request);
        });

        assertThat(replay.candidateVersionId()).isEqualTo(first.candidateVersionId());
        assertThat(first.checkReport()).isNull();
        Record artifact = database.dsl().fetchOne(
                """
                SELECT id, "taskId", "workflowRunId", status::text AS status, revision,
                       "payloadJson", "diffJson"
                FROM public."ReviewArtifact" WHERE id = ?
                """,
                first.candidateVersionId());
        assertThat(artifact.get("taskId", String.class)).isNull();
        assertThat(artifact.get("workflowRunId", String.class)).isEqualTo(runId);
        assertThat(artifact.get("status", String.class)).isEqualTo("awaiting_user");
        assertThat(artifact.get("revision", Integer.class)).isEqualTo(1);
        ShortMediumVersionPayload payload = JSON.readValue(
                artifact.get("payloadJson", String.class), ShortMediumVersionPayload.class);
        assertThat(payload.sourceTaskId()).isEqualTo(runId);
        assertThat(payload.sourceJobId()).isEqualTo("outline-producer-step");
        assertThat(payload.content()).isEqualTo("候选大纲😀完整尾部");
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACT, REVIEWARTIFACT.WORKFLOWRUNID.eq(runId)))
                .isEqualTo(1);
        Record revision = database.dsl().fetchOne(
                """
                SELECT revision, "payloadJson", "diffJson"
                FROM public."ReviewArtifactRevision" WHERE "artifactId" = ?
                """,
                first.candidateVersionId());
        assertThat(revision.get("revision", Integer.class)).isEqualTo(1);
        assertThat(revision.get("payloadJson", String.class))
                .isEqualTo(artifact.get("payloadJson", String.class));
        assertThat(revision.get("diffJson", String.class))
                .isEqualTo(artifact.get("diffJson", String.class));
        assertThat(database.dsl().select(OUTLINE.CONTENT)
                        .from(OUTLINE)
                        .where(OUTLINE.NOVELID.eq(project.novelId()))
                        .fetchSingle(OUTLINE.CONTENT))
                .isEqualTo("基础大纲");
    }

    @Test
    void 正文完成保留固定开头并执行最终六千至八万字门禁() {
        Project project = project("sm-v2-manuscript", "正式大纲", "");
        String outlineId = appliedVersion(project, "outline", 1, null, "正式大纲");
        String runId = insertRun(project, "generate_manuscript", project.chapterId(), "running");
        Map<String, Object> context = context(
                "generate_manuscript",
                "manuscript",
                project.chapterId(),
                null,
                null,
                outlineId,
                "正式大纲",
                null,
                null,
                null,
                "生成完整正文",
                "opening",
                "固定开头");
        String content = "固定开头" + "文".repeat(5_996);

        WorkflowShortMediumCompletion.Completion created = database.transactionResult(tx -> {
            tx.fetchOne("SELECT id FROM public.\"WorkflowRun\" WHERE id = ? FOR UPDATE", runId);
            return completion.complete(
                    tx,
                    request(project, runId, project.chapterId(), "manuscript-producer-step", context, content));
        });

        ShortMediumVersionPayload payload = JSON.readValue(
                database.dsl().select(REVIEWARTIFACT.PAYLOADJSON)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(created.candidateVersionId()))
                        .fetchSingle(REVIEWARTIFACT.PAYLOADJSON),
                ShortMediumVersionPayload.class);
        assertThat(payload.sourceOutlineVersionId()).isEqualTo(outlineId);
        assertThat(ShortMediumText.count(payload.content())).isEqualTo(6_000);

        String invalidRun = insertRun(project, "generate_manuscript", project.chapterId(), "running");
        assertCode(
                () -> database.transactionResult(tx -> completion.complete(
                        tx,
                        request(
                                project,
                                invalidRun,
                                project.chapterId(),
                                "manuscript-invalid-step",
                                context,
                                "未保留开头" + "文".repeat(5_990)))),
                "SHORT_MEDIUM_FIXED_SOURCE_CHANGED");
    }

    @Test
    void 正文完成允许来源大纲出现新版但仍精确绑定启动时冻结版本() {
        Project project = project("sm-v2-frozen-outline", "旧版大纲", "正文底稿");
        String frozenOutlineId = appliedVersion(project, "outline", 1, null, "旧版大纲");
        String manuscriptBaseId = appliedVersion(
                project, "manuscript", 1, frozenOutlineId, "正文底稿");
        String runId = insertRun(
                project, "generate_manuscript", project.chapterId(), "running");
        Map<String, Object> frozenContext = context(
                "generate_manuscript",
                "manuscript",
                project.chapterId(),
                manuscriptBaseId,
                "正文底稿",
                frozenOutlineId,
                "旧版大纲",
                null,
                null,
                null,
                "按冻结蓝图生成正文",
                "opening",
                "固定开头");
        WorkflowShortMediumCompletion.CompletionRequest frozenRequest = request(
                project,
                runId,
                project.chapterId(),
                "frozen-outline-producer-step",
                frozenContext,
                "固定开头" + "文".repeat(5_996));

        String newerOutlineId = appliedVersion(project, "outline", 2, null, "新版大纲");
        database.dsl().update(OUTLINE)
                .set(OUTLINE.CONTENT, "新版大纲")
                .where(OUTLINE.NOVELID.eq(project.novelId()))
                .execute();

        WorkflowShortMediumCompletion.Completion created = database.transactionResult(tx -> {
            tx.fetchOne(
                    "SELECT id FROM public.\"WorkflowRun\" WHERE id = ? FOR UPDATE",
                    runId);
            return completion.complete(tx, frozenRequest);
        });

        ShortMediumVersionPayload payload = JSON.readValue(
                database.dsl().select(REVIEWARTIFACT.PAYLOADJSON)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(created.candidateVersionId()))
                        .fetchSingle(REVIEWARTIFACT.PAYLOADJSON),
                ShortMediumVersionPayload.class);
        assertThat(newerOutlineId).isNotEqualTo(frozenOutlineId);
        assertThat(payload.baseVersionId()).isEqualTo(manuscriptBaseId);
        assertThat(payload.sourceOutlineVersionId()).isEqualTo(frozenOutlineId);
    }

    @Test
    void 选区完成按Unicode码点拼接完整候选且选区外保持不变() {
        Project project = project("sm-v2-selection", "正式大纲", "甲😀乙");
        String outlineId = appliedVersion(project, "outline", 1, null, "正式大纲");
        String baseId = appliedVersion(project, "manuscript", 1, outlineId, "甲😀乙");
        String runId = insertRun(project, "replace_selection", project.chapterId(), "running");
        Map<String, Object> context = context(
                "replace_selection",
                "manuscript",
                project.chapterId(),
                baseId,
                "甲😀乙",
                outlineId,
                "正式大纲",
                1,
                2,
                "😀",
                "把表情换成月亮",
                null,
                null);

        WorkflowShortMediumCompletion.Completion created = database.transactionResult(tx -> {
            tx.fetchOne("SELECT id FROM public.\"WorkflowRun\" WHERE id = ? FOR UPDATE", runId);
            return completion.complete(
                    tx,
                    request(project, runId, project.chapterId(), "selection-producer-step", context, "🌙"));
        });

        ShortMediumVersionPayload payload = JSON.readValue(
                database.dsl().select(REVIEWARTIFACT.PAYLOADJSON)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(created.candidateVersionId()))
                        .fetchSingle(REVIEWARTIFACT.PAYLOADJSON),
                ShortMediumVersionPayload.class);
        assertThat(payload.content()).isEqualTo("甲🌙乙");
        assertThat(payload.createdFromSelection()).isTrue();
        assertThat(payload.selectionStart()).isEqualTo(1);
        assertThat(payload.selectionEnd()).isEqualTo(2);
        assertThat(payload.selectedTextHash()).isEqualTo(ShortMediumText.sha256("😀"));
        assertThat(database.dsl().select(CHAPTER.CONTENT)
                        .from(CHAPTER)
                        .where(CHAPTER.ID.eq(project.chapterId()))
                        .fetchSingle(CHAPTER.CONTENT))
                .isEqualTo("甲😀乙");
    }

    @Test
    void 全文检查只返回原文报告且不创建任何候选() {
        Project project = project("sm-v2-check", "正式大纲", "完整正文");
        String outlineId = appliedVersion(project, "outline", 1, null, "正式大纲");
        String baseId = appliedVersion(project, "manuscript", 1, outlineId, "完整正文");
        String runId = insertRun(project, "full_check", project.chapterId(), "running");
        Map<String, Object> context = context(
                "full_check",
                "manuscript",
                project.chapterId(),
                baseId,
                "完整正文",
                outlineId,
                "正式大纲",
                null,
                null,
                null,
                null,
                null,
                null);

        WorkflowShortMediumCompletion.Completion result = database.transactionResult(tx -> {
            tx.fetchOne("SELECT id FROM public.\"WorkflowRun\" WHERE id = ? FOR UPDATE", runId);
            return completion.complete(
                    tx,
                    request(project, runId, project.chapterId(), "check-producer-step", context, "逐字完整检查报告"));
        });

        assertThat(result.candidateVersionId()).isNull();
        assertThat(result.checkReport()).containsExactly(Map.entry("text", "逐字完整检查报告"));
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACT, REVIEWARTIFACT.WORKFLOWRUNID.eq(runId)))
                .isZero();
    }

    private Project project(String prefix, String outlineContent, String chapterContent) {
        String userId = prefix + "-user";
        String novelId = prefix + "-novel";
        String chapterId = prefix + "-chapter";
        users.add(userId);
        database.dsl().insertInto(USER)
                .set(USER.ID, userId)
                .set(USER.USERNAME, userId)
                .set(USER.PASSWORDHASH, "test")
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
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, prefix + "-bible")
                .set(WRITINGBIBLE.NOVELID, novelId)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, Storylengthprofile.short_medium)
                .set(WRITINGBIBLE.TARGETTOTALWORDCOUNT, 12_000)
                .set(WRITINGBIBLE.CREATEDAT, INITIAL)
                .set(WRITINGBIBLE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(OUTLINE)
                .set(OUTLINE.ID, prefix + "-outline")
                .set(OUTLINE.NOVELID, novelId)
                .set(OUTLINE.CONTENT, outlineContent)
                .set(OUTLINE.CREATEDAT, INITIAL)
                .set(OUTLINE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "全文")
                .set(CHAPTER.CONTENT, chapterContent)
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
        return new Project(userId, novelId, chapterId);
    }

    private static String appliedVersion(
            Project project,
            String documentType,
            int versionNumber,
            String sourceOutlineVersionId,
            String content) {
        String artifactId = project.novelId() + "-" + documentType + "-v" + versionNumber;
        String artifactKey = "outline".equals(documentType)
                ? "short-medium:outline:" + project.novelId()
                : "short-medium:manuscript:" + project.chapterId();
        ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                "outline".equals(documentType) ? "outline_draft" : "chapter_draft",
                documentType,
                versionNumber,
                null,
                "manual-version-request-" + documentType + "-" + versionNumber,
                "manual",
                content,
                ShortMediumText.sha256(content),
                null,
                null,
                sourceOutlineVersionId,
                null,
                null,
                null,
                null,
                false,
                null,
                null,
                null);
        var diff = DocumentDiffEngine.bind(
                DocumentDiffEngine.build("", content, null, artifactId),
                documentType,
                "manuscript".equals(documentType) ? project.chapterId() : null,
                null,
                ShortMediumText.sha256(content),
                artifactId);
        String payloadJson = JSON.writeValueAsString(payload);
        String diffJson = JSON.writeValueAsString(diff);
        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, artifactId)
                .set(REVIEWARTIFACT.NOVELID, project.novelId())
                .set(
                        REVIEWARTIFACT.CHAPTERID,
                        "manuscript".equals(documentType) ? project.chapterId() : null)
                .set(REVIEWARTIFACT.ARTIFACTKEY, artifactKey)
                .set(
                        REVIEWARTIFACT.KIND,
                        "outline".equals(documentType)
                                ? Reviewartifactkind.outline_draft
                                : Reviewartifactkind.chapter_draft)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.applied)
                .set(REVIEWARTIFACT.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACT.DIFFJSON, diffJson)
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.APPLIEDAT, INITIAL)
                .set(REVIEWARTIFACT.CREATEDAT, INITIAL)
                .set(REVIEWARTIFACT.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(REVIEWARTIFACTREVISION)
                .set(REVIEWARTIFACTREVISION.ID, artifactId + "-revision")
                .set(REVIEWARTIFACTREVISION.ARTIFACTID, artifactId)
                .set(REVIEWARTIFACTREVISION.REVISION, 1)
                .set(REVIEWARTIFACTREVISION.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACTREVISION.DIFFJSON, diffJson)
                .set(REVIEWARTIFACTREVISION.CREATEDAT, INITIAL)
                .execute();
        return artifactId;
    }

    private static String insertRun(
            Project project, String operation, String chapterId, String status) {
        String runId = project.novelId() + "-" + operation + "-" + System.nanoTime();
        String targetType = "generate_outline".equals(operation)
                ? "short_medium_outline"
                : "short_medium_manuscript";
        String targetId = chapterId == null ? project.novelId() : chapterId;
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowRun" (
                  id, "novelId", "chapterId", "userId", kind, status, input,
                  "createdAt", "updatedAt", "engineVersion", workflow, operation,
                  "operationCatalogVersion", "idempotencyKey", "requestHash",
                  "targetType", "targetId", "budgetJson", "modelPolicyJson",
                  "lastEventSequence", revision, "completedAt"
                ) VALUES (
                  ?, ?, ?, ?, CAST('chapter_generation' AS "WorkflowRunKind"),
                  CAST(? AS "WorkflowRunStatus"), '{}', ?, ?, 2, 'short_medium', ?,
                  'agent-operation-catalog.v1', ?, ?, ?, ?, '{}', '{}', 0, 1, ?
                )
                """,
                runId,
                project.novelId(),
                chapterId,
                project.userId(),
                status,
                INITIAL,
                INITIAL,
                operation,
                runId + "-start-request",
                ShortMediumText.sha256(runId),
                targetType,
                targetId,
                "completed".equals(status) ? INITIAL : null);
        return runId;
    }

    private static Map<String, Object> context(
            String operation,
            String documentType,
            String chapterId,
            String baseVersionId,
            String baseContent,
            String sourceOutlineVersionId,
            String sourceOutlineContent,
            Integer selectionStart,
            Integer selectionEnd,
            String selectedText,
            String userInstruction,
            String sourceKind,
            String sourceText) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("workflow", "short_medium");
        value.put("operation", operation);
        value.put("documentType", documentType);
        value.put("chapterId", chapterId);
        value.put("baseVersionId", baseVersionId);
        value.put("baseContent", baseContent);
        value.put(
                "baseContentHash",
                baseContent == null ? null : ShortMediumText.sha256(baseContent));
        value.put("sourceOutlineVersionId", sourceOutlineVersionId);
        value.put("sourceOutlineContent", sourceOutlineContent);
        value.put(
                "sourceOutlineContentHash",
                sourceOutlineContent == null
                        ? null
                        : ShortMediumText.sha256(sourceOutlineContent));
        value.put("selectionStart", selectionStart);
        value.put("selectionEnd", selectionEnd);
        value.put("selectedText", selectedText);
        value.put(
                "selectedTextHash",
                selectedText == null ? null : ShortMediumText.sha256(selectedText));
        value.put(
                "contextBefore",
                selectionStart == null || baseContent == null
                        ? null
                        : slice(baseContent, 0, selectionStart));
        value.put(
                "contextAfter",
                selectionEnd == null || baseContent == null
                        ? null
                        : slice(baseContent, selectionEnd, ShortMediumText.codePointLength(baseContent)));
        value.put("userInstruction", userInstruction);
        value.put("targetTotalWordCount", 12_000);
        value.put("sourceKind", sourceKind);
        value.put("sourceText", sourceText);
        return value;
    }

    private static WorkflowShortMediumCompletion.CompletionRequest request(
            Project project,
            String runId,
            String chapterId,
            String producerStepId,
            Map<String, Object> context,
            String finalText) {
        return new WorkflowShortMediumCompletion.CompletionRequest(
                project.userId(),
                project.novelId(),
                chapterId,
                (String) context.get("operation"),
                runId,
                producerStepId,
                ShortMediumText.sha256("result:" + producerStepId),
                runId + "-bundle",
                runId + "-context-item",
                ExecutionCanonicalJson.sha256(context),
                context,
                finalText);
    }

    private static String slice(String value, int start, int end) {
        return value.substring(
                value.offsetByCodePoints(0, start), value.offsetByCodePoints(0, end));
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
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

    private record Project(String userId, String novelId, String chapterId) {}
}
