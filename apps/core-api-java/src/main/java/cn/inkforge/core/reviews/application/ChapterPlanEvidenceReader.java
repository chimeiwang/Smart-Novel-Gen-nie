package cn.inkforge.core.reviews.application;

import java.time.OffsetDateTime;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;

/** 章节规划生成与正式批准共同使用的权威来源读取端口；调用方持有外层业务事务。 */
public interface ChapterPlanEvidenceReader {

    Snapshot capture(DSLContext transaction, String novelId, String chapterId, String userInstruction);

    /** 额外文本只参与确定性相关性选择，不替换用户指令，也不自动进入规划投影。 */
    default Snapshot capture(DSLContext transaction, String novelId, String chapterId, String userInstruction,
            String additionalRelevanceText) {
        if (!Objects.requireNonNull(additionalRelevanceText).isEmpty()) {
            throw new UnsupportedOperationException("当前来源读取器不支持额外相关性文本");
        }
        return capture(transaction, novelId, chapterId, userInstruction);
    }

    record Snapshot(Map<String, Object> context, OffsetDateTime chapterUpdatedAt) {
        public Snapshot {
            context = freezeMap(context);
            chapterUpdatedAt = Objects.requireNonNull(chapterUpdatedAt);
        }

        private static Map<String, Object> freezeMap(Map<String, Object> source) {
            Map<String, Object> copy = new LinkedHashMap<>();
            source.forEach((key, value) -> copy.put(key, freeze(value)));
            return Collections.unmodifiableMap(copy);
        }

        private static Object freeze(Object value) {
            if (value instanceof Map<?, ?> map) {
                Map<String, Object> copy = new LinkedHashMap<>();
                map.forEach((key, nested) -> {
                    if (!(key instanceof String text)) throw new IllegalArgumentException("来源对象的键必须是字符串");
                    copy.put(text, freeze(nested));
                });
                return Collections.unmodifiableMap(copy);
            }
            if (value instanceof List<?> list) return list.stream().map(Snapshot::freeze).toList();
            return value;
        }
    }
}
