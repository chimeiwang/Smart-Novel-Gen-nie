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


@pytest.mark.parametrize("method_name", ["create_entity", "update_entity"])
def test_entity_mutation_locks_novel_before_validating_links(method_name: str) -> None:
    source = inspect.getsource(getattr(LoreRepository, method_name))
    helper_name = f"_{method_name}_in_session"
    assert source.index("_lock_novel") < source.index(helper_name)
    assert "_validate_entity_links" in inspect.getsource(
        getattr(LoreRepository, helper_name)
    )
    assert "pg_advisory_xact_lock(:key)" in inspect.getsource(LoreRepository._lock_novel)


def test_entity_update_and_delete_lock_target_row_for_cas() -> None:
    update_source = inspect.getsource(LoreRepository._update_entity_in_session)
    delete_source = inspect.getsource(LoreRepository._delete_entity_in_session)
    assert ".with_for_update()" in update_source
    assert ".with_for_update()" in delete_source
    assert "require_expected_updated_at" in update_source
    assert "require_expected_updated_at" in delete_source


def test_entity_delete_locks_novel_before_counting_references_and_deleting() -> None:
    source = inspect.getsource(LoreRepository.delete_entity)
    lock_index = source.index("_lock_novel")
    assert lock_index < source.index("_delete_entity_in_session")
    helper_source = inspect.getsource(LoreRepository._delete_entity_in_session)
    assert "_entity_delete_references" in helper_source
    assert "delete(model)" in helper_source
    assert "pg_advisory_xact_lock(:key)" in inspect.getsource(LoreRepository._lock_novel)


def test_entity_batch_uses_one_transaction_and_one_novel_lock() -> None:
    source = inspect.getsource(LoreRepository.apply_entity_mutations)
    assert source.count("session.begin()") == 1
    assert source.count("_lock_novel") == 1
    assert source.index("_lock_novel") < source.index("for mutation in mutations")
