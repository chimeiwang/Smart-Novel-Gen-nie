package cn.inkforge.core.writing.application;

import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.time.Clock;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;

/** 阻塞行或超过五分钟未发布的边界事实都会使服务未就绪。 */
public final class WritingOutboxReadiness {

    private final WritingOutboxRepository repository;
    private final Clock clock;
    private final Duration staleAfter;
    private volatile String errorCode;

    public WritingOutboxReadiness(
            WritingOutboxRepository repository, Clock clock, Duration staleAfter) {
        this.repository = Objects.requireNonNull(repository);
        this.clock = Objects.requireNonNull(clock);
        if (staleAfter == null || staleAfter.isZero() || staleAfter.isNegative()) {
            throw new IllegalArgumentException("Outbox 健康检查积压阈值无效");
        }
        this.staleAfter = staleAfter;
    }

    public boolean check() {
        errorCode = "OUTBOX_HEALTH_UNAVAILABLE";
        var status = repository.health(DatabaseTimestamp.now(clock), staleAfter);
        if (status.blockedCount() > 0 && status.staleUnpublishedCount() > 0) {
            errorCode = "OUTBOX_BLOCKED_AND_STALE_BACKLOG";
        } else if (status.blockedCount() > 0) {
            errorCode = "OUTBOX_BLOCKED";
        } else if (status.staleUnpublishedCount() > 0) {
            errorCode = "OUTBOX_STALE_BACKLOG";
        } else {
            errorCode = null;
        }
        return errorCode == null;
    }

    public Map<String, String> errorCodes() {
        return errorCode == null ? Map.of() : Map.of("writing_outbox", errorCode);
    }
}
