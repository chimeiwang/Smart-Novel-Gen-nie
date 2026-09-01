package cn.inkforge.core.workflows.application;

import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.util.Map;

/** Run 首个模型 Step 的完整逻辑授权；ID 与 request hash 由 Core 事务生成。 */
public record WorkflowInitialStepPlan(
        String purpose,
        String lane,
        Map<String, Object> input,
        ExecutionRegistry.Profile modelProfile,
        ExecutionRegistry.StepBudgetProfile stepBudget,
        ExecutionRegistry.OutputSchema outputSchema) {

    public WorkflowInitialStepPlan {
        if (!java.util.Set.of("generation", "review").contains(purpose)) {
            throw new IllegalArgumentException("Step purpose 只允许 generation/review");
        }
        if (!java.util.Set.of("interactive", "creative", "batch_media").contains(lane)) {
            throw new IllegalArgumentException("模型 Step lane 无效");
        }
        input = WorkflowJsonValues.freezeMap(input);
        if (!modelProfile.supported()
                || !modelProfile.promptProfile().supported()
                || !stepBudget.supported()
                || !outputSchema.supported()) {
            throw new IllegalArgumentException("首个 Step 依赖尚未启用");
        }
    }
}
