package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.agent.ExecutionCancelRequest;
import java.util.Optional;

/** V2 Run 取消的 PostgreSQL 权威端口。 */
public interface WorkflowRunCancellationRepository {

    WorkflowCancellationRequestResult request(
            String userId, String runId, String clientRequestId);

    /** 已持久失效的质量来源必须在取消事务内重新核验，不能按过期扫描结果取消新状态。 */
    default WorkflowCancellationRequestResult requestInvalidatedQuality(
            String userId, String runId, String clientRequestId) {
        throw new UnsupportedOperationException("质量来源取消端口未实现");
    }

    Optional<ExecutionCancelRequest> claimCancellationRetry();

    int settleExpired(int limit);
}
