package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.agent.ExecutionStepAccepted;
import cn.inkforge.contracts.agent.ExecutionStepRequest;

/** Workflow 模块拥有的 Core→Agent V2 出站端口。 */
public interface WorkflowExecutionSubmitter {

    ExecutionStepAccepted submit(ExecutionStepRequest request);
}
