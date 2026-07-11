from __future__ import annotations

import logging
from typing import Any, Protocol

from ..errors import ApiError
from .schemas import CreateReferenceRequest, ReferenceMaterialResponse, UpdateReferenceRequest

logger = logging.getLogger(__name__)


class IndexSubmitter(Protocol):
    async def submit(self, novel_id: str, reference_id: str, content_hash: str) -> None: ...


class ReferenceRepositoryPort(Protocol):
    async def create_reference(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def list_references(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def update_reference(
        self, novel_id: str, user_id: str, reference_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_reference(self, novel_id: str, user_id: str, reference_id: str) -> None: ...
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
    async def prepare_reindex(self, novel_id: str, user_id: str, reference_id: str) -> str: ...
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
    ) -> ReferenceMaterialResponse:
        if not request.title.strip():
            raise ApiError(status_code=422, code="REFERENCE_TITLE_REQUIRED", message="标题不能为空")
        value = await self._repository.create_reference(novel_id, user_id, request.model_dump())
        if self._submitter is not None:
            try:
                await self._submitter.submit(
                    novel_id,
                    str(value["id"]),
                    str(value["contentHash"]),
                )
            except Exception:
                logger.warning("参考资料索引任务提交失败", extra={"referenceId": value["id"]})
        return ReferenceMaterialResponse.model_validate(value)

    async def update(
        self, user_id: str, novel_id: str, reference_id: str, request: UpdateReferenceRequest
    ) -> ReferenceMaterialResponse:
        fields = request.model_dump(exclude_unset=True)
        if not fields:
            raise ApiError(status_code=422, code="EMPTY_UPDATE", message="至少需要提供一个更新字段")
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
        value = await self._repository.update_reference(novel_id, user_id, reference_id, fields)
        if self._submitter is not None and {"title", "content"} & fields.keys():
            try:
                await self._submitter.submit(
                    novel_id,
                    reference_id,
                    str(value["contentHash"]),
                )
            except Exception:
                logger.warning("参考资料索引任务提交失败", extra={"referenceId": reference_id})
        return ReferenceMaterialResponse.model_validate(value)

    async def delete(self, user_id: str, novel_id: str, reference_id: str) -> None:
        await self._repository.delete_reference(novel_id, user_id, reference_id)

    async def reindex(self, user_id: str, novel_id: str, reference_id: str) -> None:
        if self._submitter is None:
            raise ApiError(
                status_code=503,
                code="RAG_INDEX_UNAVAILABLE",
                message="检索索引服务暂时不可用",
            )
        content_hash = await self._repository.prepare_reindex(novel_id, user_id, reference_id)
        try:
            await self._submitter.submit(novel_id, reference_id, content_hash)
        except Exception:
            await self._repository.mark_index_failed(
                novel_id, reference_id, content_hash, "索引任务提交失败"
            )
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
