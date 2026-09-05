package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.text.TextLength;
import cn.inkforge.core.platform.http.ApiException;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class DurableChapterDraftArtifactTest {
    private static final String HASH = "a".repeat(64);

    @Test
    void 完整Unicode正文只保存一次且重建全文目标和Diff() {
        String content = "正文😀\n\uFEFF\u0085" + "完整长文".repeat(20_000);
        var output = output(content);
        var stored = DurableChapterDraftArtifact.create("bundle", HASH, "chapter", output, "step", HASH);
        assertThat(stored.payload()).containsEntry("content", content).doesNotContainKeys("before", "after", "source", "replacement");
        assertThat(stored.diff()).doesNotContainKeys("before", "after", "content");
        var rebuilt = DurableChapterDraftArtifact.reconstruct(stored.payload(), stored.diff(), "bundle", HASH, "chapter", "旧正文😀");
        assertThat(rebuilt.payload()).containsEntry("kind", "chapter_draft").containsEntry("operation", "write_chapter")
                .containsEntry("content", content).containsEntry("target", Map.of("mode", "existing_chapter", "chapterId", "chapter"));
        assertThat(rebuilt.diff()).containsEntry("before", "旧正文😀").containsEntry("after", content);
        assertThat(DurableChapterDraftArtifact.output(stored.payload())).isEqualTo(output);
    }

    @Test
    void 严格拒绝空白摘要额外字段和伪造派生值且不截断() {
        for (String corruption : java.util.List.of("blank", "summary", "extra", "hash", "count")) {
            Map<String, Object> value = new LinkedHashMap<>(output("正文😀\u001c"));
            switch (corruption) {
                case "blank" -> value.putAll(output("\u0085\u3000\ufeff\n"));
                case "summary" -> value.put("summary", "\u0085");
                case "extra" -> value.put("target", "模型伪造");
                case "hash" -> value.put("contentSha256", HASH);
                case "count" -> value.put("wordCount", 999);
                default -> throw new AssertionError();
            }
            assertThatThrownBy(() -> DurableChapterDraftArtifact.validateOutput(value)).isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void 来源绑定损坏必须拒绝详情() {
        var stored = DurableChapterDraftArtifact.create("bundle", HASH, "chapter", output("正文"), "step", HASH);
        assertThatThrownBy(() -> DurableChapterDraftArtifact.reconstruct(stored.payload(), stored.diff(), "other", HASH, "chapter", ""))
                .isInstanceOf(ApiException.class);
    }

    @Test
    void 非空正文严格使用跨语言计数集合而非平台广义空白分类() {
        assertThat(DurableChapterDraftArtifact.deriveOutput("\u001c", "\u001c")).containsEntry("wordCount", 1);
        assertThat(DurableChapterDraftArtifact.deriveOutput("摘要", "\u200b")).containsEntry("wordCount", 1);
        assertThatThrownBy(() -> DurableChapterDraftArtifact.deriveOutput("摘要", "\u0085\uFEFF\u3000"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 场景改写保留真实操作且旧写章持久形状不变() {
        var output = output("完整改写后的章节😀");
        var legacy = DurableChapterDraftArtifact.create("bundle", HASH, "chapter", output, "step", HASH);
        var explicitWrite = DurableChapterDraftArtifact.create(
                "write_chapter", "bundle", HASH, "chapter", output, "step", HASH);
        var scene = DurableChapterDraftArtifact.create(
                "rewrite_scene", "bundle", HASH, "chapter", output, "step", HASH);

        assertThat(explicitWrite).isEqualTo(legacy);
        assertThat(legacy.payload()).containsEntry("operation", "write_chapter");
        assertThat(legacy.payload().keySet()).isEqualTo(scene.payload().keySet());
        assertThat(scene.payload()).containsEntry("operation", "rewrite_scene");
        assertThat(DurableChapterDraftArtifact.reconstruct(
                        "rewrite_scene", scene.payload(), scene.diff(), "bundle", HASH,
                        "chapter", "原章节")
                .payload()).containsEntry("operation", "rewrite_scene");
        assertThatThrownBy(() -> DurableChapterDraftArtifact.reconstruct(
                        scene.payload(), scene.diff(), "bundle", HASH, "chapter", "原章节"))
                .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> DurableChapterDraftArtifact.create(
                        "plan_chapter", "bundle", HASH, "chapter", output, "step", HASH))
                .isInstanceOf(IllegalArgumentException.class);
    }

    static Map<String, Object> output(String content) {
        return Map.of("summary", "完整摘要", "content", content, "contentSha256", DurableSelectionArtifact.sha256(content),
                "wordCount", TextLength.count(content));
    }
}
