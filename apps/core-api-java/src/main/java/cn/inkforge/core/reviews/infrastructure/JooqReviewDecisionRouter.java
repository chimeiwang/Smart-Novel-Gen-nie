package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.contracts.api.ArtifactDecisionPublicResponse;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.reviews.domain.ReviewDecisionIdentity;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.databind.ObjectMapper;

/** 按 ReviewArtifact 持久归属在 V1 命令与 V2 Workflow 决定之间分流。 */
final class JooqReviewDecisionRouter {

    private final CoreDatabase database;
    private final ObjectMapper json;
    private final JooqReviewDecisionStore legacy;
    private final JooqDurableReviewDecisionStore durable;
    private final boolean durableAgentSchemaReady;

    JooqReviewDecisionRouter(
            CoreDatabase database,
            ObjectMapper json,
            JooqReviewDecisionStore legacy,
            JooqDurableReviewDecisionStore durable) {
        this(database, json, legacy, durable, true);
    }

    JooqReviewDecisionRouter(
            CoreDatabase database,
            ObjectMapper json,
            JooqReviewDecisionStore legacy,
            JooqDurableReviewDecisionStore durable,
            boolean durableAgentSchemaReady) {
        this.database = Objects.requireNonNull(database);
        this.json = Objects.requireNonNull(json);
        this.legacy = Objects.requireNonNull(legacy);
        this.durable = durable;
        this.durableAgentSchemaReady = durableAgentSchemaReady;
        if (durableAgentSchemaReady && durable == null) {
            throw new IllegalArgumentException("V2 审核决定仓储未装配");
        }
    }

    ArtifactDecisionPublicResponse decide(
            String userId,
            String artifactId,
            ReviewArtifactDecisionRequest request) {
        ReviewDecisionIdentity identity = ReviewDecisionIdentity.create(artifactId, request, json);
        return database.transactionResult(transaction -> {
            // 所有引擎共享同一用户级幂等锁；同 key 的跨 Run 请求也不能并发落入两个事实表。
            transaction.fetchValue(
                    "SELECT pg_catalog.pg_advisory_xact_lock(?)",
                    CommandIdempotency.advisoryLockKey(userId, request.getClientRequestId()));
            int requestedEngine = requestedEngine(request);
            if (durableAgentSchemaReady) {
                ArtifactDecisionPublicResponse replay = durable.replay(
                        transaction,
                        userId,
                        request.getClientRequestId(),
                        identity.fingerprint());
                if (replay != null) {
                    requireRequestedEngine(request, 2);
                    return replay;
                }
            } else if (requestedEngine == 2) {
                throw new ApiException(
                        503,
                        "DURABLE_WORKFLOW_SCHEMA_UNAVAILABLE",
                        "耐久工作流数据库结构尚不可用");
            }
            ArtifactIdentity persisted = identity(transaction, userId, artifactId);
            if (requestedEngine == 1) {
                // V1 discard 会物理删除 Artifact；持久命令重放必须先于“资源不存在”判断。
                if (persisted != null && persisted.engineVersion() == 2) {
                    throw engineMismatch(requestedEngine, persisted.engineVersion());
                }
                return legacy.decide(userId, artifactId, request);
            }
            if (persisted == null) throw forbidden();
            if (persisted.engineVersion() != 2) {
                throw engineMismatch(requestedEngine, persisted.engineVersion());
            }
            return durable.decide(
                    transaction,
                    userId,
                    artifactId,
                    request,
                    identity);
        });
    }

    private static ArtifactIdentity identity(
            DSLContext transaction, String userId, String artifactId) {
        Record value = transaction.fetchOne(
                """
                SELECT artifact."workflowRunId"
                FROM public."ReviewArtifact" AS artifact
                JOIN public."Novel" AS novel ON novel.id = artifact."novelId"
                WHERE artifact.id = ? AND novel."userId" = ?
                """,
                artifactId,
                userId);
        if (value == null) return null;
        return new ArtifactIdentity(
                value.get("workflowRunId", String.class) == null ? 1 : 2);
    }

    private static int requestedEngine(ReviewArtifactDecisionRequest request) {
        return request.getEngineVersion()
                        == ReviewArtifactDecisionRequest.EngineVersionEnum.NUMBER_2
                ? 2
                : 1;
    }

    private static void requireRequestedEngine(
            ReviewArtifactDecisionRequest request, int expected) {
        int actual = requestedEngine(request);
        if (actual != expected) throw engineMismatch(actual, expected);
    }

    private static ApiException engineMismatch(int requested, int persisted) {
        return new ApiException(
                409,
                "ARTIFACT_ENGINE_VERSION_MISMATCH",
                "审核决定引擎版本与草案持久身份不一致",
                Map.of(
                        "requestedEngineVersion", requested,
                        "artifactEngineVersion", persisted));
    }

    private static ApiException forbidden() {
        return new ApiException(
                403, "REVIEW_ARTIFACT_FORBIDDEN", "无权访问该待审核草案");
    }

    private record ArtifactIdentity(int engineVersion) {}
}
