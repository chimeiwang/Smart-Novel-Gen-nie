package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.api.EvaluationEvidenceReference;
import cn.inkforge.contracts.api.EvaluationFinding;
import cn.inkforge.contracts.api.EvidenceEvaluation;
import cn.inkforge.contracts.api.ExecutionCallbackReceipt;
import cn.inkforge.contracts.api.ExecutionStepFailure;
import cn.inkforge.contracts.api.ExecutionStepProgress;
import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.contracts.api.ModelProfileRef;
import cn.inkforge.contracts.api.ResolvedModelRef;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowCallbackRepository;
import cn.inkforge.core.workflows.application.WorkflowCallbackResources;
import cn.inkforge.core.workflows.application.WorkflowExecutionRejectedException;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.domain.DurableSelectionArtifact;
import cn.inkforge.core.workflows.domain.WorkflowBudgetDimension;
import cn.inkforge.core.workflows.domain.WorkflowBudgetExceededException;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.domain.WorkflowStepBudget;
import cn.inkforge.core.workflows.domain.WorkflowStepUsage;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.protocol.WorkflowOutputValidator;
import cn.inkforge.core.workflows.domain.WorkflowMessageMetadata;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** PostgreSQL 中单事务收敛 progress/result/failure，并按冻结计划物化业务结果。 */
final class JooqWorkflowCallbackRepository implements WorkflowCallbackRepository {

    private static final TypeReference<Map<String, Object>> JSON_OBJECT = new TypeReference<>() {};
    private static final String GENERATION = "generation";
    private static final String REVIEW = "review";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final Duration leaseDuration;
    private final WorkflowBillingCoordinator billing;

    JooqWorkflowCallbackRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            ExecutionRegistry registry,
            Duration leaseDuration) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        ExecutionRegistry requiredRegistry = Objects.requireNonNull(registry);
        WorkflowResultMaterializerRegistry.requireEnabledOperationKeys(
                requiredRegistry.enabledOperationKeys("long_serial", false));
        if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
            throw new IllegalArgumentException("Workflow callback lease 必须为正数");
        }
        this.leaseDuration = leaseDuration;
        this.billing = new WorkflowBillingCoordinator(ids, json, requiredRegistry);
    }

    @Override
    public WorkflowCallbackResources resources(String runId, String stepId) {
        Record value = database.dsl().fetchOne(
                """
                SELECT run.id AS "runId", step.id AS "stepId", run."novelId"
                FROM public."WorkflowRun" AS run
                JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                WHERE run.id = ? AND step.id = ? AND run."engineVersion" = 2
                """,
                runId,
                stepId);
        if (value == null) throw notFound();
        return new WorkflowCallbackResources(
                value.get("runId", String.class),
                value.get("stepId", String.class),
                value.get("novelId", String.class));
    }

    @Override
    public ExecutionCallbackReceipt progress(ExecutionStepProgress progress) {
        Objects.requireNonNull(progress);
        return database.transactionResult(transaction -> progress(transaction, progress));
    }

    @Override
    public ExecutionCallbackReceipt result(ExecutionStepResult result) {
        Objects.requireNonNull(result);
        return database.transactionResult(transaction -> result(transaction, result));
    }

    @Override
    public ExecutionCallbackReceipt failure(ExecutionStepFailure failure) {
        Objects.requireNonNull(failure);
        return database.transactionResult(transaction -> failure(transaction, failure));
    }

    /** Agent 在受理前给出确定性 HTTP 拒绝时，不等待租约反复恢复。 */
    void rejectSubmission(
            cn.inkforge.contracts.agent.ExecutionStepRequest request, String errorCode) {
        database.transactionResult(transaction -> {
            Locked locked = lock(transaction, request.getRunId(), request.getStepId());
            if (isTerminalStep(locked.step().get("status", String.class))
                    || isTerminalRun(locked.run().get("status", String.class))) {
                return null;
            }
            if (!matchesFence(
                            locked.step(), request.getJobId(), request.getFencingToken())
                    || !Objects.equals(
                            locked.step().get("requestHash", String.class),
                            request.getRequestHash())
                    || !Objects.equals(
                            locked.step().get("inputHash", String.class), request.getInputHash())
                    || !Objects.equals(
                            locked.run().get("novelId", String.class), request.getNovelId())) {
                return null;
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            WorkflowStepUsage usage = new WorkflowStepUsage(
                    cn.inkforge.core.workflows.domain.WorkflowUsageStatus.UNKNOWN,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    0,
                    0,
                    0);
            if ("pending".equals(locked.step().get("status", String.class))) {
                billing.releaseUnstarted(
                        transaction,
                        locked.run().get("id", String.class),
                        locked.step().get("id", String.class),
                        now);
            }
            convergeRejectedStep(transaction, locked, errorCode, usage, now);
            return null;
        });
    }

    private void convergeRejectedStep(
            DSLContext transaction,
            Locked locked,
            String errorCode,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        failRejectedStep(transaction, locked, errorCode, usage, now);
        long sequence = appendStepFinished(
                transaction, locked, "failed", errorCode,
                locked.run().get("lastEventSequence", Long.class), now);
        String purpose = locked.step().get("purpose", String.class);
        if (GENERATION.equals(purpose)) {
            failRun(transaction, locked, errorCode, false, sequence, now);
        } else if (REVIEW.equals(purpose)) {
            // Reviewer 不可用只产生 failed Evaluation；已有 candidate 仍由其余 Reviewer 按
            // onUnavailable 策略收敛，不能把整个 Run 当成 generation 失败。
            insertFailedEvaluation(transaction, locked, now);
            convergeReviewers(transaction, locked, sequence, now);
        } else {
            throw invalid("确定性拒绝引用了未授权的 Step purpose");
        }
    }

    private ExecutionCallbackReceipt progress(DSLContext transaction, ExecutionStepProgress body) {
        requireProtocol(body.getProtocolVersion());
        if (body.getSequence() == null || body.getSequence() < 1) {
            throw invalid("progress sequence 必须为正数");
        }
        if (body.getWaitingOnProvider()
                != (body.getPhase() == ExecutionStepProgress.PhaseEnum.WAITING_PROVIDER)) {
            throw invalid("waitingOnProvider 必须与 waiting_provider 阶段一致");
        }
        Locked locked = lock(transaction, body.getRunId(), body.getStepId());
        requireCommonBinding(
                locked,
                body.getJobId(),
                body.getFencingToken(),
                body.getRequestHash(),
                requiredNovel(body.getNovelId()));
        if (!matchesFence(locked.step(), body.getJobId(), body.getFencingToken())) {
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.STALE);
        }
        String stepStatus = locked.step().get("status", String.class);
        if (isTerminalStep(stepStatus) || isTerminalRun(locked.run().get("status", String.class))) {
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.STALE);
        }

        UsageValidation usageValidation = requireUsage(locked.step(), body.getUsage());
        requireWithinBudget(usageValidation, "progress");
        WorkflowStepUsage usage = usageValidation.usage();
        if ("pending".equals(stepStatus)
                && body.getPhase() != ExecutionStepProgress.PhaseEnum.PREPARING) {
            throw invalid("pending Step 只能由 preparing progress 开始");
        }
        LocalDateTime now = DatabaseTimestamp.now(clock);
        if (body.getPhase() == ExecutionStepProgress.PhaseEnum.PREPARING
                && (usage.providerAttempts() != 0
                        || usage.usageStatus()
                                != cn.inkforge.core.workflows.domain.WorkflowUsageStatus.UNKNOWN)) {
            throw invalid("preparing 必须发生在零 provider attempt 与未知供应商用量阶段");
        }
        WorkflowResolvedModel resolved;
        try {
            resolved = requireResolvedBinding(
                    transaction,
                    locked,
                    body.getJobId(),
                    body.getFencingToken(),
                    body.getRequestHash(),
                    body.getResolvedModel());
            if (body.getPhase() == ExecutionStepProgress.PhaseEnum.PREPARING) {
                // preparing 是唯一昂贵调用授权门：部署、Run 累计预算和 User 可用余额必须在
                // 当前 Run→Step 锁事务内同时冻结，Agent 收到 accepted 后才可进入 provider journal。
                billing.reserve(transaction, body.getRunId(), body.getStepId(), resolved, now);
            } else if (body.getPhase()
                    == ExecutionStepProgress.PhaseEnum.WAITING_PROVIDER) {
                billing.requireProviderGate(transaction, body.getRunId(), body.getStepId());
            }
        } catch (WorkflowExecutionRejectedException exception) {
            billing.releaseProvenNoProviderAttempt(
                    transaction, body.getRunId(), body.getStepId(), usage, now);
            convergeRejectedStep(transaction, locked, exception.errorCode(), usage, now);
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.STALE);
        } catch (IllegalArgumentException exception) {
            convergeRejectedStep(
                    transaction, locked, "MODEL_DEPLOYMENT_NOT_AUTHORIZED", usage, now);
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.STALE);
        }
        long previousSequence = Objects.requireNonNullElse(
                locked.step().get("lastProgressSequence", Long.class), 0L);
        long incomingSequence = body.getSequence().longValue();
        if (incomingSequence < previousSequence) {
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.STALE);
        }
        if (incomingSequence == previousSequence) {
            WorkflowStepUsage previous = storedUsage(locked.step());
            if (previous == null || !previous.equals(usage)) {
                throw invalid("同一 progress sequence 不得重写不同 usage");
            }
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        }
        transaction.execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('running' AS "WorkflowStepStatus"),
                    "heartbeatAt" = ?, "leaseExpiresAt" = ?, "usageJson" = ?,
                    "lastProgressSequence" = ?, "updatedAt" = ?
                WHERE id = ? AND "runId" = ?
                """,
                now,
                now.plus(leaseDuration),
                json.writeValueAsString(WorkflowCallbackValues.usageMap(usage)),
                incomingSequence,
                now,
                body.getStepId(),
                body.getRunId());

        // cancelRequestedAt 之后 progress 只是计费尾项，不再生成用户语义 Event。
        if (locked.run().get("cancelRequestedAt", LocalDateTime.class) != null) {
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        }
        ExecutionPlanSnapshot.Step frozenStep = frozenStep(
                locked, executionPlan(locked.run()));
        Map<String, Object> modelProfile = frozenStep.modelProfile().toMap();
        Map<String, Object> resolvedModel = WorkflowCallbackValues.resolvedModelMap(resolved);
        long sequence = locked.run().get("lastEventSequence", Long.class);
        if ("pending".equals(stepStatus)) {
            sequence = appendEvent(
                    transaction,
                    body.getRunId(),
                    sequence,
                    "step_started",
                    Map.of(
                            "stepId", body.getStepId(),
                            "ordinal", locked.step().get("ordinal", Integer.class),
                            "purpose", locked.step().get("purpose", String.class),
                            "modelProfile", modelProfile,
                            "attemptCount", locked.step().get("attemptCount", Integer.class),
                            "fencingToken", body.getFencingToken()),
                    "step:started:" + body.getStepId() + ":" + body.getFencingToken(),
                    now);
        }
        sequence = appendEvent(
                transaction,
                body.getRunId(),
                sequence,
                "step_progress",
                Map.of(
                        "stepId", body.getStepId(),
                        "fencingToken", body.getFencingToken(),
                        "progressSequence", body.getSequence(),
                        "modelProfile", modelProfile,
                        "resolvedModel", resolvedModel,
                        "phase", body.getPhase().getValue(),
                        "elapsedSeconds", body.getElapsedSeconds(),
                        "waitingOnProvider", body.getWaitingOnProvider(),
                        "usageStatus", usage.usageStatus().wireValue()),
                "progress:" + body.getStepId() + ":" + body.getFencingToken() + ":"
                        + body.getSequence(),
                now);
        transaction.execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST('running' AS "WorkflowRunStatus"),
                    "lastEventSequence" = ?, revision = revision + 1, "updatedAt" = ?
                WHERE id = ?
                """,
                sequence,
                now,
                body.getRunId());
        return receipt(body, ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
    }

    private ExecutionCallbackReceipt result(DSLContext transaction, ExecutionStepResult body) {
        requireProtocol(body.getProtocolVersion());
        Map<String, Object> hashMaterial = resultHashMaterial(body);
        requireHash(body.getResultHash(), hashMaterial, "result");
        Locked locked = lock(transaction, body.getRunId(), body.getStepId());
        requireTerminalBinding(
                transaction,
                locked,
                body.getJobId(),
                body.getFencingToken(),
                body.getRequestHash(),
                body.getInputHash(),
                requiredNovel(body.getNovelId()),
                body.getResolvedModel());
        String storedResultHash = locked.step().get("resultHash", String.class);
        if (storedResultHash != null
                && Objects.equals(
                        locked.step().get("fencingToken", Long.class),
                        body.getFencingToken().longValue())) {
            if (!storedResultHash.equals(body.getResultHash())) {
                throw invalid("同一 fence 不得提交不同 Result hash");
            }
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        }
        if (!matchesFence(locked.step(), body.getJobId(), body.getFencingToken())) {
            return receipt(body, staleTerminalDisposition(locked, body.getFencingToken()));
        }
        if (storedResultHash != null) {
            throw invalid("matching fence 的 Result hash 状态不一致");
        }
        if (isTerminalStep(locked.step().get("status", String.class))) {
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.SUPERSEDED);
        }
        UsageValidation usageValidation = requireUsage(locked.step(), body.getUsage());
        requireWithinBudget(usageValidation, "Result");
        WorkflowStepUsage usage = usageValidation.usage();
        LocalDateTime now = DatabaseTimestamp.now(clock);
        if (locked.run().get("cancelRequestedAt", LocalDateTime.class) != null) {
            skipCancelledResult(transaction, locked, body.getResultHash(), usage, now);
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        }
        requireRunning(locked);
        usage = billing.settleTerminal(
                transaction,
                body.getRunId(),
                body.getStepId(),
                usage,
                now);
        String purpose = locked.step().get("purpose", String.class);
        if (GENERATION.equals(purpose)) {
            completeGeneration(transaction, locked, body, usage, now);
        } else if (REVIEW.equals(purpose)) {
            completeReview(transaction, locked, body, usage, now);
        } else {
            throw invalid("执行回调引用了未授权的 Step purpose");
        }
        return receipt(body, ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
    }

    private ExecutionCallbackReceipt failure(DSLContext transaction, ExecutionStepFailure body) {
        requireProtocol(body.getProtocolVersion());
        Map<String, Object> hashMaterial = failureHashMaterial(body);
        requireHash(body.getResultHash(), hashMaterial, "failure result");
        Locked locked = lock(transaction, body.getRunId(), body.getStepId());
        requireTerminalBinding(
                transaction,
                locked,
                body.getJobId(),
                body.getFencingToken(),
                body.getRequestHash(),
                body.getInputHash(),
                requiredNovel(body.getNovelId()),
                body.getResolvedModel());
        String storedResultHash = locked.step().get("resultHash", String.class);
        if (storedResultHash != null
                && Objects.equals(
                        locked.step().get("fencingToken", Long.class),
                        body.getFencingToken().longValue())) {
            if (!storedResultHash.equals(body.getResultHash())) {
                throw invalid("同一 fence 不得提交不同 Failure hash");
            }
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.DUPLICATE);
        }
        if (!matchesFence(locked.step(), body.getJobId(), body.getFencingToken())) {
            return receipt(body, staleTerminalDisposition(locked, body.getFencingToken()));
        }
        if (storedResultHash != null) {
            throw invalid("matching fence 的 Failure hash 状态不一致");
        }
        if (isTerminalStep(locked.step().get("status", String.class))) {
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.SUPERSEDED);
        }
        UsageValidation usageValidation = requireUsage(locked.step(), body.getUsage());
        requireBudgetFailureBinding(body, usageValidation);
        WorkflowStepUsage usage = usageValidation.usage();
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String cancelRequestId = WorkflowCallbackValues.optional(body.getCancelRequestId());
        String runCancelRequestId = locked.run().get("cancelRequestId", String.class);
        if (locked.run().get("cancelRequestedAt", LocalDateTime.class) != null) {
            if (cancelRequestId != null && !Objects.equals(cancelRequestId, runCancelRequestId)) {
                throw invalid("cancel failure 与 Run cancelRequestId 不一致");
            }
            skipCancelledResult(transaction, locked, body.getResultHash(), usage, now);
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        }
        requireFailureState(locked, usage);
        usage = billing.settleTerminal(
                transaction,
                body.getRunId(),
                body.getStepId(),
                usage,
                now);
        String purpose = locked.step().get("purpose", String.class);
        failStep(transaction, locked, body, usage, now);
        long sequence = appendStepFinished(
                transaction,
                locked,
                "failed",
                body.getErrorCode(),
                locked.run().get("lastEventSequence", Long.class),
                now);
        if (GENERATION.equals(purpose)) {
            failRun(
                    transaction,
                    locked,
                    body.getErrorCode(),
                    body.getOutcomeUnknown(),
                    sequence,
                    now);
        } else if (REVIEW.equals(purpose)) {
            insertFailedEvaluation(transaction, locked, now);
            convergeReviewers(transaction, locked, sequence, now);
        } else {
            throw invalid("执行失败引用了未授权的 Step purpose");
        }
        return receipt(body, ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
    }

    private void completeGeneration(
            DSLContext transaction,
            Locked locked,
            ExecutionStepResult body,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        if (body.getResultKind() != ExecutionStepResult.ResultKindEnum.OUTPUT) {
            throw invalid("generation Step 只接受 output 结果");
        }
        Map<String, Object> output = WorkflowCallbackValues.optional(body.getOutput());
        if (output == null) throw invalid("generation output 不能为空");
        ExecutionPlanSnapshot executionPlan = executionPlan(locked.run());
        ExecutionPlanSnapshot.Step frozenStep = frozenStep(locked, executionPlan);
        WorkflowResultMaterializerRegistry.Materializer materializer;
        try {
            materializer = WorkflowResultMaterializerRegistry.resolve(executionPlan);
        } catch (IllegalArgumentException exception) {
            throw invalid(exception.getMessage());
        }
        switch (materializer) {
            case CHAT_ANSWER -> completeChatAnswer(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case CHAPTER_SELECTION_REVIEW_ARTIFACT -> completeSelectionGeneration(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
        }
    }

    private void completeSelectionGeneration(
            DSLContext transaction,
            Locked locked,
            ExecutionPlanSnapshot executionPlan,
            ExecutionPlanSnapshot.Step frozenStep,
            ExecutionStepResult body,
            WorkflowStepUsage usage,
            Map<String, Object> output,
            LocalDateTime now) {
        validateSelectionGenerationOutput(frozenStep.outputSchema(), output);
        Artifact artifact = materializeSelection(
                transaction,
                locked,
                executionPlan,
                output,
                body.getResultHash(),
                now);
        // revise generation 在创建时已经不可变绑定输入 Artifact revision；终报不能把该来源绑定
        // 漂移成新产出的 revision。首次 generation 没有来源绑定，才在 terminal 时一次冻结输出。
        String frozenArtifactId = locked.step().get("artifactId", String.class);
        Integer frozenArtifactRevision = locked.step().get("artifactRevision", Integer.class);
        completeStep(
                transaction,
                locked,
                body.getResultHash(),
                usage,
                canonicalJson(output),
                frozenArtifactId == null ? artifact.id() : frozenArtifactId,
                frozenArtifactRevision == null ? artifact.revision() : frozenArtifactRevision,
                now);
        List<Map<String, Object>> reviewerSteps = createReviewerSteps(
                transaction, locked, executionPlan, artifact, output, now);
        long sequence = locked.run().get("lastEventSequence", Long.class);
        sequence = appendStepFinished(
                transaction, locked, "completed", null, sequence, now);
        sequence = appendEvent(
                transaction,
                body.getRunId(),
                sequence,
                "candidate_ready",
                Map.of(
                        "stepId", body.getStepId(),
                        "artifactId", artifact.id(),
                        "artifactRevision", artifact.revision()),
                "candidate:" + artifact.id() + ":" + artifact.revision(),
                now);
        sequence = appendEvent(
                transaction,
                body.getRunId(),
                sequence,
                "review_started",
                Map.of(
                        "artifactId", artifact.id(),
                        "artifactRevision", artifact.revision(),
                        "reviewerSteps", reviewerSteps),
                "review:started:" + artifact.id() + ":" + artifact.revision(),
                now);
        updateRun(transaction, body.getRunId(), "running", sequence, null, null, now);
    }

    private void completeChatAnswer(
            DSLContext transaction,
            Locked locked,
            ExecutionPlanSnapshot executionPlan,
            ExecutionPlanSnapshot.Step frozenStep,
            ExecutionStepResult body,
            WorkflowStepUsage usage,
            Map<String, Object> output,
            LocalDateTime now) {
        requireChatAnswerPlan(locked, executionPlan);
        String answer = validateChatAnswerOutput(frozenStep.outputSchema(), output);
        String messageId = persistChatAnswer(
                transaction, locked, frozenStep, answer, body.getResultHash(), now);
        completeStep(
                transaction,
                locked,
                body.getResultHash(),
                usage,
                canonicalJson(output),
                null,
                null,
                now);
        long sequence = appendStepFinished(
                transaction,
                locked,
                "completed",
                null,
                locked.run().get("lastEventSequence", Long.class),
                now);
        sequence = appendEvent(
                transaction,
                body.getRunId(),
                sequence,
                "completed",
                Map.of("outcomeType", "chat_answer", "resultId", messageId),
                "run:completed",
                now);
        updateRun(transaction, body.getRunId(), "completed", sequence, null, now, now);
    }

    private static void requireChatAnswerPlan(
            Locked locked, ExecutionPlanSnapshot executionPlan) {
        if (executionPlan.operation().mutating()
                || !executionPlan.operation().deterministicValidators().containsAll(List.of(
                        "validator.schema_strict.v1", "validator.complete_output.v1"))
                || !"none".equals(executionPlan.reviewPolicy().mode())
                || !executionPlan.reviewers().isEmpty()
                || !executionPlan.systemSteps().isEmpty()
                || locked.step().get("artifactId", String.class) != null
                || locked.step().get("artifactRevision", Integer.class) != null) {
            throw invalid("问答 Step 与冻结的只读无评审执行计划不一致");
        }
        String writingSessionId = locked.run().get("writingSessionId", String.class);
        if (writingSessionId == null || writingSessionId.isBlank()) {
            throw invalid("问答 Run 缺少写作会话归属");
        }
    }

    private static String validateChatAnswerOutput(
            ExecutionPlanSnapshot.OutputSchema providerSchema,
            Map<String, Object> output) {
        try {
            WorkflowOutputValidator.validate(providerSchema.jsonSchema(), output);
        } catch (IllegalArgumentException exception) {
            throw invalid("问答 output 不符合冻结 Schema");
        }
        if (!output.keySet().equals(java.util.Set.of("answer"))) {
            throw invalid("问答 output 必须精确包含 answer 字段");
        }
        Object answer = output.get("answer");
        if (!(answer instanceof String text) || text.isBlank()) {
            throw invalid("问答 answer 不能为空白文本");
        }
        return text;
    }

    private String persistChatAnswer(
            DSLContext transaction,
            Locked locked,
            ExecutionPlanSnapshot.Step frozenStep,
            String answer,
            String resultHash,
            LocalDateTime now) {
        String sessionId = locked.run().get("writingSessionId", String.class);
        Record session = transaction.fetchOne(
                """
                SELECT "updatedAt" FROM public."WritingSession"
                WHERE id = ? AND "novelId" = ? AND "chapterId" = ?
                FOR UPDATE
                """,
                sessionId,
                locked.run().get("novelId", String.class),
                locked.run().get("chapterId", String.class));
        if (session == null) {
            throw invalid("问答 Run 绑定的写作会话不存在或范围不一致");
        }
        String messageId = ids.next();
        String agentId = "编辑";
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("engineVersion", 2);
        source.put("runId", locked.run().get("id", String.class));
        source.put("operation", locked.run().get("operation", String.class));
        source.put("stepId", locked.step().get("id", String.class));
        source.put("modelProfile", frozenStep.modelProfile().profile());
        source.put("resultHash", resultHash);
        source.put("outcomeType", "chat_answer");
        String metadata = WorkflowMessageMetadata.serialize(
                locked.run().get("id", String.class),
                "done",
                answer,
                agentId,
                Collections.unmodifiableMap(source),
                json);
        transaction.execute(
                """
                INSERT INTO public."WritingMessage" (
                  id, "sessionId", role, "agentId", content, metadata, "createdAt"
                ) VALUES (?, ?, 'agent', ?, ?, ?, ?)
                """,
                messageId,
                sessionId,
                agentId,
                answer,
                metadata,
                now);
        LocalDateTime sessionUpdatedAt = DatabaseTimestamp.next(
                clock, session.get("updatedAt", LocalDateTime.class));
        transaction.execute(
                "UPDATE public.\"WritingSession\" SET \"updatedAt\" = ? WHERE id = ?",
                sessionUpdatedAt,
                sessionId);
        return messageId;
    }

    private static void validateSelectionGenerationOutput(
            ExecutionPlanSnapshot.OutputSchema providerSchema,
            Map<String, Object> output) {
        Map<String, Object> providerOutput = new LinkedHashMap<>(output);
        Object derivedHash = providerOutput.remove("contentSha256");
        String replacement;
        try {
            WorkflowOutputValidator.validate(
                    providerSchema.jsonSchema(), Collections.unmodifiableMap(providerOutput));
            replacement = string(providerOutput, "replacement");
        } catch (IllegalArgumentException exception) {
            throw invalid("generation output 不符合冻结 Schema");
        }
        if (replacement.isBlank()) {
            throw invalid("generation replacement 不能为空白文本");
        }
        if (!(derivedHash instanceof String contentSha256)
                || !sha256(replacement).equals(contentSha256)) {
            throw invalid("Agent 派生的 replacement 哈希与 Core 复算不一致");
        }
    }

    private void completeReview(
            DSLContext transaction,
            Locked locked,
            ExecutionStepResult body,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        if (body.getResultKind() != ExecutionStepResult.ResultKindEnum.EVALUATION
                || body.getEvaluation() == null) {
            throw invalid("review Step 只接受 evaluation 结果");
        }
        EvidenceEvaluation evaluation = body.getEvaluation();
        validateEvaluation(transaction, locked, evaluation, body.getResolvedModel());
        ExecutionPlanSnapshot executionPlan = executionPlan(locked.run());
        ExecutionPlanSnapshot.Step frozenStep = frozenStep(locked, executionPlan);
        WorkflowOutputValidator.validate(
                frozenStep.outputSchema().jsonSchema(),
                WorkflowCallbackValues.reviewerOutput(evaluation));
        insertEvaluation(transaction, locked, evaluation, now);
        completeStep(
                transaction,
                locked,
                body.getResultHash(),
                usage,
                canonicalJson(WorkflowCallbackValues.evaluationMap(evaluation)),
                locked.step().get("artifactId", String.class),
                locked.step().get("artifactRevision", Integer.class),
                now);
        long sequence = appendStepFinished(
                transaction,
                locked,
                "completed",
                null,
                locked.run().get("lastEventSequence", Long.class),
                now);
        convergeReviewers(transaction, locked, sequence, now);
    }

    private void validateEvaluation(
            DSLContext transaction,
            Locked locked,
            EvidenceEvaluation evaluation,
            ResolvedModelRef outerResolvedModel) {
        if (!Objects.equals(evaluation.getRunId(), locked.run().get("id", String.class))
                || !Objects.equals(evaluation.getStepId(), locked.step().get("id", String.class))
                || !Objects.equals(
                        evaluation.getEvidenceBundleId(),
                        locked.step().get("evidenceBundleId", String.class))
                || !Objects.equals(
                        WorkflowCallbackValues.optional(evaluation.getArtifactId()),
                        locked.step().get("artifactId", String.class))
                || !Objects.equals(
                        WorkflowCallbackValues.optional(evaluation.getArtifactRevision()),
                        locked.step().get("artifactRevision", Integer.class))) {
            throw invalid("Evaluation 与当前 Run/Step/Evidence/Artifact 绑定不一致");
        }
        if (!WorkflowCallbackValues.resolvedModelMap(evaluation.getResolvedModel())
                .equals(WorkflowCallbackValues.resolvedModelMap(outerResolvedModel))) {
            throw invalid("Evaluation 与终报解析模型不一致");
        }
        ExecutionPlanSnapshot executionPlan = executionPlan(locked.run());
        ExecutionPlanSnapshot.Step frozenStep = frozenStep(locked, executionPlan);
        if (!frozenStep.modelProfile().toMap().equals(
                WorkflowCallbackValues.modelProfileMap(evaluation.getEvaluatorProfile()))) {
            throw invalid("Evaluation evaluatorProfile 超出 Step 逻辑授权");
        }
        if (!Objects.equals(
                evaluation.getRubricVersion(), executionPlan.reviewPolicy().rubricVersion())) {
            throw invalid("Evaluation rubricVersion 与冻结执行计划不一致");
        }
        if (evaluation.getExecutionStatus() != EvidenceEvaluation.ExecutionStatusEnum.COMPLETED) {
            throw invalid("成功 reviewer result 必须携带 completed Evaluation");
        }
        validateEvidenceReferences(transaction, evaluation);
    }

    private void validateEvidenceReferences(
            DSLContext transaction, EvidenceEvaluation evaluation) {
        List<EvaluationFinding> findings = evaluation.getFindings() == null
                ? List.of()
                : evaluation.getFindings();
        for (EvaluationFinding finding : findings) {
            for (EvaluationEvidenceReference reference : Objects.requireNonNull(
                    finding.getEvidence(), "Evaluation finding 缺少 evidence")) {
                Record evidence = transaction.fetchOne(
                        """
                        SELECT "contentSha256" FROM public."WorkflowEvidenceItem"
                        WHERE id = ? AND "bundleId" = ? AND exists
                        """,
                        reference.getEvidenceItemId(),
                        evaluation.getEvidenceBundleId());
                if (evidence == null
                        || !Objects.equals(
                                evidence.get("contentSha256", String.class),
                                reference.getContentSha256())) {
                    throw invalid("Reviewer 引用了不属于当前 Bundle 的 Evidence");
                }
            }
        }
    }

    private Artifact materializeSelection(
            DSLContext transaction,
            Locked locked,
            ExecutionPlanSnapshot executionPlan,
            Map<String, Object> output,
            String generationResultHash,
            LocalDateTime now) {
        if (!"long_serial.rewrite_chapter_selection"
                        .equals(executionPlan.operation().key())
                || !"apply.chapter_selection.v1"
                        .equals(executionPlan.operation().applyHandler())
                || !executionPlan.operation().deterministicValidators().containsAll(List.of(
                        "validator.schema_strict.v1",
                        "validator.unicode_selection.v1",
                        "validator.selection_source_hash.v1",
                        "validator.selection_outside_unchanged.v1"))) {
            throw invalid("首个 callback 纵切只支持长篇章节选区改写");
        }
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        String chapterId = locked.run().get("chapterId", String.class);
        Record evidence = transaction.fetchOne(
                """
                SELECT id, "resourceId", "resourceUpdatedAt", "contentText", "contentSha256", "rangeJson"
                FROM public."WorkflowEvidenceItem"
                WHERE "bundleId" = ? AND "resourceType" = 'chapter_content'
                  AND "resourceId" = ? AND exists AND "contentType" = 'text'
                """,
                bundleId,
                chapterId);
        if (evidence == null || evidence.get("rangeJson", String.class) == null) {
            throw invalid("选区改写 Evidence 缺少完整正文或码点范围");
        }
        String replacement = string(output, "replacement");
        String replacementHash = string(output, "contentSha256");
        if (!sha256(replacement).equals(replacementHash)) {
            throw invalid("选区替换文本与 contentSha256 不一致");
        }
        String source = evidence.get("contentText", String.class);
        Map<String, Object> range = readObject(evidence.get("rangeJson", String.class));
        int start = integer(range, "startCodePoint");
        int end = integer(range, "endCodePoint");
        int sourceLength = source.codePointCount(0, source.length());
        if (start < 0 || end <= start || end > sourceLength) {
            throw invalid("选区 Evidence 码点范围无效");
        }
        Map<String, Object> runInput = readObject(locked.run().get("input", String.class));
        requireOptionalInteger(runInput, "selectionStart", start);
        requireOptionalInteger(runInput, "selectionEnd", end);
        String selected = slice(source, start, end);
        String selectedHash = sha256(selected);
        requireOptionalHash(runInput, "selectedTextSha256", selectedHash);
        requireOptionalHash(runInput, "selectedTextHash", selectedHash);
        String prefix = slice(source, 0, start);
        String suffix = slice(source, end, sourceLength);
        String candidate = prefix + replacement + suffix;
        String baseHash = evidence.get("contentSha256", String.class);
        DurableSelectionArtifact.Stored stored = DurableSelectionArtifact.create(
                bundleId,
                evidence.get("id", String.class),
                chapterId,
                DatabaseTimestamp.api(evidence.get("resourceUpdatedAt", LocalDateTime.class)),
                baseHash,
                start,
                end,
                selectedHash,
                replacement,
                replacementHash,
                sha256(candidate),
                locked.step().get("id", String.class),
                generationResultHash);

        String profile = locked.step().get("modelProfile", String.class);
        String payloadJson = canonicalJson(stored.payload());
        String diffJson = canonicalJson(stored.diff());
        String artifactId = locked.step().get("artifactId", String.class);
        Integer expectedRevision = locked.step().get("artifactRevision", Integer.class);
        int revision;
        if (artifactId == null && expectedRevision == null) {
            artifactId = ids.next();
            revision = 1;
            transaction.execute(
                    """
                    INSERT INTO public."ReviewArtifact" (
                      id, "novelId", "chapterId", "taskId", "workflowRunId", "artifactKey",
                      kind, status, title, summary, "payloadJson", "diffJson",
                      "createdByAgent", "updatedByAgent", "reviewerAgent", revision,
                      "createdAt", "updatedAt"
                    ) VALUES (
                      ?, ?, ?, NULL, ?, ?, CAST('chapter_draft' AS "ReviewArtifactKind"),
                      CAST('under_review' AS "ReviewArtifactStatus"), ?, NULL, ?, ?, ?, ?, NULL, 1, ?, ?
                    )
                    """,
                    artifactId,
                    locked.run().get("novelId", String.class),
                    chapterId,
                    locked.run().get("id", String.class),
                    "workflow:" + locked.run().get("id", String.class) + ":candidate",
                    "章节选区改写",
                    payloadJson,
                    diffJson,
                    profile,
                    profile,
                    now,
                    now);
        } else if (artifactId != null && expectedRevision != null) {
            Record head = transaction.fetchOne(
                    """
                    SELECT id, revision FROM public."ReviewArtifact"
                    WHERE id = ? AND "workflowRunId" = ? AND "novelId" = ?
                    FOR UPDATE
                    """,
                    artifactId,
                    locked.run().get("id", String.class),
                    locked.run().get("novelId", String.class));
            if (head == null || !Objects.equals(head.get("revision", Integer.class), expectedRevision)) {
                throw invalid("返工 generation Step 引用的 Artifact revision 已过期");
            }
            revision = Math.addExact(expectedRevision, 1);
            int updated = transaction.execute(
                    """
                    UPDATE public."ReviewArtifact"
                    SET status = CAST('under_review' AS "ReviewArtifactStatus"),
                        "payloadJson" = ?, "diffJson" = ?, "updatedByAgent" = ?,
                        "reviewerAgent" = NULL, revision = ?, "updatedAt" = ?
                    WHERE id = ? AND "workflowRunId" = ? AND revision = ?
                    """,
                    payloadJson,
                    diffJson,
                    profile,
                    revision,
                    now,
                    artifactId,
                    locked.run().get("id", String.class),
                    expectedRevision);
            if (updated != 1) throw new IllegalStateException("ReviewArtifact revision CAS 失败");
        } else {
            throw invalid("generation Step 的 artifactId/artifactRevision 必须同时为空或同时存在");
        }
        transaction.execute(
                """
                INSERT INTO public."ReviewArtifactRevision" (
                  id, "artifactId", revision, summary, "payloadJson", "diffJson",
                  "createdByAgent", "createdAt"
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?)
                """,
                ids.next(),
                artifactId,
                revision,
                payloadJson,
                diffJson,
                profile,
                now);
        return new Artifact(artifactId, revision);
    }

    private List<Map<String, Object>> createReviewerSteps(
            DSLContext transaction,
            Locked locked,
            ExecutionPlanSnapshot executionPlan,
            Artifact artifact,
            Map<String, Object> candidate,
            LocalDateTime now) {
        if (executionPlan.reviewers().isEmpty()) {
            throw invalid("首个选区改写纵切必须具有 Reviewer");
        }
        Record bundle = transaction.fetchOne(
                """
                SELECT id, version, "manifestSha256" FROM public."WorkflowEvidenceBundle"
                WHERE id = ? AND "runId" = ?
                """,
                locked.step().get("evidenceBundleId", String.class),
                locked.run().get("id", String.class));
        if (bundle == null) throw invalid("Reviewer Step 缺少 Evidence bundle");
        int ordinal = transaction.fetchOne(
                        "SELECT max(ordinal) AS ordinal FROM public.\"WorkflowStep\" WHERE \"runId\" = ?",
                        locked.run().get("id", String.class))
                .get("ordinal", Integer.class);
        List<Map<String, Object>> reviewerSteps = new ArrayList<>();
        Map<String, Object> originalRunInput = readObject(
                locked.run().get("input", String.class));
        Map<String, Object> task = new LinkedHashMap<>();
        task.put("workflow", locked.run().get("workflow", String.class));
        task.put("operation", locked.run().get("operation", String.class));
        for (String key : List.of(
                "target",
                "scope",
                "selectionTarget",
                "targetWordCount",
                "userInstruction",
                "selectionStart",
                "selectionEnd",
                "selectedTextSha256")) {
            if (originalRunInput.containsKey(key)) task.put(key, originalRunInput.get(key));
        }
        Object userInstruction = task.get("userInstruction");
        if (userInstruction != null && !(userInstruction instanceof String)) {
            throw invalid("Run 的 userInstruction 必须是字符串或 null");
        }
        task.put("rubricVersion", executionPlan.reviewPolicy().rubricVersion());
        Map<String, Object> inputValues = new LinkedHashMap<>();
        inputValues.put("task", Collections.unmodifiableMap(task));
        inputValues.put(
                "candidate",
                Collections.unmodifiableMap(new LinkedHashMap<>(candidate)));
        Map<String, Object> input = Collections.unmodifiableMap(inputValues);
        String inputHash = ExecutionCanonicalJson.sha256(input);
        for (ExecutionPlanSnapshot.Step reviewer : executionPlan.reviewers()) {
            String stepId = ids.next();
            String idempotencyKey = locked.run().get("id", String.class) + "." + stepId;
            Map<String, Object> logicalProfile = reviewer.modelProfile().toMap();
            Map<String, Object> outputSchema = reviewer.outputSchema().toMap();
            Map<String, Object> budget = reviewer.stepBudget().budgetMap();
            String requestHash = ExecutionCanonicalJson.sha256(stepRequestMaterial(
                    locked.run(),
                    stepId,
                    idempotencyKey,
                    inputHash,
                    bundle,
                    reviewer.evidencePolicy(),
                    reviewer.lane(),
                    logicalProfile,
                    outputSchema,
                    budget,
                    artifact));
            Map<String, Object> storedBudget = reviewer.stepBudget().stored();
            transaction.execute(
                    """
                    INSERT INTO public."WorkflowStep" (
                      id, "runId", "agentId", "stepType", status, input, "createdAt",
                      ordinal, purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken",
                      "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                      "artifactId", "artifactRevision", "modelProfile", "modelProfileVersion",
                      "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt"
                    ) VALUES (
                      ?, ?, ?, CAST('agent' AS "WorkflowStepType"),
                      CAST('pending' AS "WorkflowStepStatus"), ?, ?, ?, 'review', ?, 0, ?, 0,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    stepId,
                    locked.run().get("id", String.class),
                    reviewer.modelProfile().profile(),
                    canonicalJson(input),
                    now,
                    ++ordinal,
                    reviewer.lane(),
                    now,
                    idempotencyKey,
                    requestHash,
                    inputHash,
                    bundle.get("id", String.class),
                    artifact.id(),
                    artifact.revision(),
                    reviewer.modelProfile().profile(),
                    Integer.toString(reviewer.modelProfile().version()),
                    reviewer.outputSchema().name(),
                    Integer.toString(reviewer.outputSchema().version()),
                    json.writeValueAsString(storedBudget),
                    now,
                    now);
            reviewerSteps.add(Map.of(
                    "stepId", stepId,
                    "ordinal", ordinal,
                    "purpose", REVIEW,
                    "lane", reviewer.lane(),
                    "modelProfile", logicalProfile,
                    "status", "pending",
                    "attemptCount", 0,
                    "fencingToken", 0));
        }
        return List.copyOf(reviewerSteps);
    }

    private void insertEvaluation(
            DSLContext transaction,
            Locked locked,
            EvidenceEvaluation evaluation,
            LocalDateTime now) {
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvaluation" (
                  id, "runId", "stepId", "evidenceBundleId", "artifactId", "artifactRevision",
                  "evaluatorProfile", "rubricVersion", "executionStatus", "contentVerdict",
                  "findingsJson", "createdAt"
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                evaluation.getEvaluationId(),
                locked.run().get("id", String.class),
                locked.step().get("id", String.class),
                locked.step().get("evidenceBundleId", String.class),
                locked.step().get("artifactId", String.class),
                locked.step().get("artifactRevision", Integer.class),
                locked.step().get("modelProfile", String.class),
                evaluation.getRubricVersion(),
                evaluation.getExecutionStatus().getValue(),
                evaluation.getContentVerdict().getValue(),
                canonicalJson(WorkflowCallbackValues.reviewerOutput(evaluation).get("findings")),
                now);
    }

    private void insertFailedEvaluation(
            DSLContext transaction, Locked locked, LocalDateTime now) {
        ExecutionPlanSnapshot executionPlan = executionPlan(locked.run());
        frozenStep(locked, executionPlan);
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvaluation" (
                  id, "runId", "stepId", "evidenceBundleId", "artifactId", "artifactRevision",
                  "evaluatorProfile", "rubricVersion", "executionStatus", "contentVerdict",
                  "findingsJson", "createdAt"
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'failed', 'cannot_assess', '[]', ?)
                """,
                ids.next(),
                locked.run().get("id", String.class),
                locked.step().get("id", String.class),
                locked.step().get("evidenceBundleId", String.class),
                locked.step().get("artifactId", String.class),
                locked.step().get("artifactRevision", Integer.class),
                locked.step().get("modelProfile", String.class),
                executionPlan.reviewPolicy().rubricVersion(),
                now);
    }

    private void convergeReviewers(
            DSLContext transaction, Locked locked, long sequence, LocalDateTime now) {
        List<Record> steps = transaction.fetch(
                """
                SELECT id, ordinal, status::text AS status
                FROM public."WorkflowStep"
                WHERE "runId" = ? AND purpose = 'review'
                  AND "artifactId" = ? AND "artifactRevision" = ?
                ORDER BY ordinal
                """,
                locked.run().get("id", String.class),
                locked.step().get("artifactId", String.class),
                locked.step().get("artifactRevision", Integer.class));
        ExecutionPlanSnapshot executionPlan = executionPlan(locked.run());
        if (!"review.merge_all_pass_else_author.v1"
                        .equals(executionPlan.reviewPolicy().mergePolicy())
                || !"awaiting_user"
                        .equals(executionPlan.reviewPolicy().onUnavailable())) {
            throw new IllegalStateException("当前 Core 不支持冻结执行计划的 Reviewer 收敛策略");
        }
        if (steps.size() != executionPlan.reviewers().size()
                || steps.stream().anyMatch(step -> !isTerminalStep(step.get("status", String.class)))) {
            updateRun(
                    transaction,
                    locked.run().get("id", String.class),
                    "running",
                    sequence,
                    null,
                    null,
                    now);
            return;
        }
        List<Record> evaluations = transaction.fetch(
                """
                SELECT evaluation.id, evaluation."executionStatus", evaluation."contentVerdict",
                       step.ordinal
                FROM public."WorkflowEvaluation" AS evaluation
                JOIN public."WorkflowStep" AS step ON step.id = evaluation."stepId"
                WHERE evaluation."runId" = ? AND evaluation."artifactId" = ?
                  AND evaluation."artifactRevision" = ?
                ORDER BY step.ordinal
                """,
                locked.run().get("id", String.class),
                locked.step().get("artifactId", String.class),
                locked.step().get("artifactRevision", Integer.class));
        if (evaluations.size() != steps.size()) {
            throw new IllegalStateException("已终态 Reviewer Step 缺少权威 Evaluation");
        }
        long completed = evaluations.stream()
                .filter(value -> "completed".equals(value.get("executionStatus", String.class)))
                .count();
        String availability = completed == 0
                ? "unavailable"
                : completed == evaluations.size() ? "complete" : "partial";
        String verdict = evaluations.stream()
                        .anyMatch(value -> "issues_found"
                                .equals(value.get("contentVerdict", String.class)))
                ? "issues_found"
                : evaluations.stream().anyMatch(value -> "cannot_assess"
                                .equals(value.get("contentVerdict", String.class)))
                        ? "cannot_assess"
                        : "pass";
        if ("unavailable".equals(availability)) verdict = "cannot_assess";
        List<String> evaluationIds = evaluations.stream()
                .map(value -> value.get("id", String.class))
                .toList();
        String artifactId = locked.step().get("artifactId", String.class);
        int artifactRevision = locked.step().get("artifactRevision", Integer.class);
        transaction.execute(
                """
                UPDATE public."ReviewArtifact"
                SET status = CAST('awaiting_user' AS "ReviewArtifactStatus"), "updatedAt" = ?
                WHERE id = ? AND "workflowRunId" = ? AND revision = ?
                """,
                now,
                artifactId,
                locked.run().get("id", String.class),
                artifactRevision);
        sequence = appendEvent(
                transaction,
                locked.run().get("id", String.class),
                sequence,
                "review_completed",
                Map.of(
                        "artifactId", artifactId,
                        "artifactRevision", artifactRevision,
                        "evaluationIds", evaluationIds,
                        "mergedVerdict", verdict,
                        "reviewAvailability", availability),
                "review:completed:" + artifactId + ":" + artifactRevision,
                now);
        sequence = appendEvent(
                transaction,
                locked.run().get("id", String.class),
                sequence,
                "awaiting_user",
                Map.of(
                        "artifactId", artifactId,
                        "artifactRevision", artifactRevision,
                        "allowedDecisions", List.of("approve", "discard", "revise"),
                        "reviewAvailability", availability),
                "awaiting:user:" + artifactId + ":" + artifactRevision,
                now);
        updateRun(
                transaction,
                locked.run().get("id", String.class),
                "waiting_user",
                sequence,
                null,
                null,
                now);
    }

    private void completeStep(
            DSLContext transaction,
            Locked locked,
            String resultHash,
            WorkflowStepUsage usage,
            String output,
            String artifactId,
            Integer artifactRevision,
            LocalDateTime now) {
        transaction.execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('completed' AS "WorkflowStepStatus"), output = ?,
                    "resultHash" = ?, "usageJson" = ?, "artifactId" = ?, "artifactRevision" = ?,
                    "activeJobId" = NULL, "leaseExpiresAt" = NULL, "completedAt" = ?,
                    "updatedAt" = ?, "errorCode" = NULL
                WHERE id = ? AND "runId" = ?
                """,
                output,
                resultHash,
                json.writeValueAsString(WorkflowCallbackValues.usageMap(usage)),
                artifactId,
                artifactRevision,
                now,
                now,
                locked.step().get("id", String.class),
                locked.run().get("id", String.class));
    }

    private void failStep(
            DSLContext transaction,
            Locked locked,
            ExecutionStepFailure failure,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        transaction.execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('failed' AS "WorkflowStepStatus"), "resultHash" = ?,
                    "usageJson" = ?, "activeJobId" = NULL, "leaseExpiresAt" = NULL,
                    "completedAt" = ?, "updatedAt" = ?, "errorCode" = ?
                WHERE id = ? AND "runId" = ?
                """,
                failure.getResultHash(),
                json.writeValueAsString(WorkflowCallbackValues.usageMap(usage)),
                now,
                now,
                failure.getErrorCode(),
                locked.step().get("id", String.class),
                locked.run().get("id", String.class));
    }

    private void failRejectedStep(
            DSLContext transaction,
            Locked locked,
            String errorCode,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        transaction.execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('failed' AS "WorkflowStepStatus"),
                    "usageJson" = ?, "activeJobId" = NULL, "leaseExpiresAt" = NULL,
                    "completedAt" = ?, "updatedAt" = ?, "errorCode" = ?
                WHERE id = ? AND "runId" = ?
                """,
                json.writeValueAsString(WorkflowCallbackValues.usageMap(usage)),
                now,
                now,
                errorCode,
                locked.step().get("id", String.class),
                locked.run().get("id", String.class));
    }

    private void failRun(
            DSLContext transaction,
            Locked locked,
            String errorCode,
            Boolean outcomeUnknown,
            long previousSequence,
            LocalDateTime now) {
        long sequence = appendEvent(
                transaction,
                locked.run().get("id", String.class),
                previousSequence,
                "failed",
                Map.of(
                        "errorCode", errorCode,
                        "failedStepId", locked.step().get("id", String.class),
                        "outcomeUnknown", Boolean.TRUE.equals(outcomeUnknown)),
                "run:failed",
                now);
        updateRun(
                transaction,
                locked.run().get("id", String.class),
                "failed",
                sequence,
                errorCode,
                now,
                now);
    }

    private void skipCancelledResult(
            DSLContext transaction,
            Locked locked,
            String resultHash,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        usage = billing.settleTerminal(
                transaction,
                locked.run().get("id", String.class),
                locked.step().get("id", String.class),
                usage,
                now);
        transaction.execute(
                """
                UPDATE public."WorkflowStep"
                SET status = CAST('skipped' AS "WorkflowStepStatus"), "resultHash" = ?,
                    "usageJson" = ?, "activeJobId" = NULL, "leaseExpiresAt" = NULL,
                    "completedAt" = ?, "updatedAt" = ?, "errorCode" = 'RUN_CANCELLED'
                WHERE id = ? AND "runId" = ?
                """,
                resultHash,
                json.writeValueAsString(WorkflowCallbackValues.usageMap(usage)),
                now,
                now,
                locked.step().get("id", String.class),
                locked.run().get("id", String.class));
        long sequence = appendStepFinished(
                transaction,
                locked,
                "skipped",
                null,
                locked.run().get("lastEventSequence", Long.class),
                now);
        int active = transaction.fetchOne(
                        """
                        SELECT count(*) AS count FROM public."WorkflowStep"
                        WHERE "runId" = ? AND status IN ('pending', 'running')
                        """,
                        locked.run().get("id", String.class))
                .get("count", Integer.class);
        if (active > 0) {
            updateRun(
                    transaction,
                    locked.run().get("id", String.class),
                    "running",
                    sequence,
                    null,
                    null,
                    now);
            return;
        }
        String cancelRequestId = locked.run().get("cancelRequestId", String.class);
        if (cancelRequestId == null) {
            throw new IllegalStateException("正在取消的 Run 缺少 cancelRequestId");
        }
        sequence = appendEvent(
                transaction,
                locked.run().get("id", String.class),
                sequence,
                "cancelled",
                Map.of(
                        "cancelRequestId", cancelRequestId,
                        "cancelledStepId", locked.step().get("id", String.class)),
                "run:cancelled",
                now);
        updateRun(
                transaction,
                locked.run().get("id", String.class),
                "cancelled",
                sequence,
                "RUN_CANCELLED",
                now,
                now);
    }

    private Locked lock(DSLContext transaction, String runId, String stepId) {
        Record run = transaction.fetchOne(
                """
                SELECT id, "novelId", "chapterId", "writingSessionId", input, workflow, operation,
                       "operationCatalogVersion", "modelPolicyJson",
                       status::text AS status, "cancelRequestId", "cancelRequestedAt",
                       "lastEventSequence", revision
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2
                FOR UPDATE
                """,
                runId);
        if (run == null) throw notFound();
        Record step = transaction.fetchOne(
                """
                SELECT id, "runId", status::text AS status, input, ordinal, purpose, lane,
                       "attemptCount", "fencingToken", "activeJobId", "requestHash", "inputHash",
                       "resultHash", "evidenceBundleId", "artifactId", "artifactRevision",
                       "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion",
                       "budgetJson", "resolvedModelJson", "usageJson", "lastProgressSequence",
                       "cancelRequestId"
                FROM public."WorkflowStep"
                WHERE id = ? AND "runId" = ?
                FOR UPDATE
                """,
                stepId,
                runId);
        if (step == null) throw notFound();
        return new Locked(run, step);
    }

    private void requireCommonBinding(
            Locked locked,
            String jobId,
            Integer fencingToken,
            String requestHash,
            String novelId) {
        if (!Objects.equals(locked.run().get("novelId", String.class), novelId)
                || !Objects.equals(locked.step().get("requestHash", String.class), requestHash)) {
            throw invalid("Workflow callback 资源或 requestHash 绑定不一致");
        }
        if (jobId == null || fencingToken == null || fencingToken < 1) {
            throw invalid("Workflow callback job/fence 无效");
        }
    }

    private void requireTerminalBinding(
            DSLContext transaction,
            Locked locked,
            String jobId,
            Integer fencingToken,
            String requestHash,
            String inputHash,
            String novelId,
            ResolvedModelRef resolvedModel) {
        requireCommonBinding(locked, jobId, fencingToken, requestHash, novelId);
        if (!Objects.equals(locked.step().get("inputHash", String.class), inputHash)) {
            throw invalid("Workflow callback inputHash 绑定不一致");
        }
        requireResolvedBinding(
                transaction, locked, jobId, fencingToken, requestHash, resolvedModel);
    }

    private WorkflowResolvedModel requireResolvedBinding(
            DSLContext transaction,
            Locked locked,
            String jobId,
            Integer fencingToken,
            String requestHash,
            ResolvedModelRef resolvedModel) {
        WorkflowResolvedModel resolved = WorkflowCallbackValues.resolvedModel(resolvedModel);
        ExecutionPlanSnapshot.Step frozenStep = frozenStep(
                locked, executionPlan(locked.run()));
        resolved.requireAuthorizedBy(frozenStep.modelProfile().toDomain());
        Map<String, Object> serialized = WorkflowCallbackValues.resolvedModelMap(resolved);
        String frozenJson = locked.step().get("resolvedModelJson", String.class);
        if (frozenJson == null) {
            // submit 先启动异步执行再回 202，极快 terminal callback 可能先于 recordAccepted。
            // 只有仍命中当前 job/fence 的终报可以代替 Accepted 原子冻结解析模型。
            if (!matchesFence(locked.step(), jobId, fencingToken)) return resolved;
            int updated = transaction.execute(
                    """
                    UPDATE public."WorkflowStep"
                    SET "resolvedModelJson" = ?, "updatedAt" = ?
                    WHERE id = ? AND "runId" = ? AND "resolvedModelJson" IS NULL
                      AND "activeJobId" = ? AND "fencingToken" = ? AND "requestHash" = ?
                    """,
                    json.writeValueAsString(serialized),
                    DatabaseTimestamp.now(clock),
                    locked.step().get("id", String.class),
                    locked.run().get("id", String.class),
                    jobId,
                    fencingToken.longValue(),
                    requestHash);
            if (updated != 1) throw new IllegalStateException("Workflow 解析模型冻结 CAS 失败");
            return resolved;
        }
        if (!readObject(frozenJson).equals(serialized)) {
            throw invalid("Workflow callback resolvedModel 与受理冻结不一致");
        }
        return resolved;
    }

    private UsageValidation requireUsage(
            Record step, cn.inkforge.contracts.api.StepUsage dto) {
        WorkflowStepUsage usage;
        try {
            usage = WorkflowCallbackValues.usage(dto);
        } catch (IllegalArgumentException | ArithmeticException exception) {
            throw invalid("Workflow callback usage 非法：" + exception.getMessage());
        }
        WorkflowStepUsage previous = storedUsage(step);
        try {
            if (previous != null) usage.requireMonotonicAfter(previous);
        } catch (IllegalArgumentException | ArithmeticException exception) {
            throw invalid("Workflow callback usage 非单调累计：" + exception.getMessage());
        }
        Map<String, Object> storedBudget = readObject(step.get("budgetJson", String.class));
        Map<String, Object> budget = object(storedBudget.get("budget"), "Step budget");
        WorkflowStepBudget frozenBudget = new WorkflowStepBudget(
                        integer(budget, "maxModelCalls"),
                        longInteger(budget, "maxInputTokens"),
                        longInteger(budget, "maxPromptCacheMissTokens"),
                        longInteger(budget, "maxCompletionTokens"),
                        longInteger(budget, "maxReasoningTokens"),
                        longInteger(budget, "maxVisibleOutputTokens"),
                        longInteger(budget, "maxCostMicros"),
                        longInteger(budget, "maxWallClockSeconds"),
                        integer(budget, "maxProviderRetries"),
                        integer(budget, "maxProtocolCorrections"));
        try {
            frozenBudget.requireWithin(usage);
            return new UsageValidation(usage, null);
        } catch (WorkflowBudgetExceededException exception) {
            return new UsageValidation(usage, exception.dimension());
        }
    }

    private static void requireWithinBudget(UsageValidation validation, String callbackKind) {
        if (validation.exceededDimension() != null) {
            throw invalid(callbackKind + " usage 超过冻结 Step 预算："
                    + validation.exceededDimension());
        }
    }

    private static void requireBudgetFailureBinding(
            ExecutionStepFailure failure, UsageValidation validation) {
        boolean declared = "STEP_BUDGET_EXCEEDED".equals(failure.getErrorCode());
        boolean exceeded = validation.exceededDimension() != null;
        if (declared != exceeded) {
            throw invalid(exceeded
                    ? "超预算 usage 只能通过 STEP_BUDGET_EXCEEDED Failure 入账"
                    : "STEP_BUDGET_EXCEEDED Failure 缺少可证明的超预算 usage");
        }
        if (declared
                && failure.getErrorCategory()
                        != ExecutionStepFailure.ErrorCategoryEnum.VALIDATION
                && failure.getErrorCategory()
                        != ExecutionStepFailure.ErrorCategoryEnum.CANCELLED) {
            throw invalid("STEP_BUDGET_EXCEEDED 必须使用 validation 或 cancelled 错误类别");
        }
    }

    private static Map<String, Object> resultHashMaterial(ExecutionStepResult result) {
        try {
            return WorkflowCallbackValues.resultHashMaterial(result);
        } catch (IllegalArgumentException | ArithmeticException | NullPointerException exception) {
            throw invalid("Execution Result 非法：" + exception.getMessage());
        }
    }

    private static Map<String, Object> failureHashMaterial(ExecutionStepFailure failure) {
        try {
            return WorkflowCallbackValues.failureHashMaterial(failure);
        } catch (IllegalArgumentException | ArithmeticException | NullPointerException exception) {
            throw invalid("Execution Failure 非法：" + exception.getMessage());
        }
    }

    private static void requireHash(
            String actual, Map<String, Object> material, String label) {
        try {
            WorkflowCallbackValues.requireHash(actual, material, label);
        } catch (IllegalArgumentException exception) {
            throw invalid("Execution callback hash 非法：" + exception.getMessage());
        }
    }

    private WorkflowStepUsage storedUsage(Record step) {
        String value = step.get("usageJson", String.class);
        if (value == null) return null;
        Map<String, Object> usage = readObject(value);
        return new WorkflowStepUsage(
                cn.inkforge.core.workflows.domain.WorkflowUsageStatus.fromWireValue(
                        string(usage, "usageStatus")),
                nullableLong(usage, "inputTokens"),
                nullableLong(usage, "cachedTokens"),
                nullableLong(usage, "promptCacheMissTokens"),
                nullableLong(usage, "completionTokens"),
                nullableLong(usage, "reasoningTokens"),
                nullableLong(usage, "visibleOutputTokens"),
                nullableLong(usage, "costMicros"),
                integer(usage, "providerAttempts"),
                integer(usage, "protocolCorrections"),
                longInteger(usage, "wallTimeMillis"));
    }

    private ExecutionPlanSnapshot executionPlan(Record run) {
        ExecutionPlanSnapshot result = ExecutionPlanSnapshot.fromStored(
                readObject(run.get("modelPolicyJson", String.class)));
        result.requireOperation(
                run.get("workflow", String.class),
                run.get("operation", String.class),
                run.get("operationCatalogVersion", String.class));
        return result;
    }

    private ExecutionPlanSnapshot.Step frozenStep(
            Locked locked, ExecutionPlanSnapshot executionPlan) {
        return executionPlan.requireStep(
                locked.step().get("purpose", String.class),
                locked.step().get("lane", String.class),
                locked.step().get("modelProfile", String.class),
                Integer.parseInt(locked.step().get("modelProfileVersion", String.class)),
                locked.step().get("outputSchema", String.class),
                Integer.parseInt(locked.step().get("outputSchemaVersion", String.class)),
                readObject(locked.step().get("budgetJson", String.class)));
    }

    private long appendEvent(
            DSLContext transaction,
            String runId,
            long previous,
            String eventType,
            Map<String, Object> payload,
            String dedupeKey,
            LocalDateTime now) {
        long sequence = Math.addExact(previous, 1L);
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvent" (
                  id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ids.next(),
                runId,
                sequence,
                eventType,
                canonicalJson(payload),
                dedupeKey,
                now);
        return sequence;
    }

    private long appendStepFinished(
            DSLContext transaction,
            Locked locked,
            String status,
            String errorCode,
            long previous,
            LocalDateTime now) {
        long fencingToken = locked.step().get("fencingToken", Long.class);
        if (fencingToken < 1) {
            throw new IllegalStateException("执行终态 Step 缺少有效 fencingToken");
        }
        boolean failed = "failed".equals(status);
        if (!List.of("completed", "failed", "skipped").contains(status)
                || failed != (errorCode != null && !errorCode.isBlank())) {
            throw new IllegalArgumentException("Step 终态事件状态与错误码不一致");
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("stepId", locked.step().get("id", String.class));
        payload.put("fencingToken", Math.toIntExact(fencingToken));
        payload.put("status", status);
        payload.put("errorCode", errorCode);
        return appendEvent(
                transaction,
                locked.run().get("id", String.class),
                previous,
                "step_finished",
                payload,
                "step:finished:" + locked.step().get("id", String.class) + ":" + fencingToken,
                now);
    }

    private void updateRun(
            DSLContext transaction,
            String runId,
            String status,
            long lastEventSequence,
            String errorCode,
            LocalDateTime completedAt,
            LocalDateTime now) {
        transaction.execute(
                """
                UPDATE public."WorkflowRun"
                SET status = CAST(? AS "WorkflowRunStatus"), "lastEventSequence" = ?,
                    revision = revision + 1, "errorCode" = ?, "completedAt" = ?, "updatedAt" = ?
                WHERE id = ?
                """,
                status,
                lastEventSequence,
                errorCode,
                completedAt,
                now,
                runId);
    }

    private static Map<String, Object> stepRequestMaterial(
            Record run,
            String stepId,
            String idempotencyKey,
            String inputHash,
            Record bundle,
            String policyVersion,
            String lane,
            Map<String, Object> modelProfile,
            Map<String, Object> outputSchema,
            Map<String, Object> budget,
            Artifact artifact) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("runId", run.get("id", String.class));
        result.put("novelId", run.get("novelId", String.class));
        result.put("stepId", stepId);
        result.put("idempotencyKey", idempotencyKey);
        result.put("inputHash", inputHash);
        result.put("workflow", run.get("workflow", String.class));
        result.put("operation", run.get("operation", String.class));
        result.put("purpose", REVIEW);
        result.put("lane", lane);
        result.put(
                "evidenceManifest",
                Map.of(
                        "bundleId", bundle.get("id", String.class),
                        "bundleVersion", bundle.get("version", Integer.class),
                        "policyVersion", policyVersion,
                        "manifestSha256", bundle.get("manifestSha256", String.class)));
        result.put("modelProfile", modelProfile);
        result.put("outputSchema", outputSchema);
        result.put("budget", budget);
        result.put("artifact", Map.of(
                "artifactId", artifact.id(), "artifactRevision", artifact.revision()));
        return Collections.unmodifiableMap(result);
    }

    private static boolean matchesFence(Record step, String jobId, Integer fencingToken) {
        return Objects.equals(step.get("activeJobId", String.class), jobId)
                && fencingToken != null
                && Objects.equals(
                        step.get("fencingToken", Long.class), fencingToken.longValue());
    }

    private static ExecutionCallbackReceipt.StatusEnum staleTerminalDisposition(
            Locked locked, Integer incomingFencingToken) {
        Long current = locked.step().get("fencingToken", Long.class);
        boolean terminalWithoutAgentResult = isTerminalStep(
                        locked.step().get("status", String.class))
                && locked.step().get("resultHash", String.class) == null;
        if (incomingFencingToken != null
                && current != null
                && incomingFencingToken.longValue() == current
                && terminalWithoutAgentResult) {
            // Core 可能在当前 fence 的 Agent 终报抵达前，因取消、计费或部署门禁自行收敛
            // Step 并清除 activeJobId。资源/hash/model 已在调用此方法前验证；该终报已被
            // Core 的权威终态取代，应明确停止 Agent 重试，不能把执行日志毒化为 rejected。
            return ExecutionCallbackReceipt.StatusEnum.SUPERSEDED;
        }
        if (incomingFencingToken == null
                || current == null
                || incomingFencingToken.longValue() >= current) {
            throw invalid("Execution terminal callback 的 job/fence 身份非法");
        }
        return isTerminalStep(locked.step().get("status", String.class))
                ? ExecutionCallbackReceipt.StatusEnum.SUPERSEDED
                : ExecutionCallbackReceipt.StatusEnum.STALE;
    }

    private static boolean isTerminalStep(String status) {
        return List.of("completed", "failed", "skipped").contains(status);
    }

    private static boolean isTerminalRun(String status) {
        return List.of("completed", "failed", "cancelled").contains(status);
    }

    private static void requireRunning(Locked locked) {
        if (!"running".equals(locked.step().get("status", String.class))
                || isTerminalRun(locked.run().get("status", String.class))) {
            throw invalid("Workflow Step 尚未进入 running 或 Run 已终态");
        }
    }

    private static void requireFailureState(Locked locked, WorkflowStepUsage usage) {
        if (isTerminalRun(locked.run().get("status", String.class))) {
            throw invalid("Workflow Run 已终态");
        }
        String status = locked.step().get("status", String.class);
        if ("running".equals(status)) return;
        if ("pending".equals(status) && usage.providerAttempts() == 0) return;
        throw invalid("pending Step 只接受 providerAttempts=0 的前置失败");
    }

    private static void requireProtocol(String protocolVersion) {
        if (!"2.0".equals(protocolVersion)) throw invalid("不支持的 Execution 协议版本");
    }

    private static String requiredNovel(JsonNullable<String> value) {
        if (value == null || !value.isPresent()) {
            throw invalid("Execution callback 必须显式携带 novelId");
        }
        return value.get();
    }

    private ExecutionCallbackReceipt receipt(
            ExecutionStepProgress value, ExecutionCallbackReceipt.StatusEnum status) {
        return receipt(
                value.getRunId(),
                value.getStepId(),
                value.getJobId(),
                value.getFencingToken(),
                value.getRequestHash(),
                status);
    }

    private ExecutionCallbackReceipt receipt(
            ExecutionStepResult value, ExecutionCallbackReceipt.StatusEnum status) {
        return receipt(
                value.getRunId(),
                value.getStepId(),
                value.getJobId(),
                value.getFencingToken(),
                value.getRequestHash(),
                status);
    }

    private ExecutionCallbackReceipt receipt(
            ExecutionStepFailure value, ExecutionCallbackReceipt.StatusEnum status) {
        return receipt(
                value.getRunId(),
                value.getStepId(),
                value.getJobId(),
                value.getFencingToken(),
                value.getRequestHash(),
                status);
    }

    private ExecutionCallbackReceipt receipt(
            String runId,
            String stepId,
            String jobId,
            Integer fencingToken,
            String requestHash,
            ExecutionCallbackReceipt.StatusEnum status) {
        return new ExecutionCallbackReceipt(
                fencingToken,
                jobId,
                "2.0",
                DatabaseTimestamp.api(DatabaseTimestamp.now(clock)),
                requestHash,
                runId,
                status,
                stepId);
    }

    private String canonicalJson(Object value) {
        return new String(ExecutionCanonicalJson.bytes(value), StandardCharsets.UTF_8);
    }

    private Map<String, Object> readObject(String value) {
        return json.readValue(value, JSON_OBJECT);
    }

    private static Map<String, Object> object(Object value, String label) {
        if (!(value instanceof Map<?, ?> source)) {
            throw new IllegalStateException(label + " 必须是 JSON 对象");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : source.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalStateException(label + " key 必须是字符串");
            }
            result.put(key, entry.getValue());
        }
        return Collections.unmodifiableMap(result);
    }

    private static String string(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof String result)) {
            throw invalid(key + " 必须是字符串");
        }
        return result;
    }

    private static int integer(Map<String, Object> value, String key) {
        return Math.toIntExact(longInteger(value, key));
    }

    private static long longInteger(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Number result)) {
            throw new IllegalStateException(key + " 必须是整数");
        }
        return result.longValue();
    }

    private static Long nullableLong(Map<String, Object> value, String key) {
        return value.containsKey(key) ? longInteger(value, key) : null;
    }

    private static void requireOptionalInteger(
            Map<String, Object> input, String key, int expected) {
        if (input.containsKey(key) && integer(input, key) != expected) {
            throw invalid("Run input 与 Evidence " + key + " 不一致");
        }
    }

    private static void requireOptionalHash(
            Map<String, Object> input, String key, String expected) {
        if (input.containsKey(key) && !Objects.equals(string(input, key), expected)) {
            throw invalid("Run input 与 Evidence " + key + " 不一致");
        }
    }

    private static String slice(String value, int start, int end) {
        return value.substring(
                value.offsetByCodePoints(0, start), value.offsetByCodePoints(0, end));
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }

    private static ApiException notFound() {
        return new ApiException(404, "WORKFLOW_CALLBACK_NOT_FOUND", "Workflow Run 或 Step 不存在");
    }

    private static ApiException invalid(String message) {
        return new ApiException(409, "WORKFLOW_CALLBACK_INVALID", message);
    }

    private record Locked(Record run, Record step) {}

    private record Artifact(String id, int revision) {}

    private record UsageValidation(
            WorkflowStepUsage usage, WorkflowBudgetDimension exceededDimension) {}
}
