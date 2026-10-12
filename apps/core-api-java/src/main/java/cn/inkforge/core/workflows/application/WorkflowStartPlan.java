package cn.inkforge.core.workflows.application;

import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.IntentExecutionPlanSnapshot;
import java.util.List;
import java.util.Map;

/** 业务域完成权限和来源冻结后交给通用引擎的 Run 创建计划。 */
public record WorkflowStartPlan(
        String userId,
        String clientRequestId,
        String requestHash,
        String workflow,
        String operation,
        String operationCatalogVersion,
        String runKind,
        String novelId,
        String chapterId,
        String writingSessionId,
        String targetType,
        String targetId,
        Map<String, Object> normalizedInput,
        String evidencePolicyVersion,
        List<WorkflowEvidenceItemPlan> evidenceItems,
        ExecutionRegistry.RunBudget runBudget,
        ExecutionPlanSnapshot executionPlan,
        WorkflowInitialStepPlan initialStep,
        IntentExecutionPlanSnapshot intentPlan,
        SourceBinding sourceBinding) {

    public WorkflowStartPlan(String userId, String clientRequestId, String requestHash,
            String workflow, String operation, String operationCatalogVersion, String runKind,
            String novelId, String chapterId, String writingSessionId, String targetType, String targetId,
            Map<String, Object> normalizedInput, String evidencePolicyVersion,
            List<WorkflowEvidenceItemPlan> evidenceItems, ExecutionRegistry.RunBudget runBudget,
            ExecutionPlanSnapshot executionPlan, WorkflowInitialStepPlan initialStep,
            IntentExecutionPlanSnapshot intentPlan) {
        this(userId, clientRequestId, requestHash, workflow, operation, operationCatalogVersion, runKind,
                novelId, chapterId, writingSessionId, targetType, targetId, normalizedInput,
                evidencePolicyVersion, evidenceItems, runBudget, executionPlan, initialStep, intentPlan,
                new SourceBinding(targetType, targetId));
    }

    public WorkflowStartPlan(String userId, String clientRequestId, String requestHash,
            String workflow, String operation, String operationCatalogVersion, String runKind,
            String novelId, String chapterId, String writingSessionId, String targetType, String targetId,
            Map<String, Object> normalizedInput, String evidencePolicyVersion,
            List<WorkflowEvidenceItemPlan> evidenceItems, ExecutionRegistry.RunBudget runBudget,
            ExecutionPlanSnapshot executionPlan, WorkflowInitialStepPlan initialStep) {
        this(userId, clientRequestId, requestHash, workflow, operation, operationCatalogVersion, runKind,
                novelId, chapterId, writingSessionId, targetType, targetId, normalizedInput,
                evidencePolicyVersion, evidenceItems, runBudget, executionPlan, initialStep, null);
    }

    public WorkflowStartPlan {
        userId = nonBlank(userId, "用户 ID");
        clientRequestId = nonBlank(clientRequestId, "clientRequestId");
        if (clientRequestId.length() < 16 || clientRequestId.length() > 128) {
            throw new IllegalArgumentException("clientRequestId 长度无效");
        }
        if (requestHash == null || !requestHash.matches("^[0-9a-f]{64}$")) {
            throw new IllegalArgumentException("Run request hash 无效");
        }
        workflow = nonBlank(workflow, "workflow");
        if (intentPlan == null) operation = nonBlank(operation, "operation");
        operationCatalogVersion = nonBlank(operationCatalogVersion, "Operation Catalog 版本");
        runKind = nonBlank(runKind, "兼容 Run kind");
        if ((targetType == null) != (targetId == null)) {
            throw new IllegalArgumentException("Run target 类型与 ID 必须成对提供");
        }
        java.util.Objects.requireNonNull(sourceBinding, "Run 来源身份不能为空");
        normalizedInput = WorkflowJsonValues.freezeMap(normalizedInput);
        evidencePolicyVersion = nonBlank(evidencePolicyVersion, "Evidence policy 版本");
        evidenceItems = List.copyOf(evidenceItems);
        if (evidenceItems.isEmpty()) throw new IllegalArgumentException("Run 必须包含 Evidence");
        java.util.Objects.requireNonNull(runBudget, "Run 预算不能为空");
        java.util.Objects.requireNonNull(initialStep, "首个 Step 不能为空");
        if ((executionPlan == null) == (intentPlan == null)) {
            throw new IllegalArgumentException("Run 必须且只能保存一种初始执行计划");
        }
        if (intentPlan == null) executionPlan.requireOperation(workflow, operation, operationCatalogVersion);
        else intentPlan.requireInitialIdentity(workflow, operation, operationCatalogVersion);
        if (!runBudget.equals(intentPlan == null ? executionPlan.runBudget() : intentPlan.runBudget())) {
            throw new IllegalArgumentException("Run 预算与冻结执行计划不一致");
        }
        var frozenStep = intentPlan == null ? executionPlan.requireStep(
                initialStep.purpose(),
                initialStep.lane(),
                initialStep.modelProfile().key(),
                initialStep.modelProfile().version(),
                initialStep.outputSchema().key(),
                initialStep.outputSchema().version(),
                java.util.Map.of(
                        "profile", initialStep.stepBudget().key(),
                        "version", initialStep.stepBudget().version(),
                        "budget", frozenBudget(initialStep.stepBudget().budget()))) : intentPlan.resolver();
        if (intentPlan != null && (!"chat".equals(runKind) || !"chapter".equals(targetType)
                || !java.util.Objects.equals(chapterId, targetId) || novelId == null || chapterId == null
                || writingSessionId == null || !frozenStep.purpose().equals(initialStep.purpose())
                || !frozenStep.lane().equals(initialStep.lane())
                || !frozenStep.modelProfile().profile().equals(initialStep.modelProfile().key())
                || frozenStep.modelProfile().version() != initialStep.modelProfile().version()
                || !frozenStep.outputSchema().name().equals(initialStep.outputSchema().key())
                || frozenStep.outputSchema().version() != initialStep.outputSchema().version()
                || !frozenStep.outputSchema().sha256().equals(initialStep.outputSchema().sha256())
                || !frozenStep.stepBudget().budget().equals(initialStep.stepBudget().budget()))) {
            throw new IllegalArgumentException("自然 Run 初始身份或解析 Step 与冻结计划不一致");
        }
        if (!evidencePolicyVersion.equals(frozenStep.evidencePolicy())) {
            throw new IllegalArgumentException("首个 Step 与冻结执行计划不一致");
        }
    }

    public Map<String, Object> storedExecutionPlan() {
        return intentPlan == null ? executionPlan.stored() : intentPlan.stored();
    }

    /** 业务来源与执行目标可不同，但必须在 INSERT 时一次冻结，不能事后改写。 */
    public record SourceBinding(String type, String id) {
        public SourceBinding {
            if ((type == null) != (id == null)
                    || (type != null && (type.isBlank() || id.isBlank()))) {
                throw new IllegalArgumentException("Run 来源类型与 ID 必须同时为空或同时为非空字符串");
            }
        }
    }

    private static String nonBlank(String value, String label) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(label + "不能为空");
        return value;
    }

    private static Map<String, Object> frozenBudget(
            cn.inkforge.core.workflows.domain.WorkflowStepBudget budget) {
        return Map.of(
                "maxModelCalls", budget.maxModelCalls(),
                "maxInputTokens", budget.maxInputTokens(),
                "maxPromptCacheMissTokens", budget.maxPromptCacheMissTokens(),
                "maxCompletionTokens", budget.maxCompletionTokens(),
                "maxReasoningTokens", budget.maxReasoningTokens(),
                "maxVisibleOutputTokens", budget.maxVisibleOutputTokens(),
                "maxCostMicros", budget.maxCostMicros(),
                "maxWallClockSeconds", budget.maxWallClockSeconds(),
                "maxProviderRetries", budget.maxProviderRetries(),
                "maxProtocolCorrections", budget.maxProtocolCorrections());
    }
}
