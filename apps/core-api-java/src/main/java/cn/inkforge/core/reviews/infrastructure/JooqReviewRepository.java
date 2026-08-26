package cn.inkforge.core.reviews.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTEVALUATION;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.contracts.api.ArtifactConflictQuarantineRequest;
import cn.inkforge.contracts.api.ArtifactConflictQuarantineResponse;
import cn.inkforge.contracts.api.ArtifactDecisionAcceptedResponse;
import cn.inkforge.contracts.api.ArtifactEvaluationResponse;
import cn.inkforge.contracts.api.CreateArtifactRequest;
import cn.inkforge.contracts.api.ReviewArtifactListResponse;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.contracts.api.ReviewArtifactResponse;
import cn.inkforge.contracts.api.SourceBinding;
import cn.inkforge.contracts.api.SubmitArtifactEvaluationRequest;
import cn.inkforge.core.db.generated.enums.Reviewartifactevaluationverdict;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactevaluationRecord;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.ReviewRepository;
import cn.inkforge.core.reviews.application.FormalArtifactWriter;
import cn.inkforge.core.reviews.domain.ReviewArtifactRules;
import cn.inkforge.core.reviews.domain.ReviewArtifactSummary;
import cn.inkforge.core.reviews.domain.SelectionMaterialization;
import cn.inkforge.core.reviews.domain.SelectionSource;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.Condition;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.impl.DSL;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * ReviewArtifact 的 PostgreSQL 实现；Agent 写入和修订始终绑定当前活动命令。
 *
 * <p>Artifact 与每个 revision 都是耐久审核事实。相同 task、artifactKey 和 revision 的重放只有在完整内容
 * 一致时才幂等；旧 job、跨资源修订或不同评审结论必须冲突，不能用“最后写入者获胜”覆盖作者正在看的草案。
 */
final class JooqReviewRepository implements ReviewRepository {

    private static final List<Reviewartifactstatus> ACTIVE_STATUSES = List.of(
            Reviewartifactstatus.draft,
            Reviewartifactstatus.under_review,
            Reviewartifactstatus.awaiting_user,
            Reviewartifactstatus.applying);
    private static final List<Reviewartifactstatus> REVISABLE_STATUSES = List.of(
            Reviewartifactstatus.draft,
            Reviewartifactstatus.under_review,
            Reviewartifactstatus.awaiting_user);
    private static final List<String> ACTIVE_COMMAND_STATUSES = List.of(
            "pending", "submitted", "processing");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final JooqReviewDecisionStore decisions;

    JooqReviewRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this(
                database,
                ids,
                clock,
                json,
                new JooqFormalArtifactWriter(database, ids, clock, json));
    }

    JooqReviewRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            FormalArtifactWriter formalWriter) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.decisions = new JooqReviewDecisionStore(
                database,
                ids,
                clock,
                json,
                formalWriter);
    }

    @Override
    public ReviewArtifactResponse get(String userId, String artifactId) {
        ReviewartifactRecord artifact = ownedArtifact(database.dsl(), userId, artifactId, false);
        if (artifact == null) throw forbidden();
        return response(database.dsl(), artifact, true);
    }

    @Override
    public ReviewArtifactResponse getTaskArtifact(String userId, String taskId) {
        String ownedTask = database.dsl().select(WRITINGTASK.ID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId), NOVEL.USERID.eq(userId))
                .fetchOne(WRITINGTASK.ID);
        if (ownedTask == null) {
            throw new ApiException(404, "WRITING_TASK_NOT_FOUND", "写作任务不存在");
        }
        ReviewartifactRecord artifact = database.dsl().selectFrom(REVIEWARTIFACT)
                .where(
                        REVIEWARTIFACT.TASKID.eq(taskId),
                        REVIEWARTIFACT.STATUS.in(ACTIVE_STATUSES))
                .orderBy(REVIEWARTIFACT.UPDATEDAT.desc(), REVIEWARTIFACT.ID.desc())
                .limit(1)
                .fetchOne();
        return artifact == null ? null : response(database.dsl(), artifact, true);
    }

    @Override
    public ReviewArtifactListResponse list(
            String userId,
            String novelId,
            String chapterId,
            String taskId,
            String status,
            String kind,
            String cursor,
            int limit) {
        List<Condition> conditions = new ArrayList<>();
        conditions.add(REVIEWARTIFACT.NOVELID.eq(novelId));
        conditions.add(REVIEWARTIFACT.NOVELID.in(database.dsl()
                .select(NOVEL.ID)
                .from(NOVEL)
                .where(NOVEL.USERID.eq(userId))));
        if (chapterId != null) conditions.add(REVIEWARTIFACT.CHAPTERID.eq(chapterId));
        if (taskId != null) conditions.add(REVIEWARTIFACT.TASKID.eq(taskId));
        if (status != null) {
            Reviewartifactstatus value = Reviewartifactstatus.lookupLiteral(status);
            conditions.add(value == null ? DSL.falseCondition() : REVIEWARTIFACT.STATUS.eq(value));
        }
        if (kind != null) {
            Reviewartifactkind value = Reviewartifactkind.lookupLiteral(kind);
            conditions.add(value == null ? DSL.falseCondition() : REVIEWARTIFACT.KIND.eq(value));
        }
        if (cursor != null) {
            CursorValue value = decodeCursor(cursor);
            conditions.add(REVIEWARTIFACT.CREATEDAT.lt(value.createdAt())
                    .or(REVIEWARTIFACT.CREATEDAT.eq(value.createdAt())
                            .and(REVIEWARTIFACT.ID.lt(value.id()))));
        }
        List<ReviewartifactRecord> artifacts = database.dsl().selectFrom(REVIEWARTIFACT)
                .where(conditions)
                .orderBy(REVIEWARTIFACT.CREATEDAT.desc(), REVIEWARTIFACT.ID.desc())
                .limit(limit + 1)
                .fetch();
        boolean more = artifacts.size() > limit;
        if (more) artifacts = new ArrayList<>(artifacts.subList(0, limit));
        List<ReviewArtifactResponse> items = artifacts.stream()
                .map(item -> response(database.dsl(), item, false))
                .toList();
        String next = more && !artifacts.isEmpty()
                ? encodeCursor(artifacts.getLast())
                : null;
        return new ReviewArtifactListResponse(items, next);
    }

    @Override
    public List<ReviewArtifactSummary> listTaskSummaries(
            String userId,
            String novelId,
            String taskId,
            String status,
            String kind) {
        List<Condition> conditions = new ArrayList<>();
        conditions.add(REVIEWARTIFACT.NOVELID.eq(novelId));
        conditions.add(REVIEWARTIFACT.TASKID.eq(taskId));
        conditions.add(REVIEWARTIFACT.NOVELID.in(database.dsl()
                .select(NOVEL.ID)
                .from(NOVEL)
                .where(NOVEL.USERID.eq(userId))));
        if (status != null) {
            Reviewartifactstatus value = Reviewartifactstatus.lookupLiteral(status);
            conditions.add(value == null ? DSL.falseCondition() : REVIEWARTIFACT.STATUS.eq(value));
        }
        if (kind != null) {
            Reviewartifactkind value = Reviewartifactkind.lookupLiteral(kind);
            conditions.add(value == null ? DSL.falseCondition() : REVIEWARTIFACT.KIND.eq(value));
        }
        return database.dsl().selectFrom(REVIEWARTIFACT)
                .where(conditions)
                .orderBy(REVIEWARTIFACT.UPDATEDAT.desc(), REVIEWARTIFACT.ID.desc())
                .fetch()
                .stream()
                .map(artifact -> new ReviewArtifactSummary(
                        artifact.getId(),
                        artifact.getNovelid(),
                        artifact.getChapterid(),
                        artifact.getTaskid(),
                        artifact.getArtifactkey(),
                        artifact.getKind().getLiteral(),
                        artifact.getStatus().getLiteral(),
                        artifact.getTitle(),
                        artifact.getSummary(),
                        artifact.getRevision(),
                        artifact.getUpdatedbyagent(),
                        artifact.getRevieweragent(),
                        DatabaseTimestamp.api(artifact.getUpdatedat())))
                .toList();
    }

    @Override
    public ReviewArtifactResponse createOrRevise(CreateArtifactRequest request) {
        requirePublicArtifactKey(nullable(request.getArtifactKey()));
        String kind = request.getKind().getValue();
        ReviewArtifactRules.requireAgentPayload(kind, request.getPayload());
        ReviewArtifactRules.requireKnownTargetMode(request.getPayload());
        CreateResult result = database.transactionResult(transaction -> {
            // 先锁任务并确认当前 job，再锁活动 Artifact；旧 Agent 不能修订新命令正在展示的草案。
            Record task = transaction.select(WRITINGTASK.CHAPTERID, NOVEL.USERID)
                    .from(WRITINGTASK)
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                    .where(
                            WRITINGTASK.ID.eq(request.getTaskId()),
                            WRITINGTASK.NOVELID.eq(request.getNovelId()))
                    .forUpdate()
                    .fetchOne();
            String chapterId = nullable(request.getChapterId());
            if (task == null
                    || (chapterId != null
                            && !chapterId.equals(task.get(WRITINGTASK.CHAPTERID)))) {
                throw taskMismatch("待审核草案与写作任务资源不匹配");
            }
            requireCurrentJob(transaction, request.getTaskId(), request.getJobId());
            String artifactKey = nullable(request.getArtifactKey());
            ReviewartifactRecord existing = artifactKey == null
                    ? null
                    : transaction.selectFrom(REVIEWARTIFACT)
                            .where(
                                    REVIEWARTIFACT.NOVELID.eq(request.getNovelId()),
                                    REVIEWARTIFACT.TASKID.eq(request.getTaskId()),
                                    REVIEWARTIFACT.ARTIFACTKEY.eq(artifactKey),
                                    REVIEWARTIFACT.STATUS.in(REVISABLE_STATUSES))
                            .forUpdate()
                            .fetchOne();
            Integer expectedRevision = nullable(request.getExpectedRevision());
            if (existing == null && expectedRevision != null) {
                throw revisionConflict(expectedRevision, null, "新建草案不得携带 expectedRevision");
            }
            if (existing != null
                    && (expectedRevision == null
                            || !expectedRevision.equals(existing.getRevision()))) {
                throw revisionConflict(
                        expectedRevision,
                        existing.getRevision(),
                        "待审核草案修订号已变化");
            }
            Map<String, Object> payload = deepCopy(request.getPayload());
            Object diff = nullable(request.getDiff());
            if (ReviewArtifactRules.isSelection(payload)) {
                // 选区正文只从锁定的 Core 来源物化，绝不信任 Agent 回传的 selectedText 或全文。
                SelectionMaterialization materialized = ReviewArtifactRules.materializeSelection(
                        payload,
                        kind,
                        selectionSource(transaction, payload, request.getNovelId()));
                payload = new LinkedHashMap<>(materialized.payload());
                diff = materialized.diff();
            }
            if (requiresSourceBindings(transaction, kind, request.getTaskId())) {
                String sourceCommandId;
                if (existing == null) {
                    sourceCommandId = sourceBindingsForTask(transaction, request.getTaskId()).commandId();
                } else {
                    sourceCommandId = inheritedSourceCommand(existing);
                }
                payload.put("_inkforgeControl", Map.of("sourceCommandId", sourceCommandId));
            }
            String payloadJson = json.writeValueAsString(payload);
            String diffJson = diff == null ? null : json.writeValueAsString(diff);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            ReviewartifactRecord artifact;
            if (existing == null) {
                artifact = transaction.newRecord(REVIEWARTIFACT);
                artifact.setId(ids.next());
                artifact.setNovelid(request.getNovelId());
                artifact.setChapterid(chapterId);
                artifact.setTaskid(request.getTaskId());
                artifact.setWorkflowrunid(nullable(request.getWorkflowRunId()));
                artifact.setArtifactkey(artifactKey);
                artifact.setKind(Reviewartifactkind.lookupLiteral(kind));
                artifact.setStatus(Reviewartifactstatus.lookupLiteral(request.getStatus().getValue()));
                artifact.setTitle(nullable(request.getTitle()));
                artifact.setSummary(nullable(request.getSummary()));
                artifact.setPayloadjson(payloadJson);
                artifact.setDiffjson(diffJson);
                artifact.setCreatedbyagent(request.getCreatedByAgent().getValue());
                artifact.setUpdatedbyagent(request.getCreatedByAgent().getValue());
                var reviewer = nullable(request.getReviewerAgent());
                artifact.setRevieweragent(reviewer == null ? null : reviewer.getValue());
                artifact.setRevision(1);
                artifact.setCreatedat(now);
                artifact.setUpdatedat(now);
                artifact.store();
            } else {
                if (!existing.getKind().getLiteral().equals(kind)) {
                    throw new ApiException(
                            409,
                            "ARTIFACT_KIND_CONFLICT",
                            "同一草案标识不能变更草案类型");
                }
                ReviewArtifactRules.requireTransition(
                        existing.getStatus().getLiteral(), request.getStatus().getValue());
                existing.setStatus(Reviewartifactstatus.lookupLiteral(request.getStatus().getValue()));
                existing.setTitle(nullable(request.getTitle()));
                existing.setSummary(nullable(request.getSummary()));
                existing.setPayloadjson(payloadJson);
                existing.setDiffjson(diffJson);
                existing.setUpdatedbyagent(request.getCreatedByAgent().getValue());
                var reviewer = nullable(request.getReviewerAgent());
                existing.setRevieweragent(reviewer == null ? null : reviewer.getValue());
                existing.setRevision(existing.getRevision() + 1);
                existing.setUpdatedat(now);
                existing.update();
                artifact = existing;
            }
            // 当前行便于查询，Revision 行保存不可变审计；两者必须在同一事务同步推进。
            transaction.insertInto(REVIEWARTIFACTREVISION)
                    .set(REVIEWARTIFACTREVISION.ID, ids.next())
                    .set(REVIEWARTIFACTREVISION.ARTIFACTID, artifact.getId())
                    .set(REVIEWARTIFACTREVISION.REVISION, artifact.getRevision())
                    .set(REVIEWARTIFACTREVISION.SUMMARY, nullable(request.getSummary()))
                    .set(REVIEWARTIFACTREVISION.PAYLOADJSON, payloadJson)
                    .set(REVIEWARTIFACTREVISION.DIFFJSON, diffJson)
                    .set(
                            REVIEWARTIFACTREVISION.CREATEDBYAGENT,
                            request.getCreatedByAgent().getValue())
                    .set(REVIEWARTIFACTREVISION.CREATEDAT, now)
                    .execute();
            return new CreateResult(artifact.getId(), task.get(NOVEL.USERID));
        });
        return get(result.userId(), result.artifactId());
    }

    @Override
    public ReviewArtifactResponse submitEvaluation(
            String artifactId, SubmitArtifactEvaluationRequest request) {
        if (request.getVerdict() == SubmitArtifactEvaluationRequest.VerdictEnum.REVISE
                && (nullable(request.getRequiredChanges()) == null
                        || nullable(request.getRequiredChanges()).isEmpty())) {
            throw new IllegalArgumentException("要求修改时必须提供 requiredChanges");
        }
        String userId = database.transactionResult(transaction -> {
            Record task = transaction.select(NOVEL.USERID)
                    .from(WRITINGTASK)
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                    .where(
                            WRITINGTASK.ID.eq(request.getTaskId()),
                            WRITINGTASK.NOVELID.eq(request.getNovelId()))
                    .forUpdate()
                    .fetchOne();
            if (task == null) throw taskMismatch("复审结论与待审核草案资源不匹配");
            ReviewartifactRecord artifact = transaction.selectFrom(REVIEWARTIFACT)
                    .where(
                            REVIEWARTIFACT.ID.eq(artifactId),
                            REVIEWARTIFACT.NOVELID.eq(request.getNovelId()),
                            REVIEWARTIFACT.TASKID.eq(request.getTaskId()))
                    .forUpdate()
                    .fetchOne();
            if (artifact == null) throw taskMismatch("复审结论与待审核草案资源不匹配");
            requireCurrentJob(transaction, request.getTaskId(), request.getJobId());
            if (!artifact.getRevision().equals(request.getRevision())) {
                throw new ApiException(
                        409,
                        "ARTIFACT_REVISION_CONFLICT",
                        "复审结论对应的草案修订号已过期");
            }
            ReviewartifactevaluationRecord existing = transaction
                    .selectFrom(REVIEWARTIFACTEVALUATION)
                    .where(
                            REVIEWARTIFACTEVALUATION.ARTIFACTID.eq(artifactId),
                            REVIEWARTIFACTEVALUATION.REVISION.eq(request.getRevision()),
                            REVIEWARTIFACTEVALUATION.EVALUATORAGENT.eq(
                                    request.getEvaluatorAgent().getValue()))
                    .fetchOne();
            String requiredChanges = nullable(request.getRequiredChanges());
            if (existing != null) {
                // evaluator/revision 唯一键只允许完全相同的网络重放，不能覆盖已经参与合并的结论。
                boolean same = existing.getVerdict().getLiteral()
                                .equals(request.getVerdict().getValue())
                        && existing.getSummary().equals(request.getSummary())
                        && Objects.equals(existing.getRequiredchanges(), requiredChanges);
                if (!same) {
                    throw new ApiException(
                            409,
                            "ARTIFACT_EVALUATION_CONFLICT",
                            "同一复审智能体重复提交了不同结论");
                }
            } else {
                transaction.insertInto(REVIEWARTIFACTEVALUATION)
                        .set(REVIEWARTIFACTEVALUATION.ID, ids.next())
                        .set(REVIEWARTIFACTEVALUATION.ARTIFACTID, artifactId)
                        .set(REVIEWARTIFACTEVALUATION.REVISION, request.getRevision())
                        .set(
                                REVIEWARTIFACTEVALUATION.EVALUATORAGENT,
                                request.getEvaluatorAgent().getValue())
                        .set(
                                REVIEWARTIFACTEVALUATION.VERDICT,
                                Reviewartifactevaluationverdict.lookupLiteral(
                                        request.getVerdict().getValue()))
                        .set(REVIEWARTIFACTEVALUATION.SUMMARY, request.getSummary())
                        .set(REVIEWARTIFACTEVALUATION.REQUIREDCHANGES, requiredChanges)
                        .set(REVIEWARTIFACTEVALUATION.CREATEDAT, DatabaseTimestamp.now(clock))
                        .execute();
            }
            return task.get(NOVEL.USERID);
        });
        return get(userId, artifactId);
    }

    @Override
    public ArtifactConflictQuarantineResponse quarantine(
            String artifactId, ArtifactConflictQuarantineRequest request) {
        return database.transactionResult(transaction -> {
            Record task = transaction.select(NOVEL.USERID)
                    .from(WRITINGTASK)
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                    .where(
                            WRITINGTASK.ID.eq(request.getTaskId()),
                            WRITINGTASK.NOVELID.eq(request.getNovelId()))
                    .forUpdate()
                    .fetchOne();
            if (task == null) throw taskMismatch("待审核草案与写作任务资源不匹配");
            requireCurrentJob(transaction, request.getTaskId(), request.getJobId());
            ReviewartifactRecord artifact = transaction.selectFrom(REVIEWARTIFACT)
                    .where(
                            REVIEWARTIFACT.ID.eq(artifactId),
                            REVIEWARTIFACT.TASKID.eq(request.getTaskId()),
                            REVIEWARTIFACT.NOVELID.eq(request.getNovelId()))
                    .forUpdate()
                    .fetchOne();
            if (artifact == null) throw taskMismatch("待审核草案与写作任务资源不匹配");
            if (artifact.getStatus() == Reviewartifactstatus.under_review) {
                artifact.setStatus(Reviewartifactstatus.awaiting_user);
                artifact.setUpdatedat(DatabaseTimestamp.now(clock));
                artifact.update();
            } else if (artifact.getStatus() != Reviewartifactstatus.awaiting_user) {
                throw new ApiException(
                        409,
                        "ARTIFACT_STATUS_CONFLICT",
                        "当前草案状态不能隔离为等待用户确认");
            }
            return new ArtifactConflictQuarantineResponse(
                    artifact.getId(), artifact.getRevision(), "awaiting_user");
        });
    }

    @Override
    public ArtifactDecisionAcceptedResponse decide(
            String userId,
            String artifactId,
            ReviewArtifactDecisionRequest request) {
        return decisions.decide(userId, artifactId, request);
    }

    private ReviewArtifactResponse response(
            DSLContext context, ReviewartifactRecord artifact, boolean includeEvaluations) {
        Map<String, Object> payload = parseObject(artifact.getPayloadjson());
        if (!artifact.getKind().getLiteral().equals(payload.get("kind"))) {
            throw invalidPayload();
        }
        payload = new LinkedHashMap<>(payload);
        payload.remove("_inkforgeControl");
        Object diff = artifact.getDiffjson() == null
                ? null
                : parseValue(artifact.getDiffjson());
        SourceView sourceView = sourceView(context, artifact);
        List<ArtifactEvaluationResponse> evaluations = includeEvaluations
                ? context.selectFrom(REVIEWARTIFACTEVALUATION)
                        .where(REVIEWARTIFACTEVALUATION.ARTIFACTID.eq(artifact.getId()))
                        .orderBy(REVIEWARTIFACTEVALUATION.CREATEDAT.desc())
                        .fetch(this::evaluation)
                : List.of();
        ReviewArtifactResponse result = new ReviewArtifactResponse();
        result.setId(artifact.getId());
        result.setNovelId(artifact.getNovelid());
        result.setChapterId(artifact.getChapterid());
        result.setTaskId(artifact.getTaskid());
        result.setWorkflowRunId(artifact.getWorkflowrunid());
        result.setArtifactKey(artifact.getArtifactkey());
        result.setKind(ReviewArtifactResponse.KindEnum.fromValue(
                artifact.getKind().getLiteral()));
        result.setStatus(ReviewArtifactResponse.StatusEnum.fromValue(
                artifact.getStatus().getLiteral()));
        result.setTitle(artifact.getTitle());
        result.setSummary(artifact.getSummary());
        result.setPayload(payload);
        result.setDiff(JsonNullable.of(diff));
        result.setCreatedByAgent(artifact.getCreatedbyagent());
        result.setUpdatedByAgent(artifact.getUpdatedbyagent());
        result.setReviewerAgent(artifact.getRevieweragent());
        result.setRevision(artifact.getRevision());
        result.setEvaluations(evaluations);
        result.setSourceBindings(sourceView.bindings());
        result.setSourceBindingStatus(ReviewArtifactResponse.SourceBindingStatusEnum.fromValue(
                sourceView.status()));
        result.setCreatedAt(DatabaseTimestamp.api(artifact.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(artifact.getUpdatedat()));
        return result;
    }

    private ArtifactEvaluationResponse evaluation(ReviewartifactevaluationRecord value) {
        return new ArtifactEvaluationResponse(
                value.getArtifactid(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getEvaluatoragent(),
                value.getId(),
                value.getRequiredchanges(),
                value.getRevision(),
                value.getSummary(),
                ArtifactEvaluationResponse.VerdictEnum.fromValue(
                        value.getVerdict().getLiteral()));
    }

    private SourceView sourceView(DSLContext context, ReviewartifactRecord artifact) {
        if (!requiresSourceBindings(context, artifact.getKind().getLiteral(), artifact.getTaskid())) {
            return new SourceView(null, "not_yet_supported");
        }
        Map<String, Object> payload = parseObject(artifact.getPayloadjson());
        Object controlValue = payload.get("_inkforgeControl");
        if (!(controlValue instanceof Map<?, ?> control)
                || !(control.get("sourceCommandId") instanceof String sourceCommandId)
                || sourceCommandId.isEmpty()
                || artifact.getTaskid() == null) {
            return new SourceView(null, "legacy_missing");
        }
        WritingruncommandRecord command = context.selectFrom(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.ID.eq(sourceCommandId),
                        WRITINGRUNCOMMAND.TASKID.eq(artifact.getTaskid()),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .fetchOne();
        List<SourceBinding> bindings = command == null
                ? null
                : sourceBindings(command.getPayloadjson());
        // 历史 Artifact 允许只读显示 legacy_missing，但绝不能因此在批准时跳过来源门禁。
        return bindings == null
                ? new SourceView(null, "legacy_missing")
                : new SourceView(bindings, "verified");
    }

    private SelectionSource selectionSource(
            DSLContext context, Map<String, Object> payload, String novelId) {
        Object targetValue = payload.get("target");
        if (!(targetValue instanceof Map<?, ?> target)
                || !(target.get("resourceType") instanceof String type)
                || !(target.get("resourceId") instanceof String id)) {
            throw sourceConflict(typeOrNull(targetValue), null);
        }
        Record source;
        if ("chapter_content".equals(type)) {
            source = context.select(CHAPTER.CONTENT, CHAPTER.UPDATEDAT)
                    .from(CHAPTER)
                    .where(CHAPTER.ID.eq(id), CHAPTER.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne();
        } else if ("outline_content".equals(type)) {
            source = context.select(OUTLINE.CONTENT, OUTLINE.UPDATEDAT)
                    .from(OUTLINE)
                    .where(OUTLINE.ID.eq(id), OUTLINE.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne();
        } else if ("outline_node_content".equals(type)) {
            source = context.select(OUTLINENODE.CONTENT, OUTLINENODE.UPDATEDAT)
                    .from(OUTLINENODE)
                    .where(OUTLINENODE.ID.eq(id), OUTLINENODE.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne();
        } else {
            throw sourceConflict(type, id);
        }
        if (source == null) throw sourceConflict(type, id);
        String content;
        LocalDateTime updatedAt;
        if ("chapter_content".equals(type)) {
            content = source.get(CHAPTER.CONTENT);
            updatedAt = source.get(CHAPTER.UPDATEDAT);
        } else if ("outline_content".equals(type)) {
            content = source.get(OUTLINE.CONTENT);
            updatedAt = source.get(OUTLINE.UPDATEDAT);
        } else {
            content = source.get(OUTLINENODE.CONTENT);
            updatedAt = source.get(OUTLINENODE.UPDATEDAT);
        }
        if (content == null || updatedAt == null) throw sourceConflict(type, id);
        return new SelectionSource(type, id, content, DatabaseTimestamp.api(updatedAt));
    }

    private boolean requiresSourceBindings(DSLContext context, String kind, String taskId) {
        if ("beat_plan".equals(kind) || "chapter_draft".equals(kind)) return true;
        if (!"outline_draft".equals(kind) || taskId == null) return false;
        String payloadJson = context.select(WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(taskId),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .orderBy(WRITINGRUNCOMMAND.CREATEDAT.asc(), WRITINGRUNCOMMAND.ID.asc())
                .limit(1)
                .fetchOne(WRITINGRUNCOMMAND.PAYLOADJSON);
        if (payloadJson == null) return false;
        Map<String, Object> payload = parseObject(payloadJson);
        Object jobValue = payload.get("job");
        Map<?, ?> source = jobValue instanceof Map<?, ?> job ? job : payload;
        return "long_serial".equals(source.get("workflow"))
                && "rewrite_outline_selection".equals(source.get("operation"));
    }

    private SourceFacts sourceBindingsForTask(DSLContext context, String taskId) {
        WritingruncommandRecord command = context.selectFrom(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(taskId),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .orderBy(WRITINGRUNCOMMAND.CREATEDAT.asc(), WRITINGRUNCOMMAND.ID.asc())
                .limit(1)
                .fetchOne();
        if (command == null) {
            throw new ApiException(
                    409,
                    "ARTIFACT_SOURCE_BINDINGS_MISSING",
                    "待审核草案缺少权威来源命令");
        }
        List<SourceBinding> bindings = sourceBindings(command.getPayloadjson());
        if (bindings == null) {
            throw new ApiException(
                    409,
                    "ARTIFACT_SOURCE_BINDINGS_MISSING",
                    "待审核草案缺少权威来源绑定");
        }
        return new SourceFacts(command.getId(), bindings);
    }

    private List<SourceBinding> sourceBindings(String payloadJson) {
        try {
            Map<String, Object> payload = parseObject(payloadJson);
            Object jobValue = payload.get("job");
            Map<?, ?> source = jobValue instanceof Map<?, ?> job ? job : payload;
            Object bindingsValue = source.get("sourceBindings");
            if (!(bindingsValue instanceof List<?> values) || values.isEmpty()) return null;
            List<SourceBinding> bindings = new ArrayList<>();
            for (Object value : values) {
                bindings.add(json.convertValue(value, SourceBinding.class));
            }
            return List.copyOf(bindings);
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private String inheritedSourceCommand(ReviewartifactRecord existing) {
        Map<String, Object> payload = parseObject(existing.getPayloadjson());
        Object controlValue = payload.get("_inkforgeControl");
        Object value = controlValue instanceof Map<?, ?> control
                ? control.get("sourceCommandId")
                : null;
        if (!(value instanceof String sourceCommandId) || sourceCommandId.isEmpty()) {
            throw new ApiException(
                    409,
                    "ARTIFACT_SOURCE_BINDINGS_MISSING",
                    "待审核草案缺少可继承的来源命令");
        }
        return sourceCommandId;
    }

    private static void requireCurrentJob(DSLContext context, String taskId, String jobId) {
        String command = context.select(WRITINGRUNCOMMAND.ID)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.ID.eq(jobId),
                        WRITINGRUNCOMMAND.TASKID.eq(taskId),
                        WRITINGRUNCOMMAND.STATUS.in(ACTIVE_COMMAND_STATUSES))
                .forUpdate()
                .fetchOne(WRITINGRUNCOMMAND.ID);
        if (command == null) {
            throw new ApiException(
                    409,
                    "WRITING_JOB_MISMATCH",
                    "待审核草案写入作业不是当前活动命令");
        }
    }

    private ReviewartifactRecord ownedArtifact(
            DSLContext context, String userId, String artifactId, boolean lock) {
        var query = context.selectFrom(REVIEWARTIFACT)
                .where(
                        REVIEWARTIFACT.ID.eq(artifactId),
                        REVIEWARTIFACT.NOVELID.in(context.select(NOVEL.ID)
                                .from(NOVEL)
                                .where(NOVEL.USERID.eq(userId))));
        return lock ? query.forUpdate().fetchOne() : query.fetchOne();
    }

    private String encodeCursor(ReviewartifactRecord artifact) {
        String payload = json.writeValueAsString(Map.of(
                "createdAt", DatabaseTimestamp.api(artifact.getCreatedat()).toString(),
                "id", artifact.getId()));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
    }

    private CursorValue decodeCursor(String cursor) {
        try {
            String payload = new String(
                    Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8);
            JsonNode value = json.readTree(payload);
            String id = value.path("id").asString();
            OffsetDateTime createdAt = OffsetDateTime.parse(
                    value.path("createdAt").asString());
            if (id.isEmpty()) throw new IllegalArgumentException();
            return new CursorValue(DatabaseTimestamp.database(createdAt), id);
        } catch (RuntimeException exception) {
            throw new ApiException(
                    422,
                    "REVIEW_ARTIFACT_CURSOR_INVALID",
                    "待审核草案分页游标无效");
        }
    }

    private Map<String, Object> deepCopy(Map<String, Object> value) {
        return json.convertValue(value, new TypeReference<>() {});
    }

    private Map<String, Object> parseObject(String value) {
        try {
            Map<String, Object> result = json.readValue(value, new TypeReference<>() {});
            if (result == null) throw new IllegalArgumentException();
            return result;
        } catch (RuntimeException exception) {
            throw invalidPayload();
        }
    }

    private Object parseValue(String value) {
        try {
            return json.readValue(value, Object.class);
        } catch (RuntimeException exception) {
            throw invalidPayload();
        }
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static void requirePublicArtifactKey(String key) {
        if (key != null && key.startsWith("short-medium:")) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_VERSION_ROUTE_REQUIRED",
                    "中短篇版本只能通过专用版本接口创建");
        }
    }

    private static ApiException revisionConflict(
            Integer expected, Integer current, String message) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("expectedRevision", expected);
        details.put("currentRevision", current);
        return new ApiException(409, "ARTIFACT_REVISION_CONFLICT", message, details);
    }

    private static ApiException forbidden() {
        return new ApiException(
                403,
                "REVIEW_ARTIFACT_FORBIDDEN",
                "无权访问该待审核草案");
    }

    private static ApiException taskMismatch(String message) {
        return new ApiException(403, "ARTIFACT_TASK_MISMATCH", message);
    }

    private static ApiException invalidPayload() {
        return new ApiException(
                409,
                "ARTIFACT_PAYLOAD_INVALID",
                "待审核草案持久化内容格式错误");
    }

    private static ApiException sourceConflict(String resourceType, String resourceId) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("resourceType", resourceType);
        details.put("resourceId", resourceId);
        return new ApiException(
                409,
                "ARTIFACT_SOURCE_VERSION_CONFLICT",
                "选区草案的来源版本已变化",
                details);
    }

    private static String typeOrNull(Object target) {
        return target instanceof Map<?, ?> value && value.get("resourceType") instanceof String type
                ? type
                : null;
    }

    private record CreateResult(String artifactId, String userId) {}

    private record CursorValue(LocalDateTime createdAt, String id) {}

    private record SourceFacts(String commandId, List<SourceBinding> bindings) {}

    private record SourceView(List<SourceBinding> bindings, String status) {}
}
