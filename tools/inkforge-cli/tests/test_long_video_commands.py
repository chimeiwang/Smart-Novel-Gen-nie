from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from inkforge_cli.api import BinaryResponse, CoreApiError
from inkforge_cli.commands.long.video import VIDEO_COMMAND_SPECS
from inkforge_cli.config import MemoryConfigStore
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import CliDependencies, CliInputError, CliRuntime

COMMAND_NAMES = {
    "long.video.project.list",
    "long.video.project.get",
    "long.video.project.create",
    "long.video.asset.upload",
    "long.video.asset.rights",
    "long.video.asset.download",
    "long.video.asset.preview",
    "long.video.adaptation.list",
    "long.video.adaptation.get",
    "long.video.adaptation.create",
    "long.video.adaptation.watch",
    "long.video.plan.start",
    "long.video.plan.confirm",
    "long.video.plan.discard",
    "long.video.episode.save",
    "long.video.prompt.start",
    "long.video.prompt.save",
    "long.video.canon.list",
    "long.video.canon.candidate.set",
    "long.video.canon.approve",
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

MUTATION_NAMES = {
    "long.video.project.create",
    "long.video.asset.upload",
    "long.video.asset.rights",
    "long.video.adaptation.create",
    "long.video.plan.start",
    "long.video.plan.confirm",
    "long.video.plan.discard",
    "long.video.episode.save",
    "long.video.prompt.start",
    "long.video.prompt.save",
    "long.video.canon.candidate.set",
    "long.video.canon.approve",
    "long.video.reference.save",
    "long.video.render.start",
    "long.video.render.retry",
    "long.video.take.confirm",
    "long.video.keyframe.set",
    "long.video.keyframe.clear",
    "long.video.keyframe.extract",
    "long.video.edit.save",
    "long.video.mix.save",
    "long.video.export.start",
    "long.video.export.retry",
}

REQUEST_ID_NAMES = {
    "long.video.adaptation.create",
    "long.video.plan.start",
    "long.video.plan.confirm",
    "long.video.plan.discard",
    "long.video.episode.save",
    "long.video.prompt.start",
    "long.video.canon.candidate.set",
    "long.video.canon.approve",
    "long.video.render.start",
    "long.video.render.retry",
    "long.video.take.confirm",
    "long.video.keyframe.set",
    "long.video.keyframe.clear",
    "long.video.keyframe.extract",
    "long.video.edit.save",
    "long.video.mix.save",
    "long.video.export.start",
    "long.video.export.retry",
}


@dataclass
class RecordingApi:
    responses: list[object] = field(default_factory=lambda: [{}])
    binary_response: BinaryResponse = field(
        default_factory=lambda: BinaryResponse(
            "原始图片".encode() + b"\x00",
            "image/png",
        )
    )
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> object:
        captured = dict(kwargs)
        files = captured.get("files")
        if isinstance(files, dict) and "file" in files:
            filename, stream, content_type = files["file"]
            captured["files"] = {
                "file": (filename, stream.read(), content_type),
            }
        self.calls.append((method, path, captured))
        if not self.responses:
            raise AssertionError("测试没有配置下一次响应")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def request_bytes(self, method: str, path: str, **kwargs: Any) -> BinaryResponse:
        self.calls.append((method, path, kwargs))
        return self.binary_response

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        raise AssertionError("视频命令不应登录")

    def iter_sse(self, task_id: str, last_event_id: str | None = None) -> Any:
        raise AssertionError("视频命令不应连接写作 SSE")


def _spec(name: str) -> Any:
    return next(spec for spec in VIDEO_COMMAND_SPECS if spec.name == name)


def _runtime(name: str, api: RecordingApi) -> CliRuntime:
    spec = _spec(name)

    def api_factory(origin: str, token: str | None = None) -> RecordingApi:
        return api

    return CliRuntime(
        spec=spec,
        argv=(),
        dependencies=CliDependencies(
            api_factory=api_factory,
            config_store=MemoryConfigStore(),
            credential_store=MemoryCredentialStore(),
            getpass_fn=lambda prompt: "unused",
            stdin_isatty=lambda: False,
        ),
        api=api,
        profile="default",
        origin="http://127.0.0.1:8000",
    )


def test_video_command_specs_are_complete_and_capabilities_are_exact() -> None:
    specs = {spec.name: spec for spec in VIDEO_COMMAND_SPECS}

    assert set(specs) == COMMAND_NAMES
    assert {name for name, spec in specs.items() if spec.mutation} == MUTATION_NAMES
    assert {
        name for name, spec in specs.items() if spec.requiresClientRequestId
    } == REQUEST_ID_NAMES
    assert specs["long.video.adaptation.watch"].outputMode == "jsonl"
    assert specs["long.video.render.watch"].outputMode == "jsonl"
    assert specs["long.video.export.watch"].outputMode == "jsonl"
    assert specs["long.video.asset.download"].fileOutput.kind == "none"
    assert specs["long.video.take.download"].fileOutput.kind == "none"
    assert specs["long.video.export.download"].fileOutput.kind == "none"


@pytest.mark.parametrize(
    ("name", "payload", "path"),
    [
        (
            "long.video.project.list",
            {"novelId": "novel /?#"},
            "/api/v1/video/novels/novel%20%2F%3F%23/projects",
        ),
        (
            "long.video.project.get",
            {"projectId": "project /?#"},
            "/api/v1/video/projects/project%20%2F%3F%23",
        ),
        (
            "long.video.adaptation.list",
            {"projectId": "project /?#"},
            "/api/v1/video/projects/project%20%2F%3F%23/chapter-adaptations",
        ),
        (
            "long.video.adaptation.get",
            {"adaptationId": "adaptation /?#"},
            "/api/v1/video/chapter-adaptations/adaptation%20%2F%3F%23",
        ),
        (
            "long.video.canon.list",
            {"projectId": "project /?#"},
            "/api/v1/video/projects/project%20%2F%3F%23/visual-canons",
        ),
        (
            "long.video.render.list",
            {"adaptationId": "adaptation /?#"},
            "/api/v1/video/chapter-adaptations/adaptation%20%2F%3F%23/renders",
        ),
        (
            "long.video.render.get",
            {"taskId": "task /?#"},
            "/api/v1/video/render-tasks/task%20%2F%3F%23",
        ),
        (
            "long.video.edit.get",
            {"versionId": "edit /?#"},
            "/api/v1/video/edit-versions/edit%20%2F%3F%23",
        ),
        (
            "long.video.mix.get",
            {"versionId": "mix /?#"},
            "/api/v1/video/mix-versions/mix%20%2F%3F%23",
        ),
    ],
)
def test_video_read_commands_use_exact_encoded_public_paths(
    name: str,
    payload: dict[str, object],
    path: str,
) -> None:
    api = RecordingApi(responses=[{"尾部": "完整😀"}])

    result = _spec(name).handler(_runtime(name, api), payload)

    assert result == {"尾部": "完整😀"}
    assert api.calls == [("GET", path, {})]


def test_render_start_retry_confirm_and_download_use_public_contract(tmp_path: Path) -> None:
    api = RecordingApi(responses=[{"id": "task-1"}, {"id": "task-2"}, {"status": "succeeded"}])
    start_result = _spec("long.video.render.start").handler(
        _runtime("long.video.render.start", api),
        {
            "adaptationId": "adaptation /?#",
            "shotId": "shot /?#",
            "clientRequestId": "request-render-0001",
            "expectedPromptRevision": 3,
            "durationSeconds": 5,
            "resolution": "1080p",
            "generateAudio": False,
            "watermark": True,
        },
    )
    retry_result = _spec("long.video.render.retry").handler(
        _runtime("long.video.render.retry", api),
        {"taskId": "task /?#", "clientRequestId": "request-render-0002"},
    )
    confirm_result = _spec("long.video.take.confirm").handler(
        _runtime("long.video.take.confirm", api),
        {
            "adaptationId": "adaptation /?#",
            "shotId": "shot /?#",
            "takeId": "take /?#",
            "clientRequestId": "request-render-0003",
            "expectedTakeRevision": 2,
        },
    )
    output = tmp_path / "候选.mp4"
    download_result = _spec("long.video.take.download").handler(
        _runtime("long.video.take.download", api),
        {"takeId": "take /?#", "outputFile": str(output)},
    )

    assert start_result == {"id": "task-1"}
    assert retry_result == {"id": "task-2"}
    assert confirm_result == {"status": "succeeded"}
    assert api.calls[0] == (
        "POST",
        "/api/v1/video/chapter-adaptations/adaptation%20%2F%3F%23/shots/shot%20%2F%3F%23/render-tasks",
        {
            "json": {
                "clientRequestId": "request-render-0001",
                "expectedPromptRevision": 3,
                "durationSeconds": 5,
                "resolution": "1080p",
                "generateAudio": False,
                "watermark": True,
            }
        },
    )
    assert api.calls[1][1] == "/api/v1/video/render-tasks/task%20%2F%3F%23/retry"
    assert api.calls[2][1].endswith(
        "/adaptation%20%2F%3F%23/shots/shot%20%2F%3F%23/takes/take%20%2F%3F%23/confirm"
    )
    assert api.calls[3][1] == "/api/v1/video/takes/take%20%2F%3F%23/content"
    assert output.read_bytes() == api.binary_response.content
    assert download_result["takeId"] == "take /?#"


def test_post_production_keyframe_commands_preserve_source_fact() -> None:
    api = RecordingApi(responses=[{"revision": 2}, {"id": "frame-1"}, {"revision": 3}])

    _spec("long.video.keyframe.set").handler(
        _runtime("long.video.keyframe.set", api),
        {
            "adaptationId": "adaptation /?#",
            "shotId": "shot /?#",
            "role": "initial_state",
            "assetId": "asset-1",
            "sourceTakeId": "take-1",
            "sourceTimeMs": 1200,
            "clientRequestId": "keyframe-request-0001",
            "expectedRevision": 1,
        },
    )
    _spec("long.video.keyframe.extract").handler(
        _runtime("long.video.keyframe.extract", api),
        {
            "takeId": "take /?#",
            "timestampMs": 1200,
            "name": "第一镜首帧",
            "clientRequestId": "keyframe-request-0002",
        },
    )
    _spec("long.video.keyframe.clear").handler(
        _runtime("long.video.keyframe.clear", api),
        {
            "adaptationId": "adaptation /?#",
            "shotId": "shot /?#",
            "role": "initial_state",
            "clientRequestId": "keyframe-request-0003",
            "expectedRevision": 2,
        },
    )

    assert api.calls[0][1].endswith(
        "/adaptation%20%2F%3F%23/shots/shot%20%2F%3F%23/keyframe-versions"
    )
    assert api.calls[0][2]["json"]["sourceTakeId"] == "take-1"
    assert api.calls[1][1] == "/api/v1/video/takes/take%20%2F%3F%23/frames"
    assert api.calls[2][2]["json"]["assetId"] is None


def test_edit_and_mix_save_accept_external_json_files(tmp_path: Path) -> None:
    api = RecordingApi(responses=[{"revision": 2}, {"revision": 2}])
    edit_file = tmp_path / "edit.json"
    edit_file.write_text(
        '{"clips":[{"shotId":"shot-1","takeId":null,"sourceInMs":null,'
        '"sourceOutMs":null,"outputDurationMs":1500,"transitionAfter":"cut",'
        '"transitionDurationMs":0}]}',
        encoding="utf-8",
    )
    mix_file = tmp_path / "mix.json"
    mix_file.write_text(
        '{"audioClips":[],"subtitleCues":[{"shotId":"shot-1",'
        '"startMs":0,"endMs":1000,"speaker":null,"text":"完整对白"}]}',
        encoding="utf-8",
    )

    _spec("long.video.edit.save").handler(
        _runtime("long.video.edit.save", api),
        {
            "adaptationId": "adaptation-1",
            "episodeNo": 1,
            "clientRequestId": "edit-request-000001",
            "expectedRevision": 1,
            "basedOnVersionId": "edit-base",
            "editFile": str(edit_file),
        },
    )
    _spec("long.video.mix.save").handler(
        _runtime("long.video.mix.save", api),
        {
            "adaptationId": "adaptation-1",
            "episodeNo": 1,
            "clientRequestId": "mix-request-0000001",
            "expectedRevision": 1,
            "basedOnVersionId": "mix-base",
            "editVersionId": "edit-v1",
            "mixFile": str(mix_file),
        },
    )

    assert api.calls[0][2]["json"]["clips"][0]["outputDurationMs"] == 1500
    assert api.calls[0][2]["json"]["basedOnVersionId"] == "edit-base"
    assert api.calls[1][2]["json"]["subtitleCues"][0]["text"] == "完整对白"
    assert api.calls[1][2]["json"]["basedOnVersionId"] == "mix-base"


def test_export_start_retry_watch_and_download_use_public_contract(tmp_path: Path) -> None:
    api = RecordingApi(
        responses=[
            {"id": "export-task-1"},
            {"id": "export-task-2"},
            {"id": "export-task-1", "status": "pending", "attemptCount": 0},
            {"id": "export-task-1", "status": "succeeded", "attemptCount": 1},
        ]
    )
    _spec("long.video.export.start").handler(
        _runtime("long.video.export.start", api),
        {
            "adaptationId": "adaptation /?#",
            "episodeNo": 2,
            "editVersionId": "edit-1",
            "mixVersionId": "mix-1",
            "clientRequestId": "export-request-0001",
            "resolution": "1080p",
            "framesPerSecond": 25,
            "burnSubtitles": False,
        },
    )
    _spec("long.video.export.retry").handler(
        _runtime("long.video.export.retry", api),
        {"taskId": "task /?#", "clientRequestId": "export-request-0002"},
    )
    watcher = _spec("long.video.export.watch").handler(
        _runtime("long.video.export.watch", api),
        {"taskId": "export-task-1"},
    )
    frames = list(watcher)
    output = tmp_path / "第一集.mp4"
    result = _spec("long.video.export.download").handler(
        _runtime("long.video.export.download", api),
        {"exportId": "export /?#", "outputFile": str(output)},
    )

    assert api.calls[0][1].endswith(
        "/adaptation%20%2F%3F%23/episodes/2/export-tasks"
    )
    assert api.calls[0][2]["json"]["framesPerSecond"] == 25
    assert api.calls[1][1] == "/api/v1/video/export-tasks/task%20%2F%3F%23/retry"
    assert [frame["type"] for frame in frames] == ["snapshot", "progress", "terminal"]
    assert output.read_bytes() == api.binary_response.content
    assert result["exportId"] == "export /?#"


def test_project_create_sends_explicit_defaults() -> None:
    api = RecordingApi(responses=[{"id": "project-1"}])
    payload = {"novelId": "novel-1", "title": "第一章影视化"}

    result = _spec("long.video.project.create").handler(
        _runtime("long.video.project.create", api),
        payload,
    )

    assert result == {"id": "project-1"}
    assert api.calls == [
        (
            "POST",
            "/api/v1/video/novels/novel-1/projects",
            {
                "json": {
                    "title": "第一章影视化",
                    "mode": "highlight",
                    "targetAspectRatio": "16:9",
                    "targetLanguage": "zh-CN",
                }
            },
        )
    ]


def test_adaptation_create_and_plan_start_preserve_idempotency_fields() -> None:
    api = RecordingApi(responses=[{"id": "adaptation-1"}, {"task": {"id": "task-1"}}])
    request_id = "video-request-000001"

    _spec("long.video.adaptation.create").handler(
        _runtime("long.video.adaptation.create", api),
        {
            "projectId": "project-1",
            "chapterId": "chapter-1",
            "expectedChapterUpdatedAt": "2026-08-23T00:00:00Z",
            "clientRequestId": request_id,
        },
    )
    _spec("long.video.plan.start").handler(
        _runtime("long.video.plan.start", api),
        {
            "adaptationId": "adaptation-1",
            "clientRequestId": "video-request-000002",
            "pacingPreset": "cinematic",
            "targetEpisodeSeconds": 120,
            "baseShotPlanVersionId": "plan-v1",
            "revisionBrief": "减少机械对白切镜",
        },
    )

    assert api.calls == [
        (
            "POST",
            "/api/v1/video/projects/project-1/chapter-adaptations",
            {
                "json": {
                    "clientRequestId": request_id,
                    "chapterId": "chapter-1",
                    "expectedChapterUpdatedAt": "2026-08-23T00:00:00Z",
                }
            },
        ),
        (
            "POST",
            "/api/v1/video/chapter-adaptations/adaptation-1/shot-plan-runs",
            {
                "json": {
                    "clientRequestId": "video-request-000002",
                    "pacingPreset": "cinematic",
                    "targetEpisodeSeconds": 120,
                    "baseShotPlanVersionId": "plan-v1",
                    "revisionBrief": "减少机械对白切镜",
                }
            },
        ),
    ]


def _candidate_snapshot() -> dict[str, object]:
    return {
        "headRevision": 3,
        "candidatePlan": {"scenes": [{"sceneKey": "SC01"}]},
        "reviewArtifact": {
            "id": "artifact-1",
            "status": "awaiting_user",
            "revision": 2,
        },
    }


def test_plan_confirm_reads_complete_file_and_preflights_revisions(tmp_path: Path) -> None:
    plan = {"scenes": [{"sceneKey": "SC01", "尾部": "完整😀"}]}
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        '{"scenes":[{"sceneKey":"SC01","尾部":"完整😀"}]}',
        encoding="utf-8",
    )
    api = RecordingApi(responses=[_candidate_snapshot(), {"state": "approved"}])
    payload = {
        "adaptationId": "adaptation/1",
        "clientRequestId": "video-confirm-0001",
        "expectedArtifactRevision": 2,
        "expectedAdaptationRevision": 3,
        "planFile": str(plan_file),
    }

    result = _spec("long.video.plan.confirm").handler(
        _runtime("long.video.plan.confirm", api),
        payload,
    )

    assert result == {"state": "approved"}
    assert api.calls == [
        (
            "GET",
            "/api/v1/video/chapter-adaptations/adaptation%2F1",
            {},
        ),
        (
            "POST",
            "/api/v1/video/chapter-adaptations/adaptation%2F1/shot-plan/confirm",
            {
                "json": {
                    "clientRequestId": "video-confirm-0001",
                    "expectedArtifactRevision": 2,
                    "expectedAdaptationRevision": 3,
                    "plan": plan,
                }
            },
        ),
    ]


@pytest.mark.parametrize(
    "snapshot",
    [
        {**_candidate_snapshot(), "headRevision": 4},
        {
            **_candidate_snapshot(),
            "reviewArtifact": {
                "status": "awaiting_user",
                "revision": 5,
            },
        },
        {**_candidate_snapshot(), "candidatePlan": None},
    ],
)
def test_plan_confirm_stops_before_post_when_preflight_conflicts(
    snapshot: dict[str, object],
) -> None:
    api = RecordingApi(responses=[snapshot])

    with pytest.raises(CoreApiError) as caught:
        _spec("long.video.plan.confirm").handler(
            _runtime("long.video.plan.confirm", api),
            {
                "adaptationId": "adaptation-1",
                "clientRequestId": "video-confirm-0001",
                "expectedArtifactRevision": 2,
                "expectedAdaptationRevision": 3,
                "plan": {"scenes": []},
            },
        )

    assert caught.value.status_code == 409
    assert api.calls == [
        ("GET", "/api/v1/video/chapter-adaptations/adaptation-1", {})
    ]


def test_plan_discard_also_preflights_before_exact_post() -> None:
    api = RecordingApi(responses=[_candidate_snapshot(), {"state": "empty"}])

    _spec("long.video.plan.discard").handler(
        _runtime("long.video.plan.discard", api),
        {
            "adaptationId": "adaptation-1",
            "clientRequestId": "video-discard-0001",
            "expectedArtifactRevision": 2,
            "expectedAdaptationRevision": 3,
        },
    )

    assert api.calls[-1] == (
        "POST",
        "/api/v1/video/chapter-adaptations/adaptation-1/candidate/discard",
        {
            "json": {
                "clientRequestId": "video-discard-0001",
                "expectedArtifactRevision": 2,
                "expectedAdaptationRevision": 3,
            }
        },
    )


def test_episode_and_prompt_commands_send_exact_cas_bodies(tmp_path: Path) -> None:
    prompt = "第一行\r\n" + "镜头动作" * 300 + "\r\n尾部😀"
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_bytes(prompt.encode("utf-8"))
    api = RecordingApi(responses=[{}, {}, {}])

    _spec("long.video.episode.save").handler(
        _runtime("long.video.episode.save", api),
        {
            "adaptationId": "adaptation-1",
            "clientRequestId": "video-episode-0001",
            "expectedAdaptationRevision": 4,
            "shotPlanVersionId": "plan-1",
            "breakAfterShotIds": ["shot-2", "shot-5"],
        },
    )
    _spec("long.video.prompt.start").handler(
        _runtime("long.video.prompt.start", api),
        {
            "adaptationId": "adaptation-1",
            "clientRequestId": "video-prompt-run-01",
            "expectedAdaptationRevision": 5,
            "shotPlanVersionId": "plan-1",
            "shotIds": ["shot-1", "shot-2"],
        },
    )
    _spec("long.video.prompt.save").handler(
        _runtime("long.video.prompt.save", api),
        {
            "adaptationId": "adaptation-1",
            "shotId": "shot/1",
            "expectedPromptRevision": 2,
            "candidateTaskId": "task-prompt-1",
            "currentPromptFile": str(prompt_file),
        },
    )

    assert api.calls[0][2]["json"]["breakAfterShotIds"] == ["shot-2", "shot-5"]
    assert api.calls[1][2]["json"]["shotIds"] == ["shot-1", "shot-2"]
    assert api.calls[2] == (
        "PUT",
        "/api/v1/video/chapter-adaptations/adaptation-1/shots/shot%2F1/prompt",
        {
            "json": {
                "expectedPromptRevision": 2,
                "candidateTaskId": "task-prompt-1",
                "currentPrompt": prompt,
            }
        },
    )


def test_visual_canon_and_reference_commands_preserve_versions_and_strengths() -> None:
    api = RecordingApi(responses=[{}, {}, {}])

    _spec("long.video.canon.candidate.set").handler(
        _runtime("long.video.canon.candidate.set", api),
        {
            "projectId": "project-1",
            "clientRequestId": "video-canon-set-01",
            "settingKind": "character",
            "settingId": "character-1",
            "duty": "identity",
            "variantKey": "default",
            "label": "林默身份",
            "candidateAssetId": "asset-1",
            "includeFeatures": ["黑色短发", "左眉疤痕"],
            "excludeFeatures": ["夸张表情"],
            "defaultStrength": 72,
        },
    )
    _spec("long.video.canon.approve").handler(
        _runtime("long.video.canon.approve", api),
        {
            "canonId": "canon-1",
            "clientRequestId": "video-canon-ok-001",
            "expectedRevision": 2,
            "candidateAssetId": "asset-1",
        },
    )
    _spec("long.video.reference.save").handler(
        _runtime("long.video.reference.save", api),
        {
            "adaptationId": "adaptation-1",
            "shotId": "shot-1",
            "expectedRevision": 0,
            "references": [
                {"canonVersionId": "canon-version-1", "strength": 72},
                {"canonVersionId": "canon-version-2", "strength": 65},
            ],
        },
    )

    assert api.calls[0][2]["json"]["includeFeatures"] == ["黑色短发", "左眉疤痕"]
    assert api.calls[1][2]["json"]["expectedRevision"] == 2
    assert api.calls[2][2]["json"] == {
        "expectedRevision": 0,
        "references": [
            {"canonVersionId": "canon-version-1", "strength": 72},
            {"canonVersionId": "canon-version-2", "strength": 65},
        ],
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "projectId": "project-1",
            "clientRequestId": "video-canon-set-01",
            "settingKind": "location",
            "settingId": "location-1",
            "duty": "identity",
            "variantKey": "default",
            "label": "错误职责",
            "candidateAssetId": "asset-1",
        },
        {
            "adaptationId": "adaptation-1",
            "shotId": "shot-1",
            "expectedRevision": 1,
            "references": [
                {"canonVersionId": "version-1", "strength": 70},
                {"canonVersionId": "version-1", "strength": 60},
            ],
        },
    ],
)
def test_visual_commands_reject_kind_mismatch_or_duplicate_versions(
    payload: dict[str, Any],
) -> None:
    name = (
        "long.video.canon.candidate.set"
        if "projectId" in payload
        else "long.video.reference.save"
    )
    api = RecordingApi()

    with pytest.raises(CliInputError):
        _spec(name).handler(_runtime(name, api), payload)

    assert api.calls == []


def test_asset_upload_preserves_original_bytes_and_download_is_atomic(
    tmp_path: Path,
) -> None:
    source = tmp_path / "角色.png"
    source_bytes = b"\x89PNG\r\n\x1a\n\x00\xff\x10"
    source.write_bytes(source_bytes)
    target = tmp_path / "下载" / "角色.png"
    preview_target = tmp_path / "预览" / "角色.png"
    api = RecordingApi(
        responses=[{"id": "asset-1"}, {"id": "asset-1", "rightsStatus": "confirmed"}],
        binary_response=BinaryResponse(source_bytes, "image/png"),
    )

    _spec("long.video.asset.upload").handler(
        _runtime("long.video.asset.upload", api),
        {
            "projectId": "project-1",
            "filePath": str(source),
            "name": "林默身份图",
            "modality": "image",
            "duty": "identity",
        },
    )
    _spec("long.video.asset.rights").handler(
        _runtime("long.video.asset.rights", api),
        {"assetId": "asset/1", "rightsStatus": "confirmed"},
    )
    result = _spec("long.video.asset.download").handler(
        _runtime("long.video.asset.download", api),
        {"assetId": "asset/1", "outputFile": str(target)},
    )
    preview_result = _spec("long.video.asset.preview").handler(
        _runtime("long.video.asset.preview", api),
        {"assetId": "asset/1", "outputFile": str(preview_target)},
    )

    assert api.calls[0][2]["files"] == {
        "file": ("角色.png", source_bytes, "image/png")
    }
    assert api.calls[1] == (
        "PATCH",
        "/api/v1/video/assets/asset%2F1/rights",
        {"json": {"rightsStatus": "confirmed"}},
    )
    assert api.calls[2] == (
        "GET",
        "/api/v1/video/assets/asset%2F1/content",
        {},
    )
    assert api.calls[3] == (
        "GET",
        "/api/v1/video/assets/asset%2F1/preview",
        {},
    )
    assert target.read_bytes() == source_bytes
    assert preview_target.read_bytes() == source_bytes
    result_file = result["resultFile"]
    assert isinstance(result_file, dict)
    assert result_file["bytes"] == len(source_bytes)
    preview_result_file = preview_result["resultFile"]
    assert isinstance(preview_result_file, dict)
    assert preview_result_file["sha256"] == result_file["sha256"]


def test_video_commands_reject_unknown_fields_before_network() -> None:
    api = RecordingApi()

    with pytest.raises(CliInputError, match="unknown"):
        _spec("long.video.project.get").handler(
            _runtime("long.video.project.get", api),
            {"projectId": "project-1", "unknown": True},
        )

    assert api.calls == []


def test_video_mutation_rejects_short_client_request_id_before_network() -> None:
    api = RecordingApi()

    with pytest.raises(CliInputError, match="clientRequestId"):
        _spec("long.video.adaptation.create").handler(
            _runtime("long.video.adaptation.create", api),
            {
                "projectId": "project-1",
                "chapterId": "chapter-1",
                "expectedChapterUpdatedAt": "2026-08-23T00:00:00Z",
                "clientRequestId": "too-short",
            },
        )

    assert api.calls == []


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        (
            "long.video.prompt.start",
            {
                "adaptationId": "adaptation-1",
                "clientRequestId": "video-prompt-run-01",
                "expectedAdaptationRevision": 2,
                "shotPlanVersionId": "plan-1",
                "shotIds": ["shot-1", "shot-1"],
            },
        ),
        (
            "long.video.episode.save",
            {
                "adaptationId": "adaptation-1",
                "clientRequestId": "video-episode-0001",
                "expectedAdaptationRevision": 2,
                "shotPlanVersionId": "plan-1",
                "breakAfterShotIds": ["shot-1", "shot-1"],
            },
        ),
        (
            "long.video.reference.save",
            {
                "adaptationId": "adaptation-1",
                "shotId": "shot-1",
                "expectedRevision": True,
                "references": [],
            },
        ),
    ],
)
def test_video_commands_reject_duplicate_lists_or_boolean_revisions(
    name: str,
    payload: dict[str, Any],
) -> None:
    api = RecordingApi()

    with pytest.raises(CliInputError):
        _spec(name).handler(_runtime(name, api), payload)

    assert api.calls == []


def test_plan_confirm_requires_exactly_one_complete_plan_source() -> None:
    api = RecordingApi()
    base = {
        "adaptationId": "adaptation-1",
        "clientRequestId": "video-confirm-0001",
        "expectedArtifactRevision": 2,
        "expectedAdaptationRevision": 3,
    }

    for sources in ({}, {"plan": {}, "planFile": "plan.json"}):
        with pytest.raises(CliInputError, match="plan"):
            _spec("long.video.plan.confirm").handler(
                _runtime("long.video.plan.confirm", api),
                {**base, **sources},
            )

    assert api.calls == []


def test_prompt_save_rejects_content_beyond_public_contract_limit(
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "过长提示词.txt"
    prompt_file.write_text("镜" * 2_001, encoding="utf-8")
    api = RecordingApi()

    with pytest.raises(CliInputError, match="2000"):
        _spec("long.video.prompt.save").handler(
            _runtime("long.video.prompt.save", api),
            {
                "adaptationId": "adaptation-1",
                "shotId": "shot-1",
                "expectedPromptRevision": 1,
                "currentPromptFile": str(prompt_file),
            },
        )

    assert api.calls == []
