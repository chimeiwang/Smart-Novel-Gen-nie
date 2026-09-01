package cn.inkforge.core.workflows.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.AwaitingUserEventPayload;
import cn.inkforge.contracts.api.RunSnapshot;
import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.contracts.api.WorkflowRunSnapshot;
import cn.inkforge.core.platform.http.ApiException;
import java.io.IOException;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class WorkflowEventStreamServiceTest {

    private final List<WorkflowEventTailObserver> observers = new CopyOnWriteArrayList<>();

    @AfterEach
    void closeObservers() {
        observers.forEach(WorkflowEventTailObserver::close);
    }

    @Test
    void 先发权威Snapshot且旧Cursor不重演随后补齐并发事件再关闭() throws Exception {
        RunSnapshot snapshot = snapshot("run-1", 2, "running");
        WorkflowEventEnvelope event = new WorkflowEventEnvelope(
                2,
                WorkflowEventEnvelope.EventTypeEnum.AWAITING_USER,
                OffsetDateTime.parse("2026-09-01T01:00:01Z"),
                new AwaitingUserEventPayload(
                        List.of(
                                AwaitingUserEventPayload.AllowedDecisionsEnum.APPROVE,
                                AwaitingUserEventPayload.AllowedDecisionsEnum.DISCARD,
                                AwaitingUserEventPayload.AllowedDecisionsEnum.REVISE),
                        "artifact-1",
                        1,
                        AwaitingUserEventPayload.ReviewAvailabilityEnum.COMPLETE),
                "2.0",
                "run-1",
                3);
        FakeRepository repository = new FakeRepository(
                Optional.of(new WorkflowEventStreamRepository.SnapshotRead(snapshot)),
                List.of(event),
                new WorkflowEventStreamRepository.TailState("waiting_user", 3));
        WorkflowEventStreamService service = service(repository);
        StringBuilder output = new StringBuilder();

        service.streamIfV2("user-1", "run-1", "1")
                .orElseThrow()
                .run(output::append);

        String text = output.toString();
        assertThat(text).startsWith("id: 2\nevent: run_snapshot\n");
        assertThat(text).contains("\"baseSequence\":2");
        assertThat(text).contains("id: 3\nevent: awaiting_user\n");
        assertThat(text).contains("\"protocolVersion\":\"2.0\"");
        assertThat(text).doesNotContain("id: 1\n");
        assertThat(repository.afterCalls).hasValue(1);
    }

    @Test
    void 零序Snapshot不写SseId且终态在对账后关闭() throws Exception {
        FakeRepository repository = new FakeRepository(
                Optional.of(new WorkflowEventStreamRepository.SnapshotRead(
                        snapshot("run-zero", 0, "completed"))),
                List.of(),
                new WorkflowEventStreamRepository.TailState("completed", 0));
        StringBuilder output = new StringBuilder();

        service(repository)
                .streamIfV2("user-1", "run-zero", null)
                .orElseThrow()
                .run(output::append);

        assertThat(output)
                .startsWith("event: run_snapshot\n")
                .doesNotContain("id: 0");
    }

    @Test
    void V2非法Cursor在返回流正文前稳定拒绝且V1Cursor不被V2解析() {
        for (String cursor : List.of("3-0", "-1", "4", " 2", "9223372036854775808")) {
            FakeRepository repository = new FakeRepository(
                    Optional.of(new WorkflowEventStreamRepository.SnapshotRead(
                            snapshot("run-1", 3, "running"))),
                    List.of(),
                    new WorkflowEventStreamRepository.TailState("running", 3));
            assertThatThrownBy(() -> service(repository)
                            .streamIfV2("user-1", "run-1", cursor))
                    .isInstanceOfSatisfying(ApiException.class, error -> {
                        assertThat(error.statusCode()).isEqualTo(409);
                        assertThat(error.code()).isEqualTo("WORKFLOW_CURSOR_INVALID");
                    });
            assertThat(repository.afterCalls).hasValue(0);
        }

        FakeRepository v1 = new FakeRepository(
                Optional.empty(),
                List.of(),
                new WorkflowEventStreamRepository.TailState("running", 0));
        assertThat(service(v1).streamIfV2("user-1", "v1-task", "3-0")).isEmpty();
    }

    @Test
    void 跨RunSnapshot必须在建立200流之前失败() {
        FakeRepository repository = new FakeRepository(
                Optional.of(new WorkflowEventStreamRepository.SnapshotRead(
                        snapshot("other-run", 0, "running"))),
                List.of(),
                new WorkflowEventStreamRepository.TailState("running", 0));

        assertThatThrownBy(() -> service(repository)
                        .streamIfV2("user-1", "expected-run", null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Run snapshot 不符合 V2 共享契约");
    }

    @Test
    void 跨Run持久事件必须关闭流而不能伪造进度() {
        WorkflowEventEnvelope other = new WorkflowEventEnvelope(
                2,
                WorkflowEventEnvelope.EventTypeEnum.AWAITING_USER,
                OffsetDateTime.parse("2026-09-01T01:00:01Z"),
                new AwaitingUserEventPayload(
                        List.of(AwaitingUserEventPayload.AllowedDecisionsEnum.APPROVE),
                        "artifact-1",
                        1,
                        AwaitingUserEventPayload.ReviewAvailabilityEnum.PARTIAL),
                "2.0",
                "other-run",
                2);
        FakeRepository repository = new FakeRepository(
                Optional.of(new WorkflowEventStreamRepository.SnapshotRead(
                        snapshot("run-1", 1, "running"))),
                List.of(other),
                new WorkflowEventStreamRepository.TailState("waiting_user", 2));
        var body = service(repository)
                .streamIfV2("user-1", "run-1", null)
                .orElseThrow();

        assertThatThrownBy(() -> body.run(ignored -> {}))
                .isInstanceOf(IOException.class)
                .hasMessageContaining("WORKFLOW_EVENT_TAIL_INCONSISTENT");
    }

    @Test
    void 持久事件序号缺口必须失败关闭而不是跳过事实() {
        WorkflowEventEnvelope gap = new WorkflowEventEnvelope(
                2,
                WorkflowEventEnvelope.EventTypeEnum.AWAITING_USER,
                OffsetDateTime.parse("2026-09-01T01:00:01Z"),
                new AwaitingUserEventPayload(
                        List.of(AwaitingUserEventPayload.AllowedDecisionsEnum.APPROVE),
                        "artifact-1",
                        1,
                        AwaitingUserEventPayload.ReviewAvailabilityEnum.PARTIAL),
                "2.0",
                "run-1",
                3);
        FakeRepository repository = new FakeRepository(
                Optional.of(new WorkflowEventStreamRepository.SnapshotRead(
                        snapshot("run-1", 1, "running"))),
                List.of(gap),
                new WorkflowEventStreamRepository.TailState("waiting_user", 3));
        var body = service(repository)
                .streamIfV2("user-1", "run-1", null)
                .orElseThrow();

        assertThatThrownBy(() -> body.run(ignored -> {}))
                .isInstanceOf(IOException.class)
                .hasMessageContaining("WORKFLOW_EVENT_TAIL_INCONSISTENT");
    }

    private WorkflowEventStreamService service(
            WorkflowEventStreamRepository repository) {
        WorkflowEventTailObserver observer = new WorkflowEventTailObserver(
                repository, Duration.ofMillis(1), 100, 16, 4, 4);
        observers.add(observer);
        return new WorkflowEventStreamService(
                repository,
                observer,
                JsonMapper.builder().build(),
                Duration.ofMillis(5));
    }

    private static RunSnapshot snapshot(String runId, int sequence, String status) {
        WorkflowRunSnapshot value = new WorkflowRunSnapshot(
                List.of(),
                sequence,
                1,
                WorkflowRunSnapshot.StatusEnum.fromValue(status),
                "long_serial");
        return new RunSnapshot(sequence, 2, "2.0", runId, value);
    }

    private static final class FakeRepository implements WorkflowEventStreamRepository {

        private final Optional<SnapshotRead> snapshot;
        private final List<WorkflowEventEnvelope> events;
        private final TailState tail;
        private final AtomicInteger afterCalls = new AtomicInteger();

        private FakeRepository(
                Optional<SnapshotRead> snapshot,
                List<WorkflowEventEnvelope> events,
                TailState tail) {
            this.snapshot = snapshot;
            this.events = events;
            this.tail = tail;
        }

        @Override
        public Optional<SnapshotRead> readSnapshot(String userId, String runId) {
            return snapshot;
        }

        @Override
        public Map<RunKey, TailState> readTails(List<RunKey> runs) {
            Map<RunKey, TailState> result = new LinkedHashMap<>();
            runs.forEach(run -> result.put(run, tail));
            return Map.copyOf(result);
        }

        @Override
        public Map<RunKey, List<WorkflowEventEnvelope>> readEventTails(
                List<EventTailRequest> requests, int limitPerRun) {
            afterCalls.incrementAndGet();
            Map<RunKey, List<WorkflowEventEnvelope>> result = new LinkedHashMap<>();
            requests.forEach(request -> result.put(request.key(), events));
            return Map.copyOf(result);
        }
    }
}
