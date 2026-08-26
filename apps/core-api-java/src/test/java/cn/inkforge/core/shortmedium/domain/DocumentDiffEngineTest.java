package cn.inkforge.core.shortmedium.domain;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class DocumentDiffEngineTest {

    @Test
    void 差异位置使用Unicode码点且确认哈希兼容Python基线() {
        String before = "第一段😀\n\n旧段";
        String after = "第一段😀\n\n新段\n\n尾部";

        DocumentDiff initial = DocumentDiffEngine.build(
                before, after, "version-1", "version-2");
        DocumentDiff bound = DocumentDiffEngine.bind(
                initial,
                "manuscript",
                "chapter-1",
                "version-1",
                ShortMediumText.sha256(before),
                "version-2");

        assertThat(initial.fromWordCount()).isEqualTo(6);
        assertThat(initial.toWordCount()).isEqualTo(8);
        assertThat(initial.confirmationHash())
                .isEqualTo("3cb1162e7e24d0a88e2193895ea6923bb5699b82e88dcc82f06ee519e45945fd");
        assertThat(initial.blocks()).containsExactly(new DocumentDiffBlock(
                "replace", 6, 8, 6, 12, "旧段", "新段\n\n尾部"));
        assertThat(bound.confirmationHash())
                .isEqualTo("e23459c5b3317c78d55c399d49e937edd110b26c387e76bcc7b49f0e10d97cb4");
    }

    @Test
    void 超长正文差异保留完整尾部且不返回equal块() {
        String before = "第一段😀\n\n" + "旧内容".repeat(20_000) + "\n\n旧尾部";
        String after = "第一段😀\n\n" + "新内容".repeat(20_000) + "\n\n八万字尾部标记";

        DocumentDiff result = DocumentDiffEngine.build(
                before, after, "version-1", "version-2");

        assertThat(result.blocks()).allMatch(block -> !"equal".equals(block.type()));
        assertThat(result.blocks())
                .anyMatch(block -> block.newText() != null
                        && block.newText().contains("八万字尾部标记"));
        assertThat(result.wordCountDelta())
                .isEqualTo(result.toWordCount() - result.fromWordCount());
    }
}
