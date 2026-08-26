package cn.inkforge.core.styles.domain;

import java.time.OffsetDateTime;
import java.util.List;

/** 私有文风、完整画像以及参考文件和任务的聚合快照。 */
public record StyleSnapshot(
        String id,
        String name,
        String sourceType,
        String creativeMethodology,
        String uniqueMarkers,
        String generationStyle,
        String expressionFeatures,
        String styleTraits,
        String portraitMarkdown,
        int originalCharCount,
        int usedCharCount,
        boolean truncated,
        String errorMessage,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        List<StyleReferenceSnapshot> references,
        List<PortraitTaskSnapshot> tasks) {

    public StyleSnapshot {
        references = List.copyOf(references);
        tasks = List.copyOf(tasks);
    }
}
