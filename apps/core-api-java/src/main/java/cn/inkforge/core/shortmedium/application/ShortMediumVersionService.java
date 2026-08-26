package cn.inkforge.core.shortmedium.application;

import cn.inkforge.contracts.api.DiffBlock;
import cn.inkforge.contracts.api.DocumentType;
import cn.inkforge.contracts.api.DocumentVersionPayload;
import cn.inkforge.contracts.api.ManualVersionRequest;
import cn.inkforge.contracts.api.VersionActionRequest;
import cn.inkforge.contracts.api.VersionDetailResponse;
import cn.inkforge.contracts.api.VersionDiffResponse;
import cn.inkforge.contracts.api.VersionListItem;
import cn.inkforge.contracts.api.VersionPreviewRequest;
import cn.inkforge.contracts.api.VersionPreviewResponse;
import cn.inkforge.contracts.api.VersionSource;
import cn.inkforge.contracts.api.VersionStatus;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.shortmedium.domain.DocumentDiff;
import cn.inkforge.core.shortmedium.domain.DocumentDiffBlock;
import cn.inkforge.core.shortmedium.domain.DocumentDiffEngine;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersion;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.shortmedium.domain.VersionDocumentBinding;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 中短篇公共版本用例。
 *
 * <p>预览只计算绑定工作稿的确认哈希；手工提交、采用候选和恢复都在仓储提供的文档事务内重验基线、工作稿哈希与
 * 确认哈希。采用会推进既有候选，恢复则从历史内容创建新版本，历史版本永不被改写。
 */
public final class ShortMediumVersionService {

    private static final ObjectMapper JSON = new ObjectMapper();

    private final ShortMediumVersionRepository repository;

    public ShortMediumVersionService(ShortMediumVersionRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public VersionPreviewResponse preview(
            String userId, String novelId, VersionPreviewRequest request) {
        VersionDocumentBinding binding = binding(
                request.getDocumentType(), nullable(request.getChapterId()));
        String requestedBase = nullable(request.getBaseVersionId());
        return repository.inDocument(userId, novelId, binding, transaction -> {
            ShortMediumVersion current = current(transaction.versions());
            requireCurrentBase(current, requestedBase);
            String before = current == null ? "" : current.content();
            String work = transaction.document().content();
            DocumentDiff diff = DocumentDiffEngine.bind(
                    DocumentDiffEngine.build(
                            before, work, current == null ? null : current.id(), null),
                    binding.documentType(),
                    binding.chapterId(),
                    current == null ? null : current.id(),
                    ShortMediumText.sha256(work),
                    null);
            boolean dirty = !ShortMediumText.sha256(work).equals(ShortMediumText.sha256(before));
            VersionPreviewResponse response = new VersionPreviewResponse();
            response.setDocumentType(request.getDocumentType());
            response.setChapterId(binding.chapterId());
            response.setBaseVersionId(current == null ? null : current.id());
            response.setExpectedUpdatedAt(transaction.document().updatedAt());
            response.setContentHash(ShortMediumText.sha256(work));
            response.setDirty(dirty);
            response.setConfirmationSummary(dirty
                    ? "将提交" + diff.toWordCount() + "字，字数变化%+d".formatted(diff.wordCountDelta())
                    : "工作稿与当前版本一致，没有可提交的变化");
            response.setConfirmationHash(diff.confirmationHash());
            response.setDiff(contract(diff));
            return response;
        });
    }

    public VersionDetailResponse submitManual(
            String userId, String novelId, ManualVersionRequest request) {
        VersionDocumentBinding binding = binding(
                request.getDocumentType(), nullable(request.getChapterId()));
        return repository.inDocument(userId, novelId, binding, transaction -> {
            ShortMediumVersion replay = transaction.versions().stream()
                    .filter(version -> request.getClientRequestId()
                            .equals(version.payload().clientRequestId()))
                    .findFirst()
                    .orElse(null);
            if (replay != null) {
                return detail(replay);
            }
            ShortMediumVersion current = current(transaction.versions());
            requireCurrentBase(current, nullable(request.getBaseVersionId()));
            if (!sameInstant(transaction.document().updatedAt(), request.getExpectedUpdatedAt())) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_WORK_DRAFT_CONFLICT",
                        "工作稿已在其他位置更新，请重新预览",
                        java.util.Map.of(
                                "currentUpdatedAt",
                                transaction.document().updatedAt().toString()));
            }
            String work = transaction.document().content();
            String workHash = ShortMediumText.sha256(work);
            // 时间戳用于并发提示，内容哈希用于精确绑定；两者都匹配才接受此前的预览确认。
            if (!request.getContentHash().equals(workHash)) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_WORK_DRAFT_HASH_CONFLICT",
                        "工作稿内容已经变化，请重新预览",
                        java.util.Map.of("currentContentHash", workHash));
            }
            DocumentDiff confirmation = DocumentDiffEngine.bind(
                    DocumentDiffEngine.build(
                            current == null ? "" : current.content(),
                            work,
                            current == null ? null : current.id(),
                            null),
                    binding.documentType(),
                    binding.chapterId(),
                    current == null ? null : current.id(),
                    workHash,
                    null);
            requireConfirmation(request.getConfirmationHash(), confirmation.confirmationHash());
            if (current != null && current.payload().contentHash().equals(workHash)) {
                return detail(current);
            }
            String sourceOutlineVersionId = null;
            if ("manuscript".equals(binding.documentType())) {
                if (current != null) {
                    sourceOutlineVersionId = current.payload().sourceOutlineVersionId();
                } else {
                    ShortMediumVersion outline = transaction.currentOutlineVersion();
                    if (outline == null) {
                        throw new ApiException(
                                409,
                                "SHORT_MEDIUM_OUTLINE_VERSION_REQUIRED",
                                "提交首个正文版本前必须先确认一份大纲版本");
                    }
                    sourceOutlineVersionId = outline.id();
                }
            }
            ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                    "outline".equals(binding.documentType()) ? "outline_draft" : "chapter_draft",
                    binding.documentType(),
                    nextVersionNumber(transaction.versions()),
                    current == null ? null : current.id(),
                    request.getClientRequestId(),
                    "manual",
                    work,
                    workHash,
                    null,
                    null,
                    sourceOutlineVersionId,
                    null,
                    null,
                    null,
                    null,
                    false,
                    null,
                    null,
                    null);
            ShortMediumVersion created = transaction.create(new VersionCreation(
                    payload,
                    DocumentDiffEngine.build(
                            current == null ? "" : current.content(),
                            work,
                            current == null ? null : current.id(),
                            null),
                    "applied",
                    nullable(request.getSummary()),
                    null,
                    null,
                    null));
            return detail(created);
        });
    }

    public VersionDetailResponse adopt(
            String userId,
            String novelId,
            String versionId,
            VersionActionRequest request) {
        VersionDocumentBinding binding = binding(
                request.getDocumentType(), nullable(request.getChapterId()));
        return repository.inDocument(userId, novelId, binding, transaction -> {
            ShortMediumVersion candidate = find(transaction.versions(), versionId);
            String key = "short-medium:adopt:" + candidate.id() + ":" + request.getClientRequestId();
            String replay = transaction.findAdoptionReplay(key);
            // 采用会同时改工作稿和候选状态，命令回放必须返回第一次采用的同一版本。
            if (replay != null) {
                JsonNode result = JSON.readTree(replay);
                if (result == null
                        || result.get("versionId") == null
                        || !candidate.id().equals(result.get("versionId").asString())) {
                    throw new IllegalStateException("采用幂等结果与候选版本不一致");
                }
                return detail(candidate);
            }
            if (!"awaiting_user".equals(candidate.status())) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_CANDIDATE_STATUS_INVALID",
                        "该版本不是可采用的候选版本");
            }
            ShortMediumVersion current = current(transaction.versions());
            requireCurrentBase(current, nullable(request.getBaseVersionId()));
            String currentId = current == null ? null : current.id();
            if (!Objects.equals(candidate.payload().baseVersionId(), currentId)) {
                throw new ApiException(
                        409,
                        "SHORT_MEDIUM_CANDIDATE_STALE",
                        "候选版本的基础版本已经过期，请改用恢复操作");
            }
            requireClean(transaction, current);
            DocumentDiff confirmation = DocumentDiffEngine.bind(
                    DocumentDiffEngine.build(
                            current == null ? "" : current.content(),
                            candidate.content(),
                            currentId,
                            candidate.id()),
                    binding.documentType(),
                    binding.chapterId(),
                    currentId,
                    ShortMediumText.sha256(transaction.document().content()),
                    candidate.id());
            requireConfirmation(request.getConfirmationHash(), confirmation.confirmationHash());
            transaction.replaceWorkContent(candidate.content());
            ShortMediumVersion applied = transaction.markApplied(candidate);
            String responseJson = JSON.writeValueAsString(java.util.Map.of("versionId", candidate.id()));
            transaction.saveAdoptionReplay(key, candidate, responseJson);
            return detail(applied);
        });
    }

    public VersionDetailResponse restore(
            String userId,
            String novelId,
            String versionId,
            VersionActionRequest request) {
        VersionDocumentBinding binding = binding(
                request.getDocumentType(), nullable(request.getChapterId()));
        return repository.inDocument(userId, novelId, binding, transaction -> {
            ShortMediumVersion replay = transaction.versions().stream()
                    .filter(version -> "restore".equals(version.payload().source()))
                    .filter(version -> request.getClientRequestId()
                            .equals(version.payload().clientRequestId()))
                    .findFirst()
                    .orElse(null);
            if (replay != null) {
                return detail(replay);
            }
            ShortMediumVersion historical = find(transaction.versions(), versionId);
            ShortMediumVersion current = current(transaction.versions());
            requireCurrentBase(current, nullable(request.getBaseVersionId()));
            requireClean(transaction, current);
            String currentId = current == null ? null : current.id();
            DocumentDiff confirmation = DocumentDiffEngine.bind(
                    DocumentDiffEngine.build(
                            current == null ? "" : current.content(),
                            historical.content(),
                            currentId,
                            historical.id()),
                    binding.documentType(),
                    binding.chapterId(),
                    currentId,
                    ShortMediumText.sha256(transaction.document().content()),
                    historical.id());
            requireConfirmation(request.getConfirmationHash(), confirmation.confirmationHash());
            // 历史版本保持只读；恢复通过创建一个 source=restore 的新 applied 版本表达。
            ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                    historical.payload().kind(),
                    historical.payload().documentType(),
                    nextVersionNumber(transaction.versions()),
                    currentId,
                    request.getClientRequestId(),
                    "restore",
                    historical.content(),
                    historical.payload().contentHash(),
                    null,
                    null,
                    historical.payload().sourceOutlineVersionId(),
                    null,
                    null,
                    null,
                    historical.id(),
                    false,
                    null,
                    null,
                    null);
            DocumentDiff storedDiff = DocumentDiffEngine.build(
                    current == null ? "" : current.content(),
                    historical.content(),
                    currentId,
                    null);
            transaction.replaceWorkContent(historical.content());
            ShortMediumVersion restored = transaction.create(new VersionCreation(
                    payload,
                    storedDiff,
                    "applied",
                    "恢复自版本 v" + historical.versionNumber(),
                    null,
                    null,
                    null));
            return detail(restored);
        });
    }

    public List<VersionListItem> list(
            String userId,
            String novelId,
            DocumentType documentType,
            String chapterId) {
        VersionDocumentBinding binding = binding(documentType, chapterId);
        return repository.list(userId, novelId, binding).stream()
                .sorted(Comparator.comparingInt(ShortMediumVersion::versionNumber).reversed())
                .map(ShortMediumVersionService::listItem)
                .toList();
    }

    public VersionDetailResponse get(String userId, String novelId, String versionId) {
        ShortMediumVersion record = repository.requireVersion(userId, novelId, versionId);
        if (record.diff() != null) {
            String baseHash = ShortMediumText.sha256("");
            if (record.payload().baseVersionId() != null) {
                baseHash = repository
                        .requireVersion(userId, novelId, record.payload().baseVersionId())
                        .payload()
                        .contentHash();
            }
            DocumentDiff diff = DocumentDiffEngine.bind(
                    record.diff().withToVersionId(record.id()),
                    record.payload().documentType(),
                    record.chapterId(),
                    record.payload().baseVersionId(),
                    baseHash,
                    record.id());
            record = record.withDiff(diff);
        }
        return detail(record);
    }

    public VersionDiffResponse diffVersions(
            String userId,
            String novelId,
            String fromVersionId,
            String toVersionId) {
        ShortMediumVersion before = repository.requireVersion(userId, novelId, fromVersionId);
        ShortMediumVersion after = repository.requireVersion(userId, novelId, toVersionId);
        if (!before.payload().documentType().equals(after.payload().documentType())
                || !before.artifactKey().equals(after.artifactKey())) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_DIFF_TYPE_MISMATCH",
                    "只能比较同一文档的版本");
        }
        DocumentDiff diff = DocumentDiffEngine.bind(
                DocumentDiffEngine.build(
                        before.content(), after.content(), before.id(), after.id()),
                before.payload().documentType(),
                before.chapterId(),
                before.id(),
                before.payload().contentHash(),
                after.id());
        return contract(diff);
    }

    private static VersionDocumentBinding binding(DocumentType type, String chapterId) {
        if (type == null) {
            throw new ApiException(422, "VALIDATION_ERROR", "请求参数校验失败");
        }
        return new VersionDocumentBinding(type.getValue(), chapterId);
    }

    private static ShortMediumVersion current(List<ShortMediumVersion> versions) {
        return versions.stream()
                .filter(version -> "applied".equals(version.status()))
                .max(Comparator.comparingInt(ShortMediumVersion::versionNumber))
                .orElse(null);
    }

    private static ShortMediumVersion find(
            List<ShortMediumVersion> versions, String versionId) {
        return versions.stream()
                .filter(version -> version.id().equals(versionId))
                .findFirst()
                .orElseThrow(() -> new ApiException(
                        404,
                        "SHORT_MEDIUM_VERSION_NOT_FOUND",
                        "中短篇版本不存在"));
    }

    private static void requireCurrentBase(
            ShortMediumVersion current, String requestedBaseVersionId) {
        String currentId = current == null ? null : current.id();
        if (!Objects.equals(requestedBaseVersionId, currentId)) {
            java.util.Map<String, Object> details = new java.util.LinkedHashMap<>();
            details.put("currentVersionId", currentId);
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_BASE_VERSION_CONFLICT",
                    "当前版本已经变化，请重新预览后再操作",
                    details);
        }
    }

    private static void requireClean(
            ShortMediumVersionTransaction transaction, ShortMediumVersion current) {
        String expected = current == null
                ? ShortMediumText.sha256("")
                : current.payload().contentHash();
        if (!ShortMediumText.sha256(transaction.document().content()).equals(expected)) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_WORK_DRAFT_DIRTY",
                    "工作稿存在未提交修改，请先提交或放弃修改");
        }
    }

    private static void requireConfirmation(String provided, String actual) {
        if (!Objects.equals(provided, actual)) {
            throw new ApiException(
                    409,
                    "SHORT_MEDIUM_CONFIRMATION_CONFLICT",
                    "版本或工作稿已变化，请重新查看差异后再确认");
        }
    }

    private static int nextVersionNumber(List<ShortMediumVersion> versions) {
        return versions.stream()
                        .mapToInt(ShortMediumVersion::versionNumber)
                        .max()
                        .orElse(0)
                + 1;
    }

    private static boolean sameInstant(OffsetDateTime first, OffsetDateTime second) {
        return first != null && second != null && first.toInstant().equals(second.toInstant());
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static VersionDetailResponse detail(ShortMediumVersion value) {
        VersionDetailResponse result = new VersionDetailResponse();
        result.setId(value.id());
        result.setNovelId(value.novelId());
        result.setChapterId(value.chapterId());
        result.setArtifactKey(value.artifactKey());
        result.setStatus(VersionStatus.fromValue(value.status()));
        result.setSummary(value.summary());
        result.setPayload(contract(value.payload()));
        result.setDocumentType(DocumentType.fromValue(value.payload().documentType()));
        result.setVersionNumber(value.versionNumber());
        result.setSource(VersionSource.fromValue(value.payload().source()));
        result.setContent(value.content());
        result.setContentHash(value.payload().contentHash());
        result.setBaseVersionId(value.payload().baseVersionId());
        result.setSourceOutlineVersionId(value.payload().sourceOutlineVersionId());
        result.setRestoredFromVersionId(value.payload().restoredFromVersionId());
        result.setDiff(value.diff() == null ? null : contract(value.diff()));
        result.setCreatedByAgent(value.createdByAgent());
        result.setTaskId(value.taskId());
        result.setCreatedAt(value.createdAt());
        result.setUpdatedAt(value.updatedAt());
        result.setAppliedAt(value.appliedAt());
        return result;
    }

    private static VersionListItem listItem(ShortMediumVersion value) {
        VersionListItem result = new VersionListItem();
        result.setId(value.id());
        result.setDocumentType(DocumentType.fromValue(value.payload().documentType()));
        result.setVersionNumber(value.versionNumber());
        result.setStatus(VersionStatus.fromValue(value.status()));
        result.setSource(VersionSource.fromValue(value.payload().source()));
        result.setWordCount(ShortMediumText.count(value.content()));
        result.setBaseVersionId(value.payload().baseVersionId());
        result.setSourceOutlineVersionId(value.payload().sourceOutlineVersionId());
        result.setRestoredFromVersionId(value.payload().restoredFromVersionId());
        result.setSummary(value.summary());
        result.setCreatedByAgent(value.createdByAgent());
        result.setCreatedAt(value.createdAt());
        result.setUpdatedAt(value.updatedAt());
        result.setAppliedAt(value.appliedAt());
        return result;
    }

    private static VersionDiffResponse contract(DocumentDiff value) {
        VersionDiffResponse result = new VersionDiffResponse();
        result.setFromVersionId(value.fromVersionId());
        result.setToVersionId(value.toVersionId());
        result.setFromWordCount(value.fromWordCount());
        result.setToWordCount(value.toWordCount());
        result.setWordCountDelta(value.wordCountDelta());
        result.setConfirmationHash(value.confirmationHash());
        result.setBlocks(value.blocks().stream()
                .map(ShortMediumVersionService::contract)
                .toList());
        return result;
    }

    private static DiffBlock contract(DocumentDiffBlock value) {
        DiffBlock result = new DiffBlock();
        result.setType(DiffBlock.TypeEnum.fromValue(value.type()));
        result.setOldStart(value.oldStart());
        result.setOldEnd(value.oldEnd());
        result.setNewStart(value.newStart());
        result.setNewEnd(value.newEnd());
        result.setOldText(value.oldText());
        result.setNewText(value.newText());
        return result;
    }

    private static DocumentVersionPayload contract(ShortMediumVersionPayload value) {
        DocumentVersionPayload result = new DocumentVersionPayload(
                value.content(),
                value.contentHash(),
                DocumentType.fromValue(value.documentType()),
                DocumentVersionPayload.KindEnum.fromValue(value.kind()),
                VersionSource.fromValue(value.source()),
                value.versionNumber());
        result.setBaseVersionId(value.baseVersionId());
        result.setClientRequestId(value.clientRequestId());
        result.setRestoredFromVersionId(value.restoredFromVersionId());
        result.setSourceTaskId(value.sourceTaskId());
        result.setSourceJobId(value.sourceJobId());
        result.setSourceOutlineVersionId(value.sourceOutlineVersionId());
        result.setUserInstruction(value.userInstruction());
        result.setSourceKind(value.sourceKind() == null
                ? null
                : DocumentVersionPayload.SourceKindEnum.fromValue(value.sourceKind()));
        result.setSourceText(value.sourceText());
        result.setCreatedFromSelection(value.createdFromSelection());
        result.setSelectionStart(value.selectionStart());
        result.setSelectionEnd(value.selectionEnd());
        result.setSelectedTextHash(value.selectedTextHash());
        return result;
    }
}
