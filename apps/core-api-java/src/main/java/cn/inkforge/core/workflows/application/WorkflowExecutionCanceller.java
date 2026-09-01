package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.agent.ExecutionCancelAccepted;
import cn.inkforge.contracts.agent.ExecutionCancelRequest;

/** V2 Workflow 到 Agent 执行器的精确取消出站端口。 */
@FunctionalInterface
public interface WorkflowExecutionCanceller {

    ExecutionCancelAccepted cancel(ExecutionCancelRequest request);
}
