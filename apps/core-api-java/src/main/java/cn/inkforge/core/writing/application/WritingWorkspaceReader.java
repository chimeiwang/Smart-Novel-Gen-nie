package cn.inkforge.core.writing.application;

import java.util.Map;

/** 写作上下文对小说工作区一致性读模型的窄端口。 */
@FunctionalInterface
public interface WritingWorkspaceReader {

    Map<String, Object> read(String userId, String novelId, String chapterId);
}
