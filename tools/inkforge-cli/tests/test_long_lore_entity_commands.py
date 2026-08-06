from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any
from urllib.parse import quote

import pytest
from inkforge_cli.config import MemoryConfigStore
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import (
    CliDependencies,
    CliInputError,
    CliRuntime,
    command_exit_code,
)


@dataclass
class RecordingApi:
    response: dict[str, object] = field(
        default_factory=lambda: {"id": "entity-1", "updatedAt": "v2"},
    )
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        self.calls.append((method, path, kwargs))
        return self.response


def _module() -> ModuleType:
    return importlib.import_module("inkforge_cli.commands.long.lore_entities")


def _spec(module: ModuleType, name: str) -> Any:
    return next(spec for spec in module.LORE_ENTITY_COMMAND_SPECS if spec.name == name)


def _runtime(spec: Any, api: RecordingApi) -> CliRuntime:
    return CliRuntime(
        spec=spec,
        argv=(),
        dependencies=CliDependencies(
            api_factory=lambda origin, token=None: api,
            config_store=MemoryConfigStore(),
            credential_store=MemoryCredentialStore(),
            getpass_fn=lambda prompt: "unused",
            stdin_isatty=lambda: False,
        ),
        api=api,
        profile="production",
        origin="https://inkforge.cn",
    )


RESOURCE_CASES = (
    (
        "character",
        "characters",
        "characterId",
        {"name": "沈砚", "aliases": None, "currentStatus": "active"},
        {"personality": "谨慎", "statusNote": None},
    ),
    (
        "location",
        "locations",
        "locationId",
        {"name": "云海城", "parentId": None, "climate": "湿润"},
        {"culture": "海贸", "description": None},
    ),
    (
        "faction",
        "factions",
        "factionId",
        {"name": "观星阁", "baseId": None, "type": "宗门"},
        {"description": "中立", "aliases": None},
    ),
    (
        "item",
        "items",
        "itemId",
        {"name": "照骨镜", "ownerId": None, "rarity": "稀有"},
        {"effect": "显形", "origin": None},
    ),
    (
        "glossary",
        "glossary",
        "glossaryId",
        {"term": "灵潮", "definition": "周期性灵气涨落", "category": None},
        {"definition": "百年一次", "category": "世界规则"},
    ),
)


def test_entity_command_specs_are_exact_mutations() -> None:
    specs = _module().LORE_ENTITY_COMMAND_SPECS
    expected = {
        f"long.lore.{resource}.{operation}"
        for resource, *_ in RESOURCE_CASES
        for operation in ("create", "update", "delete")
    }

    assert {spec.name for spec in specs} == expected
    assert all(spec.inputMode == "json" and spec.outputMode == "json" for spec in specs)
    assert all(spec.fileOutput.kind == "none" for spec in specs)
    assert all(spec.mutation and spec.requiresIdentity for spec in specs)
    assert {
        spec.name for spec in specs if spec.requiresClientRequestId
    } == {name for name in expected if name.endswith(".create")}


@pytest.mark.parametrize(
    ("resource", "path_segment", "id_field", "create_data", "update_data"),
    RESOURCE_CASES,
)
def test_entity_create_sends_exact_route_and_body(
    resource: str,
    path_segment: str,
    id_field: str,
    create_data: dict[str, object],
    update_data: dict[str, object],
) -> None:
    del id_field, update_data
    module = _module()
    spec = _spec(module, f"long.lore.{resource}.create")
    api = RecordingApi()
    novel_id = "novel/中文 ?"

    result = spec.handler(
        _runtime(spec, api),
        {
            "novelId": novel_id,
            "clientRequestId": "request-1234567890",
            "profile": "production",
            "data": create_data,
        },
    )

    assert result == api.response
    assert api.calls == [(
        "POST",
        f"/api/v1/novels/{quote(novel_id, safe='')}/{path_segment}",
        {"json": {**create_data, "clientRequestId": "request-1234567890"}},
    )]


@pytest.mark.parametrize(
    ("resource", "path_segment", "id_field", "create_data", "update_data"),
    RESOURCE_CASES,
)
def test_entity_update_sends_exact_route_and_body(
    resource: str,
    path_segment: str,
    id_field: str,
    create_data: dict[str, object],
    update_data: dict[str, object],
) -> None:
    del create_data
    module = _module()
    spec = _spec(module, f"long.lore.{resource}.update")
    api = RecordingApi()
    novel_id = "novel/中文 ?"
    entity_id = "entity/中文 ?"

    result = spec.handler(
        _runtime(spec, api),
        {
            "novelId": novel_id,
            id_field: entity_id,
            "expectedUpdatedAt": "2026-08-07T00:00:00Z",
            "profile": "production",
            "data": update_data,
        },
    )

    assert result == api.response
    assert api.calls == [(
        "PATCH",
        (
            f"/api/v1/novels/{quote(novel_id, safe='')}/{path_segment}/"
            f"{quote(entity_id, safe='')}"
        ),
        {
            "json": {
                **update_data,
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
            },
        },
    )]


@pytest.mark.parametrize(
    ("resource", "path_segment", "id_field", "create_data", "update_data"),
    RESOURCE_CASES,
)
def test_entity_delete_preserves_core_impact_response(
    resource: str,
    path_segment: str,
    id_field: str,
    create_data: dict[str, object],
    update_data: dict[str, object],
) -> None:
    del create_data, update_data
    module = _module()
    spec = _spec(module, f"long.lore.{resource}.delete")
    impact = {
        "deletedType": resource,
        "deletedId": "entity/中文 ?",
        "affected": {"relations": 2},
    }
    api = RecordingApi(response=impact)

    result = spec.handler(
        _runtime(spec, api),
        {
            "novelId": "novel/中文 ?",
            id_field: "entity/中文 ?",
            "expectedUpdatedAt": "2026-08-07T00:00:00Z",
            "profile": "production",
        },
    )

    assert result == impact
    assert api.calls == [(
        "DELETE",
        (
            f"/api/v1/novels/{quote('novel/中文 ?', safe='')}/{path_segment}/"
            f"{quote('entity/中文 ?', safe='')}"
        ),
        {"json": {"expectedUpdatedAt": "2026-08-07T00:00:00Z"}},
    )]


@pytest.mark.parametrize("resource", [case[0] for case in RESOURCE_CASES])
@pytest.mark.parametrize("field", ["outputFile", "unexpected"])
def test_unknown_top_level_fields_are_rejected_without_request(
    resource: str,
    field: str,
) -> None:
    module = _module()
    spec = _spec(module, f"long.lore.{resource}.create")
    api = RecordingApi()

    with pytest.raises(CliInputError) as caught:
        spec.handler(
            _runtime(spec, api),
            {
                "novelId": "novel-1",
                "clientRequestId": "request-1234567890",
                "data": RESOURCE_CASES[
                    [case[0] for case in RESOURCE_CASES].index(resource)
                ][3],
                field: "forbidden",
            },
        )

    assert caught.value.code == "UNEXPECTED_FIELDS"
    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        (
            "long.lore.character.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "request-1234567890",
                "data": {},
            },
        ),
        (
            "long.lore.location.update",
            {
                "novelId": "novel-1",
                "locationId": "location-1",
                "expectedUpdatedAt": "v1",
                "data": {},
            },
        ),
        (
            "long.lore.faction.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "request-1234567890",
                "data": {"unknown": "value"},
            },
        ),
        (
            "long.lore.item.update",
            {
                "novelId": "novel-1",
                "itemId": "item-1",
                "expectedUpdatedAt": "v1",
                "data": "not-object",
            },
        ),
    ],
)
def test_invalid_or_empty_data_is_rejected_without_request(
    command: str,
    payload: dict[str, object],
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        (
            "long.lore.character.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "request-1234567890",
                "data": {"name": 7},
            },
        ),
        (
            "long.lore.character.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "request-1234567890",
                "data": {"name": "沈砚", "currentStatus": "invalid"},
            },
        ),
        (
            "long.lore.glossary.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "request-1234567890",
                "data": {"term": "灵潮"},
            },
        ),
        (
            "long.lore.location.update",
            {
                "novelId": "novel-1",
                "locationId": "location-1",
                "expectedUpdatedAt": "v1",
                "data": {"description": 7},
            },
        ),
    ],
)
def test_business_field_type_and_create_requirements_fail_before_request(
    command: str,
    payload: dict[str, object],
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


@pytest.mark.parametrize(
    ("command", "id_field", "business_field"),
    [
        ("long.lore.character.update", "characterId", "name"),
        ("long.lore.character.update", "characterId", "currentStatus"),
        ("long.lore.location.update", "locationId", "name"),
        ("long.lore.faction.update", "factionId", "name"),
        ("long.lore.item.update", "itemId", "name"),
        ("long.lore.glossary.update", "glossaryId", "term"),
        ("long.lore.glossary.update", "glossaryId", "definition"),
    ],
)
def test_update_rejects_required_business_field_null_without_request(
    command: str,
    id_field: str,
    business_field: str,
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()

    with pytest.raises(CliInputError) as caught:
        spec.handler(
            _runtime(spec, api),
            {
                "novelId": "novel-1",
                id_field: "entity-1",
                "expectedUpdatedAt": "v1",
                "data": {business_field: None},
            },
        )

    assert caught.value.code == "INVALID_DATA_FIELD"
    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []


def test_glossary_definition_preserves_core_empty_string_semantics() -> None:
    module = _module()
    spec = _spec(module, "long.lore.glossary.create")
    api = RecordingApi()

    spec.handler(
        _runtime(spec, api),
        {
            "novelId": "novel-1",
            "clientRequestId": "request-1234567890",
            "data": {"term": "灵潮", "definition": ""},
        },
    )

    assert api.calls[0][2]["json"] == {
        "term": "灵潮",
        "definition": "",
        "clientRequestId": "request-1234567890",
    }


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        (
            "long.lore.character.create",
            {
                "novelId": 7,
                "clientRequestId": "request-1234567890",
                "data": {"name": "沈砚"},
            },
        ),
        (
            "long.lore.character.create",
            {
                "novelId": "novel-1",
                "clientRequestId": 7,
                "data": {"name": "沈砚"},
            },
        ),
        (
            "long.lore.location.update",
            {
                "novelId": "novel-1",
                "locationId": None,
                "expectedUpdatedAt": "v1",
                "data": {"name": "新地点"},
            },
        ),
        (
            "long.lore.item.delete",
            {
                "novelId": "novel-1",
                "itemId": "item-1",
                "expectedUpdatedAt": None,
            },
        ),
    ],
)
def test_identifier_and_version_type_errors_fail_before_request(
    command: str,
    payload: dict[str, object],
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()

    with pytest.raises(CliInputError) as caught:
        spec.handler(_runtime(spec, api), payload)

    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []
