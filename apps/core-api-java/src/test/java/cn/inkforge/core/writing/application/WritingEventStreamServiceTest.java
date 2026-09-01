package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.WritingRunListResponse;
import cn.inkforge.contracts.api.WritingRunOutcome;
import cn.inkforge.contracts.api.WritingRunOutcomeResult;
import cn.inkforge.contracts.api.WritingRunStatusPublicResponse;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.contracts.api.RunSnapshot;
import cn.inkforge.contracts.api.AwaitingUserEventPayload;
import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.contracts.api.WorkflowRunSnapshot;
import cn.inkforge.core.writing.domain.WritingEvent;
import cn.inkforge.core.writing.domain.WritingOutboxHealth;
import cn.inkforge.core.writing.domain.WritingOutboxRecord;
import cn.inkforge.core.platform.http.ManagedSseEmitter;
import cn.inkforge.core.platform.http.ManagedSseEmitterInterceptor;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository;
import java.io.IOException;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter.DataWithMediaType;
import tools.jackson.databind.json.JsonMapper;

class WritingEventStreamServiceTest {

    private static final Duration WAIT = Duration.ofSeconds(3);

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
            try (WritingEventStreamService service = new WritingEventStreamService(
                    queries,
                    null,
                    new NoopOutboxRepository(),
                    JsonMapper.builder().build(),
                    Duration.ofMillis(1),
                    Duration.ofMillis(5),
                    workflowStreams)) {
                StringBuilder output = new StringBuilder();

                service.prepare("user-1", "run-v2", null).run(output::append);

                assertThat(output)
                        .startsWith("event: run_snapshot\n")
                        .contains("\"engineVersion\":2");
            }
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
        try (WritingEventStreamService service = new WritingEventStreamService(
                queries,
                events,
                outbox,
                JsonMapper.builder().build(),
                Duration.ofMillis(1),
                Duration.ofMillis(5))) {
            StringBuilder output = new StringBuilder();

            service.prepare("user-1", "task-1", null).run(output::append);

            String text = output.toString();
            assertThat(text).startsWith("event: run_outcome\n");
            assertThat(text).contains("id: 1-0\nevent: completed\n");
            assertThat(text).doesNotContain("id: 2-0");
            assertThat(count(text, "event: run_outcome")).isEqualTo(2);
        }
    }

    @Test
    void 共享Executor为每条连接使用虚拟线程且Bean关闭会中断并回收Worker() throws Exception {
        WritingRunStatusResponse status = new WritingRunStatusResponse();
        status.setOutcome(new WritingRunOutcome(
                "WRITING_RUN_RUNNING",
                null,
                OffsetDateTime.parse("2026-09-01T02:00:00Z"),
                false,
                new WritingRunOutcomeResult(
                        WritingRunOutcomeResult.KindEnum.NONE, false),
                WritingRunOutcome.StateEnum.RUNNING,
                false,
                false));
        AtomicInteger reads = new AtomicInteger();
        AtomicReference<Thread> workerThread = new AtomicReference<>();
        CountDownLatch workerRead = new CountDownLatch(1);
        WritingRunQueryRepository queries = new WritingRunQueryRepository() {
            @Override
            public WritingRunStatusResponse get(String userId, String taskId) {
                if (reads.incrementAndGet() > 1) {
                    workerThread.compareAndSet(null, Thread.currentThread());
                    workerRead.countDown();
                }
                return status;
            }

            @Override
            public WritingRunStatusPublicResponse getPublic(String userId, String taskId) {
                return status;
            }

            @Override
            public WritingRunListResponse list(
                    String a, String b, String c, String d, String e, String f, String g, int h) {
                throw new UnsupportedOperationException();
            }
        };
        WritingEventStreamService service = new WritingEventStreamService(
                queries,
                new FixedEventStore(List.of()),
                new NoopOutboxRepository(),
                JsonMapper.builder().build(),
                Duration.ofSeconds(30),
                Duration.ofSeconds(30));

        MockHttpServletRequest request = new MockHttpServletRequest();
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
        try {
            ManagedSseEmitter emitter = service.stream("user-1", "task-running", null);
            emitter.armCurrentRequest();
            new ManagedSseEmitterInterceptor().afterConcurrentHandlingStarted(
                    request, new MockHttpServletResponse(), new Object());

            assertThat(workerRead.await(WAIT.toMillis(), TimeUnit.MILLISECONDS)).isTrue();
            assertThat(workerThread.get()).isNotNull();
            assertThat(workerThread.get().isVirtual()).isTrue();
            assertThat(service.activeWorkerCount()).isEqualTo(1);

            service.close();

            assertThat(service.activeWorkerCount()).isZero();
            assertThat(service.workerExecutorTerminated()).isTrue();
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }

    @Test
    void Handler未Ready时五个批次不得激活慢消费者且Bean关闭回收预留订阅() throws Exception {
        RunSnapshot snapshot = new RunSnapshot(
                0,
                2,
                "2.0",
                "run-delayed-handler",
                new WorkflowRunSnapshot(
                        List.of(),
                        0,
                        1,
                        WorkflowRunSnapshot.StatusEnum.RUNNING,
                        "long_serial"));
        List<WorkflowEventEnvelope> committed = java.util.stream.IntStream.rangeClosed(1, 5)
                .mapToObj(sequence -> new WorkflowEventEnvelope(
                        2,
                        WorkflowEventEnvelope.EventTypeEnum.AWAITING_USER,
                        OffsetDateTime.parse("2026-09-01T02:00:00Z").plusSeconds(sequence),
                        new AwaitingUserEventPayload(
                                List.of(AwaitingUserEventPayload.AllowedDecisionsEnum.APPROVE),
                                "artifact-" + sequence,
                                1,
                                AwaitingUserEventPayload.ReviewAvailabilityEnum.COMPLETE),
                        "2.0",
                        "run-delayed-handler",
                        sequence))
                .toList();
        CountDownLatch fiveBatchesRead = new CountDownLatch(5);
        WorkflowEventStreamRepository repository = new WorkflowEventStreamRepository() {
            @Override
            public java.util.Optional<SnapshotRead> readSnapshot(
                    String userId, String runId) {
                return java.util.Optional.of(new SnapshotRead(snapshot));
            }

            @Override
            public Map<RunKey, TailState> readTails(List<RunKey> runs) {
                if (runs.isEmpty()) return Map.of();
                return Map.of(runs.getFirst(), new TailState("running", 5));
            }

            @Override
            public Map<RunKey, List<WorkflowEventEnvelope>> readEventTails(
                    List<EventTailRequest> requests, int limitPerRun) {
                Map<RunKey, List<WorkflowEventEnvelope>> result = new java.util.LinkedHashMap<>();
                requests.forEach(request -> {
                    List<WorkflowEventEnvelope> page = committed.stream()
                            .filter(event -> event.getSequence() > request.afterSequence())
                            .filter(event -> event.getSequence() <= request.throughSequence())
                            .limit(limitPerRun)
                            .toList();
                    result.put(request.key(), page);
                    if (!page.isEmpty()) fiveBatchesRead.countDown();
                });
                return Map.copyOf(result);
            }
        };
        try (var observer = new cn.inkforge.core.workflows.application.WorkflowEventTailObserver(
                repository, Duration.ofMillis(1), 1, 16, 4, 4)) {
            var workflowStreams =
                    new cn.inkforge.core.workflows.application.WorkflowEventStreamService(
                            repository,
                            observer,
                            JsonMapper.builder().build(),
                            Duration.ofSeconds(1));
            WritingRunQueryRepository unexpectedV1 = new WritingRunQueryRepository() {
                @Override
                public WritingRunStatusResponse get(String userId, String taskId) {
                    throw new AssertionError("V2 不得回退 V1");
                }

                @Override
                public WritingRunStatusPublicResponse getPublic(String userId, String taskId) {
                    throw new UnsupportedOperationException();
                }

                @Override
                public WritingRunListResponse list(
                        String a,
                        String b,
                        String c,
                        String d,
                        String e,
                        String f,
                        String g,
                        int h) {
                    throw new UnsupportedOperationException();
                }
            };
            WritingEventStreamService service = new WritingEventStreamService(
                    unexpectedV1,
                    null,
                    new NoopOutboxRepository(),
                    JsonMapper.builder().build(),
                    Duration.ofSeconds(1),
                    Duration.ofSeconds(1),
                    workflowStreams);

            ManagedSseEmitter unarmed =
                    service.stream("user-1", "run-delayed-handler", null);

            assertThat(unarmed).isNotNull();
            assertThat(fiveBatchesRead.await(WAIT.toMillis(), TimeUnit.MILLISECONDS)).isTrue();
            assertThat(service.activeWorkerCount()).isZero();
            assertThat(observerConnectionCount(observer)).isEqualTo(1);
            assertThat(observerRunCount(observer)).isEqualTo(1);

            service.close();

            assertThat(service.activeWorkerCount()).isZero();
            assertThat(service.workerExecutorTerminated()).isTrue();
            assertThat(observerConnectionCount(observer)).isZero();
            assertThat(observerRunCount(observer)).isZero();
        }
    }

    @Test
    void HandlerReady后Executor拒绝必须错误完成并移除Session() {
        WritingRunStatusResponse status = new WritingRunStatusResponse();
        status.setOutcome(new WritingRunOutcome(
                "WRITING_RUN_RUNNING",
                null,
                OffsetDateTime.parse("2026-09-01T02:00:00Z"),
                false,
                new WritingRunOutcomeResult(
                        WritingRunOutcomeResult.KindEnum.NONE, false),
                WritingRunOutcome.StateEnum.RUNNING,
                false,
                false));
        WritingRunQueryRepository queries = fixedQueries(status);
        var rejected = Executors.newVirtualThreadPerTaskExecutor();
        rejected.shutdownNow();
        WritingEventStreamService service = new WritingEventStreamService(
                queries,
                new FixedEventStore(List.of()),
                new NoopOutboxRepository(),
                JsonMapper.builder().build(),
                Duration.ofSeconds(1),
                Duration.ofSeconds(1),
                null,
                rejected);
        MockHttpServletRequest request = new MockHttpServletRequest();
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
        try {
            ManagedSseEmitter emitter = service.stream("user-1", "task-rejected", null);
            emitter.armCurrentRequest();

            new ManagedSseEmitterInterceptor().afterConcurrentHandlingStarted(
                    request, new MockHttpServletResponse(), new Object());

            assertThat(service.liveSessionCount()).isZero();
            assertThat(service.activeWorkerCount()).isZero();
            assertThatThrownBy(() -> emitter.send("不得再发送"))
                    .isInstanceOf(IllegalStateException.class);
        } finally {
            service.close();
            RequestContextHolder.resetRequestAttributes();
        }
    }

    @Test
    void Handler内部IllegalState必须作为真实故障而仅已完成Emitter归为断线() {
        IllegalStateException converterFailure =
                new IllegalStateException("测试 converter 失败");
        ManagedSseEmitter failing = new ManagedSseEmitter(0L) {
            @Override
            public void send(Set<DataWithMediaType> items) {
                throw converterFailure;
            }

            @Override
            protected void startManagedSession() {}

            @Override
            protected void abortManagedSession() {}
        };

        assertThatThrownBy(() -> WritingEventStreamService.sendRawFrame(
                        failing, "event: test\n\n"))
                .isSameAs(converterFailure);
        assertThat(failing.isNoLongerWritable()).isFalse();

        ManagedSseEmitter completed = new ManagedSseEmitter(0L) {
            @Override
            protected void startManagedSession() {}

            @Override
            protected void abortManagedSession() {}
        };
        completed.complete();

        assertThatThrownBy(() -> WritingEventStreamService.sendRawFrame(
                        completed, "event: test\n\n"))
                .isInstanceOf(IOException.class)
                .hasMessage("SSE 客户端连接已关闭");
        assertThat(completed.isNoLongerWritable()).isTrue();
    }

    private static WritingRunQueryRepository fixedQueries(WritingRunStatusResponse status) {
        return new WritingRunQueryRepository() {
            @Override
            public WritingRunStatusResponse get(String userId, String taskId) {
                return status;
            }

            @Override
            public WritingRunStatusPublicResponse getPublic(String userId, String taskId) {
                return status;
            }

            @Override
            public WritingRunListResponse list(
                    String a, String b, String c, String d, String e, String f, String g, int h) {
                throw new UnsupportedOperationException();
            }
        };
    }

    private static int observerConnectionCount(
            cn.inkforge.core.workflows.application.WorkflowEventTailObserver observer) {
        Integer count = ReflectionTestUtils.invokeMethod(observer, "activeConnectionCount");
        return count == null ? -1 : count;
    }

    private static int observerRunCount(
            cn.inkforge.core.workflows.application.WorkflowEventTailObserver observer) {
        Integer count = ReflectionTestUtils.invokeMethod(observer, "activeRunCount");
        return count == null ? -1 : count;
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
