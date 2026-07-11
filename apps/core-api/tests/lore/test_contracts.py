from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_core.app import create_app
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
