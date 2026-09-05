package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.ChapterScope;
import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.NovelScope;
import cn.inkforge.contracts.api.OutlineNodeScope;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.Source;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;

/** 五项结构化资料操作共用的显式范围与最小冻结来源规划。 */
final class AgentUpdatesStartPlanner {

    static final Set<String> OPERATION_KEYS = Set.of(
            "long_serial.create_lore",
            "long_serial.revise_lore",
            "long_serial.create_outline",
            "long_serial.revise_outline",
            "long_serial.manage_foreshadowing");

    private static final Set<String> NOVEL_ONLY = Set.of(
            "create_lore", "revise_lore", "create_outline");

    private final AgentUpdatesEvidenceReader sources;

    AgentUpdatesStartPlanner(AgentUpdatesEvidenceReader sources) {
        this.sources = Objects.requireNonNull(sources);
    }

    Plan prepare(DSLContext transaction, LongSerialStartWritingRunRequest request) {
        Objects.requireNonNull(transaction);
        Objects.requireNonNull(request);
        String operation = request.getOperation().getValue();
        Target target = target(request, operation);
        requireOwnedFocus(transaction, request, target);

        List<Source> requested = new ArrayList<>();
        if (Set.of("create_lore", "revise_lore").contains(operation)) {
            requested.add(new Source(ResourceKind.WORLD_SETTING, request.getNovelId()));
            requested.add(new Source(ResourceKind.STORY_BACKGROUND, request.getNovelId()));
        } else {
            requested.add(new Source(ResourceKind.OUTLINE_CONTENT, request.getNovelId()));
        }
        // 公共 target 继续锚定章节；这里只冻结元数据，不把章节正文带入资料生成。
        requested.add(new Source(ResourceKind.CHAPTER_REFERENCE, request.getChapterId()));
        if (request.getScope() instanceof OutlineNodeScope outline) {
            requested.add(new Source(ResourceKind.OUTLINE_NODE, outline.getOutlineNodeId()));
        }

        List<WorkflowEvidenceItemPlan> evidence = new ArrayList<>();
        evidence.add(sources.captureIndex(transaction, request.getNovelId()));
        evidence.add(runContext(transaction, request));
        evidence.addAll(sources.capture(transaction, request.getNovelId(), requested));
        return new Plan(
                target.type(),
                target.id(),
                Map.of("userInstruction", request.getUserInstruction()),
                List.copyOf(evidence));
    }

    private static void requireOwnedFocus(
            DSLContext transaction, LongSerialStartWritingRunRequest request, Target target) {
        if (!"outline_node".equals(target.type())) return;
        Record node = transaction.fetchOne(
                """
                SELECT id FROM public."OutlineNode"
                WHERE id = ? AND "novelId" = ?
                FOR UPDATE
                """,
                target.id(),
                request.getNovelId());
        if (node == null) throw unsupported();
    }

    private static WorkflowEvidenceItemPlan runContext(
            DSLContext transaction, LongSerialStartWritingRunRequest request) {
        Record novel = transaction.fetchOne(
                """
                SELECT id, name, summary, "storyProgress", "updatedAt"
                FROM public."Novel"
                WHERE id = ?
                FOR UPDATE
                """,
                request.getNovelId());
        if (novel == null) throw unsupported();
        Map<String, Object> novelContext = new LinkedHashMap<>();
        novelContext.put("id", novel.get("id", String.class));
        novelContext.put("name", novel.get("name", String.class));
        novelContext.put("summary", novel.get("summary", String.class));
        novelContext.put("storyProgress", novel.get("storyProgress", String.class));
        Map<String, Object> content = new LinkedHashMap<>();
        content.put("novel", novelContext);
        content.put("scope", scope(request));
        return new WorkflowEvidenceItemPlan(
                "run_context",
                request.getNovelId(),
                true,
                null,
                DatabaseTimestamp.api(novel.get("updatedAt", java.time.LocalDateTime.class)),
                null,
                content,
                null,
                null,
                Map.of("role", "run_context"));
    }

    private static Map<String, Object> scope(LongSerialStartWritingRunRequest request) {
        if (request.getScope() instanceof NovelScope) {
            return Map.of("kind", "novel");
        }
        if (request.getScope() instanceof OutlineNodeScope outline) {
            return Map.of("kind", "outline_node", "outlineNodeId", outline.getOutlineNodeId());
        }
        if (request.getScope() instanceof ChapterScope chapter) {
            return Map.of("kind", "chapter", "chapterId", chapter.getChapterId());
        }
        throw unsupported();
    }

    private static Target target(LongSerialStartWritingRunRequest request, String operation) {
        if (NOVEL_ONLY.contains(operation)) {
            if (!(request.getScope() instanceof NovelScope)) throw unsupported();
            return new Target("novel", request.getNovelId());
        }
        if ("revise_outline".equals(operation)) {
            if (request.getScope() instanceof NovelScope) {
                return new Target("novel", request.getNovelId());
            }
            if (request.getScope() instanceof OutlineNodeScope outline) {
                return new Target("outline_node", outline.getOutlineNodeId());
            }
            throw unsupported();
        }
        if ("manage_foreshadowing".equals(operation)) {
            if (request.getScope() instanceof NovelScope) {
                return new Target("novel", request.getNovelId());
            }
            if (request.getScope() instanceof ChapterScope chapter
                    && request.getChapterId().equals(chapter.getChapterId())) {
                return new Target("chapter", request.getChapterId());
            }
            throw unsupported();
        }
        throw unsupported();
    }

    private static ApiException unsupported() {
        return new ApiException(
                409,
                "LONG_SCOPE_NOT_SUPPORTED",
                "当前长篇操作、目标或范围尚不受支持");
    }

    record Plan(
            String targetType,
            String targetId,
            Map<String, Object> input,
            List<WorkflowEvidenceItemPlan> evidenceItems) {

        Plan {
            targetType = Objects.requireNonNull(targetType);
            targetId = Objects.requireNonNull(targetId);
            input = Map.copyOf(input);
            evidenceItems = List.copyOf(evidenceItems);
        }
    }

    private record Target(String type, String id) {}
}
