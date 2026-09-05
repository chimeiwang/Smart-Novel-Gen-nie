package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.protocol.WorkflowOutputValidator;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 结构化候选只存一份原始 updates；冻结来源、正式写入元数据与展示 Diff 由业务适配重建。 */
public final class DurableAgentUpdatesArtifact {
    public static final String SCHEMA = "durable.agent-updates-artifact.v1";
    private static final Set<String> OPERATIONS = Set.of(
            "create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing");
    private static final Set<String> OUTPUT_KEYS = Set.of("summary", "updates", "updatesSha256");
    private static final Set<String> STORED_KEYS = Set.of("schema", "kind", "operation", "novelId", "summary", "updates",
            "updatesSha256", "evidenceBundleId", "evidenceManifestSha256", "producingStepId", "producingResultHash");
    private static final Map<String, Object> DIFF = Map.of("schema", SCHEMA, "type", "agent_updates");
    private static final List<String> ARRAYS = List.of("characters", "locations", "items", "factions", "glossaries",
            "characterExperiences", "outline", "outlineAdjustments", "foreshadowing", "references");
    private static final Set<String> TEXTS = Set.of("outlineContent", "worldSetting", "storyBackground");
    private static final Set<String> INTEGER_FIELDS = Set.of("order", "estimatedWordCount", "actualWordCount",
            "chapterStartOrder", "chapterEndOrder");
    private static final Map<String, String> ENTITY_IDS = Map.of("characters", "characterId", "locations", "locationId",
            "items", "itemId", "factions", "factionId", "glossaries", "glossaryId");
    private static final Map<String, String> ENTITY_LINKS = Map.of("characters", "factionId", "locations", "parentId",
            "items", "ownerId", "factions", "baseId");

    private DurableAgentUpdatesArtifact() {}

    public static Stored create(String operation, String bundleId, String manifestHash, String novelId,
            Map<String, Object> output, String producingStepId, String producingResultHash,
            Map<String, Object> providerSchema) {
        validateOutput(output, providerSchema);
        Map<String, Object> payload = new LinkedHashMap<>(output);
        payload.put("schema", SCHEMA);
        payload.put("kind", "agent_updates");
        payload.put("operation", operation(operation));
        payload.put("novelId", identity(novelId));
        payload.put("evidenceBundleId", identity(bundleId));
        payload.put("evidenceManifestSha256", hash(manifestHash));
        payload.put("producingStepId", identity(producingStepId));
        payload.put("producingResultHash", hash(producingResultHash));
        return new Stored(freezeMap(payload), DIFF);
    }

    /** Schema 来自该 Run 的冻结执行计划；语义复验与 Python AgentUpdatesOutput 保持一致。 */
    public static void validateOutput(Map<String, Object> output, Map<String, Object> providerSchema) {
        if (output == null || !OUTPUT_KEYS.equals(output.keySet())) throw invalid();
        Map<String, Object> provider = new LinkedHashMap<>();
        provider.put("summary", output.get("summary"));
        provider.put("updates", output.get("updates"));
        WorkflowOutputValidator.validate(providerSchema, provider);
        if (!(output.get("summary") instanceof String summary) || summary.isEmpty()
                || summary.codePointCount(0, summary.length()) > 1000) throw invalid();
        Map<String, Object> updates = object(output.get("updates"));
        boolean any = TEXTS.stream().anyMatch(updates::containsKey);
        for (String section : ARRAYS) {
            for (Map<String, Object> item : objects(updates.get(section))) {
                any = true;
                validateItem(section, item);
            }
        }
        if (!any) throw invalid();
        validateOutlineTree(updates);
        if (!ExecutionCanonicalJson.sha256(updates).equals(hash(output.get("updatesSha256")))) throw invalid();
    }

    public static Map<String, Object> output(Map<String, Object> stored, Map<String, Object> providerSchema) {
        Map<String, Object> output = new LinkedHashMap<>();
        for (String field : OUTPUT_KEYS) output.put(field, stored.get(field));
        validateOutput(output, providerSchema);
        return freezeMap(output);
    }

    /** 这里只重建原始候选，不宣称已经补齐 writer 的版本/请求键或正式 Diff。 */
    public static Map<String, Object> reconstruct(String expectedOperation, Map<String, Object> stored,
            Map<String, Object> storedDiff, String bundleId, String manifestHash, String novelId,
            String producingStepId, String producingResultHash,
            Map<String, Object> providerSchema) {
        try {
            if (!STORED_KEYS.equals(stored.keySet()) || !SCHEMA.equals(stored.get("schema"))
                    || !"agent_updates".equals(stored.get("kind")) || !DIFF.equals(storedDiff)
                    || !operation(expectedOperation).equals(stored.get("operation"))
                    || !identity(novelId).equals(stored.get("novelId"))
                    || !identity(bundleId).equals(stored.get("evidenceBundleId"))
                    || !hash(manifestHash).equals(stored.get("evidenceManifestSha256"))
                    || !identity(producingStepId).equals(stored.get("producingStepId"))
                    || !hash(producingResultHash).equals(stored.get("producingResultHash"))) throw invalid();
            return output(stored, providerSchema);
        } catch (IllegalArgumentException | NullPointerException exception) {
            throw new ApiException(409, "ARTIFACT_REVISION_INTEGRITY_ERROR", "结构化资料候选的不可变修订或 Evidence 绑定无效");
        }
    }

    public static boolean isStored(Map<String, Object> payload) { return SCHEMA.equals(payload.get("schema")); }

    private static void validateItem(String section, Map<String, Object> item) {
        for (String field : INTEGER_FIELDS) {
            if (item.get(field) != null) integer(item.get(field));
        }
        String action = text(item.get("action"));
        if (ENTITY_IDS.containsKey(section)) {
            String link = ENTITY_LINKS.get(section);
            if (link != null) nullableId(item, link);
            if (!"create".equals(action)) {
                String lookup = section.equals("glossaries") ? "term" : "name";
                locator(item, "id", ENTITY_IDS.get(section), lookup);
                if ("update".equals(action)) business(item, Set.of("action", "id", ENTITY_IDS.get(section)));
            }
            return;
        }
        switch (section) {
            case "characterExperiences" -> {
                nullableId(item, "chapterId");
                if ("create".equals(action)) locator(item, "characterId", "characterName");
                else {
                    nonEmpty(item.get("id"));
                    if ("update".equals(action)) business(item, Set.of("action", "id"));
                }
            }
            case "outline" -> {
                nonEmpty(item.get("nodeId"));
                business(item, Set.of("nodeId"));
            }
            case "outlineAdjustments" -> validateOutlineItem(item, action);
            case "foreshadowing" -> {
                if ("create".equals(action)) nonEmpty(item.get("name"));
                else {
                    locator(item, "id", "name");
                    if ("update".equals(action)) business(item, Set.of("action", "id"));
                }
            }
            case "references" -> {
                if ("create".equals(action)) nonBlank(item.get("title"));
                else {
                    locator(item, "id", "referenceId");
                    String first = text(item.get("id"));
                    String second = text(item.get("referenceId"));
                    if (!first.isEmpty() && !second.isEmpty() && !first.equals(second)) throw invalid();
                    if ("update".equals(action)) business(item, Set.of("action", "id", "referenceId"));
                }
            }
            default -> throw invalid();
        }
    }

    private static void validateOutlineItem(Map<String, Object> item, String action) {
        if ("delete".equals(action)) {
            if (text(item.get("nodeId")).isEmpty()) {
                nonEmpty(item.get(item.containsKey("title") ? "title" : "nodeTitle"));
            }
            return;
        }
        nullableId(item, "linkedChapterId");
        String parentKey = text(item.get("parentKey"));
        if (parentKey.isEmpty()) nullableId(item, "parentId");
        String titleField = item.containsKey("title") ? "title" : "nodeTitle";
        if (item.containsKey(titleField)) nonBlank(item.get(titleField));
        if ("create".equals(action)) {
            nonBlank(item.get(titleField));
            if ("stage".equals(item.get("kind"))) {
                if (item.get("parentId") != null || !parentKey.isEmpty()) throw invalid();
            } else if (item.get("parentId") == null && parentKey.isEmpty()) throw invalid();
        } else {
            locator(item, "nodeId", "nodeTitle", "title");
            business(item, Set.of("action", "nodeId", "nodeTitle"));
        }
        boolean startPresent = item.containsKey("chapterStartOrder");
        boolean endPresent = item.containsKey("chapterEndOrder");
        Object start = item.get("chapterStartOrder");
        Object end = item.get("chapterEndOrder");
        if (("create".equals(action) || startPresent && endPresent) && (start == null) != (end == null)) throw invalid();
        if (start != null && integer(start) <= 0 || end != null && integer(end) <= 0) throw invalid();
        if (start != null && end != null && integer(start) > integer(end)) throw invalid();
    }

    private static void validateOutlineTree(Map<String, Object> updates) {
        List<Map<String, Object>> adjustments = objects(updates.get("outlineAdjustments"));
        if (updates.containsKey("outlineTreeMode") && adjustments.isEmpty()) throw invalid();
        boolean replace = "replace".equals(updates.get("outlineTreeMode"));
        Map<String, Map<String, Object>> created = new LinkedHashMap<>();
        for (Map<String, Object> item : adjustments) {
            boolean create = "create".equals(item.get("action"));
            String parentKey = text(item.get("parentKey"));
            if (replace && (!create || item.get("parentId") != null && parentKey.isEmpty())) throw invalid();
            if (!parentKey.isEmpty()) {
                Map<String, Object> parent = created.get(parentKey);
                if (parent == null) throw invalid();
                // patch 的中间 update 可能改变父节点类型，不按原 create.kind 推断动态状态。
                if (replace) {
                    String expected = Map.of("plot_unit", "stage", "chapter_group", "plot_unit").get(item.get("kind"));
                    if (expected != null && !expected.equals(parent.get("kind"))) throw invalid();
                }
            }
            String clientKey = text(item.get("clientKey"));
            if (create && !clientKey.isEmpty()) {
                if (replace && created.containsKey(clientKey)) throw invalid();
                created.put(clientKey, item);
            }
        }
    }

    private static void locator(Map<String, Object> item, String... fields) {
        for (String field : fields) if (!text(item.get(field)).isEmpty()) return;
        throw invalid();
    }

    private static void business(Map<String, Object> item, Set<String> controlFields) {
        if (item.keySet().stream().allMatch(controlFields::contains)) throw invalid();
    }

    private static void nullableId(Map<String, Object> item, String field) {
        if (item.get(field) != null) nonEmpty(item.get(field));
    }

    private static int integer(Object value) {
        if (!(value instanceof Byte || value instanceof Short || value instanceof Integer || value instanceof Long
                || value instanceof BigInteger)) throw invalid();
        BigInteger integer = new BigInteger(value.toString());
        if (integer.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) < 0
                || integer.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) > 0) throw invalid();
        return integer.intValueExact();
    }

    private static String text(Object value) { return value instanceof String text ? text : ""; }

    private static String nonEmpty(Object value) {
        if (!(value instanceof String text) || text.isEmpty()) throw invalid();
        return text;
    }

    private static void nonBlank(Object value) { if (nonEmpty(value).strip().isEmpty()) throw invalid(); }

    private static String identity(Object value) {
        String result = nonEmpty(value);
        if (result.isBlank()) throw invalid();
        return result;
    }

    private static String hash(Object value) {
        if (!(value instanceof String text) || !text.matches("[0-9a-f]{64}")) throw invalid();
        return text;
    }

    private static String operation(String value) {
        if (value == null || !OPERATIONS.contains(value)) throw invalid();
        return value;
    }

    private static List<Map<String, Object>> objects(Object value) {
        if (value == null) return List.of();
        if (!(value instanceof List<?> items)) throw invalid();
        return items.stream().map(DurableAgentUpdatesArtifact::object).toList();
    }

    private static Map<String, Object> object(Object value) {
        if (!(value instanceof Map<?, ?> map)) throw invalid();
        Map<String, Object> result = new LinkedHashMap<>();
        map.forEach((key, nested) -> {
            if (!(key instanceof String field)) throw invalid();
            result.put(field, nested);
        });
        return result;
    }

    private static Map<String, Object> freezeMap(Map<String, Object> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(key, freeze(value)));
        return Collections.unmodifiableMap(result);
    }

    private static Object freeze(Object value) {
        if (value instanceof Map<?, ?>) return freezeMap(object(value));
        if (value instanceof List<?> list) {
            List<Object> result = new ArrayList<>();
            list.forEach(item -> result.add(freeze(item)));
            return Collections.unmodifiableList(result);
        }
        if (value == null || value instanceof String || value instanceof Boolean || value instanceof Number) return value;
        throw invalid();
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("结构化资料候选不符合冻结协议或完整性约束");
    }

    public record Stored(Map<String, Object> payload, Map<String, Object> diff) {}
}
