package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.ChapterPlanEvidenceReader;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 同一持锁查询用于初始 Evidence 与批准时复验，不读聚合 workspace，也不截断任何被选来源。 */
public final class JooqChapterPlanEvidenceReader implements ChapterPlanEvidenceReader {

    private static final TypeReference<Map<String, Object>> OBJECT = new TypeReference<>() {};
    private final ObjectMapper json;

    public JooqChapterPlanEvidenceReader(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public Snapshot capture(DSLContext tx, String novelId, String chapterId, String userInstruction) {
        return capture(tx, novelId, chapterId, userInstruction, "");
    }

    @Override
    public Snapshot capture(DSLContext tx, String novelId, String chapterId, String userInstruction,
            String additionalRelevanceText) {
        Map<String, Object> novel = one(tx, """
                SELECT jsonb_build_object('id', source.id, 'name', source.name)::text AS snapshot
                FROM public."Novel" AS source WHERE id = ? FOR UPDATE
                """, novelId);
        if (novel == null) throw failure("NOVEL_NOT_FOUND", "小说不存在");
        Map<String, Object> chapter = one(tx, """
                SELECT jsonb_build_object('id', source.id, 'title', source.title, 'order', source."order",
                  'status', source.status::text, 'updatedAt', source."updatedAt")::text AS snapshot
                FROM public."Chapter" AS source WHERE id = ? AND "novelId" = ? FOR UPDATE
                """, chapterId, novelId);
        if (chapter == null) throw failure("CHAPTER_NOT_FOUND", "章节不存在或不属于该小说");
        OffsetDateTime chapterUpdatedAt = updatedAt(chapter);
        List<Map<String, Object>> bindings = new ArrayList<>();
        bind(bindings, "novel", novel, "novel", novelId);
        bind(bindings, "chapter", chapter, "chapter", chapterId);

        Map<String, Object> bible = singleton(tx, "WritingBible", novelId);
        Map<String, Object> outline = singleton(tx, "Outline", novelId);
        Map<String, Object> plot = singleton(tx, "PlotProgress", novelId);
        Map<String, Object> world = singleton(tx, "WorldSetting", novelId);
        Map<String, Object> background = singleton(tx, "StoryBackground", novelId);
        bind(bindings, "writing_bible", bible, "novel", novelId);
        bind(bindings, "outline", outline, "novel", novelId);
        bind(bindings, "plot_progress", plot, "novel", novelId);
        bind(bindings, "world_setting", world, "novel", novelId);
        bind(bindings, "story_background", background, "novel", novelId);

        List<Map<String, Object>> goals = rows(tx, """
                SELECT to_jsonb(source)::text AS snapshot FROM public."ChapterWritingGoal" AS source
                WHERE "chapterId" = ? ORDER BY "updatedAt" DESC, id DESC FOR UPDATE
                """, chapterId);
        for (Map<String, Object> candidate : goals) {
            if (!novelId.equals(candidate.get("novelId"))) {
                throw failure("CHAPTER_GOAL_SOURCE_MISMATCH", "章节目标的小说归属与章节不一致");
            }
        }
        Map<String, Object> goal = goals.isEmpty() ? null : goals.getFirst();
        bind(bindings, "chapter_goal", goal, "chapter", chapterId);
        Map<String, Object> progress = one(tx, """
                SELECT to_jsonb(source)::text AS snapshot FROM public."ChapterProgress" AS source
                WHERE "chapterId" = ? FOR UPDATE
                """, chapterId);
        bind(bindings, "chapter_progress", progress, "chapter", chapterId);
        int chapterOrder = ((Number) chapter.get("order")).intValue();
        Map<String, Object> previousProgress = one(tx, """
                SELECT to_jsonb(source)::text AS snapshot FROM public."ChapterProgress" AS source
                JOIN public."Chapter" AS chapter ON chapter.id = source."chapterId"
                WHERE chapter."novelId" = ? AND chapter."order" < ?
                ORDER BY chapter."order" DESC, chapter.id DESC LIMIT 1 FOR UPDATE OF source, chapter
                """, novelId, chapterOrder);
        bind(bindings, "previous_chapter_progress", previousProgress, "chapter", chapterId);

        List<Map<String, Object>> path = outlinePath(tx, novelId, chapterOrder);
        if (path.isEmpty()) bind(bindings, "chapter_group", null, "chapter", chapterId);
        else for (Map<String, Object> node : path) bind(bindings, "outline_node", node, "novel", novelId);
        Map<String, Object> approved = approvedPlan(tx, chapterId);
        bind(bindings, "approved_beat_plan", approved, "chapter", chapterId);

        // 仅目标、当前大纲路径、当前进展、批准计划与原始指令参与字面相关性选择。
        // 不把全文总纲或完整 workspace 当检索词，从而避免无关章节人物被整体复制进提示。
        String selection = userInstruction + "\n" + json.writeValueAsString(chapter) + "\n"
                + json.writeValueAsString(goal) + "\n" + json.writeValueAsString(path) + "\n"
                + json.writeValueAsString(plot) + "\n" + json.writeValueAsString(progress) + "\n"
                + json.writeValueAsString(previousProgress) + "\n" + json.writeValueAsString(approved);
        if (!Objects.requireNonNull(additionalRelevanceText).isEmpty()) {
            selection += "\n" + additionalRelevanceText;
        }
        Map<String, Object> lore = new LinkedHashMap<>();
        for (String[] kind : List.of(
                new String[] {"Character", "name", "character", "characters"},
                new String[] {"Faction", "name", "faction", "factions"},
                new String[] {"Location", "name", "location", "locations"},
                new String[] {"Item", "name", "item", "items"},
                new String[] {"Glossary", "term", "glossary", "glossary"})) {
            List<Map<String, Object>> selected = related(tx, kind[0], kind[1], novelId, selection);
            lore.put(kind[3], selected);
            bindCollection(bindings, kind[2], selected, chapterId);
            // 已选人物的 factionId、物品 ownerId 等程序持有的引用允许一跳展开，不让模型补 ID。
            selection += "\n" + json.writeValueAsString(selected);
        }
        List<Map<String, Object>> foreshadowing = related(tx, "Foreshadowing", "name", novelId, selection);
        bindCollection(bindings, "foreshadowing", foreshadowing, chapterId);

        Map<String, Object> context = new LinkedHashMap<>();
        context.put("schemaVersion", 1);
        context.put("novelId", novelId);
        context.put("novel", novel);
        context.put("chapter", chapter);
        context.put("chapterGoal", goal);
        context.put("writingBible", bible);
        context.put("outline", outline);
        context.put("outlinePath", path);
        context.put("plotProgress", plot);
        context.put("chapterProgress", progress);
        context.put("previousChapterProgress", previousProgress);
        context.put("worldSetting", world);
        context.put("storyBackground", background);
        context.put("relatedLore", lore);
        context.put("foreshadowing", foreshadowing);
        context.put("approvedBeatPlan", approved);
        context.put("sourceBindings", bindings);
        return new Snapshot(context, chapterUpdatedAt);
    }

    private List<Map<String, Object>> outlinePath(DSLContext tx, String novelId, int order) {
        List<Map<String, Object>> groups = rows(tx, """
                SELECT to_jsonb(source)::text AS snapshot FROM public."OutlineNode" AS source
                WHERE "novelId" = ? AND kind = 'chapter_group'
                  AND "chapterStartOrder" <= ? AND "chapterEndOrder" >= ?
                ORDER BY id FOR UPDATE
                """, novelId, order, order);
        if (groups.size() > 1) throw failure("CHAPTER_GROUP_MAPPING_CONFLICT", "当前章节没有唯一对应的章节组");
        if (groups.isEmpty()) return List.of();
        List<Map<String, Object>> path = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        Map<String, Object> current = groups.getFirst();
        while (current != null) {
            String id = Objects.toString(current.get("id"), "");
            if (!seen.add(id)) throw failure("OUTLINE_PARENT_CYCLE", "章节组父级大纲节点存在循环");
            path.add(current);
            Object parent = current.get("parentId");
            if (parent == null) break;
            current = one(tx, """
                    SELECT to_jsonb(source)::text AS snapshot FROM public."OutlineNode" AS source
                    WHERE id = ? AND "novelId" = ? FOR UPDATE
                    """, parent, novelId);
            if (current == null) throw failure("OUTLINE_PARENT_MISSING", "章节组父级大纲节点不存在或不属于该小说");
        }
        Collections.reverse(path);
        return List.copyOf(path);
    }

    private Map<String, Object> approvedPlan(DSLContext tx, String chapterId) {
        List<Map<String, Object>> plans = rows(tx, """
                SELECT to_jsonb(source)::text AS snapshot FROM public."ChapterBeatPlan" AS source
                WHERE "chapterId" = ? AND status = 'approved' ORDER BY id FOR UPDATE
                """, chapterId);
        if (plans.size() > 1) throw failure("BEAT_PLAN_SOURCE_AMBIGUOUS", "章节存在多个已批准计划，无法确定权威来源");
        if (plans.isEmpty()) return null;
        Map<String, Object> result = plans.getFirst();
        result.put("sceneBeats", rows(tx, """
                SELECT to_jsonb(source)::text AS snapshot FROM public."SceneBeat" AS source
                WHERE "beatPlanId" = ? ORDER BY "order", id FOR UPDATE
                """, result.get("id")));
        return result;
    }

    private Map<String, Object> singleton(DSLContext tx, String table, String novelId) {
        return one(tx, "SELECT to_jsonb(source)::text AS snapshot FROM public.\"" + table
                + "\" AS source WHERE \"novelId\" = ? FOR UPDATE", novelId);
    }

    private List<Map<String, Object>> related(DSLContext tx, String table, String nameField, String novelId, String selection) {
        return rows(tx, "SELECT to_jsonb(source)::text AS snapshot FROM public.\"" + table
                + "\" AS source WHERE \"novelId\" = ? AND (strpos(?, id) > 0 OR (length(\"" + nameField
                + "\") > 0 AND strpos(?, \"" + nameField + "\") > 0)) ORDER BY id FOR UPDATE",
                novelId, selection, selection);
    }

    private List<Map<String, Object>> rows(DSLContext tx, String sql, Object... arguments) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Record record : tx.fetch(sql, arguments)) {
            Map<String, Object> value = json.readValue(record.get("snapshot", String.class), OBJECT);
            for (String field : List.of("createdAt", "updatedAt")) {
                if (value.get(field) instanceof String timestamp) {
                    value.put(field, DatabaseTimestamp.api(LocalDateTime.parse(timestamp)).toString());
                }
            }
            result.add(value);
        }
        return result;
    }

    private Map<String, Object> one(DSLContext tx, String sql, Object... arguments) {
        List<Map<String, Object>> values = rows(tx, sql, arguments);
        if (values.size() > 1) throw failure("CHAPTER_PLAN_SOURCE_AMBIGUOUS", "章节规划来源存在多份权威记录");
        return values.isEmpty() ? null : values.getFirst();
    }

    private static void bindCollection(List<Map<String, Object>> bindings, String type, List<Map<String, Object>> values, String chapterId) {
        if (values.isEmpty()) bind(bindings, "related_" + type, null, "chapter", chapterId);
        else for (Map<String, Object> value : values) bind(bindings, type, value, "chapter", chapterId);
    }

    private static void bind(List<Map<String, Object>> bindings, String type, Map<String, Object> source, String parentType, String parentId) {
        Map<String, Object> binding = new LinkedHashMap<>();
        binding.put("resourceType", type);
        binding.put("resourceId", source == null ? parentType + ":" + parentId + ":" + type : source.get("id"));
        binding.put("exists", source != null);
        binding.put("updatedAt", source == null ? null : source.get("updatedAt"));
        binding.put("contentSha256", source == null ? null : ExecutionCanonicalJson.sha256(source));
        binding.put("revision", null);
        binding.put("absenceSentinel", source == null ? Map.of("resourceType", parentType, "resourceId", parentId) : null);
        bindings.add(binding);
    }

    private static OffsetDateTime updatedAt(Map<String, Object> value) {
        if (!(value.get("updatedAt") instanceof String timestamp)) throw failure("CHAPTER_PLAN_SOURCE_INVALID", "章节来源缺少更新时间");
        return OffsetDateTime.parse(timestamp);
    }

    private static ApiException failure(String code, String message) { return new ApiException(409, code, message); }
}
