package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.agent.ExecutionCancelRequest;
import java.util.Objects;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 先提交 Core 取消事实，再尽力通知 Agent；失败请求由耐久扫描使用同一 cancelRequestId 重放。 */
public final class WorkflowRunCancellationService {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(WorkflowRunCancellationService.class);

    private final WorkflowRunCancellationRepository repository;
    private final Optional<WorkflowExecutionCanceller> canceller;
    private final int batchSize;

    public WorkflowRunCancellationService(
            WorkflowRunCancellationRepository repository,
            Optional<WorkflowExecutionCanceller> canceller,
            int batchSize) {
        this.repository = Objects.requireNonNull(repository);
        this.canceller = Objects.requireNonNull(canceller);
        if (batchSize < 1) throw new IllegalArgumentException("Workflow 取消批次必须为正数");
        this.batchSize = batchSize;
    }

    public void cancel(String userId, String runId, String clientRequestId) {
        WorkflowCancellationRequestResult result =
                repository.request(userId, runId, clientRequestId);
        result.executorRequests().forEach(this::deliver);
    }

    /** 每轮先结算取消中的过期租约，再限量重投仍运行的精确取消。 */
    public int runOnce() {
        int settled = repository.settleExpired(batchSize);
        int delivered = 0;
        for (int index = 0; index < batchSize; index++) {
            Optional<ExecutionCancelRequest> request = repository.claimCancellationRetry();
            if (request.isEmpty()) break;
            deliver(request.orElseThrow());
            delivered++;
        }
        return Math.addExact(settled, delivered);
    }

    private void deliver(ExecutionCancelRequest request) {
        if (canceller.isEmpty()) return;
        try {
            canceller.orElseThrow().cancel(request);
        } catch (RuntimeException exception) {
            LOGGER.warn(
                    "V2 Workflow 取消投递失败，保留 cancelRequestId 等待耐久重试 runId={} stepId={} jobId={} fence={}",
                    request.getRunId(),
                    request.getStepId(),
                    request.getJobId(),
                    request.getFencingToken(),
                    exception);
        }
    }
}
