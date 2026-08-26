package cn.inkforge.core.writing.application;

import cn.inkforge.core.platform.redis.RedisUnavailableException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.domain.WritingEventSequenceGap;
import cn.inkforge.core.writing.domain.WritingEventSourceConflict;
import cn.inkforge.core.writing.domain.WritingOutboxRecord;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

/** 把 PostgreSQL 边界事实可靠发布到 Redis Stream。 */
public final class WritingOutboxPublisher {

    private static final Set<String> EVENT_TYPES = Set.of(
            "completed", "error", "artifact_awaiting_user_approval");
    private static final Duration RETENTION = Duration.ofDays(7);

    private final WritingOutboxRepository repository;
    private final WritingEventStore events;
    private final Clock clock;
    private final int batchSize;
    private final int leaseSeconds;
    private final Duration interval;
    private final Duration cleanupInterval;
    private final AtomicBoolean stop = new AtomicBoolean();
    private LocalDateTime nextCleanupAt;

    public WritingOutboxPublisher(
            WritingOutboxRepository repository,
            WritingEventStore events,
            Clock clock,
            int batchSize,
            int leaseSeconds,
            Duration interval,
            Duration cleanupInterval) {
        this.repository = Objects.requireNonNull(repository);
        this.events = Objects.requireNonNull(events);
        this.clock = Objects.requireNonNull(clock);
        if (batchSize < 1
                || leaseSeconds < 1
                || interval == null
                || interval.isZero()
                || interval.isNegative()
                || cleanupInterval == null
                || cleanupInterval.isZero()
                || cleanupInterval.isNegative()) {
            throw new IllegalArgumentException("Outbox publisher 配置无效");
        }
        this.batchSize = batchSize;
        this.leaseSeconds = leaseSeconds;
        this.interval = interval;
        this.cleanupInterval = cleanupInterval;
    }

    public int runOnce() {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        List<WritingOutboxRecord> records = repository.claimDue(
                now, batchSize, leaseSeconds);
        int published = 0;
        for (WritingOutboxRecord record : records) {
            if (record.leaseToken() == null) continue;
            String contractError = contractError(record);
            if (contractError != null) {
                repository.markBlocked(record.id(), record.leaseToken(), contractError);
                continue;
            }
            if ("artifact_awaiting_user_approval".equals(record.eventType())
                    && repository.supersedeWaitingIfStale(
                            record.id(), record.leaseToken(), now)) {
                continue;
            }
            try {
                @SuppressWarnings("unchecked")
                Map<String, Object> payload = (Map<String, Object>) record.payload();
                var event = events.appendAgent(
                        record.taskId(),
                        record.sourceEventId(),
                        record.sourceSequence(),
                        record.eventType(),
                        payload,
                        record.durableBaseline(),
                        true);
                if (repository.markPublished(
                        record.id(), record.leaseToken(), event.id())) {
                    published++;
                }
            } catch (WritingEventSequenceGap exception) {
                if ("artifact_awaiting_user_approval".equals(record.eventType())
                        && repository.supersedeWaitingIfStale(
                                record.id(), record.leaseToken(), now)) {
                    continue;
                }
                repository.markBlocked(
                        record.id(), record.leaseToken(), "OUTBOX_EVENT_SEQUENCE_GAP");
            } catch (WritingEventSourceConflict exception) {
                repository.markBlocked(
                        record.id(), record.leaseToken(), "OUTBOX_EVENT_SOURCE_CONFLICT");
            } catch (RedisUnavailableException exception) {
                repository.scheduleRetry(
                        record.id(),
                        record.leaseToken(),
                        now.plusSeconds(retryDelay(record.attemptCount())),
                        "OUTBOX_REDIS_UNAVAILABLE");
            }
        }
        return published;
    }

    public void run() throws InterruptedException {
        while (!stop.get()) {
            runOnce();
            cleanupIfDue();
            synchronized (stop) {
                if (!stop.get()) stop.wait(interval.toMillis());
            }
        }
    }

    public void requestStop() {
        stop.set(true);
        synchronized (stop) {
            stop.notifyAll();
        }
    }

    private void cleanupIfDue() {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        if (nextCleanupAt != null && now.isBefore(nextCleanupAt)) return;
        repository.cleanupTerminal(now.minus(RETENTION));
        nextCleanupAt = now.plus(cleanupInterval);
    }

    private static String contractError(WritingOutboxRecord record) {
        if (!(record.payload() instanceof Map<?, ?>)) return "OUTBOX_PAYLOAD_INVALID";
        if (record.taskId() == null
                || record.taskId().isBlank()
                || record.sourceEventId() == null
                || record.sourceEventId().isBlank()
                || record.dedupeKey() == null
                || record.dedupeKey().isBlank()
                || record.sourceSequence() <= 0
                || record.durableBaseline() < 0
                || record.durableBaseline() >= record.sourceSequence()
                || !EVENT_TYPES.contains(record.eventType())) {
            return "OUTBOX_CONTRACT_INVALID";
        }
        return null;
    }

    private static int retryDelay(int attemptCount) {
        int exponent = Math.max(0, attemptCount - 1);
        return exponent >= 6 ? 60 : Math.max(1, 1 << exponent);
    }
}
