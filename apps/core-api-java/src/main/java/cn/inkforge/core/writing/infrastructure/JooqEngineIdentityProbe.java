package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.writing.application.EngineIdentityProbe;
import java.util.Objects;
import org.jooq.Record;

/** 按 Run 主键读取最小持久身份，不解析 Step、Artifact、命令或 Graph 快照。 */
final class JooqEngineIdentityProbe implements EngineIdentityProbe {

    private final CoreDatabase database;
    private final boolean durableAgentSchemaReady;

    JooqEngineIdentityProbe(CoreDatabase database, boolean durableAgentSchemaReady) {
        this.database = Objects.requireNonNull(database);
        this.durableAgentSchemaReady = durableAgentSchemaReady;
    }

    @Override
    public EngineIdentity probe(String userId, String runId) {
        if (!durableAgentSchemaReady) return EngineIdentity.V1_OR_MISSING;
        Record durable = database.dsl().fetchOne(
                """
                SELECT "userId"
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2
                """,
                runId);
        if (durable == null) return EngineIdentity.V1_OR_MISSING;
        if (!userId.equals(durable.get("userId", String.class))) {
            // 不能用 owner 过滤查询，否则同 ID 的 V1 会把已存在的越权 V2 身份覆盖成回退路径。
            throw new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
        }
        return EngineIdentity.V2;
    }
}
