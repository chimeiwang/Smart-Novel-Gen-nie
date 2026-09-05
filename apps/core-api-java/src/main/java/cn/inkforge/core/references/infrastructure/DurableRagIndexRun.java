package cn.inkforge.core.references.infrastructure;

import cn.inkforge.core.references.domain.RagRules;
import cn.inkforge.core.references.domain.RagJobIdentity;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 一次已冻结的 reference/hash/generation 身份，标题与作者编辑时间不参与索引失效。 */
record DurableRagIndexRun(String id, String userId, String novelId, String referenceId,
        String contentHash, String generation, String bundleId, String status) {
    static final String SOURCE_TYPE = "rag_index_v2";

    static DurableRagIndexRun load(DSLContext tx, ObjectMapper json, String runId) {
        Record row = tx.fetchOne("""
                SELECT id,"userId","novelId","chapterId","writingSessionId",workflow,operation,
                  "sourceType","sourceId","targetType","targetId",input,"currentEvidenceBundleId",status::text AS status
                FROM public."WorkflowRun" WHERE id=? AND "engineVersion"=2
                """, runId);
        if (row == null || !"rag".equals(row.get("workflow")) || !"embedding".equals(row.get("operation"))
                || !SOURCE_TYPE.equals(row.get("sourceType")) || !"reference".equals(row.get("targetType"))
                || !Objects.equals(row.get("sourceId"), row.get("targetId")) || row.get("novelId") == null
                || row.get("chapterId") != null || row.get("writingSessionId") != null) {
            throw new IllegalArgumentException("RAG V2 Run 身份无效");
        }
        Map<String, Object> input = json.readValue(row.get("input", String.class), new TypeReference<>() {});
        if (!input.keySet().equals(Set.of("referenceId", "contentHash", "indexGeneration"))
                || !Objects.equals(input.get("referenceId"), row.get("sourceId"))
                || !(input.get("contentHash") instanceof String hash) || !hash.matches("[a-f0-9]{64}")
                || !(input.get("indexGeneration") instanceof String generation)
                || !RagJobIdentity.generationText(OffsetDateTime.parse(generation)).equals(generation)) {
            throw new IllegalArgumentException("RAG V2 Run 代次无效");
        }
        return new DurableRagIndexRun(runId, row.get("userId", String.class), row.get("novelId", String.class),
                row.get("sourceId", String.class), hash, generation, row.get("currentEvidenceBundleId", String.class), row.get("status", String.class));
    }

    Map<String, Object> context(DSLContext tx, ObjectMapper json) {
        var rows = tx.fetch("""
                SELECT item."resourceType",item."resourceId",item.exists,item."contentType",item."contentJson",
                  item."contentSha256",item."byteCount",item."rangeJson",bundle."policyVersion"
                FROM public."WorkflowEvidenceItem" item JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id=item."bundleId"
                WHERE bundle.id=? AND bundle."runId"=? ORDER BY item.ordinal
                """, bundleId, id);
        if (rows.size() != 1) throw new IllegalArgumentException("RAG 必须有唯一完整 Evidence");
        Record row = rows.getFirst();
        Map<String, Object> context = json.readValue(row.get("contentJson", String.class), new TypeReference<>() {});
        if (!"rag_embedding_context".equals(row.get("resourceType")) || !referenceId.equals(row.get("resourceId"))
                || !Boolean.TRUE.equals(row.get("exists")) || !"json".equals(row.get("contentType"))
                || row.get("rangeJson") != null || !"evidence.rag.reference_chunks.v1".equals(row.get("policyVersion"))
                || !ExecutionCanonicalJson.sha256(context).equals(row.get("contentSha256"))
                || ExecutionCanonicalJson.bytes(context).length != row.get("byteCount", Long.class)) {
            throw new IllegalArgumentException("RAG Evidence 绑定无效");
        }
        validateContext(context, referenceId, contentHash, generation);
        return context;
    }

    static void validateContext(Map<String, Object> context, String referenceId, String hash, String generation) {
        if (!context.keySet().equals(Set.of("referenceId", "contentHash", "indexGeneration", "content", "chunkCount"))
                || !referenceId.equals(context.get("referenceId")) || !hash.equals(context.get("contentHash"))
                || !generation.equals(context.get("indexGeneration")) || !(context.get("content") instanceof String content)
                || !hash.equals(RagRules.sha256(content)) || !(context.get("chunkCount") instanceof Integer count)
                || count < 1 || count > RagRules.MAX_INDEX_CHUNKS || count != RagRules.chunks(content).size()) {
            throw new IllegalArgumentException("RAG 完整来源或分块数无效");
        }
    }
}
