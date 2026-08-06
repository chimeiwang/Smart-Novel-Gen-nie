from __future__ import annotations

from collections.abc import Generator

import pytest
from inkforge_cli.registry import (
    CommandSpec,
    FileOutputSpec,
    build_registry,
    get_command_registry,
)


def _json_handler(runtime: object, payload: dict[str, object]) -> dict[str, object]:
    return {"payload": payload}


def _jsonl_handler(
    runtime: object,
    payload: dict[str, object],
) -> Generator[dict[str, object], None, int]:
    yield {"type": "event", "data": payload}
    return 0


def _spec(name: str = "test.command", **overrides: object) -> CommandSpec:
    values = {
        "name": name,
        "handler": _json_handler,
        "inputMode": "json",
        "outputMode": "json",
        "fileOutput": FileOutputSpec(kind="none"),
        "mutation": False,
        "requiresIdentity": False,
        "requiresClientRequestId": False,
        **overrides,
    }
    return CommandSpec(**values)  # type: ignore[arg-type]


def test_registry_has_unique_existing_command_names_and_declares_special_modes() -> None:
    registry = get_command_registry()

    assert len(registry) == len(set(registry))
    assert registry["auth.login"].inputMode == "argv_tty"
    assert registry["short.agent.watch"].outputMode == "jsonl"
    assert {
        "auth.login",
        "auth.logout",
        "auth.whoami",
        "short.list",
        "short.create",
        "short.pull",
        "short.draft.save",
        "short.version.preview",
        "short.version.submit",
        "short.version.list",
        "short.version.diff",
        "short.version.get",
        "short.version.adopt",
        "short.version.restore",
        "short.agent.start",
        "short.agent.watch",
    } == set(registry)


@pytest.mark.parametrize(
    "specs",
    [
        [_spec("")],
        [_spec("same"), _spec("same")],
        [
            _spec(
                outputMode="jsonl",
                handler=_jsonl_handler,
                fileOutput=FileOutputSpec(kind="data_json"),
            )
        ],
        [_spec(fileOutput=FileOutputSpec(kind="primary_text"))],
        [
            _spec(
                fileOutput=FileOutputSpec(
                    kind="primary_text",
                    field="content",
                )
            )
        ],
        [_spec(mutation=True, requiresIdentity=False)],
    ],
)
def test_registry_rejects_invalid_capability_metadata(
    specs: list[CommandSpec],
) -> None:
    with pytest.raises(ValueError):
        build_registry(specs)
