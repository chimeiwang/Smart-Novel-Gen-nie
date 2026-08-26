package cn.inkforge.core.references.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class RagRulesTest {

    @Test
    void 分块必须按Unicode码点无损保留全部来源且超出64块明确失败() {
        String source = "😀  第一行\r\n最后一行  ".repeat(400);
        List<String> chunks = RagRules.chunks(source);

        assertThat(String.join("", chunks)).isEqualTo(source);
        assertThat(chunks).allSatisfy(chunk ->
                assertThat(chunk.codePointCount(0, chunk.length())).isLessThanOrEqualTo(1_800));

        String overflow = "😀".repeat(1_800 * 64 + 1);
        assertCode(() -> RagRules.chunks(overflow), 413, "EMBEDDING_CAPACITY_EXCEEDED");
    }

    @Test
    void 哈希向量和topK必须保持精确边界且不截断非法输入() {
        assertThat(RagRules.sha256("  正文\r\n😀  "))
                .isEqualTo("eaa2b0a4abf0d60790ecff6738510a46b0f4531ae24626d31dc20a842d5e51cc");
        List<List<BigDecimal>> values = List.of(
                List.of(BigDecimal.ONE, BigDecimal.TWO),
                List.of(BigDecimal.ZERO, new BigDecimal("3.5")));
        assertThat(RagRules.embeddings(values)).isSameAs(values);
        assertThat(RagRules.topK(1)).isEqualTo(1);
        assertThat(RagRules.topK(20)).isEqualTo(20);
        assertCode(() -> RagRules.topK(21), 422, "RAG_TOP_K_INVALID");
        assertCode(
                () -> RagRules.embeddings(List.of(List.of(BigDecimal.ONE), List.of(
                        BigDecimal.ONE, BigDecimal.TWO))),
                422,
                "EMBEDDING_INVALID");
        List<BigDecimal> oversized = new ArrayList<>();
        for (int index = 0; index < 4_097; index++) oversized.add(BigDecimal.ONE);
        assertCode(
                () -> RagRules.embeddings(List.of(oversized)),
                413,
                "EMBEDDING_CAPACITY_EXCEEDED");
    }

    @Test
    void 任务身份必须与Python按资料哈希和毫秒代次完全一致() {
        RagJobIdentity identity = RagJobIdentity.create(
                "reference-1",
                "a".repeat(64),
                OffsetDateTime.parse("2026-08-25T04:00:00.123Z"));

        assertThat(identity.taskId()).isEqualTo("rag-783ee574c0a9e060970bfc964fa7d223");
        assertThat(identity.runId()).isEqualTo("rag-ef0f36cc14504d4129c6ec8b8ab21a87");
    }

    private static void assertCode(Runnable action, int status, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(status);
                    assertThat(error.code()).isEqualTo(code);
                });
    }
}
