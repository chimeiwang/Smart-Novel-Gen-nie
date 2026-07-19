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
from pydantic import ValidationError


class RecordingRepository:
    def __init__(self, *, story_length_profile: str | None = "long_serial") -> None:
        self.fields: dict[str, object] | None = None
        self.content: str | None = None
        self.story_length_profile = story_length_profile

    async def get_writing_bible_profile(self, novel_id, user_id):
        del novel_id, user_id
        return self.story_length_profile

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


def test_writing_bible_update_does_not_expose_profile_switch() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        WritingBibleRequest.model_validate({"storyLengthProfile": "short_medium"})


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [5_999, 80_001])
async def test_short_writing_bible_rejects_invalid_target(target: int) -> None:
    repository = RecordingRepository(story_length_profile="short_medium")
    service = LoreService(repository)  # type: ignore[arg-type]

    with pytest.raises(ApiError) as caught:
        await service.upsert_content(
            "user-1",
            "novel-1",
            "writing-bible",
            WritingBibleRequest(targetTotalWordCount=target),
        )

    assert caught.value.code == "SHORT_STORY_TARGET_WORD_COUNT_INVALID"
    assert repository.content is None


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [None, 6_000, 80_000])
async def test_short_writing_bible_accepts_nullable_reference_boundaries(
    target: int | None,
) -> None:
    repository = RecordingRepository(story_length_profile="short_medium")
    service = LoreService(repository)  # type: ignore[arg-type]

    await service.upsert_content(
        "user-1",
        "novel-1",
        "writing-bible",
        WritingBibleRequest(targetTotalWordCount=target),
    )

    assert repository.content == {"targetTotalWordCount": target}


@pytest.mark.asyncio
async def test_long_writing_bible_keeps_nullable_target_rule() -> None:
    repository = RecordingRepository(story_length_profile="long_serial")
    service = LoreService(repository)  # type: ignore[arg-type]

    await service.upsert_content(
        "user-1",
        "novel-1",
        "writing-bible",
        WritingBibleRequest(targetTotalWordCount=None),
    )

    assert repository.content == {"targetTotalWordCount": None}


@pytest.mark.asyncio
async def test_legacy_missing_writing_bible_can_be_created_with_long_rules() -> None:
    repository = RecordingRepository(story_length_profile=None)
    service = LoreService(repository)  # type: ignore[arg-type]

    await service.upsert_content(
        "user-1",
        "novel-1",
        "writing-bible",
        WritingBibleRequest(targetTotalWordCount=None, genre="悬疑"),
    )

    assert repository.content == {
        "targetTotalWordCount": None,
        "genre": "悬疑",
    }
