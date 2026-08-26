package cn.inkforge.core.writing.application;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** 合并作品全量工作区和当前写作任务的规划快照。 */
public final class WritingContextService implements WritingContextProvider {

    private final WritingContextRepository planning;
    private final WritingWorkspaceReader workspace;

    public WritingContextService(
            WritingContextRepository planning, WritingWorkspaceReader workspace) {
        this.planning = Objects.requireNonNull(planning);
        this.workspace = Objects.requireNonNull(workspace);
    }

    @Override
    public Map<String, Object> build(String userId, String taskId) {
        Map<String, Object> planningContext = planning.planningContext(userId, taskId);
        Object novelId = planningContext.get("novelId");
        Object chapterId = planningContext.get("chapterId");
        if (!(novelId instanceof String novel) || !(chapterId instanceof String chapter)) {
            throw new IllegalStateException("写作任务上下文缺少作品身份");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("workspace", workspace.read(userId, novel, chapter));
        result.put("planning", planningContext);
        return result;
    }
}
