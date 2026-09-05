package cn.inkforge.core.quality.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.tables.records.ChapterqualitycheckRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowQualityCompletion;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 检查项只是既有质量业务投影；运行、取消、计费和终态仍由通用 Workflow 内核持有。 */
final class JooqWorkflowQualityCompletion implements WorkflowQualityCompletion {
    static final String SOURCE_TYPE = "quality_check_v2";
    private static final Set<String> CONTEXT_FIELDS = Set.of("checkId", "novelId", "chapterId",
            "chapterContent", "chapterContentSha256", "sourceUpdatedAt", "message", "sourceTaskId");
    private static final List<String> SCORE_FIELDS = List.of("characterConsistency", "worldRuleConsistency",
            "timelineConsistency", "causalityConsistency", "foreshadowingConsistency");
    private final CoreDatabase database;
    private final Clock clock;
    private final ObjectMapper json;
    private String scanAfter;

    JooqWorkflowQualityCompletion(CoreDatabase database, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public String complete(DSLContext transaction, String runId, Map<String, Object> report) {
        Map<String, Object> normalized = normalizeReport(report);
        Scope scope = scope(transaction, runId, true);
        transaction.update(WORKFLOWRUN).set(WORKFLOWRUN.OUTPUT, json.writeValueAsString(normalized))
                .where(WORKFLOWRUN.ID.eq(runId)).execute();
        if (!scope.valid()) {
            resetChangedCurrent(scope);
            return "cancelled";
        }
        ChapterqualitycheckRecord check = scope.check();
        clear(check);
        check.setStatus(Qualitycheckstatus.completed);
        check.setResult((String) normalized.get("report"));
        Map<String, Object> scores = object(normalized.get("scores"));
        BigDecimal total = SCORE_FIELDS.stream().map(key -> number(scores.get(key)))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        check.setScoreoverall(total.divide(BigDecimal.valueOf(5)).setScale(0, RoundingMode.HALF_EVEN).intValueExact());
        check.setQualitygate((String) normalized.get("qualityGate"));
        check.setRewritebrief((String) normalized.get("rewriteBrief"));
        touch(check);
        return "completed";
    }

    @Override
    public String finish(DSLContext transaction, String runId, String requestedTerminal) {
        if (!Set.of("failed", "cancelled").contains(requestedTerminal)) {
            throw new IllegalArgumentException("质量终态投影只接受 failed 或 cancelled");
        }
        Scope scope = scope(transaction, runId, true);
        if (!scope.valid()) {
            resetChangedCurrent(scope);
            return "cancelled";
        }
        if ("cancelled".equals(requestedTerminal)) reset(scope.check());
        else {
            scope.check().setStatus(Qualitycheckstatus.failed);
            touch(scope.check());
        }
        return requestedTerminal;
    }

    @Override
    public boolean isInvalidated(DSLContext transaction, String runId) {
        return !scope(transaction, runId, true).valid();
    }

    /** 调用者已锁定 Chapter/Check 的业务互斥检查只做只读判断，不再获取 Run 锁。 */
    boolean isInvalidatedWithoutLocks(DSLContext transaction, String runId) {
        return !scope(transaction, runId, false).valid();
    }

    @Override
    public synchronized List<InvalidatedRun> findInvalidatedRuns(int limit) {
        if (limit < 1 || limit > 256) throw new IllegalArgumentException("质量失效扫描批次必须为 1 到 256");
        List<Record> rows = scan(limit);
        if (rows.isEmpty() && scanAfter != null) {
            scanAfter = null;
            rows = scan(limit);
        }
        List<InvalidatedRun> result = new ArrayList<>();
        for (Record row : rows) {
            String id = row.get("id", String.class);
            // 只轮转扫描游标，不保存任何业务状态；崩溃后从头扫描仍由同一 Run 身份幂等取消。
            scanAfter = id;
            if (isInvalidatedWithoutLocks(database.dsl(), id)) {
                result.add(new InvalidatedRun(row.get("userId", String.class), id));
            }
        }
        return List.copyOf(result);
    }

    private List<Record> scan(int limit) {
        return database.dsl().fetch("""
                SELECT id, "userId" FROM public."WorkflowRun"
                WHERE "engineVersion" = 2 AND workflow = 'quality' AND operation = 'consistency'
                  AND "sourceType" = 'quality_check_v2' AND status IN ('pending','running')
                  AND "cancelRequestedAt" IS NULL AND (?::text IS NULL OR id > ?)
                ORDER BY id LIMIT ?
                """, scanAfter, scanAfter, limit);
    }

    private Scope scope(DSLContext transaction, String runId, boolean lock) {
        Record run = transaction.fetchOne("""
                SELECT id, "userId", "novelId", "chapterId", "sourceId", "targetType", "targetId", input,
                       "currentEvidenceBundleId"
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2 AND workflow = 'quality' AND operation = 'consistency'
                  AND kind = 'quality_check' AND "sourceType" = 'quality_check_v2'
                """, runId);
        if (run == null) throw new IllegalArgumentException("质量 V2 Run 身份不匹配");
        String checkId = run.get("sourceId", String.class);
        String chapterId = run.get("chapterId", String.class);
        String novelId = run.get("novelId", String.class);
        if (!"chapter".equals(run.get("targetType", String.class))
                || !Objects.equals(chapterId, run.get("targetId", String.class))) {
            throw new IllegalArgumentException("质量 V2 Run 的来源与目标不匹配");
        }
        List<Record> items = transaction.fetch("""
                SELECT item."resourceType", item."resourceId", item.exists, item."contentType", item."contentJson",
                       item."contentSha256", item."byteCount", item."rangeJson", bundle."policyVersion"
                FROM public."WorkflowEvidenceItem" AS item
                JOIN public."WorkflowEvidenceBundle" AS bundle ON bundle.id = item."bundleId"
                WHERE bundle.id = ? AND bundle."runId" = ? ORDER BY item.ordinal
                """, run.get("currentEvidenceBundleId", String.class), runId);
        if (items.size() != 1) throw new IllegalArgumentException("质量 V2 Run 必须有唯一完整来源");
        Record item = items.getFirst();
        Map<String, Object> context = read(item.get("contentJson", String.class));
        Map<String, Object> input = read(run.get("input", String.class));
        if (!CONTEXT_FIELDS.equals(context.keySet()) || !input.keySet().equals(Set.of("checkId", "taskId", "message"))
                || !"quality_context".equals(item.get("resourceType", String.class))
                || !Objects.equals(checkId, item.get("resourceId", String.class))
                || !Boolean.TRUE.equals(item.get("exists", Boolean.class))
                || !"json".equals(item.get("contentType", String.class)) || item.get("rangeJson") != null
                || !"evidence.quality.consistency.v1".equals(item.get("policyVersion", String.class))
                || !ExecutionCanonicalJson.sha256(context).equals(item.get("contentSha256", String.class))
                || !Objects.equals(checkId, context.get("checkId")) || !Objects.equals(checkId, input.get("checkId"))
                || !Objects.equals(chapterId, context.get("chapterId")) || !Objects.equals(novelId, context.get("novelId"))
                || !Objects.equals(context.get("sourceTaskId"), input.get("taskId"))
                || !Objects.equals(context.get("message"), input.get("message"))
                || !(context.get("chapterContent") instanceof String content)
                || !sha256(content).equals(context.get("chapterContentSha256"))
                || !(context.get("sourceUpdatedAt") instanceof String version) || version.isEmpty()) {
            throw new IllegalArgumentException("质量 V2 Run 冻结来源无效");
        }
        var chapterQuery = transaction.selectFrom(CHAPTER)
                .where(CHAPTER.ID.eq(chapterId), CHAPTER.NOVELID.eq(novelId));
        var chapter = lock ? chapterQuery.forUpdate().fetchOne() : chapterQuery.fetchOne();
        var checkQuery = transaction.selectFrom(CHAPTERQUALITYCHECK)
                .where(CHAPTERQUALITYCHECK.ID.eq(checkId), CHAPTERQUALITYCHECK.CHAPTERID.eq(chapterId));
        var check = lock ? checkQuery.forUpdate().fetchOne() : checkQuery.fetchOne();
        if (chapter == null || check == null) throw new IllegalArgumentException("质量 V2 Run 业务来源不存在");
        // 不能锁定最新 Run；Chapter 锁已阻止新 start 发布，反锁它会与新运行的回调形成环。
        String latest = transaction.select(WORKFLOWRUN.ID).from(WORKFLOWRUN)
                .where(WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check), WORKFLOWRUN.SOURCEID.eq(checkId),
                        WORKFLOWRUN.SOURCETYPE.in("quality_check", SOURCE_TYPE))
                .orderBy(WORKFLOWRUN.CREATEDAT.desc(), WORKFLOWRUN.ID.desc()).limit(1).fetchOne(WORKFLOWRUN.ID);
        boolean current = runId.equals(latest);
        boolean sameSource = sha256(chapter.getContent()).equals(context.get("chapterContentSha256"));
        return new Scope(check, current, sameSource,
                current && sameSource && check.getStatus() == Qualitycheckstatus.running);
    }

    private void resetChangedCurrent(Scope scope) {
        if (scope.current() && !scope.sameSource() && scope.check().getStatus() == Qualitycheckstatus.running) {
            reset(scope.check());
        }
    }

    private void reset(ChapterqualitycheckRecord check) {
        clear(check);
        check.setStatus(Qualitycheckstatus.pending);
        touch(check);
    }

    private void touch(ChapterqualitycheckRecord check) {
        check.setUpdatedat(DatabaseTimestamp.next(clock, check.getUpdatedat()));
        check.update();
    }

    private static void clear(ChapterqualitycheckRecord check) {
        check.setResult(null); check.setScorehook(null); check.setScoretension(null); check.setScorepayoff(null);
        check.setScorepacing(null); check.setScoreendinghook(null); check.setScorereaderpromise(null);
        check.setScoreoverall(null); check.setQualitygate(null); check.setRewritebrief(null);
    }

    static Map<String, Object> normalizeReport(Map<String, Object> report) {
        fields(report, Set.of("scores", "qualityGate", "issues", "report", "rewriteBrief"),
                Set.of("scores", "qualityGate", "issues", "report"));
        Map<String, Object> scores = object(report.get("scores"));
        fields(scores, Set.copyOf(SCORE_FIELDS), Set.copyOf(SCORE_FIELDS));
        for (String key : SCORE_FIELDS) {
            BigDecimal value = number(scores.get(key));
            if (value.signum() < 0 || value.compareTo(BigDecimal.valueOf(100)) > 0) {
                throw new IllegalArgumentException("一致性分数超出范围");
            }
        }
        if (!Set.of("pass", "revise").contains(report.get("qualityGate"))) {
            throw new IllegalArgumentException("一致性报告结论无效");
        }
        String text = text(report.get("report"), 1, null, false);
        if (text.codePoints().allMatch(code -> Character.isWhitespace(code) || Character.isSpaceChar(code))) {
            throw new IllegalArgumentException("一致性报告不能为空白");
        }
        if (!(report.get("issues") instanceof List<?> issues) || issues.size() > 100) {
            throw new IllegalArgumentException("一致性报告问题列表无效");
        }
        List<Map<String, Object>> normalizedIssues = new ArrayList<>();
        for (Object raw : issues) {
            Map<String, Object> issue = object(raw);
            fields(issue, Set.of("dimension", "severity", "message", "evidence", "suggestion", "location"),
                    Set.of("dimension", "severity", "message", "evidence", "suggestion"));
            if (!Set.of("character", "world_rule", "timeline", "causality", "foreshadowing").contains(issue.get("dimension"))
                    || !Set.of("warning", "error").contains(issue.get("severity"))) {
                throw new IllegalArgumentException("一致性问题维度或程度无效");
            }
            text(issue.get("message"), 1, 500, false);
            text(issue.get("evidence"), 1, 1000, false);
            text(issue.get("suggestion"), 1, 1000, false);
            text(issue.get("location"), 0, 200, true);
            Map<String, Object> normalized = new LinkedHashMap<>(issue);
            normalized.putIfAbsent("location", null);
            normalizedIssues.add(normalized);
        }
        text(report.get("rewriteBrief"), 0, 1000, true);
        Map<String, Object> normalized = new LinkedHashMap<>(report);
        normalized.put("issues", normalizedIssues);
        normalized.putIfAbsent("rewriteBrief", null);
        return normalized;
    }

    private static void fields(Map<String, Object> value, Set<String> allowed, Set<String> required) {
        if (!allowed.containsAll(value.keySet()) || !value.keySet().containsAll(required)) {
            throw new IllegalArgumentException("一致性报告字段不符合共享契约");
        }
    }

    private static String text(Object value, int minimum, Integer maximum, boolean nullable) {
        if (nullable && value == null) return null;
        if (!(value instanceof String text) || text.codePointCount(0, text.length()) < minimum
                || maximum != null && text.codePointCount(0, text.length()) > maximum) {
            throw new IllegalArgumentException("一致性报告文本不符合共享契约");
        }
        return text;
    }

    private static BigDecimal number(Object value) {
        if (!(value instanceof Number)) throw new IllegalArgumentException("一致性分数必须是规范化数值");
        try { return new BigDecimal(value.toString()); }
        catch (NumberFormatException exception) { throw new IllegalArgumentException("一致性分数必须为有限数值"); }
    }

    private Map<String, Object> read(String value) {
        return object(json.readValue(value, new TypeReference<Object>() {}));
    }

    private static Map<String, Object> object(Object value) {
        if (!(value instanceof Map<?, ?> map)) throw new IllegalArgumentException("质量结构必须是对象");
        Map<String, Object> result = new LinkedHashMap<>();
        map.forEach((key, item) -> {
            if (!(key instanceof String name)) throw new IllegalArgumentException("质量对象键必须是字符串");
            result.put(name, item);
        });
        return result;
    }

    private static String sha256(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException exception) { throw new IllegalStateException(exception); }
    }

    private record Scope(ChapterqualitycheckRecord check, boolean current, boolean sameSource, boolean valid) {}
}
