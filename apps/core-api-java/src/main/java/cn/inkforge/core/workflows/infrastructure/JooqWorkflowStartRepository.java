package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowRunStartResult;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.application.WorkflowStartRepository;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.protocol.ExecutionProtocolDateTime;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.exception.DataAccessException;
import org.postgresql.util.PSQLException;
import tools.jackson.databind.ObjectMapper;

/** PostgreSQL 单事务创建 V2 Run、Evidence、首 Step 与权威 Event。 */
public final class JooqWorkflowStartRepository implements WorkflowStartRepository {

    private static final String FOREGROUND_CONSTRAINT =
            "WorkflowRun_v2_writingSession_foreground_key";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    public JooqWorkflowStartRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public WorkflowRunStartResult start(WorkflowStartPlan plan) {
        return start(plan, () -> {});
    }

    @Override
    public WorkflowRunStartResult start(
            WorkflowStartPlan plan, Runnable finalFreshStartAuthorization) {
        Objects.requireNonNull(plan, "Workflow start plan 不能为空");
        Objects.requireNonNull(finalFreshStartAuthorization, "最终 fresh start 授权不能为空");
        try {
            return database.transactionResult(
                    transaction -> start(transaction, plan, finalFreshStartAuthorization));
        } catch (DataAccessException exception) {
            if (hasConstraint(exception, FOREGROUND_CONSTRAINT)) {
                throw new ApiException(
                        409,
                        "WORKFLOW_FOREGROUND_RUN_EXISTS",
                        "当前写作会话已有未完成的 Agent 运行");
            }
            throw exception;
        }
    }

    private WorkflowRunStartResult start(
            DSLContext transaction,
            WorkflowStartPlan plan,
            Runnable finalFreshStartAuthorization) {
        transaction.execute(
                "SELECT pg_catalog.pg_advisory_xact_lock(?)",
                CommandIdempotency.advisoryLockKey(
                        plan.userId(), plan.clientRequestId()));
        Record existing = transaction.fetchOne(
                """
                SELECT id, "novelId", "chapterId", "writingSessionId", workflow, operation,
                       status::text AS status, "lastEventSequence", revision,
                       "createdAt", "updatedAt", "requestHash"
                FROM public."WorkflowRun"
                WHERE "engineVersion" = 2 AND "userId" = ? AND "idempotencyKey" = ?
                FOR UPDATE
                """,
                plan.userId(),
                plan.clientRequestId());
        if (existing != null) {
            if (!plan.requestHash().equals(existing.get("requestHash", String.class))) {
                throw new ApiException(
                        409,
                        "IDEMPOTENCY_KEY_REUSED",
                        "同一 clientRequestId 已用于不同 Agent 请求");
            }
            return existingResult(transaction, existing, true);
        }

        lockOwnedResources(transaction, plan);
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String runId = ids.next();
        String bundleId = ids.next();
        String stepId = ids.next();
        List<EvidenceValue> evidence = evidence(bundleId, plan.evidenceItems());
        Map<String, Object> manifest = manifest(bundleId, evidence);
        String manifestJson = canonicalJson(manifest);
        String manifestHash = ExecutionCanonicalJson.sha256(manifest);
        long totalBytes = evidence.stream().mapToLong(EvidenceValue::byteCount).sum();
        Map<String, Object> stepInput = plan.initialStep().input();
        String inputHash = ExecutionCanonicalJson.sha256(stepInput);
        String stepIdempotencyKey = runId + "." + stepId;
        Map<String, Object> logicalProfile = logicalProfile(plan.initialStep().modelProfile());
        Map<String, Object> outputSchema = outputSchema(plan.initialStep().outputSchema());
        Map<String, Object> stepBudget = stepBudget(plan.initialStep().stepBudget());
        String stepRequestHash = ExecutionCanonicalJson.sha256(stepRequestMaterial(
                plan,
                runId,
                stepId,
                stepIdempotencyKey,
                inputHash,
                bundleId,
                manifestHash,
                logicalProfile,
                outputSchema,
                stepBudget));

        // advisory/idempotency 与所有 Novel/Chapter/Session 锁均已取得，正文派生、canonical
        // 与 hash 也已完成；此行到首条 INSERT 之间不再允许任何可阻塞或无界工作。
        finalFreshStartAuthorization.run();
        insertRun(transaction, plan, runId, now);
        insertEvidence(
                transaction,
                runId,
                bundleId,
                plan.evidencePolicyVersion(),
                manifestJson,
                manifestHash,
                totalBytes,
                evidence,
                now);
        transaction.execute(
                "UPDATE public.\"WorkflowRun\" SET \"currentEvidenceBundleId\" = ? WHERE id = ?",
                bundleId,
                runId);
        insertInitialStep(
                transaction,
                plan,
                runId,
                stepId,
                bundleId,
                stepIdempotencyKey,
                inputHash,
                stepRequestHash,
                logicalProfile,
                outputSchema,
                stepBudget,
                now);
        insertEvent(
                transaction,
                runId,
                1,
                "run_accepted",
                runAcceptedPayload(plan),
                "run:accepted",
                now);
        insertEvent(
                transaction,
                runId,
                2,
                "evidence_ready",
                Map.of(
                        "bundleId", bundleId,
                        "bundleVersion", 1,
                        "manifestSha256", manifestHash,
                        "totalBytes", totalBytes),
                "evidence:1",
                now);
        transaction.execute(
                """
                UPDATE public."WorkflowRun"
                SET "lastEventSequence" = 2, revision = 1, "updatedAt" = ?
                WHERE id = ?
                """,
                now,
                runId);
        return new WorkflowRunStartResult(
                runId,
                plan.novelId(),
                plan.chapterId(),
                plan.writingSessionId(),
                plan.workflow(),
                plan.operation(),
                "pending",
                stepId,
                2,
                1,
                DatabaseTimestamp.api(now),
                DatabaseTimestamp.api(now),
                false);
    }

    private void lockOwnedResources(DSLContext transaction, WorkflowStartPlan plan) {
        if (plan.novelId() != null) {
            Record novel = transaction.fetchOne(
                    "SELECT id FROM public.\"Novel\" WHERE id = ? AND \"userId\" = ? FOR UPDATE",
                    plan.novelId(),
                    plan.userId());
            if (novel == null) throw notFound();
        }
        if (plan.chapterId() != null) {
            Record chapter = transaction.fetchOne(
                    "SELECT id FROM public.\"Chapter\" WHERE id = ? AND \"novelId\" = ? FOR UPDATE",
                    plan.chapterId(),
                    plan.novelId());
            if (chapter == null) throw notFound();
        }
        if (plan.writingSessionId() != null) {
            Record session = transaction.fetchOne(
                    """
                    SELECT id FROM public."WritingSession"
                    WHERE id = ? AND "novelId" = ? AND "chapterId" = ?
                    FOR UPDATE
                    """,
                    plan.writingSessionId(),
                    plan.novelId(),
                    plan.chapterId());
            if (session == null) {
                throw new ApiException(
                        409,
                        "WRITING_SESSION_MISMATCH",
                        "当前 Agent 请求不属于所选写作会话");
            }
        }
    }

    private void insertRun(
            DSLContext transaction,
            WorkflowStartPlan plan,
            String runId,
            LocalDateTime now) {
        transaction.execute(
                """
                INSERT INTO public."WorkflowRun" (
                  id, "novelId", "chapterId", "userId", kind, status, input,
                  "sourceType", "sourceId", "currentAgentId", "createdAt", "updatedAt",
                  "engineVersion", workflow, operation, "operationCatalogVersion",
                  "writingSessionId", "idempotencyKey", "requestHash", "targetType", "targetId",
                  "budgetJson", "modelPolicyJson", "lastEventSequence", revision
                ) VALUES (
                  ?, ?, ?, ?, CAST(? AS "WorkflowRunKind"), CAST('pending' AS "WorkflowRunStatus"), ?,
                  ?, ?, ?, ?, ?, 2, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1
                )
                """,
                runId,
                plan.novelId(),
                plan.chapterId(),
                plan.userId(),
                plan.runKind(),
                json.writeValueAsString(plan.normalizedInput()),
                plan.targetType(),
                plan.targetId(),
                plan.initialStep().modelProfile().key(),
                now,
                now,
                plan.workflow(),
                plan.operation(),
                plan.operationCatalogVersion(),
                plan.writingSessionId(),
                plan.clientRequestId(),
                plan.requestHash(),
                plan.targetType(),
                plan.targetId(),
                json.writeValueAsString(runBudget(plan.runBudget())),
                json.writeValueAsString(plan.executionPlan().stored()));
    }

    private void insertEvidence(
            DSLContext transaction,
            String runId,
            String bundleId,
            String policyVersion,
            String manifestJson,
            String manifestHash,
            long totalBytes,
            List<EvidenceValue> evidence,
            LocalDateTime now) {
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvidenceBundle" (
                  id, "runId", version, "policyVersion", "manifestJson",
                  "manifestSha256", "totalBytes", "createdAt"
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                """,
                bundleId,
                runId,
                policyVersion,
                manifestJson,
                manifestHash,
                totalBytes,
                now);
        for (EvidenceValue item : evidence) {
            transaction.execute(
                    """
                    INSERT INTO public."WorkflowEvidenceItem" (
                      id, "bundleId", ordinal, "resourceType", "resourceId", exists,
                      "resourceRevision", "resourceUpdatedAt", "contentType", "contentText",
                      "contentJson", "contentSha256", "byteCount", "rangeJson", "metadataJson"
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    item.id(),
                    bundleId,
                    item.ordinal(),
                    item.plan().resourceType(),
                    item.plan().resourceId(),
                    item.plan().exists(),
                    item.plan().resourceRevision(),
                    DatabaseTimestamp.database(item.resourceUpdatedAt()),
                    item.contentType(),
                    item.plan().contentText(),
                    item.contentJson(),
                    item.contentSha256(),
                    item.byteCount(),
                    item.rangeJson(),
                    json.writeValueAsString(item.plan().metadata()));
        }
    }

    private void insertInitialStep(
            DSLContext transaction,
            WorkflowStartPlan plan,
            String runId,
            String stepId,
            String bundleId,
            String idempotencyKey,
            String inputHash,
            String requestHash,
            Map<String, Object> logicalProfile,
            Map<String, Object> outputSchema,
            Map<String, Object> stepBudget,
            LocalDateTime now) {
        WorkflowInitialStepPlan step = plan.initialStep();
        Map<String, Object> storedBudget = Map.of(
                "profile", step.stepBudget().key(),
                "version", step.stepBudget().version(),
                "budget", stepBudget);
        transaction.execute(
                """
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt",
                  ordinal, purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken",
                  "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                  "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion",
                  "budgetJson", "submittedAt", "updatedAt"
                ) VALUES (
                  ?, ?, ?, CAST('agent' AS "WorkflowStepType"),
                  CAST('pending' AS "WorkflowStepStatus"), ?, ?,
                  1, ?, ?, 0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                stepId,
                runId,
                step.modelProfile().key(),
                json.writeValueAsString(step.input()),
                now,
                step.purpose(),
                step.lane(),
                now,
                idempotencyKey,
                requestHash,
                inputHash,
                bundleId,
                step.modelProfile().key(),
                Integer.toString(step.modelProfile().version()),
                step.outputSchema().key(),
                Integer.toString(step.outputSchema().version()),
                json.writeValueAsString(storedBudget),
                now,
                now);
    }

    private void insertEvent(
            DSLContext transaction,
            String runId,
            long sequence,
            String type,
            Map<String, Object> payload,
            String dedupeKey,
            LocalDateTime now) {
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvent" (
                  id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ids.next(),
                runId,
                sequence,
                type,
                json.writeValueAsString(payload),
                dedupeKey,
                now);
    }

    private WorkflowRunStartResult existingResult(
            DSLContext transaction, Record run, boolean replayed) {
        Record step = transaction.fetchOne(
                """
                SELECT id FROM public."WorkflowStep"
                WHERE "runId" = ? AND ordinal = 1
                """,
                run.get("id", String.class));
        if (step == null) {
            throw new IllegalStateException("V2 Run 缺少首个耐久 Step");
        }
        return new WorkflowRunStartResult(
                run.get("id", String.class),
                run.get("novelId", String.class),
                run.get("chapterId", String.class),
                run.get("writingSessionId", String.class),
                run.get("workflow", String.class),
                run.get("operation", String.class),
                run.get("status", String.class),
                step.get("id", String.class),
                run.get("lastEventSequence", Long.class),
                run.get("revision", Integer.class),
                DatabaseTimestamp.api(run.get("createdAt", LocalDateTime.class)),
                DatabaseTimestamp.api(run.get("updatedAt", LocalDateTime.class)),
                replayed);
    }

    private List<EvidenceValue> evidence(
            String bundleId, List<WorkflowEvidenceItemPlan> plans) {
        List<EvidenceValue> result = new ArrayList<>();
        int ordinal = 1;
        for (WorkflowEvidenceItemPlan plan : plans) {
            String contentType = null;
            String contentJson = null;
            String contentHash = null;
            long byteCount = 0;
            if (plan.exists()) {
                byte[] content;
                if (plan.contentText() != null) {
                    contentType = "text";
                    content = plan.contentText().getBytes(StandardCharsets.UTF_8);
                } else {
                    contentType = "json";
                    content = ExecutionCanonicalJson.bytes(plan.contentJson());
                    contentJson = new String(content, StandardCharsets.UTF_8);
                }
                contentHash = sha256(content);
                byteCount = content.length;
            }
            Map<String, Object> range = plan.rangeStartCodePoint() == null
                    ? null
                    : Map.of(
                            "startCodePoint", plan.rangeStartCodePoint(),
                            "endCodePoint", plan.rangeEndCodePoint());
            OffsetDateTime resourceUpdatedAt =
                    ExecutionProtocolDateTime.normalize(plan.resourceUpdatedAt());
            result.add(new EvidenceValue(
                    ids.next(),
                    bundleId,
                    ordinal++,
                    plan,
                    resourceUpdatedAt,
                    contentType,
                    contentJson,
                    contentHash,
                    byteCount,
                    range == null ? null : json.writeValueAsString(range),
                    range));
        }
        return List.copyOf(result);
    }

    private static Map<String, Object> manifest(
            String bundleId, List<EvidenceValue> evidence) {
        List<Map<String, Object>> items = new ArrayList<>();
        for (EvidenceValue value : evidence) {
            WorkflowEvidenceItemPlan plan = value.plan();
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("itemId", value.id());
            item.put("ordinal", value.ordinal());
            item.put("resourceType", plan.resourceType());
            item.put("resourceId", plan.resourceId());
            item.put("exists", plan.exists());
            if (plan.resourceRevision() != null) {
                item.put("resourceRevision", plan.resourceRevision());
            }
            if (value.resourceUpdatedAt() != null) {
                item.put(
                        "resourceUpdatedAt",
                        ExecutionProtocolDateTime.format(value.resourceUpdatedAt()));
            }
            if (value.contentType() != null) item.put("contentType", value.contentType());
            if (value.contentSha256() != null) {
                item.put("contentSha256", value.contentSha256());
            }
            item.put("byteCount", value.byteCount());
            if (value.range() != null) item.put("range", value.range());
            item.put("metadata", plan.metadata());
            items.add(Map.copyOf(item));
        }
        return Map.of(
                "bundleId", bundleId,
                "bundleVersion", 1,
                "itemCount", items.size(),
                "items", List.copyOf(items));
    }

    private static Map<String, Object> logicalProfile(ExecutionRegistry.Profile profile) {
        return Map.of(
                "profile", profile.key(),
                "version", profile.version(),
                "reasoningMode", profile.reasoningMode(),
                "deploymentProfileKey", profile.deploymentProfileKey(),
                "promptProfile", promptProfile(profile.promptProfile()));
    }

    private static Map<String, Object> promptProfile(
            ExecutionRegistry.PromptProfile prompt) {
        return Map.of(
                "name", prompt.key(),
                "version", prompt.version(),
                "sha256", prompt.sha256());
    }

    private static Map<String, Object> outputSchema(ExecutionRegistry.OutputSchema schema) {
        return Map.of(
                "name", schema.key(),
                "version", schema.version(),
                "sha256", schema.sha256(),
                "jsonSchema", schema.jsonSchema());
    }

    private static Map<String, Object> stepBudget(
            ExecutionRegistry.StepBudgetProfile profile) {
        var budget = profile.budget();
        return Map.of(
                "maxModelCalls", budget.maxModelCalls(),
                "maxInputTokens", budget.maxInputTokens(),
                "maxPromptCacheMissTokens", budget.maxPromptCacheMissTokens(),
                "maxCompletionTokens", budget.maxCompletionTokens(),
                "maxReasoningTokens", budget.maxReasoningTokens(),
                "maxVisibleOutputTokens", budget.maxVisibleOutputTokens(),
                "maxCostMicros", budget.maxCostMicros(),
                "maxWallClockSeconds", budget.maxWallClockSeconds(),
                "maxProviderRetries", budget.maxProviderRetries(),
                "maxProtocolCorrections", budget.maxProtocolCorrections());
    }

    private static Map<String, Object> runBudget(ExecutionRegistry.RunBudget budget) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("profile", budget.profile());
        result.put("maxModelCalls", budget.maxModelCalls());
        result.put("maxInputTokens", budget.maxInputTokens());
        result.put("maxPromptCacheMissTokens", budget.maxPromptCacheMissTokens());
        result.put("maxCompletionTokens", budget.maxCompletionTokens());
        result.put("maxReasoningTokens", budget.maxReasoningTokens());
        result.put("maxVisibleOutputTokens", budget.maxVisibleOutputTokens());
        result.put("maxCostMicros", budget.maxCostMicros());
        result.put("maxWallClockSeconds", budget.maxWallClockSeconds());
        result.put("maxProviderRetriesPerStep", budget.maxProviderRetriesPerStep());
        result.put("maxProtocolCorrectionSteps", budget.maxProtocolCorrectionSteps());
        return Map.copyOf(result);
    }

    private static Map<String, Object> stepRequestMaterial(
            WorkflowStartPlan plan,
            String runId,
            String stepId,
            String idempotencyKey,
            String inputHash,
            String bundleId,
            String manifestHash,
            Map<String, Object> logicalProfile,
            Map<String, Object> outputSchema,
            Map<String, Object> stepBudget) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("runId", runId);
        result.put("novelId", plan.novelId());
        result.put("stepId", stepId);
        result.put("idempotencyKey", idempotencyKey);
        result.put("inputHash", inputHash);
        result.put("workflow", plan.workflow());
        result.put("operation", plan.operation());
        result.put("purpose", plan.initialStep().purpose());
        result.put("lane", plan.initialStep().lane());
        result.put(
                "evidenceManifest",
                Map.of(
                        "bundleId", bundleId,
                        "bundleVersion", 1,
                        "policyVersion", plan.evidencePolicyVersion(),
                        "manifestSha256", manifestHash));
        result.put("modelProfile", logicalProfile);
        result.put("outputSchema", outputSchema);
        result.put("budget", stepBudget);
        result.put("artifact", null);
        return Collections.unmodifiableMap(result);
    }

    private static Map<String, Object> runAcceptedPayload(WorkflowStartPlan plan) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("workflow", plan.workflow());
        payload.put("operation", plan.operation());
        if (plan.targetType() != null) {
            payload.put("targetType", plan.targetType());
            payload.put("targetId", plan.targetId());
        }
        payload.put("runRevision", 1);
        return Map.copyOf(payload);
    }

    private static String canonicalJson(Map<String, Object> value) {
        return new String(ExecutionCanonicalJson.bytes(value), StandardCharsets.UTF_8);
    }

    private static String sha256(byte[] value) {
        try {
            return HexFormat.of()
                    .formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }

    private static ApiException notFound() {
        return new ApiException(404, "WORKFLOW_TARGET_NOT_FOUND", "Agent 运行目标不存在或无权访问");
    }

    private static boolean hasConstraint(Throwable error, String constraint) {
        Throwable current = error;
        for (int depth = 0; current != null && depth < 16; depth++) {
            if (current instanceof PSQLException postgres
                    && "23505".equals(postgres.getSQLState())
                    && postgres.getServerErrorMessage() != null
                    && constraint.equals(postgres.getServerErrorMessage().getConstraint())) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private record EvidenceValue(
            String id,
            String bundleId,
            int ordinal,
            WorkflowEvidenceItemPlan plan,
            OffsetDateTime resourceUpdatedAt,
            String contentType,
            String contentJson,
            String contentSha256,
            long byteCount,
            String rangeJson,
            Map<String, Object> range) {}
}
