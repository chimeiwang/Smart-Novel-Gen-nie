package cn.inkforge.core.workflows.application;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 保留显式 null 的 JSON 深冻结；防止请求哈希计算后调用方再修改嵌套值。 */
final class WorkflowJsonValues {

    private WorkflowJsonValues() {}

    static Map<String, Object> freezeMap(Map<String, ?> value) {
        if (value == null) throw new IllegalArgumentException("JSON 对象不能为空");
        Map<String, Object> result = new LinkedHashMap<>();
        value.forEach((key, nested) -> {
            if (key == null) throw new IllegalArgumentException("JSON key 不能为空");
            result.put(key, freeze(nested));
        });
        return Collections.unmodifiableMap(result);
    }

    static Object freeze(Object value) {
        if (value == null
                || value instanceof String
                || value instanceof Number
                || value instanceof Boolean) {
            return value;
        }
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!(entry.getKey() instanceof String key)) {
                    throw new IllegalArgumentException("JSON 对象 key 必须是字符串");
                }
                result.put(key, freeze(entry.getValue()));
            }
            return Collections.unmodifiableMap(result);
        }
        if (value instanceof List<?> list) {
            List<Object> result = new ArrayList<>(list.size());
            list.forEach(item -> result.add(freeze(item)));
            return Collections.unmodifiableList(result);
        }
        throw new IllegalArgumentException("不支持的 JSON 值类型：" + value.getClass().getSimpleName());
    }
}
