package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.agent.ExecutionCancelRequest;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowCancellationRequestResult;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationRepository;
import cn.inkforge.core.workflows.application.WorkflowQualityCompletion;
import cn.inkforge.core.workflows.application.WorkflowStylePortraitCompletion;
import cn.inkforge.core.workflows.application.WorkflowRagIndexCompletion;
import cn.inkforge.core.workflows.application.WorkflowVideoAdaptationCompletion;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.databind.ObjectMapper;

/** Run→Step 固定锁序下实现 V2 取消、精确重投和租约超时收敛。 */
final class JooqWorkflowRunCancellationRepository
        implements WorkflowRunCancellationRepository {

    private static final List<String> TERMINAL_RUNS =
            List.of("completed", "failed", "cancelled");
    private static final Duration CANCEL_RETRY_INTERVAL = Duration.ofSeconds(5);

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final WorkflowBillingCoordinator billing;
    private final java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion;
    private final java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion;
    private final java.util.function.Supplier<WorkflowRagIndexCompletion> ragCompletion;
    private final java.util.function.Supplier<WorkflowVideoAdaptationCompletion> videoCompletion;

    JooqWorkflowRunCancellationRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            ExecutionRegistry registry) {
        this(database, ids, clock, json, registry, () -> null);
    }

    JooqWorkflowRunCancellationRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion) {
        this(database, ids, clock, json, registry, qualityCompletion, () -> null);
    }

    JooqWorkflowRunCancellationRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion) {
        this(database, ids, clock, json, registry, qualityCompletion, styleCompletion, () -> null);
    }

    JooqWorkflowRunCancellationRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion,
            java.util.function.Supplier<WorkflowRagIndexCompletion> ragCompletion) {
        this(database, ids, clock, json, registry, qualityCompletion, styleCompletion, ragCompletion, () -> null);
    }

    JooqWorkflowRunCancellationRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion,
            java.util.function.Supplier<WorkflowRagIndexCompletion> ragCompletion,
            java.util.function.Supplier<WorkflowVideoAdaptationCompletion> videoCompletion) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.billing = new WorkflowBillingCoordinator(ids, json, registry);
        this.qualityCompletion = Objects.requireNonNull(qualityCompletion);
        this.styleCompletion = Objects.requireNonNull(styleCompletion);
        this.ragCompletion = Objects.requireNonNull(ragCompletion);
        this.videoCompletion = Objects.requireNonNull(videoCompletion);
    }

    @Override
    public WorkflowCancellationRequestResult requestInvalidatedRag(String userId, String runId, String clientRequestId) {
        requireNonBlank(userId, "userId"); requireNonBlank(runId, "runId"); requireNonBlank(clientRequestId, "clientRequestId");
        return database.transactionResult(tx -> {
            Record run = lockRun(tx, runId, userId);
            if (TERMINAL_RUNS.contains(run.get("status", String.class))
                    || run.get("cancelRequestedAt", LocalDateTime.class) != null) return new WorkflowCancellationRequestResult(List.of());
            if (!isRagRun(run)) throw new IllegalArgumentException("失效索引取消只能引用 RAG 运行");
            if (!ragCompletion().isInvalidated(tx, runId)) return new WorkflowCancellationRequestResult(List.of());
            return request(tx, userId, runId, clientRequestId);
        });
    }

    @Override
    public WorkflowCancellationRequestResult request(
            String userId, String runId, String clientRequestId) {
        requireNonBlank(userId, "userId");
        requireNonBlank(runId, "runId");
        requireNonBlank(clientRequestId, "clientRequestId");
        return database.transactionResult(
                transaction -> request(transaction, userId, runId, clientRequestId));
    }

    @Override
    public WorkflowCancellationRequestResult requestInvalidatedQuality(
            String userId, String runId, String clientRequestId) {
        requireNonBlank(userId, "userId");
        requireNonBlank(runId, "runId");
        requireNonBlank(clientRequestId, "clientRequestId");
        return database.transactionResult(tx -> {
            Record run = lockRun(tx, runId, userId);
            if (TERMINAL_RUNS.contains(run.get("status", String.class))
                    || run.get("cancelRequestedAt", LocalDateTime.class) != null) {
                return new WorkflowCancellationRequestResult(List.of());
            }
            if (!isQualityRun(run)) throw new IllegalArgumentException("失效来源取消只能引用一致性终检");
            // 后续取消可能释放预留。先锁计费用户，再核验 Chapter/Check，避免 Chapter→User 反序。
            tx.fetchOne("SELECT id FROM public.\"User\" WHERE id = ? FOR UPDATE", userId);
            if (!qualityCompletion().isInvalidated(tx, runId)) {
                return new WorkflowCancellationRequestResult(List.of());
            }
            return request(tx, userId, runId, clientRequestId);
        });
    }

    @Override
    public WorkflowCancellationRequestResult requestDeletedStyle(String userId, String runId, String clientRequestId) {
        requireNonBlank(userId, "userId"); requireNonBlank(runId, "runId"); requireNonBlank(clientRequestId, "clientRequestId");
        return database.transactionResult(tx -> {
            Record run = lockRun(tx, runId, userId);
            if (TERMINAL_RUNS.contains(run.get("status", String.class))
                    || run.get("cancelRequestedAt", LocalDateTime.class) != null) return new WorkflowCancellationRequestResult(List.of());
            if (!isStyleRun(run)) throw new IllegalArgumentException("已删除文风取消只能引用画像运行");
            // 只读复验已提交的目标缺失；公开文风 ID 不复用，不在 Style 锁内反等计费 User。
            if (!styleCompletion().isDeleted(tx, runId)) return new WorkflowCancellationRequestResult(List.of());
            return request(tx, userId, runId, clientRequestId);
        });
    }

    @Override
    public Optional<ExecutionCancelRequest> claimCancellationRetry() {
        return database.transactionResult(this::claimCancellationRetry);
    }

    @Override
    public int settleExpired(int limit) {
        if (limit < 1) throw new IllegalArgumentException("取消租约收敛批次必须为正数");
        return database.transactionResult(transaction -> settleExpired(transaction, limit));
    }

    private WorkflowCancellationRequestResult request(
            DSLContext transaction, String userId, String runId, String clientRequestId) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        Record run = lockRun(transaction, runId, userId);
        String status = run.get("status", String.class);
        if (TERMINAL_RUNS.contains(status)) {
            return new WorkflowCancellationRequestResult(List.of());
        }
        String existingRequestId = run.get("cancelRequestId", String.class);
        LocalDateTime requestedAt = run.get("cancelRequestedAt", LocalDateTime.class);
        if (existingRequestId != null && !existingRequestId.equals(clientRequestId)) {
            throw new ApiException(
                    409,
                    "WORKFLOW_CANCEL_CONFLICT",
                    "该 Workflow Run 已由另一个取消请求进入停止流程");
        }
        if ((existingRequestId == null) != (requestedAt == null)) {
            throw new IllegalStateException("Workflow Run 取消身份与时间不完整");
        }
        if (requestedAt == null) requestedAt = now;
        if (existingRequestId == null) {
            // Step.cancelRequestId 通过复合 FK 绑定 Run，必须先在同一事务建立 Run 侧身份。
            transaction.execute(
                    """
                    UPDATE public."WorkflowRun"
                    SET "cancelRequestId" = ?, "cancelRequestedAt" = ?, "updatedAt" = ?
                    WHERE id = ? AND "cancelRequestId" IS NULL
                    """,
                    clientRequestId,
                    requestedAt,
                    now,
                    runId);
        }

        List<Record> active = transaction.fetch(
                """
                SELECT step.id, step.status::text AS status, step."activeJobId",
                       step."fencingToken", step."requestHash", step."submittedAt"
                FROM public."WorkflowStep" AS step
                WHERE step."runId" = ? AND step.status IN ('pending', 'running')
                ORDER BY step.ordinal, step.id
                FOR UPDATE OF step
                """,
                runId);
        List<ExecutionCancelRequest> requests = new ArrayList<>();
        int running = 0;
        long sequence = run.get("lastEventSequence", Long.class);
        for (Record step : active) {
            String stepStatus = step.get("status", String.class);
            if (step.get("activeJobId", String.class) != null) {
                requests.add(cancelRequest(run, step, clientRequestId, requestedAt));
            }
            if ("running".equals(stepStatus)) {
                running++;
                transaction.execute(
                        """
                        UPDATE public."WorkflowStep"
                        SET "cancelRequestId" = ?, "heartbeatAt" = ?, "updatedAt" = ?
                        WHERE id = ? AND "runId" = ? AND status = 'running'
                        """,
                        clientRequestId,
                        now,
                        now,
                        step.get("id", String.class),
                        runId);
            } else {
                // pending Step 尚未越过 preparing/provider 门；先在同一事务释放可能已由同步
                // Accepted 建立的预留，再把 Step 标记 skipped。
                billing.releaseUnstarted(
                        transaction,
                        runId,
                        step.get("id", String.class),
                        now);
                transaction.execute(
                        """
                        UPDATE public."WorkflowStep"
                        SET status = CAST('skipped' AS "WorkflowStepStatus"),
                            "cancelRequestId" = ?, "activeJobId" = NULL,
                            "leaseExpiresAt" = NULL, "completedAt" = ?, "updatedAt" = ?,
                            "errorCode" = 'RUN_CANCELLED'
                        WHERE id = ? AND "runId" = ? AND status = 'pending'
                        """,
                        clientRequestId,
                        now,
                        now,
                        step.get("id", String.class),
                        runId);
                long fencingToken = step.get("fencingToken", Long.class);
                if (fencingToken > 0) {
                    sequence = appendStepFinished(
                            transaction,
                            runId,
                            step.get("id", String.class),
                            fencingToken,
                            sequence,
                            now);
                }
            }
        }

        if (running == 0) {
            finalizeCancelled(
                    transaction, run, clientRequestId, requestedAt, sequence, now);
        } else {
            transaction.execute(
                    """
                    UPDATE public."WorkflowRun"
                    SET status = CAST('running' AS "WorkflowRunStatus"),
                        "lastEventSequence" = ?, revision = revision + 1, "updatedAt" = ?
                    WHERE id = ?
                    """,
                    sequence,
                    now,
                    runId);
        }
        return new WorkflowCancellationRequestResult(requests);
    }

    private Optional<ExecutionCancelRequest> claimCancellationRetry(DSLContext transaction) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        Record value = transaction.fetchOne(
                """
                SELECT run.id AS "runId", run."novelId", run."cancelRequestId",
                       run."cancelRequestedAt", step.id AS "stepId", step."activeJobId",
                       step."fencingToken", step."requestHash"
                FROM public."WorkflowRun" AS run
                JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                WHERE run."engineVersion" = 2 AND run."cancelRequestedAt" IS NOT NULL
                  AND run.status = 'running' AND step.status = 'running'
                  AND step."cancelRequestId" = run."cancelRequestId"
                  AND step."activeJobId" IS NOT NULL AND step."leaseExpiresAt" > ?
                  AND (step."heartbeatAt" IS NULL OR step."heartbeatAt" <= ?)
                ORDER BY run.id, step.ordinal, step.id
                LIMIT 1
                FOR UPDATE OF run, step SKIP LOCKED
                """,
                now,
                now.minus(CANCEL_RETRY_INTERVAL));
        if (value == null) return Optional.empty();
        transaction.execute(
                """
                UPDATE public."WorkflowStep" SET "heartbeatAt" = ?, "updatedAt" = ?
                WHERE id = ? AND "runId" = ? AND status = 'running'
                """,
                now,
                now,
                value.get("stepId", String.class),
                value.get("runId", String.class));
        return Optional.of(cancelRequest(value));
    }

    private int settleExpired(DSLContext transaction, int limit) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        List<Record> runs = transaction.fetch(
                """
                SELECT run.id, run."userId", run."novelId", run.workflow, run.operation, run.status::text AS status,
                       run."cancelRequestId", run."cancelRequestedAt",
                       run."lastEventSequence", run.revision
                FROM public."WorkflowRun" AS run
                WHERE run."engineVersion" = 2 AND run."cancelRequestedAt" IS NOT NULL
                  AND run.status = 'running'
                  AND EXISTS (
                    SELECT 1 FROM public."WorkflowStep" AS step
                    WHERE step."runId" = run.id AND step.status = 'running'
                      AND step."leaseExpiresAt" <= ?
                  )
                ORDER BY run.id
                LIMIT ?
                FOR UPDATE SKIP LOCKED
                """,
                now,
                limit);
        int settled = 0;
        Map<Record, Long> completedRuns = new LinkedHashMap<>();
        for (Record run : runs) {
            long sequence = run.get("lastEventSequence", Long.class);
            List<Record> expired = transaction.fetch(
                    """
                    SELECT id, "fencingToken", "submittedAt", "usageJson"
                    FROM public."WorkflowStep"
                    WHERE "runId" = ? AND status = 'running' AND "leaseExpiresAt" <= ?
                    ORDER BY ordinal, id
                    FOR UPDATE
                    """,
                    run.get("id", String.class),
                    now);
            for (Record step : expired) {
                String usageJson = step.get("usageJson", String.class);
                if (usageJson == null) {
                    LocalDateTime submittedAt = step.get("submittedAt", LocalDateTime.class);
                    long wallTime = submittedAt == null
                            ? 0L
                            : Math.max(0L, Duration.between(submittedAt, now).toMillis());
                    usageJson = json.writeValueAsString(Map.of(
                            "usageStatus", "unknown",
                            "providerAttempts", 0,
                            "protocolCorrections", 0,
                            "wallTimeMillis", wallTime));
                }
                // running 租约超时无法证明 Provider 没有收到请求。即使最后 progress 仍写 0 attempt，
                // 也必须保留全部预留进入人工/供应商对账，不能按零费用自动释放。
                billing.markExpiredRunningForReconciliation(
                        transaction,
                        run.get("id", String.class),
                        step.get("id", String.class),
                        usageJson,
                        now);
                transaction.execute(
                        """
                        UPDATE public."WorkflowStep"
                        SET status = CAST('skipped' AS "WorkflowStepStatus"),
                            "usageJson" = ?, "activeJobId" = NULL, "leaseExpiresAt" = NULL,
                            "completedAt" = ?, "updatedAt" = ?, "errorCode" = 'RUN_CANCELLED'
                        WHERE id = ? AND "runId" = ? AND status = 'running'
                        """,
                        usageJson,
                        now,
                        now,
                        step.get("id", String.class),
                        run.get("id", String.class));
                sequence = appendStepFinished(
                        transaction,
                        run.get("id", String.class),
                        step.get("id", String.class),
                        step.get("fencingToken", Long.class),
                        sequence,
                        now);
                settled++;
            }
            int remaining = transaction.fetchOne(
                            """
                            SELECT count(*) AS count FROM public."WorkflowStep"
                            WHERE "runId" = ? AND status IN ('pending', 'running')
                            """,
                            run.get("id", String.class))
                    .get("count", Integer.class);
            if (remaining == 0) {
                completedRuns.put(run, sequence);
            } else if (!expired.isEmpty()) {
                transaction.execute(
                        """
                        UPDATE public."WorkflowRun"
                        SET "lastEventSequence" = ?, revision = revision + 1, "updatedAt" = ?
                        WHERE id = ? AND status = 'running'
                        """,
                        sequence,
                        now,
                        run.get("id", String.class));
            }
        }
        // 先完成本批全部计费，再投影业务 Chapter/Check，避免持有章节锁后取得下一个用户计费锁。
        completedRuns.forEach((run, sequence) -> finalizeCancelled(transaction, run,
                run.get("cancelRequestId", String.class), run.get("cancelRequestedAt", LocalDateTime.class),
                sequence, now));
        return settled;
    }

    private Record lockRun(DSLContext transaction, String runId, String userId) {
        Record run = transaction.fetchOne(
                """
                SELECT id, "userId", "novelId", workflow, operation, status::text AS status,
                       "cancelRequestId", "cancelRequestedAt", "lastEventSequence", revision
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2 AND "userId" = ?
                FOR UPDATE
                """,
                runId,
                userId);
        if (run == null) {
            throw new ApiException(404, "WORKFLOW_RUN_NOT_FOUND", "Workflow Run 不存在");
        }
        return run;
    }

    private void finalizeCancelled(
            DSLContext transaction,
            Record run,
            String cancelRequestId,
            LocalDateTime requestedAt,
            long previousSequence,
            LocalDateTime now) {
        if (cancelRequestId == null || requestedAt == null) {
            throw new IllegalStateException("Workflow Run 取消终态缺少身份或时间");
        }
        if (isQualityRun(run)) {
            qualityCompletion().finish(transaction, run.get("id", String.class), "cancelled");
        }
        if (isStyleRun(run)) {
            styleCompletion().finish(transaction, run.get("id", String.class), "cancelled");
        }
        if (isRagRun(run)) {
            ragCompletion().finish(transaction, run.get("id", String.class), "cancelled");
        }
        if ("video".equals(run.get("workflow", String.class))) {
            WorkflowVideoAdaptationCompletion completion = videoCompletion.get();
            if (completion == null) throw new IllegalStateException("视频耐久任务投影端口未装配");
            completion.finish(transaction, run.get("id", String.class), "cancelled", "RUN_CANCELLED", "运行已取消");
        }
        long sequence = Math.addExact(previousSequence, 1L);
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvent" (
                  id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                ) VALUES (?, ?, ?, 'cancelled', ?, ?, ?)
                """,
                ids.next(),
                run.get("id", String.class),
                sequence,
                canonicalJson(Map.of("cancelRequestId", cancelRequestId)),
                "run:cancelled",
                now);
        transaction.execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('cancelled' AS "WorkflowRunStatus"),
                    "cancelRequestId" = ?, "cancelRequestedAt" = ?, "completedAt" = ?,
                    "errorCode" = 'RUN_CANCELLED', "lastEventSequence" = ?,
                    revision = revision + 1, "updatedAt" = ?
                WHERE id = ? AND status NOT IN ('completed', 'failed', 'cancelled')
                """,
                cancelRequestId,
                requestedAt,
                now,
                sequence,
                now,
                run.get("id", String.class));
    }

    private static boolean isQualityRun(Record run) {
        return "quality".equals(run.get("workflow", String.class))
                && "consistency".equals(run.get("operation", String.class));
    }

    private WorkflowQualityCompletion qualityCompletion() {
        WorkflowQualityCompletion completion = qualityCompletion.get();
        if (completion == null) throw new IllegalStateException("质量取消投影端口未装配");
        return completion;
    }

    private static boolean isStyleRun(Record run) {
        return "style".equals(run.get("workflow", String.class)) && "portrait".equals(run.get("operation", String.class));
    }

    private static boolean isRagRun(Record run) {
        return "rag".equals(run.get("workflow", String.class)) && "embedding".equals(run.get("operation", String.class));
    }

    private WorkflowRagIndexCompletion ragCompletion() {
        WorkflowRagIndexCompletion completion = ragCompletion.get();
        if (completion == null) throw new IllegalStateException("RAG 索引耐久投影端口未装配");
        return completion;
    }

    private WorkflowStylePortraitCompletion styleCompletion() {
        WorkflowStylePortraitCompletion completion = styleCompletion.get();
        if (completion == null) throw new IllegalStateException("画像取消投影端口未装配");
        return completion;
    }

    private long appendStepFinished(
            DSLContext transaction,
            String runId,
            String stepId,
            long fencingToken,
            long previousSequence,
            LocalDateTime now) {
        if (fencingToken < 1) {
            throw new IllegalStateException("已开始的取消 Step 缺少有效 fencingToken");
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("stepId", stepId);
        payload.put("fencingToken", Math.toIntExact(fencingToken));
        payload.put("status", "skipped");
        payload.put("errorCode", null);
        long sequence = Math.addExact(previousSequence, 1L);
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvent" (
                  id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                ) VALUES (?, ?, ?, 'step_finished', ?, ?, ?)
                """,
                ids.next(),
                runId,
                sequence,
                canonicalJson(payload),
                "step:finished:" + stepId + ":" + fencingToken,
                now);
        return sequence;
    }

    private static ExecutionCancelRequest cancelRequest(
            Record run, Record step, String cancelRequestId, LocalDateTime requestedAt) {
        return new ExecutionCancelRequest(
                cancelRequestId,
                Math.toIntExact(step.get("fencingToken", Long.class)),
                step.get("activeJobId", String.class),
                run.get("novelId", String.class),
                "2.0",
                step.get("requestHash", String.class),
                DatabaseTimestamp.api(requestedAt),
                run.get("id", String.class),
                step.get("id", String.class));
    }

    private static ExecutionCancelRequest cancelRequest(Record value) {
        return new ExecutionCancelRequest(
                value.get("cancelRequestId", String.class),
                Math.toIntExact(value.get("fencingToken", Long.class)),
                value.get("activeJobId", String.class),
                value.get("novelId", String.class),
                "2.0",
                value.get("requestHash", String.class),
                DatabaseTimestamp.api(value.get("cancelRequestedAt", LocalDateTime.class)),
                value.get("runId", String.class),
                value.get("stepId", String.class));
    }

    private String canonicalJson(Object value) {
        return new String(ExecutionCanonicalJson.bytes(value), StandardCharsets.UTF_8);
    }

    private static void requireNonBlank(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + " 不能为空");
        }
    }
}
