package cn.inkforge.core.reviews.domain;

import cn.inkforge.core.platform.http.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/** ReviewArtifact 状态、载荷和 Unicode 选区的确定性规则。 */
public final class ReviewArtifactRules {

    private static final Map<String, Set<String>> TRANSITIONS = Map.of(
            "draft", Set.of("draft", "under_review", "awaiting_user"),
            "under_review", Set.of("under_review", "draft", "awaiting_user"),
            "awaiting_user", Set.of("awaiting_user", "draft", "under_review", "applying"),
            "applying", Set.of("applying", "awaiting_user", "applied"),
            "applied", Set.of("applied"));
    private static final Set<String> SELECTION_MODES = Set.of(
            "replace_selection",
            "outline_content_selection",
            "outline_node_content_selection");
    private static final Set<String> NORMAL_MODES = Set.of(
            "existing_chapter", "new_next_chapter", "normal_outline");
    private static final Set<String> IDENTITY_FIELDS = Set.of(
            "resourceType",
            "resourceId",
            "baseUpdatedAt",
            "baseContentHash",
            "selectionStart",
            "selectionEnd",
            "selectedTextHash");

    private ReviewArtifactRules() {}

    public static boolean canTransition(String current, String target) {
        return TRANSITIONS.getOrDefault(current, Set.of()).contains(target);
    }

    public static void requireTransition(String current, String target) {
        if (!canTransition(current, target)) {
            throw new ApiException(
                    409,
                    "ARTIFACT_STATUS_CONFLICT",
                    "待审核草案不能从 " + current + " 流转到 " + target);
        }
    }

    public static void requireAgentPayload(String kind, Map<String, Object> payload) {
        if (payload == null || !kind.equals(payload.get("kind"))) {
            throw new IllegalArgumentException("草案 kind 必须与 payload.kind 一致");
        }
        if (payload.containsKey("_inkforgeControl")) {
            throw new IllegalArgumentException("草案 payload 不得包含保留控制字段");
        }
    }

    public static boolean isSelection(Map<String, Object> payload) {
        Object targetValue = payload.get("target");
        if (!(targetValue instanceof Map<?, ?> target)) return false;
        return SELECTION_MODES.contains(target.get("mode"));
    }

    public static void requireKnownTargetMode(Map<String, Object> payload) {
        Object targetValue = payload.get("target");
        if (!(targetValue instanceof Map<?, ?> target)) return;
        Object mode = target.get("mode");
        if (mode != null
                && (!(mode instanceof String value)
                        || (!SELECTION_MODES.contains(value) && !NORMAL_MODES.contains(value)))) {
            throw new ApiException(
                    409,
                    "ARTIFACT_SELECTION_TARGET_INVALID",
                    "选区草案 target mode 与类型不匹配");
        }
    }

    public static SelectionMaterialization materializeSelection(
            Map<String, Object> originalPayload,
            String kind,
            SelectionSource source) {
        requireAgentPayload(kind, originalPayload);
        requireKnownTargetMode(originalPayload);
        Object targetValue = originalPayload.get("target");
        if (!(targetValue instanceof Map<?, ?> rawTarget)
                || !(rawTarget.get("mode") instanceof String mode)
                || !SELECTION_MODES.contains(mode)
                || !Set.of("chapter_draft", "outline_draft").contains(kind)) {
            throw invalidTarget();
        }
        String expectedType = switch (mode) {
            case "replace_selection" -> "chapter_content";
            case "outline_content_selection" -> "outline_content";
            case "outline_node_content_selection" -> "outline_node_content";
            default -> throw invalidTarget();
        };
        Map<String, Object> identity = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : rawTarget.entrySet()) {
            if (entry.getKey() instanceof String key) identity.put(key, entry.getValue());
        }
        for (String field : IDENTITY_FIELDS) {
            if (identity.containsKey(field)
                    && originalPayload.containsKey(field)
                    && !java.util.Objects.equals(identity.get(field), originalPayload.get(field))) {
                throw sourceConflict(source);
            }
            if (originalPayload.containsKey(field)) {
                identity.put(field, originalPayload.get(field));
            }
        }
        String resourceType = string(identity.get("resourceType"));
        String resourceId = string(identity.get("resourceId"));
        if (!expectedType.equals(resourceType)
                || resourceId == null
                || !resourceType.equals(source.resourceType())
                || !resourceId.equals(source.resourceId())) {
            throw sourceConflict(source);
        }
        int start = integer(identity.get("selectionStart"));
        int end = integer(identity.get("selectionEnd"));
        int sourceLength = codePointLength(source.content());
        if (start < 0 || end <= start || end > sourceLength) {
            throw sourceConflict(source);
        }
        String baseHash = hash(identity.get("baseContentHash"));
        String selectedHash = hash(identity.get("selectedTextHash"));
        OffsetDateTime expectedUpdatedAt = time(identity.get("baseUpdatedAt"));
        if (!source.updatedAt().toInstant().equals(expectedUpdatedAt.toInstant())
                || !sha256(source.content()).equals(baseHash)) {
            throw sourceConflict(source);
        }
        String selected = slice(source.content(), start, end);
        if (!sha256(selected).equals(selectedHash)) {
            throw sourceConflict(source);
        }
        Object providedSelected = originalPayload.get("selectedText");
        if (providedSelected != null && !selected.equals(providedSelected)) {
            throw sourceConflict(source);
        }
        Object replacementValue = originalPayload.get("replacement");
        if (!(replacementValue instanceof String replacement) || replacement.strip().isEmpty()) {
            throw new ApiException(
                    409,
                    "ARTIFACT_SELECTION_REPLACEMENT_INVALID",
                    "选区草案缺少非空 replacement");
        }
        String prefix = slice(source.content(), 0, start);
        String suffix = slice(source.content(), end, sourceLength);
        String candidate = prefix + replacement + suffix;

        Map<String, Object> payload = new LinkedHashMap<>(originalPayload);
        payload.put("resourceType", resourceType);
        payload.put("resourceId", resourceId);
        payload.put("baseUpdatedAt", identity.get("baseUpdatedAt"));
        payload.put("baseContentHash", baseHash);
        payload.put("selectionStart", start);
        payload.put("selectionEnd", end);
        payload.put("selectedTextHash", selectedHash);
        payload.put("selectedText", selected);
        payload.put("contextBefore", slice(source.content(), Math.max(0, start - 1_000), start));
        payload.put("contextAfter", slice(source.content(), end, Math.min(sourceLength, end + 1_000)));
        Map<String, Object> normalizedTarget = new LinkedHashMap<>();
        normalizedTarget.put("mode", mode);
        for (String field : IDENTITY_FIELDS) normalizedTarget.put(field, payload.get(field));
        payload.put("target", normalizedTarget);
        payload.put("selection", Map.of(
                "start", start,
                "end", end,
                "selectedText", selected,
                "selectedTextHash", selectedHash));
        payload.put("candidate", candidate);
        payload.put("candidatePrefix", prefix);
        payload.put("candidateSuffix", suffix);

        Map<String, Object> diff = new LinkedHashMap<>();
        diff.put("type", "selection");
        diff.put("mode", mode);
        diff.put("resourceType", resourceType);
        diff.put("resourceId", resourceId);
        diff.put("selectionStart", start);
        diff.put("selectionEnd", end);
        diff.put("selectedText", selected);
        diff.put("replacement", replacement);
        diff.put("before", source.content());
        diff.put("after", candidate);
        diff.put("candidate", candidate);
        diff.put("prefix", prefix);
        diff.put("suffix", suffix);
        return new SelectionMaterialization(payload, diff);
    }

    public static String sha256(String content) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(content.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }

    public static int codePointLength(String content) {
        return content.codePointCount(0, content.length());
    }

    public static String slice(String content, int start, int end) {
        int beginIndex = content.offsetByCodePoints(0, start);
        int endIndex = content.offsetByCodePoints(0, end);
        return content.substring(beginIndex, endIndex);
    }

    private static int integer(Object value) {
        if (!(value instanceof Number number)) return -1;
        long result = number.longValue();
        return result < Integer.MIN_VALUE || result > Integer.MAX_VALUE ? -1 : (int) result;
    }

    private static String string(Object value) {
        return value instanceof String text && !text.isEmpty() ? text : null;
    }

    private static String hash(Object value) {
        if (!(value instanceof String text) || !text.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("选区草案 hash 无效");
        }
        return text;
    }

    private static OffsetDateTime time(Object value) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("选区草案缺少 baseUpdatedAt");
        }
        try {
            return OffsetDateTime.parse(text);
        } catch (DateTimeParseException exception) {
            throw new IllegalArgumentException("选区草案 baseUpdatedAt 无效", exception);
        }
    }

    private static ApiException invalidTarget() {
        return new ApiException(
                409,
                "ARTIFACT_SELECTION_TARGET_INVALID",
                "选区草案 target mode 与类型不匹配");
    }

    private static ApiException sourceConflict(SelectionSource source) {
        return new ApiException(
                409,
                "ARTIFACT_SOURCE_VERSION_CONFLICT",
                "选区草案的来源版本已变化",
                Map.of(
                        "resourceType", source.resourceType(),
                        "resourceId", source.resourceId()));
    }
}
