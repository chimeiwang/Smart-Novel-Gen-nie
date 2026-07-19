from __future__ import annotations

import inspect
from collections import deque

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.lore.repository import LoreRepository


class ScalarSession:
    def __init__(self, values: list[str | None]) -> None:
        self.values = deque(values)

    async def scalar(self, statement):
        del statement
        return self.values.popleft()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("characters", "factionId"),
        ("items", "ownerId"),
        ("locations", "parentId"),
        ("factions", "baseId"),
    ],
)
async def test_all_optional_links_reject_resources_from_another_novel(
    kind: str, field: str
) -> None:
    session = ScalarSession(["novel-other"])
    with pytest.raises(ApiError) as caught:
        await LoreRepository(lambda: None)._validate_entity_links(  # type: ignore[arg-type]
            session, "novel-1", kind, "entity-1", {field: "related-1"}
        )
    assert caught.value.code == "RELATED_RESOURCE_CROSS_NOVEL"


@pytest.mark.asyncio
async def test_location_rejects_itself_as_parent() -> None:
    session = ScalarSession(["novel-1"])
    with pytest.raises(ApiError) as caught:
        await LoreRepository(lambda: None)._validate_entity_links(  # type: ignore[arg-type]
            session,
            "novel-1",
            "locations",
            "location-1",
            {"parentId": "location-1"},
        )
    assert caught.value.code == "LOCATION_CYCLE"


@pytest.mark.asyncio
async def test_location_rejects_indirect_ancestor_cycle() -> None:
    session = ScalarSession(["novel-1", "location-1"])
    with pytest.raises(ApiError) as caught:
        await LoreRepository(lambda: None)._validate_entity_links(  # type: ignore[arg-type]
            session,
            "novel-1",
            "locations",
            "location-1",
            {"parentId": "location-2"},
        )
    assert caught.value.code == "LOCATION_CYCLE"


@pytest.mark.asyncio
async def test_null_owner_is_always_rejected() -> None:
    session = ScalarSession([None])
    with pytest.raises(ApiError) as caught:
        await LoreRepository._require_owner(session, "novel-1", "user-1")  # type: ignore[arg-type]
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_writing_bible_profile_is_returned_as_legacy_missing_state() -> None:
    session = ScalarSession(["user-1", None])
    repository = LoreRepository(lambda: session)  # type: ignore[arg-type]

    profile = await repository.get_writing_bible_profile("novel-1", "user-1")

    assert profile is None


def test_missing_writing_bible_uses_long_serial_target_rules() -> None:
    LoreRepository._require_target_for_profile(None, None)
    LoreRepository._require_target_for_profile(None, 1_000_000)


@pytest.mark.parametrize("method_name", ["create_entity", "update_entity"])
def test_location_mutation_locks_novel_before_validating_parent_chain(method_name: str) -> None:
    source = inspect.getsource(getattr(LoreRepository, method_name))
    assert source.index("_lock_novel") < source.index("_validate_entity_links")
    assert "pg_advisory_xact_lock(:key)" in inspect.getsource(LoreRepository._lock_novel)


def test_location_delete_locks_novel_before_checking_children_and_deleting() -> None:
    source = inspect.getsource(LoreRepository.delete_entity)
    lock_index = source.index("_lock_novel")
    assert lock_index < source.index("select(Location.id)")
    assert lock_index < source.index("delete(model)")
    assert "pg_advisory_xact_lock(:key)" in inspect.getsource(LoreRepository._lock_novel)
