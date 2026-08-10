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
    response: dict[str, object] = field(
        default_factory=lambda: {
            "id": "node-1",
            "updatedAt": "2026-08-10T00:00:01Z",
            "effective": True,
        }
    )
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        self.calls.append((method, path, kwargs))
        return self.response


def _module() -> ModuleType:
    return importlib.import_module("inkforge_cli.commands.long.outline_nodes")


def _spec(module: ModuleType, name: str) -> Any:
    return next(spec for spec in module.OUTLINE_NODE_COMMAND_SPECS if spec.name == name)


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


def test_outline_node_command_specs_are_exact_mutations() -> None:
    specs = _module().OUTLINE_NODE_COMMAND_SPECS

    assert {spec.name for spec in specs} == {
        "long.outline-node.create",
        "long.outline-node.update",
        "long.outline-node.delete",
    }
    assert all(spec.mutation and spec.requiresIdentity for spec in specs)
    assert {spec.name for spec in specs if spec.requiresClientRequestId} == {
        "long.outline-node.create"
    }


def test_outline_node_create_sends_exact_route_and_body() -> None:
    module = _module()
    spec = _spec(module, "long.outline-node.create")
    api = RecordingApi()
    novel_id = "novel/中文 ?"
    data = {
        "title": "第一卷",
        "kind": "stage",
        "content": "卷目标",
        "chapterStartOrder": 1,
        "chapterEndOrder": 30,
    }

    result = spec.handler(
        _runtime(spec, api),
        {
            "novelId": novel_id,
            "clientRequestId": "outline-node-123456",
            "data": data,
        },
    )

    assert result == api.response
    assert api.calls == [(
        "POST",
        f"/api/v1/novels/{quote(novel_id, safe='')}/outline-nodes",
        {"json": {**data, "clientRequestId": "outline-node-123456"}},
    )]


def test_outline_node_update_and_delete_send_cas_body() -> None:
    module = _module()
    api = RecordingApi()
    novel_id = "novel/中文 ?"
    node_id = "node/中文 ?"
    expected = "2026-08-10T00:00:00Z"

    update_spec = _spec(module, "long.outline-node.update")
    update_spec.handler(
        _runtime(update_spec, api),
        {
            "novelId": novel_id,
            "outlineNodeId": node_id,
            "expectedUpdatedAt": expected,
            "data": {"title": "第一卷·更新"},
        },
    )
    delete_spec = _spec(module, "long.outline-node.delete")
    delete_spec.handler(
        _runtime(delete_spec, api),
        {
            "novelId": novel_id,
            "outlineNodeId": node_id,
            "expectedUpdatedAt": expected,
        },
    )

    item_path = (
        f"/api/v1/novels/{quote(novel_id, safe='')}/outline-nodes/"
        f"{quote(node_id, safe='')}"
    )
    assert api.calls == [
        (
            "PATCH",
            item_path,
            {"json": {"title": "第一卷·更新", "expectedUpdatedAt": expected}},
        ),
        ("DELETE", item_path, {"json": {"expectedUpdatedAt": expected}}),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "novelId": "novel-1",
            "clientRequestId": "outline-node-123456",
            "data": {"title": "第一卷", "kind": "unknown"},
        },
        {
            "novelId": "novel-1",
            "clientRequestId": "outline-node-123456",
            "data": {
                "title": "第一卷",
                "kind": "stage",
                "chapterStartOrder": 1,
            },
        },
    ],
)
def test_outline_node_create_rejects_invalid_structure(payload: dict[str, object]) -> None:
    module = _module()
    spec = _spec(module, "long.outline-node.create")

    with pytest.raises(CliInputError) as caught:
        spec.handler(_runtime(spec, RecordingApi()), payload)

    assert caught.value.code == "INVALID_DATA_FIELD"
