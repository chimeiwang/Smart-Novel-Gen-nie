package cn.inkforge.core.video.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.SeedanceShotPromptSpec;
import java.util.List;
import org.junit.jupiter.api.Test;

class SeedancePromptCompilerTest {

    @Test
    void 必须按冻结顺序保留表演表情连续性和负向约束() {
        var specification = new SeedanceShotPromptSpec(
                        " 风声渐强。 ",
                        " 缓慢推近，保持眼平机位； ",
                        " 林岚站在昏暗走廊。 ",
                        " 她抬头望向门外！ ")
                .performance("呼吸短促。")
                .expressionAndGaze("惊惧，视线锁住门缝？")
                .continuity("黑色外套与上一镜一致。")
                .negativeConstraints(List.of("不要字幕。", "不要镜头抖动！"));

        assertThat(SeedancePromptCompiler.compile(specification, "16:9", 5_500))
                .isEqualTo(
                        "16:9 画幅，5.5 秒。林岚站在昏暗走廊。她抬头望向门外。"
                                + "表演：呼吸短促。表情与视线：惊惧，视线锁住门缝。"
                                + "摄影机：缓慢推近，保持眼平机位。声音：风声渐强。"
                                + "连续性：黑色外套与上一镜一致。禁止：不要字幕；不要镜头抖动。");
    }

    @Test
    void 非法时长和超长结果必须失败而不是截断() {
        var normal = new SeedanceShotPromptSpec("声音", "固定机位", "人物", "转身");
        assertThatThrownBy(() -> SeedancePromptCompiler.compile(normal, "9:16", 5_250))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("500ms");

        var oversized = new SeedanceShotPromptSpec(
                "声音", "固定机位", "😀".repeat(1_500), "😀".repeat(600));
        assertThatThrownBy(() -> SeedancePromptCompiler.compile(oversized, "9:16", 5_000))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("2000");
    }
}
