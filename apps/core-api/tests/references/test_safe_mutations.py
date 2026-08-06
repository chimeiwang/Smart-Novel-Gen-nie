from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from inkforge_contracts.jobs import AgentJobAccepted, AgentJobRequest
from inkforge_core.agent_client import RagAgentSubmitter
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.concurrency import command_resource_id
from inkforge_core.db.models import (
    Novel,
    RagChunk,
    RagDocument,
    ReferenceMaterial,
    User,
    WritingStyle,
)
from inkforge_core.errors import ApiError
from inkforge_core.references import schemas
from inkforge_core.references.rag import content_sha256
from inkforge_core.references.repository import ReferenceMutation, ReferenceRepository
from pydantic import ValidationError
from sqlalchemy import DefaultClause, MetaData, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


async def _create_database(path: Path) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        execution_options={"schema_translate_map": {"public": None}},
    )
    async with engine.begin() as connection:
        metadata = MetaData()
        for table in (
            User.__table__,
            WritingStyle.__table__,
            Novel.__table__,
            ReferenceMaterial.__table__,
            RagDocument.__table__,
            RagChunk.__table__,
        ):
            table.to_metadata(metadata)
        metadata.tables["public.WritingStyle"].c.sourceType.server_default = DefaultClause(
            text("'manual'")
        )
        metadata.tables["public.RagDocument"].c.status.server_default = DefaultClause(
            text("'disabled'")
        )
        await connection.run_sync(metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_novels(factory: async_sessionmaker) -> None:
    async with factory() as session, session.begin():
        session.add_all(
            [
                User(id="user-1", username="user-1", passwordHash="固定哈希"),
                User(id="user-2", username="user-2", passwordHash="固定哈希"),
                Novel(id="novel-1", userId="user-1", name="作品一"),
                Novel(id="novel-2", userId="user-1", name="作品二"),
                Novel(id="novel-other", userId="user-2", name="他人作品"),
            ]
        )


def _fields(content: str = "初始正文") -> dict[str, Any]:
    return {
        "title": "参考资料",
        "type": "note",
        "content": content,
        "sourceUrl": None,
    }


async def _rag_identity(
    reference_id: str, content_hash: str, generation: datetime
) -> tuple[str, str]:
    captured: list[AgentJobRequest] = []

    class Client:
        async def submit(self, request: AgentJobRequest) -> AgentJobAccepted:
            captured.append(request)
            return AgentJobAccepted(
                jobId=request.jobId,
                runId=request.runId,
                taskId=request.taskId,
                status="queued",
            )

    await RagAgentSubmitter(Client()).submit(  # type: ignore[arg-type]
        "user-1",
        "novel-1",
        reference_id,
        content_hash,
        generation,
    )
    return captured[0].taskId, captured[0].runId


async def _advance_to_second_generation(
    factory: async_sessionmaker,
    repository: ReferenceRepository,
    created: dict[str, Any],
) -> tuple[tuple[str, str], tuple[str, str]]:
    old_identity = await _rag_identity(
        created["id"], created["contentHash"], created["indexGeneration"]
    )
    async with factory() as session, session.begin():
        document = await session.scalar(
            select(RagDocument).where(RagDocument.sourceId == created["id"])
        )
        assert document is not None
        document.status = "failed"
        document.errorMessage = "上一代失败"
    intent = await repository.prepare_reindex(
        "novel-1", "user-1", created["id"], created["contentHash"]
    )
    new_identity = await _rag_identity(
        created["id"], created["contentHash"], intent["indexGeneration"]
    )
    assert old_identity != new_identity
    return old_identity, new_identity


def test_reference_mutation_dtos_are_strict_and_separate_operation_fields() -> None:
    create_type = schemas.CreateReferenceRequest
    update_type = schemas.UpdateReferenceRequest
    delete_type = schemas.DeleteReferenceRequest
    reindex_type = schemas.ReindexReferenceRequest
    create_response_type = schemas.CreateReferenceResponse

    with pytest.raises(ValidationError):
        create_type.model_validate(_fields())
    with pytest.raises(ValidationError):
        create_type.model_validate({**_fields(), "clientRequestId": "too-short"})
    with pytest.raises(ValidationError):
        create_type.model_validate({**_fields(), "clientRequestId": "x" * 257})
    create = create_type.model_validate(
        {**_fields(), "clientRequestId": "reference-create-0001"}
    )
    assert create.clientRequestId == "reference-create-0001"

    with pytest.raises(ValidationError):
        update_type.model_validate({"title": "新标题"})
    with pytest.raises(ValidationError):
        update_type.model_validate({"expectedUpdatedAt": "2026-08-06T00:00:00Z"})
    with pytest.raises(ValidationError):
        update_type.model_validate(
            {"title": "新标题", "expectedUpdatedAt": None}
        )
    with pytest.raises(ValidationError):
        delete_type.model_validate({})
    with pytest.raises(ValidationError):
        delete_type.model_validate({"expectedUpdatedAt": None})

    with pytest.raises(ValidationError):
        reindex_type.model_validate({})
    for invalid_hash in ("A" * 64, "a" * 63, "a" * 65, "g" * 64):
        with pytest.raises(ValidationError):
            reindex_type.model_validate({"expectedContentHash": invalid_hash})
    assert reindex_type(expectedContentHash="a" * 64).expectedContentHash == "a" * 64

    assert "clientRequestId" not in schemas.ReferenceMaterialResponse.model_fields
    assert "expectedUpdatedAt" not in schemas.ReferenceMaterialResponse.model_fields
    assert "effective" not in schemas.ReferenceMaterialResponse.model_fields
    assert "effective" in create_response_type.model_fields


@pytest.mark.asyncio
async def test_create_replay_conflict_history_delete_rebuild_and_novel_namespace(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "创建幂等.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        request_id = "reference-create-0001"

        created = await repository.create_reference(
            "novel-1",
            "user-1",
            request_id,
            _fields(),
            index_enabled=True,
        )
        expected_id = command_resource_id(
            "reference", "user-1", "novel-1", request_id
        )
        assert created["id"] == expected_id
        assert created["effective"] is True
        first_generation = created["indexGeneration"]
        assert created["createdAt"] == created["updatedAt"]
        assert created["updatedAt"].microsecond % 1000 == 0

        replayed = await repository.create_reference(
            "novel-1", "user-1", request_id, _fields(), index_enabled=True
        )
        assert replayed["id"] == expected_id
        assert replayed["effective"] is False
        assert replayed["updatedAt"] == created["updatedAt"]

        async with factory() as session:
            document_count = await session.scalar(select(func.count()).select_from(RagDocument))
        assert document_count == 1

        with pytest.raises(ApiError) as changed_replay:
            await repository.create_reference(
                "novel-1",
                "user-1",
                request_id,
                _fields("不同正文"),
                index_enabled=True,
            )
        assert changed_replay.value.code == "RESOURCE_CREATE_CONFLICT"

        changed = await repository.update_reference(
            "novel-1",
            "user-1",
            expected_id,
            {"content": "正文 B"},
            created["updatedAt"],
            index_enabled=True,
        )
        restored = await repository.update_reference(
            "novel-1",
            "user-1",
            expected_id,
            {"content": "初始正文"},
            changed["updatedAt"],
            index_enabled=True,
        )
        assert changed["indexGeneration"] != first_generation
        assert restored["indexGeneration"] != first_generation
        assert restored["indexGeneration"] != changed["indexGeneration"]
        await repository.mark_rag_dispatch_terminal(
            "novel-1",
            expected_id,
            content_sha256("初始正文"),
            first_generation,
            "cancelled",
        )
        async with factory() as session:
            current_document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == expected_id)
            )
        assert current_document is not None
        assert current_document.status == "disabled"
        assert current_document.errorMessage == "等待重新索引"
        with pytest.raises(ApiError) as history_conflict:
            await repository.create_reference(
                "novel-1", "user-1", request_id, _fields(), index_enabled=True
            )
        assert history_conflict.value.code == "RESOURCE_CREATE_CONFLICT"

        with pytest.raises(ApiError) as cross_novel:
            await repository.update_reference(
                "novel-2",
                "user-1",
                expected_id,
                {"title": "越界"},
                restored["updatedAt"],
                index_enabled=True,
            )
        assert cross_novel.value.code == "REFERENCE_NOT_FOUND"

        deleted = await repository.delete_reference(
            "novel-1", "user-1", expected_id, restored["updatedAt"]
        )
        assert deleted == {
            "deletedType": "reference",
            "deletedId": expected_id,
            "affected": {"reference": 1, "ragDocuments": 1, "ragChunks": 0},
        }
        recreated = await repository.create_reference(
            "novel-1", "user-1", request_id, _fields(), index_enabled=True
        )
        assert recreated["id"] == expected_id
        assert recreated["effective"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_replay_rejects_missing_rag_document(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "create-replay-missing-document.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        request_id = "reference-create-missing-document"
        created = await repository.create_reference(
            "novel-1", "user-1", request_id, _fields(), index_enabled=True
        )
        async with factory() as session, session.begin():
            await session.execute(
                delete(RagDocument).where(RagDocument.sourceId == created["id"])
            )

        with pytest.raises(ApiError) as caught:
            await repository.create_reference(
                "novel-1", "user-1", request_id, _fields(), index_enabled=True
            )

        assert caught.value.status_code == 409
        assert caught.value.code == "RAG_DOCUMENT_MISSING"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_update_cas_noop_and_index_input_boundaries(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "更新边界.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-update-0001",
            _fields(),
            index_enabled=True,
        )
        reference_id = created["id"]
        async with factory() as session, session.begin():
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == reference_id)
            )
            assert document is not None
            document.status = "ready"
            document.errorMessage = None
            session.add(
                RagChunk(
                    documentId=document.id,
                    novelId="novel-1",
                    chunkIndex=0,
                    text="初始正文",
                    charCount=4,
                    embeddingDimension=1,
                    embedding=[1.0],
                )
            )
        unchanged = await repository.update_reference(
            "novel-1",
            "user-1",
            reference_id,
            {"title": "参考资料"},
            created["updatedAt"],
            index_enabled=True,
        )
        assert unchanged["updatedAt"] == created["updatedAt"]
        assert unchanged["ragStatus"] == "ready"

        metadata_only = await repository.update_reference(
            "novel-1",
            "user-1",
            reference_id,
            {"type": "book", "sourceUrl": "https://example.com/source"},
            created["updatedAt"],
            index_enabled=True,
        )
        assert metadata_only["updatedAt"] > created["updatedAt"]
        assert metadata_only["ragStatus"] == "ready"
        async with factory() as session:
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
            generation_before_title = await session.scalar(
                select(RagDocument.updatedAt).where(
                    RagDocument.sourceId == reference_id
                )
            )
        assert chunk_count == 1
        assert generation_before_title is not None

        with pytest.raises(ApiError) as stale:
            await repository.update_reference(
                "novel-1",
                "user-1",
                reference_id,
                {"content": "陈旧覆盖"},
                created["updatedAt"],
                index_enabled=True,
            )
        assert stale.value.code == "REFERENCE_VERSION_CONFLICT"
        async with factory() as session:
            current = await session.get(ReferenceMaterial, reference_id)
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == reference_id)
            )
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
        assert current is not None and current.content == "初始正文"
        assert document is not None and document.status == "ready"
        assert chunk_count == 1

        title_changed = await repository.update_reference(
            "novel-1",
            "user-1",
            reference_id,
            {"title": "新标题"},
            metadata_only["updatedAt"],
            index_enabled=True,
        )
        assert title_changed["updatedAt"] > metadata_only["updatedAt"]
        assert title_changed["ragStatus"] == "ready"
        assert title_changed["indexRefreshRequired"] is False
        async with factory() as session:
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == reference_id)
            )
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
        assert document is not None and document.title == "新标题"
        assert document.status == "ready"
        assert document.updatedAt == generation_before_title
        assert chunk_count == 1

        changed = await repository.update_reference(
            "novel-1",
            "user-1",
            reference_id,
            {"content": "新正文"},
            title_changed["updatedAt"],
            index_enabled=True,
        )
        assert changed["updatedAt"] > title_changed["updatedAt"]
        assert changed["ragStatus"] == "disabled"
        assert changed["contentHash"] == content_sha256("新正文")
        assert changed["errorMessage"] == "等待重新索引"
        async with factory() as session:
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == reference_id)
            )
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
        assert document is not None and document.title == "新标题"
        assert chunk_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_reports_exact_explicit_impact_and_stale_delete_is_atomic(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "删除影响.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-delete-0001",
            _fields(),
            index_enabled=True,
        )
        async with factory() as session, session.begin():
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
            assert document is not None
            for index in range(2):
                session.add(
                    RagChunk(
                        documentId=document.id,
                        novelId="novel-1",
                        chunkIndex=index,
                        text=f"分块 {index}",
                        charCount=4,
                        embeddingDimension=1,
                        embedding=[1.0],
                    )
                )

        with pytest.raises(ApiError) as stale:
            await repository.delete_reference(
                "novel-1",
                "user-1",
                created["id"],
                created["updatedAt"] - timedelta(seconds=1),
            )
        assert stale.value.code == "REFERENCE_VERSION_CONFLICT"
        async with factory() as session:
            assert await session.get(ReferenceMaterial, created["id"]) is not None
            assert await session.scalar(select(func.count()).select_from(RagDocument)) == 1
            assert await session.scalar(select(func.count()).select_from(RagChunk)) == 2

        impact = await repository.delete_reference(
            "novel-1", "user-1", created["id"], created["updatedAt"]
        )
        assert impact == {
            "deletedType": "reference",
            "deletedId": created["id"],
            "affected": {"reference": 1, "ragDocuments": 1, "ragChunks": 2},
        }
        async with factory() as session:
            assert await session.get(ReferenceMaterial, created["id"]) is None
            assert await session.scalar(select(func.count()).select_from(RagDocument)) == 0
            assert await session.scalar(select(func.count()).select_from(RagChunk)) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reindex_requires_matching_formal_and_document_hash_before_mutation(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "安全重索引.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-reindex-0001",
            _fields(),
            index_enabled=True,
        )
        expected_hash = content_sha256("初始正文")
        async with factory() as session, session.begin():
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
            assert document is not None
            document.status = "ready"
            document.errorMessage = None
            session.add(
                RagChunk(
                    documentId=document.id,
                    novelId="novel-1",
                    chunkIndex=0,
                    text="初始正文",
                    charCount=4,
                    embeddingDimension=1,
                    embedding=[1.0],
                )
            )

        async with factory() as session:
            before_ready_reindex = await session.scalar(
                select(RagDocument.updatedAt).where(
                    RagDocument.sourceId == created["id"]
                )
            )
        assert before_ready_reindex is not None

        with pytest.raises(ApiError) as stale:
            await repository.prepare_reindex(
                "novel-1", "user-1", created["id"], "0" * 64
            )
        assert stale.value.code == "RAG_INDEX_STALE"
        async with factory() as session:
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
        assert document is not None and document.status == "ready"
        assert chunk_count == 1

        first = await repository.prepare_reindex(
            "novel-1", "user-1", created["id"], expected_hash
        )
        second = await repository.prepare_reindex(
            "novel-1", "user-1", created["id"], expected_hash
        )
        assert first["contentHash"] == second["contentHash"] == expected_hash
        assert first["indexGeneration"] == second["indexGeneration"]
        assert first["indexGeneration"] != before_ready_reindex
        async with factory() as session:
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
        assert document is not None
        assert document.contentHash == expected_hash
        assert document.status == "disabled"
        assert document.errorMessage == "等待重新索引"
        assert chunk_count == 0

        async with factory() as session, session.begin():
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
            assert document is not None
            document.status = "failed"
            document.errorMessage = "failed"
        third = await repository.prepare_reindex(
            "novel-1", "user-1", created["id"], expected_hash
        )
        assert third["contentHash"] == expected_hash
        assert third["indexGeneration"] != second["indexGeneration"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_old_generation_context_and_wrong_task_are_rejected(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "旧代次上下文.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-context-generation",
            _fields(),
            index_enabled=True,
        )
        old_identity, new_identity = await _advance_to_second_generation(
            factory, repository, created
        )

        with pytest.raises(ApiError) as old_context:
            await repository.require_index_context(
                "novel-1",
                "user-1",
                created["id"],
                old_identity[0],
                old_identity[1],
                created["contentHash"],
            )
        assert old_context.value.code == "RAG_INDEX_STALE"

        with pytest.raises(ApiError) as wrong_task:
            await repository.require_index_context(
                "novel-1",
                "user-1",
                created["id"],
                "rag-wrong-task",
                new_identity[1],
                created["contentHash"],
            )
        assert wrong_task.value.code == "RAG_INDEX_STALE"

        current = await repository.require_index_context(
            "novel-1",
            "user-1",
            created["id"],
            new_identity[0],
            new_identity[1],
            created["contentHash"],
        )
        assert current["content"] == "初始正文"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_old_generation_completion_is_rejected_before_chunk_mutation(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "旧代次完成回调.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-complete-generation",
            _fields(),
            index_enabled=True,
        )
        old_identity, new_identity = await _advance_to_second_generation(
            factory, repository, created
        )

        with pytest.raises(ApiError) as old_completion:
            await repository.replace_index(
                "novel-1",
                created["id"],
                old_identity[0],
                old_identity[1],
                created["contentHash"],
                [[1.0]],
            )
        assert old_completion.value.code == "RAG_INDEX_STALE"
        async with factory() as session:
            pending = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
        assert pending is not None and pending.status == "disabled"
        assert pending.errorMessage == "等待重新索引"
        assert chunk_count == 0

        completed = await repository.replace_index(
            "novel-1",
            created["id"],
            new_identity[0],
            new_identity[1],
            created["contentHash"],
            [[1.0]],
        )
        assert completed["ragStatus"] == "ready"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_old_generation_failure_is_rejected_without_changing_new_pending(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "旧代次失败回调.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-failure-generation",
            _fields(),
            index_enabled=True,
        )
        old_identity, _ = await _advance_to_second_generation(factory, repository, created)

        with pytest.raises(ApiError) as old_failure:
            await repository.mark_index_failed(
                "novel-1",
                created["id"],
                old_identity[0],
                old_identity[1],
                created["contentHash"],
                "旧任务失败",
            )
        assert old_failure.value.code == "RAG_INDEX_STALE"
        async with factory() as session:
            pending = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
        assert pending is not None and pending.status == "disabled"
        assert pending.errorMessage == "等待重新索引"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_success_callback_preserves_generation_and_replays_without_replacing_chunks(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "success-terminal-generation.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-success-terminal",
            _fields(),
            index_enabled=True,
        )
        task_id, run_id = await _rag_identity(
            created["id"], created["contentHash"], created["indexGeneration"]
        )

        completed = await repository.replace_index(
            "novel-1",
            created["id"],
            task_id,
            run_id,
            created["contentHash"],
            [[1.0]],
        )
        assert completed["ragStatus"] == "ready"
        async with factory() as session:
            generation = await session.scalar(
                select(RagDocument.updatedAt).where(
                    RagDocument.sourceId == created["id"]
                )
            )
            first_chunk_ids = list(
                await session.scalars(select(RagChunk.id))
            )
        assert generation == created["indexGeneration"].replace(tzinfo=None)
        assert len(first_chunk_ids) == 1

        replayed = await repository.replace_index(
            "novel-1",
            created["id"],
            task_id,
            run_id,
            created["contentHash"],
            [[1.0]],
        )
        assert replayed["ragStatus"] == "ready"
        async with factory() as session:
            replay_generation = await session.scalar(
                select(RagDocument.updatedAt).where(
                    RagDocument.sourceId == created["id"]
                )
            )
            replay_chunk_ids = list(
                await session.scalars(select(RagChunk.id))
            )
        assert replay_generation == generation
        assert replay_chunk_ids == first_chunk_ids

        with pytest.raises(ApiError) as conflicting_failure:
            await repository.mark_index_failed(
                "novel-1",
                created["id"],
                task_id,
                run_id,
                created["contentHash"],
                "索引生成失败",
            )
        assert conflicting_failure.value.code == "RAG_INDEX_TERMINAL_CONFLICT"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failure_callback_preserves_generation_and_replays_without_mutation(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "failure-terminal-generation.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-failure-terminal",
            _fields(),
            index_enabled=True,
        )
        task_id, run_id = await _rag_identity(
            created["id"], created["contentHash"], created["indexGeneration"]
        )

        await repository.mark_index_failed(
            "novel-1",
            created["id"],
            task_id,
            run_id,
            created["contentHash"],
            "索引生成失败",
        )
        await repository.mark_index_failed(
            "novel-1",
            created["id"],
            task_id,
            run_id,
            created["contentHash"],
            "索引生成失败",
        )
        async with factory() as session:
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
            chunk_count = await session.scalar(select(func.count()).select_from(RagChunk))
        assert document is not None
        assert document.status == "failed"
        assert document.updatedAt == created["indexGeneration"].replace(tzinfo=None)
        assert chunk_count == 0

        with pytest.raises(ApiError) as conflicting_success:
            await repository.replace_index(
                "novel-1",
                created["id"],
                task_id,
                run_id,
                created["contentHash"],
                [[1.0]],
            )
        assert conflicting_success.value.code == "RAG_INDEX_TERMINAL_CONFLICT"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dispatcher_terminal_preserves_generation_on_replay(tmp_path: Path) -> None:
    engine, factory = await _create_database(tmp_path / "dispatcher-terminal-generation.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        created = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-dispatcher-terminal",
            _fields(),
            index_enabled=True,
        )

        for _ in range(2):
            await repository.mark_rag_dispatch_terminal(
                "novel-1",
                created["id"],
                created["contentHash"],
                created["indexGeneration"],
                "cancelled",
            )
        async with factory() as session:
            document = await session.scalar(
                select(RagDocument).where(RagDocument.sourceId == created["id"])
            )
        assert document is not None
        assert document.status == "failed"
        assert document.updatedAt == created["indexGeneration"].replace(tzinfo=None)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reference_batch_rolls_back_all_reference_items_on_later_conflict(
    tmp_path: Path,
) -> None:
    engine, factory = await _create_database(tmp_path / "参考资料批量回滚.db")
    try:
        await _seed_novels(factory)
        repository = ReferenceRepository(factory)
        target = await repository.create_reference(
            "novel-1",
            "user-1",
            "reference-batch-target",
            _fields(),
            index_enabled=True,
        )
        create_request_id = "reference-batch-create"
        created_id = command_resource_id(
            "reference", "user-1", "novel-1", create_request_id
        )

        with pytest.raises(ApiError) as caught:
            await repository.apply_reference_mutations(
                "novel-1",
                "user-1",
                [
                    ReferenceMutation(
                        action="create",
                        fields=_fields("不会落库"),
                        client_request_id=create_request_id,
                    ),
                    ReferenceMutation(
                        action="update",
                        reference_id=target["id"],
                        fields={"content": "陈旧覆盖"},
                        expected_updated_at=target["updatedAt"] - timedelta(seconds=1),
                    ),
                ],
                index_enabled=True,
            )
        assert caught.value.code == "REFERENCE_VERSION_CONFLICT"

        async with factory() as session:
            assert await session.get(ReferenceMaterial, created_id) is None
            current = await session.get(ReferenceMaterial, target["id"])
            documents = await session.scalar(select(func.count()).select_from(RagDocument))
        assert current is not None and current.content == "初始正文"
        assert documents == 1
    finally:
        await engine.dispose()


def test_delete_and_reindex_routes_require_explicit_preconditions() -> None:
    calls: list[tuple[object, ...]] = []

    class Service:
        async def delete(self, user_id, novel_id, reference_id, body):
            calls.append(
                (
                    "delete",
                    user_id,
                    novel_id,
                    reference_id,
                    body.expectedUpdatedAt,
                )
            )
            return {
                "deletedType": "reference",
                "deletedId": reference_id,
                "affected": {"reference": 1, "ragDocuments": 1, "ragChunks": 3},
            }

        async def reindex(self, user_id, novel_id, reference_id, body):
            calls.append(
                (
                    "reindex",
                    user_id,
                    novel_id,
                    reference_id,
                    body.expectedContentHash,
                )
            )

    app = create_app(testing=True)
    app.state.reference_service = Service()
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="user-1",
        username="user",
        password_hash="固定哈希",  # noqa: S106
        credit_balance_micros=0,
    )
    client = TestClient(app)
    path = "/api/v1/novels/novel-1/references/reference-1"

    assert client.request("DELETE", path, json={}).status_code == 422
    deleted = client.request(
        "DELETE",
        path,
        json={"expectedUpdatedAt": "2026-08-06T00:00:00Z"},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {
        "deletedType": "reference",
        "deletedId": "reference-1",
        "affected": {"reference": 1, "ragDocuments": 1, "ragChunks": 3},
    }

    assert client.post(f"{path}/reindex", json={}).status_code == 422
    accepted = client.post(
        f"{path}/reindex", json={"expectedContentHash": "a" * 64}
    )
    assert accepted.status_code == 202
    assert accepted.json() == {"accepted": True}
    assert calls == [
        (
            "delete",
            "user-1",
            "novel-1",
            "reference-1",
            datetime(2026, 8, 6, tzinfo=UTC),
        ),
        ("reindex", "user-1", "novel-1", "reference-1", "a" * 64),
    ]
