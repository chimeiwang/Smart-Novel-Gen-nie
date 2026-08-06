from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol

from inkforge_contracts.jobs import AgentJobStatus

from ..errors import ApiError
from .rag import chunk_text_losslessly, validate_chunk_capacity
from .schemas import (
    CreateReferenceRequest,
    CreateReferenceResponse,
    DeleteReferenceImpactResponse,
    DeleteReferenceRequest,
    ReferenceMaterialResponse,
    ReindexReferenceRequest,
    UpdateReferenceRequest,
)

logger = logging.getLogger(__name__)


class IndexSubmitter(Protocol):
    async def submit(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        generation: datetime,
    ) -> AgentJobStatus: ...


class ReferenceRepositoryPort(Protocol):
    async def create_reference(
        self,
        novel_id: str,
        user_id: str,
        client_request_id: str,
        fields: dict[str, Any],
        *,
        index_enabled: bool = False,
    ) -> dict[str, Any]: ...
    async def list_references(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def update_reference(
        self,
        novel_id: str,
        user_id: str,
        reference_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime,
        *,
        index_enabled: bool = False,
    ) -> dict[str, Any]: ...
    async def delete_reference(
        self,
        novel_id: str,
        user_id: str,
        reference_id: str,
        expected_updated_at: datetime,
    ) -> dict[str, Any]: ...
    async def require_reference(
        self, novel_id: str, user_id: str, reference_id: str
    ) -> dict[str, Any]: ...
    async def replace_index(
        self,
        novel_id: str,
        reference_id: str,
        expected_content_hash: str,
        embeddings: list[list[float]],
    ) -> dict[str, Any]: ...
    async def prepare_reindex(
        self,
        novel_id: str,
        user_id: str,
        reference_id: str,
        expected_content_hash: str,
    ) -> dict[str, Any]: ...
    async def mark_index_failed(
        self,
        novel_id: str,
        reference_id: str,
        expected_content_hash: str,
        message: str,
    ) -> None: ...
    async def search(
        self, novel_id: str, user_id: str, embedding: list[float], top_k: int
    ) -> list[dict[str, Any]]: ...


class ReferenceService:
    def __init__(
        self, repository: ReferenceRepositoryPort, submitter: IndexSubmitter | None
    ) -> None:
        self._repository = repository
        self._submitter = submitter

    async def list_references(self, user_id: str, novel_id: str) -> list[ReferenceMaterialResponse]:
        values = await self._repository.list_references(novel_id, user_id)
        return [ReferenceMaterialResponse.model_validate(value) for value in values]

    async def create_reference(
        self, user_id: str, novel_id: str, request: CreateReferenceRequest
    ) -> CreateReferenceResponse:
        if not request.title.strip():
            raise ApiError(status_code=422, code="REFERENCE_TITLE_REQUIRED", message="标题不能为空")
        value = await self._repository.create_reference(
            novel_id,
            user_id,
            request.clientRequestId,
            request.model_dump(exclude={"clientRequestId"}),
            index_enabled=self._submitter is not None,
        )
        generation = value.pop("indexGeneration")
        if self._submitter is not None and value.get("effective") is True:
            try:
                await self._submitter.submit(
                    user_id,
                    novel_id,
                    str(value["id"]),
                    str(value["contentHash"]),
                    generation,
                )
            except Exception:
                logger.warning("参考资料索引任务提交失败", extra={"referenceId": value["id"]})
        return CreateReferenceResponse.model_validate(value)

    async def update(
        self, user_id: str, novel_id: str, reference_id: str, request: UpdateReferenceRequest
    ) -> ReferenceMaterialResponse:
        fields = request.model_dump(exclude={"expectedUpdatedAt"}, exclude_unset=True)
        if any(
            fields.get(field) is None for field in ("title", "type", "content") if field in fields
        ):
            raise ApiError(
                status_code=422,
                code="REFERENCE_FIELD_REQUIRED",
                message="标题、类型和正文不能为 null",
            )
        if "title" in fields and (fields["title"] is None or not fields["title"].strip()):
            raise ApiError(status_code=422, code="REFERENCE_TITLE_REQUIRED", message="标题不能为空")
        value = await self._repository.update_reference(
            novel_id,
            user_id,
            reference_id,
            fields,
            request.expectedUpdatedAt,
            index_enabled=self._submitter is not None,
        )
        index_refresh_required = value.pop("indexRefreshRequired", False)
        generation = value.pop("indexGeneration")
        if self._submitter is not None and index_refresh_required:
            try:
                await self._submitter.submit(
                    user_id,
                    novel_id,
                    reference_id,
                    str(value["contentHash"]),
                    generation,
                )
            except Exception:
                logger.warning("参考资料索引任务提交失败", extra={"referenceId": reference_id})
        return ReferenceMaterialResponse.model_validate(value)

    async def delete(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        request: DeleteReferenceRequest,
    ) -> DeleteReferenceImpactResponse:
        value = await self._repository.delete_reference(
            novel_id, user_id, reference_id, request.expectedUpdatedAt
        )
        return DeleteReferenceImpactResponse.model_validate(value)

    async def reindex(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        request: ReindexReferenceRequest,
    ) -> None:
        if self._submitter is None:
            raise ApiError(
                status_code=503,
                code="RAG_INDEX_UNAVAILABLE",
                message="检索索引服务暂时不可用",
            )
        intent = await self._repository.prepare_reindex(
            novel_id,
            user_id,
            reference_id,
            request.expectedContentHash,
        )
        try:
            await self._submitter.submit(
                user_id,
                novel_id,
                reference_id,
                str(intent["contentHash"]),
                intent["indexGeneration"],
            )
        except Exception:
            raise ApiError(
                status_code=503,
                code="RAG_INDEX_SUBMIT_FAILED",
                message="检索索引任务提交失败",
            ) from None

    async def complete_index(
        self,
        novel_id: str,
        reference_id: str,
        expected_content_hash: str,
        embeddings: list[list[float]],
    ) -> ReferenceMaterialResponse:
        value = await self._repository.replace_index(
            novel_id, reference_id, expected_content_hash, embeddings
        )
        return ReferenceMaterialResponse.model_validate(value)

    async def get_index_context(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        expected_content_hash: str,
    ) -> dict[str, Any]:
        value = await self._repository.require_reference(novel_id, user_id, reference_id)
        content = value.get("content")
        content_hash = value.get("contentHash")
        if not isinstance(content, str) or content_hash != expected_content_hash:
            raise ApiError(
                status_code=409,
                code="RAG_INDEX_STALE",
                message="参考资料内容已变化，需要重新提交索引任务",
            )
        return {
            "contentHash": expected_content_hash,
            "chunks": validate_chunk_capacity(chunk_text_losslessly(content)),
        }

    async def fail_index(
        self,
        novel_id: str,
        reference_id: str,
        expected_content_hash: str,
        message: str,
    ) -> None:
        del message
        await self._repository.mark_index_failed(
            novel_id, reference_id, expected_content_hash, "索引生成失败"
        )

    async def search(
        self, user_id: str, novel_id: str, embedding: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        return await self._repository.search(novel_id, user_id, embedding, top_k)
