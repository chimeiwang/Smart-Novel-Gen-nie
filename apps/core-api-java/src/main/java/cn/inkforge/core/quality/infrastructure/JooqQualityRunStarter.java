package cn.inkforge.core.quality.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.RunQualityCheckResponse;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.quality.application.QualityRunDispatcher;
import cn.inkforge.core.quality.application.QualityRunStarter;
import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 新质量检查固定使用 V1；历史请求幂等重放先于新建门禁。 */
final class JooqQualityRunStarter implements QualityRunStarter {
    private final CoreDatabase database;
    private final JooqQualityRepository legacy;
    private final Supplier<QualityRunDispatcher> dispatcher;
    private final CoreSettings settings;
    private final ObjectMapper json;
    private final CommandIdempotencyStore idempotency;

    JooqQualityRunStarter(CoreDatabase database, JooqQualityRepository legacy,
            Supplier<QualityRunDispatcher> dispatcher, CoreSettings settings,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.legacy = Objects.requireNonNull(legacy);
        this.dispatcher = Objects.requireNonNull(dispatcher);
        this.settings = Objects.requireNonNull(settings);
        this.json = Objects.requireNonNull(json);
        this.idempotency = new CommandIdempotencyStore(json, settings.historicalWorkflowSchemaReady());
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
        if (!settings.v1FreshAgentStartsEnabled()) throw draining();
        Started started = database.transactionResult(tx -> {
            advisory(tx, userId, request.getClientRequestId());
            var concurrent = idempotency.resolve(tx, userId, request.getClientRequestId(), fingerprint);
            if (concurrent != null) return new Started(replay(tx, userId, checkId, request, body, fingerprint), null);
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

    private RunQualityCheckResponse replay(DSLContext tx, String userId, String checkId,
            RunQualityCheckRequest request, Map<String, Object> body, String fingerprint) {
        var existing = idempotency.resolve(tx, userId, request.getClientRequestId(), fingerprint);
        if (existing == null || existing.recordKind() != CommandIdempotencyStore.RecordKind.WORKFLOW_RUN) {
            throw CommandIdempotencyStore.reused(request.getClientRequestId());
        }
        if (settings.historicalWorkflowSchemaReady()) {
            Record run = tx.fetchOne("""
                    SELECT id, "userId", "sourceType", "sourceId", workflow, operation, input, "requestHash"
                    FROM public."WorkflowRun" WHERE id = ? AND "engineVersion" = 2
                    """, existing.recordId());
            if (run != null) {
                Map<String, Object> expected = new LinkedHashMap<>(); expected.put("checkId", checkId); expected.putAll(body);
                Map<String, Object> stored = json.readValue(run.get("input", String.class), new TypeReference<>() {});
                if (!userId.equals(run.get("userId", String.class))
                        || !HistoricalQualitySourceReader.SOURCE_TYPE.equals(run.get("sourceType", String.class))
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
