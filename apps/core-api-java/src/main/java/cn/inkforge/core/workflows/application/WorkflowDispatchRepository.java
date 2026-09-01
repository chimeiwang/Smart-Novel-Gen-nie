package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import java.time.Duration;
import java.util.Optional;

/** V2 Step 领取、租约换 fence 与 Agent 受理事实持久化端口。 */
public interface WorkflowDispatchRepository {

    Optional<ExecutionStepRequest> claimNext();

    void recordAccepted(ExecutionStepRequest request, ExecutionStepAccepted accepted);

    void recordAdmissionSaturated(ExecutionStepRequest request, Duration retryAfter);

    void recordRejected(ExecutionStepRequest request, String errorCode);
}
