package cn.inkforge.core.lore.domain;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** 设定实体三态补丁；Map 中存在且值为 null 表示显式清空。 */
public record LoreEntityPatch(Map<String, Object> fields) {

    public LoreEntityPatch {
        Objects.requireNonNull(fields);
        fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields));
    }

    public boolean empty() {
        return fields.isEmpty();
    }
}
