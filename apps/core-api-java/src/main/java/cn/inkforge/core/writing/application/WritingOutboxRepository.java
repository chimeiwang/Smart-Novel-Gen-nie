package cn.inkforge.core.writing.application;

import cn.inkforge.core.writing.domain.WritingEvent;
import cn.inkforge.core.writing.domain.WritingOutboxHealth;
import cn.inkforge.core.writing.domain.WritingOutboxRecord;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/** 写作边界事件的租约、重试、清理与 SSE 可见性端口。 */
public interface WritingOutboxRepository {

    List<WritingOutboxRecord> claimDue(
            LocalDateTime now, int limit, int leaseSeconds);

    boolean markPublished(String outboxId, String leaseToken, String redisEventId);

    boolean scheduleRetry(
            String outboxId,
            String leaseToken,
            LocalDateTime nextAttemptAt,
            String errorCode);

    boolean markBlocked(String outboxId, String leaseToken, String errorCode);

    boolean supersedeWaitingIfStale(
            String outboxId, String leaseToken, LocalDateTime now);

    int cleanupTerminal(LocalDateTime olderThan);

    WritingOutboxHealth health(
            LocalDateTime now, Duration staleAfter);

    Map<String, String> replayDispositions(List<WritingEvent> events);
}
