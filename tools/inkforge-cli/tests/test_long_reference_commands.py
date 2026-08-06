from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from inkforge_cli.config import MemoryConfigStore
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import CliDependencies, CliInputError, CliRuntime


@dataclass
class RecordingApi:
    response: dict[str, object]
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        self.calls.append((method, path, kwargs))
        return self.response


def _module():
    return importlib.import_module("inkforge_cli.commands.long.references")


def _spec(name: str):
    return next(spec for spec in _module().REFERENCE_COMMAND_SPECS if spec.name == name)


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


def test_reference_specs_expose_only_four_safe_mutations() -> None:
    specs = _module().REFERENCE_COMMAND_SPECS

    assert {spec.name for spec in specs} == {
        "long.reference.create",
        "long.reference.update",
        "long.reference.delete",
        "long.reference.reindex",
    }
    assert all(spec.mutation and spec.requiresIdentity for spec in specs)
    assert all(spec.inputMode == "json" and spec.outputMode == "json" for spec in specs)
    assert all(spec.fileOutput.kind == "none" for spec in specs)
    assert {
        spec.name for spec in specs if spec.requiresClientRequestId
    } == {"long.reference.create"}


def test_reference_commands_send_exact_routes_bodies_and_preserve_results() -> None:
    novel_id = "novel/中文 ?"
    reference_id = "reference/中文 ?"
    encoded_novel = quote(novel_id, safe="")
    encoded_reference = quote(reference_id, safe="")
    cases = (
        (
            "long.reference.create",
            "POST",
            f"/api/v1/novels/{encoded_novel}/references",
            {
                "novelId": novel_id,
                "clientRequestId": "reference-create-0001",
                "title": "资料",
                "type": "note",
                "content": "正文",
                "sourceUrl": None,
                "profile": "production",
            },
            {
                "clientRequestId": "reference-create-0001",
                "title": "资料",
                "type": "note",
                "content": "正文",
                "sourceUrl": None,
            },
            {"id": "ref-1", "ragStatus": "disabled", "effective": True},
        ),
        (
            "long.reference.update",
            "PATCH",
            f"/api/v1/novels/{encoded_novel}/references/{encoded_reference}",
            {
                "novelId": novel_id,
                "referenceId": reference_id,
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "title": "新标题",
                "sourceUrl": None,
                "profile": "production",
            },
            {
                "title": "新标题",
                "sourceUrl": None,
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
            },
            {"id": "ref-1", "ragStatus": "failed", "errorMessage": "索引失败"},
        ),
        (
            "long.reference.delete",
            "DELETE",
            f"/api/v1/novels/{encoded_novel}/references/{encoded_reference}",
            {
                "novelId": novel_id,
                "referenceId": reference_id,
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "profile": "production",
            },
            {"expectedUpdatedAt": "2026-08-07T00:00:00Z"},
            {
                "deletedType": "reference",
                "deletedId": reference_id,
                "affected": {"reference": 1, "ragDocuments": 1, "ragChunks": 3},
            },
        ),
        (
            "long.reference.reindex",
            "POST",
            f"/api/v1/novels/{encoded_novel}/references/{encoded_reference}/reindex",
            {
                "novelId": novel_id,
                "referenceId": reference_id,
                "expectedContentHash": "a" * 64,
                "profile": "production",
            },
            {"expectedContentHash": "a" * 64},
            {"accepted": True},
        ),
    )

    for command, method, path, payload, body, response in cases:
        spec = _spec(command)
        api = RecordingApi(response)
        result = spec.handler(_runtime(spec, api), payload)
        assert result == response
        assert api.calls == [(method, path, {"json": body})]


@pytest.mark.parametrize("command", ["long.reference.create", "long.reference.update"])
def test_reference_content_file_is_read_losslessly(
    command: str,
    tmp_path: Path,
) -> None:
    content = "正文\r\n" + "甲" * 80_000 + "尾部😀e\u0301\r\n"
    content_file = tmp_path / "参考资料.txt"
    content_file.write_bytes(content.encode("utf-8"))
    spec = _spec(command)
    api = RecordingApi({"ragStatus": "disabled"})
    payload: dict[str, object] = {
        "novelId": "novel-1",
        "referenceId": "reference-1",
        "expectedUpdatedAt": "2026-08-07T00:00:00Z",
        "contentFile": str(content_file),
    }
    if command.endswith("create"):
        payload = {
            "novelId": "novel-1",
            "clientRequestId": "reference-create-0001",
            "title": "资料",
            "type": "note",
            "contentFile": str(content_file),
        }

    spec.handler(_runtime(spec, api), payload)

    assert api.calls[0][2]["json"]["content"] == content
    assert "contentFile" not in api.calls[0][2]["json"]


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        (
            "long.reference.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "reference-create-0001",
                "title": "资料",
                "type": "note",
            },
        ),
        (
            "long.reference.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "reference-create-0001",
                "title": "资料",
                "type": "note",
                "content": "正文",
                "contentFile": "正文.txt",
            },
        ),
        (
            "long.reference.update",
            {
                "novelId": "novel-1",
                "referenceId": "reference-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
            },
        ),
        (
            "long.reference.update",
            {
                "novelId": "novel-1",
                "referenceId": "reference-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "content": "正文",
                "contentFile": "正文.txt",
            },
        ),
        (
            "long.reference.reindex",
            {
                "novelId": "novel-1",
                "referenceId": "reference-1",
                "expectedContentHash": "BAD",
            },
        ),
        (
            "long.reference.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "too-short",
                "title": "资料",
                "type": "note",
                "content": "正文",
            },
        ),
        (
            "long.reference.create",
            {
                "novelId": "novel-1",
                "clientRequestId": "reference-create-0001",
                "title": "资料",
                "type": "pdf",
                "content": "正文",
            },
        ),
        (
            "long.reference.update",
            {
                "novelId": "novel-1",
                "referenceId": "reference-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "title": None,
            },
        ),
        (
            "long.reference.update",
            {
                "novelId": "novel-1",
                "referenceId": "reference-1",
                "expectedUpdatedAt": "2026-08-07T00:00:00Z",
                "sourceUrl": 7,
            },
        ),
        (
            "long.reference.delete",
            {
                "novelId": "novel-1",
                "referenceId": "reference-1",
                "expectedUpdatedAt": None,
            },
        ),
    ],
)
def test_invalid_reference_payloads_do_not_send_requests(
    command: str,
    payload: dict[str, object],
) -> None:
    spec = _spec(command)
    api = RecordingApi({})

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


@pytest.mark.parametrize("command", [
    "long.reference.create",
    "long.reference.update",
    "long.reference.delete",
    "long.reference.reindex",
])
@pytest.mark.parametrize("field", ["outputFile", "unexpected", "data"])
def test_reference_commands_reject_unknown_fields_without_request(
    command: str,
    field: str,
) -> None:
    base: dict[str, object]
    if command.endswith("create"):
        base = {
            "novelId": "novel-1",
            "clientRequestId": "reference-create-0001",
            "title": "资料",
            "type": "note",
            "content": "正文",
        }
    elif command.endswith("update"):
        base = {
            "novelId": "novel-1",
            "referenceId": "reference-1",
            "expectedUpdatedAt": "2026-08-07T00:00:00Z",
            "title": "新标题",
        }
    elif command.endswith("delete"):
        base = {
            "novelId": "novel-1",
            "referenceId": "reference-1",
            "expectedUpdatedAt": "2026-08-07T00:00:00Z",
        }
    else:
        base = {
            "novelId": "novel-1",
            "referenceId": "reference-1",
            "expectedContentHash": "a" * 64,
        }
    base[field] = "forbidden"
    spec = _spec(command)
    api = RecordingApi({})

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), base)

    assert api.calls == []
