package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.WritingRunOutcome;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.writing.domain.WritingEvent;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 从 Redis Stream 与 PostgreSQL 统一结果投影生成浏览器 SSE。 */
public final class WritingEventStreamService {

    private final WritingRunQueryRepository queries;
    private final WritingEventStore events;
    private final WritingOutboxRepository outbox;
    private final ObjectMapper json;
    private final Duration pollInterval;
    private final Duration heartbeatInterval;
    private final cn.inkforge.core.workflows.application.WorkflowEventStreamService
            workflowStreams;

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
                null);
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
        this.queries = Objects.requireNonNull(queries);
        this.events = events;
        this.outbox = Objects.requireNonNull(outbox);
        this.json = Objects.requireNonNull(json);
        this.workflowStreams = workflowStreams;
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

    public StreamingResponseBody stream(
            String userId, String taskId, String lastEventId) {
        if (workflowStreams != null) {
            var v2 = workflowStreams.streamIfV2(userId, taskId, lastEventId);
            if (v2.isPresent()) return v2.orElseThrow();
        }
        if (events == null) {
            throw new ApiException(
                    503, "WRITING_EVENTS_UNAVAILABLE", "写作事件流暂时不可用");
        }
        WritingRunStatusResponse initial = queries.get(userId, taskId);
        return output -> writeLoop(output, userId, taskId, lastEventId, initial);
    }

    private void writeLoop(
            OutputStream output,
            String userId,
            String taskId,
            String lastEventId,
            WritingRunStatusResponse initial) throws IOException {
        String cursor = lastEventId;
        WritingRunOutcome outcome = initial.getOutcome();
        String fingerprint = fingerprint(outcome);
        write(output, formatOutcome(outcome));
        if (Boolean.TRUE.equals(outcome.getStreamShouldClose())) {
            VisibleReplay replay = replay(taskId, cursor);
            for (WritingEvent event : replay.events()) write(output, formatEvent(event));
            if (!replay.events().isEmpty()) write(output, formatOutcome(outcome));
            return;
        }
        long idleMillis = 0;
        while (!Thread.currentThread().isInterrupted()) {
            VisibleReplay replay = replay(taskId, cursor);
            cursor = replay.cursor();
            if (!replay.events().isEmpty()) {
                idleMillis = 0;
                for (WritingEvent event : replay.events()) write(output, formatEvent(event));
            }
            outcome = queries.get(userId, taskId).getOutcome();
            String currentFingerprint = fingerprint(outcome);
            if (!currentFingerprint.equals(fingerprint)) {
                write(output, formatOutcome(outcome));
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
                write(output, ": 心跳\n\n");
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

    private static void write(OutputStream output, String value) throws IOException {
        output.write(value.getBytes(StandardCharsets.UTF_8));
        output.flush();
    }

    private record VisibleReplay(List<WritingEvent> events, String cursor) {}
}
