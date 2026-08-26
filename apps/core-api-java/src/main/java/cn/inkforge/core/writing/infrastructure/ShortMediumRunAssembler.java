package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;

import cn.inkforge.contracts.api.ShortMediumStartWritingRunRequest;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.OutlineRecord;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record2;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 从锁定的中短篇权威工作稿、版本和起始素材装配 Agent 任务快照。
 *
 * <p>任务只允许基于干净的当前版本启动，并把完整基线内容、哈希、起始素材及可选选区冻结进命令。
 * 中短篇始终绑定唯一全文章节；正文生成还必须固定来源大纲版本，执行期间不再回读当前 Head。
 */
final class ShortMediumRunAssembler {

    private static final String OUTLINE_PREFIX = "short-medium:outline:";
    private static final String MANUSCRIPT_PREFIX = "short-medium:manuscript:";

    private final ObjectMapper json;

    ShortMediumRunAssembler(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    Assembled assemble(
            DSLContext transaction,
            String userId,
            ShortMediumStartWritingRunRequest request) {
        Loaded source = load(transaction, userId, request);
        Version current = source.currentDocument();
        String requestedBase = nullable(request.getBaseVersionId());
        String currentId = current == null ? null : current.id();
        if (!Objects.equals(requestedBase, currentId)) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_BASE_VERSION_CONFLICT",
                    "当前版本已经变化，请重新发起任务",
                    nullableDetail("currentVersionId", currentId));
        }
        String expectedHash = current == null
                ? ShortMediumText.sha256("")
                : current.payload().contentHash();
        // 未提交的自动保存工作稿没有版本身份，不能作为可重建 Agent 任务的隐式输入。
        if (!ShortMediumText.sha256(source.documentContent()).equals(expectedHash)) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_WORK_DRAFT_DIRTY",
                    "工作稿存在未提交修改，请先提交或放弃修改");
        }

        String operation = request.getOperation().getValue();
        String documentType = request.getDocumentType().getValue();
        Map<String, Object> payload = emptyPayload();
        payload.put("workflow", "short_medium");
        payload.put("operation", operation);
        payload.put("documentType", documentType);
        payload.put("chapterId", "manuscript".equals(documentType) ? source.chapterId() : null);
        payload.put("userInstruction", nullable(request.getUserInstruction()));
        payload.put("targetTotalWordCount", source.targetTotalWordCount());
        if (current != null) {
            payload.put("baseVersionId", current.id());
            payload.put("baseContent", current.payload().content());
            payload.put("baseContentHash", current.payload().contentHash());
        }

        switch (operation) {
            case "generate_outline" -> {
                payload.put("sourceKind", source.sourceKind());
                payload.put("sourceText", source.sourceText());
            }
            case "generate_manuscript" -> {
                Version outline = source.currentOutline();
                if (outline == null
                        || !Objects.equals(
                                nullable(request.getSourceOutlineVersionId()), outline.id())) {
                    throw new ApiException(
                            409,
                            "SHORT_MEDIUM_OUTLINE_VERSION_CONFLICT",
                            "来源大纲版本已经变化，请重新发起正文生成");
                }
                requireClean(source.outlineContent(), outline);
                payload.put("sourceOutlineVersionId", outline.id());
                payload.put("sourceOutlineContent", outline.payload().content());
                payload.put("sourceOutlineContentHash", outline.payload().contentHash());
                payload.put("sourceKind", source.sourceKind());
                payload.put("sourceText", source.sourceText());
            }
            case "replace_selection" -> assembleSelection(request, source, current, payload);
            case "full_check" -> assembleCheck(source, current, payload);
            default -> throw new IllegalStateException("未覆盖的中短篇操作");
        }
        String instruction = nullable(request.getUserInstruction());
        String visibleMessage = instruction == null
                ? Map.of(
                                "generate_outline", "生成中短篇大纲",
                                "generate_manuscript", "生成中短篇正文",
                                "replace_selection", "修改中短篇选区",
                                "full_check", "检查中短篇全文")
                        .get(operation)
                : instruction;
        return new Assembled(
                source.chapterId(),
                source.targetTotalWordCount(),
                Collections.unmodifiableMap(new LinkedHashMap<>(payload)),
                visibleMessage,
                Map.of(
                                "generate_outline", "剧情",
                                "generate_manuscript", "写作",
                                "replace_selection", "编辑",
                                "full_check", "校验")
                        .get(operation));
    }

    private Loaded load(
            DSLContext transaction,
            String userId,
            ShortMediumStartWritingRunRequest request) {
        Record2<String, Integer> novel = transaction
                .select(NOVEL.ID, WRITINGBIBLE.TARGETTOTALWORDCOUNT)
                .from(NOVEL)
                .join(WRITINGBIBLE)
                .on(WRITINGBIBLE.NOVELID.eq(NOVEL.ID))
                .where(
                        NOVEL.ID.eq(request.getNovelId()),
                        NOVEL.USERID.eq(userId),
                        WRITINGBIBLE.STORYLENGTHPROFILE.eq(Storylengthprofile.short_medium))
                .forUpdate()
                .of(NOVEL)
                .fetchOne();
        if (novel == null) {
            throw new ApiException(404, "SHORT_MEDIUM_NOVEL_NOT_FOUND", "中短篇作品不存在");
        }
        Integer target = novel.value2();
        if (target == null || target < 6_000 || target > 80_000) {
            throw new ApiException(409, "SHORT_MEDIUM_TARGET_INVALID", "中短篇目标字数无效");
        }
        List<ChapterRecord> chapters = transaction.selectFrom(CHAPTER)
                .where(CHAPTER.NOVELID.eq(request.getNovelId()))
                .orderBy(CHAPTER.ORDER.asc(), CHAPTER.ID.asc())
                .forUpdate()
                .fetch();
        String requestedChapter = nullable(request.getChapterId());
        if (chapters.size() != 1
                || (requestedChapter != null
                        && !requestedChapter.equals(chapters.getFirst().getId()))) {
            throw new ApiException(
                    409, "SHORT_MEDIUM_CHAPTER_INVALID", "中短篇必须且只能绑定唯一全文章节");
        }
        ChapterRecord chapter = chapters.getFirst();
        OutlineRecord outline = transaction.selectFrom(OUTLINE)
                .where(OUTLINE.NOVELID.eq(request.getNovelId()))
                .forUpdate()
                .fetchOne();
        if (outline == null) {
            throw new ApiException(
                    404, "SHORT_MEDIUM_OUTLINE_NOT_FOUND", "中短篇大纲工作稿不存在");
        }
        ReviewartifactRecord source = transaction.selectFrom(REVIEWARTIFACT)
                .where(
                        REVIEWARTIFACT.NOVELID.eq(request.getNovelId()),
                        REVIEWARTIFACT.ARTIFACTKEY.eq(
                                "short-medium:source:" + request.getNovelId()),
                        REVIEWARTIFACT.STATUS.eq(Reviewartifactstatus.applied))
                .fetchOne();
        if (source == null) {
            throw new ApiException(409, "SHORT_MEDIUM_SOURCE_MISSING", "中短篇起始素材不存在");
        }
        Map<String, Object> sourcePayload = object(source.getPayloadjson());
        Object kind = sourcePayload.get("sourceKind");
        Object text = sourcePayload.get("sourceText");
        if (!(kind instanceof String sourceKind) || !(text instanceof String sourceText)) {
            throw new ApiException(409, "SHORT_MEDIUM_SOURCE_INVALID", "中短篇起始素材格式无效");
        }
        List<Version> outlineVersions = versions(
                transaction, request.getNovelId(), OUTLINE_PREFIX + request.getNovelId());
        List<Version> manuscriptVersions = versions(
                transaction, request.getNovelId(), MANUSCRIPT_PREFIX + chapter.getId());
        Version currentOutline = current(outlineVersions);
        Version currentDocument = request.getDocumentType()
                        == ShortMediumStartWritingRunRequest.DocumentTypeEnum.OUTLINE
                ? currentOutline
                : current(manuscriptVersions);
        Version boundOutline = null;
        if (currentDocument != null
                && "manuscript".equals(currentDocument.payload().documentType())
                && currentDocument.payload().sourceOutlineVersionId() != null) {
            String boundId = currentDocument.payload().sourceOutlineVersionId();
            boundOutline = outlineVersions.stream()
                    .filter(version -> boundId.equals(version.id()))
                    .findFirst()
                    .orElse(null);
        }
        return new Loaded(
                chapter.getId(),
                target,
                sourceKind,
                sourceText,
                request.getDocumentType() == ShortMediumStartWritingRunRequest.DocumentTypeEnum.OUTLINE
                        ? outline.getContent()
                        : chapter.getContent(),
                currentDocument,
                outline.getContent(),
                currentOutline,
                boundOutline);
    }

    private void assembleSelection(
            ShortMediumStartWritingRunRequest request,
            Loaded source,
            Version current,
            Map<String, Object> payload) {
        if (current == null) {
            throw new ApiException(
                    409, "SHORT_MEDIUM_BASE_VERSION_REQUIRED", "选区修改必须基于已确认版本");
        }
        int start = nullable(request.getSelectionStart());
        int end = nullable(request.getSelectionEnd());
        int length = current.payload().content().codePointCount(0, current.payload().content().length());
        if (end > length) {
            throw new ApiException(
                    409, "SHORT_MEDIUM_SELECTION_RANGE_INVALID", "选区码点范围超出基础版本");
        }
        String selected = codePointSlice(current.payload().content(), start, end);
        String hash = ShortMediumText.sha256(selected);
        // 选区坐标按 Unicode code point 解释，并同时绑定所选文本哈希，防止代理对错位文本动刀。
        if (!hash.equals(nullable(request.getSelectedTextHash()))) {
            throw new ApiException(
                    409, "SHORT_MEDIUM_SELECTION_HASH_CONFLICT", "选区内容已经变化，请重新选择");
        }
        payload.put("selectionStart", start);
        payload.put("selectionEnd", end);
        payload.put("selectedText", selected);
        payload.put("selectedTextHash", hash);
        payload.put("contextBefore", codePointSlice(current.payload().content(), 0, start));
        payload.put("contextAfter", codePointSlice(current.payload().content(), end, length));
        if (request.getDocumentType()
                == ShortMediumStartWritingRunRequest.DocumentTypeEnum.MANUSCRIPT) {
            Version outline = source.boundOutline() != null
                    ? source.boundOutline()
                    : source.currentOutline();
            if (outline == null
                    || !Objects.equals(
                            current.payload().sourceOutlineVersionId(), outline.id())) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_SOURCE_OUTLINE_MISSING",
                        "正文基础版本的来源大纲不存在");
            }
            payload.put("sourceOutlineVersionId", outline.id());
            payload.put("sourceOutlineContent", outline.payload().content());
            payload.put("sourceOutlineContentHash", outline.payload().contentHash());
        }
    }

    private static void assembleCheck(
            Loaded source, Version current, Map<String, Object> payload) {
        if (current == null) {
            throw new ApiException(
                    409, "SHORT_MEDIUM_BASE_VERSION_REQUIRED", "全文检查必须基于已确认正文版本");
        }
        Version outline = source.boundOutline() != null
                ? source.boundOutline()
                : source.currentOutline();
        if (outline != null) {
            payload.put("sourceOutlineVersionId", outline.id());
            payload.put("sourceOutlineContent", outline.payload().content());
            payload.put("sourceOutlineContentHash", outline.payload().contentHash());
        }
    }

    private List<Version> versions(
            DSLContext transaction, String novelId, String artifactKey) {
        List<ReviewartifactRecord> artifacts = transaction.selectFrom(REVIEWARTIFACT)
                .where(
                        REVIEWARTIFACT.NOVELID.eq(novelId),
                        REVIEWARTIFACT.ARTIFACTKEY.eq(artifactKey))
                .orderBy(REVIEWARTIFACT.CREATEDAT.asc(), REVIEWARTIFACT.ID.asc())
                .forUpdate()
                .fetch();
        List<Version> result = new ArrayList<>();
        for (ReviewartifactRecord artifact : artifacts) {
            try {
                ShortMediumVersionPayload payload =
                        json.readValue(artifact.getPayloadjson(), ShortMediumVersionPayload.class);
                String expected = "outline".equals(payload.documentType())
                        ? OUTLINE_PREFIX + artifact.getNovelid()
                        : MANUSCRIPT_PREFIX + artifact.getChapterid();
                if (!expected.equals(artifact.getArtifactkey())) throw new IllegalArgumentException();
                result.add(new Version(
                        artifact.getId(), artifact.getStatus().getLiteral(), payload));
            } catch (RuntimeException exception) {
                throw persistedInvalid();
            }
        }
        return result;
    }

    private static Version current(List<Version> versions) {
        return versions.stream()
                .filter(version -> "applied".equals(version.status()))
                .max(Comparator.comparingInt(version -> version.payload().versionNumber()))
                .orElse(null);
    }

    private static void requireClean(String workContent, Version current) {
        if (!ShortMediumText.sha256(workContent).equals(current.payload().contentHash())) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_WORK_DRAFT_DIRTY",
                    "工作稿存在未提交修改，请先提交或放弃修改");
        }
    }

    private Map<String, Object> object(String value) {
        try {
            Object parsed = json.readValue(value, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) throw persistedInvalid();
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!(entry.getKey() instanceof String key)) throw persistedInvalid();
                result.put(key, entry.getValue());
            }
            return result;
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw persistedInvalid();
        }
    }

    private static Map<String, Object> emptyPayload() {
        Map<String, Object> payload = new LinkedHashMap<>();
        for (String field : List.of(
                "workflow",
                "operation",
                "documentType",
                "chapterId",
                "baseVersionId",
                "baseContent",
                "baseContentHash",
                "sourceOutlineVersionId",
                "sourceOutlineContent",
                "sourceOutlineContentHash",
                "selectionStart",
                "selectionEnd",
                "selectedText",
                "selectedTextHash",
                "contextBefore",
                "contextAfter",
                "userInstruction",
                "targetTotalWordCount",
                "sourceKind",
                "sourceText")) {
            payload.put(field, null);
        }
        return payload;
    }

    private static String codePointSlice(String value, int start, int end) {
        int startOffset = value.offsetByCodePoints(0, start);
        int endOffset = value.offsetByCodePoints(0, end);
        return value.substring(startOffset, endOffset);
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value != null && value.isPresent() ? value.orElse(null) : null;
    }

    private static Map<String, Object> nullableDetail(String key, Object value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(key, value);
        return result;
    }

    private static ApiException persistedInvalid() {
        return new ApiException(
                409, "SHORT_MEDIUM_PERSISTED_JSON_INVALID", "中短篇持久数据格式无效");
    }

    record Assembled(
            String chapterId,
            int targetTotalWordCount,
            Map<String, Object> payload,
            String visibleMessage,
            String selectedAgent) {}

    private record Loaded(
            String chapterId,
            int targetTotalWordCount,
            String sourceKind,
            String sourceText,
            String documentContent,
            Version currentDocument,
            String outlineContent,
            Version currentOutline,
            Version boundOutline) {}

    private record Version(String id, String status, ShortMediumVersionPayload payload) {}
}
