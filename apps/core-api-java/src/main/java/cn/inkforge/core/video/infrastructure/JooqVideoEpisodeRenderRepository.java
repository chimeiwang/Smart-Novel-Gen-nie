package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.ArchivedVideoFrame;
import cn.inkforge.core.video.application.CompletedEpisodeVideoTake;
import cn.inkforge.core.video.application.VideoAssetFile;
import cn.inkforge.core.video.application.VideoEpisodeRenderClaim;
import cn.inkforge.core.video.application.VideoEpisodeRenderInput;
import cn.inkforge.core.video.application.VideoEpisodeRenderKeyframe;
import cn.inkforge.core.video.application.VideoEpisodeRenderReference;
import cn.inkforge.core.video.application.VideoEpisodeRenderRepository;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 独立剧集制作基线到耐久逐镜任务的 jOOQ 实现。
 *
 * <p>新任务只复制 {@code VideoProductionBaselineShot.inputSnapshotJson}，不读取 Prompt Head、分镜 Head 或旧
 * adaptation 身份。提交未知会一直封锁同一基线镜头的新任务，直到另有具名对账流程收敛。
 */
public final class JooqVideoEpisodeRenderRepository implements VideoEpisodeRenderRepository {

    private static final Set<String> QUERY = Set.of("queued", "running", "archiving");
    private static final Set<String> RETRYABLE = Set.of("failed", "expired", "cancelled");
    private static final Set<String> TERMINAL =
            Set.of("submission_unknown", "succeeded", "failed", "expired", "cancelled");
    private static final Set<String> DUTIES = Set.of("identity", "costume", "scene", "prop");
    private static final Set<String> KEYFRAME_DUTIES =
            Set.of("identity", "costume", "scene", "prop", "storyboard", "keyframe");
    private static final Set<String> KEYFRAME_ROLES =
            Set.of("initial_state", "transition_anchor", "end_state");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    public JooqVideoEpisodeRenderRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public ObjectNode createTask(
            String userId,
            String episodeId,
            String baselineId,
            String shotId,
            JsonNode request,
            String executionMode,
            boolean referenceTransportConfigured) {
        String clientRequestId = clientRequestId(request);
        boolean feeConfirmed = booleanField(request, "feeConfirmed", false);
        return database.transactionResult(tx -> {
            renderLock(tx, episodeId, shotId);
            // 先校验不可变制作基线的归属，再处理幂等回放，避免凭猜测任务身份读取他人回执。
            Record baselineShot = requireBaselineShot(
                    tx, userId, episodeId, baselineId, shotId, true);
            Record existing = taskByRequest(tx, shotId, clientRequestId);
            if (existing != null) {
                requireReplay(tx, existing, episodeId, baselineId, shotId, feeConfirmed);
                return taskResponse(tx, existing);
            }
            ObjectNode snapshot = readObject(baselineShot, "inputSnapshotJson", "制作基线镜头输入");
            String inputHash = baselineShot.get("inputHash", String.class);
            requireHash(snapshot, inputHash);
            VideoEpisodeRenderInput input = parseInput(
                    tx,
                    snapshot,
                    shotId,
                    baselineShot.get("shotVersionId", String.class),
                    baselineShot.get("projectId", String.class),
                    episodeId,
                    baselineId,
                    true);
            requireRuntime(input, executionMode, feeConfirmed, referenceTransportConfigured);
            requireNoBlockingTask(tx, episodeId, shotId, null);
            String taskId = ids.next();
            LocalDateTime now = now();
            tx.execute(
                    """
                    INSERT INTO public."VideoShotRenderTask" (
                      id,"adaptationId","projectId","novelId","shotId","shotPlanVersionId",
                      "promptVersionId","retryOfTaskId",provider,model,status,"clientRequestId",
                      "inputHash","requestManifestJson","pollCount","attemptCount","nextAttemptAt",
                      "createdAt","updatedAt","videoEpisodeId","episodeShotId",
                      "episodeShotVersionId","productionBaselineId"
                    ) VALUES (?,NULL,?,?,NULL,NULL,?,NULL,'seedance',?,'pending',?,?,?,0,0,?,?,?, ?,?,?,?)
                    """,
                    taskId,
                    baselineShot.get("projectId"),
                    baselineShot.get("novelId"),
                    input.promptVersionId(),
                    input.model(),
                    clientRequestId,
                    inputHash,
                    canonicalJson(input.snapshot()),
                    now,
                    now,
                    now,
                    episodeId,
                    shotId,
                    input.shotVersionId(),
                    baselineId);
            return taskResponse(tx, requireTask(tx, userId, episodeId, taskId, false));
        });
    }

    @Override
    public ObjectNode retryTask(
            String userId,
            String episodeId,
            String taskId,
            JsonNode request,
            String executionMode,
            boolean referenceTransportConfigured) {
        String clientRequestId = clientRequestId(request);
        boolean feeConfirmed = booleanField(request, "feeConfirmed", false);
        return database.transactionResult(tx -> {
            Record observed = requireTask(tx, userId, episodeId, taskId, false);
            String baselineId = observed.get("productionBaselineId", String.class);
            String shotId = observed.get("episodeShotId", String.class);
            renderLock(tx, episodeId, shotId);
            Record source = requireTask(tx, userId, episodeId, taskId, true);
            Record existing = taskByRequest(tx, shotId, clientRequestId);
            if (existing != null) {
                if (!taskId.equals(existing.get("retryOfTaskId", String.class))) {
                    throw conflict(
                            "VIDEO_RENDER_CLIENT_REQUEST_REUSED",
                            "clientRequestId 已用于另一条逐镜任务");
                }
                requireReplay(tx, existing, episodeId, baselineId, shotId, feeConfirmed);
                return taskResponse(tx, existing);
            }
            if (!TERMINAL.contains(source.get("status", String.class))) {
                throw conflict("VIDEO_RENDER_TASK_STILL_ACTIVE", "当前任务仍在执行，不能重试");
            }
            if ("submission_unknown".equals(source.get("status", String.class))) {
                throw conflict(
                        "VIDEO_RENDER_SUBMISSION_UNRESOLVED",
                        "原任务提交结果尚待核查，不能创建普通重试");
            }
            if (!RETRYABLE.contains(source.get("status", String.class))) {
                throw conflict("VIDEO_RENDER_TASK_NOT_RETRYABLE", "当前任务终态不允许重试");
            }
            ObjectNode snapshot = readObject(source, "requestManifestJson", "原渲染任务冻结输入");
            String inputHash = source.get("inputHash", String.class);
            requireHash(snapshot, inputHash);
            VideoEpisodeRenderInput input = parseInput(
                    tx,
                    snapshot,
                    shotId,
                    source.get("episodeShotVersionId", String.class),
                    source.get("projectId", String.class),
                    episodeId,
                    baselineId,
                    true);
            Record baselineShot = requireBaselineShot(
                    tx, userId, episodeId, baselineId, shotId, true);
            if (!inputHash.equals(baselineShot.get("inputHash", String.class))
                    || !input.shotVersionId()
                            .equals(baselineShot.get("shotVersionId", String.class))) {
                throw conflict(
                        "VIDEO_RENDER_RETRY_BASELINE_CHANGED",
                        "原任务冻结输入与制作基线镜头不再一致");
            }
            requireRuntime(input, executionMode, feeConfirmed, referenceTransportConfigured);
            requireNoBlockingTask(tx, episodeId, shotId, taskId);
            String retryId = ids.next();
            LocalDateTime now = now();
            tx.execute(
                    """
                    INSERT INTO public."VideoShotRenderTask" (
                      id,"adaptationId","projectId","novelId","shotId","shotPlanVersionId",
                      "promptVersionId","retryOfTaskId",provider,model,status,"clientRequestId",
                      "inputHash","requestManifestJson","pollCount","attemptCount","nextAttemptAt",
                      "createdAt","updatedAt","videoEpisodeId","episodeShotId",
                      "episodeShotVersionId","productionBaselineId"
                    ) VALUES (?,NULL,?,?,NULL,NULL,?,?,'seedance',?,'pending',?,?,?,0,0,?,?,?, ?,?,?,?)
                    """,
                    retryId,
                    source.get("projectId"),
                    source.get("novelId"),
                    source.get("promptVersionId"),
                    taskId,
                    source.get("model"),
                    clientRequestId,
                    inputHash,
                    canonicalJson(input.snapshot()),
                    now,
                    now,
                    now,
                    episodeId,
                    shotId,
                    input.shotVersionId(),
                    baselineId);
            return taskResponse(tx, requireTask(tx, userId, episodeId, retryId, false));
        });
    }

    @Override
    public ObjectNode getTask(String userId, String episodeId, String taskId) {
        return database.transactionResult(
                tx -> taskResponse(tx, requireTask(tx, userId, episodeId, taskId, false)));
    }

    @Override
    public VideoAssetFile getTakeFile(String userId, String episodeId, String takeId) {
        Record row = database.dsl().fetchOne(
                """
                SELECT asset."storageKey",asset."mimeType",asset.name
                FROM public."VideoShotTake" take
                JOIN public."VideoAsset" asset ON asset.id=take."assetId"
                JOIN public."VideoEpisode" episode ON episode.id=take."videoEpisodeId"
                JOIN public."Novel" novel ON novel.id=episode."novelId"
                WHERE take.id=? AND take."videoEpisodeId"=? AND take."adaptationId" IS NULL
                  AND novel."userId"=? AND episode."archivedAt" IS NULL
                """,
                takeId,
                episodeId,
                userId);
        if (row == null) throw notFound("VIDEO_TAKE_NOT_FOUND", "候选 Take 不存在");
        return new VideoAssetFile(
                row.get("storageKey", String.class),
                row.get("mimeType", String.class),
                row.get("name", String.class));
    }

    /** 只领取 episode-native 分支；旧 adaptation 协调器有对称过滤，不能互相消费。 */
    @Override
    public VideoAssetFile getProviderAssetFile(String assetId, String sha256) {
        Record asset = database.dsl().fetchOne(
                """
                SELECT "storageKey","mimeType",name
                FROM public."VideoAsset"
                WHERE id=? AND sha256=? AND modality='image'
                  AND "rightsStatus"='confirmed' AND "lockedAt" IS NOT NULL
                """,
                assetId,
                sha256);
        if (asset == null) {
            throw notFound(
                    "VIDEO_PROVIDER_ASSET_NOT_FOUND",
                    "供应商参考素材不存在或不可用");
        }
        return new VideoAssetFile(
                asset.get("storageKey", String.class),
                asset.get("mimeType", String.class),
                asset.get("name", String.class));
    }

    @Override
    public List<VideoEpisodeRenderClaim> claimDue(int limit) {
        if (limit < 1) throw new IllegalArgumentException("逐镜任务领取数量必须为正整数");
        LocalDateTime now = now();
        LocalDateTime lease = now.plusSeconds(90);
        return database.transactionResult(tx -> {
            List<Record> rows = tx.fetch(
                    """
                    SELECT * FROM public."VideoShotRenderTask"
                    WHERE "videoEpisodeId" IS NOT NULL AND "adaptationId" IS NULL
                      AND status IN ('pending','submitting','queued','running','archiving')
                      AND "nextAttemptAt" <= ?
                    ORDER BY "nextAttemptAt","createdAt",id
                    LIMIT ? FOR UPDATE SKIP LOCKED
                    """,
                    now,
                    limit);
            List<VideoEpisodeRenderClaim> claims = new ArrayList<>();
            for (Record row : rows) {
                String status = row.get("status", String.class);
                if ("submitting".equals(status)) {
                    finish(
                            tx,
                            row,
                            Set.of("submitting"),
                            "submission_unknown",
                            "SEEDANCE_SUBMISSION_RECOVERY_UNKNOWN",
                            "服务在供应商创建请求期间中断，未自动重提以避免重复计费");
                    continue;
                }
                VideoEpisodeRenderInput input = taskInput(
                        tx, row, "pending".equals(status));
                int attempts = row.get("attemptCount", Integer.class);
                int polls = row.get("pollCount", Integer.class);
                String claimed = status;
                if ("pending".equals(status)) {
                    claimed = "submitting";
                    attempts++;
                } else {
                    polls++;
                }
                tx.execute(
                        """
                        UPDATE public."VideoShotRenderTask"
                        SET status=?,"attemptCount"=?,"pollCount"=?,"nextAttemptAt"=?,"updatedAt"=?
                        WHERE id=? AND "videoEpisodeId" IS NOT NULL
                        """,
                        claimed,
                        attempts,
                        polls,
                        lease,
                        now,
                        row.get("id"));
                claims.add(claim(row, claimed, polls, input));
            }
            return List.copyOf(claims);
        });
    }

    @Override
    public void markSubmitted(String taskId, String providerTaskId) {
        if (providerTaskId == null || providerTaskId.isBlank()) {
            throw new IllegalArgumentException("供应商任务 ID 不能为空");
        }
        database.transactionResult(tx -> {
            Record row = lockTask(tx, taskId);
            if (row == null || !"submitting".equals(row.get("status", String.class))) {
                return null;
            }
            LocalDateTime now = now();
            tx.execute(
                    """
                    UPDATE public."VideoShotRenderTask"
                    SET "providerTaskId"=?,status='queued',"submittedAt"=?,"nextAttemptAt"=?,
                        "lastErrorCode"=NULL,"lastErrorMessage"=NULL,"updatedAt"=?
                    WHERE id=? AND "videoEpisodeId" IS NOT NULL
                    """,
                    providerTaskId,
                    now,
                    now.plusSeconds(5),
                    now,
                    taskId);
            return null;
        });
    }

    @Override
    public void markSubmissionUnknown(String taskId, String message) {
        finishTask(
                taskId,
                Set.of("submitting"),
                "submission_unknown",
                "SEEDANCE_SUBMISSION_UNKNOWN",
                message);
    }

    @Override
    public void markSubmissionRejected(String taskId, String code, String message) {
        finishTask(taskId, Set.of("submitting"), "failed", code, message);
    }

    @Override
    public void markQueryProgress(String taskId, String status) {
        if (!Set.of("queued", "running").contains(status)) {
            throw new IllegalArgumentException("供应商进行中状态无效");
        }
        database.transactionResult(tx -> {
            Record row = lockTask(tx, taskId);
            if (row == null || !QUERY.contains(row.get("status", String.class))) return null;
            LocalDateTime now = now();
            tx.execute(
                    """
                    UPDATE public."VideoShotRenderTask"
                    SET status=?,"nextAttemptAt"=?,"lastErrorCode"=NULL,
                        "lastErrorMessage"=NULL,"updatedAt"=? WHERE id=?
                    """,
                    status,
                    now.plusSeconds(pollBackoff(row.get("pollCount", Integer.class))),
                    now,
                    taskId);
            return null;
        });
    }

    @Override
    public void markQueryError(String taskId, String message) {
        database.transactionResult(tx -> {
            Record row = lockTask(tx, taskId);
            if (row == null || !QUERY.contains(row.get("status", String.class))) return null;
            LocalDateTime now = now();
            tx.execute(
                    """
                    UPDATE public."VideoShotRenderTask"
                    SET "attemptCount"="attemptCount"+1,"nextAttemptAt"=?,
                        "lastErrorCode"='SEEDANCE_QUERY_RETRY',"lastErrorMessage"=?,"updatedAt"=?
                    WHERE id=?
                    """,
                    now.plusSeconds(pollBackoff(row.get("pollCount", Integer.class))),
                    message,
                    now,
                    taskId);
            return null;
        });
    }

    @Override
    public boolean beginArchiving(String taskId) {
        return database.transactionResult(tx -> {
            Record row = lockTask(tx, taskId);
            if (row == null || !QUERY.contains(row.get("status", String.class))) return false;
            LocalDateTime now = now();
            tx.execute(
                    """
                    UPDATE public."VideoShotRenderTask"
                    SET status='archiving',"nextAttemptAt"=?,"updatedAt"=? WHERE id=?
                    """,
                    now.plusMinutes(3),
                    now,
                    taskId);
            return true;
        });
    }

    @Override
    public void markProviderTerminal(
            String taskId, String status, String code, String message) {
        if (!Set.of("failed", "expired", "cancelled").contains(status)) {
            throw new IllegalArgumentException("供应商终态无效");
        }
        database.transactionResult(tx -> {
            Record row = lockTask(tx, taskId);
            if (row == null) return null;
            if ("archiving".equals(row.get("status", String.class))) {
                LocalDateTime now = now();
                tx.execute(
                        """
                        UPDATE public."VideoShotRenderTask"
                        SET "lastErrorCode"='SEEDANCE_GENERATED_RESULT_UNAVAILABLE',
                            "lastErrorMessage"='视频已生成，但供应商结果暂时不可用，继续核查原任务',
                            "nextAttemptAt"=?,"updatedAt"=? WHERE id=?
                        """,
                        now.plusMinutes(5),
                        now,
                        taskId);
            } else {
                finish(tx, row, QUERY, status, code, message);
            }
            return null;
        });
    }

    @Override
    public boolean retryArchiving(String taskId, String message) {
        return database.transactionResult(tx -> {
            Record row = lockTask(tx, taskId);
            if (row == null || !"archiving".equals(row.get("status", String.class))) {
                return false;
            }
            LocalDateTime now = now();
            tx.execute(
                    """
                    UPDATE public."VideoShotRenderTask"
                    SET "attemptCount"="attemptCount"+1,"nextAttemptAt"=?,
                        "lastErrorCode"='SEEDANCE_RESULT_ARCHIVE_RETRY',
                        "lastErrorMessage"=?,"updatedAt"=? WHERE id=?
                    """,
                    now.plusSeconds(pollBackoff(row.get("pollCount", Integer.class))),
                    message,
                    now,
                    taskId);
            return true;
        });
    }

    /** 视频、可选尾帧、唯一 Take 与任务终态在一个事务中提交。 */
    @Override
    public void completeTake(String taskId, CompletedEpisodeVideoTake completed) {
        database.transactionResult(tx -> {
            Record task = lockTask(tx, taskId);
            if (task == null) throw new IllegalStateException("独立剧集逐镜任务不存在");
            Record existing = tx.fetchOne(
                    "SELECT id FROM public.\"VideoShotTake\" WHERE \"taskId\"=?",
                    taskId);
            if (existing != null) return null;
            if (!"archiving".equals(task.get("status", String.class))
                    || task.get("providerTaskId", String.class) == null) {
                throw new IllegalStateException("独立剧集逐镜任务不在归档阶段");
            }
            if (!taskId.equals(completed.assetId())) {
                throw new IllegalArgumentException("归档视频必须使用任务确定性素材 ID");
            }
            VideoEpisodeRenderInput input = taskInput(tx, task);
            validateCompleted(input, completed);
            String shotId = task.get("episodeShotId", String.class);
            tx.fetchOne(
                    "SELECT id FROM public.\"VideoEpisodeShot\" WHERE id=? FOR UPDATE",
                    shotId);
            Record maximum = tx.fetchOne(
                    "SELECT COALESCE(MAX(\"takeNo\"),0) n FROM public.\"VideoShotTake\""
                            + " WHERE \"episodeShotId\"=? AND \"videoEpisodeId\" IS NOT NULL",
                    shotId);
            int takeNo = maximum.get("n", Integer.class) + 1;
            LocalDateTime now = now();
            String sourceKind = "simulated".equals(input.executionMode())
                    ? "virtual"
                    : "model_generated";
            insertAsset(
                    tx,
                    completed.assetId(),
                    task.get("projectId", String.class),
                    "镜头 " + shotId + " · Take " + takeNo,
                    "video",
                    "motion",
                    completed.stored(),
                    completed.durationMs(),
                    sourceKind,
                    now);
            if (completed.lastFrame() != null) {
                ArchivedVideoFrame frame = completed.lastFrame();
                insertAsset(
                        tx,
                        frame.assetId(),
                        task.get("projectId", String.class),
                        "镜头 " + shotId + " · Take " + takeNo + " 尾帧",
                        "image",
                        "keyframe",
                        frame.stored(),
                        null,
                        sourceKind,
                        now);
            }
            tx.execute(
                    """
                    INSERT INTO public."VideoShotTake" (
                      id,"taskId","adaptationId","projectId","novelId","shotId",
                      "shotPlanVersionId","promptVersionId","assetId","takeNo",provider,model,
                      "providerTaskId","inputHash","providerMetadataJson","createdAt",
                      "videoEpisodeId","episodeShotId","episodeShotVersionId","productionBaselineId",
                      "lastFrameAssetId"
                    ) VALUES (?,?,NULL,?,?,NULL,NULL,?,?,?,?,?,?,?,?,?, ?,?,?,?,?)
                    """,
                    ids.next(),
                    taskId,
                    task.get("projectId"),
                    task.get("novelId"),
                    task.get("promptVersionId"),
                    completed.assetId(),
                    takeNo,
                    task.get("provider"),
                    task.get("model"),
                    task.get("providerTaskId"),
                    task.get("inputHash"),
                    canonicalJson(completed.providerMetadata()),
                    now,
                    task.get("videoEpisodeId"),
                    shotId,
                    task.get("episodeShotVersionId"),
                    task.get("productionBaselineId"),
                    completed.lastFrame() == null ? null : completed.lastFrame().assetId());
            tx.execute(
                    """
                    UPDATE public."VideoShotRenderTask"
                    SET status='succeeded',"lastErrorCode"=NULL,"lastErrorMessage"=NULL,
                        "completedAt"=?,"nextAttemptAt"=?,"updatedAt"=? WHERE id=?
                    """,
                    now,
                    now,
                    now,
                    taskId);
            return null;
        });
    }

    private void insertAsset(
            DSLContext tx,
            String assetId,
            String projectId,
            String name,
            String modality,
            String duty,
            cn.inkforge.core.video.application.StoredVideoAsset stored,
            Integer durationMs,
            String sourceKind,
            LocalDateTime now) {
        tx.execute(
                """
                INSERT INTO public."VideoAsset" (
                  id,"projectId",name,modality,duty,"storageKey","mimeType","byteSize",
                  "durationMs",sha256,"sourceKind","rightsStatus","lockedAt","createdAt","updatedAt"
                ) VALUES (?,?,?,?,?,?,?,?,?, ?,?,'confirmed',?,?,?)
                """,
                assetId,
                projectId,
                name,
                modality,
                duty,
                stored.storageKey(),
                stored.mimeType(),
                stored.byteSize(),
                durationMs,
                stored.sha256(),
                sourceKind,
                now,
                now,
                now);
    }

    private void validateCompleted(
            VideoEpisodeRenderInput input, CompletedEpisodeVideoTake completed) {
        Map<String, Object> metadata = completed.providerMetadata();
        String mediaKind = Objects.toString(metadata.get("mediaKind"), "");
        String mode = Objects.toString(metadata.get("executionMode"), "");
        if (!input.executionMode().equals(mode)) {
            throw new IllegalArgumentException("归档事实与冻结执行模式不一致");
        }
        Object usage = metadata.get("usage");
        if (!(usage instanceof Map<?, ?>)) {
            throw new IllegalArgumentException("归档事实缺少供应商用量对象");
        }
        if ("simulated".equals(mode)) {
            if (!"simulated_placeholder".equals(mediaKind)
                    || !((Map<?, ?>) usage).isEmpty()
                    || completed.lastFrame() != null) {
                throw new IllegalArgumentException("模拟 Take 必须是无供应商用量的占位媒体");
            }
        } else if (!"provider_media".equals(mediaKind)) {
            throw new IllegalArgumentException("真实 Take 必须标记供应商媒体来源");
        }
        if (metadata.containsKey("videoUrl") || metadata.containsKey("lastFrameUrl")) {
            throw new IllegalArgumentException("供应商临时 URL 不能进入不可变 Take");
        }
        Object lastFrame = metadata.get("lastFrame");
        if ((completed.lastFrame() == null) != (lastFrame == null)) {
            throw new IllegalArgumentException("尾帧归档事实不完整");
        }
    }

    private VideoEpisodeRenderClaim claim(
            Record row, String status, int pollCount, VideoEpisodeRenderInput input) {
        return new VideoEpisodeRenderClaim(
                row.get("id", String.class),
                row.get("videoEpisodeId", String.class),
                row.get("productionBaselineId", String.class),
                row.get("projectId", String.class),
                row.get("novelId", String.class),
                row.get("episodeShotId", String.class),
                row.get("episodeShotVersionId", String.class),
                status,
                row.get("providerTaskId", String.class),
                pollCount,
                row.get("inputHash", String.class),
                input);
    }

    private VideoEpisodeRenderInput taskInput(DSLContext tx, Record task) {
        return taskInput(tx, task, false);
    }

    private VideoEpisodeRenderInput taskInput(
            DSLContext tx, Record task, boolean verifyReferenceSources) {
        ObjectNode snapshot = readObject(task, "requestManifestJson", "渲染任务冻结输入");
        String hash = task.get("inputHash", String.class);
        requireHash(snapshot, hash);
        VideoEpisodeRenderInput input = parseInput(
                tx,
                snapshot,
                task.get("episodeShotId", String.class),
                task.get("episodeShotVersionId", String.class),
                task.get("projectId", String.class),
                task.get("videoEpisodeId", String.class),
                task.get("productionBaselineId", String.class),
                verifyReferenceSources);
        if (!input.promptVersionId().equals(task.get("promptVersionId", String.class))
                || !input.model().equals(task.get("model", String.class))
                || !input.provider().equals(task.get("provider", String.class))) {
            throw new IllegalStateException("逐镜任务列与冻结输入不一致");
        }
        return input;
    }

    private VideoEpisodeRenderInput parseInput(
            DSLContext tx,
            ObjectNode snapshot,
            String expectedShotId,
            String expectedShotVersionId,
            String projectId,
            String episodeId,
            String baselineId,
            boolean verifyReferenceSources) {
        String schemaVersion = requiredText(snapshot, "schemaVersion");
        String shotId = requiredText(snapshot, "shotId");
        String shotVersionId = requiredText(snapshot, "shotVersionId");
        if (!Set.of(
                                "video-production-shot-input/1.0",
                                "video-production-shot-input/1.1",
                                "video-production-shot-input/1.2")
                        .contains(schemaVersion)
                || !expectedShotId.equals(shotId)
                || !expectedShotVersionId.equals(shotVersionId)) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", "制作基线镜头身份或版本无效");
        }
        String provider = requiredText(snapshot, "provider");
        String generationMode = requiredText(snapshot, "generationMode");
        String executionMode = requiredText(snapshot, "executionMode");
        if ("live".equals(executionMode)
                && !"video-production-shot-input/1.2".equals(schemaVersion)) {
            throw conflict(
                    "VIDEO_RENDER_RIGHTS_SNAPSHOT_REQUIRED",
                    "真实生成必须基于冻结权利状态和锁定时间的 1.2 制作基线");
        }
        boolean frozenFeeConfirmed = requiredBoolean(snapshot, "feeConfirmed");
        String resolution = requiredText(snapshot, "resolution");
        String outputFormat = requiredText(snapshot, "outputFormat");
        int duration = requiredInt(snapshot, "durationSeconds");
        String prompt = requiredText(snapshot, "prompt");
        String model = requiredText(snapshot, "model");
        String ratio = requiredText(snapshot, "ratio");
        int shotVersionNo = requiredInt(snapshot, "shotVersionNo");
        if (!"seedance".equals(provider)
                || !"reference".equals(generationMode)
                || !Set.of("simulated", "live").contains(executionMode)
                || ("simulated".equals(executionMode) && frozenFeeConfirmed)
                || ("live".equals(executionMode) && !frozenFeeConfirmed)
                || !"720p".equals(resolution)
                || !"mp4".equals(outputFormat)
                || duration < 4
                || duration > 12
                || shotVersionNo < 1
                || model.codePointCount(0, model.length()) > 200
                || !Set.of("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive")
                        .contains(ratio)
                || prompt.codePointCount(0, prompt.length()) > 2_500) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", "制作基线生成参数超出首批范围");
        }
        ArrayNode lineValues = requiredArray(snapshot, "scriptLineIds", 500);
        List<String> lineIds = new ArrayList<>();
        lineValues.forEach(value -> lineIds.add(requiredTextValue(value, "剧本台词 ID")));
        if (new HashSet<>(lineIds).size() != lineIds.size()) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", "制作基线剧本台词身份重复");
        }
        ArrayNode referenceValues = requiredArray(snapshot, "references", 20);
        if (referenceValues.isEmpty()) {
            throw invalid("VIDEO_RENDER_REFERENCE_REQUIRED", "参考图生成至少需要一份冻结视觉素材");
        }
        List<VideoEpisodeRenderReference> references = new ArrayList<>();
        boolean freezesRights = "video-production-shot-input/1.2".equals(schemaVersion);
        Set<String> versions = new HashSet<>();
        for (int index = 0; index < referenceValues.size(); index++) {
            JsonNode value = referenceValues.get(index);
            if (!(value instanceof ObjectNode reference)) {
                throw invalid("VIDEO_RENDER_REFERENCE_INVALID", "冻结视觉参考必须是对象");
            }
            int ordinal = requiredInt(reference, "ordinal");
            String canonVersionId = requiredText(reference, "canonVersionId");
            String canonContentHash = requiredHash(reference, "canonContentHash");
            String assetId = requiredText(reference, "assetId");
            String sha256 = requiredHash(reference, "sha256");
            String mimeType = requiredText(reference, "mimeType");
            String duty = requiredText(reference, "duty");
            int strength = requiredInt(reference, "strength");
            String rightsStatus =
                    freezesRights ? requiredText(reference, "rightsStatus") : null;
            OffsetDateTime lockedAt =
                    freezesRights
                            ? requiredUtcTimestamp(
                                    reference,
                                    "lockedAt",
                                    "VIDEO_RENDER_REFERENCE_INVALID")
                            : null;
            if (ordinal != index + 1
                    || !versions.add(canonVersionId)
                    || !Set.of("image/jpeg", "image/png", "image/webp").contains(mimeType)
                    || !DUTIES.contains(duty)
                    || (freezesRights && !"confirmed".equals(rightsStatus))
                    || strength < 1
                    || strength > 100) {
                throw invalid("VIDEO_RENDER_REFERENCE_INVALID", "冻结视觉参考顺序或参数无效");
            }
            Record source = verifyReferenceSources ? tx.fetchOne(
                    """
                    SELECT version."contentHash",version."assetId",asset.sha256,asset."mimeType",
                           asset."rightsStatus",asset."lockedAt",canon.duty
                    FROM public."VideoVisualCanonVersion" version
                    JOIN public."VideoVisualCanon" canon
                      ON canon.id=version."canonId" AND canon."projectId"=version."projectId"
                    JOIN public."VideoAsset" asset
                      ON asset.id=version."assetId" AND asset."projectId"=version."projectId"
                    WHERE version.id=? AND version."projectId"=?
                    """,
                    canonVersionId,
                    projectId) : null;
            if (verifyReferenceSources && (source == null
                    || !canonContentHash.equals(source.get("contentHash", String.class))
                    || !assetId.equals(source.get("assetId", String.class))
                    || !sha256.equals(source.get("sha256", String.class))
                    || !mimeType.equals(source.get("mimeType", String.class))
                    || !duty.equals(source.get("duty", String.class))
                    || !"confirmed".equals(source.get("rightsStatus", String.class))
                    || source.get("lockedAt") == null
                    || (freezesRights
                            && (!rightsStatus.equals(source.get("rightsStatus", String.class))
                                    || !DatabaseTimestamp.sameInstant(
                                            source.get("lockedAt", LocalDateTime.class),
                                            lockedAt))))) {
                throw conflict(
                        "VIDEO_RENDER_REFERENCE_CHANGED",
                        "制作基线引用的视觉素材事实已损坏或不可用");
            }
            references.add(new VideoEpisodeRenderReference(
                    ordinal,
                    canonVersionId,
                    canonContentHash,
                    assetId,
                    sha256,
                    mimeType,
                    duty,
                    strength));
        }
        JsonNode rawKeyframes = snapshot.get("keyframes");
        ArrayNode keyframeValues;
        if (rawKeyframes == null || rawKeyframes.isNull()) {
            if (!"video-production-shot-input/1.0".equals(schemaVersion)) {
                throw invalid("VIDEO_RENDER_KEYFRAME_INVALID", "1.1 及以上制作输入缺少关键帧清单");
            }
            keyframeValues = json.createArrayNode();
        } else if (rawKeyframes instanceof ArrayNode array && array.size() <= 3) {
            keyframeValues = array;
        } else {
            throw invalid("VIDEO_RENDER_KEYFRAME_INVALID", "冻结关键帧清单无效");
        }
        if ("video-production-shot-input/1.0".equals(schemaVersion)
                && !keyframeValues.isEmpty()) {
            throw invalid("VIDEO_RENDER_KEYFRAME_INVALID", "1.0 制作输入不能携带关键帧");
        }
        if (references.size() + keyframeValues.size() > 20) {
            throw invalid("VIDEO_RENDER_REFERENCE_INVALID", "视觉参考与关键帧合计不能超过 20 张");
        }
        List<VideoEpisodeRenderKeyframe> keyframes = new ArrayList<>();
        Set<String> roles = new HashSet<>();
        for (int index = 0; index < keyframeValues.size(); index++) {
            JsonNode value = keyframeValues.get(index);
            if (!(value instanceof ObjectNode keyframe)) {
                throw invalid("VIDEO_RENDER_KEYFRAME_INVALID", "冻结关键帧必须是对象");
            }
            int ordinal = requiredInt(keyframe, "ordinal");
            String keyframeVersionId = requiredText(keyframe, "keyframeVersionId");
            String role = requiredText(keyframe, "role");
            String assetId = requiredText(keyframe, "assetId");
            String sha256 = requiredHash(keyframe, "sha256");
            String mimeType = requiredText(keyframe, "mimeType");
            String duty = requiredText(keyframe, "duty");
            String contentHash = requiredHash(keyframe, "contentHash");
            String rightsStatus =
                    freezesRights ? requiredText(keyframe, "rightsStatus") : null;
            OffsetDateTime lockedAt =
                    freezesRights
                            ? requiredUtcTimestamp(
                                    keyframe,
                                    "lockedAt",
                                    "VIDEO_RENDER_KEYFRAME_INVALID")
                            : null;
            if (ordinal != index + 1
                    || !roles.add(role)
                    || !KEYFRAME_ROLES.contains(role)
                    || !KEYFRAME_DUTIES.contains(duty)
                    || (freezesRights && !"confirmed".equals(rightsStatus))
                    || !Set.of("image/jpeg", "image/png", "image/webp").contains(mimeType)) {
                throw invalid("VIDEO_RENDER_KEYFRAME_INVALID", "关键帧顺序、角色或素材类型无效");
            }
            Record source =
                    verifyReferenceSources
                            ? tx.fetchOne(
                                    """
                                    SELECT version.role,version."assetId",version."contentHash",
                                           version."sourceKind",asset.sha256,asset."mimeType",asset.duty,
                                           asset."rightsStatus",asset."lockedAt"
                                    FROM public."VideoShotKeyframeVersion" version
                                    JOIN public."VideoAsset" asset
                                      ON asset.id=version."assetId"
                                     AND asset."projectId"=version."projectId"
                                    WHERE version.id=? AND version."projectId"=?
                                      AND version."videoEpisodeId"=?
                                      AND version."episodeShotId"=?
                                      AND version."episodeShotVersionId"=?
                                      AND version."productionBaselineId"=?
                                    """,
                                    keyframeVersionId,
                                    projectId,
                                    episodeId,
                                    expectedShotId,
                                    expectedShotVersionId,
                                    baselineId)
                            : null;
            if (verifyReferenceSources
                    && (source == null
                            || !role.equals(source.get("role", String.class))
                            || !assetId.equals(source.get("assetId", String.class))
                            || !contentHash.equals(source.get("contentHash", String.class))
                            || !"asset".equals(source.get("sourceKind", String.class))
                            || !sha256.equals(source.get("sha256", String.class))
                            || !mimeType.equals(source.get("mimeType", String.class))
                            || !duty.equals(source.get("duty", String.class))
                            || !"confirmed".equals(source.get("rightsStatus", String.class))
                            || source.get("lockedAt") == null
                            || (freezesRights
                                    && (!rightsStatus.equals(
                                                    source.get("rightsStatus", String.class))
                                            || !DatabaseTimestamp.sameInstant(
                                                    source.get(
                                                            "lockedAt", LocalDateTime.class),
                                                    lockedAt))))) {
                throw conflict(
                        "VIDEO_RENDER_KEYFRAME_CHANGED",
                        "制作基线引用的关键帧事实已损坏或不可用");
            }
            keyframes.add(
                    new VideoEpisodeRenderKeyframe(
                            ordinal,
                            keyframeVersionId,
                            role,
                            assetId,
                            sha256,
                            mimeType,
                            duty,
                            contentHash));
        }
        return new VideoEpisodeRenderInput(
                schemaVersion,
                shotId,
                shotVersionId,
                shotVersionNo,
                requiredHash(snapshot, "shotContentHash"),
                requiredText(snapshot, "scriptSceneId"),
                lineIds,
                provider,
                model,
                generationMode,
                executionMode,
                frozenFeeConfirmed,
                requiredText(snapshot, "promptVersionId"),
                prompt,
                ratio,
                duration,
                resolution,
                requiredBoolean(snapshot, "generateAudio"),
                requiredBoolean(snapshot, "watermark"),
                outputFormat,
                references,
                keyframes,
                toMap(snapshot));
    }

    private void requireRuntime(
            VideoEpisodeRenderInput input,
            String executionMode,
            boolean feeConfirmed,
            boolean referenceTransportConfigured) {
        if (!input.executionMode().equals(executionMode)) {
            throw conflict(
                    "VIDEO_RENDER_EXECUTION_MODE_CONFLICT",
                    "当前运行模式与制作基线冻结模式不同");
        }
        if (input.feeConfirmed() != feeConfirmed
                || ("simulated".equals(executionMode) && feeConfirmed)
                || ("live".equals(executionMode) && !feeConfirmed)) {
            throw invalid("VIDEO_RENDER_FEE_CONFIRMATION_INVALID", "本次费用确认与冻结模式不一致");
        }
        if ("live".equals(executionMode) && !referenceTransportConfigured) {
            throw new ApiException(
                    503,
                    "VIDEO_RENDER_REFERENCE_TRANSPORT_NOT_CONFIGURED",
                    "当前环境尚未配置供应商可访问的冻结参考图地址");
        }
    }

    private void requireNoBlockingTask(
            DSLContext tx,
            String episodeId,
            String shotId,
            String excludedTaskId) {
        Record blocker = tx.fetchOne(
                """
                SELECT id,status FROM public."VideoShotRenderTask"
                WHERE "videoEpisodeId"=? AND "episodeShotId"=?
                  AND (CAST(? AS TEXT) IS NULL OR id<>?)
                  AND status IN ('pending','submitting','submission_unknown','queued','running','archiving')
                ORDER BY "createdAt" DESC,id DESC LIMIT 1 FOR UPDATE
                """,
                episodeId,
                shotId,
                excludedTaskId,
                excludedTaskId);
        if (blocker == null) return;
        if ("submission_unknown".equals(blocker.get("status", String.class))) {
            throw conflict(
                    "VIDEO_RENDER_SUBMISSION_UNRESOLVED",
                    "同一稳定镜头存在提交未知任务，不能通过新基线或普通重试绕过");
        }
        throw conflict("VIDEO_RENDER_TASK_ACTIVE", "同一稳定镜头已有进行中的生成任务");
    }

    private Record requireBaselineShot(
            DSLContext tx,
            String userId,
            String episodeId,
            String baselineId,
            String shotId,
            boolean lock) {
        String suffix = lock ? " FOR UPDATE OF baseline_shot" : "";
        Record row = tx.fetchOne(
                """
                SELECT baseline_shot.*,episode."novelId"
                FROM public."VideoProductionBaselineShot" baseline_shot
                JOIN public."VideoProductionBaseline" baseline
                  ON baseline.id=baseline_shot."baselineId"
                 AND baseline."episodeId"=baseline_shot."episodeId"
                 AND baseline."projectId"=baseline_shot."projectId"
                JOIN public."VideoEpisode" episode
                  ON episode.id=baseline."episodeId" AND episode."projectId"=baseline."projectId"
                JOIN public."Novel" novel ON novel.id=episode."novelId"
                WHERE baseline_shot."episodeId"=? AND baseline_shot."baselineId"=?
                  AND baseline_shot."shotId"=? AND novel."userId"=?
                  AND episode."archivedAt" IS NULL
                """ + suffix,
                episodeId,
                baselineId,
                shotId,
                userId);
        if (row == null) {
            throw notFound(
                    "VIDEO_PRODUCTION_BASELINE_SHOT_NOT_FOUND",
                    "制作基线镜头不存在或不属于当前用户");
        }
        return row;
    }

    private Record requireTask(
            DSLContext tx, String userId, String episodeId, String taskId, boolean lock) {
        String suffix = lock ? " FOR UPDATE OF task" : "";
        Record row = tx.fetchOne(
                """
                SELECT task.*
                FROM public."VideoShotRenderTask" task
                JOIN public."VideoEpisode" episode ON episode.id=task."videoEpisodeId"
                JOIN public."Novel" novel ON novel.id=episode."novelId"
                WHERE task.id=? AND task."videoEpisodeId"=? AND task."adaptationId" IS NULL
                  AND task."episodeShotId" IS NOT NULL AND task."productionBaselineId" IS NOT NULL
                  AND novel."userId"=? AND episode."archivedAt" IS NULL
                """ + suffix,
                taskId,
                episodeId,
                userId);
        if (row == null) throw notFound("VIDEO_RENDER_TASK_NOT_FOUND", "逐镜任务不存在");
        return row;
    }

    private Record taskByRequest(DSLContext tx, String shotId, String clientRequestId) {
        return tx.fetchOne(
                """
                SELECT * FROM public."VideoShotRenderTask"
                WHERE "videoEpisodeId" IS NOT NULL AND "episodeShotId"=? AND "clientRequestId"=?
                FOR UPDATE
                """,
                shotId,
                clientRequestId);
    }

    private void requireReplay(
            DSLContext tx,
            Record task,
            String episodeId,
            String baselineId,
            String shotId,
            boolean feeConfirmed) {
        VideoEpisodeRenderInput input = taskInput(tx, task);
        if (!episodeId.equals(task.get("videoEpisodeId", String.class))
                || !baselineId.equals(task.get("productionBaselineId", String.class))
                || !shotId.equals(task.get("episodeShotId", String.class))
                || input.feeConfirmed() != feeConfirmed) {
            throw conflict(
                    "VIDEO_RENDER_CLIENT_REQUEST_REUSED",
                    "clientRequestId 已用于不同的逐镜生成请求");
        }
    }

    private ObjectNode taskResponse(DSLContext tx, Record task) {
        VideoEpisodeRenderInput input = taskInput(tx, task);
        Record take = tx.fetchOne(
                """
                SELECT id,"providerMetadataJson" FROM public."VideoShotTake" WHERE "taskId"=?
                """,
                task.get("id"));
        String mediaKind = null;
        if (take != null) {
            mediaKind = readObject(take, "providerMetadataJson", "Take 供应商事实")
                    .path("mediaKind")
                    .asText(null);
        }
        ObjectNode result = json.createObjectNode();
        result.put("id", task.get("id", String.class));
        result.put("episodeId", task.get("videoEpisodeId", String.class));
        result.put("productionBaselineId", task.get("productionBaselineId", String.class));
        result.put("shotId", task.get("episodeShotId", String.class));
        result.put("shotVersionId", task.get("episodeShotVersionId", String.class));
        result.put("promptVersionId", task.get("promptVersionId", String.class));
        putNullable(result, "retryOfTaskId", task.get("retryOfTaskId", String.class));
        result.put("provider", task.get("provider", String.class));
        result.put("model", task.get("model", String.class));
        result.put("status", task.get("status", String.class));
        result.put("inputHash", task.get("inputHash", String.class));
        result.set("inputSnapshot", json.valueToTree(input.snapshot()));
        putNullable(result, "providerTaskId", task.get("providerTaskId", String.class));
        result.put("pollCount", task.get("pollCount", Integer.class));
        result.put("attemptCount", task.get("attemptCount", Integer.class));
        putNullable(result, "lastErrorCode", task.get("lastErrorCode", String.class));
        putNullable(result, "lastErrorMessage", task.get("lastErrorMessage", String.class));
        putNullable(result, "takeId", take == null ? null : take.get("id", String.class));
        putNullable(result, "mediaKind", mediaKind);
        putTime(result, "createdAt", task.get("createdAt", LocalDateTime.class));
        putTime(result, "updatedAt", task.get("updatedAt", LocalDateTime.class));
        putTime(result, "submittedAt", task.get("submittedAt", LocalDateTime.class));
        putTime(result, "completedAt", task.get("completedAt", LocalDateTime.class));
        return result;
    }

    private Record lockTask(DSLContext tx, String taskId) {
        return tx.fetchOne(
                """
                SELECT * FROM public."VideoShotRenderTask"
                WHERE id=? AND "videoEpisodeId" IS NOT NULL AND "adaptationId" IS NULL
                FOR UPDATE
                """,
                taskId);
    }

    private void finishTask(
            String taskId,
            Set<String> expected,
            String status,
            String code,
            String message) {
        database.transactionResult(tx -> {
            Record row = lockTask(tx, taskId);
            if (row != null) finish(tx, row, expected, status, code, message);
            return null;
        });
    }

    private boolean finish(
            DSLContext tx,
            Record row,
            Set<String> expected,
            String status,
            String code,
            String message) {
        if (!expected.contains(row.get("status", String.class))) return false;
        LocalDateTime now = now();
        tx.execute(
                """
                UPDATE public."VideoShotRenderTask"
                SET status=?,"lastErrorCode"=?,"lastErrorMessage"=?,"completedAt"=?,
                    "nextAttemptAt"=?,"updatedAt"=? WHERE id=?
                """,
                status,
                code,
                message,
                now,
                now,
                now,
                row.get("id"));
        return true;
    }

    private ObjectNode readObject(Record row, String column, String label) {
        JsonNode value = json.readTree(row.get(column, String.class));
        if (!(value instanceof ObjectNode object)) {
            throw new IllegalStateException(label + "不是 JSON 对象");
        }
        return object;
    }

    private Map<String, Object> toMap(ObjectNode value) {
        return json.convertValue(value, new TypeReference<Map<String, Object>>() {});
    }

    private void requireHash(ObjectNode snapshot, String expected) {
        if (!canonicalHash(toMap(snapshot)).equals(expected)) {
            throw new IllegalStateException("制作基线逐镜输入哈希不一致");
        }
    }

    private String canonicalHash(Object value) {
        return CommandIdempotency.sha256(CommandIdempotency.canonicalJsonBytes(value, json));
    }

    private String canonicalJson(Object value) {
        return new String(
                CommandIdempotency.canonicalJsonBytes(value, json), StandardCharsets.UTF_8);
    }

    private static String clientRequestId(JsonNode request) {
        if (request == null || !request.isObject()) {
            throw invalid("VIDEO_RENDER_INPUT_INVALID", "逐镜任务请求必须是对象");
        }
        String value = requiredText(request, "clientRequestId").strip();
        int length = value.codePointCount(0, value.length());
        if (length < 16 || length > 128) {
            throw invalid("VIDEO_RENDER_CLIENT_REQUEST_ID_INVALID", "clientRequestId 长度无效");
        }
        return value;
    }

    private static boolean booleanField(JsonNode request, String field, boolean fallback) {
        JsonNode value = request.get(field);
        if (value == null) return fallback;
        if (!value.isBoolean()) throw invalid("VIDEO_RENDER_INPUT_INVALID", field + " 必须是布尔值");
        return value.booleanValue();
    }

    private static String requiredText(JsonNode value, String field) {
        JsonNode child = value.get(field);
        if (child == null || !child.isTextual() || child.textValue().isBlank()) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", field + " 必须是非空字符串");
        }
        return child.textValue();
    }

    private static String requiredTextValue(JsonNode value, String label) {
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", label + " 必须是非空字符串");
        }
        return value.textValue();
    }

    private static int requiredInt(JsonNode value, String field) {
        JsonNode child = value.get(field);
        if (child == null || !child.isIntegralNumber()) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", field + " 必须是整数");
        }
        return child.intValue();
    }

    private static boolean requiredBoolean(JsonNode value, String field) {
        JsonNode child = value.get(field);
        if (child == null || !child.isBoolean()) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", field + " 必须是布尔值");
        }
        return child.booleanValue();
    }

    private static String requiredHash(JsonNode value, String field) {
        String hash = requiredText(value, field);
        if (!hash.matches("^[0-9a-f]{64}$")) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", field + " 不是 SHA-256");
        }
        return hash;
    }

    private static OffsetDateTime requiredUtcTimestamp(
            JsonNode value, String field, String code) {
        JsonNode child = value.get(field);
        if (child == null || !child.isTextual()) {
            throw invalid(code, field + " 必须是规范 UTC 时间");
        }
        try {
            OffsetDateTime timestamp = OffsetDateTime.parse(child.textValue());
            if (!ZoneOffset.UTC.equals(timestamp.getOffset())
                    || !timestamp.toString().equals(child.textValue())) {
                throw invalid(code, field + " 必须是规范 UTC 时间");
            }
            return timestamp;
        } catch (java.time.format.DateTimeParseException exception) {
            throw invalid(code, field + " 必须是规范 UTC 时间");
        }
    }

    private static ArrayNode requiredArray(JsonNode value, String field, int maximum) {
        JsonNode child = value.get(field);
        if (!(child instanceof ArrayNode array) || array.size() > maximum) {
            throw invalid("VIDEO_RENDER_BASELINE_INPUT_INVALID", field + " 数组无效");
        }
        return array;
    }

    private static void renderLock(DSLContext tx, String episodeId, String shotId) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(("video-episode-render\0"
                                    + episodeId
                                    + "\0"
                                    + shotId)
                            .getBytes(StandardCharsets.UTF_8));
            tx.fetchOne(
                    "SELECT pg_advisory_xact_lock(?)",
                    ByteBuffer.wrap(digest, 0, Long.BYTES).getLong());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    private void putTime(ObjectNode target, String field, LocalDateTime value) {
        if (value == null) target.putNull(field);
        else target.set(field, json.valueToTree(DatabaseTimestamp.api(value)));
    }

    private static void putNullable(ObjectNode target, String field, String value) {
        if (value == null) target.putNull(field);
        else target.put(field, value);
    }

    private LocalDateTime now() {
        return DatabaseTimestamp.now(clock);
    }

    private static int pollBackoff(int pollCount) {
        return Math.min(5 + Math.max(pollCount - 1, 0) * 2, 30);
    }

    private static ApiException invalid(String code, String message) {
        return new ApiException(422, code, message);
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(409, code, message);
    }

    private static ApiException notFound(String code, String message) {
        return new ApiException(404, code, message);
    }
}
