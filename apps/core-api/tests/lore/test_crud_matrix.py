from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_core.lore.schemas import (
    CreateCharacterRequest,
    CreateFactionRequest,
    CreateGlossaryRequest,
    CreateItemRequest,
    CreateLocationRequest,
    DeleteEntityRequest,
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

    async def create_entity(self, novel_id, user_id, kind, client_request_id, fields):
        self.call = ("create", novel_id, user_id, kind, client_request_id, fields)
        return {"id": "new", "effective": True, **fields}

    async def update_entity(
        self, novel_id, user_id, kind, entity_id, fields, expected_updated_at
    ):
        self.call = (
            "update",
            novel_id,
            user_id,
            kind,
            entity_id,
            fields,
            expected_updated_at,
        )
        return {"id": entity_id, **fields}

    async def delete_entity(self, novel_id, user_id, kind, entity_id, expected_updated_at):
        self.call = (
            "delete",
            novel_id,
            user_id,
            kind,
            entity_id,
            expected_updated_at,
        )
        return {"deletedType": kind, "deletedId": entity_id, "affected": {}}


CASES = [
    (
        "characters",
        CreateCharacterRequest,
        {"name": "角色", "clientRequestId": "request-character"},
        UpdateCharacterRequest,
        {"name": "新角色", "expectedUpdatedAt": "2026-08-06T00:00:00Z"},
    ),
    (
        "items",
        CreateItemRequest,
        {"name": "物品", "clientRequestId": "request-item-000"},
        UpdateItemRequest,
        {"name": "新物品", "expectedUpdatedAt": "2026-08-06T00:00:00Z"},
    ),
    (
        "locations",
        CreateLocationRequest,
        {"name": "地点", "clientRequestId": "request-location"},
        UpdateLocationRequest,
        {"name": "新地点", "expectedUpdatedAt": "2026-08-06T00:00:00Z"},
    ),
    (
        "factions",
        CreateFactionRequest,
        {"name": "势力", "clientRequestId": "request-faction-"},
        UpdateFactionRequest,
        {"name": "新势力", "expectedUpdatedAt": "2026-08-06T00:00:00Z"},
    ),
    (
        "glossary",
        CreateGlossaryRequest,
        {"term": "术语", "definition": "释义", "clientRequestId": "request-glossary"},
        UpdateGlossaryRequest,
        {"term": "新术语", "expectedUpdatedAt": "2026-08-06T00:00:00Z"},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "create_schema", "create_payload", "update_schema", "update_payload"), CASES
)
async def test_each_lore_kind_supports_list(
    kind, create_schema, create_payload, update_schema, update_payload
) -> None:
    del create_schema, create_payload, update_schema, update_payload
    repository = MatrixRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    await service.list_entities("user-1", "novel-1", kind)
    assert repository.call == ("list", "novel-1", "user-1", kind)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "create_schema", "create_payload", "update_schema", "update_payload"), CASES
)
async def test_each_lore_kind_supports_create(
    kind, create_schema, create_payload, update_schema, update_payload
) -> None:
    del update_schema, update_payload
    repository = MatrixRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    create_body = create_schema.model_validate(create_payload)
    await service.create_entity("user-1", "novel-1", kind, create_body)
    assert repository.call[0:4] == ("create", "novel-1", "user-1", kind)
    assert repository.call[4] == create_body.clientRequestId
    assert "clientRequestId" not in repository.call[5]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "create_schema", "create_payload", "update_schema", "update_payload"), CASES
)
async def test_each_lore_kind_supports_update(
    kind, create_schema, create_payload, update_schema, update_payload
) -> None:
    del create_schema, create_payload
    repository = MatrixRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    update_body = update_schema.model_validate(update_payload)
    await service.update_entity("user-1", "novel-1", kind, "entity-1", update_body)
    assert repository.call[0:5] == ("update", "novel-1", "user-1", kind, "entity-1")
    assert "expectedUpdatedAt" not in repository.call[5]
    assert repository.call[6] == datetime(2026, 8, 6, tzinfo=UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "create_schema", "create_payload", "update_schema", "update_payload"), CASES
)
async def test_each_lore_kind_supports_delete(
    kind, create_schema, create_payload, update_schema, update_payload
) -> None:
    del create_schema, create_payload, update_schema, update_payload
    repository = MatrixRepository()
    service = LoreService(repository)  # type: ignore[arg-type]
    body = DeleteEntityRequest(expectedUpdatedAt="2026-08-06T00:00:00Z")
    result = await service.delete_entity("user-1", "novel-1", kind, "entity-1", body)
    assert repository.call == (
        "delete",
        "novel-1",
        "user-1",
        kind,
        "entity-1",
        datetime(2026, 8, 6, tzinfo=UTC),
    )
    assert result == {"deletedType": kind, "deletedId": "entity-1", "affected": {}}
