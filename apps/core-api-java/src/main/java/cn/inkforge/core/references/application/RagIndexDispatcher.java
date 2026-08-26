package cn.inkforge.core.references.application;

import cn.inkforge.core.references.domain.RagDispatchRecord;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 领取已落库却尚未被 Agent 接受的索引意图，避免 HTTP 自动投递失败后永久丢失。 */
public final class RagIndexDispatcher {

    private static final Logger LOGGER = LoggerFactory.getLogger(RagIndexDispatcher.class);

    private final ReferenceRepository repository;
    private final RagIndexSubmitter submitter;
    private final int batchSize;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public RagIndexDispatcher(
            ReferenceRepository repository,
            RagIndexSubmitter submitter,
            int batchSize,
            Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.submitter = Objects.requireNonNull(submitter);
        if (batchSize < 1 || interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("检索索引投递配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
    }

    public int runOnce() {
        int completed = 0;
        List<RagDispatchRecord> records = repository.listPending(batchSize);
        for (RagDispatchRecord record : records) {
            try {
                RagDispatchStatus status = submitter.submit(
                        record.userId(),
                        record.novelId(),
                        record.referenceId(),
                        record.contentHash(),
                        record.generation());
                if (status != RagDispatchStatus.QUEUED && status != RagDispatchStatus.RUNNING) {
                    repository.markDispatchTerminal(record, status);
                }
                completed++;
            } catch (RagSubmissionException exception) {
                LOGGER.warn(
                        "检索索引投递失败，等待后台重试 referenceId={} errorCode={}",
                        record.referenceId(),
                        exception.code());
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
