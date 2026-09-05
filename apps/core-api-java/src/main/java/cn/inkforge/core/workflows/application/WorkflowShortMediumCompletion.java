package cn.inkforge.core.workflows.application;

import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;

/** 工作流拥有的中短篇最终物化端口；业务模块保存候选或报告，不改变生成 Run 的生命周期。 */
@FunctionalInterface
public interface WorkflowShortMediumCompletion {
    Completion complete(DSLContext transaction, CompletionRequest request);

    /** producer 是最后一个真实生成 Step；完整分段及零模型汇总仍由工作流内核负责。 */
    record CompletionRequest(
            String userId, String novelId, String chapterId, String operation, String runId,
            String producerStepId, String producerResultHash, String evidenceBundleId,
            String contextItemId, String contextContentSha256, Map<String, Object> frozenContext,
            String finalText) {
        public CompletionRequest {
            Objects.requireNonNull(userId);
            Objects.requireNonNull(novelId);
            Objects.requireNonNull(operation);
            Objects.requireNonNull(runId);
            Objects.requireNonNull(producerStepId);
            Objects.requireNonNull(producerResultHash);
            Objects.requireNonNull(evidenceBundleId);
            Objects.requireNonNull(contextItemId);
            Objects.requireNonNull(contextContentSha256);
            frozenContext = WorkflowJsonValues.freezeMap(frozenContext);
            Objects.requireNonNull(finalText);
        }
    }

    record Completion(String candidateVersionId, Map<String, Object> checkReport) {
        public Completion {
            if ((candidateVersionId == null) == (checkReport == null)
                    || candidateVersionId != null && candidateVersionId.isBlank()) {
                throw new IllegalArgumentException("中短篇完成必须且只能返回候选 ID 或完整报告");
            }
            if (checkReport != null) checkReport = WorkflowJsonValues.freezeMap(checkReport);
        }
    }
}
