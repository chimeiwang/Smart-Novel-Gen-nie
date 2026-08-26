package cn.inkforge.core.platform.idempotency;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class CommandIdempotencyTest {

    private final ObjectMapper json = new ObjectMapper();

    @Test
    void Java必须与Python生成字节级相同的决定指纹() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("expectedRevision", 2);
        body.put("decision", "approve");
        body.put("editedContent", null);
        body.put("selectedUpdateRefs", List.of(
                Map.of("section", "characters", "index", 0),
                nullableMap("section", "outline", "index", null)));
        body.put("userMessage", "继续😀");

        byte[] canonical = CommandIdempotency.canonicalJsonBytes(
                Map.of(
                        "commandKind", "artifact_decision",
                        "resourceIdentity", Map.of("artifactId", "artifact-1"),
                        "body", body),
                json);

        assertThat(new String(canonical, StandardCharsets.UTF_8))
                .isEqualTo("{\"body\":{\"decision\":\"approve\",\"editedContent\":null,"
                        + "\"expectedRevision\":2,\"selectedUpdateRefs\":[{\"index\":0,"
                        + "\"section\":\"characters\"},{\"index\":null,\"section\":\"outline\"}],"
                        + "\"userMessage\":\"继续😀\"},\"commandKind\":\"artifact_decision\","
                        + "\"resourceIdentity\":{\"artifactId\":\"artifact-1\"}}");
        assertThat(CommandIdempotency.requestFingerprint(
                        "artifact_decision",
                        Map.of("artifactId", "artifact-1"),
                        body,
                        json))
                .isEqualTo("160bfb173b499b24b1aa93e5ffd8f95d04664a2f595ae894e5c8e41555c4da6d");
    }

    @Test
    void 锁键和新旧持久化键必须兼容Python() {
        assertThat(CommandIdempotency.advisoryLockKey("user-1", "request-00000001"))
                .isEqualTo(-2782141057241146889L);
        assertThat(CommandIdempotency.envelopedKey("user-1", "request-00000001"))
                .isEqualTo("v1:user-1:request-00000001");
        assertThat(CommandIdempotency.legacyKey("user-1", "request-00000001"))
                .isEqualTo("user-1:request-00000001");
    }

    @Test
    void 非有限浮点与非字符串对象键必须拒绝() {
        assertThatThrownBy(() -> CommandIdempotency.canonicalJsonBytes(
                        Map.of("value", Double.NaN), json))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> CommandIdempotency.canonicalJsonBytes(
                        Map.of(1, "value"), json))
                .isInstanceOf(IllegalArgumentException.class);
    }

    private static Map<String, Object> nullableMap(
            String firstKey, Object firstValue, String secondKey, Object secondValue) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(firstKey, firstValue);
        result.put(secondKey, secondValue);
        return result;
    }
}
