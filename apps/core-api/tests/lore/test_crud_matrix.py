from __future__ import annotations

from typing import Any

import pytest
from inkforge_core.lore.schemas import (
    CreateCharacterRequest,
    CreateFactionRequest,
    CreateGlossaryRequest,
    CreateItemRequest,
    CreateLocationRequest,
    UpdateCharacterRequest,
    UpdateFactionRequest,
    UpdateGlossaryRequest,
    UpdateItemRequest,
    UpdateLocationRequest,
)
from inkforge_core.lore.service import LoreService


class MatrixRepository:
    def __init__(self) -> None:
        self.call: tuple[Any, ...] | None = None

    async def list_entities(self, novel_id, user_id, kind):
        self.call = ("list", novel_id, user_id, kind)
        return []

    async def create_entity(self, novel_id, user_id, kind, fields):
        self.call = ("create", novel_id, user_id, kind, fields)
        return {"id": "new", **fields}

    async def update_entity(self, novel_id, user_id, kind, entity_id, fields):
        self.call = ("update", novel_id, user_id, kind, entity_id, fields)
        return {"id": entity_id, **fields}

    async def delete_entity(self, novel_id, user_id, kind, entity_id):
        self.call = ("delete", novel_id, user_id, kind, entity_id)


CASES = [
    ("characters", CreateCharacterRequest(name="角色"), UpdateCharacterRequest(name="新角色")),
    ("items", CreateItemRequest(name="物品"), UpdateItemRequest(name="新物品")),
    ("locations", CreateLocationRequest(name="地点"), UpdateLocationRequest(name="新地点")),
    ("factions", CreateFactionRequest(name="势力"), UpdateFactionRequest(name="新势力")),
    (
        "glossary",
        CreateGlossaryRequest(term="术语", definition="释义"),
        UpdateGlossaryRequest(term="新术语"),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "create_body", "update_body"), CASES)
async def test_each_lore_kind_supports_list(kind, create_body, update_body) -> None:
    repository = MatrixRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    await service.list_entities("user-1", "novel-1", kind)
    assert repository.call == ("list", "novel-1", "user-1", kind)


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "create_body", "update_body"), CASES)
async def test_each_lore_kind_supports_create(kind, create_body, update_body) -> None:
    repository = MatrixRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    await service.create_entity("user-1", "novel-1", kind, create_body)
    assert repository.call[0:4] == ("create", "novel-1", "user-1", kind)


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "create_body", "update_body"), CASES)
async def test_each_lore_kind_supports_update(kind, create_body, update_body) -> None:
    repository = MatrixRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    await service.update_entity("user-1", "novel-1", kind, "entity-1", update_body)
    assert repository.call[0:5] == ("update", "novel-1", "user-1", kind, "entity-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "create_body", "update_body"), CASES)
async def test_each_lore_kind_supports_delete(kind, create_body, update_body) -> None:
    repository = MatrixRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    await service.delete_entity("user-1", "novel-1", kind, "entity-1")
    assert repository.call == ("delete", "novel-1", "user-1", kind, "entity-1")
