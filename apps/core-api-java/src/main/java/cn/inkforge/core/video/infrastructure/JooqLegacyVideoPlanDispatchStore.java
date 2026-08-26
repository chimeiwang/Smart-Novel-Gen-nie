package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOGENERATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSCENE;

import cn.inkforge.core.db.generated.tables.records.VideogenerationtaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.db.generated.tables.records.VideosceneRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.LegacyVideoPlanDispatchStore;
import cn.inkforge.core.video.application.VideoAdaptationAgentStatus;
import cn.inkforge.core.video.application.VideoAdaptationTaskDispatch;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.databind.ObjectMapper;

/**
 * 旧 VideoScene 任务的隔离补投仓储。
 *
 * <p>这里只领取和收敛已存在任务，不处理 Agent 回调，也不提供任务创建入口。</p>
 */
public final class JooqLegacyVideoPlanDispatchStore
        implements LegacyVideoPlanDispatchStore {

    private static final Set<String> ACTIVE = Set.of("pending", "submitted", "processing");
    private static final Set<String> TERMINAL = Set.of("completed", "failed", "cancelled");

    private final CoreDatabase database;
    private final Clock clock;
    private final LegacyVideoPlanProgressCodec codec;
    private final String jobPrefix;

    public JooqLegacyVideoPlanDispatchStore(
            CoreDatabase database,
            Clock clock,
            ObjectMapper json,
            String dispatchNamespace) {
        this.database = Objects.requireNonNull(database);
        this.clock = Objects.requireNonNull(clock);
        this.codec = new LegacyVideoPlanProgressCodec(Objects.requireNonNull(json));
        String namespace = dispatchNamespace == null ? "default" : dispatchNamespace;
        if (!namespace.matches("[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?")) {
            throw new IllegalArgumentException("历史视频调度命名空间无效");
        }
        this.jobPrefix = "video-plan-" + namespace + "-";
    }

    @Override
    public List<VideoAdaptationTaskDispatch> claimDue(int limit) {
        if (limit < 1) throw new IllegalArgumentException("历史视频任务领取数量必须为正整数");
        LocalDateTime now = DatabaseTimestamp.now(clock);
        LocalDateTime leaseUntil = now.plusSeconds(30);
        return database.transactionResult(transaction -> {
            List<Record> rows = transaction.select(VIDEOGENERATIONTASK.fields())
                    .select(VIDEOPROJECT.fields())
                    .select(NOVEL.USERID)
                    .from(VIDEOGENERATIONTASK)
                    .join(VIDEOPROJECT)
                    .on(VIDEOPROJECT.ID.eq(VIDEOGENERATIONTASK.PROJECTID))
                    .join(NOVEL)
                    .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                    .where(
                            VIDEOGENERATIONTASK.KIND.eq("plan"),
                            VIDEOGENERATIONTASK.PROVIDER.eq("deepseek"),
                            VIDEOGENERATIONTASK.JOBID.like(jobPrefix + "%"),
                            VIDEOGENERATIONTASK.STATUS.in(ACTIVE),
                            VIDEOGENERATIONTASK.NEXTATTEMPTAT.le(now),
                            VIDEOPROJECT.DELETEDAT.isNull())
                    .orderBy(
                            VIDEOGENERATIONTASK.NEXTATTEMPTAT,
                            VIDEOGENERATIONTASK.CREATEDAT,
                            VIDEOGENERATIONTASK.ID)
                    .limit(limit)
                    .forUpdate()
                    .of(VIDEOGENERATIONTASK)
                    .skipLocked()
                    .fetch();
            List<VideoAdaptationTaskDispatch> result = new ArrayList<>();
            for (Record row : rows) {
                VideogenerationtaskRecord task = row.into(VIDEOGENERATIONTASK);
                VideoprojectRecord project = row.into(VIDEOPROJECT);
                VideosceneRecord scene = transaction.selectFrom(VIDEOSCENE)
                        .where(VIDEOSCENE.ID.eq(task.getSceneid()))
                        .forUpdate()
                        .fetchOne();
                try {
                    if (scene == null) throw new IllegalArgumentException("视频场景不存在");
                    LegacyVideoPlanProgressCodec.FrozenPayload payload =
                            codec.parseFrozenPayload(task.getRequestjson());
                    requireDispatchPayload(task, scene, project, payload);
                    transaction.update(VIDEOGENERATIONTASK)
                            .set(VIDEOGENERATIONTASK.NEXTATTEMPTAT, leaseUntil)
                            .set(VIDEOGENERATIONTASK.UPDATEDAT, now)
                            .where(VIDEOGENERATIONTASK.ID.eq(task.getId()))
                            .execute();
                    result.add(new VideoAdaptationTaskDispatch(
                            row.get(NOVEL.USERID),
                            project.getNovelid(),
                            task.getId(),
                            task.getJobid(),
                            payload.agentPayload()));
                } catch (RuntimeException exception) {
                    failDispatch(
                            transaction,
                            task,
                            scene,
                            "failed",
                            "VIDEO_DISPATCH_INPUT_INVALID",
                            exception.getMessage());
                }
            }
            return List.copyOf(result);
        });
    }

    @Override
    public void markSubmitted(String taskId) {
        database.transactionResult(transaction -> {
            VideogenerationtaskRecord task = lockTask(transaction, taskId);
            if (task != null && ACTIVE.contains(task.getStatus())) {
                LocalDateTime now = DatabaseTimestamp.now(clock);
                transaction.update(VIDEOGENERATIONTASK)
                        .set(
                                VIDEOGENERATIONTASK.STATUS,
                                "pending".equals(task.getStatus())
                                        ? "submitted"
                                        : task.getStatus())
                        .set(
                                VIDEOGENERATIONTASK.SUBMITTEDAT,
                                task.getSubmittedat() == null ? now : task.getSubmittedat())
                        .set(VIDEOGENERATIONTASK.NEXTATTEMPTAT, now.plusMinutes(10))
                        .set(VIDEOGENERATIONTASK.LASTERRORCODE, (String) null)
                        .set(VIDEOGENERATIONTASK.LASTERRORMESSAGE, (String) null)
                        .set(VIDEOGENERATIONTASK.UPDATEDAT, now)
                        .where(VIDEOGENERATIONTASK.ID.eq(taskId))
                        .execute();
            }
            return null;
        });
    }

    @Override
    public void recordDispatchFailure(
            String taskId, String errorCode, boolean transientFailure) {
        database.transactionResult(transaction -> {
            VideogenerationtaskRecord task = lockTask(transaction, taskId);
            if (task == null || TERMINAL.contains(task.getStatus())) return null;
            VideosceneRecord scene = lockScene(transaction, task.getSceneid());
            if (transientFailure) {
                int attempts = task.getAttemptcount() + 1;
                LocalDateTime now = DatabaseTimestamp.now(clock);
                transaction.update(VIDEOGENERATIONTASK)
                        .set(VIDEOGENERATIONTASK.ATTEMPTCOUNT, attempts)
                        .set(VIDEOGENERATIONTASK.STATUS, "pending")
                        .set(VIDEOGENERATIONTASK.NEXTATTEMPTAT, now.plusSeconds(backoff(attempts)))
                        .set(VIDEOGENERATIONTASK.LASTERRORCODE, "VIDEO_AGENT_SUBMIT_RETRY")
                        .set(VIDEOGENERATIONTASK.LASTERRORMESSAGE,
                                "视频任务投递暂时失败：" + errorCode)
                        .set(VIDEOGENERATIONTASK.COMPLETEDAT, (LocalDateTime) null)
                        .set(VIDEOGENERATIONTASK.UPDATEDAT, now)
                        .where(VIDEOGENERATIONTASK.ID.eq(taskId))
                        .execute();
            } else {
                failDispatch(
                        transaction,
                        task,
                        scene,
                        "failed",
                        "VIDEO_AGENT_SUBMIT_FAILED",
                        "视频任务投递失败：" + errorCode);
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
            VideogenerationtaskRecord task = lockTask(transaction, taskId);
            if (task == null || TERMINAL.contains(task.getStatus())) return null;
            failDispatch(
                    transaction,
                    task,
                    lockScene(transaction, task.getSceneid()),
                    status == VideoAdaptationAgentStatus.CANCELLED ? "cancelled" : "failed",
                    "VIDEO_AGENT_TERMINAL_WITHOUT_CALLBACK",
                    "Agent 队列已进入 " + status.name().toLowerCase()
                            + "，但 Core 尚未收到视频终态回调");
            return null;
        });
    }

    private static void requireDispatchPayload(
            VideogenerationtaskRecord task,
            VideosceneRecord scene,
            VideoprojectRecord project,
            LegacyVideoPlanProgressCodec.FrozenPayload payload) {
        String sourceHash = CommandIdempotency.sha256(
                payload.sourceText().getBytes(StandardCharsets.UTF_8));
        if (!task.getProjectid().equals(project.getId())
                || !task.getSceneid().equals(scene.getId())
                || !payload.projectId().equals(project.getId())
                || !payload.sceneId().equals(scene.getId())
                || !Objects.equals(payload.chapterId(), scene.getChapterid())
                || !payload.title().equals(scene.getTitle())
                || !payload.sourceText().equals(scene.getSourcetext())
                || !sourceHash.equals(scene.getSourcehash())
                || payload.durationSeconds() != scene.getDurationseconds()) {
            throw new IllegalArgumentException("原任务与当前场景冻结输入不一致");
        }
    }

    private void failDispatch(
            DSLContext transaction,
            VideogenerationtaskRecord task,
            VideosceneRecord scene,
            String status,
            String code,
            String message) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.update(VIDEOGENERATIONTASK)
                .set(VIDEOGENERATIONTASK.STATUS, status)
                .set(VIDEOGENERATIONTASK.LASTERRORCODE, code)
                .set(VIDEOGENERATIONTASK.LASTERRORMESSAGE, message)
                .set(VIDEOGENERATIONTASK.COMPLETEDAT, now)
                .set(VIDEOGENERATIONTASK.UPDATEDAT, now)
                .where(VIDEOGENERATIONTASK.ID.eq(task.getId()))
                .execute();
        if (scene != null) {
            transaction.update(VIDEOSCENE)
                    .set(VIDEOSCENE.STATUS, "failed")
                    .set(VIDEOSCENE.LASTERRORCODE, code)
                    .set(VIDEOSCENE.LASTERRORMESSAGE, message)
                    .set(VIDEOSCENE.UPDATEDAT, now)
                    .where(VIDEOSCENE.ID.eq(scene.getId()))
                    .execute();
        }
    }

    private static int backoff(int attempts) {
        return Math.min(300, 1 << Math.min(Math.max(attempts, 1), 8));
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
}
