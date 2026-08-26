package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.AgentEvent;
import cn.inkforge.contracts.api.CheckpointCallback;
import cn.inkforge.contracts.api.RunCompletionCallback;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.writing.application.WritingCallbackRepository;
import cn.inkforge.core.writing.application.WritingCallbackService;
import cn.inkforge.core.writing.domain.WritingBoundaryEvent;
import cn.inkforge.core.writing.domain.WritingCallbackAcceptance;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

class WritingCallbackServiceTest {

    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T10:00:00Z"), ZoneOffset.UTC);
    private final ObjectMapper json = JsonMapper.builder().build();

    @Test
    void 普通事件必须先校验来源和序号再推进命令并可幂等重放() {
        RecordingRepository repository = new RecordingRepository();
        InMemoryWritingEventStore events = new InMemoryWritingEventStore(CLOCK);
        WritingCallbackService service = new WritingCallbackService(repository, events, json);
        AgentEvent body = event("event-1", 1, Map.of("agentId", "写作"));

        var first = service.acceptEvent(body);
        var replay = service.acceptEvent(body);
        AgentEvent conflict = event("event-1", 1, Map.of("agentId", "编辑"));
        var rejected = service.acceptEvent(conflict);

        assertThat(first.getDisposition().getValue()).isEqualTo("applied");
        assertThat(repository.markProcessingCalls).isEqualTo(1);
        assertThat(events.replay("task-1", null)).hasSize(1);
        assertThat(replay.getDisposition().getValue()).isEqualTo("already_applied");
        assertThat(rejected.getDisposition().getValue()).isEqualTo("rejected");
        assertThat(rejected.getReasonCode()).isEqualTo("WRITING_EVENT_SOURCE_CONFLICT");
    }

    @Test
    void Redis序号缺口必须返回可对账冲突而不能推进数据库() {
        RecordingRepository repository = new RecordingRepository();
        InMemoryWritingEventStore events = new InMemoryWritingEventStore(CLOCK);
        WritingCallbackService service = new WritingCallbackService(repository, events, json);
        service.acceptEvent(event("event-1", 1, Map.of()));

        assertThatThrownBy(() -> service.acceptEvent(event("event-3", 3, Map.of())))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.code()).isEqualTo("AGENT_EVENT_SEQUENCE_GAP");
                    assertThat(((Map<?, ?>) error.details()).get("expectedSequence"))
                            .isEqualTo(2);
                });
        assertThat(repository.markProcessingCalls).isEqualTo(1);
    }

    @Test
    void 非等待检查点写入后才发布短期事件而等待检查点只走原子Outbox() {
        RecordingRepository repository = new RecordingRepository();
        InMemoryWritingEventStore events = new InMemoryWritingEventStore(CLOCK);
        WritingCallbackService service = new WritingCallbackService(repository, events, json);
        Map<String, Object> active = longCheckpoint("active", 1);

        var activeReceipt = service.saveCheckpoint(
                checkpoint("checkpoint-active", 1, active), "user-1", "novel-1");

        assertThat(activeReceipt.getDisposition().getValue()).isEqualTo("applied");
        assertThat(repository.lastBoundary).isNull();
        assertThat(events.replay("task-1", null)).extracting(item -> item.event())
                .containsExactly("checkpoint");

        RecordingRepository waitingRepository = new RecordingRepository();
        InMemoryWritingEventStore waitingEvents = new InMemoryWritingEventStore(CLOCK);
        WritingCallbackService waitingService =
                new WritingCallbackService(waitingRepository, waitingEvents, json);
        Map<String, Object> waiting = longCheckpoint("awaiting_user_review", 1);
        waiting.put("activeArtifactId", "artifact-1");
        waitingService.saveCheckpoint(
                checkpoint("checkpoint-waiting", 1, waiting), "user-1", "novel-1");

        assertThat(waitingRepository.lastBoundary).isNotNull();
        assertThat(waitingRepository.lastBoundary.eventType())
                .isEqualTo("artifact_awaiting_user_approval");
        assertThat(waitingEvents.replay("task-1", null)).isEmpty();
    }

    @Test
    void 长篇完成结果不携带中短篇判别字段时必须正常收敛() {
        RecordingRepository repository = new RecordingRepository();
        WritingCallbackService service = new WritingCallbackService(
                repository, new InMemoryWritingEventStore(CLOCK), json);
        RunCompletionCallback body = new RunCompletionCallback(
                "complete-1",
                "job-1",
                OffsetDateTime.now(CLOCK),
                "1.1",
                Map.of("finalResponse", "复审完成"),
                "task-1",
                1,
                "task-1");

        assertThat(service.complete(body).getDisposition().getValue()).isEqualTo("applied");
    }

    private static AgentEvent event(
            String eventId, int sequence, Map<String, Object> data) {
        return new AgentEvent(
                data,
                "agent_status",
                eventId,
                "job-1",
                OffsetDateTime.now(CLOCK),
                "1.1",
                "task-1",
                sequence,
                "task-1");
    }

    private static CheckpointCallback checkpoint(
            String eventId, int sequence, Map<String, Object> value) {
        return new CheckpointCallback(
                value,
                eventId,
                "job-1",
                OffsetDateTime.now(CLOCK),
                "1.1",
                "task-1",
                sequence,
                "task-1");
    }

    private static Map<String, Object> longCheckpoint(String phase, int sequence) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("taskId", "task-1");
        value.put("userId", "user-1");
        value.put("novelId", "novel-1");
        value.put("chapterId", "chapter-1");
        value.put("targetWordCount", 4_000);
        value.put("conversationHistory", java.util.List.of());
        value.put("currentOperation", Map.of("kind", "review_chapter"));
        value.put("operationStage", "reviewing");
        value.put("eventSequence", sequence);
        value.put("phase", phase);
        return value;
    }

    private static final class RecordingRepository implements WritingCallbackRepository {

        private int markProcessingCalls;
        private WritingBoundaryEvent lastBoundary;

        @Override
        public TaskResources resources(String taskId) {
            return new TaskResources("novel-1", "user-1");
        }

        @Override
        public WritingCallbackAcceptance authorize(String taskId, String jobId) {
            return accepted("pending", 0);
        }

        @Override
        public WritingCallbackAcceptance markProcessing(
                String taskId, String jobId, int sequence) {
            markProcessingCalls++;
            return accepted("processing", 0);
        }

        @Override
        public WritingCallbackAcceptance saveCheckpoint(
                String taskId,
                String jobId,
                String serialized,
                String phase,
                int sequence,
                WritingBoundaryEvent boundary) {
            lastBoundary = boundary;
            return new WritingCallbackAcceptance(
                    true,
                    0,
                    false,
                    null,
                    phase,
                    "awaiting_user_review".equals(phase) ? "succeeded" : "processing",
                    boundary == null ? null : "outbox-1");
        }

        @Override
        public WritingCallbackAcceptance complete(
                String taskId,
                String jobId,
                Map<String, Object> result,
                String visibleResponse,
                int sequence,
                WritingBoundaryEvent boundary) {
            return accepted("succeeded", 0);
        }

        @Override
        public WritingCallbackAcceptance fail(
                String taskId,
                String jobId,
                String code,
                int sequence,
                WritingBoundaryEvent boundary) {
            return accepted("failed", 0);
        }

        private static WritingCallbackAcceptance accepted(String status, int sequence) {
            return new WritingCallbackAcceptance(
                    true, sequence, false, null, "active", status, null);
        }
    }
}
