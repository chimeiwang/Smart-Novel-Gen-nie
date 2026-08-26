package cn.inkforge.core.lore.domain;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** 作品圣经三态补丁；显式 null 用于清空可空字段。 */
public record WritingBiblePatch(Map<String, Object> fields) {

    public WritingBiblePatch {
        Objects.requireNonNull(fields);
        fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields));
    }

    public boolean empty() {
        return fields.isEmpty();
    }
}
