package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.api.EvidenceExpansionRequest;
import java.util.List;
import java.util.Map;
import org.jooq.DSLContext;

/** 工作流拥有的结构化候选校验端口，由审核业务实现，避免工作流反向依赖审核内部实现。 */
@FunctionalInterface
public interface WorkflowStructuredCandidatePreparation {
    void validate(DSLContext transaction, String userId, String novelId, String runId, String bundleId,
            String artifactId, int revision, Map<String, Object> output);

    /** 返回保留原始事实并补齐所需来源的新 bundle 内容；不创建 Step 或修改现有 bundle。 */
    default List<WorkflowEvidenceItemPlan> expand(DSLContext transaction, String userId, String novelId,
            String runId, String bundleId, EvidenceExpansionRequest request) {
        throw new IllegalStateException("结构化资料证据补齐尚未装配");
    }
}
