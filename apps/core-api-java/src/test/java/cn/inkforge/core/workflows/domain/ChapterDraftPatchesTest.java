package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class ChapterDraftPatchesTest {
    @Test
    void 同原文定位逆序应用且相同提议去重保留完整Unicode() {
        var first = new ChapterDraftPatches.Proposal("😀乙", "新段", 1, 3);
        var second = new ChapterDraftPatches.Proposal("丁", "", null, null);
        assertThat(ChapterDraftPatches.apply("甲😀乙丙丁", List.of(first, second, first))).isEqualTo("甲新段丙");
    }

    @Test
    void 零命中多命中重叠范围漂移和清空正文均原子拒绝() {
        for (var patches : List.of(
                List.of(new ChapterDraftPatches.Proposal("不存在", "新", null, null)),
                List.of(new ChapterDraftPatches.Proposal("甲", "新", null, null)),
                List.of(new ChapterDraftPatches.Proposal("甲乙", "新", null, null), new ChapterDraftPatches.Proposal("乙甲", "旧", null, null)),
                List.of(new ChapterDraftPatches.Proposal("乙", "新", 0, 1)),
                List.of(new ChapterDraftPatches.Proposal("甲乙甲", "", null, null)))) {
            assertThatThrownBy(() -> ChapterDraftPatches.apply("甲乙甲", patches)).isInstanceOf(ChapterDraftPatches.Rejected.class);
        }
        assertThatThrownBy(() -> ChapterDraftPatches.apply("甲", List.of(
                new ChapterDraftPatches.Proposal("甲", "乙", null, null), new ChapterDraftPatches.Proposal("甲", "丙", null, null))))
                .isInstanceOf(ChapterDraftPatches.Rejected.class);
    }

    @Test
    void 相同建议去重后最多二十项且纯空格定位不被裁剪() {
        String content = "正文 " + IntStream.range(0, 21).mapToObj(i -> "【" + i + "】").collect(java.util.stream.Collectors.joining());
        var patches = IntStream.range(0, 21).mapToObj(i -> new ChapterDraftPatches.Proposal("【" + i + "】", "新", null, null)).toList();
        assertThat(ChapterDraftPatches.apply(content, patches.subList(0, 20))).isEqualTo("正文 " + "新".repeat(20) + "【20】");
        assertThatThrownBy(() -> ChapterDraftPatches.apply(content, patches)).isInstanceOf(ChapterDraftPatches.Rejected.class).hasMessage("PATCH_COUNT_EXCEEDED");
        assertThat(ChapterDraftPatches.apply("甲  乙", List.of(new ChapterDraftPatches.Proposal("  ", "", null, null)))).isEqualTo("甲乙");
    }
}
