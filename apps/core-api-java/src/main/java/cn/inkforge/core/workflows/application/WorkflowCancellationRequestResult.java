package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.agent.ExecutionCancelRequest;
import java.util.List;

/** 一次公共取消事务产生的精确执行器取消请求；数据库状态已先于这些请求提交。 */
public record WorkflowCancellationRequestResult(List<ExecutionCancelRequest> executorRequests) {

    public WorkflowCancellationRequestResult {
        executorRequests = List.copyOf(executorRequests);
    }
}
