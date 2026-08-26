package cn.inkforge.core.video.application;

import java.util.Map;

/** 后台领取的一份冻结章节改编任务。 */
public record VideoAdaptationTaskDispatch(
        String userId,
        String novelId,
        String taskId,
        String jobId,
        Map<String, Object> payload) {

    public VideoAdaptationTaskDispatch {
        payload = java.util.Collections.unmodifiableMap(
                new java.util.LinkedHashMap<>(payload));
    }
}
