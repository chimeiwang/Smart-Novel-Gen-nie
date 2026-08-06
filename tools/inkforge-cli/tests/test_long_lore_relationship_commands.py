from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any
from urllib.parse import quote

import pytest
from inkforge_cli.config import MemoryConfigStore
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import CliDependencies, CliInputError, CliRuntime


@dataclass
class RecordingApi:
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        self.calls.append((method, path, kwargs))
        return {
            "deletedType": "relation",
            "deletedId": "resource-1",
            "affected": {"relations": 1},
        }


def _module() -> ModuleType:
    return importlib.import_module("inkforge_cli.commands.long.lore_relationships")


def _spec(module: ModuleType, name: str) -> Any:
    return next(spec for spec in module.LORE_RELATIONSHIP_COMMAND_SPECS if spec.name == name)


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


def test_relationship_command_specs_have_exact_identity_contracts() -> None:
    specs = _module().LORE_RELATIONSHIP_COMMAND_SPECS

    assert {spec.name for spec in specs} == {
        "long.lore.relation.create",
        "long.lore.relation.update",
        "long.lore.relation.delete",
        "long.lore.experience.create",
        "long.lore.experience.update",
        "long.lore.experience.delete",
    }
    assert all(spec.mutation and spec.requiresIdentity for spec in specs)
    assert {
        spec.name for spec in specs if spec.requiresClientRequestId
    } == {
        "long.lore.relation.create",
        "long.lore.experience.create",
    }
    assert all(spec.fileOutput.kind == "none" for spec in specs)


@pytest.mark.parametrize(
    ("command", "payload", "method", "path", "body"),
    [
        (
            "long.lore.relation.create",
            {
                "novelId": "novel/一",
                "clientRequestId": "stable-relation-create-0001",
                "data": {
                    "characterId": "character-1",
                    "targetId": "character-2",
                    "relationType": "friend",
                    "intimacy": 80,
                    "description": None,
                },
                "profile": "production",
            },
            "POST",
            f"/api/v1/novels/{quote('novel/一', safe='')}/relations",
            {
                "characterId": "character-1",
                "targetId": "character-2",
                "relationType": "friend",
                "intimacy": 80,
                "description": None,
                "clientRequestId": "stable-relation-create-0001",
            },
        ),
        (
            "long.lore.relation.update",
            {
                "novelId": "novel-1",
                "relationId": "relation/一",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "data": {"description": None},
            },
            "PATCH",
            f"/api/v1/novels/novel-1/relations/{quote('relation/一', safe='')}",
            {"description": None, "expectedUpdatedAt": "2026-08-07T00:00:00Z"},
        ),
        (
            "long.lore.relation.delete",
            {
                "novelId": "novel-1",
                "relationId": "relation/一",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
            },
            "DELETE",
            f"/api/v1/novels/novel-1/relations/{quote('relation/一', safe='')}",
            {"expectedUpdatedAt": "2026-08-07T00:00:00Z"},
        ),
        (
            "long.lore.experience.create",
            {
                "novelId": "novel-1",
                "characterId": "character/一",
                "clientRequestId": "stable-experience-create-01",
                "data": {"chapterId": None, "content": "初次历练", "order": 1},
            },
            "POST",
            (
                "/api/v1/novels/novel-1/characters/"
                f"{quote('character/一', safe='')}/experiences"
            ),
            {
                "chapterId": None,
                "content": "初次历练",
                "order": 1,
                "clientRequestId": "stable-experience-create-01",
            },
        ),
        (
            "long.lore.experience.update",
            {
                "novelId": "novel-1",
                "experienceId": "experience/一",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "data": {"content": "更新后的经历"},
            },
            "PATCH",
            f"/api/v1/novels/novel-1/experiences/{quote('experience/一', safe='')}",
            {"content": "更新后的经历", "expectedUpdatedAt": "2026-08-07T00:00:00Z"},
        ),
        (
            "long.lore.experience.delete",
            {
                "novelId": "novel-1",
                "experienceId": "experience/一",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "profile": "production",
            },
            "DELETE",
            f"/api/v1/novels/novel-1/experiences/{quote('experience/一', safe='')}",
            {"expectedUpdatedAt": "2026-08-07T00:00:00Z"},
        ),
    ],
)
def test_relationship_commands_send_exact_public_requests(
    command: str,
    payload: dict[str, Any],
    method: str,
    path: str,
    body: dict[str, object],
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()

    result = spec.handler(_runtime(spec, api), payload)

    assert result == {
        "deletedType": "relation",
        "deletedId": "resource-1",
        "affected": {"relations": 1},
    }
    assert api.calls == [(method, path, {"json": body})]


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        (
            "long.lore.relation.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "stable-relation-create-0001",
                "data": {"targetId": "target", "relationType": "friend"},
            },
        ),
        (
            "long.lore.experience.create",
            {
                "novelId": "novel-1",
                "characterId": "character-1",
                "clientRequestId": "stable-experience-create-01",
                "data": {"order": 1},
            },
        ),
        (
            "long.lore.relation.update",
            {
                "novelId": "novel-1",
                "relationId": "relation-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "data": {},
            },
        ),
        (
            "long.lore.experience.update",
            {
                "novelId": "novel-1",
                "experienceId": "experience-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "data": {},
            },
        ),
    ],
)
def test_required_create_fields_and_non_empty_updates_are_enforced(
    command: str,
    payload: dict[str, Any],
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
            "long.lore.relation.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "short",
                "data": {
                    "characterId": "character-1",
                    "targetId": "target-1",
                    "relationType": "friend",
                },
            },
        ),
        (
            "long.lore.experience.update",
            {
                "novelId": "novel-1",
                "experienceId": 7,
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "data": {"content": "经历"},
            },
        ),
        (
            "long.lore.relation.delete",
            {
                "novelId": "novel-1",
                "relationId": "relation-1",
                "expectedUpdatedAt": None,
            },
        ),
        (
            "long.lore.experience.create",
            {
                "novelId": "novel-1",
                "characterId": "character-1",
                "clientRequestId": "stable-experience-create-01",
                "data": "not-an-object",
            },
        ),
    ],
)
def test_invalid_types_and_cas_are_rejected_without_requests(
    command: str,
    payload: dict[str, Any],
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
            "long.lore.relation.update",
            {
                "novelId": "novel-1",
                "relationId": "relation-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "data": {"characterId": "forbidden"},
            },
        ),
        (
            "long.lore.experience.update",
            {
                "novelId": "novel-1",
                "experienceId": "experience-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "data": {"unknown": "forbidden"},
            },
        ),
        (
            "long.lore.relation.delete",
            {
                "novelId": "novel-1",
                "relationId": "relation-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "outputFile": "forbidden.json",
            },
        ),
    ],
)
def test_unknown_fields_are_rejected_without_requests(
    command: str,
    payload: dict[str, Any],
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []
