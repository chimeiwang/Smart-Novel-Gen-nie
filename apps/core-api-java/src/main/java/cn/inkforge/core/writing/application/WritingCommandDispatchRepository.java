package cn.inkforge.core.writing.application;

import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;
import java.time.LocalDateTime;
import java.util.List;

/** 写作命令认领、投递结算与退避重试的 PostgreSQL 端口。 */
public interface WritingCommandDispatchRepository {

    List<WritingDispatchRecord> claimDue(int limit, LocalDateTime activeStaleBefore);

    WritingDispatchRecord markAgentActive(String commandId);

    WritingDispatchRecord settleDispatchTerminal(
            String commandId, WritingAgentJobStatus agentStatus);

    WritingDispatchRecord settleCancelDispatch(String commandId);

    WritingDispatchRecord recordDispatchFailure(String commandId, String errorCode);
}
