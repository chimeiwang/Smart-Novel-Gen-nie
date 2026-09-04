package cn.inkforge.core.workflows.application;

import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import java.util.List;
import java.util.Map;

/** 自然入口选择已冻结业务后，只准备输入与来源；实现不得创建第二个 Run。 */
public interface WorkflowIntentBusinessPreparation {
    Prepared prepare(String userId, String novelId, String chapterId, String writingSessionId,
            String userInstruction, int targetWordCount, ExecutionPlanSnapshot operationPlan);

    record Prepared(Map<String, Object> input, List<WorkflowEvidenceItemPlan> evidenceItems,
            ExecutionPlanSnapshot.Step initialStep) {
        public Prepared {
            input = WorkflowJsonValues.freezeMap(input);
            evidenceItems = List.copyOf(evidenceItems);
            java.util.Objects.requireNonNull(initialStep);
            if (evidenceItems.isEmpty()) throw new IllegalArgumentException("业务准备缺少完整 Evidence");
        }
    }
}
