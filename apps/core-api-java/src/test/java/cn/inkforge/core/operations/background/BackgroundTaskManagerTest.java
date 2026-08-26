package cn.inkforge.core.operations.background;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.operations.ReadinessRegistry;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import org.junit.jupiter.api.Test;

class BackgroundTaskManagerTest {

    @Test
    void 没有工作者时不得改变现有健康响应字段() {
        ReadinessRegistry readiness = new ReadinessRegistry();
        try (BackgroundTaskManager ignored = new BackgroundTaskManager(
                readiness, new BackgroundTaskRegistry())) {
            assertThat(readiness.evaluate().checks()).isEmpty();
        }
    }

    @Test
    void 首个工作者注册后崩溃状态必须进入统一就绪响应() throws Exception {
        ReadinessRegistry readiness = new ReadinessRegistry();
        BackgroundTaskRegistry tasks = new BackgroundTaskRegistry(
                Duration.ofMillis(100),
                Duration.ofMillis(100),
                Duration.ofMillis(20),
                3);
        try (BackgroundTaskManager manager = new BackgroundTaskManager(readiness, tasks)) {
            manager.start("writing_reconciler", new BackgroundWorker() {
                @Override
                public void run() {
                    throw new IllegalStateException("不能泄露的内部异常");
                }

                @Override
                public void requestStop() {}
            });
            await(
                    () -> "BACKGROUND_TASK_BACKOFF".equals(
                            tasks.errorCode("writing_reconciler")),
                    Duration.ofSeconds(1));

            ReadinessRegistry.Snapshot snapshot = readiness.evaluate();
            assertThat(snapshot.ready()).isFalse();
            assertThat(snapshot.checks()).containsEntry("background_tasks", "failed");
            assertThat(snapshot.backgroundTasks())
                    .containsExactlyEntriesOf(java.util.Map.of(
                            "writing_reconciler", "BACKGROUND_TASK_BACKOFF"));
            assertThat(snapshot.toString()).doesNotContain("不能泄露");
        }
    }

    @Test
    void 正常运行工作者必须使后台任务检查就绪() throws Exception {
        ReadinessRegistry readiness = new ReadinessRegistry();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch stopped = new CountDownLatch(1);
        try (BackgroundTaskManager manager = new BackgroundTaskManager(readiness)) {
            manager.start("writing_outbox_publisher", new BackgroundWorker() {
                @Override
                public void run() throws InterruptedException {
                    started.countDown();
                    stopped.await();
                }

                @Override
                public void requestStop() {
                    stopped.countDown();
                }
            });
            assertThat(started.await(1, java.util.concurrent.TimeUnit.SECONDS)).isTrue();

            assertThat(readiness.evaluate().checks())
                    .containsEntry("background_tasks", "ok");
        }
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
