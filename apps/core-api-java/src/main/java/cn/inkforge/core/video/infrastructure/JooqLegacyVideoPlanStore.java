package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOGENERATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSCENE;

import cn.inkforge.contracts.api.AssetBinding;
import cn.inkforge.contracts.api.SceneAssetsStageArguments;
import cn.inkforge.contracts.api.StoryPlanStageArguments;
import cn.inkforge.contracts.api.VideoPlanAttemptState;
import cn.inkforge.contracts.api.VideoPlanCallReservationRequest;
import cn.inkforge.contracts.api.VideoPlanCallReservationResponse;
import cn.inkforge.contracts.api.VideoPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoPlanFailureCallback;
import cn.inkforge.contracts.api.VideoPlanProgressQuery;
import cn.inkforge.contracts.api.VideoPlanProgressResponse;
import cn.inkforge.contracts.api.VideoStoryPlanCheckpointCallback;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.VideogenerationtaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.db.generated.tables.records.VideosceneRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.LegacyVideoPlanProgress;
import cn.inkforge.core.video.application.LegacyVideoPlanStore;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 旧 VideoScene 任务的隔离收敛仓储。
 *
 * <p>这里只读取和推进已存在任务，刻意不提供任何创建、重试或返工公共准入。</p>
 */
public final class JooqLegacyVideoPlanStore implements LegacyVideoPlanStore {

    private static final Set<String> ACTIVE = Set.of("pending", "submitted", "processing");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final LegacyVideoPlanProgressCodec codec;

    public JooqLegacyVideoPlanStore(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.codec = new LegacyVideoPlanProgressCodec(json);
    }

    @Override
    public VideoPlanProgressResponse getProgress(VideoPlanProgressQuery query) {
        return database.transactionResult(transaction -> {
            CallbackResources resources = resources(transaction, query.getTaskId());
            requireBinding(
                    resources,
                    query.getTaskId(),
                    query.getJobId(),
                    query.getRunId(),
                    query.getNovelId(),
                    query.getProjectId(),
                    query.getSceneId());
            requirePlanTask(resources.task());
            requireCurrentTask(transaction, resources.task(), resources.scene());
            VideoDatabaseAccess.requireLongSerial(
                    transaction, resources.project().getNovelid(), true);
            LegacyVideoPlanProgressCodec.FrozenPayload payload = frozenPayload(resources.task());
            String status = progressStatus(resources.task().getStatus());
            LegacyVideoPlanProgress durable = null;
            VideoPlanAttemptState attempt;
            String checkpoint;
            if ("active".equals(status)) {
                LocalDateTime now = DatabaseTimestamp.now(clock);
                durable = activeProgress(resources.task().getResultjson());
                transaction.update(VIDEOGENERATIONTASK)
                        .set(VIDEOGENERATIONTASK.STATUS, "processing")
                        .set(VIDEOGENERATIONTASK.NEXTATTEMPTAT, now.plusMinutes(10))
                        .set(VIDEOGENERATIONTASK.UPDATEDAT, now)
                        .where(VIDEOGENERATIONTASK.ID.eq(resources.task().getId()))
                        .execute();
                attempt = durable.attemptState();
                checkpoint = durable.checkpointStage();
            } else {
                attempt = codec.terminalAttemptState(resources.task().getResultjson());
                checkpoint = "terminal";
            }
            VideoPlanProgressResponse response = new VideoPlanProgressResponse(
                    attempt,
                    VideoPlanProgressResponse.CheckpointStageEnum.fromValue(checkpoint),
                    payload.inputFingerprint(),
                    query.getJobId(),
                    query.getNovelId(),
                    query.getProjectId(),
                    "1.0",
                    query.getRunId(),
                    query.getSceneId(),
                    VideoPlanProgressResponse.StatusEnum.fromValue(status),
                    query.getTaskId());
            if (durable != null) {
                response.setSceneAssetsPlan(durable.sceneAssetsPlan());
                response.setStoryPlan(durable.storyPlan());
            }
            return response;
        });
    }

    @Override
    public VideoPlanCallReservationResponse reserveCall(
            VideoPlanCallReservationRequest request) {
        return database.transactionResult(transaction -> {
            CallbackResources resources = resources(transaction, request.getTaskId());
            requireBinding(
                    resources,
                    request.getTaskId(),
                    request.getJobId(),
                    request.getRunId(),
                    request.getNovelId(),
                    request.getProjectId(),
                    request.getSceneId());
            requirePlanTask(resources.task());
            requireCurrentTask(transaction, resources.task(), resources.scene());
            VideoDatabaseAccess.requireLongSerial(
                    transaction, resources.project().getNovelid(), true);
            requireActive(resources.task());
            LegacyVideoPlanProgress durable = activeProgress(resources.task().getResultjson());
            String checkpoint = request.getCheckpointStage().getValue();
            String stage = request.getStage().getValue();
            int expected = request.getExpectedReservedCalls();
            int inherited = request.getInheritedCalls() == null
                    ? 0
                    : request.getInheritedCalls();
            LegacyVideoPlanProgress.Reservation replay = durable.reservations().stream()
                    .filter(value -> value.eventId().equals(request.getEventId()))
                    .findFirst()
                    .orElse(null);
            // 预留必须先于模型调用耐久化；eventId 回放返回原计数，不能重复消耗五次调用预算。
            if (replay != null) {
                if (!checkpoint.equals(replay.checkpointStage())
                        || !stage.equals(replay.stage())
                        || expected != replay.reservedCallsBefore()
                        || inherited != LegacyVideoPlanProgressCodec.inheritedCalls(
                                durable.attemptState())) {
                    throw conflict(
                            "VIDEO_PLAN_RESERVATION_EVENT_CONFLICT",
                            "同一模型调用预留事件不能绑定不同请求");
                }
                return reservationResponse(request, replay);
            }
            if (!durable.checkpointStage().equals(checkpoint)) {
                throw conflict(
                        "VIDEO_PLAN_RESERVATION_STAGE_CONFLICT",
                        "视频规划检查点阶段已经变化，请重新读取进度");
            }
            if (durable.attemptState().getReservedCalls() != expected) {
                throw conflict(
                        "VIDEO_PLAN_RESERVATION_COUNT_CONFLICT",
                        "视频规划模型调用计数已经变化，请重新读取进度");
            }
            if (LegacyVideoPlanProgressCodec.inheritedCalls(durable.attemptState())
                    != inherited) {
                throw conflict(
                        "VIDEO_PLAN_RESERVATION_INHERITANCE_CONFLICT",
                        "视频规划继承调用基线已经变化，请重新读取进度");
            }
            if (expected + inherited >= 5) {
                throw conflict(
                        "VIDEO_PLAN_CALL_BUDGET_EXHAUSTED",
                        "视频规划模型调用预算已经耗尽");
            }
            LegacyVideoPlanProgress.Reservation reservation =
                    new LegacyVideoPlanProgress.Reservation(
                            request.getEventId(), checkpoint, stage, expected);
            VideoPlanCallReservationResponse response = reservationResponse(request, reservation);
            List<LegacyVideoPlanProgress.Reservation> reservations =
                    new ArrayList<>(durable.reservations());
            reservations.add(reservation);
            LegacyVideoPlanProgress updated = new LegacyVideoPlanProgress(
                    durable.checkpointStage(),
                    durable.sceneAssetsPlan(),
                    durable.storyPlan(),
                    response.getAttemptState(),
                    reservations,
                    durable.inheritedFromTaskId(),
                    durable.inheritedInputFingerprint());
            saveActiveProgress(transaction, resources.task().getId(), updated);
            return response;
        });
    }

    @Override
    public void saveCheckpoint(VideoStoryPlanCheckpointCallback callback) {
        database.transactionResult(transaction -> {
            CallbackResources resources = resources(transaction, callback.getTaskId());
            requireBinding(
                    resources,
                    callback.getTaskId(),
                    callback.getJobId(),
                    callback.getRunId(),
                    callback.getNovelId(),
                    callback.getProjectId(),
                    callback.getSceneId());
            requirePlanTask(resources.task());
            requireCurrentTask(transaction, resources.task(), resources.scene());
            VideoDatabaseAccess.requireLongSerial(
                    transaction, resources.project().getNovelid(), true);
            requireActive(resources.task());
            LegacyVideoPlanProgress current = activeProgress(resources.task().getResultjson());
            LegacyVideoPlanProgress target = new LegacyVideoPlanProgress(
                    callback.getCheckpointStage().getValue(),
                    callback.getSceneAssetsPlan(),
                    callback.getStoryPlan(),
                    callback.getAttemptState(),
                    current.reservations(),
                    current.inheritedFromTaskId(),
                    current.inheritedInputFingerprint());
            // 先严格编码一次，拒绝损坏或与预留账本不一致的回调。
            try {
                codec.encodeProgress(target);
            } catch (IllegalArgumentException exception) {
                throw conflict(
                        "VIDEO_PLAN_CHECKPOINT_ATTEMPT_CONFLICT",
                        "阶段检查点与已预留模型调用账本不一致");
            }
            if (target.checkpointStage().equals(current.checkpointStage())) {
                if (target.equals(current)) return null;
                throw conflict(
                        "VIDEO_PLAN_CHECKPOINT_CONFLICT",
                        "同一视频规划阶段不能覆盖不同的检查点内容");
            }
            validateCheckpointAdvance(current, target);
            saveActiveProgress(transaction, resources.task().getId(), target);
            return null;
        });
    }

    @Override
    public void complete(VideoPlanCompletionCallback callback) {
        database.transactionResult(transaction -> {
            CallbackResources resources = resources(transaction, callback.getTaskId());
            requireBinding(
                    resources,
                    callback.getTaskId(),
                    callback.getJobId(),
                    callback.getRunId(),
                    callback.getNovelId(),
                    callback.getProjectId(),
                    callback.getSceneId());
            if (!callback.getSceneId().equals(callback.getScenePlan().getSceneId())
                    || !callback.getSceneId().equals(callback.getPromptPackage().getSceneId())) {
                throw forbiddenBinding("视频回调内部场景标识不匹配");
            }
            requirePlanTask(resources.task());
            requireCurrentTask(transaction, resources.task(), resources.scene());
            Map<String, Object> result = completionResult(callback);
            if ("completed".equals(resources.task().getStatus())) {
                requireTerminalReplay(resources.task(), "completed", callback.getEventId(), result);
                return null;
            }
            if ("failed".equals(resources.task().getStatus())) throw terminalConflict();
            requireActive(resources.task());
            VideoDatabaseAccess.requireLongSerial(
                    transaction, resources.project().getNovelid(), true);
            LegacyVideoPlanProgressCodec.FrozenPayload payload =
                    completionFrozenPayload(resources.task());
            validateSettingReferences(payload, callback);
            if (!Boolean.TRUE.equals(callback.getPromptPackage().getPreviewOnly())
                    || Boolean.TRUE.equals(callback.getPromptPackage().getSubmissionReady())) {
                throw conflict(
                        "VIDEO_PREVIEW_PACKAGE_REQUIRED",
                        "结构冻结期只接受禁止供应商提交的开发预览包");
            }
            String payloadJson = json.writeValueAsString(result);
            String terminalJson = terminal(
                    resources.task().getResultjson(),
                    "completed",
                    callback.getEventId(),
                    result);
            // 旧链也只能生成待审 Artifact；Artifact 与任务终态同事务收敛，不直接写正式章节或新视频域。
            ReviewartifactRecord artifact = transaction.selectFrom(REVIEWARTIFACT)
                    .where(REVIEWARTIFACT.VIDEOSCENEID.eq(resources.scene().getId()))
                    .orderBy(REVIEWARTIFACT.REVISION.desc(), REVIEWARTIFACT.CREATEDAT.desc())
                    .limit(1)
                    .forUpdate()
                    .fetchOne();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            if (!payload.revision()) {
                if (artifact != null) {
                    throw conflict(
                            "VIDEO_ARTIFACT_ALREADY_EXISTS",
                            "视频场景已经存在候选方案");
                }
                transaction.insertInto(REVIEWARTIFACT)
                        .set(REVIEWARTIFACT.ID, ids.next())
                        .set(REVIEWARTIFACT.NOVELID, callback.getNovelId())
                        .set(REVIEWARTIFACT.CHAPTERID, resources.scene().getChapterid())
                        .set(REVIEWARTIFACT.ARTIFACTKEY,
                                "video-scene:" + resources.scene().getId())
                        .set(REVIEWARTIFACT.KIND, Reviewartifactkind.video_scene_plan)
                        .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.awaiting_user)
                        .set(REVIEWARTIFACT.TITLE,
                                "视频场景方案：" + resources.scene().getTitle())
                        .set(REVIEWARTIFACT.SUMMARY, callback.getScenePlan().getSummary())
                        .set(REVIEWARTIFACT.PAYLOADJSON, payloadJson)
                        .set(REVIEWARTIFACT.CREATEDBYAGENT, "剧情")
                        .set(REVIEWARTIFACT.UPDATEDBYAGENT, "剧情")
                        .set(REVIEWARTIFACT.REVISION, 1)
                        .set(REVIEWARTIFACT.CREATEDAT, now)
                        .set(REVIEWARTIFACT.UPDATEDAT, now)
                        .set(REVIEWARTIFACT.VIDEOSCENEID, resources.scene().getId())
                        .execute();
            } else {
                if (artifact == null || artifact.getStatus() != Reviewartifactstatus.draft) {
                    throw conflict(
                            "VIDEO_REVISE_ARTIFACT_NOT_DRAFT",
                            "返工任务没有可更新的草稿候选");
                }
                boolean historyExists = transaction.fetchExists(
                        transaction.selectOne()
                                .from(REVIEWARTIFACTREVISION)
                                .where(
                                        REVIEWARTIFACTREVISION.ARTIFACTID.eq(artifact.getId()),
                                        REVIEWARTIFACTREVISION.REVISION.eq(artifact.getRevision())));
                if (!historyExists) {
                    throw conflict(
                            "VIDEO_REVISE_HISTORY_MISSING",
                            "返工前候选缺少历史快照，不能覆盖");
                }
                transaction.update(REVIEWARTIFACT)
                        .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.awaiting_user)
                        .set(REVIEWARTIFACT.TITLE,
                                "视频场景方案：" + resources.scene().getTitle())
                        .set(REVIEWARTIFACT.SUMMARY, callback.getScenePlan().getSummary())
                        .set(REVIEWARTIFACT.PAYLOADJSON, payloadJson)
                        .set(REVIEWARTIFACT.DIFFJSON, (String) null)
                        .set(REVIEWARTIFACT.UPDATEDBYAGENT, "剧情")
                        .set(REVIEWARTIFACT.REVISION, artifact.getRevision() + 1)
                        .set(REVIEWARTIFACT.UPDATEDAT, now)
                        .where(REVIEWARTIFACT.ID.eq(artifact.getId()))
                        .execute();
            }
            transaction.update(VIDEOGENERATIONTASK)
                    .set(VIDEOGENERATIONTASK.STATUS, "completed")
                    .set(VIDEOGENERATIONTASK.RESULTJSON, terminalJson)
                    .set(VIDEOGENERATIONTASK.COMPLETEDAT, now)
                    .set(VIDEOGENERATIONTASK.UPDATEDAT, now)
                    .where(VIDEOGENERATIONTASK.ID.eq(resources.task().getId()))
                    .execute();
            transaction.update(VIDEOSCENE)
                    .set(VIDEOSCENE.STATUS, "awaiting_review")
                    .set(VIDEOSCENE.LASTERRORCODE, (String) null)
                    .set(VIDEOSCENE.LASTERRORMESSAGE, (String) null)
                    .set(VIDEOSCENE.UPDATEDAT, now)
                    .where(VIDEOSCENE.ID.eq(resources.scene().getId()))
                    .execute();
            return null;
        });
    }

    @Override
    public void fail(VideoPlanFailureCallback callback) {
        database.transactionResult(transaction -> {
            CallbackResources resources = resources(transaction, callback.getTaskId());
            requireBinding(
                    resources,
                    callback.getTaskId(),
                    callback.getJobId(),
                    callback.getRunId(),
                    callback.getNovelId(),
                    callback.getProjectId(),
                    callback.getSceneId());
            requirePlanTask(resources.task());
            requireCurrentTask(transaction, resources.task(), resources.scene());
            LinkedHashMap<String, Object> result = new LinkedHashMap<>();
            result.put("code", callback.getCode());
            result.put("message", callback.getMessage());
            result.put("recoverable", callback.getRecoverable());
            if ("failed".equals(resources.task().getStatus())) {
                requireTerminalReplay(resources.task(), "failed", callback.getEventId(), result);
                return null;
            }
            if ("completed".equals(resources.task().getStatus())) throw terminalConflict();
            requireActive(resources.task());
            VideoDatabaseAccess.requireLongSerial(
                    transaction, resources.project().getNovelid(), true);
            if (refundable(callback)) {
                // 仅结构校验类可恢复失败退款；供应商或任意业务失败不能借此路径泛化退款语义。
                refund(transaction, resources.task(), resources.project().getNovelid());
            }
            String terminalJson = terminal(
                    resources.task().getResultjson(),
                    "failed",
                    callback.getEventId(),
                    result);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.update(VIDEOGENERATIONTASK)
                    .set(VIDEOGENERATIONTASK.STATUS, "failed")
                    .set(VIDEOGENERATIONTASK.RESULTJSON, terminalJson)
                    .set(VIDEOGENERATIONTASK.LASTERRORCODE, callback.getCode())
                    .set(VIDEOGENERATIONTASK.LASTERRORMESSAGE, callback.getMessage())
                    .set(VIDEOGENERATIONTASK.COMPLETEDAT, now)
                    .set(VIDEOGENERATIONTASK.UPDATEDAT, now)
                    .where(VIDEOGENERATIONTASK.ID.eq(resources.task().getId()))
                    .execute();
            transaction.update(VIDEOSCENE)
                    .set(VIDEOSCENE.STATUS, "failed")
                    .set(VIDEOSCENE.LASTERRORCODE, callback.getCode())
                    .set(VIDEOSCENE.LASTERRORMESSAGE, callback.getMessage())
                    .set(VIDEOSCENE.UPDATEDAT, now)
                    .where(VIDEOSCENE.ID.eq(resources.scene().getId()))
                    .execute();
            return null;
        });
    }

    private CallbackResources resources(DSLContext transaction, String taskId) {
        VideogenerationtaskRecord task = lockTask(transaction, taskId);
        if (task == null) throw notFound("VIDEO_TASK_NOT_FOUND", "视频任务不存在");
        VideosceneRecord scene = lockScene(transaction, task.getSceneid());
        if (scene == null) throw notFound("VIDEO_SCENE_NOT_FOUND", "视频场景不存在");
        VideoprojectRecord project = transaction.selectFrom(VIDEOPROJECT)
                .where(VIDEOPROJECT.ID.eq(task.getProjectid()))
                .forUpdate()
                .fetchOne();
        if (project == null) throw notFound("VIDEO_PROJECT_NOT_FOUND", "视频项目不存在");
        return new CallbackResources(task, scene, project);
    }

    private static void requireBinding(
            CallbackResources resources,
            String taskId,
            String jobId,
            String runId,
            String novelId,
            String projectId,
            String sceneId) {
        if (!resources.task().getId().equals(taskId)
                || !resources.task().getJobid().equals(jobId)
                || !resources.task().getId().equals(runId)
                || !resources.task().getProjectid().equals(projectId)
                || !resources.task().getSceneid().equals(sceneId)
                || !resources.scene().getProjectid().equals(projectId)
                || !resources.project().getId().equals(projectId)
                || !resources.project().getNovelid().equals(novelId)) {
            throw forbiddenBinding("视频回调资源绑定不匹配");
        }
    }

    private static void requirePlanTask(VideogenerationtaskRecord task) {
        if (!"plan".equals(task.getKind()) || !"deepseek".equals(task.getProvider())) {
            throw conflict(
                    "VIDEO_PLAN_TASK_REQUIRED",
                    "当前任务不是 DeepSeek 视频场景规划任务");
        }
    }

    private static void requireActive(VideogenerationtaskRecord task) {
        if (!ACTIVE.contains(task.getStatus())) {
            throw conflict(
                    "VIDEO_PLAN_TASK_NOT_ACTIVE",
                    "只有活动中的视频规划任务可以继续执行");
        }
    }

    private static void requireCurrentTask(
            DSLContext transaction,
            VideogenerationtaskRecord task,
            VideosceneRecord scene) {
        String latest = transaction.select(VIDEOGENERATIONTASK.ID)
                .from(VIDEOGENERATIONTASK)
                .where(VIDEOGENERATIONTASK.SCENEID.eq(scene.getId()))
                .orderBy(VIDEOGENERATIONTASK.CREATEDAT.desc(), VIDEOGENERATIONTASK.ID.desc())
                .limit(1)
                .fetchOne(VIDEOGENERATIONTASK.ID);
        if (!task.getId().equals(latest)) {
            throw conflict(
                    "VIDEO_CALLBACK_STALE_ATTEMPT",
                    "旧视频规划尝试的回调已失效");
        }
    }

    private LegacyVideoPlanProgress activeProgress(String resultJson) {
        try {
            return codec.decodeActiveProgress(resultJson);
        } catch (IllegalArgumentException exception) {
            throw conflict(
                    "VIDEO_PLAN_PROGRESS_CHECKPOINT_INVALID",
                    "视频规划进度或调用账本已损坏，不能安全恢复");
        }
    }

    private LegacyVideoPlanProgressCodec.FrozenPayload frozenPayload(
            VideogenerationtaskRecord task) {
        try {
            return codec.parseFrozenPayload(task.getRequestjson());
        } catch (IllegalArgumentException exception) {
            throw conflict(
                    "VIDEO_PLAN_INPUT_INVALID",
                    "视频规划任务的冻结输入已损坏，不能安全恢复");
        }
    }

    private LegacyVideoPlanProgressCodec.FrozenPayload completionFrozenPayload(
            VideogenerationtaskRecord task) {
        try {
            return codec.parseFrozenPayload(task.getRequestjson());
        } catch (IllegalArgumentException exception) {
            // Python 旧 Core 把完成回调中的冻结输入损坏归入设定引用冲突。
            throw conflict(
                    "VIDEO_PLAN_SETTING_REFERENCE_INVALID",
                    "视频方案引用了任务冻结快照之外的设定");
        }
    }

    private void saveActiveProgress(
            DSLContext transaction, String taskId, LegacyVideoPlanProgress progress) {
        String result;
        try {
            result = codec.encodeProgress(progress);
        } catch (IllegalArgumentException exception) {
            throw conflict(
                    "VIDEO_PLAN_PROGRESS_CHECKPOINT_INVALID",
                    "视频规划进度或调用账本已损坏，不能安全恢复");
        }
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.update(VIDEOGENERATIONTASK)
                .set(VIDEOGENERATIONTASK.STATUS, "processing")
                .set(VIDEOGENERATIONTASK.RESULTJSON, result)
                .set(VIDEOGENERATIONTASK.NEXTATTEMPTAT, now.plusMinutes(10))
                .set(VIDEOGENERATIONTASK.UPDATEDAT, now)
                .where(VIDEOGENERATIONTASK.ID.eq(taskId))
                .execute();
    }

    private static void validateCheckpointAdvance(
            LegacyVideoPlanProgress current, LegacyVideoPlanProgress target) {
        int currentRank = rank(current.checkpointStage());
        int targetRank = rank(target.checkpointStage());
        if (targetRank != currentRank + 1) {
            throw conflict(
                    "VIDEO_PLAN_CHECKPOINT_TRANSITION_INVALID",
                    "视频规划检查点只能按阶段单向推进一次");
        }
        String expectedPending = switch (current.checkpointStage()) {
            case "empty" -> "scene_assets";
            case "scene_assets" -> "story_beats";
            case "story" -> null;
            default -> throw new IllegalStateException("未知视频规划阶段");
        };
        if (!Objects.equals(
                LegacyVideoPlanProgressCodec.pendingStage(current.attemptState()),
                expectedPending)) {
            throw conflict(
                    "VIDEO_PLAN_CHECKPOINT_PENDING_MISMATCH",
                    "阶段检查点与当前待确认模型调用不一致");
        }
        if (LegacyVideoPlanProgressCodec.pendingStage(target.attemptState()) != null) {
            throw conflict(
                    "VIDEO_PLAN_CHECKPOINT_PENDING_MISMATCH",
                    "完成阶段后必须清除当前待确认模型调用");
        }
        if (current.attemptState().getReservedCalls()
                        != target.attemptState().getReservedCalls()
                || LegacyVideoPlanProgressCodec.inheritedCalls(current.attemptState())
                        != LegacyVideoPlanProgressCodec.inheritedCalls(target.attemptState())
                || !current.reservations().equals(target.reservations())) {
            throw conflict(
                    "VIDEO_PLAN_CHECKPOINT_ATTEMPT_CONFLICT",
                    "阶段检查点不能改写已预留模型调用账本");
        }
        if ("story".equals(target.checkpointStage())) {
            SceneAssetsStageArguments assets = current.sceneAssetsPlan();
            StoryPlanStageArguments story = target.storyPlan();
            if (assets == null
                    || story == null
                    || !LegacyVideoPlanProgressCodec.frozenSceneAssetsEqual(assets, story)) {
                throw conflict(
                        "VIDEO_PLAN_STORY_CHANGED_SCENE_ASSETS",
                        "故事阶段改写了已冻结的场景或素材事实");
            }
        }
    }

    private static int rank(String stage) {
        return switch (stage) {
            case "empty" -> 0;
            case "scene_assets" -> 1;
            case "story" -> 2;
            default -> -100;
        };
    }

    private static VideoPlanCallReservationResponse reservationResponse(
            VideoPlanCallReservationRequest request,
            LegacyVideoPlanProgress.Reservation reservation) {
        VideoPlanAttemptState attempt = new VideoPlanAttemptState(
                VideoPlanAttemptState.PendingStageEnum.fromValue(reservation.stage()),
                reservation.reservedCallsBefore() + 1);
        attempt.setInheritedCalls(
                request.getInheritedCalls() == null ? 0 : request.getInheritedCalls());
        return new VideoPlanCallReservationResponse(
                attempt,
                VideoPlanCallReservationResponse.CheckpointStageEnum.fromValue(
                        reservation.checkpointStage()),
                reservation.eventId(),
                request.getJobId(),
                request.getNovelId(),
                request.getProjectId(),
                "1.0",
                reservation.reservedCallsBefore(),
                request.getRunId(),
                request.getSceneId(),
                VideoPlanCallReservationResponse.StageEnum.fromValue(reservation.stage()),
                request.getTaskId());
    }

    private Map<String, Object> completionResult(VideoPlanCompletionCallback callback) {
        LinkedHashMap<String, Object> target = new LinkedHashMap<>();
        target.put("type", "video_scene_plan");
        target.put("sceneId", callback.getSceneId());
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        result.put("applyTarget", target);
        result.put("scenePlan", codec.modelMap(callback.getScenePlan()));
        result.put("promptPackage", codec.modelMap(callback.getPromptPackage()));
        return result;
    }

    private void validateSettingReferences(
            LegacyVideoPlanProgressCodec.FrozenPayload payload,
            VideoPlanCompletionCallback callback) {
        try {
            for (AssetBinding asset : callback.getScenePlan().getAssets()) {
                if (asset.getBindingScope() != AssetBinding.BindingScopeEnum.CANON_SLOT) continue;
                if (asset.getSettingReference() == null
                        || !payload.settingKeys().contains(
                                asset.getSettingReference().getKind().getValue()
                                        + "\0"
                                        + asset.getSettingReference().getId())) {
                    throw new IllegalArgumentException("设定引用不存在");
                }
            }
        } catch (RuntimeException exception) {
            throw conflict(
                    "VIDEO_PLAN_SETTING_REFERENCE_INVALID",
                    "视频方案引用了任务冻结快照之外的设定");
        }
    }

    private void requireTerminalReplay(
            VideogenerationtaskRecord task,
            String status,
            String eventId,
            Map<String, Object> result) {
        LegacyVideoPlanProgressCodec.TerminalResult terminal;
        try {
            terminal = codec.decodeTerminal(task.getResultjson());
        } catch (IllegalArgumentException exception) {
            throw conflict(
                    "VIDEO_PLAN_TERMINAL_RESULT_INVALID",
                    "视频规划终态结果已损坏，不能核验重复回调");
        }
        if (terminal != null) {
            if (terminal.status().equals(status)
                    && terminal.eventId().equals(eventId)
                    && codec.jsonEquivalent(terminal.result(), result)) {
                return;
            }
            throw terminalConflict();
        }
        if ("completed".equals(status)) {
            try {
                Map<String, Object> legacy = json.readValue(
                        task.getResultjson(),
                        new TypeReference<LinkedHashMap<String, Object>>() {});
                if (codec.jsonEquivalent(legacy, result)) return;
            } catch (RuntimeException exception) {
                throw conflict(
                        "VIDEO_PLAN_TERMINAL_RESULT_INVALID",
                        "历史视频规划终态结果已损坏，不能核验重复回调");
            }
        }
        throw terminalConflict();
    }

    private String terminal(
            String progressJson,
            String status,
            String eventId,
            Map<String, Object> result) {
        try {
            return codec.encodeTerminal(progressJson, status, eventId, result);
        } catch (IllegalArgumentException exception) {
            throw conflict(
                    "VIDEO_PLAN_TERMINAL_RESULT_INVALID",
                    "视频规划进度或终态结果已损坏，不能安全收敛任务");
        }
    }

    private static boolean refundable(VideoPlanFailureCallback callback) {
        return "VIDEO_PLAN_FAILED".equals(callback.getCode())
                && Boolean.TRUE.equals(callback.getRecoverable())
                && callback.getMessage().startsWith("VIDEO_SCENE_PLAN_INVALID");
    }

    private void refund(
            DSLContext transaction,
            VideogenerationtaskRecord task,
            String novelId) {
        String userId = transaction.select(NOVEL.USERID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .fetchOne(NOVEL.USERID);
        if (userId == null) {
            throw conflict(
                    "VIDEO_PLAN_REFUND_OWNER_MISSING",
                    "视频规划失败补偿缺少小说归属，不能安全结算");
        }
        String prefix = "video-task-"
                + CommandIdempotency.sha256(task.getId().getBytes(StandardCharsets.UTF_8))
                        .substring(0, 32)
                + "-";
        String refundId = prefix + "refund";
        // 退款请求标识由任务确定，先锁账本查重，回调重放不会重复增加余额。
        boolean existing = transaction.fetchExists(transaction.selectOne()
                .from(CREDITLEDGER)
                .where(
                        CREDITLEDGER.USERID.eq(userId),
                        CREDITLEDGER.TYPE.eq("video_plan_refund"),
                        CREDITLEDGER.REQUESTID.eq(refundId))
                .forUpdate());
        if (existing) return;
        List<Long> charges = transaction.select(CREDITLEDGER.AMOUNTMICROS)
                .from(CREDITLEDGER)
                .where(
                        CREDITLEDGER.USERID.eq(userId),
                        CREDITLEDGER.NOVELID.eq(novelId),
                        CREDITLEDGER.TYPE.eq("ai_charge"),
                        CREDITLEDGER.REQUESTID.like(prefix + "%"))
                .forUpdate()
                .fetch(CREDITLEDGER.AMOUNTMICROS);
        long refund = 0;
        for (long charge : charges) {
            if (charge < 0) refund = Math.addExact(refund, Math.negateExact(charge));
        }
        if (refund == 0) return;
        Long balance = transaction.update(USER)
                .set(USER.CREDITBALANCEMICROS, USER.CREDITBALANCEMICROS.add(refund))
                .where(USER.ID.eq(userId))
                .returningResult(USER.CREDITBALANCEMICROS)
                .fetchOne(USER.CREDITBALANCEMICROS);
        if (balance == null) {
            throw conflict(
                    "VIDEO_PLAN_REFUND_USER_MISSING",
                    "视频规划失败补偿缺少用户账户，不能安全结算");
        }
        transaction.insertInto(CREDITLEDGER)
                .set(CREDITLEDGER.ID, ids.next())
                .set(CREDITLEDGER.USERID, userId)
                .set(CREDITLEDGER.TYPE, "video_plan_refund")
                .set(CREDITLEDGER.AMOUNTMICROS, refund)
                .set(CREDITLEDGER.BALANCEAFTERMICROS, balance)
                .set(CREDITLEDGER.MODEL, "deepseek-v4-flash")
                .set(CREDITLEDGER.PROMPTTOKENS, 0)
                .set(CREDITLEDGER.CACHEDTOKENS, 0)
                .set(CREDITLEDGER.COMPLETIONTOKENS, 0)
                .set(CREDITLEDGER.TOTALTOKENS, 0)
                .set(CREDITLEDGER.AGENTID, "剧情")
                .set(CREDITLEDGER.NOVELID, novelId)
                .set(CREDITLEDGER.REQUESTID, refundId)
                .set(CREDITLEDGER.NOTE, "视频规划结构失败积分退回")
                .set(CREDITLEDGER.CREATEDAT, DatabaseTimestamp.now(clock))
                .execute();
    }

    private static String progressStatus(String status) {
        if (ACTIVE.contains(status)) return "active";
        if ("completed".equals(status)) return "completed";
        if ("failed".equals(status)) return "failed";
        throw conflict(
                "VIDEO_PLAN_PROGRESS_STATUS_INVALID",
                "当前视频规划任务状态不能恢复或继续执行");
    }

    private static VideogenerationtaskRecord lockTask(DSLContext transaction, String taskId) {
        return transaction.selectFrom(VIDEOGENERATIONTASK)
                .where(VIDEOGENERATIONTASK.ID.eq(taskId))
                .forUpdate()
                .fetchOne();
    }

    private static VideosceneRecord lockScene(DSLContext transaction, String sceneId) {
        return transaction.selectFrom(VIDEOSCENE)
                .where(VIDEOSCENE.ID.eq(sceneId))
                .forUpdate()
                .fetchOne();
    }

    private static ApiException notFound(String code, String message) {
        return new ApiException(404, code, message);
    }

    private static ApiException forbiddenBinding(String message) {
        return new ApiException(403, "VIDEO_CALLBACK_RESOURCE_MISMATCH", message);
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(409, code, message);
    }

    private static ApiException terminalConflict() {
        return conflict(
                "VIDEO_PLAN_TERMINAL_CALLBACK_CONFLICT",
                "视频规划终态回调与首次保存的结果不一致");
    }

    private record CallbackResources(
            VideogenerationtaskRecord task,
            VideosceneRecord scene,
            VideoprojectRecord project) {}
}
