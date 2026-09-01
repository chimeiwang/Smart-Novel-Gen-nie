package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.api.RunSnapshot;
import cn.inkforge.contracts.api.WorkflowArtifactSnapshot;
import cn.inkforge.contracts.api.WorkflowCurrentStepSnapshot;
import cn.inkforge.contracts.api.WorkflowErrorSnapshot;
import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.contracts.api.WorkflowRunSnapshot;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowStepSnapshotFactory;
import cn.inkforge.core.workflows.protocol.WorkflowEventPayloadCodec;
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

/** PostgreSQL V2 Run snapshot 与 WorkflowEvent 回放实现；Redis 不参与正确性判定。 */
final class JooqWorkflowEventStreamRepository implements WorkflowEventStreamRepository {

    private final CoreDatabase database;
    private final WorkflowEventPayloadCodec payloads;
    private final WorkflowStepSnapshotFactory stepSnapshots;

    JooqWorkflowEventStreamRepository(
            CoreDatabase database,
            WorkflowEventPayloadCodec payloads,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.payloads = Objects.requireNonNull(payloads);
        this.stepSnapshots = new WorkflowStepSnapshotFactory(json);
    }

    @Override
    public Optional<SnapshotRead> readSnapshot(String userId, String runId) {
        return database.transactionResult(transaction -> {
            // snapshot、baseSequence 及所有关联投影共享同一个 PostgreSQL 快照。
            transaction.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY");
            Record run = transaction.fetchOne(
                    """
                    SELECT id, "userId", workflow, operation,
                           "operationCatalogVersion", "modelPolicyJson",
                           status::text AS status,
                           "cancelRequestedAt", "lastEventSequence", revision, "errorCode"
                    FROM public."WorkflowRun"
                    WHERE id = ? AND "engineVersion" = 2
                    """,
                    runId);
            if (run == null) return Optional.empty();
            if (!Objects.equals(userId, run.get("userId", String.class))) throw forbidden();

            long baseSequence = requiredNonNegative(
                    run.get("lastEventSequence", Long.class), "WorkflowRun lastEventSequence");
            long durableMaximum = transaction.fetchOne(
                            """
                            SELECT COALESCE(MAX(sequence), 0) AS maximum
                            FROM public."WorkflowEvent" WHERE "runId" = ?
                            """,
                            runId)
                    .get("maximum", Long.class);
            if (durableMaximum != baseSequence) {
                throw new IllegalStateException("WorkflowRun 与 WorkflowEvent 序号不一致");
            }

            WorkflowRunSnapshot snapshot = snapshot(transaction, run, baseSequence);
            RunSnapshot frame = new RunSnapshot(
                    Math.toIntExact(baseSequence), 2, "2.0", runId, snapshot);
            return Optional.of(new SnapshotRead(frame));
        });
    }

    @Override
    public Map<RunKey, TailState> readTails(List<RunKey> runs) {
        if (runs == null || runs.isEmpty()) return Map.of();
        if (runs.size() > 1_000 || runs.stream().distinct().count() != runs.size()) {
            throw new IllegalArgumentException("Workflow SSE 批量观察范围无效");
        }
        String values = String.join(", ", java.util.Collections.nCopies(
                runs.size(), "(CAST(? AS text), CAST(? AS text))"));
        List<Object> bindings = new ArrayList<>(runs.size() * 2);
        runs.forEach(run -> {
            bindings.add(run.userId());
            bindings.add(run.runId());
        });
        Map<RunKey, TailState> result = new LinkedHashMap<>();
        database.dsl()
                .fetch(
                        """
                        WITH requested(user_id, run_id) AS (VALUES %s)
                        SELECT requested.user_id AS requested_user_id,
                               requested.run_id AS requested_run_id,
                               run.status::text AS status,
                               run."lastEventSequence" AS last_event_sequence
                        FROM requested
                        JOIN public."WorkflowRun" AS run
                          ON run.id = requested.run_id
                         AND run."userId" = requested.user_id
                         AND run."engineVersion" = 2
                        ORDER BY requested.run_id, requested.user_id
                        """
                                .formatted(values),
                        bindings.toArray())
                .forEach(run -> {
                    RunKey key = new RunKey(
                            run.get("requested_user_id", String.class),
                            run.get("requested_run_id", String.class));
                    result.put(
                            key,
                            new TailState(
                                    run.get("status", String.class),
                                    requiredNonNegative(
                                            run.get("last_event_sequence", Long.class),
                                            "WorkflowRun lastEventSequence")));
                });
        return Map.copyOf(result);
    }

    @Override
    public Map<RunKey, List<WorkflowEventEnvelope>> readEventTails(
            List<EventTailRequest> requests, int limitPerRun) {
        if (requests == null || requests.isEmpty()) return Map.of();
        if (requests.size() > 1_000
                || requests.stream().map(EventTailRequest::key).distinct().count()
                        != requests.size()
                || limitPerRun < 1
                || limitPerRun > 1_000) {
            throw new IllegalArgumentException("WorkflowEvent 批量回放范围无效");
        }
        String values = String.join(", ", java.util.Collections.nCopies(
                requests.size(),
                "(CAST(? AS text), CAST(? AS text), CAST(? AS bigint), CAST(? AS bigint))"));
        List<Object> bindings = new ArrayList<>(requests.size() * 4 + 1);
        Map<RunKey, List<WorkflowEventEnvelope>> result = new LinkedHashMap<>();
        requests.forEach(request -> {
            bindings.add(request.key().userId());
            bindings.add(request.key().runId());
            bindings.add(request.afterSequence());
            bindings.add(request.throughSequence());
            result.put(request.key(), new ArrayList<>());
        });
        bindings.add(limitPerRun);
        database.dsl()
                .fetch(
                        """
                        WITH requested(user_id, run_id, after_sequence, through_sequence) AS (
                          VALUES %s
                        ), ranked AS (
                          SELECT requested.user_id AS requested_user_id,
                                 requested.run_id AS requested_run_id,
                                 event.sequence,
                                 event."eventType",
                                 event."payloadJson",
                                 event."createdAt",
                                 ROW_NUMBER() OVER (
                                   PARTITION BY requested.user_id, requested.run_id
                                   ORDER BY event.sequence ASC
                                 ) AS event_rank
                          FROM requested
                          JOIN public."WorkflowRun" AS run
                            ON run.id = requested.run_id
                           AND run."userId" = requested.user_id
                           AND run."engineVersion" = 2
                          JOIN public."WorkflowEvent" AS event
                            ON event."runId" = requested.run_id
                           AND event.sequence > requested.after_sequence
                           AND event.sequence <= requested.through_sequence
                        )
                        SELECT requested_user_id, requested_run_id, sequence,
                               "eventType", "payloadJson", "createdAt"
                        FROM ranked
                        WHERE event_rank <= ?
                        ORDER BY requested_run_id, requested_user_id, sequence ASC
                        """
                                .formatted(values),
                        bindings.toArray())
                .forEach(event -> {
                    RunKey key = new RunKey(
                            event.get("requested_user_id", String.class),
                            event.get("requested_run_id", String.class));
                    result.get(key).add(envelope(key.runId(), event));
                });
        result.replaceAll((ignored, events) -> List.copyOf(events));
        return Map.copyOf(result);
    }

    public List<WorkflowEventEnvelope> readAfter(
            String userId, String runId, long afterSequence, int limit) {
        if (afterSequence < 0 || limit < 1 || limit > 1_000) {
            throw new IllegalArgumentException("WorkflowEvent 回放范围无效");
        }
        List<WorkflowEventEnvelope> result = new ArrayList<>();
        database.dsl()
                .fetch(
                        """
                        SELECT event.sequence, event."eventType", event."payloadJson", event."createdAt"
                        FROM public."WorkflowEvent" AS event
                        JOIN public."WorkflowRun" AS run ON run.id = event."runId"
                        WHERE event."runId" = ? AND event.sequence > ?
                          AND run."engineVersion" = 2 AND run."userId" = ?
                        ORDER BY event.sequence ASC
                        LIMIT ?
                        """,
                        runId,
                        afterSequence,
                        userId,
                        limit)
                .forEach(event -> result.add(envelope(runId, event)));
        return List.copyOf(result);
    }

    public TailState readTail(String userId, String runId) {
        Record run = database.dsl().fetchOne(
                """
                SELECT status::text AS status, "lastEventSequence"
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2 AND "userId" = ?
                """,
                runId,
                userId);
        if (run == null) throw forbidden();
        return new TailState(
                run.get("status", String.class),
                requiredNonNegative(
                        run.get("lastEventSequence", Long.class),
                        "WorkflowRun lastEventSequence"));
    }

    private WorkflowRunSnapshot snapshot(
            DSLContext transaction, Record run, long baseSequence) {
        String runId = run.get("id", String.class);
        String status = run.get("status", String.class);
        LocalDateTime cancelRequestedAt = run.get("cancelRequestedAt", LocalDateTime.class);
        if ("cancelled".equals(status) && cancelRequestedAt == null) {
            throw new IllegalStateException("cancelled WorkflowRun 缺少取消时间");
        }
        if (cancelRequestedAt != null
                && !"running".equals(status)
                && !"cancelled".equals(status)) {
            throw new IllegalStateException("WorkflowRun 取消时间与生命周期不一致");
        }

        List<Record> activeStepRecords = transaction.fetch(
                """
                WITH active_steps AS (
                  SELECT step.id, step."runId", step.ordinal, step.purpose, step.lane,
                         step.status::text AS status, step."attemptCount",
                         step."fencingToken", step."errorCode", step."modelProfile",
                         step."modelProfileVersion", step."resolvedModelJson"
                  FROM public."WorkflowStep" AS step
                  WHERE step."runId" = ? AND step.ordinal IS NOT NULL
                    AND step.status::text IN ('pending', 'running')
                ), latest_progress AS (
                  SELECT DISTINCT ON (event."runId", event."payloadJson"::jsonb ->> 'stepId')
                         event."runId", event."payloadJson"::jsonb ->> 'stepId' AS step_id,
                         event."payloadJson" AS latest_progress_json
                  FROM public."WorkflowEvent" AS event
                  JOIN active_steps AS step
                    ON step."runId" = event."runId"
                   AND step.id = event."payloadJson"::jsonb ->> 'stepId'
                  WHERE event."eventType" = 'step_progress'
                  ORDER BY event."runId", event."payloadJson"::jsonb ->> 'stepId',
                           event.sequence DESC
                )
                SELECT step.*, progress.latest_progress_json
                FROM active_steps AS step
                LEFT JOIN latest_progress AS progress
                  ON progress."runId" = step."runId" AND progress.step_id = step.id
                ORDER BY step.ordinal ASC, step.id ASC
                """,
                runId);
        ExecutionPlanSnapshot executionPlan = activeStepRecords.isEmpty()
                ? null
                : stepSnapshots.executionPlan(run.get("modelPolicyJson", String.class));
        if (executionPlan != null) {
            executionPlan.requireOperation(
                    run.get("workflow", String.class),
                    run.get("operation", String.class),
                    run.get("operationCatalogVersion", String.class));
        }
        List<WorkflowCurrentStepSnapshot> activeSteps = activeStepRecords.stream()
                .map(value -> stepSnapshot(executionPlan, value))
                .toList();
        if (!activeSteps.isEmpty() && !List.of("pending", "running").contains(status)) {
            throw new IllegalStateException("非执行中 WorkflowRun 含活动 Step");
        }
        WorkflowCurrentStepSnapshot step = activeSteps.isEmpty()
                ? null
                : activeSteps.getFirst();

        Record artifactRecord = transaction.fetchOne(
                """
                SELECT id, revision, status::text AS status
                FROM public."ReviewArtifact"
                WHERE "workflowRunId" = ?
                ORDER BY "updatedAt" DESC, id DESC
                LIMIT 1
                """,
                runId);
        WorkflowArtifactSnapshot artifact = artifactRecord == null
                ? null
                : artifact(transaction, runId, status, cancelRequestedAt, artifactRecord);

        WorkflowErrorSnapshot error = null;
        String errorCode = run.get("errorCode", String.class);
        if ("failed".equals(status)) {
            if (errorCode == null || errorCode.isBlank()) {
                throw new IllegalStateException("failed WorkflowRun 缺少错误码");
            }
            Record failed = transaction.fetchOne(
                    """
                    SELECT id FROM public."WorkflowStep"
                    WHERE "runId" = ? AND ordinal IS NOT NULL AND status::text = 'failed'
                    ORDER BY ordinal DESC, id DESC LIMIT 1
                    """,
                    runId);
            error = new WorkflowErrorSnapshot(
                            errorCode, "MODEL_OUTCOME_UNKNOWN".equals(errorCode))
                    .failedStepId(failed == null ? null : failed.get("id", String.class));
        }

        Integer revision = run.get("revision", Integer.class);
        if (revision == null || revision < 1) {
            throw new IllegalStateException("WorkflowRun revision 无效");
        }
        return new WorkflowRunSnapshot(
                        activeSteps,
                        Math.toIntExact(baseSequence),
                        revision,
                        WorkflowRunSnapshot.StatusEnum.fromValue(status),
                        run.get("workflow", String.class))
                .operation(run.get("operation", String.class))
                .currentStep(step)
                .cancelRequestedAt(DatabaseTimestamp.api(cancelRequestedAt))
                .artifact(artifact)
                .error(error);
    }

    private WorkflowCurrentStepSnapshot stepSnapshot(
            ExecutionPlanSnapshot executionPlan, Record value) {
        String lane = value.get("lane", String.class);
        if ("control".equals(lane)) {
            return stepSnapshots.controlStep(
                    value.get("id", String.class),
                    value.get("ordinal", Integer.class),
                    value.get("purpose", String.class),
                    value.get("status", String.class),
                    value.get("attemptCount", Integer.class),
                    value.get("fencingToken", Long.class),
                    value.get("errorCode", String.class));
        }
        if (executionPlan == null) throw new IllegalStateException("模型 Step 缺少冻结执行计划");
        return stepSnapshots.modelStep(
                executionPlan,
                value.get("id", String.class),
                value.get("ordinal", Integer.class),
                value.get("purpose", String.class),
                lane,
                value.get("status", String.class),
                value.get("attemptCount", Integer.class),
                value.get("fencingToken", Long.class),
                value.get("errorCode", String.class),
                value.get("modelProfile", String.class),
                Integer.parseInt(value.get("modelProfileVersion", String.class)),
                value.get("resolvedModelJson", String.class),
                value.get("latest_progress_json", String.class));
    }

    private static WorkflowArtifactSnapshot artifact(
            DSLContext transaction,
            String runId,
            String runStatus,
            LocalDateTime cancelRequestedAt,
            Record value) {
        String artifactId = value.get("id", String.class);
        int artifactRevision = value.get("revision", Integer.class);
        String artifactStatus = value.get("status", String.class);
        boolean actionable = "waiting_user".equals(runStatus)
                && cancelRequestedAt == null
                && "awaiting_user".equals(artifactStatus);
        WorkflowArtifactSnapshot result = new WorkflowArtifactSnapshot(
                actionable,
                artifactId,
                artifactRevision,
                WorkflowArtifactSnapshot.StatusEnum.fromValue(artifactStatus));
        Record evaluations = transaction.fetchOne(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE "executionStatus" = 'completed') AS completed
                FROM public."WorkflowEvaluation"
                WHERE "runId" = ? AND "artifactId" = ? AND "artifactRevision" = ?
                """,
                runId,
                artifactId,
                artifactRevision);
        long total = evaluations.get("total", Long.class);
        long completed = evaluations.get("completed", Long.class);
        if (total > 0) {
            String availability = completed == 0
                    ? "unavailable"
                    : completed == total ? "complete" : "partial";
            result.setReviewAvailability(
                    WorkflowArtifactSnapshot.ReviewAvailabilityEnum.fromValue(availability));
        }
        return result;
    }

    private WorkflowEventEnvelope envelope(String runId, Record event) {
        long sequence = event.get("sequence", Long.class);
        if (sequence < 1) throw new IllegalStateException("WorkflowEvent sequence 无效");
        String eventType = event.get("eventType", String.class);
        Object payload = payloads.parse(eventType, event.get("payloadJson", String.class));
        return new WorkflowEventEnvelope(
                2,
                WorkflowEventEnvelope.EventTypeEnum.fromValue(eventType),
                DatabaseTimestamp.api(event.get("createdAt", LocalDateTime.class)),
                payload,
                "2.0",
                runId,
                Math.toIntExact(sequence));
    }

    private static long requiredNonNegative(Long value, String field) {
        if (value == null || value < 0) throw new IllegalStateException(field + " 无效");
        return value;
    }

    private static ApiException forbidden() {
        return new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
    }
}
