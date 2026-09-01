package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.WritingRunStartResponse;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.writing.application.DurableAgentExecutionReadiness;
import cn.inkforge.core.writing.application.LongSerialDurableRunStarter;
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.writing.application.WritingCommandRepository;
import cn.inkforge.core.writing.application.WritingRunStarter;
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

/** 先无锁预解析并握手，再在用户级锁内冻结引擎身份；开关变化不迁移既有请求。 */
final class RoutingWritingRunStarter implements WritingRunStarter {

    private final CoreDatabase database;
    private final WritingCommandRepository legacy;
    private final LongSerialDurableRunStarter durable;
    private final CommandIdempotencyStore idempotency;
    private final CoreSettings settings;
    private final DurableAgentExecutionReadiness agentReadiness;
    private final ObjectMapper json;

    RoutingWritingRunStarter(
            CoreDatabase database,
            WritingCommandRepository legacy,
            LongSerialDurableRunStarter durable,
            CommandIdempotencyStore idempotency,
            CoreSettings settings,
            DurableAgentExecutionReadiness agentReadiness,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.legacy = Objects.requireNonNull(legacy);
        this.durable = Objects.requireNonNull(durable);
        this.idempotency = Objects.requireNonNull(idempotency);
        this.settings = Objects.requireNonNull(settings);
        this.agentReadiness = Objects.requireNonNull(agentReadiness);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public WritingRunStartResponse start(
            String userId, ParsedWritingRunStartRequest request) {
        String clientRequestId = clientRequestId(request);
        // 先做无锁只读预解析：已有 V1/V2 身份必须能在 Agent 离线或 manifest 升级时重放。
        CommandIdempotencyStore.Resolution preexisting = database.transactionResult(
                transaction -> idempotency.resolve(
                        transaction, userId, clientRequestId, null));
        if (preexisting != null) {
            return replayExisting(userId, request, clientRequestId, preexisting);
        }

        boolean routeDurable = routesDurable(userId, request);
        // 网络握手必须发生在 advisory/Run/章节锁之外。稍后会在原用户事务内二次解析，
        // 因此并发同标识即使同时通过握手，也只会创建一个 Run。
        boolean agentCompatible = !routeDurable || agentReadiness.check();
        return database.transactionResult(transaction -> {
            transaction.execute(
                    "SELECT pg_catalog.pg_advisory_xact_lock(?)",
                    CommandIdempotency.advisoryLockKey(userId, clientRequestId));
            CommandIdempotencyStore.Resolution existing = idempotency.resolve(
                    transaction, userId, clientRequestId, null);
            if (existing != null) {
                return replayExisting(userId, request, clientRequestId, existing);
            }
            if (routeDurable && !agentCompatible) throw agentUnavailable();
            StartScope scope = startScope(request);
            boolean locked = scope != null && lockStartScope(transaction, userId, scope);
            if (locked && scope.writingSessionId() != null) {
                requireNoActiveForegroundRun(transaction, scope.writingSessionId());
            }
            if (routeDurable) {
                if (locked) {
                    requireNoActiveLegacyMutation(transaction, scope.chapterId());
                    requireNoActiveDurableMutation(transaction, scope.chapterId());
                }
                return durable.start(userId, durableRequest(request));
            }
            if (locked && isLegacyMutation(request)) {
                requireNoActiveDurableMutation(transaction, scope.chapterId());
            }
            return legacy.start(userId, request);
        });
    }

    private WritingRunStartResponse replayExisting(
            String userId,
            ParsedWritingRunStartRequest request,
            String clientRequestId,
            CommandIdempotencyStore.Resolution existing) {
        return switch (existing.recordKind()) {
            case WRITING_COMMAND -> legacy.start(userId, request);
            case WORKFLOW_RUN -> durableReplay(userId, request, clientRequestId);
        };
    }

    private WritingRunStartResponse durableReplay(
            String userId,
            ParsedWritingRunStartRequest request,
            String clientRequestId) {
        if (!isDurableOperation(request)) {
            throw CommandIdempotencyStore.reused(clientRequestId);
        }
        return durable.start(userId, durableRequest(request));
    }

    private boolean routesDurable(
            String userId, ParsedWritingRunStartRequest request) {
        return isDurableOperation(request)
                && settings.routesNewDurableAgentRun(
                        userId, durableRequest(request).getNovelId());
    }

    private static boolean isDurableOperation(ParsedWritingRunStartRequest request) {
        return request instanceof ParsedWritingRunStartRequest.LongSerial value
                && value.request().getOperation()
                        == LongSerialStartWritingRunRequest.OperationEnum.REWRITE_CHAPTER_SELECTION;
    }

    private static LongSerialStartWritingRunRequest durableRequest(
            ParsedWritingRunStartRequest request) {
        if (request instanceof ParsedWritingRunStartRequest.LongSerial value
                && isDurableOperation(request)) {
            return value.request();
        }
        throw new IllegalArgumentException("当前请求不是已启用的 V2 长篇操作");
    }

    private static String clientRequestId(ParsedWritingRunStartRequest request) {
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
        if (request instanceof ParsedWritingRunStartRequest.LongSerial value) {
            LongSerialStartWritingRunRequest body = value.request();
            return new StartScope(
                    body.getNovelId(),
                    body.getChapterId(),
                    nullable(body.getWritingSessionId()));
        }
        if (request instanceof ParsedWritingRunStartRequest.Legacy value) {
            var body = value.request();
            return new StartScope(
                    body.getNovelId(),
                    body.getChapterId(),
                    nullable(body.getWritingSessionId()));
        }
        return null;
    }

    private static boolean lockStartScope(
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
        if (novel == null) return false;
        var chapter = transaction.fetchOne(
                """
                SELECT id FROM public."Chapter"
                WHERE id = ? AND "novelId" = ?
                FOR UPDATE
                """,
                scope.chapterId(),
                scope.novelId());
        if (chapter == null) return false;
        if (scope.writingSessionId() == null) return true;
        var session = transaction.fetchOne(
                """
                SELECT id FROM public."WritingSession"
                WHERE id = ? AND "novelId" = ? AND "chapterId" = ?
                FOR UPDATE
                """,
                scope.writingSessionId(),
                scope.novelId(),
                scope.chapterId());
        return session != null;
    }

    private void requireNoActiveLegacyMutation(
            DSLContext transaction, String chapterId) {
        List<Record> rows = transaction.fetch(
                """
                SELECT task.id, command."payloadJson"
                FROM public."WritingTask" AS task
                LEFT JOIN public."WritingRunCommand" AS command
                  ON command."taskId" = task.id AND command.kind = 'start'
                WHERE task."chapterId" = ? AND task.phase NOT IN ('completed', 'error')
                ORDER BY task."createdAt" ASC, task.id ASC
                FOR UPDATE OF task
                """,
                chapterId);
        Set<String> seen = new HashSet<>();
        for (Record row : rows) {
            String taskId = row.get("id", String.class);
            if (seen.add(taskId)
                    && startPayloadMutating(row.get("payloadJson", String.class))) {
                throw busy();
            }
        }
    }

    private static void requireNoActiveDurableMutation(
            DSLContext transaction, String chapterId) {
        var active = transaction.fetchOne(
                """
                SELECT id FROM public."WorkflowRun"
                WHERE "engineVersion" = 2 AND "chapterId" = ?
                  AND status IN ('pending', 'running', 'waiting_user')
                LIMIT 1
                """,
                chapterId);
        if (active != null) throw busy();
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

    private boolean startPayloadMutating(String serialized) {
        if (serialized == null) return true;
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
            return true;
        }
        Object metadata = payload.get("_inkforgeCommand");
        if (!(metadata instanceof Map<?, ?> map)
                || !"start".equals(map.get("commandKind"))) {
            return true;
        }
        Object job = payload.get("job");
        if (!(job instanceof Map<?, ?> value)
                || !"long_serial".equals(value.get("workflow"))
                || !(value.get("operation") instanceof String operation)) {
            return true;
        }
        return !"review_chapter".equals(operation);
    }

    private static ApiException busy() {
        return new ApiException(
                409, "WRITING_TARGET_BUSY", "当前章节已有进行中的写作任务");
    }

    private static ApiException foregroundBusy() {
        return new ApiException(
                409,
                "WORKFLOW_FOREGROUND_RUN_EXISTS",
                "当前写作会话已有未完成的 Agent 运行");
    }

    private static ApiException agentUnavailable() {
        return new ApiException(
                503,
                "DURABLE_AGENT_EXECUTION_UNAVAILABLE",
                "耐久 Agent 执行器当前不可用");
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value != null && value.isPresent() ? value.orElse(null) : null;
    }

    private record StartScope(String novelId, String chapterId, String writingSessionId) {}
}
