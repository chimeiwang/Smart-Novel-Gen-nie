package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.agent.ExecutionStepRequest;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** PostgreSQL 租约驱动的 V2 Step 调度器；提交结果未知时只等租约恢复，不在 HTTP 层重试。 */
public final class WorkflowStepDispatcher {

    private static final Logger LOGGER = LoggerFactory.getLogger(WorkflowStepDispatcher.class);

    private final WorkflowDispatchRepository repository;
    private final WorkflowExecutionSubmitter submitter;
    private final int batchSize;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public WorkflowStepDispatcher(
            WorkflowDispatchRepository repository,
            WorkflowExecutionSubmitter submitter,
            int batchSize,
            Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.submitter = Objects.requireNonNull(submitter);
        if (batchSize < 1
                || interval == null
                || interval.isZero()
                || interval.isNegative()) {
            throw new IllegalArgumentException("Workflow 调度器配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
    }

    public int runOnce() {
        int submitted = 0;
        for (int index = 0; index < batchSize; index++) {
            var claimed = repository.claimNext();
            if (claimed.isEmpty()) break;
            ExecutionStepRequest request = claimed.orElseThrow();
            try {
                var accepted = submitter.submit(request);
                repository.recordAccepted(request, accepted);
                submitted++;
            } catch (WorkflowExecutionAdmissionSaturatedException exception) {
                repository.recordAdmissionSaturated(request, exception.retryAfter());
            } catch (WorkflowExecutionRejectedException exception) {
                repository.recordRejected(request, exception.errorCode());
            } catch (RuntimeException exception) {
                // HTTP 超时可能发生在 Agent 已耐久受理之后；保留 lease，禁止立即重复提交。
                LOGGER.warn(
                        "V2 Workflow Step 提交结果未知，等待租约恢复 runId={} stepId={} jobId={} fence={}",
                        request.getRunId(),
                        request.getStepId(),
                        request.getJobId(),
                        request.getFencingToken(),
                        exception);
            }
        }
        return submitted;
    }

    public void run() throws InterruptedException {
        while (!stop.get()) {
            runOnce();
            synchronized (stop) {
                if (!stop.get()) stop.wait(interval.toMillis());
            }
        }
    }

    public void requestStop() {
        stop.set(true);
        synchronized (stop) {
            stop.notifyAll();
        }
    }
}
