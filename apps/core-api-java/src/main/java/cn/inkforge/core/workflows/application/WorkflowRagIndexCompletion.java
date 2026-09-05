package cn.inkforge.core.workflows.application;

import java.math.BigDecimal;
import java.util.List;
import org.jooq.DSLContext;

/** 参考资料域拥有索引来源与最终派生结果，通用内核拥有 Run/Step 生命周期。 */
public interface WorkflowRagIndexCompletion {
    int frozenChunkCount(DSLContext transaction, String runId);
    boolean isCurrent(DSLContext transaction, String runId);
    String complete(DSLContext transaction, String runId, List<List<BigDecimal>> embeddings);
    String finish(DSLContext transaction, String runId, String requestedTerminal);
    List<InvalidatedRun> findInvalidatedRuns(int limit);
    boolean isInvalidated(DSLContext transaction, String runId);

    record InvalidatedRun(String userId, String runId) {
        public String cancelRequestId() { return "rag-invalidated." + runId; }
    }
}
