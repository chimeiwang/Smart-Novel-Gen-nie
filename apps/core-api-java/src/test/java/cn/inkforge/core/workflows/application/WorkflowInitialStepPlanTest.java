package cn.inkforge.core.workflows.application;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WorkflowInitialStepPlanTest {

    @Test
    void 初始模型Step只允许执行器已发布的Generation或ReviewPurpose() {
        var operation = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST)
                .resolve("long_serial.rewrite_chapter_selection", false);

        assertThatThrownBy(() -> new WorkflowInitialStepPlan(
                        "generate_candidate",
                        "creative",
                        Map.of("source", "test"),
                        operation.generatorProfile(),
                        operation.generatorStepBudget(),
                        operation.outputSchema()))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("generation/review");
    }
}
