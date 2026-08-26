package cn.inkforge.core.styles.domain;

import cn.inkforge.core.platform.http.ApiException;

/** 可独立生成人工修改的五个文风画像分节。 */
public enum PortraitSection {
    CREATIVE_METHODOLOGY("creativeMethodology"),
    UNIQUE_MARKERS("uniqueMarkers"),
    GENERATION_STYLE("generationStyle"),
    EXPRESSION_FEATURES("expressionFeatures"),
    STYLE_TRAITS("styleTraits");

    private final String value;

    PortraitSection(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    public static PortraitSection from(String value) {
        for (PortraitSection section : values()) {
            if (section.value.equals(value)) return section;
        }
        throw new ApiException(422, "VALIDATION_ERROR", "画像分节无效");
    }
}
