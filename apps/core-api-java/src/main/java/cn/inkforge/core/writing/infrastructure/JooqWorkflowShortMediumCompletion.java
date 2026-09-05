package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;

import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.OutlineRecord;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.shortmedium.domain.DocumentDiff;
import cn.inkforge.core.shortmedium.domain.DocumentDiffEngine;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.workflows.application.WorkflowShortMediumCompletion;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
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
import org.jooq.Record1;
import tools.jackson.databind.ObjectMapper;

/**
 * 把 V2 中短篇最终语义结果物化为既有不可变版本，或返回只读全文报告。
 *
 * <p>外层 Workflow 回调已经锁定 Run/Step；本适配器继续按 Novel → 工作稿 → Artifact 的顺序锁定业务写面。
 * 它不更新 Run/Step，也不创建 WritingTask 或 WritingRunCommand，候选采用仍由中短篇版本公共入口独立完成。
 */
final class JooqWorkflowShortMediumCompletion implements WorkflowShortMediumCompletion {

    private static final String OUTLINE_PREFIX = "short-medium:outline:";
    private static final String MANUSCRIPT_PREFIX = "short-medium:manuscript:";
    private static final Set<String> OPERATIONS = Set.of(
            "generate_outline", "generate_manuscript", "replace_selection", "full_check");
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

    JooqWorkflowShortMediumCompletion(
            CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public Completion complete(DSLContext transaction, CompletionRequest request) {
        Objects.requireNonNull(transaction);
        Objects.requireNonNull(request);
        Snapshot snapshot = snapshot(request);
        if (request.finalText().isEmpty()) throw completionMismatch();
        if ("full_check".equals(snapshot.operation())) {
            return new Completion(null, Map.of("text", request.finalText()));
        }
        String content = materializeContent(snapshot, request.finalText());
        return new Completion(createCandidate(transaction, request, snapshot, content), null);
    }

    private String createCandidate(
            DSLContext transaction,
            CompletionRequest request,
            Snapshot snapshot,
            String content) {
        requireShortMediumNovel(transaction, request.userId(), request.novelId());
        LockedDocument document = lockDocument(transaction, request, snapshot);
        String expectedWorkHash = snapshot.baseContentHash() == null
                ? ShortMediumText.sha256("")
                : snapshot.baseContentHash();
        List<Version> versions = lockVersions(transaction, request, document, snapshot);

        List<Version> runCandidates = versions.stream()
                .filter(version -> request.runId().equals(version.workflowRunId()))
                .toList();
        if (runCandidates.size() > 1) throw persistedInvalid();
        if (!runCandidates.isEmpty()) {
            Version replay = runCandidates.getFirst();
            requireExactRevision(transaction, replay);
            requireReplay(replay, request, snapshot, content);
            return replay.id();
        }

        // 候选只能建立在启动时冻结的干净工作稿与 applied head 上；运行期间的人工编辑或采用不能被覆盖。
        if (!ShortMediumText.sha256(document.content()).equals(expectedWorkHash)) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_WORK_DRAFT_DIRTY",
                    "任务运行期间工作稿已经变化，未创建候选版本");
        }
        List<Version> documentVersions = versions.stream()
                .filter(version -> document.artifactKey().equals(version.artifactKey()))
                .toList();
        Version current = current(documentVersions);
        if (!Objects.equals(current == null ? null : current.id(), snapshot.baseVersionId())) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_BASE_VERSION_CONFLICT",
                    "任务完成时当前版本已经变化，未创建候选版本");
        }
        requireSourceOutline(versions, snapshot);

        int versionNumber = documentVersions.stream()
                        .mapToInt(version -> version.payload().versionNumber())
                        .max()
                        .orElse(0)
                + 1;
        String kind = "outline".equals(snapshot.documentType())
                ? "outline_draft"
                : "chapter_draft";
        ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                kind,
                snapshot.documentType(),
                versionNumber,
                snapshot.baseVersionId(),
                null,
                "agent",
                content,
                ShortMediumText.sha256(content),
                request.runId(),
                request.producerStepId(),
                snapshot.sourceOutlineVersionId(),
                snapshot.userInstruction(),
                snapshot.sourceKind(),
                snapshot.sourceText(),
                null,
                "replace_selection".equals(snapshot.operation()),
                snapshot.selectionStart(),
                snapshot.selectionEnd(),
                snapshot.selectedTextHash());
        String artifactId = ids.next();
        DocumentDiff diff = DocumentDiffEngine.bind(
                DocumentDiffEngine.build(
                        current == null ? "" : current.payload().content(),
                        content,
                        current == null ? null : current.id(),
                        artifactId),
                snapshot.documentType(),
                document.chapterId(),
                snapshot.baseVersionId(),
                expectedWorkHash,
                artifactId);
        String agentName = Map.of(
                        "generate_outline", "剧情",
                        "generate_manuscript", "写作",
                        "replace_selection", "编辑")
                .get(snapshot.operation());
        String title = "outline".equals(snapshot.documentType())
                ? "中短篇大纲候选版本"
                : "中短篇正文候选版本";
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String payloadJson = json.writeValueAsString(payload);
        String diffJson = json.writeValueAsString(diff);
        // taskId/workflowRunId 必须二选一；V2 只绑定真实 Run，sourceTaskId 保留为公共兼容别名。
        transaction.insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, artifactId)
                .set(REVIEWARTIFACT.NOVELID, request.novelId())
                .set(REVIEWARTIFACT.CHAPTERID, document.chapterId())
                .setNull(REVIEWARTIFACT.TASKID)
                .set(REVIEWARTIFACT.WORKFLOWRUNID, request.runId())
                .set(REVIEWARTIFACT.ARTIFACTKEY, document.artifactKey())
                .set(
                        REVIEWARTIFACT.KIND,
                        "outline".equals(snapshot.documentType())
                                ? Reviewartifactkind.outline_draft
                                : Reviewartifactkind.chapter_draft)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.awaiting_user)
                .set(REVIEWARTIFACT.TITLE, title)
                .set(REVIEWARTIFACT.SUMMARY, snapshot.userInstruction())
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
                .set(REVIEWARTIFACTREVISION.SUMMARY, snapshot.userInstruction())
                .set(REVIEWARTIFACTREVISION.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACTREVISION.DIFFJSON, diffJson)
                .set(REVIEWARTIFACTREVISION.CREATEDBYAGENT, agentName)
                .set(REVIEWARTIFACTREVISION.CREATEDAT, now)
                .execute();
        return artifactId;
    }

    private Snapshot snapshot(CompletionRequest request) {
        Map<String, Object> value = request.frozenContext();
        if (!value.keySet().equals(SNAPSHOT_FIELDS)
                || !"short_medium".equals(value.get("workflow"))
                || !(value.get("operation") instanceof String operation)
                || !OPERATIONS.contains(operation)
                || !operation.equals(request.operation())
                || !(value.get("documentType") instanceof String documentType)
                || !Set.of("outline", "manuscript").contains(documentType)
                || request.runId().isBlank()
                || request.producerStepId().isBlank()
                || request.evidenceBundleId().isBlank()
                || request.contextItemId().isBlank()
                || !validHash(request.producerResultHash())
                || !validHash(request.contextContentSha256())
                || !request.contextContentSha256()
                        .equals(ExecutionCanonicalJson.sha256(value))) {
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
        validateSnapshot(snapshot, request);
        return snapshot;
    }

    private static void validateSnapshot(
            Snapshot value, CompletionRequest request) {
        if (!Objects.equals(value.chapterId(), request.chapterId())
                || value.targetTotalWordCount() == null
                || value.targetTotalWordCount() < 6_000
                || value.targetTotalWordCount() > 80_000) {
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
                        || value.chapterId() != null
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
                        || value.chapterId() == null
                        || value.sourceOutlineVersionId() == null
                        || value.sourceKind() == null
                        || value.sourceText() == null
                        || value.sourceText().isBlank()
                        || value.hasSelection()) {
                    throw snapshotInvalid();
                }
            }
            case "replace_selection" -> validateSelection(value);
            case "full_check" -> {
                if (!"manuscript".equals(value.documentType())
                        || value.chapterId() == null
                        || value.baseVersionId() == null
                        || value.hasSelection()) {
                    throw snapshotInvalid();
                }
            }
            default -> throw snapshotInvalid();
        }
    }

    private static void validateSelection(Snapshot value) {
        if (value.baseVersionId() == null
                || value.baseContent() == null
                || value.baseContentHash() == null
                || value.selectionStart() == null
                || value.selectionEnd() == null
                || value.selectionStart() < 0
                || value.selectionStart() >= value.selectionEnd()
                || value.selectionEnd() > ShortMediumText.codePointLength(value.baseContent())
                || value.selectedText() == null
                || value.selectedTextHash() == null
                || value.contextBefore() == null
                || value.contextAfter() == null
                || value.userInstruction() == null
                || value.userInstruction().isBlank()
                || !ShortMediumText.sha256(value.selectedText()).equals(value.selectedTextHash())
                || !slice(value.baseContent(), value.selectionStart(), value.selectionEnd())
                        .equals(value.selectedText())
                || !(value.contextBefore() + value.selectedText() + value.contextAfter())
                        .equals(value.baseContent())
                || "manuscript".equals(value.documentType())
                        != (value.sourceOutlineVersionId() != null)) {
            throw snapshotInvalid();
        }
    }

    private static String materializeContent(Snapshot snapshot, String finalText) {
        if ("replace_selection".equals(snapshot.operation())) {
            return snapshot.contextBefore() + finalText + snapshot.contextAfter();
        }
        if ("generate_manuscript".equals(snapshot.operation())) {
            if ("opening".equals(snapshot.sourceKind())
                            && !finalText.startsWith(snapshot.sourceText())
                    || "ending".equals(snapshot.sourceKind())
                            && !finalText.endsWith(snapshot.sourceText())) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_FIXED_SOURCE_CHANGED",
                        "生成正文改动了固定开头或结尾");
            }
            int wordCount = ShortMediumText.count(finalText);
            if (wordCount < 6_000 || wordCount > 80_000) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_MANUSCRIPT_LENGTH_INVALID",
                        "生成正文必须保持在6000至80000字范围内");
            }
        }
        return finalText;
    }

    private static void requireReplay(
            Version replay,
            CompletionRequest request,
            Snapshot snapshot,
            String content) {
        ShortMediumVersionPayload payload = replay.payload();
        boolean valid = replay.taskId() == null
                && request.runId().equals(replay.workflowRunId())
                && request.runId().equals(payload.sourceTaskId())
                && request.producerStepId().equals(payload.sourceJobId())
                && snapshot.documentType().equals(payload.documentType())
                && Objects.equals(snapshot.baseVersionId(), payload.baseVersionId())
                && Objects.equals(
                        snapshot.sourceOutlineVersionId(), payload.sourceOutlineVersionId())
                && Objects.equals(snapshot.userInstruction(), payload.userInstruction())
                && Objects.equals(snapshot.sourceKind(), payload.sourceKind())
                && Objects.equals(snapshot.sourceText(), payload.sourceText())
                && content.equals(payload.content())
                && ShortMediumText.sha256(content).equals(payload.contentHash())
                && ("replace_selection".equals(snapshot.operation())
                        == payload.createdFromSelection())
                && Objects.equals(snapshot.selectionStart(), payload.selectionStart())
                && Objects.equals(snapshot.selectionEnd(), payload.selectionEnd())
                && Objects.equals(snapshot.selectedTextHash(), payload.selectedTextHash());
        if (!valid) throw completionMismatch();
    }

    private static void requireSourceOutline(
            List<Version> versions, Snapshot snapshot) {
        if (snapshot.sourceOutlineVersionId() == null) return;
        Version outline = versions.stream()
                .filter(version -> snapshot.sourceOutlineVersionId().equals(version.id()))
                .findFirst()
                .orElseThrow(JooqWorkflowShortMediumCompletion::snapshotInvalid);
        if (!"outline".equals(outline.payload().documentType())
                || !"applied".equals(outline.status())
                || !snapshot.sourceOutlineContent().equals(outline.payload().content())
                || !snapshot.sourceOutlineContentHash()
                        .equals(outline.payload().contentHash())) {
            throw snapshotInvalid();
        }
    }

    private List<Version> lockVersions(
            DSLContext transaction,
            CompletionRequest request,
            LockedDocument document,
            Snapshot snapshot) {
        List<String> keys = new ArrayList<>();
        keys.add(document.artifactKey());
        if (snapshot.sourceOutlineVersionId() != null
                && !"outline".equals(snapshot.documentType())) {
            keys.add(OUTLINE_PREFIX + request.novelId());
        }
        List<ReviewartifactRecord> artifacts = transaction.selectFrom(REVIEWARTIFACT)
                .where(
                        REVIEWARTIFACT.NOVELID.eq(request.novelId()),
                        REVIEWARTIFACT.ARTIFACTKEY.in(keys))
                .orderBy(REVIEWARTIFACT.ARTIFACTKEY.asc(), REVIEWARTIFACT.ID.asc())
                .forUpdate()
                .fetch();
        List<Version> result = new ArrayList<>();
        for (ReviewartifactRecord artifact : artifacts) {
            result.add(map(artifact));
        }
        return List.copyOf(result);
    }

    private static void requireExactRevision(
            DSLContext transaction, Version version) {
        var revision = transaction.select(
                        REVIEWARTIFACTREVISION.PAYLOADJSON,
                        REVIEWARTIFACTREVISION.DIFFJSON)
                .from(REVIEWARTIFACTREVISION)
                .where(
                        REVIEWARTIFACTREVISION.ARTIFACTID.eq(version.id()),
                        REVIEWARTIFACTREVISION.REVISION.eq(1))
                .forUpdate()
                .fetchOne();
        if (revision == null
                || !Objects.equals(revision.value1(), version.payloadJson())
                || !Objects.equals(revision.value2(), version.diffJson())) {
            throw persistedInvalid();
        }
    }

    private Version map(ReviewartifactRecord artifact) {
        try {
            ShortMediumVersionPayload payload = json.readValue(
                    artifact.getPayloadjson(), ShortMediumVersionPayload.class);
            String expectedKey = "outline".equals(payload.documentType())
                    ? OUTLINE_PREFIX + artifact.getNovelid()
                    : MANUSCRIPT_PREFIX + artifact.getChapterid();
            String expectedKind = "outline".equals(payload.documentType())
                    ? "outline_draft"
                    : "chapter_draft";
            boolean v1 = artifact.getTaskid() != null
                    && artifact.getWorkflowrunid() == null
                    && artifact.getTaskid().equals(payload.sourceTaskId());
            boolean v2 = artifact.getTaskid() == null
                    && artifact.getWorkflowrunid() != null
                    && artifact.getWorkflowrunid().equals(payload.sourceTaskId());
            boolean manual = artifact.getTaskid() == null
                    && artifact.getWorkflowrunid() == null
                    && !"agent".equals(payload.source());
            boolean originValid = "agent".equals(payload.source()) ? v1 || v2 : manual;
            if (!expectedKey.equals(artifact.getArtifactkey())
                    || !expectedKind.equals(artifact.getKind().getLiteral())
                    || artifact.getRevision() == null
                    || artifact.getRevision() != 1
                    || !originValid) {
                throw persistedInvalid();
            }
            return new Version(
                    artifact.getId(),
                    artifact.getArtifactkey(),
                    artifact.getStatus().getLiteral(),
                    payload,
                    artifact.getTaskid(),
                    artifact.getWorkflowrunid(),
                    artifact.getPayloadjson(),
                    artifact.getDiffjson());
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw persistedInvalid();
        }
    }

    private static Version current(List<Version> versions) {
        return versions.stream()
                .filter(version -> "applied".equals(version.status()))
                .max(Comparator.comparingInt(version -> version.payload().versionNumber()))
                .orElse(null);
    }

    private static LockedDocument lockDocument(
            DSLContext transaction, CompletionRequest request, Snapshot snapshot) {
        if ("outline".equals(snapshot.documentType())) {
            OutlineRecord outline = transaction.selectFrom(OUTLINE)
                    .where(OUTLINE.NOVELID.eq(request.novelId()))
                    .forUpdate()
                    .fetchOne();
            if (outline == null) throw documentNotFound();
            return new LockedDocument(
                    null, OUTLINE_PREFIX + request.novelId(), outline.getContent());
        }
        List<ChapterRecord> chapters = transaction.selectFrom(CHAPTER)
                .where(CHAPTER.NOVELID.eq(request.novelId()))
                .orderBy(CHAPTER.ORDER.asc(), CHAPTER.ID.asc())
                .forUpdate()
                .fetch();
        if (chapters.size() != 1
                || !chapters.getFirst().getId().equals(request.chapterId())) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_CHAPTER_INVALID",
                    "中短篇必须且只能绑定唯一全文章节");
        }
        ChapterRecord chapter = chapters.getFirst();
        return new LockedDocument(
                chapter.getId(), MANUSCRIPT_PREFIX + chapter.getId(), chapter.getContent());
    }

    private static void requireShortMediumNovel(
            DSLContext transaction, String userId, String novelId) {
        Record1<String> novel = transaction.select(NOVEL.ID)
                .from(NOVEL)
                .join(WRITINGBIBLE)
                .on(WRITINGBIBLE.NOVELID.eq(NOVEL.ID))
                .where(
                        NOVEL.ID.eq(novelId),
                        NOVEL.USERID.eq(userId),
                        WRITINGBIBLE.STORYLENGTHPROFILE.eq(Storylengthprofile.short_medium))
                .forUpdate()
                .of(NOVEL)
                .fetchOne();
        if (novel == null) {
            throw new ApiException(
                    404, "SHORT_MEDIUM_NOVEL_NOT_FOUND", "中短篇作品不存在");
        }
    }

    private static void validateOptionalSnapshot(
            String id, String content, String hash) {
        if (id == null && content == null && hash == null) return;
        if (id == null
                || content == null
                || !validHash(hash)
                || !ShortMediumText.sha256(content).equals(hash)) {
            throw snapshotInvalid();
        }
    }

    private static String string(Object value) {
        if (value == null) return null;
        if (!(value instanceof String text)) throw snapshotInvalid();
        return text;
    }

    private static Integer integer(Object value) {
        if (value == null) return null;
        if (!(value instanceof Byte
                        || value instanceof Short
                        || value instanceof Integer
                        || value instanceof Long)
                || ((Number) value).longValue() < Integer.MIN_VALUE
                || ((Number) value).longValue() > Integer.MAX_VALUE) {
            throw snapshotInvalid();
        }
        return ((Number) value).intValue();
    }

    private static boolean validHash(String value) {
        return value != null && value.matches("[0-9a-f]{64}");
    }

    private static String slice(String value, int start, int end) {
        if (start < 0 || end < start || end > ShortMediumText.codePointLength(value)) {
            throw snapshotInvalid();
        }
        return value.substring(
                value.offsetByCodePoints(0, start), value.offsetByCodePoints(0, end));
    }

    private static ApiException snapshotInvalid() {
        return new ApiException(
                409, "SHORT_MEDIUM_RUN_SNAPSHOT_INVALID", "中短篇任务快照无效");
    }

    private static ApiException completionMismatch() {
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

    private record LockedDocument(
            String chapterId, String artifactKey, String content) {}

    private record Version(
            String id,
            String artifactKey,
            String status,
            ShortMediumVersionPayload payload,
            String taskId,
            String workflowRunId,
            String payloadJson,
            String diffJson) {}

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
