package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

class WritingCommandPayloadTest {

    private final ObjectMapper json = JsonMapper.builder().build();

    @Test
    void 兼容载荷直接作为Job而版本化载荷只暴露Job() {
        var legacy = WritingCommandPayload.parse(
                "start", "{\"resume\":false,\"chapterId\":\"chapter-1\"}", json);
        assertThat(legacy.logicalKind()).isEqualTo("start");
        assertThat(legacy.job()).containsEntry("chapterId", "chapter-1");

        var enveloped = WritingCommandPayload.parse(
                "resume",
                json.writeValueAsString(Map.of(
                        "_inkforgeCommand",
                        Map.of(
                                "schemaVersion", 1,
                                "clientRequestId", "request-12345678",
                                "commandKind", "cancel",
                                "resourceIdentity", Map.of("taskId", "task-1"),
                                "normalizedBody", Map.of(),
                                "requestFingerprint", "a".repeat(64)),
                        "job",
                        Map.of("cancelledJobId", "command-1"))),
                json);
        assertThat(enveloped.logicalKind()).isEqualTo("cancel");
        assertThat(enveloped.job()).containsOnlyKeys("cancelledJobId");
    }

    @Test
    void 损坏或扩展的版本化信封必须拒绝而不能猜测() {
        assertThatThrownBy(() -> WritingCommandPayload.parse(
                        "resume",
                        "{\"_inkforgeCommand\":{},\"job\":{},\"extra\":true}",
                        json))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("写作命令持久载荷无效");
        assertThatThrownBy(() -> WritingCommandPayload.parse(
                        "resume", "[]", json))
                .isInstanceOf(IllegalStateException.class);
    }
}
