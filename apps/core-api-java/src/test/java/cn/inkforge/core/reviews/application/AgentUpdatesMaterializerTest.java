package cn.inkforge.core.reviews.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AgentUpdatesMaterializerTest {
    private static final String USER = "user-1";
    private static final String NOVEL = "novel-1";
    private static final String ARTIFACT = "artifact-1";
    private static final int REVISION = 2;
    private static final OffsetDateTime NOW = OffsetDateTime.parse("2026-09-05T12:00:00.123Z");

    @Test
    void 按冻结名称和批内重命名解析实体并为新建项绑定原下标身份() {
        Map<String, Object> before = row("character-1", Map.of(
                "name", "旧名",
                "background", "旧背景",
                "personality", "旧性格"));
        List<Map<String, Object>> characters = new ArrayList<>();
        characters.add(mutable("action", "update", "name", "旧名", "background", "第一版背景"));
        characters.add(mutable("action", "update", "id", "character-1", "name", "新名"));
        characters.add(mutable("action", "update", "name", "新名", "personality", "新性格"));
        characters.add(mutable("action", "create", "name", "批内新角色"));
        characters.add(mutable("action", "update", "name", "批内新角色", "background", "补充背景"));
        Map<String, Object> updates = new LinkedHashMap<>();
        updates.put("characters", characters);
        Map<String, Object> output = output("实体物化", updates);

        AgentUpdatesMaterializer.Materialized result = AgentUpdatesMaterializer.materialize(
                USER,
                NOVEL,
                ARTIFACT,
                REVISION,
                output,
                sources(List.of(indexRow(ResourceKind.CHARACTER, "character-1", "name", "旧名")),
                        target(ResourceKind.CHARACTER, "character-1", before)));

        List<Map<String, Object>> materialized = items(result, "characters");
        assertThat(materialized).hasSize(5);
        assertThat(materialized.get(0)).containsEntry("id", "character-1");
        assertThat(materialized.get(2)).containsEntry("id", "character-1");
        assertThat(materialized.get(3).get("clientRequestId"))
                .isEqualTo(AgentUpdatesIdentity.requestKey(ARTIFACT, REVISION, "characters", 3));
        String createdId = AgentUpdatesIdentity.resourceId(
                USER, NOVEL, ARTIFACT, REVISION, "characters", 3);
        assertThat(materialized.get(4)).containsEntry("id", createdId);
        assertThat(output.toString()).doesNotContain("clientRequestId", createdId);

        assertThat(result.diff()).extracting(item -> item.get("action"))
                .containsExactly("update", "update", "update", "create", "update");
        assertThat(fields(result.diff().get(1))).containsExactly(Map.of(
                "field", "name", "label", "名称", "oldValue", "旧名", "newValue", "新名"));
        assertThat(fields(result.diff().get(2))).containsExactly(Map.of(
                "field", "personality", "label", "性格", "oldValue", "旧性格", "newValue", "新性格"));
        assertThat(fields(result.diff().get(3)))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "currentStatus")
                        .containsEntry("newValue", "active"));
    }

    @Test
    void 角色经历按真实writer顺序解析批内人物并从虚拟顺序派生默认值() {
        Map<String, Object> experienceOne = experience("experience-1", "character-1", 2, "旧经历一");
        Map<String, Object> experienceTwo = experience("experience-2", "character-1", -1, "旧经历二");
        Map<String, Object> updates = new LinkedHashMap<>();
        updates.put("characters", List.of(mutable("action", "create", "name", "新角色")));
        updates.put("characterExperiences", List.of(
                mutable("action", "update", "id", "experience-1", "order", 10),
                mutable("action", "delete", "id", "experience-2"),
                mutable("action", "create", "characterName", "旧角色", "content", "第三段"),
                mutable("action", "create", "characterName", "新角色", "content", "首段")));
        List<Map<String, Object>> index = List.of(
                indexRow(ResourceKind.CHARACTER, "character-1", "name", "旧角色"),
                experienceIndex("experience-1", "character-1", 2),
                experienceIndex("experience-2", "character-1", -1));

        AgentUpdatesMaterializer.Materialized result = AgentUpdatesMaterializer.materialize(
                USER,
                NOVEL,
                ARTIFACT,
                REVISION,
                output("经历物化", updates),
                sources(index,
                        target(ResourceKind.CHARACTER, "character-1", row(
                                "character-1", Map.of("name", "旧角色"))),
                        target(ResourceKind.CHARACTER_EXPERIENCE, "experience-1", experienceOne),
                        target(ResourceKind.CHARACTER_EXPERIENCE, "experience-2", experienceTwo)));

        String createdCharacterId = AgentUpdatesIdentity.resourceId(
                USER, NOVEL, ARTIFACT, REVISION, "characters", 0);
        List<Map<String, Object>> experiences = items(result, "characterExperiences");
        assertThat(experiences.get(0)).containsEntry("id", "experience-1");
        assertThat(experiences.get(1)).containsEntry("id", "experience-2");
        assertThat(experiences.get(2))
                .containsEntry("characterId", "character-1")
                .containsEntry("order", 11)
                .containsEntry("clientRequestId", AgentUpdatesIdentity.requestKey(
                        ARTIFACT, REVISION, "characterExperiences", 2));
        assertThat(experiences.get(3))
                .containsEntry("characterId", createdCharacterId)
                .containsEntry("order", 0);
    }

    @Test
    void 角色经历默认顺序沿用真实负数最大值而不擅自钳制为零() {
        Map<String, Object> updates = Map.of("characterExperiences", List.of(
                mutable("action", "create", "characterName", "旧角色", "content", "新经历")));
        AgentUpdatesMaterializer.Materialized result = materialize(
                updates,
                sources(
                        List.of(
                                indexRow(ResourceKind.CHARACTER, "character-1", "name", "旧角色"),
                                experienceIndex("experience-1", "character-1", -7)),
                        target(ResourceKind.CHARACTER, "character-1", row(
                                "character-1", Map.of("name", "旧角色")))));

        assertThat(items(result, "characterExperiences").getFirst()).containsEntry("order", -6);
        assertThat(fields(result.diff().getFirst()))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "order")
                        .containsEntry("newValue", "-6"));
    }

    @Test
    void 大纲使用冻结名录和批内临时键并保留parentKey及派生顺序() {
        Map<String, Object> oldStage = outline("stage-1", "旧阶段", null, "stage", 0);
        Map<String, Object> oldUnit = outline("unit-1", "旧单元", "stage-1", "plot_unit", 1);
        Map<String, Object> updates = new LinkedHashMap<>();
        updates.put("outline", List.of(Map.of("nodeId", "stage-1", "actualWordCount", 120)));
        updates.put("outlineAdjustments", List.of(
                mutable("action", "update", "nodeTitle", "旧单元", "content", "补充单元"),
                mutable("action", "create", "kind", "stage", "title", "新阶段", "clientKey", "stage-key"),
                mutable("action", "update", "nodeTitle", "新阶段", "content", "批内补充"),
                mutable("action", "create", "kind", "plot_unit", "title", "新单元",
                        "parentKey", "stage-key", "linkedChapterId", "chapter-1")));
        List<Map<String, Object>> index = List.of(
                outlineIndex("stage-1", "旧阶段", null, "stage", 0),
                outlineIndex("unit-1", "旧单元", "stage-1", "plot_unit", 1),
                chapterIndex("chapter-1", "第一章", 1));

        AgentUpdatesMaterializer.Materialized result = AgentUpdatesMaterializer.materialize(
                USER,
                NOVEL,
                ARTIFACT,
                REVISION,
                output("大纲物化", updates),
                sources(index,
                        target(ResourceKind.OUTLINE_NODE, "stage-1", oldStage),
                        target(ResourceKind.OUTLINE_NODE, "unit-1", oldUnit),
                        target(ResourceKind.CHAPTER_REFERENCE, "chapter-1", row(
                                "chapter-1", Map.of("title", "第一章", "order", 1)))));

        List<Map<String, Object>> adjustments = items(result, "outlineAdjustments");
        assertThat(adjustments.get(0)).containsEntry("nodeId", "unit-1");
        assertThat(adjustments.get(1))
                .containsEntry("order", 2)
                .containsEntry("clientRequestId", AgentUpdatesIdentity.requestKey(
                        ARTIFACT, REVISION, "outlineAdjustments", 1));
        String newStageId = AgentUpdatesIdentity.resourceId(
                USER, NOVEL, ARTIFACT, REVISION, "outlineAdjustments", 1);
        assertThat(adjustments.get(2)).containsEntry("nodeId", newStageId);
        assertThat(adjustments.get(3))
                .containsEntry("parentKey", "stage-key")
                .doesNotContainKey("parentId")
                .containsEntry("order", 3);
        assertThat(fields(result.diff().get(2)))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "status")
                        .containsEntry("newValue", "planned"))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "order")
                        .containsEntry("newValue", "2"));
        assertThat(result.diff().stream()
                        .flatMap(item -> fields(item).stream())
                        .filter(field -> field.get("field").equals("linkedChapterId"))
                        .filter(field -> field.get("newValue") != null))
                .singleElement()
                .satisfies(field -> assertThat(field.get("newValue")).isEqualTo("chapter-1"));
    }

    @Test
    void 参考资料伏笔及三个全文保留null空串并生成完整展示字段和版本基线() {
        Map<String, Object> reference = row("reference-1", nullableMap(
                "title", "旧资料", "type", "web", "content", "旧正文", "sourceUrl", "https://old.invalid"));
        Map<String, Object> foreshadowing = row("foreshadow-1", Map.of(
                "name", "旧伏笔", "status", "active", "plantedContent", "旧埋设"));
        Map<String, Object> outline = row("outline-row", Map.of("content", "旧总纲"));
        Map<String, Object> world = row("world-row", Map.of("content", "旧世界"));
        List<Map<String, Object>> index = List.of(
                indexRow(ResourceKind.REFERENCE, "reference-1", "title", "旧资料"),
                indexRow(ResourceKind.FORESHADOWING, "foreshadow-1", "name", "旧伏笔"));
        Map<String, Object> updates = new LinkedHashMap<>();
        updates.put("foreshadowing", List.of(mutable(
                "action", "payoff", "name", "旧伏笔", "payoffAt", "第二章")));
        updates.put("references", List.of(mutable(
                "action", "update", "id", "reference-1", "sourceUrl", null)));
        updates.put("outlineContent", "新总纲");
        updates.put("worldSetting", "");
        updates.put("storyBackground", "");

        AgentUpdatesMaterializer.Materialized result = AgentUpdatesMaterializer.materialize(
                USER,
                NOVEL,
                ARTIFACT,
                REVISION,
                output("全文物化", updates),
                sources(index,
                        target(ResourceKind.REFERENCE, "reference-1", reference),
                        target(ResourceKind.FORESHADOWING, "foreshadow-1", foreshadowing),
                        target(ResourceKind.OUTLINE_CONTENT, NOVEL, outline),
                        target(ResourceKind.WORLD_SETTING, NOVEL, world),
                        missingSingleton(ResourceKind.STORY_BACKGROUND)));

        assertThat(items(result, "foreshadowing").getFirst()).containsEntry("id", "foreshadow-1");
        assertThat(items(result, "references").getFirst())
                .containsEntry("sourceUrl", null)
                .containsEntry("id", "reference-1");
        assertThat(result.payload()).containsEntry("baseOutlineUpdatedAt", NOW.toString());
        assertThat(result.payload().get("baseLoreUpdatedAt")).isEqualTo(nullableMap(
                "worldSetting", NOW.toString(), "storyBackground", null));
        assertThat(result.diff()).extracting(item -> item.get("section"))
                .containsExactly("伏笔", "参考资料", "总纲", "世界设定", "故事背景");
        Map<String, Object> sourceUrl = fields(result.diff().get(1)).getFirst();
        assertThat(sourceUrl)
                .containsEntry("field", "sourceUrl")
                .containsEntry("oldValue", "https://old.invalid")
                .doesNotContainKey("newValue");
        assertThat(fields(result.diff().get(3)).getFirst())
                .containsEntry("newValue", "");
        assertThat(fields(result.diff().get(4)).getFirst())
                .containsEntry("newValue", "")
                .doesNotContainKey("oldValue");
    }

    @Test
    void 删除Diff展示完整冻结业务字段且整树替换先展示实际删除再展示创建默认值() {
        Map<String, Object> oldStage = outline("stage-1", "旧阶段", null, "stage", 0);
        Map<String, Object> oldUnit = outline("unit-1", "旧单元", "stage-1", "plot_unit", 1);
        Map<String, Object> updates = new LinkedHashMap<>();
        updates.put("outlineTreeMode", "replace");
        updates.put("outlineAdjustments", List.of(mutable(
                "action", "create", "kind", "stage", "title", "新阶段", "order", 99)));

        AgentUpdatesMaterializer.Materialized result = AgentUpdatesMaterializer.materialize(
                USER,
                NOVEL,
                ARTIFACT,
                REVISION,
                output("整树替换", updates),
                sourcesWithMembership(
                        List.of(
                                outlineIndex("stage-1", "旧阶段", null, "stage", 0),
                                outlineIndex("unit-1", "旧单元", "stage-1", "plot_unit", 1)),
                        List.of(Map.of("id", "stage-1"), Map.of("id", "unit-1")),
                        target(ResourceKind.OUTLINE_NODE, "stage-1", oldStage),
                        target(ResourceKind.OUTLINE_NODE, "unit-1", oldUnit)));

        assertThat(result.diff()).extracting(item -> item.get("action"))
                .containsExactly("delete", "delete", "create");
        assertThat(result.diff()).extracting(item -> item.get("name"))
                .containsExactly("旧单元", "旧阶段", "新阶段");
        assertThat(fields(result.diff().getFirst()))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "title")
                        .containsEntry("oldValue", "旧单元")
                        .doesNotContainKey("newValue"))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "content")
                        .doesNotContainKeys("oldValue", "newValue"));
        assertThat(items(result, "outlineAdjustments").getFirst()).containsEntry("order", 0);
        assertThat(fields(result.diff().getLast()))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "status")
                        .containsEntry("newValue", "planned"))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "order")
                        .containsEntry("newValue", "0"));
    }

    @Test
    void 普通删除保留完整旧值而创建Diff展示数据库默认值且不改原缺省字段() {
        Map<String, Object> deletedCharacter = row("character-1", nullableMap(
                "name", "待删角色",
                "aliases", null,
                "gender", null,
                "age", null,
                "identity", null,
                "appearance", null,
                "personality", "旧性格",
                "background", null,
                "factionId", null,
                "combatAbility", null,
                "powerLevel", null,
                "specialSkills", null,
                "currentStatus", "active",
                "coreDesire", null,
                "shortTermGoal", null,
                "behaviorBoundaries", null,
                "speechStyle", null,
                "relationshipPrinciples", null,
                "statusNote", null));
        Map<String, Object> updates = new LinkedHashMap<>();
        updates.put("characters", List.of(
                Map.of("action", "delete", "id", "character-1"),
                Map.of("action", "create", "name", "新角色")));
        Map<String, Object> output = output("删除与创建", updates);

        AgentUpdatesMaterializer.Materialized result = AgentUpdatesMaterializer.materialize(
                USER,
                NOVEL,
                ARTIFACT,
                REVISION,
                output,
                sources(
                        List.of(indexRow(ResourceKind.CHARACTER, "character-1", "name", "待删角色")),
                        target(ResourceKind.CHARACTER, "character-1", deletedCharacter)));

        assertThat(fields(result.diff().getFirst()))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "personality")
                        .containsEntry("oldValue", "旧性格"))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "aliases")
                        .doesNotContainKeys("oldValue", "newValue"));
        assertThat(fields(result.diff().getLast()))
                .anySatisfy(field -> assertThat(field).containsEntry("field", "currentStatus")
                        .containsEntry("newValue", "active"));
        assertThat(items(result, "characters").getLast()).doesNotContainKey("currentStatus");
        assertThat(output.toString()).doesNotContain("currentStatus", "clientRequestId");
    }

    @Test
    void Diff比较保留JSON类型差异且合法可选空串不被裁剪() {
        Map<String, Object> outline = outline("stage-1", "阶段", null, "stage", 0);
        outline.put("actualWordCount", 1);
        Map<String, Object> reference = row("reference-1", nullableMap(
                "title", "资料",
                "type", "web",
                "content", "正文",
                "sourceUrl", null));
        Map<String, Object> updates = new LinkedHashMap<>();
        // Materializer 位于严格候选校验之后；这里刻意构造跨类型值，单独保护 Diff 比较不能按显示文本合并。
        updates.put("outline", List.of(mutable("nodeId", "stage-1", "actualWordCount", "1")));
        updates.put("references", List.of(mutable(
                "action", "update", "id", "reference-1", "sourceUrl", "")));

        AgentUpdatesMaterializer.Materialized result = materialize(
                updates,
                sources(
                        List.of(
                                outlineIndex("stage-1", "阶段", null, "stage", 0),
                                indexRow(ResourceKind.REFERENCE, "reference-1", "title", "资料")),
                        target(ResourceKind.OUTLINE_NODE, "stage-1", outline),
                        target(ResourceKind.REFERENCE, "reference-1", reference)));

        assertThat(fields(result.diff().getFirst()))
                .singleElement()
                .satisfies(field -> assertThat(field)
                        .containsEntry("field", "actualWordCount")
                        .containsEntry("oldValue", "1")
                        .containsEntry("newValue", "1"));
        assertThat(fields(result.diff().getLast()))
                .singleElement()
                .satisfies(field -> assertThat(field).containsEntry("field", "sourceUrl")
                        .containsEntry("newValue", ""));
    }

    @Test
    void 冻结名录重复身份非法而名称零个或多个匹配均明确拒绝() {
        List<Map<String, Object>> duplicateIdentity = List.of(
                indexRow(ResourceKind.CHARACTER, "character-1", "name", "甲"),
                indexRow(ResourceKind.CHARACTER, "character-1", "name", "甲"));
        assertCode(
                () -> materialize(
                        Map.of("characters", List.of(Map.of("action", "delete", "id", "character-1"))),
                        sources(duplicateIdentity)),
                "AGENT_UPDATES_SOURCE_INVALID");

        List<Map<String, Object>> ambiguous = List.of(
                indexRow(ResourceKind.CHARACTER, "character-1", "name", "同名"),
                indexRow(ResourceKind.CHARACTER, "character-2", "name", "同名"));
        assertCode(
                () -> materialize(
                        Map.of("characters", List.of(Map.of("action", "delete", "name", "同名"))),
                        sources(ambiguous)),
                "AGENT_UPDATES_TARGET_UNRESOLVED");
        assertCode(
                () -> materialize(
                        Map.of("characters", List.of(Map.of("action", "delete", "name", "不存在"))),
                        sources(List.of(indexRow(ResourceKind.CHARACTER, "character-1", "name", "甲")))),
                "AGENT_UPDATES_TARGET_UNRESOLVED");
    }

    @Test
    void 实际历史目标必须有完整before且物化结果递归只读() {
        AgentUpdatesFrozenSources missingBefore = sources(List.of(
                indexRow(ResourceKind.CHARACTER, "character-1", "name", "甲")));
        assertCode(
                () -> materialize(
                        Map.of("characters", List.of(Map.of(
                                "action", "update", "id", "character-1", "background", "新背景"))),
                        missingBefore),
                "AGENT_UPDATES_EVIDENCE_REQUIRED");

        AgentUpdatesMaterializer.Materialized result = materialize(
                Map.of("characters", List.of(Map.of("action", "create", "name", "甲"))),
                sources(List.of()));
        assertThatThrownBy(() -> result.payload().put("kind", "tampered"))
                .isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> items(result, "characters").getFirst().put("name", "tampered"))
                .isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> result.diff().clear()).isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> fields(result.diff().getFirst()).clear())
                .isInstanceOf(UnsupportedOperationException.class);
    }

    private static AgentUpdatesMaterializer.Materialized materialize(
            Map<String, Object> updates,
            AgentUpdatesFrozenSources sources) {
        return AgentUpdatesMaterializer.materialize(
                USER, NOVEL, ARTIFACT, REVISION, output("测试", updates), sources);
    }

    private static Map<String, Object> output(String summary, Map<String, Object> updates) {
        return Map.of("summary", summary, "updates", updates, "updatesSha256", "a".repeat(64));
    }

    private static AgentUpdatesFrozenSources sources(
            List<Map<String, Object>> index,
            WorkflowEvidenceItemPlan... targets) {
        List<WorkflowEvidenceItemPlan> evidence = new ArrayList<>();
        evidence.add(index(index));
        evidence.addAll(List.of(targets));
        return new AgentUpdatesFrozenSources(NOVEL, evidence);
    }

    private static AgentUpdatesFrozenSources sourcesWithMembership(
            List<Map<String, Object>> index,
            List<Map<String, Object>> members,
            WorkflowEvidenceItemPlan... targets) {
        List<WorkflowEvidenceItemPlan> evidence = new ArrayList<>();
        evidence.add(index(index));
        evidence.add(evidence(
                "outline_tree_membership",
                NOVEL,
                true,
                null,
                Map.of("items", members),
                Map.of("targetType", "novel", "targetId", NOVEL, "roles", List.of("delete_impact"))));
        evidence.addAll(List.of(targets));
        return new AgentUpdatesFrozenSources(NOVEL, evidence);
    }

    private static WorkflowEvidenceItemPlan index(List<Map<String, Object>> rows) {
        return evidence(
                "agent_updates_index",
                NOVEL,
                true,
                null,
                Map.of("items", rows),
                Map.of("targetType", "novel", "targetId", NOVEL, "roles", List.of("index")));
    }

    private static WorkflowEvidenceItemPlan target(
            ResourceKind kind,
            String id,
            Map<String, Object> before) {
        return evidence(
                kind.wireName(),
                id,
                true,
                NOW,
                before,
                Map.of("targetType", kind.wireName(), "targetId", id, "roles", List.of("target")));
    }

    private static WorkflowEvidenceItemPlan missingSingleton(ResourceKind kind) {
        return evidence(
                kind.wireName(),
                NOVEL,
                false,
                null,
                null,
                Map.of(
                        "targetType", kind.wireName(),
                        "targetId", NOVEL,
                        "roles", List.of("target"),
                        "absenceSentinel", Map.of("resourceType", "novel", "resourceId", NOVEL)));
    }

    private static WorkflowEvidenceItemPlan evidence(
            String resourceType,
            String resourceId,
            boolean exists,
            OffsetDateTime updatedAt,
            Object contentJson,
            Map<String, Object> metadata) {
        return new WorkflowEvidenceItemPlan(
                resourceType, resourceId, exists, null, updatedAt, null, contentJson, null, null, metadata);
    }

    private static Map<String, Object> indexRow(
            ResourceKind kind,
            String id,
            String nameField,
            String name) {
        return mutable("resourceType", kind.wireName(), "id", id, nameField, name);
    }

    private static Map<String, Object> experienceIndex(String id, String characterId, int order) {
        return mutable(
                "resourceType", ResourceKind.CHARACTER_EXPERIENCE.wireName(),
                "id", id,
                "characterId", characterId,
                "order", order);
    }

    private static Map<String, Object> outlineIndex(
            String id,
            String title,
            String parentId,
            String kind,
            int order) {
        return mutable(
                "resourceType", ResourceKind.OUTLINE_NODE.wireName(),
                "id", id,
                "title", title,
                "parentId", parentId,
                "kind", kind,
                "order", order);
    }

    private static Map<String, Object> chapterIndex(String id, String title, int order) {
        return mutable(
                "resourceType", ResourceKind.CHAPTER_REFERENCE.wireName(),
                "id", id,
                "title", title,
                "order", order);
    }

    private static Map<String, Object> experience(
            String id,
            String characterId,
            int order,
            String content) {
        Map<String, Object> result = mutable(
                "id", id,
                "characterId", characterId,
                "chapterId", null,
                "content", content,
                "order", order,
                "updatedAt", NOW.toString());
        return result;
    }

    private static Map<String, Object> outline(
            String id,
            String title,
            String parentId,
            String kind,
            int order) {
        return row(id, nullableMap(
                "title", title,
                "content", null,
                "parentId", parentId,
                "kind", kind,
                "status", "planned",
                "order", order,
                "linkedChapterId", null,
                "estimatedWordCount", null,
                "actualWordCount", null,
                "chapterStartOrder", null,
                "chapterEndOrder", null));
    }

    private static Map<String, Object> row(String id, Map<String, Object> fields) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", id);
        result.put("novelId", NOVEL);
        result.putAll(fields);
        result.put("updatedAt", NOW.toString());
        return result;
    }

    private static Map<String, Object> nullableMap(Object... values) {
        return mutable(values);
    }

    private static Map<String, Object> mutable(Object... values) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int index = 0; index < values.length; index += 2) {
            result.put((String) values[index], values[index + 1]);
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> items(
            AgentUpdatesMaterializer.Materialized result,
            String section) {
        return (List<Map<String, Object>>) ((Map<String, Object>) result.payload().get("updates")).get(section);
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> fields(Map<String, Object> diff) {
        return (List<Map<String, Object>>) diff.get("fields");
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(
                ApiException.class,
                error -> assertThat(error.code()).isEqualTo(code));
    }
}
