package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.Map;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 详情与决定共用同一不可变 Evidence，不能以可变工作区拼装历史候选。 */
record DurableChapterPlanReviewEvidence(String bundleId, String manifestHash, Map<String, Object> context) {
    static DurableChapterPlanReviewEvidence read(DSLContext tx, ObjectMapper json,
            String runId, String bundleId, String chapterId) {
        Record value = tx.fetchOne("""
                SELECT bundle."manifestSha256", item."contentJson", item."contentSha256"
                FROM public."WorkflowEvidenceBundle" AS bundle
                JOIN public."WorkflowEvidenceItem" AS item ON item."bundleId" = bundle.id
                WHERE bundle.id = ? AND bundle."runId" = ?
                  AND item."resourceType" = 'chapter_plan_context' AND item."resourceId" = ?
                  AND item.exists AND item."contentType" = 'json'
                """, bundleId, runId, chapterId);
        if (value == null) throw invalid();
        try {
            Map<String, Object> context = json.readValue(value.get("contentJson", String.class), new TypeReference<>() {});
            if (!ExecutionCanonicalJson.sha256(context).equals(value.get("contentSha256", String.class))) throw invalid();
            return new DurableChapterPlanReviewEvidence(bundleId, value.get("manifestSha256", String.class), context);
        } catch (IllegalArgumentException exception) {
            throw invalid();
        }
    }

    private static ApiException invalid() {
        return new ApiException(409, "ARTIFACT_REVISION_INTEGRITY_ERROR", "章节规划不可变 Evidence 无法通过完整性校验");
    }
}
