package cn.inkforge.core.workflows.application;

import java.util.Map;
import org.jooq.DSLContext;

/** 工作流拥有的结构化候选校验端口，由审核业务实现，避免工作流反向依赖审核内部实现。 */
@FunctionalInterface
public interface WorkflowStructuredCandidatePreparation {
    void validate(DSLContext transaction, String userId, String novelId, String runId, String bundleId,
            String artifactId, int revision, Map<String, Object> output);
}
