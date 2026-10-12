package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.api.ExecutionCallbackReceipt;
import cn.inkforge.contracts.api.ExecutionStepFailure;
import cn.inkforge.contracts.api.ExecutionStepProgress;
import cn.inkforge.contracts.api.ExecutionStepResult;

/** Agent→Core V2 callback 的权威资源查询与事务收敛端口。 */
public interface WorkflowCallbackRepository {

    WorkflowCallbackResources resources(String runId, String stepId);

    ExecutionCallbackReceipt progress(ExecutionStepProgress progress);

    ExecutionCallbackReceipt result(ExecutionStepResult result);

    ExecutionCallbackReceipt failure(ExecutionStepFailure failure);
}
