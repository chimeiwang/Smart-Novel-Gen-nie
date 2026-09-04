package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.ObjectMapper;

class WorkflowExecutionContextTest {

    private static final ExecutionRegistry REGISTRY = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
    private static final IntentExecutionPlanSnapshot INTENT = IntentExecutionPlanSnapshot.freeze(
            REGISTRY, List.of("long_serial.answer_question", "long_serial.plan_chapter", "long_serial.write_chapter"));
    private static final WorkflowExecutionContext.RunIdentity NATURAL = new WorkflowExecutionContext.RunIdentity(
            "run-1", "long_serial", null, REGISTRY.catalogVersion(), "chapter-1", "chapter", "chapter-1");

    @Test
    void 旧版业务计划保持原身份预算和Step查找() {
        ExecutionPlanSnapshot plan = REGISTRY.freezePlan("long_serial.rewrite_chapter_selection", false);
        WorkflowExecutionContext context = WorkflowExecutionContext.fromStored(plan.stored(), null, null,
                new WorkflowExecutionContext.RunIdentity("run-old", "long_serial", "rewrite_chapter_selection",
                        REGISTRY.catalogVersion(), "chapter-1", "chapter", "chapter-1"));
        assertThat(context.modelPolicyStored()).isEqualTo(plan.stored());
        assertThat(context.initialIntentPlan()).isNull();
        assertThat(context.selection()).isNull();
        assertThat(context.businessPlan().stored()).isEqualTo(plan.stored());
        assertThat(context.effectiveOperation()).isEqualTo("rewrite_chapter_selection");
        assertThat(context.outerRunBudget()).isEqualTo(plan.runBudget());
        assertThat(context.conservativeMutating()).isTrue();
        assertStep(context, plan.generator());
        assertStep(context, plan.reviewers().getFirst());
    }

    @Test
    void 未解析自然Run没有业务身份并保守互斥但可以查解析器() {
        WorkflowExecutionContext context = unresolved();
        assertThat(context.initialIntentPlan().stored()).isEqualTo(INTENT.stored());
        assertThat(context.businessPlan()).isNull();
        assertThat(context.effectiveOperation()).isNull();
        assertThat(context.operationForPurpose("resolve_intent")).isNull();
        assertThat(context.conservativeMutating()).isTrue();
        assertThat(context.outerRunBudget().maxModelCalls()).isEqualTo(9);
        assertStep(context, INTENT.resolver());
        assertThatThrownBy(() -> context.operationForPurpose("generation")).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> assertStep(context, INTENT.requireOperationPlan("long_serial.write_chapter").generator()))
                .isInstanceOf(IllegalStateException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"answer_question", "plan_chapter", "write_chapter"})
    void 唯一选择只切换有效业务而不改初始身份及外层预算(String operation) {
        Map<String, Object> selection = selection(operation);
        WorkflowExecutionContext context = selected(selection);
        ExecutionPlanSnapshot business = INTENT.requireOperationPlan("long_serial." + operation);
        assertThat(context.modelPolicyStored()).isEqualTo(INTENT.stored());
        assertThat(context.effectiveOperation()).isEqualTo(operation);
        assertThat(context.operationForPurpose("generation")).isEqualTo(operation);
        assertThat(context.operationForPurpose("resolve_intent")).isNull();
        assertThat(context.businessPlan().sha256()).isEqualTo(business.sha256());
        assertThat(context.outerRunBudget()).isEqualTo(INTENT.runBudget());
        assertThat(context.conservativeMutating()).isEqualTo(!"answer_question".equals(operation));
        assertThat(context.selection().stored()).isEqualTo(selection);
        assertStep(context, business.generator());
        for (ExecutionPlanSnapshot.Step reviewer : business.reviewers()) assertStep(context, reviewer);
        // 已完成 resolver 的终态、计费仍可按初始计划校验，不误用所选业务 Profile。
        assertStep(context, INTENT.resolver());
    }

    @Test
    void 选择完整材料和哈希可往返且深不可变() {
        Map<String, Object> source = selection("write_chapter");
        String hash = ExecutionCanonicalJson.sha256(source);
        WorkflowIntentSelection parsed = WorkflowIntentSelection.fromStored(source, hash);
        assertThat(parsed.stored()).isEqualTo(source);
        assertThat(parsed.inputHash()).isEqualTo(hash);
        source.put("operationKey", "long_serial.answer_question");
        assertThat(parsed.operationKey()).isEqualTo("long_serial.write_chapter");
        assertThatThrownBy(() -> parsed.stored().put("runId", "other")).isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> WorkflowIntentSelection.fromStored(source, hash)).isInstanceOf(IllegalStateException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"schema", "runId", "operationKey", "operationPlanSha256", "resolverStepId",
            "resolverResultHash", "intentEvidenceBundleId", "targetType", "targetId", "scopeKind", "extra"})
    void 选择不允许缺字段或额外字段(String field) {
        Map<String, Object> selection = selection("write_chapter");
        if ("extra".equals(field)) selection.put("other", "额外字段");
        else selection.remove(field);
        assertThatThrownBy(() -> selected(selection)).isInstanceOf(IllegalStateException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"runId", "operationKey", "operationPlanSha256", "targetType", "targetId", "scopeKind", "schema"})
    void 即使选择材料自带正确哈希也不能换Run章节或授权子计划(String field) {
        Map<String, Object> selection = selection("write_chapter");
        selection.put(field, switch (field) {
            case "operationKey" -> "long_serial.rewrite_chapter_selection";
            case "operationPlanSha256" -> "0".repeat(64);
            default -> "other";
        });
        assertThatThrownBy(() -> selected(selection)).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 自然Run必须从当前章固定身份读取而不能已改成业务操作() {
        for (WorkflowExecutionContext.RunIdentity identity : List.of(
                new WorkflowExecutionContext.RunIdentity("run-1", "long_serial", "write_chapter", REGISTRY.catalogVersion(), "chapter-1", "chapter", "chapter-1"),
                new WorkflowExecutionContext.RunIdentity("run-1", "long_serial", null, REGISTRY.catalogVersion(), "chapter-1", "chapter", "chapter-2"),
                new WorkflowExecutionContext.RunIdentity("run-1", "long_serial", null, REGISTRY.catalogVersion(), null, null, null))) {
            assertThatThrownBy(() -> WorkflowExecutionContext.fromStored(INTENT.stored(), null, null, identity))
                    .isInstanceOf(IllegalStateException.class);
        }
    }

    @Test
    void 旧版计划不能夹带自然选择且选择材料与inputHash必须成对() {
        ExecutionPlanSnapshot plan = REGISTRY.freezePlan("long_serial.answer_question", false);
        Map<String, Object> selection = selection("answer_question");
        assertThatThrownBy(() -> WorkflowExecutionContext.fromStored(plan.stored(), selection,
                ExecutionCanonicalJson.sha256(selection), new WorkflowExecutionContext.RunIdentity(
                        "run-1", "long_serial", "answer_question", REGISTRY.catalogVersion(), "chapter-1", "chapter", "chapter-1")))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> WorkflowExecutionContext.fromStored(INTENT.stored(), selection, null, NATURAL))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> WorkflowExecutionContext.fromStored(INTENT.stored(), null, "0".repeat(64), NATURAL))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 不能用另一个授权子计划的Step模型冒充当前选择() {
        WorkflowExecutionContext context = selected(selection("write_chapter"));
        assertThatThrownBy(() -> assertStep(context, INTENT.requireOperationPlan("long_serial.plan_chapter").generator()))
                .isInstanceOf(IllegalStateException.class);
        ExecutionPlanSnapshot.Step resolver = INTENT.resolver();
        assertThatThrownBy(() -> context.requireStep("resolve_intent", "creative",
                resolver.modelProfile().profile(), 1, resolver.outputSchema().name(), 1, resolver.stepBudget().stored()))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 公共Step快照使用统一上下文并保留旧运行中模型绑定门禁() {
        WorkflowExecutionContext context = unresolved();
        WorkflowStepSnapshotFactory snapshots = new WorkflowStepSnapshotFactory(new ObjectMapper());
        var pending = snapshots.modelStep(context, "resolver-1", 1, "resolve_intent", "interactive", "pending",
                0, 0, null, INTENT.resolver().modelProfile().profile(), 1, null);
        assertThat(pending.getPurpose()).isEqualTo("resolve_intent");
        assertThat(pending.getModelProfile().getProfile()).isEqualTo("system.intent_resolver.v1");
        assertThatThrownBy(() -> snapshots.modelStep(context, "resolver-1", 1, "resolve_intent", "interactive", "running",
                1, 1, null, INTENT.resolver().modelProfile().profile(), 1, null))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("resolvedModel");
    }

    private static WorkflowExecutionContext unresolved() {
        return WorkflowExecutionContext.fromStored(INTENT.stored(), null, null, NATURAL);
    }

    private static WorkflowExecutionContext selected(Map<String, Object> selection) {
        return WorkflowExecutionContext.fromStored(INTENT.stored(), selection, ExecutionCanonicalJson.sha256(selection), NATURAL);
    }

    private static Map<String, Object> selection(String operation) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("schema", "durable.intent-selection.v1");
        value.put("runId", "run-1");
        value.put("operationKey", "long_serial." + operation);
        value.put("operationPlanSha256", INTENT.requireOperationPlan("long_serial." + operation).sha256());
        value.put("resolverStepId", "resolver-1");
        value.put("resolverResultHash", "a".repeat(64));
        value.put("intentEvidenceBundleId", "evidence-intent-1");
        value.put("targetType", "chapter");
        value.put("targetId", "chapter-1");
        value.put("scopeKind", "chapter");
        return value;
    }

    private static void assertStep(WorkflowExecutionContext context, ExecutionPlanSnapshot.Step step) {
        assertThat(context.requireStep(step.purpose(), step.lane(), step.modelProfile().profile(), step.modelProfile().version(),
                step.outputSchema().name(), step.outputSchema().version(), step.stepBudget().stored())).isEqualTo(step);
        assertThat(context.requireStepProfile(step.purpose(), step.lane(), step.modelProfile().profile(), step.modelProfile().version()))
                .isEqualTo(step.modelProfile());
    }
}
