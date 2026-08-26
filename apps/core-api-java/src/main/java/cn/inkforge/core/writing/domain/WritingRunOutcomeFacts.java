package cn.inkforge.core.writing.domain;

import java.time.OffsetDateTime;

/** 从 PostgreSQL 权威事实投影写作结果所需的最小输入。 */
public record WritingRunOutcomeFacts(
        String taskPhase,
        OffsetDateTime taskUpdatedAt,
        String workflow,
        String commandId,
        String commandKind,
        String commandStatus,
        OffsetDateTime commandUpdatedAt,
        String operation,
        String resultKind,
        String resultId,
        boolean resultReady,
        String effectiveCommandStatus,
        Boolean cancelEffective,
        boolean cancelChainValid) {

    public WritingRunOutcomeFacts withWorkflow(String value) {
        return copy(taskPhase, value, commandId, commandKind, commandStatus, operation,
                resultKind, resultId, resultReady, effectiveCommandStatus,
                cancelEffective, cancelChainValid);
    }

    public WritingRunOutcomeFacts withoutCommand() {
        return new WritingRunOutcomeFacts(
                taskPhase, taskUpdatedAt, workflow, null, null, null, null, operation,
                resultKind, resultId, resultReady, effectiveCommandStatus,
                cancelEffective, cancelChainValid);
    }

    public WritingRunOutcomeFacts withOperation(String value) {
        return copy(taskPhase, workflow, commandId, commandKind, commandStatus, value,
                resultKind, resultId, resultReady, effectiveCommandStatus,
                cancelEffective, cancelChainValid);
    }

    public WritingRunOutcomeFacts withResult(String kind, String id, boolean ready) {
        return copy(taskPhase, workflow, commandId, commandKind, commandStatus, operation,
                kind, id, ready, effectiveCommandStatus, cancelEffective, cancelChainValid);
    }

    public WritingRunOutcomeFacts withCommandKind(String value) {
        return copy(taskPhase, workflow, commandId, value, commandStatus, operation,
                resultKind, resultId, resultReady, effectiveCommandStatus,
                cancelEffective, cancelChainValid);
    }

    public WritingRunOutcomeFacts withCommand(String id, String kind, String status) {
        return copy(taskPhase, workflow, id, kind, status, operation,
                resultKind, resultId, resultReady, effectiveCommandStatus,
                cancelEffective, cancelChainValid);
    }

    public WritingRunOutcomeFacts withEffectiveCommandStatus(String value) {
        return copy(taskPhase, workflow, commandId, commandKind, commandStatus, operation,
                resultKind, resultId, resultReady, value, cancelEffective, cancelChainValid);
    }

    public WritingRunOutcomeFacts withCancel(Boolean effective, boolean chainValid) {
        return copy(taskPhase, workflow, commandId, commandKind, commandStatus, operation,
                resultKind, resultId, resultReady, effectiveCommandStatus, effective, chainValid);
    }

    public WritingRunOutcomeFacts withCommandStatus(String value) {
        return copy(taskPhase, workflow, commandId, commandKind, value, operation,
                resultKind, resultId, resultReady, effectiveCommandStatus,
                cancelEffective, cancelChainValid);
    }

    private WritingRunOutcomeFacts copy(
            String phase,
            String workflowValue,
            String commandIdValue,
            String commandKindValue,
            String commandStatusValue,
            String operationValue,
            String resultKindValue,
            String resultIdValue,
            boolean resultReadyValue,
            String effectiveCommandStatusValue,
            Boolean cancelEffectiveValue,
            boolean cancelChainValidValue) {
        return new WritingRunOutcomeFacts(
                phase,
                taskUpdatedAt,
                workflowValue,
                commandIdValue,
                commandKindValue,
                commandStatusValue,
                commandIdValue == null ? null : commandUpdatedAt,
                operationValue,
                resultKindValue,
                resultIdValue,
                resultReadyValue,
                effectiveCommandStatusValue,
                cancelEffectiveValue,
                cancelChainValidValue);
    }
}
