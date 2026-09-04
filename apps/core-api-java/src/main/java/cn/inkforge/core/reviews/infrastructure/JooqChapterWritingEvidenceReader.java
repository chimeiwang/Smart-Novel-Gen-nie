package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.ChapterPlanEvidenceReader;
import cn.inkforge.core.reviews.application.ChapterWritingEvidenceReader;
import cn.inkforge.core.workflows.domain.DurableSelectionArtifact;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 组合规划证据与正文、相邻章节摘要及作者已选画像，所有来源均在同一事务持锁重建。 */
public final class JooqChapterWritingEvidenceReader implements ChapterWritingEvidenceReader {
    private static final TypeReference<Map<String, Object>> OBJECT = new TypeReference<>() {};
    // 与 WorkspaceChapterReader / TextLength 相同；SQL 只返回邻章字数，不把邻章正文载入上下文。
    private static final String IGNORED_TEXT_CHARACTERS = new String(new int[] {
        0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x0020, 0x0085, 0x00A0,
        0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006,
        0x2007, 0x2008, 0x2009, 0x200A, 0x2028, 0x2029, 0x202F, 0x205F,
        0x3000, 0xFEFF
    }, 0, 26);
    private final ObjectMapper json;
    private final ChapterPlanEvidenceReader planningSources;

    public JooqChapterWritingEvidenceReader(ObjectMapper json) {
        this(json, new JooqChapterPlanEvidenceReader(json));
    }

    public JooqChapterWritingEvidenceReader(ObjectMapper json, ChapterPlanEvidenceReader planningSources) {
        this.json = Objects.requireNonNull(json);
        this.planningSources = Objects.requireNonNull(planningSources);
    }

    @Override
    public Snapshot capture(DSLContext tx, String novelId, String chapterId, String userInstruction) {
        Record novelRow = tx.fetchOne("""
                SELECT source."userId" AS owner,
                  jsonb_build_object('id', source.id, 'name', source.name, 'summary', source.summary,
                    'storyProgress', source."storyProgress", 'appliedStyleId', source."appliedStyleId",
                    'updatedAt', source."updatedAt")::text AS snapshot
                FROM public."Novel" source WHERE id = ? FOR UPDATE
                """, novelId);
        if (novelRow == null) throw failure("NOVEL_NOT_FOUND", "小说不存在");
        Map<String, Object> novel = snapshot(novelRow);
        Map<String, Object> chapter = one(tx, """
                SELECT (to_jsonb(source) || jsonb_build_object('wordCount', length(translate(content, ?, ''))))::text AS snapshot
                FROM public."Chapter" source WHERE id = ? AND "novelId" = ? FOR UPDATE
                """, IGNORED_TEXT_CHARACTERS, chapterId, novelId);
        if (chapter == null) throw failure("CHAPTER_NOT_FOUND", "章节不存在或不属于该小说");
        String content = (String) chapter.get("content");
        ChapterPlanEvidenceReader.Snapshot plan = planningSources.capture(
                tx, novelId, chapterId, userInstruction, content);
        Map<String, Object> context = new LinkedHashMap<>(plan.context());
        List<Map<String, Object>> bindings = bindings(plan.context().get("sourceBindings"));
        // 规划旧快照保持不变；写章所有存在来源均提供 SourceBinding 契约要求的版本。
        for (Map<String, Object> binding : bindings) {
            if ("novel".equals(binding.get("resourceType"))) binding.put("updatedAt", novel.get("updatedAt"));
        }
        bind(bindings, "novel_context", novel, "novel", novelId);
        Map<String, Object> contentBinding = bind(bindings, "chapter_content", chapter, "chapter", chapterId);
        contentBinding.put("contentSha256", DurableSelectionArtifact.sha256(content));

        int order = ((Number) chapter.get("order")).intValue();
        Map<String, Object> previous = adjacent(tx, novelId, chapterId, order, true);
        Map<String, Object> next = adjacent(tx, novelId, chapterId, order, false);
        bind(bindings, "previous_chapter", previous, "chapter", chapterId);
        bind(bindings, "next_chapter", next, "chapter", chapterId);
        Map<String, Object> adjacent = new LinkedHashMap<>();
        adjacent.put("previous", previous);
        adjacent.put("next", next);

        String styleId = (String) novel.get("appliedStyleId");
        Map<String, Object> style = null;
        if (styleId != null) {
            style = one(tx, """
                    SELECT jsonb_build_object('id', source.id, 'name', source.name,
                      'sourceType', source."sourceType"::text, 'portraitMarkdown', source."portraitMarkdown",
                      'updatedAt', source."updatedAt")::text AS snapshot
                    FROM public."WritingStyle" source WHERE id = ? AND "userId" = ? FOR UPDATE
                    """, styleId, novelRow.get("owner", String.class));
            if (style == null) throw failure("CHAPTER_WRITING_STYLE_SOURCE_MISMATCH", "已选文风不存在或不属于该作品作者");
        }
        bind(bindings, "writing_style", style, "novel", novelId);
        Map<String, Object> appliedStyle = new LinkedHashMap<>();
        appliedStyle.put("selectedStyleId", styleId);
        appliedStyle.put("available", style != null && style.get("portraitMarkdown") instanceof String portrait && !portrait.isEmpty());
        appliedStyle.put("profile", style);
        context.put("novelContext", novel);
        context.put("currentChapter", chapter);
        context.put("adjacentChapters", adjacent);
        context.put("appliedStyle", appliedStyle);
        context.put("sourceBindings", bindings);
        return new Snapshot(context, plan.chapterUpdatedAt());
    }

    private Map<String, Object> adjacent(DSLContext tx, String novelId, String chapterId, int order, boolean previous) {
        String comparison = previous ? "<" : ">";
        String direction = previous ? "DESC" : "ASC";
        return one(tx, """
                SELECT jsonb_build_object('id', source.id, 'title', source.title, 'order', source."order",
                  'status', source.status::text, 'updatedAt', source."updatedAt",
                  'wordCount', length(translate(source.content, ?, '')))::text AS snapshot
                FROM public."Chapter" source
                WHERE "novelId" = ? AND ("order", id) %s (?, ?)
                ORDER BY "order" %s, id %s LIMIT 1 FOR UPDATE
                """.formatted(comparison, direction, direction), IGNORED_TEXT_CHARACTERS, novelId, order, chapterId);
    }

    private Map<String, Object> one(DSLContext tx, String sql, Object... arguments) {
        Record row = tx.fetchOne(sql, arguments);
        return row == null ? null : snapshot(row);
    }

    private Map<String, Object> snapshot(Record row) {
        Map<String, Object> result = json.readValue(row.get("snapshot", String.class), OBJECT);
        for (String field : List.of("createdAt", "updatedAt", "completedAt")) {
            if (result.get(field) instanceof String timestamp) {
                result.put(field, DatabaseTimestamp.api(LocalDateTime.parse(timestamp)).toString());
            }
        }
        return result;
    }

    private static List<Map<String, Object>> bindings(Object value) {
        if (!(value instanceof List<?> values)) throw new IllegalStateException("规划证据缺少 sourceBindings");
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : values) {
            if (!(item instanceof Map<?, ?> map)) throw new IllegalStateException("规划来源绑定不是对象");
            Map<String, Object> copied = new LinkedHashMap<>();
            map.forEach((key, content) -> copied.put((String) key, content));
            result.add(copied);
        }
        return result;
    }

    private static Map<String, Object> bind(List<Map<String, Object>> bindings, String type,
            Map<String, Object> source, String parentType, String parentId) {
        Map<String, Object> binding = new LinkedHashMap<>();
        binding.put("resourceType", type);
        binding.put("resourceId", source == null ? parentType + ":" + parentId + ":" + type : source.get("id"));
        binding.put("exists", source != null);
        binding.put("updatedAt", source == null ? null : source.get("updatedAt"));
        binding.put("contentSha256", source == null ? null : ExecutionCanonicalJson.sha256(source));
        binding.put("revision", null);
        binding.put("absenceSentinel", source == null ? Map.of("resourceType", parentType, "resourceId", parentId) : null);
        bindings.add(binding);
        return binding;
    }

    private static ApiException failure(String code, String message) { return new ApiException(409, code, message); }
}
