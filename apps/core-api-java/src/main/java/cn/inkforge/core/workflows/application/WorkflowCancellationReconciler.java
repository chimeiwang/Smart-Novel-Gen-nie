package cn.inkforge.core.workflows.application;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;

/** 与执行提交器解耦的取消补投/租约收敛循环；route-off 或 Agent 暂不可配时仍必须运行。 */
public final class WorkflowCancellationReconciler {

    private final WorkflowRunCancellationService cancellations;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public WorkflowCancellationReconciler(
            WorkflowRunCancellationService cancellations, Duration interval) {
        this.cancellations = Objects.requireNonNull(cancellations);
        if (interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("Workflow 取消对账间隔必须为正数");
        }
        this.interval = interval;
    }

    public int runOnce() {
        return cancellations.runOnce();
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
