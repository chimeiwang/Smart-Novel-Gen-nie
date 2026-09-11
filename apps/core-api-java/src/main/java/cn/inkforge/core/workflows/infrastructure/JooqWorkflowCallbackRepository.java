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
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import cn.inkforge.core.workflows.application.WorkflowIntentBusinessPreparation;
import cn.inkforge.core.workflows.application.WorkflowStructuredCandidatePreparation;
import cn.inkforge.core.workflows.application.WorkflowShortMediumCompletion;
import cn.inkforge.core.workflows.application.WorkflowQualityCompletion;
import cn.inkforge.core.workflows.application.WorkflowStylePortraitCompletion;
import cn.inkforge.core.workflows.application.WorkflowRagIndexCompletion;
import cn.inkforge.core.workflows.application.WorkflowVideoEpisodeScriptCompletion;
import cn.inkforge.core.workflows.domain.VideoEpisodeScriptTransitions;
import cn.inkforge.core.workflows.application.WorkflowVideoEpisodeStoryboardCompletion;
import cn.inkforge.core.workflows.domain.VideoEpisodeStoryboardTransitions;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowExecutionContext;
import cn.inkforge.core.workflows.catalog.WorkflowIntentSelection;
import cn.inkforge.core.workflows.domain.DurableIntentDecision;
import cn.inkforge.core.workflows.domain.WorkflowIntentQuestion;
import cn.inkforge.core.workflows.domain.DurableSelectionArtifact;
import cn.inkforge.core.workflows.domain.DurableOutlineSelectionArtifact;
import cn.inkforge.core.workflows.domain.DurableBeatPlanArtifact;
import cn.inkforge.core.workflows.domain.DurableChapterDraftArtifact;
import cn.inkforge.core.workflows.domain.DurableAgentUpdatesArtifact;
import cn.inkforge.core.workflows.domain.ChapterDraftPatches;
import cn.inkforge.core.workflows.domain.WorkflowBudgetDimension;
import cn.inkforge.core.workflows.domain.WorkflowBudgetExceededException;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.domain.WorkflowStepBudget;
import cn.inkforge.core.workflows.domain.WorkflowStepUsage;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.protocol.WorkflowOutputValidator;
import cn.inkforge.core.workflows.domain.WorkflowMessageMetadata;
import cn.inkforge.core.workflows.domain.ShortMediumSegments;
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
import java.util.Set;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.impl.DSL;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** PostgreSQL 中单事务收敛 progress/result/failure，并按冻结计划物化业务结果。 */
final class JooqWorkflowCallbackRepository implements WorkflowCallbackRepository {

    private static final TypeReference<Map<String, Object>> JSON_OBJECT = new TypeReference<>() {};
    private static final String GENERATION = "generation";
    private static final String REVIEW = "review";
    private static final String RESOLVE_INTENT = "resolve_intent";
    private static final String PROTOCOL_CORRECTION = "protocol_correction";
    private static final String QUALITY_CORRECTION_REQUIRED = "MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final Duration leaseDuration;
    private final WorkflowBillingCoordinator billing;
    private final WorkflowExecutionContextReader contexts;
    private final java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation;
    private final java.util.function.Supplier<WorkflowStructuredCandidatePreparation> structuredCandidates;
    private final java.util.function.Supplier<WorkflowShortMediumCompletion> shortMediumCompletion;
    private final java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion;
    private final java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion;
    private final java.util.function.Supplier<WorkflowRagIndexCompletion> ragCompletion;
    private final java.util.function.Supplier<WorkflowVideoEpisodeScriptCompletion> episodeScriptCompletion;
    private final java.util.function.Supplier<WorkflowVideoEpisodeStoryboardCompletion> episodeStoryboardCompletion;

    JooqWorkflowCallbackRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            ExecutionRegistry registry,
            Duration leaseDuration) {
        this(database, ids, clock, json, registry, leaseDuration,
                new JooqWorkflowExecutionContextReader(json), () -> null);
    }

    JooqWorkflowCallbackRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, Duration leaseDuration,
            WorkflowExecutionContextReader contexts,
            java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation) {
        this(database, ids, clock, json, registry, leaseDuration, contexts, businessPreparation, () -> null);
    }

    JooqWorkflowCallbackRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, Duration leaseDuration,
            WorkflowExecutionContextReader contexts,
            java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation,
            java.util.function.Supplier<WorkflowStructuredCandidatePreparation> structuredCandidates) {
        this(database, ids, clock, json, registry, leaseDuration, contexts, businessPreparation, structuredCandidates, () -> null);
    }

    JooqWorkflowCallbackRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, Duration leaseDuration,
            WorkflowExecutionContextReader contexts,
            java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation,
            java.util.function.Supplier<WorkflowStructuredCandidatePreparation> structuredCandidates,
            java.util.function.Supplier<WorkflowShortMediumCompletion> shortMediumCompletion) {
        this(database, ids, clock, json, registry, leaseDuration, contexts, businessPreparation,
                structuredCandidates, shortMediumCompletion, () -> null);
    }

    JooqWorkflowCallbackRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, Duration leaseDuration,
            WorkflowExecutionContextReader contexts,
            java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation,
            java.util.function.Supplier<WorkflowStructuredCandidatePreparation> structuredCandidates,
            java.util.function.Supplier<WorkflowShortMediumCompletion> shortMediumCompletion,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion) {
        this(database, ids, clock, json, registry, leaseDuration, contexts, businessPreparation,
                structuredCandidates, shortMediumCompletion, qualityCompletion, () -> null);
    }

    JooqWorkflowCallbackRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, Duration leaseDuration,
            WorkflowExecutionContextReader contexts,
            java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation,
            java.util.function.Supplier<WorkflowStructuredCandidatePreparation> structuredCandidates,
            java.util.function.Supplier<WorkflowShortMediumCompletion> shortMediumCompletion,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion) {
        this(database, ids, clock, json, registry, leaseDuration, contexts, businessPreparation,
                structuredCandidates, shortMediumCompletion, qualityCompletion, styleCompletion, () -> null);
    }

    JooqWorkflowCallbackRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, Duration leaseDuration,
            WorkflowExecutionContextReader contexts,
            java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation,
            java.util.function.Supplier<WorkflowStructuredCandidatePreparation> structuredCandidates,
            java.util.function.Supplier<WorkflowShortMediumCompletion> shortMediumCompletion,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion,
            java.util.function.Supplier<WorkflowRagIndexCompletion> ragCompletion) {
        this(database, ids, clock, json, registry, leaseDuration, contexts, businessPreparation, structuredCandidates,
                shortMediumCompletion, qualityCompletion, styleCompletion, ragCompletion, () -> null);
    }

    JooqWorkflowCallbackRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, Duration leaseDuration,
            WorkflowExecutionContextReader contexts,
            java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation,
            java.util.function.Supplier<WorkflowStructuredCandidatePreparation> structuredCandidates,
            java.util.function.Supplier<WorkflowShortMediumCompletion> shortMediumCompletion,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion,
            java.util.function.Supplier<WorkflowRagIndexCompletion> ragCompletion,
            java.util.function.Supplier<WorkflowVideoEpisodeScriptCompletion> episodeScriptCompletion) {
        this(database, ids, clock, json, registry, leaseDuration, contexts, businessPreparation, structuredCandidates,
                shortMediumCompletion, qualityCompletion, styleCompletion, ragCompletion, episodeScriptCompletion, () -> null);
    }

    JooqWorkflowCallbackRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            ObjectMapper json, ExecutionRegistry registry, Duration leaseDuration,
            WorkflowExecutionContextReader contexts,
            java.util.function.Supplier<WorkflowIntentBusinessPreparation> businessPreparation,
            java.util.function.Supplier<WorkflowStructuredCandidatePreparation> structuredCandidates,
            java.util.function.Supplier<WorkflowShortMediumCompletion> shortMediumCompletion,
            java.util.function.Supplier<WorkflowQualityCompletion> qualityCompletion,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styleCompletion,
            java.util.function.Supplier<WorkflowRagIndexCompletion> ragCompletion,
            java.util.function.Supplier<WorkflowVideoEpisodeScriptCompletion> episodeScriptCompletion,
            java.util.function.Supplier<WorkflowVideoEpisodeStoryboardCompletion> episodeStoryboardCompletion) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        ExecutionRegistry requiredRegistry = Objects.requireNonNull(registry);
        WorkflowResultMaterializerRegistry.requireEnabledOperationKeys(
                requiredRegistry.enabledOperationKeys("long_serial", false));
        WorkflowResultMaterializerRegistry.requireEnabledOperationKeys(
                requiredRegistry.enabledOperationKeys("short_medium", false));
        WorkflowResultMaterializerRegistry.requireEnabledOperationKeys(
                requiredRegistry.enabledOperationKeys("quality", false));
        WorkflowResultMaterializerRegistry.requireEnabledOperationKeys(
                requiredRegistry.enabledOperationKeys("style", false));
        WorkflowResultMaterializerRegistry.requireEnabledOperationKeys(
                requiredRegistry.enabledOperationKeys("rag", false));
        if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
            throw new IllegalArgumentException("Workflow callback lease 必须为正数");
        }
        this.leaseDuration = leaseDuration;
        this.billing = new WorkflowBillingCoordinator(ids, json, requiredRegistry, contexts);
        this.contexts = Objects.requireNonNull(contexts);
        this.businessPreparation = Objects.requireNonNull(businessPreparation);
        this.structuredCandidates = Objects.requireNonNull(structuredCandidates);
        this.shortMediumCompletion = Objects.requireNonNull(shortMediumCompletion);
        this.qualityCompletion = Objects.requireNonNull(qualityCompletion);
        this.styleCompletion = Objects.requireNonNull(styleCompletion);
        this.ragCompletion = Objects.requireNonNull(ragCompletion);
        this.episodeScriptCompletion = Objects.requireNonNull(episodeScriptCompletion);
        this.episodeStoryboardCompletion = Objects.requireNonNull(episodeStoryboardCompletion);
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
        if (GENERATION.equals(purpose) || RESOLVE_INTENT.equals(purpose)
                || PROTOCOL_CORRECTION.equals(purpose) && isQualityRun(locked.run())) {
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
                if (isEpisodeScriptRun(locked.run())) {
                    requireEpisodeScriptCurrentInput(transaction, locked);
                    if (!episodeScriptCompletion().targetExists(transaction, body.getRunId())) {
                        throw new IllegalArgumentException("剧集来源已经不存在");
                    }
                } else if (isEpisodeStoryboardRun(locked.run())) {
                    requireEpisodeStoryboardCurrentInput(transaction, locked);
                    if (!episodeStoryboardCompletion().targetExists(transaction, body.getRunId())) {
                        throw new IllegalArgumentException("分镜剧集来源已经不存在");
                    }
                }
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
        ExecutionPlanSnapshot.Step frozenStep = frozenStep(locked);
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
        if (GENERATION.equals(purpose)
                || PROTOCOL_CORRECTION.equals(purpose) && isQualityRun(locked.run())) {
            completeGeneration(transaction, locked, body, usage, now);
        } else if (REVIEW.equals(purpose)) {
            completeReview(transaction, locked, body, usage, now);
        } else if (RESOLVE_INTENT.equals(purpose)) {
            completeIntent(transaction, locked, body, usage, now);
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
        if (tryQualityProtocolCorrection(transaction, locked, body, usage, sequence, now)) {
            return receipt(body, ExecutionCallbackReceipt.StatusEnum.ACCEPTED);
        }
        if (GENERATION.equals(purpose) || RESOLVE_INTENT.equals(purpose)
                || PROTOCOL_CORRECTION.equals(purpose) && isQualityRun(locked.run())) {
            String terminalCode = isQualityRun(locked.run()) && QUALITY_CORRECTION_REQUIRED.equals(body.getErrorCode())
                    ? "MODEL_TOOL_PROTOCOL_RECOVERY_FAILED" : body.getErrorCode();
            failRun(
                    transaction,
                    locked,
                    terminalCode,
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

    private void completeIntent(DSLContext tx, Locked locked, ExecutionStepResult body,
            WorkflowStepUsage usage, LocalDateTime now) {
        if (body.getResultKind() != ExecutionStepResult.ResultKindEnum.PROPOSED_COMMAND
                || body.getProposedCommand() == null || locked.step().get("artifactId", String.class) != null) {
            throw invalid("意图解析只接受无 Artifact 的 proposed_command");
        }
        WorkflowExecutionContext context = executionContext(locked.run());
        if (context.initialIntentPlan() == null || context.selection() != null) {
            throw invalid("意图回调必须属于尚未选择业务操作的自然 Run");
        }
        Map<String, Object> input = readObject(locked.step().get("input", String.class));
        requireHash(locked.step().get("inputHash", String.class), input, "resolver input");
        if (!input.keySet().equals(java.util.Set.of("userInstruction", "clarifications"))
                || !(input.get("clarifications") instanceof List<?> answers)) {
            throw invalid("意图解析缺少完整初始指令或有序回答");
        }
        Map<String, Object> proposed = WorkflowCallbackValues.proposedCommandMap(body.getProposedCommand());
        DurableIntentDecision decision;
        try {
            WorkflowOutputValidator.validate(frozenStep(locked).outputSchema().jsonSchema(), proposed);
            decision = DurableIntentDecision.resolve(proposed, context.initialIdentity().workflow(),
                    context.initialIntentPlan().operationPlans().stream().map(plan -> plan.operation().key())
                            .collect(java.util.stream.Collectors.toUnmodifiableSet()),
                    answers.size(), context.initialIntentPlan().maxClarifications());
        } catch (IllegalArgumentException exception) {
            throw invalid("意图结果不符合冻结计划或严格输出契约");
        }
        String runId = locked.run().get("id", String.class);
        completeStep(tx, locked, body.getResultHash(), usage, canonicalJson(proposed), null, null, now);
        long sequence = appendStepFinished(tx, locked, "completed", null,
                locked.run().get("lastEventSequence", Long.class), now);
        if (decision.errorCode() != null) {
            failRun(tx, locked, decision.errorCode(), false, sequence, now);
            return;
        }
        String resolverBundle = locked.step().get("evidenceBundleId", String.class);
        if (decision.clarification() != null) {
            var question = new WorkflowIntentQuestion(runId, body.getStepId(), body.getResultHash(), resolverBundle,
                    decision.clarification().code(), decision.clarification().prompt());
            String questionId = appendIntentControl(tx, runId, "intent_clarification", "user_confirmation",
                    question.stored(), resolverBundle, now);
            persistIntentQuestion(tx, locked, questionId, question, now);
            sequence = appendEvent(tx, runId, sequence, "clarification_required",
                    Map.of("clarificationCode", question.clarificationCode(), "prompt", question.prompt(),
                            "decisionStepId", questionId), "intent:question:" + questionId, now);
            updateRun(tx, runId, "waiting_user", sequence, null, null, now);
            return;
        }
        ExecutionPlanSnapshot plan = context.initialIntentPlan().requireOperationPlan(decision.operationKey());
        WorkflowIntentBusinessPreparation preparation = businessPreparation.get();
        if (preparation == null) throw new IllegalStateException("自然入口的业务准备端口未装配");
        String instruction = string(input, "userInstruction");
        if (!answers.isEmpty()) {
            List<Map<String, Object>> completeAnswers = answers.stream().map(answer -> {
                Map<String, Object> value = object(answer, "澄清回答");
                return Map.<String, Object>of("prompt", string(value, "prompt"), "userMessage", string(value, "userMessage"));
            }).toList();
            instruction = canonicalJson(Map.of("initialInstruction", instruction, "clarifications", completeAnswers));
        }
        Map<String, Object> originalInput = readObject(locked.run().get("input", String.class));
        WorkflowIntentBusinessPreparation.Prepared prepared;
        try {
            prepared = preparation.prepare(locked.run().get("userId", String.class),
                    locked.run().get("novelId", String.class), locked.run().get("chapterId", String.class),
                    locked.run().get("writingSessionId", String.class), instruction,
                    integer(originalInput, "targetWordCount"), plan);
        } catch (ApiException exception) {
            // 解析已经实际完成；来源/业务校验拒绝必须成为可见 Run 终态，不能反复拒绝同一份模型结果。
            // 临时错误、SQL 和未知程序异常仍交给原回调重试，不隐藏失败或伪造业务决定。
            if (exception.statusCode() >= 500 || exception.statusCode() == 408 || exception.statusCode() == 429) {
                throw exception;
            }
            failRun(tx, locked, exception.code(), false, sequence, now);
            return;
        }
        if (!plan.generator().equals(prepared.initialStep())) {
            throw invalid("自然业务准备不得替换冻结的生成器");
        }
        int version = tx.fetchOne("SELECT max(version) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", runId)
                .get(0, Integer.class) + 1;
        var evidence = new JooqWorkflowStartRepository(database, ids, clock, json).appendEvidence(tx, runId, version,
                plan.generator().evidencePolicy(), prepared.evidenceItems(), now);
        var selection = new WorkflowIntentSelection(runId, plan.operation().key(), plan.sha256(), body.getStepId(),
                body.getResultHash(), resolverBundle, "chapter", locked.run().get("chapterId", String.class),
                context.initialIntentPlan().scopeKindForOperation(plan.operation().key()),
                context.initialIntentPlan().supportsNovelScopes() ? WorkflowIntentSelection.SCHEMA_V2 : WorkflowIntentSelection.SCHEMA);
        appendIntentControl(tx, runId, "intent_selection", "persistence", selection.stored(), resolverBundle, now);
        appendIntentBusinessStep(tx, locked, plan.generator(), prepared.input(), evidence.id(), now);
        tx.execute("UPDATE public.\"WorkflowRun\" SET \"currentEvidenceBundleId\" = ? WHERE id = ?", evidence.id(), runId);
        sequence = appendEvent(tx, runId, sequence, "intent_resolved", Map.of("workflow", plan.operation().workflow(),
                "operation", plan.operation().operation(), "targetType", "chapter", "targetId", selection.targetId(),
                "confidence", decision.confidence()), "intent:resolved", now);
        sequence = appendEvent(tx, runId, sequence, "evidence_ready", Map.of("bundleId", evidence.id(),
                "bundleVersion", evidence.version(), "manifestSha256", evidence.manifestSha256(), "totalBytes", evidence.totalBytes()),
                "evidence:" + evidence.version(), now);
        updateRun(tx, runId, "running", sequence, null, null, now);
    }

    private String appendIntentControl(DSLContext tx, String runId, String purpose, String type,
            Map<String, Object> input, String bundleId, LocalDateTime now) {
        String id = ids.next();
        String hash = ExecutionCanonicalJson.sha256(input);
        int ordinal = tx.fetchOne("SELECT max(ordinal) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", runId)
                .get(0, Integer.class) + 1;
        tx.execute("""
                INSERT INTO public."WorkflowStep" (id, "runId", "stepType", status, input, "createdAt", ordinal,
                  purpose, lane, "attemptCount", "fencingToken", "idempotencyKey", "requestHash", "inputHash",
                  "evidenceBundleId", "submittedAt", "updatedAt", "completedAt")
                VALUES (?, ?, CAST(? AS "WorkflowStepType"), CAST('completed' AS "WorkflowStepStatus"), ?, ?, ?,
                  ?, 'control', 0, 1, ?, ?, ?, ?, ?, ?, ?)
                """, id, runId, type, canonicalJson(input), now, ordinal, purpose, runId + "." + id, hash, hash,
                bundleId, now, now, now);
        return id;
    }

    private void appendIntentBusinessStep(DSLContext tx, Locked locked, ExecutionPlanSnapshot.Step generator,
            Map<String, Object> input, String bundleId, LocalDateTime now) {
        appendGenerationStep(tx, locked, generator, input, bundleId, null, now);
    }

    private String appendGenerationStep(DSLContext tx, Locked locked, ExecutionPlanSnapshot.Step generator,
            Map<String, Object> input, String bundleId, Artifact previous, LocalDateTime now) {
        String runId = locked.run().get("id", String.class);
        String id = ids.next();
        String idempotencyKey = runId + "." + id;
        String inputHash = ExecutionCanonicalJson.sha256(input);
        Record bundle = tx.fetchOne("SELECT id, version, \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ? AND \"runId\" = ?", bundleId, runId);
        Map<String, Object> request = new LinkedHashMap<>(stepRequestMaterial(locked.run(), id, idempotencyKey,
                inputHash, bundle, generator.evidencePolicy(), generator.lane(), generator.modelProfile().toMap(),
                generator.outputSchema().toMap(), generator.stepBudget().budgetMap(), previous));
        request.put("purpose", generator.purpose());
        int ordinal = tx.fetchOne("SELECT max(ordinal) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", runId)
                .get(0, Integer.class) + 1;
        tx.execute("""
                INSERT INTO public."WorkflowStep" (id, "runId", "agentId", "stepType", status, input, "createdAt", ordinal,
                  purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken", "idempotencyKey", "requestHash", "inputHash",
                  "evidenceBundleId", "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt", "artifactId", "artifactRevision")
                VALUES (?, ?, ?, CAST('agent' AS "WorkflowStepType"), CAST('pending' AS "WorkflowStepStatus"), ?, ?, ?,
                  ?, ?, 0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, id, runId, generator.modelProfile().profile(), canonicalJson(input), now, ordinal,
                generator.purpose(), generator.lane(), now, idempotencyKey, ExecutionCanonicalJson.sha256(request), inputHash, bundleId,
                generator.modelProfile().profile(), Integer.toString(generator.modelProfile().version()),
                generator.outputSchema().name(), Integer.toString(generator.outputSchema().version()),
                json.writeValueAsString(generator.stepBudget().stored()), now, now,
                previous == null ? null : previous.id(), previous == null ? null : previous.revision());
        return id;
    }

    private void persistIntentQuestion(DSLContext tx, Locked locked, String questionId, WorkflowIntentQuestion question, LocalDateTime now) {
        String sessionId = locked.run().get("writingSessionId", String.class);
        Record session = tx.fetchOne("SELECT \"updatedAt\" FROM public.\"WritingSession\" WHERE id = ? AND \"novelId\" = ? AND \"chapterId\" = ? FOR UPDATE",
                sessionId, locked.run().get("novelId", String.class), locked.run().get("chapterId", String.class));
        if (session == null) throw invalid("意图问题的写作会话不存在或归属不一致");
        Map<String, Object> source = Map.of("engineVersion", 2, "runId", question.runId(), "stepId", questionId,
                "decisionStepId", questionId, "outcomeType", "clarification", "resultHash", question.resolverResultHash());
        tx.execute("""
                INSERT INTO public."WritingMessage" (id, "sessionId", role, "agentId", content, metadata, "createdAt")
                VALUES (?, ?, 'agent', '编辑', ?, ?, ?)
                """, ids.next(), sessionId, question.prompt(), WorkflowMessageMetadata.serialize(question.runId(),
                        "waiting_user", question.prompt(), "编辑", source, json), now);
        tx.execute("UPDATE public.\"WritingSession\" SET \"updatedAt\" = ? WHERE id = ?",
                DatabaseTimestamp.next(clock, session.get("updatedAt", LocalDateTime.class)), sessionId);
    }

    private void completeGeneration(
            DSLContext transaction,
            Locked locked,
            ExecutionStepResult body,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        if (body.getResultKind() == ExecutionStepResult.ResultKindEnum.EVIDENCE_EXPANSION) {
            completeEvidenceExpansion(transaction, locked, body, usage, now);
            return;
        }
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
            case VIDEO_EPISODE_SCRIPT -> completeEpisodeScriptStage(transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case VIDEO_EPISODE_STORYBOARD -> completeEpisodeStoryboardStage(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case RAG_INDEX -> completeRagIndex(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case STYLE_PORTRAIT -> completeStylePortrait(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case CONSISTENCY_QUALITY -> completeQuality(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case SHORT_MEDIUM -> completeShortMedium(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case CHAT_ANSWER -> completeChatAnswer(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case CHAPTER_REVIEW_REPORT -> completeChapterReview(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case OUTLINE_SELECTION_REVIEW_ARTIFACT -> completeSelectionGeneration(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case CHAPTER_SELECTION_REVIEW_ARTIFACT -> completeSelectionGeneration(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case BEAT_PLAN_REVIEW_ARTIFACT -> completeSelectionGeneration(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case CHAPTER_DRAFT_REVIEW_ARTIFACT -> completeSelectionGeneration(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
            case AGENT_UPDATES_REVIEW_ARTIFACT -> completeSelectionGeneration(
                    transaction, locked, executionPlan, frozenStep, body, usage, output, now);
        }
    }

    private void completeEpisodeScriptStage(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            ExecutionPlanSnapshot.Step stage, ExecutionStepResult body, WorkflowStepUsage usage,
            Map<String, Object> output, LocalDateTime now) {
        requireEpisodeScriptCurrentInput(tx, locked);
        WorkflowOutputValidator.validate(stage.outputSchema().jsonSchema(), output);
        completeStep(tx, locked, body.getResultHash(), usage, canonicalJson(output), null, null, now);
        long sequence = appendStepFinished(tx, locked, "completed", null,
                locked.run().get("lastEventSequence", Long.class), now);
        VideoEpisodeScriptTransitions.Decision decision;
        try {
            decision = episodeScriptDecision(tx, locked);
        } catch (IllegalArgumentException error) {
            failRun(tx, locked, "VIDEO_EPISODE_SCRIPT_OUTPUT_INVALID", false, sequence, now);
            return;
        }
        if (decision.nextInput() != null) {
            ExecutionPlanSnapshot.Step next = plan.requireVideoStage(string(decision.nextInput(), "stageKey")).step();
            appendGenerationStep(tx, locked, next, decision.nextInput(),
                    locked.step().get("evidenceBundleId", String.class), null, now);
            updateRun(tx, body.getRunId(), "running", sequence, null, null, now);
            return;
        }
        String artifactId;
        try {
            artifactId = tx.transactionResult(configuration -> episodeScriptCompletion().completeCandidate(
                    DSL.using(configuration), body.getRunId(), decision.document(), decision.review()));
        } catch (ApiException error) {
            if (error.statusCode() >= 500 || error.statusCode() == 408 || error.statusCode() == 429) throw error;
            failRun(tx, locked, error.code(), false, sequence, now);
            return;
        }
        tx.execute("UPDATE public.\"WorkflowRun\" SET output = ? WHERE id = ?",
                canonicalJson(Map.of("episodeId", locked.run().get("targetId", String.class), "artifactId", artifactId)), body.getRunId());
        sequence = appendEvent(tx, body.getRunId(), sequence, "candidate_ready",
                Map.of("stepId", body.getStepId(), "artifactId", artifactId, "artifactRevision", 1), "candidate:" + artifactId + ":1", now);
        sequence = appendEvent(tx, body.getRunId(), sequence, "completed",
                Map.of("outcomeType", "video_episode_script_candidate", "resultId", artifactId), "run:completed", now);
        updateRun(tx, body.getRunId(), "completed", sequence, null, now, now);
    }

    private void requireEpisodeScriptCurrentInput(DSLContext tx, Locked locked) {
        var decision = episodeScriptDecision(tx, locked);
        Map<String, Object> input = readObject(locked.step().get("input", String.class));
        if (decision.nextInput() == null || !ExecutionCanonicalJson.sha256(decision.nextInput()).equals(ExecutionCanonicalJson.sha256(input))
                || !executionPlan(locked.run()).requireVideoStage(string(input, "stageKey")).step().equals(frozenStep(locked, executionPlan(locked.run())))) {
            throw invalid("当前剧本阶段不匹配 Core 的冻结接续");
        }
    }

    private VideoEpisodeScriptTransitions.Decision episodeScriptDecision(DSLContext tx, Locked locked) {
        String runId = locked.run().get("id", String.class);
        String episodeId = locked.run().get("targetId", String.class);
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        var plan = executionPlan(locked.run());
        if (!isEpisodeScriptRun(locked.run()) || locked.run().get("novelId") == null
                || locked.run().get("chapterId") != null || locked.run().get("writingSessionId") != null
                || !"video_episode_script".equals(locked.run().get("sourceType", String.class))
                || !"video_episode_script".equals(locked.run().get("targetType", String.class))
                || !Objects.equals(episodeId, locked.run().get("sourceId", String.class))
                || locked.step().get("artifactId") != null || !GENERATION.equals(locked.step().get("purpose", String.class))
                || !Objects.equals(bundleId, locked.run().get("currentEvidenceBundleId", String.class))) {
            throw invalid("独立剧本必须绑定小说级剧集来源，不绑定旧章节任务或候选");
        }
        var rows = tx.fetch("""
                SELECT item."resourceType", item."resourceId", item.exists, item."contentType", item."contentJson",
                    item."contentSha256", item."byteCount", item."rangeJson", bundle."policyVersion"
                FROM public."WorkflowEvidenceItem" item JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId"
                WHERE bundle.id = ? AND bundle."runId" = ? ORDER BY item.ordinal
                """, bundleId, runId);
        if (rows.size() != 1) throw invalid("剧本必须冻结唯一完整上下文");
        Record item = rows.getFirst();
        Map<String, Object> context = readObject(item.get("contentJson", String.class));
        Map<String, Object> runInput = readObject(locked.run().get("input", String.class));
        if (!"video_episode_script_context".equals(item.get("resourceType")) || !episodeId.equals(item.get("resourceId"))
                || !Boolean.TRUE.equals(item.get("exists")) || !"json".equals(item.get("contentType")) || item.get("rangeJson") != null
                || !"evidence.video.episode_script.v1".equals(item.get("policyVersion"))
                || !episodeId.equals(context.get("episodeId")) || !episodeId.equals(runInput.get("episodeId"))
                || !locked.run().get("novelId").equals(context.get("novelId"))
                || !locked.run().get("operation").equals(context.get("operation"))
                || !"video-episode-script-context/1.0".equals(context.get("schemaVersion"))
                || !ExecutionCanonicalJson.sha256(context).equals(item.get("contentSha256"))
                || ExecutionCanonicalJson.bytes(context).length != item.get("byteCount", Long.class)) {
            throw invalid("分镜 Evidence 身份或哈希无效");
        }
        var steps = tx.fetch("""
                SELECT id, input, "inputHash", output, "resultHash", "evidenceBundleId", purpose, lane,
                    "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion", "budgetJson"
                FROM public."WorkflowStep" WHERE "runId" = ? AND status = 'completed' ORDER BY ordinal LIMIT 5
                """, runId);
        if (steps.size() > 4) throw invalid("剧本历史阶段超过固定上限");
        List<VideoEpisodeScriptTransitions.Completed> history = new ArrayList<>();
        for (Record step : steps) {
            Map<String, Object> input = readObject(step.get("input", String.class));
            var frozen = plan.requireStep(step.get("purpose", String.class), step.get("lane", String.class),
                    step.get("modelProfile", String.class), Integer.parseInt(step.get("modelProfileVersion", String.class)),
                    step.get("outputSchema", String.class), Integer.parseInt(step.get("outputSchemaVersion", String.class)),
                    readObject(step.get("budgetJson", String.class)));
            if (!bundleId.equals(step.get("evidenceBundleId")) || !ExecutionCanonicalJson.sha256(input).equals(step.get("inputHash"))
                    || !frozen.equals(plan.requireVideoStage(string(input, "stageKey")).step())) {
                throw invalid("剧本前序模型、来源或输入身份无效");
            }
            Map<String, Object> output = readObject(step.get("output", String.class));
            WorkflowOutputValidator.validate(frozen.outputSchema().jsonSchema(), output);
            history.add(new VideoEpisodeScriptTransitions.Completed(step.get("id", String.class), step.get("resultHash", String.class), input, output));
        }
        return VideoEpisodeScriptTransitions.replay(plan, context, history);
    }

    private static boolean isEpisodeScriptRun(Record run) {
        return "video".equals(run.get("workflow", String.class))
                && Set.of("episode_script_generate", "episode_script_revise").contains(run.get("operation", String.class));
    }

    private WorkflowVideoEpisodeScriptCompletion episodeScriptCompletion() {
        var completion = episodeScriptCompletion.get();
        if (completion == null) throw new IllegalStateException("独立剧本候选物化端口未装配");
        return completion;
    }

    private void completeEpisodeStoryboardStage(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            ExecutionPlanSnapshot.Step stage, ExecutionStepResult body, WorkflowStepUsage usage,
            Map<String, Object> output, LocalDateTime now) {
        requireEpisodeStoryboardCurrentInput(tx, locked);
        WorkflowOutputValidator.validate(stage.outputSchema().jsonSchema(), output);
        completeStep(tx, locked, body.getResultHash(), usage, canonicalJson(output), null, null, now);
        long sequence = appendStepFinished(tx, locked, "completed", null,
                locked.run().get("lastEventSequence", Long.class), now);
        VideoEpisodeStoryboardTransitions.Decision decision;
        try {
            decision = episodeStoryboardDecision(tx, locked);
        } catch (IllegalArgumentException error) {
            failRun(tx, locked, "VIDEO_EPISODE_STORYBOARD_OUTPUT_INVALID", false, sequence, now);
            return;
        }
        if (decision.nextInput() != null) {
            ExecutionPlanSnapshot.Step next = plan.requireVideoStage(string(decision.nextInput(), "stageKey")).step();
            appendGenerationStep(tx, locked, next, decision.nextInput(),
                    locked.step().get("evidenceBundleId", String.class), null, now);
            updateRun(tx, body.getRunId(), "running", sequence, null, null, now);
            return;
        }
        String artifactId;
        try {
            artifactId = tx.transactionResult(configuration -> episodeStoryboardCompletion().completeCandidate(
                    DSL.using(configuration), body.getRunId(), decision.document(), decision.review()));
        } catch (ApiException error) {
            if (error.statusCode() >= 500 || error.statusCode() == 408 || error.statusCode() == 429) throw error;
            failRun(tx, locked, error.code(), false, sequence, now);
            return;
        }
        tx.execute("UPDATE public.\"WorkflowRun\" SET output = ? WHERE id = ?",
                canonicalJson(Map.of("episodeId", locked.run().get("targetId", String.class), "artifactId", artifactId)), body.getRunId());
        sequence = appendEvent(tx, body.getRunId(), sequence, "candidate_ready",
                Map.of("stepId", body.getStepId(), "artifactId", artifactId, "artifactRevision", 1), "candidate:" + artifactId + ":1", now);
        sequence = appendEvent(tx, body.getRunId(), sequence, "completed",
                Map.of("outcomeType", "video_episode_storyboard_candidate", "resultId", artifactId), "run:completed", now);
        updateRun(tx, body.getRunId(), "completed", sequence, null, now, now);
    }

    private void requireEpisodeStoryboardCurrentInput(DSLContext tx, Locked locked) {
        var decision = episodeStoryboardDecision(tx, locked);
        Map<String, Object> input = readObject(locked.step().get("input", String.class));
        if (decision.nextInput() == null || !ExecutionCanonicalJson.sha256(decision.nextInput()).equals(ExecutionCanonicalJson.sha256(input))
                || !executionPlan(locked.run()).requireVideoStage(string(input, "stageKey")).step().equals(frozenStep(locked, executionPlan(locked.run())))) {
            throw invalid("当前分镜阶段不匹配 Core 的冻结接续");
        }
    }

    private VideoEpisodeStoryboardTransitions.Decision episodeStoryboardDecision(DSLContext tx, Locked locked) {
        String runId = locked.run().get("id", String.class);
        String episodeId = locked.run().get("targetId", String.class);
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        var plan = executionPlan(locked.run());
        if (!isEpisodeStoryboardRun(locked.run()) || locked.run().get("novelId") == null
                || locked.run().get("chapterId") != null || locked.run().get("writingSessionId") != null
                || !"video_episode_storyboard".equals(locked.run().get("sourceType", String.class))
                || !"video_episode_storyboard".equals(locked.run().get("targetType", String.class))
                || !Objects.equals(episodeId, locked.run().get("sourceId", String.class))
                || locked.step().get("artifactId") != null || !GENERATION.equals(locked.step().get("purpose", String.class))
                || !Objects.equals(bundleId, locked.run().get("currentEvidenceBundleId", String.class))) {
            throw invalid("独立分镜必须绑定小说级剧集来源，不绑定旧章节任务或候选");
        }
        var rows = tx.fetch("""
                SELECT item."resourceType", item."resourceId", item.exists, item."contentType", item."contentJson",
                    item."contentSha256", item."byteCount", item."rangeJson", bundle."policyVersion"
                FROM public."WorkflowEvidenceItem" item JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId"
                WHERE bundle.id = ? AND bundle."runId" = ? ORDER BY item.ordinal
                """, bundleId, runId);
        if (rows.size() != 1) throw invalid("分镜必须冻结唯一完整上下文");
        Record item = rows.getFirst();
        Map<String, Object> context = readObject(item.get("contentJson", String.class));
        Map<String, Object> runInput = readObject(locked.run().get("input", String.class));
        if (!"video_episode_storyboard_context".equals(item.get("resourceType")) || !episodeId.equals(item.get("resourceId"))
                || !Boolean.TRUE.equals(item.get("exists")) || !"json".equals(item.get("contentType")) || item.get("rangeJson") != null
                || !"evidence.video.episode_storyboard.v1".equals(item.get("policyVersion"))
                || !episodeId.equals(context.get("episodeId")) || !episodeId.equals(runInput.get("episodeId"))
                || !locked.run().get("novelId").equals(context.get("novelId"))
                || !locked.run().get("operation").equals(context.get("operation"))
                || !"video-episode-storyboard-context/1.0".equals(context.get("schemaVersion"))
                || !ExecutionCanonicalJson.sha256(context).equals(item.get("contentSha256"))
                || ExecutionCanonicalJson.bytes(context).length != item.get("byteCount", Long.class)) {
            throw invalid("剧本 Evidence 身份或哈希无效");
        }
        var steps = tx.fetch("""
                SELECT id, input, "inputHash", output, "resultHash", "evidenceBundleId", purpose, lane,
                    "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion", "budgetJson"
                FROM public."WorkflowStep" WHERE "runId" = ? AND status = 'completed' ORDER BY ordinal LIMIT 5
                """, runId);
        if (steps.size() > 4) throw invalid("分镜历史阶段超过固定上限");
        List<VideoEpisodeStoryboardTransitions.Completed> history = new ArrayList<>();
        for (Record step : steps) {
            Map<String, Object> input = readObject(step.get("input", String.class));
            var frozen = plan.requireStep(step.get("purpose", String.class), step.get("lane", String.class),
                    step.get("modelProfile", String.class), Integer.parseInt(step.get("modelProfileVersion", String.class)),
                    step.get("outputSchema", String.class), Integer.parseInt(step.get("outputSchemaVersion", String.class)),
                    readObject(step.get("budgetJson", String.class)));
            if (!bundleId.equals(step.get("evidenceBundleId")) || !ExecutionCanonicalJson.sha256(input).equals(step.get("inputHash"))
                    || !frozen.equals(plan.requireVideoStage(string(input, "stageKey")).step())) {
                throw invalid("分镜前序模型、来源或输入身份无效");
            }
            Map<String, Object> output = readObject(step.get("output", String.class));
            WorkflowOutputValidator.validate(frozen.outputSchema().jsonSchema(), output);
            history.add(new VideoEpisodeStoryboardTransitions.Completed(step.get("id", String.class), step.get("resultHash", String.class), input, output));
        }
        return VideoEpisodeStoryboardTransitions.replay(plan, context, history);
    }

    private static boolean isEpisodeStoryboardRun(Record run) {
        return "video".equals(run.get("workflow", String.class))
                && Set.of("episode_storyboard_generate", "episode_storyboard_revise").contains(run.get("operation", String.class));
    }

    private WorkflowVideoEpisodeStoryboardCompletion episodeStoryboardCompletion() {
        var completion = episodeStoryboardCompletion.get();
        if (completion == null) throw new IllegalStateException("独立分镜候选物化端口未装配");
        return completion;
    }

    private void completeRagIndex(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            ExecutionPlanSnapshot.Step generator, ExecutionStepResult body, WorkflowStepUsage usage,
            Map<String, Object> output, LocalDateTime now) {
        if (!isRagRun(locked.run()) || locked.run().get("novelId") == null
                || locked.run().get("chapterId") != null || locked.run().get("writingSessionId") != null
                || !"reference".equals(locked.run().get("targetType", String.class))
                || !GENERATION.equals(locked.step().get("purpose", String.class))
                || locked.step().get("artifactId") != null || !plan.reviewers().isEmpty() || !plan.systemSteps().isEmpty()) {
            throw invalid("RAG 索引必须是小说级无草案的串行 embedding 批次");
        }
        String runId = body.getRunId();
        WorkflowRagIndexCompletion completion = ragCompletion();
        int chunkCount = completion.frozenChunkCount(tx, runId);
        int batches = Math.ceilDiv(chunkCount, 10);
        if (chunkCount < 1 || chunkCount > 64 || batches > plan.runBudget().maxModelCalls()) {
            throw invalid("RAG 完整分块超出冻结调用额度");
        }
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        if (!Objects.equals(bundleId, locked.run().get("currentEvidenceBundleId", String.class))) {
            throw invalid("RAG 批次必须使用原冻结来源");
        }
        List<Record> previous = tx.fetch("""
                SELECT input, "inputHash", output, "evidenceBundleId", "modelProfile", "outputSchema"
                FROM public."WorkflowStep" WHERE "runId" = ? AND purpose = 'generation' AND status = 'completed'
                ORDER BY ordinal, id
                """, runId);
        if (previous.size() >= batches) throw invalid("RAG 批次数量超出冻结来源");
        List<List<java.math.BigDecimal>> vectors = new ArrayList<>();
        for (int index = 0; index < previous.size(); index++) {
            Record step = previous.get(index);
            Map<String, Object> input = readObject(step.get("input", String.class));
            requireHash(step.get("inputHash", String.class), input, "embedding batch input");
            if (!Map.of("batchIndex", index).equals(input)
                    || !Objects.equals(bundleId, step.get("evidenceBundleId", String.class))
                    || !generator.modelProfile().profile().equals(step.get("modelProfile", String.class))
                    || !generator.outputSchema().name().equals(step.get("outputSchema", String.class))) {
                throw invalid("已完成 RAG 批次顺序或来源不匹配");
            }
            vectors.addAll(embeddingVectors(generator, readObject(step.get("output", String.class)),
                    Math.min(10, chunkCount - index * 10)));
        }
        Map<String, Object> input = readObject(locked.step().get("input", String.class));
        requireHash(locked.step().get("inputHash", String.class), input, "embedding batch input");
        if (!Map.of("batchIndex", previous.size()).equals(input)) throw invalid("RAG 当前批次不符合冻结顺序");
        vectors.addAll(embeddingVectors(generator, output, Math.min(10, chunkCount - previous.size() * 10)));
        int dimension = vectors.getFirst().size();
        boolean dimensionMismatch = vectors.stream().anyMatch(vector -> vector.size() != dimension);
        boolean storageRangeInvalid = vectors.stream().flatMap(List::stream).anyMatch(value ->
                !Float.isFinite(value.floatValue()));
        completeStep(tx, locked, body.getResultHash(), usage, canonicalJson(output), null, null, now);
        long sequence = appendStepFinished(tx, locked, "completed", null,
                locked.run().get("lastEventSequence", Long.class), now);
        if (!completion.isCurrent(tx, runId)) {
            cancelInvalidatedRag(tx, locked, sequence, now);
            return;
        }
        if (dimensionMismatch) {
            // 每批单独合法但跨批维度漂移属于确定性业务失败，保留真实用量并结束，不能无限重投同一终报。
            failRun(tx, locked, "EMBEDDING_DIMENSION_MISMATCH", false, sequence, now);
            return;
        }
        if (storageRangeInvalid) {
            // pgvector 使用 float4；不可存的原始数值只能明确失败，不能裁切、归零或无限重投终报。
            failRun(tx, locked, "EMBEDDING_OUTPUT_INVALID", false, sequence, now);
            return;
        }
        if (previous.size() + 1 < batches) {
            appendGenerationStep(tx, locked, generator, Map.of("batchIndex", previous.size() + 1), bundleId, null, now);
            updateRun(tx, runId, "running", sequence, null, null, now);
            return;
        }
        String status = completion.complete(tx, runId, vectors);
        if ("cancelled".equals(status)) {
            cancelInvalidatedRag(tx, locked, sequence, now);
            return;
        }
        if (!"completed".equals(status)) throw invalid("RAG 物化端口返回非法状态");
        sequence = appendEvent(tx, runId, sequence, "completed", Map.of("outcomeType", "rag_index",
                "resultId", locked.run().get("targetId", String.class)), "run:completed", now);
        updateRun(tx, runId, "completed", sequence, null, now, now);
    }

    private static List<List<java.math.BigDecimal>> embeddingVectors(ExecutionPlanSnapshot.Step generator,
            Map<String, Object> output, int expectedCount) {
        try { WorkflowOutputValidator.validate(generator.outputSchema().jsonSchema(), output); }
        catch (IllegalArgumentException exception) { throw invalid("RAG 批次不符合冻结 Schema"); }
        if (!output.keySet().equals(Set.of("embeddings")) || !(output.get("embeddings") instanceof List<?> raw)
                || raw.size() != expectedCount) throw invalid("RAG 向量数量不匹配完整批次");
        List<List<java.math.BigDecimal>> result = new ArrayList<>();
        for (Object item : raw) {
            if (!(item instanceof List<?> values) || values.isEmpty() || values.size() > 4096) {
                throw invalid("RAG 向量维度无效");
            }
            List<java.math.BigDecimal> vector = new ArrayList<>();
            for (Object number : values) {
                if (!(number instanceof Number value) || !Double.isFinite(value.doubleValue())) {
                    throw invalid("RAG 向量只能包含有限数值");
                }
                vector.add(new java.math.BigDecimal(value.toString()));
            }
            result.add(List.copyOf(vector));
        }
        return List.copyOf(result);
    }

    private static boolean isRagRun(Record run) {
        return "rag".equals(run.get("workflow", String.class)) && "embedding".equals(run.get("operation", String.class));
    }

    private WorkflowRagIndexCompletion ragCompletion() {
        WorkflowRagIndexCompletion completion = ragCompletion.get();
        if (completion == null) throw new IllegalStateException("RAG 索引耐久投影端口未装配");
        return completion;
    }

    private void cancelInvalidatedRag(DSLContext tx, Locked locked, long sequence, LocalDateTime now) {
        String runId = locked.run().get("id", String.class);
        String cancelRequestId = "rag-invalidated." + runId;
        tx.execute("UPDATE public.\"WorkflowRun\" SET \"cancelRequestId\" = ?, \"cancelRequestedAt\" = ? WHERE id = ?",
                cancelRequestId, now, runId);
        sequence = appendEvent(tx, runId, sequence, "cancelled", Map.of("cancelRequestId", cancelRequestId), "run:cancelled", now);
        updateRun(tx, runId, "cancelled", sequence, "RUN_CANCELLED", now, now);
    }

    private void completeStylePortrait(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            ExecutionPlanSnapshot.Step generator, ExecutionStepResult body, WorkflowStepUsage usage,
            Map<String, Object> output, LocalDateTime now) {
        if (!isStyleRun(locked.run()) || locked.run().get("novelId") != null
                || locked.run().get("chapterId") != null || locked.run().get("writingSessionId") != null
                || !"style_profile".equals(locked.run().get("targetType", String.class))
                || !GENERATION.equals(locked.step().get("purpose", String.class))
                || locked.step().get("artifactId") != null || !plan.reviewers().isEmpty() || !plan.systemSteps().isEmpty()) {
            throw invalid("文风画像必须是无小说、无草案或系统纠正的串行生成");
        }
        Map<String, Object> runInput = readObject(locked.run().get("input", String.class));
        if (!runInput.keySet().equals(Set.of("mode", "section"))) throw invalid("画像运行模式字段不完整");
        List<String> expected;
        if ("full".equals(runInput.get("mode")) && runInput.get("section") == null) {
            expected = WorkflowStylePortraitCompletion.SECTIONS;
        } else if ("section".equals(runInput.get("mode"))
                && runInput.get("section") instanceof String section
                && WorkflowStylePortraitCompletion.SECTIONS.contains(section)) {
            expected = List.of(section);
        } else throw invalid("画像运行模式与分节不匹配");
        String runId = body.getRunId();
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        if (!Objects.equals(bundleId, locked.run().get("currentEvidenceBundleId", String.class))) {
            throw invalid("画像分节必须使用原冻结来源");
        }
        List<Record> previous = tx.fetch("""
                SELECT input, "inputHash", output, "evidenceBundleId", "modelProfile", "outputSchema"
                FROM public."WorkflowStep" WHERE "runId" = ? AND purpose = 'generation' AND status = 'completed'
                ORDER BY ordinal, id
                """, runId);
        if (previous.size() >= expected.size()) throw invalid("画像分节数量超出冻结模式");
        Map<String, String> sections = new LinkedHashMap<>();
        for (int index = 0; index < previous.size(); index++) {
            Record step = previous.get(index);
            Map<String, Object> input = readObject(step.get("input", String.class));
            requireHash(step.get("inputHash", String.class), input, "portrait section input");
            if (!Map.of("section", expected.get(index)).equals(input)
                    || !Objects.equals(bundleId, step.get("evidenceBundleId", String.class))
                    || !generator.modelProfile().profile().equals(step.get("modelProfile", String.class))
                    || !generator.outputSchema().name().equals(step.get("outputSchema", String.class))) {
                throw invalid("已完成画像分节顺序或来源不匹配");
            }
            sections.put(expected.get(index), portraitText(generator, readObject(step.get("output", String.class))));
        }
        Map<String, Object> input = readObject(locked.step().get("input", String.class));
        requireHash(locked.step().get("inputHash", String.class), input, "portrait section input");
        String section = expected.get(previous.size());
        if (!Map.of("section", section).equals(input)) throw invalid("画像当前分节不符合固定顺序");
        sections.put(section, portraitText(generator, output));
        completeStep(tx, locked, body.getResultHash(), usage, canonicalJson(output), null, null, now);
        long sequence = appendStepFinished(tx, locked, "completed", null,
                locked.run().get("lastEventSequence", Long.class), now);
        WorkflowStylePortraitCompletion completion = styleCompletion();
        if (!completion.targetExists(tx, runId)) {
            cancelDeletedStyle(tx, locked, sequence, now);
            return;
        }
        if (sections.size() < expected.size()) {
            if (expected.size() > plan.runBudget().maxModelCalls()) throw invalid("画像计划超过冻结调用额度");
            appendGenerationStep(tx, locked, generator, Map.of("section", expected.get(sections.size())), bundleId, null, now);
            updateRun(tx, runId, "running", sequence, null, null, now);
            return;
        }
        String status = completion.complete(tx, runId, sections);
        if ("cancelled".equals(status)) {
            cancelDeletedStyle(tx, locked, sequence, now);
            return;
        }
        if (!"completed".equals(status)) throw invalid("画像物化端口返回非法状态");
        sequence = appendEvent(tx, runId, sequence, "completed", Map.of("outcomeType", "style_portrait",
                "resultId", locked.run().get("targetId", String.class)), "run:completed", now);
        updateRun(tx, runId, "completed", sequence, null, now, now);
    }

    private static String portraitText(ExecutionPlanSnapshot.Step generator, Map<String, Object> output) {
        try {
            WorkflowOutputValidator.validate(generator.outputSchema().jsonSchema(), output);
        } catch (IllegalArgumentException exception) {
            throw invalid("画像分节不符合冻结 Schema");
        }
        if (!output.keySet().equals(Set.of("content")) || !(output.get("content") instanceof String content)
                || content.codePoints().allMatch(point -> Character.isWhitespace(point)
                        || Character.isSpaceChar(point) || point == 0x85)) {
            throw invalid("画像分节必须是按原空白规则非空的完整文本");
        }
        return content;
    }

    private static boolean isStyleRun(Record run) {
        return "style".equals(run.get("workflow", String.class)) && "portrait".equals(run.get("operation", String.class));
    }

    private WorkflowStylePortraitCompletion styleCompletion() {
        WorkflowStylePortraitCompletion completion = styleCompletion.get();
        if (completion == null) throw new IllegalStateException("文风画像耐久投影端口未装配");
        return completion;
    }

    private void cancelDeletedStyle(DSLContext tx, Locked locked, long sequence, LocalDateTime now) {
        String runId = locked.run().get("id", String.class);
        String cancelRequestId = "style-deleted." + runId;
        tx.execute("UPDATE public.\"WorkflowRun\" SET \"cancelRequestId\" = ?, \"cancelRequestedAt\" = ? WHERE id = ?",
                cancelRequestId, now, runId);
        sequence = appendEvent(tx, runId, sequence, "cancelled", Map.of("cancelRequestId", cancelRequestId), "run:cancelled", now);
        updateRun(tx, runId, "cancelled", sequence, "RUN_CANCELLED", now, now);
    }

    private void completeQuality(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            ExecutionPlanSnapshot.Step step, ExecutionStepResult body, WorkflowStepUsage usage,
            Map<String, Object> output, LocalDateTime now) {
        if (!isQualityRun(locked.run()) || !plan.reviewers().isEmpty()
                || locked.step().get("artifactId") != null) {
            throw invalid("一致性终检必须是无 Artifact、无 Reviewer 的质量运行");
        }
        try {
            WorkflowOutputValidator.validate(step.outputSchema().jsonSchema(), output);
        } catch (IllegalArgumentException exception) {
            throw invalid("一致性终检报告不符合冻结 Schema");
        }
        String runId = body.getRunId();
        String status = qualityCompletion().complete(tx, runId, output);
        completeStep(tx, locked, body.getResultHash(), usage, canonicalJson(output), null, null, now);
        long sequence = appendStepFinished(tx, locked, "completed", null,
                locked.run().get("lastEventSequence", Long.class), now);
        if ("cancelled".equals(status)) {
            cancelInvalidatedQuality(tx, locked, sequence, now);
            return;
        }
        if (!"completed".equals(status)) throw invalid("质量物化端口返回非法完成状态");
        sequence = appendEvent(tx, runId, sequence, "completed",
                Map.of("outcomeType", "consistency_quality_report", "resultId", body.getStepId()),
                "run:completed", now);
        updateRun(tx, runId, "completed", sequence, null, now, now);
    }

    /** 已结算的坏报告只授权一个新 Step，不回放坏 arguments，也不在当前 Step 隐式重调模型。 */
    private boolean tryQualityProtocolCorrection(DSLContext tx, Locked locked, ExecutionStepFailure body,
            WorkflowStepUsage usage, long sequence, LocalDateTime now) {
        if (!isQualityRun(locked.run()) || !GENERATION.equals(locked.step().get("purpose", String.class))
                || !QUALITY_CORRECTION_REQUIRED.equals(body.getErrorCode())
                || body.getErrorCategory() != ExecutionStepFailure.ErrorCategoryEnum.PROTOCOL
                || !Boolean.FALSE.equals(body.getRetryable()) || !Boolean.FALSE.equals(body.getOutcomeUnknown())
                || usage.usageStatus() == cn.inkforge.core.workflows.domain.WorkflowUsageStatus.UNKNOWN
                || usage.providerAttempts() == 0 || usage.inputTokens() == null || usage.cachedTokens() == null
                || usage.promptCacheMissTokens() == null || usage.completionTokens() == null
                || usage.reasoningTokens() == null || usage.visibleOutputTokens() == null) {
            return false;
        }
        String runId = body.getRunId();
        Record reservation = tx.fetchOne("SELECT status FROM public.\"WorkflowBillingReservation\" WHERE \"runId\" = ? AND \"stepId\" = ?",
                runId, body.getStepId());
        if (reservation == null || !"settled".equals(reservation.get("status", String.class))) return false;
        if (qualityCompletion().isInvalidated(tx, runId)) return false;
        if (tx.fetchOne("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'protocol_correction'", runId)
                .get(0, Integer.class) != 0) return false;
        var plan = executionPlan(locked.run());
        var corrections = plan.systemSteps().stream().filter(step -> PROTOCOL_CORRECTION.equals(step.purpose())).toList();
        if (corrections.size() != 1) return false;
        var correction = corrections.getFirst();
        if (!correction.outputSchema().equals(plan.generator().outputSchema())
                || !correction.evidencePolicy().equals(plan.generator().evidencePolicy())) return false;
        try {
            plan.runBudget().toDomain().requireWithin(List.of(
                    cn.inkforge.core.workflows.domain.WorkflowRunBudgetCharge.terminal(
                            plan.generator().stepBudget().budget(), usage, false),
                    cn.inkforge.core.workflows.domain.WorkflowRunBudgetCharge.active(correction.stepBudget().budget(), true)));
        } catch (WorkflowBudgetExceededException exception) {
            return false;
        }
        Map<String, Object> previous = readObject(locked.step().get("input", String.class));
        if (!previous.keySet().equals(Set.of("userInstruction"))) throw invalid("质量首步 input 不完整");
        Map<String, Object> nextInput = Map.of("userInstruction", string(previous, "userInstruction"),
                "failedStepId", body.getStepId(), "failedResultHash", body.getResultHash(),
                "failureCode", QUALITY_CORRECTION_REQUIRED);
        appendGenerationStep(tx, locked, correction, nextInput,
                locked.step().get("evidenceBundleId", String.class), null, now);
        updateRun(tx, runId, "running", sequence, null, null, now);
        return true;
    }

    private static boolean isQualityRun(Record run) {
        return "quality".equals(run.get("workflow", String.class))
                && "consistency".equals(run.get("operation", String.class));
    }

    private WorkflowQualityCompletion qualityCompletion() {
        WorkflowQualityCompletion completion = qualityCompletion.get();
        if (completion == null) throw new IllegalStateException("一致性终检耐久结果投影端口未装配");
        return completion;
    }

    private void cancelInvalidatedQuality(DSLContext tx, Locked locked, long sequence, LocalDateTime now) {
        String runId = locked.run().get("id", String.class);
        String cancelRequestId = "quality-invalidated." + runId;
        tx.execute("UPDATE public.\"WorkflowRun\" SET \"cancelRequestId\" = ?, \"cancelRequestedAt\" = ? WHERE id = ?",
                cancelRequestId, now, runId);
        sequence = appendEvent(tx, runId, sequence, "cancelled", Map.of("cancelRequestId", cancelRequestId),
                "run:cancelled", now);
        updateRun(tx, runId, "cancelled", sequence, "RUN_CANCELLED", now, now);
    }

    private void completeShortMedium(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            ExecutionPlanSnapshot.Step generator, ExecutionStepResult body, WorkflowStepUsage usage,
            Map<String, Object> output, LocalDateTime now) {
        if (!"short_medium".equals(plan.operation().workflow()) || !plan.reviewers().isEmpty()
                || !"none".equals(plan.reviewPolicy().mode()) || locked.step().get("artifactId") != null) {
            throw invalid("中短篇生成不能绑定长篇复审或候选返工");
        }
        String runId = locked.run().get("id", String.class);
        String novelId = locked.run().get("novelId", String.class);
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        if (!Objects.equals(bundleId, locked.run().get("currentEvidenceBundleId", String.class))) {
            throw invalid("中短篇生成必须绑定当前不可变来源");
        }
        var evidence = new JooqShortMediumWorkflowEvidence(json);
        var snapshot = evidence.load(tx, runId, novelId, bundleId, plan);
        String operation = plan.operation().operation();
        Map<String, Object> input = readObject(locked.step().get("input", String.class));
        requireHash(locked.step().get("inputHash", String.class), input, "short medium generation input");
        int index = ShortMediumSegments.index(operation, snapshot.context(), input);
        int count = ShortMediumSegments.segmentCount(operation, snapshot.context());
        if (index != snapshot.segments().size()) throw invalid("中短篇生成前缀不完整或序号重复");
        String text = ShortMediumSegments.output(operation, output, generator.outputSchema().jsonSchema());
        completeStep(tx, locked, body.getResultHash(), usage, canonicalJson(output), null, null, now);
        long sequence = appendStepFinished(tx, locked, "completed", null, locked.run().get("lastEventSequence", Long.class), now);
        var completed = new ShortMediumSegments.Segment(body.getStepId(), index, text, ShortMediumSegments.sha256(text), body.getResultHash());
        List<ShortMediumSegments.Segment> segments = new ArrayList<>(snapshot.segments());
        segments.add(completed);
        if (index + 1 < count) {
            if (count > plan.runBudget().maxModelCalls()) throw invalid("分段计划超过原 Run 调用额度");
            List<WorkflowEvidenceItemPlan> items = new ArrayList<>(snapshot.items());
            items.add(new WorkflowEvidenceItemPlan("short_medium_segment", body.getStepId(), true, null, null, null,
                    Map.of("index", index, "content", text, "contentSha256", completed.contentSha256()), null, null,
                    Map.of("role", "completed_segment")));
            var next = new JooqWorkflowStartRepository(database, ids, clock, json).appendEvidence(tx, runId,
                    snapshot.version() + 1, generator.evidencePolicy(), items, now);
            appendGenerationStep(tx, locked, generator, Map.of("segmentIndex", index + 1, "segmentCount", count), next.id(), null, now);
            tx.execute("UPDATE public.\"WorkflowRun\" SET \"currentEvidenceBundleId\" = ? WHERE id = ?", next.id(), runId);
            sequence = appendEvent(tx, runId, sequence, "evidence_ready", Map.of("bundleId", next.id(), "bundleVersion", next.version(),
                    "manifestSha256", next.manifestSha256(), "totalBytes", next.totalBytes()), "evidence:" + next.version(), now);
            updateRun(tx, runId, "running", sequence, null, null, now);
            return;
        }
        String fullText = ShortMediumSegments.join(segments, count);
        WorkflowShortMediumCompletion completion = shortMediumCompletion.get();
        if (completion == null) throw new IllegalStateException("中短篇业务完成端口未装配");
        WorkflowShortMediumCompletion.Completion result;
        try {
            // 业务冲突回滚候选写入，但已发生的模型结果和用量仍能收敛为明确失败。
            result = tx.transactionResult(configuration -> completion.complete(DSL.using(configuration),
                    new WorkflowShortMediumCompletion.CompletionRequest(locked.run().get("userId", String.class), novelId,
                            locked.run().get("chapterId", String.class), operation, runId, body.getStepId(), body.getResultHash(),
                            bundleId, snapshot.contextItemId(), snapshot.contextHash(), snapshot.context(), fullText)));
        } catch (ApiException error) {
            if (error.statusCode() >= 500 || error.statusCode() == 408 || error.statusCode() == 429) throw error;
            failRun(tx, locked, error.code(), false, sequence, now);
            return;
        }
        boolean report = "full_check".equals(operation);
        if (report != (result.checkReport() != null)
                || report && !Map.of("text", fullText).equals(result.checkReport())) {
            throw new IllegalStateException("中短篇业务结果与冻结操作不一致");
        }
        String resultId = report ? body.getStepId() : result.candidateVersionId();
        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("schema", ShortMediumSegments.MANIFEST_SCHEMA);
        manifest.put("runId", runId);
        manifest.put("operation", operation);
        manifest.put("evidenceBundleId", bundleId);
        manifest.put("contextItemId", snapshot.contextItemId());
        manifest.put("contextContentSha256", snapshot.contextHash());
        manifest.put("segmentCount", count);
        manifest.put("segments", segments.stream().map(ShortMediumSegments.Segment::reference).toList());
        manifest.put("contentSha256", ShortMediumSegments.sha256(fullText));
        String manifestId = appendIntentControl(tx, runId, ShortMediumSegments.MANIFEST_PURPOSE, "persistence", manifest, bundleId, now);
        Map<String, Object> resultReference = Map.of(report ? "checkReportStepId" : "candidateVersionId", resultId);
        String resultHash = ExecutionCanonicalJson.sha256(Map.of("inputHash", ExecutionCanonicalJson.sha256(manifest), "output", resultReference));
        tx.execute("UPDATE public.\"WorkflowStep\" SET output = ?, \"resultHash\" = ? WHERE id = ? AND \"runId\" = ?",
                canonicalJson(resultReference), resultHash, manifestId, runId);
        if (!report) {
            sequence = appendEvent(tx, runId, sequence, "candidate_ready", Map.of("stepId", body.getStepId(),
                    "artifactId", resultId, "artifactRevision", 1), "candidate:" + resultId + ":1", now);
        }
        sequence = appendEvent(tx, runId, sequence, "completed", Map.of("outcomeType", report ? "check_report" : "short_candidate",
                "resultId", resultId), "run:completed", now);
        updateRun(tx, runId, "completed", sequence, null, now, now);
    }

    private void completeEvidenceExpansion(DSLContext tx, Locked locked, ExecutionStepResult body,
            WorkflowStepUsage usage, LocalDateTime now) {
        ExecutionPlanSnapshot plan = executionPlan(locked.run());
        ExecutionPlanSnapshot.Step generator = frozenStep(locked, plan);
        if (!isAgentUpdates(plan) || !"output.agent_updates_step.v1".equals(generator.outputSchema().name())) {
            throw invalid("当前生成器未授权证据扩展输出");
        }
        var expansion = body.getEvidenceExpansion();
        Map<String, Object> material = WorkflowCallbackValues.evidenceExpansionMap(expansion);
        String runId = locked.run().get("id", String.class);
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        Record bundle = tx.fetchOne("SELECT version FROM public.\"WorkflowEvidenceBundle\" WHERE id = ? AND \"runId\" = ?", bundleId, runId);
        if (bundle == null || !Objects.equals(bundleId, locked.run().get("currentEvidenceBundleId", String.class))
                || !Objects.equals(bundleId, expansion.getSourceBundleId())
                || !Objects.equals(bundle.get("version", Integer.class), expansion.getSourceBundleVersion())
                || !"agent_updates_sources_required".equals(expansion.getReasonCode())
                || expansion.getMaxAdditionalBytes().longValue() != generator.stepBudget().budget().maxInputTokens() * 4L) {
            throw invalid("证据扩展的来源身份或字节额度与当前 Step 不一致");
        }
        String expectedRequestId = "evidence-" + ExecutionCanonicalJson.sha256(Map.of(
                "stepId", body.getStepId(), "requestHash", body.getRequestHash(), "items", material.get("items"))).substring(0, 32);
        if (!expectedRequestId.equals(expansion.getRequestId())) throw invalid("证据扩展请求身份与完整需求不一致");

        String artifactId = locked.step().get("artifactId", String.class);
        Integer artifactRevision = locked.step().get("artifactRevision", Integer.class);
        completeStep(tx, locked, body.getResultHash(), usage, canonicalJson(Map.of("evidenceExpansion", material)),
                artifactId, artifactRevision, now);
        long sequence = appendStepFinished(tx, locked, "completed", null, locked.run().get("lastEventSequence", Long.class), now);
        List<WorkflowEvidenceItemPlan> items;
        try {
            WorkflowOutputValidator.validate(generator.outputSchema().jsonSchema(), Map.of("evidenceRequest", material.get("items")));
            long modelSteps = tx.fetchOne("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND \"stepType\" = 'agent' AND purpose <> 'resolve_intent'", runId).get(0, Long.class);
            if (modelSteps + 1 + plan.reviewers().size() > plan.runBudget().maxModelCalls()) {
                failRun(tx, locked, "WORKFLOW_RUN_BUDGET_EXCEEDED", false, sequence, now);
                return;
            }
            WorkflowStructuredCandidatePreparation preparation = structuredCandidates.get();
            if (preparation == null) throw new IllegalStateException("结构化资料证据补齐尚未装配");
            items = preparation.expand(tx, locked.run().get("userId", String.class), locked.run().get("novelId", String.class), runId, bundleId, expansion);
        } catch (ApiException error) {
            // 已发生的模型用量必须收口；确定性资料错误成为可见 Run 失败，不反复拒绝同一已付费结果。
            if (error.statusCode() >= 500 || error.statusCode() == 408 || error.statusCode() == 429) throw error;
            failRun(tx, locked, error.code(), false, sequence, now);
            return;
        } catch (IllegalArgumentException error) {
            failRun(tx, locked, "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID", false, sequence, now);
            return;
        }
        var next = new JooqWorkflowStartRepository(database, ids, clock, json).appendEvidence(tx, runId,
                expansion.getSourceBundleVersion() + 1, plan.generator().evidencePolicy(), items, now);
        Map<String, Object> input = readObject(locked.step().get("input", String.class));
        requireHash(locked.step().get("inputHash", String.class), input, "evidence expansion generation input");
        appendGenerationStep(tx, locked, generator, input, next.id(),
                artifactId == null ? null : new Artifact(artifactId, artifactRevision), now);
        tx.execute("UPDATE public.\"WorkflowRun\" SET \"currentEvidenceBundleId\" = ? WHERE id = ?", next.id(), runId);
        sequence = appendEvent(tx, runId, sequence, "evidence_ready", Map.of("bundleId", next.id(),
                "bundleVersion", next.version(), "manifestSha256", next.manifestSha256(), "totalBytes", next.totalBytes()),
                "evidence:" + next.version(), now);
        updateRun(tx, runId, "running", sequence, null, null, now);
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
        boolean beatPlan = "long_serial.plan_chapter".equals(executionPlan.operation().key());
        boolean chapterDraft = isChapterDraft(executionPlan);
        boolean structured = isAgentUpdates(executionPlan);
        if (!beatPlan && !chapterDraft && !structured) validateSelectionGenerationOutput(frozenStep.outputSchema(), output);
        Artifact artifact = structured ? materializeAgentUpdates(transaction, locked, executionPlan, output, body.getResultHash(), now)
                : chapterDraft ? materializeChapterDraft(
                transaction, locked, executionPlan, output, body.getResultHash(), now) : beatPlan ? materializeBeatPlan(
                transaction, locked, executionPlan, output, body.getResultHash(), now) : materializeSelection(
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
                canonicalJson(structured ? Map.of("artifactId", artifact.id(), "artifactRevision", artifact.revision(), "updatesSha256", output.get("updatesSha256"))
                        : beatPlan || chapterDraft ? Map.of("artifactId", artifact.id(),
                        "artifactRevision", artifact.revision(), "contentSha256", output.get("contentSha256")) : output),
                frozenArtifactId == null ? artifact.id() : frozenArtifactId,
                frozenArtifactRevision == null ? artifact.revision() : frozenArtifactRevision,
                now);
        Map<String, Object> reviewerCandidate = output;
        if (beatPlan || chapterDraft) {
            Record exact = transaction.fetchOne("SELECT \"payloadJson\" FROM public.\"ReviewArtifactRevision\" WHERE \"artifactId\" = ? AND revision = ?",
                    artifact.id(), artifact.revision());
            reviewerCandidate = chapterDraft ? DurableChapterDraftArtifact.output(readObject(exact.get("payloadJson", String.class)))
                    : DurableBeatPlanArtifact.output(readObject(exact.get("payloadJson", String.class)));
        }
        List<Map<String, Object>> reviewerSteps = createReviewerSteps(
                transaction, locked, executionPlan, artifact, reviewerCandidate, now);
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

    private void completeChapterReview(DSLContext transaction, Locked locked, ExecutionPlanSnapshot plan,
            ExecutionPlanSnapshot.Step frozenStep, ExecutionStepResult body, WorkflowStepUsage usage,
            Map<String, Object> output, LocalDateTime now) {
        requireReadOnlyPlan(locked, plan);
        try {
            WorkflowOutputValidator.validate(frozenStep.outputSchema().jsonSchema(), output);
        } catch (IllegalArgumentException exception) {
            throw invalid("审阅报告不符合冻结 Schema");
        }
        if (!output.keySet().equals(java.util.Set.of("report"))
                || !(output.get("report") instanceof String report) || report.isBlank()) {
            throw invalid("审阅 output 必须精确包含完整非空白 report");
        }
        String sessionId = locked.run().get("writingSessionId", String.class);
        String resultId = sessionId == null ? body.getStepId() : persistReadOnlyMessage(
                transaction, locked, frozenStep, report, body.getResultHash(), "chapter_review_report", now);
        completeStep(transaction, locked, body.getResultHash(), usage, canonicalJson(output), null, null, now);
        long sequence = appendStepFinished(transaction, locked, "completed", null,
                locked.run().get("lastEventSequence", Long.class), now);
        sequence = appendEvent(transaction, body.getRunId(), sequence, "completed",
                Map.of("outcomeType", "chapter_review_report", "resultId", resultId), "run:completed", now);
        updateRun(transaction, body.getRunId(), "completed", sequence, null, now, now);
    }

    private static boolean isChapterDraft(ExecutionPlanSnapshot plan) {
        return java.util.Set.of("long_serial.write_chapter", "long_serial.rewrite_scene").contains(plan.operation().key());
    }

    private static void requireChatAnswerPlan(
            Locked locked, ExecutionPlanSnapshot executionPlan) {
        requireReadOnlyPlan(locked, executionPlan);
        String writingSessionId = locked.run().get("writingSessionId", String.class);
        if (writingSessionId == null || writingSessionId.isBlank()) {
            throw invalid("问答 Run 缺少写作会话归属");
        }
    }

    private static void requireReadOnlyPlan(Locked locked, ExecutionPlanSnapshot executionPlan) {
        if (executionPlan.operation().mutating()
                || !executionPlan.operation().deterministicValidators().containsAll(List.of(
                        "validator.schema_strict.v1", "validator.complete_output.v1"))
                || !"none".equals(executionPlan.reviewPolicy().mode())
                || !executionPlan.reviewers().isEmpty()
                || !executionPlan.systemSteps().isEmpty()
                || locked.step().get("artifactId", String.class) != null
                || locked.step().get("artifactRevision", Integer.class) != null) {
            throw invalid("只读 Step 与冻结的无评审执行计划不一致");
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
        return persistReadOnlyMessage(transaction, locked, frozenStep, answer, resultHash, "chat_answer", now);
    }

    private String persistReadOnlyMessage(DSLContext transaction, Locked locked,
            ExecutionPlanSnapshot.Step frozenStep, String answer, String resultHash, String outcomeType, LocalDateTime now) {
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
            throw invalid("只读 Run 绑定的写作会话不存在或范围不一致");
        }
        String messageId = ids.next();
        String agentId = "编辑";
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("engineVersion", 2);
        source.put("runId", locked.run().get("id", String.class));
        source.put("operation", executionContext(locked.run()).effectiveOperation());
        source.put("stepId", locked.step().get("id", String.class));
        source.put("modelProfile", frozenStep.modelProfile().profile());
        source.put("resultHash", resultHash);
        source.put("outcomeType", outcomeType);
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
        boolean outline = "long_serial.rewrite_outline_selection".equals(executionPlan.operation().key());
        if ((!outline && !"long_serial.rewrite_chapter_selection".equals(executionPlan.operation().key()))
                || !(outline ? "apply.outline_selection.v1" : "apply.chapter_selection.v1")
                        .equals(executionPlan.operation().applyHandler())
                || !executionPlan.operation().deterministicValidators().containsAll(List.of(
                        "validator.schema_strict.v1",
                        "validator.unicode_selection.v1",
                        "validator.selection_source_hash.v1",
                        "validator.selection_outside_unchanged.v1"))) {
            throw invalid("选区操作与冻结应用策略不一致");
        }
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        String chapterId = locked.run().get("chapterId", String.class);
        String resourceType = outline ? locked.run().get("targetType", String.class) : "chapter_content";
        String resourceId = outline ? locked.run().get("targetId", String.class) : chapterId;
        if (outline && !java.util.Set.of("outline_content", "outline_node_content").contains(resourceType)) {
            throw invalid("大纲选区必须绑定总纲或节点来源");
        }
        Record evidence = transaction.fetchOne(
                """
                SELECT id, "resourceId", "resourceUpdatedAt", "contentText", "contentSha256", "rangeJson", "metadataJson"
                FROM public."WorkflowEvidenceItem"
                WHERE "bundleId" = ? AND "resourceType" = ?
                  AND "resourceId" = ? AND exists AND "contentType" = 'text'
                """,
                bundleId,
                resourceType,
                resourceId);
        if (evidence == null || evidence.get("rangeJson", String.class) == null) {
            throw invalid("选区改写 Evidence 缺少完整正文或码点范围");
        }
        String replacement = string(output, "replacement");
        String replacementHash = string(output, "contentSha256");
        if (!sha256(replacement).equals(replacementHash)) {
            throw invalid("选区替换文本与 contentSha256 不一致");
        }
        String source = evidence.get("contentText", String.class);
        if (source == null || !sha256(source).equals(evidence.get("contentSha256", String.class))) {
            throw invalid("选区 Evidence 完整原文哈希不一致");
        }
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
        if (outline) {
            requireOutlineSelectionMetadata(evidence, baseHash, selectedHash);
            Map<String, Object> binding = object(runInput.get("selectionTarget"), "大纲 selectionTarget");
            if (!resourceType.equals(binding.get("resourceType")) || !resourceId.equals(binding.get("resourceId"))
                    || !baseHash.equals(binding.get("baseContentHash"))
                    || !selectedHash.equals(binding.get("selectedTextHash"))
                    || start != integer(binding, "selectionStart") || end != integer(binding, "selectionEnd")
                    || !DatabaseTimestamp.api(evidence.get("resourceUpdatedAt", LocalDateTime.class)).toInstant()
                            .equals(java.time.OffsetDateTime.parse(string(binding, "baseUpdatedAt")).toInstant())) {
                throw invalid("大纲选区 Run 与冻结来源绑定不一致");
            }
            var stored = DurableOutlineSelectionArtifact.create(bundleId, evidence.get("id", String.class),
                    resourceType, resourceId, DatabaseTimestamp.api(evidence.get("resourceUpdatedAt", LocalDateTime.class)),
                    baseHash, start, end, selectedHash, replacement, replacementHash, sha256(candidate),
                    locked.step().get("id", String.class), generationResultHash);
            return persistCandidate(transaction, locked, "outline_draft", "大纲选区改写", null,
                    stored.payload(), stored.diff(), now);
        }
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
        return persistCandidate(transaction, locked, "chapter_draft", "章节选区改写", null,
                stored.payload(), stored.diff(), now);
    }

    private Artifact materializeBeatPlan(DSLContext transaction, Locked locked,
            ExecutionPlanSnapshot executionPlan, Map<String, Object> output,
            String resultHash, LocalDateTime now) {
        if (!"long_serial.plan_chapter".equals(executionPlan.operation().key())
                || !"apply.beat_plan.v1".equals(executionPlan.operation().applyHandler())) {
            throw invalid("章节计划未绑定正式 BeatPlan 应用器");
        }
        try {
            DurableBeatPlanArtifact.validateOutput(output);
            Map<String, Object> semantic = new LinkedHashMap<>(output);
            semantic.remove("contentSha256");
            semantic.remove("beatCount");
            List<Map<String, Object>> scenes = new ArrayList<>();
            for (Object value : (List<?>) semantic.get("sceneBeats")) {
                Map<String, Object> scene = new LinkedHashMap<>((Map<String, Object>) value);
                scene.remove("order");
                scenes.add(scene);
            }
            semantic.put("sceneBeats", scenes);
            WorkflowOutputValidator.validate(executionPlan.generator().outputSchema().jsonSchema(), semantic);
        } catch (IllegalArgumentException exception) {
            throw invalid("章节计划不符合冻结的严格语义结果契约");
        }
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        Record bundle = transaction.fetchOne("""
                SELECT bundle."manifestSha256" FROM public."WorkflowEvidenceBundle" AS bundle
                JOIN public."WorkflowEvidenceItem" AS item ON item."bundleId" = bundle.id
                WHERE bundle.id = ? AND bundle."runId" = ?
                  AND item."resourceType" = 'chapter_plan_context' AND item."resourceId" = ?
                  AND item.exists AND item."contentType" = 'json'
                """, bundleId, locked.run().get("id", String.class), locked.run().get("chapterId", String.class));
        if (bundle == null) throw invalid("章节计划缺少不可变完整 Evidence");
        DurableBeatPlanArtifact.Stored stored = DurableBeatPlanArtifact.create(bundleId,
                bundle.get("manifestSha256", String.class), locked.run().get("chapterId", String.class),
                output, locked.step().get("id", String.class), resultHash);
        return persistCandidate(transaction, locked, "beat_plan", string(output, "title"),
                string(output, "summary"), stored.payload(), stored.diff(), now);
    }

    private static boolean isAgentUpdates(ExecutionPlanSnapshot plan) {
        return "apply.agent_updates.v1".equals(plan.operation().applyHandler()) && Set.of(
                "create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing")
                .contains(plan.operation().operation());
    }

    private Artifact materializeAgentUpdates(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            Map<String, Object> output, String resultHash, LocalDateTime now) {
        DurableAgentUpdatesArtifact.validateOutput(output, plan.generator().outputSchema().jsonSchema());
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        Record bundle = tx.fetchOne("SELECT \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ? AND \"runId\" = ?",
                bundleId, locked.run().get("id", String.class));
        if (bundle == null) throw invalid("结构化候选缺少冻结 Evidence");
        var stored = DurableAgentUpdatesArtifact.create(plan.operation().operation(), bundleId,
                bundle.get("manifestSha256", String.class), locked.run().get("novelId", String.class), output,
                locked.step().get("id", String.class), resultHash, plan.generator().outputSchema().jsonSchema());
        Artifact artifact = persistCandidate(tx, locked, "agent_updates", "结构化资料修改建议", string(output, "summary"),
                stored.payload(), stored.diff(), now);
        WorkflowStructuredCandidatePreparation preparation = structuredCandidates.get();
        if (preparation == null) throw invalid("结构化候选业务物化器尚未装配");
        preparation.validate(tx, locked.run().get("userId", String.class), locked.run().get("novelId", String.class),
                locked.run().get("id", String.class), bundleId, artifact.id(), artifact.revision(), output);
        return artifact;
    }

    private Artifact materializeChapterDraft(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            Map<String, Object> output, String resultHash, LocalDateTime now) {
        try {
            DurableChapterDraftArtifact.validateOutput(output);
            WorkflowOutputValidator.validate(plan.generator().outputSchema().jsonSchema(),
                    Map.of("summary", output.get("summary"), "content", output.get("content")));
        } catch (IllegalArgumentException exception) {
            throw invalid("正文草案不符合冻结的严格语义结果契约");
        }
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        Record bundle = tx.fetchOne("""
                SELECT bundle."manifestSha256", item."contentJson", item."contentSha256"
                FROM public."WorkflowEvidenceBundle" AS bundle
                JOIN public."WorkflowEvidenceItem" AS item ON item."bundleId" = bundle.id
                WHERE bundle.id = ? AND bundle."runId" = ? AND item."resourceType" = 'chapter_writing_context'
                  AND item."resourceId" = ? AND item.exists AND item."contentType" = 'json'
                """, bundleId, locked.run().get("id", String.class), locked.run().get("chapterId", String.class));
        if (bundle == null || !ExecutionCanonicalJson.sha256(readObject(bundle.get("contentJson", String.class)))
                .equals(bundle.get("contentSha256", String.class))) throw invalid("正文草案缺少完整可信 Evidence");
        var stored = DurableChapterDraftArtifact.create(plan.operation().operation(), bundleId, bundle.get("manifestSha256", String.class),
                locked.run().get("chapterId", String.class), output, locked.step().get("id", String.class), resultHash);
        return persistCandidate(tx, locked, "chapter_draft", "章节正文草案", string(output, "summary"), stored.payload(), stored.diff(), now);
    }

    private Artifact persistCandidate(DSLContext transaction, Locked locked, String kind,
            String title, String summary, Map<String, Object> payload, Map<String, Object> diff, LocalDateTime now) {
        return persistCandidate(transaction, locked, kind, title, summary, payload, diff, now,
                locked.step().get("modelProfile", String.class));
    }

    private Artifact persistCandidate(DSLContext transaction, Locked locked, String kind,
            String title, String summary, Map<String, Object> payload, Map<String, Object> diff, LocalDateTime now, String profile) {
        String chapterId = locked.run().get("chapterId", String.class);
        String payloadJson = canonicalJson(payload);
        String diffJson = canonicalJson(diff);
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
                      ?, ?, ?, NULL, ?, ?, CAST(? AS "ReviewArtifactKind"),
                      CAST('under_review' AS "ReviewArtifactStatus"), ?, ?, ?, ?, ?, ?, NULL, 1, ?, ?
                    )
                    """,
                    artifactId,
                    locked.run().get("novelId", String.class),
                    chapterId,
                    locked.run().get("id", String.class),
                    "workflow:" + locked.run().get("id", String.class) + ":candidate",
                    kind,
                    title,
                    summary,
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
                        title = ?, summary = ?, "payloadJson" = ?, "diffJson" = ?, "updatedByAgent" = ?,
                        "reviewerAgent" = NULL, revision = ?, "updatedAt" = ?
                    WHERE id = ? AND "workflowRunId" = ? AND revision = ?
                    """,
                    title,
                    summary,
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ids.next(),
                artifactId,
                revision,
                summary,
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
        task.put("operation", executionPlan.operation().operation());
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
        WorkflowExecutionContext context = executionContext(locked.run());
        if (context.initialIntentPlan() != null) {
            task.put("target", Map.of("type", "chapter", "id", locked.run().get("chapterId", String.class)));
            task.put("scope", context.selectedScope());
        }
        Object userInstruction = task.get("userInstruction");
        if (userInstruction != null && !(userInstruction instanceof String)) {
            throw invalid("Run 的 userInstruction 必须是字符串或 null");
        }
        if ("long_serial.plan_chapter".equals(executionPlan.operation().key())
                || isChapterDraft(executionPlan)
                || isAgentUpdates(executionPlan)
                || "long_serial.rewrite_outline_selection".equals(executionPlan.operation().key())) {
            Map<String, Object> generationInput = readObject(locked.step().get("input", String.class));
            if (REVIEW.equals(locked.step().get("purpose", String.class))) {
                generationInput = object(generationInput.get("task"), "Reviewer task");
            }
            task.put("userInstruction", generationInput.get("userInstruction"));
            if (generationInput.containsKey("originalUserInstruction")) {
                task.put("originalUserInstruction", generationInput.get("originalUserInstruction"));
            }
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
        boolean planPolicy = "long_serial.plan_chapter".equals(executionPlan.operation().key())
                && "review.chapter_plan_one_revision_else_author.v1".equals(executionPlan.reviewPolicy().mergePolicy());
        boolean chapterPolicy = isChapterDraft(executionPlan)
                && "review.chapter_draft.patch_or_author.v1".equals(executionPlan.reviewPolicy().mergePolicy());
        boolean outlinePolicy = "long_serial.rewrite_outline_selection".equals(executionPlan.operation().key())
                && "review.outline_selection_one_revision_else_author.v1".equals(executionPlan.reviewPolicy().mergePolicy());
        boolean structuredPolicy = isAgentUpdates(executionPlan)
                && "review.agent_updates_one_revision_else_author.v1".equals(executionPlan.reviewPolicy().mergePolicy());
        if ((!planPolicy && !chapterPolicy && !outlinePolicy && !structuredPolicy && !"review.merge_all_pass_else_author.v1"
                        .equals(executionPlan.reviewPolicy().mergePolicy()))
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
                       evaluation."findingsJson", step.ordinal
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
        if ((planPolicy || outlinePolicy || structuredPolicy) && "complete".equals(availability) && "issues_found".equals(verdict)
                && enqueueAutomaticRevision(transaction, locked, executionPlan, evaluations, false, now)) {
            transaction.execute("""
                    UPDATE public."ReviewArtifact" SET status = CAST('draft' AS "ReviewArtifactStatus"), "updatedAt" = ?
                    WHERE id = ? AND "workflowRunId" = ? AND revision = ?
                    """, now, artifactId, locked.run().get("id", String.class), artifactRevision);
            updateRun(transaction, locked.run().get("id", String.class), "running", sequence, null, null, now);
            return;
        }
        if (chapterPolicy && "complete".equals(availability) && "issues_found".equals(verdict)) {
            Long revisedSequence = automaticallyReviseChapter(transaction, locked, executionPlan, evaluations, sequence, now);
            if (revisedSequence != null) {
                updateRun(transaction, locked.run().get("id", String.class), "running", revisedSequence, null, null, now);
                return;
            }
        }
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

    private boolean enqueueAutomaticRevision(DSLContext tx, Locked locked,
            ExecutionPlanSnapshot plan, List<Record> evaluations, boolean chapterDraft, LocalDateTime now) {
        boolean outlineSelection = "long_serial.rewrite_outline_selection".equals(plan.operation().key());
        boolean structured = isAgentUpdates(plan);
        String localDimension = chapterDraft ? "chapter_draft.local"
                : outlineSelection ? "outline_selection.local" : structured ? "agent_updates.local" : "chapter_plan.local";
        List<Map<String, Object>> findings = new ArrayList<>();
        for (Record evaluation : evaluations) {
            // 任何分歧或无法判断都交作者；模型不能自行把结构阻塞降级为局部返工。
            if (!"issues_found".equals(evaluation.get("contentVerdict", String.class))) return false;
            List<Map<String, Object>> values = json.readValue(evaluation.get("findingsJson", String.class), new TypeReference<>() {});
            if (values.isEmpty()) return false;
            for (Map<String, Object> finding : values) {
                if (!localDimension.equals(finding.get("dimension"))
                        || !(finding.get("confidence") instanceof Number confidence)
                        || !Double.isFinite(confidence.doubleValue()) || confidence.doubleValue() < 0.8) return false;
            }
            findings.addAll(values);
        }
        String runId = locked.run().get("id", String.class);
        String artifactId = locked.step().get("artifactId", String.class);
        // 资料补齐也使用 generation，但没有生成候选；只将真正的候选产出计入返工次数。
        long generations = structured
                ? tx.fetchOne("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose = 'generation' AND status = 'completed' AND output::jsonb ->> 'artifactId' = ?", runId, artifactId).get(0, Long.class)
                : tx.fetchOne("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose IN ('generation', 'candidate_patch')", runId).get(0, Long.class);
        long modelSteps = tx.fetchOne("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND \"stepType\" = CAST('agent' AS \"WorkflowStepType\") AND purpose <> 'resolve_intent'", runId).get(0, Long.class);
        if (generations - 1 >= Math.min(1, plan.reviewPolicy().maxAutomaticRevisions())
                || modelSteps + 1 + plan.reviewers().size() > plan.runBudget().maxModelCalls()) return false;
        int revision = locked.step().get("artifactRevision", Integer.class);
        Record stored = tx.fetchOne("""
                SELECT revision."payloadJson", revision."diffJson" FROM public."ReviewArtifact" AS artifact
                JOIN public."ReviewArtifactRevision" AS revision ON revision."artifactId" = artifact.id AND revision.revision = artifact.revision
                WHERE artifact.id = ? AND artifact."workflowRunId" = ? AND artifact.revision = ?
                  AND artifact."payloadJson" = revision."payloadJson" AND artifact."diffJson" = revision."diffJson"
                FOR UPDATE OF artifact, revision
                """, artifactId, runId, revision);
        if (stored == null) throw invalid("自动返工引用的候选 revision 不一致");
        Record bundle = tx.fetchOne("SELECT id, version, \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ? AND \"runId\" = ?",
                locked.step().get("evidenceBundleId", String.class), runId);
        if (bundle == null) throw invalid("自动返工缺少冻结 Evidence");
        Map<String, Object> payload = readObject(stored.get("payloadJson", String.class));
        Map<String, Object> structuredOutput = null;
        if (chapterDraft) {
            DurableChapterDraftArtifact.reconstruct(plan.operation().operation(), payload, readObject(stored.get("diffJson", String.class)),
                    bundle.get("id", String.class), bundle.get("manifestSha256", String.class), locked.run().get("chapterId", String.class),
                    chapterWritingContent(tx, locked));
        } else if (outlineSelection) {
            DurableOutlineSelectionArtifact.reconstruct(payload, readObject(stored.get("diffJson", String.class)),
                    outlineSelectionEvidence(tx, locked));
        } else if (structured) {
            structuredOutput = reconstructStructuredRevision(tx, locked, plan, payload,
                    readObject(stored.get("diffJson", String.class)), bundle, artifactId, revision);
        } else {
            DurableBeatPlanArtifact.reconstruct(payload, readObject(stored.get("diffJson", String.class)),
                    bundle.get("id", String.class), bundle.get("manifestSha256", String.class), locked.run().get("chapterId", String.class));
        }
        Record originalGeneration = tx.fetchOne("""
                SELECT input FROM public."WorkflowStep" WHERE "runId" = ? AND purpose = 'generation'
                ORDER BY ordinal ASC LIMIT 1
                """, runId);
        if (originalGeneration == null) throw invalid("自动返工缺少原始 generation 输入");
        Map<String, Object> input = new LinkedHashMap<>(readObject(originalGeneration.get("input", String.class)));
        input.put("originalUserInstruction", input.get("userInstruction"));
        input.put("userInstruction", (chapterDraft ? "依据同一冻结来源修正下列明确局部问题，输出完整正文："
                : outlineSelection ? "依据同一冻结来源修正下列明确局部问题，仅输出完整选区 replacement："
                : structured ? "依据同一冻结来源修正下列明确局部问题，输出完整 summary 与 updates，不省略未被要求删除的候选变更："
                : "依据同一冻结来源修正下列明确局部问题，输出完整章节计划：") + canonicalJson(findings));
        if (structured) {
            input.put("previousCandidate", Map.of("artifactId", artifactId, "artifactRevision", revision,
                    "summary", structuredOutput.get("summary"), "updates", structuredOutput.get("updates")));
        } else if (outlineSelection) {
            input.put("previousCandidate", Map.of("artifactId", artifactId, "artifactRevision", revision,
                    "replacement", payload.get("replacement")));
        } else {
            input.put("previousArtifact", Map.of("artifactId", artifactId, "artifactRevision", revision,
                    "payload", chapterDraft ? DurableChapterDraftArtifact.output(payload) : DurableBeatPlanArtifact.output(payload)));
        }
        ExecutionPlanSnapshot.Step generator = plan.generator();
        String stepId = ids.next();
        String idempotencyKey = runId + "." + stepId;
        String inputHash = ExecutionCanonicalJson.sha256(input);
        Map<String, Object> request = new LinkedHashMap<>(stepRequestMaterial(locked.run(), stepId,
                idempotencyKey, inputHash, bundle, generator.evidencePolicy(), generator.lane(),
                generator.modelProfile().toMap(), generator.outputSchema().toMap(), generator.stepBudget().budgetMap(), new Artifact(artifactId, revision)));
        request.put("purpose", GENERATION);
        int ordinal = tx.fetchOne("SELECT max(ordinal) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", runId).get(0, Integer.class) + 1;
        tx.execute("""
                INSERT INTO public."WorkflowStep" (
                  id, "runId", "agentId", "stepType", status, input, "createdAt", ordinal,
                  purpose, lane, "attemptCount", "nextAttemptAt", "fencingToken", "idempotencyKey",
                  "requestHash", "inputHash", "evidenceBundleId", "artifactId", "artifactRevision",
                  "modelProfile", "modelProfileVersion", "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt", "updatedAt"
                ) VALUES (?, ?, ?, CAST('agent' AS "WorkflowStepType"), CAST('pending' AS "WorkflowStepStatus"),
                  ?, ?, ?, 'generation', ?, 0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, stepId, runId, generator.modelProfile().profile(), canonicalJson(input), now, ordinal,
                generator.lane(), now, idempotencyKey, ExecutionCanonicalJson.sha256(request), inputHash,
                bundle.get("id", String.class), artifactId, revision, generator.modelProfile().profile(),
                Integer.toString(generator.modelProfile().version()), generator.outputSchema().name(),
                Integer.toString(generator.outputSchema().version()), json.writeValueAsString(generator.stepBudget().stored()), now, now);
        return true;
    }

    private Map<String, Object> reconstructStructuredRevision(DSLContext tx, Locked locked,
            ExecutionPlanSnapshot plan, Map<String, Object> payload, Map<String, Object> diff,
            Record bundle, String artifactId, int revision) {
        String runId = locked.run().get("id", String.class);
        List<Record> producers = tx.fetch("""
                SELECT id, output, "resultHash", "resolvedModelJson", "usageJson", "evidenceBundleId"
                FROM public."WorkflowStep" WHERE "runId" = ? AND purpose = 'generation' AND status = 'completed'
                  AND output::jsonb ->> 'artifactId' = ? AND output::jsonb ->> 'artifactRevision' = ?
                """, runId, artifactId, Integer.toString(revision));
        if (producers.size() != 1) throw invalid("结构化返工缺少唯一候选生成记录");
        Record producer = producers.getFirst();
        if (!Objects.equals(bundle.get("id", String.class), producer.get("evidenceBundleId", String.class))) {
            throw invalid("结构化返工与候选来源不一致");
        }
        Map<String, Object> output = DurableAgentUpdatesArtifact.reconstruct(plan.operation().operation(), payload, diff,
                bundle.get("id", String.class), bundle.get("manifestSha256", String.class), locked.run().get("novelId", String.class),
                producer.get("id", String.class), producer.get("resultHash", String.class), plan.generator().outputSchema().jsonSchema());
        if (!readObject(producer.get("output", String.class)).equals(Map.of("artifactId", artifactId,
                "artifactRevision", revision, "updatesSha256", output.get("updatesSha256")))) {
            throw invalid("结构化返工的候选收据不一致");
        }
        requireHash(producer.get("resultHash", String.class), Map.of("resultKind", "output", "value", output,
                "resolvedModel", readObject(producer.get("resolvedModelJson", String.class)),
                "usage", readObject(producer.get("usageJson", String.class))), "structured revision source result");
        WorkflowStructuredCandidatePreparation preparation = structuredCandidates.get();
        if (preparation == null) throw new IllegalStateException("结构化返工的来源校验尚未装配");
        preparation.validate(tx, locked.run().get("userId", String.class), locked.run().get("novelId", String.class),
                runId, bundle.get("id", String.class), artifactId, revision, output);
        return output;
    }

    private DurableOutlineSelectionArtifact.Evidence outlineSelectionEvidence(DSLContext tx, Locked locked) {
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        Record evidence = tx.fetchOne("""
                SELECT item.* FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId"
                WHERE bundle.id = ? AND bundle."runId" = ? AND item."resourceType" = ?
                  AND item."resourceId" = ? AND item.exists AND item."contentType" = 'text'
                """, bundleId, locked.run().get("id", String.class),
                locked.run().get("targetType", String.class), locked.run().get("targetId", String.class));
        if (evidence == null || evidence.get("rangeJson", String.class) == null) {
            throw invalid("大纲选区返工缺少冻结完整 Evidence");
        }
        Map<String, Object> range = readObject(evidence.get("rangeJson", String.class));
        String content = evidence.get("contentText", String.class);
        int start = integer(range, "startCodePoint");
        int end = integer(range, "endCodePoint");
        if (content == null || start < 0 || end <= start || end > content.codePointCount(0, content.length())) {
            throw invalid("大纲选区返工来源范围无效");
        }
        requireOutlineSelectionMetadata(evidence, sha256(content), sha256(slice(content, start, end)));
        return new DurableOutlineSelectionArtifact.Evidence(bundleId, evidence.get("id", String.class),
                evidence.get("resourceType", String.class), evidence.get("resourceId", String.class),
                DatabaseTimestamp.api(evidence.get("resourceUpdatedAt", LocalDateTime.class)),
                evidence.get("contentText", String.class), evidence.get("contentSha256", String.class),
                integer(range, "startCodePoint"), integer(range, "endCodePoint"));
    }

    private void requireOutlineSelectionMetadata(Record evidence, String sourceHash, String selectedHash) {
        Map<String, Object> metadata = readObject(evidence.get("metadataJson", String.class));
        if (!metadata.keySet().equals(java.util.Set.of("role", "baseContentHash", "selectedTextHash"))
                || !"selection_source".equals(metadata.get("role"))
                || !sourceHash.equals(metadata.get("baseContentHash"))
                || !selectedHash.equals(metadata.get("selectedTextHash"))) {
            throw invalid("大纲选区 Evidence 来源 metadata 不一致");
        }
    }

    private Long automaticallyReviseChapter(DSLContext tx, Locked locked, ExecutionPlanSnapshot plan,
            List<Record> evaluations, long sequence, LocalDateTime now) {
        List<ChapterDraftPatches.Proposal> proposals = new ArrayList<>();
        List<Map<String, Object>> references = new ArrayList<>();
        int findingsCount = 0;
        for (Record evaluation : evaluations) {
            if (!"completed".equals(evaluation.get("executionStatus", String.class))
                    || !"issues_found".equals(evaluation.get("contentVerdict", String.class))) return null;
            List<Map<String, Object>> findings = json.readValue(evaluation.get("findingsJson", String.class), new TypeReference<>() {});
            if (findings.isEmpty()) return null;
            for (int index = 0; index < findings.size(); index++) {
                Map<String, Object> finding = findings.get(index);
                if (!"chapter_draft.local".equals(finding.get("dimension"))
                        || !(finding.get("confidence") instanceof Number confidence)
                        || !Double.isFinite(confidence.doubleValue()) || confidence.doubleValue() < 0.8) return null;
                findingsCount++;
                if (finding.get("candidatePatch") != null) {
                    Map<String, Object> patch = object(finding.get("candidatePatch"), "candidatePatch");
                    if (!patch.keySet().equals(java.util.Set.of("kind", "find", "replace")) || !"text_replace".equals(patch.get("kind"))) return null;
                    Map<String, Object> range = finding.get("candidateRange") == null ? null : object(finding.get("candidateRange"), "candidateRange");
                    proposals.add(new ChapterDraftPatches.Proposal(string(patch, "find"), string(patch, "replace"),
                            range == null ? null : integer(range, "startCodePoint"), range == null ? null : integer(range, "endCodePoint")));
                    references.add(Map.of("evaluationId", evaluation.get("id", String.class), "findingIndex", index));
                }
            }
        }
        String runId = locked.run().get("id", String.class);
        String artifactId = locked.step().get("artifactId", String.class);
        int oldRevision = locked.step().get("artifactRevision", Integer.class);
        if (proposals.isEmpty()) {
            if (!enqueueAutomaticRevision(tx, locked, plan, evaluations, true, now)) return null;
            tx.execute("UPDATE public.\"ReviewArtifact\" SET status = CAST('draft' AS \"ReviewArtifactStatus\"), \"updatedAt\" = ? WHERE id = ? AND revision = ?", now, artifactId, oldRevision);
            return sequence;
        }
        if (proposals.size() != findingsCount) return null;
        long modifications = tx.fetchOne("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND purpose IN ('generation','candidate_patch')", runId).get(0, Long.class);
        long modelSteps = tx.fetchOne("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ? AND \"stepType\" = CAST('agent' AS \"WorkflowStepType\") AND purpose <> 'resolve_intent'", runId).get(0, Long.class);
        if (modifications - 1 >= Math.min(1, plan.reviewPolicy().maxAutomaticRevisions())
                || modelSteps + plan.reviewers().size() > plan.runBudget().maxModelCalls()) return null;
        Record revision = tx.fetchOne("""
                SELECT rev."payloadJson", rev."diffJson" FROM public."ReviewArtifact" a
                JOIN public."ReviewArtifactRevision" rev ON rev."artifactId" = a.id AND rev.revision = a.revision
                WHERE a.id = ? AND a."workflowRunId" = ? AND a.revision = ?
                  AND a."payloadJson" = rev."payloadJson" AND a."diffJson" = rev."diffJson"
                FOR UPDATE OF a, rev
                """, artifactId, runId, oldRevision);
        if (revision == null) throw invalid("候选 patch 的精确修订不一致");
        Map<String, Object> oldPayload = readObject(revision.get("payloadJson", String.class));
        String bundleId = locked.step().get("evidenceBundleId", String.class);
        String manifest = tx.fetchOne("SELECT \"manifestSha256\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ? AND \"runId\" = ?", bundleId, runId).get(0, String.class);
        DurableChapterDraftArtifact.reconstruct(plan.operation().operation(), oldPayload, readObject(revision.get("diffJson", String.class)), bundleId,
                manifest, locked.run().get("chapterId", String.class), chapterWritingContent(tx, locked));
        String content;
        try {
            content = ChapterDraftPatches.apply(string(oldPayload, "content"), proposals);
        } catch (ChapterDraftPatches.Rejected exception) {
            return null;
        }
        Map<String, Object> output = DurableChapterDraftArtifact.deriveOutput(string(oldPayload, "summary"), content);
        String stepId = ids.next();
        Map<String, Object> input = Map.of("schemaVersion", 1, "runId", runId, "policy", plan.reviewPolicy().mergePolicy(),
                "artifactId", artifactId, "artifactRevision", oldRevision, "contentSha256", oldPayload.get("contentSha256"),
                "evidenceBundleId", bundleId, "findings", references);
        Map<String, Object> result = Map.of("artifactId", artifactId, "artifactRevision", oldRevision + 1, "contentSha256", output.get("contentSha256"));
        String resultHash = ExecutionCanonicalJson.sha256(result);
        var stored = DurableChapterDraftArtifact.create(plan.operation().operation(), bundleId, manifest, locked.run().get("chapterId", String.class), output, stepId, resultHash);
        Artifact artifact = persistCandidate(tx, locked, "chapter_draft", "章节正文草案", string(output, "summary"), stored.payload(), stored.diff(), now, "Core");
        int ordinal = tx.fetchOne("SELECT max(ordinal) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", runId).get(0, Integer.class) + 1;
        tx.execute("""
                INSERT INTO public."WorkflowStep" (id, "runId", "stepType", status, input, output, "createdAt", ordinal,
                  purpose, lane, "attemptCount", "fencingToken", "idempotencyKey", "requestHash", "inputHash", "resultHash",
                  "evidenceBundleId", "artifactId", "artifactRevision", "submittedAt", "updatedAt", "completedAt")
                VALUES (?, ?, CAST('persistence' AS "WorkflowStepType"), CAST('completed' AS "WorkflowStepStatus"), ?, ?, ?, ?,
                  'candidate_patch', 'control', 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, stepId, runId, canonicalJson(input), canonicalJson(result), now, ordinal,
                "candidate-patch:" + artifactId + ":" + oldRevision, ExecutionCanonicalJson.sha256(input), ExecutionCanonicalJson.sha256(input),
                resultHash, bundleId, artifactId, oldRevision, now, now, now);
        List<Map<String, Object>> reviewers = createReviewerSteps(tx, locked, plan, artifact, output, now);
        sequence = appendEvent(tx, runId, sequence, "candidate_ready", Map.of("stepId", stepId,
                "artifactId", artifactId, "artifactRevision", artifact.revision()), "candidate:" + artifactId + ":" + artifact.revision(), now);
        return appendEvent(tx, runId, sequence, "review_started", Map.of("artifactId", artifactId,
                "artifactRevision", artifact.revision(), "reviewerSteps", reviewers), "review:started:" + artifactId + ":" + artifact.revision(), now);
    }

    private String chapterWritingContent(DSLContext tx, Locked locked) {
        Record evidence = tx.fetchOne("""
                SELECT item."contentJson", item."contentSha256" FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId"
                WHERE bundle.id = ? AND bundle."runId" = ? AND item."resourceType" = 'chapter_writing_context'
                  AND item."resourceId" = ? AND item.exists AND item."contentType" = 'json'
                """, locked.step().get("evidenceBundleId", String.class), locked.run().get("id", String.class), locked.run().get("chapterId", String.class));
        if (evidence == null) throw invalid("章节写作缺少冻结正文 Evidence");
        Map<String, Object> context = readObject(evidence.get("contentJson", String.class));
        if (!ExecutionCanonicalJson.sha256(context).equals(evidence.get("contentSha256", String.class))) throw invalid("章节写作 Evidence 已损坏");
        return string(object(context.get("currentChapter"), "currentChapter"), "content");
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
        if (isRagRun(locked.run())) {
            String terminal = ragCompletion().finish(transaction, locked.run().get("id", String.class), "failed");
            if ("cancelled".equals(terminal)) {
                cancelInvalidatedRag(transaction, locked, previousSequence, now);
                return;
            }
            if (!"failed".equals(terminal)) throw invalid("RAG 物化端口返回非法失败状态");
        }
        if (isStyleRun(locked.run())) {
            if (!styleCompletion().targetExists(transaction, locked.run().get("id", String.class))) {
                cancelDeletedStyle(transaction, locked, previousSequence, now);
                return;
            }
            styleCompletion().finish(transaction, locked.run().get("id", String.class), "failed");
        }
        if (isQualityRun(locked.run())) {
            String terminal = qualityCompletion().finish(transaction, locked.run().get("id", String.class), "failed");
            if ("cancelled".equals(terminal)) {
                cancelInvalidatedQuality(transaction, locked, previousSequence, now);
                return;
            }
            if (!"failed".equals(terminal)) throw invalid("质量物化端口返回非法失败状态");
        }
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
        if (isQualityRun(locked.run())) {
            qualityCompletion().finish(transaction, locked.run().get("id", String.class), "cancelled");
        }
        if (isStyleRun(locked.run())) {
            styleCompletion().finish(transaction, locked.run().get("id", String.class), "cancelled");
        }
        if (isRagRun(locked.run())) {
            ragCompletion().finish(transaction, locked.run().get("id", String.class), "cancelled");
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
                SELECT id, "userId", "novelId", "chapterId", "writingSessionId", input, workflow, operation,
                       "sourceType", "sourceId", "targetType", "targetId", "currentEvidenceBundleId",
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
        ExecutionPlanSnapshot.Step frozenStep = frozenStep(locked);
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
        return executionContext(run).requireBusinessPlan();
    }

    private WorkflowExecutionContext executionContext(Record run) {
        return contexts.load(database.dsl(), new WorkflowExecutionContext.RunIdentity(
                run.get("id", String.class), run.get("workflow", String.class), run.get("operation", String.class),
                run.get("operationCatalogVersion", String.class), run.get("chapterId", String.class),
                run.get("targetType", String.class), run.get("targetId", String.class)),
                readObject(run.get("modelPolicyJson", String.class)));
    }

    private ExecutionPlanSnapshot.Step frozenStep(Locked locked) {
        return executionContext(locked.run()).requireStep(
                locked.step().get("purpose", String.class), locked.step().get("lane", String.class),
                locked.step().get("modelProfile", String.class), Integer.parseInt(locked.step().get("modelProfileVersion", String.class)),
                locked.step().get("outputSchema", String.class), Integer.parseInt(locked.step().get("outputSchemaVersion", String.class)),
                readObject(locked.step().get("budgetJson", String.class)));
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

    private Map<String, Object> stepRequestMaterial(
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
        result.put("operation", executionContext(run).effectiveOperation());
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
        result.put("artifact", artifact == null ? null : Map.of(
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
