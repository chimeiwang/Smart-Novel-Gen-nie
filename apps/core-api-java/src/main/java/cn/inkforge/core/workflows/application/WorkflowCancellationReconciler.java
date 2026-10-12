package cn.inkforge.core.workflows.application;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;

/** 与执行提交器解耦的取消补投/租约收敛循环；route-off 或 Agent 暂不可配时仍必须运行。 */
public final class WorkflowCancellationReconciler {

    private final WorkflowRunCancellationService cancellations;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();
    private final java.util.function.Supplier<WorkflowQualityCompletion> quality;
    private final java.util.function.Supplier<WorkflowStylePortraitCompletion> styles;
    private final java.util.function.Supplier<WorkflowRagIndexCompletion> rag;

    public WorkflowCancellationReconciler(
            WorkflowRunCancellationService cancellations, Duration interval) {
        this(cancellations, interval, () -> null);
    }

    public WorkflowCancellationReconciler(WorkflowRunCancellationService cancellations, Duration interval,
            java.util.function.Supplier<WorkflowQualityCompletion> quality) {
        this(cancellations, interval, quality, () -> null);
    }

    public WorkflowCancellationReconciler(WorkflowRunCancellationService cancellations, Duration interval,
            java.util.function.Supplier<WorkflowQualityCompletion> quality,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styles) {
        this(cancellations, interval, quality, styles, () -> null);
    }

    public WorkflowCancellationReconciler(WorkflowRunCancellationService cancellations, Duration interval,
            java.util.function.Supplier<WorkflowQualityCompletion> quality,
            java.util.function.Supplier<WorkflowStylePortraitCompletion> styles,
            java.util.function.Supplier<WorkflowRagIndexCompletion> rag) {
        this.cancellations = Objects.requireNonNull(cancellations);
        this.quality = Objects.requireNonNull(quality);
        this.styles = Objects.requireNonNull(styles);
        this.rag = Objects.requireNonNull(rag);
        if (interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("Workflow 取消对账间隔必须为正数");
        }
        this.interval = interval;
    }

    public int runOnce() {
        WorkflowQualityCompletion projection = quality.get();
        int invalidated = 0;
        if (projection != null) {
            for (var run : projection.findInvalidatedRuns(20)) {
                cancellations.cancelInvalidatedQuality(run);
                invalidated++;
            }
        }
        WorkflowStylePortraitCompletion portraits = styles.get();
        if (portraits != null) {
            for (var run : portraits.findDeletedRuns(20)) {
                cancellations.cancelDeletedStyle(run);
                invalidated++;
            }
        }
        WorkflowRagIndexCompletion indexes = rag.get();
        if (indexes != null) {
            for (var run : indexes.findInvalidatedRuns(20)) {
                cancellations.cancelInvalidatedRag(run);
                invalidated++;
            }
        }
        return Math.addExact(invalidated, cancellations.runOnce());
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
