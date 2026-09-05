"""索引执行只重建已冻结完整原文，不读取 Core 当前资料或创建后续批次。"""

from inkforge_contracts.execution import ExecutionStepRequest
from inkforge_contracts.rag_execution import RagEmbeddingContextV2, RagEmbeddingStepInput


def rag_context(request: ExecutionStepRequest) -> RagEmbeddingContextV2:
    if (
        request.workflow != "rag"
        or request.operation != "embedding"
        or request.purpose != "generation"
        or request.novelId is None
        or request.lane != "batch_media"
        or request.artifactId is not None
        or request.artifactRevision is not None
        or request.modelProfile.profile != "rag.embedding.v2"
        or request.modelProfile.version != 2
        or request.outputSchema.name != "output.embedding_batch.v2"
        or request.outputSchema.version != 2
        or request.evidenceBundle.policyVersion != "evidence.rag.reference_chunks.v1"
    ):
        raise ValueError("索引 Step 必须使用精确小说级 embedding 资产")
    value = RagEmbeddingStepInput.model_validate(request.input)
    items = request.evidenceBundle.items
    if len(items) != 1:
        raise ValueError("索引必须读取唯一完整冻结来源")
    item = items[0]
    if (
        item.resourceType != "rag_embedding_context"
        or not item.exists
        or item.contentType != "json"
        or item.range is not None
    ):
        raise ValueError("索引必须使用完整 JSON 原文来源")
    context = RagEmbeddingContextV2.model_validate(item.contentJson)
    if item.resourceId != context.referenceId:
        raise ValueError("索引来源与资料身份不匹配")
    context.batch(value.batchIndex)
    return context
