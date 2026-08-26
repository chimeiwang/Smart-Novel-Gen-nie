package cn.inkforge.core.writing.domain;

import cn.inkforge.contracts.api.WritingRunOutcome;
import cn.inkforge.contracts.api.WritingRunOutcomeCommand;
import cn.inkforge.contracts.api.WritingRunOutcomeResult;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.Set;

/**
 * 把任务、当前命令和耐久结果事实收敛为唯一公开写作结果状态。
 *
 * <p>判断优先级固定为：有效取消、任务与命令终态冲突、活动命令、工作流专用结果。这个顺序保证取消链或
 * 损坏终态不会被“任务已完成”掩盖。投影器不读取 Redis/SSE，也不根据用户文本猜操作；输入事实必须先由
 * {@link WritingRunStatusProjector} 从 PostgreSQL 相互印证。
 */
public final class WritingRunOutcomeProjector {

    private static final Set<String> ACTIVE_COMMANDS =
            Set.of("pending", "submitted", "processing");

    public WritingRunOutcome project(
            WritingRunOutcomeFacts facts, OffsetDateTime observedAt) {
        Objects.requireNonNull(facts);
        Objects.requireNonNull(observedAt);
        WritingRunOutcomeCommand command = command(facts);
        WritingRunOutcomeResult result = new WritingRunOutcomeResult(
                        WritingRunOutcomeResult.KindEnum.fromValue(facts.resultKind()),
                        facts.resultReady())
                .id(facts.resultId());
        boolean taskTerminal = terminal(facts.taskPhase());

        // 取消是覆盖性控制事实：先验证取消链，不能再让被取消命令的成功结果决定公开状态。
        if (Boolean.TRUE.equals(facts.cancelEffective())) {
            return outcome(
                    "cancelled", "WRITING_RUN_CANCELLED", true, command, result, observedAt, false);
        }
        if (Boolean.FALSE.equals(facts.cancelEffective()) && !facts.cancelChainValid()) {
            return outcome(
                    "inconsistent",
                    "CANCEL_PRIOR_OUTCOME_INVALID",
                    taskTerminal,
                    command,
                    result,
                    observedAt,
                    false);
        }

        String effectiveStatus = facts.effectiveCommandStatus() == null
                ? facts.commandStatus()
                : facts.effectiveCommandStatus();
        // 任务与命令分别持久化；两者终态不一致代表提交链损坏，不能选择“看起来更成功”的一侧。
        if (terminalConflict(facts.taskPhase(), effectiveStatus)) {
            return outcome(
                    "inconsistent",
                    "TASK_COMMAND_TERMINAL_CONFLICT",
                    taskTerminal,
                    command,
                    result,
                    observedAt,
                    false);
        }
        if ("pending".equals(effectiveStatus)) {
            return outcome(
                    "queued", "COMMAND_PENDING", taskTerminal, command, result, observedAt, false);
        }
        if ("submitted".equals(effectiveStatus) || "processing".equals(effectiveStatus)) {
            return outcome(
                    "running", "COMMAND_RUNNING", taskTerminal, command, result, observedAt, false);
        }
        if ("short_medium".equals(facts.workflow())) {
            return shortMedium(facts, effectiveStatus, command, result, observedAt);
        }
        return longForm(facts, effectiveStatus, command, result, observedAt);
    }

    private static WritingRunOutcome shortMedium(
            WritingRunOutcomeFacts facts,
            String commandStatus,
            WritingRunOutcomeCommand command,
            WritingRunOutcomeResult result,
            OffsetDateTime observedAt) {
        if ("error".equals(facts.taskPhase()) && "failed".equals(commandStatus)) {
            if (facts.resultReady()) {
                return outcome(
                        "inconsistent",
                        "SHORT_MEDIUM_RESULT_CONFLICT",
                        true,
                        command,
                        result,
                        observedAt,
                        false);
            }
            return outcome(
                    "failed", "WRITING_RUN_FAILED", true, command, result, observedAt, false);
        }
        if ("completed".equals(facts.taskPhase()) && "succeeded".equals(commandStatus)) {
            String expected = "full_check".equals(facts.operation())
                    ? "check_report"
                    : "short_candidate";
            if (expected.equals(facts.resultKind()) && facts.resultReady()) {
                return outcome(
                        "succeeded",
                        "SHORT_MEDIUM_RESULT_READY",
                        true,
                        command,
                        result,
                        observedAt,
                        false);
            }
            return outcome(
                    "inconsistent",
                    "SHORT_MEDIUM_RESULT_MISSING",
                    true,
                    command,
                    result,
                    observedAt,
                    false);
        }
        return outcome(
                "inconsistent",
                "SHORT_MEDIUM_STATE_UNRESOLVED",
                terminal(facts.taskPhase()),
                command,
                result,
                observedAt,
                false);
    }

    private static WritingRunOutcome longForm(
            WritingRunOutcomeFacts facts,
            String commandStatus,
            WritingRunOutcomeCommand command,
            WritingRunOutcomeResult result,
            OffsetDateTime observedAt) {
        if (commandStatus == null && "completed".equals(facts.taskPhase())) {
            return outcome(
                    "succeeded",
                    "LEGACY_WRITING_RUN_SUCCEEDED",
                    true,
                    command,
                    result,
                    observedAt,
                    false);
        }
        if (commandStatus == null && "error".equals(facts.taskPhase())) {
            return outcome(
                    "failed",
                    "LEGACY_WRITING_RUN_FAILED",
                    true,
                    command,
                    result,
                    observedAt,
                    false);
        }
        if (Set.of("active", "waiting_call").contains(facts.taskPhase())
                && !activeCommand(commandStatus)) {
            // 旧任务可能没有当前命令；保持流开启并请求 reconciler 补建，而不是伪造完成或失败。
            return outcome(
                    "running",
                    "WRITING_RUN_RECONCILING",
                    false,
                    command,
                    result,
                    observedAt,
                    true);
        }
        if ("awaiting_user_review".equals(facts.taskPhase())) {
            if ((commandStatus == null || "succeeded".equals(commandStatus))
                    && "review_artifact".equals(facts.resultKind())
                    && facts.resultReady()) {
                return outcome(
                        "waiting_user",
                        "REVIEW_ARTIFACT_READY",
                        false,
                        command,
                        result,
                        observedAt,
                        false);
            }
            return outcome(
                    "inconsistent",
                    "AWAITING_REVIEW_ARTIFACT_MISSING",
                    false,
                    command,
                    result,
                    observedAt,
                    false);
        }
        if ("completed".equals(facts.taskPhase()) && "succeeded".equals(commandStatus)) {
            return outcome(
                    "succeeded", "WRITING_RUN_SUCCEEDED", true, command, result, observedAt, false);
        }
        if ("error".equals(facts.taskPhase()) && "failed".equals(commandStatus)) {
            return outcome(
                    "failed", "WRITING_RUN_FAILED", true, command, result, observedAt, false);
        }
        return outcome(
                "inconsistent",
                "WRITING_RUN_STATE_UNRESOLVED",
                terminal(facts.taskPhase()),
                command,
                result,
                observedAt,
                false);
    }

    private static boolean terminalConflict(String taskPhase, String commandStatus) {
        return ("completed".equals(taskPhase) && "failed".equals(commandStatus))
                || ("error".equals(taskPhase) && "succeeded".equals(commandStatus))
                || (terminal(taskPhase) && activeCommand(commandStatus));
    }

    private static WritingRunOutcomeCommand command(WritingRunOutcomeFacts facts) {
        if (facts.commandId() == null
                || facts.commandKind() == null
                || facts.commandStatus() == null
                || facts.commandUpdatedAt() == null) {
            return null;
        }
        return new WritingRunOutcomeCommand(
                facts.commandId(),
                facts.commandKind(),
                WritingRunOutcomeCommand.StatusEnum.fromValue(facts.commandStatus()),
                facts.commandUpdatedAt());
    }

    private static WritingRunOutcome outcome(
            String state,
            String code,
            boolean taskTerminal,
            WritingRunOutcomeCommand command,
            WritingRunOutcomeResult result,
            OffsetDateTime observedAt,
            boolean reconciliationRequired) {
        WritingRunOutcome.StateEnum stateEnum = WritingRunOutcome.StateEnum.fromValue(state);
        boolean inconsistent = stateEnum == WritingRunOutcome.StateEnum.INCONSISTENT;
        if (inconsistent && Boolean.TRUE.equals(result.getReady())) {
            // 不一致结果可以保留定位 ID 供诊断，但绝不能继续向用户暴露可应用能力。
            result = new WritingRunOutcomeResult(result.getKind(), false).id(result.getId());
        }
        boolean close = Set.of(
                        WritingRunOutcome.StateEnum.WAITING_USER,
                        WritingRunOutcome.StateEnum.SUCCEEDED,
                        WritingRunOutcome.StateEnum.FAILED,
                        WritingRunOutcome.StateEnum.CANCELLED,
                        WritingRunOutcome.StateEnum.INCONSISTENT)
                .contains(stateEnum);
        return new WritingRunOutcome(
                code,
                command,
                observedAt,
                inconsistent || reconciliationRequired,
                result,
                stateEnum,
                close,
                taskTerminal);
    }

    private static boolean terminal(String phase) {
        return Set.of("completed", "error").contains(phase);
    }

    private static boolean activeCommand(String status) {
        return status != null && ACTIVE_COMMANDS.contains(status);
    }
}
