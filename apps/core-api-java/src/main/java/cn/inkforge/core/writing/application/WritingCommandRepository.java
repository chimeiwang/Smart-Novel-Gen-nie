package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.WritingRunResponse;
import cn.inkforge.contracts.api.ResumeWritingRunRequest;
import cn.inkforge.contracts.api.ResumeWritingRunResponse;
import cn.inkforge.contracts.api.CancelWritingRunRequest;
import cn.inkforge.contracts.api.CancelWritingRunResponse;

/** 写作任务与耐久命令的事务端口；后续恢复、取消和投递共用同一实现。 */
public interface WritingCommandRepository {

    WritingRunResponse start(String userId, ParsedWritingRunStartRequest request);

    ResumeWritingRunResponse resume(
            String userId, String taskId, ResumeWritingRunRequest request);

    CancelWritingRunResponse cancel(
            String userId, String taskId, CancelWritingRunRequest request);
}
