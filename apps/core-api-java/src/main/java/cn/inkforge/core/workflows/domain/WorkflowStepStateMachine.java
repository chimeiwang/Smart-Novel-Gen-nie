package cn.inkforge.core.workflows.domain;

import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** `WorkflowStep` 的唯一状态转换规则；终态只能按相同事实幂等重放。 */
public final class WorkflowStepStateMachine {

    private static final Map<WorkflowStepState, Set<WorkflowStepState>> TRANSITIONS = transitions();
    private static final Set<WorkflowStepState> TERMINAL = EnumSet.of(
            WorkflowStepState.COMPLETED, WorkflowStepState.FAILED, WorkflowStepState.SKIPPED);

    private WorkflowStepStateMachine() {}

    public static WorkflowStepState transition(WorkflowStepState from, WorkflowStepState to) {
        Objects.requireNonNull(from, "来源状态不能为空");
        Objects.requireNonNull(to, "目标状态不能为空");
        if (from == to) return to;
        if (!TRANSITIONS.getOrDefault(from, Set.of()).contains(to)) {
            throw new IllegalWorkflowTransitionException(
                    "WorkflowStep", from.databaseValue(), to.databaseValue());
        }
        return to;
    }

    public static boolean isTerminal(WorkflowStepState state) {
        return TERMINAL.contains(Objects.requireNonNull(state));
    }

    private static Map<WorkflowStepState, Set<WorkflowStepState>> transitions() {
        Map<WorkflowStepState, Set<WorkflowStepState>> transitions =
                new EnumMap<>(WorkflowStepState.class);
        transitions.put(
                WorkflowStepState.PENDING,
                EnumSet.of(
                        WorkflowStepState.RUNNING,
                        WorkflowStepState.COMPLETED,
                        WorkflowStepState.FAILED,
                        WorkflowStepState.SKIPPED));
        transitions.put(
                WorkflowStepState.RUNNING,
                EnumSet.of(
                        WorkflowStepState.COMPLETED,
                        WorkflowStepState.FAILED,
                        WorkflowStepState.SKIPPED));
        return Map.copyOf(transitions);
    }
}
