package cn.inkforge.core.workflows.protocol;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class ExecutionCanonicalJsonTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void 必须与Python生成字节级相同的执行哈希材料() {
        Map<String, Object> fixture = fixture();
        assertThat(fixture.get("algorithm")).isEqualTo(ExecutionCanonicalJson.ALGORITHM);
        @SuppressWarnings("unchecked")
        Map<String, Object> vector = ((List<Map<String, Object>>) fixture.get("vectors")).getFirst();
        Object value = vector.get("value");

        byte[] canonical = ExecutionCanonicalJson.bytes(value);

        assertThat(new String(canonical, StandardCharsets.UTF_8))
                .isEqualTo(vector.get("canonicalUtf8"));
        assertThat(ExecutionCanonicalJson.sha256(value))
                .isEqualTo(vector.get("sha256"));
    }

    @Test
    void 拒绝不稳定数值非法对象键和未配对代理字符() {
        assertThatThrownBy(() -> ExecutionCanonicalJson.bytes(Double.NaN))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> ExecutionCanonicalJson.bytes(Map.of(1, "非法")))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> ExecutionCanonicalJson.bytes("\ud800"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> fixture() {
        InputStream input = ExecutionCanonicalJsonTest.class
                .getResourceAsStream("/agent-execution/hash-vectors.v1.json");
        if (input == null) throw new IllegalStateException("缺少共享执行哈希向量");
        return JSON.readValue(input, Map.class);
    }
}
