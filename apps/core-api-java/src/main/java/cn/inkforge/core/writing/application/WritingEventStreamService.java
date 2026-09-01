package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.WritingRunOutcome;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.ManagedSseEmitter;
import cn.inkforge.core.platform.http.SseStream;
import cn.inkforge.core.writing.domain.WritingEvent;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter.DataWithMediaType;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 从 Redis Stream 与 PostgreSQL 统一结果投影生成浏览器 SSE。 */
public final class WritingEventStreamService implements AutoCloseable {

    private static final MediaType RAW_SSE_FRAME_TYPE =
            new MediaType("text", "plain", StandardCharsets.UTF_8);
    private static final Duration WORKER_SHUTDOWN_TIMEOUT = Duration.ofSeconds(5);

    private final WritingRunQueryRepository queries;
    private final WritingEventStore events;
    private final WritingOutboxRepository outbox;
    private final ObjectMapper json;
    private final Duration pollInterval;
    private final Duration heartbeatInterval;
    private final cn.inkforge.core.workflows.application.WorkflowEventStreamService
            workflowStreams;
    private final ExecutorService workers;
    private final AtomicInteger activeWorkers = new AtomicInteger();
    private final Set<EmitterSession> sessions = ConcurrentHashMap.newKeySet();
    private final AtomicBoolean closing = new AtomicBoolean();
    private final Object workerDrain = new Object();

    public WritingEventStreamService(
            WritingRunQueryRepository queries,
            WritingEventStore events,
            WritingOutboxRepository outbox,
            ObjectMapper json,
            Duration pollInterval,
            Duration heartbeatInterval) {
        this(
                queries,
                events,
                outbox,
                json,
                pollInterval,
                heartbeatInterval,
                null,
                newWorkerExecutor());
    }

    public WritingEventStreamService(
            WritingRunQueryRepository queries,
            WritingEventStore events,
            WritingOutboxRepository outbox,
            ObjectMapper json,
            Duration pollInterval,
            Duration heartbeatInterval,
            cn.inkforge.core.workflows.application.WorkflowEventStreamService
                    workflowStreams) {
        this(
                queries,
                events,
                outbox,
                json,
                pollInterval,
                heartbeatInterval,
                workflowStreams,
                newWorkerExecutor());
    }

    WritingEventStreamService(
            WritingRunQueryRepository queries,
            WritingEventStore events,
            WritingOutboxRepository outbox,
            ObjectMapper json,
            Duration pollInterval,
            Duration heartbeatInterval,
            cn.inkforge.core.workflows.application.WorkflowEventStreamService workflowStreams,
            ExecutorService workers) {
        this.queries = Objects.requireNonNull(queries);
        this.events = events;
        this.outbox = Objects.requireNonNull(outbox);
        this.json = Objects.requireNonNull(json);
        this.workflowStreams = workflowStreams;
        this.workers = Objects.requireNonNull(workers);
        if (pollInterval == null
                || pollInterval.isZero()
                || pollInterval.isNegative()
                || heartbeatInterval == null
                || heartbeatInterval.isZero()
                || heartbeatInterval.isNegative()) {
            throw new IllegalArgumentException("写作 SSE 间隔无效");
        }
        this.pollInterval = pollInterval;
        this.heartbeatInterval = heartbeatInterval;
    }

    public ManagedSseEmitter stream(
            String userId, String taskId, String lastEventId) {
        return open(prepare(userId, taskId, lastEventId));
    }

    SseStream prepare(String userId, String taskId, String lastEventId) {
        if (workflowStreams != null) {
            var v2 = workflowStreams.streamIfV2(userId, taskId, lastEventId);
            if (v2.isPresent()) return v2.orElseThrow();
        }
        if (events == null) {
            throw new ApiException(
                    503, "WRITING_EVENTS_UNAVAILABLE", "写作事件流暂时不可用");
        }
        WritingRunStatusResponse initial = queries.get(userId, taskId);
        return sender -> writeLoop(sender, userId, taskId, lastEventId, initial);
    }

    private void writeLoop(
            SseStream.FrameSender sender,
            String userId,
            String taskId,
            String lastEventId,
            WritingRunStatusResponse initial) throws IOException {
        String cursor = lastEventId;
        WritingRunOutcome outcome = initial.getOutcome();
        String fingerprint = fingerprint(outcome);
        sender.send(formatOutcome(outcome));
        if (Boolean.TRUE.equals(outcome.getStreamShouldClose())) {
            VisibleReplay replay = replay(taskId, cursor);
            for (WritingEvent event : replay.events()) sender.send(formatEvent(event));
            if (!replay.events().isEmpty()) sender.send(formatOutcome(outcome));
            return;
        }
        long idleMillis = 0;
        while (!Thread.currentThread().isInterrupted()) {
            VisibleReplay replay = replay(taskId, cursor);
            cursor = replay.cursor();
            if (!replay.events().isEmpty()) {
                idleMillis = 0;
                for (WritingEvent event : replay.events()) sender.send(formatEvent(event));
            }
            outcome = queries.get(userId, taskId).getOutcome();
            String currentFingerprint = fingerprint(outcome);
            if (!currentFingerprint.equals(fingerprint)) {
                sender.send(formatOutcome(outcome));
                fingerprint = currentFingerprint;
            }
            if (Boolean.TRUE.equals(outcome.getStreamShouldClose())) return;
            if (!replay.events().isEmpty()) continue;
            try {
                Thread.sleep(pollInterval.toMillis());
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return;
            }
            idleMillis += pollInterval.toMillis();
            if (idleMillis >= heartbeatInterval.toMillis()) {
                sender.send(": 心跳\n\n");
                idleMillis = 0;
            }
        }
    }

    private VisibleReplay replay(String taskId, String cursor) {
        List<WritingEvent> replayed = events.replay(taskId, cursor);
        if (replayed.isEmpty()) return new VisibleReplay(List.of(), cursor);
        Map<String, String> dispositions = outbox.replayDispositions(replayed);
        List<WritingEvent> visible = new ArrayList<>();
        String next = cursor;
        for (WritingEvent event : replayed) {
            String disposition = dispositions.getOrDefault(event.id(), "wait");
            if ("wait".equals(disposition)) break;
            next = event.id();
            if ("emit".equals(disposition)) visible.add(event);
        }
        return new VisibleReplay(List.copyOf(visible), next);
    }

    private String formatEvent(WritingEvent event) {
        return "id: "
                + event.id()
                + "\nevent: "
                + event.event()
                + "\ndata: "
                + json.writeValueAsString(event.data())
                + "\n\n";
    }

    private String formatOutcome(WritingRunOutcome outcome) {
        return "event: run_outcome\ndata: "
                + json.writeValueAsString(outcome)
                + "\n\n";
    }

    private String fingerprint(WritingRunOutcome outcome) {
        Map<String, Object> value = json.convertValue(
                outcome, new TypeReference<Map<String, Object>>() {});
        value.remove("observedAt");
        return CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(value, json));
    }

    private ManagedSseEmitter open(SseStream stream) {
        if (closing.get()) {
            stream.close();
            throw new IllegalStateException("写作 SSE 服务正在停止");
        }
        EmitterSession session = new EmitterSession(stream);
        sessions.add(session);
        if (closing.get()) {
            session.shutdown();
            throw new IllegalStateException("写作 SSE 服务正在停止");
        }
        return session;
    }

    static void sendRawFrame(ManagedSseEmitter emitter, String frame)
            throws IOException {
        try {
            emitter.send(Set.of(new DataWithMediaType(frame, RAW_SSE_FRAME_TYPE)));
        } catch (IOException exception) {
            throw new ClientConnectionClosedException(exception);
        } catch (IllegalStateException exception) {
            if (!emitter.isNoLongerWritable()) throw exception;
            throw new ClientConnectionClosedException(exception);
        }
    }

    private static ExecutorService newWorkerExecutor() {
        return Executors.newThreadPerTaskExecutor(
                Thread.ofVirtual().name("writing-sse-", 0).factory());
    }

    @Override
    public void close() {
        closing.set(true);
        List.copyOf(sessions).forEach(EmitterSession::shutdown);
        workers.shutdownNow();
        try {
            if (!workers.awaitTermination(
                    WORKER_SHUTDOWN_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS)) {
                workers.shutdownNow();
            }
            awaitWorkerDrain();
        } catch (InterruptedException exception) {
            workers.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    private void awaitWorkerDrain() throws InterruptedException {
        long deadline = System.nanoTime() + WORKER_SHUTDOWN_TIMEOUT.toNanos();
        synchronized (workerDrain) {
            while (activeWorkers.get() > 0) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) {
                    throw new IllegalStateException("写作 SSE 连接 worker 未在关闭期限内退出");
                }
                TimeUnit.NANOSECONDS.timedWait(workerDrain, remaining);
            }
        }
    }

    int activeWorkerCount() {
        return activeWorkers.get();
    }

    boolean workerExecutorTerminated() {
        return workers.isTerminated();
    }

    int liveSessionCount() {
        return sessions.size();
    }

    private final class EmitterSession extends ManagedSseEmitter {

        private final SseStream stream;
        private final AtomicBoolean closed = new AtomicBoolean();
        private final AtomicReference<Future<?>> worker = new AtomicReference<>();

        private EmitterSession(SseStream stream) {
            super(0L);
            this.stream = stream;
            onCompletion(this::abort);
            onTimeout(this::abort);
            onError(ignored -> abort());
        }

        @Override
        protected void startManagedSession() {
            if (closed.get()) return;
            final Future<?> submitted;
            try {
                submitted = workers.submit(this::run);
            } catch (RuntimeException exception) {
                closeResources();
                throw exception;
            }
            worker.set(submitted);
            // completion/error 可能在 Future 发布前到达；发布后必须再次收敛取消。
            if (closed.get()) submitted.cancel(true);
        }

        @Override
        protected void abortManagedSession() {
            if (!closeResources()) return;
            Future<?> running = worker.get();
            if (running != null) running.cancel(true);
        }

        private void run() {
            activeWorkers.incrementAndGet();
            try {
                stream.run(frame -> sendRawFrame(this, frame));
                completeNormally();
            } catch (ClientConnectionClosedException exception) {
                closeResources();
            } catch (IOException | RuntimeException exception) {
                completeAbnormally(exception);
            } finally {
                try {
                    closeResources();
                } finally {
                    activeWorkers.decrementAndGet();
                    synchronized (workerDrain) {
                        workerDrain.notifyAll();
                    }
                }
            }
        }

        private void completeNormally() {
            if (!closeResources()) return;
            complete();
        }

        private void completeAbnormally(Throwable failure) {
            if (!closeResources()) return;
            super.completeWithError(failure);
        }

        private boolean closeResources() {
            if (!closed.compareAndSet(false, true)) return false;
            try {
                stream.close();
            } finally {
                sessions.remove(this);
            }
            return true;
        }
    }

    private static final class ClientConnectionClosedException extends IOException {

        private ClientConnectionClosedException(Throwable cause) {
            super("SSE 客户端连接已关闭", cause);
        }
    }

    private record VisibleReplay(List<WritingEvent> events, String cursor) {}
}
