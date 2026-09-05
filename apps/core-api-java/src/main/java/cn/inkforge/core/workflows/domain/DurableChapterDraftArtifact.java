package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.platform.text.TextLength;
import cn.inkforge.core.platform.http.ApiException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/** 全文章节候选只保存一份正文，来源和完整 Diff 由冻结 Evidence 重建。 */
public final class DurableChapterDraftArtifact {
    public static final String SCHEMA = "durable.chapter-draft-artifact.v1";
    private static final Set<String> OPERATIONS = Set.of("write_chapter", "rewrite_scene");
    private static final Set<String> OUTPUT_KEYS = Set.of("summary", "content", "contentSha256", "wordCount");
    private static final Map<String, Object> DIFF = Map.of("schema", SCHEMA, "type", "chapter_content");
    private DurableChapterDraftArtifact() {}

    public static Stored create(String bundleId, String manifestHash, String chapterId,
            Map<String, Object> output, String producingStepId, String producingResultHash) {
        return create("write_chapter", bundleId, manifestHash, chapterId, output,
                producingStepId, producingResultHash);
    }

    public static Stored create(String operation, String bundleId, String manifestHash,
            String chapterId, Map<String, Object> output, String producingStepId,
            String producingResultHash) {
        validateOutput(output);
        Map<String, Object> stored = new LinkedHashMap<>(output);
        stored.put("schema", SCHEMA);
        stored.put("kind", "chapter_draft");
        stored.put("operation", operation(operation));
        stored.put("evidenceBundleId", nonBlank(bundleId));
        stored.put("evidenceManifestSha256", hash(manifestHash));
        stored.put("chapterId", nonBlank(chapterId));
        stored.put("producingStepId", nonBlank(producingStepId));
        stored.put("producingResultHash", hash(producingResultHash));
        return new Stored(Map.copyOf(stored), DIFF);
    }

    public static void validateOutput(Map<String, Object> output) {
        if (!OUTPUT_KEYS.equals(output.keySet())) throw invalid();
        String summary = nonBlank(output.get("summary"));
        if (summary.codePointCount(0, summary.length()) > 1000) throw invalid();
        String content = nonBlank(output.get("content"));
        if (!DurableSelectionArtifact.sha256(content).equals(hash(output.get("contentSha256")))) throw invalid();
        Object count = output.get("wordCount");
        if (!(count instanceof Integer || count instanceof Long)
                || ((Number) count).longValue() != TextLength.count(content)) throw invalid();
    }

    public static Map<String, Object> deriveOutput(String summary, String content) {
        Map<String, Object> result = Map.of("summary", nonBlank(summary), "content", nonBlank(content),
                "contentSha256", DurableSelectionArtifact.sha256(content), "wordCount", TextLength.count(content));
        validateOutput(result);
        return result;
    }

    public static Map<String, Object> output(Map<String, Object> stored) {
        Map<String, Object> output = new LinkedHashMap<>();
        for (String field : OUTPUT_KEYS) output.put(field, stored.get(field));
        validateOutput(output);
        return Map.copyOf(output);
    }

    public static Materialized reconstruct(Map<String, Object> stored, Map<String, Object> diff,
            String bundleId, String manifestHash, String chapterId, String originalContent) {
        return reconstruct("write_chapter", stored, diff, bundleId, manifestHash,
                chapterId, originalContent);
    }

    public static Materialized reconstruct(String expectedOperation, Map<String, Object> stored,
            Map<String, Object> diff, String bundleId, String manifestHash, String chapterId,
            String originalContent) {
        try {
            String operation = operation(expectedOperation);
            if (!stored.keySet().equals(Set.of("summary", "content", "contentSha256", "wordCount", "schema", "kind", "operation",
                    "evidenceBundleId", "evidenceManifestSha256", "chapterId", "producingStepId", "producingResultHash"))
                    || !SCHEMA.equals(stored.get("schema")) || !"chapter_draft".equals(stored.get("kind"))
                    || !operation.equals(stored.get("operation")) || !DIFF.equals(diff)
                    || !bundleId.equals(stored.get("evidenceBundleId")) || !manifestHash.equals(stored.get("evidenceManifestSha256"))
                    || !chapterId.equals(stored.get("chapterId")) || originalContent == null) throw invalid();
            hash(manifestHash);
            nonBlank(stored.get("producingStepId"));
            hash(stored.get("producingResultHash"));
            Map<String, Object> payload = new LinkedHashMap<>(output(stored));
            payload.put("kind", "chapter_draft");
            payload.put("operation", operation);
            payload.put("target", Map.of("mode", "existing_chapter", "chapterId", chapterId));
            return new Materialized(Map.copyOf(payload), Map.of("type", "chapter_content", "before", originalContent, "after", stored.get("content")));
        } catch (IllegalArgumentException | NullPointerException exception) {
            throw new ApiException(409, "ARTIFACT_REVISION_INTEGRITY_ERROR", "正文草案的不可变修订或 Evidence 无法通过完整性校验");
        }
    }

    public static boolean isStored(Map<String, Object> payload) { return SCHEMA.equals(payload.get("schema")); }

    public static String nonBlank(Object value) {
        if (!(value instanceof String text) || TextLength.count(text) == 0) throw invalid();
        return text;
    }
    private static String operation(String value) {
        if (!OPERATIONS.contains(value)) throw invalid();
        return value;
    }
    private static String hash(Object value) {
        if (!(value instanceof String text) || !text.matches("[0-9a-f]{64}")) throw invalid();
        return text;
    }
    private static IllegalArgumentException invalid() { return new IllegalArgumentException("完整正文草案不符合严格语义与完整性契约"); }
    public record Stored(Map<String, Object> payload, Map<String, Object> diff) {}
    public record Materialized(Map<String, Object> payload, Map<String, Object> diff) {}
}
