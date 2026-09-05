package cn.inkforge.core.references.infrastructure;

import static cn.inkforge.core.db.generated.Tables.RAGCHUNK;
import static cn.inkforge.core.db.generated.Tables.RAGDOCUMENT;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.patch.PatchField;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import cn.inkforge.core.references.domain.RagJobIdentity;
import cn.inkforge.core.references.domain.RagRules;
import cn.inkforge.core.references.domain.ReferenceCreateResult;
import cn.inkforge.core.references.domain.ReferenceData;
import cn.inkforge.core.references.domain.ReferencePatch;
import cn.inkforge.core.references.application.ReferenceService;
import cn.inkforge.contracts.api.CreateReferenceRequest;
import cn.inkforge.contracts.api.ReindexReferenceRequest;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;

/** 原索引代次与 V2 绑定使用真实 PostgreSQL，不靠内存状态模拟领取和来源失效。 */
@Testcontainers
class JooqDurableRagIndexTest {
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-05T23:00:00Z"), ZoneOffset.UTC);
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-05T23:00:00");
    private static final ObjectMapper JSON = new ObjectMapper();
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("isolated-test-only");
    private static CoreDatabase database;
    private static CuidV1Generator ids;
    private static ExecutionRegistry registry;
    private static JooqWorkflowRagIndexCompletion completion;

    @BeforeAll
    static void prepare() throws Exception {
        for (String resource : List.of("db/novelwriterdev-schema.sql", "migrations/20260831_durable_agent_execution.sql")) {
            String path = "/tmp/" + resource.substring(resource.lastIndexOf('/') + 1);
            POSTGRES.copyFileToContainer(MountableFile.forClasspathResource(resource), path);
            var result = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(),
                    "-d", POSTGRES.getDatabaseName(), "-f", path);
            assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        }
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername()
                + ":" + POSTGRES.getPassword() + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName()));
        ids = new CuidV1Generator(CLOCK);
        registry = ExecutionRegistryFixtures.ragOperationEnabled(ExecutionRegistry.Environment.TEST);
        completion = new JooqWorkflowRagIndexCompletion(database, ids, CLOCK, JSON);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 新代次同事务冻结完整来源并保持原幂等且旧队列不领取V2() {
        Fixture f = fixture("rag-v2-create");
        var repo = repository(f, true);
        String content = "\uFEFF甲😀\r\n" + "乙".repeat(18001) + "\n尾";
        var created = create(repo, f, content);
        String runId = runId(created);
        var run = database.dsl().fetchOne("SELECT * FROM public.\"WorkflowRun\" WHERE id = ?", runId);
        assertThat(run.get("sourceType", String.class)).isEqualTo("rag_index_v2");
        assertThat(run.get("sourceId", String.class)).isEqualTo(created.reference().id());
        assertThat(run.get("targetType", String.class)).isEqualTo("reference");
        assertThat(run.get("novelId", String.class)).isEqualTo(f.novelId());
        assertThat(run.get("chapterId")).isNull();
        var input = JSON.readTree(run.get("input", String.class));
        assertThat(input.size()).isEqualTo(3);
        assertThat(input.get("indexGeneration").asText()).isEqualTo("2026-09-05T23:00:00.000Z");
        assertThat(input.get("contentHash").asText()).isEqualTo(RagRules.sha256(content));
        var evidence = JSON.readTree(database.dsl().fetchOne("""
                SELECT item."contentJson" FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId" WHERE bundle."runId" = ?
                """, runId).get("contentJson", String.class));
        assertThat(evidence.size()).isEqualTo(5);
        assertThat(evidence.get("content").asText()).isEqualTo(content);
        assertThat(evidence.get("chunkCount").asInt()).isEqualTo(11);
        assertThat(create(repo, f, content).effective()).isFalse();
        assertThat(countRuns(created.reference().id())).isEqualTo(1);
        assertThat(repo.listPending(100)).noneMatch(value -> value.referenceId().equals(created.reference().id()));
        AtomicInteger legacyCalls = new AtomicInteger();
        var router = new RagIndexSubmissionRouter(repo, () -> (user, novel, reference, hash, generation) -> {
            legacyCalls.incrementAndGet(); return RagDispatchStatus.QUEUED;
        });
        assertThat(router.submit(f.userId(), f.novelId(), created.reference().id(), created.reference().contentHash(), created.indexGeneration()))
                .isEqualTo(RagDispatchStatus.QUEUED);
        assertThat(legacyCalls).hasValue(0);
        var identity = identity(created);
        assertCode(() -> repo.requireIndexContext(f.novelId(), f.userId(), created.reference().id(), identity.taskId(),
                identity.runId(), created.reference().contentHash()), "RAG_INDEX_STALE");
    }

    @Test
    void 旧pending代次不因开启路由被迁移且终态同hash重建才绑定新Run() {
        Fixture f = fixture("rag-v1-preserved");
        var old = repository(f, false);
        var created = create(old, f, "正文");
        var enabled = repository(f, true);
        var pending = enabled.prepareReindex(f.novelId(), f.userId(), created.reference().id(), created.reference().contentHash());
        assertThat(pending.indexGeneration()).isEqualTo(created.indexGeneration());
        assertThat(countRuns(created.reference().id())).isZero();
        var identity = identity(created);
        enabled.replaceIndex(f.novelId(), created.reference().id(), identity.taskId(), identity.runId(),
                created.reference().contentHash(), vectors(1));
        var next = enabled.prepareReindex(f.novelId(), f.userId(), created.reference().id(), created.reference().contentHash());
        assertThat(next.indexGeneration()).isAfter(created.indexGeneration());
        assertThat(countRuns(created.reference().id())).isEqualTo(1);
        assertThat(database.dsl().fetchCount(RAGCHUNK, RAGCHUNK.NOVELID.eq(f.novelId()))).isZero();
        assertThat(enabled.prepareReindex(f.novelId(), f.userId(), created.reference().id(), created.reference().contentHash()))
                .isEqualTo(next);
    }

    @Test
    void 空正文零Run直接ready且超容量只索引失败不丢完整原文() {
        Fixture empty = fixture("rag-empty");
        var emptyRepo = repository(empty, true);
        var blank = create(emptyRepo, empty, "");
        assertThat(blank.reference().ragStatus()).isEqualTo("ready");
        assertThat(countRuns(blank.reference().id())).isZero();
        assertThat(emptyRepo.listPending(100)).noneMatch(value -> value.referenceId().equals(blank.reference().id()));
        Fixture huge = fixture("rag-capacity");
        String content = "😀".repeat(1800 * 64 + 1);
        var value = create(repository(huge, true), huge, content);
        assertThat(value.reference().content()).isEqualTo(content);
        assertThat(value.reference().ragStatus()).isEqualTo("failed");
        assertThat(value.reference().errorMessage()).isEqualTo("索引生成失败");
        assertThat(countRuns(value.reference().id())).isZero();
    }

    @Test
    void 全部批次向量最后一次物化且不反向改Run终态或索引代次() {
        Fixture f = fixture("rag-v2-complete"); var repo = repository(f, true);
        var created = create(repo, f, "甲".repeat(1800 * 10) + "\uFEFF😀\n尾");
        String runId = runId(created);
        assertThat(database.<Boolean>transactionResult(tx -> completion.isCurrent(tx, runId))).isTrue();
        assertThat(database.dsl().fetchCount(RAGCHUNK, RAGCHUNK.NOVELID.eq(f.novelId()))).isZero();
        assertThatThrownBy(() -> database.transactionResult(tx -> completion.complete(tx, runId, vectors(10))))
                .isInstanceOf(ApiException.class);
        assertThat(database.dsl().fetchCount(RAGCHUNK, RAGCHUNK.NOVELID.eq(f.novelId()))).isZero();
        assertThat(database.<String>transactionResult(tx -> completion.complete(tx, runId, vectors(11)))).isEqualTo("completed");
        assertThat(repo.list(f.novelId(), f.userId()).getFirst().ragStatus()).isEqualTo("ready");
        assertThat(database.dsl().select(RAGCHUNK.TEXT).from(RAGCHUNK).where(RAGCHUNK.NOVELID.eq(f.novelId()))
                .orderBy(RAGCHUNK.CHUNKINDEX).fetch(RAGCHUNK.TEXT)).isEqualTo(RagRules.chunks(created.reference().content()));
        assertThat(database.dsl().select(RAGDOCUMENT.UPDATEDAT).from(RAGDOCUMENT).where(RAGDOCUMENT.SOURCEID.eq(created.reference().id()))
                .fetchSingle(RAGDOCUMENT.UPDATEDAT)).isEqualTo(NOW);
        assertThat(database.dsl().fetchOne("SELECT status::text AS status FROM public.\"WorkflowRun\" WHERE id = ?", runId)
                .get("status", String.class)).isEqualTo("pending");
    }

    @Test
    void 标题变化仍可物化当前标题且正文A到B再到A使旧代次失效() {
        Fixture f = fixture("rag-v2-change"); var repo = repository(f, true);
        var created = create(repo, f, "A"); String runId = runId(created);
        var titled = repo.update(f.novelId(), f.userId(), created.reference().id(),
                patch("新标题", null), created.reference().updatedAt(), true);
        assertThat(titled.indexGeneration()).isEqualTo(created.indexGeneration());
        assertThat(database.<Boolean>transactionResult(tx -> completion.isCurrent(tx, runId))).isTrue();
        var b = repo.update(f.novelId(), f.userId(), created.reference().id(), patch(null, "B"), titled.reference().updatedAt(), true);
        var a = repo.update(f.novelId(), f.userId(), created.reference().id(), patch(null, "A"), b.reference().updatedAt(), true);
        assertThat(a.indexGeneration()).isAfter(created.indexGeneration());
        assertThat(database.<Boolean>transactionResult(tx -> completion.isCurrent(tx, runId))).isFalse();
        assertThat(completion.findInvalidatedRuns(100)).anyMatch(value -> value.runId().equals(runId));
        assertThat(database.<String>transactionResult(tx -> completion.complete(tx, runId, vectors(1)))).isEqualTo("cancelled");
        assertThat(repo.list(f.novelId(), f.userId()).getFirst().ragStatus()).isEqualTo("disabled");
        String current = runId(created.reference().id(), a.reference().contentHash(), a.indexGeneration());
        assertThat(database.<String>transactionResult(tx -> completion.complete(tx, current, vectors(1)))).isEqualTo("completed");
        assertThat(repo.search(f.novelId(), f.userId(), vectors(1).getFirst(), 1).getFirst().title()).isEqualTo("新标题");
    }

    @Test
    void 失败只投影当前代次且删除后发现取消不重建索引() {
        Fixture f = fixture("rag-v2-fail"); var repo = repository(f, true);
        var created = create(repo, f, "正文"); String runId = runId(created);
        assertThat(database.<String>transactionResult(tx -> completion.finish(tx, runId, "failed"))).isEqualTo("failed");
        assertThat(repo.list(f.novelId(), f.userId()).getFirst().errorMessage()).isEqualTo("索引生成失败");
        database.dsl().execute("UPDATE public.\"WorkflowRun\" SET status='failed', \"completedAt\"=\"createdAt\" WHERE id=?", runId);
        var next = repo.prepareReindex(f.novelId(), f.userId(), created.reference().id(), created.reference().contentHash());
        String nextRun = runId(created.reference().id(), next.contentHash(), next.indexGeneration());
        repo.delete(f.novelId(), f.userId(), created.reference().id(), created.reference().updatedAt());
        assertThat(database.<Boolean>transactionResult(tx -> completion.isInvalidated(tx, nextRun))).isTrue();
        assertThat(completion.findInvalidatedRuns(100)).anyMatch(value -> value.runId().equals(nextRun));
        assertThat(database.<String>transactionResult(tx -> completion.finish(tx, nextRun, "failed"))).isEqualTo("cancelled");
        assertThat(database.dsl().fetchCount(RAGDOCUMENT, RAGDOCUMENT.SOURCEID.eq(created.reference().id()))).isZero();
    }

    @Test
    void V2登记服务写入前不可用保留CRUD并明确索引失败且绝不回退V1() {
        Fixture f = fixture("rag-local-unavailable");
        var starter = new JooqRagIndexRunStarter(() -> null, registry, settings(f, true));
        var repo = new JooqReferenceRepository(database, ids, CLOCK, true, JSON, () -> starter);
        AtomicInteger legacyCalls = new AtomicInteger();
        var router = new RagIndexSubmissionRouter(repo, () -> (user, novel, reference, hash, generation) -> {
            legacyCalls.incrementAndGet(); return RagDispatchStatus.QUEUED;
        });
        var service = new ReferenceService(repo, router);
        var value = service.create(f.userId(), f.novelId(), new CreateReferenceRequest(
                "rag-unavailable-request-0001", "完整原文", "标题", CreateReferenceRequest.TypeEnum.NOTE));
        assertThat(value.getContent()).isEqualTo("完整原文");
        assertThat(value.getRagStatus().getValue()).isEqualTo("failed");
        assertThat(countRuns(value.getId())).isZero();
        assertCode(() -> service.reindex(f.userId(), f.novelId(), value.getId(), new ReindexReferenceRequest(value.getContentHash())),
                "RAG_INDEX_SUBMIT_FAILED");
        assertThat(repo.list(f.novelId(), f.userId()).getFirst().content()).isEqualTo("完整原文");
        assertThat(legacyCalls).hasValue(0);
    }

    @Test
    void 正文修改与索引完成按User先行锁序收敛且不会留下旧块() throws Exception {
        concurrentCompleteAndEdit(true);
    }

    @Test
    void 部分用量未预锁User时先锁Novel再锁资料避免向量FK与修改成环() throws Exception {
        concurrentCompleteAndEdit(false);
    }

    private void concurrentCompleteAndEdit(boolean prelockUser) throws Exception {
        Fixture f = fixture("rag-race-" + prelockUser); var repo = repository(f, true);
        var created = create(repo, f, "旧正文"); String runId = runId(created);
        var held = new java.util.concurrent.CountDownLatch(1);
        var release = new java.util.concurrent.CountDownLatch(1);
        try (var executor = java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
            var callback = executor.submit(() -> database.transactionResult(tx -> {
                tx.fetchOne("SELECT id FROM public.\"WorkflowRun\" WHERE id=? FOR UPDATE", runId);
                if (prelockUser) tx.fetchOne("SELECT id FROM public.\"User\" WHERE id=? FOR UPDATE", f.userId());
                assertThat(completion.isCurrent(tx, runId)).isTrue();
                held.countDown();
                try { assertThat(release.await(5, java.util.concurrent.TimeUnit.SECONDS)).isTrue(); }
                catch (InterruptedException exception) { Thread.currentThread().interrupt(); throw new IllegalStateException(exception); }
                assertThat(completion.complete(tx, runId, vectors(1))).isEqualTo("completed");
                tx.execute("UPDATE public.\"WorkflowRun\" SET status='completed',\"completedAt\"=\"createdAt\" WHERE id=?", runId);
                return null;
            }));
            assertThat(held.await(5, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
            if (!prelockUser) {
                // 独立连接验证真实 Novel 锁：旧实现仅锁 Reference，会让此 NOWAIT 意外成功。
                var competingNovel = executor.submit(() -> database.transactionResult(tx -> tx.fetchOne(
                        "SELECT id FROM public.\"Novel\" WHERE id=? FOR UPDATE NOWAIT", f.novelId())));
                try {
                    assertThatThrownBy(() -> competingNovel.get(5, java.util.concurrent.TimeUnit.SECONDS))
                            .isInstanceOf(java.util.concurrent.ExecutionException.class)
                            .hasCauseInstanceOf(org.jooq.exception.DataAccessException.class);
                } catch (RuntimeException | Error failure) {
                    release.countDown();
                    throw failure;
                }
            }
            var edit = executor.submit(() -> repo.update(f.novelId(), f.userId(), created.reference().id(),
                    patch(null, "新正文"), created.reference().updatedAt(), true));
            release.countDown();
            callback.get(10, java.util.concurrent.TimeUnit.SECONDS);
            assertThat(edit.get(10, java.util.concurrent.TimeUnit.SECONDS).reference().content()).isEqualTo("新正文");
        } finally { release.countDown(); }
        assertThat(database.dsl().fetchCount(RAGCHUNK, RAGCHUNK.NOVELID.eq(f.novelId()))).isZero();
        assertThat(repo.list(f.novelId(), f.userId()).getFirst().ragStatus()).isEqualTo("disabled");
    }

    private static Fixture fixture(String id) {
        database.dsl().execute("INSERT INTO public.\"User\"(id,username,\"passwordHash\",\"createdAt\",\"updatedAt\") VALUES (?,?,?,?,?)",
                id, id, "隔离测试摘要", NOW, NOW);
        String novel = id + "-novel";
        database.dsl().execute("INSERT INTO public.\"Novel\"(id,name,\"userId\",\"createdAt\",\"updatedAt\") VALUES (?,?,?,?,?)",
                novel, "资料索引测试", id, NOW, NOW);
        return new Fixture(id, novel);
    }

    private static JooqReferenceRepository repository(Fixture f, boolean route) {
        var workflows = new DurableWorkflowService(new JooqWorkflowStartRepository(database, ids, CLOCK, JSON));
        var starter = new JooqRagIndexRunStarter(() -> workflows, registry, settings(f, route));
        return new JooqReferenceRepository(database, ids, CLOCK, true, JSON, () -> starter);
    }

    private static CoreSettings settings(Fixture f, boolean route) {
        return CoreSettings.from(Map.of("RAG_INDEX_ENABLED", "true", "DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true",
                "DURABLE_AGENT_EXECUTION_ROUTE_MODE", route ? "allowlist" : "off",
                "DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", f.userId(), "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", f.novelId()));
    }

    private static ReferenceCreateResult create(JooqReferenceRepository repo, Fixture f, String content) {
        return repo.create(f.novelId(), f.userId(), f.userId() + "-create-request", new ReferenceData("标题", "note", content, null), true);
    }

    private static ReferencePatch patch(String title, String content) {
        return new ReferencePatch(new PatchField<>(title != null, title), new PatchField<>(false, null),
                new PatchField<>(content != null, content), new PatchField<>(false, null));
    }

    private static RagJobIdentity identity(ReferenceCreateResult result) {
        return RagJobIdentity.create(result.reference().id(), result.reference().contentHash(), result.indexGeneration());
    }

    private static String runId(ReferenceCreateResult result) {
        return runId(result.reference().id(), result.reference().contentHash(), result.indexGeneration());
    }

    private static String runId(String reference, String hash, java.time.OffsetDateTime generation) {
        return database.dsl().fetchOne("SELECT id FROM public.\"WorkflowRun\" WHERE \"idempotencyKey\" = ?",
                RagJobIdentity.create(reference, hash, generation).runId()).get("id", String.class);
    }

    private static int countRuns(String reference) {
        return database.dsl().fetchOne("SELECT count(*) AS n FROM public.\"WorkflowRun\" WHERE \"sourceId\"=?", reference).get("n", Integer.class);
    }

    private static List<List<BigDecimal>> vectors(int count) {
        return java.util.stream.IntStream.range(0, count).mapToObj(index -> List.of(BigDecimal.ONE, BigDecimal.ZERO)).toList();
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(ApiException.class, value -> assertThat(value.code()).isEqualTo(code));
    }

    private record Fixture(String userId, String novelId) {}
}
