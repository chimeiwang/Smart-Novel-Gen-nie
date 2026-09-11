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

VIDEO_EPISODE_READS = {
    "long.video.episode.list",
    "long.video.episode.get",
    "long.video.episode.source.list",
    "long.video.episode.source.get",
    "long.video.episode.script.draft.get",
    "long.video.episode.script.run.get",
    "long.video.episode.script.confirmation.get",
    "long.video.episode.script.version.list",
    "long.video.episode.script.version.get",
    "long.video.episode.command.get",
    "long.video.episode.project-command.get",
}

VIDEO_EPISODE_MUTATIONS = {
    "long.video.episode.create",
    "long.video.episode.update",
    "long.video.episode.reorder",
    "long.video.episode.source.create",
    "long.video.episode.script.draft.save",
    "long.video.episode.script.run.start",
    "long.video.episode.script.candidate.adopt",
    "long.video.episode.script.confirmation.prepare",
    "long.video.episode.script.confirmation.approve",
}

VIDEO_COMMANDS = {
    "long.video.project.list",
    "long.video.project.get",
    "long.video.project.create",
    "long.video.asset.upload",
    "long.video.asset.rights",
    "long.video.asset.download",
    "long.video.asset.preview",
    "long.video.episode.list",
    "long.video.episode.get",
    "long.video.episode.create",
    "long.video.episode.update",
    "long.video.episode.reorder",
    "long.video.episode.source.create",
    "long.video.episode.source.list",
    "long.video.episode.source.get",
    "long.video.episode.script.draft.get",
    "long.video.episode.script.draft.save",
    "long.video.episode.script.run.start",
    "long.video.episode.script.run.get",
    "long.video.episode.script.candidate.adopt",
    "long.video.episode.script.confirmation.prepare",
    "long.video.episode.script.confirmation.get",
    "long.video.episode.script.confirmation.approve",
    "long.video.episode.script.version.list",
    "long.video.episode.script.version.get",
    "long.video.episode.command.get",
    "long.video.episode.project-command.get",
    "long.video.canon.list",
    "long.video.canon.candidate.set",
    "long.video.canon.approve",
    "long.video.production.capabilities.get",
    "long.video.episode.storyboard.draft.get",
    "long.video.episode.storyboard.draft.save",
    "long.video.episode.storyboard.run.start",
    "long.video.episode.storyboard.run.list",
    "long.video.episode.storyboard.run.get",
    "long.video.episode.storyboard.candidate.get",
    "long.video.episode.storyboard.candidate.adopt",
    "long.video.episode.storyboard.confirmation.prepare",
    "long.video.episode.storyboard.confirmation.get",
    "long.video.episode.storyboard.confirmation.approve",
    "long.video.episode.storyboard.version.list",
    "long.video.episode.storyboard.version.get",
    "long.video.episode.take.list",
    "long.video.episode.take.download",
    "long.video.episode.adoption.create",
    "long.video.episode.adoption.get",
    "long.video.episode.baseline.create",
    "long.video.episode.baseline.list",
    "long.video.episode.baseline.get",
    "long.video.episode.impact.list",
    "long.video.episode.impact.get",
    "long.video.episode.impact.decide",
    "long.video.episode.render.start",
    "long.video.episode.render.get",
    "long.video.episode.render.retry",
    "long.video.episode.edit.create",
    "long.video.episode.edit.list",
    "long.video.episode.edit.get",
    "long.video.episode.mix.create",
    "long.video.episode.mix.list",
    "long.video.episode.mix.get",
    "long.video.episode.export.start",
    "long.video.episode.export.get",
    "long.video.episode.export.retry",
    "long.video.episode.delivery.get",
    "long.video.episode.delivery.download",
}

VIDEO_MUTATIONS = {
    "long.video.project.create",
    "long.video.asset.upload",
    "long.video.asset.rights",
    "long.video.episode.create",
    "long.video.episode.update",
    "long.video.episode.reorder",
    "long.video.episode.source.create",
    "long.video.episode.script.draft.save",
    "long.video.episode.script.run.start",
    "long.video.episode.script.candidate.adopt",
    "long.video.episode.script.confirmation.prepare",
    "long.video.episode.script.confirmation.approve",
    "long.video.canon.candidate.set",
    "long.video.canon.approve",
    "long.video.episode.storyboard.draft.save",
    "long.video.episode.storyboard.run.start",
    "long.video.episode.storyboard.candidate.adopt",
    "long.video.episode.storyboard.confirmation.prepare",
    "long.video.episode.storyboard.confirmation.approve",
    "long.video.episode.adoption.create",
    "long.video.episode.baseline.create",
    "long.video.episode.impact.decide",
    "long.video.episode.render.start",
    "long.video.episode.render.retry",
    "long.video.episode.edit.create",
    "long.video.episode.mix.create",
    "long.video.episode.export.start",
    "long.video.episode.export.retry",
}

VIDEO_REQUEST_ID_MUTATIONS = VIDEO_MUTATIONS - {
    "long.video.project.create",
    "long.video.asset.upload",
    "long.video.asset.rights",
}

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
    "long.novel.create",
    "long.novel.summary.save",
    "long.chapter.list",
    "long.chapter.get",
    "long.chapter.create",
    "long.chapter.save",
    "long.chapter.status",
    "long.chapter.progress.save",
    "long.session.list",
    "long.session.get",
    "long.session.create",
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
    "long.lore.story-background.save",
    "long.lore.world-setting.save",
    "long.lore.writing-bible.save",
    "long.lore.story-progress.save",
    "long.plot-progress.save",
    "long.outline.save",
    "long.outline-node.create",
    "long.outline-node.update",
    "long.outline-node.delete",
    "long.lore.character.create",
    "long.lore.character.update",
    "long.lore.character.delete",
    "long.lore.location.create",
    "long.lore.location.update",
    "long.lore.location.delete",
    "long.lore.faction.create",
    "long.lore.faction.update",
    "long.lore.faction.delete",
    "long.lore.item.create",
    "long.lore.item.update",
    "long.lore.item.delete",
    "long.lore.glossary.create",
    "long.lore.glossary.update",
    "long.lore.glossary.delete",
    "long.lore.relation.create",
    "long.lore.relation.update",
    "long.lore.relation.delete",
    "long.lore.experience.create",
    "long.lore.experience.update",
    "long.lore.experience.delete",
    "long.reference.create",
    "long.reference.update",
    "long.reference.delete",
    "long.reference.reindex",
    "long.style.apply",
    "long.style.clear",
} | VIDEO_COMMANDS

EXPECTED_LONG_MUTATIONS = {
    "long.session.create",
    "long.novel.create",
    "long.novel.summary.save",
    "long.chapter.create",
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
    "long.lore.story-background.save",
    "long.lore.world-setting.save",
    "long.lore.writing-bible.save",
    "long.lore.story-progress.save",
    "long.plot-progress.save",
    "long.outline.save",
    "long.outline-node.create",
    "long.outline-node.update",
    "long.outline-node.delete",
    "long.lore.character.create",
    "long.lore.character.update",
    "long.lore.character.delete",
    "long.lore.location.create",
    "long.lore.location.update",
    "long.lore.location.delete",
    "long.lore.faction.create",
    "long.lore.faction.update",
    "long.lore.faction.delete",
    "long.lore.item.create",
    "long.lore.item.update",
    "long.lore.item.delete",
    "long.lore.glossary.create",
    "long.lore.glossary.update",
    "long.lore.glossary.delete",
    "long.lore.relation.create",
    "long.lore.relation.update",
    "long.lore.relation.delete",
    "long.lore.experience.create",
    "long.lore.experience.update",
    "long.lore.experience.delete",
    "long.reference.create",
    "long.reference.update",
    "long.reference.delete",
    "long.reference.reindex",
    "long.style.apply",
    "long.style.clear",
} | VIDEO_MUTATIONS

EXPECTED_STRUCTURED_WRITES = EXPECTED_LONG_MUTATIONS - {
    "long.session.create",
    "long.novel.create",
    "long.novel.summary.save",
    "long.chapter.create",
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
} - VIDEO_MUTATIONS

EXPECTED_STRUCTURED_CREATES = {
    "long.outline-node.create",
    "long.lore.character.create",
    "long.lore.location.create",
    "long.lore.faction.create",
    "long.lore.item.create",
    "long.lore.glossary.create",
    "long.lore.relation.create",
    "long.lore.experience.create",
    "long.reference.create",
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
    assert registry["long.video.episode.take.download"].mutation is False
    assert registry["long.video.episode.take.download"].outputMode == "json"
    assert registry["long.video.episode.take.download"].fileOutput.kind == "none"
    assert registry["long.video.episode.take.download"].requiresIdentity is True


def test_structured_mutation_capabilities_are_exact() -> None:
    registry = get_command_registry()

    assert len(registry) == 152
    assert sum(
        name.startswith("long.") and spec.mutation
        for name, spec in registry.items()
    ) == 80
    assert len(EXPECTED_STRUCTURED_WRITES) == 36
    assert "long.novel.create" not in EXPECTED_STRUCTURED_WRITES
    assert "long.novel.summary.save" not in EXPECTED_STRUCTURED_WRITES
    assert {
        name for name in EXPECTED_STRUCTURED_WRITES if name in registry
    } == EXPECTED_STRUCTURED_WRITES
    assert {
        name
        for name, spec in registry.items()
        if name in EXPECTED_STRUCTURED_WRITES and spec.requiresClientRequestId
    } == EXPECTED_STRUCTURED_CREATES
    assert registry["long.reference.reindex"].requiresClientRequestId is False
    assert {
        name
        for name in VIDEO_MUTATIONS
        if registry[name].requiresClientRequestId
    } == VIDEO_REQUEST_ID_MUTATIONS


def test_excluded_stage_c_families_remain_unregistered() -> None:
    command_names = set(get_command_registry())

    assert not {
        "long.foreshadowing.create",
        "long.foreshadowing.update",
        "long.foreshadowing.delete",
        "long.style.create",
        "long.style.update",
        "long.style.delete",
    } & command_names


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
