package cn.inkforge.core.quality.application;

import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import cn.inkforge.core.quality.domain.QualityDispatchStatus;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 质量运行的即时投递与后台补投使用同一实现，并始终复用 WorkflowRun ID。
 */
public final class QualityRunDispatcher {

    private static final Logger LOGGER = LoggerFactory.getLogger(QualityRunDispatcher.class);

    private final QualityDispatchRepository repository;
    private final QualityRunSubmitter submitter;
    private final int batchSize;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public QualityRunDispatcher(
            QualityDispatchRepository repository,
            QualityRunSubmitter submitter,
            int batchSize,
            Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.submitter = Objects.requireNonNull(submitter);
        if (batchSize < 1
                || interval == null
                || interval.isZero()
                || interval.isNegative()) {
            throw new IllegalArgumentException("质量检查投递配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
    }

    public boolean dispatch(QualityDispatchRecord record) {
        try {
            QualityDispatchStatus status = submitter.submit(record);
            if (status == QualityDispatchStatus.QUEUED
                    || status == QualityDispatchStatus.RUNNING) {
                repository.markRunning(record.runId());
            } else {
                repository.failRun(
                        record.userId(), record.checkId(), record.runId(), record.novelId());
            }
            return true;
        } catch (RuntimeException exception) {
            String code = exception instanceof QualitySubmissionException transientFailure
                    ? transientFailure.code()
                    : exception.getClass().getSimpleName();
            repository.recordDispatchFailure(record.runId(), code);
            if (!(exception instanceof QualitySubmissionException)) throw exception;
            LOGGER.warn(
                    "质量检查投递失败，等待后台重试 runId={} checkId={} errorCode={}",
                    record.runId(), record.checkId(), code);
            return false;
        }
    }

    public int runOnce() {
        int completed = 0;
        List<QualityDispatchRecord> records = repository.listDispatchable(batchSize);
        for (QualityDispatchRecord record : records) {
            if (dispatch(record)) completed++;
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
