from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

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
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        self.calls.append((method, path, kwargs))
        return {"updatedAt": "2026-08-06T00:00:01Z"}


def _module() -> ModuleType:
    return importlib.import_module("inkforge_cli.commands.long.chapters")


def _spec(module: ModuleType, name: str) -> Any:
    return next(spec for spec in module.CHAPTER_COMMAND_SPECS if spec.name == name)


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
        profile="default",
        origin="http://127.0.0.1:8000",
    )


def test_chapter_command_specs_are_mutations_without_request_ids() -> None:
    specs = _module().CHAPTER_COMMAND_SPECS

    assert {spec.name for spec in specs} == {
        "long.chapter.create",
        "long.chapter.save",
        "long.chapter.status",
        "long.chapter.progress.save",
    }
    assert all(spec.mutation and spec.requiresIdentity for spec in specs)
    assert all(not spec.requiresClientRequestId for spec in specs)
    assert all(spec.fileOutput.kind == "none" for spec in specs)


def test_chapter_create_sends_exact_public_route_without_request_body() -> None:
    module = _module()
    spec = _spec(module, "long.chapter.create")
    api = RecordingApi()

    result = spec.handler(
        _runtime(spec, api),
        {"novelId": "novel /?#", "profile": "production"},
    )

    assert result == {"updatedAt": "2026-08-06T00:00:01Z"}
    assert api.calls == [("POST", "/api/v1/novels/novel%20%2F%3F%23/chapters", {})]


@pytest.mark.parametrize("novel_id", [None, "", 1, True])
def test_chapter_create_rejects_missing_or_invalid_novel_id(
    novel_id: object,
) -> None:
    module = _module()
    spec = _spec(module, "long.chapter.create")
    api = RecordingApi()
    payload: dict[str, object] = {}
    if novel_id is not None:
        payload["novelId"] = novel_id

    with pytest.raises(CliInputError, match="novelId"):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


@pytest.mark.parametrize(
    ("command", "payload", "method", "path", "body"),
    [
        (
            "long.chapter.save",
            {
                "chapterId": "chapter/1",
                "title": "第一章",
                "content": "正文",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                "profile": "default",
            },
            "PATCH",
            "/api/v1/chapters/chapter%2F1",
            {
                "title": "第一章",
                "content": "正文",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            },
        ),
        (
            "long.chapter.status",
            {
                "chapterId": "chapter/1",
                "status": "review",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                "profile": "default",
            },
            "PATCH",
            "/api/v1/chapters/chapter%2F1/status",
            {
                "status": "review",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            },
        ),
        (
            "long.chapter.progress.save",
            {
                "chapterId": "chapter/1",
                "content": "阶段正文",
                "expectedUpdatedAt": None,
                "profile": "default",
            },
            "PUT",
            "/api/v1/chapters/chapter%2F1/progress",
            {"content": "阶段正文", "expectedUpdatedAt": None},
        ),
    ],
)
def test_chapter_commands_send_exact_public_routes_and_cas_bodies(
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

    assert result == {"updatedAt": "2026-08-06T00:00:01Z"}
    assert api.calls == [(method, path, {"json": body})]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "chapterId": "chapter-1",
            "title": "第一章",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
        },
        {
            "chapterId": "chapter-1",
            "title": "第一章",
            "content": "正文",
            "contentFile": "chapter.txt",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
        },
    ],
)
def test_chapter_save_requires_exactly_one_content_source(
    payload: dict[str, Any],
) -> None:
    module = _module()
    spec = _spec(module, "long.chapter.save")
    api = RecordingApi()

    with pytest.raises(CliInputError, match="content"):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


def test_chapter_save_reads_content_file_without_changing_exact_utf8(
    tmp_path: Path,
) -> None:
    module = _module()
    spec = _spec(module, "long.chapter.save")
    api = RecordingApi()
    content = "正文\r\n" + "甲" * 80_000 + "尾部😀e\u0301\r\n"
    content_file = tmp_path / "chapter.txt"
    content_file.write_bytes(content.encode("utf-8"))

    spec.handler(
        _runtime(spec, api),
        {
            "chapterId": "chapter-1",
            "title": "第一章",
            "contentFile": str(content_file),
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            "profile": "production",
        },
    )

    assert api.calls[0][2]["json"] == {
        "title": "第一章",
        "content": content,
        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
    }


@pytest.mark.parametrize("payload", [b"\xff", b"\xe4\xb8"])
def test_chapter_content_file_errors_map_to_local_file_exit_code(
    tmp_path: Path,
    payload: bytes,
) -> None:
    module = _module()
    spec = _spec(module, "long.chapter.save")
    api = RecordingApi()
    content_file = tmp_path / "invalid.txt"
    content_file.write_bytes(payload)

    with pytest.raises(UnicodeError) as caught:
        spec.handler(
            _runtime(spec, api),
            {
                "chapterId": "chapter-1",
                "title": "第一章",
                "contentFile": str(content_file),
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            },
        )

    assert command_exit_code(spec, caught.value) == 6
    assert api.calls == []


def test_progress_requires_explicit_expected_updated_at_even_when_null() -> None:
    module = _module()
    spec = _spec(module, "long.chapter.progress.save")
    api = RecordingApi()

    with pytest.raises(CliInputError, match="expectedUpdatedAt"):
        spec.handler(
            _runtime(spec, api),
            {"chapterId": "chapter-1", "content": "首次进展"},
        )

    assert api.calls == []
