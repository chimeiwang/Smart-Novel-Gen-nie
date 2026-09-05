"""短篇 V2 watcher 仍由 GET 决定结果，SSE 只提供观察和恢复游标。"""

import io
import json

import pytest
from inkforge_cli.api import SseConnectionError
from inkforge_cli.cli import run

from .test_cli import RecordingApi, dependencies


class WatchApi(RecordingApi):
    def __init__(self, states, streams=()):
        super().__init__(responses=list(states))
        self.streams = list(streams)

    def iter_sse(self, task_id, last_event_id=None):
        self.calls.append(("SSE", task_id, {"lastEventId": last_event_id}))
        for event in self.streams.pop(0) if self.streams else ():
            if isinstance(event, Exception):
                raise event
            yield event


def state(status="completed", operation="generate_outline", **changes):
    return {
        "engineVersion": 2,
        "workflow": "short_medium",
        "taskId": "task-1",
        "runId": "task-1",
        "operation": operation,
        "status": status,
        "activeSteps": [],
        "artifact": None,
        "error": None,
        "candidateVersionId": "candidate-exact"
        if status == "completed" and operation != "full_check"
        else None,
        "checkReport": {"text": "完整检查😀\r\n"}
        if status == "completed" and operation == "full_check"
        else None,
        **changes,
    }


def snapshot(sequence=4, status="running"):
    return {
        "id": sequence,
        "event": "run_snapshot",
        "data": {
            "engineVersion": 2,
            "runId": "task-1",
            "baseSequence": sequence,
            "snapshot": {"status": status, "lastEventSequence": sequence},
        },
    }


def invoke(api):
    stdout = io.StringIO()
    code = run(
        ["short.agent.watch"],
        stdin=io.StringIO('{"taskId":"task-1"}'),
        stdout=stdout,
        stderr=io.StringIO(),
        dependencies=dependencies(api),
    )
    return code, [json.loads(line) for line in stdout.getvalue().splitlines()]


@pytest.mark.parametrize(("status", "code"), [("completed", 0), ("failed", 5), ("cancelled", 5)])
def test_v2_status_not_v1_phase_decides_exit(status, code):
    authoritative = state(status, phase="completed", commandStatus="succeeded")
    api = WatchApi([authoritative])
    exit_code, frames = invoke(api)
    assert exit_code == code
    assert frames[-1] == {"type": "terminal", "data": authoritative}
    assert len([call for call in api.calls if call[0] == "GET"]) == 1


def test_numeric_snapshot_cursor_reconnects_and_completed_event_only_triggers_get():
    terminal = state()
    api = WatchApi(
        [state("running"), terminal],
        streams=[
            [snapshot(4), SseConnectionError("中断")],
            [
                {
                    "id": 5,
                    "event": "completed",
                    "data": {"engineVersion": 2, "resultId": "伪候选不得采用"},
                },
                AssertionError("终态事件后应先 GET，不继续等待流"),
            ],
        ],
    )
    code, frames = invoke(api)
    assert code == 0
    assert [call[2]["lastEventId"] for call in api.calls if call[0] == "SSE"] == [None, "4"]
    assert frames[0] == {"type": "event", **snapshot(4)}
    assert frames[-1] == {"type": "terminal", "data": terminal}
    assert frames[-1]["data"]["candidateVersionId"] == "candidate-exact"


def test_check_report_is_complete_get_text_and_no_candidate():
    report = "检查😀\r\n" * 20001 + "完整尾部🚀"
    terminal = state(operation="full_check", checkReport={"text": report})
    api = WatchApi([terminal], streams=[[snapshot(status="completed")]])
    code, frames = invoke(api)
    assert code == 0
    assert frames[-1]["data"]["checkReport"]["text"] == report
    assert frames[-1]["data"]["candidateVersionId"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"engineVersion": None},
        {"engineVersion": "2"},
        {"engineVersion": True},
        {"status": "waiting_user"},
        {"candidateVersionId": None},
        {"candidateVersionId": 3},
        {"activeSteps": None},
        {"runId": "other-run"},
        {"operation": "full_check", "candidateVersionId": None, "checkReport": None},
    ],
)
def test_invalid_v2_get_never_reports_success(changes):
    code, frames = invoke(WatchApi([state(**changes)]))
    assert code == 5
    assert frames[-1]["error"]["code"] == "CORE_RESPONSE_CONTRACT_ERROR"


def test_zero_snapshot_base_sequence_is_valid_reconnect_cursor():
    frame = snapshot(0)
    frame.pop("id")
    api = WatchApi([state("running"), state()], streams=[[frame, SseConnectionError("中断")], []])
    code, _ = invoke(api)
    assert code == 0
    assert [call[2]["lastEventId"] for call in api.calls if call[0] == "SSE"] == [None, "0"]
