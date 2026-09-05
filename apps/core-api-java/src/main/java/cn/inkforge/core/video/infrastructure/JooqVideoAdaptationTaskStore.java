package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.contracts.api.ChapterAdaptationTaskResponse;
import cn.inkforge.contracts.api.ChapterAdaptationPlanCandidate;
import cn.inkforge.contracts.api.DramaticStructureCheckpoint;
import cn.inkforge.contracts.api.ShotPromptSpecBatch;
import cn.inkforge.contracts.api.StartPromptRunRequest;
import cn.inkforge.contracts.api.StartShotPlanRunRequest;
import cn.inkforge.contracts.api.VideoAdaptationCheckpointCallback;
import cn.inkforge.contracts.api.VideoAdaptationFailureCallback;
import cn.inkforge.contracts.api.VideoAdaptationPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationPromptCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressQuery;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressResponse;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.tables.records.VideoadaptationtaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoAdaptationAgentStatus;
import cn.inkforge.core.video.application.VideoAdaptationTaskAcceptance;
import cn.inkforge.core.video.application.VideoAdaptationTaskDispatch;
import cn.inkforge.core.video.application.VideoAdaptationTaskStore;
import cn.inkforge.core.video.domain.VideoAdaptationPlans;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowVideoAdaptationCompletion;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;
import org.jooq.Condition;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 章节拆镜与逐镜提示词任务的耐久状态机。
 *
 * <p>任务创建时冻结章节、正式镜头版本、设定和目标镜头；Agent 回调只能完成同一最新 task/job/run 绑定。
 * 拆镜完成只创建待审 Artifact，提示词完成只保存候选批次，二者都不能越过作者确认直接改正式方案或 PromptHead。
 */
public final class JooqVideoAdaptationTaskStore implements VideoAdaptationTaskStore, WorkflowVideoAdaptationCompletion {

    private static final Set<String> ACTIVE = Set.of("pending", "submitted", "processing");
    private static final Set<String> TERMINAL = Set.of("completed", "failed", "cancelled");
    private static final String PROVIDER = "deepseek";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final String jobPrefix;
    private final JooqVideoAdaptationReadModel readModel;
    private final JooqVideoVisualCanonRepository visualCanons;
    private final JooqVideoSettingSnapshotBuilder settings;
    private final JooqVideoModelRunStarter durableStarter;

    public JooqVideoAdaptationTaskStore(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            JooqVideoVisualCanonRepository visualCanons,
            String dispatchNamespace) {
        this(database, ids, clock, json, visualCanons, dispatchNamespace, null, null, null);
    }

    public JooqVideoAdaptationTaskStore(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, JooqVideoVisualCanonRepository visualCanons, String dispatchNamespace,
            CoreSettings coreSettings, ExecutionRegistry registry, Supplier<DurableWorkflowService> workflows) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.visualCanons = Objects.requireNonNull(visualCanons);
        this.readModel = new JooqVideoAdaptationReadModel(json, visualCanons);
        this.settings = new JooqVideoSettingSnapshotBuilder(json);
        String namespace = dispatchNamespace == null ? "default" : dispatchNamespace;
        this.jobPrefix = "video-adaptation-" + namespace + "-";
        this.durableStarter = coreSettings == null ? null : new JooqVideoModelRunStarter(coreSettings, registry, workflows, json);
    }

    @Override
    public VideoAdaptationTaskAcceptance createPlanTask(
            String userId, String adaptationId, StartShotPlanRunRequest request) {
        return database.transactionResult(transaction -> {
            if (durableStarter != null) JooqVideoModelRunStarter.lockStartOwner(transaction, userId);
            var owned = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, adaptationId, true);
            VideochapteradaptationRecord adaptation = owned.adaptation();
            VideoprojectRecord project = owned.project();
            VideochapteradaptationheadRecord head = owned.head();
            String requestId = requestId(request.getClientRequestId());
            String idempotencyKey =
                    "video-adaptation-plan:" + userId + ":" + adaptationId + ":" + requestId;
            // 先重放再检查当前 Head：同一个已成功受理的请求不能因为后来版本变化而失去可重放性。
            VideoadaptationtaskRecord existing = transaction.selectFrom(VIDEOADAPTATIONTASK)
                    .where(VIDEOADAPTATIONTASK.IDEMPOTENCYKEY.eq(idempotencyKey))
                    .fetchOne();
            String baseId = nullable(request.getBaseShotPlanVersionId(), false);
            String revisionBrief = nullable(request.getRevisionBrief(), true);
            if (revisionBrief != null && baseId == null) {
                throw validation("没有正式镜头方案基线时不能提交修订重点");
            }
            String pacing = request.getPacingPreset().getValue();
            int targetSeconds = request.getTargetEpisodeSeconds().getValue();
            if (existing != null) {
                VideoAdaptationTaskPayload payload = parseStored(existing);
                if (!payload.isPlan()
                        || !pacing.equals(payload.pacingPreset())
                        || targetSeconds != payload.targetEpisodeSeconds()
                        || !Objects.equals(baseId, payload.baseShotPlanVersionId())
                        || !Objects.equals(revisionBrief, payload.revisionBrief())) {
                    throw idempotencyConflict("同一拆镜请求标识不能提交不同参数");
                }
                return new VideoAdaptationTaskAcceptance(adaptationId, existing.getId());
            }
            requireNoActiveTask(transaction, adaptationId);
            String awaiting = transaction.select(REVIEWARTIFACT.ID)
                    .from(REVIEWARTIFACT)
                    .where(
                            REVIEWARTIFACT.VIDEOADAPTATIONID.eq(adaptationId),
                            REVIEWARTIFACT.STATUS.eq(Reviewartifactstatus.awaiting_user))
                    .fetchAny(REVIEWARTIFACT.ID);
            if (awaiting != null) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_REVIEW_PENDING",
                        "当前已有待确认镜头方案，请先确认或放弃");
            }
            cn.inkforge.contracts.api.ChapterAdaptationPlanCandidate basePlan = null;
            if (head.getCurrentshotplanversionid() != null) {
                if (!head.getCurrentshotplanversionid().equals(baseId)) {
                    throw new ApiException(
                            409,
                            "VIDEO_ADAPTATION_BASE_PLAN_REQUIRED",
                            "已有正式方案时必须基于当前版本创建修订候选");
                }
                var detail = readModel.load(transaction, userId, adaptationId);
                if (detail.getCurrentPlan() == null) {
                    throw new ApiException(
                            409,
                            "VIDEO_ADAPTATION_BASE_PLAN_INVALID",
                            "当前正式镜头方案无法读取");
                }
                basePlan = VideoAdaptationPlans.candidateFromFormal(detail.getCurrentPlan());
            } else if (baseId != null) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_BASE_PLAN_INVALID",
                        "当前改编还没有可作为修订基线的正式方案");
            }
            String taskId = ids.next();
            String payload = VideoAdaptationTaskPayload.plan(
                    json,
                    adaptationId,
                    project.getId(),
                    adaptation.getChapterid() == null
                            ? "deleted-chapter"
                            : adaptation.getChapterid(),
                    adaptation.getChaptertitle(),
                    adaptation.getSourcetext(),
                    adaptation.getSourcehash(),
                    project.getTargetaspectratio(),
                    project.getTargetlanguage(),
                    pacing,
                    targetSeconds,
                    baseId,
                    basePlan,
                    revisionBrief);
            // 只有冻结输入完全相同，失败任务的戏剧结构才可复用；否则必须让 Agent 从章节原文重新分析。
            String inheritedCheckpoint = inheritedCheckpoint(
                    transaction,
                    adaptationId,
                    adaptation.getSourcehash(),
                    pacing,
                    targetSeconds,
                    baseId,
                    revisionBrief);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.insertInto(VIDEOADAPTATIONTASK)
                    .set(VIDEOADAPTATIONTASK.ID, taskId)
                    .set(VIDEOADAPTATIONTASK.ADAPTATIONID, adaptationId)
                    .set(VIDEOADAPTATIONTASK.PROJECTID, project.getId())
                    .set(VIDEOADAPTATIONTASK.NOVELID, adaptation.getNovelid())
                    .set(VIDEOADAPTATIONTASK.BASESHOTPLANVERSIONID, baseId)
                    .set(VIDEOADAPTATIONTASK.JOBID, jobPrefix + taskId)
                    .set(VIDEOADAPTATIONTASK.KIND, "shot_plan")
                    .set(VIDEOADAPTATIONTASK.WORKFLOW, VideoAdaptationTaskPayload.PLAN_WORKFLOW)
                    .set(VIDEOADAPTATIONTASK.PROVIDER, PROVIDER)
                    .set(VIDEOADAPTATIONTASK.STATUS, "pending")
                    .set(VIDEOADAPTATIONTASK.IDEMPOTENCYKEY, idempotencyKey)
                    .set(VIDEOADAPTATIONTASK.REQUESTJSON, payload)
                    .set(
                            VIDEOADAPTATIONTASK.CHECKPOINTSTAGE,
                            inheritedCheckpoint == null ? "none" : "dramatic_structure")
                    .set(VIDEOADAPTATIONTASK.CHECKPOINTJSON, inheritedCheckpoint)
                    .set(VIDEOADAPTATIONTASK.ATTEMPTCOUNT, 0)
                    .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOADAPTATIONTASK.CREATEDAT, now)
                    .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                    .execute();
            transaction.update(VIDEOCHAPTERADAPTATIONHEAD)
                    .set(
                            VIDEOCHAPTERADAPTATIONHEAD.UPDATEDAT,
                            DatabaseTimestamp.next(clock, head.getUpdatedat()))
                    .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId))
                    .execute();
            if (durableStarter != null) durableStarter.bind(userId, adaptation.getNovelid(), taskId, payload, inheritedCheckpoint);
            return new VideoAdaptationTaskAcceptance(adaptationId, taskId);
        });
    }

    @Override
    public VideoAdaptationTaskAcceptance createPromptTask(
            String userId, String adaptationId, StartPromptRunRequest request) {
        return database.transactionResult(transaction -> {
            if (durableStarter != null) JooqVideoModelRunStarter.lockStartOwner(transaction, userId);
            var owned = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, adaptationId, true);
            var adaptation = owned.adaptation();
            var project = owned.project();
            var head = owned.head();
            String requestId = requestId(request.getClientRequestId());
            List<String> requestedShotIds = list(request.getShotIds());
            if (new HashSet<>(requestedShotIds).size() != requestedShotIds.size()) {
                throw validation("逐镜提示词目标不能重复");
            }
            String idempotencyKey =
                    "video-adaptation-prompt:" + userId + ":" + adaptationId + ":" + requestId;
            VideoadaptationtaskRecord existing = transaction.selectFrom(VIDEOADAPTATIONTASK)
                    .where(VIDEOADAPTATIONTASK.IDEMPOTENCYKEY.eq(idempotencyKey))
                    .fetchOne();
            if (existing != null) {
                VideoAdaptationTaskPayload payload = parseStored(existing);
                if (!payload.isPrompt()
                        || !request.getShotPlanVersionId().equals(
                                payload.baseShotPlanVersionId())) {
                    throw idempotencyConflict("同一提示词请求标识不能提交不同镜头方案");
                }
                if (!requestedShotIds.isEmpty()) {
                    List<String> requestedKeys = transaction.select(VIDEOSHOT.SHOTKEY)
                            .from(VIDEOSHOT)
                            .where(
                                    VIDEOSHOT.PLANVERSIONID.eq(request.getShotPlanVersionId()),
                                    VIDEOSHOT.ID.in(requestedShotIds))
                            .orderBy(VIDEOSHOT.ORDINAL)
                            .fetch(VIDEOSHOT.SHOTKEY);
                    if (requestedKeys.size() != requestedShotIds.size()
                            || !requestedKeys.equals(payload.targetShotKeys())) {
                        throw idempotencyConflict("同一提示词请求标识不能提交不同镜头");
                    }
                }
                return new VideoAdaptationTaskAcceptance(adaptationId, existing.getId());
            }
            if (!Objects.equals(head.getRevision(), request.getExpectedAdaptationRevision())) {
                throw revisionConflict(head.getRevision());
            }
            if (!Objects.equals(
                    head.getCurrentshotplanversionid(), request.getShotPlanVersionId())) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_PLAN_CHANGED",
                        "当前正式镜头方案已经变化");
            }
            var detail = readModel.load(transaction, userId, adaptationId);
            if (detail.getCurrentPlan() == null) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_PLAN_REQUIRED",
                        "请先确认电影化镜头方案");
            }
            List<VideoshotRecord> shots = transaction.selectFrom(VIDEOSHOT)
                    .where(VIDEOSHOT.PLANVERSIONID.eq(request.getShotPlanVersionId()))
                    .orderBy(VIDEOSHOT.ORDINAL)
                    .forUpdate()
                    .fetch();
            List<VideoshotRecord> targets;
            if (!requestedShotIds.isEmpty()) {
                Set<String> requested = new HashSet<>(requestedShotIds);
                targets = shots.stream().filter(shot -> requested.contains(shot.getId())).toList();
                if (targets.size() != requested.size()) {
                    throw new ApiException(
                            422,
                            "VIDEO_ADAPTATION_SHOT_NOT_FOUND",
                            "提示词任务包含当前方案之外的镜头");
                }
            } else {
                Set<String> saved = detail.getPromptVersions().stream()
                        .map(value -> value.getShotId())
                        .collect(java.util.stream.Collectors.toSet());
                targets = shots.stream().filter(shot -> !saved.contains(shot.getId())).toList();
            }
            if (targets.isEmpty()) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_PROMPTS_COMPLETE",
                        "所选镜头均已有正式提示词");
            }
            requireNoActiveTask(transaction, adaptationId);
            List<String> targetKeys =
                    targets.stream().map(VideoshotRecord::getShotkey).toList();
            Map<String, Object> settingSnapshot =
                    settings.build(transaction, adaptation.getNovelid());
            Map<String, cn.inkforge.contracts.api.ShotVisualReferenceSetResponse> referenceSets =
                    new LinkedHashMap<>();
            visualCanons.shotReferences(transaction, shots)
                    .forEach(value -> referenceSets.put(value.getShotKey(), value));
            // 提示词任务冻结“设定快照 + 每镜参考版本”，执行期间修改设定卡不能偷偷改变已受理任务的输入。
            List<VideoAdaptationTaskPayload.VisualReferenceBundle> bundles = targetKeys.stream()
                    .map(key -> new VideoAdaptationTaskPayload.VisualReferenceBundle(
                            key, referenceSets.get(key).getReferences()))
                    .toList();
            String taskId = ids.next();
            String payload = VideoAdaptationTaskPayload.prompt(
                    json,
                    adaptationId,
                    project.getId(),
                    request.getShotPlanVersionId(),
                    adaptation.getSourcetext(),
                    adaptation.getSourcehash(),
                    VideoAdaptationPlans.candidateFromFormal(detail.getCurrentPlan()),
                    list(detail.getCurrentPlan().getEpisodeBreakAfterShotKeys()),
                    targetKeys,
                    project.getTargetaspectratio(),
                    project.getTargetlanguage(),
                    settingSnapshot,
                    bundles);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.insertInto(VIDEOADAPTATIONTASK)
                    .set(VIDEOADAPTATIONTASK.ID, taskId)
                    .set(VIDEOADAPTATIONTASK.ADAPTATIONID, adaptationId)
                    .set(VIDEOADAPTATIONTASK.PROJECTID, project.getId())
                    .set(VIDEOADAPTATIONTASK.NOVELID, adaptation.getNovelid())
                    .set(
                            VIDEOADAPTATIONTASK.BASESHOTPLANVERSIONID,
                            request.getShotPlanVersionId())
                    .set(VIDEOADAPTATIONTASK.JOBID, jobPrefix + taskId)
                    .set(VIDEOADAPTATIONTASK.KIND, "shot_prompt")
                    .set(VIDEOADAPTATIONTASK.WORKFLOW, VideoAdaptationTaskPayload.PROMPT_WORKFLOW)
                    .set(VIDEOADAPTATIONTASK.PROVIDER, PROVIDER)
                    .set(VIDEOADAPTATIONTASK.STATUS, "pending")
                    .set(VIDEOADAPTATIONTASK.IDEMPOTENCYKEY, idempotencyKey)
                    .set(VIDEOADAPTATIONTASK.REQUESTJSON, payload)
                    .set(VIDEOADAPTATIONTASK.CHECKPOINTSTAGE, "none")
                    .set(VIDEOADAPTATIONTASK.ATTEMPTCOUNT, 0)
                    .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOADAPTATIONTASK.CREATEDAT, now)
                    .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                    .execute();
            if (durableStarter != null) durableStarter.bind(userId, adaptation.getNovelid(), taskId, payload, null);
            return new VideoAdaptationTaskAcceptance(adaptationId, taskId);
        });
    }

    @Override
    public ChapterAdaptationTaskResponse getTask(String userId, String taskId) {
        Record row = database.dsl().select(VIDEOADAPTATIONTASK.fields())
                .select(NOVEL.USERID)
                .from(VIDEOADAPTATIONTASK)
                .join(VIDEOCHAPTERADAPTATION)
                .on(VIDEOCHAPTERADAPTATION.ID.eq(VIDEOADAPTATIONTASK.ADAPTATIONID))
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOCHAPTERADAPTATION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(VIDEOADAPTATIONTASK.ID.eq(taskId))
                .fetchOne();
        if (row == null || !userId.equals(row.get(NOVEL.USERID))) {
            throw new ApiException(
                    404,
                    "VIDEO_ADAPTATION_TASK_NOT_FOUND",
                    "章节影视化任务不存在");
        }
        return response(row.into(VIDEOADAPTATIONTASK));
    }

    @Override
    public List<VideoAdaptationTaskDispatch> claimDue(int limit) {
        if (limit < 1) throw new IllegalArgumentException("章节影视化任务领取数量必须为正整数");
        LocalDateTime now = DatabaseTimestamp.now(clock);
        LocalDateTime leaseUntil = now.plusSeconds(30);
        return database.transactionResult(transaction -> {
            // SKIP LOCKED 让多个 worker 分摊任务；nextAttemptAt 同时充当短租约，崩溃后任务可重新被领取。
            List<Record> rows = transaction.select(VIDEOADAPTATIONTASK.fields())
                    .select(NOVEL.USERID)
                    .from(VIDEOADAPTATIONTASK)
                    .join(VIDEOCHAPTERADAPTATION)
                    .on(VIDEOCHAPTERADAPTATION.ID.eq(VIDEOADAPTATIONTASK.ADAPTATIONID))
                    .join(VIDEOPROJECT)
                    .on(VIDEOPROJECT.ID.eq(VIDEOADAPTATIONTASK.PROJECTID))
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                    .where(
                            VIDEOADAPTATIONTASK.PROVIDER.eq(PROVIDER),
                            VIDEOADAPTATIONTASK.JOBID.like(jobPrefix + "%"),
                            VIDEOADAPTATIONTASK.STATUS.in(ACTIVE),
                            VIDEOADAPTATIONTASK.NEXTATTEMPTAT.le(now),
                            legacyTaskCondition(),
                            VIDEOPROJECT.DELETEDAT.isNull())
                    .orderBy(
                            VIDEOADAPTATIONTASK.NEXTATTEMPTAT,
                            VIDEOADAPTATIONTASK.CREATEDAT,
                            VIDEOADAPTATIONTASK.ID)
                    .limit(limit)
                    .forUpdate()
                    .of(VIDEOADAPTATIONTASK)
                    .skipLocked()
                    .fetch();
            List<VideoAdaptationTaskDispatch> result = new ArrayList<>();
            for (Record row : rows) {
                VideoadaptationtaskRecord task = row.into(VIDEOADAPTATIONTASK);
                try {
                    VideoAdaptationTaskPayload payload = parseStored(task);
                    validateTaskPayload(task, payload);
                    transaction.update(VIDEOADAPTATIONTASK)
                            .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, leaseUntil)
                            .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                            .where(VIDEOADAPTATIONTASK.ID.eq(task.getId()))
                            .execute();
                    result.add(new VideoAdaptationTaskDispatch(
                            row.get(NOVEL.USERID),
                            task.getNovelid(),
                            task.getId(),
                            task.getJobid(),
                            payload.agentPayload()));
                } catch (RuntimeException exception) {
                    failTask(
                            transaction,
                            task,
                            "failed",
                            "VIDEO_ADAPTATION_DISPATCH_INPUT_INVALID",
                            exception.getMessage(),
                            null);
                }
            }
            return List.copyOf(result);
        });
    }

    @Override
    public void markSubmitted(String taskId) {
        database.transactionResult(transaction -> {
            VideoadaptationtaskRecord task = lockTask(transaction, taskId);
            if (task != null && !hasDurableBinding(transaction, taskId) && ACTIVE.contains(task.getStatus())) {
                LocalDateTime now = DatabaseTimestamp.now(clock);
                transaction.update(VIDEOADAPTATIONTASK)
                        .set(
                                VIDEOADAPTATIONTASK.STATUS,
                                "pending".equals(task.getStatus())
                                        ? "submitted"
                                        : task.getStatus())
                        .set(
                                VIDEOADAPTATIONTASK.SUBMITTEDAT,
                                task.getSubmittedat() == null ? now : task.getSubmittedat())
                        .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, now.plusMinutes(10))
                        .set(VIDEOADAPTATIONTASK.LASTERRORCODE, (String) null)
                        .set(VIDEOADAPTATIONTASK.LASTERRORMESSAGE, (String) null)
                        .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                        .where(VIDEOADAPTATIONTASK.ID.eq(taskId))
                        .execute();
            }
            return null;
        });
    }

    @Override
    public void recordDispatchFailure(
            String taskId, String errorCode, boolean transientFailure) {
        database.transactionResult(transaction -> {
            VideoadaptationtaskRecord task = lockTask(transaction, taskId);
            if (task == null || hasDurableBinding(transaction, taskId) || TERMINAL.contains(task.getStatus())) return null;
            if (transientFailure) {
                int attempts = task.getAttemptcount() + 1;
                LocalDateTime now = DatabaseTimestamp.now(clock);
                transaction.update(VIDEOADAPTATIONTASK)
                        .set(VIDEOADAPTATIONTASK.ATTEMPTCOUNT, attempts)
                        .set(VIDEOADAPTATIONTASK.STATUS, "pending")
                        .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, now.plusSeconds(backoff(attempts)))
                        .set(
                                VIDEOADAPTATIONTASK.LASTERRORCODE,
                                "VIDEO_ADAPTATION_AGENT_SUBMIT_RETRY")
                        .set(
                                VIDEOADAPTATIONTASK.LASTERRORMESSAGE,
                                "章节影视化任务投递暂时失败：" + errorCode)
                        .set(VIDEOADAPTATIONTASK.COMPLETEDAT, (LocalDateTime) null)
                        .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                        .where(VIDEOADAPTATIONTASK.ID.eq(taskId))
                        .execute();
            } else {
                failTask(
                        transaction,
                        task,
                        "failed",
                        "VIDEO_ADAPTATION_AGENT_SUBMIT_FAILED",
                        "章节影视化任务投递失败：" + errorCode,
                        null);
            }
            return null;
        });
    }

    @Override
    public void settleDispatchTerminal(
            String taskId, VideoAdaptationAgentStatus status) {
        if (status == VideoAdaptationAgentStatus.QUEUED
                || status == VideoAdaptationAgentStatus.RUNNING) {
            throw new IllegalArgumentException("活动 Agent 状态不能按终态收敛");
        }
        database.transactionResult(transaction -> {
            VideoadaptationtaskRecord task = lockTask(transaction, taskId);
            if (task == null || hasDurableBinding(transaction, taskId) || TERMINAL.contains(task.getStatus())) return null;
            failTask(
                    transaction,
                    task,
                    status == VideoAdaptationAgentStatus.CANCELLED ? "cancelled" : "failed",
                    "VIDEO_ADAPTATION_AGENT_TERMINAL_WITHOUT_CALLBACK",
                    "Agent 队列已进入 " + status.name().toLowerCase()
                            + "，但 Core 未收到章节影视化终态回调",
                    null);
            return null;
        });
    }

    @Override
    public VideoAdaptationWorkflowProgressResponse progress(
            VideoAdaptationWorkflowProgressQuery query) {
        return database.transactionResult(transaction -> {
            CallbackContext context = callbackContext(transaction, identity(query));
            VideoadaptationtaskRecord task = context.task();
            VideoAdaptationWorkflowProgressResponse.StatusEnum status;
            if (ACTIVE.contains(task.getStatus())) {
                LocalDateTime now = DatabaseTimestamp.now(clock);
                transaction.update(VIDEOADAPTATIONTASK)
                        .set(VIDEOADAPTATIONTASK.STATUS, "processing")
                        .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, now.plusMinutes(10))
                        .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                        .where(VIDEOADAPTATIONTASK.ID.eq(task.getId()))
                        .execute();
                status = VideoAdaptationWorkflowProgressResponse.StatusEnum.ACTIVE;
            } else if ("completed".equals(task.getStatus())) {
                status = VideoAdaptationWorkflowProgressResponse.StatusEnum.COMPLETED;
            } else {
                status = VideoAdaptationWorkflowProgressResponse.StatusEnum.FAILED;
            }
            var response = new VideoAdaptationWorkflowProgressResponse(
                    query.getAdaptationId(),
                    query.getJobId(),
                    query.getNovelId(),
                    query.getProjectId(),
                    query.getProtocolVersion(),
                    query.getRunId(),
                    status,
                    query.getTaskId(),
                    VideoAdaptationWorkflowProgressResponse.WorkflowEnum.fromValue(
                            task.getWorkflow()));
            if (task.getCheckpointjson() != null) {
                response.setCheckpoint(
                        json.readValue(task.getCheckpointjson(), DramaticStructureCheckpoint.class));
            }
            return response;
        });
    }

    @Override
    public void saveCheckpoint(VideoAdaptationCheckpointCallback callback) {
        database.transactionResult(transaction -> {
            CallbackContext context = callbackContext(transaction, identity(callback));
            VideoadaptationtaskRecord task = context.task();
            if (!"shot_plan".equals(task.getKind()) || !ACTIVE.contains(task.getStatus())) {
                throw callbackStateConflict();
            }
            String checkpoint = json.writeValueAsString(callback.getCheckpoint());
            if ("dramatic_structure".equals(task.getCheckpointstage())) {
                // 同一阶段仅允许内容完全相同的回放，避免迟到回调覆盖已用于后续拆镜的结构分析。
                if (jsonEquivalent(task.getCheckpointjson(), checkpoint)) return null;
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_CHECKPOINT_CONFLICT",
                        "同一戏剧结构阶段不能覆盖不同内容");
            }
            if (!"none".equals(task.getCheckpointstage()) || task.getCheckpointjson() != null) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_CHECKPOINT_CONFLICT",
                        "章节影视化检查点阶段非法");
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.update(VIDEOADAPTATIONTASK)
                    .set(VIDEOADAPTATIONTASK.STATUS, "processing")
                    .set(VIDEOADAPTATIONTASK.CHECKPOINTSTAGE, "dramatic_structure")
                    .set(VIDEOADAPTATIONTASK.CHECKPOINTJSON, checkpoint)
                    .set(VIDEOADAPTATIONTASK.NEXTATTEMPTAT, now.plusMinutes(10))
                    .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                    .where(VIDEOADAPTATIONTASK.ID.eq(task.getId()))
                    .execute();
            return null;
        });
    }

    @Override
    public void completePlan(VideoAdaptationPlanCompletionCallback callback) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("eventId", callback.getEventId());
        result.put("workflow", VideoAdaptationTaskPayload.PLAN_WORKFLOW);
        result.put("candidate", VideoAdaptationPlans.candidateMap(callback.getCandidate()));
        String resultJson = canonicalJson(result);
        database.transactionResult(transaction -> {
            CallbackContext context = callbackContext(transaction, identity(callback));
            VideoadaptationtaskRecord task = context.task();
            if (!"shot_plan".equals(task.getKind())) throw callbackStateConflict();
            if ("completed".equals(task.getStatus())) {
                if (jsonEquivalent(task.getResultjson(), resultJson)) return null;
                throw terminalCallbackConflict();
            }
            if (!ACTIVE.contains(task.getStatus())) throw callbackStateConflict();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            createPlanArtifact(transaction, context, callback.getCandidate(), now);
            completeTask(transaction, task, resultJson, now);
            return null;
        });
    }

    @Override
    public void completePrompts(VideoAdaptationPromptCompletionCallback callback) {
        validatePromptBatch(callback.getPromptBatch());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("eventId", callback.getEventId());
        result.put("workflow", VideoAdaptationTaskPayload.PROMPT_WORKFLOW);
        result.put(
                "promptBatch",
                json.convertValue(
                        callback.getPromptBatch(),
                        new TypeReference<Map<String, Object>>() {}));
        String resultJson = canonicalJson(result);
        database.transactionResult(transaction -> {
            CallbackContext context = callbackContext(transaction, identity(callback));
            VideoadaptationtaskRecord task = context.task();
            if (!"shot_prompt".equals(task.getKind())) throw callbackStateConflict();
            if ("completed".equals(task.getStatus())) {
                if (jsonEquivalent(task.getResultjson(), resultJson)) return null;
                throw terminalCallbackConflict();
            }
            if (!ACTIVE.contains(task.getStatus())) throw callbackStateConflict();
            VideoAdaptationTaskPayload payload = parseStored(task);
            if (!payload.isPrompt()) throw callbackStateConflict();
            List<String> actual = callback.getPromptBatch().getPrompts().stream()
                    .map(value -> value.getShotKey())
                    .toList();
            if (!actual.equals(payload.targetShotKeys())) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_PROMPT_TARGET_MISMATCH",
                        "逐镜提示词结果没有按请求顺序完整覆盖目标镜头");
            }
            // 此处只持久化完整候选批次；逐镜 PromptHead 必须经用户保存命令逐个推进。
            completeTask(
                    transaction, task, resultJson, DatabaseTimestamp.now(clock));
            return null;
        });
    }

    @Override
    public void fail(VideoAdaptationFailureCallback callback) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("eventId", callback.getEventId());
        result.put("code", callback.getCode());
        result.put("message", callback.getMessage());
        result.put("recoverable", callback.getRecoverable());
        String resultJson = canonicalJson(result);
        database.transactionResult(transaction -> {
            CallbackContext context = callbackContext(transaction, identity(callback));
            VideoadaptationtaskRecord task = context.task();
            if ("failed".equals(task.getStatus())) {
                if (jsonEquivalent(task.getResultjson(), resultJson)) return null;
                throw terminalCallbackConflict();
            }
            if (!ACTIVE.contains(task.getStatus())) throw callbackStateConflict();
            failTask(
                    transaction,
                    task,
                    "failed",
                    callback.getCode(),
                    callback.getMessage(),
                    resultJson);
            return null;
        });
    }

    @Override
    public boolean targetExists(DSLContext transaction, String runId) {
        return durableContext(transaction, DurableVideoAdaptationRun.load(transaction, json, runId)) != null;
    }

    @Override
    public void markProcessing(DSLContext transaction, String runId) {
        CallbackContext context = durableContext(transaction, DurableVideoAdaptationRun.load(transaction, json, runId));
        if (context == null || !ACTIVE.contains(context.task().getStatus())) return;
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.update(VIDEOADAPTATIONTASK).set(VIDEOADAPTATIONTASK.STATUS, "processing")
                .set(VIDEOADAPTATIONTASK.SUBMITTEDAT, context.task().getSubmittedat() == null ? now : context.task().getSubmittedat())
                .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                .where(VIDEOADAPTATIONTASK.ID.eq(context.task().getId())).execute();
    }

    @Override
    public void saveDramaticCheckpoint(DSLContext transaction, String runId, Map<String, Object> checkpoint) {
        var normalized = json.convertValue(checkpoint, DramaticStructureCheckpoint.class);
        CallbackContext context = durableContext(transaction, DurableVideoAdaptationRun.load(transaction, json, runId));
        if (context == null || !"shot_plan".equals(context.task().getKind()) || !ACTIVE.contains(context.task().getStatus())) {
            throw callbackStateConflict();
        }
        var task = context.task();
        String value = json.writeValueAsString(normalized);
        if ("dramatic_structure".equals(task.getCheckpointstage())) {
            if (jsonEquivalent(task.getCheckpointjson(), value)) return;
            throw new ApiException(409, "VIDEO_ADAPTATION_CHECKPOINT_CONFLICT", "同一戏剧结构阶段不能覆盖不同内容");
        }
        if (!"none".equals(task.getCheckpointstage()) || task.getCheckpointjson() != null) throw callbackStateConflict();
        transaction.update(VIDEOADAPTATIONTASK).set(VIDEOADAPTATIONTASK.STATUS, "processing")
                .set(VIDEOADAPTATIONTASK.CHECKPOINTSTAGE, "dramatic_structure").set(VIDEOADAPTATIONTASK.CHECKPOINTJSON, value)
                .set(VIDEOADAPTATIONTASK.UPDATEDAT, DatabaseTimestamp.now(clock))
                .where(VIDEOADAPTATIONTASK.ID.eq(task.getId())).execute();
    }

    @Override
    public Completion completePlan(DSLContext transaction, String runId, Map<String, Object> candidate) {
        var run = DurableVideoAdaptationRun.load(transaction, json, runId);
        CallbackContext context = durableContext(transaction, run);
        if (context == null) return new Completion("cancelled", run.taskId(), null);
        var task = context.task();
        if (!"shot_plan".equals(task.getKind())) throw callbackStateConflict();
        var normalized = json.convertValue(candidate, ChapterAdaptationPlanCandidate.class);
        String resultJson = canonicalJson(Map.of("eventId", "video-v2-result." + runId,
                "workflow", VideoAdaptationTaskPayload.PLAN_WORKFLOW, "candidate", VideoAdaptationPlans.candidateMap(normalized)));
        if ("completed".equals(task.getStatus())) {
            if (!jsonEquivalent(task.getResultjson(), resultJson)) throw terminalCallbackConflict();
            String artifactId = transaction.select(REVIEWARTIFACT.ID).from(REVIEWARTIFACT)
                    .where(REVIEWARTIFACT.VIDEOADAPTATIONTASKID.eq(task.getId())).fetchOne(REVIEWARTIFACT.ID);
            return new Completion("completed", task.getId(), artifactId);
        }
        if (!ACTIVE.contains(task.getStatus())) throw callbackStateConflict();
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String artifactId = createPlanArtifact(transaction, context, normalized, now);
        completeTask(transaction, task, resultJson, now);
        return new Completion("completed", task.getId(), artifactId);
    }

    @Override
    public Completion completePrompts(DSLContext transaction, String runId, Map<String, Object> batch) {
        var normalized = json.convertValue(batch, ShotPromptSpecBatch.class);
        validatePromptBatch(normalized);
        var run = DurableVideoAdaptationRun.load(transaction, json, runId);
        CallbackContext context = durableContext(transaction, run);
        if (context == null) return new Completion("cancelled", run.taskId(), null);
        var task = context.task();
        if (!"shot_prompt".equals(task.getKind())) throw callbackStateConflict();
        String resultJson = canonicalJson(Map.of("eventId", "video-v2-result." + runId,
                "workflow", VideoAdaptationTaskPayload.PROMPT_WORKFLOW,
                "promptBatch", json.convertValue(normalized, new TypeReference<Map<String, Object>>() {})));
        if ("completed".equals(task.getStatus())) {
            if (!jsonEquivalent(task.getResultjson(), resultJson)) throw terminalCallbackConflict();
            return new Completion("completed", task.getId(), null);
        }
        if (!ACTIVE.contains(task.getStatus())) throw callbackStateConflict();
        List<String> actual = normalized.getPrompts().stream().map(value -> value.getShotKey()).toList();
        if (!actual.equals(parseStored(task).targetShotKeys())) {
            throw new ApiException(409, "VIDEO_ADAPTATION_PROMPT_TARGET_MISMATCH", "逐镜提示词结果没有按请求顺序完整覆盖目标镜头");
        }
        completeTask(transaction, task, resultJson, DatabaseTimestamp.now(clock));
        return new Completion("completed", task.getId(), null);
    }

    @Override
    public String finish(DSLContext transaction, String runId, String terminal, String code, String message) {
        if (!Set.of("failed", "cancelled").contains(terminal)) throw new IllegalArgumentException("视频失败投影终态无效");
        var run = DurableVideoAdaptationRun.load(transaction, json, runId);
        CallbackContext context = durableContext(transaction, run);
        if (context == null) return "cancelled";
        if (ACTIVE.contains(context.task().getStatus())) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("eventId", "video-v2-terminal." + runId); result.put("code", code);
            result.put("message", message); result.put("recoverable", false);
            failTask(transaction, context.task(), terminal, code, message, canonicalJson(result));
        } else if (!terminal.equals(context.task().getStatus())) {
            throw callbackStateConflict();
        }
        return terminal;
    }

    private CallbackContext durableContext(DSLContext transaction, DurableVideoAdaptationRun run) {
        // 调用方先完成预算/用户账务，再按 Novel→Project→Adaptation→Head→Task 投影业务。
        if (transaction.fetchOne("SELECT id FROM public.\"Novel\" WHERE id=? AND \"userId\"=? FOR KEY SHARE",
                run.novelId(), run.userId()) == null) return null;
        VideoadaptationtaskRecord observed = transaction.selectFrom(VIDEOADAPTATIONTASK)
                .where(VIDEOADAPTATIONTASK.ID.eq(run.taskId())).fetchOne();
        if (observed == null) return null;
        VideoprojectRecord project = transaction.selectFrom(VIDEOPROJECT)
                .where(VIDEOPROJECT.ID.eq(observed.getProjectid())).forUpdate().fetchOne();
        VideochapteradaptationRecord adaptation = transaction.selectFrom(VIDEOCHAPTERADAPTATION)
                .where(VIDEOCHAPTERADAPTATION.ID.eq(run.adaptationId())).forUpdate().fetchOne();
        var head = transaction.selectFrom(VIDEOCHAPTERADAPTATIONHEAD)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(run.adaptationId())).forUpdate().fetchOne();
        VideoadaptationtaskRecord task = lockTask(transaction, run.taskId());
        if (project == null || adaptation == null || head == null || task == null) return null;
        if (!run.novelId().equals(task.getNovelid()) || !run.novelId().equals(project.getNovelid())
                || !run.novelId().equals(adaptation.getNovelid()) || !run.adaptationId().equals(task.getAdaptationid())
                || !project.getId().equals(adaptation.getProjectid()) || !run.operation().equals(task.getWorkflow())) {
            throw new IllegalArgumentException("视频 V2 Run 与原任务归属不匹配");
        }
        var context = run.frozenContext(transaction, json);
        VideoAdaptationTaskPayload payload = parseStored(task);
        validateTaskPayload(task, payload);
        if (!jsonEquivalent(json.writeValueAsString(context.get("payload")), json.writeValueAsString(payload.agentPayload()))) {
            throw new IllegalArgumentException("视频 V2 Task 冻结输入与 Evidence 不匹配");
        }
        return new CallbackContext(task, adaptation, project);
    }

    private String createPlanArtifact(DSLContext transaction, CallbackContext context,
            ChapterAdaptationPlanCandidate candidate, LocalDateTime now) {
        try {
            VideoAdaptationPlans.validateAgainstSource(candidate, context.adaptation().getId(),
                    context.adaptation().getSourcetext(), context.adaptation().getSourcehash());
        } catch (IllegalArgumentException exception) { throw validation(exception.getMessage()); }
        String awaiting = transaction.select(REVIEWARTIFACT.ID).from(REVIEWARTIFACT)
                .where(REVIEWARTIFACT.VIDEOADAPTATIONID.eq(context.adaptation().getId()),
                        REVIEWARTIFACT.STATUS.eq(Reviewartifactstatus.awaiting_user)).fetchAny(REVIEWARTIFACT.ID);
        if (awaiting != null) throw new ApiException(409, "VIDEO_ADAPTATION_REVIEW_PENDING", "当前已有待确认章节镜头方案");
        String artifactId = ids.next();
        Map<String, Object> payload = Map.of("applyTarget", Map.of("type", "video_adaptation_plan",
                "adaptationId", context.adaptation().getId()), "candidate", VideoAdaptationPlans.candidateMap(candidate));
        transaction.insertInto(REVIEWARTIFACT).set(REVIEWARTIFACT.ID, artifactId)
                .set(REVIEWARTIFACT.NOVELID, context.adaptation().getNovelid()).set(REVIEWARTIFACT.CHAPTERID, context.adaptation().getChapterid())
                .set(REVIEWARTIFACT.KIND, Reviewartifactkind.video_adaptation_plan).set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.awaiting_user)
                .set(REVIEWARTIFACT.TITLE, context.adaptation().getChaptertitle() + " · 电影化镜头方案")
                .set(REVIEWARTIFACT.SUMMARY, summary(candidate)).set(REVIEWARTIFACT.PAYLOADJSON, json.writeValueAsString(payload))
                .set(REVIEWARTIFACT.ARTIFACTKEY, "video-adaptation-plan:" + context.adaptation().getId() + ":" + context.task().getId())
                .set(REVIEWARTIFACT.REVISION, 1).set(REVIEWARTIFACT.CREATEDBYAGENT, "剧情")
                .set(REVIEWARTIFACT.VIDEOADAPTATIONID, context.adaptation().getId()).set(REVIEWARTIFACT.VIDEOADAPTATIONTASKID, context.task().getId())
                .set(REVIEWARTIFACT.CREATEDAT, now).set(REVIEWARTIFACT.UPDATEDAT, now).execute();
        return artifactId;
    }

    private static Condition legacyTaskCondition() {
        // sourceType/sourceId 是旧 schema 已有字段；关闭新路由也不能让已有 V2 任务被旧队列误领。
        return org.jooq.impl.DSL.notExists(org.jooq.impl.DSL.selectOne().from(WORKFLOWRUN)
                .where(WORKFLOWRUN.SOURCETYPE.eq(DurableVideoAdaptationRun.SOURCE_TYPE),
                        WORKFLOWRUN.SOURCEID.eq(VIDEOADAPTATIONTASK.ID)));
    }

    private static boolean hasDurableBinding(DSLContext transaction, String taskId) {
        return transaction.fetchExists(transaction.selectOne().from(WORKFLOWRUN)
                .where(WORKFLOWRUN.SOURCETYPE.eq(DurableVideoAdaptationRun.SOURCE_TYPE), WORKFLOWRUN.SOURCEID.eq(taskId)));
    }

    private CallbackContext callbackContext(
            DSLContext transaction, CallbackIdentity identity) {
        // 先按固定顺序锁项目、改编、Head，最后锁任务；所有回调共用顺序以规避交叉死锁。
        VideoadaptationtaskRecord observed = transaction.selectFrom(VIDEOADAPTATIONTASK)
                .where(VIDEOADAPTATIONTASK.ID.eq(identity.taskId()))
                .fetchOne();
        if (observed == null) {
            throw new ApiException(
                    404,
                    "VIDEO_ADAPTATION_TASK_NOT_FOUND",
                    "章节影视化任务不存在");
        }
        if (hasDurableBinding(transaction, observed.getId())) {
            throw new ApiException(409, "VIDEO_ADAPTATION_V2_CALLBACK_REQUIRED", "该任务由耐久执行回调收敛，不接受旧任务回调");
        }
        // 新旧候选投影与作者决定使用相同的 Novel→Project 顺序。
        transaction.fetchOne("SELECT id FROM public.\"Novel\" WHERE id=? FOR KEY SHARE", observed.getNovelid());
        VideoprojectRecord project = transaction.selectFrom(VIDEOPROJECT)
                .where(VIDEOPROJECT.ID.eq(observed.getProjectid()))
                .forUpdate()
                .fetchOne();
        VideochapteradaptationRecord adaptation = transaction
                .selectFrom(VIDEOCHAPTERADAPTATION)
                .where(VIDEOCHAPTERADAPTATION.ID.eq(observed.getAdaptationid()))
                .forUpdate()
                .fetchOne();
        VideochapteradaptationheadRecord head = transaction
                .selectFrom(VIDEOCHAPTERADAPTATIONHEAD)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(
                        observed.getAdaptationid()))
                .forUpdate()
                .fetchOne();
        VideoadaptationtaskRecord task = lockTask(transaction, identity.taskId());
        if (project == null || adaptation == null || head == null || task == null) {
            throw new ApiException(
                    409,
                    "VIDEO_ADAPTATION_CALLBACK_TARGET_INVALID",
                    "章节影视化回调目标已经不存在");
        }
        if (!task.getJobid().equals(identity.jobId())
                || !task.getId().equals(identity.runId())
                || !task.getNovelid().equals(identity.novelId())
                || !task.getProjectid().equals(identity.projectId())
                || !task.getAdaptationid().equals(identity.adaptationId())
                || (identity.workflow() != null
                        && !task.getWorkflow().equals(identity.workflow()))) {
            throw new ApiException(
                    403,
                    "VIDEO_ADAPTATION_CALLBACK_RESOURCE_MISMATCH",
                    "章节影视化回调资源绑定不匹配");
        }
        String latestId = transaction.select(VIDEOADAPTATIONTASK.ID)
                .from(VIDEOADAPTATIONTASK)
                .where(
                        VIDEOADAPTATIONTASK.ADAPTATIONID.eq(task.getAdaptationid()),
                        VIDEOADAPTATIONTASK.KIND.eq(task.getKind()))
                .orderBy(VIDEOADAPTATIONTASK.CREATEDAT.desc(), VIDEOADAPTATIONTASK.ID.desc())
                .limit(1)
                .fetchOne(VIDEOADAPTATIONTASK.ID);
        // 身份匹配仍不够：同类旧任务的迟到终态不能覆盖作者后来启动的新一轮结果。
        if (!task.getId().equals(latestId)) {
            throw new ApiException(
                    409,
                    "VIDEO_ADAPTATION_CALLBACK_STALE",
                    "旧章节影视化任务不能覆盖更新任务");
        }
        return new CallbackContext(task, adaptation, project);
    }

    private String inheritedCheckpoint(
            DSLContext transaction,
            String adaptationId,
            String sourceHash,
            String pacing,
            int targetSeconds,
            String baseId,
            String brief) {
        List<VideoadaptationtaskRecord> failed = transaction.selectFrom(VIDEOADAPTATIONTASK)
                .where(
                        VIDEOADAPTATIONTASK.ADAPTATIONID.eq(adaptationId),
                        VIDEOADAPTATIONTASK.KIND.eq("shot_plan"),
                        VIDEOADAPTATIONTASK.STATUS.eq("failed"),
                        VIDEOADAPTATIONTASK.CHECKPOINTSTAGE.eq("dramatic_structure"),
                        VIDEOADAPTATIONTASK.CHECKPOINTJSON.isNotNull())
                .orderBy(VIDEOADAPTATIONTASK.CREATEDAT.desc(), VIDEOADAPTATIONTASK.ID.desc())
                .limit(1)
                .forUpdate()
                .fetch();
        if (failed.isEmpty()) return null;
        try {
            VideoAdaptationTaskPayload payload = parseStored(failed.getFirst());
            if (payload.isPlan()
                    && sourceHash.equals(payload.sourceHash())
                    && pacing.equals(payload.pacingPreset())
                    && targetSeconds == payload.targetEpisodeSeconds()
                    && Objects.equals(baseId, payload.baseShotPlanVersionId())
                    && Objects.equals(brief, payload.revisionBrief())) {
                DramaticStructureCheckpoint checkpoint = json.readValue(
                        failed.getFirst().getCheckpointjson(),
                        DramaticStructureCheckpoint.class);
                return json.writeValueAsString(checkpoint);
            }
        } catch (RuntimeException ignored) {
            // 损坏的旧检查点不可继承，但不能阻断一份全新任务。
        }
        return null;
    }

    private VideoAdaptationTaskPayload parseStored(VideoadaptationtaskRecord task) {
        try {
            return VideoAdaptationTaskPayload.parse(json, task.getRequestjson());
        } catch (RuntimeException exception) {
            throw new ApiException(
                    409,
                    "VIDEO_ADAPTATION_TASK_INPUT_INVALID",
                    "章节影视化任务冻结输入已损坏");
        }
    }

    private static void validateTaskPayload(
            VideoadaptationtaskRecord task, VideoAdaptationTaskPayload payload) {
        boolean common = task.getAdaptationid().equals(payload.adaptationId())
                && task.getProjectid().equals(payload.projectId())
                && task.getWorkflow().equals(payload.workflow());
        if (!common) throw new IllegalArgumentException("章节影视化任务冻结输入与任务归属不一致");
        if (payload.isPlan()) {
            if (!"shot_plan".equals(task.getKind())
                    || !Objects.equals(
                            task.getBaseshotplanversionid(), payload.baseShotPlanVersionId())) {
                throw new IllegalArgumentException("章节拆镜任务类型或基础版本不一致");
            }
        } else if (!"shot_prompt".equals(task.getKind())
                || !Objects.equals(
                        task.getBaseshotplanversionid(), payload.baseShotPlanVersionId())) {
            throw new IllegalArgumentException("逐镜提示词任务类型或基础版本不一致");
        }
    }

    private void completeTask(
            DSLContext transaction,
            VideoadaptationtaskRecord task,
            String resultJson,
            LocalDateTime now) {
        transaction.update(VIDEOADAPTATIONTASK)
                .set(VIDEOADAPTATIONTASK.STATUS, "completed")
                .set(VIDEOADAPTATIONTASK.RESULTJSON, resultJson)
                .set(VIDEOADAPTATIONTASK.COMPLETEDAT, now)
                .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                .where(VIDEOADAPTATIONTASK.ID.eq(task.getId()))
                .execute();
    }

    private void failTask(
            DSLContext transaction,
            VideoadaptationtaskRecord task,
            String status,
            String code,
            String message,
            String resultJson) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.update(VIDEOADAPTATIONTASK)
                .set(VIDEOADAPTATIONTASK.STATUS, status)
                .set(VIDEOADAPTATIONTASK.LASTERRORCODE, code)
                .set(VIDEOADAPTATIONTASK.LASTERRORMESSAGE, message)
                .set(VIDEOADAPTATIONTASK.RESULTJSON, resultJson)
                .set(VIDEOADAPTATIONTASK.COMPLETEDAT, now)
                .set(VIDEOADAPTATIONTASK.UPDATEDAT, now)
                .where(VIDEOADAPTATIONTASK.ID.eq(task.getId()))
                .execute();
    }

    private static VideoadaptationtaskRecord lockTask(DSLContext context, String taskId) {
        return context.selectFrom(VIDEOADAPTATIONTASK)
                .where(VIDEOADAPTATIONTASK.ID.eq(taskId))
                .forUpdate()
                .fetchOne();
    }

    private static void requireNoActiveTask(DSLContext context, String adaptationId) {
        String active = context.select(VIDEOADAPTATIONTASK.ID)
                .from(VIDEOADAPTATIONTASK)
                .where(
                        VIDEOADAPTATIONTASK.ADAPTATIONID.eq(adaptationId),
                        VIDEOADAPTATIONTASK.STATUS.in(ACTIVE))
                .fetchAny(VIDEOADAPTATIONTASK.ID);
        if (active != null) {
            throw new ApiException(
                    409,
                    "VIDEO_ADAPTATION_TASK_ACTIVE",
                    "当前章节改编已有活动任务");
        }
    }

    private static ChapterAdaptationTaskResponse response(VideoadaptationtaskRecord task) {
        return new ChapterAdaptationTaskResponse(
                task.getBaseshotplanversionid(),
                task.getCheckpointstage(),
                DatabaseTimestamp.api(task.getCreatedat()),
                task.getId(),
                task.getJobid(),
                ChapterAdaptationTaskResponse.KindEnum.fromValue(task.getKind()),
                task.getLasterrorcode(),
                task.getLasterrormessage(),
                task.getStatus(),
                DatabaseTimestamp.api(task.getUpdatedat()),
                task.getWorkflow());
    }

    private static void validatePromptBatch(ShotPromptSpecBatch batch) {
        if (batch == null
                || !"shot_prompt_spec_batch_v2".equals(batch.getSchemaVersion())
                || batch.getPrompts() == null
                || batch.getPrompts().isEmpty()
                || batch.getPrompts().size() > 120) {
            throw validation("逐镜提示词结果无效");
        }
        List<String> keys = batch.getPrompts().stream().map(value -> value.getShotKey()).toList();
        if (new HashSet<>(keys).size() != keys.size()) {
            throw validation("逐镜提示词候选不能包含重复镜头");
        }
    }

    private static String summary(ChapterAdaptationPlanCandidate candidate) {
        int scenes = candidate.getScenes().size();
        int beats = candidate.getScenes().stream()
                .mapToInt(scene -> scene.getBeats().size())
                .sum();
        List<cn.inkforge.contracts.api.CinematicShotCandidate> shots = candidate
                .getScenes().stream()
                .flatMap(scene -> scene.getBeats().stream())
                .flatMap(beat -> beat.getShots().stream())
                .toList();
        int durationMs = shots.stream()
                .mapToInt(value -> value.getTimelineDurationMs())
                .sum();
        String duration = durationMs % 1_000 == 0
                ? Integer.toString(durationMs / 1_000)
                : java.math.BigDecimal.valueOf(durationMs / 1_000.0)
                        .stripTrailingZeros()
                        .toPlainString();
        return scenes + " 个场景 · " + beats + " 个戏剧节拍 · " + shots.size()
                + " 个镜头 · 约 " + duration + " 秒";
    }

    private String canonicalJson(Object value) {
        return new String(
                CommandIdempotency.canonicalJsonBytes(value, json),
                java.nio.charset.StandardCharsets.UTF_8);
    }

    private boolean jsonEquivalent(String left, String right) {
        if (left == null || right == null) return Objects.equals(left, right);
        try {
            Object leftValue = json.readValue(left, new TypeReference<Object>() {});
            Object rightValue = json.readValue(right, new TypeReference<Object>() {});
            return java.util.Arrays.equals(
                    CommandIdempotency.canonicalJsonBytes(leftValue, json),
                    CommandIdempotency.canonicalJsonBytes(rightValue, json));
        } catch (RuntimeException exception) {
            return false;
        }
    }

    private static int backoff(int attempts) {
        return Math.min(300, 1 << Math.min(Math.max(attempts, 1), 8));
    }

    private static String requestId(String value) {
        String normalized = value == null ? "" : value.strip();
        int length = normalized.codePointCount(0, normalized.length());
        if (length < 16 || length > 128) throw validation("请求标识长度无效");
        return normalized;
    }

    private static String nullable(JsonNullable<String> value, boolean strip) {
        if (value == null || !value.isPresent() || value.get() == null) return null;
        String result = strip ? value.get().strip() : value.get();
        if (result.isEmpty()) throw validation("可选文本不能为空");
        return result;
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : List.copyOf(value);
    }

    private static ApiException revisionConflict(int currentRevision) {
        return new ApiException(
                409,
                "VIDEO_ADAPTATION_REVISION_CONFLICT",
                "章节影视化版本已经变化，请刷新后重试",
                Map.of("currentRevision", currentRevision));
    }

    private static ApiException idempotencyConflict(String message) {
        return new ApiException(
                409,
                "VIDEO_ADAPTATION_IDEMPOTENCY_CONFLICT",
                message);
    }

    private static ApiException callbackStateConflict() {
        return new ApiException(
                409,
                "VIDEO_ADAPTATION_CALLBACK_STATE_CONFLICT",
                "章节影视化任务当前状态不接受该回调");
    }

    private static ApiException terminalCallbackConflict() {
        return new ApiException(
                409,
                "VIDEO_ADAPTATION_TERMINAL_CALLBACK_CONFLICT",
                "章节影视化终态回调与已保存结果不一致");
    }

    private static ApiException validation(String message) {
        return new ApiException(422, "VALIDATION_ERROR", message);
    }

    private static CallbackIdentity identity(VideoAdaptationWorkflowProgressQuery value) {
        return new CallbackIdentity(
                value.getJobId(),
                value.getRunId(),
                value.getTaskId(),
                value.getNovelId(),
                value.getProjectId(),
                value.getAdaptationId(),
                value.getWorkflow().getValue());
    }

    private static CallbackIdentity identity(VideoAdaptationCheckpointCallback value) {
        return new CallbackIdentity(
                value.getJobId(),
                value.getRunId(),
                value.getTaskId(),
                value.getNovelId(),
                value.getProjectId(),
                value.getAdaptationId(),
                null);
    }

    private static CallbackIdentity identity(VideoAdaptationPlanCompletionCallback value) {
        return new CallbackIdentity(
                value.getJobId(),
                value.getRunId(),
                value.getTaskId(),
                value.getNovelId(),
                value.getProjectId(),
                value.getAdaptationId(),
                null);
    }

    private static CallbackIdentity identity(VideoAdaptationPromptCompletionCallback value) {
        return new CallbackIdentity(
                value.getJobId(),
                value.getRunId(),
                value.getTaskId(),
                value.getNovelId(),
                value.getProjectId(),
                value.getAdaptationId(),
                null);
    }

    private static CallbackIdentity identity(VideoAdaptationFailureCallback value) {
        return new CallbackIdentity(
                value.getJobId(),
                value.getRunId(),
                value.getTaskId(),
                value.getNovelId(),
                value.getProjectId(),
                value.getAdaptationId(),
                null);
    }

    private record CallbackIdentity(
            String jobId,
            String runId,
            String taskId,
            String novelId,
            String projectId,
            String adaptationId,
            String workflow) {}

    private record CallbackContext(
            VideoadaptationtaskRecord task,
            VideochapteradaptationRecord adaptation,
            VideoprojectRecord project) {}
}
