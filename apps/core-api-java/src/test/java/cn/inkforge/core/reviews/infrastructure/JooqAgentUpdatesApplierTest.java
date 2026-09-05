package cn.inkforge.core.reviews.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ArtifactSelectionRef;
import cn.inkforge.core.lore.infrastructure.JooqLoreRepository;
import cn.inkforge.core.outlines.infrastructure.JooqOutlineRepository;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.infrastructure.ReferenceRepositoryTestFactory;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.Source;
import cn.inkforge.core.reviews.application.AgentUpdatesExecutor;
import cn.inkforge.core.reviews.application.AgentUpdatesFrozenSources;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
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
class JooqAgentUpdatesApplierTest {
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-05T12:00:00.123");
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-05T12:01:00.456Z"), ZoneOffset.UTC);
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("agent_updates_apply").withUsername("inkforge").withPassword("test-only-password");
    private static CoreDatabase database;
    private static JooqAgentUpdatesEvidenceReader reader;
    private static JooqAgentUpdatesApplier applier;

    @BeforeAll
    static void schema() throws Exception {
        POSTGRES.copyFileToContainer(MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"), "/tmp/schema.sql");
        var result = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername()
                + ":" + POSTGRES.getPassword() + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName()));
        reader = new JooqAgentUpdatesEvidenceReader(JsonMapper.builder().build());
        var ids = new CuidV1Generator(CLOCK);
        applier = new JooqAgentUpdatesApplier(database, reader, new AgentUpdatesExecutor(
                new JooqLoreRepository(database, ids, CLOCK), new JooqOutlineRepository(database, ids, CLOCK),
                ReferenceRepositoryTestFactory.create(database, ids, CLOCK), ids, false));
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 未选资料变化和未选项缺少来源不阻塞实际采用且原候选不变() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.CHARACTER, n + "-a"));
        var updates = Map.<String, Object>of("characters", List.of(
                Map.of("action", "update", "id", n + "-b", "background", "不采用"),
                Map.of("action", "update", "id", n + "-a", "background", "采用全文")));
        database.dsl().execute("UPDATE public.\"Character\" SET background = '作者已改' WHERE id = ?", n + "-b");
        assertThat(apply(n, updates, List.of(new ArtifactSelectionRef("characters").index(1)), frozen)).isEqualTo(1);
        assertThat(field("Character", n + "-a", "background")).isEqualTo("采用全文");
        assertThat(field("Character", n + "-b", "background")).isEqualTo("作者已改");
        assertThat(updates.toString()).doesNotContain("expectedUpdatedAt", "clientRequestId");
    }

    @Test
    void 选中目标同时间但内容或外键改变仍然拒绝() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.ITEM, n + "-item"));
        database.dsl().execute("UPDATE public.\"Item\" SET \"ownerId\" = NULL WHERE id = ?", n + "-item");
        assertCode(() -> apply(n, Map.of("items", List.of(Map.of("action", "update", "id", n + "-item", "description", "不应写入"))),
                null, frozen), "AGENT_UPDATES_SOURCE_CHANGED");
        assertThat(field("Item", n + "-item", "description")).isEqualTo("原道具");
    }

    @Test
    void 显式引用的无关正文变化不变成目标CAS() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.ITEM, n + "-item"));
        database.dsl().execute("UPDATE public.\"Character\" SET background = '人物作者改稿', \"updatedAt\" = ? WHERE id = ?", NOW.plusMinutes(1), n + "-a");
        assertThat(apply(n, Map.of("items", List.of(Map.of("action", "update", "id", n + "-item",
                "ownerId", n + "-a", "description", "只改道具"))), null, frozen)).isEqualTo(1);
        assertThat(field("Item", n + "-item", "description")).isEqualTo("只改道具");
    }

    @Test
    void 同目标连续修改使用本事务新版本而不是重复注入旧时间() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.CHARACTER, n + "-a"), new Source(ResourceKind.REFERENCE, n + "-reference"));
        assertThat(apply(n, Map.of("characters", List.of(
                Map.of("action", "update", "id", n + "-a", "name", "新人物名"),
                Map.of("action", "update", "id", n + "-a", "background", "第二项全文")),
                "references", List.of(
                Map.of("action", "update", "id", n + "-reference", "title", "新标题"),
                Map.of("action", "update", "id", n + "-reference", "content", "新参考全文"))), null, frozen)).isEqualTo(4);
        assertThat(field("Character", n + "-a", "name")).isEqualTo("新人物名");
        assertThat(field("Character", n + "-a", "background")).isEqualTo("第二项全文");
        assertThat(field("ReferenceMaterial", n + "-reference", "content")).isEqualTo("新参考全文");
    }

    @Test
    void 后续领域拒绝删除时此前人物写入整体回滚() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.CHARACTER, n + "-a"), new Source(ResourceKind.LOCATION, n + "-location", true));
        var ids = new CuidV1Generator(CLOCK);
        var lore = org.mockito.Mockito.spy(new JooqLoreRepository(database, ids, CLOCK));
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        org.mockito.Mockito.doAnswer(invocation -> {
            if (calls.incrementAndGet() == 2) {
                assertThat(field("Character", n + "-a", "background")).isEqualTo("必须回滚");
            }
            return invocation.callRealMethod();
        }).when(lore).applyEntityMutations(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.anyList());
        var observed = new JooqAgentUpdatesApplier(database, reader, new AgentUpdatesExecutor(lore,
                new JooqOutlineRepository(database, ids, CLOCK), ReferenceRepositoryTestFactory.create(database, ids, CLOCK), ids, false));
        assertThatThrownBy(() -> observed.apply(n, n, n + "-artifact", 1, Map.of("characters", List.of(
                Map.of("action", "update", "id", n + "-a", "background", "必须回滚")), "locations", List.of(
                Map.of("action", "delete", "id", n + "-location"))), null, frozen)).isInstanceOf(ApiException.class);
        assertThat(calls.get()).isEqualTo(2);
        assertThat(field("Character", n + "-a", "background")).isEqualTo("人物原文");
        assertThat(field("Location", n + "-location", "name")).isEqualTo("地点");
    }

    @Test
    void 正式写入完成后外层审核事务失败仍回滚且锁不提前释放() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.CHARACTER, n + "-a"));
        assertThatThrownBy(() -> database.transactionResult(tx -> {
            apply(n, Map.of("characters", List.of(Map.of("action", "update", "id", n + "-a", "background", "事务内可见"))), null, frozen);
            assertThat(field("Character", n + "-a", "background")).isEqualTo("事务内可见");
            var concurrent = CompletableFuture.runAsync(() -> database.transactionResult(other -> {
                other.execute("SET LOCAL lock_timeout = '200ms'");
                other.execute("UPDATE public.\"Character\" SET background = '并发写入' WHERE id = ?", n + "-a");
                return null;
            }));
            assertThatThrownBy(() -> concurrent.get(5, TimeUnit.SECONDS)).hasStackTraceContaining("lock timeout");
            throw new IllegalStateException("模拟审核状态写入失败");
        })).isInstanceOf(IllegalStateException.class).hasMessage("模拟审核状态写入失败");
        assertThat(field("Character", n + "-a", "background")).isEqualTo("人物原文");
    }

    @Test
    void 单例缺席可以创建但冻结后出现新版本必须拒绝() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.WORLD_SETTING, n), new Source(ResourceKind.STORY_BACKGROUND, n));
        database.dsl().execute("INSERT INTO public.\"WorldSetting\" (id,\"novelId\",content,\"updatedAt\") VALUES (?, ?, '作者先写', ?)", n + "-world", n, NOW);
        assertCode(() -> apply(n, Map.of("worldSetting", "不覆盖作者"), null, frozen), "AGENT_UPDATES_SOURCE_CHANGED");
        assertThat(apply(n, Map.of("storyBackground", ""), null, frozen)).isEqualTo(1);
        assertThat(database.dsl().fetchValue("SELECT content FROM public.\"StoryBackground\" WHERE \"novelId\" = ?", n)).isEqualTo("");
    }

    @Test
    void 新建请求键绑定原下标而不是过滤后的下标() {
        String n = fixture();
        var frozen = new AgentUpdatesFrozenSources(n, List.of());
        var updates = Map.<String, Object>of("glossaries", List.of(
                Map.of("action", "create", "term", "第一词条", "definition", "第一释义"),
                Map.of("action", "create", "term", "第二词条", "definition", "第二释义")));
        apply(n, updates, List.of(new ArtifactSelectionRef("glossaries").index(1)), frozen);
        Object secondId = database.dsl().fetchValue("SELECT id FROM public.\"Glossary\" WHERE \"novelId\" = ? AND term = '第二词条'", n);
        apply(n, updates, null, frozen);
        assertThat(database.dsl().fetch("SELECT id FROM public.\"Glossary\" WHERE \"novelId\" = ?", n)).hasSize(2);
        assertThat(database.dsl().fetchValue("SELECT id FROM public.\"Glossary\" WHERE \"novelId\" = ? AND term = '第二词条'", n)).isEqualTo(secondId);
    }

    @Test
    void 整树替换仍可只采用合法的一个节点() {
        String n = fixture();
        var frozen = freezeTree(n);
        var updates = Map.<String, Object>of("outlineTreeMode", "replace", "outlineAdjustments", List.of(
                Map.of("action", "create", "kind", "stage", "title", "未选阶段"),
                Map.of("action", "create", "kind", "stage", "title", "选中阶段")));
        assertThat(apply(n, updates, List.of(new ArtifactSelectionRef("outlineAdjustments").index(1)), frozen)).isEqualTo(1);
        assertThat(database.dsl().fetch("SELECT title FROM public.\"OutlineNode\" WHERE \"novelId\" = ?", n)
                .getValues("title", String.class)).containsExactly("选中阶段");
    }

    @Test
    void 替换子项缺少被过滤父项由旧写入器拒绝并恢复已删旧树和前项写入() {
        String n = fixture();
        List<WorkflowEvidenceItemPlan> evidence = new ArrayList<>(database.transactionResult(tx -> reader.captureOutlineTree(tx, n)));
        evidence.addAll(database.transactionResult(tx -> reader.capture(tx, n, List.of(new Source(ResourceKind.CHARACTER, n + "-a")))));
        var updates = Map.<String, Object>of("characters", List.of(Map.of("action", "update", "id", n + "-a", "background", "前项写入")),
                "outlineTreeMode", "replace", "outlineAdjustments", List.of(
                Map.of("action", "create", "kind", "stage", "title", "父", "clientKey", "parent"),
                Map.of("action", "create", "kind", "plot_unit", "title", "子", "parentKey", "parent")));
        assertThatThrownBy(() -> apply(n, updates, List.of(new ArtifactSelectionRef("characters"),
                new ArtifactSelectionRef("outlineAdjustments").index(1)), new AgentUpdatesFrozenSources(n, evidence)))
                .isInstanceOf(IllegalArgumentException.class).hasMessageContaining("parentKey");
        assertThat(field("Character", n + "-a", "background")).isEqualTo("人物原文");
        assertThat(database.dsl().fetch("SELECT id FROM public.\"OutlineNode\" WHERE \"novelId\" = ?", n)).hasSize(2);
    }

    @Test
    void 替换成员新增会冲突() {
        String n = fixture();
        var frozen = freezeTree(n);
        database.dsl().execute("INSERT INTO public.\"OutlineNode\" (id,\"novelId\",title,kind,\"updatedAt\") VALUES (?, ?, '新增阶段', 'stage', ?)", n + "-new-stage", n, NOW);
        assertCode(() -> apply(n, Map.of("outlineTreeMode", "replace", "outlineAdjustments", List.of(
                Map.of("action", "create", "title", "替换", "kind", "stage"))), null, frozen), "AGENT_UPDATES_SOURCE_CHANGED");
    }

    @Test
    void 空树需要显式成员凭据且能正常替换() {
        String n = emptyNovel();
        var updates = Map.<String, Object>of("outlineTreeMode", "replace", "outlineAdjustments", List.of(
                Map.of("action", "create", "title", "首个阶段", "kind", "stage")));
        assertCode(() -> apply(n, updates, null, new AgentUpdatesFrozenSources(n, List.of())), "AGENT_UPDATES_EVIDENCE_REQUIRED");
        assertThat(apply(n, updates, null, freezeTree(n))).isEqualTo(1);
    }

    @Test
    void 同组新建大纲随后修改和parentKey仍交给现有写入器执行() {
        String n = emptyNovel();
        assertThat(apply(n, Map.of("outlineAdjustments", List.of(
                Map.of("action", "create", "kind", "stage", "title", "新阶段", "clientKey", "stage", "order", 0),
                Map.of("action", "update", "nodeTitle", "新阶段", "content", "随后补充"),
                Map.of("action", "create", "kind", "plot_unit", "title", "新单元", "parentKey", "stage", "order", 1))),
                null, new AgentUpdatesFrozenSources(n, List.of()))).isEqualTo(3);
        assertThat(database.dsl().fetchValue("SELECT content FROM public.\"OutlineNode\" WHERE \"novelId\" = ? AND title = '新阶段'", n)).isEqualTo("随后补充");
    }

    @Test
    void 所选伏笔变化不能绕过原写入器缺少时间CAS的限制() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.FORESHADOWING, n + "-foreshadow"));
        database.dsl().execute("UPDATE public.\"Foreshadowing\" SET \"plantedContent\" = '已变化' WHERE id = ?", n + "-foreshadow");
        assertCode(() -> apply(n, Map.of("foreshadowing", List.of(Map.of("action", "payoff", "id", n + "-foreshadow"))), null, frozen),
                "AGENT_UPDATES_SOURCE_CHANGED");
        assertThat(field("Foreshadowing", n + "-foreshadow", "status")).isEqualTo("active");
    }

    @Test
    void 未选大纲快照变化与空分区不影响人物采用() {
        String n = fixture();
        List<WorkflowEvidenceItemPlan> evidence = new ArrayList<>(database.transactionResult(tx -> reader.captureOutlineTree(tx, n)));
        evidence.addAll(database.transactionResult(tx -> reader.capture(tx, n, List.of(new Source(ResourceKind.CHARACTER, n + "-a")))));
        database.dsl().execute("UPDATE public.\"OutlineNode\" SET content = '无关改稿' WHERE id = ?", n + "-stage");
        assertThat(apply(n, Map.of("characters", List.of(Map.of("action", "update", "id", n + "-a", "background", "允许采用")),
                "outline", List.of(), "outlineAdjustments", List.of(), "foreshadowing", List.of()),
                null, new AgentUpdatesFrozenSources(n, evidence))).isEqualTo(1);
    }

    @Test
    void 本组新建节点的名称引用不命中同名历史节点() {
        String n = fixture();
        assertThat(apply(n, Map.of("outlineAdjustments", List.of(
                Map.of("action", "create", "kind", "stage", "title", "原阶段", "order", 2),
                Map.of("action", "update", "nodeTitle", "原阶段", "content", "只改刚创建的节点"))),
                null, new AgentUpdatesFrozenSources(n, List.of()))).isEqualTo(2);
        assertThat(field("OutlineNode", n + "-stage", "content")).isNull();
        assertThat(database.dsl().fetchValue("SELECT content FROM public.\"OutlineNode\" WHERE \"novelId\" = ? AND id <> ? AND title = '原阶段'", n, n + "-stage"))
                .isEqualTo("只改刚创建的节点");
    }

    @Test
    void 未物化的历史名称不能绕过来源校验在采用时重找当前数据() {
        String n = fixture();
        assertThatThrownBy(() -> apply(n, Map.of("outlineAdjustments", List.of(
                Map.of("action", "update", "nodeTitle", "原阶段", "content", "不应写入"))),
                null, new AgentUpdatesFrozenSources(n, List.of()))).isInstanceOf(IllegalArgumentException.class);
        assertCode(() -> apply(n, Map.of("characterExperiences", List.of(
                Map.of("action", "create", "characterName", "a", "content", "未冻结人物"))),
                null, new AgentUpdatesFrozenSources(n, List.of())), "AGENT_UPDATES_EVIDENCE_REQUIRED");
        assertThat(field("OutlineNode", n + "-stage", "content")).isNull();
    }

    @Test
    void 冻结后删除所选目标报告来源变化而不是冻结材料非法() {
        String n = fixture();
        var frozen = freeze(n, new Source(ResourceKind.ITEM, n + "-item"));
        database.dsl().execute("DELETE FROM public.\"Item\" WHERE id = ?", n + "-item");
        assertCode(() -> apply(n, Map.of("items", List.of(Map.of("action", "update", "id", n + "-item", "description", "不应复活"))),
                null, frozen), "AGENT_UPDATES_SOURCE_CHANGED");
    }

    private static int apply(String novel, Map<String, Object> updates, List<ArtifactSelectionRef> refs, AgentUpdatesFrozenSources frozen) {
        return applier.apply(novel, novel, novel + "-artifact", 1, updates, refs, frozen);
    }

    private static AgentUpdatesFrozenSources freeze(String novel, Source... sources) {
        return new AgentUpdatesFrozenSources(novel, database.transactionResult(tx -> reader.capture(tx, novel, List.of(sources))));
    }

    private static AgentUpdatesFrozenSources freezeTree(String novel) {
        return new AgentUpdatesFrozenSources(novel, database.transactionResult(tx -> reader.captureOutlineTree(tx, novel)));
    }

    private static void assertCode(Runnable work, String code) {
        assertThatThrownBy(work::run).isInstanceOfSatisfying(ApiException.class, error -> assertThat(error.code()).isEqualTo(code));
    }

    private static String field(String table, String id, String field) {
        return database.dsl().fetchOne("SELECT \"" + field + "\" FROM public.\"" + table + "\" WHERE id = ?", id).get(field, String.class);
    }

    private static String emptyNovel() {
        String n = "apply-" + UUID.randomUUID();
        database.dsl().execute("INSERT INTO public.\"User\" (id,username,\"passwordHash\",\"updatedAt\") VALUES (?, ?, 'test', ?)", n, n, NOW);
        database.dsl().execute("INSERT INTO public.\"Novel\" (id,name,\"userId\",\"updatedAt\") VALUES (?, '采用测试作品', ?, ?)", n, n, NOW);
        return n;
    }

    private static String fixture() {
        String n = emptyNovel();
        var tx = database.dsl();
        for (String suffix : List.of("a", "b")) tx.execute("INSERT INTO public.\"Character\" (id,\"novelId\",name,background,\"updatedAt\") VALUES (?, ?, ?, '人物原文', ?)", n + "-" + suffix, n, suffix, NOW);
        tx.execute("INSERT INTO public.\"Location\" (id,\"novelId\",name,\"updatedAt\") VALUES (?, ?, '地点', ?)", n + "-location", n, NOW);
        tx.execute("INSERT INTO public.\"Faction\" (id,\"novelId\",name,\"baseId\",\"updatedAt\") VALUES (?, ?, '组织', ?, ?)", n + "-faction", n, n + "-location", NOW);
        tx.execute("INSERT INTO public.\"Item\" (id,\"novelId\",name,description,\"ownerId\",\"updatedAt\") VALUES (?, ?, '道具', '原道具', ?, ?)", n + "-item", n, n + "-a", NOW);
        tx.execute("INSERT INTO public.\"ReferenceMaterial\" (id,\"novelId\",title,type,content,\"updatedAt\") VALUES (?, ?, '参考标题', 'web', '参考原文', ?)", n + "-reference", n, NOW);
        tx.execute("INSERT INTO public.\"RagDocument\" (id,\"novelId\",\"sourceType\",\"sourceId\",title,\"contentHash\",\"updatedAt\") VALUES (?, ?, 'reference_material', ?, '参考标题', '初始hash', ?)", n + "-rag", n, n + "-reference", NOW);
        tx.execute("INSERT INTO public.\"OutlineNode\" (id,\"novelId\",title,kind,\"updatedAt\") VALUES (?, ?, '原阶段', 'stage', ?)", n + "-stage", n, NOW);
        tx.execute("INSERT INTO public.\"OutlineNode\" (id,\"novelId\",title,kind,\"parentId\",\"updatedAt\") VALUES (?, ?, '原单元', 'plot_unit', ?, ?)", n + "-unit", n, n + "-stage", NOW);
        tx.execute("INSERT INTO public.\"Foreshadowing\" (id,\"novelId\",name,\"updatedAt\") VALUES (?, ?, '伏笔', ?)", n + "-foreshadow", n, NOW);
        return n;
    }
}
