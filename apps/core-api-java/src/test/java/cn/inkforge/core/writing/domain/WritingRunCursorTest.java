package cn.inkforge.core.writing.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class WritingRunCursorTest {

    private final WritingRunCursor cursor = new WritingRunCursor(new ObjectMapper());

    @Test
    void 游标只往返创建时间和任务标识并统一为UTC() {
        OffsetDateTime createdAt = OffsetDateTime.of(
                LocalDateTime.of(2026, 8, 5, 20, 30), ZoneOffset.ofHours(8));

        String encoded = cursor.encode(createdAt, "task-1");
        WritingRunCursor.Position decoded = cursor.decode(encoded);

        assertThat(decoded.createdAt()).isEqualTo(OffsetDateTime.parse("2026-08-05T12:30:00Z"));
        assertThat(decoded.taskId()).isEqualTo("task-1");
        assertThat(encoded).doesNotContain("=");
    }

    @Test
    void 游标拒绝填充缺字段和额外字段() {
        assertThatThrownBy(() -> cursor.decode("e30="))
                .isInstanceOf(IllegalArgumentException.class);
        assertInvalid("{\"createdAt\":\"2026-08-05T12:30:00Z\"}");
        assertInvalid("{\"createdAt\":\"2026-08-05T12:30:00Z\",\"id\":\"t\",\"x\":1}");
        assertInvalid("{\"createdAt\":\"2026-08-05T12:30:00\",\"id\":\"t\"}");
    }

    private void assertInvalid(String json) {
        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(json.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        assertThatThrownBy(() -> cursor.decode(encoded))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
