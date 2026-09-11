package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.text.TextLength;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** V2 大纲总纲/节点选区候选的独立耐久事实与完整详情重建。 */
public final class DurableOutlineSelectionArtifact {
    public static final String SCHEMA = "durable.outline-selection-artifact.v1";
    private static final Set<String> RESOURCE_TYPES =
            Set.of("outline_content", "outline_node_content");
    private static final Set<String> PAYLOAD_KEYS = Set.of(
            "schema", "kind", "operation", "evidenceBundleId", "evidenceItemId",
            "resourceType", "resourceId", "resourceUpdatedAt", "sourceContentSha256",
            "selectionStartCodePoint", "selectionEndCodePoint", "selectedTextSha256",
            "replacement", "replacementSha256", "candidateSha256", "generationStepId",
            "generationResultHash");
    private static final Set<String> DIFF_KEYS =
            Set.of("schema", "type", "mode", "resourceType");

    private DurableOutlineSelectionArtifact() {}

    /** 冻结大纲选区身份和替换文本，创建尚未物化的耐久草案。 */
    public static Stored create(
            String evidenceBundleId,
            String evidenceItemId,
            String resourceType,
            String resourceId,
            OffsetDateTime resourceUpdatedAt,
            String sourceContentSha256,
            int selectionStart,
            int selectionEnd,
            String selectedTextSha256,
            String replacement,
            String replacementSha256,
            String candidateSha256,
            String generationStepId,
            String generationResultHash) {
        String type = resourceType(resourceType);
        String value = requireReplacement(replacement);
        if (!DurableSelectionArtifact.sha256(value)
                .equals(requireHash(replacementSha256, "replacementSha256"))) {
            throw invalid();
        }
        if (selectionStart < 0 || selectionEnd <= selectionStart) throw invalid();
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schema", SCHEMA);
        payload.put("kind", "outline_draft");
        payload.put("operation", "rewrite_outline_selection");
        payload.put("evidenceBundleId", requireText(evidenceBundleId, "evidenceBundleId"));
        payload.put("evidenceItemId", requireText(evidenceItemId, "evidenceItemId"));
        payload.put("resourceType", type);
        payload.put("resourceId", requireText(resourceId, "resourceId"));
        payload.put("resourceUpdatedAt", Objects.requireNonNull(resourceUpdatedAt).toString());
        payload.put("sourceContentSha256", requireHash(sourceContentSha256, "sourceContentSha256"));
        payload.put("selectionStartCodePoint", selectionStart);
        payload.put("selectionEndCodePoint", selectionEnd);
        payload.put("selectedTextSha256", requireHash(selectedTextSha256, "selectedTextSha256"));
        payload.put("replacement", value);
        payload.put("replacementSha256", replacementSha256);
        payload.put("candidateSha256", requireHash(candidateSha256, "candidateSha256"));
        payload.put("generationStepId", requireText(generationStepId, "generationStepId"));
        payload.put("generationResultHash", requireHash(generationResultHash, "generationResultHash"));
        return new Stored(Map.copyOf(payload), diff(type));
    }

    public static Stored edit(Stored base, String replacement) {
        Objects.requireNonNull(base);
        requireStoredShape(base.payload(), base.diff());
        String value = requireReplacement(replacement);
        Map<String, Object> payload = new LinkedHashMap<>(base.payload());
        payload.put("replacement", value);
        payload.put("replacementSha256", DurableSelectionArtifact.sha256(value));
        payload.remove("candidateSha256");
        return new Stored(payload, base.diff());
    }

    public static Stored withCandidateHash(Stored value, String candidateSha256) {
        Objects.requireNonNull(value);
        Map<String, Object> payload = new LinkedHashMap<>(value.payload());
        payload.put("candidateSha256", requireHash(candidateSha256, "candidateSha256"));
        requireStoredShape(payload, value.diff());
        return new Stored(Map.copyOf(payload), Map.copyOf(value.diff()));
    }

    /** 对照 Evidence 复验来源版本与选区哈希后重建完整候选。 */
    public static Materialized reconstruct(
            Map<String, Object> storedPayload,
            Map<String, Object> storedDiff,
            Evidence evidence) {
        Objects.requireNonNull(evidence);
        requireStoredShape(storedPayload, storedDiff);
        String type = string(storedPayload, "resourceType");
        String resourceId = string(storedPayload, "resourceId");
        String sourceHash = hash(storedPayload, "sourceContentSha256");
        int start = integer(storedPayload, "selectionStartCodePoint");
        int end = integer(storedPayload, "selectionEndCodePoint");
        String selectedHash = hash(storedPayload, "selectedTextSha256");
        String replacement = string(storedPayload, "replacement");
        String replacementHash = hash(storedPayload, "replacementSha256");
        String candidateHash = hash(storedPayload, "candidateSha256");
        OffsetDateTime updatedAt = timestamp(storedPayload, "resourceUpdatedAt");
        int length = codePointLength(evidence.content());
        if (!string(storedPayload, "evidenceBundleId").equals(evidence.bundleId())
                || !string(storedPayload, "evidenceItemId").equals(evidence.itemId())
                || !type.equals(evidence.resourceType())
                || !resourceId.equals(evidence.resourceId())
                || !updatedAt.toInstant().equals(evidence.resourceUpdatedAt().toInstant())
                || !sourceHash.equals(evidence.contentSha256())
                || !sourceHash.equals(DurableSelectionArtifact.sha256(evidence.content()))
                || start != evidence.selectionStartCodePoint()
                || end != evidence.selectionEndCodePoint()
                || start < 0 || end <= start || end > length
                || !replacementHash.equals(DurableSelectionArtifact.sha256(replacement))) {
            throw integrityError();
        }
        String selected = slice(evidence.content(), start, end);
        String prefix = slice(evidence.content(), 0, start);
        String suffix = slice(evidence.content(), end, length);
        String candidate = prefix + replacement + suffix;
        if (!selectedHash.equals(DurableSelectionArtifact.sha256(selected))
                || !candidateHash.equals(DurableSelectionArtifact.sha256(candidate))) {
            throw integrityError();
        }
        String mode = mode(type);
        Map<String, Object> target = new LinkedHashMap<>();
        target.put("mode", mode);
        target.put("resourceType", type);
        target.put("resourceId", resourceId);
        target.put("baseUpdatedAt", updatedAt.toString());
        target.put("baseContentHash", sourceHash);
        target.put("selectionStart", start);
        target.put("selectionEnd", end);
        target.put("selectedTextHash", selectedHash);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", "outline_draft");
        payload.put("operation", "rewrite_outline_selection");
        payload.put("target", Map.copyOf(target));
        payload.put("resourceType", type);
        payload.put("resourceId", resourceId);
        payload.put("baseUpdatedAt", updatedAt.toString());
        payload.put("baseContentHash", sourceHash);
        payload.put("selectionStart", start);
        payload.put("selectionEnd", end);
        payload.put("selectedTextHash", selectedHash);
        payload.put("selectedText", selected);
        payload.put("contextBefore", slice(evidence.content(), Math.max(0, start - 1_000), start));
        payload.put("contextAfter", slice(evidence.content(), end, Math.min(length, end + 1_000)));
        payload.put("selection", Map.of(
                "start", start, "end", end, "selectedText", selected,
                "selectedTextHash", selectedHash));
        payload.put("replacement", replacement);
        payload.put("contentSha256", replacementHash);
        payload.put("candidate", candidate);
        payload.put("candidatePrefix", prefix);
        payload.put("candidateSuffix", suffix);

        Map<String, Object> materializedDiff = new LinkedHashMap<>();
        materializedDiff.put("type", "selection");
        materializedDiff.put("mode", mode);
        materializedDiff.put("resourceType", type);
        materializedDiff.put("resourceId", resourceId);
        materializedDiff.put("selectionStart", start);
        materializedDiff.put("selectionEnd", end);
        materializedDiff.put("selectedText", selected);
        materializedDiff.put("replacement", replacement);
        materializedDiff.put("before", evidence.content());
        materializedDiff.put("after", candidate);
        materializedDiff.put("candidate", candidate);
        materializedDiff.put("prefix", prefix);
        materializedDiff.put("suffix", suffix);
        return new Materialized(Map.copyOf(payload), Map.copyOf(materializedDiff));
    }

    public static boolean isStored(Map<String, Object> payload) {
        return SCHEMA.equals(payload.get("schema"));
    }

    private static void requireStoredShape(
            Map<String, Object> payload, Map<String, Object> storedDiff) {
        if (!payload.keySet().equals(PAYLOAD_KEYS)
                || !storedDiff.keySet().equals(DIFF_KEYS)
                || !SCHEMA.equals(payload.get("schema"))
                || !"outline_draft".equals(payload.get("kind"))
                || !"rewrite_outline_selection".equals(payload.get("operation"))) {
            throw integrityError();
        }
        String type = string(payload, "resourceType");
        if (!RESOURCE_TYPES.contains(type)) throw integrityError();
        if (!diff(type).equals(storedDiff)) throw integrityError();
        string(payload, "evidenceBundleId");
        string(payload, "evidenceItemId");
        string(payload, "resourceId");
        timestamp(payload, "resourceUpdatedAt");
        hash(payload, "sourceContentSha256");
        int start = integer(payload, "selectionStartCodePoint");
        int end = integer(payload, "selectionEndCodePoint");
        if (start < 0 || end <= start) throw integrityError();
        hash(payload, "selectedTextSha256");
        String replacement = string(payload, "replacement");
        if (TextLength.count(replacement) == 0
                || !hash(payload, "replacementSha256")
                        .equals(DurableSelectionArtifact.sha256(replacement))) {
            throw integrityError();
        }
        hash(payload, "candidateSha256");
        string(payload, "generationStepId");
        hash(payload, "generationResultHash");
    }

    private static Map<String, Object> diff(String resourceType) {
        return Map.of(
                "schema", SCHEMA,
                "type", "selection",
                "mode", mode(resourceType),
                "resourceType", resourceType);
    }

    private static String resourceType(String value) {
        if (!RESOURCE_TYPES.contains(value)) throw invalid();
        return value;
    }

    private static String mode(String type) {
        return "outline_content".equals(type)
                ? "outline_content_selection"
                : "outline_node_content_selection";
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " 不能为空");
        }
        return value;
    }

    private static String requireReplacement(String value) {
        if (value == null || TextLength.count(value) == 0) {
            throw new IllegalArgumentException("replacement 不能为空");
        }
        return value;
    }

    private static String requireHash(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(field + " 必须是小写 SHA-256");
        }
        return value;
    }

    private static String string(Map<String, Object> value, String field) {
        Object item = value.get(field);
        if (!(item instanceof String text) || text.isEmpty()) throw integrityError();
        return text;
    }

    private static String hash(Map<String, Object> value, String field) {
        String text = string(value, field);
        if (!text.matches("[0-9a-f]{64}")) throw integrityError();
        return text;
    }

    private static int integer(Map<String, Object> value, String field) {
        Object item = value.get(field);
        if (!(item instanceof Integer || item instanceof Long)) throw integrityError();
        long result = ((Number) item).longValue();
        if (result < Integer.MIN_VALUE || result > Integer.MAX_VALUE) throw integrityError();
        return (int) result;
    }

    private static OffsetDateTime timestamp(Map<String, Object> value, String field) {
        try {
            return OffsetDateTime.parse(string(value, field));
        } catch (DateTimeParseException exception) {
            throw integrityError();
        }
    }

    private static int codePointLength(String value) {
        return value.codePointCount(0, value.length());
    }

    private static String slice(String content, int start, int end) {
        return content.substring(
                content.offsetByCodePoints(0, start),
                content.offsetByCodePoints(0, end));
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("大纲选区候选不符合严格语义契约");
    }

    private static ApiException integrityError() {
        return new ApiException(
                409,
                "ARTIFACT_REVISION_INTEGRITY_ERROR",
                "待审核大纲选区候选的不可变修订或 Evidence 无法通过完整性校验");
    }

    public record Stored(Map<String, Object> payload, Map<String, Object> diff) {
        public Stored {
            Objects.requireNonNull(payload);
            Objects.requireNonNull(diff);
        }
    }

    public record Evidence(
            String bundleId,
            String itemId,
            String resourceType,
            String resourceId,
            OffsetDateTime resourceUpdatedAt,
            String content,
            String contentSha256,
            int selectionStartCodePoint,
            int selectionEndCodePoint) {
        public Evidence {
            Objects.requireNonNull(bundleId);
            Objects.requireNonNull(itemId);
            Objects.requireNonNull(resourceType);
            Objects.requireNonNull(resourceId);
            Objects.requireNonNull(resourceUpdatedAt);
            Objects.requireNonNull(content);
            Objects.requireNonNull(contentSha256);
        }
    }

    public record Materialized(Map<String, Object> payload, Map<String, Object> diff) {
        public Materialized {
            Objects.requireNonNull(payload);
            Objects.requireNonNull(diff);
        }
    }
}
