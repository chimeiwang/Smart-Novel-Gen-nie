package cn.inkforge.core.reviews.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.Source;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqAgentUpdatesEvidenceReaderTest {
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-05T12:00:00.123");
    private static final JsonMapper JSON = JsonMapper.builder().build();
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("agent_updates_evidence").withUsername("inkforge").withPassword("test-only-password");
    private static CoreDatabase database;
    private static AgentUpdatesEvidenceReader reader;

    @BeforeAll
    static void schema() throws Exception {
        POSTGRES.copyFileToContainer(MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"), "/tmp/schema.sql");
        var result = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername()
                + ":" + POSTGRES.getPassword() + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName()));
        reader = new JooqAgentUpdatesEvidenceReader(JSON);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 定向人物保留完整原文和直接关系且不加载无关资料正文() {
        String novel = fixture();
        String full = " 原始设定😀\r\n".repeat(4000) + "不可丢失的末尾";
        database.dsl().execute("UPDATE public.\"Character\" SET background = ? WHERE id = ?", full, novel + "-character");
        var values = capture(novel, new Source(ResourceKind.CHARACTER, novel + "-character"));
        var target = value(values, "character");
        assertThat(JSON.valueToTree(target.contentJson()).path("background").textValue()).isEqualTo(full);
        assertThat(target.resourceUpdatedAt().toString()).isEqualTo("2026-09-05T12:00:00.123Z");
        String serialized = JSON.writeValueAsString(values);
        assertThat(serialized).contains("直接经历", "只读状态变化", "阵营说明")
                .doesNotContain("无关人物秘密", "不得进入资料快照的章节正文", "RAG派生正文");
        assertThat(value(values, "character_state_changes").resourceUpdatedAt()).isNull();
        assertThat(value(values, "character_owned_items", false)).isNull();
    }

    @Test
    void 所有实际目标分区可读取且章节引用只含元数据() {
        String novel = fixture();
        List<Source> sources = List.of(
                new Source(ResourceKind.CHARACTER, novel + "-character"),
                new Source(ResourceKind.LOCATION, novel + "-location"),
                new Source(ResourceKind.ITEM, novel + "-item"),
                new Source(ResourceKind.FACTION, novel + "-faction"),
                new Source(ResourceKind.GLOSSARY, novel + "-glossary"),
                new Source(ResourceKind.CHARACTER_EXPERIENCE, novel + "-experience"),
                new Source(ResourceKind.OUTLINE_NODE, novel + "-unit"),
                new Source(ResourceKind.FORESHADOWING, novel + "-foreshadowing"),
                new Source(ResourceKind.REFERENCE, novel + "-reference"),
                new Source(ResourceKind.OUTLINE_CONTENT, novel),
                new Source(ResourceKind.WORLD_SETTING, novel),
                new Source(ResourceKind.STORY_BACKGROUND, novel),
                new Source(ResourceKind.CHAPTER_REFERENCE, novel + "-chapter"));
        var values = database.transactionResult(tx -> reader.capture(tx, novel, sources));
        assertThat(values.stream().filter(item -> item.metadata().get("roles").equals(List.of("target")))).hasSize(13);
        assertThat(JSON.valueToTree(value(values, "reference").contentJson()).path("sourceUrl").textValue())
                .isEqualTo("https://example.invalid/原始资料");
        assertThat(JSON.valueToTree(value(values, "character_experience").contentJson()).path("order").intValue()).isEqualTo(-7);
        assertThat(JSON.writeValueAsString(values)).doesNotContain("不得进入资料快照的章节正文", "RAG派生正文");
        assertThat(value(values, "faction_territories").resourceUpdatedAt()).isNull();
    }

    @Test
    void 单例缺席绑定当前小说而空串仍为存在的完整正文() {
        String novel = fixture();
        var missing = value(capture(novel, new Source(ResourceKind.WORLD_SETTING, novel)), "world_setting");
        assertThat(missing.exists()).isFalse();
        assertThat(missing.contentJson()).isNull();
        assertThat(missing.resourceUpdatedAt()).isNull();
        assertThat(missing.metadata().get("absenceSentinel")).isEqualTo(Map.of("resourceType", "novel", "resourceId", novel));
        database.dsl().execute("INSERT INTO public.\"WorldSetting\" (id,\"novelId\",content,\"updatedAt\") VALUES (?, ?, '', ?)",
                novel + "-world", novel, NOW);
        var present = value(capture(novel, new Source(ResourceKind.WORLD_SETTING, novel)), "world_setting");
        assertThat(present.exists()).isTrue();
        assertThat(JSON.valueToTree(present.contentJson()).path("content").textValue()).isEmpty();
        assertThat(present.metadata()).doesNotContainKey("absenceSentinel");
    }

    @Test
    void 经历归属通过角色判定且外部目标不能伪装为缺席() {
        String novel = fixture();
        String other = fixture();
        for (Source source : List.of(new Source(ResourceKind.CHARACTER, other + "-character"),
                new Source(ResourceKind.CHARACTER_EXPERIENCE, other + "-experience"),
                new Source(ResourceKind.REFERENCE, "不存在' OR 1=1 --"),
                new Source(ResourceKind.WORLD_SETTING, other))) {
            assertThatThrownBy(() -> capture(novel, source)).isInstanceOfSatisfying(ApiException.class,
                    error -> assertThat(error.code()).isEqualTo("AGENT_UPDATES_SOURCE_INVALID"));
        }
        assertThatThrownBy(() -> capture("不存在的小说", new Source(ResourceKind.WORLD_SETTING, "不存在的小说")))
                .isInstanceOf(ApiException.class);
    }

    @Test
    void 无关资料修改不会改变该目标投影且解除外键不能仅靠更新时间判断() {
        String novel = fixture();
        Source source = new Source(ResourceKind.ITEM, novel + "-item");
        String before = JSON.writeValueAsString(capture(novel, source));
        database.dsl().execute("UPDATE public.\"Character\" SET background = '无关资料已经修改' WHERE id = ?", novel + "-other");
        assertThat(JSON.writeValueAsString(capture(novel, source))).isEqualTo(before);
        var targetBefore = value(capture(novel, source), "item");
        database.dsl().execute("UPDATE public.\"Item\" SET \"ownerId\" = NULL WHERE id = ?", novel + "-item");
        var targetAfter = value(capture(novel, source), "item");
        assertThat(targetAfter.resourceUpdatedAt()).isEqualTo(targetBefore.resourceUpdatedAt());
        assertThat(targetAfter.contentJson()).isNotEqualTo(targetBefore.contentJson());
    }

    @Test
    void 删除依赖仅在明确请求时读取并不含被解除引用对象的无关字段() {
        String novel = fixture();
        var sources = List.of(new Source(ResourceKind.CHARACTER, novel + "-character", true),
                new Source(ResourceKind.FACTION, novel + "-faction", true),
                new Source(ResourceKind.LOCATION, novel + "-location", true),
                new Source(ResourceKind.OUTLINE_NODE, novel + "-stage", true));
        var values = database.transactionResult(tx -> reader.capture(tx, novel, sources));
        for (String type : List.of("character_owned_items", "faction_characters", "location_children",
                "location_based_factions", "location_territories", "outline_delete_children")) {
            var item = value(values, type);
            assertThat(item.metadata().get("roles")).isEqualTo(List.of("delete_impact"));
            assertThat(item.resourceUpdatedAt()).isNull();
        }
        for (String type : List.of("character_experiences", "character_relations", "character_state_changes", "faction_territories")) {
            assertThat(value(values, type).metadata().get("roles")).isEqualTo(List.of("direct_relation", "delete_impact"));
            assertThat(values.stream().filter(item -> item.resourceType().equals(type))).hasSize(1);
        }
        assertThat(JSON.valueToTree(value(values, "character_owned_items").contentJson()).at("/items/0").properties())
                .extracting(Map.Entry::getKey).containsExactlyInAnyOrder("id", "ownerId");
        String original = JSON.writeValueAsString(value(values, "character_owned_items"));
        database.dsl().execute("UPDATE public.\"Item\" SET description = '无关描述修改' WHERE id = ?", novel + "-item");
        assertThat(JSON.writeValueAsString(value(capture(novel, sources.getFirst()), "character_owned_items"))).isEqualTo(original);
    }

    @Test
    void 空关系集合和无时间戳关系均保持可重建事实() {
        String novel = fixture();
        var values = capture(novel, new Source(ResourceKind.CHARACTER, novel + "-character"));
        assertThat(JSON.valueToTree(value(values, "character_relations").contentJson()).path("items")).isEmpty();
        String before = JSON.writeValueAsString(value(values, "character_state_changes"));
        database.dsl().execute("UPDATE public.\"CharacterStateChange\" SET description = '已修订状态事实' WHERE id = ?", novel + "-state");
        var changed = value(capture(novel, new Source(ResourceKind.CHARACTER, novel + "-character")), "character_state_changes");
        assertThat(changed.resourceUpdatedAt()).isNull();
        assertThat(JSON.writeValueAsString(changed)).isNotEqualTo(before);
    }

    @Test
    void 人物关系校验双方归属且不会静默过滤异常关系() {
        String novel = fixture();
        String other = fixture();
        database.dsl().execute("""
                INSERT INTO public."CharacterRelation" (id,"characterId","targetId","relationType",description,"updatedAt")
                VALUES (?, ?, ?, 'friend', '合法关系全文', ?)
                """, novel + "-relation", novel + "-character", novel + "-other", NOW);
        assertThat(JSON.writeValueAsString(capture(novel, new Source(ResourceKind.CHARACTER, novel + "-character"))))
                .contains("合法关系全文").doesNotContain("无关人物秘密");
        database.dsl().execute("""
                INSERT INTO public."CharacterRelation" (id,"characterId","targetId","relationType",description,"updatedAt")
                VALUES (?, ?, ?, 'friend', '不得泄漏的跨小说关系', ?)
                """, novel + "-cross-relation", novel + "-character", other + "-character", NOW);
        for (String selected : List.of(novel, other)) {
            assertThatThrownBy(() -> capture(selected, new Source(ResourceKind.CHARACTER, selected + "-character", true)))
                    .isInstanceOfSatisfying(ApiException.class,
                            error -> assertThat(error.code()).isEqualTo("AGENT_UPDATES_SOURCE_INVALID"));
        }
    }

    @Test
    void 领地关系从组织或地点进入均拒绝跨小说另一端() {
        String novel = fixture();
        String other = fixture();
        database.dsl().execute("INSERT INTO public.\"_FactionTerritories\" (\"A\",\"B\") VALUES (?, ?)",
                novel + "-faction", other + "-location");
        assertThatThrownBy(() -> capture(novel, new Source(ResourceKind.FACTION, novel + "-faction")))
                .isInstanceOfSatisfying(ApiException.class,
                        error -> assertThat(error.code()).isEqualTo("AGENT_UPDATES_SOURCE_INVALID"));
        assertThatThrownBy(() -> capture(other, new Source(ResourceKind.LOCATION, other + "-location", true)))
                .isInstanceOfSatisfying(ApiException.class,
                        error -> assertThat(error.code()).isEqualTo("AGENT_UPDATES_SOURCE_INVALID"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void 快照深冻结且读取清单去重不丢显式删除依赖() {
        String novel = fixture();
        Source plain = new Source(ResourceKind.CHARACTER, novel + "-character");
        Source deletion = new Source(ResourceKind.CHARACTER, novel + "-character", true);
        var values = capture(novel, plain, deletion, plain);
        assertThat(values.stream().filter(item -> item.resourceType().equals("character"))).hasSize(1);
        assertThat(value(values, "character_owned_items")).isNotNull();
        assertThatThrownBy(() -> values.clear()).isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> ((Map<String, Object>) value(values, "character").contentJson()).put("name", "篡改"))
                .isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> ((List<?>) ((Map<?, ?>) value(values, "character_experiences").contentJson()).get("items")).clear())
                .isInstanceOf(UnsupportedOperationException.class);
        assertThat(JSON.writeValueAsString(capture(novel, deletion))).isEqualTo(JSON.writeValueAsString(values));
    }

    @Test
    void 目标锁持续到外层事务结束而不是读取后提前释放() {
        String novel = fixture();
        database.transactionResult(tx -> {
            reader.capture(tx, novel, List.of(new Source(ResourceKind.GLOSSARY, novel + "-glossary")));
            var concurrent = CompletableFuture.runAsync(() -> database.transactionResult(other -> {
                other.execute("SET LOCAL lock_timeout = '200ms'");
                other.execute("UPDATE public.\"Glossary\" SET definition = '不应成功' WHERE id = ?", novel + "-glossary");
                return null;
            }));
            assertThatThrownBy(() -> concurrent.get(5, TimeUnit.SECONDS)).hasStackTraceContaining("lock timeout");
            return null;
        });
        assertThat(database.dsl().fetchOne("SELECT definition FROM public.\"Glossary\" WHERE id = ?", novel + "-glossary")
                .get("definition", String.class)).isEqualTo("词条原文");
    }

    private static List<WorkflowEvidenceItemPlan> capture(String novel, Source... sources) {
        return database.transactionResult(tx -> reader.capture(tx, novel, List.of(sources)));
    }

    private static WorkflowEvidenceItemPlan value(List<WorkflowEvidenceItemPlan> items, String type) {
        return value(items, type, true);
    }

    private static WorkflowEvidenceItemPlan value(List<WorkflowEvidenceItemPlan> items, String type, boolean required) {
        var found = items.stream().filter(item -> item.resourceType().equals(type)).findFirst().orElse(null);
        if (required) assertThat(found).as(type).isNotNull();
        return found;
    }

    private static String fixture() {
        String n = "updates-" + UUID.randomUUID();
        var tx = database.dsl();
        tx.execute("INSERT INTO public.\"User\" (id,username,\"passwordHash\",\"updatedAt\") VALUES (?, ?, 'test', ?)", n, n, NOW);
        tx.execute("INSERT INTO public.\"Novel\" (id,name,\"userId\",\"updatedAt\") VALUES (?, '资料作品', ?, ?)", n, n, NOW);
        tx.execute("INSERT INTO public.\"Chapter\" (id,\"novelId\",title,content,\"order\",\"updatedAt\") VALUES (?, ?, '章节元数据', '不得进入资料快照的章节正文', 1, ?)", n + "-chapter", n, NOW);
        tx.execute("INSERT INTO public.\"Outline\" (id,\"novelId\",content,\"updatedAt\") VALUES (?, ?, '完整总纲😀', ?)", n + "-outline", n, NOW);
        tx.execute("INSERT INTO public.\"Location\" (id,\"novelId\",name,\"updatedAt\") VALUES (?, ?, '地点', ?)", n + "-location", n, NOW);
        tx.execute("INSERT INTO public.\"Faction\" (id,\"novelId\",name,description,\"baseId\",\"updatedAt\") VALUES (?, ?, '组织', '阵营说明', ?, ?)", n + "-faction", n, n + "-location", NOW);
        tx.execute("INSERT INTO public.\"_FactionTerritories\" (\"A\",\"B\") VALUES (?, ?)", n + "-faction", n + "-location");
        tx.execute("INSERT INTO public.\"Character\" (id,\"novelId\",name,\"factionId\",\"updatedAt\") VALUES (?, ?, '人物', ?, ?)", n + "-character", n, n + "-faction", NOW);
        tx.execute("INSERT INTO public.\"Character\" (id,\"novelId\",name,background,\"updatedAt\") VALUES (?, ?, '无关人物', '无关人物秘密', ?)", n + "-other", n, NOW);
        tx.execute("INSERT INTO public.\"Item\" (id,\"novelId\",name,\"ownerId\",\"updatedAt\") VALUES (?, ?, '道具', ?, ?)", n + "-item", n, n + "-character", NOW);
        tx.execute("INSERT INTO public.\"Glossary\" (id,\"novelId\",term,definition,\"updatedAt\") VALUES (?, ?, '词条', '词条原文', ?)", n + "-glossary", n, NOW);
        tx.execute("INSERT INTO public.\"CharacterExperience\" (id,\"characterId\",\"chapterId\",content,\"order\",\"updatedAt\") VALUES (?, ?, ?, '直接经历', -7, ?)", n + "-experience", n + "-character", n + "-chapter", NOW);
        tx.execute("INSERT INTO public.\"CharacterStateChange\" (id,\"characterId\",\"changeType\",description,\"afterState\") VALUES (?, ?, '状态', '只读状态变化', '变化后')", n + "-state", n + "-character");
        tx.execute("INSERT INTO public.\"Foreshadowing\" (id,\"novelId\",name,\"plantedAt\",\"updatedAt\") VALUES (?, ?, '伏笔', '第一章只是文本描述', ?)", n + "-foreshadowing", n, NOW);
        tx.execute("INSERT INTO public.\"ReferenceMaterial\" (id,\"novelId\",title,type,content,\"sourceUrl\",\"updatedAt\") VALUES (?, ?, '参考资料', 'web', '参考全文', 'https://example.invalid/原始资料', ?)", n + "-reference", n, NOW);
        tx.execute("INSERT INTO public.\"RagDocument\" (id,\"novelId\",\"sourceType\",\"sourceId\",title,\"contentHash\",\"updatedAt\") VALUES (?, ?, 'reference_material', ?, 'RAG派生正文', 'hash', ?)", n + "-rag", n, n + "-reference", NOW);
        tx.execute("INSERT INTO public.\"OutlineNode\" (id,\"novelId\",title,kind,\"updatedAt\") VALUES (?, ?, '阶段', 'stage', ?)", n + "-stage", n, NOW);
        tx.execute("INSERT INTO public.\"OutlineNode\" (id,\"novelId\",title,kind,\"parentId\",\"linkedChapterId\",\"updatedAt\") VALUES (?, ?, '单元', 'plot_unit', ?, ?, ?)", n + "-unit", n, n + "-stage", n + "-chapter", NOW);
        return n;
    }
}
