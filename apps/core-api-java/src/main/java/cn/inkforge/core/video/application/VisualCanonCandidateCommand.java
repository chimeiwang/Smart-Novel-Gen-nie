package cn.inkforge.core.video.application;

import java.util.List;

/** 已完成跨字段和空白规范化的视觉设定候选命令。 */
public record VisualCanonCandidateCommand(
        String settingKind,
        String settingId,
        String duty,
        String variantKey,
        String label,
        String candidateAssetId,
        List<String> includeFeatures,
        List<String> excludeFeatures,
        int defaultStrength,
        int expectedRevision) {

    public VisualCanonCandidateCommand {
        includeFeatures = List.copyOf(includeFeatures);
        excludeFeatures = List.copyOf(excludeFeatures);
        if (expectedRevision < 0) throw new IllegalArgumentException("候选基线版本不能为负数");
    }
}
