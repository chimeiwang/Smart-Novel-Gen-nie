package cn.inkforge.core.workflows.protocol;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.OffsetDateTime;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class ExecutionProtocolDateTimeTest {

    @Test
    void 秒位始终存在且UTC使用Z() {
        assertThat(ExecutionProtocolDateTime.format(
                        OffsetDateTime.parse("2026-09-01T02:00:00Z")))
                .isEqualTo("2026-09-01T02:00:00Z");
    }

    @Test
    void 非零小数固定六位并保留原Offset() {
        Locale original = Locale.getDefault(Locale.Category.FORMAT);
        try {
            Locale.setDefault(Locale.Category.FORMAT, Locale.forLanguageTag("ar-EG"));
            assertThat(ExecutionProtocolDateTime.format(
                            OffsetDateTime.parse("2026-09-01T02:00:00.123Z")))
                    .isEqualTo("2026-09-01T02:00:00.123000Z");
            assertThat(ExecutionProtocolDateTime.format(
                            OffsetDateTime.parse("2026-09-01T10:00:00.123456789+08:00")))
                    .isEqualTo("2026-09-01T10:00:00.123456+08:00");
        } finally {
            Locale.setDefault(Locale.Category.FORMAT, original);
        }
    }
}
