package cn.inkforge.core.reviews.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.EvidenceExpansionItem;
import cn.inkforge.contracts.api.EvidenceExpansionRequest;
import cn.inkforge.contracts.api.EvidenceRange;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.Source;
import cn.inkforge.core.reviews.application.AgentUpdatesFrozenSources;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.json.JsonMapper;

/** 只在隔离 PostgreSQL 验证来源补齐；不创建模型调用或开放业务 Catalog。 */
@Testcontainers
class JooqAgentUpdatesEvidenceExpansionTest {
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-05T05:00:00.123");
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-05T05:00:00.123Z"), ZoneOffset.UTC);
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final JooqAgentUpdatesEvidenceReader READER = new JooqAgentUpdatesEvidenceReader(JSON);
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("test-only-password");
    private static CoreDatabase database;
    private static JooqWorkflowStartRepository starts;
    private static ExecutionRegistry registry;

    @BeforeAll
    static void schema() throws Exception {
        for (String path : List.of("db/novelwriterdev-schema.sql", "migrations/20260831_durable_agent_execution.sql")) {
            POSTGRES.copyFileToContainer(MountableFile.forClasspathResource(path), "/tmp/test.sql");
            var result = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(), "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/test.sql");
            assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        }
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432) + "/" + POSTGRES.getDatabaseName()));
        registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        starts = new JooqWorkflowStartRepository(database, new CuidV1Generator(CLOCK), CLOCK, JSON);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 补齐保留全部原始事实且不读取无关Head或修改原bundle() {
        Fixture f = fixture(n -> List.of(new Source(ResourceKind.CHARACTER, n + "-a")));
        String manifest = manifest(f);
        database.dsl().execute("UPDATE public.\"Character\" SET background = '未请求的新内容' WHERE id = ?", f.novel() + "-a");
        var expanded = expand(f, request(f, target("glossary", f.novel() + "-g"), target("world_setting", f.novel())));
        assertThat(expanded.subList(0, f.original().size())).isEqualTo(f.original());
        assertThat(new AgentUpdatesFrozenSources(f.novel(), expanded).require(ResourceKind.CHARACTER, f.novel() + "-a").before())
                .containsEntry("background", "旧人物原文");
        assertThat(item(expanded, "world_setting", f.novel()).exists()).isFalse();
        assertThat(item(expanded, "world_setting", f.novel()).metadata()).containsEntry("absenceSentinel", Map.of("resourceType", "novel", "resourceId", f.novel()));
        assertThat(item(expanded, "run_context", f.novel()).contentText()).isEqualTo("不可截断的原文😀\n".repeat(2000));
        assertThat(manifest(f)).isEqualTo(manifest);
        assertThat(database.dsl().fetchValue("SELECT count(*) FROM public.\"WorkflowEvidenceBundle\" WHERE \"runId\" = ?", f.run())).isEqualTo(1L);
        assertThat(database.dsl().fetchValue("SELECT count(*) FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", f.run())).isEqualTo(1L);
    }

    @Test
    void 请求资源受冻结名录和用途范围约束() {
        Fixture f = fixture(n -> List.of());
        String n = f.novel();
        database.dsl().execute("INSERT INTO public.\"Glossary\" (id,\"novelId\",term,definition,\"updatedAt\") VALUES (?, ?, '新增术语', '不在冻结名录', ?)", n + "-later", n, NOW);
        List<EvidenceExpansionItem> invalid = List.of(
                target("character", n + "-outside"), target("character", "不存在"), target("glossary", n + "-later"),
                target("world_setting", n + "-other"), target("workspace", n), target("outline_tree", n),
                new EvidenceExpansionItem("replace_tree", n + "-parent", "outline_node"),
                new EvidenceExpansionItem("replace_tree", n + "-other", "outline_tree"),
                new EvidenceExpansionItem("delete_impact", n + "-g", "glossary"),
                new EvidenceExpansionItem("unknown", n + "-a", "character"),
                target("character", n + "-a").range(new EvidenceRange(2, 0)));
        for (var item : invalid) assertCode(() -> expand(f, request(f, item)), "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID");
        assertCode(() -> expand(f, request(f, target("character", n + "-a"), target("character", n + "-a"))), "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID");
        assertCode(() -> expand(f, request(f, target("character", n + "-a")).sourceBundleVersion(2)), "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID");
        assertCode(() -> expand(f, request(f, target("character", n + "-a")).reasonCode("other")), "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID");
    }

    @Test
    void 运行和小说归属必须一致且冻结后移出的资料不能读出() {
        Fixture f = fixture(n -> List.of());
        Fixture other = fixture(n -> List.of());
        var request = request(f, target("character", f.novel() + "-a"));
        var adapter = new JooqAgentUpdatesEvidenceExpansion(JSON, READER);
        assertCode(() -> database.transactionResult(tx -> adapter.expand(tx, other.novel(), f.novel(), f.run(), f.bundle(), request)), "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID");
        assertCode(() -> database.transactionResult(tx -> adapter.expand(tx, f.novel(), other.novel(), f.run(), f.bundle(), request)), "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID");
        assertCode(() -> database.transactionResult(tx -> adapter.expand(tx, f.novel(), f.novel(), other.run(), f.bundle(), request)), "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID");
        database.dsl().execute("UPDATE public.\"Character\" SET \"novelId\" = ? WHERE id = ?", f.novel() + "-other", f.novel() + "-a");
        assertCode(() -> expand(f, request), "AGENT_UPDATES_SOURCE_INVALID");
    }

    @Test
    void 相同来源去重且删除依赖合并用途并保留显式空集() {
        Fixture f = fixture(n -> List.of(new Source(ResourceKind.CHARACTER, n + "-b")));
        var result = expand(f, request(f, new EvidenceExpansionItem("delete_impact", f.novel() + "-b", "character")));
        assertThat(result.stream().filter(value -> value.resourceType().equals("character")).count()).isEqualTo(1);
        for (String type : List.of("character_experiences", "character_relations", "character_state_changes")) {
            assertThat(item(result, type, f.novel() + "-b").metadata()).containsEntry("roles", List.of("direct_relation", "delete_impact"));
            assertThat(item(result, type, f.novel() + "-b").contentJson()).isEqualTo(Map.of("items", List.of()));
        }
        assertThat(item(result, "character_owned_items", f.novel() + "-b").contentJson()).isEqualTo(Map.of("items", List.of()));
        assertThat(item(f.original(), "character_experiences", f.novel() + "-b").metadata()).containsEntry("roles", List.of("direct_relation"));
    }

    @Test
    void 同目标的新内容或跨引用别名冲突不得替换旧来源() {
        Fixture direct = fixture(n -> List.of(new Source(ResourceKind.CHARACTER, n + "-a")));
        database.dsl().execute("UPDATE public.\"Character\" SET background = '同时间新内容' WHERE id = ?", direct.novel() + "-a");
        assertCode(() -> expand(direct, request(direct, target("character", direct.novel() + "-a"))), "AGENT_UPDATES_SOURCE_CHANGED");
        Fixture alias = fixture(n -> List.of(new Source(ResourceKind.ITEM, n + "-item")));
        database.dsl().execute("UPDATE public.\"Character\" SET background = '直接引用已有旧快照' WHERE id = ?", alias.novel() + "-a");
        assertCode(() -> expand(alias, request(alias, target("character", alias.novel() + "-a"))), "AGENT_UPDATES_SOURCE_CHANGED");
        Fixture nested = fixture(n -> List.of(new Source(ResourceKind.OUTLINE_NODE, n + "-parent")));
        database.dsl().execute("UPDATE public.\"OutlineNode\" SET content = '嵌套子节点已有旧快照' WHERE id = ?", nested.novel() + "-child");
        assertCode(() -> expand(nested, request(nested, target("outline_node", nested.novel() + "-child"))), "AGENT_UPDATES_SOURCE_CHANGED");
    }

    @Test
    void 只重复已有来源不能再排队且边界按全部新增原始字节计算() {
        Fixture known = fixture(n -> List.of(new Source(ResourceKind.GLOSSARY, n + "-g")));
        assertCode(() -> expand(known, request(known, target("glossary", known.novel() + "-g"))), "AGENT_UPDATES_EVIDENCE_NO_PROGRESS");
        Fixture f = fixture(n -> List.of());
        var request = request(f, target("character", f.novel() + "-a"));
        var full = expand(f, request);
        int delta = Math.toIntExact(bytes(full) - bytes(f.original()));
        assertThat(delta).isGreaterThan(0);
        assertCode(() -> expand(f, request.maxAdditionalBytes(delta - 1)), "AGENT_UPDATES_EVIDENCE_BUDGET_EXCEEDED");
        assertThat(expand(f, request.maxAdditionalBytes(delta))).isEqualTo(full);
        Fixture absent = fixture(n -> List.of());
        assertThat(item(expand(absent, request(absent, target("story_background", absent.novel())).maxAdditionalBytes(1)), "story_background", absent.novel()).exists()).isFalse();
    }

    @Test
    void 整树只冻结已知本小说的全部节点和显式空成员集() {
        Fixture f = fixture(n -> List.of(new Source(ResourceKind.OUTLINE_NODE, n + "-parent")));
        var full = expand(f, request(f, new EvidenceExpansionItem("replace_tree", f.novel(), "outline_tree")));
        assertThat(full.stream().filter(value -> value.resourceType().equals("outline_node")).count()).isEqualTo(2);
        assertThat(new AgentUpdatesFrozenSources(f.novel(), full).requireCollection("outline_tree_membership", f.novel()))
                .containsExactly(Map.of("id", f.novel() + "-child"), Map.of("id", f.novel() + "-parent"));
        Fixture empty = fixture(n -> {
            database.dsl().execute("DELETE FROM public.\"OutlineNode\" WHERE \"novelId\" = ?", n);
            return List.of();
        });
        assertThat(item(expand(empty, request(empty, new EvidenceExpansionItem("replace_tree", empty.novel(), "outline_tree"))), "outline_tree_membership", empty.novel()).contentJson())
                .isEqualTo(Map.of("items", List.of()));
        database.dsl().execute("INSERT INTO public.\"OutlineNode\" (id,\"novelId\",kind,title,\"order\",\"updatedAt\") VALUES (?, ?, 'stage', '名录外节点', 3, ?)", f.novel() + "-late", f.novel(), NOW);
        assertCode(() -> expand(f, request(f, new EvidenceExpansionItem("replace_tree", f.novel(), "outline_tree"))), "AGENT_UPDATES_SOURCE_CHANGED");
    }

    @Test
    void 原bundle任何完整性漂移都不能用当前资料补救() {
        Fixture content = fixture(n -> List.of());
        assertCode(() -> database.transactionResult(tx -> {
            // 仅在隔离测试事务内模拟存储损坏；异常回滚同时恢复原数据和本地会话设置。
            tx.execute("SET LOCAL session_replication_role = replica");
            tx.execute("UPDATE public.\"WorkflowEvidenceItem\" SET \"contentText\" = '篡改' WHERE \"bundleId\" = ? AND \"resourceType\" = 'run_context'", content.bundle());
            return new ReviewConfiguration().structuredCandidatePreparation(JSON).expand(tx,
                    content.novel(), content.novel(), content.run(), content.bundle(),
                    request(content, target("glossary", content.novel() + "-g")));
        }), "ARTIFACT_REVISION_INTEGRITY_ERROR");
        Fixture manifest = fixture(n -> List.of());
        assertCode(() -> database.transactionResult(tx -> {
            tx.execute("SET LOCAL session_replication_role = replica");
            tx.execute("UPDATE public.\"WorkflowEvidenceBundle\" SET \"manifestJson\" = '{}' WHERE id = ?", manifest.bundle());
            return new ReviewConfiguration().structuredCandidatePreparation(JSON).expand(tx,
                    manifest.novel(), manifest.novel(), manifest.run(), manifest.bundle(),
                    request(manifest, target("glossary", manifest.novel() + "-g")));
        }), "ARTIFACT_REVISION_INTEGRITY_ERROR");
    }

    @Test
    void 临时读取故障不能伪装成不可变来源损坏() throws Exception {
        var failure = new java.sql.SQLTransientConnectionException("隔离测试注入的连接故障", "08006");
        try (var connection = new org.jooq.tools.jdbc.MockConnection(context -> { throw failure; })) {
            var tx = org.jooq.impl.DSL.using(connection, org.jooq.SQLDialect.POSTGRES);
            assertThatThrownBy(() -> DurableAgentUpdatesReviewEvidence.readPlans(tx, JSON, "test-run", "test-bundle"))
                    .isInstanceOf(org.jooq.exception.DataAccessException.class)
                    .hasCause(failure);
        }
    }

    @Test
    void 既有小说与advisory锁保持到调用方事务结束() throws Exception {
        Fixture f = fixture(n -> List.of());
        long key = ByteBuffer.wrap(MessageDigest.getInstance("SHA-256").digest(f.novel().getBytes(StandardCharsets.UTF_8))).getLong();
        var adapter = new JooqAgentUpdatesEvidenceExpansion(JSON, READER);
        database.transactionResult(tx -> {
            adapter.expand(tx, f.novel(), f.novel(), f.run(), f.bundle(), request(f, target("world_setting", f.novel())));
            try (var independent = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                    + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432) + "/" + POSTGRES.getDatabaseName()))) {
                assertThat(independent.dsl().fetchValue("SELECT pg_try_advisory_xact_lock(?)", key)).isEqualTo(false);
                assertThat(independent.dsl().fetch("SELECT id FROM public.\"Novel\" WHERE id = ? FOR UPDATE SKIP LOCKED", f.novel())).isEmpty();
            }
            return null;
        });
        assertThat(database.dsl().fetchValue("SELECT pg_try_advisory_xact_lock(?)", key)).isEqualTo(true);
    }

    private static Fixture fixture(Function<String, List<Source>> requested) {
        String n = "expand-" + UUID.randomUUID();
        database.dsl().execute("INSERT INTO public.\"User\" (id,username,\"passwordHash\",\"updatedAt\") VALUES (?, ?, 'test', ?)", n, n, NOW);
        for (String novel : List.of(n, n + "-other")) database.dsl().execute("INSERT INTO public.\"Novel\" (id,name,\"userId\",\"updatedAt\") VALUES (?, '资料补齐测试', ?, ?)", novel, n, NOW);
        for (String suffix : List.of("a", "b")) database.dsl().execute("INSERT INTO public.\"Character\" (id,\"novelId\",name,background,\"updatedAt\") VALUES (?, ?, ?, '旧人物原文', ?)", n + "-" + suffix, n, suffix, NOW);
        database.dsl().execute("INSERT INTO public.\"Character\" (id,\"novelId\",name,\"updatedAt\") VALUES (?, ?, '其他小说人物', ?)", n + "-outside", n + "-other", NOW);
        database.dsl().execute("INSERT INTO public.\"Item\" (id,\"novelId\",name,\"ownerId\",\"updatedAt\") VALUES (?, ?, '道具', ?, ?)", n + "-item", n, n + "-a", NOW);
        database.dsl().execute("INSERT INTO public.\"Glossary\" (id,\"novelId\",term,definition,\"updatedAt\") VALUES (?, ?, '术语', '完整定义😀', ?)", n + "-g", n, NOW);
        database.dsl().execute("INSERT INTO public.\"OutlineNode\" (id,\"novelId\",kind,title,\"order\",\"updatedAt\") VALUES (?, ?, 'stage', '阶段', 0, ?)", n + "-parent", n, NOW);
        database.dsl().execute("INSERT INTO public.\"OutlineNode\" (id,\"novelId\",kind,title,\"parentId\",\"order\",\"updatedAt\") VALUES (?, ?, 'plot_unit', '单元', ?, 1, ?)", n + "-child", n, n + "-parent", NOW);
        List<Source> sources = requested.apply(n);
        List<WorkflowEvidenceItemPlan> items = database.transactionResult(tx -> {
            List<WorkflowEvidenceItemPlan> result = new ArrayList<>();
            result.add(READER.captureIndex(tx, n));
            result.add(new WorkflowEvidenceItemPlan("run_context", n, true, null, null, "不可截断的原文😀\n".repeat(2000), null, null, null, Map.of("purpose", "original")));
            result.addAll(READER.capture(tx, n, sources));
            return List.copyOf(result);
        });
        // 仅保存不可变 bundle 使用现有运行仓储；不派发、不伪造模型终态，也不翻转五项 Catalog。
        var base = registry.resolve("long_serial.plan_chapter", false);
        var old = base.operation();
        var operation = new ExecutionRegistry.Operation("long_serial.revise_lore", "long_serial", "revise_lore", List.of("novel"), List.of("novel"),
                true, false, true, old.lane(), old.evidencePolicy(), old.generatorProfile(), old.generatorStepBudgetProfile(), base.outputSchema().key(),
                old.deterministicValidators(), old.reviewPolicy(), "apply.agent_updates.v1", old.runBudget());
        var resolved = new ExecutionRegistry.ResolvedOperation(operation, base.generatorProfile(), base.generatorStepBudget(), base.outputSchema(), base.reviewers(), base.reviewerOutputSchema());
        var plan = ExecutionPlanSnapshot.freeze("1", registry.manifestFingerprint(), resolved);
        Map<String, Object> input = Map.of("userInstruction", "调整资料");
        var started = starts.start(new WorkflowStartPlan(n, n + "-request", ExecutionCanonicalJson.sha256(n), "long_serial", "revise_lore", "1",
                "chapter_generation", n, null, null, "novel", n, input, old.evidencePolicy(), items, old.runBudget(), plan,
                new WorkflowInitialStepPlan("generation", old.lane(), input, base.generatorProfile(), base.generatorStepBudget(), base.outputSchema())));
        String bundle = database.dsl().fetchOne("SELECT \"currentEvidenceBundleId\" FROM public.\"WorkflowRun\" WHERE id = ?", started.runId()).get(0, String.class);
        return new Fixture(n, started.runId(), bundle, items);
    }

    private static List<WorkflowEvidenceItemPlan> expand(Fixture f, EvidenceExpansionRequest request) {
        return database.transactionResult(tx -> new ReviewConfiguration().structuredCandidatePreparation(JSON)
                .expand(tx, f.novel(), f.novel(), f.run(), f.bundle(), request));
    }

    private static EvidenceExpansionRequest request(Fixture f, EvidenceExpansionItem... items) {
        return new EvidenceExpansionRequest(List.of(items), 320000, "agent_updates_sources_required", f.run() + "-expand", f.bundle(), 1);
    }

    private static EvidenceExpansionItem target(String type, String id) { return new EvidenceExpansionItem("target", id, type); }
    private static WorkflowEvidenceItemPlan item(List<WorkflowEvidenceItemPlan> items, String type, String id) {
        return items.stream().filter(item -> type.equals(item.resourceType()) && id.equals(item.resourceId())).findFirst().orElseThrow();
    }
    private static void assertCode(Runnable runnable, String code) {
        assertThatThrownBy(runnable::run).isInstanceOfSatisfying(ApiException.class, error -> assertThat(error.code()).isEqualTo(code));
    }
    private static String manifest(Fixture f) { return database.dsl().fetchOne("SELECT \"manifestJson\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ?", f.bundle()).get(0, String.class); }
    private static long bytes(List<WorkflowEvidenceItemPlan> items) {
        return items.stream().filter(WorkflowEvidenceItemPlan::exists).mapToLong(item -> item.contentText() == null
                ? ExecutionCanonicalJson.bytes(item.contentJson()).length : item.contentText().getBytes(StandardCharsets.UTF_8).length).sum();
    }
    private record Fixture(String novel, String run, String bundle, List<WorkflowEvidenceItemPlan> original) {}
}
