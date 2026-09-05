package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 按 Run 已冻结的 Operation Catalog key 选择 Core 结果物化器。 */
final class WorkflowResultMaterializerRegistry {

    private static final Map<String, Binding> BINDINGS = bindings();

    private static Map<String, Binding> bindings() {
        Map<String, Binding> result = new java.util.LinkedHashMap<>(Map.of(
            "long_serial.answer_question",
            new Binding("apply.chat_answer.v1", Materializer.CHAT_ANSWER),
            "long_serial.plan_chapter",
            new Binding("apply.beat_plan.v1", Materializer.BEAT_PLAN_REVIEW_ARTIFACT),
            "long_serial.write_chapter",
            new Binding("apply.chapter_draft.v1", Materializer.CHAPTER_DRAFT_REVIEW_ARTIFACT),
            "long_serial.rewrite_scene",
            new Binding("apply.chapter_draft.v1", Materializer.CHAPTER_DRAFT_REVIEW_ARTIFACT),
            "long_serial.review_chapter",
            new Binding("apply.chapter_review_report.v1", Materializer.CHAPTER_REVIEW_REPORT),
            "long_serial.rewrite_outline_selection",
            new Binding("apply.outline_selection.v1", Materializer.OUTLINE_SELECTION_REVIEW_ARTIFACT),
            "long_serial.rewrite_chapter_selection",
            new Binding(
                    "apply.chapter_selection.v1",
                    Materializer.CHAPTER_SELECTION_REVIEW_ARTIFACT)));
        for (String operation : Set.of("create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing")) {
            result.put("long_serial." + operation, new Binding("apply.agent_updates.v1", Materializer.AGENT_UPDATES_REVIEW_ARTIFACT));
        }
        result.put("short_medium.generate_outline", new Binding("apply.short_medium_outline.v1", Materializer.SHORT_MEDIUM));
        result.put("short_medium.generate_manuscript", new Binding("apply.short_medium_manuscript.v1", Materializer.SHORT_MEDIUM));
        result.put("short_medium.replace_selection", new Binding("apply.short_medium_selection.v1", Materializer.SHORT_MEDIUM));
        result.put("short_medium.full_check", new Binding("apply.short_medium_check_report.v1", Materializer.SHORT_MEDIUM));
        result.put("quality.consistency", new Binding("apply.consistency_quality_report.v1", Materializer.CONSISTENCY_QUALITY));
        result.put("style.portrait", new Binding("apply.style_portrait.v1", Materializer.STYLE_PORTRAIT));
        result.put("rag.embedding", new Binding("apply.rag_embedding.v1", Materializer.RAG_INDEX));
        return Map.copyOf(result);
    }

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
        CHAPTER_REVIEW_REPORT,
        BEAT_PLAN_REVIEW_ARTIFACT,
        CHAPTER_DRAFT_REVIEW_ARTIFACT,
        CHAPTER_SELECTION_REVIEW_ARTIFACT,
        OUTLINE_SELECTION_REVIEW_ARTIFACT,
        AGENT_UPDATES_REVIEW_ARTIFACT,
        SHORT_MEDIUM,
        CONSISTENCY_QUALITY,
        STYLE_PORTRAIT,
        RAG_INDEX
    }

    private record Binding(String applyHandler, Materializer materializer) {}
}
