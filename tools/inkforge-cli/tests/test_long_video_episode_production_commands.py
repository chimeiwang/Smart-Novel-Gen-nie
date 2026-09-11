from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from inkforge_cli.api import BinaryResponse, CoreTransportError
from inkforge_cli.commands.long.video import VIDEO_COMMAND_SPECS
from inkforge_cli.config import MemoryConfigStore
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import CliDependencies, CliInputError, CliRuntime


@dataclass
class RecordingApi:
    responses: list[object] = field(default_factory=lambda: [{}] * 100)
    binary: BinaryResponse = field(
        default_factory=lambda: BinaryResponse(b"video-bytes", "video/mp4")
    )
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> object:
        self.calls.append((method, path, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def request_bytes(self, method: str, path: str, **kwargs: Any) -> BinaryResponse:
        self.calls.append((method, path, kwargs))
        return self.binary


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


def test_native_episode_video_commands_replace_every_legacy_write_surface() -> None:
    specs = {spec.name: spec for spec in VIDEO_COMMAND_SPECS}
    expected = {
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
    retired = {
        "long.video.adaptation.list",
        "long.video.adaptation.get",
        "long.video.adaptation.watch",
        "long.video.plan.confirm",
        "long.video.plan.discard",
        "long.video.episode.save",
        "long.video.prompt.save",
        "long.video.reference.save",
        "long.video.render.list",
        "long.video.render.start",
        "long.video.render.get",
        "long.video.render.retry",
        "long.video.render.watch",
        "long.video.take.confirm",
        "long.video.take.download",
        "long.video.post.show",
        "long.video.keyframe.set",
        "long.video.keyframe.clear",
        "long.video.keyframe.extract",
        "long.video.edit.save",
        "long.video.edit.get",
        "long.video.mix.save",
        "long.video.mix.get",
        "long.video.export.start",
        "long.video.export.get",
        "long.video.export.retry",
        "long.video.export.watch",
        "long.video.export.download",
    }

    assert expected <= set(specs)
    assert retired.isdisjoint(specs)
    assert all(specs[name].requiresClientRequestId for name in expected if specs[name].mutation)
    assert specs["long.video.episode.take.download"].fileOutput.kind == "none"
    assert specs["long.video.episode.delivery.download"].fileOutput.kind == "none"


def test_native_reads_encode_path_and_bounded_cursor_query() -> None:
    api = RecordingApi()

    _run(
        "long.video.episode.storyboard.run.list",
        api,
        {"episodeId": "ep /😀", "limit": 50, "beforeRunId": "run /😀"},
    )
    _run(
        "long.video.episode.take.list",
        api,
        {
            "episodeId": "ep/1",
            "targetShotVersionId": "shot /😀",
            "limit": 7,
            "beforeTakeId": "take /😀",
        },
    )
    _run(
        "long.video.episode.impact.list",
        api,
        {
            "episodeId": "ep/1",
            "status": "pending",
            "limit": 8,
            "beforeReviewId": "review /😀",
        },
    )
    _run(
        "long.video.episode.edit.get",
        api,
        {"episodeId": "ep/1", "baselineId": "base/1", "versionId": "edit/1"},
    )

    assert api.calls[0][1] == (
        "/api/v1/video/episodes/ep%20%2F%F0%9F%98%80/storyboard/runs"
        "?limit=50&beforeRunId=run%20%2F%F0%9F%98%80"
    )
    assert api.calls[1][1] == (
        "/api/v1/video/episodes/ep%2F1/takes"
        "?targetShotVersionId=shot%20%2F%F0%9F%98%80&limit=7"
        "&beforeTakeId=take%20%2F%F0%9F%98%80"
    )
    assert api.calls[2][1].endswith(
        "/impact-reviews?status=pending&limit=8&beforeReviewId=review%20%2F%F0%9F%98%80"
    )
    assert api.calls[3][1].endswith("/production-baselines/base%2F1/edit-versions/edit%2F1")


def test_storyboard_adoption_baseline_and_impact_writes_preserve_exact_bodies(
    tmp_path: Path,
) -> None:
    api = RecordingApi()
    document = {"schemaVersion": "video-episode-storyboard/1.0", "shots": []}
    document_file = tmp_path / "storyboard.json"
    document_file.write_text(json.dumps(document), encoding="utf-8")
    comparison = {
        "sourceBaselineId": "base/0",
        "targetShotVersionId": "shotv/1",
        "directInputsUnchanged": False,
        "referenceHashesChecked": ["a" * 64],
        "summary": "人工核对通过",
    }
    decisions_file = tmp_path / "decisions.json"
    decisions_file.write_text(
        json.dumps(
            [{"itemId": "item/1", "action": "revise_target", "note": "下一版修订"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _run(
        "long.video.episode.storyboard.draft.save",
        api,
        {
            "episodeId": "ep/1",
            "clientRequestId": "storyboard-save-0001",
            "expectedRevision": 2,
            "scriptVersionId": "script/1",
            "baseStoryboardVersionId": None,
            "documentFile": str(document_file),
        },
    )
    _run(
        "long.video.episode.adoption.create",
        api,
        {
            "episodeId": "ep/1",
            "clientRequestId": "adoption-create-001",
            "expectedProductionRevision": 3,
            "targetShotVersionId": "shotv/1",
            "sourceTakeId": "take/1",
            "sourceBaselineId": "base/0",
            "comparison": comparison,
        },
    )
    _run(
        "long.video.episode.baseline.create",
        api,
        {
            "episodeId": "ep/1",
            "clientRequestId": "baseline-create-001",
            "expectedEpisodeRevision": 5,
            "expectedProductionRevision": 3,
            "basedOnBaselineId": "base/0",
            "scriptVersionId": "script/1",
            "storyboardVersionId": "board/1",
            "shotAdoptions": [{"shotVersionId": "shotv/1", "adoptionId": "adopt/1"}],
            "keyframes": [
                {
                    "shotVersionId": "shotv/1",
                    "role": "initial_state",
                    "assetId": "keyframe/1",
                }
            ],
        },
    )
    _run(
        "long.video.episode.impact.decide",
        api,
        {
            "episodeId": "ep/1",
            "reviewId": "review/1",
            "clientRequestId": "impact-decide-0001",
            "expectedRevision": 1,
            "decisionsFile": str(decisions_file),
        },
    )

    assert api.calls[0][0:2] == (
        "PUT",
        "/api/v1/video/episodes/ep%2F1/storyboard/draft",
    )
    assert api.calls[0][2]["json"]["document"] == document
    assert api.calls[1][2]["json"]["comparison"] == comparison
    assert api.calls[2][2]["json"]["shotAdoptions"][0]["adoptionId"] == "adopt/1"
    assert api.calls[2][2]["json"]["keyframes"][0]["role"] == "initial_state"
    assert api.calls[3][1].endswith("/impact-reviews/review%2F1/decisions")
    assert api.calls[3][2]["json"]["decisions"][0]["note"] == "下一版修订"


def test_render_edit_mix_export_and_delivery_use_episode_baseline_scope(
    tmp_path: Path,
) -> None:
    api = RecordingApi()
    edit_file = tmp_path / "edit.json"
    edit_file.write_text(
        json.dumps(
            {
                "clips": [
                    {
                        "tempKey": "clip-1",
                        "adoptionId": "adopt/1",
                        "takeId": "take/1",
                        "sourceInMs": 0,
                        "sourceOutMs": 1000,
                        "sourceAudioMode": "keep",
                    }
                ],
                "omissions": [],
            }
        ),
        encoding="utf-8",
    )
    mix_file = tmp_path / "mix.json"
    mix_file.write_text(json.dumps({"audioClips": [], "subtitleCues": []}), encoding="utf-8")

    _run(
        "long.video.episode.render.start",
        api,
        {
            "episodeId": "ep/1",
            "baselineId": "base/1",
            "shotId": "shot/1",
            "clientRequestId": "render-start-0001",
            "feeConfirmed": False,
        },
    )
    _run(
        "long.video.episode.edit.create",
        api,
        {
            "episodeId": "ep/1",
            "baselineId": "base/1",
            "clientRequestId": "edit-create-00001",
            "expectedHeadRevision": 1,
            "basedOnVersionId": None,
            "editFile": str(edit_file),
        },
    )
    _run(
        "long.video.episode.mix.create",
        api,
        {
            "episodeId": "ep/1",
            "baselineId": "base/1",
            "clientRequestId": "mix-create-000001",
            "expectedHeadRevision": 1,
            "basedOnVersionId": None,
            "editVersionId": "edit/1",
            "mixFile": str(mix_file),
        },
    )
    _run(
        "long.video.episode.export.start",
        api,
        {
            "episodeId": "ep/1",
            "baselineId": "base/1",
            "clientRequestId": "export-start-0001",
            "editVersionId": "edit/1",
            "mixVersionId": "mix/1",
            "resolution": "1080p",
            "framesPerSecond": 25,
            "burnSubtitles": False,
        },
    )
    _run(
        "long.video.episode.export.retry",
        api,
        {
            "episodeId": "ep/1",
            "baselineId": "base/1",
            "taskId": "task/1",
            "clientRequestId": "export-retry-0001",
        },
    )

    root = "/api/v1/video/episodes/ep%2F1/production-baselines/base%2F1"
    assert api.calls[0][1] == root + "/shots/shot%2F1/render-tasks"
    assert api.calls[1][1] == root + "/edit-versions"
    assert api.calls[1][2]["json"]["clips"][0]["adoptionId"] == "adopt/1"
    assert api.calls[2][1] == root + "/mix-versions"
    assert api.calls[3][1] == root + "/export-tasks"
    assert api.calls[3][2]["json"]["resolution"] == "1080p"
    assert api.calls[4][1] == root + "/export-tasks/task%2F1/retry"


def test_take_and_delivery_download_write_exact_bytes(tmp_path: Path) -> None:
    api = RecordingApi()
    take = tmp_path / "take.mp4"
    delivery = tmp_path / "delivery.mp4"

    take_result = _run(
        "long.video.episode.take.download",
        api,
        {"episodeId": "ep/1", "takeId": "take/1", "outputFile": str(take)},
    )
    delivery_result = _run(
        "long.video.episode.delivery.download",
        api,
        {
            "episodeId": "ep/1",
            "baselineId": "base/1",
            "exportId": "export/1",
            "outputFile": str(delivery),
        },
    )

    assert take.read_bytes() == delivery.read_bytes() == b"video-bytes"
    assert take_result["resultFile"]["sha256"] == delivery_result["resultFile"]["sha256"]
    assert api.calls[0][1].endswith("/episodes/ep%2F1/takes/take%2F1/content")
    assert api.calls[1][1].endswith("/production-baselines/base%2F1/exports/export%2F1/content")


def test_response_unknown_is_recovered_only_by_episode_command_receipt() -> None:
    api = RecordingApi(responses=[CoreTransportError(), {"operation": "episode.export-task.start"}])

    with pytest.raises(CoreTransportError):
        _run(
            "long.video.episode.export.start",
            api,
            {
                "episodeId": "ep-1",
                "baselineId": "base-1",
                "clientRequestId": "export-unknown-001",
                "editVersionId": "edit-1",
                "mixVersionId": "mix-1",
            },
        )
    _run(
        "long.video.episode.command.get",
        api,
        {"episodeId": "ep-1", "clientRequestId": "export-unknown-001"},
    )

    assert [call[0] for call in api.calls] == ["POST", "GET"]
    assert api.calls[1][1] == "/api/v1/video/episodes/ep-1/commands/export-unknown-001"


def test_native_cli_rejects_invalid_scope_before_network() -> None:
    api = RecordingApi()

    with pytest.raises(CliInputError, match="分镜修订必须选择"):
        _run(
            "long.video.episode.storyboard.run.start",
            api,
            {
                "episodeId": "ep-1",
                "clientRequestId": "storyboard-run-0001",
                "expectedDraftRevision": 1,
                "scriptVersionId": "script-1",
                "operation": "episode_storyboard_revise",
                "instruction": "修订",
            },
        )
    with pytest.raises(CliInputError, match="comparison"):
        _run(
            "long.video.episode.adoption.create",
            api,
            {
                "episodeId": "ep-1",
                "clientRequestId": "adoption-invalid-01",
                "expectedProductionRevision": 1,
                "targetShotVersionId": "shot-1",
                "sourceTakeId": "take-1",
                "sourceBaselineId": "base-1",
                "comparison": {"sourceBaselineId": "base-2"},
            },
        )
    with pytest.raises(CliInputError, match="keyframes 不能重复"):
        _run(
            "long.video.episode.baseline.create",
            api,
            {
                "episodeId": "ep-1",
                "clientRequestId": "baseline-invalid-01",
                "expectedEpisodeRevision": 1,
                "expectedProductionRevision": 1,
                "basedOnBaselineId": None,
                "scriptVersionId": "script-1",
                "storyboardVersionId": "board-1",
                "keyframes": [
                    {"shotVersionId": "shot-1", "role": "initial_state", "assetId": "asset-1"},
                    {"shotVersionId": "shot-1", "role": "initial_state", "assetId": "asset-2"},
                ],
            },
        )
    assert api.calls == []
