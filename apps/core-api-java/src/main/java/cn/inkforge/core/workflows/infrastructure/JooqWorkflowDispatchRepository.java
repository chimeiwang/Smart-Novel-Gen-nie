package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.agent.EvidenceBundle;
import cn.inkforge.contracts.agent.EvidenceItem;
import cn.inkforge.contracts.agent.EvidenceManifest;
import cn.inkforge.contracts.agent.EvidenceManifestItem;
import cn.inkforge.contracts.agent.EvidenceRange;
import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.contracts.agent.ModelProfileRef;
import cn.inkforge.contracts.agent.OutputSchemaRef;
import cn.inkforge.contracts.agent.PromptProfileRef;
import cn.inkforge.contracts.agent.ResolvedModelRef;
import cn.inkforge.contracts.agent.StepBudget;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowDispatchRepository;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.domain.WorkflowModelProfile;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.domain.WorkflowStepLeasePolicy;
import cn.inkforge.core.workflows.domain.WorkflowStepState;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** PostgreSQL 权威 V2 Step 领取与 request 重建。 */
final class JooqWorkflowDispatchRepository implements WorkflowDispatchRepository {

    private static final TypeReference<Map<String, Object>> JSON_OBJECT = new TypeReference<>() {};
    private static final Duration LANE_AGING = Duration.ofSeconds(5);
    private static final long CAPACITY_LOCK_KEY = CommandIdempotency.advisoryLockKey(
            "workflow-dispatch-capacity", "global");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final Duration leaseDuration;
    private final int maxActiveLeases;
    private final int maxCreativeLeases;
    private final int maxBatchMediaLeases;
    private final int maxReviewLeases;
    private final JooqWorkflowCallbackRepository rejectionConvergence;

    JooqWorkflowDispatchRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            ExecutionRegistry registry,
            Duration leaseDuration,
            int maxActiveLeases) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        Objects.requireNonNull(registry);
        if (leaseDuration == null || leaseDuration.isZero() || leaseDuration.isNegative()) {
            throw new IllegalArgumentException("Workflow Step lease 必须为正数");
        }
        this.leaseDuration = leaseDuration;
        if (maxActiveLeases < 1 || maxActiveLeases > 3) {
            throw new IllegalArgumentException("Workflow active lease 上限必须在 1 到 3 之间");
        }
        this.maxActiveLeases = maxActiveLeases;
        // 容量大于一时，为 interactive 保留下一释放槽；没有竞争 waiter 时允许借满。
        this.maxCreativeLeases = Math.max(0, maxActiveLeases - 1);
        this.maxBatchMediaLeases = maxActiveLeases == 1 ? 0 : 1;
        this.maxReviewLeases = Math.min(2, maxActiveLeases);
        this.rejectionConvergence = new JooqWorkflowCallbackRepository(
                database, ids, clock, json, registry, leaseDuration);
    }

    @Override
    public Optional<ExecutionStepRequest> claimNext() {
        return database.transactionResult(this::claimNext);
    }

    @Override
    public void recordAccepted(ExecutionStepRequest request, ExecutionStepAccepted accepted) {
        Objects.requireNonNull(request);
        Objects.requireNonNull(accepted);
        database.transactionResult(transaction -> {
            Record run = transaction.fetchOne(
                    """
                    SELECT id FROM public."WorkflowRun"
                    WHERE id = ? AND "engineVersion" = 2
                    FOR UPDATE
                    """,
                    request.getRunId());
            if (run == null) return null;
            Record step = transaction.fetchOne(
                    """
                    SELECT status::text AS status, "activeJobId", "fencingToken", "requestHash",
                           "modelProfile", "modelProfileVersion", "resolvedModelJson"
                    FROM public."WorkflowStep"
                    WHERE id = ? AND "runId" = ?
                    FOR UPDATE
                    """,
                    request.getStepId(),
                    request.getRunId());
            if (step == null
                    || step.get("fencingToken", Long.class) != request.getFencingToken().longValue()
                    || !Objects.equals(step.get("requestHash", String.class), request.getRequestHash())) {
                return null;
            }
            boolean activeJob = Objects.equals(
                    step.get("activeJobId", String.class), request.getJobId());
            boolean terminal = List.of("completed", "failed", "skipped")
                    .contains(step.get("status", String.class));
            if (!activeJob && !terminal) return null;
            requireAcceptedBinding(request, accepted);
            ResolvedModelRef resolved = accepted.getResolvedModel();
            WorkflowResolvedModel verified = new WorkflowResolvedModel(
                            resolved.getDeploymentProfileKey(),
                            resolved.getDeploymentFingerprint(),
                            resolved.getProvider(),
                            resolved.getModel(),
                            resolved.getTransportProfile(),
                            resolved.getEndpointProfile(),
                            resolved.getStructuredOutputRoute().getValue(),
                            resolved.getCapabilityVersion(),
                            resolved.getReasoningMode().getValue(),
                            resolved.getSupportsRequestIdempotency())
                    .requireAuthorizedBy(new WorkflowModelProfile(
                            step.get("modelProfile", String.class),
                            Integer.parseInt(step.get("modelProfileVersion", String.class)),
                            request.getModelProfile().getReasoningMode().getValue(),
                            request.getModelProfile().getDeploymentProfileKey()));
            Map<String, Object> serialized = resolvedModel(verified);
            String existing = step.get("resolvedModelJson", String.class);
            if (existing != null && !readObject(existing).equals(serialized)) {
                throw new IllegalStateException("同一 Workflow Step 的解析模型发生漂移");
            }
            // terminal callback 已先行冻结时，迟到的 202 Accepted 只做同值幂等校验。
            if (terminal) return null;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            if (existing == null) {
                transaction.execute(
                        """
                        UPDATE public."WorkflowStep"
                        SET "resolvedModelJson" = ?, "updatedAt" = ?
                        WHERE id = ? AND "runId" = ?
                        """,
                        json.writeValueAsString(serialized),
                        now,
                        request.getStepId(),
                        request.getRunId());
            }
            // Accepted 只冻结 Agent 的部署解析，不占用 queued Step 的积分。唯一 Provider 授权门位于
            // preparing callback；它会在同一事务完成模型授权、Run 预算和用户预留。
            return null;
        });
    }

    @Override
    public void recordRejected(ExecutionStepRequest request, String errorCode) {
        Objects.requireNonNull(request);
        if (errorCode == null || !errorCode.matches("[A-Z][A-Z0-9_]{0,127}")) {
            throw new IllegalArgumentException("Workflow 确定性拒绝错误码无效");
        }
        rejectionConvergence.rejectSubmission(request, errorCode);
    }

    @Override
    public void recordAdmissionSaturated(
            ExecutionStepRequest request, Duration retryAfter) {
        Objects.requireNonNull(request);
        if (retryAfter == null
                || retryAfter.isZero()
                || retryAfter.isNegative()
                || retryAfter.compareTo(Duration.ofSeconds(60)) > 0) {
            throw new IllegalArgumentException("Workflow admission 重试时间无效");
        }
        database.transactionResult(transaction -> {
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.execute(
                    """
                    UPDATE public."WorkflowStep"
                    SET "activeJobId" = NULL, "leaseExpiresAt" = NULL,
                        "heartbeatAt" = NULL, "nextAttemptAt" = ?, "updatedAt" = ?
                    WHERE id = ? AND "runId" = ?
                      AND status = CAST('pending' AS "WorkflowStepStatus")
                      AND "activeJobId" = ? AND "fencingToken" = ? AND "requestHash" = ?
                    """,
                    now.plus(retryAfter),
                    now,
                    request.getStepId(),
                    request.getRunId(),
                    request.getJobId(),
                    request.getFencingToken().longValue(),
                    request.getRequestHash());
            return null;
        });
    }

    private Optional<ExecutionStepRequest> claimNext(DSLContext transaction) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        // 领取者必须在同一 PostgreSQL 临界区内计数并建立 lease；否则两个 Core
        // dispatcher 都可能看到两个空槽，各自再领取三个 Step。
        transaction.execute(
                "SELECT pg_catalog.pg_advisory_xact_lock(?)", CAPACITY_LOCK_KEY);
        ActiveLeases active = activeLeases(transaction, now);
        if (active.total() >= maxActiveLeases) return Optional.empty();
        DueLanes due = dueLanes(transaction, now);
        String preferredLane = due.interactive()
                        && (active.creative() >= maxCreativeLeases
                                || active.batchMedia() > maxBatchMediaLeases)
                ? "interactive"
                : due.creative() && active.review() >= maxReviewLeases
                        ? "creative"
                        : "";
        LocalDateTime agedBefore = now.minus(LANE_AGING);
        Record candidate = transaction.fetchOne(
                """
                SELECT step.id, step."runId", run."novelId"
                FROM public."WorkflowStep" AS step
                JOIN public."WorkflowRun" AS run ON run.id = step."runId"
                WHERE run."engineVersion" = 2
                  AND run.status IN ('pending', 'running')
                  AND run."cancelRequestedAt" IS NULL
                  AND step.status IN ('pending', 'running')
                  AND step."nextAttemptAt" <= ?
                  AND (step."leaseExpiresAt" IS NULL OR step."leaseExpiresAt" <= ?)
                  AND step.lane IN ('interactive', 'creative', 'batch_media')
                  AND NOT (step.lane = 'creative' AND ? AND ? >= ?)
                  AND NOT (step.lane = 'batch_media' AND ? AND ? >= ?)
                  AND NOT (step.purpose = 'review' AND ? >= ?)
                  AND NOT EXISTS (
                    SELECT 1
                    FROM public."WorkflowRun" AS other_run
                    JOIN public."WorkflowStep" AS other_step
                      ON other_step."runId" = other_run.id
                    WHERE other_run."engineVersion" = 2
                      AND other_run."novelId" = run."novelId"
                      AND other_run.id <> run.id
                      AND other_run.status IN ('pending', 'running')
                      AND other_run."cancelRequestedAt" IS NULL
                      AND other_step.status IN ('pending', 'running')
                      AND (
                        other_step.status = 'running'
                        OR other_step."activeJobId" IS NOT NULL
                      )
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM public."WritingRunCommand" AS legacy_command
                    JOIN public."WritingTask" AS legacy_task
                      ON legacy_task.id = legacy_command."taskId"
                    WHERE legacy_task."novelId" = run."novelId"
                      AND legacy_command.status IN ('pending', 'submitted', 'processing')
                  )
                ORDER BY
                  CASE WHEN ? = '' THEN 0 WHEN step.lane = ? THEN 0 ELSE 1 END,
                  CASE WHEN step."submittedAt" <= ? THEN 0 ELSE 1 END,
                  CASE WHEN step."submittedAt" <= ? THEN step."submittedAt" END,
                  CASE step.lane
                    WHEN 'interactive' THEN 0
                    WHEN 'creative' THEN 1
                    WHEN 'batch_media' THEN 2
                    ELSE 3
                  END,
                  step."nextAttemptAt", step."runId", step.ordinal
                LIMIT 1
                """,
                now,
                now,
                due.interactive(),
                active.creative(),
                maxCreativeLeases,
                due.interactive() || due.creative(),
                active.batchMedia(),
                maxBatchMediaLeases,
                active.review(),
                maxReviewLeases,
                preferredLane,
                preferredLane,
                agedBefore,
                agedBefore);
        if (candidate == null) return Optional.empty();

        String runId = candidate.get("runId", String.class);
        String novelId = candidate.get("novelId", String.class);
        if (novelId != null) {
            transaction.execute(
                    "SELECT pg_catalog.pg_advisory_xact_lock(?)",
                    CommandIdempotency.advisoryLockKey("agent-novel-dispatch", novelId));
            if (hasCompetingNovelExecution(transaction, runId, novelId)) {
                return Optional.empty();
            }
        }
        Record run = transaction.fetchOne(
                """
                SELECT id, "novelId", workflow, operation, "operationCatalogVersion",
                       "modelPolicyJson", status::text AS status, "cancelRequestedAt",
                       "lastEventSequence", revision
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2
                FOR UPDATE
                """,
                runId);
        if (run == null || run.get("cancelRequestedAt", LocalDateTime.class) != null) {
            return Optional.empty();
        }
        Record step = transaction.fetchOne(
                """
                SELECT id, "runId", status::text AS status, input, ordinal, purpose, lane,
                       "attemptCount", "nextAttemptAt", "fencingToken", "leaseExpiresAt",
                       "idempotencyKey", "requestHash", "inputHash", "evidenceBundleId",
                       "artifactId", "artifactRevision", "modelProfile", "modelProfileVersion",
                       "outputSchema", "outputSchemaVersion", "budgetJson", "submittedAt"
                FROM public."WorkflowStep"
                WHERE id = ? AND "runId" = ?
                FOR UPDATE
                """,
                candidate.get("id", String.class),
                runId);
        if (step == null) return Optional.empty();
        WorkflowStepState state = WorkflowStepState.fromDatabaseValue(
                step.get("status", String.class));
        if (!WorkflowStepLeasePolicy.canClaim(
                state,
                step.get("leaseExpiresAt", LocalDateTime.class),
                now,
                false)) {
            return Optional.empty();
        }
        LocalDateTime nextAttemptAt = step.get("nextAttemptAt", LocalDateTime.class);
        if (nextAttemptAt == null || nextAttemptAt.isAfter(now)) return Optional.empty();

        int previousAttempts = step.get("attemptCount", Integer.class);
        int attemptCount = Math.addExact(previousAttempts, 1);
        long fencingToken = WorkflowStepLeasePolicy.nextFencingToken(
                step.get("fencingToken", Long.class));
        String jobId = ids.next();
        LocalDateTime leaseExpiresAt = now.plus(leaseDuration);
        String dispatchMode;
        String reason;
        if (state == WorkflowStepState.RUNNING) {
            dispatchMode = "running_recovery";
            reason = "lease_recovery";
        } else if (previousAttempts == 0) {
            dispatchMode = "initial";
            reason = "initial_dispatch";
        } else {
            dispatchMode = "pending_recovery";
            reason = "pending_recovery";
        }
        transaction.execute(
                """
                UPDATE public."WorkflowStep"
                SET "attemptCount" = ?, "fencingToken" = ?, "activeJobId" = ?,
                    "leaseExpiresAt" = ?, "heartbeatAt" = NULL,
                    "lastProgressSequence" = NULL, "updatedAt" = ?
                WHERE id = ? AND "runId" = ?
                """,
                attemptCount,
                fencingToken,
                jobId,
                leaseExpiresAt,
                now,
                step.get("id", String.class),
                runId);
        ExecutionStepRequest claimed = request(
                transaction, run, step, jobId, fencingToken, dispatchMode);
        long sequence = Math.addExact(run.get("lastEventSequence", Long.class), 1L);
        Map<String, Object> payload = Map.of(
                "stepId", step.get("id", String.class),
                "ordinal", step.get("ordinal", Integer.class),
                "purpose", step.get("purpose", String.class),
                "lane", step.get("lane", String.class),
                "modelProfile", WorkflowCallbackValues.modelProfileMap(
                        claimed.getModelProfile()),
                "attemptCount", attemptCount,
                "fencingToken", fencingToken,
                "reason", reason);
        transaction.execute(
                """
                INSERT INTO public."WorkflowEvent" (
                  id, "runId", sequence, "eventType", "payloadJson", "dedupeKey", "createdAt"
                ) VALUES (?, ?, ?, 'step_queued', ?, ?, ?)
                """,
                ids.next(),
                runId,
                sequence,
                json.writeValueAsString(payload),
                "step:queued:" + step.get("id", String.class) + ":" + fencingToken,
                now);
        transaction.execute(
                """
                UPDATE public."WorkflowRun"
                SET "lastEventSequence" = ?, revision = revision + 1, "updatedAt" = ?
                WHERE id = ?
                """,
                sequence,
                now,
                runId);
        return Optional.of(claimed);
    }

    private static ActiveLeases activeLeases(DSLContext transaction, LocalDateTime now) {
        Record value = transaction.fetchOne(
                """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE step.lane = 'creative') AS creative,
                       count(*) FILTER (WHERE step.lane = 'batch_media') AS batch_media,
                       count(*) FILTER (WHERE step.purpose = 'review') AS review
                FROM public."WorkflowStep" AS step
                JOIN public."WorkflowRun" AS run ON run.id = step."runId"
                WHERE run."engineVersion" = 2
                  AND step.status IN ('pending', 'running')
                  AND step."activeJobId" IS NOT NULL
                  AND step."leaseExpiresAt" > ?
                """,
                now);
        if (value == null) return new ActiveLeases(0, 0, 0, 0);
        return new ActiveLeases(
                Math.toIntExact(value.get("total", Long.class)),
                Math.toIntExact(value.get("creative", Long.class)),
                Math.toIntExact(value.get("batch_media", Long.class)),
                Math.toIntExact(value.get("review", Long.class)));
    }

    private static DueLanes dueLanes(DSLContext transaction, LocalDateTime now) {
        Record value = transaction.fetchOne(
                """
                SELECT COALESCE(bool_or(step.lane = 'interactive'), FALSE) AS interactive,
                       COALESCE(bool_or(step.lane = 'creative'), FALSE) AS creative
                FROM public."WorkflowStep" AS step
                JOIN public."WorkflowRun" AS run ON run.id = step."runId"
                WHERE run."engineVersion" = 2
                  AND run.status IN ('pending', 'running')
                  AND run."cancelRequestedAt" IS NULL
                  AND step.status IN ('pending', 'running')
                  AND step."nextAttemptAt" <= ?
                  AND (step."leaseExpiresAt" IS NULL OR step."leaseExpiresAt" <= ?)
                  AND step.lane IN ('interactive', 'creative', 'batch_media')
                  AND NOT EXISTS (
                    SELECT 1
                    FROM public."WorkflowRun" AS other_run
                    JOIN public."WorkflowStep" AS other_step
                      ON other_step."runId" = other_run.id
                    WHERE other_run."engineVersion" = 2
                      AND other_run."novelId" = run."novelId"
                      AND other_run.id <> run.id
                      AND other_run.status IN ('pending', 'running')
                      AND other_run."cancelRequestedAt" IS NULL
                      AND other_step.status IN ('pending', 'running')
                      AND (
                        other_step.status = 'running'
                        OR other_step."activeJobId" IS NOT NULL
                      )
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM public."WritingRunCommand" AS legacy_command
                    JOIN public."WritingTask" AS legacy_task
                      ON legacy_task.id = legacy_command."taskId"
                    WHERE legacy_task."novelId" = run."novelId"
                      AND legacy_command.status IN ('pending', 'submitted', 'processing')
                  )
                """,
                now,
                now);
        return value == null
                ? new DueLanes(false, false)
                : new DueLanes(
                        Boolean.TRUE.equals(value.get("interactive", Boolean.class)),
                        Boolean.TRUE.equals(value.get("creative", Boolean.class)));
    }

    private static boolean hasCompetingNovelExecution(
            DSLContext transaction, String runId, String novelId) {
        return Boolean.TRUE.equals(transaction.fetchOne(
                        """
                        SELECT (
                          EXISTS (
                            SELECT 1
                            FROM public."WorkflowRun" AS other_run
                            JOIN public."WorkflowStep" AS other_step
                              ON other_step."runId" = other_run.id
                            WHERE other_run."engineVersion" = 2
                              AND other_run."novelId" = ? AND other_run.id <> ?
                              AND other_run.status IN ('pending', 'running')
                              AND other_run."cancelRequestedAt" IS NULL
                              AND other_step.status IN ('pending', 'running')
                              AND (
                                other_step.status = 'running'
                                OR other_step."activeJobId" IS NOT NULL
                              )
                          )
                          OR EXISTS (
                            SELECT 1
                            FROM public."WritingRunCommand" AS legacy_command
                            JOIN public."WritingTask" AS legacy_task
                              ON legacy_task.id = legacy_command."taskId"
                            WHERE legacy_task."novelId" = ?
                              AND legacy_command.status IN ('pending', 'submitted', 'processing')
                          )
                        ) AS blocked
                        """,
                        novelId,
                        runId,
                        novelId)
                .get("blocked", Boolean.class));
    }

    private record ActiveLeases(int total, int creative, int batchMedia, int review) {}

    private record DueLanes(boolean interactive, boolean creative) {}

    private ExecutionStepRequest request(
            DSLContext transaction,
            Record run,
            Record step,
            String jobId,
            long fencingToken,
            String dispatchMode) {
        Map<String, Object> storedBudget = readObject(step.get("budgetJson", String.class));
        ExecutionPlanSnapshot executionPlan = executionPlan(run);
        ExecutionPlanSnapshot.Step frozenStep = executionPlan.requireStep(
                step.get("purpose", String.class),
                step.get("lane", String.class),
                step.get("modelProfile", String.class),
                Integer.parseInt(step.get("modelProfileVersion", String.class)),
                step.get("outputSchema", String.class),
                Integer.parseInt(step.get("outputSchemaVersion", String.class)),
                storedBudget);
        Map<String, Object> budget = frozenStep.stepBudget().budgetMap();
        Map<String, Object> input = readObject(step.get("input", String.class));
        EvidenceBundle evidence = evidenceBundle(
                transaction, step.get("evidenceBundleId", String.class));
        // policyVersion 是本 Step 对同一不可变 bundle 的授权视图；Reviewer
        // 不复制 items/manifest，但必须使用 Catalog 冻结的 review policy。
        evidence.policyVersion(frozenStep.evidencePolicy());
        ExecutionPlanSnapshot.ModelProfile profile = frozenStep.modelProfile();
        ExecutionPlanSnapshot.PromptProfile prompt = profile.promptProfile();
        PromptProfileRef promptProfile = new PromptProfileRef()
                .name(prompt.name())
                .version(prompt.version())
                .sha256(prompt.sha256());
        ModelProfileRef modelProfile = new ModelProfileRef()
                .deploymentProfileKey(profile.deploymentProfileKey())
                .profile(step.get("modelProfile", String.class))
                .promptProfile(promptProfile)
                .reasoningMode(ModelProfileRef.ReasoningModeEnum.fromValue(
                        profile.reasoningMode()))
                .version(Integer.parseInt(step.get("modelProfileVersion", String.class)));
        ExecutionPlanSnapshot.OutputSchema output = frozenStep.outputSchema();
        OutputSchemaRef outputSchema = new OutputSchemaRef(
                output.jsonSchema(),
                step.get("outputSchema", String.class),
                output.sha256(),
                Integer.parseInt(step.get("outputSchemaVersion", String.class)));
        StepBudget stepBudget = new StepBudget(
                integer(budget, "maxCompletionTokens"),
                integer(budget, "maxCostMicros"),
                integer(budget, "maxInputTokens"),
                integer(budget, "maxModelCalls"),
                integer(budget, "maxPromptCacheMissTokens"),
                integer(budget, "maxProtocolCorrections"),
                integer(budget, "maxProviderRetries"),
                integer(budget, "maxReasoningTokens"),
                integer(budget, "maxVisibleOutputTokens"),
                integer(budget, "maxWallClockSeconds"));
        ExecutionStepRequest request = new ExecutionStepRequest(
                stepBudget,
                ExecutionStepRequest.DispatchModeEnum.fromValue(dispatchMode),
                evidence,
                Math.toIntExact(fencingToken),
                step.get("idempotencyKey", String.class),
                input,
                step.get("inputHash", String.class),
                jobId,
                ExecutionStepRequest.LaneEnum.fromValue(step.get("lane", String.class)),
                modelProfile,
                run.get("novelId", String.class),
                run.get("operation", String.class),
                outputSchema,
                "2.0",
                step.get("purpose", String.class),
                step.get("requestHash", String.class),
                run.get("id", String.class),
                step.get("id", String.class),
                DatabaseTimestamp.api(step.get("submittedAt", LocalDateTime.class)),
                run.get("workflow", String.class));
        String artifactId = step.get("artifactId", String.class);
        if (artifactId != null) {
            request.artifactId(artifactId)
                    .artifactRevision(step.get("artifactRevision", Integer.class));
        }
        return request;
    }

    private EvidenceBundle evidenceBundle(DSLContext transaction, String bundleId) {
        Record bundle = transaction.fetchOne(
                """
                SELECT id, "runId", version, "policyVersion", "manifestJson",
                       "manifestSha256", "totalBytes"
                FROM public."WorkflowEvidenceBundle" WHERE id = ?
                """,
                bundleId);
        if (bundle == null) throw new IllegalStateException("Workflow Step 的 Evidence 不存在");
        List<EvidenceItem> items = new ArrayList<>();
        for (Record item : transaction.fetch(
                """
                SELECT id, "bundleId", ordinal, "resourceType", "resourceId", exists,
                       "resourceRevision", "resourceUpdatedAt", "contentType", "contentText",
                       "contentJson", "contentSha256", "byteCount", "rangeJson", "metadataJson"
                FROM public."WorkflowEvidenceItem"
                WHERE "bundleId" = ? ORDER BY ordinal
                """,
                bundleId)) {
            EvidenceItem value = new EvidenceItem(
                    bundleId,
                    Math.toIntExact(item.get("byteCount", Long.class)),
                    item.get("exists", Boolean.class),
                    item.get("id", String.class),
                    item.get("ordinal", Integer.class),
                    item.get("resourceId", String.class),
                    item.get("resourceType", String.class));
            value.resourceRevision(item.get("resourceRevision", Integer.class));
            LocalDateTime updatedAt = item.get("resourceUpdatedAt", LocalDateTime.class);
            if (updatedAt != null) value.resourceUpdatedAt(DatabaseTimestamp.api(updatedAt));
            String contentType = item.get("contentType", String.class);
            if (contentType != null) {
                value.contentType(EvidenceItem.ContentTypeEnum.fromValue(contentType));
            }
            value.contentText(item.get("contentText", String.class));
            String contentJson = item.get("contentJson", String.class);
            if (contentJson != null) value.contentJson(readValue(contentJson));
            value.contentSha256(item.get("contentSha256", String.class));
            String rangeJson = item.get("rangeJson", String.class);
            if (rangeJson != null) {
                Map<String, Object> range = readObject(rangeJson);
                value.range(new EvidenceRange(
                        integer(range, "endCodePoint"), integer(range, "startCodePoint")));
            }
            value.metadata(readObject(item.get("metadataJson", String.class)));
            items.add(value);
        }
        Map<String, Object> manifestValue = readObject(bundle.get("manifestJson", String.class));
        List<EvidenceManifestItem> manifestItems = new ArrayList<>();
        for (Object raw : list(manifestValue.get("items"), "Evidence manifest items")) {
            Map<String, Object> item = object(raw, "Evidence manifest item");
            EvidenceManifestItem value = new EvidenceManifestItem(
                    integer(item, "byteCount"),
                    bool(item, "exists"),
                    string(item, "itemId"),
                    integer(item, "ordinal"),
                    string(item, "resourceId"),
                    string(item, "resourceType"));
            if (item.containsKey("resourceRevision")) {
                value.resourceRevision(integer(item, "resourceRevision"));
            }
            if (item.containsKey("resourceUpdatedAt")) {
                value.resourceUpdatedAt(java.time.OffsetDateTime.parse(
                        string(item, "resourceUpdatedAt")));
            }
            if (item.containsKey("contentType")) {
                value.contentType(EvidenceManifestItem.ContentTypeEnum.fromValue(
                        string(item, "contentType")));
            }
            if (item.containsKey("contentSha256")) {
                value.contentSha256(string(item, "contentSha256"));
            }
            if (item.containsKey("range")) {
                Map<String, Object> range = object(item.get("range"), "Evidence range");
                value.range(new EvidenceRange(
                        integer(range, "endCodePoint"), integer(range, "startCodePoint")));
            }
            value.metadata(object(item.get("metadata"), "Evidence metadata"));
            manifestItems.add(value);
        }
        EvidenceManifest manifest = new EvidenceManifest(
                bundleId,
                bundle.get("version", Integer.class),
                integer(manifestValue, "itemCount"),
                manifestItems);
        return new EvidenceBundle(
                bundleId,
                items,
                manifest,
                bundle.get("manifestSha256", String.class),
                bundle.get("policyVersion", String.class),
                bundle.get("runId", String.class),
                Math.toIntExact(bundle.get("totalBytes", Long.class)),
                bundle.get("version", Integer.class));
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

    private static void requireAcceptedBinding(
            ExecutionStepRequest request, ExecutionStepAccepted accepted) {
        if (!"2.0".equals(accepted.getProtocolVersion())
                || !Objects.equals(request.getJobId(), accepted.getJobId())
                || !Objects.equals(request.getRunId(), accepted.getRunId())
                || !Objects.equals(request.getNovelId(), accepted.getNovelId())
                || !Objects.equals(request.getStepId(), accepted.getStepId())
                || !Objects.equals(request.getFencingToken(), accepted.getFencingToken())
                || !Objects.equals(request.getRequestHash(), accepted.getRequestHash())) {
            throw new IllegalArgumentException("Agent execution accepted 响应资源绑定不一致");
        }
    }

    private static Map<String, Object> resolvedModel(WorkflowResolvedModel value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("deploymentProfileKey", value.deploymentProfileKey());
        result.put("deploymentFingerprint", value.deploymentFingerprint());
        result.put("provider", value.provider());
        result.put("model", value.model());
        result.put("transportProfile", value.transportProfile());
        result.put("endpointProfile", value.endpointProfile());
        result.put("structuredOutputRoute", value.structuredOutputRoute());
        result.put("capabilityVersion", value.capabilityVersion());
        result.put("reasoningMode", value.reasoningMode());
        result.put("supportsRequestIdempotency", value.supportsRequestIdempotency());
        return Collections.unmodifiableMap(result);
    }

    private Map<String, Object> readObject(String value) {
        return json.readValue(value, JSON_OBJECT);
    }

    private Object readValue(String value) {
        return json.convertValue(json.readTree(value), Object.class);
    }

    private static Map<String, Object> object(Object value, String label) {
        if (!(value instanceof Map<?, ?> raw)) throw new IllegalStateException(label + " 必须是对象");
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalStateException(label + " key 必须是字符串");
            }
            result.put(key, entry.getValue());
        }
        return Collections.unmodifiableMap(result);
    }

    private static List<?> list(Object value, String label) {
        if (!(value instanceof List<?> result)) throw new IllegalStateException(label + " 必须是数组");
        return result;
    }

    private static String string(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof String result)) {
            throw new IllegalStateException(key + " 必须是字符串");
        }
        return result;
    }

    private static int integer(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Number result)) {
            throw new IllegalStateException(key + " 必须是整数");
        }
        return Math.toIntExact(result.longValue());
    }

    private static boolean bool(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Boolean result)) {
            throw new IllegalStateException(key + " 必须是布尔值");
        }
        return result;
    }
}
