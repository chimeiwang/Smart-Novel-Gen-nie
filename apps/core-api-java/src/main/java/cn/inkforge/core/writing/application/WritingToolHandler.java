package cn.inkforge.core.writing.application;

import java.util.Map;

/** 单个 Agent 工具的同步应用处理器。 */
@FunctionalInterface
public interface WritingToolHandler {

    Map<String, Object> handle(WritingToolRequest request);
}
