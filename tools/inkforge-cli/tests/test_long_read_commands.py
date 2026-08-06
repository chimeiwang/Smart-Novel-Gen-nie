from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from inkforge_cli.cli import run
from inkforge_cli.config import MemoryConfigStore, ProfileConfig
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.registry import get_command_registry
from inkforge_cli.runtime import CliDependencies

PUBLIC_ID = "id/带 空格"
ENCODED_ID = "id%2F%E5%B8%A6%20%E7%A9%BA%E6%A0%BC"


@dataclass
class RecordingApi:
    response: Any = field(default_factory=lambda: {"value": "完整响应"})
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        return self.response

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        raise AssertionError("只读命令不应登录")

    def iter_sse(self, task_id: str, last_event_id: str | None = None) -> Any:
        raise AssertionError("普通只读命令不应连接 SSE")


def _dependencies(api: RecordingApi) -> CliDependencies:
    config = MemoryConfigStore()
    config.save(
        "default",
        ProfileConfig(
            origin="http://127.0.0.1:8000",
            username="tester",
        ),
    )
    credentials = MemoryCredentialStore()
    credentials.set("default", "http://127.0.0.1:8000", "session-cookie")
    return CliDependencies(
        api_factory=lambda origin, token=None: api,
        config_store=config,
        credential_store=credentials,
        getpass_fn=lambda prompt: "unused",
        stdin_isatty=lambda: False,
    )


def _invoke(
    command: str,
    payload: dict[str, Any],
    api: RecordingApi,
) -> tuple[int, dict[str, Any], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run(
        [command],
        stdin=io.StringIO(json.dumps(payload, ensure_ascii=False)),
        stdout=stdout,
        stderr=stderr,
        dependencies=_dependencies(api),
    )
    return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()


READ_CASES = [
    (
        "long.novel.list",
        {},
        "/api/v1/novels",
        {"params": {"storyLengthProfile": "long_serial"}},
    ),
    (
        "long.novel.get",
        {"novelId": PUBLIC_ID},
        f"/api/v1/novels/{ENCODED_ID}",
        {},
    ),
    (
        "long.chapter.list",
        {"novelId": PUBLIC_ID},
        f"/api/v1/novels/{ENCODED_ID}/chapters",
        {},
    ),
    (
        "long.chapter.get",
        {"chapterId": PUBLIC_ID},
        f"/api/v1/chapters/{ENCODED_ID}",
        {},
    ),
    (
        "long.session.list",
        {"novelId": PUBLIC_ID, "chapterId": "chapter-1"},
        "/api/v1/writing/sessions",
        {"params": {"novelId": PUBLIC_ID, "chapterId": "chapter-1"}},
    ),
    (
        "long.session.get",
        {"sessionId": PUBLIC_ID},
        f"/api/v1/writing/sessions/{ENCODED_ID}",
        {},
    ),
    (
        "long.planning.get",
        {"novelId": PUBLIC_ID},
        f"/api/v1/novels/{ENCODED_ID}/workspace/planning",
        {},
    ),
    (
        "long.lore.get",
        {"novelId": PUBLIC_ID},
        f"/api/v1/novels/{ENCODED_ID}/workspace/lore",
        {},
    ),
    (
        "long.resources.get",
        {"novelId": PUBLIC_ID},
        f"/api/v1/novels/{ENCODED_ID}/workspace/resources",
        {},
    ),
    (
        "long.outline-node.list",
        {"novelId": PUBLIC_ID},
        f"/api/v1/novels/{ENCODED_ID}/outline-nodes",
        {},
    ),
    (
        "long.foreshadowing.list",
        {"novelId": PUBLIC_ID},
        f"/api/v1/novels/{ENCODED_ID}/foreshadowings",
        {},
    ),
    (
        "long.task.list",
        {
            "novelId": PUBLIC_ID,
            "chapterId": "chapter-1",
            "writingSessionId": "session-1",
            "operation": "review_chapter",
            "outcome": "succeeded",
            "cursor": "next/cursor",
            "limit": 37,
        },
        "/api/v1/writing/runs",
        {
            "params": {
                "novelId": PUBLIC_ID,
                "chapterId": "chapter-1",
                "writingSessionId": "session-1",
                "operation": "review_chapter",
                "outcome": "succeeded",
                "cursor": "next/cursor",
                "limit": 37,
            }
        },
    ),
    (
        "long.task.get",
        {"taskId": PUBLIC_ID},
        f"/api/v1/writing/runs/{ENCODED_ID}",
        {},
    ),
    (
        "long.artifact.list",
        {
            "novelId": PUBLIC_ID,
            "chapterId": "chapter-1",
            "taskId": "task-1",
            "status": "awaiting_user",
            "kind": "chapter_draft",
            "cursor": "next/cursor",
            "limit": 41,
        },
        "/api/v1/review-artifacts",
        {
            "params": {
                "novelId": PUBLIC_ID,
                "chapterId": "chapter-1",
                "taskId": "task-1",
                "status": "awaiting_user",
                "kind": "chapter_draft",
                "cursor": "next/cursor",
                "limit": 41,
            }
        },
    ),
    (
        "long.artifact.get",
        {"artifactId": PUBLIC_ID},
        f"/api/v1/review-artifacts/{ENCODED_ID}",
        {},
    ),
    (
        "long.quality.get",
        {"checkId": PUBLIC_ID},
        f"/api/v1/quality-checks/{ENCODED_ID}",
        {},
    ),
]


@pytest.mark.parametrize(
    ("command", "payload", "expected_path", "expected_kwargs"),
    READ_CASES,
)
def test_long_read_command_uses_exact_get_mapping(
    command: str,
    payload: dict[str, Any],
    expected_path: str,
    expected_kwargs: dict[str, Any],
) -> None:
    api = RecordingApi(response={"command": command, "尾部": "完整🚀"})

    exit_code, output, stderr = _invoke(
        command,
        {**payload, "profile": "default"},
        api,
    )

    assert exit_code == 0
    assert stderr == ""
    assert output["data"] == {"command": command, "尾部": "完整🚀"}
    assert api.calls == [("GET", expected_path, expected_kwargs)]


@pytest.mark.parametrize(
    ("command", "payload", "_expected_path", "_expected_kwargs"),
    READ_CASES,
)
def test_long_read_command_rejects_unknown_fields_before_request(
    command: str,
    payload: dict[str, Any],
    _expected_path: str,
    _expected_kwargs: dict[str, Any],
) -> None:
    api = RecordingApi()

    exit_code, output, _stderr = _invoke(
        command,
        {**payload, "unexpected": True},
        api,
    )

    assert exit_code == 2
    assert output["error"]["code"] == "UNEXPECTED_FIELDS"
    assert api.calls == []


def test_long_novel_list_does_not_allow_profile_filter_override() -> None:
    api = RecordingApi()

    exit_code, output, _stderr = _invoke(
        "long.novel.list",
        {"storyLengthProfile": "short_medium"},
        api,
    )

    assert exit_code == 2
    assert output["error"]["code"] == "UNEXPECTED_FIELDS"
    assert api.calls == []


def test_long_task_get_keeps_full_review_report_inline() -> None:
    review_report = "审核" * 40_001 + "尾部🚀"
    response = {
        "taskId": "task-1",
        "operation": "review_chapter",
        "reviewReport": review_report,
    }
    api = RecordingApi(response=response)

    exit_code, output, _stderr = _invoke(
        "long.task.get",
        {"taskId": "task-1"},
        api,
    )

    assert exit_code == 0
    assert output["data"] == response
    assert output["data"]["reviewReport"].endswith("尾部🚀")


def test_long_task_get_writes_complete_unwrapped_json_when_requested(
    tmp_path: Path,
) -> None:
    review_report = "审核" * 40_001 + "尾部🚀"
    response = {"taskId": "task-1", "reviewReport": review_report}
    output_file = tmp_path / "task.json"
    api = RecordingApi(response=response)

    exit_code, output, _stderr = _invoke(
        "long.task.get",
        {"taskId": "task-1", "outputFile": str(output_file)},
        api,
    )

    assert exit_code == 0
    assert json.loads(output_file.read_text(encoding="utf-8")) == response
    assert output["data"]["resultFile"]["path"] == str(output_file.resolve())
    assert api.calls == [("GET", "/api/v1/writing/runs/task-1", {})]


def test_long_chapter_get_writes_primary_content_when_requested(
    tmp_path: Path,
) -> None:
    content = "章节正文\r\n" + "正文" * 40_001 + "尾部🚀"
    output_file = tmp_path / "chapter.txt"
    api = RecordingApi(
        response={"id": "chapter-1", "title": "第一章", "content": content}
    )

    exit_code, output, _stderr = _invoke(
        "long.chapter.get",
        {"chapterId": "chapter-1", "outputFile": str(output_file)},
        api,
    )

    assert exit_code == 0
    assert output_file.read_bytes() == content.encode("utf-8")
    assert output["data"]["id"] == "chapter-1"
    assert "content" not in output["data"]
    assert output["data"]["contentFile"]["path"] == str(output_file.resolve())


def test_long_read_registry_declares_expected_file_output_contracts() -> None:
    registry = get_command_registry()
    read_names = {case[0] for case in READ_CASES}

    assert registry["long.chapter.get"].fileOutput.kind == "primary_text"
    assert registry["long.chapter.get"].fileOutput.field == "content"
    assert registry["long.chapter.get"].fileOutput.media_type == (
        "text/plain; charset=utf-8"
    )
    assert all(
        registry[name].fileOutput.kind == "data_json"
        for name in read_names - {"long.chapter.get"}
    )
    assert all(registry[name].mutation is False for name in read_names)
