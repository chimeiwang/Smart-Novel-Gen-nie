package cn.inkforge.core.quality.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import cn.inkforge.core.quality.domain.QualityDispatchStatus;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class QualityRunDispatcherTest {

    @Test
    void 必须复用WorkflowRun身份且一条暂时失败不能阻断同批任务() {
        RecordingRepository repository = new RecordingRepository(List.of(
                record("run-bad"), record("run-good")));
        RecordingSubmitter submitter = new RecordingSubmitter();
        submitter.failures.put("run-bad", new QualitySubmissionException("AGENT_UNAVAILABLE"));
        QualityRunDispatcher dispatcher = new QualityRunDispatcher(
                repository, submitter, 20, Duration.ofMillis(10));

        assertThat(dispatcher.runOnce()).isEqualTo(1);
        assertThat(submitter.runIds).containsExactly("run-bad", "run-good");
        assertThat(repository.running).containsExactly("run-good");
        assertThat(repository.dispatchFailures)
                .containsExactly(Map.entry("run-bad", "AGENT_UNAVAILABLE"));
    }

    @Test
    void 确定性投递错误必须记录后抛给后台监督器() {
        RecordingRepository repository = new RecordingRepository(List.of(record("run-invalid")));
        QualityRunSubmitter submitter = ignored -> {
            throw new IllegalArgumentException("质量任务契约无效");
        };
        QualityRunDispatcher dispatcher = new QualityRunDispatcher(
                repository, submitter, 20, Duration.ofMillis(10));

        assertThatThrownBy(dispatcher::runOnce)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("质量任务契约无效");
        assertThat(repository.dispatchFailures)
                .containsExactly(Map.entry("run-invalid", "IllegalArgumentException"));
    }

    @Test
    void Agent已经终态时必须收敛运行而不能误标为running() {
        RecordingRepository repository = new RecordingRepository(List.of(record("run-terminal")));
        RecordingSubmitter submitter = new RecordingSubmitter();
        submitter.statuses.put("run-terminal", QualityDispatchStatus.COMPLETED);
        QualityRunDispatcher dispatcher = new QualityRunDispatcher(
                repository, submitter, 20, Duration.ofMillis(10));

        assertThat(dispatcher.runOnce()).isEqualTo(1);
        assertThat(repository.running).isEmpty();
        assertThat(repository.failedRuns).containsExactly("run-terminal");
    }

    private static QualityDispatchRecord record(String runId) {
        return new QualityDispatchRecord(
                runId,
                "check-1",
                "user-1",
                "novel-1",
                "chapter-1",
                "source-task-1",
                "检查时间线");
    }

    private static final class RecordingSubmitter implements QualityRunSubmitter {

        private final List<String> runIds = new ArrayList<>();
        private final Map<String, RuntimeException> failures = new LinkedHashMap<>();
        private final Map<String, QualityDispatchStatus> statuses = new LinkedHashMap<>();

        @Override
        public QualityDispatchStatus submit(QualityDispatchRecord record) {
            runIds.add(record.runId());
            RuntimeException failure = failures.get(record.runId());
            if (failure != null) throw failure;
            return statuses.getOrDefault(record.runId(), QualityDispatchStatus.QUEUED);
        }
    }

    private static final class RecordingRepository implements QualityDispatchRepository {

        private final List<QualityDispatchRecord> records;
        private final List<String> running = new ArrayList<>();
        private final List<Map.Entry<String, String>> dispatchFailures = new ArrayList<>();
        private final List<String> failedRuns = new ArrayList<>();

        private RecordingRepository(List<QualityDispatchRecord> records) {
            this.records = records;
        }

        @Override
        public List<QualityDispatchRecord> listDispatchable(int limit) {
            return records.stream().limit(limit).toList();
        }

        @Override
        public void markRunning(String runId) {
            running.add(runId);
        }

        @Override
        public void recordDispatchFailure(String runId, String errorCode) {
            dispatchFailures.add(Map.entry(runId, errorCode));
        }

        @Override
        public void failRun(String userId, String checkId, String runId, String novelId) {
            failedRuns.add(runId);
        }
    }
}
