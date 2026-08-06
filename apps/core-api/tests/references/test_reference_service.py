from __future__ import annotations

from datetime import UTC, datetime

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.references import schemas
from inkforge_core.references.service import ReferenceService
from pydantic import ValidationError

HASH = "a" * 64
NOW = datetime(2026, 8, 6, tzinfo=UTC)


class RecordingRepository:
    def __init__(self) -> None:
        self.created = None
        self.created_index_enabled: bool | None = None
        self.updated_index_enabled: bool | None = None
        self.prepared: list[tuple[str, str, str, str]] = []
        self.create_effective = True
        self.update_refresh_required = True

    async def create_reference(
        self,
        novel_id,
        user_id,
        client_request_id,
        fields,
        *,
        index_enabled=False,
    ):
        del novel_id, user_id
        self.created = (client_request_id, fields)
        self.created_index_enabled = index_enabled
        return {
            "id": "reference-1",
            **fields,
            "effective": self.create_effective,
            "ragStatus": "disabled",
            "contentHash": HASH,
            "errorMessage": "等待重新索引" if index_enabled else "检索索引服务未配置",
            "createdAt": NOW,
            "updatedAt": NOW,
            "indexGeneration": NOW,
        }

    async def update_reference(
        self,
        novel_id,
        user_id,
        reference_id,
        fields,
        expected_updated_at,
        *,
        index_enabled=False,
    ):
        del novel_id, user_id, expected_updated_at
        self.updated_index_enabled = index_enabled
        return {
            "id": reference_id,
            "title": fields.get("title", "资料"),
            "type": fields.get("type", "note"),
            "content": fields.get("content", "正文"),
            "sourceUrl": fields.get("sourceUrl"),
            "ragStatus": "disabled",
            "contentHash": HASH,
            "errorMessage": "等待重新索引" if index_enabled else "检索索引服务未配置",
            "createdAt": NOW,
            "updatedAt": NOW,
            "indexRefreshRequired": self.update_refresh_required,
            "indexGeneration": NOW,
        }

    async def prepare_reindex(self, novel_id, user_id, reference_id, expected_content_hash):
        self.prepared.append((novel_id, user_id, reference_id, expected_content_hash))
        return {"contentHash": HASH, "indexGeneration": NOW}

    async def replace_index(
        self,
        novel_id,
        reference_id,
        task_id,
        run_id,
        expected_content_hash,
        embeddings,
    ):
        self.completed = (
            novel_id,
            reference_id,
            task_id,
            run_id,
            expected_content_hash,
            embeddings,
        )
        return {
            "id": reference_id,
            "title": "资料",
            "type": "note",
            "content": "正文",
            "sourceUrl": None,
            "ragStatus": "ready",
            "contentHash": expected_content_hash,
            "errorMessage": None,
            "createdAt": NOW,
            "updatedAt": NOW,
        }

    async def mark_index_failed(
        self,
        novel_id,
        reference_id,
        task_id,
        run_id,
        expected_content_hash,
        message,
    ):
        self.failed = (
            novel_id,
            reference_id,
            task_id,
            run_id,
            expected_content_hash,
            message,
        )

    async def require_reference(self, novel_id, user_id, reference_id):
        assert (novel_id, user_id, reference_id) == ("novel-1", "user-1", "reference-1")
        return {"content": "甲" * 1800 + "乙", "contentHash": HASH}

    async def require_index_context(
        self,
        novel_id,
        user_id,
        reference_id,
        task_id,
        run_id,
        expected_content_hash,
    ):
        self.context = (
            novel_id,
            user_id,
            reference_id,
            task_id,
            run_id,
            expected_content_hash,
        )
        return {"content": "甲" * 1800 + "乙", "contentHash": HASH}


class RecordingSubmitter:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, str, str, str, datetime]] = []

    async def submit(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        generation: datetime,
    ) -> None:
        self.jobs.append((user_id, novel_id, reference_id, content_hash, generation))


class FailingSubmitter:
    async def submit(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        generation: datetime,
    ) -> None:
        del user_id, novel_id, reference_id, content_hash, generation
        raise RuntimeError("队列不可用")


@pytest.mark.asyncio
async def test_unconfigured_indexer_still_saves_original_reference() -> None:
    repository = RecordingRepository()
    service = ReferenceService(repository, submitter=None)  # type: ignore[arg-type]
    source = "  原始资料\r\n  "
    result = await service.create_reference(
        "user-1",
        "novel-1",
        schemas.CreateReferenceRequest(
            title="资料",
            type="note",
            content=source,
            sourceUrl=None,
            clientRequestId="reference-create-0001",
        ),
    )
    assert repository.created == (
        "reference-create-0001",
        {"title": "资料", "type": "note", "content": source, "sourceUrl": None},
    )
    assert repository.created_index_enabled is False
    assert result.ragStatus == "disabled"
    assert result.errorMessage == "检索索引服务未配置"


@pytest.mark.asyncio
async def test_configured_indexer_receives_saved_reference_id() -> None:
    repository = RecordingRepository()
    submitter = RecordingSubmitter()
    service = ReferenceService(repository, submitter)  # type: ignore[arg-type]
    result = await service.create_reference(
        "user-1",
        "novel-1",
        schemas.CreateReferenceRequest(
            title="资料",
            type="book",
            content="正文",
            sourceUrl=None,
            clientRequestId="reference-create-0001",
        ),
    )
    assert submitter.jobs == [
        ("user-1", "novel-1", "reference-1", result.contentHash, NOW)
    ]
    assert repository.created_index_enabled is True


@pytest.mark.asyncio
async def test_index_context_revalidates_owner_hash_and_returns_lossless_chunks() -> None:
    service = ReferenceService(RecordingRepository(), submitter=None)  # type: ignore[arg-type]

    context = await service.get_index_context(
        "user-1",
        "novel-1",
        "reference-1",
        "task-1",
        "run-1",
        HASH,
    )

    assert context == {"contentHash": HASH, "chunks": ["甲" * 1800, "乙"]}
    assert service._repository.context == (  # type: ignore[attr-defined]
        "novel-1",
        "user-1",
        "reference-1",
        "task-1",
        "run-1",
        HASH,
    )


@pytest.mark.asyncio
async def test_complete_index_forwards_signed_job_identity() -> None:
    repository = RecordingRepository()
    service = ReferenceService(repository, submitter=None)  # type: ignore[arg-type]

    await service.complete_index(
        "novel-1",
        "reference-1",
        "task-1",
        "run-1",
        HASH,
        [[1.0]],
    )

    assert repository.completed == (
        "novel-1",
        "reference-1",
        "task-1",
        "run-1",
        HASH,
        [[1.0]],
    )


@pytest.mark.asyncio
async def test_fail_index_forwards_signed_job_identity() -> None:
    repository = RecordingRepository()
    service = ReferenceService(repository, submitter=None)  # type: ignore[arg-type]

    await service.fail_index(
        "novel-1",
        "reference-1",
        "task-1",
        "run-1",
        HASH,
        "内部细节",
    )

    assert repository.failed == (
        "novel-1",
        "reference-1",
        "task-1",
        "run-1",
        HASH,
        "索引生成失败",
    )


@pytest.mark.asyncio
async def test_create_remains_successful_when_async_submission_fails() -> None:
    service = ReferenceService(RecordingRepository(), FailingSubmitter())  # type: ignore[arg-type]
    result = await service.create_reference(
        "user-1",
        "novel-1",
        schemas.CreateReferenceRequest(
            title="资料",
            type="note",
            content="正文",
            sourceUrl=None,
            clientRequestId="reference-create-0001",
        ),
    )
    assert result.id == "reference-1"
    assert result.ragStatus == "disabled"


@pytest.mark.asyncio
async def test_update_remains_successful_when_async_submission_fails() -> None:
    repository = RecordingRepository()
    service = ReferenceService(repository, FailingSubmitter())  # type: ignore[arg-type]
    result = await service.update(
        "user-1",
        "novel-1",
        "reference-1",
        schemas.UpdateReferenceRequest(content="新正文", expectedUpdatedAt=NOW),
    )
    assert result.content == "新正文"
    assert result.ragStatus == "disabled"
    assert repository.updated_index_enabled is True


@pytest.mark.asyncio
async def test_reindex_without_infrastructure_returns_503() -> None:
    service = ReferenceService(RecordingRepository(), submitter=None)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.reindex(
            "user-1",
            "novel-1",
            "reference-1",
            schemas.ReindexReferenceRequest(expectedContentHash=HASH),
        )
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_explicit_reindex_submission_failure_keeps_persisted_retry_intent() -> None:
    repository = RecordingRepository()
    service = ReferenceService(repository, FailingSubmitter())  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.reindex(
            "user-1",
            "novel-1",
            "reference-1",
            schemas.ReindexReferenceRequest(expectedContentHash=HASH),
        )
    assert caught.value.status_code == 503
    assert repository.prepared == [("novel-1", "user-1", "reference-1", HASH)]
    assert not hasattr(repository, "failed")


@pytest.mark.asyncio
async def test_repeated_explicit_reindex_reuses_persisted_generation() -> None:
    repository = RecordingRepository()
    submitter = RecordingSubmitter()
    service = ReferenceService(repository, submitter)  # type: ignore[arg-type]
    body = schemas.ReindexReferenceRequest(expectedContentHash=HASH)

    await service.reindex("user-1", "novel-1", "reference-1", body)
    await service.reindex("user-1", "novel-1", "reference-1", body)

    assert submitter.jobs == [
        ("user-1", "novel-1", "reference-1", HASH, NOW),
        ("user-1", "novel-1", "reference-1", HASH, NOW),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"title": None},
        {"type": None},
        {"content": None},
    ],
)
async def test_update_rejects_null_for_required_reference_fields(fields) -> None:
    service = ReferenceService(RecordingRepository(), submitter=None)  # type: ignore[arg-type]
    body = schemas.UpdateReferenceRequest(**fields, expectedUpdatedAt=NOW)
    with pytest.raises(ApiError) as caught:
        await service.update("user-1", "novel-1", "reference-1", body)
    assert caught.value.code == "REFERENCE_FIELD_REQUIRED"


@pytest.mark.asyncio
async def test_empty_reference_update_is_rejected() -> None:
    with pytest.raises(ValidationError):
        schemas.UpdateReferenceRequest(expectedUpdatedAt=NOW)


@pytest.mark.asyncio
async def test_create_replay_submits_only_when_creation_is_effective() -> None:
    repository = RecordingRepository()
    submitter = RecordingSubmitter()
    service = ReferenceService(repository, submitter)  # type: ignore[arg-type]
    body = schemas.CreateReferenceRequest(
        title="资料",
        type="note",
        content="正文",
        sourceUrl=None,
        clientRequestId="reference-create-0001",
    )

    first = await service.create_reference("user-1", "novel-1", body)
    repository.create_effective = False
    replayed = await service.create_reference("user-1", "novel-1", body)

    assert first.effective is True
    assert replayed.effective is False
    assert submitter.jobs == [("user-1", "novel-1", "reference-1", HASH, NOW)]


@pytest.mark.asyncio
async def test_title_only_update_does_not_submit_index_job() -> None:
    repository = RecordingRepository()
    repository.update_refresh_required = False
    submitter = RecordingSubmitter()
    service = ReferenceService(repository, submitter)  # type: ignore[arg-type]

    result = await service.update(
        "user-1",
        "novel-1",
        "reference-1",
        schemas.UpdateReferenceRequest(title="资料", expectedUpdatedAt=NOW),
    )

    assert result.updatedAt == NOW
    assert submitter.jobs == []
