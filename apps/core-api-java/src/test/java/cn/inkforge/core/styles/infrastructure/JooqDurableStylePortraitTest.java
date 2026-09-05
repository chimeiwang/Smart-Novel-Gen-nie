package cn.inkforge.core.styles.infrastructure;

import static cn.inkforge.core.db.generated.Tables.STYLEPORTRAITTASK;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.styles.application.StoredStyleFile;
import cn.inkforge.core.styles.application.StyleFileStorage;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowStylePortraitCompletion;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.web.multipart.MultipartFile;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 真实 PostgreSQL 验证用户级 Run、完整文件冻结和正式文风的单事务物化。 */
@Testcontainers
class JooqDurableStylePortraitTest {
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-05T21:00:00Z"), ZoneOffset.UTC);
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-05T21:00:00");
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("isolated-test-only");
    private static CoreDatabase database;
    private static final ObjectMapper JSON = new ObjectMapper();
    private static CuidV1Generator ids;
    private static JooqStyleRepository repository;
    private static JooqWorkflowStylePortraitCompletion completion;
    private static ExecutionRegistry registry;
    private final Map<String, String> files = new LinkedHashMap<>();

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
        repository = new JooqStyleRepository(database, ids, CLOCK, true, JSON);
        completion = new JooqWorkflowStylePortraitCompletion(database, CLOCK, JSON);
        registry = ExecutionRegistryFixtures.styleOperationEnabled(ExecutionRegistry.Environment.TEST);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 无小说运行只建V2并按参考顺序冻结完整BOM换行正文而不暴露路径() {
        Fixture f = fixture("style-frozen");
        addReference(f, "z", "后.txt", "后文\n", 2);
        addReference(f, "a", "前.txt", "\uFEFF甲😀\r\n乙\n", 4);
        String runId = router(f, "allowlist", true).start(f.userId(), f.styleId(), null).id();
        var run = database.dsl().fetchOne("SELECT * FROM public.\"WorkflowRun\" WHERE id = ?", runId);
        assertThat(run.get("engineVersion", Integer.class)).isEqualTo(2);
        assertThat(run.get("novelId")).isNull();
        assertThat(run.get("chapterId")).isNull();
        assertThat(run.get("sourceType", String.class)).isEqualTo("style_portrait_v2");
        assertThat(run.get("sourceId", String.class)).isEqualTo(f.styleId());
        assertThat(run.get("targetType", String.class)).isEqualTo("style_profile");
        assertThat(run.get("targetId", String.class)).isEqualTo(f.styleId());
        JsonNode input = JSON.readTree(run.get("input", String.class));
        assertThat(input.size()).isEqualTo(2);
        assertThat(input.get("mode").asText()).isEqualTo("full");
        assertThat(input.get("section").isNull()).isTrue();
        JsonNode context = evidence(runId);
        assertThat(context.size()).isEqualTo(6);
        assertThat(context.get("references").get(0).get("filename").asText()).isEqualTo("前.txt");
        assertThat(context.get("references").get(0).get("content").asText()).isEqualTo("\uFEFF甲😀\r\n乙\n");
        assertThat(context.get("references").get(0).size()).isEqualTo(5);
        assertThat(context.get("originalCharCount").asInt()).isEqualTo(6);
        assertThat(context.toString()).doesNotContain("filepath", "/app/uploads");
        assertThat(context.get("sourceTextSha256").asText()).isEqualTo(DurableStylePortraitEvidence.sha256(
                "参考资料：前.txt\n\n\uFEFF甲😀\r\n乙\n\n\n参考资料：后.txt\n\n后文\n"));
        JsonNode step = JSON.readTree(database.dsl().fetchOne(
                "SELECT input FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", runId).get("input", String.class));
        assertThat(step.size()).isEqualTo(1);
        assertThat(step.get("section").asText()).isEqualTo("creativeMethodology");
        assertThat(database.dsl().fetchCount(STYLEPORTRAITTASK, STYLEPORTRAITTASK.STYLEID.eq(f.styleId()))).isZero();
        assertThat(repository.listReconcilable(100, NOW.minusMinutes(10).atOffset(ZoneOffset.UTC))).noneMatch(value -> value.taskId().equals(runId));
        assertThat(repository.list(f.userId()).getFirst().tasks()).extracting(value -> value.id()).containsExactly(runId);
        assertThatThrownBy(() -> database.dsl().execute(
                "UPDATE public.\"WorkflowRun\" SET \"sourceId\" = ? WHERE id = ?", "other-style", runId))
                .isInstanceOf(org.jooq.exception.DataAccessException.class);
    }

    @Test
    void 新旧引擎活动互斥且关闭路由仍读取V2原公开状态() {
        Fixture f = fixture("style-cross"); addReference(f, "a", "参考.txt", "正文", 2);
        String runId = router(f, "allowlist", true).start(f.userId(), f.styleId(), PortraitSection.UNIQUE_MARKERS).id();
        assertThat(repository.getPortraitTask(f.userId(), runId).section()).isEqualTo(PortraitSection.UNIQUE_MARKERS);
        assertCode(() -> router(f, "off", true).start(f.userId(), f.styleId(), null), "PORTRAIT_TASK_ACTIVE");
        for (var state : List.of(List.of("running", "processing"), List.of("completed", "success"))) {
            status(runId, state.getFirst());
            assertThat(repository.getPortraitTask(f.userId(), runId).status()).isEqualTo(state.getLast());
        }
        assertThat(repository.getPortraitTask(f.userId(), runId).errorMessage()).isNull();
        // 每个终态使用独立 Run，不能为测试状态投影反转已完成的执行事实。
        for (String terminal : List.of("failed", "cancelled")) {
            Fixture another = fixture("style-status-" + terminal);
            addReference(another, "a", "参考.txt", "正文", 2);
            String terminalRun = router(another, "allowlist", true).start(another.userId(), another.styleId(), null).id();
            status(terminalRun, terminal);
            assertThat(repository.getPortraitTask(another.userId(), terminalRun).status()).isEqualTo("error");
            assertThat(repository.getPortraitTask(another.userId(), terminalRun).errorMessage()).isEqualTo("画像生成失败");
        }
        var legacy = router(f, "off", true).start(f.userId(), f.styleId(), null);
        assertCode(() -> router(f, "allowlist", true).start(f.userId(), f.styleId(), null), "PORTRAIT_TASK_ACTIVE");
        assertThat(repository.list(f.userId()).getFirst().tasks()).extracting(value -> value.id()).contains(runId, legacy.id());
        assertCode(() -> repository.getPortraitTask("another-user", runId), "PORTRAIT_TASK_NOT_FOUND");
    }

    @Test
    void full必须完整五节才原子物化并保留Python去空白与原计数() {
        Fixture f = fixture("style-full"); addReference(f, "a", "参考.txt", "原文", 2);
        repository.updateSection(f.userId(), f.styleId(), PortraitSection.CREATIVE_METHODOLOGY, "原方法");
        String runId = router(f, "allowlist", true).start(f.userId(), f.styleId(), null).id();
        assertThat(database.<Boolean>transactionResult(tx -> completion.targetExists(tx, runId))).isTrue();
        assertThat(repository.list(f.userId()).getFirst().creativeMethodology()).isEqualTo("原方法");
        assertThatThrownBy(() -> database.transactionResult(tx -> completion.complete(tx, runId, Map.of("creativeMethodology", "只有一节"))))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(repository.list(f.userId()).getFirst().creativeMethodology()).isEqualTo("原方法");
        Map<String, String> sections = new LinkedHashMap<>();
        for (String section : WorkflowStylePortraitCompletion.SECTIONS) sections.put(section, "\u0085 \uFEFF" + section + " \u0085");
        assertThat(database.<String>transactionResult(tx -> completion.complete(tx, runId, sections))).isEqualTo("completed");
        var style = repository.list(f.userId()).getFirst();
        assertThat(style.creativeMethodology()).isEqualTo("\uFEFFcreativeMethodology");
        assertThat(style.styleTraits()).isEqualTo("\uFEFFstyleTraits");
        assertThat(style.portraitMarkdown()).contains("创作方法论\n\uFEFFcreativeMethodology", "风格特质\n\uFEFFstyleTraits");
        assertThat(style.originalCharCount()).isEqualTo(2);
        assertThat(style.usedCharCount()).isEqualTo(2);
        assertThat(style.truncated()).isFalse();
        assertThat(repository.getPortraitTask(f.userId(), runId).status()).isEqualTo("pending");
        var output = JSON.readTree(database.dsl().fetchOne("SELECT output FROM public.\"WorkflowRun\" WHERE id = ?", runId)
                .get("output", String.class));
        assertThat(output.get("creativeMethodology").asText()).isEqualTo("\uFEFFcreativeMethodology");
        assertThat(output.get("originalCharCount").asInt()).isEqualTo(2);
    }

    @Test
    void 单节完成只覆盖目标且参考增删和其他分节人工编辑不失效() {
        Fixture f = fixture("style-single"); addReference(f, "a", "参考.txt", "冻结原文", 4);
        String runId = router(f, "allowlist", true).start(f.userId(), f.styleId(), PortraitSection.UNIQUE_MARKERS).id();
        repository.updateSection(f.userId(), f.styleId(), PortraitSection.CREATIVE_METHODOLOGY, "作者新方法");
        repository.deleteReference(f.userId(), f.styleId(), f.styleId() + "-a");
        files.clear();
        addReference(f, "b", "新参考.txt", "不能用新参考改写冻结来源", 12);
        assertThat(database.<Boolean>transactionResult(tx -> completion.isDeleted(tx, runId))).isFalse();
        assertThat(completion.findDeletedRuns(100)).noneMatch(value -> value.runId().equals(runId));
        assertThat(database.<String>transactionResult(tx -> completion.complete(tx, runId, Map.of("uniqueMarkers", " 新标记 "))))
                .isEqualTo("completed");
        var style = repository.list(f.userId()).getFirst();
        assertThat(style.creativeMethodology()).isEqualTo("作者新方法");
        assertThat(style.uniqueMarkers()).isEqualTo("新标记");
        assertThat(style.originalCharCount()).isEqualTo(4);
        assertThat(style.portraitMarkdown()).isNull();
    }

    @Test
    void 失败只写稳定错误保留正文并可重新发起新任务() {
        Fixture f = fixture("style-failed"); addReference(f, "a", "参考.txt", "正文", 2);
        repository.updateSection(f.userId(), f.styleId(), PortraitSection.STYLE_TRAITS, "旧特质");
        String runId = router(f, "allowlist", true).start(f.userId(), f.styleId(), PortraitSection.STYLE_TRAITS).id();
        database.transactionResult(tx -> { completion.finish(tx, runId, "failed"); return null; });
        assertThat(repository.list(f.userId()).getFirst().styleTraits()).isEqualTo("旧特质");
        assertThat(repository.list(f.userId()).getFirst().errorMessage()).isEqualTo("画像生成失败");
        status(runId, "failed");
        String next = router(f, "allowlist", true).start(f.userId(), f.styleId(), PortraitSection.STYLE_TRAITS).id();
        assertThat(next).isNotEqualTo(runId);
        assertThat(repository.list(f.userId()).getFirst().errorMessage()).isNull();
        assertThat(repository.list(f.userId()).getFirst().styleTraits()).isEqualTo("旧特质");
    }

    @Test
    void 删除来源只发现取消不重建文风且原任务公开查询不可越权曝光() {
        Fixture f = fixture("style-delete"); addReference(f, "a", "参考.txt", "正文", 2);
        String runId = router(f, "allowlist", true).start(f.userId(), f.styleId(), PortraitSection.STYLE_TRAITS).id();
        repository.deleteStyle(f.userId(), f.styleId());
        assertThat(completion.findDeletedRuns(100)).anySatisfy(value -> {
            assertThat(value.runId()).isEqualTo(runId);
            assertThat(value.cancelRequestId()).isEqualTo("style-deleted." + runId);
        });
        assertThat(database.<Boolean>transactionResult(tx -> completion.targetExists(tx, runId))).isFalse();
        assertThat(database.<Boolean>transactionResult(tx -> completion.isDeleted(tx, runId))).isTrue();
        assertThat(database.<String>transactionResult(tx -> completion.complete(tx, runId, Map.of("styleTraits", "迟到结果"))))
                .isEqualTo("cancelled");
        assertThat(database.dsl().fetchCount(WRITINGSTYLE, WRITINGSTYLE.ID.eq(f.styleId()))).isZero();
        assertThat(repository.list(f.userId())).isEmpty();
        assertCode(() -> repository.getPortraitTask(f.userId(), runId), "PORTRAIT_TASK_NOT_FOUND");
        database.dsl().execute("UPDATE public.\"WorkflowRun\" SET \"cancelRequestedAt\" = ?, \"cancelRequestId\" = ? WHERE id = ?",
                NOW, "style-deleted." + runId, runId);
        assertThat(completion.findDeletedRuns(100)).noneMatch(value -> value.runId().equals(runId));
    }

    @Test
    void 无参考或离线时不留下运行且未知用户无法开始画像() {
        Fixture f = fixture("style-rejected");
        assertCode(() -> router(f, "allowlist", true).start(f.userId(), f.styleId(), null), "STYLE_REFERENCE_REQUIRED");
        addReference(f, "a", "参考.txt", "正文", 2);
        assertCode(() -> router(f, "allowlist", false).start(f.userId(), f.styleId(), null), "PORTRAIT_SERVICE_UNAVAILABLE");
        assertCode(() -> router(f, "allowlist", true).start("stranger", f.styleId(), null), "STYLE_NOT_FOUND");
        assertThat(database.dsl().fetchOne("SELECT count(*) AS n FROM public.\"WorkflowRun\" WHERE \"sourceId\" = ?", f.styleId())
                .get("n", Long.class)).isZero();
    }

    private Fixture fixture(String userId) {
        database.dsl().insertInto(USER).set(USER.ID, userId).set(USER.USERNAME, userId).set(USER.PASSWORDHASH, "隔离测试摘要")
                .set(USER.CREATEDAT, NOW).set(USER.UPDATEDAT, NOW).execute();
        return new Fixture(userId, repository.create(userId, "文风画像测试").id());
    }

    private void addReference(Fixture f, String suffix, String filename, String content, int charCount) {
        String referenceId = f.styleId() + "-" + suffix;
        String path = "/app/uploads/styles/" + f.styleId() + "/" + referenceId + "_" + filename;
        files.put(path, content);
        repository.createReference(f.userId(), f.styleId(), referenceId,
                new StoredStyleFile(filename, Path.of("/tmp/unused-style-test"), path, charCount));
    }

    private JooqStylePortraitRunStarter router(Fixture f, String route, boolean ready) {
        var configuration = new LinkedHashMap<String, String>();
        configuration.put("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true");
        configuration.put("DURABLE_AGENT_EXECUTION_ROUTE_MODE", route);
        if ("allowlist".equals(route)) {
            configuration.put("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", f.userId());
            configuration.put("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", "unused-novel-allowlist");
        }
        var workflows = new DurableWorkflowService(new JooqWorkflowStartRepository(database, ids, CLOCK, JSON));
        return new JooqStylePortraitRunStarter(database, repository, new StyleFileStorage() {
            public StoredStyleFile save(String styleId, String referenceId, MultipartFile file) { throw new UnsupportedOperationException(); }
            public String read(String path) { return java.util.Objects.requireNonNull(files.get(path)); }
            public boolean delete(String path) { return files.remove(path) != null; }
        }, () -> (userId, styleId, taskId, runId, section) -> PortraitDispatchStatus.QUEUED,
                () -> workflows, () -> ready, registry, CoreSettings.from(configuration), ids, CLOCK, JSON);
    }

    private static JsonNode evidence(String runId) {
        return JSON.readTree(database.dsl().fetchOne("""
                SELECT item."contentJson" FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId" WHERE bundle."runId" = ?
                """, runId).get("contentJson", String.class));
    }

    private static void status(String runId, String status) {
        LocalDateTime completed = List.of("completed", "failed", "cancelled").contains(status) ? NOW : null;
        if ("cancelled".equals(status)) {
            database.dsl().execute("""
                    UPDATE public."WorkflowRun" SET status = 'cancelled', "completedAt" = ?,
                      "cancelRequestedAt" = ?, "cancelRequestId" = ? WHERE id = ?
                    """, NOW, NOW, "style-test-cancel." + runId, runId);
            return;
        }
        database.dsl().execute("UPDATE public.\"WorkflowRun\" SET status = ?::public.\"WorkflowRunStatus\", \"completedAt\" = ? WHERE id = ?",
                status, completed, runId);
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(ApiException.class, value -> assertThat(value.code()).isEqualTo(code));
    }

    private record Fixture(String userId, String styleId) {}
}
