package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class WorkflowEventSequenceTest {

    @Test
    void 新运行从一开始且只接受连续序号() {
        assertThat(WorkflowEventSequence.next(0)).isEqualTo(1);
        assertThat(WorkflowEventSequence.next(41)).isEqualTo(42);
        assertThat(WorkflowEventSequence.requireNext(41, 42)).isEqualTo(42);
    }

    @Test
    void 缺口回退和溢出都明确失败() {
        assertThatThrownBy(() -> WorkflowEventSequence.requireNext(41, 43))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("连续");
        assertThatThrownBy(() -> WorkflowEventSequence.requireNext(41, 41))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("连续");
        assertThatThrownBy(() -> WorkflowEventSequence.next(Long.MAX_VALUE))
                .isInstanceOf(ArithmeticException.class);
    }

    @Test
    void 事件类型使用稳定线格式() {
        assertThat(WorkflowEventType.STEP_PROGRESS.wireValue()).isEqualTo("step_progress");
        assertThat(WorkflowEventType.STEP_FINISHED.wireValue()).isEqualTo("step_finished");
        assertThat(WorkflowEventType.fromWireValue("awaiting_user"))
                .isEqualTo(WorkflowEventType.AWAITING_USER);
        assertThatThrownBy(() -> WorkflowEventType.fromWireValue("agent_start"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
