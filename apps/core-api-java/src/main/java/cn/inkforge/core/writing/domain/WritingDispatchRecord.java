package cn.inkforge.core.writing.domain;

import java.util.Map;

/** Agent 投递所需的最小耐久写作命令快照。 */
public record WritingDispatchRecord(
        String id,
        String taskId,
        String userId,
        String novelId,
        String chapterId,
        String writingSessionId,
        String taskPhase,
        String graphStateJson,
        String kind,
        Map<String, Object> job,
        String status,
        int attemptCount,
        String artifactId,
        String decision) {}
