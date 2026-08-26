package cn.inkforge.core.styles.domain;

import java.util.Map;

/** 成功回调允许原子写入文风聚合的字段。 */
public record PortraitSuccessData(Map<String, Object> fields) {

    public PortraitSuccessData {
        fields = java.util.Collections.unmodifiableMap(new java.util.LinkedHashMap<>(fields));
    }
}
