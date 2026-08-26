package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.platform.redis.RedisUnavailableException;
import cn.inkforge.core.writing.domain.WritingEvent;
import cn.inkforge.core.writing.domain.WritingOutboxHealth;
import cn.inkforge.core.writing.domain.WritingOutboxRecord;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WritingOutboxPublisherTest {

    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-25T11:00:00Z"), ZoneOffset.UTC);
    private static final LocalDateTime NOW =
            LocalDateTime.parse("2026-08-25T11:00:00");

    @Test
    void 单条Redis失败应退避且不阻断同批其他边界事件() {
        RecordingRepository repository = new RecordingRepository(List.of(
                record("outbox-fail", 1), record("outbox-good", 2)));
        WritingEventStore events = new WritingEventStore() {
            @Override
            public WritingEvent appendAgent(
                    String taskId,
                    String sourceEventId,
                    int sequence,
                    String event,
                    Map<String, Object> data,
                    int durableBaseline,
                    boolean allowRebase) {
                if ("event-1".equals(sourceEventId)) throw new RedisUnavailableException();
                return new WritingEvent(
                        "redis-2", event, data, OffsetDateTime.now(CLOCK), sourceEventId, sequence);
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
            public List<WritingEvent> replay(String taskId, String lastEventId) {
                return List.of();
            }
        };
        WritingOutboxPublisher publisher = publisher(repository, events);

        assertThat(publisher.runOnce()).isEqualTo(1);
        assertThat(repository.retries).containsExactly("outbox-fail");
        assertThat(repository.published).containsExactly("outbox-good");
    }

    @Test
    void 损坏的耐久载荷必须阻塞而不能发送或无限重试() {
        WritingOutboxRecord invalid = new WritingOutboxRecord(
                "outbox-invalid",
                "task-1",
                "command-1",
                "event-invalid",
                1,
                0,
                "dedupe-invalid",
                "completed",
                "not-an-object",
                "delivering",
                1,
                NOW,
                "lease-invalid",
                NOW.plusSeconds(30));
        RecordingRepository repository = new RecordingRepository(List.of(invalid));
        WritingEventStore events = new NoopEventStore();

        assertThat(publisher(repository, events).runOnce()).isZero();
        assertThat(repository.blocked)
                .containsExactly(Map.entry("outbox-invalid", "OUTBOX_PAYLOAD_INVALID"));
    }

    private static WritingOutboxPublisher publisher(
            WritingOutboxRepository repository, WritingEventStore events) {
        return new WritingOutboxPublisher(
                repository,
                events,
                CLOCK,
                20,
                30,
                Duration.ofMillis(10),
                Duration.ofHours(1));
    }

    private static WritingOutboxRecord record(String id, int sequence) {
        return new WritingOutboxRecord(
                id,
                "task-1",
                "command-1",
                "event-" + sequence,
                sequence,
                sequence - 1,
                "dedupe-" + sequence,
                "completed",
                Map.of("taskId", "task-1"),
                "delivering",
                1,
                NOW,
                "lease-" + sequence,
                NOW.plusSeconds(30));
    }

    private static final class RecordingRepository implements WritingOutboxRepository {

        private final List<WritingOutboxRecord> records;
        private final List<String> published = new ArrayList<>();
        private final List<String> retries = new ArrayList<>();
        private final List<Map.Entry<String, String>> blocked = new ArrayList<>();

        private RecordingRepository(List<WritingOutboxRecord> records) {
            this.records = records;
        }

        @Override
        public List<WritingOutboxRecord> claimDue(LocalDateTime now, int limit, int leaseSeconds) {
            return records;
        }

        @Override
        public boolean markPublished(String outboxId, String leaseToken, String redisEventId) {
            published.add(outboxId);
            return true;
        }

        @Override
        public boolean scheduleRetry(String outboxId, String leaseToken, LocalDateTime nextAttemptAt, String errorCode) {
            retries.add(outboxId);
            return true;
        }

        @Override
        public boolean markBlocked(String outboxId, String leaseToken, String errorCode) {
            blocked.add(Map.entry(outboxId, errorCode));
            return true;
        }

        @Override
        public boolean supersedeWaitingIfStale(String outboxId, String leaseToken, LocalDateTime now) {
            return false;
        }

        @Override
        public int cleanupTerminal(LocalDateTime olderThan) {
            return 0;
        }

        @Override
        public WritingOutboxHealth health(LocalDateTime now, Duration staleAfter) {
            return new WritingOutboxHealth(0, 0);
        }

        @Override
        public Map<String, String> replayDispositions(List<WritingEvent> events) {
            return Map.of();
        }
    }

    private static final class NoopEventStore implements WritingEventStore {

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
            throw new AssertionError("损坏 Outbox 不应投递");
        }

        @Override
        public List<WritingEvent> replay(String taskId, String lastEventId) {
            return List.of();
        }
    }
}
