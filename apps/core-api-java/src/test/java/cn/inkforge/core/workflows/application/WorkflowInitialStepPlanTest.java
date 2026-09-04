package cn.inkforge.core.workflows.application;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WorkflowInitialStepPlanTest {

    @Test
    void 初始模型Step拒绝未发布Purpose() {
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
                .hasMessageContaining("purpose 尚未支持");
    }

    @Test
    void 初始意图Step使用已发布系统用途的完整授权() {
        var system = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST).resolveSystemPurpose("resolve_intent");
        var input = Map.<String, Object>of("userInstruction", "  请分析当前章节\n", "clarifications", java.util.List.of());
        var step = new WorkflowInitialStepPlan("resolve_intent", system.purpose().lane(), input,
                system.modelProfile(), system.stepBudget(), system.outputSchema());
        assertThat(step.purpose()).isEqualTo("resolve_intent");
        assertThat(step.lane()).isEqualTo("interactive");
        assertThat(step.input()).isEqualTo(input);
        assertThat(step.modelProfile()).isEqualTo(system.modelProfile());
    }
}
