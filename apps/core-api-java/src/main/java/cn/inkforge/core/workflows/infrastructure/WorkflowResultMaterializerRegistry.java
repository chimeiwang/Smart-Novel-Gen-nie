package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 按 Run 已冻结的 Operation Catalog key 选择 Core 结果物化器。 */
final class WorkflowResultMaterializerRegistry {

    private static final Map<String, Binding> BINDINGS = Map.of(
            "long_serial.answer_question",
            new Binding("apply.chat_answer.v1", Materializer.CHAT_ANSWER),
            "long_serial.rewrite_chapter_selection",
            new Binding(
                    "apply.chapter_selection.v1",
                    Materializer.CHAPTER_SELECTION_REVIEW_ARTIFACT));

    private WorkflowResultMaterializerRegistry() {}

    static Set<String> supportedOperationKeys() {
        return Set.copyOf(BINDINGS.keySet());
    }

    static void requireEnabledOperationKeys(Set<String> enabledOperationKeys) {
        Objects.requireNonNull(enabledOperationKeys, "启用 Operation key 不能为空");
        Set<String> missing = new LinkedHashSet<>(enabledOperationKeys);
        missing.removeAll(BINDINGS.keySet());
        if (!missing.isEmpty()) {
            throw new IllegalStateException("启用 Operation 缺少 Core 结果物化器：" + missing);
        }
    }

    static Materializer resolve(ExecutionPlanSnapshot executionPlan) {
        Objects.requireNonNull(executionPlan, "冻结执行计划不能为空");
        ExecutionPlanSnapshot.Operation operation = executionPlan.operation();
        Binding binding = BINDINGS.get(operation.key());
        if (binding == null) {
            throw new IllegalArgumentException("冻结 Operation 尚未注册 Core 结果物化器");
        }
        if (!binding.applyHandler().equals(operation.applyHandler())) {
            throw new IllegalArgumentException("冻结 Operation 的 applyHandler 与结果物化器不一致");
        }
        return binding.materializer();
    }

    enum Materializer {
        CHAT_ANSWER,
        CHAPTER_SELECTION_REVIEW_ARTIFACT
    }

    private record Binding(String applyHandler, Materializer materializer) {}
}
