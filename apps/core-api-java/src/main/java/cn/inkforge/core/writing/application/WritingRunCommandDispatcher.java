package cn.inkforge.core.writing.application;

import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;
import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 即时投递与后台补投共用的写作命令调度器。 */
public final class WritingRunCommandDispatcher {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(WritingRunCommandDispatcher.class);

    private final WritingCommandDispatchRepository repository;
    private final WritingCommandSubmitter submitter;
    private final Clock clock;
    private final int batchSize;
    private final Duration interval;
    private final Duration activeStaleAfter;
    private final AtomicBoolean stop = new AtomicBoolean();

    public WritingRunCommandDispatcher(
            WritingCommandDispatchRepository repository,
            WritingCommandSubmitter submitter,
            Clock clock,
            int batchSize,
            Duration interval,
            Duration activeStaleAfter) {
        this.repository = Objects.requireNonNull(repository);
        this.submitter = Objects.requireNonNull(submitter);
        this.clock = Objects.requireNonNull(clock);
        if (batchSize < 1
                || interval == null
                || interval.isZero()
                || interval.isNegative()
                || activeStaleAfter == null
                || activeStaleAfter.isZero()
                || activeStaleAfter.isNegative()) {
            throw new IllegalArgumentException("写作命令投递配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
        this.activeStaleAfter = activeStaleAfter;
    }

    public boolean dispatch(WritingDispatchRecord command) {
        try {
            if ("cancel".equals(command.kind())) {
                submitter.cancel(command);
                repository.settleCancelDispatch(command.id());
                return true;
            }
            WritingAgentJobStatus status = submitter.submit(command);
            if (status == WritingAgentJobStatus.QUEUED
                    || status == WritingAgentJobStatus.RUNNING) {
                repository.markAgentActive(command.id());
            } else {
                repository.settleDispatchTerminal(command.id(), status);
            }
            return true;
        } catch (RuntimeException exception) {
            String code = exception instanceof WritingSubmissionException transientFailure
                    ? transientFailure.code()
                    : exception.getClass().getSimpleName();
            repository.recordDispatchFailure(command.id(), code);
            if (!(exception instanceof WritingSubmissionException)) throw exception;
            LOGGER.warn(
                    "写作命令投递失败，等待后台重试 commandId={} taskId={} errorCode={}",
                    command.id(), command.taskId(), code);
            return false;
        }
    }

    public int runOnce() {
        int completed = 0;
        List<WritingDispatchRecord> commands = repository.claimDue(
                batchSize, DatabaseTimestamp.now(clock).minus(activeStaleAfter));
        for (WritingDispatchRecord command : commands) {
            if (dispatch(command)) completed++;
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
