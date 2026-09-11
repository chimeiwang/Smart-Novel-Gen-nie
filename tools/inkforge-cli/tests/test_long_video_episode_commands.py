from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from inkforge_cli.api import CoreTransportError
from inkforge_cli.commands.long.video import VIDEO_COMMAND_SPECS
from inkforge_cli.config import MemoryConfigStore
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import CliDependencies, CliInputError, CliRuntime

READ_COMMANDS = {
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

WRITE_COMMANDS = {
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


@dataclass
class RecordingApi:
    responses: list[object] = field(default_factory=lambda: [{}] * 40)
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> object:
        self.calls.append((method, path, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _spec(name: str) -> Any:
    return next(spec for spec in VIDEO_COMMAND_SPECS if spec.name == name)


def _runtime(name: str, api: RecordingApi) -> CliRuntime:
    return CliRuntime(
        spec=_spec(name),
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


def _run(name: str, api: RecordingApi, payload: dict[str, object]) -> object:
    return _spec(name).handler(_runtime(name, api), payload)


def _document() -> dict[str, object]:
    return {
        "schemaVersion": "video-episode-script/1.0",
        "overview": {
            "summary": "  完整摘要😀\r\n尾行  ",
            "creativeIntent": "保留人物沉默",
            "targetDurationSeconds": 90,
        },
        "scenes": [],
        "endingStates": [],
        "dependencies": [],
    }


def test_episode_command_specs_are_exact_and_old_starters_are_closed() -> None:
    specs = {spec.name: spec for spec in VIDEO_COMMAND_SPECS}

    assert READ_COMMANDS | WRITE_COMMANDS <= set(specs)
    assert all(not specs[name].mutation for name in READ_COMMANDS)
    assert all(specs[name].fileOutput.kind == "data_json" for name in READ_COMMANDS)
    assert all(specs[name].mutation for name in WRITE_COMMANDS)
    assert all(specs[name].requiresClientRequestId for name in WRITE_COMMANDS)
    assert not {
        "long.video.adaptation.create",
        "long.video.plan.start",
        "long.video.prompt.start",
    } & set(specs)


@pytest.mark.parametrize(
    ("name", "payload", "path"),
    [
        (
            "long.video.episode.list",
            {"projectId": "project /😀"},
            "/api/v1/video/projects/project%20%2F%F0%9F%98%80/episodes",
        ),
        (
            "long.video.episode.get",
            {"episodeId": "episode /😀"},
            "/api/v1/video/episodes/episode%20%2F%F0%9F%98%80",
        ),
        (
            "long.video.episode.source.list",
            {"episodeId": "ep/1"},
            "/api/v1/video/episodes/ep%2F1/source-sets",
        ),
        (
            "long.video.episode.source.get",
            {"episodeId": "ep/1", "versionId": "source/1"},
            "/api/v1/video/episodes/ep%2F1/source-sets/source%2F1",
        ),
        (
            "long.video.episode.script.draft.get",
            {"episodeId": "ep/1"},
            "/api/v1/video/episodes/ep%2F1/script/draft",
        ),
        (
            "long.video.episode.script.run.get",
            {"episodeId": "ep/1", "runId": "run/1"},
            "/api/v1/video/episodes/ep%2F1/script/runs/run%2F1",
        ),
        (
            "long.video.episode.script.confirmation.get",
            {"episodeId": "ep/1", "artifactId": "artifact/1"},
            "/api/v1/video/episodes/ep%2F1/script/confirmations/artifact%2F1",
        ),
        (
            "long.video.episode.script.version.list",
            {"episodeId": "ep/1"},
            "/api/v1/video/episodes/ep%2F1/script/versions",
        ),
        (
            "long.video.episode.script.version.get",
            {"episodeId": "ep/1", "versionId": "script/1"},
            "/api/v1/video/episodes/ep%2F1/script/versions/script%2F1",
        ),
        (
            "long.video.episode.command.get",
            {"episodeId": "ep/1", "clientRequestId": "episode-command-0001"},
            "/api/v1/video/episodes/ep%2F1/commands/episode-command-0001",
        ),
        (
            "long.video.episode.project-command.get",
            {"projectId": "project/1", "clientRequestId": "episode-create-0001"},
            "/api/v1/video/projects/project%2F1/episode-commands/episode-create-0001",
        ),
    ],
)
def test_episode_read_commands_use_exact_public_paths(
    name: str, payload: dict[str, object], path: str
) -> None:
    api = RecordingApi()

    _run(name, api, payload)

    assert api.calls == [("GET", path, {})]


def test_episode_writes_preserve_cas_ids_and_complete_bodies() -> None:
    api = RecordingApi()
    source_hash = "a" * 64
    confirmation_hash = "b" * 64

    _run(
        "long.video.episode.create",
        api,
        {
            "projectId": "project/1",
            "clientRequestId": "episode-create-0001",
            "title": "  第一集😀  ",
            "creativeIntent": "保留换行\r\n与空白  ",
            "targetDurationSeconds": 90,
        },
    )
    _run(
        "long.video.episode.update",
        api,
        {
            "episodeId": "episode/1",
            "clientRequestId": "episode-update-0001",
            "expectedRevision": 2,
            "title": "第二版",
            "creativeIntent": None,
            "targetDurationSeconds": None,
        },
    )
    _run(
        "long.video.episode.reorder",
        api,
        {
            "projectId": "project/1",
            "clientRequestId": "episode-reorder-001",
            "expectedProjectRevision": 3,
            "episodeIds": ["episode/2", "episode/1"],
        },
    )
    _run(
        "long.video.episode.source.create",
        api,
        {
            "episodeId": "episode/1",
            "clientRequestId": "source-create-00001",
            "expectedRevision": 3,
            "basedOnVersionId": None,
            "sources": [
                {
                    "chapterId": "chapter/1",
                    "expectedUpdatedAt": "2026-09-10T00:00:00Z",
                    "sourceHash": source_hash,
                    "ranges": [{"start": 0, "end": 12}],
                }
            ],
        },
    )
    _run(
        "long.video.episode.script.draft.save",
        api,
        {
            "episodeId": "episode/1",
            "clientRequestId": "script-draft-save1",
            "expectedRevision": 4,
            "sourceSetVersionId": "source/1",
            "baseScriptVersionId": None,
            "document": _document(),
        },
    )
    _run(
        "long.video.episode.script.run.start",
        api,
        {
            "episodeId": "episode/1",
            "clientRequestId": "script-run-start-01",
            "expectedDraftRevision": 5,
            "operation": "episode_script_revise",
            "selectedSceneIds": ["scene/1"],
            "instruction": "  减少对白😀  ",
        },
    )
    _run(
        "long.video.episode.script.candidate.adopt",
        api,
        {
            "episodeId": "episode/1",
            "artifactId": "artifact/1",
            "clientRequestId": "candidate-adopt-001",
            "expectedArtifactRevision": 2,
            "expectedDraftRevision": 5,
        },
    )
    _run(
        "long.video.episode.script.confirmation.prepare",
        api,
        {
            "episodeId": "episode/1",
            "clientRequestId": "confirm-prepare-001",
            "expectedDraftRevision": 6,
            "expectedEpisodeRevision": 4,
        },
    )
    _run(
        "long.video.episode.script.confirmation.approve",
        api,
        {
            "episodeId": "episode/1",
            "artifactId": "artifact/2",
            "clientRequestId": "confirm-approve-001",
            "expectedArtifactRevision": 1,
            "expectedDraftRevision": 6,
            "expectedEpisodeRevision": 4,
            "confirmationHash": confirmation_hash,
        },
    )

    assert api.calls[0] == (
        "POST",
        "/api/v1/video/projects/project%2F1/episodes",
        {
            "json": {
                "clientRequestId": "episode-create-0001",
                "title": "  第一集😀  ",
                "creativeIntent": "保留换行\r\n与空白  ",
                "targetDurationSeconds": 90,
            }
        },
    )
    assert api.calls[1][0:2] == ("PATCH", "/api/v1/video/episodes/episode%2F1")
    assert api.calls[1][2]["json"]["creativeIntent"] is None
    assert api.calls[1][2]["json"]["targetDurationSeconds"] is None
    assert api.calls[2][1] == "/api/v1/video/projects/project%2F1/episodes/reorder"
    assert api.calls[3][2]["json"]["sources"][0]["ranges"] == [
        {"start": 0, "end": 12}
    ]
    assert api.calls[4][2]["json"]["document"] == _document()
    assert api.calls[5][2]["json"]["selectedSceneIds"] == ["scene/1"]
    assert api.calls[6][1].endswith("/script/candidates/artifact%2F1/adopt")
    assert api.calls[7][1].endswith("/script/confirmations")
    assert api.calls[8][2]["json"]["confirmationHash"] == confirmation_hash


def test_episode_source_and_script_accept_complete_utf8_json_files(tmp_path: Path) -> None:
    api = RecordingApi()
    sources = [
        {
            "chapterId": "章节😀",
            "expectedUpdatedAt": "2026-09-10T00:00:00Z",
            "sourceHash": "c" * 64,
            "ranges": [{"start": 1, "end": 9}],
        }
    ]
    sources_file = tmp_path / "sources.json"
    sources_file.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    document_file = tmp_path / "script.json"
    document_file.write_text(
        json.dumps(_document(), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    _run(
        "long.video.episode.source.create",
        api,
        {
            "episodeId": "episode-1",
            "clientRequestId": "source-file-save-01",
            "expectedRevision": 1,
            "sourcesFile": str(sources_file),
        },
    )
    _run(
        "long.video.episode.script.draft.save",
        api,
        {
            "episodeId": "episode-1",
            "clientRequestId": "script-file-save-01",
            "expectedRevision": 1,
            "sourceSetVersionId": "source-1",
            "baseScriptVersionId": None,
            "documentFile": str(document_file),
        },
    )

    assert api.calls[0][2]["json"]["sources"] == sources
    assert api.calls[1][2]["json"]["document"] == _document()


def test_unknown_fields_and_invalid_revision_scope_are_rejected_before_request() -> None:
    api = RecordingApi()

    with pytest.raises(CliInputError, match="unknown"):
        _run(
            "long.video.episode.get",
            api,
            {"episodeId": "episode-1", "unknown": True},
        )
    with pytest.raises(CliInputError, match="修订必须选择"):
        _run(
            "long.video.episode.script.run.start",
            api,
            {
                "episodeId": "episode-1",
                "clientRequestId": "script-run-start-01",
                "expectedDraftRevision": 1,
                "operation": "episode_script_revise",
                "instruction": "修订",
            },
        )
    with pytest.raises(CliInputError, match="字段必须精确匹配"):
        _run(
            "long.video.episode.source.create",
            api,
            {
                "episodeId": "episode-1",
                "clientRequestId": "source-invalid-0001",
                "expectedRevision": 1,
                "sources": [
                    {
                        "chapterId": "chapter-1",
                        "expectedUpdatedAt": "v1",
                        "sourceHash": "a" * 64,
                        "ranges": [{"start": 0, "end": 1}],
                        "unknown": True,
                    }
                ],
            },
        )

    assert api.calls == []


def test_unknown_create_response_is_recovered_only_through_same_request_receipt() -> None:
    api = RecordingApi(
        responses=[
            CoreTransportError(),
            {
                "clientRequestId": "episode-create-0001",
                "operation": "episode_create",
                "resultType": "episode",
                "resultId": "episode-1",
            },
        ]
    )

    with pytest.raises(CoreTransportError):
        _run(
            "long.video.episode.create",
            api,
            {
                "projectId": "project-1",
                "clientRequestId": "episode-create-0001",
                "title": "第一集",
            },
        )
    _run(
        "long.video.episode.project-command.get",
        api,
        {"projectId": "project-1", "clientRequestId": "episode-create-0001"},
    )

    assert [call[0] for call in api.calls] == ["POST", "GET"]
    assert api.calls[1][1] == (
        "/api/v1/video/projects/project-1/episode-commands/episode-create-0001"
    )
