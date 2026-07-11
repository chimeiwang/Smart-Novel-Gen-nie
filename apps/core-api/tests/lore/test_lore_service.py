from __future__ import annotations

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.lore.schemas import (
    ContentRequest,
    UpdateCharacterRequest,
    UpdateItemRequest,
    WritingBibleRequest,
)
from inkforge_core.lore.service import LoreService


class RecordingRepository:
    def __init__(self) -> None:
        self.fields: dict[str, object] | None = None
        self.content: str | None = None

    async def update_entity(self, novel_id, user_id, kind, entity_id, fields):
        del novel_id, user_id, kind, entity_id
        self.fields = fields
        return {"id": "character-1", "name": "角色"}

    async def upsert_content(self, novel_id, user_id, kind, content):
        del novel_id, user_id, kind
        self.content = content
        return {"id": "content-1", "content": content}


@pytest.mark.asyncio
async def test_explicit_null_is_distinct_from_omitted_field() -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    request = UpdateCharacterRequest(factionId=None)
    await service.update_entity("user-1", "novel-1", "characters", "character-1", request)
    assert repository.fields == {"factionId": None}


@pytest.mark.asyncio
async def test_lore_content_is_preserved_exactly() -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    source = "  第一行\r\n\r\n最后一行  "
    await service.upsert_content(
        "user-1", "novel-1", "story-background", ContentRequest(content=source)
    )
    assert repository.content == source


@pytest.mark.asyncio
async def test_story_progress_rejects_30001_without_truncating() -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.upsert_content(
            "user-1", "novel-1", "story-progress", ContentRequest(content="文" * 30_001)
        )
    assert caught.value.code == "STORY_PROGRESS_TOO_LONG"
    assert repository.content is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "body"),
    [
        ("characters", UpdateCharacterRequest(name=None)),
        ("characters", UpdateCharacterRequest(currentStatus=None)),
        ("items", UpdateItemRequest(name=None)),
    ],
)
async def test_patch_rejects_explicit_null_for_non_nullable_fields(kind, body) -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.update_entity("user-1", "novel-1", kind, "entity-1", body)
    assert caught.value.code == "LORE_FIELD_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "body"),
    [("characters", UpdateCharacterRequest()), ("writing-bible", WritingBibleRequest())],
)
async def test_empty_lore_update_is_rejected(kind, body) -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        if kind == "writing-bible":
            await service.upsert_content("user-1", "novel-1", kind, body)
        else:
            await service.update_entity("user-1", "novel-1", kind, "entity-1", body)
    assert caught.value.code == "EMPTY_UPDATE"
