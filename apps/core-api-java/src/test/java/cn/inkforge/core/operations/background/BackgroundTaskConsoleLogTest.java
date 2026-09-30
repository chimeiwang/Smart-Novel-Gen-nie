package cn.inkforge.core.operations.background;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.SQLException;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

/** 验证实际 Boot 控制台布局，而不只检查 SLF4J 事件对象。 */
@ExtendWith(OutputCaptureExtension.class)
class BackgroundTaskConsoleLogTest {

    @Test
    void 异常字段须在控制台可见且不泄漏异常消息(CapturedOutput output) throws Exception {
        try (var context = new SpringApplicationBuilder(MinimalApplication.class)
                        .web(WebApplicationType.NONE)
                        .properties("spring.main.banner-mode=off")
                        .run();
                var registry = new BackgroundTaskRegistry(
                        Duration.ofMillis(200), Duration.ofMillis(200), Duration.ofMillis(20), 3)) {
            registry.start("诊断任务", new BackgroundWorker() {
                @Override
                public void run() {
                    throw new IllegalStateException(
                            "secret=假令牌", new SQLException("INSERT 参数=假密码", "23505", 17));
                }

                @Override
                public void requestStop() {}
            });

            awaitLog(output, "backgroundTaskName=\"诊断任务\"");
            String console = output.getOut() + output.getErr();
            assertThat(console)
                    .contains("errorCode=\"IllegalStateException\"")
                    .contains("consecutiveFailures=\"1\"")
                    .contains("retryDelayMillis=\"200\"")
                    .contains("exceptionClass=\"java.lang.IllegalStateException\"")
                    .contains("java.sql.SQLException{sqlState=23505}{vendorCode=17}[")
                    .contains("BackgroundTaskConsoleLogTest")
                    .doesNotContain("假令牌", "假密码", "INSERT 参数", "secret=");
        }
    }

    @Test
    void 非标准SQLState与异常因果循环不能泄漏或卡住(CapturedOutput output) throws Exception {
        try (var context = new SpringApplicationBuilder(MinimalApplication.class)
                        .web(WebApplicationType.NONE)
                        .properties("spring.main.banner-mode=off")
                        .run();
                var registry = new BackgroundTaskRegistry(
                        Duration.ofMillis(200), Duration.ofMillis(200), Duration.ofMillis(20), 3)) {
            registry.start("非法状态任务", new BackgroundWorker() {
                @Override
                public void run() {
                    throw new IllegalStateException(
                            "假令牌", new SQLException("假SQL参数", "secret=假SQLState", -42));
                }

                @Override
                public void requestStop() {}
            });
            awaitLog(output, "backgroundTaskName=\"非法状态任务\"");

            Exception first = new Exception("假循环秘密");
            Exception second = new Exception("假循环参数");
            first.initCause(second);
            second.initCause(first);
            registry.start("因果循环任务", new BackgroundWorker() {
                @Override
                public void run() throws Exception {
                    throw first;
                }

                @Override
                public void requestStop() {}
            });
            awaitLog(output, "[因果循环]");
            assertThat(output.getOut())
                    .contains("java.sql.SQLException{vendorCode=-42}[")
                    .contains("backgroundTaskName=\"因果循环任务\"")
                    .contains("[因果循环]")
                    .doesNotContain("假令牌", "假SQL参数", "假SQLState", "假循环秘密", "假循环参数");
        }
    }

    @Test
    void 提前返回和稳定恢复须分别留下可见事件(CapturedOutput output) throws Exception {
        CountDownLatch restarted = new CountDownLatch(1);
        CountDownLatch stopped = new CountDownLatch(1);
        try (var context = new SpringApplicationBuilder(MinimalApplication.class)
                        .web(WebApplicationType.NONE)
                        .properties("spring.main.banner-mode=off")
                        .run();
                var registry = new BackgroundTaskRegistry(
                        Duration.ofMillis(10), Duration.ofMillis(10), Duration.ofMillis(30), 3)) {
            registry.start("恢复任务", new BackgroundWorker() {
                private int starts;

                @Override
                public void run() throws InterruptedException {
                    if (++starts == 1) {
                        return;
                    }
                    restarted.countDown();
                    stopped.await();
                }

                @Override
                public void requestStop() {
                    stopped.countDown();
                }
            });
            assertThat(restarted.await(1, TimeUnit.SECONDS)).isTrue();
            awaitLog(output, "errorCode=\"BACKGROUND_TASK_RETURNED\"");
            assertThat(registry.isReady()).isTrue();
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
            while (!output.getOut().contains("recoveredFailures=\"1\"") && System.nanoTime() < deadline) {
                registry.isReady();
                Thread.sleep(1);
            }
            assertThat(output.getOut())
                    .contains("backgroundTaskName=\"恢复任务\"")
                    .contains("errorCode=\"BACKGROUND_TASK_RETURNED\"")
                    .contains("recoveredFailures=\"1\"")
                    .contains("stableWindowMillis=\"30\"");
        }
    }

    private static void awaitLog(CapturedOutput output, String expected) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (!output.getOut().contains(expected) && System.nanoTime() < deadline) {
            Thread.sleep(1);
        }
        assertThat(output.getOut()).contains(expected);
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    static class MinimalApplication {}
}
