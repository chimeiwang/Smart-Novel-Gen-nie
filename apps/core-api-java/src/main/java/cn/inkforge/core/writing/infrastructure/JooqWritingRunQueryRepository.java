package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.contracts.api.WorkflowArtifactSnapshot;
import cn.inkforge.contracts.api.WorkflowCurrentStepSnapshot;
import cn.inkforge.contracts.api.WorkflowErrorSnapshot;
import cn.inkforge.contracts.api.WritingRunListItem;
import cn.inkforge.contracts.api.WritingRunListResponse;
import cn.inkforge.contracts.api.WritingRunPublicListItem;
import cn.inkforge.contracts.api.WritingRunStatusPublicResponse;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowStepSnapshotFactory;
import cn.inkforge.core.writing.application.WritingRunQueryRepository;
import cn.inkforge.core.writing.domain.WritingRunCursor;
import cn.inkforge.core.writing.domain.WritingRunStatusProjector;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.databind.ObjectMapper;

/** 使用批量关联读取避免 N+1，并在内存中应用依赖统一结果投影的过滤条件。 */
final class JooqWritingRunQueryRepository implements WritingRunQueryRepository {

    private static final int SCAN_BATCH_SIZE = 200;
    private static final Set<String> OPERATIONS = Set.of(
            "generate_outline",
            "generate_manuscript",
            "replace_selection",
            "full_check",
            "plan_chapter",
            "rewrite_scene",
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
            "write_chapter",
            "review_chapter");
    private static final Set<String> OUTCOMES = Set.of(
            "queued", "running", "waiting_user", "succeeded", "failed", "cancelled", "inconsistent");

    private final CoreDatabase database;
    private final WritingRunStatusProjector projector;
    private final WritingRunCursor cursors;
    private final WorkflowStepSnapshotFactory stepSnapshots;
    private final boolean durableAgentSchemaReady;

    JooqWritingRunQueryRepository(
            CoreDatabase database,
            WritingRunStatusProjector projector,
            WritingRunCursor cursors,
            ObjectMapper json) {
        this(database, projector, cursors, json, false);
    }

    JooqWritingRunQueryRepository(
            CoreDatabase database,
            WritingRunStatusProjector projector,
            WritingRunCursor cursors,
            ObjectMapper json,
            boolean durableAgentSchemaReady) {
        this.database = Objects.requireNonNull(database);
        this.projector = Objects.requireNonNull(projector);
        this.cursors = Objects.requireNonNull(cursors);
        this.stepSnapshots = new WorkflowStepSnapshotFactory(json);
        this.durableAgentSchemaReady = durableAgentSchemaReady;
    }

    @Override
    public WritingRunStatusResponse get(String userId, String taskId) {
        DSLContext context = database.dsl();
        WritingtaskRecord task = context.select(WRITINGTASK.fields())
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId), NOVEL.USERID.eq(userId))
                .fetchOneInto(WritingtaskRecord.class);
        if (task == null) {
            throw new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
        }
        return v1(projector.project(
                task,
                commands(context, List.of(taskId)),
                artifacts(context, List.of(taskId))));
    }

    @Override
    public WritingRunStatusPublicResponse getPublic(String userId, String taskId) {
        if (!durableAgentSchemaReady) return get(userId, taskId);
        return database.transactionResult(context -> {
            // 引擎身份来自持久化记录；V2 存在但归属不符时禁止回退到同 ID 的 V1。
            V2Run run = v2Run(context, taskId);
            if (run == null) return get(userId, taskId);
            if (!userId.equals(run.userId())) {
                throw forbidden();
            }
            V2Related related = v2Related(context, List.of(taskId));
            return v2Response(
                    run,
                    related.activeSteps().getOrDefault(taskId, List.of()),
                    related.failedSteps().get(taskId),
                    related.artifacts().get(taskId));
        });
    }

    @Override
    public WritingRunListResponse list(
            String userId,
            String novelId,
            String chapterId,
            String writingSessionId,
            String operation,
            String outcome,
            String cursor,
            int limit) {
        if (operation != null && !OPERATIONS.contains(operation)) {
            throw new ApiException(422, "VALIDATION_ERROR", "任务 operation 过滤值无效");
        }
        if (outcome != null && !OUTCOMES.contains(outcome)) {
            throw new ApiException(422, "VALIDATION_ERROR", "任务 outcome 过滤值无效");
        }
        WritingRunCursor.Position initial = decode(cursor);
        WritingRunCursor.Position scan = initial;
        List<ProjectedItem> matched = new ArrayList<>();
        DSLContext context = database.dsl();
        while (matched.size() < limit + 1) {
            List<RunCandidate> candidates = candidates(
                    context,
                    userId,
                    novelId,
                    chapterId,
                    writingSessionId,
                    scan,
                    durableAgentSchemaReady);
            if (candidates.isEmpty()) break;
            List<String> taskIds = candidates.stream()
                    .filter(candidate -> candidate.engineVersion() == 1)
                    .map(RunCandidate::id)
                    .toList();
            List<String> runIds = candidates.stream()
                    .filter(candidate -> candidate.engineVersion() == 2)
                    .map(RunCandidate::id)
                    .toList();
            Map<String, WritingtaskRecord> tasks = taskIds.isEmpty()
                    ? Map.of()
                    : context.selectFrom(WRITINGTASK)
                            .where(WRITINGTASK.ID.in(taskIds))
                            .fetchMap(WRITINGTASK.ID);
            Map<String, List<WritingruncommandRecord>> commands = groupCommands(
                    commands(context, taskIds));
            Map<String, List<ReviewartifactRecord>> artifacts = groupArtifacts(
                    artifacts(context, taskIds));
            Map<String, V2Run> runs = v2Runs(context, runIds);
            V2Related related = v2Related(context, runIds);
            for (RunCandidate candidate : candidates) {
                WritingRunPublicListItem item;
                if (candidate.engineVersion() == 1) {
                    WritingtaskRecord task = tasks.get(candidate.id());
                    if (task == null) throw new IllegalStateException("V1 写作任务候选已消失");
                    WritingRunStatusResponse status = v1(projector.project(
                            task,
                            commands.getOrDefault(task.getId(), List.of()),
                            artifacts.getOrDefault(task.getId(), List.of())));
                    String statusOperation = status.getOperation() == null
                            ? null
                            : status.getOperation().getValue();
                    if (operation != null && !operation.equals(statusOperation)) continue;
                    if (outcome != null
                            && !outcome.equals(status.getOutcome().getState().getValue())) {
                        continue;
                    }
                    item = listItem(status);
                } else {
                    V2Run run = runs.get(candidate.id());
                    if (run == null) throw new IllegalStateException("V2 WorkflowRun 候选已消失");
                    WritingRunV2Response response = v2Response(
                            run,
                            related.activeSteps().getOrDefault(run.id(), List.of()),
                            related.failedSteps().get(run.id()),
                            related.artifacts().get(run.id()));
                    if (operation != null && !operation.equals(response.getOperation())) continue;
                    if (outcome != null && !outcome.equals(v2Outcome(response.getStatus()))) {
                        continue;
                    }
                    item = response;
                }
                matched.add(new ProjectedItem(
                        item,
                        DatabaseTimestamp.api(candidate.createdAt()),
                        candidate.id()));
                if (matched.size() == limit + 1) break;
            }
            RunCandidate last = candidates.getLast();
            scan = new WritingRunCursor.Position(
                    DatabaseTimestamp.api(last.createdAt()), last.id());
            if (candidates.size() < SCAN_BATCH_SIZE) break;
        }
        List<WritingRunPublicListItem> page = matched.size() <= limit
                ? matched.stream().map(ProjectedItem::item).toList()
                : matched.subList(0, limit).stream().map(ProjectedItem::item).toList();
        String next = matched.size() > limit && !page.isEmpty()
                ? cursors.encode(
                        matched.get(limit - 1).createdAt(),
                        matched.get(limit - 1).id())
                : null;
        return new WritingRunListResponse(page, next);
    }

    private static List<RunCandidate> candidates(
            DSLContext context,
            String userId,
            String novelId,
            String chapterId,
            String writingSessionId,
            WritingRunCursor.Position cursor,
            boolean durableAgentSchemaReady) {
        LocalDateTime cursorTime = cursor == null
                ? null
                : DatabaseTimestamp.database(cursor.createdAt());
        String cursorId = cursor == null ? null : cursor.taskId();
        if (!durableAgentSchemaReady) {
            return context.fetch(
                            """
                            SELECT task.id, 1 AS engine_version, task."createdAt" AS created_at
                            FROM public."WritingTask" AS task
                            JOIN public."Novel" AS novel ON novel.id = task."novelId"
                            WHERE novel."userId" = ? AND task."novelId" = ?
                              AND (CAST(? AS text) IS NULL OR task."chapterId" = ?)
                              AND (CAST(? AS text) IS NULL OR task."writingSessionId" = ?)
                              AND (
                                CAST(? AS timestamp) IS NULL
                                OR task."createdAt" < CAST(? AS timestamp)
                                OR (task."createdAt" = CAST(? AS timestamp) AND task.id < ?)
                              )
                            ORDER BY task."createdAt" DESC, task.id DESC
                            LIMIT ?
                            """,
                            userId,
                            novelId,
                            chapterId,
                            chapterId,
                            writingSessionId,
                            writingSessionId,
                            cursorTime,
                            cursorTime,
                            cursorTime,
                            cursorId,
                            SCAN_BATCH_SIZE)
                    .map(record -> new RunCandidate(
                            record.get("id", String.class),
                            record.get("engine_version", Integer.class),
                            record.get("created_at", LocalDateTime.class)));
        }
        return context.fetch(
                        """
                        SELECT candidate.id, candidate.engine_version, candidate.created_at
                        FROM (
                          SELECT task.id, 1 AS engine_version, task."createdAt" AS created_at
                          FROM public."WritingTask" AS task
                          JOIN public."Novel" AS novel ON novel.id = task."novelId"
                          WHERE novel."userId" = ? AND task."novelId" = ?
                            AND NOT EXISTS (
                              SELECT 1 FROM public."WorkflowRun" AS identity_run
                              WHERE identity_run.id = task.id
                                AND identity_run."engineVersion" = 2
                            )
                            AND (CAST(? AS text) IS NULL OR task."chapterId" = ?)
                            AND (CAST(? AS text) IS NULL OR task."writingSessionId" = ?)
                          UNION ALL
                          SELECT run.id, 2 AS engine_version, run."createdAt" AS created_at
                          FROM public."WorkflowRun" AS run
                          WHERE run."engineVersion" = 2
                            AND run."userId" = ? AND run."novelId" = ?
                            AND (CAST(? AS text) IS NULL OR run."chapterId" = ?)
                            AND (CAST(? AS text) IS NULL OR run."writingSessionId" = ?)
                        ) AS candidate
                        WHERE CAST(? AS timestamp) IS NULL
                           OR candidate.created_at < CAST(? AS timestamp)
                           OR (candidate.created_at = CAST(? AS timestamp) AND candidate.id < ?)
                        ORDER BY candidate.created_at DESC, candidate.id DESC
                        LIMIT ?
                        """,
                        userId,
                        novelId,
                        chapterId,
                        chapterId,
                        writingSessionId,
                        writingSessionId,
                        userId,
                        novelId,
                        chapterId,
                        chapterId,
                        writingSessionId,
                        writingSessionId,
                        cursorTime,
                        cursorTime,
                        cursorTime,
                        cursorId,
                        SCAN_BATCH_SIZE)
                .map(record -> new RunCandidate(
                        record.get("id", String.class),
                        record.get("engine_version", Integer.class),
                        record.get("created_at", LocalDateTime.class)));
    }

    private WritingRunCursor.Position decode(String cursor) {
        if (cursor == null) return null;
        try {
            return cursors.decode(cursor);
        } catch (IllegalArgumentException exception) {
            throw new ApiException(422, "WRITING_RUN_CURSOR_INVALID", "任务游标无效");
        }
    }

    private static List<WritingruncommandRecord> commands(
            DSLContext context, List<String> taskIds) {
        if (taskIds.isEmpty()) return List.of();
        return context.selectFrom(WRITINGRUNCOMMAND)
                .where(WRITINGRUNCOMMAND.TASKID.in(taskIds))
                .orderBy(
                        WRITINGRUNCOMMAND.TASKID.asc(),
                        WRITINGRUNCOMMAND.CREATEDAT.desc(),
                        WRITINGRUNCOMMAND.ID.desc())
                .fetch();
    }

    private static List<ReviewartifactRecord> artifacts(
            DSLContext context, List<String> taskIds) {
        if (taskIds.isEmpty()) return List.of();
        return context.selectFrom(REVIEWARTIFACT)
                .where(REVIEWARTIFACT.TASKID.in(taskIds))
                .orderBy(
                        REVIEWARTIFACT.TASKID.asc(),
                        REVIEWARTIFACT.CREATEDAT.desc(),
                        REVIEWARTIFACT.ID.desc())
                .fetch();
    }

    private static Map<String, List<WritingruncommandRecord>> groupCommands(
            List<WritingruncommandRecord> values) {
        Map<String, List<WritingruncommandRecord>> result = new LinkedHashMap<>();
        for (WritingruncommandRecord value : values) {
            result.computeIfAbsent(value.getTaskid(), ignored -> new ArrayList<>()).add(value);
        }
        return result;
    }

    private static Map<String, List<ReviewartifactRecord>> groupArtifacts(
            List<ReviewartifactRecord> values) {
        Map<String, List<ReviewartifactRecord>> result = new LinkedHashMap<>();
        for (ReviewartifactRecord value : values) {
            if (value.getTaskid() != null) {
                result.computeIfAbsent(value.getTaskid(), ignored -> new ArrayList<>()).add(value);
            }
        }
        return result;
    }

    private static V2Run v2Run(DSLContext context, String runId) {
        Record value = context.fetchOne(
                """
                SELECT id, "userId", "chapterId", workflow, operation,
                       "operationCatalogVersion", "modelPolicyJson", status::text AS status,
                       "cancelRequestedAt", "lastEventSequence", revision, "errorCode"
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2
                """,
                runId);
        return value == null ? null : v2Run(value);
    }

    private static Map<String, V2Run> v2Runs(
            DSLContext context, List<String> runIds) {
        if (runIds.isEmpty()) return Map.of();
        Map<String, V2Run> result = new LinkedHashMap<>();
        context.fetch(
                        """
                        SELECT id, "userId", "chapterId", workflow, operation,
                               "operationCatalogVersion", "modelPolicyJson",
                               status::text AS status, "cancelRequestedAt",
                               "lastEventSequence", revision, "errorCode"
                        FROM public."WorkflowRun"
                        WHERE "engineVersion" = 2 AND id IN (%s)
                        """.formatted(placeholders(runIds.size())),
                        runIds.toArray())
                .forEach(value -> {
                    V2Run run = v2Run(value);
                    result.put(run.id(), run);
                });
        return result;
    }

    private static V2Run v2Run(Record value) {
        return new V2Run(
                value.get("id", String.class),
                value.get("userId", String.class),
                value.get("chapterId", String.class),
                value.get("workflow", String.class),
                value.get("operation", String.class),
                value.get("operationCatalogVersion", String.class),
                value.get("modelPolicyJson", String.class),
                value.get("status", String.class),
                value.get("cancelRequestedAt", LocalDateTime.class),
                value.get("lastEventSequence", Long.class),
                value.get("revision", Integer.class),
                value.get("errorCode", String.class));
    }

    private static V2Related v2Related(
            DSLContext context, List<String> runIds) {
        if (runIds.isEmpty()) return V2Related.empty();
        String placeholders = placeholders(runIds.size());
        Map<String, List<V2Step>> activeSteps = new LinkedHashMap<>();
        Map<String, V2Step> failedSteps = new LinkedHashMap<>();
        context.fetch(
                """
                        WITH selected_steps AS (
                          SELECT step.id, step."runId", step.ordinal, step.purpose, step.lane,
                                 step.status::text AS status, step."attemptCount",
                                 step."fencingToken", step."errorCode", step."modelProfile",
                                 step."modelProfileVersion", step."resolvedModelJson"
                          FROM public."WorkflowStep" AS step
                          WHERE step.ordinal IS NOT NULL AND step."runId" IN (%s)
                        ), latest_progress AS (
                          SELECT DISTINCT ON (
                                   event."runId", event."payloadJson"::jsonb ->> 'stepId')
                                 event."runId",
                                 event."payloadJson"::jsonb ->> 'stepId' AS step_id,
                                 event."payloadJson" AS latest_progress_json
                          FROM public."WorkflowEvent" AS event
                          JOIN selected_steps AS step
                            ON step."runId" = event."runId"
                           AND step.id = event."payloadJson"::jsonb ->> 'stepId'
                          WHERE event."eventType" = 'step_progress'
                          ORDER BY event."runId", event."payloadJson"::jsonb ->> 'stepId',
                                   event.sequence DESC
                        )
                        SELECT step.*, progress.latest_progress_json
                        FROM selected_steps AS step
                        LEFT JOIN latest_progress AS progress
                          ON progress."runId" = step."runId" AND progress.step_id = step.id
                        ORDER BY step."runId", step.ordinal ASC, step.id ASC
                        """.formatted(placeholders),
                        runIds.toArray())
                .forEach(value -> {
                    V2Step step = new V2Step(
                            value.get("id", String.class),
                            value.get("runId", String.class),
                            value.get("ordinal", Integer.class),
                            value.get("purpose", String.class),
                            value.get("lane", String.class),
                            value.get("status", String.class),
                            value.get("attemptCount", Integer.class),
                            value.get("fencingToken", Long.class),
                            value.get("errorCode", String.class),
                            value.get("modelProfile", String.class),
                            value.get("modelProfileVersion", String.class),
                            value.get("resolvedModelJson", String.class),
                            value.get("latest_progress_json", String.class));
                    if (List.of("pending", "running").contains(step.status())) {
                        activeSteps.computeIfAbsent(step.runId(), ignored -> new ArrayList<>())
                                .add(step);
                    }
                    if ("failed".equals(step.status())) {
                        failedSteps.put(step.runId(), step);
                    }
                });
        Map<String, V2Artifact> artifacts = new LinkedHashMap<>();
        context.fetch(
                        """
                        SELECT id, "workflowRunId", status::text AS status, revision
                        FROM public."ReviewArtifact"
                        WHERE "workflowRunId" IN (%s)
                        ORDER BY "workflowRunId", "updatedAt" DESC, id DESC
                        """.formatted(placeholders),
                        runIds.toArray())
                .forEach(value -> {
                    V2Artifact artifact = new V2Artifact(
                            value.get("id", String.class),
                            value.get("workflowRunId", String.class),
                            value.get("status", String.class),
                            value.get("revision", Integer.class));
                    artifacts.putIfAbsent(artifact.runId(), artifact);
                });
        activeSteps.replaceAll((ignored, values) -> List.copyOf(values));
        return new V2Related(activeSteps, failedSteps, artifacts);
    }

    private WritingRunV2Response v2Response(
            V2Run run,
            List<V2Step> activeStepValues,
            V2Step failedStep,
            V2Artifact artifact) {
        boolean cancelRequested = run.cancelRequestedAt() != null;
        if ("cancelled".equals(run.status()) && !cancelRequested) {
            throw new IllegalStateException("cancelled V2 WorkflowRun 缺少取消时间");
        }
        if (cancelRequested
                && !"running".equals(run.status())
                && !"cancelled".equals(run.status())) {
            throw new IllegalStateException("V2 WorkflowRun 取消时间与生命周期不一致");
        }
        ExecutionPlanSnapshot executionPlan = activeStepValues.isEmpty()
                ? null
                : stepSnapshots.executionPlan(run.modelPolicyJson());
        if (executionPlan != null) {
            executionPlan.requireOperation(
                    run.workflow(), run.operation(), run.operationCatalogVersion());
        }
        List<WorkflowCurrentStepSnapshot> activeSteps = activeStepValues.stream()
                .map(value -> stepSnapshot(executionPlan, value))
                .toList();
        if (!activeSteps.isEmpty() && !List.of("pending", "running").contains(run.status())) {
            throw new IllegalStateException("非执行中 V2 WorkflowRun 含活动 Step");
        }
        WorkflowCurrentStepSnapshot current = activeSteps.isEmpty()
                ? null
                : activeSteps.getFirst();
        WorkflowArtifactSnapshot artifactSnapshot = artifact == null
                ? null
                : new WorkflowArtifactSnapshot(
                        "waiting_user".equals(run.status())
                                && run.cancelRequestedAt() == null
                                && "awaiting_user".equals(artifact.status()),
                        artifact.id(),
                        artifact.revision(),
                        WorkflowArtifactSnapshot.StatusEnum.fromValue(artifact.status()));
        WorkflowErrorSnapshot error = null;
        if ("failed".equals(run.status())) {
            String errorCode = run.errorCode();
            if (errorCode == null) {
                throw new IllegalStateException("failed V2 WorkflowRun 缺少持久错误码");
            }
            error = new WorkflowErrorSnapshot(
                            errorCode,
                            "MODEL_OUTCOME_UNKNOWN".equals(errorCode))
                    .failedStepId(failedStep == null ? null : failedStep.id());
        }
        return new WritingRunV2Response(
                        activeSteps,
                        run.chapterId(),
                        null,
                        null,
                        2,
                        Math.toIntExact(run.lastEventSequence()),
                        run.revision(),
                        run.id(),
                        WritingRunV2Response.StatusEnum.fromValue(run.status()),
                        run.id(),
                        run.workflow())
                .operation(run.operation())
                .currentStep(current)
                .cancelRequestedAt(DatabaseTimestamp.api(run.cancelRequestedAt()))
                .artifact(artifactSnapshot)
                .error(error);
    }

    private WorkflowCurrentStepSnapshot stepSnapshot(
            ExecutionPlanSnapshot executionPlan, V2Step value) {
        if ("control".equals(value.lane())) {
            return stepSnapshots.controlStep(
                    value.id(),
                    value.ordinal(),
                    value.purpose(),
                    value.status(),
                    value.attemptCount(),
                    value.fencingToken(),
                    value.errorCode());
        }
        if (executionPlan == null) throw new IllegalStateException("模型 Step 缺少冻结执行计划");
        return stepSnapshots.modelStep(
                executionPlan,
                value.id(),
                value.ordinal(),
                value.purpose(),
                value.lane(),
                value.status(),
                value.attemptCount(),
                value.fencingToken(),
                value.errorCode(),
                value.modelProfile(),
                Integer.parseInt(value.modelProfileVersion()),
                value.resolvedModelJson(),
                value.latestProgressJson());
    }

    private static String v2Outcome(WritingRunV2Response.StatusEnum status) {
        return switch (status) {
            case PENDING -> "queued";
            case RUNNING -> "running";
            case WAITING_USER -> "waiting_user";
            case COMPLETED -> "succeeded";
            case FAILED -> "failed";
            case CANCELLED -> "cancelled";
        };
    }

    private static String placeholders(int size) {
        return String.join(", ", java.util.Collections.nCopies(size, "?"));
    }

    private static ApiException forbidden() {
        return new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
    }

    private static WritingRunListItem listItem(WritingRunStatusResponse status) {
        if (status.getCreatedAt() == null || status.getTarget() == null || status.getScope() == null) {
            throw new IllegalStateException("统一任务投影缺少列表必需字段");
        }
        return new WritingRunListItem(
                status.getActiveArtifactId(),
                status.getChapterId(),
                status.getCreatedAt(),
                1,
                status.getNovelId(),
                status.getOperation() == null ? null : status.getOperation().getValue(),
                status.getOutcome(),
                status.getPhase(),
                status.getRecoverable(),
                status.getTaskId(),
                status.getScope(),
                status.getTarget(),
                status.getTaskId(),
                status.getUpdatedAt(),
                WritingRunListItem.WorkflowEnum.fromValue(status.getWorkflow().getValue()),
                status.getWritingSessionId());
    }

    private static WritingRunStatusResponse v1(WritingRunStatusResponse status) {
        status.setEngineVersion(1);
        status.setRunId(status.getTaskId());
        return status;
    }

    private record RunCandidate(String id, int engineVersion, LocalDateTime createdAt) {}

    private record ProjectedItem(
            WritingRunPublicListItem item,
            java.time.OffsetDateTime createdAt,
            String id) {}

    private record V2Run(
            String id,
            String userId,
            String chapterId,
            String workflow,
            String operation,
            String operationCatalogVersion,
            String modelPolicyJson,
            String status,
            LocalDateTime cancelRequestedAt,
            long lastEventSequence,
            int revision,
            String errorCode) {}

    private record V2Step(
            String id,
            String runId,
            int ordinal,
            String purpose,
            String lane,
            String status,
            int attemptCount,
            long fencingToken,
            String errorCode,
            String modelProfile,
            String modelProfileVersion,
            String resolvedModelJson,
            String latestProgressJson) {}

    private record V2Artifact(
            String id,
            String runId,
            String status,
            int revision) {}

    private record V2Related(
            Map<String, List<V2Step>> activeSteps,
            Map<String, V2Step> failedSteps,
            Map<String, V2Artifact> artifacts) {

        private static V2Related empty() {
            return new V2Related(Map.of(), Map.of(), Map.of());
        }
    }
}
