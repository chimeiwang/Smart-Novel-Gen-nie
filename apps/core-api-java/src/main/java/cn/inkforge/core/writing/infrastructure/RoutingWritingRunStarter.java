package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.ShortMediumStartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunStartResponse;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.writing.application.WritingCommandRepository;
import cn.inkforge.core.writing.application.WritingRunStarter;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.WorkflowExecutionContext;
import cn.inkforge.core.workflows.application.WorkflowExecutionContextReader;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 新任务固定使用 V1；保留历史请求重放与跨旧任务互斥，禁止转换既有引擎身份。 */
final class RoutingWritingRunStarter implements WritingRunStarter {

    private static final Set<String> PROVABLY_READ_ONLY_LEGACY_OPERATIONS =
            Set.of("answer_question", "review_chapter");

    private final CoreDatabase database;
    private final WritingCommandRepository legacy;
    private final CommandIdempotencyStore idempotency;
    private final CoreSettings settings;
    private final ObjectMapper json;
    private final WorkflowExecutionContextReader executionContexts;
    private final cn.inkforge.core.writing.application.WritingRunQueryRepository queries;

    RoutingWritingRunStarter(CoreDatabase database, WritingCommandRepository legacy,
            CommandIdempotencyStore idempotency, CoreSettings settings, ObjectMapper json,
            WorkflowExecutionContextReader contexts,
            cn.inkforge.core.writing.application.WritingRunQueryRepository queries) {
        this.database = Objects.requireNonNull(database);
        this.legacy = Objects.requireNonNull(legacy);
        this.idempotency = Objects.requireNonNull(idempotency);
        this.settings = Objects.requireNonNull(settings);
        this.json = Objects.requireNonNull(json);
        this.executionContexts = contexts;
        this.queries = Objects.requireNonNull(queries);
    }

    @Override
    public WritingRunStartResponse start(String userId, ParsedWritingRunStartRequest request) {
        String key = clientRequestId(request);
        var existing = database.transactionResult(tx -> idempotency.resolve(tx, userId, key, null));
        if (existing != null) return replay(userId, request, key, existing);
        if (request instanceof ParsedWritingRunStartRequest.Natural) throw retired();
        if (!settings.v1FreshAgentStartsEnabled()) throw V1FreshAgentStartGate.draining();
        return database.transactionResult(tx -> {
            tx.execute("SELECT pg_catalog.pg_advisory_xact_lock(?)", CommandIdempotency.advisoryLockKey(userId, key));
            var concurrent = idempotency.resolve(tx, userId, key, null);
            if (concurrent != null) return replay(userId, request, key, concurrent);
            StartScope requested = startScope(request);
            StartScope scope = requested == null ? null : lockStartScope(tx, userId, requested);
            if (scope != null) {
                if (scope.writingSessionId() != null) requireNoActiveForegroundRun(tx, scope.writingSessionId());
                if (isLegacyMutation(request) || isShortMedium(request)) requireNoActiveDurableMutation(tx, scope);
            }
            return legacy.start(userId, request);
        });
    }

    /** 历史请求只返回原运行，不重新派发；仍核对完整请求指纹，防止复用键转换引擎。 */
    private WritingRunStartResponse replay(String userId, ParsedWritingRunStartRequest request,
            String key, CommandIdempotencyStore.Resolution existing) {
        if (existing.recordKind() == CommandIdempotencyStore.RecordKind.WRITING_COMMAND) {
            if (request instanceof ParsedWritingRunStartRequest.Natural) throw CommandIdempotencyStore.reused(key);
            return legacy.start(userId, request);
        }
        if (existing.recordKind() != CommandIdempotencyStore.RecordKind.WORKFLOW_RUN) throw CommandIdempotencyStore.reused(key);
        var matched = database.transactionResult(tx -> idempotency.resolve(tx, userId, key, historicalFingerprint(request)));
        if (matched == null || !existing.recordId().equals(matched.recordId())) throw CommandIdempotencyStore.reused(key);
        Object response = queries.getPublic(userId, existing.recordId());
        if (!(response instanceof cn.inkforge.contracts.api.WritingRunV2Response historical)) throw CommandIdempotencyStore.reused(key);
        return historical;
    }

    private String historicalFingerprint(ParsedWritingRunStartRequest request) {
        if (request instanceof ParsedWritingRunStartRequest.LongSerial value) return new LongSerialRunAssembler(json, new WritingSourceBindingCapture(json)).normalize(value.request()).fingerprint();
        if (request instanceof ParsedWritingRunStartRequest.Natural value) {
            var r = value.request();
            Map<String, Object> body = Map.of("inputMode", "natural", "workflow", "long_serial", "novelId", r.getNovelId(), "chapterId", r.getChapterId(), "writingSessionId", r.getWritingSessionId(), "userInstruction", r.getUserInstruction(), "targetWordCount", r.getTargetWordCount() == null ? 4000 : r.getTargetWordCount());
            return CommandIdempotency.requestFingerprint("start", Map.of("novelId", r.getNovelId(), "chapterId", r.getChapterId()), body, json);
        }
        if (request instanceof ParsedWritingRunStartRequest.ShortMedium value) {
            var r = value.request();
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("workflow", r.getWorkflow()); body.put("novelId", r.getNovelId()); body.put("operation", r.getOperation().getValue()); body.put("documentType", r.getDocumentType().getValue()); body.put("chapterId", nullable(r.getChapterId())); body.put("baseVersionId", nullable(r.getBaseVersionId())); body.put("sourceOutlineVersionId", nullable(r.getSourceOutlineVersionId())); body.put("selectionStart", nullable(r.getSelectionStart())); body.put("selectionEnd", nullable(r.getSelectionEnd())); body.put("selectedTextHash", nullable(r.getSelectedTextHash())); body.put("userInstruction", nullable(r.getUserInstruction()));
            Map<String, Object> resource = new LinkedHashMap<>(); resource.put("novelId", r.getNovelId()); resource.put("chapterId", nullable(r.getChapterId()));
            return CommandIdempotency.requestFingerprint("start", resource, body, json);
        }
        throw CommandIdempotencyStore.reused(clientRequestId(request));
    }

    private static ApiException retired() {
        return new ApiException(409, "EXECUTION_ENGINE_RETIRED", "历史耐久执行引擎已退役，请使用 V1 写作入口创建新任务");
    }

    static String clientRequestId(ParsedWritingRunStartRequest request) {
        if (request instanceof ParsedWritingRunStartRequest.Natural value) return value.request().getClientRequestId();
        if (request instanceof ParsedWritingRunStartRequest.Legacy value) {
            return value.request().getClientRequestId();
        }
        if (request instanceof ParsedWritingRunStartRequest.ShortMedium value) {
            return value.request().getClientRequestId();
        }
        return ((ParsedWritingRunStartRequest.LongSerial) request)
                .request()
                .getClientRequestId();
    }

    private static StartScope startScope(ParsedWritingRunStartRequest request) {
        if (request instanceof ParsedWritingRunStartRequest.Natural value) {
            var body = value.request();
            return new StartScope(body.getNovelId(), body.getChapterId(), body.getWritingSessionId(),
                    mutationTarget("chapter", body.getChapterId()));
        }
        if (request instanceof ParsedWritingRunStartRequest.LongSerial value) {
            LongSerialStartWritingRunRequest body = value.request();
            MutationTarget target = body.getOperation() == LongSerialStartWritingRunRequest.OperationEnum.REWRITE_OUTLINE_SELECTION
                    && body.getSelectionTarget() != null
                    ? mutationTarget(body.getSelectionTarget().getResourceType().getValue(),
                            body.getSelectionTarget().getResourceId())
                    : mutationTarget("chapter", body.getChapterId());
            return new StartScope(body.getNovelId(), body.getChapterId(), nullable(body.getWritingSessionId()), target);
        }
        if (request instanceof ParsedWritingRunStartRequest.Legacy value) {
            var body = value.request();
            return new StartScope(body.getNovelId(), body.getChapterId(), nullable(body.getWritingSessionId()),
                    mutationTarget("chapter", body.getChapterId()));
        }
        if (request instanceof ParsedWritingRunStartRequest.ShortMedium value) {
            ShortMediumStartWritingRunRequest body = value.request();
            String chapterId = nullable(body.getChapterId());
            MutationTarget target = body.getDocumentType()
                            == ShortMediumStartWritingRunRequest.DocumentTypeEnum.OUTLINE
                    ? mutationTarget("short_medium_outline", body.getNovelId())
                    : mutationTarget("short_medium_manuscript", chapterId);
            return new StartScope(
                    body.getNovelId(), chapterId, null, target, true);
        }
        return null;
    }

    private static StartScope lockStartScope(
            DSLContext transaction, String userId, StartScope scope) {
        // 所有新建入口必须先锁 Novel 再锁 Chapter；这样嵌套的 V1/V2 starter
        // 只会重复取得同序锁，不会从 Chapter 回头等待 Novel。
        var novel = transaction.fetchOne(
                """
                SELECT id FROM public."Novel"
                WHERE id = ? AND "userId" = ?
                FOR UPDATE
                """,
                scope.novelId(),
                userId);
        if (novel == null) return null;
        String chapterId = scope.chapterId();
        if (chapterId == null && scope.shortMedium()) {
            List<Record> chapters = transaction.fetch(
                    """
                    SELECT id FROM public."Chapter"
                    WHERE "novelId" = ?
                    ORDER BY "order", id
                    FOR UPDATE
                    """,
                    scope.novelId());
            if (chapters.size() != 1) return null;
            chapterId = chapters.getFirst().get("id", String.class);
        } else {
            var chapter = transaction.fetchOne(
                    """
                    SELECT id FROM public."Chapter"
                    WHERE id = ? AND "novelId" = ?
                    FOR UPDATE
                    """,
                    chapterId,
                    scope.novelId());
            if (chapter == null) return null;
        }
        MutationTarget target = scope.mutationTarget();
        if (scope.shortMedium()
                && "short_medium_manuscript".equals(target.type())
                && target.id() == null) {
            target = mutationTarget(target.type(), chapterId);
        }
        StartScope locked = new StartScope(
                scope.novelId(), chapterId, scope.writingSessionId(), target, scope.shortMedium());
        if (scope.writingSessionId() == null) return locked;
        var session = transaction.fetchOne(
                """
                SELECT id FROM public."WritingSession"
                WHERE id = ? AND "novelId" = ? AND "chapterId" = ?
                FOR UPDATE
                """,
                scope.writingSessionId(),
                scope.novelId(),
                chapterId);
        return session == null ? null : locked;
    }

    private void requireNoActiveLegacyMutation(DSLContext transaction, StartScope scope) {
        List<Record> rows = transaction.fetch(
                """
                SELECT task.id, task."chapterId", command."payloadJson"
                FROM public."WritingTask" AS task
                LEFT JOIN public."WritingRunCommand" AS command
                  ON command."taskId" = task.id AND command.kind = 'start'
                WHERE task."novelId" = ? AND task.phase NOT IN ('completed', 'error')
                ORDER BY task."createdAt" ASC, task.id ASC
                FOR UPDATE OF task
                """,
                scope.novelId());
        Set<String> seen = new HashSet<>();
        for (Record row : rows) {
            String taskId = row.get("id", String.class);
            if (seen.add(taskId) && startPayloadConflicts(
                    row.get("payloadJson", String.class),
                    row.get("chapterId", String.class),
                    scope)) {
                throw busy(scope);
            }
        }
    }

    private void requireNoActiveDurableMutation(DSLContext transaction, StartScope scope) {
        List<Record> active = transaction.fetch(
                """
                SELECT id, workflow, operation, "operationCatalogVersion", "chapterId", "targetType", "targetId", "modelPolicyJson" FROM public."WorkflowRun"
                WHERE "engineVersion" = 2 AND "novelId" = ?
                  AND status IN ('pending', 'running', 'waiting_user')
                ORDER BY "createdAt", id
                """,
                scope.novelId());
        for (Record run : active) {
            boolean mutating = executionContexts == null
                    ? executionPlan(run.get("modelPolicyJson", String.class)).operation().mutating()
                    : executionContexts.load(transaction, new WorkflowExecutionContext.RunIdentity(
                            run.get("id", String.class), run.get("workflow", String.class), run.get("operation", String.class),
                            run.get("operationCatalogVersion", String.class), run.get("chapterId", String.class),
                            run.get("targetType", String.class), run.get("targetId", String.class)),
                            json.readValue(run.get("modelPolicyJson", String.class), new TypeReference<Map<String, Object>>() {})).conservativeMutating();
            String targetType = run.get("targetType", String.class);
            String targetId = run.get("targetId", String.class);
            boolean sameChapter = Objects.equals(
                    scope.chapterId(), run.get("chapterId", String.class));
            boolean sameTarget = targetType == null || targetId == null
                    || scope.mutationTarget().equals(mutationTarget(targetType, targetId));
            if (mutating && (scope.shortMedium() || sameChapter || sameTarget)) {
                throw busy(scope);
            }
        }
    }

    private ExecutionPlanSnapshot executionPlan(String serialized) {
        try {
            Map<String, Object> stored = json.readValue(
                    serialized, new TypeReference<Map<String, Object>>() {});
            return ExecutionPlanSnapshot.fromStored(stored);
        } catch (RuntimeException exception) {
            throw new IllegalStateException("活动 V2 Run 的冻结执行计划无法解析", exception);
        }
    }

    private static void requireNoActiveForegroundRun(
            DSLContext transaction, String writingSessionId) {
        var legacy = transaction.fetchOne(
                """
                SELECT id FROM public."WritingTask"
                WHERE "writingSessionId" = ? AND phase NOT IN ('completed', 'error')
                LIMIT 1
                """,
                writingSessionId);
        if (legacy != null) throw foregroundBusy();
        var durable = transaction.fetchOne(
                """
                SELECT id FROM public."WorkflowRun"
                WHERE "engineVersion" = 2 AND "writingSessionId" = ?
                  AND status IN ('pending', 'running', 'waiting_user')
                LIMIT 1
                """,
                writingSessionId);
        if (durable != null) throw foregroundBusy();
    }

    private static boolean isLegacyMutation(ParsedWritingRunStartRequest request) {
        if (request instanceof ParsedWritingRunStartRequest.Legacy) return true;
        if (!(request instanceof ParsedWritingRunStartRequest.LongSerial value)) {
            return false;
        }
        return switch (value.request().getOperation()) {
            case PLAN_CHAPTER,
                    WRITE_CHAPTER,
                    REWRITE_SCENE,
                    REWRITE_CHAPTER_SELECTION,
                    REWRITE_OUTLINE_SELECTION -> true;
            default -> false;
        };
    }

    private boolean startPayloadConflicts(
            String serialized, String existingChapterId, StartScope requested) {
        boolean sameChapter = Objects.equals(requested.chapterId(), existingChapterId);
        if (serialized == null) return sameChapter;
        Map<String, Object> payload;
        try {
            Object parsed = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> raw)) return true;
            payload = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : raw.entrySet()) {
                if (!(entry.getKey() instanceof String key)) return true;
                payload.put(key, entry.getValue());
            }
        } catch (RuntimeException exception) {
            return sameChapter;
        }
        if (requested.shortMedium()
                && "short_medium".equals(payload.get("workflow"))
                && payload.get("operation") instanceof String operation) {
            return Set.of("generate_outline", "generate_manuscript", "replace_selection")
                    .contains(operation);
        }
        Object metadata = payload.get("_inkforgeCommand");
        if (!(metadata instanceof Map<?, ?> map)
                || !"start".equals(map.get("commandKind"))) {
            return sameChapter;
        }
        Object job = payload.get("job");
        if (!(job instanceof Map<?, ?> value)
                || !"long_serial".equals(value.get("workflow"))
                || !(value.get("operation") instanceof String operation)) {
            return sameChapter;
        }
        if (PROVABLY_READ_ONLY_LEGACY_OPERATIONS.contains(operation)) return false;
        if (sameChapter) return true;
        if (!"rewrite_outline_selection".equals(operation)) {
            return requested.mutationTarget().equals(
                    mutationTarget("chapter", existingChapterId));
        }
        Object selectionValue = value.get("selectionTarget");
        if (!(selectionValue instanceof Map<?, ?> selection)
                || !(selection.get("resourceType") instanceof String type)
                || !(selection.get("resourceId") instanceof String id)) return false;
        return requested.mutationTarget().equals(new MutationTarget(type, id));
    }

    private static ApiException busy() {
        return new ApiException(
                409, "WRITING_TARGET_BUSY", "当前写作目标已有进行中的写作任务");
    }

    private static ApiException busy(StartScope scope) {
        if (scope.shortMedium()) {
            return new ApiException(
                    409,
                    "SHORT_MEDIUM_DOCUMENT_RUN_ACTIVE",
                    "该中短篇作品已有文档任务正在处理");
        }
        return busy();
    }

    private static ApiException foregroundBusy() {
        return new ApiException(
                409,
                "WORKFLOW_FOREGROUND_RUN_EXISTS",
                "当前写作会话已有未完成的 Agent 运行");
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value != null && value.isPresent() ? value.orElse(null) : null;
    }

    private static MutationTarget mutationTarget(String type, String id) {
        return new MutationTarget("chapter".equals(type) ? "chapter_content" : type, id);
    }

    private static boolean isShortMedium(ParsedWritingRunStartRequest request) {
        return request instanceof ParsedWritingRunStartRequest.ShortMedium;
    }

    private record MutationTarget(String type, String id) {}
    private record StartScope(
            String novelId,
            String chapterId,
            String writingSessionId,
            MutationTarget mutationTarget,
            boolean shortMedium) {
        private StartScope(
                String novelId,
                String chapterId,
                String writingSessionId,
                MutationTarget mutationTarget) {
            this(novelId, chapterId, writingSessionId, mutationTarget, false);
        }
    }
}
