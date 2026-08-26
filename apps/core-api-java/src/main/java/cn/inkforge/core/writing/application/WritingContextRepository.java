package cn.inkforge.core.writing.application;

import java.util.Map;

/** 写作任务资源绑定与规划上下文的持久化端口。 */
public interface WritingContextRepository extends WritingToolAuthorizer {

    Map<String, Object> planningContext(String userId, String taskId);
}
