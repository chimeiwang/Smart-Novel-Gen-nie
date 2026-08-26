package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WritingRunCommandDispatcherTest {

    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T08:00:00Z"), ZoneOffset.UTC);

    @Test
    void 一条暂时失败不能阻断同批写作命令() {
        RecordingRepository repository = new RecordingRepository(List.of(
                record("command-bad", "start"), record("command-good", "resume")));
        RecordingSubmitter submitter = new RecordingSubmitter();
        submitter.failures.put(
                "command-bad", new WritingSubmissionException("AGENT_UNAVAILABLE"));
        WritingRunCommandDispatcher dispatcher = dispatcher(repository, submitter);

        assertThat(dispatcher.runOnce()).isEqualTo(1);
        assertThat(submitter.submitted).containsExactly("command-bad", "command-good");
        assertThat(repository.active).containsExactly("command-good");
        assertThat(repository.failures)
                .containsExactly(Map.entry("command-bad", "AGENT_UNAVAILABLE"));
    }

    @Test
    void 取消和Agent终态必须进入各自结算路径() {
        RecordingRepository repository = new RecordingRepository(List.of(
                record("command-cancel", "cancel"), record("command-terminal", "start")));
        RecordingSubmitter submitter = new RecordingSubmitter();
        submitter.statuses.put("command-terminal", WritingAgentJobStatus.COMPLETED);
        WritingRunCommandDispatcher dispatcher = dispatcher(repository, submitter);

        assertThat(dispatcher.runOnce()).isEqualTo(2);
        assertThat(submitter.cancelled).containsExactly("command-cancel");
        assertThat(repository.cancelSettled).containsExactly("command-cancel");
        assertThat(repository.terminalSettled)
                .containsExactly(Map.entry("command-terminal", WritingAgentJobStatus.COMPLETED));
        assertThat(repository.active).isEmpty();
    }

    @Test
    void 确定性载荷错误必须记录后交给后台监督器() {
        RecordingRepository repository =
                new RecordingRepository(List.of(record("command-invalid", "start")));
        WritingCommandSubmitter submitter = new WritingCommandSubmitter() {
            @Override
            public WritingAgentJobStatus submit(WritingDispatchRecord command) {
                throw new IllegalArgumentException("写作 job 无效");
            }

            @Override
            public void cancel(WritingDispatchRecord command) {}
        };
        WritingRunCommandDispatcher dispatcher = dispatcher(repository, submitter);

        assertThatThrownBy(dispatcher::runOnce)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("写作 job 无效");
        assertThat(repository.failures)
                .containsExactly(Map.entry("command-invalid", "IllegalArgumentException"));
    }

    private static WritingRunCommandDispatcher dispatcher(
            WritingCommandDispatchRepository repository,
            WritingCommandSubmitter submitter) {
        return new WritingRunCommandDispatcher(
                repository,
                submitter,
                CLOCK,
                20,
                Duration.ofMillis(10),
                Duration.ofMinutes(10));
    }

    private static WritingDispatchRecord record(String id, String kind) {
        Map<String, Object> job = "cancel".equals(kind)
                ? mapWithNullable("cancelledJobId", "source-command")
                : Map.of("resume", false);
        return new WritingDispatchRecord(
                id,
                "task-1",
                "user-1",
                "novel-1",
                "chapter-1",
                null,
                "active",
                null,
                kind,
                job,
                "pending",
                0,
                null,
                null);
    }

    private static Map<String, Object> mapWithNullable(String key, Object value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(key, value);
        return result;
    }

    private static final class RecordingSubmitter implements WritingCommandSubmitter {

        private final List<String> submitted = new ArrayList<>();
        private final List<String> cancelled = new ArrayList<>();
        private final Map<String, RuntimeException> failures = new LinkedHashMap<>();
        private final Map<String, WritingAgentJobStatus> statuses = new LinkedHashMap<>();

        @Override
        public WritingAgentJobStatus submit(WritingDispatchRecord command) {
            submitted.add(command.id());
            RuntimeException failure = failures.get(command.id());
            if (failure != null) throw failure;
            return statuses.getOrDefault(command.id(), WritingAgentJobStatus.QUEUED);
        }

        @Override
        public void cancel(WritingDispatchRecord command) {
            cancelled.add(command.id());
        }
    }

    private static final class RecordingRepository
            implements WritingCommandDispatchRepository {

        private final List<WritingDispatchRecord> records;
        private final List<String> active = new ArrayList<>();
        private final List<String> cancelSettled = new ArrayList<>();
        private final List<Map.Entry<String, WritingAgentJobStatus>> terminalSettled =
                new ArrayList<>();
        private final List<Map.Entry<String, String>> failures = new ArrayList<>();

        private RecordingRepository(List<WritingDispatchRecord> records) {
            this.records = records;
        }

        @Override
        public List<WritingDispatchRecord> claimDue(
                int limit, LocalDateTime activeStaleBefore) {
            return records.stream().limit(limit).toList();
        }

        @Override
        public WritingDispatchRecord markAgentActive(String commandId) {
            active.add(commandId);
            return byId(commandId);
        }

        @Override
        public WritingDispatchRecord settleDispatchTerminal(
                String commandId, WritingAgentJobStatus agentStatus) {
            terminalSettled.add(Map.entry(commandId, agentStatus));
            return byId(commandId);
        }

        @Override
        public WritingDispatchRecord settleCancelDispatch(String commandId) {
            cancelSettled.add(commandId);
            return byId(commandId);
        }

        @Override
        public WritingDispatchRecord recordDispatchFailure(
                String commandId, String errorCode) {
            failures.add(Map.entry(commandId, errorCode));
            return byId(commandId);
        }

        private WritingDispatchRecord byId(String id) {
            return records.stream()
                    .filter(record -> record.id().equals(id))
                    .findFirst()
                    .orElseThrow();
        }
    }
}
