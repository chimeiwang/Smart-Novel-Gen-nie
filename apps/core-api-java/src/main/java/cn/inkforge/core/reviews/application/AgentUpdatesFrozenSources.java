package cn.inkforge.core.reviews.application;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 将一次 Run 冻结的资料证据整理为按真实业务身份读取的只读索引。 */
public final class AgentUpdatesFrozenSources {
    private static final Set<ResourceKind> SINGLETONS = EnumSet.of(
            ResourceKind.OUTLINE_CONTENT,
            ResourceKind.WORLD_SETTING,
            ResourceKind.STORY_BACKGROUND);
    private static final Map<String, ResourceKind> TARGET_KINDS = targetKinds();
    private static final Map<String, DirectReferenceSpec> DIRECT_REFERENCES = Map.of(
            "faction_reference", new DirectReferenceSpec(ResourceKind.FACTION, Map.of(
                    ResourceKind.CHARACTER, Set.of("factionId"))),
            "location_reference", new DirectReferenceSpec(ResourceKind.LOCATION, Map.of(
                    ResourceKind.LOCATION, Set.of("parentId"),
                    ResourceKind.FACTION, Set.of("baseId"))),
            "character_reference", new DirectReferenceSpec(ResourceKind.CHARACTER, Map.of(
                    ResourceKind.ITEM, Set.of("ownerId"),
                    ResourceKind.CHARACTER_EXPERIENCE, Set.of("characterId"))),
            "outline_node_reference", new DirectReferenceSpec(ResourceKind.OUTLINE_NODE, Map.of(
                    ResourceKind.OUTLINE_NODE, Set.of("parentId"))),
            "chapter_reference_reference", new DirectReferenceSpec(ResourceKind.CHAPTER_REFERENCE, Map.of(
                    ResourceKind.CHARACTER_EXPERIENCE, Set.of("chapterId"),
                    ResourceKind.OUTLINE_NODE, Set.of("linkedChapterId"))));
    private static final Map<String, CollectionSpec> COLLECTIONS = Map.ofEntries(
            Map.entry("character_experiences", new CollectionSpec(
                    ResourceKind.CHARACTER, directOrDelete(), ResourceKind.CHARACTER_EXPERIENCE)),
            Map.entry("character_relations", new CollectionSpec(
                    ResourceKind.CHARACTER, directOrDelete(), null)),
            Map.entry("character_state_changes", new CollectionSpec(
                    ResourceKind.CHARACTER, directOrDelete(), null)),
            Map.entry("faction_territories", new CollectionSpec(
                    ResourceKind.FACTION, directOrDelete(), null)),
            Map.entry("outline_children", new CollectionSpec(
                    ResourceKind.OUTLINE_NODE, Set.of(List.of("direct_relation")), ResourceKind.OUTLINE_NODE)),
            Map.entry("outline_sibling_structure", new CollectionSpec(
                    ResourceKind.OUTLINE_NODE, Set.of(List.of("direct_relation")), null)),
            Map.entry("character_owned_items", new CollectionSpec(
                    ResourceKind.CHARACTER, Set.of(List.of("delete_impact")), null)),
            Map.entry("faction_characters", new CollectionSpec(
                    ResourceKind.FACTION, Set.of(List.of("delete_impact")), null)),
            Map.entry("location_children", new CollectionSpec(
                    ResourceKind.LOCATION, Set.of(List.of("delete_impact")), null)),
            Map.entry("location_based_factions", new CollectionSpec(
                    ResourceKind.LOCATION, Set.of(List.of("delete_impact")), null)),
            Map.entry("location_territories", new CollectionSpec(
                    ResourceKind.LOCATION, Set.of(List.of("delete_impact")), null)),
            Map.entry("outline_delete_children", new CollectionSpec(
                    ResourceKind.OUTLINE_NODE.wireName(), Set.of(List.of("delete_impact")), null, false)),
            Map.entry("outline_tree_membership", new CollectionSpec(
                    "novel", Set.of(List.of("delete_impact")), null, true)));

    private final Map<SourceKey, Snapshot> sources;
    private final Map<CollectionKey, List<Map<String, Object>>> collections;

    public AgentUpdatesFrozenSources(String novelId, List<WorkflowEvidenceItemPlan> evidence) {
        if (novelId == null || novelId.isEmpty()) throw invalid("小说 ID 不能为空");
        if (evidence == null) throw invalid("冻结资料清单不能为空");
        Map<SourceKey, Snapshot> indexedSources = new LinkedHashMap<>();
        Map<CollectionKey, List<Map<String, Object>>> indexedCollections = new LinkedHashMap<>();
        for (WorkflowEvidenceItemPlan item : evidence) {
            if (item == null) throw invalid("冻结资料清单不能包含空项");
            ResourceKind targetKind = TARGET_KINDS.get(item.resourceType());
            if (targetKind != null) {
                indexTarget(novelId, item, targetKind, indexedSources);
                continue;
            }
            DirectReferenceSpec reference = DIRECT_REFERENCES.get(item.resourceType());
            if (reference != null) {
                indexDirectReference(novelId, item, reference, indexedSources);
                continue;
            }
            CollectionSpec collection = COLLECTIONS.get(item.resourceType());
            if (collection != null) {
                indexCollection(novelId, item, collection, indexedSources, indexedCollections);
            }
            // 运行上下文等非业务 Evidence 不属于资料采用门禁，在此明确忽略。
        }
        sources = Collections.unmodifiableMap(indexedSources);
        collections = Collections.unmodifiableMap(indexedCollections);
    }

    public Snapshot require(ResourceKind kind, String id) {
        if (kind == null || id == null || id.isEmpty()) throw required("资料来源身份不能为空");
        Snapshot result = sources.get(new SourceKey(kind, id));
        if (result == null) throw required("缺少所选资料的冻结来源：" + kind.wireName() + ":" + id);
        return result;
    }

    /** 返回该类型全部已索引来源，保持 Evidence 中首次出现的稳定顺序。 */
    public List<Snapshot> snapshots(ResourceKind kind) {
        Objects.requireNonNull(kind, "资料来源类型不能为空");
        return sources.values().stream().filter(snapshot -> snapshot.kind() == kind).toList();
    }

    public List<Map<String, Object>> requireCollection(String resourceType, String targetId) {
        if (resourceType == null || resourceType.isEmpty() || targetId == null || targetId.isEmpty()) {
            throw required("资料集合身份不能为空");
        }
        List<Map<String, Object>> result = collections.get(new CollectionKey(resourceType, targetId));
        if (result == null) throw required("缺少所选资料的冻结集合：" + resourceType + ":" + targetId);
        return result;
    }

    private static void indexTarget(
            String novelId,
            WorkflowEvidenceItemPlan item,
            ResourceKind kind,
            Map<SourceKey, Snapshot> sources) {
        requireJsonEvidenceShape(item);
        requireMetadata(item, kind, item.resourceId(), List.of("target"));
        boolean singleton = SINGLETONS.contains(kind);
        if (singleton && !novelId.equals(item.resourceId())) {
            throw invalid("单例全文必须绑定当前小说");
        }
        if (!item.exists()) {
            if (!singleton) throw invalid("非单例资料来源不能以缺席哨兵代替");
            requireAbsenceSentinel(item.metadata(), novelId);
            putSource(sources, new Snapshot(kind, novelId, false, null, null));
            return;
        }
        if (item.metadata().containsKey("absenceSentinel")) {
            throw invalid("存在的资料来源不能携带缺席哨兵");
        }
        Map<String, Object> before = requireObject(item.contentJson(), "资料来源正文必须是 JSON 对象");
        String rowId = requireString(before, "id", "资料来源真实 ID 不能为空");
        if (!singleton && !rowId.equals(item.resourceId())) {
            throw invalid("资料来源资源 ID 与完整行 ID 不一致");
        }
        if (kind != ResourceKind.CHARACTER_EXPERIENCE) {
            requireEqualString(before, "novelId", novelId, "资料来源不属于当前小说");
        }
        OffsetDateTime updatedAt = requireMatchingUpdatedAt(before, item.resourceUpdatedAt());
        putSource(sources, new Snapshot(kind, singleton ? novelId : rowId, true, before, updatedAt));
    }

    private static void indexDirectReference(
            String novelId,
            WorkflowEvidenceItemPlan item,
            DirectReferenceSpec reference,
            Map<SourceKey, Snapshot> sources) {
        requireJsonEvidenceShape(item);
        if (!item.exists()) throw invalid("直接引用必须包含完整来源");
        Map<String, Object> metadata = item.metadata();
        ResourceKind targetKind = requireTargetKind(metadata);
        String targetId = requireString(metadata, "targetId", "直接引用目标 ID 不能为空");
        requireRoles(metadata, List.of("direct_reference"));
        Set<String> allowedFields = reference.fieldsByTarget().get(targetKind);
        String prefix = targetKind.wireName() + ":" + targetId + ":";
        String field = item.resourceId().startsWith(prefix) ? item.resourceId().substring(prefix.length()) : "";
        if (allowedFields == null || !allowedFields.contains(field)) {
            throw invalid("直接引用身份与关系字段不一致");
        }
        if (metadata.containsKey("absenceSentinel")) {
            throw invalid("直接引用不能携带缺席哨兵");
        }
        Map<String, Object> before = requireObject(item.contentJson(), "直接引用正文必须是 JSON 对象");
        String rowId = requireString(before, "id", "直接引用真实 ID 不能为空");
        requireEqualString(before, "novelId", novelId, "直接引用不属于当前小说");
        OffsetDateTime updatedAt = requireMatchingUpdatedAt(before, item.resourceUpdatedAt());
        putSource(sources, new Snapshot(reference.referencedKind(), rowId, true, before, updatedAt));
    }

    private static void indexCollection(
            String novelId,
            WorkflowEvidenceItemPlan item,
            CollectionSpec specification,
            Map<SourceKey, Snapshot> sources,
            Map<CollectionKey, List<Map<String, Object>>> collections) {
        requireJsonEvidenceShape(item);
        if (!item.exists() || item.resourceUpdatedAt() != null) {
            throw invalid("具名资料集合必须是无顶层时间戳的完整 JSON 快照");
        }
        requireMetadata(item, specification.targetType(), item.resourceId(), null);
        if (specification.membership() && !novelId.equals(item.resourceId())) {
            throw invalid("大纲树成员集合必须绑定当前小说");
        }
        List<String> roles = requireRoles(item.metadata(), null);
        if (!specification.allowedRoles().contains(roles)) throw invalid("具名资料集合角色无效");
        if (item.metadata().containsKey("absenceSentinel")) throw invalid("具名资料集合不能携带缺席哨兵");
        Map<String, Object> content = requireObject(
                item.contentJson(), "具名资料集合正文必须是 JSON 对象");
        if (!content.keySet().equals(Set.of("items")) || !(content.get("items") instanceof List<?> values)) {
            throw invalid("具名资料集合必须只包含 items 数组");
        }
        List<Map<String, Object>> rows = new ArrayList<>(values.size());
        Set<String> membershipIds = specification.membership()
                ? new HashSet<>()
                : Set.of();
        for (Object value : values) {
            Map<String, Object> row = requireObject(value, "具名资料集合成员必须是 JSON 对象");
            rows.add(row);
            if (specification.membership()) {
                String rowId = requireString(row, "id", "大纲树成员 ID 不能为空");
                if (!membershipIds.add(rowId)) throw invalid("大纲树成员 ID 重复");
            } else if (specification.nestedSourceKind() == ResourceKind.CHARACTER_EXPERIENCE) {
                requireEqualString(row, "characterId", item.resourceId(), "人物经历不属于集合目标");
                String rowId = requireString(row, "id", "人物经历真实 ID 不能为空");
                putSource(sources, new Snapshot(
                        ResourceKind.CHARACTER_EXPERIENCE, rowId, true, row, optionalUpdatedAt(row)));
            } else if (specification.nestedSourceKind() == ResourceKind.OUTLINE_NODE) {
                requireEqualString(row, "parentId", item.resourceId(), "大纲子节点不属于集合目标");
                requireEqualString(row, "novelId", novelId, "大纲子节点不属于当前小说");
                String rowId = requireString(row, "id", "大纲子节点真实 ID 不能为空");
                putSource(sources, new Snapshot(ResourceKind.OUTLINE_NODE, rowId, true, row, optionalUpdatedAt(row)));
            }
        }
        List<Map<String, Object>> frozenRows = Collections.unmodifiableList(rows);
        CollectionKey key = new CollectionKey(item.resourceType(), item.resourceId());
        List<Map<String, Object>> previous = collections.putIfAbsent(key, frozenRows);
        if (previous != null && !previous.equals(frozenRows)) {
            throw invalid("同一具名资料集合存在冲突快照");
        }
    }

    private static void requireJsonEvidenceShape(WorkflowEvidenceItemPlan item) {
        if (item.resourceRevision() != null
                || item.contentText() != null
                || item.rangeStartCodePoint() != null
                || item.rangeEndCodePoint() != null) {
            throw invalid("资料来源必须使用无范围的 JSON 快照");
        }
    }

    private static void requireMetadata(
            WorkflowEvidenceItemPlan item,
            ResourceKind targetKind,
            String targetId,
            List<String> roles) {
        requireMetadata(item, targetKind.wireName(), targetId, roles);
    }

    private static void requireMetadata(
            WorkflowEvidenceItemPlan item,
            String targetType,
            String targetId,
            List<String> roles) {
        requireEqualString(item.metadata(), "targetType", targetType, "冻结资料目标类型不一致");
        requireEqualString(item.metadata(), "targetId", targetId, "冻结资料目标 ID 不一致");
        if (roles != null) requireRoles(item.metadata(), roles);
    }

    private static ResourceKind requireTargetKind(Map<String, Object> metadata) {
        String wireName = requireString(metadata, "targetType", "冻结资料目标类型不能为空");
        ResourceKind result = TARGET_KINDS.get(wireName);
        if (result == null) throw invalid("冻结资料目标类型无效");
        return result;
    }

    private static List<String> requireRoles(Map<String, Object> metadata, List<String> expected) {
        Object value = metadata.get("roles");
        if (!(value instanceof List<?> raw)) throw invalid("冻结资料角色必须是字符串数组");
        List<String> result = new ArrayList<>(raw.size());
        for (Object role : raw) {
            if (!(role instanceof String text)) throw invalid("冻结资料角色必须是字符串数组");
            result.add(text);
        }
        List<String> frozen = List.copyOf(result);
        if (expected != null && !frozen.equals(expected)) throw invalid("冻结资料角色不一致");
        return frozen;
    }

    private static void requireAbsenceSentinel(Map<String, Object> metadata, String novelId) {
        Map<String, Object> sentinel = requireObject(
                metadata.get("absenceSentinel"), "缺席单例必须携带缺席哨兵");
        if (!sentinel.equals(Map.of("resourceType", "novel", "resourceId", novelId))) {
            throw invalid("缺席单例的哨兵身份无效");
        }
    }

    private static String requireString(Map<String, Object> value, String field, String message) {
        Object found = value.get(field);
        if (!(found instanceof String text) || text.isEmpty()) throw invalid(message);
        return text;
    }

    private static void requireEqualString(Map<String, Object> value, String field, String expected, String message) {
        if (!(value.get(field) instanceof String text) || !text.equals(expected)) throw invalid(message);
    }

    private static OffsetDateTime requireMatchingUpdatedAt(
            Map<String, Object> before,
            OffsetDateTime evidenceUpdatedAt) {
        OffsetDateTime rowUpdatedAt = optionalUpdatedAt(before);
        if (!Objects.equals(rowUpdatedAt, evidenceUpdatedAt)) {
            throw invalid("资料来源更新时间与完整行不一致");
        }
        return evidenceUpdatedAt;
    }

    private static OffsetDateTime optionalUpdatedAt(Map<String, Object> value) {
        Object raw = value.get("updatedAt");
        if (raw == null) return null;
        if (!(raw instanceof String text)) {
            throw invalid("资料来源更新时间必须是 ISO-8601 字符串或 null");
        }
        try {
            return OffsetDateTime.parse(text);
        } catch (DateTimeParseException error) {
            throw invalid("资料来源更新时间格式无效");
        }
    }

    private static Map<String, Object> requireObject(Object value, String message) {
        if (!(value instanceof Map<?, ?> map)) throw invalid(message);
        return freezeMap(map);
    }

    private static Map<String, Object> freezeMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw invalid("JSON 对象 key 必须是字符串");
            result.put(key, freeze(entry.getValue()));
        }
        return Collections.unmodifiableMap(result);
    }

    private static Object freeze(Object value) {
        if (value == null || value instanceof String || value instanceof Number || value instanceof Boolean) {
            return value;
        }
        if (value instanceof Map<?, ?> map) return freezeMap(map);
        if (value instanceof List<?> list) {
            List<Object> result = new ArrayList<>(list.size());
            for (Object nested : list) result.add(freeze(nested));
            return Collections.unmodifiableList(result);
        }
        throw invalid("冻结资料包含不支持的 JSON 值");
    }

    private static void putSource(Map<SourceKey, Snapshot> sources, Snapshot snapshot) {
        SourceKey key = new SourceKey(snapshot.kind(), snapshot.id());
        Snapshot previous = sources.putIfAbsent(key, snapshot);
        if (previous != null && !previous.equals(snapshot)) {
            throw invalid("同类型真实资料 ID 存在冲突快照");
        }
    }

    private static Map<String, ResourceKind> targetKinds() {
        Map<String, ResourceKind> result = new LinkedHashMap<>();
        for (ResourceKind kind : ResourceKind.values()) result.put(kind.wireName(), kind);
        return Collections.unmodifiableMap(result);
    }

    private static Set<List<String>> directOrDelete() {
        return Set.of(List.of("direct_relation"), List.of("direct_relation", "delete_impact"));
    }

    private static ApiException required(String message) {
        return new ApiException(409, "AGENT_UPDATES_EVIDENCE_REQUIRED", message);
    }

    private static ApiException invalid(String message) {
        return new ApiException(409, "AGENT_UPDATES_SOURCE_INVALID", message);
    }

    public record Snapshot(
            ResourceKind kind,
            String id,
            boolean exists,
            Map<String, Object> before,
            OffsetDateTime updatedAt) {
        public Snapshot {
            Objects.requireNonNull(kind, "资料来源类型不能为空");
            if (id == null || id.isEmpty()) throw new IllegalArgumentException("资料来源 ID 不能为空");
            if (exists && before == null) {
                throw new IllegalArgumentException("存在的资料来源必须包含完整快照");
            }
            if (!exists && (before != null || updatedAt != null)) {
                throw new IllegalArgumentException("缺席资料来源不能包含快照或更新时间");
            }
            before = before == null ? null : freezeMap(before);
        }
    }

    private record SourceKey(ResourceKind kind, String id) {}

    private record CollectionKey(String resourceType, String targetId) {}

    private record DirectReferenceSpec(
            ResourceKind referencedKind,
            Map<ResourceKind, Set<String>> fieldsByTarget) {}

    private record CollectionSpec(
            String targetType,
            Set<List<String>> allowedRoles,
            ResourceKind nestedSourceKind,
            boolean membership) {
        private CollectionSpec(
                ResourceKind targetKind,
                Set<List<String>> allowedRoles,
                ResourceKind nestedSourceKind) {
            this(targetKind.wireName(), allowedRoles, nestedSourceKind, false);
        }
    }
}
