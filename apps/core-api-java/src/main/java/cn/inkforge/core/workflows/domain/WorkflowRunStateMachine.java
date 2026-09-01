package cn.inkforge.core.workflows.domain;

import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** `WorkflowRun` 的唯一状态转换规则；数据库仓储只能通过这里判断业务转换。 */
public final class WorkflowRunStateMachine {

    private static final Map<WorkflowRunState, Set<WorkflowRunState>> TRANSITIONS = transitions();
    private static final Set<WorkflowRunState> TERMINAL =
            EnumSet.of(WorkflowRunState.COMPLETED, WorkflowRunState.FAILED, WorkflowRunState.CANCELLED);

    private WorkflowRunStateMachine() {}

    public static WorkflowRunState transition(WorkflowRunState from, WorkflowRunState to) {
        Objects.requireNonNull(from, "来源状态不能为空");
        Objects.requireNonNull(to, "目标状态不能为空");
        if (from == to) return to;
        if (!TRANSITIONS.getOrDefault(from, Set.of()).contains(to)) {
            throw new IllegalWorkflowTransitionException(
                    "WorkflowRun", from.databaseValue(), to.databaseValue());
        }
        return to;
    }

    public static boolean isTerminal(WorkflowRunState state) {
        return TERMINAL.contains(Objects.requireNonNull(state));
    }

    private static Map<WorkflowRunState, Set<WorkflowRunState>> transitions() {
        Map<WorkflowRunState, Set<WorkflowRunState>> transitions =
                new EnumMap<>(WorkflowRunState.class);
        transitions.put(
                WorkflowRunState.PENDING,
                EnumSet.of(
                        WorkflowRunState.RUNNING,
                        WorkflowRunState.FAILED,
                        WorkflowRunState.CANCELLED));
        transitions.put(
                WorkflowRunState.RUNNING,
                EnumSet.of(
                        WorkflowRunState.WAITING_USER,
                        WorkflowRunState.COMPLETED,
                        WorkflowRunState.FAILED,
                        WorkflowRunState.CANCELLED));
        transitions.put(
                WorkflowRunState.WAITING_USER,
                EnumSet.of(
                        WorkflowRunState.RUNNING,
                        WorkflowRunState.COMPLETED,
                        WorkflowRunState.FAILED,
                        WorkflowRunState.CANCELLED));
        return Map.copyOf(transitions);
    }
}
