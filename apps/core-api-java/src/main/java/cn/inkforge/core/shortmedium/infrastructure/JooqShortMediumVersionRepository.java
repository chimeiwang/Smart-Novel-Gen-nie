package cn.inkforge.core.shortmedium.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.enums.Workflowrunstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterqualitycheckRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.OutlineRecord;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.ReviewArtifactRowProjection;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.shortmedium.application.ShortMediumVersionRepository;
import cn.inkforge.core.shortmedium.application.ShortMediumVersionTransaction;
import cn.inkforge.core.shortmedium.application.VersionCreation;
import cn.inkforge.core.shortmedium.domain.DocumentDiff;
import cn.inkforge.core.shortmedium.domain.ShortMediumDocument;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersion;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.shortmedium.domain.VersionDocumentBinding;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.Record1;
import org.jooq.impl.DSL;
import tools.jackson.databind.ObjectMapper;

/**
 * PostgreSQL 中短篇版本仓储。
 *
 * <p>所有写入固定按作品、工作稿、Artifact 版本、质量项顺序加锁。版本以 ReviewArtifact 及 revision 1
 * 保存为不可变历史；采用候选时工作稿、候选状态、采用命令与质量失效共享同一事务。
 */
final class JooqShortMediumVersionRepository implements ShortMediumVersionRepository {

    private static final String OUTLINE_PREFIX = "short-medium:outline:";
    private static final String MANUSCRIPT_PREFIX = "short-medium:manuscript:";
    private static final String QUALITY_SOURCE_CHANGED = "QUALITY_SOURCE_CHANGED";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final boolean durableAgentSchemaReady;
    private final CommandIdempotencyStore globalIdempotency;

    JooqShortMediumVersionRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this(database, ids, clock, json, false);
    }

    JooqShortMediumVersionRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            boolean durableAgentSchemaReady) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.durableAgentSchemaReady = durableAgentSchemaReady;
        this.globalIdempotency =
                new CommandIdempotencyStore(json, durableAgentSchemaReady);
    }

    @Override
    public <T> T inDocument(
            String userId,
            String novelId,
            VersionDocumentBinding binding,
            Function<ShortMediumVersionTransaction, T> operation) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            return inLockedDocument(
                    transaction, userId, novelId, binding, null, operation);
        });
    }

    @Override
    public <T> T inAdoption(
            String userId,
            String novelId,
            VersionDocumentBinding binding,
            String versionId,
            String clientRequestId,
            String requestHash,
            Map<String, Object> normalizedRequest,
            Function<ShortMediumVersionTransaction, T> operation) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            Record1<String> source = transaction.select(REVIEWARTIFACT.WORKFLOWRUNID)
                    .from(REVIEWARTIFACT)
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(REVIEWARTIFACT.NOVELID))
                    .where(
                            REVIEWARTIFACT.ID.eq(versionId),
                            REVIEWARTIFACT.NOVELID.eq(novelId),
                            NOVEL.USERID.eq(userId))
                    .fetchOne();
            String runId = source == null ? null : source.value1();
            if (runId == null) {
                // V1 继续使用原 Novel → 文档 → Artifact 锁序和 WritingRunCommand 回执。
                return inLockedDocument(
                        transaction, userId, novelId, binding, null, operation);
            }
            if (!durableAgentSchemaReady) {
                throw new ApiException(
                        503,
                        "DURABLE_WORKFLOW_SCHEMA_UNAVAILABLE",
                        "耐久工作流数据库结构尚不可用");
            }

            // V2 采用与所有写命令共享用户级命名空间；锁序固定为 advisory → Run → Novel/文档/Artifact。
            transaction.fetchValue(
                    "SELECT pg_catalog.pg_advisory_xact_lock(?)",
                    CommandIdempotency.advisoryLockKey(userId, clientRequestId));
            CommandIdempotencyStore.Resolution global = globalIdempotency.resolve(
                    transaction, userId, clientRequestId, requestHash);
            Record run = transaction.fetchOne(
                    """
                    SELECT id, "userId", "novelId", "chapterId", workflow, operation,
                           status::text AS status, "targetType", "targetId",
                           "currentEvidenceBundleId", "completedAt"
                    FROM public."WorkflowRun"
                    WHERE id = ? AND "engineVersion" = 2
                    FOR UPDATE
                    """,
                    runId);
            requireDurableRun(run, userId, novelId, binding);
            String replay = durableReplay(
                    transaction,
                    global,
                    runId,
                    versionId,
                    clientRequestId,
                    requestHash,
                    normalizedRequest);
            DurableAdoption adoption = new DurableAdoption(
                    runId,
                    run.get("operation", String.class),
                    run.get("currentEvidenceBundleId", String.class),
                    clientRequestId,
                    requestHash,
                    Collections.unmodifiableMap(new LinkedHashMap<>(normalizedRequest)),
                    replay);
            return inLockedDocument(
                    transaction,
                    userId,
                    novelId,
                    binding,
                    adoption,
                    locked -> {
                        ((SqlTransaction) locked).requireDurableCandidate(versionId);
                        return operation.apply(locked);
                    });
        });
    }

    private <T> T inLockedDocument(
            DSLContext transaction,
            String userId,
            String novelId,
            VersionDocumentBinding binding,
            DurableAdoption adoption,
            Function<ShortMediumVersionTransaction, T> operation) {
        // 调用方拿到的 document 与 versions 来自同一锁定快照；V2 的 Run 已在进入本方法前锁定。
        requireShortMediumNovel(transaction, userId, novelId, true);
        LoadedDocument loaded = loadDocument(transaction, novelId, binding, true);
        List<ReviewartifactRecord> artifacts = loadArtifacts(
                transaction, novelId, loaded.document().artifactKey(), true);
        return operation.apply(new SqlTransaction(
                transaction,
                loaded,
                artifacts.stream().map(this::map).toList(),
                adoption));
    }

    private void requireDurableRun(
            Record run,
            String userId,
            String novelId,
            VersionDocumentBinding binding) {
        if (run == null) throw versionNotFound();
        String operation = run.get("operation", String.class);
        boolean operationMatches = "outline".equals(binding.documentType())
                ? List.of("generate_outline", "replace_selection").contains(operation)
                : List.of("generate_manuscript", "replace_selection").contains(operation);
        String expectedTarget = "outline".equals(binding.documentType())
                ? "short_medium_outline"
                : "short_medium_manuscript";
        boolean valid = userId.equals(run.get("userId", String.class))
                && novelId.equals(run.get("novelId", String.class))
                && Objects.equals(binding.chapterId(), run.get("chapterId", String.class))
                && "short_medium".equals(run.get("workflow", String.class))
                && operationMatches
                && "completed".equals(run.get("status", String.class))
                && expectedTarget.equals(run.get("targetType", String.class))
                && run.get("targetId", String.class) != null
                && run.get("completedAt", LocalDateTime.class) != null;
        if (!valid) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_CANDIDATE_RUN_INVALID",
                    "候选版本的耐久运行身份无效");
        }
    }

    private String durableReplay(
            DSLContext transaction,
            CommandIdempotencyStore.Resolution global,
            String runId,
            String versionId,
            String clientRequestId,
            String requestHash,
            Map<String, Object> normalizedRequest) {
        if (global == null) return null;
        if (global.recordKind() != CommandIdempotencyStore.RecordKind.CONTROL_DECISION) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        Record receipt = transaction.fetchOne(
                """
                SELECT id, "runId", "stepType"::text AS "stepType",
                       status::text AS status, purpose, "idempotencyKey",
                       "requestHash", "resultHash", "artifactId",
                       "artifactRevision", input, output
                FROM public."WorkflowStep" WHERE id = ?
                """,
                global.recordId());
        Map<String, Object> input = global.metadata().normalizedBody();
        boolean validInput = input.keySet().equals(Set.of(
                        "schemaVersion",
                        "clientRequestId",
                        "candidateVersionId",
                        "expectedArtifactRevision",
                        "decision",
                        "normalizedBody"))
                && Integer.valueOf(1).equals(input.get("schemaVersion"))
                && clientRequestId.equals(input.get("clientRequestId"))
                && versionId.equals(input.get("candidateVersionId"))
                && Integer.valueOf(1).equals(input.get("expectedArtifactRevision"))
                && "adopt".equals(input.get("decision"))
                && normalizedRequest.equals(input.get("normalizedBody"));
        boolean valid = receipt != null
                && runId.equals(receipt.get("runId", String.class))
                && "user_confirmation".equals(receipt.get("stepType", String.class))
                && "completed".equals(receipt.get("status", String.class))
                && "user_decision".equals(receipt.get("purpose", String.class))
                && ("decision:" + clientRequestId)
                        .equals(receipt.get("idempotencyKey", String.class))
                && requestHash.equals(receipt.get("requestHash", String.class))
                && versionId.equals(receipt.get("artifactId", String.class))
                && Integer.valueOf(1).equals(receipt.get("artifactRevision", Integer.class))
                && validInput
                && receipt.get("output", String.class) != null
                && ShortMediumText.sha256(receipt.get("output", String.class))
                        .equals(receipt.get("resultHash", String.class));
        if (!valid) throw CommandIdempotencyStore.reused(clientRequestId);
        return receipt.get("output", String.class);
    }

    @Override
    public List<ShortMediumVersion> list(
            String userId, String novelId, VersionDocumentBinding binding) {
        DSLContext context = database.dsl();
        requireShortMediumNovel(context, userId, novelId, false);
        LoadedDocument loaded = loadDocument(context, novelId, binding, false);
        return loadArtifacts(context, novelId, loaded.document().artifactKey(), false).stream()
                .map(this::map)
                .toList();
    }

    @Override
    public ShortMediumVersion requireVersion(
            String userId, String novelId, String versionId) {
        // 版本读取统一使用生产冻结列，避免 selectFrom 把视频扩展列带入 SQL。
        ReviewartifactRecord artifact = database.dsl()
                .select(ReviewArtifactRowProjection.fields())
                .from(REVIEWARTIFACT)
                .join(NOVEL)
                .on(NOVEL.ID.eq(REVIEWARTIFACT.NOVELID))
                .join(WRITINGBIBLE)
                .on(WRITINGBIBLE.NOVELID.eq(NOVEL.ID))
                .where(
                        REVIEWARTIFACT.ID.eq(versionId),
                        REVIEWARTIFACT.NOVELID.eq(novelId),
                        NOVEL.USERID.eq(userId),
                        WRITINGBIBLE.STORYLENGTHPROFILE.eq(Storylengthprofile.short_medium))
                .fetchOneInto(REVIEWARTIFACT);
        if (artifact == null || !isVersionKey(artifact.getArtifactkey())) {
            throw versionNotFound();
        }
        return map(artifact);
    }

    private final class SqlTransaction implements ShortMediumVersionTransaction {

        private final DSLContext transaction;
        private final LoadedDocument loaded;
        private final List<ShortMediumVersion> versions;
        private final DurableAdoption adoption;
        private ShortMediumDocument document;

        private SqlTransaction(
                DSLContext transaction,
                LoadedDocument loaded,
                List<ShortMediumVersion> versions,
                DurableAdoption adoption) {
            this.transaction = transaction;
            this.loaded = loaded;
            this.document = loaded.document();
            this.versions = new ArrayList<>(versions);
            this.adoption = adoption;
        }

        private void requireDurableCandidate(String versionId) {
            ShortMediumVersion candidate = versions.stream()
                    .filter(version -> version.id().equals(versionId))
                    .findFirst()
                    .orElseThrow(JooqShortMediumVersionRepository::versionNotFound);
            Record exact = transaction.fetchOne(
                    """
                    SELECT artifact."taskId", artifact."workflowRunId", artifact.revision,
                           artifact."payloadJson", artifact."diffJson",
                           revision."payloadJson" AS "revisionPayloadJson",
                           revision."diffJson" AS "revisionDiffJson"
                    FROM public."ReviewArtifact" AS artifact
                    JOIN public."ReviewArtifactRevision" AS revision
                      ON revision."artifactId" = artifact.id
                     AND revision.revision = artifact.revision
                    WHERE artifact.id = ? AND artifact."artifactKey" = ?
                    FOR UPDATE OF artifact, revision
                    """,
                    candidate.id(),
                    document.artifactKey());
            boolean exactRevision = exact != null
                    && exact.get("taskId", String.class) == null
                    && adoption.runId().equals(exact.get("workflowRunId", String.class))
                    && Integer.valueOf(1).equals(exact.get("revision", Integer.class))
                    && Objects.equals(
                            exact.get("payloadJson", String.class),
                            exact.get("revisionPayloadJson", String.class))
                    && Objects.equals(
                            exact.get("diffJson", String.class),
                            exact.get("revisionDiffJson", String.class))
                    && adoption.runId().equals(candidate.payload().sourceTaskId())
                    && ("replace_selection".equals(adoption.operation())
                            == candidate.payload().createdFromSelection());
            Record producer = transaction.fetchOne(
                    """
                    SELECT id, "runId", "stepType"::text AS "stepType",
                           status::text AS status, purpose, "resultHash"
                    FROM public."WorkflowStep"
                    WHERE id = ? AND "runId" = ?
                    """,
                    candidate.payload().sourceJobId(),
                    adoption.runId());
            boolean exactProducer = producer != null
                    && "agent".equals(producer.get("stepType", String.class))
                    && "completed".equals(producer.get("status", String.class))
                    && "generation".equals(producer.get("purpose", String.class))
                    && producer.get("resultHash", String.class) != null
                    && producer.get("resultHash", String.class).matches("[0-9a-f]{64}");
            if (!exactRevision || !exactProducer) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_CANDIDATE_RUN_INVALID",
                        "候选版本的耐久运行身份无效");
            }
        }

        @Override
        public ShortMediumDocument document() {
            return document;
        }

        @Override
        public List<ShortMediumVersion> versions() {
            return versions;
        }

        @Override
        public ShortMediumVersion create(VersionCreation creation) {
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String artifactId = ids.next();
            DocumentDiff persistedDiff = creation.diff().withToVersionId(artifactId);
            String payloadJson = json.writeValueAsString(creation.payload());
            String diffJson = json.writeValueAsString(persistedDiff);
            Reviewartifactkind kind = "outline".equals(document.binding().documentType())
                    ? Reviewartifactkind.outline_draft
                    : Reviewartifactkind.chapter_draft;
            Reviewartifactstatus status = Reviewartifactstatus.lookupLiteral(creation.status());
            if (status == null
                    || (status != Reviewartifactstatus.awaiting_user
                            && status != Reviewartifactstatus.applied)) {
                throw new IllegalArgumentException("中短篇版本状态无效");
            }
            // 当前行和首个 revision 同时创建，确保候选刚出现就具备可追溯的不可变初始快照。
            transaction.insertInto(REVIEWARTIFACT)
                    .set(REVIEWARTIFACT.ID, artifactId)
                    .set(REVIEWARTIFACT.NOVELID, document.novelId())
                    .set(REVIEWARTIFACT.CHAPTERID, document.chapterId())
                    .set(REVIEWARTIFACT.TASKID, creation.taskId())
                    .set(REVIEWARTIFACT.ARTIFACTKEY, document.artifactKey())
                    .set(REVIEWARTIFACT.KIND, kind)
                    .set(REVIEWARTIFACT.STATUS, status)
                    .set(
                            REVIEWARTIFACT.TITLE,
                            "outline".equals(document.binding().documentType())
                                    ? (status == Reviewartifactstatus.awaiting_user
                                            ? "中短篇大纲候选版本"
                                            : "中短篇大纲版本")
                                    : (status == Reviewartifactstatus.awaiting_user
                                            ? "中短篇正文候选版本"
                                            : "中短篇正文版本"))
                    .set(REVIEWARTIFACT.SUMMARY, creation.summary())
                    .set(REVIEWARTIFACT.PAYLOADJSON, payloadJson)
                    .set(REVIEWARTIFACT.DIFFJSON, diffJson)
                    .set(REVIEWARTIFACT.CREATEDBYAGENT, creation.createdByAgent())
                    .set(REVIEWARTIFACT.UPDATEDBYAGENT, creation.createdByAgent())
                    .set(REVIEWARTIFACT.REVISION, 1)
                    .set(
                            REVIEWARTIFACT.APPLIEDAT,
                            status == Reviewartifactstatus.applied ? now : null)
                    .set(REVIEWARTIFACT.CREATEDAT, now)
                    .set(REVIEWARTIFACT.UPDATEDAT, now)
                    .execute();
            transaction.insertInto(REVIEWARTIFACTREVISION)
                    .set(REVIEWARTIFACTREVISION.ID, ids.next())
                    .set(REVIEWARTIFACTREVISION.ARTIFACTID, artifactId)
                    .set(REVIEWARTIFACTREVISION.REVISION, 1)
                    .set(REVIEWARTIFACTREVISION.SUMMARY, creation.summary())
                    .set(REVIEWARTIFACTREVISION.PAYLOADJSON, payloadJson)
                    .set(REVIEWARTIFACTREVISION.DIFFJSON, diffJson)
                    .set(REVIEWARTIFACTREVISION.CREATEDBYAGENT, creation.createdByAgent())
                    .set(REVIEWARTIFACTREVISION.CREATEDAT, now)
                    .execute();
            ShortMediumVersion created = new ShortMediumVersion(
                    artifactId,
                    document.novelId(),
                    document.chapterId(),
                    document.artifactKey(),
                    creation.status(),
                    creation.summary(),
                    creation.payload(),
                    persistedDiff,
                    creation.createdByAgent(),
                    creation.taskId(),
                    DatabaseTimestamp.api(now),
                    DatabaseTimestamp.api(now),
                    status == Reviewartifactstatus.applied
                            ? DatabaseTimestamp.api(now)
                            : null);
            versions.add(created);
            return created;
        }

        @Override
        public ShortMediumVersion saveInitialDiff(
                ShortMediumVersion version, DocumentDiff diff) {
            String diffJson = json.writeValueAsString(diff);
            int artifactRows = transaction.update(REVIEWARTIFACT)
                    .set(REVIEWARTIFACT.DIFFJSON, diffJson)
                    .where(
                            REVIEWARTIFACT.ID.eq(version.id()),
                            REVIEWARTIFACT.ARTIFACTKEY.eq(document.artifactKey()))
                    .execute();
            int revisionRows = transaction.update(REVIEWARTIFACTREVISION)
                    .set(REVIEWARTIFACTREVISION.DIFFJSON, diffJson)
                    .where(
                            REVIEWARTIFACTREVISION.ARTIFACTID.eq(version.id()),
                            REVIEWARTIFACTREVISION.REVISION.eq(1))
                    .execute();
            if (artifactRows != 1 || revisionRows != 1) {
                throw new IllegalStateException("版本初始差异模型未加载");
            }
            ShortMediumVersion updated = version.withDiff(diff);
            versions.set(versions.indexOf(version), updated);
            return updated;
        }

        @Override
        public void replaceWorkContent(String content) {
            if (loaded.outline() != null) {
                LocalDateTime updatedAt = DatabaseTimestamp.next(
                        clock, loaded.outline().getUpdatedat());
                transaction.update(OUTLINE)
                        .set(OUTLINE.CONTENT, content)
                        .set(OUTLINE.UPDATEDAT, updatedAt)
                        .where(OUTLINE.ID.eq(loaded.outline().getId()))
                        .execute();
                loaded.outline().setContent(content);
                loaded.outline().setUpdatedat(updatedAt);
                document = document.withContent(content, DatabaseTimestamp.api(updatedAt));
                return;
            }
            replaceChapterContent(content);
        }

        private void replaceChapterContent(String content) {
            ChapterRecord chapter = loaded.chapter();
            ChapterqualitycheckRecord check = transaction.selectFrom(CHAPTERQUALITYCHECK)
                    .where(
                            CHAPTERQUALITYCHECK.CHAPTERID.eq(chapter.getId()),
                            CHAPTERQUALITYCHECK.TYPE.eq(Qualitychecktype.consistency))
                    .forUpdate()
                    .fetchOne();
            boolean contentChanged = !chapter.getContent().equals(content);
            boolean reopenChanged = chapter.getStatus() != Chapterstatus.drafting
                    || chapter.getCompletedat() != null;
            if (!contentChanged && !reopenChanged) {
                return;
            }
            // 正文内容变化会重新打开章节并使一致性终检失效；采用版本不能绕过普通编辑路径的质量语义。
            LocalDateTime updatedAt = DatabaseTimestamp.next(clock, chapter.getUpdatedat());
            var update = transaction.update(CHAPTER)
                    .set(CHAPTER.STATUS, Chapterstatus.drafting)
                    .setNull(CHAPTER.COMPLETEDAT)
                    .set(CHAPTER.UPDATEDAT, updatedAt);
            if (contentChanged) {
                update.set(CHAPTER.CONTENT, content);
            }
            update.where(CHAPTER.ID.eq(chapter.getId())).execute();
            chapter.setStatus(Chapterstatus.drafting);
            chapter.setCompletedat(null);
            chapter.setUpdatedat(updatedAt);
            if (contentChanged) {
                chapter.setContent(content);
                if (check != null) {
                    invalidateQuality(check, DatabaseTimestamp.now(clock));
                }
            }
            document = document.withContent(content, DatabaseTimestamp.api(updatedAt));
        }

        private void invalidateQuality(
                ChapterqualitycheckRecord check, LocalDateTime now) {
            // 与章节编辑路径保持同一字段集；中短篇采用必须和版本写入共享当前事务。
            transaction.update(CHAPTERQUALITYCHECK)
                    .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                    .setNull(CHAPTERQUALITYCHECK.RESULT)
                    .setNull(CHAPTERQUALITYCHECK.SCOREHOOK)
                    .setNull(CHAPTERQUALITYCHECK.SCORETENSION)
                    .setNull(CHAPTERQUALITYCHECK.SCOREPAYOFF)
                    .setNull(CHAPTERQUALITYCHECK.SCOREPACING)
                    .setNull(CHAPTERQUALITYCHECK.SCOREENDINGHOOK)
                    .setNull(CHAPTERQUALITYCHECK.SCOREREADERPROMISE)
                    .setNull(CHAPTERQUALITYCHECK.SCOREOVERALL)
                    .setNull(CHAPTERQUALITYCHECK.QUALITYGATE)
                    .setNull(CHAPTERQUALITYCHECK.REWRITEBRIEF)
                    .set(CHAPTERQUALITYCHECK.UPDATEDAT, now)
                    .where(CHAPTERQUALITYCHECK.ID.eq(check.getId()))
                    .execute();
            transaction.update(WORKFLOWRUN)
                    .set(WORKFLOWRUN.STATUS, Workflowrunstatus.cancelled)
                    .set(WORKFLOWRUN.ERRORMESSAGE, QUALITY_SOURCE_CHANGED)
                    .set(WORKFLOWRUN.UPDATEDAT, now)
                    .where(
                            WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check),
                            WORKFLOWRUN.SOURCETYPE.eq("quality_check"),
                            WORKFLOWRUN.SOURCEID.eq(check.getId()),
                            WORKFLOWRUN.STATUS.in(
                                    Workflowrunstatus.pending,
                                    Workflowrunstatus.running))
                    .execute();
        }

        @Override
        public ShortMediumVersion markApplied(ShortMediumVersion candidate) {
            LocalDateTime now = DatabaseTimestamp.now(clock);
            // 状态谓词是最终 CAS：只有仍在 awaiting_user 的同文档候选才能被推进一次。
            int affected = transaction.update(REVIEWARTIFACT)
                    .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.applied)
                    .set(REVIEWARTIFACT.APPLIEDAT, now)
                    .set(REVIEWARTIFACT.UPDATEDAT, now)
                    .where(
                            REVIEWARTIFACT.ID.eq(candidate.id()),
                            REVIEWARTIFACT.ARTIFACTKEY.eq(document.artifactKey()),
                            REVIEWARTIFACT.STATUS.eq(Reviewartifactstatus.awaiting_user))
                    .execute();
            if (affected != 1) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_CANDIDATE_STATUS_INVALID",
                        "该版本不是可采用的候选版本");
            }
            ShortMediumVersion applied = candidate.withStatus(
                    "applied", DatabaseTimestamp.api(now), DatabaseTimestamp.api(now));
            versions.set(versions.indexOf(candidate), applied);
            return applied;
        }

        @Override
        public String findAdoptionReplay(String key) {
            if (adoption != null) return adoption.replayJson();
            return transaction.select(WRITINGRUNCOMMAND.RESULTJSON)
                    .from(WRITINGRUNCOMMAND)
                    .where(
                            WRITINGRUNCOMMAND.IDEMPOTENCYKEY.eq(key),
                            WRITINGRUNCOMMAND.STATUS.eq("succeeded"))
                    .fetchOne(WRITINGRUNCOMMAND.RESULTJSON);
        }

        @Override
        public void saveAdoptionReplay(
                String key, ShortMediumVersion candidate, String responseJson) {
            if (adoption != null) {
                saveDurableAdoptionReceipt(candidate, responseJson);
                return;
            }
            if (candidate.taskId() == null) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_CANDIDATE_TASK_MISSING",
                        "候选版本缺少来源任务，不能记录采用幂等结果");
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.insertInto(WRITINGRUNCOMMAND)
                    .set(WRITINGRUNCOMMAND.ID, ids.next())
                    .set(WRITINGRUNCOMMAND.TASKID, candidate.taskId())
                    .set(WRITINGRUNCOMMAND.ARTIFACTID, candidate.id())
                    .set(WRITINGRUNCOMMAND.IDEMPOTENCYKEY, key)
                    .set(WRITINGRUNCOMMAND.KIND, "artifact_decision")
                    .set(WRITINGRUNCOMMAND.DECISION, "approve")
                    .set(
                            WRITINGRUNCOMMAND.PAYLOADJSON,
                            json.writeValueAsString(java.util.Map.of(
                                    "artifactId", candidate.id())))
                    .set(WRITINGRUNCOMMAND.RESULTJSON, responseJson)
                    .set(WRITINGRUNCOMMAND.STATUS, "succeeded")
                    .set(WRITINGRUNCOMMAND.SUBMITTEDAT, now)
                    .set(WRITINGRUNCOMMAND.COMPLETEDAT, now)
                    .set(WRITINGRUNCOMMAND.NEXTATTEMPTAT, now)
                    .set(WRITINGRUNCOMMAND.ATTEMPTCOUNT, 0)
                    .set(WRITINGRUNCOMMAND.CREATEDAT, now)
                    .set(WRITINGRUNCOMMAND.UPDATEDAT, now)
                    .execute();
        }

        private void saveDurableAdoptionReceipt(
                ShortMediumVersion candidate, String responseJson) {
            Map<String, Object> input = new LinkedHashMap<>();
            input.put("schemaVersion", 1);
            input.put("clientRequestId", adoption.clientRequestId());
            input.put("candidateVersionId", candidate.id());
            input.put("expectedArtifactRevision", 1);
            input.put("decision", "adopt");
            input.put("normalizedBody", adoption.normalizedRequest());
            String inputJson = new String(
                    CommandIdempotency.canonicalJsonBytes(input, json),
                    StandardCharsets.UTF_8);
            int ordinal = transaction.fetchOne(
                            "SELECT coalesce(max(ordinal), 0) + 1 FROM public.\"WorkflowStep\" WHERE \"runId\" = ?",
                            adoption.runId())
                    .get(0, Integer.class);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            int affected = transaction.execute(
                    """
                    INSERT INTO public."WorkflowStep" (
                      id, "runId", "agentId", "stepType", status, input, output,
                      "durationMs", "createdAt", ordinal, purpose, lane, "attemptCount",
                      "nextAttemptAt", "fencingToken", "leaseExpiresAt", "heartbeatAt",
                      "activeJobId", "idempotencyKey", "requestHash", "inputHash",
                      "resultHash", "evidenceBundleId", "artifactId", "artifactRevision",
                      "modelProfile", "modelProfileVersion", "outputSchema",
                      "outputSchemaVersion", "budgetJson", "resolvedModelJson", "usageJson",
                      "lastProgressSequence", "cancelRequestId", "submittedAt", "updatedAt",
                      "completedAt", "errorCode"
                    ) VALUES (
                      ?, ?, NULL, CAST('user_confirmation' AS "WorkflowStepType"),
                      CAST('completed' AS "WorkflowStepStatus"), ?, ?, 0, ?, ?,
                      'user_decision', 'control', 0, NULL, 0, NULL, NULL, NULL, ?, ?, ?,
                      ?, ?, ?, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL
                    )
                    """,
                    ids.next(),
                    adoption.runId(),
                    inputJson,
                    responseJson,
                    now,
                    ordinal,
                    "decision:" + adoption.clientRequestId(),
                    adoption.requestHash(),
                    ShortMediumText.sha256(inputJson),
                    ShortMediumText.sha256(responseJson),
                    adoption.evidenceBundleId(),
                    candidate.id(),
                    now,
                    now,
                    now);
            if (affected != 1) {
                throw new IllegalStateException("中短篇 V2 采用回执未写入");
            }
        }

        @Override
        public ShortMediumVersion currentOutlineVersion() {
            return transaction
                    .select(ReviewArtifactRowProjection.fields())
                    .from(REVIEWARTIFACT)
                    .where(
                            REVIEWARTIFACT.NOVELID.eq(document.novelId()),
                            REVIEWARTIFACT.ARTIFACTKEY.eq(OUTLINE_PREFIX + document.novelId()),
                            REVIEWARTIFACT.STATUS.eq(Reviewartifactstatus.applied))
                    .orderBy(REVIEWARTIFACT.CREATEDAT.asc(), REVIEWARTIFACT.ID.asc())
                    .fetchInto(REVIEWARTIFACT)
                    .stream()
                    .map(JooqShortMediumVersionRepository.this::map)
                    .max(Comparator.comparingInt(ShortMediumVersion::versionNumber))
                    .orElse(null);
        }
    }

    private LoadedDocument loadDocument(
            DSLContext context,
            String novelId,
            VersionDocumentBinding binding,
            boolean lock) {
        if ("outline".equals(binding.documentType())) {
            var query = context.selectFrom(OUTLINE).where(OUTLINE.NOVELID.eq(novelId));
            OutlineRecord outline = lock ? query.forUpdate().fetchOne() : query.fetchOne();
            if (outline == null) {
                throw new ApiException(
                        404,
                        "SHORT_MEDIUM_OUTLINE_NOT_FOUND",
                        "中短篇大纲工作稿不存在");
            }
            ShortMediumDocument document = new ShortMediumDocument(
                    novelId,
                    null,
                    binding,
                    binding.artifactKey(novelId),
                    outline.getContent(),
                    DatabaseTimestamp.api(outline.getUpdatedat()));
            return new LoadedDocument(document, outline, null);
        }
        var query = context.selectFrom(CHAPTER).where(
                CHAPTER.ID.eq(binding.chapterId()), CHAPTER.NOVELID.eq(novelId));
        ChapterRecord chapter = lock ? query.forUpdate().fetchOne() : query.fetchOne();
        if (chapter == null) {
            throw new ApiException(
                    404,
                    "SHORT_MEDIUM_MANUSCRIPT_NOT_FOUND",
                    "中短篇全文工作稿不存在");
        }
        ShortMediumDocument document = new ShortMediumDocument(
                novelId,
                chapter.getId(),
                binding,
                binding.artifactKey(novelId),
                chapter.getContent(),
                DatabaseTimestamp.api(chapter.getUpdatedat()));
        return new LoadedDocument(document, null, chapter);
    }

    private static void requireShortMediumNovel(
            DSLContext context, String userId, String novelId, boolean lock) {
        var query = context.select(NOVEL.ID)
                .from(NOVEL)
                .join(WRITINGBIBLE)
                .on(WRITINGBIBLE.NOVELID.eq(NOVEL.ID))
                .where(
                        NOVEL.ID.eq(novelId),
                        NOVEL.USERID.eq(userId),
                        WRITINGBIBLE.STORYLENGTHPROFILE.eq(Storylengthprofile.short_medium));
        Record1<String> row = lock
                ? query.forUpdate().of(NOVEL).fetchOne()
                : query.fetchOne();
        if (row == null) {
            throw new ApiException(
                    404,
                    "SHORT_MEDIUM_NOVEL_NOT_FOUND",
                    "中短篇作品不存在");
        }
    }

    private static List<ReviewartifactRecord> loadArtifacts(
            DSLContext context, String novelId, String artifactKey, boolean lock) {
        var query = context.select(ReviewArtifactRowProjection.fields())
                .from(REVIEWARTIFACT)
                .where(
                        REVIEWARTIFACT.NOVELID.eq(novelId),
                        REVIEWARTIFACT.ARTIFACTKEY.eq(artifactKey))
                .orderBy(REVIEWARTIFACT.CREATEDAT.asc(), REVIEWARTIFACT.ID.asc());
        return lock
                ? query.forUpdate().fetchInto(REVIEWARTIFACT)
                : query.fetchInto(REVIEWARTIFACT);
    }

    private ShortMediumVersion map(ReviewartifactRecord artifact) {
        if (!isVersionKey(artifact.getArtifactkey())) {
            throw versionNotFound();
        }
        try {
            ShortMediumVersionPayload payload = json.readValue(
                    artifact.getPayloadjson(), ShortMediumVersionPayload.class);
            String expectedKey = "outline".equals(payload.documentType())
                    ? OUTLINE_PREFIX + artifact.getNovelid()
                    : MANUSCRIPT_PREFIX + artifact.getChapterid();
            if (!expectedKey.equals(artifact.getArtifactkey())) {
                throw new IllegalArgumentException("版本文档绑定不一致");
            }
            boolean v1Agent = artifact.getTaskid() != null
                    && artifact.getWorkflowrunid() == null
                    && artifact.getTaskid().equals(payload.sourceTaskId());
            boolean v2Agent = artifact.getTaskid() == null
                    && artifact.getWorkflowrunid() != null
                    && artifact.getWorkflowrunid().equals(payload.sourceTaskId());
            boolean manual = artifact.getTaskid() == null
                    && artifact.getWorkflowrunid() == null
                    && !"agent".equals(payload.source());
            if ("agent".equals(payload.source()) ? !v1Agent && !v2Agent : !manual) {
                throw new IllegalArgumentException("版本来源归属不一致");
            }
            DocumentDiff diff = artifact.getDiffjson() == null
                    ? null
                    : json.readValue(artifact.getDiffjson(), DocumentDiff.class);
            return new ShortMediumVersion(
                    artifact.getId(),
                    artifact.getNovelid(),
                    artifact.getChapterid(),
                    artifact.getArtifactkey(),
                    artifact.getStatus().getLiteral(),
                    artifact.getSummary(),
                    payload,
                    diff,
                    artifact.getCreatedbyagent(),
                    artifact.getTaskid(),
                    DatabaseTimestamp.api(artifact.getCreatedat()),
                    DatabaseTimestamp.api(artifact.getUpdatedat()),
                    DatabaseTimestamp.api(artifact.getAppliedat()));
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_PERSISTED_JSON_INVALID",
                    "中短篇持久数据格式无效");
        }
    }

    private static boolean isVersionKey(String value) {
        return value != null
                && (value.startsWith(OUTLINE_PREFIX) || value.startsWith(MANUSCRIPT_PREFIX));
    }

    private static ApiException versionNotFound() {
        return new ApiException(
                404,
                "SHORT_MEDIUM_VERSION_NOT_FOUND",
                "中短篇版本不存在");
    }

    private record LoadedDocument(
            ShortMediumDocument document, OutlineRecord outline, ChapterRecord chapter) {}

    private record DurableAdoption(
            String runId,
            String operation,
            String evidenceBundleId,
            String clientRequestId,
            String requestHash,
            Map<String, Object> normalizedRequest,
            String replayJson) {}
}
