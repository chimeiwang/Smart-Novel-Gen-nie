package cn.inkforge.core.workflows.application;

import java.time.OffsetDateTime;

/** V2 Run 创建或相同幂等请求重放后的权威身份。 */
public record WorkflowRunStartResult(
        String runId,
        String novelId,
        String chapterId,
        String writingSessionId,
        String workflow,
        String operation,
        String status,
        String stepId,
        long lastEventSequence,
        int revision,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        boolean replayed) {}
