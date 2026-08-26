package cn.inkforge.core.writing.application;

import cn.inkforge.core.platform.failure.TransientInfrastructureErrors;
import cn.inkforge.core.writing.domain.WritingReconciliationTask;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 为没有耐久命令的旧 active/waiting_call 任务创建一次强制恢复命令。 */
public final class WritingRunReconciler {

    private static final Logger LOGGER = LoggerFactory.getLogger(WritingRunReconciler.class);

    private final WritingReconciliationRepository repository;
    private final WritingRunCommandDispatcher dispatcher;
    private final int batchSize;
    private final Duration interval;
    private final AtomicBoolean stop = new AtomicBoolean();

    public WritingRunReconciler(
            WritingReconciliationRepository repository,
            WritingRunCommandDispatcher dispatcher,
            int batchSize,
            Duration interval) {
        this.repository = Objects.requireNonNull(repository);
        this.dispatcher = Objects.requireNonNull(dispatcher);
        if (batchSize < 1 || interval == null || interval.isZero() || interval.isNegative()) {
            throw new IllegalArgumentException("运行对账配置无效");
        }
        this.batchSize = batchSize;
        this.interval = interval;
    }

    public int runOnce() {
        int created = 0;
        List<WritingReconciliationTask> tasks = repository.listReconcilable(batchSize);
        for (WritingReconciliationTask task : tasks) {
            try {
                if (repository.createCommand(task)) created++;
            } catch (RuntimeException exception) {
                if (!TransientInfrastructureErrors.isTransient(exception)) throw exception;
                LOGGER.warn(
                        "写作运行对账命令创建失败 taskId={} errorCode={}",
                        task.id(),
                        exception.getClass().getSimpleName());
            }
        }
        if (created > 0) dispatcher.runOnce();
        return created;
    }

    public void run() throws InterruptedException {
        while (!stop.get()) {
            try {
                runOnce();
            } catch (RuntimeException exception) {
                if (!TransientInfrastructureErrors.isTransient(exception)) throw exception;
                LOGGER.warn(
                        "写作运行后台领取暂时失败，等待下次重试 errorCode={}",
                        exception.getClass().getSimpleName());
            }
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
