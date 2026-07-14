from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import and_, delete, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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
        fields: dict[str, Any],
        *,
        index_enabled: bool = False,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                reference = ReferenceMaterial(novelId=novel_id, **fields)
                session.add(reference)
                await session.flush()
                document = RagDocument(
                    novelId=novel_id,
                    sourceType="reference_material",
                    sourceId=reference.id,
                    title=reference.title,
                    contentHash=content_sha256(reference.content),
                    status="disabled",
                    errorMessage=("等待重新索引" if index_enabled else "检索索引服务未配置"),
                )
                session.add(document)
                await session.flush()
                result = self._dto(reference, document.status, document)
        return result

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
        *,
        index_enabled: bool = False,
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                reference = await self._find(session, novel_id, reference_id)
                if reference is None:
                    raise self._not_found()
                changed_index_input = bool({"title", "content"} & fields.keys())
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(ReferenceMaterial)
                        .where(
                            ReferenceMaterial.id == reference_id,
                            ReferenceMaterial.novelId == novel_id,
                        )
                        .values(**fields)
                    ),
                )
                if outcome.rowcount != 1:
                    raise self._not_found()
                await session.refresh(reference)
                document = await self._document(session, reference_id)
                if document is None:
                    document = RagDocument(
                        novelId=novel_id,
                        sourceType="reference_material",
                        sourceId=reference_id,
                        title=reference.title,
                        contentHash=content_sha256(reference.content),
                        status="disabled",
                        errorMessage=(
                            "等待重新索引" if index_enabled else "检索索引服务未配置"
                        ),
                    )
                    session.add(document)
                    await session.flush()
                elif changed_index_input:
                    await session.execute(
                        delete(RagChunk).where(RagChunk.documentId == document.id)
                    )
                    document.title = reference.title
                    document.contentHash = content_sha256(reference.content)
                    document.status = "disabled"
                    document.errorMessage = (
                        "等待重新索引" if index_enabled else "检索索引服务未配置"
                    )
                result = self._dto(reference, document.status, document)
        return result

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

    async def delete_reference(self, novel_id: str, user_id: str, reference_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                _, document = await self._lock_reference_and_document(
                    session, novel_id, reference_id
                )
                await session.execute(delete(RagDocument).where(RagDocument.id == document.id))
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        delete(ReferenceMaterial).where(
                            ReferenceMaterial.id == reference_id,
                            ReferenceMaterial.novelId == novel_id,
                        )
                    ),
                )
                if outcome.rowcount != 1:
                    raise self._not_found()

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

    async def prepare_reindex(self, novel_id: str, user_id: str, reference_id: str) -> str:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                reference, document = await self._lock_reference_and_document(
                    session, novel_id, reference_id
                )
                current_hash = content_sha256(reference.content)
                await session.execute(delete(RagChunk).where(RagChunk.documentId == document.id))
                document.title = reference.title
                document.contentHash = current_hash
                document.status = "disabled"
                document.errorMessage = "等待重新索引"
                return current_hash

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
