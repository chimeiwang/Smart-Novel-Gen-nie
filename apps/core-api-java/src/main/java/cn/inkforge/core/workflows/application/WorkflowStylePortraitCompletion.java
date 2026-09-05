package cn.inkforge.core.workflows.application;

import java.util.List;
import java.util.Map;
import org.jooq.DSLContext;

/** 文风业务投影在通用 Run/Step 事务内完成，不复制执行状态或开启模型调用。 */
public interface WorkflowStylePortraitCompletion {
    List<String> SECTIONS = List.of("creativeMethodology", "uniqueMarkers", "generationStyle",
            "expressionFeatures", "styleTraits");

    boolean targetExists(DSLContext transaction, String runId);

    String complete(DSLContext transaction, String runId, Map<String, String> sections);

    void finish(DSLContext transaction, String runId, String terminal);

    List<DeletedRun> findDeletedRuns(int limit);

    boolean isDeleted(DSLContext transaction, String runId);

    record DeletedRun(String userId, String runId) {
        public String cancelRequestId() { return "style-deleted." + runId; }
    }
}
