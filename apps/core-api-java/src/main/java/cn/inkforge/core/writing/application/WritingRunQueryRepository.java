package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.WritingRunListResponse;
import cn.inkforge.contracts.api.WritingRunStatusResponse;

/** 写作运行统一状态的只读端口。 */
public interface WritingRunQueryRepository {

    WritingRunStatusResponse get(String userId, String taskId);

    WritingRunListResponse list(
            String userId,
            String novelId,
            String chapterId,
            String writingSessionId,
            String operation,
            String outcome,
            String cursor,
            int limit);
}
