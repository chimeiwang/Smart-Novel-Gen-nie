package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.WorkflowCurrentStepSnapshot;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.application.LongSerialDurableRunStarter;
import cn.inkforge.core.writing.domain.WritingMessageMetadata;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowRunStartResult;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowStepSnapshotFactory;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;

/** 长篇章节选区改写的确定性 Evidence Planner 与 V2 Run 入口。 */
final class JooqLongSerialDurableRunStarter implements LongSerialDurableRunStarter {

    private final CoreDatabase database;
    private final LongSerialRunAssembler assembler;
    private final DurableWorkflowService workflows;
    private final ExecutionRegistry registry;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final WorkflowStepSnapshotFactory stepSnapshots;

    JooqLongSerialDurableRunStarter(
            CoreDatabase database,
            LongSerialRunAssembler assembler,
            DurableWorkflowService workflows,
            ExecutionRegistry registry,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.assembler = Objects.requireNonNull(assembler);
        this.workflows = Objects.requireNonNull(workflows);
        this.registry = Objects.requireNonNull(registry);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.stepSnapshots = new WorkflowStepSnapshotFactory(json);
    }

    @Override
    public WritingRunV2Response start(
            String userId, LongSerialStartWritingRunRequest request) {
        if (request.getOperation()
                != LongSerialStartWritingRunRequest.OperationEnum.REWRITE_CHAPTER_SELECTION) {
            throw new ApiException(
                    409,
                    "DURABLE_OPERATION_NOT_ENABLED",
                    "该写作操作尚未切换到耐久执行引擎");
        }
        LongSerialRunAssembler.Normalized normalized = assembler.normalize(request);
        return database.transactionResult(transaction -> {
            WritingRunV2Response replay = replay(
                    transaction,
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint());
            if (replay != null) return replay;
            requireLongSerialOwner(transaction, userId, request);
            LongSerialRunAssembler.Assembled assembled = assembler.assemble(
                    transaction, userId, request, normalized.definition());
            Map<String, Object> snapshot = object(
                    assembled.job().get("selectionSnapshot"), "选区快照");
            Map<String, Object> source = object(
                    snapshot.get("sourceSnapshot"), "选区完整来源");
            String content = string(source, "content");
            String resourceType = string(snapshot, "resourceType");
            String resourceId = string(snapshot, "resourceId");
            OffsetDateTime updatedAt = OffsetDateTime.parse(string(source, "updatedAt"));
            int selectionStart = integer(snapshot, "selectionStart");
            int selectionEnd = integer(snapshot, "selectionEnd");

            Map<String, Object> input = new LinkedHashMap<>();
            input.put("target", normalized.body().get("target"));
            input.put("selectionTarget", normalized.body().get("selectionTarget"));
            input.put("selectedText", snapshot.get("selectedText"));
            input.put("contextBefore", snapshot.get("contextBefore"));
            input.put("contextAfter", snapshot.get("contextAfter"));
            input.put("userInstruction", request.getUserInstruction());

            ExecutionRegistry.ResolvedOperation operation = registry.resolve(
                    "long_serial.rewrite_chapter_selection", false);
            ExecutionPlanSnapshot executionPlan = registry.freezePlan(
                    "long_serial.rewrite_chapter_selection", false);

            WorkflowStartPlan plan = new WorkflowStartPlan(
                    userId,
                    request.getClientRequestId(),
                    normalized.fingerprint(),
                    operation.operation().workflow(),
                    operation.operation().operation(),
                    registry.catalogVersion(),
                    "chapter_generation",
                    request.getNovelId(),
                    request.getChapterId(),
                    nullable(request.getWritingSessionId()),
                    resourceType,
                    resourceId,
                    normalized.body(),
                    operation.operation().evidencePolicy(),
                    List.of(new WorkflowEvidenceItemPlan(
                            resourceType,
                            resourceId,
                            true,
                            null,
                            updatedAt,
                            content,
                            null,
                            selectionStart,
                            selectionEnd,
                            Map.of(
                                    "role", "selection_source",
                                    "baseContentHash", string(snapshot, "baseContentHash"),
                                    "selectedTextHash", string(snapshot, "selectedTextHash")))),
                    operation.operation().runBudget(),
                    executionPlan,
                    new WorkflowInitialStepPlan(
                            "generation",
                            operation.operation().lane(),
                            input,
                            operation.generatorProfile(),
                            operation.generatorStepBudget(),
                            operation.outputSchema()));
            WorkflowRunStartResult result = workflows.start(plan);
            if (result.replayed()) {
                WritingRunV2Response concurrentReplay = replay(
                        transaction,
                        userId,
                        request.getClientRequestId(),
                        normalized.fingerprint());
                if (concurrentReplay == null) {
                    throw new IllegalStateException("幂等重放的 V2 Run 不可见");
                }
                return concurrentReplay;
            }
            persistUserMessage(
                    transaction,
                    result,
                    request.getUserInstruction(),
                    assembled.selectionAttachmentMetadata());
            return response(result, executionPlan);
        });
    }

    private void persistUserMessage(
            DSLContext transaction,
            WorkflowRunStartResult result,
            String userInstruction,
            Map<String, Object> selectionAttachmentMetadata) {
        String sessionId = result.writingSessionId();
        if (sessionId == null || result.replayed()) return;
        Map<String, Object> source = new LinkedHashMap<>();
        if (selectionAttachmentMetadata != null) {
            source.putAll(selectionAttachmentMetadata);
        }
        source.put("engineVersion", 2);
        source.put("runId", result.runId());
        source.put("operation", result.operation());
        String metadata = WritingMessageMetadata.serialize(
                result.runId(),
                "user",
                userInstruction,
                null,
                source,
                json);
        Record existing = transaction.fetchOne(
                """
                SELECT id FROM public."WritingMessage"
                WHERE "sessionId" = ? AND metadata = ?
                ORDER BY "createdAt", id
                LIMIT 1
                """,
                sessionId,
                metadata);
        if (existing != null) return;
        Record session = transaction.fetchOne(
                """
                SELECT "updatedAt" FROM public."WritingSession"
                WHERE id = ? FOR UPDATE
                """,
                sessionId);
        if (session == null) {
            throw new IllegalStateException("V2 Run 绑定的写作会话不存在");
        }
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.execute(
                """
                INSERT INTO public."WritingMessage" (
                  id, "sessionId", role, "agentId", content, metadata, "createdAt"
                ) VALUES (?, ?, 'user', NULL, ?, ?, ?)
                """,
                ids.next(),
                sessionId,
                userInstruction,
                metadata,
                now);
        LocalDateTime sessionUpdatedAt = DatabaseTimestamp.next(
                clock, session.get("updatedAt", LocalDateTime.class));
        transaction.execute(
                "UPDATE public.\"WritingSession\" SET \"updatedAt\" = ? WHERE id = ?",
                sessionUpdatedAt,
                sessionId);
    }

    private WritingRunV2Response replay(
            DSLContext transaction,
            String userId,
            String clientRequestId,
            String requestHash) {
        Record run = transaction.fetchOne(
                """
                SELECT id, "chapterId", workflow, operation, status::text AS status,
                       "operationCatalogVersion", "requestHash", "modelPolicyJson",
                       "lastEventSequence", revision
                FROM public."WorkflowRun"
                WHERE "engineVersion" = 2 AND "userId" = ? AND "idempotencyKey" = ?
                FOR UPDATE
                """,
                userId,
                clientRequestId);
        if (run == null) return null;
        if (!requestHash.equals(run.get("requestHash", String.class))) {
            throw new ApiException(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 clientRequestId 已用于不同 Agent 请求");
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
                run.get("id", String.class));
        return response(run, activeStepRecords);
    }

    private static void requireLongSerialOwner(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request) {
        // 公共 Router 已按 Novel -> Chapter 取得首轮锁；这里即使被单独调用也保持同序，
        // 再锁附属 WritingBible 与可选 Session，不能从 Chapter 回头等待 Novel。
        Record novel = transaction.fetchOne(
                """
                SELECT id FROM public."Novel"
                WHERE id = ? AND "userId" = ?
                FOR UPDATE
                """,
                request.getNovelId(),
                userId);
        if (novel == null) {
            throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
        }
        Record chapter = transaction.fetchOne(
                """
                SELECT id FROM public."Chapter"
                WHERE id = ? AND "novelId" = ? FOR UPDATE
                """,
                request.getChapterId(),
                request.getNovelId());
        if (chapter == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节不存在");
        }
        Record bible = transaction.fetchOne(
                """
                SELECT "storyLengthProfile"::text AS profile
                FROM public."WritingBible"
                WHERE "novelId" = ?
                FOR UPDATE
                """,
                request.getNovelId());
        if (bible == null) {
            throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
        }
        if (!"long_serial".equals(bible.get("profile", String.class))) {
            throw new ApiException(409, "LONG_WORKFLOW_MISMATCH", "目标小说不是长篇作品");
        }
        String sessionId = nullable(request.getWritingSessionId());
        if (sessionId != null) {
            Record session = transaction.fetchOne(
                    """
                    SELECT id FROM public."WritingSession"
                    WHERE id = ? AND "novelId" = ? AND "chapterId" = ?
                    FOR UPDATE
                    """,
                    sessionId,
                    request.getNovelId(),
                    request.getChapterId());
            if (session == null) {
                throw new ApiException(
                        409,
                        "WRITING_SESSION_MISMATCH",
                        "当前请求不属于所选写作会话");
            }
        }
    }

    private WritingRunV2Response response(
            WorkflowRunStartResult result, ExecutionPlanSnapshot executionPlan) {
        ExecutionPlanSnapshot.Step generator = executionPlan.generator();
        WorkflowCurrentStepSnapshot step = stepSnapshots.modelStep(
                executionPlan,
                result.stepId(),
                1,
                generator.purpose(),
                generator.lane(),
                "pending",
                0,
                0,
                null,
                generator.modelProfile().profile(),
                generator.modelProfile().version(),
                null);
        List<WorkflowCurrentStepSnapshot> activeSteps = List.of(step);
        return new WritingRunV2Response(
                        activeSteps,
                        result.chapterId(),
                        null,
                        null,
                        2,
                        Math.toIntExact(result.lastEventSequence()),
                        result.revision(),
                        result.runId(),
                        WritingRunV2Response.StatusEnum.fromValue(result.status()),
                        result.runId(),
                        result.workflow())
                .operation(result.operation())
                .currentStep(step);
    }

    private WritingRunV2Response response(Record run, List<Record> activeStepRecords) {
        ExecutionPlanSnapshot executionPlan =
                stepSnapshots.executionPlan(run.get("modelPolicyJson", String.class));
        executionPlan.requireOperation(
                run.get("workflow", String.class),
                run.get("operation", String.class),
                run.get("operationCatalogVersion", String.class));
        List<WorkflowCurrentStepSnapshot> activeSteps = activeStepRecords.stream()
                .map(step -> stepSnapshot(executionPlan, step))
                .toList();
        String status = run.get("status", String.class);
        if (!activeSteps.isEmpty() && !List.of("pending", "running").contains(status)) {
            throw new IllegalStateException("非执行中 V2 WorkflowRun 含活动 Step");
        }
        WorkflowCurrentStepSnapshot current = activeSteps.isEmpty()
                ? null
                : activeSteps.getFirst();
        return new WritingRunV2Response(
                        activeSteps,
                        run.get("chapterId", String.class),
                        null,
                        null,
                        2,
                        Math.toIntExact(run.get("lastEventSequence", Long.class)),
                        run.get("revision", Integer.class),
                        run.get("id", String.class),
                        WritingRunV2Response.StatusEnum.fromValue(status),
                        run.get("id", String.class),
                        run.get("workflow", String.class))
                .operation(run.get("operation", String.class))
                .currentStep(current);
    }

    private WorkflowCurrentStepSnapshot stepSnapshot(
            ExecutionPlanSnapshot executionPlan, Record step) {
        String lane = step.get("lane", String.class);
        if ("control".equals(lane)) {
            return stepSnapshots.controlStep(
                    step.get("id", String.class),
                    step.get("ordinal", Integer.class),
                    step.get("purpose", String.class),
                    step.get("status", String.class),
                    step.get("attemptCount", Integer.class),
                    step.get("fencingToken", Long.class),
                    step.get("errorCode", String.class));
        }
        if (executionPlan == null) {
            throw new IllegalStateException("模型 Step 缺少冻结执行计划");
        }
        return stepSnapshots.modelStep(
                executionPlan,
                step.get("id", String.class),
                step.get("ordinal", Integer.class),
                step.get("purpose", String.class),
                lane,
                step.get("status", String.class),
                step.get("attemptCount", Integer.class),
                step.get("fencingToken", Long.class),
                step.get("errorCode", String.class),
                step.get("modelProfile", String.class),
                Integer.parseInt(step.get("modelProfileVersion", String.class)),
                step.get("resolvedModelJson", String.class),
                step.get("latest_progress_json", String.class));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value, String label) {
        if (!(value instanceof Map<?, ?> raw)) {
            throw new IllegalStateException(label + "缺失或类型无效");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        raw.forEach((key, nested) -> {
            if (!(key instanceof String text)) {
                throw new IllegalStateException(label + " key 类型无效");
            }
            result.put(text, nested);
        });
        return result;
    }

    private static String string(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof String result)) {
            throw new IllegalStateException("选区快照缺少 " + key);
        }
        return result;
    }

    private static int integer(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Number result)) {
            throw new IllegalStateException("选区快照缺少 " + key);
        }
        return Math.toIntExact(result.longValue());
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value != null && value.isPresent() ? value.orElse(null) : null;
    }
}
