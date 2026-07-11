from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from inkforge_core.app import create_app
from inkforge_core.auth.dependencies import get_current_user
from inkforge_core.auth.repository import AuthUser
from inkforge_core.lore.schemas import (
    CreateCharacterRequest,
    CreateFactionRequest,
    CreateGlossaryRequest,
    CreateItemRequest,
    CreateLocationRequest,
    RelationRequest,
)
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (CreateCharacterRequest, {"name": "角色", "unknown": "x"}),
        (CreateItemRequest, {"name": "物品", "unknown": "x"}),
        (CreateLocationRequest, {"name": "地点", "unknown": "x"}),
        (CreateFactionRequest, {"name": "势力", "unknown": "x"}),
        (CreateGlossaryRequest, {"term": "术语", "definition": "释义", "unknown": "x"}),
        (
            RelationRequest,
            {"characterId": "a", "targetId": "b", "relationType": "friend", "unknown": "x"},
        ),
    ],
)
def test_all_lore_requests_reject_unknown_fields(schema, payload) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


@pytest.mark.parametrize(
    "status",
    ["alive", "Active", "死亡", "", 1],
)
def test_character_status_is_exact_literal(status: object) -> None:
    with pytest.raises(ValidationError):
        CreateCharacterRequest.model_validate({"name": "角色", "currentStatus": status})


@pytest.mark.parametrize(
    "relation_type",
    ["friends", "Friend", "亲友", "", 1],
)
def test_relation_type_is_exact_literal(relation_type: object) -> None:
    with pytest.raises(ValidationError):
        RelationRequest.model_validate(
            {"characterId": "a", "targetId": "b", "relationType": relation_type}
        )


def test_openapi_contains_complete_lore_outline_and_reference_routes() -> None:
    paths = create_app(testing=True).openapi()["paths"]
    expected = {
        "/api/v1/novels/{novel_id}/characters",
        "/api/v1/novels/{novel_id}/items",
        "/api/v1/novels/{novel_id}/locations",
        "/api/v1/novels/{novel_id}/factions",
        "/api/v1/novels/{novel_id}/glossary",
        "/api/v1/novels/{novel_id}/foreshadowings",
        "/api/v1/novels/{novel_id}/relations",
        "/api/v1/novels/{novel_id}/outline",
        "/api/v1/novels/{novel_id}/outline-nodes",
        "/api/v1/novels/{novel_id}/plot-progress",
        "/api/v1/novels/{novel_id}/references",
        "/api/v1/novels/{novel_id}/references/search",
    }
    assert expected <= paths.keys()


def test_task8_modules_contain_no_schema_mutation_or_background_tasks() -> None:
    root = Path(__file__).parents[2] / "src" / "inkforge_core"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for folder in ("lore", "outlines", "references")
        for path in (root / folder).glob("*.py")
    ).lower()
    for forbidden in (
        "create_all",
        "drop_all",
        "alter table",
        "create table",
        "backgroundtasks",
        "alembic",
    ):
        assert forbidden not in source


def test_all_task8_success_routes_publish_explicit_response_schemas() -> None:
    paths = create_app(testing=True).openapi()["paths"]
    domain_markers = (
        "/characters",
        "/experiences",
        "/relations",
        "/items",
        "/locations",
        "/factions",
        "/glossary",
        "/story-background",
        "/world-setting",
        "/writing-bible",
        "/story-progress",
        "/outline",
        "/plot-progress",
        "/foreshadowings",
        "/references",
    )
    checked = 0
    for path, operations in paths.items():
        if not any(marker in path for marker in domain_markers):
            continue
        for method, operation in operations.items():
            if method == "delete" or operation.get("responses", {}).get("204") is not None:
                continue
            success = next(
                value for code, value in operation["responses"].items() if code.startswith("2")
            )
            schema = success["content"]["application/json"]["schema"]
            assert schema
            assert schema != {}
            checked += 1
    assert checked >= 25


def test_lore_success_response_is_filtered_by_declared_dto() -> None:
    class Service:
        async def list_entities(self, user_id, novel_id, kind):
            del user_id, novel_id, kind
            now = datetime(2026, 7, 11, tzinfo=UTC)
            return [
                {
                    "id": "item-1",
                    "name": "物品",
                    "aliases": None,
                    "type": None,
                    "rarity": None,
                    "effect": None,
                    "origin": None,
                    "description": None,
                    "ownerId": None,
                    "createdAt": now,
                    "updatedAt": now,
                }
            ]

    app = create_app(testing=True)
    app.state.lore_service = Service()
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="user-1",
        username="user",
        password_hash="固定哈希",  # noqa: S106
        credit_balance_micros=0,
    )
    response = TestClient(app).get("/api/v1/novels/novel-1/items")
    assert response.status_code == 200
    assert response.json()[0]["id"] == "item-1"
    assert "novelId" not in response.json()[0]
