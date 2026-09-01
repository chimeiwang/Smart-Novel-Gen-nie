package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class WorkflowStepStateMachineTest {

    @Test
    void 模型步骤按待执行运行和终态推进() {
        assertThat(WorkflowStepStateMachine.transition(
                        WorkflowStepState.PENDING, WorkflowStepState.RUNNING))
                .isEqualTo(WorkflowStepState.RUNNING);
        assertThat(WorkflowStepStateMachine.transition(
                        WorkflowStepState.RUNNING, WorkflowStepState.COMPLETED))
                .isEqualTo(WorkflowStepState.COMPLETED);
        assertThat(WorkflowStepStateMachine.transition(
                        WorkflowStepState.RUNNING, WorkflowStepState.FAILED))
                .isEqualTo(WorkflowStepState.FAILED);
    }

    @Test
    void Core同步步骤可以在同一事务从待执行直接完成() {
        assertThat(WorkflowStepStateMachine.transition(
                        WorkflowStepState.PENDING, WorkflowStepState.COMPLETED))
                .isEqualTo(WorkflowStepState.COMPLETED);
        assertThat(WorkflowStepStateMachine.transition(
                        WorkflowStepState.PENDING, WorkflowStepState.SKIPPED))
                .isEqualTo(WorkflowStepState.SKIPPED);
    }

    @Test
    void 步骤终态不可重新运行且重放幂等() {
        assertThat(WorkflowStepStateMachine.transition(
                        WorkflowStepState.COMPLETED, WorkflowStepState.COMPLETED))
                .isEqualTo(WorkflowStepState.COMPLETED);
        assertThatThrownBy(() -> WorkflowStepStateMachine.transition(
                        WorkflowStepState.COMPLETED, WorkflowStepState.RUNNING))
                .isInstanceOf(IllegalWorkflowTransitionException.class);
        assertThat(WorkflowStepStateMachine.isTerminal(WorkflowStepState.SKIPPED)).isTrue();
    }
}
