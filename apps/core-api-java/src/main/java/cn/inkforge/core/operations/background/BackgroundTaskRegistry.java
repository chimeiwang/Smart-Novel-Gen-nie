package cn.inkforge.core.operations.background;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 独占监督后台工作者：意外返回或异常后指数退避重启，停机时先协作停止再中断失控线程。
 *
 * <p>监督器不会吞掉失败后继续宣称服务就绪。任务在退避、连续失败、监督线程退出或应用排空期间都会拉低
 * readiness，并只暴露稳定错误码。
 */
public final class BackgroundTaskRegistry implements AutoCloseable {

    private static final Logger LOGGER = LoggerFactory.getLogger(BackgroundTaskRegistry.class);
    private static final Duration DEFAULT_STOP_TIMEOUT = Duration.ofSeconds(10);

    private final Duration backoffBase;
    private final Duration backoffMax;
    private final Duration stabilityWindow;
    private final int unhealthyFailureThreshold;
    private final ExecutorService executor;
    private final Map<String, Registration> registrations = new ConcurrentSkipListMap<>();
    private final CountDownLatch stoppingSignal = new CountDownLatch(1);
    private final AtomicBoolean stopping = new AtomicBoolean();
    private final Object lifecycleLock = new Object();

    public BackgroundTaskRegistry() {
        this(Duration.ofSeconds(1), Duration.ofSeconds(30), Duration.ofSeconds(60), 3);
    }

    public BackgroundTaskRegistry(
            Duration backoffBase,
            Duration backoffMax,
            Duration stabilityWindow,
            int unhealthyFailureThreshold) {
        this.backoffBase = positive(backoffBase, "后台任务基础退避时间");
        this.backoffMax = positive(backoffMax, "后台任务最大退避时间");
        this.stabilityWindow = positive(stabilityWindow, "后台任务稳定窗口");
        if (this.backoffMax.compareTo(this.backoffBase) < 0 || unhealthyFailureThreshold < 1) {
            throw new IllegalArgumentException("后台监督器配置无效");
        }
        this.unhealthyFailureThreshold = unhealthyFailureThreshold;
        this.executor = Executors.newThreadPerTaskExecutor(
                Thread.ofVirtual().name("inkforge-background-supervisor-", 0).factory());
    }

    public void start(String name, BackgroundWorker worker) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("后台任务名称无效");
        }
        Objects.requireNonNull(worker, "后台工作者不能为空");
        synchronized (lifecycleLock) {
            if (stopping.get()) {
                throw new IllegalStateException("后台监督器正在停止");
            }
            Registration registration = new Registration(name, worker);
            if (registrations.putIfAbsent(name, registration) != null) {
                throw new IllegalArgumentException("后台任务已注册：" + name);
            }
            try {
                registration.supervisor = executor.submit(() -> supervise(registration));
            } catch (RuntimeException exception) {
                registrations.remove(name, registration);
                throw exception;
            }
        }
    }

    public boolean hasRegistrations() {
        return !registrations.isEmpty();
    }

    public boolean isReady() {
        return !registrations.isEmpty()
                && registrations.values().stream().allMatch(this::registrationIsReady);
    }

    public String errorCode(String name) {
        Registration registration = registrations.get(name);
        if (registration == null) {
            return "BACKGROUND_TASK_NOT_REGISTERED";
        }
        markStableIfNeeded(registration);
        if (registration.state == State.BACKOFF) {
            return "BACKGROUND_TASK_BACKOFF";
        }
        if (registration.consecutiveFailures >= unhealthyFailureThreshold) {
            return "BACKGROUND_TASK_REPEATED_FAILURE";
        }
        Future<?> supervisor = registration.supervisor;
        if (supervisor != null && supervisor.isDone() && !stopping.get()) {
            return "BACKGROUND_SUPERVISOR_STOPPED";
        }
        return registrationIsReady(registration) ? null : "BACKGROUND_TASK_NOT_RUNNING";
    }

    public Map<String, String> errorCodes() {
        Map<String, String> errors = new LinkedHashMap<>();
        registrations.keySet().forEach(name -> {
            String errorCode = errorCode(name);
            if (errorCode != null) {
                errors.put(name, errorCode);
            }
        });
        return Map.copyOf(errors);
    }

    public void stopAll(Duration timeout) {
        Duration boundedTimeout = positive(timeout, "后台任务停止超时");
        synchronized (lifecycleLock) {
            if (stopping.compareAndSet(false, true)) {
                stoppingSignal.countDown();
                registrations.values().forEach(registration -> {
                    registration.stopRequested = true;
                    try {
                        registration.worker.requestStop();
                    } catch (RuntimeException exception) {
                        LOGGER.atError()
                                .addKeyValue("backgroundTaskName", registration.name)
                                .addKeyValue("errorCode", "BACKGROUND_STOP_FAILED")
                                .log("请求后台任务停止时发生异常");
                    }
                });
            }
        }

        long deadline = saturatingAdd(System.nanoTime(), boundedTimeout.toNanos());
        registrations.values().forEach(registration -> awaitUntil(registration.supervisor, deadline));
        registrations.values().stream()
                .map(registration -> registration.supervisor)
                .filter(Objects::nonNull)
                .filter(future -> !future.isDone())
                .forEach(future -> future.cancel(true));
        executor.shutdownNow();
        try {
            long remaining = Math.max(0, deadline - System.nanoTime());
            executor.awaitTermination(remaining, TimeUnit.NANOSECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public void close() {
        stopAll(DEFAULT_STOP_TIMEOUT);
    }

    private void supervise(Registration registration) {
        try {
            while (!stopping.get() && !registration.stopRequested) {
                registration.startedNanos = System.nanoTime();
                registration.state = State.RUNNING;
                String errorCode = "BACKGROUND_TASK_RETURNED";
                try {
                    registration.worker.run();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    errorCode = "InterruptedException";
                } catch (Exception exception) {
                    errorCode = exception.getClass().getSimpleName();
                }

                long ranFor = Math.max(0, System.nanoTime() - registration.startedNanos);
                if (stopping.get() || registration.stopRequested) {
                    registration.state = State.STOPPED;
                    return;
                }
                if (ranFor >= stabilityWindow.toNanos()) {
                    registration.consecutiveFailures = 0;
                }
                registration.consecutiveFailures++;
                registration.state = State.BACKOFF;
                Duration delay = backoff(registration.consecutiveFailures);
                LOGGER.atError()
                        .addKeyValue("backgroundTaskName", registration.name)
                        .addKeyValue("errorCode", errorCode)
                        .addKeyValue("consecutiveFailures", registration.consecutiveFailures)
                        .addKeyValue("retryDelayMillis", delay.toMillis())
                        .log("后台任务意外结束，等待监督器重启");
                try {
                    stoppingSignal.await(delay.toNanos(), TimeUnit.NANOSECONDS);
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    registration.state = State.STOPPED;
                    return;
                }
            }
        } finally {
            registration.state = State.STOPPED;
        }
    }

    private boolean registrationIsReady(Registration registration) {
        markStableIfNeeded(registration);
        Future<?> supervisor = registration.supervisor;
        return !stopping.get()
                && registration.state == State.RUNNING
                && registration.consecutiveFailures < unhealthyFailureThreshold
                && supervisor != null
                && !supervisor.isDone();
    }

    private void markStableIfNeeded(Registration registration) {
        if (registration.state == State.RUNNING
                && registration.consecutiveFailures > 0
                && System.nanoTime() - registration.startedNanos >= stabilityWindow.toNanos()) {
            registration.consecutiveFailures = 0;
        }
    }

    private Duration backoff(int failures) {
        long factor = 1L << Math.min(Math.max(0, failures - 1), 10);
        long baseNanos = backoffBase.toNanos();
        long maxNanos = backoffMax.toNanos();
        if (baseNanos > maxNanos / factor) {
            return backoffMax;
        }
        return Duration.ofNanos(Math.min(baseNanos * factor, maxNanos));
    }

    private static void awaitUntil(Future<?> future, long deadline) {
        if (future == null || future.isDone()) {
            return;
        }
        try {
            future.get(Math.max(0, deadline - System.nanoTime()), TimeUnit.NANOSECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        } catch (ExecutionException | TimeoutException ignored) {
            // 失败由稳定错误码表达；这里仅负责有界排空。
        }
    }

    private static Duration positive(Duration value, String label) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(label + "必须大于零");
        }
        return value;
    }

    private static long saturatingAdd(long first, long second) {
        long result = first + second;
        if (((first ^ result) & (second ^ result)) < 0) {
            return Long.MAX_VALUE;
        }
        return result;
    }

    private enum State {
        STARTING,
        RUNNING,
        BACKOFF,
        STOPPED
    }

    private static final class Registration {
        private final String name;
        private final BackgroundWorker worker;
        private volatile Future<?> supervisor;
        private volatile State state = State.STARTING;
        private volatile int consecutiveFailures;
        private volatile long startedNanos;
        private volatile boolean stopRequested;

        private Registration(String name, BackgroundWorker worker) {
            this.name = name;
            this.worker = worker;
        }
    }
}
