package cn.inkforge.core.reviews.application;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** 用户决定事务中已经锁定的审核产物快照。 */
public record ReviewArtifactState(
        String id,
        String novelId,
        String chapterId,
        String taskId,
        String artifactKey,
        String kind,
        int revision,
        Map<String, Object> payload) {

    public ReviewArtifactState {
        Objects.requireNonNull(id);
        Objects.requireNonNull(novelId);
        // V1 绑定 WritingTask；V2 由 workflowRunId 归属，因此正式应用快照允许 taskId 为空。
        Objects.requireNonNull(kind);
        Objects.requireNonNull(payload);
        payload = Collections.unmodifiableMap(new LinkedHashMap<>(payload));
    }
}
