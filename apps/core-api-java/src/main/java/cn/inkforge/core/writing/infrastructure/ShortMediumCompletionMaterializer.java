package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;

import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.OutlineRecord;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.shortmedium.domain.DocumentDiff;
import cn.inkforge.core.shortmedium.domain.DocumentDiffEngine;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.writing.application.WritingCommandPayload;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/**
 * 在写作完成回调事务内校验中短篇结果并创建不可变候选版本。
 *
 * <p>完成结果必须与命令冻结的操作、文档、选区、基线内容和哈希逐项匹配；全文检查只返回报告，其余操作只创建
 * {@code awaiting_user} Artifact，不直接覆盖两份工作稿。候选、修订快照和命令绑定与任务终态共享外层事务。
 */
final class ShortMediumCompletionMaterializer {

    private static final String OUTLINE_PREFIX = "short-medium:outline:";
    private static final String MANUSCRIPT_PREFIX = "short-medium:manuscript:";
    private static final Set<String> SNAPSHOT_FIELDS = Set.of(
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
            "sourceText");

    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    ShortMediumCompletionMaterializer(
            CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    Map<String, Object> finalizeResult(
            DSLContext transaction,
            WritingtaskRecord task,
            WritingruncommandRecord command,
            Map<String, Object> incoming) {
        Snapshot payload = snapshot(command, task);
        Materialized materialized = materialize(payload, incoming);
        Map<String, Object> result = new LinkedHashMap<>(incoming);
        if ("full_check".equals(payload.operation())) {
            result.put("checkReport", materialized.checkReport());
            return result;
        }
        String artifactKey = "outline".equals(payload.documentType())
                ? OUTLINE_PREFIX + task.getNovelid()
                : MANUSCRIPT_PREFIX + task.getChapterid();
        String workContent = lockWorkContent(transaction, task, payload.documentType());
        String expectedWorkHash = payload.baseContentHash() == null
                ? ShortMediumText.sha256("")
                : payload.baseContentHash();
        // Agent 运行期间作者若已编辑工作稿，宁可拒绝候选也不能把基于旧文本的结果套到新正文上。
        if (!ShortMediumText.sha256(workContent).equals(expectedWorkHash)) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_WORK_DRAFT_DIRTY",
                    "任务运行期间工作稿已经变化，未创建候选版本");
        }
        List<Version> versions = loadVersions(
                transaction, task.getNovelid(), artifactKey);
        Version replay = versions.stream()
                .filter(version -> task.getId().equals(version.payload().sourceTaskId())
                        && command.getId().equals(version.payload().sourceJobId()))
                .findFirst()
                .orElse(null);
        // 终态回调可能重放；以 task + command 找回原候选，不能再分配一个新版本号。
        if (replay != null) {
            command.setArtifactid(replay.id());
            result.put("candidateVersionId", replay.id());
            return result;
        }
        Version current = versions.stream()
                .filter(version -> "applied".equals(version.status()))
                .max(Comparator.comparingInt(version -> version.payload().versionNumber()))
                .orElse(null);
        if (!Objects.equals(current == null ? null : current.id(), payload.baseVersionId())) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_BASE_VERSION_CONFLICT",
                    "任务完成时当前版本已经变化，未创建候选版本");
        }
        String content = materialized.content();
        int versionNumber = versions.stream()
                        .mapToInt(version -> version.payload().versionNumber())
                        .max()
                        .orElse(0)
                + 1;
        String kind = "outline".equals(payload.documentType())
                ? "outline_draft"
                : "chapter_draft";
        ShortMediumVersionPayload versionPayload = new ShortMediumVersionPayload(
                kind,
                payload.documentType(),
                versionNumber,
                payload.baseVersionId(),
                null,
                "agent",
                content,
                ShortMediumText.sha256(content),
                task.getId(),
                command.getId(),
                payload.sourceOutlineVersionId(),
                payload.userInstruction(),
                payload.sourceKind(),
                payload.sourceText(),
                null,
                "replace_selection".equals(payload.operation()),
                payload.selectionStart(),
                payload.selectionEnd(),
                payload.selectedTextHash());
        String before = current == null ? "" : current.payload().content();
        DocumentDiff initial = DocumentDiffEngine.build(
                before, content, current == null ? null : current.id(), null);
        String artifactId = ids.next();
        DocumentDiff bound = DocumentDiffEngine.bind(
                initial.withToVersionId(artifactId),
                payload.documentType(),
                "manuscript".equals(payload.documentType()) ? task.getChapterid() : null,
                payload.baseVersionId(),
                expectedWorkHash,
                artifactId);
        String agentName = Map.of(
                        "generate_outline", "剧情",
                        "generate_manuscript", "写作",
                        "replace_selection", "编辑")
                .get(payload.operation());
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String payloadJson = json.writeValueAsString(versionPayload);
        String diffJson = json.writeValueAsString(bound);
        // Artifact 当前行与 revision 1 同时建立，后续返工才有不可覆盖的历史基点。
        transaction.insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, artifactId)
                .set(REVIEWARTIFACT.NOVELID, task.getNovelid())
                .set(
                        REVIEWARTIFACT.CHAPTERID,
                        "manuscript".equals(payload.documentType())
                                ? task.getChapterid()
                                : null)
                .set(REVIEWARTIFACT.TASKID, task.getId())
                .set(REVIEWARTIFACT.ARTIFACTKEY, artifactKey)
                .set(
                        REVIEWARTIFACT.KIND,
                        "outline".equals(payload.documentType())
                                ? Reviewartifactkind.outline_draft
                                : Reviewartifactkind.chapter_draft)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.awaiting_user)
                .set(
                        REVIEWARTIFACT.TITLE,
                        "outline".equals(payload.documentType())
                                ? "中短篇大纲候选版本"
                                : "中短篇正文候选版本")
                .set(REVIEWARTIFACT.SUMMARY, payload.userInstruction())
                .set(REVIEWARTIFACT.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACT.DIFFJSON, diffJson)
                .set(REVIEWARTIFACT.CREATEDBYAGENT, agentName)
                .set(REVIEWARTIFACT.UPDATEDBYAGENT, agentName)
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.CREATEDAT, now)
                .set(REVIEWARTIFACT.UPDATEDAT, now)
                .execute();
        transaction.insertInto(REVIEWARTIFACTREVISION)
                .set(REVIEWARTIFACTREVISION.ID, ids.next())
                .set(REVIEWARTIFACTREVISION.ARTIFACTID, artifactId)
                .set(REVIEWARTIFACTREVISION.REVISION, 1)
                .set(REVIEWARTIFACTREVISION.SUMMARY, payload.userInstruction())
                .set(REVIEWARTIFACTREVISION.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACTREVISION.DIFFJSON, diffJson)
                .set(REVIEWARTIFACTREVISION.CREATEDBYAGENT, agentName)
                .set(REVIEWARTIFACTREVISION.CREATEDAT, now)
                .execute();
        command.setArtifactid(artifactId);
        result.put("candidateVersionId", artifactId);
        return result;
    }

    private Snapshot snapshot(
            WritingruncommandRecord command, WritingtaskRecord task) {
        Map<String, Object> value;
        try {
            value = WritingCommandPayload.parse(
                            command.getKind(), command.getPayloadjson(), json)
                    .job();
        } catch (RuntimeException exception) {
            throw snapshotInvalid();
        }
        if (!value.keySet().equals(SNAPSHOT_FIELDS)
                || !"short_medium".equals(value.get("workflow"))
                || !(value.get("operation") instanceof String operation)
                || !Set.of(
                                "generate_outline",
                                "generate_manuscript",
                                "replace_selection",
                                "full_check")
                        .contains(operation)
                || !(value.get("documentType") instanceof String documentType)
                || !Set.of("outline", "manuscript").contains(documentType)) {
            throw snapshotInvalid();
        }
        Snapshot snapshot = new Snapshot(
                operation,
                documentType,
                string(value.get("chapterId")),
                string(value.get("baseVersionId")),
                string(value.get("baseContent")),
                string(value.get("baseContentHash")),
                string(value.get("sourceOutlineVersionId")),
                string(value.get("sourceOutlineContent")),
                string(value.get("sourceOutlineContentHash")),
                integer(value.get("selectionStart")),
                integer(value.get("selectionEnd")),
                string(value.get("selectedText")),
                string(value.get("selectedTextHash")),
                string(value.get("contextBefore")),
                string(value.get("contextAfter")),
                string(value.get("userInstruction")),
                integer(value.get("targetTotalWordCount")),
                string(value.get("sourceKind")),
                string(value.get("sourceText")));
        validateSnapshot(snapshot, task);
        return snapshot;
    }

    private static void validateSnapshot(Snapshot value, WritingtaskRecord task) {
        if ("manuscript".equals(value.documentType())) {
            if (!Objects.equals(value.chapterId(), task.getChapterid())) throw snapshotInvalid();
        } else if (value.chapterId() != null) {
            throw snapshotInvalid();
        }
        validateOptionalSnapshot(
                value.baseVersionId(), value.baseContent(), value.baseContentHash());
        validateOptionalSnapshot(
                value.sourceOutlineVersionId(),
                value.sourceOutlineContent(),
                value.sourceOutlineContentHash());
        switch (value.operation()) {
            case "generate_outline" -> {
                if (!"outline".equals(value.documentType())
                        || value.sourceOutlineVersionId() != null
                        || value.sourceKind() == null
                        || value.sourceText() == null
                        || value.sourceText().isBlank()
                        || value.hasSelection()) {
                    throw snapshotInvalid();
                }
            }
            case "generate_manuscript" -> {
                if (!"manuscript".equals(value.documentType())
                        || value.sourceOutlineVersionId() == null
                        || value.targetTotalWordCount() == null
                        || value.targetTotalWordCount() < 6_000
                        || value.targetTotalWordCount() > 80_000
                        || value.hasSelection()) {
                    throw snapshotInvalid();
                }
            }
            case "replace_selection" -> {
                if (value.baseVersionId() == null
                        || value.baseContent() == null
                        || value.baseContentHash() == null
                        || value.selectionStart() == null
                        || value.selectionEnd() == null
                        || value.selectionStart() < 0
                        || value.selectionStart() >= value.selectionEnd()
                        || value.selectedText() == null
                        || value.selectedTextHash() == null
                        || value.contextBefore() == null
                        || value.contextAfter() == null
                        || value.userInstruction() == null
                        || value.userInstruction().isBlank()
                        || !ShortMediumText.sha256(value.selectedText())
                                .equals(value.selectedTextHash())) {
                    throw snapshotInvalid();
                }
                if ("manuscript".equals(value.documentType())
                        != (value.sourceOutlineVersionId() != null)) {
                    throw snapshotInvalid();
                }
            }
            case "full_check" -> {
                if (!"manuscript".equals(value.documentType())
                        || value.baseVersionId() == null
                        || value.baseContent() == null
                        || value.baseContentHash() == null
                        || value.hasSelection()) {
                    throw snapshotInvalid();
                }
            }
            default -> throw snapshotInvalid();
        }
    }

    private static Materialized materialize(
            Snapshot payload, Map<String, Object> result) {
        try {
            if (Set.of("generate_outline", "generate_manuscript")
                    .contains(payload.operation())) {
                requireKeys(result, Set.of(
                        "resultType",
                        "operation",
                        "documentType",
                        "content",
                        "sourceOutlineVersionId"));
                if (!"short_medium_document".equals(result.get("resultType"))
                        || !payload.operation().equals(result.get("operation"))
                        || !payload.documentType().equals(result.get("documentType"))
                        || !(result.get("content") instanceof String content)
                        || content.isEmpty()
                        || !Objects.equals(
                                payload.sourceOutlineVersionId(),
                                result.get("sourceOutlineVersionId"))) {
                    throw mismatch();
                }
                if ("generate_manuscript".equals(payload.operation())
                        && "opening".equals(payload.sourceKind())
                        && payload.sourceText() != null
                        && !content.startsWith(payload.sourceText())
                        || "generate_manuscript".equals(payload.operation())
                                && "ending".equals(payload.sourceKind())
                                && payload.sourceText() != null
                                && !content.endsWith(payload.sourceText())) {
                    throw new ApiException(
                            409,
                            "SHORT_MEDIUM_FIXED_SOURCE_CHANGED",
                            "生成正文改动了固定开头或结尾");
                }
                return new Materialized(content, null);
            }
            if ("replace_selection".equals(payload.operation())) {
                requireKeys(result, Set.of(
                        "resultType",
                        "operation",
                        "documentType",
                        "replacement",
                        "baseVersionId",
                        "baseContentHash",
                        "selectionStart",
                        "selectionEnd",
                        "selectedTextHash"));
                if (!"short_medium_replacement".equals(result.get("resultType"))
                        || !"replace_selection".equals(result.get("operation"))
                        || !payload.documentType().equals(result.get("documentType"))
                        || !(result.get("replacement") instanceof String replacement)
                        || !Objects.equals(payload.baseVersionId(), result.get("baseVersionId"))
                        || !Objects.equals(payload.baseContentHash(), result.get("baseContentHash"))
                        || !Objects.equals(payload.selectionStart(), integer(result.get("selectionStart")))
                        || !Objects.equals(payload.selectionEnd(), integer(result.get("selectionEnd")))
                        || !Objects.equals(payload.selectedTextHash(), result.get("selectedTextHash"))) {
                    throw mismatch();
                }
                String base = Objects.requireNonNull(payload.baseContent());
                String content = codePointSlice(base, 0, payload.selectionStart())
                        + replacement
                        + codePointSlice(
                                base,
                                payload.selectionEnd(),
                                ShortMediumText.codePointLength(base));
                return new Materialized(content, null);
            }
            requireKeys(result, Set.of(
                    "resultType", "operation", "documentType", "baseVersionId", "report"));
            if (!"short_medium_check".equals(result.get("resultType"))
                    || !"full_check".equals(result.get("operation"))
                    || !"manuscript".equals(result.get("documentType"))
                    || !Objects.equals(payload.baseVersionId(), result.get("baseVersionId"))
                    || !(result.get("report") instanceof Map<?, ?> report)) {
                throw mismatch();
            }
            Map<String, Object> normalized = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : report.entrySet()) {
                if (!(entry.getKey() instanceof String key)) throw mismatch();
                normalized.put(key, entry.getValue());
            }
            return new Materialized(null, normalized);
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw mismatch();
        }
    }

    private String lockWorkContent(
            DSLContext transaction, WritingtaskRecord task, String documentType) {
        if ("outline".equals(documentType)) {
            OutlineRecord outline = transaction.selectFrom(OUTLINE)
                    .where(OUTLINE.NOVELID.eq(task.getNovelid()))
                    .forUpdate()
                    .fetchOne();
            if (outline == null) throw documentNotFound();
            return outline.getContent();
        }
        ChapterRecord chapter = transaction.selectFrom(CHAPTER)
                .where(
                        CHAPTER.ID.eq(task.getChapterid()),
                        CHAPTER.NOVELID.eq(task.getNovelid()))
                .forUpdate()
                .fetchOne();
        if (chapter == null) throw documentNotFound();
        return chapter.getContent();
    }

    private List<Version> loadVersions(
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
                ShortMediumVersionPayload payload = json.readValue(
                        artifact.getPayloadjson(), ShortMediumVersionPayload.class);
                String expected = "outline".equals(payload.documentType())
                        ? OUTLINE_PREFIX + artifact.getNovelid()
                        : MANUSCRIPT_PREFIX + artifact.getChapterid();
                if (!expected.equals(artifact.getArtifactkey())) throw persistedInvalid();
                result.add(new Version(
                        artifact.getId(), artifact.getStatus().getLiteral(), payload));
            } catch (ApiException exception) {
                throw exception;
            } catch (RuntimeException exception) {
                throw persistedInvalid();
            }
        }
        return result;
    }

    private static void validateOptionalSnapshot(
            String id, String content, String hash) {
        boolean allNull = id == null && content == null && hash == null;
        if (allNull) return;
        if (id == null
                || content == null
                || hash == null
                || !hash.matches("[0-9a-f]{64}")
                || !ShortMediumText.sha256(content).equals(hash)) {
            throw snapshotInvalid();
        }
    }

    private static void requireKeys(Map<String, Object> value, Set<String> keys) {
        if (value == null || !value.keySet().equals(keys)) throw mismatch();
    }

    private static String string(Object value) {
        if (value == null) return null;
        if (!(value instanceof String text)) throw snapshotInvalid();
        return text;
    }

    private static Integer integer(Object value) {
        if (value == null) return null;
        if (!(value instanceof Number number)
                || value instanceof Double
                || value instanceof Float
                || number.longValue() < Integer.MIN_VALUE
                || number.longValue() > Integer.MAX_VALUE) {
            throw snapshotInvalid();
        }
        return number.intValue();
    }

    private static String codePointSlice(String value, int start, int end) {
        if (start < 0 || end < start || end > ShortMediumText.codePointLength(value)) {
            throw mismatch();
        }
        return value.substring(
                value.offsetByCodePoints(0, start), value.offsetByCodePoints(0, end));
    }

    private static ApiException snapshotInvalid() {
        return new ApiException(
                409, "SHORT_MEDIUM_RUN_SNAPSHOT_INVALID", "中短篇任务快照无效");
    }

    private static ApiException mismatch() {
        return new ApiException(
                409,
                "SHORT_MEDIUM_COMPLETION_IDENTITY_MISMATCH",
                "中短篇完成结果与任务快照不一致");
    }

    private static ApiException documentNotFound() {
        return new ApiException(
                404, "SHORT_MEDIUM_DOCUMENT_NOT_FOUND", "中短篇工作稿不存在");
    }

    private static ApiException persistedInvalid() {
        return new ApiException(
                409, "SHORT_MEDIUM_PERSISTED_JSON_INVALID", "中短篇持久数据格式无效");
    }

    private record Materialized(String content, Map<String, Object> checkReport) {}

    private record Version(String id, String status, ShortMediumVersionPayload payload) {}

    private record Snapshot(
            String operation,
            String documentType,
            String chapterId,
            String baseVersionId,
            String baseContent,
            String baseContentHash,
            String sourceOutlineVersionId,
            String sourceOutlineContent,
            String sourceOutlineContentHash,
            Integer selectionStart,
            Integer selectionEnd,
            String selectedText,
            String selectedTextHash,
            String contextBefore,
            String contextAfter,
            String userInstruction,
            Integer targetTotalWordCount,
            String sourceKind,
            String sourceText) {

        boolean hasSelection() {
            return selectionStart != null
                    || selectionEnd != null
                    || selectedText != null
                    || selectedTextHash != null
                    || contextBefore != null
                    || contextAfter != null;
        }
    }
}
