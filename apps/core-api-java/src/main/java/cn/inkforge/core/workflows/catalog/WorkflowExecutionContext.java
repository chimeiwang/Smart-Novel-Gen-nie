package cn.inkforge.core.workflows.catalog;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.Map;
import java.util.Objects;

/** 初始 Run 身份和唯一业务选择的纯投影；不查询数据库，也不按模型名称猜测业务操作。 */
public final class WorkflowExecutionContext {

    private final RunIdentity identity;
    private final IntentExecutionPlanSnapshot initialIntentPlan;
    private final ExecutionPlanSnapshot businessPlan;
    private final WorkflowIntentSelection selection;

    private WorkflowExecutionContext(RunIdentity identity, IntentExecutionPlanSnapshot initialIntentPlan,
            ExecutionPlanSnapshot businessPlan, WorkflowIntentSelection selection) {
        this.identity = identity;
        this.initialIntentPlan = initialIntentPlan;
        this.businessPlan = businessPlan;
        this.selection = selection;
    }

    public static WorkflowExecutionContext fromStored(
            Map<String, Object> initialMap, Map<String, Object> selectionInputMap,
            String selectionInputHash, RunIdentity identity) {
        Objects.requireNonNull(identity, "Run 身份不能为空");
        if (initialMap == null) throw invalid("Run 初始计划不能为空");
        if ((selectionInputMap == null) != (selectionInputHash == null)) {
            throw invalid("intent_selection 完整输入与 inputHash 必须成对");
        }
        Object version = initialMap.get("planVersion");
        if (ExecutionPlanSnapshot.PLAN_VERSION.equals(version)) {
            if (selectionInputMap != null) throw invalid("旧版业务计划不能夹带自然选择");
            ExecutionPlanSnapshot plan = ExecutionPlanSnapshot.fromStored(initialMap);
            plan.requireOperation(identity.workflow(), identity.operation(), identity.catalogVersion());
            return new WorkflowExecutionContext(identity, null, plan, null);
        }
        if (!IntentExecutionPlanSnapshot.PLAN_VERSION.equals(version)) throw invalid("Run 执行计划版本不受支持");
        IntentExecutionPlanSnapshot intent = IntentExecutionPlanSnapshot.fromStored(initialMap);
        intent.requireInitialIdentity(identity.workflow(), identity.operation(), identity.catalogVersion());
        if (identity.chapterId() == null || identity.chapterId().isBlank()
                || !"chapter".equals(identity.targetType()) || !identity.chapterId().equals(identity.targetId())) {
            throw invalid("自然 Run 初始目标必须固定到当前章节");
        }
        if (selectionInputMap == null) return new WorkflowExecutionContext(identity, intent, null, null);
        WorkflowIntentSelection selection = WorkflowIntentSelection.fromStored(selectionInputMap, selectionInputHash);
        if (!identity.runId().equals(selection.runId()) || !identity.chapterId().equals(selection.targetId())
                || !identity.targetType().equals(selection.targetType())) {
            throw invalid("intent_selection 与 Run 或当前章身份不一致");
        }
        ExecutionPlanSnapshot business = intent.requireOperationPlan(selection.operationKey(), selection.operationPlanSha256());
        String expectedSchema = intent.supportsNovelScopes() ? WorkflowIntentSelection.SCHEMA_V2 : WorkflowIntentSelection.SCHEMA;
        if (!expectedSchema.equals(selection.schema())
                || !intent.scopeKindForOperation(selection.operationKey()).equals(selection.scopeKind())) {
            throw invalid("intent_selection 版本或范围不匹配冻结解析器授权");
        }
        return new WorkflowExecutionContext(identity, intent, business, selection);
    }

    public RunIdentity initialIdentity() { return identity; }
    public IntentExecutionPlanSnapshot initialIntentPlan() { return initialIntentPlan; }
    public WorkflowIntentSelection selection() { return selection; }
    public ExecutionPlanSnapshot businessPlan() { return businessPlan; }
    public String effectiveOperation() { return businessPlan == null ? null : businessPlan.operation().operation(); }
    public boolean conservativeMutating() { return businessPlan == null || businessPlan.operation().mutating(); }

    /** 只用于已选择的自然任务，生成、复审和恢复共用相同的冻结范围投影。 */
    public Map<String, Object> selectedScope() {
        if (selection == null || initialIntentPlan == null) throw invalid("自然 Run 尚未选择有效范围");
        return "novel".equals(selection.scopeKind()) ? Map.of("kind", "novel")
                : Map.of("kind", "chapter", "chapterId", identity.chapterId());
    }

    public Map<String, Object> modelPolicyStored() {
        return initialIntentPlan == null ? requireBusinessPlan().stored() : initialIntentPlan.stored();
    }

    public ExecutionRegistry.RunBudget outerRunBudget() {
        return initialIntentPlan == null ? requireBusinessPlan().runBudget() : initialIntentPlan.runBudget();
    }

    public ExecutionPlanSnapshot requireBusinessPlan() {
        if (businessPlan == null) throw invalid("自然 Run 尚未选择业务操作，不能执行业务 Step");
        return businessPlan;
    }

    public String operationForPurpose(String purpose) {
        if (isResolver(purpose)) return null;
        return requireBusinessPlan().operation().operation();
    }

    public ExecutionPlanSnapshot.Step requireStep(String purpose, String lane, String profile,
            int profileVersion, String outputSchema, int outputSchemaVersion, Map<String, Object> storedBudget) {
        if (!isResolver(purpose)) {
            return requireBusinessPlan().requireStep(purpose, lane, profile, profileVersion,
                    outputSchema, outputSchemaVersion, storedBudget);
        }
        ExecutionPlanSnapshot.Step resolver = initialIntentPlan.resolver();
        requireStepProfile(purpose, lane, profile, profileVersion);
        if (!resolver.outputSchema().name().equals(outputSchema) || resolver.outputSchema().version() != outputSchemaVersion
                || !ExecutionCanonicalJson.sha256(resolver.stepBudget().stored()).equals(ExecutionCanonicalJson.sha256(storedBudget))) {
            throw invalid("解析器 Step 的 Schema 或预算不匹配冻结计划");
        }
        return resolver;
    }

    public ExecutionPlanSnapshot.ModelProfile requireStepProfile(String purpose, String lane, String profile, int profileVersion) {
        if (!isResolver(purpose)) return requireBusinessPlan().requireStepProfile(purpose, lane, profile, profileVersion);
        ExecutionPlanSnapshot.Step resolver = initialIntentPlan.resolver();
        if (!resolver.lane().equals(lane) || !resolver.modelProfile().profile().equals(profile)
                || resolver.modelProfile().version() != profileVersion) {
            throw invalid("解析器 Step 的模型身份不匹配冻结计划");
        }
        return resolver.modelProfile();
    }

    private boolean isResolver(String purpose) {
        if (!"resolve_intent".equals(purpose)) return false;
        if (initialIntentPlan == null) throw invalid("旧版业务 Run 不包含意图解析器");
        return true;
    }

    public record RunIdentity(String runId, String workflow, String operation, String catalogVersion,
            String chapterId, String targetType, String targetId) {
        public RunIdentity {
            if (runId == null || runId.isBlank() || workflow == null || workflow.isBlank()
                    || catalogVersion == null || catalogVersion.isBlank()) {
                throw invalid("Run ID、workflow 与 Catalog 版本不能为空");
            }
        }
    }

    private static IllegalStateException invalid(String message) { return new IllegalStateException(message); }
}
