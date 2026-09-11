package cn.inkforge.core.reviews.application;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 从不可变候选与冻结来源确定性重建既有 writer payload 和作者可见 Diff。 */
public final class AgentUpdatesMaterializer {
    private static final List<EntitySection> ENTITY_SECTIONS = List.of(
            entity(
                    "characters",
                    "角色",
                    ResourceKind.CHARACTER,
                    "name",
                    List.of("id", "characterId"),
                    "name",
                    "aliases",
                    "gender",
                    "age",
                    "identity",
                    "appearance",
                    "personality",
                    "background",
                    "factionId",
                    "combatAbility",
                    "powerLevel",
                    "specialSkills",
                    "currentStatus",
                    "coreDesire",
                    "shortTermGoal",
                    "behaviorBoundaries",
                    "speechStyle",
                    "relationshipPrinciples",
                    "statusNote"),
            entity(
                    "locations",
                    "地点",
                    ResourceKind.LOCATION,
                    "name",
                    List.of("id", "locationId"),
                    "name",
                    "aliases",
                    "type",
                    "parentId",
                    "description",
                    "climate",
                    "culture"),
            entity(
                    "items",
                    "物品",
                    ResourceKind.ITEM,
                    "name",
                    List.of("id", "itemId"),
                    "name",
                    "aliases",
                    "type",
                    "rarity",
                    "ownerId",
                    "description",
                    "effect",
                    "origin"),
            entity(
                    "factions",
                    "势力",
                    ResourceKind.FACTION,
                    "name",
                    List.of("id", "factionId"),
                    "name",
                    "aliases",
                    "type",
                    "baseId",
                    "description"),
            entity(
                    "glossaries",
                    "术语",
                    ResourceKind.GLOSSARY,
                    "term",
                    List.of("id", "glossaryId"),
                    "term",
                    "definition",
                    "category"));
    private static final List<String> EXPERIENCE_FIELDS = List.of("characterId", "chapterId", "content", "order");
    private static final List<String> OUTLINE_STATUS_FIELDS = List.of("status", "actualWordCount");
    private static final List<String> OUTLINE_FIELDS = List.of(
            "title",
            "content",
            "kind",
            "parentId",
            "status",
            "order",
            "linkedChapterId",
            "estimatedWordCount",
            "actualWordCount",
            "chapterStartOrder",
            "chapterEndOrder");
    private static final List<String> FORESHADOWING_FIELDS = List.of(
            "name", "plantedAt", "plantedContent", "expectedPayoff", "payoffAt", "status");
    private static final List<String> REFERENCE_FIELDS = List.of("title", "type", "content", "sourceUrl");
    private static final Map<String, String> FIELD_LABELS = fieldLabels();
    private static final Map<String, ResourceKind> INDEX_KINDS = indexKinds();

    private AgentUpdatesMaterializer() {}

    /** 将模型候选绑定到冻结来源，生成可执行载荷和作者可读的逐项差异。 */
    public static Materialized materialize(
            String userId,
            String novelId,
            String artifactId,
            int revision,
            Map<String, Object> output,
            AgentUpdatesFrozenSources sources) {
        requireIdentity(userId, "用户 ID");
        requireIdentity(novelId, "小说 ID");
        requireIdentity(artifactId, "草案 ID");
        if (revision < 1) throw new IllegalArgumentException("草案修订必须为正整数");
        Objects.requireNonNull(output, "结构化候选不能为空");
        Objects.requireNonNull(sources, "冻结来源不能为空");

        Object rawSummary = output.get("summary");
        if (!(rawSummary instanceof String summary)) throw new IllegalArgumentException("结构化候选说明无效");
        Map<String, Object> updates = mutableObject(output.get("updates"), "结构化候选 updates 无效");
        State state = new State(novelId, sources);
        List<Map<String, Object>> diff = new ArrayList<>();

        // 各分区共享同一内存状态，后续更新可以安全引用本候选前面新建的资源。
        for (EntitySection section : ENTITY_SECTIONS) {
            materializeEntities(userId, novelId, artifactId, revision, updates, section, state, diff);
        }
        materializeExperiences(userId, novelId, artifactId, revision, updates, state, diff);
        materializeOutlineStatuses(updates, state, diff);
        materializeOutlineAdjustments(userId, novelId, artifactId, revision, updates, state, diff);
        materializeForeshadowing(userId, novelId, artifactId, revision, updates, state, diff);
        materializeReferences(userId, novelId, artifactId, revision, updates, state, diff);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", "agent_updates");
        payload.put("summary", summary);
        payload.put("updates", updates);
        materializeTexts(novelId, updates, sources, payload, diff);
        return new Materialized(payload, diff);
    }

    private static void materializeEntities(
            String userId,
            String novelId,
            String artifactId,
            int revision,
            Map<String, Object> updates,
            EntitySection section,
            State state,
            List<Map<String, Object>> diff) {
        List<Map<String, Object>> items = mutableItems(updates, section.name());
        if (items == null) return;
        for (int index = 0; index < items.size(); index++) {
            Map<String, Object> item = items.get(index);
            String action = action(item, section.name());
            if ("create".equals(action)) {
                injectCreateIdentity(userId, novelId, artifactId, revision, section.name(), index, item);
                String id = AgentUpdatesIdentity.resourceId(
                        userId, novelId, artifactId, revision, section.name(), index);
                Map<String, Object> current = new LinkedHashMap<>();
                current.put("id", id);
                copyPresent(item, current, section.fields());
                completeCreateFields(
                        current,
                        section.fields(),
                        section.kind() == ResourceKind.CHARACTER ? Map.of("currentStatus", "active") : Map.of());
                validateEntityReferences(section.kind(), item, state);
                state.addNew(section.kind(), id, current);
                diff.add(diffItem(section.label(), action, display(current, null, section.lookupField(), id),
                        changedFields(null, current, section.fields(), new LinkedHashSet<>(section.fields()))));
                continue;
            }

            MutableResource target = state.resolve(
                    section.kind(),
                    firstNonEmpty(item, section.idFields()),
                    section.lookupField(),
                    text(item.get(section.lookupField())));
            Map<String, Object> before = target.current();
            item.put("id", target.id());
            if ("delete".equals(action)) {
                diff.add(diffItem(section.label(), action, display(null, before, section.lookupField(), target.id()),
                        deletedFields(before, section.fields())));
                state.remove(target);
                continue;
            }
            if (!"update".equals(action)) throw invalidCandidate(section.name() + " action 无效");
            validateEntityReferences(section.kind(), item, state);
            target.apply(item, section.fields());
            Map<String, Object> after = target.current();
            diff.add(diffItem(section.label(), action, display(after, before, section.lookupField(), target.id()),
                    changedFields(before, after, section.fields(), item.keySet())));
        }
    }

    private static void validateEntityReferences(ResourceKind kind, Map<String, Object> item, State state) {
        switch (kind) {
            case CHARACTER -> state.requireReference(ResourceKind.FACTION, item, "factionId");
            case LOCATION -> state.requireReference(ResourceKind.LOCATION, item, "parentId");
            case ITEM -> state.requireReference(ResourceKind.CHARACTER, item, "ownerId");
            case FACTION -> state.requireReference(ResourceKind.LOCATION, item, "baseId");
            default -> { }
        }
    }

    private static void materializeExperiences(
            String userId,
            String novelId,
            String artifactId,
            int revision,
            Map<String, Object> updates,
            State state,
            List<Map<String, Object>> diff) {
        String section = "characterExperiences";
        List<Map<String, Object>> items = mutableItems(updates, section);
        if (items == null) return;
        for (int index = 0; index < items.size(); index++) {
            Map<String, Object> item = items.get(index);
            String action = action(item, section);
            if ("create".equals(action)) {
                MutableResource character = state.resolve(
                        ResourceKind.CHARACTER,
                        text(item.get("characterId")),
                        "name",
                        text(item.get("characterName")));
                character.current();
                item.put("characterId", character.id());
                state.requireReference(ResourceKind.CHAPTER_REFERENCE, item, "chapterId");
                if (!item.containsKey("order") || item.get("order") == null) {
                    item.put("order", state.nextExperienceOrder(character.id()));
                }
                injectCreateIdentity(userId, novelId, artifactId, revision, section, index, item);
                String id = AgentUpdatesIdentity.resourceId(userId, novelId, artifactId, revision, section, index);
                Map<String, Object> current = new LinkedHashMap<>();
                current.put("id", id);
                copyPresent(item, current, EXPERIENCE_FIELDS);
                completeCreateFields(current, EXPERIENCE_FIELDS, Map.of());
                state.addNew(ResourceKind.CHARACTER_EXPERIENCE, id, current);
                diff.add(diffItem("角色经历", action, experienceName(current, character),
                        changedFields(null, current, EXPERIENCE_FIELDS, new LinkedHashSet<>(EXPERIENCE_FIELDS))));
                continue;
            }

            MutableResource target = state.resolveById(ResourceKind.CHARACTER_EXPERIENCE, requiredText(item, "id"));
            Map<String, Object> before = target.current();
            item.put("id", target.id());
            if ("delete".equals(action)) {
                diff.add(diffItem("角色经历", action, experienceName(before, state),
                        deletedFields(before, EXPERIENCE_FIELDS)));
                state.remove(target);
                continue;
            }
            if (!"update".equals(action)) throw invalidCandidate(section + " action 无效");
            state.requireReference(ResourceKind.CHAPTER_REFERENCE, item, "chapterId");
            target.apply(item, EXPERIENCE_FIELDS);
            Map<String, Object> after = target.current();
            diff.add(diffItem("角色经历", action, experienceName(after, state),
                    changedFields(before, after, EXPERIENCE_FIELDS, item.keySet())));
        }
    }

    private static void materializeOutlineStatuses(
            Map<String, Object> updates, State state, List<Map<String, Object>> diff) {
        List<Map<String, Object>> items = mutableItems(updates, "outline");
        if (items == null) return;
        for (Map<String, Object> item : items) {
            MutableResource target = state.resolveById(ResourceKind.OUTLINE_NODE, requiredText(item, "nodeId"));
            Map<String, Object> before = target.current();
            target.apply(item, OUTLINE_STATUS_FIELDS);
            Map<String, Object> after = target.current();
            diff.add(diffItem("大纲状态", "update", display(after, before, "title", target.id()),
                    changedFields(before, after, OUTLINE_STATUS_FIELDS, item.keySet())));
        }
    }

    private static void materializeOutlineAdjustments(
            String userId,
            String novelId,
            String artifactId,
            int revision,
            Map<String, Object> updates,
            State state,
            List<Map<String, Object>> diff) {
        String section = "outlineAdjustments";
        List<Map<String, Object>> items = mutableItems(updates, section);
        if (items == null) return;
        boolean replace = "replace".equals(updates.get("outlineTreeMode"));
        if (replace) {
            // replace 先把冻结旧树投影为删除，再按候选顺序建立全新树，不能混用当前数据库 Head。
            for (Map<String, Object> before : state.outlineReplacementBefore()) {
                diff.add(diffItem("大纲节点", "delete", display(null, before, "title", (String) before.get("id")),
                        deletedFields(before, OUTLINE_FIELDS)));
            }
            state.clear(ResourceKind.OUTLINE_NODE);
        }
        Map<String, String> clientIds = new LinkedHashMap<>();
        for (int index = 0; index < items.size(); index++) {
            Map<String, Object> item = items.get(index);
            String action = action(item, section);
            if ("create".equals(action)) {
                injectCreateIdentity(userId, novelId, artifactId, revision, section, index, item);
                String id = AgentUpdatesIdentity.resourceId(userId, novelId, artifactId, revision, section, index);
                Map<String, Object> current = outlineFields(item, state, clientIds);
                current.put("id", id);
                if (replace || !current.containsKey("order")) {
                    int order = replace ? index : state.count(ResourceKind.OUTLINE_NODE);
                    current.put("order", order);
                    item.put("order", order);
                }
                completeCreateFields(current, OUTLINE_FIELDS, Map.of("status", "planned"));
                state.addNew(ResourceKind.OUTLINE_NODE, id, current);
                rememberClientKey(item, id, clientIds);
                diff.add(diffItem("大纲节点", action, display(current, null, "title", id),
                        changedFields(null, current, OUTLINE_FIELDS, current.keySet())));
                continue;
            }

            String lookupField = item.containsKey("title") ? "title" : "nodeTitle";
            MutableResource target = state.resolve(
                    ResourceKind.OUTLINE_NODE,
                    text(item.get("nodeId")),
                    "title",
                    text(item.get(lookupField)));
            Map<String, Object> before = target.current();
            item.put("nodeId", target.id());
            if ("delete".equals(action)) {
                diff.add(diffItem("大纲节点", action, display(null, before, "title", target.id()),
                        deletedFields(before, OUTLINE_FIELDS)));
                state.remove(target);
                continue;
            }
            if (!"update".equals(action)) throw invalidCandidate(section + " action 无效");
            Map<String, Object> fields = outlineFields(item, state, clientIds);
            target.apply(fields, OUTLINE_FIELDS);
            Map<String, Object> after = target.current();
            diff.add(diffItem("大纲节点", action, display(after, before, "title", target.id()),
                    changedFields(before, after, OUTLINE_FIELDS, fields.keySet())));
        }
    }

    private static Map<String, Object> outlineFields(
            Map<String, Object> item, State state, Map<String, String> clientIds) {
        Map<String, Object> fields = new LinkedHashMap<>();
        copyPresent(item, fields, OUTLINE_FIELDS);
        if (!fields.containsKey("title") && item.get("nodeTitle") instanceof String title) {
            fields.put("title", title);
        }
        String parentKey = text(item.get("parentKey"));
        if (parentKey != null) {
            // parentKey 只允许引用同一候选中已经出现的 create，避免前向引用造成顺序不确定。
            String parentId = clientIds.get(parentKey);
            if (parentId == null) throw unresolved("大纲 parentKey 无法解析到前序 create");
            state.resolveById(ResourceKind.OUTLINE_NODE, parentId);
            fields.put("parentId", parentId);
        } else {
            state.requireReference(ResourceKind.OUTLINE_NODE, fields, "parentId");
        }
        state.requireReference(ResourceKind.CHAPTER_REFERENCE, fields, "linkedChapterId");
        return fields;
    }

    private static void rememberClientKey(
            Map<String, Object> item, String id, Map<String, String> clientIds) {
        String clientKey = text(item.get("clientKey"));
        if (clientKey != null) clientIds.put(clientKey, id);
    }

    private static void materializeForeshadowing(
            String userId,
            String novelId,
            String artifactId,
            int revision,
            Map<String, Object> updates,
            State state,
            List<Map<String, Object>> diff) {
        String section = "foreshadowing";
        List<Map<String, Object>> items = mutableItems(updates, section);
        if (items == null) return;
        for (int index = 0; index < items.size(); index++) {
            Map<String, Object> item = items.get(index);
            String action = action(item, section);
            if ("create".equals(action)) {
                injectCreateIdentity(userId, novelId, artifactId, revision, section, index, item);
                String id = AgentUpdatesIdentity.resourceId(userId, novelId, artifactId, revision, section, index);
                Map<String, Object> current = new LinkedHashMap<>();
                current.put("id", id);
                copyPresent(item, current, FORESHADOWING_FIELDS);
                completeCreateFields(current, FORESHADOWING_FIELDS, Map.of("status", "active"));
                state.addNew(ResourceKind.FORESHADOWING, id, current);
                diff.add(diffItem("伏笔", action, display(current, null, "name", id),
                        changedFields(null, current, FORESHADOWING_FIELDS,
                                new LinkedHashSet<>(FORESHADOWING_FIELDS))));
                continue;
            }

            MutableResource target = state.resolve(
                    ResourceKind.FORESHADOWING, text(item.get("id")), "name", text(item.get("name")));
            Map<String, Object> before = target.current();
            item.put("id", target.id());
            if (!Set.of("update", "payoff", "abandon").contains(action)) {
                throw invalidCandidate(section + " action 无效");
            }
            target.apply(item, FORESHADOWING_FIELDS);
            if ("payoff".equals(action)) target.put("status", "paid_off");
            if ("abandon".equals(action)) target.put("status", "abandoned");
            Map<String, Object> after = target.current();
            Set<String> present = new LinkedHashSet<>(item.keySet());
            if (!"update".equals(action)) present.add("status");
            diff.add(diffItem("伏笔", action, display(after, before, "name", target.id()),
                    changedFields(before, after, FORESHADOWING_FIELDS, present)));
        }
    }

    private static void materializeReferences(
            String userId,
            String novelId,
            String artifactId,
            int revision,
            Map<String, Object> updates,
            State state,
            List<Map<String, Object>> diff) {
        String section = "references";
        List<Map<String, Object>> items = mutableItems(updates, section);
        if (items == null) return;
        for (int index = 0; index < items.size(); index++) {
            Map<String, Object> item = items.get(index);
            String action = action(item, section);
            if ("create".equals(action)) {
                injectCreateIdentity(userId, novelId, artifactId, revision, section, index, item);
                String id = AgentUpdatesIdentity.resourceId(userId, novelId, artifactId, revision, section, index);
                Map<String, Object> current = new LinkedHashMap<>();
                current.put("id", id);
                copyPresent(item, current, REFERENCE_FIELDS);
                completeCreateFields(current, REFERENCE_FIELDS, Map.of());
                state.addNew(ResourceKind.REFERENCE, id, current);
                diff.add(diffItem("参考资料", action, display(current, null, "title", id),
                        changedFields(null, current, REFERENCE_FIELDS, new LinkedHashSet<>(REFERENCE_FIELDS))));
                continue;
            }

            MutableResource target = state.resolveById(
                    ResourceKind.REFERENCE, firstRequiredNonEmpty(item, "id", "referenceId"));
            Map<String, Object> before = target.current();
            item.put("id", target.id());
            if ("delete".equals(action)) {
                diff.add(diffItem("参考资料", action, display(null, before, "title", target.id()),
                        deletedFields(before, REFERENCE_FIELDS)));
                state.remove(target);
                continue;
            }
            if (!"update".equals(action)) throw invalidCandidate(section + " action 无效");
            target.apply(item, REFERENCE_FIELDS);
            Map<String, Object> after = target.current();
            diff.add(diffItem("参考资料", action, display(after, before, "title", target.id()),
                    changedFields(before, after, REFERENCE_FIELDS, item.keySet())));
        }
    }

    private static void materializeTexts(
            String novelId,
            Map<String, Object> updates,
            AgentUpdatesFrozenSources sources,
            Map<String, Object> payload,
            List<Map<String, Object>> diff) {
        if (updates.containsKey("outlineContent")) {
            AgentUpdatesFrozenSources.Snapshot source = sources.require(ResourceKind.OUTLINE_CONTENT, novelId);
            payload.put("baseOutlineUpdatedAt", timestamp(source.updatedAt()));
            diff.add(textDiff("outlineContent", "总纲", source, updates.get("outlineContent")));
        }
        Map<String, Object> loreBaseline = new LinkedHashMap<>();
        if (updates.containsKey("worldSetting")) {
            AgentUpdatesFrozenSources.Snapshot source = sources.require(ResourceKind.WORLD_SETTING, novelId);
            loreBaseline.put("worldSetting", timestamp(source.updatedAt()));
            diff.add(textDiff("worldSetting", "世界设定", source, updates.get("worldSetting")));
        }
        if (updates.containsKey("storyBackground")) {
            AgentUpdatesFrozenSources.Snapshot source = sources.require(ResourceKind.STORY_BACKGROUND, novelId);
            loreBaseline.put("storyBackground", timestamp(source.updatedAt()));
            diff.add(textDiff("storyBackground", "故事背景", source, updates.get("storyBackground")));
        }
        if (!loreBaseline.isEmpty()) payload.put("baseLoreUpdatedAt", loreBaseline);
    }

    private static Map<String, Object> textDiff(
            String field,
            String label,
            AgentUpdatesFrozenSources.Snapshot source,
            Object newValue) {
        Object oldValue = source.exists() && source.before() != null ? source.before().get("content") : null;
        return diffItem(label, "update", label, List.of(diffField(field, label, oldValue, newValue)));
    }

    private static void injectCreateIdentity(
            String userId,
            String novelId,
            String artifactId,
            int revision,
            String section,
            int index,
            Map<String, Object> item) {
        String requestKey = AgentUpdatesIdentity.requestKey(artifactId, revision, section, index);
        String resourceId = AgentUpdatesIdentity.resourceId(userId, novelId, section, requestKey);
        if (requestKey.isEmpty() || resourceId.isEmpty()) {
            throw new IllegalStateException("无法派生稳定创建身份");
        }
        item.put("clientRequestId", requestKey);
    }

    private static List<Map<String, Object>> changedFields(
            Map<String, Object> before,
            Map<String, Object> after,
            List<String> orderedFields,
            Set<String> present) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (String field : orderedFields) {
            if (!present.contains(field)) continue;
            Object oldValue = before == null ? null : before.get(field);
            Object newValue = after == null ? null : after.get(field);
            if (before != null && canonicalEquals(oldValue, newValue)) continue;
            result.add(diffField(field, FIELD_LABELS.getOrDefault(field, field), oldValue, newValue));
        }
        return result;
    }

    private static List<Map<String, Object>> deletedFields(
            Map<String, Object> before, List<String> orderedFields) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (String field : orderedFields) {
            if (before.containsKey(field)) {
                result.add(diffField(field, FIELD_LABELS.getOrDefault(field, field), before.get(field), null));
            }
        }
        return result;
    }

    private static void completeCreateFields(
            Map<String, Object> current,
            List<String> fields,
            Map<String, Object> defaults) {
        for (String field : fields) {
            if (!current.containsKey(field)) current.put(field, deepMutable(defaults.get(field)));
        }
    }

    private static Map<String, Object> diffField(
            String field, String label, Object oldValue, Object newValue) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("field", field);
        result.put("label", label);
        String oldText = stringify(oldValue);
        String newText = stringify(newValue);
        if (oldText != null) result.put("oldValue", oldText);
        if (newText != null) result.put("newValue", newText);
        return result;
    }

    private static Map<String, Object> diffItem(
            String section, String action, String name, List<Map<String, Object>> fields) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("section", section);
        result.put("action", action);
        result.put("name", name);
        result.put("fields", fields);
        return result;
    }

    private static String display(
            Map<String, Object> after,
            Map<String, Object> before,
            String field,
            String fallback) {
        String result = after == null ? null : text(after.get(field));
        if (result == null && before != null) result = text(before.get(field));
        return result == null ? fallback : result;
    }

    private static String experienceName(Map<String, Object> experience, State state) {
        Object characterId = experience.get("characterId");
        if (characterId instanceof String id && !id.isEmpty()) {
            MutableResource character = state.find(ResourceKind.CHARACTER, id);
            if (character != null) return display(character.peek(), null, "name", id);
            return id;
        }
        return "角色经历";
    }

    private static String experienceName(Map<String, Object> experience, MutableResource character) {
        return display(character.peek(), null, "name", String.valueOf(experience.get("characterId")));
    }

    private static void copyPresent(
            Map<String, Object> source, Map<String, Object> target, List<String> fields) {
        for (String field : fields) {
            if (source.containsKey(field)) target.put(field, deepMutable(source.get(field)));
        }
    }

    private static List<Map<String, Object>> mutableItems(Map<String, Object> updates, String section) {
        if (!updates.containsKey(section)) return null;
        Object value = updates.get(section);
        if (!(value instanceof List<?> list)) throw invalidCandidate(section + " 必须是数组");
        List<Map<String, Object>> result = new ArrayList<>(list.size());
        for (Object item : list) result.add(mutableObject(item, section + " 必须是对象数组"));
        updates.put(section, result);
        return result;
    }

    private static Map<String, Object> mutableObject(Object value, String message) {
        if (!(value instanceof Map<?, ?> map)) throw invalidCandidate(message);
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw invalidCandidate("JSON 对象 key 必须是字符串");
            result.put(key, deepMutable(entry.getValue()));
        }
        return result;
    }

    private static Object deepMutable(Object value) {
        if (value == null
                || value instanceof String
                || value instanceof Number
                || value instanceof Boolean) return value;
        if (value instanceof Map<?, ?> map) return mutableObject(map, "JSON 对象无效");
        if (value instanceof List<?> list) {
            List<Object> result = new ArrayList<>(list.size());
            for (Object item : list) result.add(deepMutable(item));
            return result;
        }
        throw invalidCandidate("候选包含不支持的 JSON 值");
    }

    private static Map<String, Object> freezeMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw invalidCandidate("JSON 对象 key 必须是字符串");
            result.put(key, freeze(entry.getValue()));
        }
        return Collections.unmodifiableMap(result);
    }

    private static Object freeze(Object value) {
        if (value == null
                || value instanceof String
                || value instanceof Number
                || value instanceof Boolean) return value;
        if (value instanceof Map<?, ?> map) return freezeMap(map);
        if (value instanceof List<?> list) {
            List<Object> result = new ArrayList<>(list.size());
            for (Object item : list) result.add(freeze(item));
            return Collections.unmodifiableList(result);
        }
        throw invalidCandidate("候选包含不支持的 JSON 值");
    }

    private static String action(Map<String, Object> item, String section) {
        String action = text(item.get("action"));
        if (action == null) throw invalidCandidate(section + " action 无效");
        return action;
    }

    private static String firstNonEmpty(Map<String, Object> item, List<String> fields) {
        for (String field : fields) {
            String result = text(item.get(field));
            if (result != null) return result;
        }
        return null;
    }

    private static String firstRequiredNonEmpty(Map<String, Object> item, String... fields) {
        for (String field : fields) {
            String result = text(item.get(field));
            if (result != null) return result;
        }
        throw unresolved("更新项缺少冻结目标 ID");
    }

    private static String requiredText(Map<String, Object> item, String field) {
        String value = text(item.get(field));
        if (value == null) throw unresolved("更新项缺少冻结目标 ID");
        return value;
    }

    private static String text(Object value) {
        return value instanceof String text && !text.isEmpty() ? text : null;
    }

    private static void requireIdentity(String value, String label) {
        if (value == null || value.isEmpty()) throw new IllegalArgumentException(label + " 不能为空");
    }

    private static String timestamp(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }

    private static boolean canonicalEquals(Object left, Object right) {
        return Arrays.equals(ExecutionCanonicalJson.bytes(left), ExecutionCanonicalJson.bytes(right));
    }

    private static String stringify(Object value) {
        if (value == null) return null;
        if (value instanceof String text) return text;
        if (value instanceof Number || value instanceof Boolean) return String.valueOf(value);
        return new String(ExecutionCanonicalJson.bytes(value), StandardCharsets.UTF_8);
    }

    private static EntitySection entity(
            String name,
            String label,
            ResourceKind kind,
            String lookupField,
            List<String> idFields,
            String... fields) {
        return new EntitySection(name, label, kind, lookupField, idFields, List.of(fields));
    }

    private static Map<String, String> fieldLabels() {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("name", "名称");
        result.put("title", "标题");
        result.put("term", "术语");
        result.put("aliases", "别名");
        result.put("gender", "性别");
        result.put("age", "年龄");
        result.put("identity", "身份");
        result.put("appearance", "外貌");
        result.put("personality", "性格");
        result.put("background", "背景");
        result.put("factionId", "阵营");
        result.put("combatAbility", "战斗能力");
        result.put("powerLevel", "实力层级");
        result.put("specialSkills", "特殊能力");
        result.put("currentStatus", "当前状态");
        result.put("coreDesire", "核心欲望");
        result.put("shortTermGoal", "短期目标");
        result.put("behaviorBoundaries", "行为边界");
        result.put("speechStyle", "说话习惯");
        result.put("relationshipPrinciples", "关系原则");
        result.put("statusNote", "状态说明");
        result.put("type", "类型");
        result.put("parentId", "父级");
        result.put("description", "描述");
        result.put("climate", "气候");
        result.put("culture", "文化");
        result.put("rarity", "稀有度");
        result.put("ownerId", "所属角色");
        result.put("effect", "效果");
        result.put("origin", "来源");
        result.put("baseId", "驻地");
        result.put("definition", "定义");
        result.put("category", "分类");
        result.put("characterId", "角色");
        result.put("chapterId", "章节");
        result.put("content", "内容");
        result.put("order", "顺序");
        result.put("status", "状态");
        result.put("kind", "节点类型");
        result.put("linkedChapterId", "关联章节");
        result.put("estimatedWordCount", "预计字数");
        result.put("actualWordCount", "实际字数");
        result.put("chapterStartOrder", "起始章节序号");
        result.put("chapterEndOrder", "结束章节序号");
        result.put("plantedAt", "埋设位置");
        result.put("plantedContent", "埋设内容");
        result.put("expectedPayoff", "预期回收");
        result.put("payoffAt", "回收位置");
        result.put("sourceUrl", "来源地址");
        result.put("outlineContent", "总纲");
        result.put("worldSetting", "世界设定");
        result.put("storyBackground", "故事背景");
        return Collections.unmodifiableMap(result);
    }

    private static Map<String, ResourceKind> indexKinds() {
        Map<String, ResourceKind> result = new LinkedHashMap<>();
        for (ResourceKind kind : List.of(
                ResourceKind.CHARACTER,
                ResourceKind.LOCATION,
                ResourceKind.ITEM,
                ResourceKind.FACTION,
                ResourceKind.GLOSSARY,
                ResourceKind.CHARACTER_EXPERIENCE,
                ResourceKind.OUTLINE_NODE,
                ResourceKind.FORESHADOWING,
                ResourceKind.REFERENCE,
                ResourceKind.CHAPTER_REFERENCE)) {
            result.put(kind.wireName(), kind);
        }
        return Collections.unmodifiableMap(result);
    }

    private static Set<String> expectedIndexKeys(ResourceKind kind) {
        return switch (kind) {
            case CHARACTER, LOCATION, ITEM, FACTION, FORESHADOWING -> Set.of("resourceType", "id", "name");
            case GLOSSARY -> Set.of("resourceType", "id", "term");
            case REFERENCE -> Set.of("resourceType", "id", "title");
            case CHARACTER_EXPERIENCE -> Set.of("resourceType", "id", "characterId", "order");
            case OUTLINE_NODE -> Set.of("resourceType", "id", "title", "parentId", "kind", "order");
            case CHAPTER_REFERENCE -> Set.of("resourceType", "id", "title", "order");
            default -> throw invalidSource("名录包含不支持的资料类型");
        };
    }

    private static void validateIndexRow(ResourceKind kind, Map<String, Object> row) {
        if (!row.keySet().equals(expectedIndexKeys(kind))) throw invalidSource("资料名录成员字段无效");
        requireIndexText(row, "id", false);
        switch (kind) {
            case CHARACTER, LOCATION, ITEM, FACTION, FORESHADOWING -> requireIndexText(row, "name", true);
            case GLOSSARY -> requireIndexText(row, "term", true);
            case REFERENCE -> requireIndexText(row, "title", true);
            case CHARACTER_EXPERIENCE -> {
                requireIndexText(row, "characterId", false);
                requireIndexInteger(row.get("order"));
            }
            case OUTLINE_NODE -> {
                requireIndexText(row, "title", true);
                if (row.get("parentId") != null) requireIndexText(row, "parentId", false);
                String kindValue = requireIndexText(row, "kind", false);
                if (!Set.of("stage", "plot_unit", "chapter_group").contains(kindValue)) {
                    throw invalidSource("大纲名录节点类型无效");
                }
                requireIndexInteger(row.get("order"));
            }
            case CHAPTER_REFERENCE -> {
                requireIndexText(row, "title", true);
                requireIndexInteger(row.get("order"));
            }
            default -> throw invalidSource("名录包含不支持的资料类型");
        }
    }

    private static String requireIndexText(Map<String, Object> row, String field, boolean emptyAllowed) {
        Object value = row.get(field);
        if (!(value instanceof String text) || !emptyAllowed && text.isEmpty()) {
            throw invalidSource("资料名录字符串字段无效：" + field);
        }
        return text;
    }

    private static int requireIndexInteger(Object value) {
        if (!(value instanceof Byte
                || value instanceof Short
                || value instanceof Integer
                || value instanceof Long
                || value instanceof BigInteger)) {
            throw invalidSource("资料名录顺序字段无效");
        }
        BigInteger number = new BigInteger(value.toString());
        if (number.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) < 0
                || number.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) > 0) {
            throw invalidSource("资料名录顺序越界");
        }
        return number.intValueExact();
    }

    private static ApiException invalidSource(String message) {
        return new ApiException(409, "AGENT_UPDATES_SOURCE_INVALID", message);
    }

    private static ApiException unresolved(String message) {
        return new ApiException(409, "AGENT_UPDATES_TARGET_UNRESOLVED", message);
    }

    private static IllegalArgumentException invalidCandidate(String message) {
        return new IllegalArgumentException(message);
    }

    public record Materialized(Map<String, Object> payload, List<Map<String, Object>> diff) {
        public Materialized {
            payload = freezeMap(payload);
            List<Map<String, Object>> frozenDiff = new ArrayList<>(diff.size());
            for (Map<String, Object> item : diff) frozenDiff.add(freezeMap(item));
            diff = Collections.unmodifiableList(frozenDiff);
        }
    }

    private record EntitySection(
            String name,
            String label,
            ResourceKind kind,
            String lookupField,
            List<String> idFields,
            List<String> fields) {}

    private static final class State {
        private final String novelId;
        private final AgentUpdatesFrozenSources sources;
        private final EnumMap<ResourceKind, LinkedHashMap<String, MutableResource>> resources =
                new EnumMap<>(ResourceKind.class);

        private State(String novelId, AgentUpdatesFrozenSources sources) {
            this.novelId = novelId;
            this.sources = sources;
            for (ResourceKind kind : ResourceKind.values()) resources.put(kind, new LinkedHashMap<>());
            List<Map<String, Object>> index = sources.requireCollection("agent_updates_index", novelId);
            for (Map<String, Object> raw : index) {
                Map<String, Object> row = mutableObject(raw, "资料名录成员必须是对象");
                ResourceKind kind = INDEX_KINDS.get(row.get("resourceType"));
                if (kind == null) throw invalidSource("资料名录包含不支持的资料类型");
                validateIndexRow(kind, row);
                String id = (String) row.get("id");
                MutableResource value = new MutableResource(kind, id, row, true, sources);
                if (resources.get(kind).putIfAbsent(id, value) != null) {
                    throw invalidSource("资料名录同类型 ID 重复");
                }
            }
        }

        private MutableResource resolve(
                ResourceKind kind, String id, String lookupField, String lookupValue) {
            if (id != null) return resolveById(kind, id);
            if (lookupValue == null) throw unresolved(kind.wireName() + " 缺少可解析目标");
            List<MutableResource> found = resources.get(kind).values().stream()
                    .filter(value -> Objects.equals(value.peek().get(lookupField), lookupValue))
                    .toList();
            if (found.size() != 1) throw unresolved(kind.wireName() + " 名称无法唯一解析");
            return found.getFirst();
        }

        private MutableResource resolveById(ResourceKind kind, String id) {
            MutableResource found = resources.get(kind).get(id);
            if (found == null) throw unresolved(kind.wireName() + " ID 无法从冻结名录解析");
            return found;
        }

        private MutableResource find(ResourceKind kind, String id) {
            return resources.get(kind).get(id);
        }

        private void requireReference(ResourceKind kind, Map<String, Object> item, String field) {
            if (!item.containsKey(field) || item.get(field) == null) return;
            String id = text(item.get(field));
            if (id == null) throw invalidCandidate(field + " 必须为 null 或非空字符串");
            resolveById(kind, id).current();
        }

        private int nextExperienceOrder(String characterId) {
            Integer maximum = null;
            for (MutableResource resource : resources.get(ResourceKind.CHARACTER_EXPERIENCE).values()) {
                if (!Objects.equals(resource.peek().get("characterId"), characterId)) continue;
                int order = requireIndexInteger(resource.peek().get("order"));
                maximum = maximum == null ? order : Math.max(maximum, order);
            }
            if (maximum == null) return 0;
            if (maximum == Integer.MAX_VALUE) {
                throw invalidSource("角色经历默认顺序超出数据库整数范围");
            }
            return maximum + 1;
        }

        private void addNew(ResourceKind kind, String id, Map<String, Object> current) {
            MutableResource value = new MutableResource(kind, id, current, false, sources);
            if (resources.get(kind).putIfAbsent(id, value) != null) {
                throw invalidSource("稳定创建身份与冻结资料冲突");
            }
        }

        private void remove(MutableResource target) {
            resources.get(target.kind()).remove(target.id());
        }

        private void clear(ResourceKind kind) {
            resources.get(kind).clear();
        }

        private List<Map<String, Object>> outlineReplacementBefore() {
            List<Map<String, Object>> membership = sources.requireCollection("outline_tree_membership", novelId);
            Set<String> memberIds = new LinkedHashSet<>();
            for (Map<String, Object> member : membership) {
                if (!member.keySet().equals(Set.of("id"))) {
                    throw invalidSource("大纲树成员名录字段无效");
                }
                String id = requireIndexText(member, "id", false);
                if (!memberIds.add(id)) throw invalidSource("大纲树成员 ID 重复");
            }
            if (!memberIds.equals(resources.get(ResourceKind.OUTLINE_NODE).keySet())) {
                throw invalidSource("大纲树成员与冻结名录不一致");
            }
            List<MutableResource> existing = new ArrayList<>(resources.get(ResourceKind.OUTLINE_NODE).values());
            for (MutableResource resource : existing) resource.current();
            Map<String, MutableResource> byId = resources.get(ResourceKind.OUTLINE_NODE);
            existing.sort(Comparator.comparingInt((MutableResource value) -> -outlineDepth(value, byId))
                    .thenComparingInt(value -> requireIndexInteger(value.peek().get("order")))
                    .thenComparing(MutableResource::id));
            return existing.stream().map(MutableResource::current).toList();
        }

        private static int outlineDepth(
                MutableResource resource, Map<String, MutableResource> byId) {
            int depth = 0;
            String parent = text(resource.peek().get("parentId"));
            Set<String> seen = new LinkedHashSet<>();
            while (parent != null) {
                if (!seen.add(parent)) throw invalidSource("冻结大纲树存在父级环");
                MutableResource value = byId.get(parent);
                if (value == null) throw invalidSource("冻结大纲树父级不存在");
                depth++;
                parent = text(value.peek().get("parentId"));
            }
            return depth;
        }

        private int count(ResourceKind kind) {
            return resources.get(kind).size();
        }
    }

    private static final class MutableResource {
        private final ResourceKind kind;
        private final String id;
        private final Map<String, Object> indexIdentity;
        private final boolean historical;
        private final AgentUpdatesFrozenSources sources;
        private Map<String, Object> current;
        private boolean loaded;

        private MutableResource(
                ResourceKind kind,
                String id,
                Map<String, Object> initial,
                boolean historical,
                AgentUpdatesFrozenSources sources) {
            this.kind = kind;
            this.id = id;
            this.historical = historical;
            this.sources = sources;
            this.current = mutableObject(initial, "资料状态无效");
            this.indexIdentity = historical ? mutableObject(initial, "资料名录无效") : Map.of();
            this.loaded = !historical;
        }

        private ResourceKind kind() {
            return kind;
        }

        private String id() {
            return id;
        }

        private Map<String, Object> peek() {
            return current;
        }

        private Map<String, Object> current() {
            if (!loaded) load();
            return mutableObject(current, "资料状态无效");
        }

        private void load() {
            AgentUpdatesFrozenSources.Snapshot snapshot = sources.require(kind, id);
            if (!snapshot.exists() || snapshot.before() == null) {
                throw invalidSource("冻结名录目标缺少完整 before");
            }
            Map<String, Object> before = mutableObject(snapshot.before(), "冻结资料 before 无效");
            for (Map.Entry<String, Object> entry : indexIdentity.entrySet()) {
                if ("resourceType".equals(entry.getKey())) continue;
                if (!before.containsKey(entry.getKey())
                        || !canonicalEquals(before.get(entry.getKey()), entry.getValue())) {
                    throw invalidSource("冻结名录与完整 before 身份不一致");
                }
            }
            current = before;
            loaded = true;
        }

        private void apply(Map<String, Object> values, List<String> fields) {
            if (!loaded) load();
            copyPresent(values, current, fields);
        }

        private void put(String field, Object value) {
            if (!loaded) load();
            current.put(field, deepMutable(value));
        }
    }
}
