package cn.inkforge.core.workflows.protocol;

import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Locale;

/** V2 execution 协议 datetime 的唯一格式；与 Pydantic JSON mode 保持一致。 */
public final class ExecutionProtocolDateTime {

    private static final DateTimeFormatter SECONDS =
            DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss", Locale.ROOT);

    private ExecutionProtocolDateTime() {}

    /** 协议最多保留微秒，且不改变原 offset。 */
    public static OffsetDateTime normalize(OffsetDateTime value) {
        return value == null ? null : value.truncatedTo(ChronoUnit.MICROS);
    }

    /** 秒位始终存在；非零小数固定六位；UTC 使用 {@code Z}。 */
    public static String format(OffsetDateTime value) {
        OffsetDateTime normalized = normalize(value);
        if (normalized == null) return null;
        StringBuilder result = new StringBuilder(SECONDS.format(normalized));
        int micros = normalized.getNano() / 1_000;
        if (micros != 0) {
            String paddedMicros = Integer.toString(1_000_000 + micros);
            result.append('.').append(paddedMicros, 1, paddedMicros.length());
        }
        return result.append(normalized.getOffset().getId()).toString();
    }
}
