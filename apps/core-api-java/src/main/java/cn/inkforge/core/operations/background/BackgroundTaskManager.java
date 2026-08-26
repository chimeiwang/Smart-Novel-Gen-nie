package cn.inkforge.core.operations.background;

import cn.inkforge.core.operations.ReadinessRegistry;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;

/** Spring 业务模块使用的后台任务入口，并在首个任务出现时按现有契约惰性注册 readiness。 */
public final class BackgroundTaskManager implements AutoCloseable {

    private final ReadinessRegistry readiness;
    private final BackgroundTaskRegistry tasks;
    private final AtomicBoolean readinessRegistered = new AtomicBoolean();

    public BackgroundTaskManager(ReadinessRegistry readiness) {
        this(readiness, new BackgroundTaskRegistry());
    }

    BackgroundTaskManager(ReadinessRegistry readiness, BackgroundTaskRegistry tasks) {
        this.readiness = Objects.requireNonNull(readiness);
        this.tasks = Objects.requireNonNull(tasks);
    }

    public void start(String name, BackgroundWorker worker) {
        tasks.start(name, worker);
        if (readinessRegistered.compareAndSet(false, true)) {
            try {
                readiness.register(
                        "background_tasks", tasks::isReady, tasks::errorCodes);
            } catch (RuntimeException exception) {
                // readiness 无法接管时不能留下无人监督、却仍在写业务数据的工作线程。
                tasks.stopAll(Duration.ofSeconds(10));
                throw exception;
            }
        }
    }

    public boolean isReady() {
        return tasks.isReady();
    }

    public String errorCode(String name) {
        return tasks.errorCode(name);
    }

    @Override
    public void close() {
        tasks.close();
    }
}
