package cn.inkforge.core.operations;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.junit.jupiter.api.Test;

class ReadinessRegistryTest {

    @Test
    void 异常检查必须失败并只暴露稳定诊断() {
        ReadinessRegistry registry = new ReadinessRegistry();
        registry.register("database", () -> true);
        registry.register(
                "queue_consumer",
                () -> {
                    throw new IllegalStateException("敏感底层地址");
                },
                () -> Map.of("queue_consumer", "BACKGROUND_TASK_FAILURE_DRAINING"));

        ReadinessRegistry.Snapshot snapshot = registry.evaluate();

        assertThat(snapshot.ready()).isFalse();
        assertThat(snapshot.checks())
                .containsEntry("database", "ok")
                .containsEntry("queue_consumer", "failed");
        assertThat(snapshot.backgroundTasks())
                .containsEntry("queue_consumer", "BACKGROUND_TASK_FAILURE_DRAINING");
        assertThat(snapshot.toString()).doesNotContain("敏感底层地址");
    }
}
