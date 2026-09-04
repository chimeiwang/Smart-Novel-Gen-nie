package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.Map;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 正文详情和决定均从同一完整不可变 JSON Evidence 读取基础正文。 */
record DurableChapterWritingReviewEvidence(String bundleId, String manifestHash, Map<String, Object> context, String content) {
    static DurableChapterWritingReviewEvidence read(DSLContext tx, ObjectMapper json, String runId, String bundleId, String chapterId) {
        Record value = tx.fetchOne("""
                SELECT bundle."manifestSha256", item."contentJson", item."contentSha256"
                FROM public."WorkflowEvidenceBundle" bundle JOIN public."WorkflowEvidenceItem" item ON item."bundleId" = bundle.id
                WHERE bundle.id = ? AND bundle."runId" = ? AND item."resourceType" = 'chapter_writing_context'
                  AND item."resourceId" = ? AND item.exists AND item."contentType" = 'json'
                """, bundleId, runId, chapterId);
        if (value == null) throw invalid();
        Map<String, Object> context = json.readValue(value.get("contentJson", String.class), new TypeReference<>() {});
        if (!ExecutionCanonicalJson.sha256(context).equals(value.get("contentSha256", String.class))
                || !(context.get("currentChapter") instanceof Map<?, ?> chapter) || !chapterId.equals(chapter.get("id"))
                || !(chapter.get("content") instanceof String content)) throw invalid();
        return new DurableChapterWritingReviewEvidence(bundleId, value.get("manifestSha256", String.class), context, content);
    }
    private static ApiException invalid() {
        return new ApiException(409, "ARTIFACT_REVISION_INTEGRITY_ERROR", "正文草案的不可变 Evidence 无法通过完整性校验");
    }
}
