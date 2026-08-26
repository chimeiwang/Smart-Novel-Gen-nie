package cn.inkforge.core.platform.time;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;

/** PostgreSQL {@code TIMESTAMP(3)} 的统一 UTC 转换，避免各领域产生精度与时区漂移。 */
public final class DatabaseTimestamp {

    private DatabaseTimestamp() {}

    public static LocalDateTime now(Clock clock) {
        return LocalDateTime.ofInstant(
                clock.instant().truncatedTo(ChronoUnit.MILLIS), ZoneOffset.UTC);
    }

    public static LocalDateTime next(Clock clock, LocalDateTime current) {
        LocalDateTime wallClock = now(clock);
        LocalDateTime monotonic = current.plus(1, ChronoUnit.MILLIS);
        return wallClock.isAfter(monotonic) ? wallClock : monotonic;
    }

    public static OffsetDateTime api(LocalDateTime value) {
        return value == null ? null : value.atOffset(ZoneOffset.UTC);
    }

    public static LocalDateTime database(OffsetDateTime value) {
        return value == null
                ? null
                : LocalDateTime.ofInstant(value.toInstant(), ZoneOffset.UTC);
    }

    public static boolean sameInstant(LocalDateTime current, OffsetDateTime expected) {
        if (current == null || expected == null) {
            return current == null && expected == null;
        }
        Instant currentInstant = current.toInstant(ZoneOffset.UTC);
        return currentInstant.equals(expected.toInstant());
    }
}
