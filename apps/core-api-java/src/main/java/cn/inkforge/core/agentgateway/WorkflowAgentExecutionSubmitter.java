package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;
import cn.inkforge.core.workflows.application.WorkflowExecutionSubmitter;
import java.util.Objects;

/** 通用 V2 Workflow 出站端口的唯一 Agent HTTP 适配器。 */
final class WorkflowAgentExecutionSubmitter implements WorkflowExecutionSubmitter {

    private final AgentServiceClient client;

    WorkflowAgentExecutionSubmitter(AgentServiceClient client) {
        this.client = Objects.requireNonNull(client);
    }

    @Override
    public ExecutionStepAccepted submit(ExecutionStepRequest request) {
        return client.submitExecution(request);
    }
}
