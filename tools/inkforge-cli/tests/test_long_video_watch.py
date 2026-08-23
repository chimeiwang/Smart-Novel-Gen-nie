from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Any

from inkforge_cli.api import BinaryResponse, CoreTransportError
from inkforge_cli.cli import run
from inkforge_cli.config import MemoryConfigStore, ProfileConfig
from inkforge_cli.credentials import MemoryCredentialStore
from inkforge_cli.runtime import CliDependencies


@dataclass
class FakeClock:
    now: float = 0.0
    interrupt_on_sleep: bool = False
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if self.interrupt_on_sleep:
            raise KeyboardInterrupt
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class WatchApi:
    snapshots: list[object]
    repeat_last: bool = False
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def request(self, method: str, path: str, **kwargs: Any) -> object:
        self.calls.append((method, path, kwargs))
        if self.snapshots:
            value = self.snapshots.pop(0)
            if self.repeat_last and not self.snapshots:
                self.snapshots.append(value)
        else:
            raise AssertionError("测试没有配置下一次改编快照")
        if isinstance(value, BaseException):
            raise value
        return value

    def request_bytes(self, method: str, path: str, **kwargs: Any) -> BinaryResponse:
        raise AssertionError("观察命令不应下载二进制")

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        raise AssertionError("观察命令不应登录")

    def iter_sse(self, task_id: str, last_event_id: str | None = None) -> Any:
        raise AssertionError("章节影视化观察命令没有公共 SSE")


def _snapshot(
    status: str,
    *,
    task_id: str = "task-1",
    checkpoint: str = "none",
    updated_at: str = "2026-08-23T00:00:00Z",
) -> dict[str, object]:
    return {
        "id": "adaptation-1",
        "state": "generating" if status not in {"completed", "failed"} else "failed",
        "latestTask": {
            "id": task_id,
            "status": status,
            "checkpointStage": checkpoint,
            "updatedAt": updated_at,
            "lastErrorCode": "MODEL_FAILED" if status == "failed" else None,
            "lastErrorMessage": "模型失败" if status == "failed" else None,
        },
    }


def _dependencies(api: WatchApi, clock: FakeClock) -> CliDependencies:
    config = MemoryConfigStore()
    config.save(
        "default",
        ProfileConfig(origin="http://127.0.0.1:8000", username="tester"),
    )
    credentials = MemoryCredentialStore()
    credentials.set("default", "http://127.0.0.1:8000", "session-cookie")

    def api_factory(origin: str, token: str | None = None) -> WatchApi:
        return api

    return CliDependencies(
        api_factory=api_factory,
        config_store=config,
        credential_store=credentials,
        getpass_fn=lambda prompt: "unused",
        stdin_isatty=lambda: False,
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )


def _invoke(api: WatchApi, clock: FakeClock) -> tuple[int, list[dict[str, Any]]]:
    stdout = io.StringIO()
    exit_code = run(
        ["long.video.adaptation.watch"],
        stdin=io.StringIO(
            json.dumps(
                {"adaptationId": "adaptation-1", "taskId": "task-1"},
                ensure_ascii=False,
            )
        ),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=_dependencies(api, clock),
    )
    return exit_code, [json.loads(line) for line in stdout.getvalue().splitlines()]


def test_video_watch_emits_snapshot_changed_progress_and_terminal() -> None:
    initial = _snapshot("pending")
    processing = _snapshot(
        "processing",
        checkpoint="dramatic_checkpoint",
        updated_at="2026-08-23T00:00:01Z",
    )
    completed = _snapshot(
        "completed",
        checkpoint="completed",
        updated_at="2026-08-23T00:00:02Z",
    )
    api = WatchApi([initial, processing, completed])
    clock = FakeClock()

    exit_code, frames = _invoke(api, clock)

    assert exit_code == 0
    assert frames == [
        {"type": "snapshot", "data": initial},
        {
            "type": "progress",
            "adaptationId": "adaptation-1",
            "taskId": "task-1",
            "data": processing["latestTask"],
        },
        {
            "type": "progress",
            "adaptationId": "adaptation-1",
            "taskId": "task-1",
            "data": completed["latestTask"],
        },
        {"type": "terminal", "data": completed},
    ]
    assert clock.sleeps == [0.5, 1.0]
    assert all(call[0] == "GET" for call in api.calls)


def test_video_watch_returns_failure_exit_code_from_authoritative_task_status() -> None:
    failed = _snapshot("failed")

    exit_code, frames = _invoke(WatchApi([failed]), FakeClock())

    assert exit_code == 5
    assert frames == [
        {"type": "snapshot", "data": failed},
        {"type": "terminal", "data": failed},
    ]


def test_video_watch_stops_when_latest_task_has_been_superseded() -> None:
    api = WatchApi([_snapshot("processing", task_id="task-2")])

    exit_code, frames = _invoke(api, FakeClock())

    assert exit_code == 5
    assert frames == [
        {
            "type": "error",
            "error": {
                "code": "VIDEO_TASK_SUPERSEDED",
                "message": "改编当前最新任务与目标 taskId 不一致；仅停止观察",
                "adaptationId": "adaptation-1",
                "taskId": "task-1",
                "latestTaskId": "task-2",
            },
        }
    ]


def test_video_watch_times_out_only_after_core_is_unreachable_for_300_seconds() -> None:
    api = WatchApi([CoreTransportError()], repeat_last=True)
    clock = FakeClock()

    exit_code, frames = _invoke(api, clock)

    assert exit_code == 5
    assert frames[-1]["error"]["code"] == "WATCH_CORE_UNREACHABLE"
    assert clock.now > 300
    assert max(clock.sleeps) == 10.0


def test_video_watch_ctrl_c_only_stops_observation() -> None:
    api = WatchApi([_snapshot("processing")])
    clock = FakeClock(interrupt_on_sleep=True)

    exit_code, frames = _invoke(api, clock)

    assert exit_code == 130
    assert frames[0]["type"] == "snapshot"
    assert frames[-1] == {
        "type": "error",
        "error": {
            "code": "WATCH_INTERRUPTED",
            "message": "仅停止观察，服务端任务未取消",
            "adaptationId": "adaptation-1",
            "taskId": "task-1",
        },
    }
