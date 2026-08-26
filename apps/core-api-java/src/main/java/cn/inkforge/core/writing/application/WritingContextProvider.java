package cn.inkforge.core.writing.application;

import java.util.Map;

/** 写作工具需要的作品全量工作区与当前任务规划上下文。 */
@FunctionalInterface
public interface WritingContextProvider {

    Map<String, Object> build(String userId, String taskId);
}
