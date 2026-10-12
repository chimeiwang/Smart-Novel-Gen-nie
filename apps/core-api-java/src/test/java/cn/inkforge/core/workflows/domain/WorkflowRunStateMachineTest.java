package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class WorkflowRunStateMachineTest {

    @Test
    void 只允许规格定义的运行状态转换() {
        assertThat(WorkflowRunStateMachine.transition(
                        WorkflowRunState.PENDING, WorkflowRunState.RUNNING))
                .isEqualTo(WorkflowRunState.RUNNING);
        assertThat(WorkflowRunStateMachine.transition(
                        WorkflowRunState.RUNNING, WorkflowRunState.WAITING_USER))
                .isEqualTo(WorkflowRunState.WAITING_USER);
        assertThat(WorkflowRunStateMachine.transition(
                        WorkflowRunState.WAITING_USER, WorkflowRunState.RUNNING))
                .isEqualTo(WorkflowRunState.RUNNING);
        assertThat(WorkflowRunStateMachine.transition(
                        WorkflowRunState.WAITING_USER, WorkflowRunState.COMPLETED))
                .isEqualTo(WorkflowRunState.COMPLETED);
    }

    @Test
    void 相同状态重放保持幂等() {
        assertThat(WorkflowRunStateMachine.transition(
                        WorkflowRunState.RUNNING, WorkflowRunState.RUNNING))
                .isEqualTo(WorkflowRunState.RUNNING);
        assertThat(WorkflowRunStateMachine.transition(
                        WorkflowRunState.COMPLETED, WorkflowRunState.COMPLETED))
                .isEqualTo(WorkflowRunState.COMPLETED);
    }

    @Test
    void 终态不能被重新打开() {
        assertThatThrownBy(() -> WorkflowRunStateMachine.transition(
                        WorkflowRunState.COMPLETED, WorkflowRunState.RUNNING))
                .isInstanceOf(IllegalWorkflowTransitionException.class)
                .hasMessageContaining("completed")
                .hasMessageContaining("running");
        assertThat(WorkflowRunStateMachine.isTerminal(WorkflowRunState.FAILED)).isTrue();
        assertThat(WorkflowRunStateMachine.isTerminal(WorkflowRunState.CANCELLED)).isTrue();
    }

    @Test
    void 等待用户不能直接回到尚未开始() {
        assertThatThrownBy(() -> WorkflowRunStateMachine.transition(
                        WorkflowRunState.WAITING_USER, WorkflowRunState.PENDING))
                .isInstanceOf(IllegalWorkflowTransitionException.class);
    }
}
