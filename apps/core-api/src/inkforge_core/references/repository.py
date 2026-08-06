from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from inkforge_contracts.jobs import AgentJobStatus
from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..concurrency import command_resource_id, next_utc_timestamp, require_expected_updated_at
from ..db.models import Novel, RagChunk, RagDocument, ReferenceMaterial
from ..errors import ApiError
from .rag import (
    EMBEDDING_BATCH_SIZE,
    chunk_text_losslessly,
    content_sha256,
    normalize_embeddings,
    public_rag_error,
    search_statement,
    validate_chunk_capacity,
    validate_top_k,
    vector_literal,
)
from .rag_dispatcher import RagDispatchRecord

_REFERENCE_FIELDS = ("title", "type", "content", "sourceUrl")


@dataclass(frozen=True, slots=True)
class ReferenceMutation:
    action: Literal["create", "update", "delete"]
    fields: dict[str, Any]
    reference_id: str | None = None
    client_request_id: str | None = None
    expected_updated_at: datetime | None = None


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _database_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


class ReferenceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_references(self, novel_id: str, user_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            rows = (
                await session.execute(
                    select(ReferenceMaterial, RagDocument)
                    .outerjoin(
                        RagDocument,
                        (RagDocument.sourceType == "reference_material")
                        & (RagDocument.sourceId == ReferenceMaterial.id),
                    )
                    .where(ReferenceMaterial.novelId == novel_id)
                    .order_by(ReferenceMaterial.createdAt.asc(), ReferenceMaterial.id.asc())
                )
            ).all()
        return [
            self._dto(
                reference,
                document.status if isinstance(document, RagDocument) else None,
                cast(RagDocument | None, document),
            )
            for reference, document in rows
        ]

    async def create_reference(
        self,
        novel_id: str,
        user_id: str,
        client_request_id: str,
        fields: dict[str, Any],
        *,
        index_enabled: bool = False,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                return await self._create_reference_in_session(
                    session,
                    novel_id,
                    user_id,
                    client_request_id,
                    fields,
                    index_enabled=index_enabled,
                )

    async def require_reference(
        self, novel_id: str, user_id: str, reference_id: str
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            reference = await self._find(session, novel_id, reference_id)
            if reference is None:
                raise self._not_found()
            document = await self._document(session, reference_id)
        return self._dto(reference, document.status if document else None, document)

    async def update_reference(
        self,
        novel_id: str,
        user_id: str,
        reference_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime,
        *,
        index_enabled: bool = False,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                return await self._update_reference_in_session(
                    session,
                    novel_id,
                    reference_id,
                    fields,
                    expected_updated_at,
                    index_enabled=index_enabled,
                )

    async def apply_reference_mutations(
        self,
        novel_id: str,
        user_id: str,
        mutations: list[ReferenceMutation],
        *,
        index_enabled: bool = False,
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                results: list[dict[str, Any]] = []
                for mutation in mutations:
                    if mutation.action == "create":
                        if mutation.client_request_id is None:
                            raise ValueError("references create 缺少 clientRequestId")
                        result = await self._create_reference_in_session(
                            session,
                            novel_id,
                            user_id,
                            mutation.client_request_id,
                            mutation.fields,
                            index_enabled=index_enabled,
                        )
                    else:
                        if mutation.reference_id is None:
                            raise ValueError(f"references {mutation.action} 缺少 referenceId")
                        if mutation.expected_updated_at is None:
                            raise ValueError(
                                f"references {mutation.action} 缺少 expectedUpdatedAt"
                            )
                        if mutation.action == "update":
                            result = await self._update_reference_in_session(
                                session,
                                novel_id,
                                mutation.reference_id,
                                mutation.fields,
                                mutation.expected_updated_at,
                                index_enabled=index_enabled,
                            )
                        else:
                            result = await self._delete_reference_in_session(
                                session,
                                novel_id,
                                mutation.reference_id,
                                mutation.expected_updated_at,
                            )
                    results.append(result)
                return results

    async def _create_reference_in_session(
        self,
        session: AsyncSession,
        novel_id: str,
        user_id: str,
        client_request_id: str,
        fields: dict[str, Any],
        *,
        index_enabled: bool,
    ) -> dict[str, Any]:
        reference_id = command_resource_id(
            "reference", user_id, novel_id, client_request_id
        )
        create_fields = {name: fields.get(name) for name in _REFERENCE_FIELDS}
        reference = cast(
            ReferenceMaterial | None,
            await session.scalar(
                select(ReferenceMaterial)
                .where(ReferenceMaterial.id == reference_id)
                .with_for_update()
            ),
        )
        if reference is not None:
            current_fields = {name: getattr(reference, name) for name in _REFERENCE_FIELDS}
            if (
                reference.novelId == novel_id
                and _utc(reference.createdAt) == _utc(reference.updatedAt)
                and current_fields == create_fields
            ):
                document = await self._document(session, reference_id)
                return {
                    **self._dto(
                        reference,
                        document.status if document is not None else None,
                        document,
                    ),
                    "effective": False,
                }
            raise ApiError(
                status_code=409,
                code="RESOURCE_CREATE_CONFLICT",
                message="创建请求已绑定其他内容",
            )
        created_at = _database_utc(next_utc_timestamp(None))
        reference = ReferenceMaterial(
            id=reference_id,
            novelId=novel_id,
            **create_fields,
            createdAt=created_at,
            updatedAt=created_at,
        )
        document = RagDocument(
            novelId=novel_id,
            sourceType="reference_material",
            sourceId=reference_id,
            title=reference.title,
            contentHash=content_sha256(reference.content),
            status="disabled",
            errorMessage=("等待重新索引" if index_enabled else "检索索引服务未配置"),
            createdAt=created_at,
            updatedAt=created_at,
        )
        session.add_all((reference, document))
        await session.flush()
        return {
            **self._dto(reference, document.status, document),
            "effective": True,
        }

    async def _update_reference_in_session(
        self,
        session: AsyncSession,
        novel_id: str,
        reference_id: str,
        fields: dict[str, Any],
        expected_updated_at: datetime,
        *,
        index_enabled: bool,
    ) -> dict[str, Any]:
        reference, document = await self._lock_reference_and_document(
            session, novel_id, reference_id
        )
        current_updated_at = _utc(reference.updatedAt)
        require_expected_updated_at(
            current_updated_at,
            expected_updated_at,
            code="REFERENCE_VERSION_CONFLICT",
        )
        changed_fields = {
            name: requested
            for name, requested in fields.items()
            if getattr(reference, name) != requested
        }
        if not changed_fields:
            return {
                **self._dto(reference, document.status, document),
                "indexRefreshRequired": False,
            }
        for name, requested in changed_fields.items():
            setattr(reference, name, requested)
        reference.updatedAt = _database_utc(next_utc_timestamp(current_updated_at))
        index_refresh_required = bool({"title", "content"} & changed_fields.keys())
        if index_refresh_required:
            await session.execute(delete(RagChunk).where(RagChunk.documentId == document.id))
            document.title = reference.title
            document.contentHash = content_sha256(reference.content)
            document.status = "disabled"
            document.errorMessage = (
                "等待重新索引" if index_enabled else "检索索引服务未配置"
            )
        await session.flush()
        return {
            **self._dto(reference, document.status, document),
            "indexRefreshRequired": index_refresh_required,
        }

    async def _delete_reference_in_session(
        self,
        session: AsyncSession,
        novel_id: str,
        reference_id: str,
        expected_updated_at: datetime,
    ) -> dict[str, Any]:
        reference, document = await self._lock_reference_and_document(
            session, novel_id, reference_id
        )
        require_expected_updated_at(
            _utc(reference.updatedAt),
            expected_updated_at,
            code="REFERENCE_VERSION_CONFLICT",
        )
        chunk_count = int(
            await session.scalar(
                select(func.count()).select_from(RagChunk).where(
                    RagChunk.documentId == document.id
                )
            )
            or 0
        )
        await session.execute(delete(RagChunk).where(RagChunk.documentId == document.id))
        document_outcome = cast(
            CursorResult[Any],
            await session.execute(delete(RagDocument).where(RagDocument.id == document.id)),
        )
        reference_outcome = cast(
            CursorResult[Any],
            await session.execute(
                delete(ReferenceMaterial).where(
                    ReferenceMaterial.id == reference_id,
                    ReferenceMaterial.novelId == novel_id,
                )
            ),
        )
        if reference_outcome.rowcount != 1:
            raise self._not_found()
        return {
            "deletedType": "reference",
            "deletedId": reference_id,
            "affected": {
                "reference": 1,
                "ragDocuments": int(document_outcome.rowcount or 0),
                "ragChunks": chunk_count,
            },
        }

    async def list_pending_rag_documents(self, limit: int) -> list[RagDispatchRecord]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(RagDocument, ReferenceMaterial, Novel.userId)
                    .join(
                        ReferenceMaterial,
                        and_(
                            RagDocument.sourceType == "reference_material",
                            RagDocument.sourceId == ReferenceMaterial.id,
                        ),
                    )
                    .join(Novel, Novel.id == ReferenceMaterial.novelId)
                    .where(
                        RagDocument.status == "disabled",
                        RagDocument.errorMessage == "等待重新索引",
                    )
                    .order_by(RagDocument.updatedAt.asc(), RagDocument.id.asc())
                    .limit(limit)
                )
            ).all()
        records: list[RagDispatchRecord] = []
        for document, reference, user_id in rows:
            current_hash = content_sha256(reference.content)
            if document.contentHash != current_hash:
                continue
            records.append(
                RagDispatchRecord(
                    user_id=user_id,
                    novel_id=reference.novelId,
                    reference_id=reference.id,
                    content_hash=current_hash,
                )
            )
        return records

    async def delete_reference(
        self,
        novel_id: str,
        user_id: str,
        reference_id: str,
        expected_updated_at: datetime,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                return await self._delete_reference_in_session(
                    session, novel_id, reference_id, expected_updated_at
                )

    async def replace_index(
        self,
        novel_id: str,
        reference_id: str,
        expected_content_hash: str,
        embeddings: list[list[float]],
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                reference, document = await self._lock_reference_and_document(
                    session, novel_id, reference_id
                )
                self._require_current_hash(reference, document, expected_content_hash)
                chunks = validate_chunk_capacity(chunk_text_losslessly(reference.content))
                if chunks:
                    normalized = normalize_embeddings(embeddings)
                else:
                    if embeddings:
                        raise ApiError(
                            status_code=422,
                            code="EMBEDDING_COUNT_MISMATCH",
                            message="嵌入向量数量与资料分块数量不一致",
                        )
                    normalized = []
                if len(chunks) != len(normalized):
                    raise ApiError(
                        status_code=422,
                        code="EMBEDDING_COUNT_MISMATCH",
                        message="嵌入向量数量与资料分块数量不一致",
                    )
                await session.execute(delete(RagChunk).where(RagChunk.documentId == document.id))
                for offset in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
                    values = [
                        {
                            "documentId": document.id,
                            "novelId": novel_id,
                            "chunkIndex": index,
                            "text": chunks[index],
                            "charCount": len(chunks[index]),
                            "embeddingDimension": len(normalized[index]),
                            "embedding": normalized[index],
                        }
                        for index in range(offset, min(offset + EMBEDDING_BATCH_SIZE, len(chunks)))
                    ]
                    await session.execute(insert(RagChunk), values)
                document.status = "ready"
                document.errorMessage = None
                document.contentHash = content_sha256(reference.content)
                result = self._dto(reference, document.status, document)
        return result

    async def prepare_reindex(
        self,
        novel_id: str,
        user_id: str,
        reference_id: str,
        expected_content_hash: str,
    ) -> str:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                reference, document = await self._lock_reference_and_document(
                    session, novel_id, reference_id
                )
                self._require_current_hash(reference, document, expected_content_hash)
                await session.execute(delete(RagChunk).where(RagChunk.documentId == document.id))
                document.title = reference.title
                document.contentHash = expected_content_hash
                document.status = "disabled"
                document.errorMessage = "等待重新索引"
                return expected_content_hash

    async def mark_index_failed(
        self,
        novel_id: str,
        reference_id: str,
        expected_content_hash: str,
        message: str,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                reference, document = await self._lock_reference_and_document(
                    session, novel_id, reference_id
                )
                self._require_current_hash(reference, document, expected_content_hash)
                self._require_failure_target(document)
                document.status = "failed"
                document.errorMessage = message

    async def mark_rag_dispatch_terminal(
        self,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        agent_status: AgentJobStatus,
    ) -> None:
        if agent_status in {"queued", "running"}:
            return
        async with self._session_factory() as session:
            async with session.begin():
                reference, document = await self._lock_reference_and_document(
                    session, novel_id, reference_id
                )
                if not self._matches_pending_dispatch(
                    reference, document, content_hash
                ):
                    return
                document.status = "failed"
                document.errorMessage = f"智能体索引任务已终止：{agent_status}"

    async def search(
        self, novel_id: str, user_id: str, embedding: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        vector = normalize_embeddings([embedding])[0]
        top_k = validate_top_k(top_k)
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            rows = (
                (
                    await session.execute(
                        search_statement(),
                        {
                            "novel_id": novel_id,
                            "source_type": "reference_material",
                            "dimension": len(vector),
                            "query_vector": vector_literal(vector),
                            "top_k": top_k,
                        },
                    )
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    @staticmethod
    async def _require_owner(session: AsyncSession, novel_id: str, user_id: str) -> None:
        owner = await session.scalar(select(Novel.userId).where(Novel.id == novel_id))
        if owner is None or owner != user_id:
            raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")

    @staticmethod
    async def _lock_novel(session: AsyncSession, novel_id: str) -> None:
        value = await session.scalar(
            select(Novel.id).where(Novel.id == novel_id).with_for_update()
        )
        if value is None:
            raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")

    @staticmethod
    async def _find(
        session: AsyncSession, novel_id: str, reference_id: str
    ) -> ReferenceMaterial | None:
        return cast(
            ReferenceMaterial | None,
            await session.scalar(
                select(ReferenceMaterial).where(
                    ReferenceMaterial.id == reference_id,
                    ReferenceMaterial.novelId == novel_id,
                )
            ),
        )

    @staticmethod
    async def _document(session: AsyncSession, reference_id: str) -> RagDocument | None:
        return cast(
            RagDocument | None,
            await session.scalar(
                select(RagDocument).where(
                    RagDocument.sourceType == "reference_material",
                    RagDocument.sourceId == reference_id,
                )
            ),
        )

    @classmethod
    async def _lock_reference_and_document(
        cls, session: AsyncSession, novel_id: str, reference_id: str
    ) -> tuple[ReferenceMaterial, RagDocument]:
        reference = cast(
            ReferenceMaterial | None,
            await session.scalar(
                select(ReferenceMaterial)
                .where(
                    ReferenceMaterial.id == reference_id,
                    ReferenceMaterial.novelId == novel_id,
                )
                .with_for_update()
            ),
        )
        if reference is None:
            raise cls._not_found()
        document = cast(
            RagDocument | None,
            await session.scalar(
                select(RagDocument)
                .where(
                    RagDocument.sourceType == "reference_material",
                    RagDocument.sourceId == reference_id,
                    RagDocument.novelId == novel_id,
                )
                .with_for_update()
            ),
        )
        if document is None:
            raise ApiError(
                status_code=409,
                code="RAG_DOCUMENT_MISSING",
                message="检索文档不存在",
            )
        return reference, document

    @classmethod
    def _require_current_hash(
        cls,
        reference: ReferenceMaterial,
        document: RagDocument,
        expected_content_hash: str,
    ) -> None:
        if (
            content_sha256(reference.content) != expected_content_hash
            or document.contentHash != expected_content_hash
        ):
            raise cls._stale_index()

    @classmethod
    def _require_failure_target(cls, document: RagDocument) -> None:
        if document.status != "disabled":
            raise cls._stale_index()

    @staticmethod
    def _matches_pending_dispatch(
        reference: ReferenceMaterial,
        document: RagDocument,
        expected_content_hash: str,
    ) -> bool:
        return (
            content_sha256(reference.content) == expected_content_hash
            and document.contentHash == expected_content_hash
            and document.status == "disabled"
            and document.errorMessage == "等待重新索引"
        )

    @staticmethod
    def _dto(
        reference: ReferenceMaterial,
        status: str | None,
        document: RagDocument | None = None,
    ) -> dict[str, Any]:
        return {
            "id": reference.id,
            "title": reference.title,
            "type": reference.type,
            "content": reference.content,
            "sourceUrl": reference.sourceUrl,
            "ragStatus": status or "disabled",
            "contentHash": document.contentHash if document else content_sha256(reference.content),
            "errorMessage": (
                public_rag_error(document.status, document.errorMessage) if document else None
            ),
            "createdAt": _utc(reference.createdAt),
            "updatedAt": _utc(reference.updatedAt),
        }

    @staticmethod
    def _not_found() -> ApiError:
        return ApiError(status_code=404, code="REFERENCE_NOT_FOUND", message="参考资料不存在")

    @staticmethod
    def _stale_index() -> ApiError:
        return ApiError(
            status_code=409,
            code="RAG_INDEX_STALE",
            message="参考资料内容已变化，拒绝写入过期索引结果",
        )
