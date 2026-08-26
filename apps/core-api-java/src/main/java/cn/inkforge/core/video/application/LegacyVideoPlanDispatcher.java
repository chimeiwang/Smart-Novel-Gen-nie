package cn.inkforge.core.video.application;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 只补投当前命名空间内已经存在的旧任务，不创建新的 VideoScene。 */
public final class LegacyVideoPlanDispatcher {

    private static final Logger LOGGER = LoggerFactory.getLogger(LegacyVideoPlanDispatcher.class);

    private final LegacyVideoPlanDispatchStore store;
    private final VideoAdaptationTaskSubmitter submitter;
    private final int batchSize;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public LegacyVideoPlanDispatcher(
            LegacyVideoPlanDispatchStore store,
            VideoAdaptationTaskSubmitter submitter,
            int batchSize,
            Duration interval) {
        this.store = Objects.requireNonNull(store);
        this.submitter = Objects.requireNonNull(submitter);
        if (batchSize < 1 || interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("历史视频任务投递配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
    }

    public boolean dispatch(VideoAdaptationTaskDispatch task) {
        try {
            VideoAdaptationAgentStatus status = submitter.submit(task);
            if (status == VideoAdaptationAgentStatus.QUEUED
                    || status == VideoAdaptationAgentStatus.RUNNING) {
                store.markSubmitted(task.taskId());
            } else {
                store.settleDispatchTerminal(task.taskId(), status);
            }
            return true;
        } catch (VideoAdaptationSubmissionException exception) {
            store.recordDispatchFailure(task.taskId(), exception.code(), true);
            LOGGER.warn(
                    "历史视频任务投递暂时失败 taskId={} jobId={} errorCode={}",
                    task.taskId(), task.jobId(), exception.code());
            return false;
        } catch (RuntimeException exception) {
            store.recordDispatchFailure(
                    task.taskId(), exception.getClass().getSimpleName(), false);
            throw exception;
        }
    }

    public int runOnce() {
        int completed = 0;
        for (VideoAdaptationTaskDispatch task : store.claimDue(batchSize)) {
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
