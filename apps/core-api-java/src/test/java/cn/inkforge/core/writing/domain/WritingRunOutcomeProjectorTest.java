package cn.inkforge.core.writing.domain;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.api.WritingRunOutcome;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class WritingRunOutcomeProjectorTest {

    private static final OffsetDateTime NOW =
            OffsetDateTime.of(2026, 8, 1, 12, 0, 0, 0, ZoneOffset.UTC);

    @Test
    void 中短篇成功必须存在对应候选或检查报告() {
        WritingRunOutcome queued = project(facts("active", "short_medium", "pending"));
        WritingRunOutcome running = project(facts("active", "short_medium", "processing"));
        WritingRunOutcome succeeded = project(facts("completed", "short_medium", "succeeded")
                .withOperation("generate_outline")
                .withResult("short_candidate", "candidate-1", true));
        WritingRunOutcome missing = project(facts("completed", "short_medium", "succeeded")
                .withOperation("generate_outline")
                .withResult("short_candidate", "candidate-1", false));
        WritingRunOutcome check = project(facts("completed", "short_medium", "succeeded")
                .withOperation("full_check")
                .withResult("check_report", "command-1", true));

        assertThat(queued.getState()).isEqualTo(WritingRunOutcome.StateEnum.QUEUED);
        assertThat(queued.getStreamShouldClose()).isFalse();
        assertThat(running.getState()).isEqualTo(WritingRunOutcome.StateEnum.RUNNING);
        assertThat(succeeded.getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(succeeded.getResult().getReady()).isTrue();
        assertThat(missing.getState()).isEqualTo(WritingRunOutcome.StateEnum.INCONSISTENT);
        assertThat(missing.getCode()).isEqualTo("SHORT_MEDIUM_RESULT_MISSING");
        assertThat(missing.getReconciliationRequired()).isTrue();
        assertThat(check.getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
    }

    @Test
    void 长篇等待用户审核不是任务终态但流应关闭() {
        WritingRunOutcome outcome = project(facts("awaiting_user_review", "long_form", "succeeded")
                .withResult("review_artifact", "artifact-1", true));

        assertThat(outcome.getState()).isEqualTo(WritingRunOutcome.StateEnum.WAITING_USER);
        assertThat(outcome.getTaskTerminal()).isFalse();
        assertThat(outcome.getStreamShouldClose()).isTrue();
    }

    @ParameterizedTest
    @MethodSource("terminalConflicts")
    void 任务与命令终态冲突必须显式不一致(String phase, String commandStatus) {
        WritingRunOutcome outcome = project(facts(phase, "long_form", commandStatus));

        assertThat(outcome.getState()).isEqualTo(WritingRunOutcome.StateEnum.INCONSISTENT);
        assertThat(outcome.getCode()).isEqualTo("TASK_COMMAND_TERMINAL_CONFLICT");
        assertThat(outcome.getStreamShouldClose()).isTrue();
    }

    @Test
    void 一致的长篇终态收敛为成功或失败() {
        WritingRunOutcome succeeded = project(facts("completed", "long_form", "succeeded")
                .withResult("final_message", "message-1", true));
        WritingRunOutcome failed = project(facts("error", "long_form", "failed"));

        assertThat(succeeded.getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(succeeded.getTaskTerminal()).isTrue();
        assertThat(failed.getState()).isEqualTo(WritingRunOutcome.StateEnum.FAILED);
        assertThat(failed.getTaskTerminal()).isTrue();
    }

    @Test
    void 只有长篇活动任务可以在缺少命令时等待对账() {
        WritingRunOutcomeFacts withoutCommand = facts("active", "long_form", null)
                .withoutCommand();
        WritingRunOutcome longForm = project(withoutCommand);
        WritingRunOutcome shortMedium = project(withoutCommand.withWorkflow("short_medium"));

        assertThat(longForm.getState()).isEqualTo(WritingRunOutcome.StateEnum.RUNNING);
        assertThat(longForm.getCode()).isEqualTo("WRITING_RUN_RECONCILING");
        assertThat(longForm.getReconciliationRequired()).isTrue();
        assertThat(longForm.getStreamShouldClose()).isFalse();
        assertThat(shortMedium.getState()).isEqualTo(WritingRunOutcome.StateEnum.INCONSISTENT);
        assertThat(shortMedium.getStreamShouldClose()).isTrue();
    }

    @ParameterizedTest
    @MethodSource("nonTerminalReconciliation")
    void 长篇非终态在最新命令已终态后继续对账(String phase, String commandStatus) {
        WritingRunOutcome outcome = project(facts(phase, "long_form", commandStatus));

        assertThat(outcome.getState()).isEqualTo(WritingRunOutcome.StateEnum.RUNNING);
        assertThat(outcome.getCode()).isEqualTo("WRITING_RUN_RECONCILING");
        assertThat(outcome.getReconciliationRequired()).isTrue();
        assertThat(outcome.getStreamShouldClose()).isFalse();
    }

    @Test
    void 不一致结果绝不能暴露为可用() {
        WritingRunOutcome outcome = project(facts("completed", "short_medium", "failed")
                .withResult("short_candidate", "candidate-1", true));

        assertThat(outcome.getState()).isEqualTo(WritingRunOutcome.StateEnum.INCONSISTENT);
        assertThat(outcome.getResult().getId()).isEqualTo("candidate-1");
        assertThat(outcome.getResult().getReady()).isFalse();
    }

    @Test
    void 兼容旧长篇无命令的等待与终态语义() {
        WritingRunOutcome waiting = project(facts("awaiting_user_review", "long_form", null)
                .withoutCommand()
                .withResult("review_artifact", "artifact-1", true));
        WritingRunOutcome succeeded = project(facts("completed", "long_form", null).withoutCommand());
        WritingRunOutcome failed = project(facts("error", "long_form", null).withoutCommand());

        assertThat(waiting.getState()).isEqualTo(WritingRunOutcome.StateEnum.WAITING_USER);
        assertThat(succeeded.getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(failed.getState()).isEqualTo(WritingRunOutcome.StateEnum.FAILED);
    }

    @Test
    void 有效取消覆盖其他状态并成为终态() {
        WritingRunOutcome outcome = project(facts("error", "long_form", "succeeded")
                .withCommandKind("cancel")
                .withCancel(true, true));

        assertThat(outcome.getState()).isEqualTo(WritingRunOutcome.StateEnum.CANCELLED);
        assertThat(outcome.getTaskTerminal()).isTrue();
        assertThat(outcome.getStreamShouldClose()).isTrue();
        assertThat(outcome.getReconciliationRequired()).isFalse();
    }

    @Test
    void 无效取消链不允许伪造前序结果() {
        WritingRunOutcome outcome = project(facts("completed", "long_form", "succeeded")
                .withCommandKind("cancel")
                .withCancel(false, false)
                .withResult("final_message", "message-1", true));

        assertThat(outcome.getState()).isEqualTo(WritingRunOutcome.StateEnum.INCONSISTENT);
        assertThat(outcome.getCode()).isEqualTo("CANCEL_PRIOR_OUTCOME_INVALID");
        assertThat(outcome.getResult().getReady()).isFalse();
    }

    @Test
    void 终态空操作取消保留前序成功但展示当前取消命令() {
        WritingRunOutcome outcome = project(facts("completed", "long_form", "succeeded")
                .withCommand("cancel-2", "cancel", "succeeded")
                .withEffectiveCommandStatus("succeeded")
                .withCancel(false, true)
                .withResult("final_message", "message-1", true));

        assertThat(outcome.getState()).isEqualTo(WritingRunOutcome.StateEnum.SUCCEEDED);
        assertThat(outcome.getCurrentCommand().getId()).isEqualTo("cancel-2");
        assertThat(outcome.getResult().getReady()).isTrue();
    }

    private static WritingRunOutcome project(WritingRunOutcomeFacts facts) {
        return new WritingRunOutcomeProjector().project(facts, NOW);
    }

    private static WritingRunOutcomeFacts facts(
            String phase, String workflow, String commandStatus) {
        return new WritingRunOutcomeFacts(
                phase,
                NOW,
                workflow,
                "command-1",
                "start",
                commandStatus,
                NOW,
                null,
                "none",
                null,
                false,
                null,
                null,
                true);
    }

    private static Stream<Arguments> terminalConflicts() {
        return Stream.of(
                Arguments.of("completed", "failed"),
                Arguments.of("error", "succeeded"),
                Arguments.of("completed", "processing"));
    }

    private static Stream<Arguments> nonTerminalReconciliation() {
        return Stream.of(
                Arguments.of("active", "succeeded"),
                Arguments.of("active", "failed"),
                Arguments.of("waiting_call", "succeeded"),
                Arguments.of("waiting_call", "failed"));
    }
}
