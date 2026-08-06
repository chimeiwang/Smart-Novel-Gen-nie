from __future__ import annotations

from datetime import UTC, datetime

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.lore.schemas import (
    ContentRequest,
    UpdateCharacterRequest,
    UpdateItemRequest,
    WritingBibleRequest,
)
from inkforge_core.lore.service import LoreService
from pydantic import ValidationError


class RecordingRepository:
    def __init__(self) -> None:
        self.fields: dict[str, object] | None = None
        self.content: object | None = None
        self.expected_updated_at: datetime | None = None

    async def update_entity(
        self, novel_id, user_id, kind, entity_id, fields, expected_updated_at
    ):
        del novel_id, user_id, kind, entity_id
        self.fields = fields
        self.expected_updated_at = expected_updated_at
        return {"id": "character-1", "name": "角色"}

    async def upsert_content(self, novel_id, user_id, kind, content, expected_updated_at):
        del novel_id, user_id, kind
        self.content = content
        self.expected_updated_at = expected_updated_at
        return {"id": "content-1", "content": content}


@pytest.mark.asyncio
async def test_explicit_null_is_distinct_from_omitted_field() -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    expected = datetime(2026, 8, 6, tzinfo=UTC)
    request = UpdateCharacterRequest(factionId=None, expectedUpdatedAt=expected)
    await service.update_entity("user-1", "novel-1", "characters", "character-1", request)
    assert repository.fields == {"factionId": None}
    assert repository.expected_updated_at == expected


@pytest.mark.asyncio
async def test_lore_content_is_preserved_exactly() -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    source = "  第一行\r\n\r\n最后一行  "
    await service.upsert_content(
        "user-1",
        "novel-1",
        "story-background",
        ContentRequest(content=source, expectedUpdatedAt=None),
    )
    assert repository.content == source
    assert repository.expected_updated_at is None


@pytest.mark.asyncio
async def test_story_progress_rejects_30001_without_truncating() -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.upsert_content(
            "user-1",
            "novel-1",
            "story-progress",
            ContentRequest(content="文" * 30_001, expectedUpdatedAt=None),
        )
    assert caught.value.code == "STORY_PROGRESS_TOO_LONG"
    assert repository.content is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "body"),
    [
        (
            "characters",
            UpdateCharacterRequest(name=None, expectedUpdatedAt="2026-08-06T00:00:00Z"),
        ),
        (
            "characters",
            UpdateCharacterRequest(
                currentStatus=None, expectedUpdatedAt="2026-08-06T00:00:00Z"
            ),
        ),
        ("items", UpdateItemRequest(name=None, expectedUpdatedAt="2026-08-06T00:00:00Z")),
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
    ("kind", "payload"),
    [
        ("characters", {"expectedUpdatedAt": "2026-08-06T00:00:00Z"}),
        ("writing-bible", {"expectedUpdatedAt": None}),
    ],
)
async def test_empty_lore_update_is_rejected(kind, payload) -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    if kind == "characters":
        with pytest.raises(ValidationError):
            UpdateCharacterRequest.model_validate(payload)
        return
    with pytest.raises(ApiError) as caught:
        body = WritingBibleRequest.model_validate(payload)
        await service.upsert_content("user-1", "novel-1", kind, body)
    assert caught.value.code == "EMPTY_UPDATE"


@pytest.mark.asyncio
async def test_writing_bible_rejects_short_medium_profile() -> None:
    service = LoreService(RecordingRepository())  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await service.upsert_content(
            "user-1",
            "novel-1",
            "writing-bible",
            WritingBibleRequest(
                storyLengthProfile="short_medium",
                expectedUpdatedAt=None,
            ),
        )
    assert caught.value.status_code == 422
    assert caught.value.code == "WRITING_BIBLE_PROFILE_MISMATCH"
    assert caught.value.message == "长篇作品不能改为中短篇模式"


@pytest.mark.asyncio
async def test_writing_bible_passes_business_fields_and_precondition_separately() -> None:
    repository = RecordingRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    expected = datetime(2026, 8, 6, tzinfo=UTC)

    await service.upsert_content(
        "user-1",
        "novel-1",
        "writing-bible",
        WritingBibleRequest(
            storyLengthProfile=None,
            genre="仙侠",
            expectedUpdatedAt=expected,
        ),
    )

    assert repository.content == {"genre": "仙侠"}
    assert repository.expected_updated_at == expected
