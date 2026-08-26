package cn.inkforge.core.reviews.application;

import cn.inkforge.contracts.api.ArtifactSelectionRef;
import cn.inkforge.contracts.api.ForeshadowingResponse;
import cn.inkforge.contracts.api.OutlineNodeResponse;
import cn.inkforge.core.lore.application.LoreRepository;
import cn.inkforge.core.lore.domain.ContentKind;
import cn.inkforge.core.lore.domain.EntityMutation;
import cn.inkforge.core.lore.domain.ExperienceMutation;
import cn.inkforge.core.lore.domain.LoreEntityKind;
import cn.inkforge.core.lore.domain.MutationAction;
import cn.inkforge.core.outlines.application.OutlineRepository;
import cn.inkforge.core.outlines.domain.ForeshadowingData;
import cn.inkforge.core.outlines.domain.ForeshadowingPatch;
import cn.inkforge.core.outlines.domain.OutlineNodeData;
import cn.inkforge.core.outlines.domain.OutlineNodePatch;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.patch.PatchField;
import cn.inkforge.core.references.application.ReferenceRepository;
import cn.inkforge.core.references.domain.ReferenceData;
import cn.inkforge.core.references.domain.ReferencePatch;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 把 agent_updates 的分区命令严格转换为各正式领域的有类型写入。
 *
 * <p>调用方已经建立审核决定外层事务，各领域仓储通过 {@code CoreDatabase} 加入该事务；因此任一分区失败会
 * 回滚全部更新。选择引用按原草案 section/index 过滤，不能重排后再解释 index，也不能把未选择项当作默认全选。
 */
public final class AgentUpdatesExecutor {

    private static final List<String> ARRAY_SECTIONS = List.of(
            "characters",
            "locations",
            "items",
            "factions",
            "glossaries",
            "characterExperiences",
            "outline",
            "outlineAdjustments",
            "foreshadowing",
            "references");
    private static final List<String> TEXT_SECTIONS =
            List.of("outlineContent", "worldSetting", "storyBackground");
    private static final Map<String, EntityConfig> ENTITY_CONFIGS = entityConfigs();

    private final LoreRepository lore;
    private final OutlineRepository outlines;
    private final ReferenceRepository references;
    private final CuidV1Generator ids;
    private final boolean referenceIndexEnabled;

    public AgentUpdatesExecutor(
            LoreRepository lore,
            OutlineRepository outlines,
            ReferenceRepository references,
            CuidV1Generator ids,
            boolean referenceIndexEnabled) {
        this.lore = Objects.requireNonNull(lore);
        this.outlines = Objects.requireNonNull(outlines);
        this.references = Objects.requireNonNull(references);
        this.ids = Objects.requireNonNull(ids);
        this.referenceIndexEnabled = referenceIndexEnabled;
    }

    public int apply(
            String novelId,
            String userId,
            Map<String, Object> rawUpdates,
            List<ArtifactSelectionRef> selectedRefs,
            OffsetDateTime expectedOutlineUpdatedAt,
            Map<String, OffsetDateTime> expectedLoreUpdatedAt) {
        Map<String, Object> updates = filter(rawUpdates, selectedRefs);
        if (updates.isEmpty()) throw new IllegalArgumentException("没有选择任何可应用更新");
        // 以下调用都加入审核决定已经开启的 CoreDatabase 事务，不能改成异步或逐分区提交。
        int count = 0;
        List<EntityMutation> entities = entityMutations(updates);
        if (!entities.isEmpty()) {
            lore.applyEntityMutations(novelId, userId, entities);
            count += entities.size();
        }
        List<ExperienceMutation> experiences = experienceMutations(updates);
        if (!experiences.isEmpty()) {
            lore.applyExperienceMutations(novelId, userId, experiences);
            count += experiences.size();
        }
        count += applyOutlineUpdates(novelId, userId, updates);
        count += applyForeshadowings(novelId, userId, updates);
        count += applyReferences(novelId, userId, updates);
        if (updates.containsKey("outlineContent")) {
            String content = requireString(updates.get("outlineContent"), "outlineContent 必须是完整文本");
            outlines.saveOutline(novelId, userId, content, expectedOutlineUpdatedAt);
            count++;
        }
        for (Map.Entry<String, ContentKind> entry : Map.of(
                        "worldSetting", ContentKind.WORLD_SETTING,
                        "storyBackground", ContentKind.STORY_BACKGROUND)
                .entrySet()) {
            if (!updates.containsKey(entry.getKey())) continue;
            if (expectedLoreUpdatedAt == null || !expectedLoreUpdatedAt.containsKey(entry.getKey())) {
                throw new IllegalArgumentException(entry.getKey() + " 缺少审核草案版本基线");
            }
            String content = requireString(updates.get(entry.getKey()), entry.getKey() + " 必须是完整文本");
            lore.saveContent(
                    novelId,
                    userId,
                    entry.getValue(),
                    content,
                    expectedLoreUpdatedAt.get(entry.getKey()));
            count++;
        }
        if (count == 0) throw new IllegalArgumentException("agent_updates 不包含可应用更新");
        return count;
    }

    public static Map<String, Object> filter(
            Map<String, Object> updates, List<ArtifactSelectionRef> selectedRefs) {
        if (selectedRefs == null) return deepCopyMap(updates);
        // index 指向原始 Artifact 数组；先筛选再解析，避免删除前项后让后续 index 漂移。
        Map<String, Selection> selected = new LinkedHashMap<>();
        for (ArtifactSelectionRef ref : selectedRefs) {
            if (ref == null || ref.getSection() == null) continue;
            Selection choice = selected.computeIfAbsent(ref.getSection(), ignored -> new Selection());
            Integer index = ref.getIndex() == null || ref.getIndex().isUndefined()
                    ? null
                    : ref.getIndex().orElse(null);
            if (index == null) choice.full = true;
            else if (index >= 0) choice.indices.add(index);
        }
        Map<String, Object> output = new LinkedHashMap<>();
        for (String section : ARRAY_SECTIONS) {
            Object raw = updates.get(section);
            Selection choice = selected.get(section);
            if (!(raw instanceof List<?> values) || choice == null) continue;
            List<Object> picked = new ArrayList<>();
            for (int index = 0; index < values.size(); index++) {
                if (choice.full || choice.indices.contains(index)) {
                    picked.add(deepCopy(values.get(index)));
                }
            }
            if (!picked.isEmpty()) output.put(section, picked);
        }
        for (String section : TEXT_SECTIONS) {
            if (selected.containsKey(section) && truthy(updates.get(section))) {
                output.put(section, deepCopy(updates.get(section)));
            }
        }
        if (output.containsKey("outlineAdjustments")
                && updates.get("outlineTreeMode") != null) {
            output.put("outlineTreeMode", updates.get("outlineTreeMode"));
        }
        return output;
    }

    private List<EntityMutation> entityMutations(Map<String, Object> updates) {
        List<EntityMutation> result = new ArrayList<>();
        for (Map.Entry<String, EntityConfig> entry : ENTITY_CONFIGS.entrySet()) {
            String section = entry.getKey();
            if (!updates.containsKey(section)) continue;
            List<Map<String, Object>> values = objectList(updates.get(section), section + " 必须是数组");
            for (Map<String, Object> item : values) {
                result.add(entityMutation(section, entry.getValue(), item));
            }
        }
        return result;
    }

    private static EntityMutation entityMutation(
            String section, EntityConfig config, Map<String, Object> item) {
        MutationAction action = action(item, section);
        Set<String> business = action == MutationAction.CREATE
                ? config.createFields()
                : config.updateFields();
        Set<String> allowed = new LinkedHashSet<>(business);
        allowed.addAll(config.idFields());
        allowed.add(config.lookupField());
        allowed.addAll(Set.of("action", "fieldChanges", "clientRequestId", "expectedUpdatedAt"));
        rejectUnknown(item, allowed, section);
        Map<String, Object> fields = fields(item, business);
        if (action == MutationAction.CREATE) {
            String clientRequestId = clientRequestId(item, section);
            return new EntityMutation(
                    action, config.kind(), fields, null, clientRequestId, null, null, null, section);
        }
        String entityId = firstString(item, config.idFields());
        String lookup = entityId == null ? optionalNonEmptyString(item.get(config.lookupField())) : null;
        if (entityId == null && lookup == null) {
            throw new IllegalArgumentException(section + " " + action.name().toLowerCase() + " 缺少可解析目标");
        }
        return new EntityMutation(
                action,
                config.kind(),
                action == MutationAction.DELETE ? Map.of() : fields,
                entityId,
                null,
                expectedTime(item, section),
                entityId == null ? config.lookupField() : null,
                lookup,
                section);
    }

    private static List<ExperienceMutation> experienceMutations(Map<String, Object> updates) {
        if (!updates.containsKey("characterExperiences")) return List.of();
        List<Map<String, Object>> values = objectList(
                updates.get("characterExperiences"), "characterExperiences 必须是数组");
        List<ExperienceMutation> result = new ArrayList<>();
        for (Map<String, Object> item : values) {
            MutationAction action = action(item, "characterExperiences");
            Set<String> business = action == MutationAction.CREATE
                    ? Set.of("chapterId", "content", "order")
                    : action == MutationAction.UPDATE
                            ? Set.of("chapterId", "content", "order")
                            : Set.of();
            Set<String> allowed = new LinkedHashSet<>(business);
            allowed.addAll(Set.of(
                    "action",
                    "fieldChanges",
                    "clientRequestId",
                    "expectedUpdatedAt",
                    "id",
                    "characterId",
                    "characterName"));
            rejectUnknown(item, allowed, "characterExperiences");
            Map<String, Object> fields = fields(item, business);
            if (action == MutationAction.CREATE) {
                String characterId = optionalNonEmptyString(item.get("characterId"));
                String characterName = optionalNonEmptyString(item.get("characterName"));
                if (characterId == null && characterName == null) {
                    throw new IllegalArgumentException("角色经历无法唯一解析角色");
                }
                requireString(fields.get("content"), "characterExperiences create 业务字段无效");
                result.add(new ExperienceMutation(
                        action,
                        fields,
                        null,
                        characterId,
                        characterName,
                        clientRequestId(item, "characterExperiences"),
                        null));
            } else {
                String id = requireNonEmptyString(item.get("id"), "角色经历更新缺少有效标识");
                if (action == MutationAction.UPDATE && fields.isEmpty()) {
                    throw new IllegalArgumentException("characterExperiences update 业务字段无效");
                }
                result.add(new ExperienceMutation(
                        action,
                        action == MutationAction.DELETE ? Map.of() : fields,
                        id,
                        null,
                        null,
                        null,
                        expectedTime(item, "characterExperiences")));
            }
        }
        return result;
    }

    private int applyOutlineUpdates(
            String novelId, String userId, Map<String, Object> updates) {
        int count = 0;
        if (updates.get("outline") instanceof List<?> rawStatuses) {
            for (Map<String, Object> item : objectList(rawStatuses, "outline 必须是数组")) {
                String nodeId = requireNonEmptyString(item.get("nodeId"), "outline 更新缺少 nodeId");
                rejectUnknown(item, Set.of("nodeId", "status", "actualWordCount"), "outline");
                OutlineNodeResponse current = node(outlines.listNodes(novelId, userId), nodeId);
                outlines.updateNode(
                        novelId,
                        userId,
                        nodeId,
                        new OutlineNodePatch(
                                absent(),
                                absent(),
                                absent(),
                                patch(item, "status", String.class),
                                absent(),
                                absent(),
                                absent(),
                                absent(),
                                patch(item, "actualWordCount", Integer.class),
                                absent(),
                                absent()),
                        current.getUpdatedAt());
                count++;
            }
        }
        if (!updates.containsKey("outlineAdjustments")) return count;
        List<Map<String, Object>> adjustments = objectList(
                updates.get("outlineAdjustments"), "outlineAdjustments 更新项结构无效");
        if ("replace".equals(updates.get("outlineTreeMode"))) {
            replaceOutlineTree(novelId, userId, adjustments);
            return count + adjustments.size();
        }
        List<OutlineNodeResponse> existing = new ArrayList<>(outlines.listNodes(novelId, userId));
        Map<String, String> clientIds = new HashMap<>();
        for (Map<String, Object> item : adjustments) {
            MutationAction action = action(item, "outlineAdjustments");
            String nodeId = resolveNodeId(item, existing);
            Map<String, Object> fields = outlineFields(item, clientIds);
            if (action == MutationAction.CREATE) {
                var mutation = outlines.createNode(
                        novelId,
                        userId,
                        ids.next(),
                        outlineNodeData(fields, existing.size()));
                OutlineNodeResponse created =
                        node(outlines.listNodes(novelId, userId), mutation.getId());
                existing.add(created);
                String clientKey = optionalNonEmptyString(item.get("clientKey"));
                if (clientKey != null) clientIds.put(clientKey, created.getId());
            } else if (action == MutationAction.UPDATE && nodeId != null) {
                OutlineNodeResponse current = node(existing, nodeId);
                var mutation = outlines.updateNode(
                        novelId,
                        userId,
                        nodeId,
                        outlinePatch(fields),
                        current.getUpdatedAt());
                OutlineNodeResponse changed =
                        node(outlines.listNodes(novelId, userId), mutation.getId());
                existing.removeIf(value -> value.getId().equals(nodeId));
                existing.add(changed);
            } else if (action == MutationAction.DELETE && nodeId != null) {
                OutlineNodeResponse current = node(existing, nodeId);
                outlines.deleteNode(novelId, userId, nodeId, current.getUpdatedAt());
                existing.removeIf(value -> value.getId().equals(nodeId));
            } else {
                throw new IllegalArgumentException("outlineAdjustments 缺少有效标识");
            }
            count++;
        }
        return count;
    }

    private void replaceOutlineTree(
            String novelId, String userId, List<Map<String, Object>> adjustments) {
        if (adjustments.stream().anyMatch(value -> action(value, "outlineAdjustments") != MutationAction.CREATE)) {
            throw new IllegalArgumentException("整树替换只能包含新建节点");
        }
        List<OutlineNodeResponse> existing = new ArrayList<>(outlines.listNodes(novelId, userId));
        existing.sort(Comparator.comparingInt(value -> -depth(value, existing)));
        for (OutlineNodeResponse value : existing) {
            outlines.deleteNode(novelId, userId, value.getId(), value.getUpdatedAt());
        }
        Map<String, String> clientIds = new HashMap<>();
        for (int order = 0; order < adjustments.size(); order++) {
            Map<String, Object> item = adjustments.get(order);
            Map<String, Object> fields = outlineFields(item, clientIds);
            fields.put("order", order);
            var mutation = outlines.createNode(
                    novelId,
                    userId,
                    ids.next(),
                    outlineNodeData(fields, order));
            OutlineNodeResponse value =
                    node(outlines.listNodes(novelId, userId), mutation.getId());
            String clientKey = optionalNonEmptyString(item.get("clientKey"));
            if (clientKey != null) {
                if (clientIds.putIfAbsent(clientKey, value.getId()) != null) {
                    throw new IllegalArgumentException("大纲节点临时标识重复");
                }
            }
        }
    }

    private int applyForeshadowings(
            String novelId, String userId, Map<String, Object> updates) {
        if (!updates.containsKey("foreshadowing")) return 0;
        List<Map<String, Object>> values = objectList(
                updates.get("foreshadowing"), "foreshadowing 必须是数组");
        List<ForeshadowingResponse> existing = null;
        for (Map<String, Object> item : values) {
            if (item.get("payoffNote") != null) {
                throw new IllegalArgumentException("payoffNote 无法写入现有数据库结构");
            }
            String action = requireNonEmptyString(item.get("action"), "foreshadowing action 无效");
            Set<String> allowed = Set.of(
                    "action", "id", "name", "plantedAt", "plantedContent",
                    "expectedPayoff", "payoffAt", "payoffNote");
            rejectUnknown(item, allowed, "foreshadowing");
            if ("create".equals(action)) {
                outlines.createForeshadowing(
                        novelId,
                        userId,
                        new ForeshadowingData(
                                requireNonEmptyString(item.get("name"), "伏笔名称不能为空"),
                                optionalString(item.get("plantedAt")),
                                optionalString(item.get("plantedContent")),
                                optionalString(item.get("expectedPayoff")),
                                optionalString(item.get("payoffAt")),
                                "active"));
                continue;
            }
            if (existing == null) existing = outlines.listForeshadowings(novelId, userId);
            String id = resolveForeshadowingId(item, existing);
            String status = switch (action) {
                case "payoff" -> "paid_off";
                case "abandon" -> "abandoned";
                case "update" -> null;
                default -> throw new IllegalArgumentException("foreshadowing action 无效");
            };
            outlines.updateForeshadowing(
                    novelId,
                    userId,
                    id,
                    new ForeshadowingPatch(
                            patch(item, "name", String.class),
                            patch(item, "plantedAt", String.class),
                            patch(item, "plantedContent", String.class),
                            patch(item, "expectedPayoff", String.class),
                            patch(item, "payoffAt", String.class),
                            status == null ? absent() : new PatchField<>(true, status)));
        }
        return values.size();
    }

    private int applyReferences(
            String novelId, String userId, Map<String, Object> updates) {
        if (!updates.containsKey("references")) return 0;
        List<Map<String, Object>> values = objectList(updates.get("references"), "references 必须是数组");
        for (Map<String, Object> item : values) {
            MutationAction action = action(item, "references");
            if (action == MutationAction.CREATE) {
                rejectUnknown(
                        item,
                        Set.of("action", "fieldChanges", "clientRequestId", "title", "type", "content", "sourceUrl"),
                        "references");
                references.create(
                        novelId,
                        userId,
                        clientRequestId(item, "references"),
                        new ReferenceData(
                                requireNonBlankString(item.get("title"), "references title 不能为空"),
                                requireNonEmptyString(item.get("type"), "references create 业务字段无效"),
                                requireString(item.get("content"), "references create 业务字段无效"),
                                optionalString(item.get("sourceUrl"))),
                        referenceIndexEnabled);
                continue;
            }
            rejectUnknown(
                    item,
                    Set.of(
                            "action", "fieldChanges", "id", "referenceId", "expectedUpdatedAt",
                            "title", "type", "content", "sourceUrl"),
                    "references");
            String id = pairedId(item, "id", "referenceId", "references");
            OffsetDateTime expected = expectedTime(item, "references");
            if (action == MutationAction.DELETE) {
                references.delete(novelId, userId, id, expected);
            } else {
                references.update(
                        novelId,
                        userId,
                        id,
                        new ReferencePatch(
                                patch(item, "title", String.class),
                                patch(item, "type", String.class),
                                patch(item, "content", String.class),
                                patch(item, "sourceUrl", String.class)),
                        expected,
                        referenceIndexEnabled);
            }
        }
        return values.size();
    }

    private static Map<String, Object> outlineFields(
            Map<String, Object> item, Map<String, String> clientIds) {
        Set<String> business = Set.of(
                "title", "content", "kind", "parentId", "status", "order",
                "linkedChapterId", "estimatedWordCount", "actualWordCount",
                "chapterStartOrder", "chapterEndOrder");
        Set<String> allowed = new LinkedHashSet<>(business);
        allowed.addAll(Set.of(
                "action", "nodeId", "nodeTitle", "clientKey", "parentKey", "fieldChanges"));
        rejectUnknown(item, allowed, "outlineAdjustments");
        Map<String, Object> fields = fields(item, business);
        if (!fields.containsKey("title") && item.get("nodeTitle") instanceof String title) {
            fields.put("title", title);
        }
        String parentKey = optionalNonEmptyString(item.get("parentKey"));
        if (parentKey != null) {
            String parentId = clientIds.get(parentKey);
            if (parentId == null) {
                throw new IllegalArgumentException("outlineAdjustments parentKey 无法解析");
            }
            fields.put("parentId", parentId);
        }
        return fields;
    }

    private static OutlineNodeData outlineNodeData(Map<String, Object> fields, int fallbackOrder) {
        return new OutlineNodeData(
                requireNonEmptyString(fields.get("title"), "整树替换节点缺少标题或类型"),
                optionalString(fields.get("content")),
                requireNonEmptyString(fields.get("kind"), "整树替换节点缺少标题或类型"),
                optionalString(fields.get("status")) == null ? "planned" : (String) fields.get("status"),
                fields.get("order") instanceof Integer value ? value : fallbackOrder,
                optionalString(fields.get("parentId")),
                optionalString(fields.get("linkedChapterId")),
                optionalInteger(fields.get("estimatedWordCount")),
                optionalInteger(fields.get("actualWordCount")),
                optionalInteger(fields.get("chapterStartOrder")),
                optionalInteger(fields.get("chapterEndOrder")));
    }

    private static OutlineNodePatch outlinePatch(Map<String, Object> fields) {
        return new OutlineNodePatch(
                patch(fields, "title", String.class),
                patch(fields, "content", String.class),
                patch(fields, "kind", String.class),
                patch(fields, "status", String.class),
                patch(fields, "order", Integer.class),
                patch(fields, "parentId", String.class),
                patch(fields, "linkedChapterId", String.class),
                patch(fields, "estimatedWordCount", Integer.class),
                patch(fields, "actualWordCount", Integer.class),
                patch(fields, "chapterStartOrder", Integer.class),
                patch(fields, "chapterEndOrder", Integer.class));
    }

    private static int depth(OutlineNodeResponse node, List<OutlineNodeResponse> nodes) {
        Map<String, OutlineNodeResponse> byId = new HashMap<>();
        nodes.forEach(value -> byId.put(value.getId(), value));
        int depth = 0;
        String parent = node.getParentId();
        Set<String> seen = new LinkedHashSet<>();
        while (parent != null && seen.add(parent)) {
            depth++;
            OutlineNodeResponse value = byId.get(parent);
            parent = value == null ? null : value.getParentId();
        }
        return depth;
    }

    private static String resolveNodeId(
            Map<String, Object> item, List<OutlineNodeResponse> existing) {
        String id = optionalNonEmptyString(item.get("nodeId"));
        if (id != null) return id;
        String title = optionalNonEmptyString(
                item.get("title") == null ? item.get("nodeTitle") : item.get("title"));
        List<OutlineNodeResponse> matches = existing.stream()
                .filter(value -> Objects.equals(value.getTitle(), title))
                .toList();
        return matches.size() == 1 ? matches.getFirst().getId() : null;
    }

    private static String resolveForeshadowingId(
            Map<String, Object> item, List<ForeshadowingResponse> existing) {
        String id = optionalNonEmptyString(item.get("id"));
        if (id != null) return id;
        String name = optionalNonEmptyString(item.get("name"));
        List<ForeshadowingResponse> matches = existing.stream()
                .filter(value -> Objects.equals(value.getName(), name))
                .toList();
        if (matches.size() != 1) {
            throw new IllegalArgumentException("foreshadowing 无法唯一解析已有伏笔");
        }
        return matches.getFirst().getId();
    }

    private static OutlineNodeResponse node(List<OutlineNodeResponse> nodes, String id) {
        return nodes.stream()
                .filter(value -> value.getId().equals(id))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("大纲节点不存在"));
    }

    private static MutationAction action(Map<String, Object> item, String section) {
        return switch (optionalString(item.get("action"))) {
            case "create" -> MutationAction.CREATE;
            case "update" -> MutationAction.UPDATE;
            case "delete" -> MutationAction.DELETE;
            default -> throw new IllegalArgumentException(section + " action 无效");
        };
    }

    private static OffsetDateTime expectedTime(Map<String, Object> item, String section) {
        Object value = item.get("expectedUpdatedAt");
        if (value instanceof OffsetDateTime time) return time;
        if (!(value instanceof String text) || text.isEmpty()) {
            throw new IllegalArgumentException(section + " update/delete 必须提供非空 expectedUpdatedAt");
        }
        try {
            return OffsetDateTime.parse(text);
        } catch (DateTimeParseException exception) {
            throw new IllegalArgumentException(section + " expectedUpdatedAt 格式无效");
        }
    }

    private static String clientRequestId(Map<String, Object> item, String section) {
        String value = optionalNonEmptyString(item.get("clientRequestId"));
        if (value == null || value.length() < 16 || value.length() > 256) {
            throw new IllegalArgumentException(section + " create 必须提供 16..256 字符的 clientRequestId");
        }
        return value;
    }

    private static String pairedId(
            Map<String, Object> item, String first, String second, String section) {
        String firstValue = optionalNonEmptyString(item.get(first));
        String secondValue = optionalNonEmptyString(item.get(second));
        if (firstValue != null && secondValue != null && !firstValue.equals(secondValue)) {
            throw new IllegalArgumentException(section + " " + first + " 与 " + second + " 不一致");
        }
        String result = firstValue == null ? secondValue : firstValue;
        if (result == null) throw new IllegalArgumentException(section + " 缺少有效 " + second);
        return result;
    }

    private static Map<String, Object> fields(Map<String, Object> item, Set<String> allowed) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (String field : allowed) {
            if (item.containsKey(field)) result.put(field, deepCopy(item.get(field)));
        }
        return result;
    }

    private static void rejectUnknown(
            Map<String, Object> item, Set<String> allowed, String section) {
        Set<String> unknown = new LinkedHashSet<>(item.keySet());
        unknown.removeAll(allowed);
        if (!unknown.isEmpty()) {
            throw new IllegalArgumentException(
                    section + " 包含无法持久化字段：" + String.join("、", unknown));
        }
    }

    private static List<Map<String, Object>> objectList(Object raw, String message) {
        if (!(raw instanceof List<?> values)) throw new IllegalArgumentException(message);
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object value : values) {
            if (!(value instanceof Map<?, ?> map)) throw new IllegalArgumentException(message);
            result.add(stringMap(map));
        }
        return result;
    }

    private static Map<String, Object> stringMap(Map<?, ?> map) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalArgumentException("JSON 对象键必须是字符串");
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private static Object deepCopy(Object value) {
        if (value instanceof Map<?, ?> map) return deepCopyMap(stringMap(map));
        if (value instanceof List<?> list) {
            List<Object> result = new ArrayList<>();
            list.forEach(item -> result.add(deepCopy(item)));
            return result;
        }
        return value;
    }

    private static Map<String, Object> deepCopyMap(Map<String, Object> map) {
        Map<String, Object> result = new LinkedHashMap<>();
        map.forEach((key, value) -> result.put(key, deepCopy(value)));
        return result;
    }

    private static boolean truthy(Object value) {
        return value != null && (!(value instanceof String text) || !text.isEmpty());
    }

    private static String firstString(Map<String, Object> item, List<String> fields) {
        for (String field : fields) {
            String value = optionalNonEmptyString(item.get(field));
            if (value != null) return value;
        }
        return null;
    }

    private static String requireString(Object value, String message) {
        if (value instanceof String text) return text;
        throw new IllegalArgumentException(message);
    }

    private static String requireNonEmptyString(Object value, String message) {
        String text = optionalNonEmptyString(value);
        if (text == null) throw new IllegalArgumentException(message);
        return text;
    }

    private static String requireNonBlankString(Object value, String message) {
        if (value instanceof String text && !text.strip().isEmpty()) return text;
        throw new IllegalArgumentException(message);
    }

    private static String optionalNonEmptyString(Object value) {
        return value instanceof String text && !text.isEmpty() ? text : null;
    }

    private static String optionalString(Object value) {
        return value instanceof String text ? text : null;
    }

    private static Integer optionalInteger(Object value) {
        return value instanceof Integer number ? number : null;
    }

    private static <T> PatchField<T> patch(
            Map<String, Object> fields, String name, Class<T> type) {
        if (!fields.containsKey(name)) return absent();
        Object value = fields.get(name);
        if (value != null && !type.isInstance(value)) {
            throw new IllegalArgumentException(name + " 字段类型无效");
        }
        return new PatchField<>(true, type.cast(value));
    }

    private static <T> PatchField<T> absent() {
        return new PatchField<>(false, null);
    }

    private static Map<String, EntityConfig> entityConfigs() {
        Map<String, EntityConfig> result = new LinkedHashMap<>();
        result.put("characters", new EntityConfig(
                LoreEntityKind.CHARACTERS,
                List.of("id", "characterId"),
                "name",
                Set.of(
                        "name", "aliases", "gender", "age", "identity", "appearance",
                        "personality", "background", "factionId", "combatAbility", "powerLevel",
                        "specialSkills", "currentStatus", "coreDesire", "shortTermGoal",
                        "behaviorBoundaries", "speechStyle", "relationshipPrinciples", "statusNote"),
                Set.of(
                        "name", "aliases", "gender", "age", "identity", "appearance",
                        "personality", "background", "factionId", "combatAbility", "powerLevel",
                        "specialSkills", "currentStatus", "coreDesire", "shortTermGoal",
                        "behaviorBoundaries", "speechStyle", "relationshipPrinciples", "statusNote")));
        result.put("locations", new EntityConfig(
                LoreEntityKind.LOCATIONS,
                List.of("id", "locationId"),
                "name",
                Set.of("name", "aliases", "type", "parentId", "description", "climate", "culture"),
                Set.of("name", "aliases", "type", "parentId", "description", "climate", "culture")));
        result.put("items", new EntityConfig(
                LoreEntityKind.ITEMS,
                List.of("id", "itemId"),
                "name",
                Set.of("name", "aliases", "type", "rarity", "ownerId", "description", "effect", "origin"),
                Set.of("name", "aliases", "type", "rarity", "ownerId", "description", "effect", "origin")));
        result.put("factions", new EntityConfig(
                LoreEntityKind.FACTIONS,
                List.of("id", "factionId"),
                "name",
                Set.of("name", "aliases", "type", "baseId", "description"),
                Set.of("name", "aliases", "type", "baseId", "description")));
        result.put("glossaries", new EntityConfig(
                LoreEntityKind.GLOSSARY,
                List.of("id", "glossaryId"),
                "term",
                Set.of("term", "category", "definition"),
                Set.of("term", "category", "definition")));
        return Collections.unmodifiableMap(result);
    }

    private record EntityConfig(
            LoreEntityKind kind,
            List<String> idFields,
            String lookupField,
            Set<String> createFields,
            Set<String> updateFields) {}

    private static final class Selection {
        private boolean full;
        private final Set<Integer> indices = new LinkedHashSet<>();
    }
}
