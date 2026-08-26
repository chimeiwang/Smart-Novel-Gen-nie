package cn.inkforge.core.video.domain;

import cn.inkforge.contracts.api.SeedanceShotPromptSpec;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.openapitools.jackson.nullable.JsonNullable;

/** 把结构化镜头描述按冻结顺序编译成可审核的即梦提示词。 */
public final class SeedancePromptCompiler {

    private SeedancePromptCompiler() {}

    public static String compile(
            SeedanceShotPromptSpec specification, String ratio, int timelineDurationMs) {
        if (timelineDurationMs < 500
                || timelineDurationMs > 15_000
                || timelineDurationMs % 500 != 0) {
            throw new IllegalArgumentException(
                    "即梦提示词镜头时长必须是 500ms 到 15000ms 的 500ms 倍数");
        }
        String duration = timelineDurationMs % 1_000 == 0
                ? Integer.toString(timelineDurationMs / 1_000)
                : String.format(Locale.ROOT, "%.1f", timelineDurationMs / 1_000.0);
        List<String> parts = new ArrayList<>();
        parts.add(ratio + " 画幅，" + duration + " 秒");
        parts.add(sentence(specification.getSubjectAndScene()));
        parts.add(sentence(specification.getVisibleAction()));
        optional(specification.getPerformance())
                .ifPresent(value -> parts.add("表演：" + sentence(value)));
        optional(specification.getExpressionAndGaze())
                .ifPresent(value -> parts.add("表情与视线：" + sentence(value)));
        parts.add("摄影机：" + sentence(specification.getCamera()));
        parts.add("声音：" + sentence(specification.getAudio()));
        optional(specification.getContinuity())
                .ifPresent(value -> parts.add("连续性：" + sentence(value)));
        if (specification.getNegativeConstraints() != null
                && !specification.getNegativeConstraints().isEmpty()) {
            parts.add("禁止：" + specification.getNegativeConstraints().stream()
                    .map(SeedancePromptCompiler::sentence)
                    .collect(java.util.stream.Collectors.joining("；")));
        }
        String prompt = String.join("。", parts) + "。";
        if (prompt.codePointCount(0, prompt.length()) > 2_000) {
            throw new IllegalArgumentException("编译后的即梦提示词超过 2000 字安全包络");
        }
        return prompt;
    }

    private static java.util.Optional<String> optional(JsonNullable<String> value) {
        if (value == null || !value.isPresent() || value.get() == null) {
            return java.util.Optional.empty();
        }
        return java.util.Optional.of(value.get());
    }

    private static String sentence(String value) {
        String normalized = value.strip();
        int end = normalized.length();
        while (end > 0) {
            int point = normalized.codePointBefore(end);
            if ("。；;，,.！!？?".indexOf(point) < 0) break;
            end -= Character.charCount(point);
        }
        return normalized.substring(0, end);
    }
}
