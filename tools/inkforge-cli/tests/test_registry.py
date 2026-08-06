from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from inkforge_cli.registry import (
    CommandSpec,
    FileOutputSpec,
    build_registry,
    get_command_registry,
)

README_PATH = Path(__file__).resolve().parents[1] / "README.md"
COMMAND_LIST_START = "<!-- command-list:start -->"
COMMAND_LIST_END = "<!-- command-list:end -->"

EXPECTED_COMMANDS = {
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
    "long.novel.list",
    "long.novel.get",
    "long.chapter.list",
    "long.chapter.get",
    "long.chapter.save",
    "long.chapter.status",
    "long.chapter.progress.save",
    "long.session.list",
    "long.session.get",
    "long.planning.get",
    "long.lore.get",
    "long.resources.get",
    "long.outline-node.list",
    "long.foreshadowing.list",
    "long.task.list",
    "long.task.get",
    "long.task.watch",
    "long.agent.start",
    "long.task.resume",
    "long.task.cancel",
    "long.artifact.list",
    "long.artifact.get",
    "long.artifact.approve",
    "long.artifact.revise",
    "long.artifact.discard",
    "long.quality.get",
    "long.quality.run",
    "long.quality.skip",
    "long.quality.reset",
}

EXPECTED_LONG_MUTATIONS = {
    "long.chapter.save",
    "long.chapter.status",
    "long.chapter.progress.save",
    "long.agent.start",
    "long.task.resume",
    "long.task.cancel",
    "long.artifact.approve",
    "long.artifact.revise",
    "long.artifact.discard",
    "long.quality.run",
    "long.quality.skip",
    "long.quality.reset",
}

STAGE_C_FAMILIES = {
    "outline",
    "outline-node",
    "foreshadowing",
    "lore",
    "reference",
    "style",
}
STAGE_C_ACTIONS = {
    "save",
    "create",
    "update",
    "delete",
    "reindex",
    "apply",
    "clear",
}


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
    assert EXPECTED_COMMANDS == set(registry)


def test_long_mutation_and_watcher_capabilities_are_exact() -> None:
    registry = get_command_registry()
    long_mutations = {
        name
        for name, spec in registry.items()
        if name.startswith("long.") and spec.mutation
    }

    assert long_mutations == EXPECTED_LONG_MUTATIONS
    assert registry["long.task.watch"].mutation is False
    assert registry["long.task.watch"].outputMode == "jsonl"
    assert registry["long.task.watch"].fileOutput.kind == "none"
    assert registry["long.task.watch"].requiresIdentity is True
    assert registry["long.task.watch"].requiresClientRequestId is False


def test_stage_c_structured_mutations_are_not_registered() -> None:
    command_names = get_command_registry()

    assert not {
        name
        for name in command_names
        if len(segments := name.split(".")) >= 3
        and segments[0] == "long"
        and segments[1] in STAGE_C_FAMILIES
        and segments[-1] in STAGE_C_ACTIONS
    }


def test_readme_command_list_matches_registry_without_wildcards() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    start = readme.index(COMMAND_LIST_START) + len(COMMAND_LIST_START)
    end = readme.index(COMMAND_LIST_END, start)
    documented = [
        line.strip()
        for line in readme[start:end].splitlines()
        if line.strip() and not line.strip().startswith("```")
    ]

    assert documented == list(get_command_registry())
    assert len(documented) == len(set(documented))
    assert all("*" not in name for name in documented)


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
