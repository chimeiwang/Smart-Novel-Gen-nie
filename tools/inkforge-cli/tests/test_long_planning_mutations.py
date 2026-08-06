from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
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
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        self.calls.append((method, path, kwargs))
        return {"updatedAt": "2026-08-07T00:00:01Z"}


def _module() -> ModuleType:
    return importlib.import_module("inkforge_cli.commands.long.planning_mutations")


def _spec(module: ModuleType, name: str) -> Any:
    return next(spec for spec in module.PLANNING_COMMAND_SPECS if spec.name == name)


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


COMMAND_CASES = (
    (
        "long.lore.story-background.save",
        "story-background",
        {"content": "故事背景"},
        {"content": "故事背景", "expectedUpdatedAt": None},
    ),
    (
        "long.lore.world-setting.save",
        "world-setting",
        {"content": "世界设定"},
        {"content": "世界设定", "expectedUpdatedAt": None},
    ),
    (
        "long.lore.story-progress.save",
        "story-progress",
        {"content": "故事进展"},
        {"content": "故事进展", "expectedUpdatedAt": None},
    ),
    (
        "long.lore.writing-bible.save",
        "writing-bible",
        {"data": {"genre": "末法修仙", "storyLengthProfile": "long_serial"}},
        {
            "genre": "末法修仙",
            "storyLengthProfile": "long_serial",
            "expectedUpdatedAt": None,
        },
    ),
    (
        "long.plot-progress.save",
        "plot-progress",
        {"data": {"currentStage": "开篇", "currentGoal": None}},
        {"currentStage": "开篇", "currentGoal": None, "expectedUpdatedAt": None},
    ),
)


def test_planning_command_specs_are_explicit_cas_mutations_without_request_ids() -> None:
    specs = _module().PLANNING_COMMAND_SPECS

    assert {spec.name for spec in specs} == {case[0] for case in COMMAND_CASES}
    assert all(spec.mutation and spec.requiresIdentity for spec in specs)
    assert all(not spec.requiresClientRequestId for spec in specs)
    assert all(spec.fileOutput.kind == "none" for spec in specs)


@pytest.mark.parametrize(("command", "suffix", "input_fields", "body"), COMMAND_CASES)
def test_planning_commands_send_exact_public_routes_and_bodies(
    command: str,
    suffix: str,
    input_fields: dict[str, object],
    body: dict[str, object],
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()
    novel_id = "novel/中文 ?"

    result = spec.handler(
        _runtime(spec, api),
        {
            "novelId": novel_id,
            "expectedUpdatedAt": None,
            "profile": "production",
            **input_fields,
        },
    )

    assert result == {"updatedAt": "2026-08-07T00:00:01Z"}
    assert api.calls == [(
        "PUT",
        f"/api/v1/novels/{quote(novel_id, safe='')}/{suffix}",
        {"json": body},
    )]


@pytest.mark.parametrize("command", [case[0] for case in COMMAND_CASES])
def test_expected_updated_at_must_be_explicit_and_may_be_null(command: str) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()
    payload: dict[str, object] = {"novelId": "novel-1"}
    if command.endswith(("writing-bible.save", "plot-progress.save")):
        payload["data"] = (
            {"genre": "仙侠"}
            if "writing-bible" in command
            else {"currentStage": "开篇"}
        )
    else:
        payload["content"] = "正文"

    with pytest.raises(CliInputError, match="expectedUpdatedAt") as caught:
        spec.handler(_runtime(spec, api), payload)

    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []


@pytest.mark.parametrize(
    "command",
    [
        "long.lore.story-background.save",
        "long.lore.world-setting.save",
        "long.lore.story-progress.save",
    ],
)
@pytest.mark.parametrize(
    "content_fields",
    [{}, {"content": "正文", "contentFile": "content.txt"}],
)
def test_text_planning_commands_require_exactly_one_content_source(
    command: str,
    content_fields: dict[str, str],
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()

    with pytest.raises(CliInputError, match="content"):
        spec.handler(
            _runtime(spec, api),
            {"novelId": "novel-1", "expectedUpdatedAt": None, **content_fields},
        )

    assert api.calls == []


def test_content_file_is_sent_as_exact_utf8_text(tmp_path: Path) -> None:
    module = _module()
    spec = _spec(module, "long.lore.story-background.save")
    api = RecordingApi()
    content = "正文\r\n" + "甲" * 80_000 + "尾部😄e\u0301\r\n"
    content_file = tmp_path / "背景.txt"
    content_file.write_bytes(content.encode("utf-8"))

    spec.handler(
        _runtime(spec, api),
        {
            "novelId": "novel-1",
            "contentFile": str(content_file),
            "expectedUpdatedAt": "2026-08-07T00:00:00Z",
        },
    )

    assert api.calls[0][2]["json"] == {
        "content": content,
        "expectedUpdatedAt": "2026-08-07T00:00:00Z",
    }


@pytest.mark.parametrize("raw", [b"\xff", b"\xe4\xb8"])
def test_invalid_utf8_maps_to_local_file_exit_code(tmp_path: Path, raw: bytes) -> None:
    module = _module()
    spec = _spec(module, "long.lore.story-background.save")
    api = RecordingApi()
    content_file = tmp_path / "invalid.txt"
    content_file.write_bytes(raw)

    with pytest.raises(UnicodeError) as caught:
        spec.handler(
            _runtime(spec, api),
            {
                "novelId": "novel-1",
                "contentFile": str(content_file),
                "expectedUpdatedAt": None,
            },
        )

    assert command_exit_code(spec, caught.value) == 6
    assert api.calls == []


@pytest.mark.parametrize("field", ["outputFile", "unexpected"])
@pytest.mark.parametrize("command", [case[0] for case in COMMAND_CASES])
def test_unknown_top_level_fields_are_rejected_without_request(
    command: str,
    field: str,
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()
    payload: dict[str, object] = {
        "novelId": "novel-1",
        "expectedUpdatedAt": None,
        field: "forbidden",
    }
    payload.update(
        {"data": {"genre": "仙侠"} if "writing-bible" in command else {"currentStage": "开篇"}}
        if command.endswith(("writing-bible.save", "plot-progress.save"))
        else {"content": "正文"},
    )

    with pytest.raises(CliInputError) as caught:
        spec.handler(_runtime(spec, api), payload)

    assert caught.value.code == "UNEXPECTED_FIELDS"
    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []


@pytest.mark.parametrize(
    ("command", "data"),
    [
        ("long.lore.writing-bible.save", {}),
        ("long.lore.writing-bible.save", {"unknown": "value"}),
        ("long.plot-progress.save", {}),
        ("long.plot-progress.save", {"unknown": "value"}),
    ],
)
def test_structured_data_requires_allowed_business_fields(
    command: str,
    data: dict[str, object],
) -> None:
    module = _module()
    spec = _spec(module, command)
    api = RecordingApi()

    with pytest.raises(CliInputError):
        spec.handler(
            _runtime(spec, api),
            {"novelId": "novel-1", "expectedUpdatedAt": None, "data": data},
        )

    assert api.calls == []


def test_writing_bible_rejects_short_medium_profile() -> None:
    module = _module()
    spec = _spec(module, "long.lore.writing-bible.save")
    api = RecordingApi()

    with pytest.raises(CliInputError, match="short_medium") as caught:
        spec.handler(
            _runtime(spec, api),
            {
                "novelId": "novel-1",
                "expectedUpdatedAt": None,
                "data": {"storyLengthProfile": "short_medium"},
            },
        )

    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []


@pytest.mark.parametrize("novel_id", [None, "", 7])
def test_novel_id_must_be_a_non_empty_string(novel_id: object) -> None:
    module = _module()
    spec = _spec(module, "long.lore.story-progress.save")
    api = RecordingApi()

    with pytest.raises(CliInputError) as caught:
        spec.handler(
            _runtime(spec, api),
            {"novelId": novel_id, "expectedUpdatedAt": None, "content": "正文"},
        )

    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []


@pytest.mark.parametrize("expected_updated_at", ["", 7, False])
def test_expected_updated_at_rejects_non_string_non_null_values(
    expected_updated_at: object,
) -> None:
    module = _module()
    spec = _spec(module, "long.lore.story-progress.save")
    api = RecordingApi()

    with pytest.raises(CliInputError) as caught:
        spec.handler(
            _runtime(spec, api),
            {
                "novelId": "novel-1",
                "expectedUpdatedAt": expected_updated_at,
                "content": "正文",
            },
        )

    assert caught.value.code == "INVALID_EXPECTED_UPDATED_AT"
    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []


@pytest.mark.parametrize("data", [None, "not-object", []])
def test_structured_data_must_be_an_object(data: object) -> None:
    module = _module()
    spec = _spec(module, "long.lore.writing-bible.save")
    api = RecordingApi()

    with pytest.raises(CliInputError) as caught:
        spec.handler(
            _runtime(spec, api),
            {"novelId": "novel-1", "expectedUpdatedAt": None, "data": data},
        )

    assert caught.value.code == "OBJECT_REQUIRED"
    assert command_exit_code(spec, caught.value) == 2
    assert api.calls == []
