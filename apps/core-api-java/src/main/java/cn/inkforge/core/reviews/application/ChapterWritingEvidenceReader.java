package cn.inkforge.core.reviews.application;

import java.time.OffsetDateTime;
import java.util.Map;
import org.jooq.DSLContext;

/** 正文生成与批准共同使用的完整最小来源；调用方持有外层 Run/Artifact 事务。 */
public interface ChapterWritingEvidenceReader {
    Snapshot capture(DSLContext transaction, String novelId, String chapterId, String userInstruction);

    record Snapshot(Map<String, Object> context, OffsetDateTime chapterUpdatedAt) {
        public Snapshot {
            var immutable = new ChapterPlanEvidenceReader.Snapshot(context, chapterUpdatedAt);
            context = immutable.context();
            chapterUpdatedAt = immutable.chapterUpdatedAt();
        }
    }
}
