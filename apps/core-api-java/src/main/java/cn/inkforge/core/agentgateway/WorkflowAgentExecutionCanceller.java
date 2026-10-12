package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.ExecutionCancelAccepted;
import cn.inkforge.contracts.agent.ExecutionCancelRequest;
import cn.inkforge.core.workflows.application.WorkflowExecutionCanceller;
import java.util.Objects;

/** V2 Workflow 精确取消的唯一 Agent HTTP 适配器。 */
final class WorkflowAgentExecutionCanceller implements WorkflowExecutionCanceller {

    private final AgentServiceClient client;

    WorkflowAgentExecutionCanceller(AgentServiceClient client) {
        this.client = Objects.requireNonNull(client);
    }

    @Override
    public ExecutionCancelAccepted cancel(ExecutionCancelRequest request) {
        return client.cancelExecution(request.getJobId(), request);
    }
}
