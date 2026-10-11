package cn.inkforge.core.quality.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.tables.records.ChapterqualitycheckRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
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

/** 仅验证历史质量运行的冻结来源，不回调写结果、不扫描或取消任务。 */
final class HistoricalQualitySourceReader {
    static final String SOURCE_TYPE = "quality_check_v2";
    private static final Set<String> CONTEXT_FIELDS = Set.of("checkId", "novelId", "chapterId",
            "chapterContent", "chapterContentSha256", "sourceUpdatedAt", "message", "sourceTaskId");
    private final ObjectMapper json;

    HistoricalQualitySourceReader(CoreDatabase database, Clock clock, ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    /** 调用者已锁定 Chapter/Check 的业务互斥检查只做只读判断，不再获取 Run 锁。 */
    boolean isInvalidatedWithoutLocks(DSLContext transaction, String runId) {
        return !scope(transaction, runId, false).valid();
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
