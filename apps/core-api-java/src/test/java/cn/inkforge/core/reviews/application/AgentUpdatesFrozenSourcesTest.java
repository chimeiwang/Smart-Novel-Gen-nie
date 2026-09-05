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

class AgentUpdatesFrozenSourcesTest {
    private static final String NOVEL = "novel-1";
    private static final OffsetDateTime NOW = OffsetDateTime.parse("2026-09-05T12:00:00.123Z");

    @Test
    void 目标直接引用和缺席单例都按真实业务身份索引() {
        Map<String, Object> character = row("character-1", "character");
        Map<String, Object> faction = row("faction-1", "faction");
        Map<String, Object> world = row("world-row", "world");
        List<WorkflowEvidenceItemPlan> evidence = List.of(
                item("character", "character-1", true, NOW, character,
                        metadata("character", "character-1", "target")),
                item("faction_reference", "character:character-1:factionId", true, NOW, faction,
                        metadata("character", "character-1", "direct_reference")),
                item("world_setting", NOVEL, true, NOW, world,
                        metadata("world_setting", NOVEL, "target")),
                missingSingleton("story_background"),
                item("debug_context", "ignored", true, null, Map.of("not", "business evidence"), Map.of()));

        AgentUpdatesFrozenSources sources = new AgentUpdatesFrozenSources(NOVEL, evidence);

        assertThat(sources.require(ResourceKind.CHARACTER, "character-1"))
                .satisfies(snapshot -> {
                    assertThat(snapshot.kind()).isEqualTo(ResourceKind.CHARACTER);
                    assertThat(snapshot.id()).isEqualTo("character-1");
                    assertThat(snapshot.exists()).isTrue();
                    assertThat(snapshot.before()).isEqualTo(character);
                    assertThat(snapshot.updatedAt()).isEqualTo(NOW);
                });
        assertThat(sources.require(ResourceKind.FACTION, "faction-1").before()).isEqualTo(faction);
        assertThat(sources.require(ResourceKind.WORLD_SETTING, NOVEL).before()).isEqualTo(world);
        assertThat(sources.require(ResourceKind.STORY_BACKGROUND, NOVEL))
                .satisfies(snapshot -> {
                    assertThat(snapshot.exists()).isFalse();
                    assertThat(snapshot.before()).isNull();
                    assertThat(snapshot.updatedAt()).isNull();
                });
        assertRequired(() -> sources.require(ResourceKind.CHARACTER, "missing"));
        assertRequired(() -> sources.requireCollection("debug_context", "ignored"));
    }

    @Test
    void 全部具名集合可取而只有两种完整行能追加到目标索引() {
        Map<String, Object> experience = row("experience-1", "experience");
        experience.put("characterId", "character-1");
        experience.put("chapterId", null);
        Map<String, Object> child = row("outline-child", "child");
        child.put("parentId", "outline-parent");
        Map<String, Object> ownedItem = new LinkedHashMap<>();
        ownedItem.put("id", "item-1");
        ownedItem.put("ownerId", "character-1");

        List<WorkflowEvidenceItemPlan> evidence = List.of(
                collection("character_experiences", "character", "character-1", List.of("direct_relation"),
                        List.of(experience)),
                collection("character_relations", "character", "character-1", List.of("direct_relation"), List.of()),
                collection("character_state_changes", "character", "character-1", List.of("direct_relation"),
                        List.of()),
                collection("faction_territories", "faction", "faction-1", List.of("direct_relation"), List.of()),
                collection("outline_children", "outline_node", "outline-parent", List.of("direct_relation"),
                        List.of(child)),
                collection("outline_sibling_structure", "outline_node", "outline-parent", List.of("direct_relation"),
                        List.of()),
                collection("character_owned_items", "character", "character-1", List.of("delete_impact"),
                        List.of(ownedItem)),
                collection("faction_characters", "faction", "faction-1", List.of("delete_impact"), List.of()),
                collection("location_children", "location", "location-1", List.of("delete_impact"), List.of()),
                collection("location_based_factions", "location", "location-1", List.of("delete_impact"), List.of()),
                collection("location_territories", "location", "location-1", List.of("delete_impact"), List.of()),
                collection("outline_delete_children", "outline_node", "outline-parent", List.of("delete_impact"),
                        List.of()),
                collection("outline_tree_membership", "novel", NOVEL, List.of("delete_impact"),
                        List.of(Map.of("id", "outline-child"))));

        AgentUpdatesFrozenSources sources = new AgentUpdatesFrozenSources(NOVEL, evidence);

        for (WorkflowEvidenceItemPlan item : evidence) {
            assertThat(sources.requireCollection(item.resourceType(), item.resourceId()))
                    .isEqualTo(((Map<?, ?>) item.contentJson()).get("items"));
        }
        assertThat(sources.require(ResourceKind.CHARACTER_EXPERIENCE, "experience-1"))
                .satisfies(snapshot -> {
                    assertThat(snapshot.before()).containsEntry("chapterId", null);
                    assertThat(snapshot.updatedAt()).isEqualTo(NOW);
                });
        assertThat(sources.require(ResourceKind.OUTLINE_NODE, "outline-child").before())
                .containsEntry("parentId", "outline-parent");
        assertThat(sources.snapshots(ResourceKind.CHARACTER_EXPERIENCE))
                .extracting(AgentUpdatesFrozenSources.Snapshot::id)
                .containsExactly("experience-1");
        assertThat(sources.snapshots(ResourceKind.OUTLINE_NODE))
                .extracting(AgentUpdatesFrozenSources.Snapshot::id)
                .containsExactly("outline-child");
        assertThatThrownBy(() -> sources.snapshots(ResourceKind.OUTLINE_NODE).clear())
                .isInstanceOf(UnsupportedOperationException.class);
        assertRequired(() -> sources.require(ResourceKind.ITEM, "item-1"));
        assertThat(sources.requireCollection("outline_tree_membership", NOVEL))
                .containsExactly(Map.of("id", "outline-child"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void 快照与集合递归冻结并保留显式null() {
        Map<String, Object> character = row("character-1", "character");
        character.put("aliases", null);
        character.put("notes", new ArrayList<>(List.of(Map.of("text", "原文"))));
        AgentUpdatesFrozenSources sources = new AgentUpdatesFrozenSources(
                NOVEL,
                List.of(
                        item("character", "character-1", true, NOW, character,
                                metadata("character", "character-1", "target")),
                        collection("character_owned_items", "character", "character-1", List.of("delete_impact"),
                                List.of(Map.of("id", "item-1", "ownerId", "character-1")))));

        Map<String, Object> before = sources.require(ResourceKind.CHARACTER, "character-1").before();
        assertThat(before).containsEntry("aliases", null);
        assertThatThrownBy(() -> before.put("name", "篡改")).isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> ((List<Object>) before.get("notes")).clear())
                .isInstanceOf(UnsupportedOperationException.class);
        List<Map<String, Object>> collection = sources.requireCollection("character_owned_items", "character-1");
        assertThatThrownBy(collection::clear).isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> collection.getFirst().put("ownerId", "篡改"))
                .isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    void 同一真实来源和集合的完全相同快照去重而冲突快照拒绝() {
        WorkflowEvidenceItemPlan target = item(
                "character", "character-1", true, NOW, row("character-1", "target"),
                metadata("character", "character-1", "target"));
        WorkflowEvidenceItemPlan conflictingReference = item(
                "character_reference", "item:item-1:ownerId", true, NOW, row("character-1", "reference"),
                metadata("item", "item-1", "direct_reference"));
        assertInvalid(() -> new AgentUpdatesFrozenSources(NOVEL, List.of(target, conflictingReference)));

        WorkflowEvidenceItemPlan collection = collection(
                "character_relations", "character", "character-1", List.of("direct_relation"), List.of());
        AgentUpdatesFrozenSources exactCollection = new AgentUpdatesFrozenSources(
                NOVEL, List.of(collection, collection));
        assertThat(exactCollection.requireCollection("character_relations", "character-1")).isEmpty();

        WorkflowEvidenceItemPlan conflictingCollection = collection(
                "character_relations",
                "character",
                "character-1",
                List.of("direct_relation"),
                List.of(Map.of("id", "relation-1")));
        assertInvalid(() -> new AgentUpdatesFrozenSources(NOVEL, List.of(collection, conflictingCollection)));
    }

    @Test
    void 目标与多个真实Reader形状的直接引用共享同一完整行时只建立一个来源() {
        Map<String, Object> character = row("character-1", "shared");
        WorkflowEvidenceItemPlan target = item(
                "character", "character-1", true, NOW, character,
                metadata("character", "character-1", "target"));
        WorkflowEvidenceItemPlan firstReference = item(
                "character_reference", "item:item-1:ownerId", true, NOW, character,
                metadata("item", "item-1", "direct_reference"));
        WorkflowEvidenceItemPlan secondReference = item(
                "character_reference", "item:item-2:ownerId", true, NOW, character,
                metadata("item", "item-2", "direct_reference"));

        AgentUpdatesFrozenSources sources = new AgentUpdatesFrozenSources(
                NOVEL, List.of(target, firstReference, secondReference));

        assertThat(sources.snapshots(ResourceKind.CHARACTER))
                .extracting(AgentUpdatesFrozenSources.Snapshot::id)
                .containsExactly("character-1");
        assertThat(sources.require(ResourceKind.CHARACTER, "character-1").before()).isEqualTo(character);
    }

    @Test
    void 非完整来源与集合成员身份不一致时拒绝() {
        WorkflowEvidenceItemPlan missingCharacter = item(
                "character", "character-1", false, null, null,
                metadata("character", "character-1", "target"));
        assertInvalid(() -> new AgentUpdatesFrozenSources(NOVEL, List.of(missingCharacter)));

        WorkflowEvidenceItemPlan wrongTargetId = item(
                "character", "character-1", true, NOW, row("another-character", "wrong"),
                metadata("character", "character-1", "target"));
        assertInvalid(() -> new AgentUpdatesFrozenSources(NOVEL, List.of(wrongTargetId)));

        Map<String, Object> wrongExperience = row("experience-1", "experience");
        wrongExperience.put("characterId", "another-character");
        assertInvalid(() -> new AgentUpdatesFrozenSources(
                NOVEL,
                List.of(collection("character_experiences", "character", "character-1",
                        List.of("direct_relation"), List.of(wrongExperience)))));

        Map<String, Object> wrongChild = row("child-1", "child");
        wrongChild.put("parentId", "another-parent");
        assertInvalid(() -> new AgentUpdatesFrozenSources(
                NOVEL,
                List.of(collection("outline_children", "outline_node", "outline-parent",
                        List.of("direct_relation"), List.of(wrongChild)))));
    }

    @Test
    void 缺席单例必须绑定小说并携带精确缺席哨兵() {
        WorkflowEvidenceItemPlan wrongNovel = item(
                "world_setting", "another-novel", false, null, null,
                metadata("world_setting", "another-novel", "target"));
        assertInvalid(() -> new AgentUpdatesFrozenSources(NOVEL, List.of(wrongNovel)));

        WorkflowEvidenceItemPlan noSentinel = item(
                "world_setting", NOVEL, false, null, null,
                metadata("world_setting", NOVEL, "target"));
        assertInvalid(() -> new AgentUpdatesFrozenSources(NOVEL, List.of(noSentinel)));
    }

    @Test
    void 大纲树成员集合显式区分空树并拒绝重复成员且不冒充完整节点() {
        AgentUpdatesFrozenSources empty = new AgentUpdatesFrozenSources(
                NOVEL,
                List.of(collection("outline_tree_membership", "novel", NOVEL, List.of("delete_impact"), List.of())));
        assertThat(empty.requireCollection("outline_tree_membership", NOVEL)).isEmpty();
        assertThat(empty.snapshots(ResourceKind.OUTLINE_NODE)).isEmpty();

        WorkflowEvidenceItemPlan duplicate = collection(
                "outline_tree_membership",
                "novel",
                NOVEL,
                List.of("delete_impact"),
                List.of(Map.of("id", "node-1"), Map.of("id", "node-1")));
        assertInvalid(() -> new AgentUpdatesFrozenSources(NOVEL, List.of(duplicate)));

        WorkflowEvidenceItemPlan wrongNovel = collection(
                "outline_tree_membership", "novel", "another-novel", List.of("delete_impact"), List.of());
        assertInvalid(() -> new AgentUpdatesFrozenSources(NOVEL, List.of(wrongNovel)));
    }

    private static WorkflowEvidenceItemPlan missingSingleton(String resourceType) {
        Map<String, Object> metadata = new LinkedHashMap<>(metadata(resourceType, NOVEL, "target"));
        metadata.put("absenceSentinel", Map.of("resourceType", "novel", "resourceId", NOVEL));
        return item(resourceType, NOVEL, false, null, null, metadata);
    }

    private static WorkflowEvidenceItemPlan collection(
            String resourceType,
            String targetType,
            String targetId,
            List<String> roles,
            List<Map<String, Object>> rows) {
        return item(
                resourceType,
                targetId,
                true,
                null,
                Map.of("items", rows),
                metadata(targetType, targetId, roles.toArray(String[]::new)));
    }

    private static WorkflowEvidenceItemPlan item(
            String resourceType,
            String resourceId,
            boolean exists,
            OffsetDateTime updatedAt,
            Object contentJson,
            Map<String, Object> metadata) {
        return new WorkflowEvidenceItemPlan(
                resourceType,
                resourceId,
                exists,
                null,
                updatedAt,
                null,
                contentJson,
                null,
                null,
                metadata);
    }

    private static Map<String, Object> metadata(String targetType, String targetId, String... roles) {
        return Map.of("targetType", targetType, "targetId", targetId, "roles", List.of(roles));
    }

    private static Map<String, Object> row(String id, String value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", id);
        result.put("novelId", NOVEL);
        result.put("value", value);
        result.put("updatedAt", NOW.toString());
        return result;
    }

    private static void assertRequired(Runnable action) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(
                ApiException.class,
                error -> assertThat(error.code()).isEqualTo("AGENT_UPDATES_EVIDENCE_REQUIRED"));
    }

    private static void assertInvalid(Runnable action) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(
                ApiException.class,
                error -> assertThat(error.code()).isEqualTo("AGENT_UPDATES_SOURCE_INVALID"));
    }
}
