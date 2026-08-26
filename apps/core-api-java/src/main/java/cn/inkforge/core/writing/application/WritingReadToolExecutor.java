package cn.inkforge.core.writing.application;

import java.util.Map;

/** 共享只读工具注册层依赖的执行端口。 */
@FunctionalInterface
public interface WritingReadToolExecutor {

    Map<String, Object> execute(WritingToolRequest request);
}
