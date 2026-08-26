package cn.inkforge.core.styles.application;

import cn.inkforge.core.styles.domain.PortraitDispatchRecord;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 重投 pending 与陈旧 processing 画像任务，并复用已持久化 taskId。 */
public final class PortraitTaskDispatcher {

    private static final Logger LOGGER = LoggerFactory.getLogger(PortraitTaskDispatcher.class);

    private final StyleRepository repository;
    private final PortraitRunSubmitter submitter;
    private final Clock clock;
    private final int batchSize;
    private final Duration interval;
    private final Duration processingStaleAfter;
    private final AtomicBoolean stop = new AtomicBoolean();

    public PortraitTaskDispatcher(
            StyleRepository repository,
            PortraitRunSubmitter submitter,
            Clock clock,
            int batchSize,
            Duration interval,
            Duration processingStaleAfter) {
        this.repository = Objects.requireNonNull(repository);
        this.submitter = Objects.requireNonNull(submitter);
        this.clock = Objects.requireNonNull(clock);
        if (batchSize < 1
                || interval == null
                || interval.isZero()
                || interval.isNegative()
                || processingStaleAfter == null
                || processingStaleAfter.isZero()
                || processingStaleAfter.isNegative()) {
            throw new IllegalArgumentException("画像任务投递配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
        this.processingStaleAfter = processingStaleAfter;
    }

    public int runOnce() {
        OffsetDateTime staleBefore = OffsetDateTime.ofInstant(
                clock.instant().minus(processingStaleAfter), ZoneOffset.UTC);
        List<PortraitDispatchRecord> records = repository.listReconcilable(
                batchSize, staleBefore);
        int completed = 0;
        for (PortraitDispatchRecord record : records) {
            try {
                PortraitDispatchStatus status = submitter.submit(
                        record.userId(),
                        record.styleId(),
                        record.taskId(),
                        record.taskId(),
                        record.section());
                if (status != PortraitDispatchStatus.QUEUED
                        && status != PortraitDispatchStatus.RUNNING) {
                    repository.markDispatchTerminal(
                            record.styleId(), record.taskId(), status);
                }
                completed++;
            } catch (PortraitSubmissionException exception) {
                LOGGER.warn(
                        "画像任务投递失败，等待后台重试 taskId={} styleId={} errorCode={}",
                        record.taskId(), record.styleId(), exception.code());
            }
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
