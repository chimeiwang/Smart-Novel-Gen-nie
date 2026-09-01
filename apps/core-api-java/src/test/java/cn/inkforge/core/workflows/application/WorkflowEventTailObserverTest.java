package cn.inkforge.core.workflows.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.AwaitingUserEventPayload;
import cn.inkforge.contracts.api.RunSnapshot;
import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.contracts.api.WorkflowRunSnapshot;
import cn.inkforge.core.platform.http.ApiException;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.AbstractMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import tools.jackson.databind.json.JsonMapper;

class WorkflowEventTailObserverTest {

    private static final Duration WAIT = Duration.ofSeconds(3);

    @Test
    void 同一Run多连接共享一次高水位变化后的EventTail查询() throws Exception {
        ControlledRepository repository = new ControlledRepository();
        var key = new WorkflowEventStreamRepository.RunKey("user-1", "run-1");
        repository.put(key, "running", 0);
        try (var observer = observer(repository, 100, 8, 4, 4);
                var first = observer.subscribe(key.userId(), key.runId(), 0).activate();
                var second = observer.subscribe(key.userId(), key.runId(), 0).activate()) {
            awaitTail(first);
            awaitTail(second);
            int eventQueries = repository.eventTailCalls.get();

            repository.publish(key, event(key.runId(), 1), "waiting_user");
            observer.wake();

            assertThat(awaitEvent(first).events()).extracting(WorkflowEventEnvelope::getSequence)
                    .containsExactly(1);
            assertThat(awaitEvent(second).events()).extracting(WorkflowEventEnvelope::getSequence)
                    .containsExactly(1);
            assertThat(repository.eventTailCalls.get() - eventQueries).isEqualTo(1);
            assertThat(repository.eventTailBatches.getLast()).containsExactly(key);
        }
    }

    @Test
    void 不同Run在同一批次各推进一页且不会被热点Run饿死() throws Exception {
        ControlledRepository repository = new ControlledRepository();
        var hot = new WorkflowEventStreamRepository.RunKey("user-1", "run-hot");
        var quiet = new WorkflowEventStreamRepository.RunKey("user-2", "run-quiet");
        repository.put(hot, "running", 0);
        repository.put(quiet, "running", 0);
        try (var observer = observer(repository, 1, 8, 4, 4);
                var hotSubscription = observer.subscribe(hot.userId(), hot.runId(), 0).activate();
                var quietSubscription = observer.subscribe(quiet.userId(), quiet.runId(), 0).activate()) {
            awaitTail(hotSubscription);
            awaitTail(quietSubscription);
            repository.publish(hot, event(hot.runId(), 1), "running");
            repository.publish(hot, event(hot.runId(), 2), "running");
            repository.publish(hot, event(hot.runId(), 3), "running");
            repository.publish(quiet, event(quiet.runId(), 1), "waiting_user");
            observer.wake();

            assertThat(awaitEvent(hotSubscription).events()).extracting(WorkflowEventEnvelope::getSequence)
                    .containsExactly(1);
            assertThat(awaitEvent(quietSubscription).events()).extracting(WorkflowEventEnvelope::getSequence)
                    .containsExactly(1);
            assertThat(repository.eventTailBatches)
                    .anySatisfy(batch -> assertThat(batch).containsExactlyInAnyOrder(hot, quiet));
        }
    }

    @Test
    void 共享Cursor回拨时旧连接过滤已发送前缀且新连接连续补齐() throws Exception {
        ControlledRepository repository = new ControlledRepository();
        var key = new WorkflowEventStreamRepository.RunKey("user-1", "run-rewind");
        repository.put(key, "running", 0);
        try (var observer = observer(repository, 1, 8, 4, 1);
                var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            WorkflowEventStreamService service = new WorkflowEventStreamService(
                    repository, observer, JsonMapper.builder().build(), Duration.ofSeconds(1));
            RecordingOutputStream firstOutput = new RecordingOutputStream();
            StreamingResponseBody firstBody = service.streamIfV2(
                            key.userId(), key.runId(), null)
                    .orElseThrow();
            Future<?> first = executor.submit(() -> write(firstBody, firstOutput));

            repository.publish(key, event(key.runId(), 1), "running");
            observer.wake();
            await(() -> firstOutput.text().contains("id: 1\n"));
            repository.publish(key, event(key.runId(), 2), "running");
            observer.wake();
            await(() -> firstOutput.text().contains("id: 2\n"));

            // 模拟 snapshot 与订阅注册之间跨过有界历史：第二条连接从更早 base 触发共享重读。
            repository.snapshotSequence.set(0);
            RecordingOutputStream secondOutput = new RecordingOutputStream();
            StreamingResponseBody secondBody = service.streamIfV2(
                            key.userId(), key.runId(), "0")
                    .orElseThrow();
            Future<?> second = executor.submit(() -> write(secondBody, secondOutput));
            await(() -> secondOutput.text().contains("id: 2\n"));

            repository.publish(key, event(key.runId(), 3), "waiting_user");
            observer.wake();
            first.get(WAIT.toMillis(), TimeUnit.MILLISECONDS);
            second.get(WAIT.toMillis(), TimeUnit.MILLISECONDS);

            assertThat(count(firstOutput.text(), "id: 1\n")).isEqualTo(1);
            assertThat(count(firstOutput.text(), "id: 2\n")).isEqualTo(1);
            assertThat(count(firstOutput.text(), "id: 3\n")).isEqualTo(1);
            assertThat(count(secondOutput.text(), "id: 1\n")).isEqualTo(1);
            assertThat(count(secondOutput.text(), "id: 2\n")).isEqualTo(1);
            assertThat(count(secondOutput.text(), "id: 3\n")).isEqualTo(1);
            await(() -> observer.activeConnectionCount() == 0 && observer.activeRunCount() == 0);
            int stoppedTailCalls = repository.tailCalls.get();
            Thread.sleep(30);
            assertThat(repository.tailCalls).hasValue(stoppedTailCalls);
        }
    }

    @Test
    void 连接上限慢消费者和输出断线都会立即注销() throws Exception {
        ControlledRepository repository = new ControlledRepository();
        assertThatThrownBy(() -> observer(repository, 1_000, 2, 1, 65))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Workflow SSE 共享观察配置无效");
        var key = new WorkflowEventStreamRepository.RunKey("user-1", "run-limits");
        var secondKey = new WorkflowEventStreamRepository.RunKey("user-2", "run-limits-2");
        repository.put(key, "running", 0);
        repository.put(secondKey, "running", 0);
        try (var observer = observer(repository, 1, 2, 1, 1);
                var accepted = observer.subscribe(key.userId(), key.runId(), 0).activate()) {
            assertThatThrownBy(() -> observer.subscribe(key.userId(), "run-other", 0))
                    .isInstanceOfSatisfying(ApiException.class, error -> {
                        assertThat(error.statusCode()).isEqualTo(429);
                        assertThat(error.code()).isEqualTo("WORKFLOW_STREAM_LIMIT_EXCEEDED");
                    });
            try (var second = observer.subscribe(secondKey.userId(), secondKey.runId(), 0)) {
                assertThatThrownBy(() -> observer.subscribe("user-3", "run-third", 0))
                        .isInstanceOfSatisfying(ApiException.class, error ->
                                assertThat(error.code())
                                        .isEqualTo("WORKFLOW_STREAM_LIMIT_EXCEEDED"));
            }
            repository.publish(key, event(key.runId(), 1), "running");
            observer.wake();
            await(() -> observer.activeConnectionCount() == 0);
        }

        repository.put(key, "completed", 1);
        try (var observer = observer(repository, 100, 2, 1, 1)) {
            WorkflowEventStreamService service = new WorkflowEventStreamService(
                    repository, observer, JsonMapper.builder().build(), Duration.ofSeconds(1));
            assertThatThrownBy(() -> service.streamIfV2(key.userId(), key.runId(), null)
                            .orElseThrow()
                            .writeTo(new AlwaysFailingOutputStream()))
                    .isInstanceOf(IOException.class);
            await(() -> observer.activeConnectionCount() == 0 && observer.activeRunCount() == 0);
        }
    }

    @Test
    void 空闲心跳不读取EventTail且断开观察不取消Run() throws Exception {
        ControlledRepository repository = new ControlledRepository();
        var key = new WorkflowEventStreamRepository.RunKey("user-1", "run-heartbeat");
        repository.put(key, "running", 0);
        try (var observer = observer(repository, 100, 4, 2, 2);
                var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            WorkflowEventStreamService service = new WorkflowEventStreamService(
                    repository, observer, JsonMapper.builder().build(), Duration.ofMillis(20));
            RecordingOutputStream output = new RecordingOutputStream();
            Future<?> stream = executor.submit(() -> write(
                    service.streamIfV2(key.userId(), key.runId(), null)
                            .orElseThrow(),
                    output));

            await(() -> output.text().contains(": 心跳\n\n"));
            assertThat(repository.eventTailCalls).hasValue(0);
            stream.cancel(true);
            await(() -> observer.activeConnectionCount() == 0);
            assertThat(repository.tails.get(key).status()).isEqualTo("running");
        }
    }

    @Test
    void 单轮数据库失败保留订阅而连续三轮失败才断开() throws Exception {
        ControlledRepository repository = new ControlledRepository();
        var key = new WorkflowEventStreamRepository.RunKey("user-1", "run-db-failure");
        repository.put(key, "running", 0);
        repository.tailFailures.set(2);
        try (var observer = observer(repository, 100, 4, 2, 2);
                var subscription = observer.subscribe(key.userId(), key.runId(), 0).activate()) {
            await(() -> repository.tailCalls.get() >= 2);
            assertThat(observer.activeConnectionCount()).isEqualTo(1);
            assertThat(awaitTail(subscription).tail().status()).isEqualTo("running");
        }

        repository.tailFailures.set(3);
        try (var observer = observer(repository, 100, 4, 2, 2);
                var subscription = observer.subscribe(key.userId(), key.runId(), 0).activate()) {
            assertThatThrownBy(() -> subscription.await(WAIT))
                    .isInstanceOf(IOException.class)
                    .hasMessageContaining("WORKFLOW_TAIL_QUERY_FAILED");
            await(() -> observer.activeConnectionCount() == 0);
        }
    }

    @Test
    void 观察循环未知异常清理旧订阅后仍能监督恢复() throws Exception {
        ControlledRepository repository = new ControlledRepository();
        var key = new WorkflowEventStreamRepository.RunKey("user-1", "run-supervised");
        repository.put(key, "running", 0);
        repository.explodingTailLookups.set(1);
        try (var observer = observer(repository, 100, 4, 2, 2)) {
            try (var failed = observer.subscribe(key.userId(), key.runId(), 0).activate()) {
                assertThatThrownBy(() -> failed.await(WAIT))
                        .isInstanceOf(IOException.class)
                        .hasMessageContaining("WORKFLOW_TAIL_OBSERVER_FAILED");
            }
            await(() -> observer.activeConnectionCount() == 0);

            try (var recovered = observer.subscribe(key.userId(), key.runId(), 0).activate()) {
                assertThat(awaitTail(recovered).tail().status()).isEqualTo("running");
            }
        }
    }

    private static WorkflowEventTailObserver observer(
            ControlledRepository repository,
            int eventBatchSize,
            int globalLimit,
            int userLimit,
            int queueCapacity) {
        return new WorkflowEventTailObserver(
                repository,
                Duration.ofMillis(5),
                eventBatchSize,
                globalLimit,
                userLimit,
                queueCapacity);
    }

    private static WorkflowEventTailObserver.Update awaitTail(
            WorkflowEventTailObserver.Subscription subscription) throws Exception {
        WorkflowEventTailObserver.Update update = subscription.await(WAIT).orElseThrow();
        assertThat(update.tail()).isNotNull();
        return update;
    }

    private static WorkflowEventTailObserver.Update awaitEvent(
            WorkflowEventTailObserver.Subscription subscription) throws Exception {
        long deadline = System.nanoTime() + WAIT.toNanos();
        while (System.nanoTime() < deadline) {
            Optional<WorkflowEventTailObserver.Update> update =
                    subscription.await(Duration.ofMillis(100));
            if (update.isPresent() && !update.orElseThrow().events().isEmpty()) {
                return update.orElseThrow();
            }
        }
        throw new AssertionError("未收到 WorkflowEvent tail");
    }

    private static void await(BooleanSupplier condition) throws Exception {
        long deadline = System.nanoTime() + WAIT.toNanos();
        while (!condition.getAsBoolean()) {
            if (System.nanoTime() >= deadline) throw new AssertionError("等待条件超时");
            Thread.sleep(5);
        }
    }

    private static void write(StreamingResponseBody body, OutputStream output) {
        try {
            body.writeTo(output);
        } catch (IOException exception) {
            throw new RuntimeException(exception);
        }
    }

    private static int count(String value, String needle) {
        return (value.length() - value.replace(needle, "").length()) / needle.length();
    }

    private static WorkflowEventEnvelope event(String runId, int sequence) {
        return new WorkflowEventEnvelope(
                2,
                WorkflowEventEnvelope.EventTypeEnum.AWAITING_USER,
                OffsetDateTime.parse("2026-09-01T01:00:00Z").plusSeconds(sequence),
                new AwaitingUserEventPayload(
                        List.of(AwaitingUserEventPayload.AllowedDecisionsEnum.APPROVE),
                        "artifact-1",
                        1,
                        AwaitingUserEventPayload.ReviewAvailabilityEnum.COMPLETE),
                "2.0",
                runId,
                sequence);
    }

    private static RunSnapshot snapshot(String runId, int sequence, String status) {
        return new RunSnapshot(
                sequence,
                2,
                "2.0",
                runId,
                new WorkflowRunSnapshot(
                        List.of(),
                        sequence,
                        1,
                        WorkflowRunSnapshot.StatusEnum.fromValue(status),
                        "long_serial"));
    }

    private static final class ControlledRepository
            implements WorkflowEventStreamRepository {

        private final Map<RunKey, TailState> tails = new ConcurrentHashMap<>();
        private final Map<RunKey, CopyOnWriteArrayList<WorkflowEventEnvelope>> events =
                new ConcurrentHashMap<>();
        private final AtomicInteger snapshotSequence = new AtomicInteger();
        private final AtomicInteger tailCalls = new AtomicInteger();
        private final AtomicInteger eventTailCalls = new AtomicInteger();
        private final AtomicInteger tailFailures = new AtomicInteger();
        private final AtomicInteger explodingTailLookups = new AtomicInteger();
        private final List<List<RunKey>> eventTailBatches = new CopyOnWriteArrayList<>();

        private void put(RunKey key, String status, long sequence) {
            tails.put(key, new TailState(status, sequence));
            events.computeIfAbsent(key, ignored -> new CopyOnWriteArrayList<>());
            snapshotSequence.set(Math.toIntExact(sequence));
        }

        private void publish(
                RunKey key, WorkflowEventEnvelope event, String status) {
            events.computeIfAbsent(key, ignored -> new CopyOnWriteArrayList<>()).add(event);
            tails.put(key, new TailState(status, event.getSequence().longValue()));
            snapshotSequence.set(event.getSequence());
        }

        @Override
        public Optional<SnapshotRead> readSnapshot(String userId, String runId) {
            RunKey key = new RunKey(userId, runId);
            TailState tail = tails.get(key);
            if (tail == null) return Optional.empty();
            int sequence = snapshotSequence.get();
            return Optional.of(new SnapshotRead(snapshot(runId, sequence, tail.status())));
        }

        @Override
        public Map<RunKey, TailState> readTails(List<RunKey> runs) {
            tailCalls.incrementAndGet();
            if (tailFailures.getAndUpdate(value -> Math.max(0, value - 1)) > 0) {
                throw new IllegalStateException("test database unavailable");
            }
            Map<RunKey, TailState> result = new LinkedHashMap<>();
            runs.forEach(run -> {
                TailState tail = tails.get(run);
                if (tail != null) result.put(run, tail);
            });
            if (explodingTailLookups.getAndUpdate(value -> Math.max(0, value - 1)) > 0) {
                Map<RunKey, TailState> values = Map.copyOf(result);
                return new AbstractMap<>() {
                    @Override
                    public TailState get(Object key) {
                        throw new IllegalStateException("test observer bug");
                    }

                    @Override
                    public Set<Map.Entry<RunKey, TailState>> entrySet() {
                        return values.entrySet();
                    }
                };
            }
            return Map.copyOf(result);
        }

        @Override
        public Map<RunKey, List<WorkflowEventEnvelope>> readEventTails(
                List<EventTailRequest> requests, int limitPerRun) {
            eventTailCalls.incrementAndGet();
            eventTailBatches.add(requests.stream().map(EventTailRequest::key).toList());
            Map<RunKey, List<WorkflowEventEnvelope>> result = new LinkedHashMap<>();
            requests.forEach(request -> result.put(
                    request.key(),
                    events.getOrDefault(request.key(), new CopyOnWriteArrayList<>()).stream()
                            .filter(event -> event.getSequence().longValue()
                                    > request.afterSequence())
                            .filter(event -> event.getSequence().longValue()
                                    <= request.throughSequence())
                            .limit(limitPerRun)
                            .toList()));
            return Map.copyOf(result);
        }
    }

    private static final class RecordingOutputStream extends OutputStream {
        private final ByteArrayOutputStream delegate = new ByteArrayOutputStream();

        @Override
        public synchronized void write(int value) {
            delegate.write(value);
        }

        @Override
        public synchronized void write(byte[] value, int offset, int length) {
            delegate.write(value, offset, length);
        }

        private synchronized String text() {
            return delegate.toString(StandardCharsets.UTF_8);
        }
    }

    private static final class AlwaysFailingOutputStream extends OutputStream {
        @Override
        public void write(int value) throws IOException {
            throw new IOException("client disconnected");
        }

        @Override
        public void write(byte[] value, int offset, int length) throws IOException {
            throw new IOException("client disconnected");
        }
    }
}
