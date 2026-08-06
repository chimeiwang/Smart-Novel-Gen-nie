from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from inkforge_cli.api import CoreTransportError, SseConnectionError
from inkforge_cli.cli import run
from inkforge_cli.config import MemoryConfigStore, ProfileConfig
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import CliDependencies

TASK_ID = "task/带 空格"
ENCODED_TASK_ID = "task%2F%E5%B8%A6%20%E7%A9%BA%E6%A0%BC"
TASK_PATH = f"/api/v1/writing/runs/{ENCODED_TASK_ID}"


@dataclass
class FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class WatchApi:
    snapshots: list[object]
    streams: list[list[object]] = field(default_factory=list)
    unreachable_after_snapshots: bool = False
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if self.snapshots:
            result = self.snapshots.pop(0)
        elif self.unreachable_after_snapshots:
            result = CoreTransportError()
        else:
            raise AssertionError("测试没有配置下一次 Core 状态响应")
        if isinstance(result, BaseException):
            raise result
        return result

    def iter_sse(self, task_id: str, last_event_id: str | None = None) -> Any:
        self.calls.append(("SSE", task_id, {"lastEventId": last_event_id}))
        if not self.streams:
            raise AssertionError("测试没有配置下一次 SSE 连接")
        stream = self.streams.pop(0)
        for item in stream:
            if isinstance(item, BaseException):
                raise item
            yield item

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        raise AssertionError("观察命令不应登录")


def _status(
    state: str,
    *,
    artifact_id: str | None = None,
    phase: str = "仅用于展示",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "taskId": TASK_ID,
        "phase": phase,
        "commandStatus": "不参与生命周期判断",
        "outcome": {
            "state": state,
            "result": {
                "kind": "review_artifact" if artifact_id else "none",
                "ready": artifact_id is not None,
                "id": artifact_id,
            },
        },
        **extra,
    }


def _dependencies(api: WatchApi, clock: FakeClock) -> CliDependencies:
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
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )


def _invoke(
    api: WatchApi,
    clock: FakeClock,
    payload: dict[str, Any] | None = None,
) -> tuple[int, list[dict[str, Any]], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run(
        ["long.task.watch"],
        stdin=io.StringIO(
            json.dumps(payload or {"taskId": TASK_ID}, ensure_ascii=False)
        ),
        stdout=stdout,
        stderr=stderr,
        dependencies=_dependencies(api, clock),
    )
    frames = [json.loads(line) for line in stdout.getvalue().splitlines()]
    return exit_code, frames, stderr.getvalue()


def test_watch_gets_snapshot_before_sse_and_reconnects_with_latest_event_id() -> None:
    initial = _status("running")
    after_disconnect = _status("running")
    terminal = _status("succeeded")
    api = WatchApi(
        snapshots=[initial, after_disconnect, terminal],
        streams=[
            [
                {"id": "event-1", "event": "progress", "data": {"step": 1}},
                SseConnectionError("断线"),
            ],
            [{"id": "event-2", "event": "progress", "data": {"step": 2}}],
        ],
    )
    clock = FakeClock()

    exit_code, frames, stderr = _invoke(api, clock)

    assert exit_code == 0
    assert stderr == ""
    assert frames == [
        {"type": "snapshot", "data": initial},
        {
            "type": "event",
            "id": "event-1",
            "event": "progress",
            "data": {"step": 1},
        },
        {
            "type": "event",
            "id": "event-2",
            "event": "progress",
            "data": {"step": 2},
        },
        {"type": "terminal", "data": terminal},
    ]
    assert api.calls == [
        ("GET", TASK_PATH, {}),
        ("SSE", TASK_ID, {"lastEventId": None}),
        ("GET", TASK_PATH, {}),
        ("SSE", TASK_ID, {"lastEventId": "event-1"}),
        ("GET", TASK_PATH, {}),
    ]
    assert clock.sleeps == [0.5]


def test_watch_does_not_timeout_when_core_is_reachable_without_sse_events() -> None:
    running_checks = 35
    api = WatchApi(
        snapshots=[
            _status("running"),
            *[_status("running") for _ in range(running_checks)],
            _status("succeeded"),
        ],
        streams=[[] for _ in range(running_checks + 1)],
    )
    clock = FakeClock()

    exit_code, frames, _stderr = _invoke(api, clock)

    assert exit_code == 0
    assert frames[0]["type"] == "snapshot"
    assert frames[-1]["type"] == "terminal"
    assert all(frame["type"] != "error" for frame in frames)
    assert clock.sleeps[:5] == [0.5, 1.0, 2.0, 5.0, 10.0]
    assert max(clock.sleeps) == 10.0
    assert clock.now > 300.0


@pytest.mark.parametrize(
    ("state", "expected_exit_code", "expected_frame_type"),
    [
        ("waiting_user", 0, "waiting_user"),
        ("succeeded", 0, "terminal"),
        ("failed", 5, "terminal"),
        ("cancelled", 5, "terminal"),
        ("inconsistent", 5, "terminal"),
    ],
)
def test_watch_uses_only_outcome_state_for_terminal_result(
    state: str,
    expected_exit_code: int,
    expected_frame_type: str,
) -> None:
    status = _status(
        state,
        artifact_id="artifact-1" if state == "waiting_user" else None,
        phase="active" if state != "waiting_user" else "completed",
    )
    api = WatchApi(snapshots=[status])

    exit_code, frames, _stderr = _invoke(api, FakeClock())

    assert exit_code == expected_exit_code
    assert frames[0] == {"type": "snapshot", "data": status}
    assert frames[-1]["type"] == expected_frame_type
    assert frames[-1]["data"] == status
    if state == "waiting_user":
        assert frames[-1]["taskId"] == TASK_ID
        assert frames[-1]["artifactId"] == "artifact-1"
    assert api.calls == [("GET", TASK_PATH, {})]


def test_watch_terminal_frame_keeps_complete_review_report() -> None:
    review_report = "审核" * 40_001 + "尾部🚀"
    status = _status(
        "succeeded",
        operation="review_chapter",
        reviewReport=review_report,
    )
    api = WatchApi(snapshots=[status])

    exit_code, frames, _stderr = _invoke(api, FakeClock())

    assert exit_code == 0
    assert frames[-1] == {"type": "terminal", "data": status}
    assert frames[-1]["data"]["reviewReport"].endswith("尾部🚀")


def test_watch_ignores_terminal_looking_legacy_fields_while_outcome_is_running() -> None:
    running = _status(
        "running",
        phase="completed",
        commandStatus="succeeded",
    )
    terminal = _status("succeeded", phase="active", commandStatus="pending")
    api = WatchApi(snapshots=[running, terminal], streams=[[]])

    exit_code, frames, _stderr = _invoke(api, FakeClock())

    assert exit_code == 0
    assert frames == [
        {"type": "snapshot", "data": running},
        {"type": "terminal", "data": terminal},
    ]
    assert api.calls[1] == ("SSE", TASK_ID, {"lastEventId": None})


def test_watch_exits_after_core_is_continuously_unreachable_for_over_300_seconds() -> None:
    running = _status("running")
    api = WatchApi(
        snapshots=[running],
        streams=[
            [
                {"id": "event-9", "event": "progress", "data": {"step": 9}},
                SseConnectionError("断线"),
            ]
        ],
        unreachable_after_snapshots=True,
    )
    clock = FakeClock()

    exit_code, frames, _stderr = _invoke(api, clock)

    assert exit_code == 5
    assert frames[-1]["type"] == "error"
    assert frames[-1]["error"] == {
        "code": "WATCH_CORE_UNREACHABLE",
        "message": "Core API 连续不可达超过 300 秒；仅停止观察，服务端任务未取消",
        "taskId": TASK_ID,
        "lastEventId": "event-9",
        "state": "running",
    }
    assert clock.now > 300.0
    assert max(clock.sleeps) == 10.0
    assert [call[0] for call in api.calls].count("SSE") == 1
    assert set(call[0] for call in api.calls) == {"GET", "SSE"}


def test_watch_ctrl_c_returns_130_without_cancelling_server_task() -> None:
    running = _status("running")
    api = WatchApi(
        snapshots=[running],
        streams=[
            [
                {"id": "event-7", "event": "progress", "data": {"step": 7}},
                KeyboardInterrupt(),
            ]
        ],
    )

    exit_code, frames, stderr = _invoke(api, FakeClock())

    assert exit_code == 130
    assert stderr == ""
    assert frames[-1] == {
        "type": "error",
        "error": {
            "code": "WATCH_INTERRUPTED",
            "message": "仅停止观察，服务端任务未取消",
            "taskId": TASK_ID,
            "lastEventId": "event-7",
        },
    }
    assert api.calls == [
        ("GET", TASK_PATH, {}),
        ("SSE", TASK_ID, {"lastEventId": None}),
    ]


def test_watch_rejects_caller_supplied_cursor_without_contacting_core() -> None:
    api = WatchApi(snapshots=[])

    exit_code, frames, _stderr = _invoke(
        api,
        FakeClock(),
        {"taskId": TASK_ID, "lastEventId": "stale-local-cursor"},
    )

    assert exit_code == 2
    assert frames[0]["error"]["code"] == "UNEXPECTED_FIELDS"
    assert api.calls == []
