package cn.inkforge.core.workflows.application;

import java.util.Map;
import org.jooq.DSLContext;

/** 视频领域投影端口；Run/Step 是执行权威，原 Task 保留来源、候选和作者决定的业务关联。 */
public interface WorkflowVideoAdaptationCompletion {
    boolean targetExists(DSLContext transaction, String runId);

    void markProcessing(DSLContext transaction, String runId);

    void saveDramaticCheckpoint(DSLContext transaction, String runId, Map<String, Object> checkpoint);

    Completion completePlan(DSLContext transaction, String runId, Map<String, Object> candidate);

    Completion completePrompts(DSLContext transaction, String runId, Map<String, Object> batch);

    String finish(DSLContext transaction, String runId, String terminal, String code, String message);

    record Completion(String terminal, String taskId, String artifactId) {}
}
