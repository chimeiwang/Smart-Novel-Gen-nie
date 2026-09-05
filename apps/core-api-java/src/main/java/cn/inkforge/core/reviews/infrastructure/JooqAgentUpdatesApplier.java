package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.contracts.api.ArtifactSelectionRef;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.Source;
import cn.inkforge.core.reviews.application.AgentUpdatesExecutor;
import cn.inkforge.core.reviews.application.AgentUpdatesFrozenSources;
import cn.inkforge.core.reviews.application.AgentUpdatesIdentity;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;

/**
 * 已物化建议的所选项采用事务。历史目标必须已由 Core 按冻结来源解析成 ID，不能在批准时按当前名称重找。
 * 本类不生成候选、修改审核状态或提交 Run；调用方的审核事务若失败，正式写入一起回滚。
 */
public final class JooqAgentUpdatesApplier {
    private static final List<String> ENTITY_SECTIONS = List.of("characters", "locations", "items", "factions", "glossaries");
    private static final Map<String, ResourceKind> KINDS = Map.ofEntries(
            Map.entry("characters", ResourceKind.CHARACTER), Map.entry("locations", ResourceKind.LOCATION),
            Map.entry("items", ResourceKind.ITEM), Map.entry("factions", ResourceKind.FACTION),
            Map.entry("glossaries", ResourceKind.GLOSSARY), Map.entry("characterExperiences", ResourceKind.CHARACTER_EXPERIENCE),
            Map.entry("outline", ResourceKind.OUTLINE_NODE), Map.entry("outlineAdjustments", ResourceKind.OUTLINE_NODE),
            Map.entry("foreshadowing", ResourceKind.FORESHADOWING), Map.entry("references", ResourceKind.REFERENCE));
    private static final Map<String, ResourceKind> TEXTS = Map.of("outlineContent", ResourceKind.OUTLINE_CONTENT,
            "worldSetting", ResourceKind.WORLD_SETTING, "storyBackground", ResourceKind.STORY_BACKGROUND);
    private static final Map<String, String> ALIASES = Map.of("characters", "characterId", "locations", "locationId",
            "items", "itemId", "factions", "factionId", "glossaries", "glossaryId", "references", "referenceId");
    private final CoreDatabase database;
    private final JooqAgentUpdatesEvidenceReader reader;
    private final AgentUpdatesExecutor writer;

    public JooqAgentUpdatesApplier(CoreDatabase database, JooqAgentUpdatesEvidenceReader reader, AgentUpdatesExecutor writer) {
        this.database = Objects.requireNonNull(database);
        this.reader = Objects.requireNonNull(reader);
        this.writer = Objects.requireNonNull(writer);
    }

    public int apply(String novelId, String userId, String artifactId, int revision,
            Map<String, Object> materializedUpdates, List<ArtifactSelectionRef> selectedRefs,
            AgentUpdatesFrozenSources sources) {
        if (artifactId == null || artifactId.isEmpty() || revision < 1) throw new IllegalArgumentException("草案身份无效");
        // 在副本上按原索引派生请求键；原候选、原 refs 和用于决定幂等的用户请求均不改写。
        Map<String, Object> prepared = AgentUpdatesExecutor.filter(materializedUpdates, null);
        for (String section : AgentUpdatesIdentity.createSections()) {
            List<Map<String, Object>> values = items(prepared, section);
            for (int index = 0; index < values.size(); index++) {
                Map<String, Object> item = values.get(index);
                if ("create".equals(item.get("action"))) item.put("clientRequestId",
                        AgentUpdatesIdentity.requestKey(artifactId, revision, section, index));
            }
        }
        Map<String, Object> selected = AgentUpdatesExecutor.filter(prepared, selectedRefs);
        if (selected.isEmpty()) throw new IllegalArgumentException("没有选择任何可应用更新");
        Set<Source> created = new HashSet<>();
        for (String section : AgentUpdatesIdentity.createSections()) {
            for (Map<String, Object> item : items(selected, section)) {
                if ("create".equals(item.get("action"))) created.add(new Source(KINDS.get(section),
                        AgentUpdatesIdentity.resourceId(userId, novelId, section, (String) item.get("clientRequestId"))));
            }
        }
        return database.transactionResult(tx -> {
            lockNovel(tx, novelId, userId);
            verifySelected(tx, novelId, selected, sources, created);
            int count = 0;
            // 同一实体可以被连续修改；冻结来源只在所有写入前核验，逐项 CAS 读取本事务自己的最新写入。
            for (String section : ENTITY_SECTIONS) count += applyItems(tx, novelId, userId, selected, section);
            count += applyItems(tx, novelId, userId, selected, "characterExperiences");
            Map<String, Object> outline = new LinkedHashMap<>();
            for (String key : List.of("outline", "outlineAdjustments", "outlineTreeMode")) {
                if (selected.containsKey(key)) outline.put(key, selected.get(key));
            }
            if (!items(outline, "outline").isEmpty() || !items(outline, "outlineAdjustments").isEmpty()) {
                count += writer.applyMaterialized(novelId, userId, outline, null, null);
            }
            if (!items(selected, "foreshadowing").isEmpty()) {
                count += writer.applyMaterialized(novelId, userId, Map.of("foreshadowing", selected.get("foreshadowing")), null, null);
            }
            count += applyItems(tx, novelId, userId, selected, "references");
            Map<String, Object> texts = new LinkedHashMap<>();
            Map<String, OffsetDateTime> expectedLore = new LinkedHashMap<>();
            for (String section : TEXTS.keySet()) {
                if (selected.containsKey(section)) {
                    texts.put(section, selected.get(section));
                    expectedLore.put(section, sources.require(TEXTS.get(section), novelId).updatedAt());
                }
            }
            if (!texts.isEmpty()) count += writer.applyMaterialized(novelId, userId, texts, expectedLore.get("outlineContent"), expectedLore);
            if (count == 0) throw new IllegalArgumentException("agent_updates 不包含可应用更新");
            return count;
        });
    }

    private void verifySelected(DSLContext tx, String novel, Map<String, Object> selected, AgentUpdatesFrozenSources sources,
            Set<Source> created) {
        Set<Source> checked = new HashSet<>();
        for (String section : KINDS.keySet()) {
            for (Map<String, Object> item : items(selected, section)) {
                boolean create = "create".equals(item.get("action"));
                // V2 writer 只允许这类无 ID 引用命中本组新建节点，不会以当前名称重找历史节点。
                boolean inBatchOutline = section.equals("outlineAdjustments") && !create && text(item.get("nodeId")) == null;
                if (!create && !inBatchOutline) {
                    String id = targetId(section, item);
                    Source target = new Source(KINDS.get(section), id);
                    if (!created.contains(target)) {
                        if (checked.add(target)) verifyTarget(tx, novel, target, sources);
                        if ("delete".equals(item.get("action"))) verifyDelete(tx, novel, target, sources);
                    }
                }
                if (!"delete".equals(item.get("action"))) verifyReferences(tx, novel, section, item, sources, created);
            }
        }
        if (selected.containsKey("outlineAdjustments") && "replace".equals(selected.get("outlineTreeMode"))) {
            List<Map<String, Object>> before = sources.requireCollection("outline_tree_membership", novel);
            same(before, reader.outlineTreeMembers(tx, novel));
            for (Map<String, Object> member : before) {
                Source target = new Source(ResourceKind.OUTLINE_NODE, (String) member.get("id"));
                if (checked.add(target)) verifyTarget(tx, novel, target, sources);
            }
        }
        for (String section : TEXTS.keySet()) {
            if (selected.containsKey(section)) verifyTarget(tx, novel, new Source(TEXTS.get(section), novel), sources);
        }
    }

    private void verifyTarget(DSLContext tx, String novel, Source target, AgentUpdatesFrozenSources sources) {
        var before = sources.require(target.kind(), target.id());
        same(before.before(), currentTarget(tx, novel, target.kind(), target.id()));
    }

    private void verifyDelete(DSLContext tx, String novel, Source target, AgentUpdatesFrozenSources sources) {
        List<String> dependencies = switch (target.kind()) {
            case CHARACTER -> List.of("character_experiences", "character_relations", "character_state_changes", "character_owned_items");
            case LOCATION -> List.of("location_children", "location_based_factions", "location_territories");
            case FACTION -> List.of("faction_territories", "faction_characters");
            case OUTLINE_NODE -> List.of("outline_delete_children");
            default -> List.of();
        };
        if (dependencies.isEmpty()) return;
        var current = reader.capture(tx, novel, List.of(new Source(target.kind(), target.id(), true)));
        for (String type : dependencies) {
            Object after = current.stream().filter(value -> value.resourceType().equals(type)).findFirst().orElseThrow().contentJson();
            same(Map.of("items", sources.requireCollection(type, target.id())), after);
        }
    }

    private void verifyReferences(DSLContext tx, String novel, String section, Map<String, Object> item,
            AgentUpdatesFrozenSources sources, Set<Source> created) {
        if (section.equals("characterExperiences") && "create".equals(item.get("action")) && text(item.get("characterId")) == null) {
            throw new ApiException(409, "AGENT_UPDATES_EVIDENCE_REQUIRED", "经历所属人物尚未按冻结来源物化为 ID");
        }
        Map<String, ResourceKind> references = switch (section) {
            case "characters" -> Map.of("factionId", ResourceKind.FACTION);
            case "locations" -> Map.of("parentId", ResourceKind.LOCATION);
            case "items" -> Map.of("ownerId", ResourceKind.CHARACTER);
            case "factions" -> Map.of("baseId", ResourceKind.LOCATION);
            case "characterExperiences" -> Map.of("characterId", ResourceKind.CHARACTER, "chapterId", ResourceKind.CHAPTER_REFERENCE);
            case "outlineAdjustments" -> text(item.get("parentKey")) == null
                    ? Map.of("parentId", ResourceKind.OUTLINE_NODE, "linkedChapterId", ResourceKind.CHAPTER_REFERENCE)
                    : Map.of("linkedChapterId", ResourceKind.CHAPTER_REFERENCE);
            default -> Map.of();
        };
        for (Map.Entry<String, ResourceKind> reference : references.entrySet()) {
            String id = text(item.get(reference.getKey()));
            if (id == null) continue;
            if (created.contains(new Source(reference.getValue(), id))) continue;
            // 显式引用只复验冻结身份、存在与归属，不把引用正文的无关编辑提升为目标 CAS。
            sources.require(reference.getValue(), id);
            currentTarget(tx, novel, reference.getValue(), id);
        }
    }

    private int applyItems(DSLContext tx, String novel, String user, Map<String, Object> selected, String section) {
        int count = 0;
        for (Map<String, Object> item : items(selected, section)) {
            if (!"create".equals(item.get("action"))) {
                Map<String, Object> current = currentTarget(tx, novel, KINDS.get(section), targetId(section, item));
                item.put("expectedUpdatedAt", current.get("updatedAt"));
            }
            count += writer.applyMaterialized(novel, user, Map.of(section, List.of(item)), null, null);
        }
        return count;
    }

    private Map<String, Object> currentTarget(DSLContext tx, String novel, ResourceKind kind, String id) {
        try {
            return reader.readTarget(tx, novel, kind, id);
        } catch (ApiException error) {
            if (!error.code().equals("AGENT_UPDATES_SOURCE_INVALID")) throw error;
            throw new ApiException(409, "AGENT_UPDATES_SOURCE_CHANGED", "所选建议的来源已删除或归属已变化，请重新生成或返工");
        }
    }

    private static String targetId(String section, Map<String, Object> item) {
        String id = text(item.get(section.equals("outline") || section.equals("outlineAdjustments") ? "nodeId" : "id"));
        if (id == null && ALIASES.containsKey(section)) id = text(item.get(ALIASES.get(section)));
        if (id == null) throw new ApiException(409, "AGENT_UPDATES_EVIDENCE_REQUIRED", "历史目标尚未按冻结来源物化为 ID");
        return id;
    }

    private static String text(Object value) { return value instanceof String text && !text.isEmpty() ? text : null; }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> items(Map<String, Object> updates, String section) {
        if (!updates.containsKey(section)) return List.of();
        if (!(updates.get(section) instanceof List<?> values) || values.stream().anyMatch(item -> !(item instanceof Map<?, ?>))) {
            throw new IllegalArgumentException(section + " 必须是对象数组");
        }
        return (List<Map<String, Object>>) (List<?>) values;
    }

    private static void same(Object before, Object after) {
        if (!ExecutionCanonicalJson.sha256(before).equals(ExecutionCanonicalJson.sha256(after))) {
            throw new ApiException(409, "AGENT_UPDATES_SOURCE_CHANGED", "所选建议的来源已变化，请重新生成或返工");
        }
    }

    private static void lockNovel(DSLContext tx, String novel, String user) {
        var owner = tx.fetchOne("SELECT \"userId\" FROM public.\"Novel\" WHERE id = ? FOR UPDATE", novel);
        if (owner == null || !Objects.equals(owner.get("userId", String.class), user)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
        try {
            // 与既有 Lore/Outline/Reference 写入器相同的锁及顺序，不引入新的 Run 互斥协议。
            long key = ByteBuffer.wrap(MessageDigest.getInstance("SHA-256").digest(novel.getBytes(StandardCharsets.UTF_8))).getLong();
            tx.fetch("SELECT pg_advisory_xact_lock(?)", key);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("JDK 缺少 SHA-256", error);
        }
    }
}
