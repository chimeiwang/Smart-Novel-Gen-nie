package cn.inkforge.core.quality.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.ConsistencyScores;
import cn.inkforge.contracts.api.QualityRunSuccessRequest;
import cn.inkforge.contracts.api.UpdateQualityCheckRequest;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.quality.application.QualityRunDispatcher;
import cn.inkforge.core.quality.domain.QualityDispatchStatus;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.catalog.ExecutionRegistryFixtures;
import cn.inkforge.core.workflows.infrastructure.JooqWorkflowStartRepository;
import java.time.Clock;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqDurableQualityTest {
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-05T18:00:00Z"), ZoneOffset.UTC);
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-05T18:00:00");
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("novelwriterdev").withUsername("inkforge").withPassword("test-only-password");
    private static CoreDatabase database;
    private static ObjectMapper json;
    private static CuidV1Generator ids;
    private static JooqQualityRepository repository;
    private static JooqWorkflowQualityCompletion completion;
    private static ExecutionRegistry registry;

    @BeforeAll
    static void prepare() throws Exception {
        for (String resource : List.of("db/novelwriterdev-schema.sql", "migrations/20260831_durable_agent_execution.sql")) {
            String path = "/tmp/" + resource.substring(resource.lastIndexOf('/') + 1);
            POSTGRES.copyFileToContainer(MountableFile.forClasspathResource(resource), path);
            var executed = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U",
                    POSTGRES.getUsername(), "-d", POSTGRES.getDatabaseName(), "-f", path);
            assertThat(executed.getExitCode()).as(executed.getStderr()).isZero();
        }
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername()
                + ":" + POSTGRES.getPassword() + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName()));
        json = JsonMapper.builder().addModule(new JsonNullableJackson3Module()).build();
        ids = new CuidV1Generator(CLOCK);
        repository = new JooqQualityRepository(database, ids, CLOCK, json, true);
        completion = new JooqWorkflowQualityCompletion(database, CLOCK, json);
        registry = ExecutionRegistryFixtures.qualityOperationEnabled(ExecutionRegistry.Environment.TEST);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 新运行一次冻结检查项来源并保留章节目标与完整正文() {
        Fixture f = fixture("quality-v2-create", "甲😀乙\n完整正文");
        String runId = router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "first").message("")).getTaskId();
        var run = database.dsl().fetchOne("SELECT * FROM public.\"WorkflowRun\" WHERE id = ?", runId);
        assertThat(run.get("engineVersion", Integer.class)).isEqualTo(2);
        assertThat(run.get("sourceType", String.class)).isEqualTo("quality_check_v2");
        assertThat(run.get("sourceId", String.class)).isEqualTo(f.checkId());
        assertThat(run.get("targetType", String.class)).isEqualTo("chapter");
        assertThat(run.get("targetId", String.class)).isEqualTo(f.chapterId());
        var context = json.readTree(database.dsl().fetchOne("""
                SELECT item."contentJson" FROM public."WorkflowEvidenceItem" item
                JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId"
                WHERE bundle."runId" = ?
                """, runId).get("contentJson", String.class));
        assertThat(context.size()).isEqualTo(8);
        assertThat(context.get("chapterContent").asText()).isEqualTo("甲😀乙\n完整正文");
        assertThat(context.get("sourceTaskId").isNull()).isTrue();
        var step = json.readTree(database.dsl().fetchOne(
                "SELECT input FROM public.\"WorkflowStep\" WHERE \"runId\" = ?", runId).get("input", String.class));
        assertThat(step.get("userInstruction").asText()).isEqualTo("检查本章一致性");
        assertThat(repository.get(f.userId(), f.checkId()).getStatus().getValue()).isEqualTo("running");
        assertThat(repository.listDispatchable(100)).noneMatch(value -> value.runId().equals(runId));
        assertThat(database.dsl().fetchOne("SELECT count(*) AS n FROM public.\"WritingTask\" WHERE \"novelId\" = ?", f.novelId())
                .get("n", Integer.class)).isZero();
        assertThatThrownBy(() -> database.dsl().execute("UPDATE public.\"WorkflowRun\" SET \"sourceId\" = ? WHERE id = ?",
                f.chapterId(), runId)).isInstanceOf(org.jooq.exception.DataAccessException.class);
    }

    @Test
    void 既有V2在路由关闭和Agent离线时仍精确重放且不同请求冲突() {
        Fixture f = fixture("quality-v2-replay", "正文");
        var request = request(f, "first");
        String runId = router(f, "allowlist", true).start(f.userId(), f.checkId(), request).getTaskId();
        assertThat(router(f, "off", false).start(f.userId(), f.checkId(), request).getTaskId()).isEqualTo(runId);
        assertThatThrownBy(() -> router(f, "off", false).start(f.userId(), f.checkId(), request(f, "first").message("不同指令")))
                .isInstanceOfSatisfying(ApiException.class, failure -> assertThat(failure.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED"));
        assertThatThrownBy(() -> router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "second")))
                .isInstanceOfSatisfying(ApiException.class, failure -> assertThat(failure.code()).isEqualTo("QUALITY_RUN_ACTIVE"));
        assertThatThrownBy(() -> router(f, "off", true).start(f.userId(), f.checkId(), request(f, "third")))
                .isInstanceOfSatisfying(ApiException.class, failure -> assertThat(failure.code()).isEqualTo("QUALITY_RUN_ACTIVE"));
    }

    @Test
    void V1活动运行阻止V2且切换后原请求仍重放V1() {
        Fixture f = fixture("quality-v1-replay", "正文");
        var request = request(f, "first");
        String runId = router(f, "off", true).start(f.userId(), f.checkId(), request).getTaskId();
        assertThat(router(f, "allowlist", false).start(f.userId(), f.checkId(), request).getTaskId()).isEqualTo(runId);
        assertThatThrownBy(() -> router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "second")))
                .isInstanceOfSatisfying(ApiException.class, failure -> assertThat(failure.code()).isEqualTo("QUALITY_RUN_ACTIVE"));
    }

    @Test
    void 旧V1迟到回调必须识别较新V2而不能覆盖公开检查项() {
        Fixture f = fixture("quality-cross-late", "正文");
        String old = router(f, "off", true).start(f.userId(), f.checkId(), request(f, "first")).getTaskId();
        repository.failRun(f.userId(), f.checkId(), old, f.novelId());
        String fresh = router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "second")).getTaskId();
        // 与旧仓储的迟到回调用例一致，构造尚未观察到终态的旧 V1 行，证明 latest 必须跨引擎。
        database.dsl().execute("UPDATE public.\"WorkflowRun\" SET status = 'running' WHERE id = ?", old);
        var scores = new ConsistencyScores(BigDecimal.valueOf(81), BigDecimal.valueOf(82),
                BigDecimal.valueOf(83), BigDecimal.valueOf(84), BigDecimal.valueOf(85));
        repository.completeRun(f.userId(), f.checkId(), old, f.novelId(), new QualityRunSuccessRequest(
                List.of(), f.novelId(), QualityRunSuccessRequest.QualityGateEnum.PASS,
                "旧 V1 报告", old, scores, old, f.userId()));
        assertThat(repository.get(f.userId(), f.checkId()).getStatus().getValue()).isEqualTo("running");
        assertThat(repository.get(f.userId(), f.checkId()).getResult()).isNull();
        assertThat(database.<Boolean>transactionResult(tx -> completion.isInvalidated(tx, fresh))).isFalse();
    }

    @Test
    void 不可用Agent不会把检查项置为running() {
        Fixture f = fixture("quality-v2-offline", "正文");
        assertThatThrownBy(() -> router(f, "allowlist", false).start(f.userId(), f.checkId(), request(f, "first")))
                .isInstanceOfSatisfying(ApiException.class, failure -> assertThat(failure.statusCode()).isEqualTo(503));
        assertThat(repository.get(f.userId(), f.checkId()).getStatus().getValue()).isEqualTo("pending");
    }

    @Test
    void revise仍完成并保存完整报告与五维平均分而不代替内核推进Run() {
        Fixture f = fixture("quality-v2-report", "正文");
        String runId = router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "first")).getTaskId();
        Map<String, Object> report = report("完整报告😀\n第二段", "revise");
        assertThat(database.<String>transactionResult(tx -> completion.complete(tx, runId, report))).isEqualTo("completed");
        var check = repository.get(f.userId(), f.checkId());
        assertThat(check.getStatus().getValue()).isEqualTo("completed");
        assertThat(check.getQualityGate().getValue()).isEqualTo("revise");
        assertThat(check.getScoreOverall()).isEqualTo(84);
        assertThat(check.getScoreHook()).isNull();
        assertThat(check.getResult()).isEqualTo("完整报告😀\n第二段");
        var run = database.dsl().select(WORKFLOWRUN.OUTPUT, WORKFLOWRUN.STATUS).from(WORKFLOWRUN)
                .where(WORKFLOWRUN.ID.eq(runId)).fetchSingle();
        assertThat(json.readTree(run.value1()).get("report").asText()).isEqualTo("完整报告😀\n第二段");
        assertThat(run.value2().getLiteral()).isEqualTo("pending");
    }

    @Test
    void 同正文重新送审及正文往返修改都不能被旧回调重新完成() {
        Fixture f = fixture("quality-v2-reset", "甲");
        String old = router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "first")).getTaskId();
        resetCheck(f);
        assertThat(database.<Boolean>transactionResult(tx -> completion.isInvalidated(tx, old))).isTrue();
        assertThat(database.<String>transactionResult(tx -> completion.complete(tx, old, report("旧报告", "pass")))).isEqualTo("cancelled");
        assertThat(repository.get(f.userId(), f.checkId()).getStatus().getValue()).isEqualTo("pending");
        String fresh = router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "second")).getTaskId();
        assertThat(database.<String>transactionResult(tx -> completion.finish(tx, old, "failed"))).isEqualTo("cancelled");
        assertThat(repository.get(f.userId(), f.checkId()).getStatus().getValue()).isEqualTo("running");
        assertThat(database.<Boolean>transactionResult(tx -> completion.isInvalidated(tx, fresh))).isFalse();
        database.dsl().update(CHAPTER).set(CHAPTER.CONTENT, "乙").where(CHAPTER.ID.eq(f.chapterId())).execute();
        resetCheck(f);
        database.dsl().update(CHAPTER).set(CHAPTER.CONTENT, "甲").where(CHAPTER.ID.eq(f.chapterId())).execute();
        assertThat(database.<Boolean>transactionResult(tx -> completion.isInvalidated(tx, fresh))).isTrue();
        boolean found = false;
        for (int attempt = 0; attempt < 20; attempt++) {
            if (completion.findInvalidatedRuns(1).stream().anyMatch(value -> value.runId().equals(fresh))) { found = true; break; }
        }
        assertThat(found).isTrue();
    }

    @Test
    void 有效运行禁止跳过而失效后的原跳过不被取消尾项覆盖() {
        Fixture f = fixture("quality-v2-skip", "正文");
        String runId = router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "first")).getTaskId();
        var current = repository.get(f.userId(), f.checkId());
        assertThatThrownBy(() -> repository.updateStatus(f.userId(), f.checkId(), new UpdateQualityCheckRequest(
                current.getUpdatedAt(), UpdateQualityCheckRequest.StatusEnum.SKIPPED)))
                .isInstanceOfSatisfying(ApiException.class, failure -> assertThat(failure.code()).isEqualTo("QUALITY_RUN_ACTIVE"));
        resetCheck(f);
        var reset = repository.get(f.userId(), f.checkId());
        repository.updateStatus(f.userId(), f.checkId(), new UpdateQualityCheckRequest(
                reset.getUpdatedAt(), UpdateQualityCheckRequest.StatusEnum.SKIPPED));
        assertThat(database.<String>transactionResult(tx -> completion.finish(tx, runId, "cancelled"))).isEqualTo("cancelled");
        assertThat(repository.get(f.userId(), f.checkId()).getStatus().getValue()).isEqualTo("skipped");
    }

    @Test
    void 失败和取消只更新有效检查项且不改Run终态() {
        Fixture failed = fixture("quality-v2-failed", "正文");
        String failedRun = router(failed, "allowlist", true).start(failed.userId(), failed.checkId(), request(failed, "first")).getTaskId();
        assertThat(database.<String>transactionResult(tx -> completion.finish(tx, failedRun, "failed"))).isEqualTo("failed");
        assertThat(repository.get(failed.userId(), failed.checkId()).getStatus().getValue()).isEqualTo("failed");
        Fixture cancelled = fixture("quality-v2-cancelled", "正文");
        String cancelledRun = router(cancelled, "allowlist", true).start(cancelled.userId(), cancelled.checkId(), request(cancelled, "first")).getTaskId();
        assertThat(database.<String>transactionResult(tx -> completion.finish(tx, cancelledRun, "cancelled"))).isEqualTo("cancelled");
        assertThat(repository.get(cancelled.userId(), cancelled.checkId()).getStatus().getValue()).isEqualTo("pending");
    }

    @Test
    void 报告字段和分数必须完整并保留可选空值与Unicode长度() {
        Map<String, Object> good = report("报告", "pass");
        assertThat(JooqWorkflowQualityCompletion.normalizeReport(good)).containsEntry("rewriteBrief", null);
        Map<String, Object> unknown = new LinkedHashMap<>(good); unknown.put("unexpected", true);
        assertThatThrownBy(() -> JooqWorkflowQualityCompletion.normalizeReport(unknown)).isInstanceOf(IllegalArgumentException.class);
        Map<String, Object> blank = new LinkedHashMap<>(good); blank.put("report", "\u3000\n");
        assertThatThrownBy(() -> JooqWorkflowQualityCompletion.normalizeReport(blank)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 原taskId字段接受同归属长短篇V2写作Run且冻结来源身份() {
        for (String workflow : List.of("long_serial", "short_medium")) {
            Fixture f = fixture("quality-source-" + workflow, "正文");
            String source = writingSource(f, workflow);
            String qualityRun = router(f, "allowlist", true).start(f.userId(), f.checkId(),
                    request(f, "first").taskId(source)).getTaskId();
            var context = json.readTree(database.dsl().fetchOne("""
                    SELECT item."contentJson" FROM public."WorkflowEvidenceItem" item
                    JOIN public."WorkflowEvidenceBundle" bundle ON bundle.id = item."bundleId"
                    WHERE bundle."runId" = ?
                    """, qualityRun).get("contentJson", String.class));
            assertThat(context.get("sourceTaskId").asText()).isEqualTo(source);
        }
    }

    @Test
    void V2来源的跨用户小说章节以及质量Run冒充均拒绝且不回退同ID旧Task() {
        Fixture f = fixture("quality-source-invalid", "正文");
        String source = writingSource(f, "long_serial");
        for (List<String> identity : List.of(List.of("另一作者", f.novelId(), f.chapterId()),
                List.of(f.userId(), "另一本小说", f.chapterId()), List.of(f.userId(), f.novelId(), "另一个章节"))) {
            assertThatThrownBy(() -> database.transactionResult(tx -> {
                repository.validateTaskBinding(tx, source, identity.get(0), identity.get(1), identity.get(2));
                return null;
            })).isInstanceOfSatisfying(ApiException.class, failure -> {
                assertThat(failure.statusCode()).isEqualTo(403);
                assertThat(failure.code()).isEqualTo("QUALITY_TASK_MISMATCH");
            });
        }
        String quality = router(f, "allowlist", true).start(f.userId(), f.checkId(), request(f, "first")).getTaskId();
        database.dsl().execute("""
                INSERT INTO public."WritingTask"(id,"novelId","chapterId","targetWordCount","selectedAgents",phase,"createdAt","updatedAt")
                VALUES (?,?,?,4000,'[]','active',?,?)
                """, quality, f.novelId(), f.chapterId(), NOW, NOW);
        assertThatThrownBy(() -> database.transactionResult(tx -> {
            repository.validateTaskBinding(tx, quality, f.userId(), f.novelId(), f.chapterId());
            return null;
        })).isInstanceOfSatisfying(ApiException.class, failure -> assertThat(failure.code()).isEqualTo("QUALITY_TASK_MISMATCH"));
    }

    private static String writingSource(Fixture f, String workflow) {
        boolean shortMedium = "short_medium".equals(workflow);
        String operationName = shortMedium ? "full_check" : "answer_question";
        String key = workflow + "." + operationName;
        var operation = registry.resolve(key, false);
        Map<String, Object> input = shortMedium ? Map.of("segmentIndex", 0, "segmentCount", 1)
                : Map.of("userInstruction", "只作为来源身份的未派发写作请求");
        WorkflowEvidenceItemPlan evidence;
        if (shortMedium) {
            Map<String, Object> context = new LinkedHashMap<>();
            for (String name : List.of("workflow", "operation", "documentType", "chapterId", "baseVersionId",
                    "baseContent", "baseContentHash", "sourceOutlineVersionId", "sourceOutlineContent", "sourceOutlineContentHash",
                    "selectionStart", "selectionEnd", "selectedText", "selectedTextHash", "contextBefore", "contextAfter",
                    "userInstruction", "targetTotalWordCount", "sourceKind", "sourceText")) context.put(name, null);
            context.put("workflow", workflow); context.put("operation", operationName); context.put("documentType", "manuscript");
            context.put("chapterId", f.chapterId()); context.put("baseVersionId", "source-version");
            context.put("baseContent", "正文"); context.put("baseContentHash", JooqQualityRepository.sha256("正文"));
            context.put("userInstruction", "只作为来源身份的未派发写作请求"); context.put("targetTotalWordCount", 6000);
            context.put("sourceKind", "inspiration"); context.put("sourceText", "完整起始素材");
            evidence = new WorkflowEvidenceItemPlan("short_medium_context", f.novelId(), true,
                    null, null, null, context, null, null, Map.of("role", "short_medium_context"));
        } else evidence = new WorkflowEvidenceItemPlan("chapter_content", f.chapterId(), true,
                null, DatabaseTimestamp.api(NOW), "正文", null, null, null, Map.of());
        var plan = new WorkflowStartPlan(f.userId(), f.checkId() + "-writing-source", ExecutionCanonicalJson.sha256(input),
                workflow, operationName, registry.catalogVersion(), shortMedium ? "quality_check" : "chat",
                f.novelId(), f.chapterId(), null, shortMedium ? "short_medium_manuscript" : "chapter", f.chapterId(),
                input, operation.operation().evidencePolicy(), List.of(evidence), operation.operation().runBudget(),
                registry.freezePlan(key, false), new WorkflowInitialStepPlan("generation", operation.operation().lane(), input,
                        operation.generatorProfile(), operation.generatorStepBudget(), operation.outputSchema()));
        return new JooqWorkflowStartRepository(database, ids, CLOCK, json).start(plan).runId();
    }

    private static JooqQualityRunStarter router(Fixture f, String mode, boolean ready) {
        Map<String, String> settings = new LinkedHashMap<>();
        settings.put("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true");
        settings.put("DURABLE_AGENT_EXECUTION_ROUTE_MODE", mode);
        if ("allowlist".equals(mode)) {
            settings.put("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", f.userId());
            settings.put("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", f.novelId());
        }
        var dispatcher = new QualityRunDispatcher(repository, ignored -> QualityDispatchStatus.QUEUED, 20, Duration.ofSeconds(5));
        var workflows = new DurableWorkflowService(new JooqWorkflowStartRepository(database, ids, CLOCK, json));
        return new JooqQualityRunStarter(database, repository, () -> dispatcher, () -> workflows,
                () -> ready, registry, CoreSettings.from(settings), CLOCK, json);
    }

    private static RunQualityCheckRequest request(Fixture fixture, String suffix) {
        return new RunQualityCheckRequest(fixture.checkId() + "-request-" + suffix);
    }

    private static void resetCheck(Fixture f) {
        database.dsl().update(CHAPTERQUALITYCHECK).set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                .setNull(CHAPTERQUALITYCHECK.RESULT).set(CHAPTERQUALITYCHECK.UPDATEDAT, NOW.plusSeconds(1))
                .where(CHAPTERQUALITYCHECK.ID.eq(f.checkId())).execute();
    }

    private static Map<String, Object> report(String text, String gate) {
        return Map.of("scores", Map.of("characterConsistency", 84.5, "worldRuleConsistency", 84.5,
                "timelineConsistency", 84.5, "causalityConsistency", 84.5, "foreshadowingConsistency", 84.5),
                "qualityGate", gate, "issues", List.of(), "report", text);
    }

    private static Fixture fixture(String prefix, String content) {
        Fixture f = new Fixture(prefix + "-user", prefix + "-novel", prefix + "-chapter", prefix + "-check");
        database.dsl().insertInto(USER).set(USER.ID, f.userId()).set(USER.USERNAME, f.userId())
                .set(USER.PASSWORDHASH, "test").set(USER.CREDITBALANCEMICROS, 10_000_000L)
                .set(USER.CREATEDAT, NOW).set(USER.UPDATEDAT, NOW).execute();
        database.dsl().insertInto(NOVEL).set(NOVEL.ID, f.novelId()).set(NOVEL.NAME, prefix).set(NOVEL.USERID, f.userId())
                .set(NOVEL.CREATEDAT, NOW).set(NOVEL.UPDATEDAT, NOW).execute();
        database.dsl().insertInto(CHAPTER).set(CHAPTER.ID, f.chapterId()).set(CHAPTER.NOVELID, f.novelId())
                .set(CHAPTER.TITLE, "第一章").set(CHAPTER.CONTENT, content).set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.review).set(CHAPTER.CREATEDAT, NOW).set(CHAPTER.UPDATEDAT, NOW).execute();
        database.dsl().insertInto(CHAPTERQUALITYCHECK).set(CHAPTERQUALITYCHECK.ID, f.checkId())
                .set(CHAPTERQUALITYCHECK.CHAPTERID, f.chapterId()).set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                .set(CHAPTERQUALITYCHECK.TITLE, "一致性终检").set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                .set(CHAPTERQUALITYCHECK.CREATEDAT, NOW).set(CHAPTERQUALITYCHECK.UPDATEDAT, NOW).execute();
        return f;
    }

    private record Fixture(String userId, String novelId, String chapterId, String checkId) {}
}
