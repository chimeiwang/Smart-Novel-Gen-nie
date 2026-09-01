package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.agent.ExecutionCancelRequest;
import java.util.Optional;

/** V2 Run 取消的 PostgreSQL 权威端口。 */
public interface WorkflowRunCancellationRepository {

    WorkflowCancellationRequestResult request(
            String userId, String runId, String clientRequestId);

    Optional<ExecutionCancelRequest> claimCancellationRetry();

    int settleExpired(int limit);
}
