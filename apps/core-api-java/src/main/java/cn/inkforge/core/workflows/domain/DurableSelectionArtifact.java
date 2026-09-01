package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.platform.http.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** V2 章节选区候选的最小耐久事实与确定性详情重建。 */
public final class DurableSelectionArtifact {

    public static final String SCHEMA = "durable.chapter-selection-artifact.v1";

    private DurableSelectionArtifact() {}

    public static Stored create(
            String evidenceBundleId,
            String evidenceItemId,
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
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schema", SCHEMA);
        payload.put("kind", "chapter_draft");
        payload.put("operation", "rewrite_chapter_selection");
        payload.put("evidenceBundleId", requireText(evidenceBundleId, "evidenceBundleId"));
        payload.put("evidenceItemId", requireText(evidenceItemId, "evidenceItemId"));
        payload.put("resourceType", "chapter_content");
        payload.put("resourceId", requireText(resourceId, "resourceId"));
        payload.put("resourceUpdatedAt", Objects.requireNonNull(resourceUpdatedAt).toString());
        payload.put("sourceContentSha256", requireHash(sourceContentSha256, "sourceContentSha256"));
        payload.put("selectionStartCodePoint", selectionStart);
        payload.put("selectionEndCodePoint", selectionEnd);
        payload.put("selectedTextSha256", requireHash(selectedTextSha256, "selectedTextSha256"));
        payload.put("replacement", requireReplacement(replacement));
        payload.put("replacementSha256", requireHash(replacementSha256, "replacementSha256"));
        payload.put("candidateSha256", requireHash(candidateSha256, "candidateSha256"));
        payload.put("generationStepId", requireText(generationStepId, "generationStepId"));
        payload.put("generationResultHash", requireHash(generationResultHash, "generationResultHash"));
        Map<String, Object> diff = Map.of(
                "schema", SCHEMA,
                "type", "selection",
                "mode", "replace_selection");
        return new Stored(Map.copyOf(payload), diff);
    }

    public static Stored edit(Stored base, String replacement) {
        Objects.requireNonNull(base);
        requireStoredShape(base.payload(), base.diff());
        String value = requireReplacement(replacement);
        Map<String, Object> payload = new LinkedHashMap<>(base.payload());
        payload.put("replacement", value);
        payload.put("replacementSha256", sha256(value));
        // candidateSha256 依赖不可变 Evidence，必须由调用方重建后再写入。
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

    public static Materialized reconstruct(
            Map<String, Object> storedPayload,
            Map<String, Object> storedDiff,
            Evidence evidence) {
        Objects.requireNonNull(evidence);
        requireStoredShape(storedPayload, storedDiff);
        String bundleId = string(storedPayload, "evidenceBundleId");
        String itemId = string(storedPayload, "evidenceItemId");
        String resourceId = string(storedPayload, "resourceId");
        String sourceHash = hash(storedPayload, "sourceContentSha256");
        int start = integer(storedPayload, "selectionStartCodePoint");
        int end = integer(storedPayload, "selectionEndCodePoint");
        String selectedHash = hash(storedPayload, "selectedTextSha256");
        String replacement = string(storedPayload, "replacement");
        String replacementHash = hash(storedPayload, "replacementSha256");
        String candidateHash = hash(storedPayload, "candidateSha256");
        OffsetDateTime updatedAt = timestamp(storedPayload, "resourceUpdatedAt");

        int sourceLength = evidence.content().codePointCount(0, evidence.content().length());
        if (!bundleId.equals(evidence.bundleId())
                || !itemId.equals(evidence.itemId())
                || !"chapter_content".equals(evidence.resourceType())
                || !resourceId.equals(evidence.resourceId())
                || !updatedAt.toInstant().equals(evidence.resourceUpdatedAt().toInstant())
                || !sourceHash.equals(evidence.contentSha256())
                || !sourceHash.equals(sha256(evidence.content()))
                || start != evidence.selectionStartCodePoint()
                || end != evidence.selectionEndCodePoint()
                || start < 0
                || end <= start
                || end > sourceLength
                || !replacementHash.equals(sha256(replacement))) {
            throw integrityError();
        }
        String selected = slice(evidence.content(), start, end);
        String prefix = slice(evidence.content(), 0, start);
        String suffix = slice(evidence.content(), end, sourceLength);
        String candidate = prefix + replacement + suffix;
        if (!selectedHash.equals(sha256(selected)) || !candidateHash.equals(sha256(candidate))) {
            throw integrityError();
        }

        Map<String, Object> target = new LinkedHashMap<>();
        target.put("mode", "replace_selection");
        target.put("resourceType", "chapter_content");
        target.put("resourceId", resourceId);
        target.put("baseUpdatedAt", updatedAt.toString());
        target.put("baseContentHash", sourceHash);
        target.put("selectionStart", start);
        target.put("selectionEnd", end);
        target.put("selectedTextHash", selectedHash);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", "chapter_draft");
        payload.put("operation", "rewrite_chapter_selection");
        payload.put("target", Map.copyOf(target));
        payload.put("resourceType", "chapter_content");
        payload.put("resourceId", resourceId);
        payload.put("baseUpdatedAt", updatedAt.toString());
        payload.put("baseContentHash", sourceHash);
        payload.put("selectionStart", start);
        payload.put("selectionEnd", end);
        payload.put("selectedTextHash", selectedHash);
        payload.put("selectedText", selected);
        payload.put("contextBefore", slice(evidence.content(), Math.max(0, start - 1_000), start));
        payload.put("contextAfter", slice(evidence.content(), end, Math.min(sourceLength, end + 1_000)));
        payload.put("selection", Map.of(
                "start", start,
                "end", end,
                "selectedText", selected,
                "selectedTextHash", selectedHash));
        payload.put("replacement", replacement);
        payload.put("contentSha256", replacementHash);
        payload.put("candidate", candidate);
        payload.put("candidatePrefix", prefix);
        payload.put("candidateSuffix", suffix);

        Map<String, Object> diff = new LinkedHashMap<>();
        diff.put("type", "selection");
        diff.put("mode", "replace_selection");
        diff.put("resourceType", "chapter_content");
        diff.put("resourceId", resourceId);
        diff.put("selectionStart", start);
        diff.put("selectionEnd", end);
        diff.put("selectedText", selected);
        diff.put("replacement", replacement);
        diff.put("before", evidence.content());
        diff.put("after", candidate);
        diff.put("candidate", candidate);
        diff.put("prefix", prefix);
        diff.put("suffix", suffix);
        return new Materialized(Map.copyOf(payload), Map.copyOf(diff));
    }

    public static boolean isStored(Map<String, Object> payload) {
        return SCHEMA.equals(payload.get("schema"));
    }

    public static String sha256(String content) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(content.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }

    private static void requireStoredShape(
            Map<String, Object> payload, Map<String, Object> diff) {
        if (!SCHEMA.equals(payload.get("schema"))
                || !"chapter_draft".equals(payload.get("kind"))
                || !"rewrite_chapter_selection".equals(payload.get("operation"))
                || !"chapter_content".equals(payload.get("resourceType"))
                || !SCHEMA.equals(diff.get("schema"))
                || !"selection".equals(diff.get("type"))
                || !"replace_selection".equals(diff.get("mode"))) {
            throw integrityError();
        }
        string(payload, "evidenceBundleId");
        string(payload, "evidenceItemId");
        string(payload, "resourceId");
        timestamp(payload, "resourceUpdatedAt");
        hash(payload, "sourceContentSha256");
        integer(payload, "selectionStartCodePoint");
        integer(payload, "selectionEndCodePoint");
        hash(payload, "selectedTextSha256");
        String replacement = string(payload, "replacement");
        if (replacement.isBlank()) throw integrityError();
        hash(payload, "replacementSha256");
        hash(payload, "candidateSha256");
        string(payload, "generationStepId");
        hash(payload, "generationResultHash");
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " 不能为空");
        return value;
    }

    private static String requireReplacement(String value) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException("replacement 不能为空");
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
        if (!(item instanceof Number number)) throw integrityError();
        long result = number.longValue();
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

    private static String slice(String content, int start, int end) {
        return content.substring(
                content.offsetByCodePoints(0, start), content.offsetByCodePoints(0, end));
    }

    private static ApiException integrityError() {
        return new ApiException(
                409,
                "ARTIFACT_REVISION_INTEGRITY_ERROR",
                "待审核草案的不可变修订或 Evidence 无法通过完整性校验");
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
