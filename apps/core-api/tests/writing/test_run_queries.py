from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from inkforge_core.db.models import ReviewArtifact, WritingRunCommand, WritingTask
from inkforge_core.writing.run_queries import project_run_status

NOW = datetime(2026, 8, 5, 12, 30)


def _task(*, phase: str = "completed", graph: dict[str, object] | None = None) -> WritingTask:
    return WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        writingSessionId=None,
        phase=phase,
        selectedAgents="写作,编辑",
        targetWordCount=4000,
        graphStateJson=json.dumps(graph, ensure_ascii=False) if graph else None,
        createdAt=NOW,
        updatedAt=NOW,
    )


def _command(
    command_id: str,
    *,
    kind: str = "start",
    operation: str = "review_chapter",
    result: dict[str, object] | None = None,
    created_at: datetime = NOW,
) -> WritingRunCommand:
    return WritingRunCommand(
        id=command_id,
        taskId="task-1",
        kind=kind,
        payloadJson=json.dumps(
            {
                "_inkforgeCommand": {"schemaVersion": 1},
                "job": {
                    "workflow": "long_serial",
                    "operation": operation,
                    "target": {"type": "chapter", "id": "chapter-1"},
                    "scope": {"kind": "chapter", "chapterId": "chapter-1"},
                },
            }
        ),
        resultJson=json.dumps(result) if result is not None else None,
        idempotencyKey=f"key-{command_id}",
        status="succeeded",
        attemptCount=0,
        nextAttemptAt=created_at,
        createdAt=created_at,
        updatedAt=created_at,
    )


def test_run_cursor_round_trips_created_at_and_id_only() -> None:
    from inkforge_core.http.cursor import decode_run_cursor, encode_run_cursor

    created_at = datetime(2026, 8, 5, 12, 30, tzinfo=UTC)

    cursor = encode_run_cursor(created_at=created_at, task_id="task-1")

    assert decode_run_cursor(cursor) == (created_at, "task-1")


def test_run_cursor_normalizes_database_naive_utc_time() -> None:
    from inkforge_core.http.cursor import decode_run_cursor, encode_run_cursor

    created_at = datetime(2026, 8, 5, 12, 30)

    cursor = encode_run_cursor(created_at=created_at, task_id="task-1")
    decoded_at, task_id = decode_run_cursor(cursor)

    assert decoded_at == created_at.replace(tzinfo=UTC)
    assert task_id == "task-1"


@pytest.mark.parametrize(
    "cursor",
    [
        "e30=",
        "eyJjcmVhdGVkQXQiOiIyMDI2LTA4LTA1VDEyOjMwOjAwWiJ9",
        "eyJjcmVhdGVkQXQiOiIyMDI2LTA4LTA1VDEyOjMwOjAwWiIsImlkIjoidCIsIngiOjF9",
    ],
)
def test_run_cursor_rejects_padding_missing_fields_and_extra_fields(cursor: str) -> None:
    from inkforge_core.http.cursor import InvalidCursorError, decode_run_cursor

    with pytest.raises(InvalidCursorError):
        decode_run_cursor(cursor)


def test_review_projection_keeps_complete_large_terminal_callback_report() -> None:
    report = "完整复审报告" * 14_001
    callback = {
        "_inkforgeTerminalCallbackResult": {"finalResponse": report}
    }

    status = project_run_status(
        _task(),
        commands=[_command("start-1", result=callback)],
        artifacts=[],
    )

    assert len(status.reviewReport or "") > 80_000
    assert status.reviewReport == report
    assert status.outcome.state == "succeeded"
    assert status.outcome.result.kind == "final_message"


def test_review_projection_does_not_expose_callback_result_before_terminal_success() -> None:
    command = _command(
        "start-1",
        result={
            "_inkforgeTerminalCallbackResult": {"finalResponse": "不应提前公开"}
        },
    )
    command.status = "processing"

    status = project_run_status(
        _task(phase="active"),
        commands=[command],
        artifacts=[],
    )

    assert status.reviewReport is None
    assert status.outcome.result.ready is False


def test_noop_cancel_chain_keeps_review_result_and_current_cancel() -> None:
    report = "复审结论"
    start = _command(
        "start-1",
        result={"_inkforgeTerminalCallbackResult": {"finalResponse": report}},
    )
    cancel_1 = _command(
        "cancel-1",
        kind="cancel",
        result={
            "effective": False,
            "priorOutcome": {"currentCommand": {"id": "start-1"}},
        },
        created_at=datetime(2026, 8, 5, 12, 31),
    )
    cancel_2 = _command(
        "cancel-2",
        kind="cancel",
        result={
            "effective": False,
            "priorOutcome": {"currentCommand": {"id": "cancel-1"}},
        },
        created_at=datetime(2026, 8, 5, 12, 32),
    )

    status = project_run_status(
        _task(),
        commands=[start, cancel_1, cancel_2],
        artifacts=[],
    )

    assert status.outcome.state == "succeeded"
    assert status.reviewReport == report
    assert status.outcome.currentCommand is not None
    assert status.outcome.currentCommand.id == "cancel-2"


def test_checkpoint_projection_whitelists_only_four_public_fields() -> None:
    task = _task(
        phase="active",
        graph={
            "eventSequence": 8,
            "phase": "writing",
            "operationStage": "drafting",
            "operationStep": "scene-2",
            "messages": ["不应公开"],
            "toolResults": {"secret": True},
        },
    )
    command = _command("start-1")
    command.status = "processing"

    status = project_run_status(task, commands=[command], artifacts=[])

    assert status.checkpoint is not None
    assert status.checkpoint.model_dump() == {
        "eventSequence": 8,
        "phase": "writing",
        "operationStage": "drafting",
        "operationStep": "scene-2",
    }


@pytest.mark.parametrize(
    ("artifact_status", "task_phase", "expected_outcome"),
    [
        ("awaiting_user", "awaiting_user_review", "waiting_user"),
        ("applied", "completed", "succeeded"),
    ],
)
def test_plan_projection_uses_authoritative_artifact_fact(
    artifact_status: str,
    task_phase: str,
    expected_outcome: str,
) -> None:
    artifact = ReviewArtifact(
        id="artifact-1",
        taskId="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        artifactKey="beat-plan-1",
        kind="beat_plan",
        status=artifact_status,
        payloadJson="{}",
        revision=1,
        createdAt=NOW,
        updatedAt=NOW,
    )

    status = project_run_status(
        _task(phase=task_phase),
        commands=[_command("start-1", operation="plan_chapter")],
        artifacts=[artifact],
    )

    assert status.outcome.state == expected_outcome
    assert status.outcome.result.id == "artifact-1"
