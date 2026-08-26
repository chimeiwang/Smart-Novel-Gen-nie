package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;

import cn.inkforge.contracts.api.ChapterScope;
import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.NovelScope;
import cn.inkforge.contracts.api.OutlineNodeScope;
import cn.inkforge.contracts.api.Scope;
import cn.inkforge.contracts.api.SelectionAttachmentMetadata;
import cn.inkforge.contracts.api.SelectionTarget;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.OutlineRecord;
import cn.inkforge.core.db.generated.tables.records.OutlinenodeRecord;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;

/**
 * 校验显式长篇操作身份，并从已锁定权威文本构造不可变 Agent job。
 *
 * <p>操作表同时规定主 Agent、复审者、是否写入和目标域；scope、target 与选区资源必须彼此一致。
 * 组装时冻结所有来源绑定和完整选区来源快照，Agent 后续只能消费 job，不能按当前数据库状态重新解释用户选择。
 */
final class LongSerialRunAssembler {

    private static final Map<String, Definition> DEFINITIONS = Map.of(
            "plan_chapter", new Definition("剧情", List.of("编辑"), true, "chapter"),
            "rewrite_scene", new Definition("写作", List.of("校验", "编辑"), true, "chapter"),
            "rewrite_chapter_selection",
                    new Definition("写作", List.of("校验", "编辑"), true, "chapter"),
            "rewrite_outline_selection",
                    new Definition("剧情", List.of("编辑"), true, "outline"),
            "write_chapter", new Definition("写作", List.of("校验", "编辑"), true, "chapter"),
            "review_chapter", new Definition("编辑", List.of(), false, "chapter"));

    private final ObjectMapper json;
    private final WritingSourceBindingCapture bindings;

    LongSerialRunAssembler(ObjectMapper json, WritingSourceBindingCapture bindings) {
        this.json = Objects.requireNonNull(json);
        this.bindings = Objects.requireNonNull(bindings);
    }

    Normalized normalize(LongSerialStartWritingRunRequest request) {
        Definition definition = requireDefinition(request);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("workflow", "long_serial");
        body.put("novelId", request.getNovelId());
        body.put("chapterId", request.getChapterId());
        body.put("writingSessionId", nullable(request.getWritingSessionId()));
        body.put("operation", request.getOperation().getValue());
        body.put("target", target(request));
        body.put("scope", scope(request.getScope()));
        body.put("selectionTarget", selectionTarget(request.getSelectionTarget()));
        body.put(
                "selectionAttachmentMetadata",
                selectionAttachment(request.getSelectionAttachmentMetadata()));
        body.put("targetWordCount", request.getTargetWordCount());
        body.put("userInstruction", request.getUserInstruction());
        Map<String, Object> resource = Map.of(
                "novelId", request.getNovelId(),
                "chapterId", request.getChapterId());
        String fingerprint = CommandIdempotency.requestFingerprint(
                "start", resource, body, json);
        // 指纹只覆盖规范化请求身份；数据库来源快照稍后在持锁事务中捕获并写入正式命令。
        return new Normalized(
                definition,
                Collections.unmodifiableMap(new LinkedHashMap<>(body)),
                resource,
                fingerprint);
    }

    Assembled assemble(
            DSLContext transaction,
            String userId,
            LongSerialStartWritingRunRequest request,
            Definition definition) {
        List<Map<String, Object>> sourceBindings =
                new ArrayList<>(bindings.capture(transaction, request.getNovelId(), request.getChapterId()));
        Map<String, Object> selectionSnapshot = null;
        Map<String, Object> attachment = null;
        int targetWordCount = request.getTargetWordCount();
        if (request.getSelectionTarget() != null) {
            selectionSnapshot = captureSelection(
                    transaction,
                    request.getNovelId(),
                    request.getChapterId(),
                    request.getOperation().getValue(),
                    request.getSelectionTarget());
            if (request.getSelectionAttachmentMetadata() != null) {
                attachment = validateAttachment(
                        request.getSelectionAttachmentMetadata(),
                        request.getSelectionTarget(),
                        selectionSnapshot);
            }
            targetWordCount = Math.max(
                    1,
                    request.getSelectionTarget().getSelectionEnd()
                            - request.getSelectionTarget().getSelectionStart());
            sourceBindings.add(existingSelectionBinding(request.getSelectionTarget()));
        }
        // job 是提交给 Agent 的唯一输入信封，构造完成后冻结，禁止运行中回读 Head 拼装缺失字段。
        Map<String, Object> job = new LinkedHashMap<>();
        job.put("version", 1);
        job.put("workflow", "long_serial");
        job.put("chapterId", request.getChapterId());
        job.put("writingSessionId", nullable(request.getWritingSessionId()));
        job.put("operation", request.getOperation().getValue());
        job.put("target", target(request));
        job.put("scope", scope(request.getScope()));
        job.put("sourceBindings", List.copyOf(sourceBindings));
        job.put("targetWordCount", targetWordCount);
        job.put("userInstruction", request.getUserInstruction());
        job.put("resume", false);
        job.put("resumeInput", null);
        if (selectionSnapshot != null) {
            job.put("selectionTarget", selectionTarget(request.getSelectionTarget()));
            job.put("selectionSnapshot", selectionSnapshot);
        }
        List<Map<String, Object>> conversation =
                List.of(Map.of("role", "user", "content", request.getUserInstruction()));
        return new Assembled(
                Collections.unmodifiableMap(new LinkedHashMap<>(job)),
                targetWordCount,
                conversation,
                attachment,
                definition.selectedAgents());
    }

    private Definition requireDefinition(LongSerialStartWritingRunRequest request) {
        String operation = request.getOperation().getValue();
        Definition definition = DEFINITIONS.get(operation);
        if (definition == null) throw unsupported();
        boolean identitySupported;
        if ("rewrite_outline_selection".equals(operation)) {
            SelectionTarget selection = request.getSelectionTarget();
            if (selection != null
                    && selection.getResourceType()
                            == SelectionTarget.ResourceTypeEnum.OUTLINE_CONTENT) {
                identitySupported = request.getScope() instanceof NovelScope;
            } else if (selection != null
                    && selection.getResourceType()
                            == SelectionTarget.ResourceTypeEnum.OUTLINE_NODE_CONTENT) {
                identitySupported = request.getScope() instanceof OutlineNodeScope outline
                        && outline.getOutlineNodeId().equals(selection.getResourceId());
            } else {
                identitySupported = false;
            }
        } else {
            identitySupported = request.getScope() instanceof ChapterScope chapter
                    && request.getChapterId().equals(chapter.getChapterId());
        }
        boolean targetSupported = "chapter".equals(request.getTarget().getType())
                && request.getChapterId().equals(request.getTarget().getId());
        if (!identitySupported || !targetSupported) throw unsupported();
        return definition;
    }

    private Map<String, Object> captureSelection(
            DSLContext transaction,
            String novelId,
            String chapterId,
            String operation,
            SelectionTarget target) {
        String resourceType = target.getResourceType().getValue();
        String resourceId = target.getResourceId();
        String content = null;
        java.time.LocalDateTime updatedAt = null;
        String ownerNovelId = null;
        if ("chapter_content".equals(resourceType)) {
            ChapterRecord chapter = transaction.selectFrom(CHAPTER)
                    .where(CHAPTER.ID.eq(resourceId))
                    .forUpdate()
                    .fetchOne();
            if (chapter != null) {
                content = chapter.getContent();
                updatedAt = chapter.getUpdatedat();
                ownerNovelId = chapter.getNovelid();
            }
        } else if ("outline_content".equals(resourceType)) {
            OutlineRecord outline = transaction.selectFrom(OUTLINE)
                    .where(OUTLINE.ID.eq(resourceId))
                    .forUpdate()
                    .fetchOne();
            if (outline != null) {
                content = outline.getContent();
                updatedAt = outline.getUpdatedat();
                ownerNovelId = outline.getNovelid();
            }
        } else {
            OutlinenodeRecord node = transaction.selectFrom(OUTLINENODE)
                    .where(OUTLINENODE.ID.eq(resourceId))
                    .forUpdate()
                    .fetchOne();
            if (node != null) {
                content = node.getContent();
                updatedAt = node.getUpdatedat();
                ownerNovelId = node.getNovelid();
            }
        }
        if (!novelId.equals(ownerNovelId)
                || content == null
                || updatedAt == null
                || ("chapter_content".equals(resourceType) && !chapterId.equals(resourceId))
                || ("rewrite_chapter_selection".equals(operation)
                        && !"chapter_content".equals(resourceType))
                || ("rewrite_outline_selection".equals(operation)
                        && "chapter_content".equals(resourceType))) {
            throw selectionConflict(target);
        }
        OffsetDateTime authoritativeUpdatedAt = DatabaseTimestamp.api(updatedAt);
        String fullHash = sha256(content);
        int start = target.getSelectionStart();
        int end = target.getSelectionEnd();
        int length = content.codePointCount(0, content.length());
        if (start < 0 || end > length || start >= end) throw selectionConflict(target);
        String selected = codePointSlice(content, start, end);
        String selectedHash = sha256(selected);
        // 时间戳、全文哈希、范围和选区哈希四者共同绑定；任一变化都要求用户重新选区。
        if (!authoritativeUpdatedAt.toInstant().equals(target.getBaseUpdatedAt().toInstant())
                || !fullHash.equals(target.getBaseContentHash())
                || !selectedHash.equals(target.getSelectedTextHash())) {
            throw selectionConflict(target);
        }
        int context = 1000;
        // sourceSnapshot 保留完整来源以便确认时重验；前后各 1000 码点只是供模型理解的上下文窗口。
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("resourceType", resourceType);
        source.put("resourceId", resourceId);
        source.put("content", content);
        source.put("updatedAt", utc(authoritativeUpdatedAt));
        source.put("contentSha256", fullHash);
        Map<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put("resourceType", resourceType);
        snapshot.put("resourceId", resourceId);
        snapshot.put("baseUpdatedAt", utc(authoritativeUpdatedAt));
        snapshot.put("baseContentHash", fullHash);
        snapshot.put("selectionStart", start);
        snapshot.put("selectionEnd", end);
        snapshot.put("selectedTextHash", selectedHash);
        snapshot.put("selectedText", selected);
        snapshot.put("contextBefore", codePointSlice(content, Math.max(0, start - context), start));
        snapshot.put("contextAfter", codePointSlice(content, end, Math.min(length, end + context)));
        snapshot.put("sourceSnapshot", source);
        return Collections.unmodifiableMap(snapshot);
    }

    private Map<String, Object> validateAttachment(
            SelectionAttachmentMetadata metadata,
            SelectionTarget target,
            Map<String, Object> snapshot) {
        Map<String, Object> actual = selectionAttachment(metadata);
        Map<String, Object> expected = new LinkedHashMap<>();
        expected.put("resourceType", snapshot.get("resourceType"));
        expected.put("resourceId", snapshot.get("resourceId"));
        expected.put("baseUpdatedAt", snapshot.get("baseUpdatedAt"));
        expected.put("baseContentHash", snapshot.get("baseContentHash"));
        expected.put("selectionStart", snapshot.get("selectionStart"));
        expected.put("selectionEnd", snapshot.get("selectionEnd"));
        expected.put("selectedTextHash", snapshot.get("selectedTextHash"));
        expected.put("selectionPreview", preview((String) snapshot.get("selectedText"), 48));
        for (Map.Entry<String, Object> entry : expected.entrySet()) {
            if (!Objects.equals(entry.getValue(), actual.get(entry.getKey()))) {
                throw selectionConflict(target);
            }
        }
        return actual;
    }

    private static Map<String, Object> existingSelectionBinding(SelectionTarget target) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("resourceType", target.getResourceType().getValue());
        value.put("resourceId", target.getResourceId());
        value.put("exists", true);
        value.put("updatedAt", utc(target.getBaseUpdatedAt()));
        value.put("contentSha256", target.getBaseContentHash());
        value.put("revision", null);
        value.put("absenceSentinel", null);
        return value;
    }

    private static Map<String, Object> target(LongSerialStartWritingRunRequest request) {
        return Map.of("type", request.getTarget().getType(), "id", request.getTarget().getId());
    }

    private static Map<String, Object> scope(Scope value) {
        if (value instanceof ChapterScope chapter) {
            return Map.of("kind", chapter.getKind(), "chapterId", chapter.getChapterId());
        }
        if (value instanceof NovelScope novel) {
            return Map.of("kind", novel.getKind());
        }
        if (value instanceof OutlineNodeScope outline) {
            return Map.of("kind", outline.getKind(), "outlineNodeId", outline.getOutlineNodeId());
        }
        if (value instanceof cn.inkforge.contracts.api.ChapterRangeScope range) {
            return Map.of(
                    "kind", range.getKind(),
                    "chapterStartOrder", range.getChapterStartOrder(),
                    "chapterEndOrder", range.getChapterEndOrder());
        }
        throw unsupported();
    }

    private static Map<String, Object> selectionTarget(SelectionTarget value) {
        if (value == null) return null;
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("resourceType", value.getResourceType().getValue());
        result.put("resourceId", value.getResourceId());
        result.put("baseUpdatedAt", utc(value.getBaseUpdatedAt()));
        result.put("baseContentHash", value.getBaseContentHash());
        result.put("selectionStart", value.getSelectionStart());
        result.put("selectionEnd", value.getSelectionEnd());
        result.put("selectedTextHash", value.getSelectedTextHash());
        return result;
    }

    private static Map<String, Object> selectionAttachment(SelectionAttachmentMetadata value) {
        if (value == null) return null;
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("resourceType", value.getResourceType().getValue());
        result.put("resourceId", value.getResourceId());
        result.put("sourceLabel", value.getSourceLabel());
        result.put("baseUpdatedAt", utc(value.getBaseUpdatedAt()));
        result.put("baseContentHash", value.getBaseContentHash());
        result.put("selectionStart", value.getSelectionStart());
        result.put("selectionEnd", value.getSelectionEnd());
        result.put("selectedTextHash", value.getSelectedTextHash());
        result.put("selectionPreview", value.getSelectionPreview());
        return result;
    }

    private static String preview(String text, int limit) {
        int length = text.codePointCount(0, text.length());
        if (length <= limit) return text;
        int head = (limit + 1) / 2;
        int tail = limit / 2;
        return codePointSlice(text, 0, head)
                + "…"
                + codePointSlice(text, length - tail, length);
    }

    private static String codePointSlice(String value, int start, int end) {
        return value.substring(
                value.offsetByCodePoints(0, start), value.offsetByCodePoints(0, end));
    }

    private static String sha256(String value) {
        return CommandIdempotency.sha256(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String utc(OffsetDateTime value) {
        return value.withOffsetSameInstant(ZoneOffset.UTC).toString();
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value != null && value.isPresent() ? value.orElse(null) : null;
    }

    private static ApiException unsupported() {
        return new ApiException(
                409,
                "LONG_SCOPE_NOT_SUPPORTED",
                "当前长篇操作、目标或范围尚不受支持");
    }

    private static ApiException selectionConflict(SelectionTarget target) {
        return new ApiException(
                409,
                "LONG_SELECTION_SOURCE_CONFLICT",
                "选区来源版本、范围或哈希已变化，请重新选择",
                Map.of(
                        "resourceType", target.getResourceType().getValue(),
                        "resourceId", target.getResourceId()));
    }

    record Normalized(
            Definition definition,
            Map<String, Object> body,
            Map<String, Object> resourceIdentity,
            String fingerprint) {}

    record Assembled(
            Map<String, Object> job,
            int targetWordCount,
            List<Map<String, Object>> conversation,
            Map<String, Object> selectionAttachmentMetadata,
            List<String> selectedAgents) {}

    record Definition(
            String principalAgent,
            List<String> reviewers,
            boolean mutating,
            String targetDomain) {
        List<String> selectedAgents() {
            List<String> result = new ArrayList<>();
            result.add(principalAgent);
            result.addAll(reviewers);
            return List.copyOf(result);
        }
    }
}
