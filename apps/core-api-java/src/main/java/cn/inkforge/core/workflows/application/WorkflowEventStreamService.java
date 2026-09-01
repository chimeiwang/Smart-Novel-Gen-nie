package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.api.RunSnapshot;
import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.core.platform.http.ApiException;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Pattern;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import tools.jackson.databind.ObjectMapper;

/** 从 PostgreSQL snapshot 与 WorkflowEvent 生成 V2 写作运行 SSE。 */
public final class WorkflowEventStreamService {

    private static final String PROTOCOL_VERSION = "2.0";
    private static final Pattern DECIMAL_CURSOR = Pattern.compile("[0-9]+");

    private final WorkflowEventStreamRepository repository;
    private final WorkflowEventTailObserver observer;
    private final ObjectMapper json;
    private final Duration heartbeatInterval;

    public WorkflowEventStreamService(
            WorkflowEventStreamRepository repository,
            WorkflowEventTailObserver observer,
            ObjectMapper json,
            Duration heartbeatInterval) {
        this.repository = Objects.requireNonNull(repository);
        this.observer = Objects.requireNonNull(observer);
        this.json = Objects.requireNonNull(json);
        if (heartbeatInterval == null
                || heartbeatInterval.isZero()
                || heartbeatInterval.isNegative()) {
            throw new IllegalArgumentException("Workflow SSE 间隔无效");
        }
        this.heartbeatInterval = heartbeatInterval;
    }

    /**
     * 按持久化引擎身份准备流。cursor 在返回 StreamingResponseBody 前校验，确保错误仍能返回稳定 409。
     */
    public Optional<StreamingResponseBody> streamIfV2(
            String userId, String runId, String lastEventId) {
        Optional<WorkflowEventStreamRepository.SnapshotRead> initial =
                repository.readSnapshot(userId, runId);
        if (initial.isEmpty()) return Optional.empty();
        RunSnapshot frame = initial.orElseThrow().frame();
        validateSnapshot(runId, frame);
        long baseSequence = frame.getBaseSequence().longValue();
        validateCursor(lastEventId, baseSequence);
        WorkflowEventTailObserver.Subscription subscription =
                observer.subscribe(userId, runId, baseSequence);
        AtomicBoolean claimed = new AtomicBoolean();
        return Optional.of(output -> {
            if (!claimed.compareAndSet(false, true)) {
                subscription.close();
                throw new IOException("Workflow SSE 响应不能重复执行");
            }
            try (subscription) {
                writeLoop(output, runId, frame, subscription);
            }
        });
    }

    private void writeLoop(
            OutputStream output,
            String runId,
            RunSnapshot initial,
            WorkflowEventTailObserver.Subscription subscription) throws IOException {
        long cursor = initial.getBaseSequence().longValue();
        write(output, formatSnapshot(runId, initial));
        subscription.activate();
        long heartbeatDeadline = System.nanoTime() + heartbeatInterval.toNanos();
        while (!Thread.currentThread().isInterrupted()) {
            long remainingNanos = Math.max(0L, heartbeatDeadline - System.nanoTime());
            Optional<WorkflowEventTailObserver.Update> observed;
            try {
                observed = subscription.await(Duration.ofNanos(remainingNanos));
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return;
            }

            if (observed.isEmpty()) {
                write(output, ": 心跳\n\n");
                heartbeatDeadline = System.nanoTime() + heartbeatInterval.toNanos();
                continue;
            }

            WorkflowEventTailObserver.Update update = observed.orElseThrow();
            boolean wroteEvent = false;
            for (WorkflowEventEnvelope event : update.events()) {
                long sequence = event.getSequence().longValue();
                // 共享 cursor 因较晚订阅回拨时会重读前缀；每条连接只接受自己的严格后继。
                if (sequence <= cursor) continue;
                if (sequence != Math.addExact(cursor, 1L)) {
                    throw new IllegalStateException("WorkflowEvent sequence 不连续");
                }
                write(output, formatEvent(runId, event));
                cursor = sequence;
                subscription.markDelivered(sequence);
                wroteEvent = true;
            }
            if (wroteEvent) {
                heartbeatDeadline = System.nanoTime() + heartbeatInterval.toNanos();
            }

            WorkflowEventStreamRepository.TailState tail = update.tail();
            if (tail == null) continue;
            if (tail.lastEventSequence() < cursor) {
                throw new IllegalStateException("WorkflowRun lastEventSequence 发生倒退");
            }
            // waiting_user 和终态只在该连接已经写完同一高水位的事件后关闭。
            if (tail.lastEventSequence() == cursor && tail.streamShouldClose()) {
                return;
            }
        }
    }

    private String formatSnapshot(String expectedRunId, RunSnapshot snapshot) {
        validateSnapshot(expectedRunId, snapshot);
        StringBuilder frame = new StringBuilder();
        if (snapshot.getBaseSequence() > 0) {
            frame.append("id: ").append(snapshot.getBaseSequence()).append('\n');
        }
        frame.append("event: run_snapshot\ndata: ")
                .append(json.writeValueAsString(snapshot))
                .append("\n\n");
        return frame.toString();
    }

    private static void validateSnapshot(String expectedRunId, RunSnapshot snapshot) {
        if (snapshot == null
                || !PROTOCOL_VERSION.equals(snapshot.getProtocolVersion())
                || !Integer.valueOf(2).equals(snapshot.getEngineVersion())
                || !Objects.equals(snapshot.getRunId(), expectedRunId)
                || snapshot.getSnapshot() == null
                || snapshot.getBaseSequence() == null
                || snapshot.getBaseSequence() < 0
                || !Objects.equals(
                        snapshot.getBaseSequence(),
                        snapshot.getSnapshot().getLastEventSequence())) {
            throw new IllegalStateException("Run snapshot 不符合 V2 共享契约");
        }
    }

    private String formatEvent(String expectedRunId, WorkflowEventEnvelope event) {
        if (!PROTOCOL_VERSION.equals(event.getProtocolVersion())
                || !Integer.valueOf(2).equals(event.getEngineVersion())
                || !Objects.equals(event.getRunId(), expectedRunId)
                || event.getSequence() == null
                || event.getSequence() < 1
                || event.getEventType() == null
                || event.getOccurredAt() == null
                || event.getPayload() == null) {
            throw new IllegalStateException("WorkflowEvent envelope 不符合 V2 共享契约");
        }
        return "id: "
                + event.getSequence()
                + "\nevent: "
                + event.getEventType().getValue()
                + "\ndata: "
                + json.writeValueAsString(event)
                + "\n\n";
    }

    private static void validateCursor(String lastEventId, long baseSequence) {
        if (lastEventId == null) return;
        if (!DECIMAL_CURSOR.matcher(lastEventId).matches()) throw invalidCursor();
        final long cursor;
        try {
            cursor = Long.parseLong(lastEventId);
        } catch (NumberFormatException exception) {
            throw invalidCursor();
        }
        // 等于或小于 baseSequence 仅用于诊断；当前 snapshot 已覆盖旧 UI 状态。
        if (cursor > baseSequence) throw invalidCursor();
    }

    private static ApiException invalidCursor() {
        return new ApiException(409, "WORKFLOW_CURSOR_INVALID", "工作流事件游标无效");
    }

    private static void write(OutputStream output, String value) throws IOException {
        output.write(value.getBytes(StandardCharsets.UTF_8));
        output.flush();
    }
}
