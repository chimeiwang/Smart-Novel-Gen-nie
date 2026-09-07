package cn.inkforge.core.shortmedium.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.DocumentType;
import cn.inkforge.contracts.api.ManualVersionRequest;
import cn.inkforge.contracts.api.VersionActionRequest;
import cn.inkforge.contracts.api.VersionPreviewRequest;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.enums.Workflowrunstatus;
import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.shortmedium.application.ShortMediumVersionService;
import cn.inkforge.core.shortmedium.application.VersionCreation;
import cn.inkforge.core.shortmedium.domain.DocumentDiffEngine;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersion;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.shortmedium.domain.VersionDocumentBinding;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
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
class JooqShortMediumVersionRepositoryTest {

    private static final LocalDateTime INITIAL = LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T06:00:00.123Z"), ZoneOffset.UTC);
    private static final ObjectMapper JSON = new ObjectMapper();

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqShortMediumVersionRepository repository;
    private static ShortMediumVersionService service;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void 重建冻结结构() throws Exception {
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
        repository = new JooqShortMediumVersionRepository(
                database, new CuidV1Generator(CLOCK), CLOCK, JSON, true);
        service = new ShortMediumVersionService(repository);
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
    void 人工版本必须完整落入Artifact和Revision并隔离作品模式与归属() {
        String owner = user("short-version-owner-1");
        String stranger = user("short-version-stranger-1");
        Project shortProject = project("short-version-novel-1", owner, true, "  完整大纲😀尾部  ", "");
        Project longProject = project("long-version-novel-1", owner, false, "长篇大纲", "");

        var preview = service.preview(
                owner,
                shortProject.novelId(),
                new VersionPreviewRequest(DocumentType.OUTLINE));
        var created = service.submitManual(
                owner,
                shortProject.novelId(),
                new ManualVersionRequest(
                        "short-request-0001",
                        preview.getConfirmationHash(),
                        preview.getContentHash(),
                        DocumentType.OUTLINE,
                        preview.getExpectedUpdatedAt()));

        assertThat(created.getContent()).isEqualTo("  完整大纲😀尾部  ");
        assertThat(service.list(owner, shortProject.novelId(), DocumentType.OUTLINE, null))
                .extracting(value -> value.getId())
                .containsExactly(created.getId());
        assertThat(service.get(owner, shortProject.novelId(), created.getId()).getContent())
                .isEqualTo(created.getContent());
        assertThat(database.dsl().selectFrom(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(created.getId()))
                        .fetchSingle()
                        .getPayloadjson())
                .contains("完整大纲😀尾部");
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACTREVISION,
                        REVIEWARTIFACTREVISION.ARTIFACTID.eq(created.getId())))
                .isEqualTo(1);
        assertCode(
                () -> service.list(stranger, shortProject.novelId(), DocumentType.OUTLINE, null),
                "SHORT_MEDIUM_NOVEL_NOT_FOUND");
        assertCode(
                () -> service.list(owner, longProject.novelId(), DocumentType.OUTLINE, null),
                "SHORT_MEDIUM_NOVEL_NOT_FOUND");
        assertCode(
                () -> service.list(
                        owner, shortProject.novelId(), DocumentType.OUTLINE, shortProject.chapterId()),
                "SHORT_MEDIUM_DOCUMENT_BINDING_INVALID");
    }

    @Test
    void 候选采用必须原子替换工作稿标记Artifact并只保存一个稳定回执() {
        String owner = user("short-version-owner-2");
        Project project = project("short-version-novel-2", owner, true, "基础大纲", "");
        ShortMediumVersion base = submitOutline(owner, project.novelId());
        writingTask("short-task-2", project, owner);
        ShortMediumVersion candidate = agentCandidate(
                owner,
                project,
                new VersionDocumentBinding("outline", null),
                base,
                "候选大纲😀完整尾部",
                null,
                "short-task-2",
                "short-job-2");
        String confirmation = service.get(owner, project.novelId(), candidate.id())
                .getDiff()
                .getConfirmationHash();
        VersionActionRequest request = new VersionActionRequest(
                        "short-adopt-0002", confirmation, DocumentType.OUTLINE)
                .baseVersionId(base.id());

        var adopted = service.adopt(owner, project.novelId(), candidate.id(), request);
        var replay = service.adopt(owner, project.novelId(), candidate.id(), request);

        assertThat(adopted.getStatus().getValue()).isEqualTo("applied");
        assertThat(replay.getId()).isEqualTo(adopted.getId());
        assertThat(database.dsl().select(OUTLINE.CONTENT)
                        .from(OUTLINE)
                        .where(OUTLINE.NOVELID.eq(project.novelId()))
                        .fetchSingle(OUTLINE.CONTENT))
                .isEqualTo("候选大纲😀完整尾部");
        assertThat(database.dsl().select(REVIEWARTIFACT.STATUS)
                        .from(REVIEWARTIFACT)
                        .where(REVIEWARTIFACT.ID.eq(candidate.id()))
                        .fetchSingle(REVIEWARTIFACT.STATUS)
                        .getLiteral())
                .isEqualTo("applied");
        assertThat(database.dsl().fetchCount(
                        WRITINGRUNCOMMAND,
                        WRITINGRUNCOMMAND.IDEMPOTENCYKEY.eq(
                                "short-medium:adopt:" + candidate.id() + ":short-adopt-0002")))
                .isEqualTo(1);
    }

    @Test
    void V2候选采用必须写同Run零模型回执且不伪造WritingTask或反转Run() {
        String owner = user("short-version-owner-v2");
        Project project = project("short-version-novel-v2", owner, true, "基础大纲", "");
        ShortMediumVersion base = submitOutline(owner, project.novelId());
        String runId = completedV2Run(owner, project, "generate_outline");
        ShortMediumVersion candidate = workflowCandidate(
                owner,
                project,
                new VersionDocumentBinding("outline", null),
                base,
                "V2候选大纲😀完整尾部",
                null,
                runId,
                "short-v2-producer-step");
        String confirmation = service.get(owner, project.novelId(), candidate.id())
                .getDiff()
                .getConfirmationHash();
        VersionActionRequest request = new VersionActionRequest(
                        "short-v2-adopt-0001", confirmation, DocumentType.OUTLINE)
                .baseVersionId(base.id());

        var adopted = service.adopt(owner, project.novelId(), candidate.id(), request);
        var replay = service.adopt(owner, project.novelId(), candidate.id(), request);

        assertThat(adopted.getId()).isEqualTo(candidate.id());
        assertThat(adopted.getTaskId()).isNull();
        assertThat(replay.getId()).isEqualTo(candidate.id());
        assertThat(database.dsl().fetchCount(
                        WRITINGRUNCOMMAND,
                        WRITINGRUNCOMMAND.ARTIFACTID.eq(candidate.id())))
                .isZero();
        var receipt = database.dsl().fetchOne(
                """
                SELECT step."runId", step."stepType"::text AS "stepType",
                       step.status::text AS status, step.purpose, step."artifactId",
                       step."artifactRevision", step."requestHash", step.input,
                       run.status::text AS "runStatus", run."completedAt"
                FROM public."WorkflowStep" AS step
                JOIN public."WorkflowRun" AS run ON run.id = step."runId"
                WHERE step."runId" = ? AND step.purpose = 'user_decision'
                """,
                runId);
        assertThat(receipt.get("stepType", String.class)).isEqualTo("user_confirmation");
        assertThat(receipt.get("status", String.class)).isEqualTo("completed");
        assertThat(receipt.get("artifactId", String.class)).isEqualTo(candidate.id());
        assertThat(receipt.get("artifactRevision", Integer.class)).isEqualTo(1);
        assertThat(receipt.get("requestHash", String.class)).matches("[0-9a-f]{64}");
        assertThat(receipt.get("input", String.class)).contains(confirmation);
        assertThat(receipt.get("runStatus", String.class)).isEqualTo("completed");
        assertThat(receipt.get("completedAt", LocalDateTime.class)).isEqualTo(INITIAL);
        assertThat(database.dsl().fetchOne(
                                "SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'user_decision'",
                                runId)
                        .get(0, Long.class))
                .isEqualTo(1L);

        VersionActionRequest conflicting = new VersionActionRequest(
                        "short-v2-adopt-0001", "0".repeat(64), DocumentType.OUTLINE)
                .baseVersionId(base.id());
        assertCode(
                () -> service.adopt(owner, project.novelId(), candidate.id(), conflicting),
                "IDEMPOTENCY_KEY_REUSED");
    }

    @Test
    void 正文采用必须继承大纲并复用章节重开与质量失效语义() {
        String owner = user("short-version-owner-3");
        Project project = project("short-version-novel-3", owner, true, "正式大纲", "正文基础");
        ShortMediumVersion outline = submitOutline(owner, project.novelId());
        ShortMediumVersion manuscript = submitManuscript(owner, project, outline.id());
        writingTask("short-task-3", project, owner);
        ShortMediumVersion candidate = agentCandidate(
                owner,
                project,
                new VersionDocumentBinding("manuscript", project.chapterId()),
                manuscript,
                "候选正文😀完整尾部",
                outline.id(),
                "short-task-3",
                "short-job-3");
        qualityFacts(project.chapterId());
        String confirmation = service.get(owner, project.novelId(), candidate.id())
                .getDiff()
                .getConfirmationHash();

        service.adopt(
                owner,
                project.novelId(),
                candidate.id(),
                new VersionActionRequest(
                                "short-adopt-0003", confirmation, DocumentType.MANUSCRIPT)
                        .chapterId(project.chapterId())
                        .baseVersionId(manuscript.id()));

        var chapter = database.dsl().selectFrom(CHAPTER)
                .where(CHAPTER.ID.eq(project.chapterId()))
                .fetchSingle();
        var check = database.dsl().selectFrom(CHAPTERQUALITYCHECK)
                .where(CHAPTERQUALITYCHECK.CHAPTERID.eq(project.chapterId()))
                .fetchSingle();
        var run = database.dsl().selectFrom(WORKFLOWRUN)
                .where(WORKFLOWRUN.ID.eq("short-quality-run-3"))
                .fetchSingle();
        assertThat(chapter.getContent()).isEqualTo("候选正文😀完整尾部");
        assertThat(chapter.getStatus()).isEqualTo(Chapterstatus.drafting);
        assertThat(chapter.getCompletedat()).isNull();
        assertThat(check.getStatus()).isEqualTo(Qualitycheckstatus.pending);
        assertThat(check.getResult()).isNull();
        assertThat(check.getScoreoverall()).isNull();
        assertThat(run.getStatus()).isEqualTo(Workflowrunstatus.cancelled);
        assertThat(run.getErrormessage()).isEqualTo("QUALITY_SOURCE_CHANGED");
    }

    private ShortMediumVersion submitOutline(String owner, String novelId) {
        var preview = service.preview(
                owner, novelId, new VersionPreviewRequest(DocumentType.OUTLINE));
        var response = service.submitManual(
                owner,
                novelId,
                new ManualVersionRequest(
                        "outline-base-0001",
                        preview.getConfirmationHash(),
                        preview.getContentHash(),
                        DocumentType.OUTLINE,
                        preview.getExpectedUpdatedAt()));
        return repository.requireVersion(owner, novelId, response.getId());
    }

    @Test
    void 旧Task退出终态后原候选仍可列出预览采用并从历史恢复() {
        String owner = user("retired-source-owner");
        Project project = project("retired-source-novel", owner, true, "原有大纲😀完整尾部", "原有正文");
        ShortMediumVersion base = submitOutline(owner, project.novelId());
        String taskId = "retired-source-task";
        writingTask(taskId, project, owner);
        ShortMediumVersion candidate = agentCandidate(owner, project,
                new VersionDocumentBinding("outline", null), base,
                "原候选全文😀不可丢失", null, taskId, "retired-source-job");
        var originalArtifact = database.dsl().selectFrom(REVIEWARTIFACT)
                .where(REVIEWARTIFACT.ID.eq(candidate.id())).fetchSingle();
        var originalOutline = database.dsl().selectFrom(OUTLINE)
                .where(OUTLINE.NOVELID.eq(project.novelId())).fetchSingle();

        // 模拟具名维护允许的唯一状态变化，不删除来源，不改候选或工作稿。
        database.dsl().update(WRITINGTASK).set(WRITINGTASK.PHASE, Writingtaskphase.error)
                .set(WRITINGTASK.UPDATEDAT, LocalDateTime.ofInstant(CLOCK.instant(), ZoneOffset.UTC))
                .where(WRITINGTASK.ID.eq(taskId)).execute();
        assertThat(service.list(owner, project.novelId(), DocumentType.OUTLINE, null))
                .extracting(value -> value.getId()).containsExactly(candidate.id(), base.id());
        var detail = service.get(owner, project.novelId(), candidate.id());
        assertThat(detail.getContent()).isEqualTo(candidate.content());
        assertThat(detail.getTaskId()).isEqualTo(taskId);
        assertThat(service.preview(owner, project.novelId(),
                new VersionPreviewRequest(DocumentType.OUTLINE).baseVersionId(base.id())).getDirty()).isFalse();
        assertThat(database.dsl().selectFrom(REVIEWARTIFACT)
                .where(REVIEWARTIFACT.ID.eq(candidate.id())).fetchSingle()).isEqualTo(originalArtifact);
        assertThat(database.dsl().selectFrom(OUTLINE)
                .where(OUTLINE.NOVELID.eq(project.novelId())).fetchSingle()).isEqualTo(originalOutline);

        // 此后是隔离数据库中的作者显式采用／恢复，不是维护脚本自动改成果。
        service.adopt(owner, project.novelId(), candidate.id(),
                new VersionActionRequest("retired-source-adopt", detail.getDiff().getConfirmationHash(),
                        DocumentType.OUTLINE).baseVersionId(base.id()));
        var diff = service.diffVersions(owner, project.novelId(), candidate.id(), base.id());
        var restored = service.restore(owner, project.novelId(), base.id(),
                new VersionActionRequest("retired-source-restore", diff.getConfirmationHash(),
                        DocumentType.OUTLINE).baseVersionId(candidate.id()));
        assertThat(restored.getId()).isNotEqualTo(base.id()).isNotEqualTo(candidate.id());
        assertThat(restored.getContent()).isEqualTo(base.content());
        assertThat(service.get(owner, project.novelId(), candidate.id()).getContent())
                .isEqualTo(candidate.content());
        assertThat(database.dsl().select(CHAPTER.CONTENT).from(CHAPTER)
                .where(CHAPTER.ID.eq(project.chapterId())).fetchSingle(CHAPTER.CONTENT)).isEqualTo("原有正文");
    }

    private ShortMediumVersion submitManuscript(
            String owner, Project project, String expectedOutlineId) {
        var preview = service.preview(
                owner,
                project.novelId(),
                new VersionPreviewRequest(DocumentType.MANUSCRIPT)
                        .chapterId(project.chapterId()));
        var response = service.submitManual(
                owner,
                project.novelId(),
                new ManualVersionRequest(
                                "manuscript-base-01",
                                preview.getConfirmationHash(),
                                preview.getContentHash(),
                                DocumentType.MANUSCRIPT,
                                preview.getExpectedUpdatedAt())
                        .chapterId(project.chapterId()));
        assertThat(response.getSourceOutlineVersionId()).isEqualTo(expectedOutlineId);
        return repository.requireVersion(owner, project.novelId(), response.getId());
    }

    private ShortMediumVersion agentCandidate(
            String owner,
            Project project,
            VersionDocumentBinding binding,
            ShortMediumVersion base,
            String content,
            String sourceOutlineVersionId,
            String taskId,
            String jobId) {
        return repository.inDocument(owner, project.novelId(), binding, transaction -> {
            ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                    "outline".equals(binding.documentType()) ? "outline_draft" : "chapter_draft",
                    binding.documentType(),
                    transaction.versions().stream()
                                    .mapToInt(ShortMediumVersion::versionNumber)
                                    .max()
                                    .orElse(0)
                            + 1,
                    base.id(),
                    null,
                    "agent",
                    content,
                    ShortMediumText.sha256(content),
                    taskId,
                    jobId,
                    sourceOutlineVersionId,
                    "生成候选",
                    null,
                    null,
                    null,
                    false,
                    null,
                    null,
                    null);
            ShortMediumVersion created = transaction.create(new VersionCreation(
                    payload,
                    DocumentDiffEngine.build(base.content(), content, base.id(), null),
                    "awaiting_user",
                    "生成候选",
                    "outline".equals(binding.documentType()) ? "剧情" : "写作",
                    taskId,
                    jobId));
            return transaction.saveInitialDiff(
                    created,
                    DocumentDiffEngine.bind(
                            created.diff(),
                            binding.documentType(),
                            binding.chapterId(),
                            base.id(),
                            base.payload().contentHash(),
                            created.id()));
        });
    }

    private static String completedV2Run(
            String owner, Project project, String operation) {
        String runId = project.novelId() + "-v2-run";
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowRun" (
                  id, "novelId", "chapterId", "userId", kind, status, input,
                  "createdAt", "updatedAt", "engineVersion", workflow, operation,
                  "operationCatalogVersion", "idempotencyKey", "requestHash",
                  "targetType", "targetId", "budgetJson", "modelPolicyJson",
                  "lastEventSequence", revision, "completedAt"
                ) VALUES (
                  ?, ?, NULL, ?, CAST('chapter_generation' AS "WorkflowRunKind"),
                  CAST('completed' AS "WorkflowRunStatus"), '{}', ?, ?, 2,
                  'short_medium', ?, 'agent-operation-catalog.v1', ?, ?,
                  'short_medium_outline', ?, '{}', '{}', 1, 1, ?
                )
                """,
                runId,
                project.novelId(),
                owner,
                INITIAL,
                INITIAL,
                operation,
                runId + "-start-request",
                ShortMediumText.sha256(runId),
                project.novelId(),
                INITIAL);
        String emptyHash = ShortMediumText.sha256("{}");
        database.dsl().execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, output,
                  "durationMs", "createdAt", ordinal, purpose, lane, "attemptCount",
                  "fencingToken", "idempotencyKey", "requestHash", "inputHash",
                  "resultHash", "submittedAt", "updatedAt", "completedAt"
                ) VALUES (
                  'short-v2-producer-step', ?, '写作', CAST('agent' AS "WorkflowStepType"),
                  CAST('completed' AS "WorkflowStepStatus"), '{}', '{}', 1, ?, 1,
                  'generation', 'creative', 1, 1, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                runId,
                INITIAL,
                runId + ".short-v2-producer-step",
                ShortMediumText.sha256(runId + ":producer-request"),
                emptyHash,
                emptyHash,
                INITIAL,
                INITIAL,
                INITIAL);
        return runId;
    }

    private static ShortMediumVersion workflowCandidate(
            String owner,
            Project project,
            VersionDocumentBinding binding,
            ShortMediumVersion base,
            String content,
            String sourceOutlineVersionId,
            String runId,
            String producerStepId) {
        String id = runId + "-candidate";
        ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                "outline".equals(binding.documentType()) ? "outline_draft" : "chapter_draft",
                binding.documentType(),
                base.versionNumber() + 1,
                base.id(),
                null,
                "agent",
                content,
                ShortMediumText.sha256(content),
                runId,
                producerStepId,
                sourceOutlineVersionId,
                "生成V2候选",
                null,
                null,
                null,
                false,
                null,
                null,
                null);
        var diff = DocumentDiffEngine.bind(
                DocumentDiffEngine.build(base.content(), content, base.id(), id),
                binding.documentType(),
                binding.chapterId(),
                base.id(),
                base.payload().contentHash(),
                id);
        String payloadJson = JSON.writeValueAsString(payload);
        String diffJson = JSON.writeValueAsString(diff);
        database.dsl().insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, id)
                .set(REVIEWARTIFACT.NOVELID, project.novelId())
                .set(REVIEWARTIFACT.CHAPTERID, binding.chapterId())
                .setNull(REVIEWARTIFACT.TASKID)
                .set(REVIEWARTIFACT.WORKFLOWRUNID, runId)
                .set(REVIEWARTIFACT.ARTIFACTKEY, binding.artifactKey(project.novelId()))
                .set(
                        REVIEWARTIFACT.KIND,
                        "outline".equals(binding.documentType())
                                ? cn.inkforge.core.db.generated.enums.Reviewartifactkind.outline_draft
                                : cn.inkforge.core.db.generated.enums.Reviewartifactkind.chapter_draft)
                .set(
                        REVIEWARTIFACT.STATUS,
                        cn.inkforge.core.db.generated.enums.Reviewartifactstatus.awaiting_user)
                .set(REVIEWARTIFACT.SUMMARY, "生成V2候选")
                .set(REVIEWARTIFACT.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACT.DIFFJSON, diffJson)
                .set(REVIEWARTIFACT.CREATEDBYAGENT, "剧情")
                .set(REVIEWARTIFACT.UPDATEDBYAGENT, "剧情")
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.CREATEDAT, INITIAL)
                .set(REVIEWARTIFACT.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(REVIEWARTIFACTREVISION)
                .set(REVIEWARTIFACTREVISION.ID, id + "-revision")
                .set(REVIEWARTIFACTREVISION.ARTIFACTID, id)
                .set(REVIEWARTIFACTREVISION.REVISION, 1)
                .set(REVIEWARTIFACTREVISION.SUMMARY, "生成V2候选")
                .set(REVIEWARTIFACTREVISION.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACTREVISION.DIFFJSON, diffJson)
                .set(REVIEWARTIFACTREVISION.CREATEDBYAGENT, "剧情")
                .set(REVIEWARTIFACTREVISION.CREATEDAT, INITIAL)
                .execute();
        return repository.requireVersion(owner, project.novelId(), id);
    }

    private String user(String id) {
        users.add(id);
        database.dsl().insertInto(USER)
                .set(USER.ID, id)
                .set(USER.USERNAME, id)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private static Project project(
            String novelId,
            String owner,
            boolean shortMedium,
            String outlineContent,
            String chapterContent) {
        String chapterId = novelId + "-chapter";
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, novelId)
                .set(NOVEL.NAME, novelId)
                .set(NOVEL.USERID, owner)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, novelId + "-bible")
                .set(WRITINGBIBLE.NOVELID, novelId)
                .set(
                        WRITINGBIBLE.STORYLENGTHPROFILE,
                        shortMedium
                                ? Storylengthprofile.short_medium
                                : Storylengthprofile.long_serial)
                .set(WRITINGBIBLE.TARGETTOTALWORDCOUNT, shortMedium ? 12_000 : 1_000_000)
                .set(WRITINGBIBLE.CREATEDAT, INITIAL)
                .set(WRITINGBIBLE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(OUTLINE)
                .set(OUTLINE.ID, novelId + "-outline")
                .set(OUTLINE.NOVELID, novelId)
                .set(OUTLINE.CONTENT, outlineContent)
                .set(OUTLINE.CREATEDAT, INITIAL)
                .set(OUTLINE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, chapterId)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, shortMedium ? "全文" : "第一章")
                .set(CHAPTER.CONTENT, chapterContent)
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
        return new Project(novelId, chapterId);
    }

    private static void writingTask(String id, Project project, String owner) {
        database.dsl().insertInto(WRITINGTASK)
                .set(WRITINGTASK.ID, id)
                .set(WRITINGTASK.NOVELID, project.novelId())
                .set(WRITINGTASK.CHAPTERID, project.chapterId())
                .set(WRITINGTASK.TARGETWORDCOUNT, 12_000)
                .set(WRITINGTASK.SELECTEDAGENTS, "[]")
                .set(WRITINGTASK.PHASE, Writingtaskphase.waiting_call)
                .set(WRITINGTASK.CREATEDAT, INITIAL)
                .set(WRITINGTASK.UPDATEDAT, INITIAL)
                .execute();
    }

    private static void qualityFacts(String chapterId) {
        database.dsl().update(CHAPTER)
                .set(CHAPTER.STATUS, Chapterstatus.completed)
                .set(CHAPTER.COMPLETEDAT, INITIAL)
                .where(CHAPTER.ID.eq(chapterId))
                .execute();
        database.dsl().insertInto(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.ID, "short-quality-check-3")
                .set(CHAPTERQUALITYCHECK.CHAPTERID, chapterId)
                .set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.completed)
                .set(CHAPTERQUALITYCHECK.TITLE, "一致性终检")
                .set(CHAPTERQUALITYCHECK.RESULT, "通过")
                .set(CHAPTERQUALITYCHECK.SCOREOVERALL, 90)
                .set(CHAPTERQUALITYCHECK.QUALITYGATE, "pass")
                .set(CHAPTERQUALITYCHECK.CREATEDAT, INITIAL)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, INITIAL)
                .execute();
        String novelId = database.dsl().select(CHAPTER.NOVELID)
                .from(CHAPTER)
                .where(CHAPTER.ID.eq(chapterId))
                .fetchSingle(CHAPTER.NOVELID);
        database.dsl().insertInto(WORKFLOWRUN)
                .set(WORKFLOWRUN.ID, "short-quality-run-3")
                .set(WORKFLOWRUN.NOVELID, novelId)
                .set(WORKFLOWRUN.CHAPTERID, chapterId)
                .set(WORKFLOWRUN.KIND, Workflowrunkind.quality_check)
                .set(WORKFLOWRUN.STATUS, Workflowrunstatus.running)
                .set(WORKFLOWRUN.SOURCETYPE, "quality_check")
                .set(WORKFLOWRUN.SOURCEID, "short-quality-check-3")
                .set(WORKFLOWRUN.CREATEDAT, INITIAL)
                .set(WORKFLOWRUN.UPDATEDAT, INITIAL)
                .execute();
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

    private record Project(String novelId, String chapterId) {}
}
