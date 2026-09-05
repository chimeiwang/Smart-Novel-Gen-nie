package cn.inkforge.core.styles.infrastructure;

import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.core.db.generated.tables.records.WritingstyleRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.styles.application.StyleService;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.workflows.application.WorkflowStylePortraitCompletion;
import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 最后一节成功才写入正式文风，原始 Step 结果及执行终态由 Workflow 内核保存。 */
final class JooqWorkflowStylePortraitCompletion implements WorkflowStylePortraitCompletion {
    private final CoreDatabase database;
    private final Clock clock;
    private final ObjectMapper json;

    JooqWorkflowStylePortraitCompletion(CoreDatabase database, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public boolean targetExists(DSLContext transaction, String runId) {
        return lockedStyle(transaction, requireRun(transaction, runId)) != null;
    }

    @Override
    public String complete(DSLContext transaction, String runId, Map<String, String> rawSections) {
        DurableStylePortraitRun run = requireRun(transaction, runId);
        WritingstyleRecord style = lockedStyle(transaction, run);
        if (style == null) return "cancelled";
        List<String> expected = run.section() == null ? SECTIONS : List.of(run.section().value());
        if (!new ArrayList<>(rawSections.keySet()).equals(expected)) {
            throw new IllegalArgumentException("文风画像完成分节顺序与原运行范围不匹配");
        }
        Map<String, Object> context = DurableStylePortraitEvidence.load(transaction, json, run);
        Map<String, Object> output = new LinkedHashMap<>();
        output.put("mode", run.mode());
        if (run.section() != null) output.put("section", run.section().value());
        for (String name : expected) {
            String raw = rawSections.get(name);
            if (raw == null) throw new IllegalArgumentException("文风画像不能缺少分节正文");
            String content = StyleStorage.stripPythonWhitespace(raw);
            if (content.isEmpty()) throw new IllegalArgumentException("文风画像不能保存空白分节");
            JooqStyleRepository.setSection(style, PortraitSection.from(name), content);
            output.put(run.section() == null ? name : "content", content);
        }
        int count = (Integer) context.get("originalCharCount");
        style.setOriginalcharcount(count); style.setUsedcharcount(count); style.setTruncated(false);
        style.setPortraitmarkdown(StyleService.buildPortraitMarkdown(JooqStyleRepository.sections(style)));
        style.setErrormessage(null);
        style.setUpdatedat(DatabaseTimestamp.next(clock, style.getUpdatedat()));
        style.store();
        output.put("originalCharCount", count); output.put("usedCharCount", count); output.put("truncated", false);
        transaction.update(WORKFLOWRUN).set(WORKFLOWRUN.OUTPUT, json.writeValueAsString(output))
                .where(WORKFLOWRUN.ID.eq(runId)).execute();
        return "completed";
    }

    @Override
    public void finish(DSLContext transaction, String runId, String terminal) {
        if (!Set.of("failed", "cancelled").contains(terminal)) throw new IllegalArgumentException("画像错误投影只接受执行失败或取消");
        DurableStylePortraitRun run = requireRun(transaction, runId);
        WritingstyleRecord style = lockedStyle(transaction, run);
        if (style == null) return;
        style.setErrormessage("画像生成失败");
        style.setUpdatedat(DatabaseTimestamp.next(clock, style.getUpdatedat()));
        style.store();
    }

    @Override
    public List<DeletedRun> findDeletedRuns(int limit) {
        if (limit < 1 || limit > 256) throw new IllegalArgumentException("文风删除扫描批次必须为 1 到 256");
        return database.dsl().fetch("""
                SELECT run.id, run."userId" FROM public."WorkflowRun" run
                WHERE run."engineVersion" = 2 AND run.workflow = 'style' AND run.operation = 'portrait'
                  AND run."sourceType" = 'style_portrait_v2' AND run.status IN ('pending','running')
                  AND run."cancelRequestedAt" IS NULL
                  AND NOT EXISTS (SELECT 1 FROM public."WritingStyle" style WHERE style.id = run."sourceId")
                ORDER BY run.id LIMIT ?
                """, limit).map(row -> new DeletedRun(row.get("userId", String.class), row.get("id", String.class)));
    }

    @Override
    public boolean isDeleted(DSLContext transaction, String runId) {
        DurableStylePortraitRun run = requireRun(transaction, runId);
        // 公开 Style ID 不复用；只检查已提交的删除事实，不在取消的计费锁之前取得 Style 锁。
        return transaction.select(WRITINGSTYLE.ID).from(WRITINGSTYLE).where(WRITINGSTYLE.ID.eq(run.styleId())).fetchOne() == null;
    }

    private DurableStylePortraitRun requireRun(DSLContext transaction, String runId) {
        DurableStylePortraitRun run = DurableStylePortraitRun.load(transaction, json, runId);
        if (run == null) throw new IllegalArgumentException("文风画像 V2 Run 不存在");
        return run;
    }

    private static WritingstyleRecord lockedStyle(DSLContext transaction, DurableStylePortraitRun run) {
        WritingstyleRecord style = transaction.selectFrom(WRITINGSTYLE).where(WRITINGSTYLE.ID.eq(run.styleId())).forUpdate().fetchOne();
        if (style != null && !run.userId().equals(style.getUserid())) {
            throw new IllegalArgumentException("文风画像 V2 Run 归属不匹配");
        }
        return style;
    }
}
