package cn.inkforge.core.writing.domain;

import cn.inkforge.core.db.generated.enums.Writingtaskphase;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 把非终态 WritingTask 收敛为稳定错误状态，并尽可能保留合法检查点。 */
public final class WritingTaskFailure {

    private WritingTaskFailure() {}

    public static void apply(
            WritingtaskRecord task,
            String code,
            LocalDateTime now,
            ObjectMapper json) {
        if (task.getPhase() == Writingtaskphase.completed
                || task.getPhase() == Writingtaskphase.error) {
            return;
        }
        Map<String, Object> snapshot = objectOrEmpty(task.getGraphstatejson(), json);
        if (!snapshot.isEmpty()) {
            snapshot.put("errorMessage", "智能体运行失败：" + code);
            task.setGraphstatejson(json.writeValueAsString(snapshot));
        }
        task.setPhase(Writingtaskphase.error);
        task.setUpdatedat(now);
    }

    private static Map<String, Object> objectOrEmpty(
            String serialized, ObjectMapper json) {
        if (serialized == null) return new LinkedHashMap<>();
        try {
            Object parsed = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) return new LinkedHashMap<>();
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!(entry.getKey() instanceof String key)) return new LinkedHashMap<>();
                result.put(key, entry.getValue());
            }
            return result;
        } catch (RuntimeException exception) {
            return new LinkedHashMap<>();
        }
    }
}
