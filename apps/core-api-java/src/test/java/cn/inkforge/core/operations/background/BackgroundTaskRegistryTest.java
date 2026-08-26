package cn.inkforge.core.operations.background;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class BackgroundTaskRegistryTest {

    @Test
    void 只有仍在运行的任务才能通过就绪检查() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch stopped = new CountDownLatch(1);
        BackgroundWorker worker = blockingWorker(started, stopped);
        try (BackgroundTaskRegistry registry = new BackgroundTaskRegistry()) {
            registry.start("测试任务", worker);

            assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();
            assertThat(registry.isReady()).isTrue();

            worker.requestStop();
            await(() -> !registry.isReady(), Duration.ofSeconds(1));
            assertThat(registry.isReady()).isFalse();
        }
    }

    @Test
    void 崩溃任务必须退避并拉低就绪状态() throws Exception {
        try (BackgroundTaskRegistry registry = registry(
                Duration.ofMillis(100), Duration.ofMillis(100), Duration.ofMillis(20), 3)) {
            registry.start("崩溃任务", new BackgroundWorker() {
                @Override
                public void run() {
                    throw new IllegalStateException("模拟后台任务崩溃");
                }

                @Override
                public void requestStop() {}
            });

            await(
                    () -> "BACKGROUND_TASK_BACKOFF".equals(registry.errorCode("崩溃任务")),
                    Duration.ofSeconds(1));

            assertThat(registry.isReady()).isFalse();
            assertThat(registry.errorCodes())
                    .containsExactlyEntriesOf(java.util.Map.of(
                            "崩溃任务", "BACKGROUND_TASK_BACKOFF"));
        }
    }

    @Test
    void 崩溃后必须无重叠重启并在稳定窗口后恢复就绪() throws Exception {
        AtomicInteger starts = new AtomicInteger();
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximumActive = new AtomicInteger();
        CountDownLatch restarted = new CountDownLatch(1);
        CountDownLatch stopped = new CountDownLatch(1);
        BackgroundWorker worker = new BackgroundWorker() {
            @Override
            public void run() throws InterruptedException {
                int currentStarts = starts.incrementAndGet();
                int currentActive = active.incrementAndGet();
                maximumActive.accumulateAndGet(currentActive, Math::max);
                try {
                    if (currentStarts == 1) {
                        throw new IllegalStateException("模拟首次崩溃");
                    }
                    restarted.countDown();
                    stopped.await();
                } finally {
                    active.decrementAndGet();
                }
            }

            @Override
            public void requestStop() {
                stopped.countDown();
            }
        };

        try (BackgroundTaskRegistry registry = registry(
                Duration.ofMillis(5), Duration.ofMillis(10), Duration.ofMillis(40), 1)) {
            registry.start("可恢复任务", worker);

            assertThat(restarted.await(1, TimeUnit.SECONDS)).isTrue();
            assertThat(starts).hasValue(2);
            assertThat(maximumActive).hasValue(1);
            assertThat(registry.isReady()).isFalse();
            await(registry::isReady, Duration.ofSeconds(1));
            assertThat(registry.isReady()).isTrue();
        }
    }

    @Test
    void 停机不得重启任务且超时后必须中断失控线程() throws Exception {
        AtomicInteger starts = new AtomicInteger();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch interrupted = new CountDownLatch(1);
        BackgroundWorker worker = new BackgroundWorker() {
            @Override
            public void run() {
                starts.incrementAndGet();
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                } catch (InterruptedException exception) {
                    interrupted.countDown();
                    Thread.currentThread().interrupt();
                }
            }

            @Override
            public void requestStop() {}
        };

        BackgroundTaskRegistry registry = registry(
                Duration.ofMillis(5), Duration.ofMillis(10), Duration.ofMillis(20), 3);
        registry.start("关闭任务", worker);
        assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();

        registry.stopAll(Duration.ofMillis(20));

        assertThat(interrupted.await(1, TimeUnit.SECONDS)).isTrue();
        assertThat(starts).hasValue(1);
        assertThat(registry.isReady()).isFalse();
        assertThatThrownBy(() -> registry.start("新任务", worker))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("停止");
    }

    @Test
    void 重名任务和未注册任务必须返回稳定诊断() {
        CountDownLatch stopped = new CountDownLatch(1);
        BackgroundWorker worker = blockingWorker(new CountDownLatch(1), stopped);
        try (BackgroundTaskRegistry registry = new BackgroundTaskRegistry()) {
            assertThat(registry.errorCode("不存在")).isEqualTo("BACKGROUND_TASK_NOT_REGISTERED");
            registry.start("唯一任务", worker);
            assertThatThrownBy(() -> registry.start("唯一任务", worker))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("已注册");
        }
    }

    private static BackgroundTaskRegistry registry(
            Duration backoffBase,
            Duration backoffMax,
            Duration stabilityWindow,
            int unhealthyFailureThreshold) {
        return new BackgroundTaskRegistry(
                backoffBase, backoffMax, stabilityWindow, unhealthyFailureThreshold);
    }

    private static BackgroundWorker blockingWorker(
            CountDownLatch started, CountDownLatch stopped) {
        return new BackgroundWorker() {
            @Override
            public void run() throws InterruptedException {
                started.countDown();
                stopped.await();
            }

            @Override
            public void requestStop() {
                stopped.countDown();
            }
        };
    }

    private static void await(CheckedBoolean condition, Duration timeout) throws Exception {
        long deadline = System.nanoTime() + timeout.toNanos();
        while (!condition.getAsBoolean() && System.nanoTime() < deadline) {
            Thread.sleep(1);
        }
        assertThat(condition.getAsBoolean()).isTrue();
    }

    @FunctionalInterface
    private interface CheckedBoolean {
        boolean getAsBoolean() throws Exception;
    }
}
