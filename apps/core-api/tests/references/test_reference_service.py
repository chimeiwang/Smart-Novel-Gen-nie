from __future__ import annotations

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.references.schemas import CreateReferenceRequest, UpdateReferenceRequest
from inkforge_core.references.service import ReferenceService


class RecordingRepository:
    def __init__(self) -> None:
        self.created = None

    async def create_reference(self, novel_id, user_id, fields):
        del novel_id, user_id
        self.created = fields
        return {"id": "reference-1", **fields, "ragStatus": "disabled"}


class RecordingSubmitter:
    def __init__(self) -> None:
        self.ids: list[str] = []

    async def submit(self, reference_id: str) -> None:
        self.ids.append(reference_id)


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
    await service.create_reference(
        "user-1",
        "novel-1",
        CreateReferenceRequest(title="资料", type="book", content="正文", sourceUrl=None),
    )
    assert submitter.ids == ["reference-1"]


@pytest.mark.asyncio
async def test_reindex_without_infrastructure_returns_503() -> None:
    service = ReferenceService(RecordingRepository(), submitter=None)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.reindex("user-1", "novel-1", "reference-1")
    assert caught.value.status_code == 503


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
