from __future__ import annotations

import importlib
from dataclasses import dataclass, field
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
        return {"styleId": kwargs["json"]["styleId"], "effective": True}


def _module():
    return importlib.import_module("inkforge_cli.commands.long.styles")


def _spec(name: str):
    return next(spec for spec in _module().STYLE_COMMAND_SPECS if spec.name == name)


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


def test_style_specs_expose_only_apply_and_clear() -> None:
    specs = _module().STYLE_COMMAND_SPECS

    assert {spec.name for spec in specs} == {"long.style.apply", "long.style.clear"}
    assert all(spec.mutation and spec.requiresIdentity for spec in specs)
    assert all(not spec.requiresClientRequestId for spec in specs)
    assert all(spec.inputMode == "json" and spec.outputMode == "json" for spec in specs)
    assert all(spec.fileOutput.kind == "none" for spec in specs)


@pytest.mark.parametrize(
    ("command", "payload", "body"),
    [
        (
            "long.style.apply",
            {
                "novelId": "novel/中文 ?",
                "styleId": "style-1",
                "expectedStyleId": None,
                "profile": "production",
            },
            {"styleId": "style-1", "expectedStyleId": None},
        ),
        (
            "long.style.clear",
            {
                "novelId": "novel/中文 ?",
                "expectedStyleId": "style-old",
                "profile": "production",
            },
            {"styleId": None, "expectedStyleId": "style-old"},
        ),
        (
            "long.style.clear",
            {
                "novelId": "novel/中文 ?",
                "expectedStyleId": "",
                "profile": "production",
            },
            {"styleId": None, "expectedStyleId": ""},
        ),
    ],
)
def test_style_commands_send_exact_cas_body(
    command: str,
    payload: dict[str, object],
    body: dict[str, object],
) -> None:
    spec = _spec(command)
    api = RecordingApi()

    result = spec.handler(_runtime(spec, api), payload)

    assert result == {"styleId": body["styleId"], "effective": True}
    assert api.calls == [(
        "PATCH",
        f"/api/v1/novels/{quote(str(payload['novelId']), safe='')}/applied-style",
        {"json": body},
    )]


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("long.style.apply", {"novelId": "novel-1", "expectedStyleId": None}),
        (
            "long.style.apply",
            {"novelId": "novel-1", "styleId": "", "expectedStyleId": None},
        ),
        ("long.style.clear", {"novelId": "novel-1"}),
        (
            "long.style.clear",
            {"novelId": "novel-1", "expectedStyleId": None, "styleId": "forbidden"},
        ),
        (
            "long.style.apply",
            {"novelId": "novel-1", "styleId": "style-1", "expectedStyleId": 7},
        ),
    ],
)
def test_invalid_style_payloads_do_not_send_requests(
    command: str,
    payload: dict[str, object],
) -> None:
    spec = _spec(command)
    api = RecordingApi()

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []


@pytest.mark.parametrize("command", ["long.style.apply", "long.style.clear"])
@pytest.mark.parametrize("field", ["outputFile", "unexpected", "clientRequestId"])
def test_style_commands_reject_unknown_fields_without_request(
    command: str,
    field: str,
) -> None:
    payload: dict[str, object] = {
        "novelId": "novel-1",
        "expectedStyleId": None,
    }
    if command.endswith("apply"):
        payload["styleId"] = "style-1"
    payload[field] = "forbidden"
    spec = _spec(command)
    api = RecordingApi()

    with pytest.raises(CliInputError):
        spec.handler(_runtime(spec, api), payload)

    assert api.calls == []
