package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.api.WritingRunListResponse;
import cn.inkforge.contracts.api.WritingRunOutcome;
import cn.inkforge.contracts.api.WritingRunOutcomeResult;
import cn.inkforge.contracts.api.WritingRunStatusPublicResponse;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.contracts.api.RunSnapshot;
import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.contracts.api.WorkflowRunSnapshot;
import cn.inkforge.core.writing.domain.WritingEvent;
import cn.inkforge.core.writing.domain.WritingOutboxHealth;
import cn.inkforge.core.writing.domain.WritingOutboxRecord;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository;
import java.io.ByteArrayOutputStream;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class WritingEventStreamServiceTest {

    @Test
    void V2按持久身份委托PostgreSQL流且没有Redis也不回退V1() throws Exception {
        WritingRunQueryRepository queries = new WritingRunQueryRepository() {
            @Override
            public WritingRunStatusResponse get(String userId, String taskId) {
                throw new AssertionError("V2 不得回退读取 V1 WritingTask");
            }

            @Override
            public WritingRunStatusPublicResponse getPublic(String userId, String taskId) {
                throw new UnsupportedOperationException();
            }

            @Override
            public WritingRunListResponse list(
                    String a, String b, String c, String d, String e, String f, String g, int h) {
                throw new UnsupportedOperationException();
            }
        };
        WorkflowRunSnapshot state = new WorkflowRunSnapshot(
                List.of(), 0, 1, WorkflowRunSnapshot.StatusEnum.COMPLETED, "long_serial");
        RunSnapshot snapshot = new RunSnapshot(0, 2, "2.0", "run-v2", state);
        WorkflowEventStreamRepository repository = new WorkflowEventStreamRepository() {
            @Override
            public java.util.Optional<SnapshotRead> readSnapshot(
                    String userId, String runId) {
                return java.util.Optional.of(new SnapshotRead(snapshot));
            }

            @Override
            public Map<RunKey, TailState> readTails(List<RunKey> runs) {
                return Map.of(runs.getFirst(), new TailState("completed", 0));
            }

            @Override
            public Map<RunKey, List<WorkflowEventEnvelope>> readEventTails(
                    List<EventTailRequest> requests, int limitPerRun) {
                return Map.of();
            }
        };
        try (var observer =
                new cn.inkforge.core.workflows.application.WorkflowEventTailObserver(
                        repository,
                        Duration.ofMillis(1),
                        100,
                        16,
                        4,
                        4)) {
            var workflowStreams =
                    new cn.inkforge.core.workflows.application.WorkflowEventStreamService(
                            repository,
                            observer,
                            JsonMapper.builder().build(),
                            Duration.ofMillis(5));
            WritingEventStreamService service = new WritingEventStreamService(
                    queries,
                    null,
                    new NoopOutboxRepository(),
                    JsonMapper.builder().build(),
                    Duration.ofMillis(1),
                    Duration.ofMillis(5),
                    workflowStreams);
            ByteArrayOutputStream output = new ByteArrayOutputStream();

            service.stream("user-1", "run-v2", null).writeTo(output);

            assertThat(output.toString(java.nio.charset.StandardCharsets.UTF_8))
                    .startsWith("event: run_snapshot\n")
                    .contains("\"engineVersion\":2");
        }
    }

    @Test
    void 终态连接必须先发统一结果再按Outbox可见性回放并关闭() throws Exception {
        WritingRunStatusResponse status = new WritingRunStatusResponse();
        status.setOutcome(new WritingRunOutcome(
                "WRITING_RUN_SUCCEEDED",
                null,
                OffsetDateTime.parse("2026-08-25T12:00:00Z"),
                false,
                new WritingRunOutcomeResult(
                        WritingRunOutcomeResult.KindEnum.FINAL_MESSAGE, true),
                WritingRunOutcome.StateEnum.SUCCEEDED,
                true,
                true));
        WritingRunQueryRepository queries = new WritingRunQueryRepository() {
            @Override
            public WritingRunStatusResponse get(String userId, String taskId) {
                return status;
            }

            @Override
            public WritingRunStatusPublicResponse getPublic(String userId, String taskId) {
                return status;
            }

            @Override
            public WritingRunListResponse list(String a, String b, String c, String d, String e, String f, String g, int h) {
                throw new UnsupportedOperationException();
            }
        };
        List<WritingEvent> values = List.of(
                event("1-0", "completed"),
                event("2-0", "artifact_awaiting_user_approval"));
        WritingEventStore events = new FixedEventStore(values);
        WritingOutboxRepository outbox = new NoopOutboxRepository() {
            @Override
            public Map<String, String> replayDispositions(List<WritingEvent> events) {
                return Map.of("1-0", "emit", "2-0", "skip");
            }
        };
        WritingEventStreamService service = new WritingEventStreamService(
                queries,
                events,
                outbox,
                JsonMapper.builder().build(),
                Duration.ofMillis(1),
                Duration.ofMillis(5));
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        service.stream("user-1", "task-1", null).writeTo(output);

        String text = output.toString(java.nio.charset.StandardCharsets.UTF_8);
        assertThat(text).startsWith("event: run_outcome\n");
        assertThat(text).contains("id: 1-0\nevent: completed\n");
        assertThat(text).doesNotContain("id: 2-0");
        assertThat(count(text, "event: run_outcome")).isEqualTo(2);
    }

    private static WritingEvent event(String id, String type) {
        return new WritingEvent(
                id,
                type,
                Map.of("taskId", "task-1"),
                OffsetDateTime.now(ZoneOffset.UTC),
                "source-" + id,
                Integer.parseInt(id.substring(0, 1)));
    }

    private static int count(String value, String needle) {
        return (value.length() - value.replace(needle, "").length()) / needle.length();
    }

    private record FixedEventStore(List<WritingEvent> values) implements WritingEventStore {

        @Override
        public List<WritingEvent> replay(String taskId, String lastEventId) {
            return values;
        }

        @Override
        public boolean validateSource(String a, String b, int c, String d, Map<String, Object> e) {
            return true;
        }

        @Override
        public boolean validate(String a, String b, int c, String d, Map<String, Object> e, int f, boolean g) {
            return true;
        }

        @Override
        public WritingEvent appendAgent(String a, String b, int c, String d, Map<String, Object> e, int f, boolean g) {
            throw new UnsupportedOperationException();
        }
    }

    private static class NoopOutboxRepository implements WritingOutboxRepository {

        @Override
        public List<WritingOutboxRecord> claimDue(LocalDateTime now, int limit, int leaseSeconds) {
            return List.of();
        }

        @Override
        public boolean markPublished(String a, String b, String c) { return false; }

        @Override
        public boolean scheduleRetry(String a, String b, LocalDateTime c, String d) { return false; }

        @Override
        public boolean markBlocked(String a, String b, String c) { return false; }

        @Override
        public boolean supersedeWaitingIfStale(String a, String b, LocalDateTime c) { return false; }

        @Override
        public int cleanupTerminal(LocalDateTime olderThan) { return 0; }

        @Override
        public WritingOutboxHealth health(LocalDateTime now, Duration staleAfter) {
            return new WritingOutboxHealth(0, 0);
        }

        @Override
        public Map<String, String> replayDispositions(List<WritingEvent> events) {
            return Map.of();
        }
    }
}
