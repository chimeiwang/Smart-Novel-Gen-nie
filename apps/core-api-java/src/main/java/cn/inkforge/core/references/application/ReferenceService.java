package cn.inkforge.core.references.application;

import cn.inkforge.contracts.api.CompleteReferenceIndexRequest;
import cn.inkforge.contracts.api.CreateReferenceRequest;
import cn.inkforge.contracts.api.CreateReferenceResponse;
import cn.inkforge.contracts.api.DeleteReferenceAffected;
import cn.inkforge.contracts.api.DeleteReferenceImpactResponse;
import cn.inkforge.contracts.api.DeleteReferenceRequest;
import cn.inkforge.contracts.api.FailReferenceIndexRequest;
import cn.inkforge.contracts.api.RagSearchRequest;
import cn.inkforge.contracts.api.RagSearchResult;
import cn.inkforge.contracts.api.ReferenceIndexContextRequest;
import cn.inkforge.contracts.api.ReferenceIndexContextResponse;
import cn.inkforge.contracts.api.ReferenceMaterialResponse;
import cn.inkforge.contracts.api.ReindexAcceptedResponse;
import cn.inkforge.contracts.api.ReindexReferenceRequest;
import cn.inkforge.contracts.api.UpdateReferenceRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.patch.PatchField;
import cn.inkforge.core.references.domain.RagIndexIntent;
import cn.inkforge.core.references.domain.RagRules;
import cn.inkforge.core.references.domain.RagSearchHit;
import cn.inkforge.core.references.domain.ReferenceCreateResult;
import cn.inkforge.core.references.domain.ReferenceData;
import cn.inkforge.core.references.domain.ReferenceDeleteImpact;
import cn.inkforge.core.references.domain.ReferencePatch;
import cn.inkforge.core.references.domain.ReferenceSnapshot;
import cn.inkforge.core.references.domain.ReferenceUpdateResult;
import java.util.List;
import org.openapitools.jackson.nullable.JsonNullable;

/** 参考资料公共命令和 Agent 索引回调的应用服务。 */
public final class ReferenceService {

    private final ReferenceRepository repository;
    private final RagIndexSubmitter submitter;

    public ReferenceService(ReferenceRepository repository, RagIndexSubmitter submitter) {
        this.repository = java.util.Objects.requireNonNull(repository);
        this.submitter = submitter;
    }

    public List<ReferenceMaterialResponse> list(String userId, String novelId) {
        return repository.list(novelId, userId).stream()
                .map(ReferenceService::response)
                .toList();
    }

    public CreateReferenceResponse create(
            String userId, String novelId, CreateReferenceRequest request) {
        requireTitle(request.getTitle());
        ReferenceData data = new ReferenceData(
                request.getTitle(),
                request.getType().getValue(),
                request.getContent(),
                nullableValue(request.getSourceUrl()));
        ReferenceCreateResult result = repository.create(
                novelId,
                userId,
                request.getClientRequestId(),
                data,
                submitter != null);
        if (submitter != null && result.effective()) {
            submitAutomatically(userId, novelId, result.reference(), result.indexGeneration());
        }
        ReferenceSnapshot value = result.reference();
        return new CreateReferenceResponse(
                        value.content(),
                        value.contentHash(),
                        result.effective(),
                        value.errorMessage(),
                        value.id(),
                        CreateReferenceResponse.RagStatusEnum.fromValue(value.ragStatus()),
                        value.title(),
                        CreateReferenceResponse.TypeEnum.fromValue(value.type()))
                .sourceUrl(value.sourceUrl())
                .createdAt(value.createdAt())
                .updatedAt(value.updatedAt());
    }

    public ReferenceMaterialResponse update(
            String userId,
            String novelId,
            String referenceId,
            UpdateReferenceRequest request) {
        ReferencePatch patch = new ReferencePatch(
                PatchField.from(request.getTitle()),
                PatchField.from(request.getType()).map(UpdateReferenceRequest.TypeEnum::getValue),
                PatchField.from(request.getContent()),
                PatchField.from(request.getSourceUrl()));
        if (patch.empty()) {
            throw new ApiException(422, "EMPTY_UPDATE", "至少需要提供一个更新字段");
        }
        if ((patch.title().present() && patch.title().value() == null)
                || (patch.type().present() && patch.type().value() == null)
                || (patch.content().present() && patch.content().value() == null)) {
            throw new ApiException(422, "REFERENCE_FIELD_REQUIRED", "标题、类型和正文不能为 null");
        }
        if (patch.title().present()) {
            requireTitle(patch.title().value());
        }
        ReferenceUpdateResult result = repository.update(
                novelId,
                userId,
                referenceId,
                patch,
                request.getExpectedUpdatedAt(),
                submitter != null);
        if (submitter != null && result.indexRefreshRequired()) {
            submitAutomatically(userId, novelId, result.reference(), result.indexGeneration());
        }
        return response(result.reference());
    }

    public DeleteReferenceImpactResponse delete(
            String userId,
            String novelId,
            String referenceId,
            DeleteReferenceRequest request) {
        ReferenceDeleteImpact impact = repository.delete(
                novelId, userId, referenceId, request.getExpectedUpdatedAt());
        DeleteReferenceAffected affected = new DeleteReferenceAffected(
                impact.ragChunks(),
                DeleteReferenceAffected.RagDocumentsEnum.fromValue(impact.ragDocuments()),
                1);
        return new DeleteReferenceImpactResponse(affected, impact.referenceId(), "reference");
    }

    public ReindexAcceptedResponse reindex(
            String userId,
            String novelId,
            String referenceId,
            ReindexReferenceRequest request) {
        if (submitter == null) {
            throw new ApiException(503, "RAG_INDEX_UNAVAILABLE", "检索索引服务暂时不可用");
        }
        RagIndexIntent intent = repository.prepareReindex(
                novelId, userId, referenceId, request.getExpectedContentHash());
        try {
            submitter.submit(
                    userId,
                    novelId,
                    referenceId,
                    intent.contentHash(),
                    intent.indexGeneration());
        } catch (RuntimeException exception) {
            throw new ApiException(503, "RAG_INDEX_SUBMIT_FAILED", "检索索引任务提交失败");
        }
        return new ReindexAcceptedResponse(true);
    }

    public ReferenceMaterialResponse completeIndex(
            String novelId, String referenceId, CompleteReferenceIndexRequest request) {
        List<List<java.math.BigDecimal>> embeddings = request.getEmbeddings();
        // 空正文的合法索引结果是空向量列表，其余批次先在应用边界验证。
        if (!embeddings.isEmpty()) {
            RagRules.embeddings(embeddings);
        }
        return response(repository.replaceIndex(
                novelId,
                referenceId,
                request.getTaskId(),
                request.getRunId(),
                request.getExpectedContentHash(),
                embeddings));
    }

    public ReferenceIndexContextResponse indexContext(
            String novelId, String referenceId, ReferenceIndexContextRequest request) {
        ReferenceSnapshot value = repository.requireIndexContext(
                novelId,
                request.getUserId(),
                referenceId,
                request.getTaskId(),
                request.getRunId(),
                request.getExpectedContentHash());
        if (!request.getExpectedContentHash().equals(value.contentHash())) {
            throw stale();
        }
        return new ReferenceIndexContextResponse(
                RagRules.chunks(value.content()), request.getExpectedContentHash());
    }

    public void failIndex(
            String novelId, String referenceId, FailReferenceIndexRequest request) {
        repository.markIndexFailed(
                novelId,
                referenceId,
                request.getTaskId(),
                request.getRunId(),
                request.getExpectedContentHash(),
                "索引生成失败");
    }

    public List<RagSearchResult> search(
            String userId, String novelId, RagSearchRequest request) {
        RagRules.embeddings(List.of(request.getQueryEmbedding()));
        int topK = RagRules.topK(request.getTopK());
        return repository.search(novelId, userId, request.getQueryEmbedding(), topK).stream()
                .map(ReferenceService::searchResult)
                .toList();
    }

    private void submitAutomatically(
            String userId,
            String novelId,
            ReferenceSnapshot reference,
            java.time.OffsetDateTime generation) {
        try {
            submitter.submit(
                    userId,
                    novelId,
                    reference.id(),
                    reference.contentHash(),
                    generation);
        } catch (RuntimeException ignored) {
            // 意图已经落库，后台投递器会继续领取；创建或更新本身不能因此失败。
        }
    }

    private static ReferenceMaterialResponse response(ReferenceSnapshot value) {
        return new ReferenceMaterialResponse(
                        value.content(),
                        value.contentHash(),
                        value.errorMessage(),
                        value.id(),
                        ReferenceMaterialResponse.RagStatusEnum.fromValue(value.ragStatus()),
                        value.title(),
                        ReferenceMaterialResponse.TypeEnum.fromValue(value.type()))
                .sourceUrl(value.sourceUrl())
                .createdAt(value.createdAt())
                .updatedAt(value.updatedAt());
    }

    private static RagSearchResult searchResult(RagSearchHit value) {
        return new RagSearchResult(
                value.chunkIndex(),
                value.score(),
                value.sourceId(),
                value.text(),
                value.title());
    }

    private static void requireTitle(String value) {
        if (value == null || value.strip().isEmpty()) {
            throw new ApiException(422, "REFERENCE_TITLE_REQUIRED", "标题不能为空");
        }
    }

    private static <T> T nullableValue(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static ApiException stale() {
        return new ApiException(409, "RAG_INDEX_STALE", "参考资料内容已变化，需要重新提交索引任务");
    }
}
