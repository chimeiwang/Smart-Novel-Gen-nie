from __future__ import annotations

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.references.schemas import CreateReferenceRequest, UpdateReferenceRequest
from inkforge_core.references.service import ReferenceService

HASH = "a" * 64


class RecordingRepository:
    def __init__(self) -> None:
        self.created = None

    async def create_reference(self, novel_id, user_id, fields):
        del novel_id, user_id
        self.created = fields
        return {
            "id": "reference-1",
            **fields,
            "ragStatus": "disabled",
            "contentHash": HASH,
            "errorMessage": None,
        }

    async def update_reference(self, novel_id, user_id, reference_id, fields):
        del novel_id, user_id
        return {
            "id": reference_id,
            "title": fields.get("title", "资料"),
            "type": fields.get("type", "note"),
            "content": fields.get("content", "正文"),
            "sourceUrl": fields.get("sourceUrl"),
            "ragStatus": "disabled",
            "contentHash": HASH,
            "errorMessage": "等待重新索引",
        }

    async def prepare_reindex(self, novel_id, user_id, reference_id):
        del novel_id, user_id, reference_id
        return HASH

    async def mark_index_failed(self, novel_id, reference_id, expected_content_hash, message):
        self.failed = (novel_id, reference_id, expected_content_hash, message)

    async def require_reference(self, novel_id, user_id, reference_id):
        assert (novel_id, user_id, reference_id) == ("novel-1", "user-1", "reference-1")
        return {"content": "甲" * 1800 + "乙", "contentHash": HASH}


class RecordingSubmitter:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, str, str, str]] = []

    async def submit(
        self, user_id: str, novel_id: str, reference_id: str, content_hash: str
    ) -> None:
        self.jobs.append((user_id, novel_id, reference_id, content_hash))


class FailingSubmitter:
    async def submit(
        self, user_id: str, novel_id: str, reference_id: str, content_hash: str
    ) -> None:
        del user_id, novel_id, reference_id, content_hash
        raise RuntimeError("队列不可用")


@pytest.mark.asyncio
async def test_unconfigured_indexer_still_saves_original_reference() -> None:
    repository = RecordingRepository()
    service = ReferenceService(repository, submitter=None)  # type: ignore[arg-type]
    source = "  原始资料\r\n  "
    result = await service.create_reference(
        "user-1",
        "novel-1",
        CreateReferenceRequest(title="资料", type="note", content=source, sourceUrl=None),
    )
    assert repository.created["content"] == source
    assert result.ragStatus == "disabled"


@pytest.mark.asyncio
async def test_configured_indexer_receives_saved_reference_id() -> None:
    repository = RecordingRepository()
    submitter = RecordingSubmitter()
    service = ReferenceService(repository, submitter)  # type: ignore[arg-type]
    result = await service.create_reference(
        "user-1",
        "novel-1",
        CreateReferenceRequest(title="资料", type="book", content="正文", sourceUrl=None),
    )
    assert submitter.jobs == [("user-1", "novel-1", "reference-1", result.contentHash)]


@pytest.mark.asyncio
async def test_index_context_revalidates_owner_hash_and_returns_lossless_chunks() -> None:
    service = ReferenceService(RecordingRepository(), submitter=None)  # type: ignore[arg-type]

    context = await service.get_index_context(
        "user-1", "novel-1", "reference-1", HASH
    )

    assert context == {"contentHash": HASH, "chunks": ["甲" * 1800, "乙"]}


@pytest.mark.asyncio
async def test_create_remains_successful_when_async_submission_fails() -> None:
    service = ReferenceService(RecordingRepository(), FailingSubmitter())  # type: ignore[arg-type]
    result = await service.create_reference(
        "user-1",
        "novel-1",
        CreateReferenceRequest(title="资料", type="note", content="正文", sourceUrl=None),
    )
    assert result.id == "reference-1"
    assert result.ragStatus == "disabled"


@pytest.mark.asyncio
async def test_update_remains_successful_when_async_submission_fails() -> None:
    service = ReferenceService(RecordingRepository(), FailingSubmitter())  # type: ignore[arg-type]
    result = await service.update(
        "user-1",
        "novel-1",
        "reference-1",
        UpdateReferenceRequest(content="新正文"),
    )
    assert result.content == "新正文"
    assert result.ragStatus == "disabled"


@pytest.mark.asyncio
async def test_reindex_without_infrastructure_returns_503() -> None:
    service = ReferenceService(RecordingRepository(), submitter=None)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.reindex("user-1", "novel-1", "reference-1")
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_explicit_reindex_submission_failure_is_reconciled_as_failed() -> None:
    repository = RecordingRepository()
    service = ReferenceService(repository, FailingSubmitter())  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.reindex("user-1", "novel-1", "reference-1")
    assert caught.value.status_code == 503
    assert repository.failed == (
        "novel-1",
        "reference-1",
        HASH,
        "索引任务提交失败",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        UpdateReferenceRequest(title=None),
        UpdateReferenceRequest(type=None),
        UpdateReferenceRequest(content=None),
    ],
)
async def test_update_rejects_null_for_required_reference_fields(body) -> None:
    service = ReferenceService(RecordingRepository(), submitter=None)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.update("user-1", "novel-1", "reference-1", body)
    assert caught.value.code == "REFERENCE_FIELD_REQUIRED"


@pytest.mark.asyncio
async def test_empty_reference_update_is_rejected() -> None:
    service = ReferenceService(RecordingRepository(), submitter=None)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.update("user-1", "novel-1", "reference-1", UpdateReferenceRequest())
    assert caught.value.code == "EMPTY_UPDATE"
