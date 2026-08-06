from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from inkforge_cli.api import SseConnectionError
from inkforge_cli.cli import CliDependencies, run
from inkforge_cli.config import MemoryConfigStore, ProfileConfig
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.files import export_snapshot, sha256_text


@dataclass
class RecordingApi:
    responses: list[Any] = field(default_factory=list)
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method, path, kwargs))
        return self.responses.pop(0) if self.responses else {}

    def login(self, username: str, provided_secret: str) -> tuple[dict[str, Any], str]:
        assert provided_secret == "pw-" + "secret"
        return {"id": "user-1", "username": username}, "cookie-secret"

    def iter_sse(self, task_id: str, last_event_id: str | None = None):
        self.calls.append(("SSE", task_id, {"lastEventId": last_event_id}))
        yield {"id": "1", "event": "progress", "data": {"sequence": 1}}
        yield {"id": "2", "event": "done", "data": {"sequence": 2}}


@dataclass
class ReconnectingApi(RecordingApi):
    disconnects_before_success: int = 1
    sse_attempts: int = 0

    def iter_sse(self, task_id: str, last_event_id: str | None = None):
        self.sse_attempts += 1
        self.calls.append(("SSE", task_id, {"lastEventId": last_event_id}))
        if self.sse_attempts <= self.disconnects_before_success:
            if last_event_id is None:
                yield {"id": "7", "event": "progress", "data": {"sequence": 7}}
            raise SseConnectionError("连接中断")
        yield {"id": "8", "event": "done", "data": {"sequence": 8}}


def dependencies(api: RecordingApi, *, tty: bool = True) -> CliDependencies:
    config = MemoryConfigStore()
    config.save(
        "default",
        ProfileConfig(
            origin="http://127.0.0.1:8000",
            username="nie",
        ),
    )
    credentials = MemoryCredentialStore()
    credentials.set("default", "http://127.0.0.1:8000", "session-cookie")
    return CliDependencies(
        api_factory=lambda origin, token=None: api,
        config_store=config,
        credential_store=credentials,
        getpass_fn=lambda prompt: "pw-secret",
        stdin_isatty=lambda: tty,
    )


def invoke(
    command: str,
    payload: dict[str, Any],
    api: RecordingApi,
) -> tuple[int, dict[str, Any], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        [command],
        stdin=io.StringIO(json.dumps(payload, ensure_ascii=False)),
        stdout=stdout,
        stderr=stderr,
        dependencies=dependencies(api),
    )
    return code, json.loads(stdout.getvalue()), stderr.getvalue()


def create_clean_snapshot(tmp_path: Path) -> str:
    export_snapshot(
        tmp_path,
        novel_id="novel-1",
        outline="已同步大纲",
        manuscript="已同步正文",
        metadata={"outlineUpdatedAt": "v1", "manuscriptUpdatedAt": "v1"},
    )
    return str(tmp_path / "manifest.json")


def test_login_requires_real_tty_and_never_prints_password_or_cookie() -> None:
    api = RecordingApi()
    stdout = io.StringIO()
    stderr = io.StringIO()
    deps = dependencies(api, tty=False)

    code = run(
        [
            "auth.login",
            "--origin",
            "http://127.0.0.1:8000",
            "--username",
            "nie",
        ],
        stdin=io.StringIO(),
        stdout=stdout,
        stderr=stderr,
        dependencies=deps,
    )

    output = stdout.getvalue() + stderr.getvalue()
    assert code == 2
    assert "真实终端" in output
    assert "pw-secret" not in output
    assert "cookie-secret" not in output


def test_login_saves_cookie_but_stdout_contains_only_user_identity() -> None:
    api = RecordingApi()
    stdout = io.StringIO()
    deps = dependencies(api)

    code = run(
        [
            "auth.login",
            "--origin",
            "http://127.0.0.1:8000",
            "--username",
            "nie",
        ],
        stdin=io.StringIO(),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=deps,
    )

    result = json.loads(stdout.getvalue())
    assert code == 0
    assert result["data"]["username"] == "nie"
    assert "cookie-secret" not in stdout.getvalue()
    assert "pw-secret" not in stdout.getvalue()


def test_login_argument_error_never_writes_argparse_usage_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        ["auth.login", "--password", "forbidden"],
        stdin=io.StringIO(),
        stdout=stdout,
        stderr=stderr,
        dependencies=dependencies(RecordingApi()),
    )

    result = json.loads(stdout.getvalue())
    captured = capsys.readouterr()
    assert code == 2
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
    assert stderr.getvalue() == ""
    assert captured.err == ""


def test_plain_command_consumes_one_json_and_emits_one_json() -> None:
    api = RecordingApi(responses=[[{"id": "novel-1"}]])

    code, result, stderr = invoke("short.list", {}, api)

    assert code == 0
    assert result == {
        "ok": True,
        "command": "short.list",
        "data": {"novels": [{"id": "novel-1"}]},
    }
    assert stderr == ""
    assert api.calls[0][0:2] == ("GET", "/api/v1/novels")
    assert api.calls[0][2]["params"] == {"storyLengthProfile": "short_medium"}


def test_unknown_command_is_rejected_before_reading_stdin_or_credentials() -> None:
    stdout = io.StringIO()
    deps = dependencies(RecordingApi())
    deps.config_store.delete("default")

    code = run(
        ["short.does-not-exist"],
        stdin=io.StringIO("this is deliberately not json"),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=deps,
    )

    result = json.loads(stdout.getvalue())
    assert code == 2
    assert result["error"]["code"] == "UNKNOWN_COMMAND"


def test_windows_powershell_utf8_bom_is_accepted() -> None:
    api = RecordingApi(responses=[[]])
    stdout = io.StringIO()

    code = run(
        ["short.list"],
        stdin=io.StringIO("\ufeff{}\r\n"),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=dependencies(api),
    )

    assert code == 0


def test_create_requires_caller_owned_stable_client_request_id() -> None:
    code, result, _ = invoke(
        "short.create",
        {
            "name": "作品",
            "storyLengthProfile": "short_medium",
            "targetTotalWordCount": 20_000,
            "sourceKind": "idea",
            "sourceText": "灵感",
        },
        RecordingApi(),
    )

    assert code == 2
    assert result["error"]["code"] == "CLIENT_REQUEST_ID_REQUIRED"


def test_draft_save_maps_outline_and_manuscript_to_existing_public_routes(
    tmp_path: Path,
) -> None:
    export_snapshot(
        tmp_path,
        novel_id="novel-1",
        outline="旧蓝图",
        manuscript="旧正文",
        metadata={
            "chapterId": "chapter-1",
            "outlineUpdatedAt": "v1",
            "manuscriptUpdatedAt": "v2",
        },
    )
    outline_file = tmp_path / "outline.md"
    manuscript_file = tmp_path / "manuscript.txt"
    outline_file.write_text("蓝图", encoding="utf-8")
    manuscript_file.write_text("正文", encoding="utf-8")
    manifest_file = tmp_path / "manifest.json"
    api = RecordingApi(
        responses=[
            {"updatedAt": "v2", "contentHash": "a" * 64},
            {"updatedAt": "v3"},
        ]
    )

    invoke(
        "short.draft.save",
        {
            "novelId": "novel-1",
            "documentType": "outline",
            "filePath": str(outline_file),
            "manifestPath": str(manifest_file),
        },
        api,
    )
    invoke(
        "short.draft.save",
        {
            "novelId": "novel-1",
            "documentType": "manuscript",
            "filePath": str(manuscript_file),
            "manifestPath": str(manifest_file),
            "title": "全文",
        },
        api,
    )

    assert api.calls[0][0:2] == ("PUT", "/api/v1/novels/novel-1/outline")
    assert api.calls[0][2]["json"]["content"] == "蓝图"
    assert api.calls[0][2]["json"]["expectedUpdatedAt"] == "v1"
    assert api.calls[1][0:2] == ("PATCH", "/api/v1/chapters/chapter-1")
    assert api.calls[1][2]["json"]["content"] == "正文"
    assert api.calls[1][2]["json"]["expectedUpdatedAt"] == "v2"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["outlineUpdatedAt"] == "v2"
    assert manifest["manuscriptUpdatedAt"] == "v3"
    assert manifest["documents"]["outline"]["contentHash"] == sha256_text("蓝图")
    assert manifest["documents"]["manuscript"]["contentHash"] == sha256_text("正文")


@pytest.mark.parametrize(
    ("command", "method", "path"),
    [
        ("short.version.preview", "POST", "/api/v1/novels/novel-1/versions/preview"),
        ("short.version.submit", "POST", "/api/v1/novels/novel-1/versions"),
        ("short.version.list", "GET", "/api/v1/novels/novel-1/versions"),
        ("short.version.get", "GET", "/api/v1/novels/novel-1/versions/version-1"),
        ("short.version.diff", "GET", "/api/v1/novels/novel-1/version-diff"),
        (
            "short.version.adopt",
            "POST",
            "/api/v1/novels/novel-1/versions/version-1/adopt",
        ),
        (
            "short.version.restore",
            "POST",
            "/api/v1/novels/novel-1/versions/version-1/restore",
        ),
        ("short.agent.start", "POST", "/api/v1/writing/runs"),
    ],
)
def test_command_maps_to_public_api(
    tmp_path: Path,
    command: str,
    method: str,
    path: str,
) -> None:
    payload: dict[str, Any] = {
        "novelId": "novel-1",
        "versionId": "version-1",
        "documentType": "outline",
    }
    if command in {
        "short.version.submit",
        "short.version.adopt",
        "short.version.restore",
        "short.agent.start",
    }:
        payload["clientRequestId"] = "request-12345678"
        payload["manifestPath"] = create_clean_snapshot(tmp_path)
    if command == "short.agent.start":
        payload["operation"] = "outline"
    if command in {
        "short.version.submit",
        "short.version.adopt",
        "short.version.restore",
    }:
        payload["confirmationHash"] = "a" * 64

    api = RecordingApi()
    code, _, _ = invoke(command, payload, api)

    assert code == 0
    assert api.calls[0][0:2] == (method, path)


def test_watch_emits_jsonl_then_reads_persistent_terminal_state() -> None:
    api = RecordingApi(
        responses=[
            {
                "taskId": "task-1",
                "phase": "completed",
                "commandStatus": "succeeded",
            }
        ]
    )
    stdout = io.StringIO()

    code = run(
        ["short.agent.watch"],
        stdin=io.StringIO(json.dumps({"taskId": "task-1"})),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=dependencies(api),
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert code == 0
    assert [line["type"] for line in lines] == ["event", "event", "terminal"]
    assert api.calls[-1][0:2] == ("GET", "/api/v1/writing/runs/task-1")


def test_watch_reconnects_with_last_event_id_before_reading_terminal_state() -> None:
    api = ReconnectingApi(
        responses=[
            {
                "taskId": "task-1",
                "phase": "completed",
                "commandStatus": "succeeded",
            }
        ],
        disconnects_before_success=1,
    )
    stdout = io.StringIO()

    code = run(
        ["short.agent.watch"],
        stdin=io.StringIO(json.dumps({"taskId": "task-1"})),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=dependencies(api),
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    sse_calls = [call for call in api.calls if call[0] == "SSE"]
    assert code == 0
    assert [call[2]["lastEventId"] for call in sse_calls] == [None, "7"]
    assert [line["type"] for line in lines] == ["event", "event", "terminal"]
    assert api.calls[-1][0:2] == ("GET", "/api/v1/writing/runs/task-1")


def test_watch_bounds_reconnects_and_reads_persistent_state_after_exhaustion() -> None:
    api = ReconnectingApi(
        responses=[{"id": "task-1", "phase": "running"}],
        disconnects_before_success=99,
    )
    stdout = io.StringIO()

    code = run(
        ["short.agent.watch"],
        stdin=io.StringIO(json.dumps({"taskId": "task-1"})),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=dependencies(api),
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert code == 5
    assert len([call for call in api.calls if call[0] == "SSE"]) == 4
    assert api.calls[-1][0:2] == ("GET", "/api/v1/writing/runs/task-1")
    assert [line["type"] for line in lines[-2:]] == ["state", "error"]


def test_version_diff_uses_two_version_ids_and_writes_the_complete_file(
    tmp_path: Path,
) -> None:
    tail = "差异尾部😀"
    api = RecordingApi(
        responses=[
            {
                "fromVersionId": "version-a",
                "toVersionId": "version-b",
                "blocks": [{"type": "added", "text": "甲" * 80_000 + tail}],
            }
        ]
    )
    output_file = tmp_path / "diff.json"

    code, result, _ = invoke(
        "short.version.diff",
        {
            "novelId": "novel-1",
            "fromVersionId": "version-a",
            "toVersionId": "version-b",
            "outputFile": str(output_file),
        },
        api,
    )

    assert code == 0
    assert api.calls[0][2]["params"] == {
        "fromVersionId": "version-a",
        "toVersionId": "version-b",
    }
    assert output_file.read_text(encoding="utf-8").rstrip().endswith(f'{tail}"\n    }}\n  ]\n}}')
    assert result["data"]["diffFile"]["contentHash"]


def test_agent_start_sends_only_the_final_short_medium_public_contract(
    tmp_path: Path,
) -> None:
    export_snapshot(
        tmp_path,
        novel_id="novel-1",
        outline="已同步大纲",
        manuscript="已同步正文",
        metadata={"outlineUpdatedAt": "v1", "manuscriptUpdatedAt": "v1"},
    )
    api = RecordingApi()

    code, _, _ = invoke(
        "short.agent.start",
        {
            "novelId": "novel-1",
            "clientRequestId": "request-12345678",
            "operation": "selection",
            "documentType": "outline",
            "baseVersionId": "outline-v1",
            "selectionStart": 2,
            "selectionEnd": 8,
            "selectedTextHash": "b" * 64,
            "userInstruction": "只修改选区",
            "manifestPath": str(tmp_path / "manifest.json"),
            "profile": "default",
            "content": "不得发送的全文",
            "contentHash": "c" * 64,
            "baseContentHash": "d" * 64,
            "selectedText": "不得发送的原选区",
            "sourceText": "不得发送的素材",
            "targetTotalWordCount": 20_000,
            "target": "不得发送的目标",
        },
        api,
    )

    assert code == 0
    assert api.calls[0][2]["json"] == {
        "clientRequestId": "request-12345678",
        "workflow": "short_medium",
        "novelId": "novel-1",
        "operation": "replace_selection",
        "documentType": "outline",
        "baseVersionId": "outline-v1",
        "selectionStart": 2,
        "selectionEnd": 8,
        "selectedTextHash": "b" * 64,
        "userInstruction": "只修改选区",
    }


@pytest.mark.parametrize(
    ("shortcut", "operation", "document_type", "extra"),
    [
        ("outline", "generate_outline", "outline", {}),
        (
            "manuscript",
            "generate_manuscript",
            "manuscript",
            {"chapterId": "chapter-1", "sourceOutlineVersionId": "outline-v1"},
        ),
        (
            "selection",
            "replace_selection",
            "manuscript",
            {
                "chapterId": "chapter-1",
                "baseVersionId": "manuscript-v1",
                "selectionStart": 1,
                "selectionEnd": 3,
                "selectedTextHash": "a" * 64,
                "userInstruction": "加强这句话的冲突",
            },
        ),
        (
            "full_check",
            "full_check",
            "manuscript",
            {"chapterId": "chapter-1", "baseVersionId": "manuscript-v1"},
        ),
    ],
)
def test_agent_start_maps_each_cli_shortcut_to_the_shared_operation(
    tmp_path: Path,
    shortcut: str,
    operation: str,
    document_type: str,
    extra: dict[str, Any],
) -> None:
    api = RecordingApi()
    payload: dict[str, Any] = {
        "novelId": "novel-1",
        "clientRequestId": "request-12345678",
        "operation": shortcut,
        "documentType": document_type,
        "manifestPath": create_clean_snapshot(tmp_path),
        **extra,
    }

    code, _, _ = invoke(
        "short.agent.start",
        payload,
        api,
    )

    assert code == 0
    sent = api.calls[0][2]["json"]
    assert sent["operation"] == operation
    assert sent["documentType"] == document_type


def test_selection_agent_start_requires_a_non_empty_instruction(
    tmp_path: Path,
) -> None:
    api = RecordingApi()
    payload = {
        "novelId": "novel-1",
        "clientRequestId": "request-12345678",
        "operation": "selection",
        "documentType": "manuscript",
        "chapterId": "chapter-1",
        "baseVersionId": "manuscript-v1",
        "selectionStart": 1,
        "selectionEnd": 3,
        "selectedTextHash": "a" * 64,
        "userInstruction": "  ",
        "manifestPath": create_clean_snapshot(tmp_path),
    }

    code, result, _ = invoke("short.agent.start", payload, api)

    assert code == 2
    assert result["error"]["code"] == "FIELD_REQUIRED"
    assert api.calls == []


@pytest.mark.parametrize(
    "terminal",
    [
        {
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "phase": "completed",
            "updatedAt": "2026-07-30T12:00:00Z",
            "commandId": "command-1",
            "commandStatus": "succeeded",
            "operation": "generate_manuscript",
            "candidateVersionId": "version-2",
            "checkReport": None,
            "error": None,
        },
        {
            "taskId": "task-2",
            "novelId": "novel-1",
            "chapterId": "chapter-1",
            "phase": "error",
            "updatedAt": "2026-07-30T12:01:00Z",
            "commandId": "command-2",
            "commandStatus": "failed",
            "operation": "replace_selection",
            "candidateVersionId": None,
            "checkReport": None,
            "error": {"code": "MODEL_FAILED"},
        },
    ],
)
def test_watch_preserves_the_final_public_terminal_contract(
    terminal: dict[str, Any],
) -> None:
    api = RecordingApi(responses=[terminal])
    stdout = io.StringIO()

    code = run(
        ["short.agent.watch"],
        stdin=io.StringIO(json.dumps({"taskId": terminal["taskId"]})),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=dependencies(api),
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert code == 0
    assert lines[-1] == {"type": "terminal", "data": terminal}


@pytest.mark.parametrize(
    "command",
    [
        "short.version.submit",
        "short.version.adopt",
        "short.version.restore",
    ],
)
@pytest.mark.parametrize("confirmation_hash", ["a" * 63, "A" * 64, "not-a-hash"])
def test_version_writes_require_a_lowercase_sha256_confirmation_hash(
    command: str,
    confirmation_hash: str,
) -> None:
    payload: dict[str, Any] = {
        "novelId": "novel-1",
        "versionId": "version-1",
        "documentType": "outline",
        "clientRequestId": "request-12345678",
        "confirmationHash": confirmation_hash,
    }
    api = RecordingApi()

    code, result, _ = invoke(command, payload, api)

    assert code == 2
    assert result["error"]["code"] == "INVALID_CONFIRMATION_HASH"
    assert api.calls == []


@pytest.mark.parametrize(
    "command",
    [
        "short.agent.start",
        "short.version.submit",
        "short.version.adopt",
        "short.version.restore",
    ],
)
def test_protected_operations_reject_a_dirty_snapshot(
    tmp_path: Path,
    command: str,
) -> None:
    create_clean_snapshot(tmp_path)
    (tmp_path / "outline.md").write_text("未保存的大纲修改", encoding="utf-8")
    payload: dict[str, Any] = {
        "novelId": "novel-1",
        "versionId": "version-1",
        "documentType": "outline",
        "clientRequestId": "request-12345678",
        "confirmationHash": "a" * 64,
        "manifestPath": str(tmp_path / "manifest.json"),
    }
    if command == "short.agent.start":
        payload["operation"] = "outline"
    api = RecordingApi()

    code, result, _ = invoke(command, payload, api)

    assert code == 6
    assert result["error"]["code"] == "LOCAL_FILE_ERROR"
    assert api.calls == []


@pytest.mark.parametrize(
    "command",
    [
        "short.agent.start",
        "short.version.submit",
        "short.version.adopt",
        "short.version.restore",
    ],
)
def test_protected_operations_require_a_snapshot_manifest(command: str) -> None:
    payload: dict[str, Any] = {
        "novelId": "novel-1",
        "versionId": "version-1",
        "documentType": "outline",
        "clientRequestId": "request-12345678",
        "confirmationHash": "a" * 64,
    }
    if command == "short.agent.start":
        payload["operation"] = "outline"
    api = RecordingApi()

    code, result, _ = invoke(command, payload, api)

    assert code == 2
    assert result["error"]["code"] == "MANIFEST_REQUIRED"
    assert api.calls == []


@pytest.mark.parametrize(
    "command",
    [
        "short.agent.start",
        "short.version.submit",
        "short.version.adopt",
        "short.version.restore",
    ],
)
def test_clean_snapshot_manifest_is_a_local_gate_not_an_api_field(
    tmp_path: Path,
    command: str,
) -> None:
    create_clean_snapshot(tmp_path)
    payload: dict[str, Any] = {
        "novelId": "novel-1",
        "versionId": "version-1",
        "documentType": "outline",
        "clientRequestId": "request-12345678",
        "confirmationHash": "a" * 64,
        "manifestPath": str(tmp_path / "manifest.json"),
    }
    if command == "short.agent.start":
        payload["operation"] = "outline"
    api = RecordingApi()

    code, _, _ = invoke(command, payload, api)

    assert code == 0
    assert "manifestPath" not in api.calls[0][2]["json"]


def test_whoami_rejects_an_identity_different_from_the_expected_username() -> None:
    api = RecordingApi(responses=[{"id": "user-2", "username": "other"}])

    code, result, _ = invoke(
        "auth.whoami",
        {"expectedUsername": "nie"},
        api,
    )

    assert code == 3
    assert result["error"]["code"] == "IDENTITY_MISMATCH"


def test_pull_exports_both_documents_and_version_metadata(tmp_path: Path) -> None:
    api = RecordingApi(
        responses=[
            {
                "currentChapter": {
                    "id": "chapter-1",
                    "content": "完整正文",
                    "updatedAt": "2026-07-30T12:00:00Z",
                }
            },
            {
                "outline": {
                    "content": "完整大纲",
                    "updatedAt": "2026-07-30T11:00:00Z",
                }
            },
            [{"id": "outline-v1", "status": "applied"}],
            [{"id": "manuscript-v1", "status": "applied"}],
        ]
    )

    code, result, _ = invoke(
        "short.pull",
        {"novelId": "novel-1", "outputDirectory": str(tmp_path)},
        api,
    )

    assert code == 0
    assert (tmp_path / "outline.md").read_text(encoding="utf-8") == "完整大纲"
    assert (tmp_path / "manuscript.txt").read_text(encoding="utf-8") == "完整正文"
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["outlineVersions"][0]["id"] == "outline-v1"
    assert manifest["manuscriptVersions"][0]["id"] == "manuscript-v1"
    assert result["data"]["manifestPath"] == str((tmp_path / "manifest.json").resolve())
