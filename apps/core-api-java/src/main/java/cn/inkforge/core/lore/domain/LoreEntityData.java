package cn.inkforge.core.lore.domain;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** 创建设定实体时的完整业务字段，不包含协议控制字段。 */
public record LoreEntityData(Map<String, Object> fields) {

    public LoreEntityData {
        Objects.requireNonNull(fields);
        fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields));
    }
}
