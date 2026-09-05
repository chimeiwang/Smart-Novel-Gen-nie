package cn.inkforge.core.quality.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.RunQualityCheckResponse;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.quality.application.QualityRunDispatcher;
import cn.inkforge.core.quality.application.QualityRunStarter;
import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import cn.inkforge.core.quality.application.QualityExecutionReadiness;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 原质量 API 的 V1/V2 路由；网络握手在锁外，原引擎幂等重放在任何开关门禁之前。 */
final class JooqQualityRunStarter implements QualityRunStarter {
    private static final String OPERATION_KEY = "quality.consistency";
    private final CoreDatabase database;
    private final JooqQualityRepository legacy;
    private final Supplier<QualityRunDispatcher> dispatcher;
    private final Supplier<DurableWorkflowService> workflows;
    private final QualityExecutionReadiness readiness;
    private final ExecutionRegistry registry;
    private final CoreSettings settings;
    private final Clock clock;
    private final ObjectMapper json;
    private final CommandIdempotencyStore idempotency;

    JooqQualityRunStarter(CoreDatabase database, JooqQualityRepository legacy,
            Supplier<QualityRunDispatcher> dispatcher, Supplier<DurableWorkflowService> workflows,
            QualityExecutionReadiness readiness, ExecutionRegistry registry, CoreSettings settings,
            Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.legacy = Objects.requireNonNull(legacy);
        this.dispatcher = Objects.requireNonNull(dispatcher);
        this.workflows = Objects.requireNonNull(workflows);
        this.readiness = Objects.requireNonNull(readiness);
        this.registry = Objects.requireNonNull(registry);
        this.settings = Objects.requireNonNull(settings);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.idempotency = new CommandIdempotencyStore(json, settings.durableAgentExecutionSchemaReady());
    }

    @Override
    public RunQualityCheckResponse start(String userId, String checkId, RunQualityCheckRequest request) {
        Identity identity = identity(database.dsl(), userId, checkId);
        Map<String, Object> body = normalizedBody(request);
        String fingerprint = fingerprint(identity, checkId, body);
        var existing = idempotency.resolve(database.dsl(), userId, request.getClientRequestId(), fingerprint);
        if (existing != null) return database.transactionResult(tx -> {
            advisory(tx, userId, request.getClientRequestId());
            return replay(tx, userId, checkId, request, body, fingerprint);
        });
        boolean durable = settings.routesNewDurableAgentRun(userId, identity.novelId())
                && registry.enabledOperationKeys("quality", false).contains(OPERATION_KEY);
        if (!durable && !settings.v1FreshAgentStartsEnabled()) throw draining();
        boolean compatible = !durable || readiness.check();
        Started started = database.transactionResult(tx -> {
            advisory(tx, userId, request.getClientRequestId());
            var concurrent = idempotency.resolve(tx, userId, request.getClientRequestId(), fingerprint);
            if (concurrent != null) return new Started(replay(tx, userId, checkId, request, body, fingerprint), null);
            if (durable) {
                if (!compatible || workflows.get() == null) throw new ApiException(503,
                        "DURABLE_AGENT_EXECUTION_UNAVAILABLE", "耐久 Agent 执行服务暂时不可用");
                return new Started(startDurable(tx, userId, checkId, request, body, fingerprint), null);
            }
            if (dispatcher.get() == null) throw new ApiException(503,
                    "QUALITY_RUN_UNAVAILABLE", "质量检查运行服务暂时不可用");
            var creation = legacy.createRun(userId, checkId, request);
            return new Started(new RunQualityCheckResponse(true, checkId, creation.record().runId()),
                    creation.created() ? creation.record() : null);
        });
        // 不能在业务事务里触发 Agent 网络调用；临时失败仍由既有 V1 dispatcher 补投。
        if (started.legacyDispatch() != null) dispatcher.get().dispatch(started.legacyDispatch());
        return started.response();
    }

    private RunQualityCheckResponse startDurable(DSLContext tx, String userId, String checkId,
            RunQualityCheckRequest request, Map<String, Object> body, String fingerprint) {
        // INSERT Run 的 User FK 需要此锁；先取得它，避免在 Novel 锁内反等正在结算的 User。
        if (tx.fetchOne("SELECT id FROM public.\"User\" WHERE id = ? FOR KEY SHARE", userId) == null) {
            throw new ApiException(403, "QUALITY_CHECK_FORBIDDEN", "无权访问该检查项");
        }
        JooqQualityRepository.LockedScope scope = legacy.lockScope(tx, userId, checkId);
        if (scope.chapter().getStatus() != Chapterstatus.review) throw new ApiException(409,
                "QUALITY_CHECK_CHAPTER_NOT_IN_REVIEW", "只有待审章节可以运行一致性终检");
        if (scope.check().getType() != Qualitychecktype.consistency) throw new ApiException(400,
                "UNSUPPORTED_QUALITY_CHECK", "当前只支持一致性终检");
        String sourceTaskId = (String) body.get("taskId");
        String message = (String) body.get("message");
        legacy.validateTaskBinding(tx, sourceTaskId, userId, scope.novelId(), scope.chapter().getId());
        if (legacy.activeRun(tx, checkId) != null) throw new ApiException(409,
                "QUALITY_RUN_ACTIVE", "质量检查已有运行中的任务");
        ExecutionRegistry.ResolvedOperation operation = registry.resolve(OPERATION_KEY, false);
        if (!operation.operation().targetKinds().contains("chapter")
                || !operation.operation().scopeKinds().contains("chapter")) {
            throw new IllegalStateException("一致性终检 Catalog 目标范围不匹配");
        }
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("checkId", checkId); input.putAll(body);
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("checkId", checkId); context.put("novelId", scope.novelId());
        context.put("chapterId", scope.chapter().getId()); context.put("chapterContent", scope.chapter().getContent());
        context.put("chapterContentSha256", JooqQualityRepository.sha256(scope.chapter().getContent()));
        context.put("sourceUpdatedAt", JooqQualityRepository.sourceUpdatedAt(scope.chapter().getUpdatedat()));
        context.put("message", message); context.put("sourceTaskId", sourceTaskId);
        String instruction = message == null || message.isEmpty() ? "检查本章一致性" : message;
        WorkflowStartPlan plan = new WorkflowStartPlan(userId, request.getClientRequestId(), fingerprint,
                "quality", "consistency", registry.catalogVersion(), "quality_check", scope.novelId(),
                scope.chapter().getId(), null, "chapter", scope.chapter().getId(), input,
                operation.operation().evidencePolicy(), List.of(new WorkflowEvidenceItemPlan(
                        "quality_context", checkId, true, null, null, null, context, null, null,
                        Map.of("role", "quality_context"))), operation.operation().runBudget(),
                registry.freezePlan(OPERATION_KEY, false), new WorkflowInitialStepPlan("generation",
                        operation.operation().lane(), Map.of("userInstruction", instruction),
                        operation.generatorProfile(), operation.generatorStepBudget(), operation.outputSchema()),
                null, new WorkflowStartPlan.SourceBinding(JooqWorkflowQualityCompletion.SOURCE_TYPE, checkId));
        scope.check().setStatus(Qualitycheckstatus.running);
        scope.check().setUpdatedat(DatabaseTimestamp.next(clock, scope.check().getUpdatedat()));
        scope.check().update();
        String runId = workflows.get().startFresh(plan).runId();
        return new RunQualityCheckResponse(true, checkId, runId);
    }

    private RunQualityCheckResponse replay(DSLContext tx, String userId, String checkId,
            RunQualityCheckRequest request, Map<String, Object> body, String fingerprint) {
        var existing = idempotency.resolve(tx, userId, request.getClientRequestId(), fingerprint);
        if (existing == null || existing.recordKind() != CommandIdempotencyStore.RecordKind.WORKFLOW_RUN) {
            throw CommandIdempotencyStore.reused(request.getClientRequestId());
        }
        if (settings.durableAgentExecutionSchemaReady()) {
            Record run = tx.fetchOne("""
                    SELECT id, "userId", "sourceType", "sourceId", workflow, operation, input, "requestHash"
                    FROM public."WorkflowRun" WHERE id = ? AND "engineVersion" = 2
                    """, existing.recordId());
            if (run != null) {
                Map<String, Object> expected = new LinkedHashMap<>(); expected.put("checkId", checkId); expected.putAll(body);
                Map<String, Object> stored = json.readValue(run.get("input", String.class), new TypeReference<>() {});
                if (!userId.equals(run.get("userId", String.class))
                        || !JooqWorkflowQualityCompletion.SOURCE_TYPE.equals(run.get("sourceType", String.class))
                        || !checkId.equals(run.get("sourceId", String.class)) || !"quality".equals(run.get("workflow", String.class))
                        || !"consistency".equals(run.get("operation", String.class)) || !expected.equals(stored)
                        || !fingerprint.equals(run.get("requestHash", String.class))) {
                    throw CommandIdempotencyStore.reused(request.getClientRequestId());
                }
                return new RunQualityCheckResponse(true, checkId, existing.recordId());
            }
        }
        var legacyRun = legacy.createRun(userId, checkId, request);
        if (legacyRun.created()) throw new IllegalStateException("质量幂等重放不得创建新运行");
        return new RunQualityCheckResponse(true, checkId, legacyRun.record().runId());
    }

    private Identity identity(DSLContext tx, String userId, String checkId) {
        Record value = tx.select(CHAPTER.NOVELID, CHAPTER.ID, NOVEL.USERID).from(CHAPTERQUALITYCHECK)
                .join(CHAPTER).on(CHAPTER.ID.eq(CHAPTERQUALITYCHECK.CHAPTERID))
                .join(NOVEL).on(NOVEL.ID.eq(CHAPTER.NOVELID)).where(CHAPTERQUALITYCHECK.ID.eq(checkId)).fetchOne();
        if (value == null) throw new ApiException(404, "QUALITY_CHECK_NOT_FOUND", "检查项不存在");
        if (!userId.equals(value.get(NOVEL.USERID))) throw new ApiException(403,
                "QUALITY_CHECK_FORBIDDEN", "无权访问该检查项");
        return new Identity(value.get(CHAPTER.NOVELID), value.get(CHAPTER.ID));
    }

    private String fingerprint(Identity identity, String checkId, Map<String, Object> body) {
        return CommandIdempotency.requestFingerprint("quality_run", Map.of("novelId", identity.novelId(),
                "chapterId", identity.chapterId(), "checkItemId", checkId), body, json);
    }

    private static Map<String, Object> normalizedBody(RunQualityCheckRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("taskId", nullable(request.getTaskId())); body.put("message", nullable(request.getMessage()));
        return body;
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static void advisory(DSLContext tx, String userId, String clientRequestId) {
        tx.execute("SELECT pg_catalog.pg_advisory_xact_lock(?)", CommandIdempotency.advisoryLockKey(userId, clientRequestId));
    }

    private static ApiException draining() {
        return new ApiException(503, "AGENT_FRESH_STARTS_DRAINING", "Agent 新建入口正在受控 drain，请稍后重试");
    }

    private record Identity(String novelId, String chapterId) {}
    private record Started(RunQualityCheckResponse response, QualityDispatchRecord legacyDispatch) {}
}
