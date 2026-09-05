package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 完整定向快照及一跳关联；不读 workspace，不遍历无关资料，也不新增小说级写锁。 */
public final class JooqAgentUpdatesEvidenceReader implements AgentUpdatesEvidenceReader {
    private static final TypeReference<Map<String, Object>> OBJECT = new TypeReference<>() {};
    private final ObjectMapper json;

    public JooqAgentUpdatesEvidenceReader(ObjectMapper json) { this.json = Objects.requireNonNull(json); }

    @Override
    public WorkflowEvidenceItemPlan captureIndex(DSLContext tx, String novelId) {
        if (tx.fetchOne("SELECT id FROM public.\"Novel\" WHERE id = ?", novelId) == null) throw invalid("小说不存在");
        List<Map<String, Object>> index = new ArrayList<>();
        for (ResourceKind kind : ResourceKind.values()) {
            String table = switch (kind) {
                case CHARACTER -> "Character";
                case LOCATION -> "Location";
                case ITEM -> "Item";
                case FACTION -> "Faction";
                case GLOSSARY -> "Glossary";
                case CHARACTER_EXPERIENCE -> "CharacterExperience";
                case OUTLINE_NODE -> "OutlineNode";
                case FORESHADOWING -> "Foreshadowing";
                case REFERENCE -> "ReferenceMaterial";
                case CHAPTER_REFERENCE -> "Chapter";
                default -> null;
            };
            if (table == null) continue;
            String fields = switch (kind) {
                case GLOSSARY -> "'term', source.term";
                case CHARACTER_EXPERIENCE -> "'characterId', source.\"characterId\", 'order', source.\"order\"";
                case OUTLINE_NODE -> "'title', source.title, 'parentId', source.\"parentId\", 'kind', source.kind, 'order', source.\"order\"";
                case CHAPTER_REFERENCE -> "'title', source.title, 'order', source.\"order\"";
                case REFERENCE -> "'title', source.title";
                default -> "'name', source.name";
            };
            index.addAll(rows(tx, "SELECT jsonb_build_object('resourceType', ?, 'id', source.id, " + fields
                    + ")::text AS snapshot FROM public.\"" + table + "\" source "
                    + (kind == ResourceKind.CHARACTER_EXPERIENCE
                    ? "JOIN public.\"Character\" owner ON owner.id = source.\"characterId\" WHERE owner.\"novelId\" = ?"
                    : "WHERE source.\"novelId\" = ?") + " ORDER BY source.id", kind.wireName(), novelId));
        }
        return new WorkflowEvidenceItemPlan("agent_updates_index", novelId, true, null, null, null,
                Map.of("items", index), null, null, Map.of("targetType", "novel", "targetId", novelId, "roles", List.of("index")));
    }

    @Override
    public List<WorkflowEvidenceItemPlan> capture(DSLContext tx, String novelId, List<Source> sources) {
        Objects.requireNonNull(tx);
        if (novelId == null || novelId.isEmpty()) throw new IllegalArgumentException("小说 ID 不能为空");
        if (tx.fetchOne("SELECT id FROM public.\"Novel\" WHERE id = ?", novelId) == null) {
            throw invalid("小说不存在");
        }
        // 排序/合并仅针对 Core 读取清单，不改写候选数组或作者的 selectedUpdateRefs。
        Map<String, Source> unique = new LinkedHashMap<>();
        for (Source source : sources) {
            String key = source.kind().wireName() + ":" + source.id();
            unique.merge(key, source, (left, right) -> new Source(left.kind(), left.id(),
                    left.includeDeleteImpact() || right.includeDeleteImpact()));
        }
        List<WorkflowEvidenceItemPlan> result = new ArrayList<>();
        for (Source source : unique.values().stream()
                .sorted(Comparator.comparing((Source value) -> value.kind().wireName()).thenComparing(Source::id)).toList()) {
            Map<String, Object> row = readTarget(tx, novelId, source.kind(), source.id());
            result.add(item(source.kind().wireName(), source.id(), row, source, "target"));
            if (row == null) continue;
            directReferences(tx, novelId, source, row, result);
            if (source.includeDeleteImpact()) deleteImpact(tx, novelId, source, result);
        }
        return List.copyOf(result);
    }

    @Override
    public List<WorkflowEvidenceItemPlan> captureOutlineTree(DSLContext tx, String novelId) {
        if (tx.fetchOne("SELECT id FROM public.\"Novel\" WHERE id = ?", novelId) == null) throw invalid("小说不存在");
        List<Map<String, Object>> members = outlineTreeMembers(tx, novelId);
        List<WorkflowEvidenceItemPlan> result = new ArrayList<>();
        for (Map<String, Object> member : members) {
            String id = (String) member.get("id");
            Source target = new Source(ResourceKind.OUTLINE_NODE, id, true);
            result.add(item(ResourceKind.OUTLINE_NODE.wireName(), id,
                    readTarget(tx, novelId, ResourceKind.OUTLINE_NODE, id), target, "target"));
        }
        result.add(new WorkflowEvidenceItemPlan("outline_tree_membership", novelId, true, null, null,
                null, Map.of("items", members), null, null,
                Map.of("targetType", "novel", "targetId", novelId, "roles", List.of("delete_impact"))));
        return List.copyOf(result);
    }

    List<Map<String, Object>> outlineTreeMembers(DSLContext tx, String novelId) {
        return rows(tx, """
                SELECT jsonb_build_object('id', id)::text AS snapshot FROM public."OutlineNode"
                WHERE "novelId" = ? ORDER BY id FOR UPDATE
                """, novelId);
    }

    // 采用普通更新时只读取实际目标，不扩展无关关系集合或引用正文。
    Map<String, Object> readTarget(DSLContext tx, String novelId, ResourceKind kind, String id) {
        boolean singleton = switch (kind) {
            case OUTLINE_CONTENT, WORLD_SETTING, STORY_BACKGROUND -> true;
            default -> false;
        };
        if (singleton && !novelId.equals(id)) throw invalid("单例全文必须在当前小说内定位");
        String table = switch (kind) {
            case CHARACTER -> "Character";
            case LOCATION -> "Location";
            case ITEM -> "Item";
            case FACTION -> "Faction";
            case GLOSSARY -> "Glossary";
            case CHARACTER_EXPERIENCE -> "CharacterExperience";
            case OUTLINE_NODE -> "OutlineNode";
            case FORESHADOWING -> "Foreshadowing";
            case REFERENCE -> "ReferenceMaterial";
            case OUTLINE_CONTENT -> "Outline";
            case WORLD_SETTING -> "WorldSetting";
            case STORY_BACKGROUND -> "StoryBackground";
            case CHAPTER_REFERENCE -> "Chapter";
        };
        List<Map<String, Object>> found;
        if (kind == ResourceKind.CHARACTER_EXPERIENCE) {
            found = rows(tx, """
                    SELECT to_jsonb(source)::text AS snapshot FROM public."CharacterExperience" source
                    JOIN public."Character" owner ON owner.id = source."characterId"
                    WHERE source.id = ? AND owner."novelId" = ? FOR UPDATE OF source, owner
                    """, id, novelId);
        } else {
            String projection = kind == ResourceKind.CHAPTER_REFERENCE
                    ? "jsonb_build_object('id', source.id, 'novelId', source.\"novelId\", 'title', source.title, "
                            + "'order', source.\"order\", 'status', source.status, 'updatedAt', source.\"updatedAt\")"
                    : "to_jsonb(source)";
            found = rows(tx, "SELECT " + projection + "::text AS snapshot FROM public.\"" + table + "\" source WHERE "
                    + (singleton ? "source.\"novelId\" = ?" : "source.id = ? AND source.\"novelId\" = ?")
                    + " FOR UPDATE", singleton ? new Object[] {novelId} : new Object[] {id, novelId});
        }
        if (found.size() > 1) throw invalid("资料来源存在多份权威记录");
        if (found.isEmpty()) {
            if (singleton) return null;
            throw invalid("资料来源不存在或不属于当前小说");
        }
        return found.getFirst();
    }

    private void directReferences(DSLContext tx, String novel, Source source, Map<String, Object> row,
            List<WorkflowEvidenceItemPlan> output) {
        switch (source.kind()) {
            case CHARACTER -> {
                reference(tx, novel, source, row, "factionId", ResourceKind.FACTION, output);
                collection(tx, source, "character_experiences", "direct_relation", output, """
                        SELECT to_jsonb(source)::text AS snapshot FROM public."CharacterExperience" source
                        WHERE source."characterId" = ? ORDER BY source.id FOR UPDATE
                        """, source.id());
                collection(tx, source, "character_relations", "direct_relation", output, """
                        SELECT to_jsonb(source)::text AS snapshot,
                          (owner."novelId" = ? AND target."novelId" = ?) AS in_scope
                        FROM public."CharacterRelation" source
                        LEFT JOIN public."Character" owner ON owner.id = source."characterId"
                        LEFT JOIN public."Character" target ON target.id = source."targetId"
                        WHERE source."characterId" = ? OR source."targetId" = ? ORDER BY source.id FOR UPDATE OF source
                        """, novel, novel, source.id(), source.id());
                collection(tx, source, "character_state_changes", "direct_relation", output, """
                        SELECT to_jsonb(source)::text AS snapshot FROM public."CharacterStateChange" source
                        WHERE source."characterId" = ? ORDER BY source.id FOR UPDATE
                        """, source.id());
            }
            case LOCATION -> reference(tx, novel, source, row, "parentId", ResourceKind.LOCATION, output);
            case ITEM -> reference(tx, novel, source, row, "ownerId", ResourceKind.CHARACTER, output);
            case FACTION -> {
                reference(tx, novel, source, row, "baseId", ResourceKind.LOCATION, output);
                collection(tx, source, "faction_territories", "direct_relation", output, """
                        SELECT to_jsonb(source)::text AS snapshot,
                          (faction."novelId" = ? AND location."novelId" = ?) AS in_scope
                        FROM public."_FactionTerritories" source
                        LEFT JOIN public."Faction" faction ON faction.id = source."A"
                        LEFT JOIN public."Location" location ON location.id = source."B"
                        WHERE source."A" = ? ORDER BY source."B" FOR UPDATE OF source
                        """, novel, novel, source.id());
            }
            case CHARACTER_EXPERIENCE -> {
                reference(tx, novel, source, row, "characterId", ResourceKind.CHARACTER, output);
                reference(tx, novel, source, row, "chapterId", ResourceKind.CHAPTER_REFERENCE, output);
            }
            case OUTLINE_NODE -> {
                reference(tx, novel, source, row, "parentId", ResourceKind.OUTLINE_NODE, output);
                reference(tx, novel, source, row, "linkedChapterId", ResourceKind.CHAPTER_REFERENCE, output);
                collection(tx, source, "outline_children", "direct_relation", output, """
                        SELECT to_jsonb(source)::text AS snapshot FROM public."OutlineNode" source
                        WHERE source."parentId" = ? AND source."novelId" = ? ORDER BY source.id FOR UPDATE
                        """, source.id(), novel);
                collection(tx, source, "outline_sibling_structure", "direct_relation", output, """
                        SELECT jsonb_build_object('id', source.id, 'parentId', source."parentId", 'kind', source.kind,
                          'chapterStartOrder', source."chapterStartOrder", 'chapterEndOrder', source."chapterEndOrder")::text AS snapshot
                        FROM public."OutlineNode" source WHERE source."novelId" = ?
                          AND source."parentId" IS NOT DISTINCT FROM ? AND source.id <> ? ORDER BY source.id FOR UPDATE
                        """, novel, row.get("parentId"), source.id());
            }
            default -> { }
        }
    }

    private void deleteImpact(DSLContext tx, String novel, Source source, List<WorkflowEvidenceItemPlan> output) {
        switch (source.kind()) {
            case CHARACTER -> collection(tx, source, "character_owned_items", "delete_impact", output, """
                    SELECT jsonb_build_object('id', source.id, 'ownerId', source."ownerId")::text AS snapshot
                    FROM public."Item" source WHERE source."ownerId" = ? AND source."novelId" = ? ORDER BY source.id FOR UPDATE
                    """, source.id(), novel);
            case FACTION -> collection(tx, source, "faction_characters", "delete_impact", output, """
                    SELECT jsonb_build_object('id', source.id, 'factionId', source."factionId")::text AS snapshot
                    FROM public."Character" source WHERE source."factionId" = ? AND source."novelId" = ? ORDER BY source.id FOR UPDATE
                    """, source.id(), novel);
            case LOCATION -> {
                collection(tx, source, "location_children", "delete_impact", output, """
                        SELECT jsonb_build_object('id', source.id, 'parentId', source."parentId")::text AS snapshot
                        FROM public."Location" source WHERE source."parentId" = ? AND source."novelId" = ? ORDER BY source.id FOR UPDATE
                        """, source.id(), novel);
                collection(tx, source, "location_based_factions", "delete_impact", output, """
                        SELECT jsonb_build_object('id', source.id, 'baseId', source."baseId")::text AS snapshot
                        FROM public."Faction" source WHERE source."baseId" = ? AND source."novelId" = ? ORDER BY source.id FOR UPDATE
                        """, source.id(), novel);
                collection(tx, source, "location_territories", "delete_impact", output, """
                        SELECT to_jsonb(source)::text AS snapshot,
                          (faction."novelId" = ? AND location."novelId" = ?) AS in_scope
                        FROM public."_FactionTerritories" source
                        LEFT JOIN public."Faction" faction ON faction.id = source."A"
                        LEFT JOIN public."Location" location ON location.id = source."B"
                        WHERE source."B" = ? ORDER BY source."A" FOR UPDATE OF source
                        """, novel, novel, source.id());
            }
            case OUTLINE_NODE -> collection(tx, source, "outline_delete_children", "delete_impact", output, """
                    SELECT jsonb_build_object('id', source.id, 'parentId', source."parentId")::text AS snapshot
                    FROM public."OutlineNode" source WHERE source."parentId" = ? AND source."novelId" = ?
                    ORDER BY source.id FOR UPDATE
                    """, source.id(), novel);
            default -> { }
        }
    }

    private void reference(DSLContext tx, String novel, Source target, Map<String, Object> row, String field,
            ResourceKind kind, List<WorkflowEvidenceItemPlan> output) {
        if (row.get(field) instanceof String id) {
            output.add(item(kind.wireName() + "_reference", target.kind().wireName() + ":" + target.id() + ":" + field,
                    readTarget(tx, novel, kind, id), target, "direct_reference"));
        }
    }

    private void collection(DSLContext tx, Source source, String type, String role,
            List<WorkflowEvidenceItemPlan> output, String sql, Object... args) {
        output.add(item(type, source.id(), Map.of("items", rows(tx, sql, args)), source, role));
    }

    private static WorkflowEvidenceItemPlan item(String type, String id, Map<String, Object> content, Source target, String role) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("targetType", target.kind().wireName());
        metadata.put("targetId", target.id());
        boolean alsoDeleteDependency = target.includeDeleteImpact() && Set.of("character_experiences",
                "character_relations", "character_state_changes", "faction_territories").contains(type);
        metadata.put("roles", alsoDeleteDependency ? List.of(role, "delete_impact") : List.of(role));
        if (content == null) metadata.put("absenceSentinel", Map.of("resourceType", "novel", "resourceId", target.id()));
        OffsetDateTime updated = content != null && content.get("updatedAt") instanceof String value
                ? OffsetDateTime.parse(value) : null;
        return new WorkflowEvidenceItemPlan(type, id, content != null, null, updated, null, content, null, null, metadata);
    }

    private List<Map<String, Object>> rows(DSLContext tx, String sql, Object... args) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Record record : tx.fetch(sql, args)) {
            if (record.field("in_scope") != null && !Boolean.TRUE.equals(record.get("in_scope", Boolean.class))) {
                throw invalid("直接关系两端必须都属于当前小说");
            }
            Map<String, Object> row = json.readValue(record.get("snapshot", String.class), OBJECT);
            for (String field : List.of("createdAt", "updatedAt")) {
                if (row.get(field) instanceof String value) {
                    row.put(field, DatabaseTimestamp.api(LocalDateTime.parse(value)).toString());
                }
            }
            result.add(row);
        }
        return result;
    }

    private static ApiException invalid(String message) {
        return new ApiException(409, "AGENT_UPDATES_SOURCE_INVALID", message);
    }
}
