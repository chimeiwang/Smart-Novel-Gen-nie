package cn.inkforge.core.video.application;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 即时投递和 PostgreSQL 租约补投共用的章节影视化调度器。 */
public final class VideoAdaptationTaskDispatcher {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(VideoAdaptationTaskDispatcher.class);

    private final VideoAdaptationTaskStore tasks;
    private final VideoAdaptationTaskSubmitter submitter;
    private final int batchSize;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public VideoAdaptationTaskDispatcher(
            VideoAdaptationTaskStore tasks,
            VideoAdaptationTaskSubmitter submitter,
            int batchSize,
            Duration interval) {
        this.tasks = Objects.requireNonNull(tasks);
        this.submitter = Objects.requireNonNull(submitter);
        if (batchSize < 1
                || interval == null
                || interval.isZero()
                || interval.isNegative()) {
            throw new IllegalArgumentException("章节影视化任务投递配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
    }

    public boolean dispatch(VideoAdaptationTaskDispatch task) {
        try {
            VideoAdaptationAgentStatus status = submitter.submit(task);
            if (status == VideoAdaptationAgentStatus.QUEUED
                    || status == VideoAdaptationAgentStatus.RUNNING) {
                tasks.markSubmitted(task.taskId());
            } else {
                tasks.settleDispatchTerminal(task.taskId(), status);
            }
            return true;
        } catch (VideoAdaptationSubmissionException exception) {
            tasks.recordDispatchFailure(task.taskId(), exception.code(), true);
            LOGGER.warn(
                    "章节影视化任务投递暂时失败 taskId={} jobId={} errorCode={}",
                    task.taskId(), task.jobId(), exception.code());
            return false;
        } catch (RuntimeException exception) {
            tasks.recordDispatchFailure(
                    task.taskId(), exception.getClass().getSimpleName(), false);
            throw exception;
        }
    }

    public int runOnce() {
        int completed = 0;
        for (VideoAdaptationTaskDispatch task : tasks.claimDue(batchSize)) {
            if (dispatch(task)) completed++;
        }
        return completed;
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
