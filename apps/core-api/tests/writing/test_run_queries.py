from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from inkforge_core.db.models import ReviewArtifact, WritingRunCommand, WritingTask
from inkforge_core.http.cursor import decode_run_cursor, encode_run_cursor
from inkforge_core.writing import run_queries as run_queries_module
from inkforge_core.writing.run_queries import (
    WritingRunQueryRepository,
    project_run_status,
)
from sqlalchemy.dialects import postgresql

NOW = datetime(2026, 8, 5, 12, 30)


def _task(
    task_id: str = "task-1",
    *,
    phase: str = "completed",
    graph: dict[str, object] | None = None,
    writing_session_id: str | None = None,
    created_at: datetime = NOW,
) -> WritingTask:
    return WritingTask(
        id=task_id,
        novelId="novel-1",
        chapterId="chapter-1",
        writingSessionId=writing_session_id,
        phase=phase,
        selectedAgents="写作,编辑",
        targetWordCount=4000,
        graphStateJson=json.dumps(graph, ensure_ascii=False) if graph else None,
        createdAt=created_at,
        updatedAt=created_at,
    )


def _command(
    command_id: str,
    *,
    kind: str = "start",
    operation: str = "review_chapter",
    result: dict[str, object] | None = None,
    created_at: datetime = NOW,
    task_id: str = "task-1",
    status: str = "succeeded",
    artifact_id: str | None = None,
    decision: str | None = None,
) -> WritingRunCommand:
    return WritingRunCommand(
        id=command_id,
        taskId=task_id,
        kind=kind,
        artifactId=artifact_id,
        decision=decision,
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
        status=status,
        attemptCount=0,
        nextAttemptAt=created_at,
        createdAt=created_at,
        updatedAt=created_at,
    )


def _artifact(
    *,
    kind: str = "beat_plan",
    status: str = "awaiting_user",
    revision: int = 1,
    updated_at: datetime = NOW,
) -> ReviewArtifact:
    return ReviewArtifact(
        id="artifact-1",
        taskId="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        artifactKey="chapter-artifact-1",
        kind=kind,
        status=status,
        payloadJson="{}",
        revision=revision,
        createdAt=NOW,
        updatedAt=updated_at,
    )


def _decision_command(
    decision: str,
    *,
    operation: str = "plan_chapter",
    result: dict[str, object] | None = None,
    created_at: datetime = NOW + timedelta(seconds=1),
) -> WritingRunCommand:
    command_id = f"decision-{decision}"
    command = _command(
        command_id,
        kind="artifact_decision",
        operation=operation,
        result=result
        if result is not None
        else {
            "artifactId": "artifact-1",
            "taskId": "task-1",
            "commandId": command_id,
            "decision": decision,
            "status": "pending",
            "savedCount": 1 if decision == "approve" else 0,
            "deleted": decision == "discard",
        },
        created_at=created_at,
        artifact_id="artifact-1",
        decision=decision,
    )
    command.payloadJson = json.dumps(
        {
            "_inkforgeCommand": {
                "schemaVersion": 1,
                "clientRequestId": f"decision-{decision}-request",
                "commandKind": "artifact_decision",
                "resourceIdentity": {"artifactId": "artifact-1"},
                "normalizedBody": {
                    "expectedRevision": 1,
                    "decision": decision,
                    "editedContent": None,
                    "selectedUpdateRefs": None,
                    "userMessage": None,
                },
                "requestFingerprint": "a" * 64,
            },
            "job": {
                "version": 1,
                "workflow": "long_serial",
                "chapterId": "chapter-1",
                "writingSessionId": "session-1",
                "operation": operation,
                "target": {"type": "chapter", "id": "chapter-1"},
                "scope": {"kind": "chapter", "chapterId": "chapter-1"},
                "sourceBindings": [
                    {
                        "resourceType": "chapter",
                        "resourceId": "chapter-1",
                        "exists": True,
                        "updatedAt": "2026-08-05T12:30:00Z",
                        "contentSha256": "b" * 64,
                        "revision": 1,
                        "absenceSentinel": None,
                    }
                ],
                "targetWordCount": 4000,
                "userInstruction": "规划本章",
                "resume": True,
                "resumeInput": {
                    "artifactId": "artifact-1",
                    "decision": decision,
                },
            },
        }
    )
    return command


class ScalarRows:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class ListQuerySession:
    def __init__(self, scalar_batches: list[list[object]]) -> None:
        self.scalar_batches = list(scalar_batches)
        self.statements: list[object] = []

    async def __aenter__(self) -> ListQuerySession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def scalars(self, statement: object) -> ScalarRows:
        self.statements.append(statement)
        if not self.scalar_batches:
            raise AssertionError("收到未预期的列表查询")
        return ScalarRows(self.scalar_batches.pop(0))


class ListQuerySessionFactory:
    def __init__(self, session: ListQuerySession) -> None:
        self.session = session

    def __call__(self) -> ListQuerySession:
        return self.session


def test_run_cursor_round_trips_created_at_and_id_only() -> None:
    created_at = datetime(2026, 8, 5, 12, 30, tzinfo=UTC)

    cursor = encode_run_cursor(created_at=created_at, task_id="task-1")

    assert decode_run_cursor(cursor) == (created_at, "task-1")


def test_run_cursor_normalizes_database_naive_utc_time() -> None:
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
    from inkforge_core.http.cursor import InvalidCursorError

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


def test_plan_projection_waits_only_on_an_authoritative_awaiting_artifact() -> None:
    status = project_run_status(
        _task(phase="awaiting_user_review"),
        commands=[_command("start-1", operation="plan_chapter")],
        artifacts=[_artifact()],
    )

    assert status.outcome.state == "waiting_user"
    assert status.activeArtifactId == "artifact-1"
    assert status.outcome.result.id == "artifact-1"


@pytest.mark.parametrize(
    ("artifact_status", "task_phase"),
    [
        ("awaiting_user", "completed"),
        ("applied", "completed"),
        ("applied", "awaiting_user_review"),
    ],
)
def test_plan_projection_rejects_artifact_lifecycle_without_matching_decision(
    artifact_status: str,
    task_phase: str,
) -> None:
    commands = [_command("start-1", operation="plan_chapter")]
    if task_phase == "awaiting_user_review":
        commands.append(_decision_command("approve"))

    status = project_run_status(
        _task(phase=task_phase),
        commands=commands,
        artifacts=[_artifact(status=artifact_status)],
    )

    assert status.outcome.state == "inconsistent"
    assert status.outcome.result.ready is False
    assert status.activeArtifactId is None


@pytest.mark.parametrize(
    ("operation", "artifact_kind"),
    [
        ("plan_chapter", "beat_plan"),
        ("write_chapter", "chapter_draft"),
    ],
)
def test_plan_and_write_projection_require_matching_approve_decision(
    operation: str,
    artifact_kind: str,
) -> None:
    status = project_run_status(
        _task(),
        commands=[
            _command("start-1", operation=operation),
            _decision_command("approve", operation=operation),
        ],
        artifacts=[_artifact(kind=artifact_kind, status="applied")],
    )

    assert status.outcome.state == "succeeded"
    assert status.outcome.result.ready is True
    assert status.outcome.result.id == "artifact-1"


def test_plan_projection_rejects_decision_result_identity_mismatch() -> None:
    decision = _decision_command(
        "approve",
        result={
            "artifactId": "artifact-1",
            "taskId": "task-other",
            "commandId": "decision-approve",
            "decision": "approve",
            "status": "pending",
            "savedCount": 1,
            "deleted": False,
        },
    )

    status = project_run_status(
        _task(),
        commands=[_command("start-1", operation="plan_chapter"), decision],
        artifacts=[_artifact(status="applied")],
    )

    assert status.outcome.state == "inconsistent"
    assert status.outcome.result.ready is False


def test_plan_projection_uses_persisted_discard_result_after_artifact_deletion() -> None:
    status = project_run_status(
        _task(),
        commands=[
            _command("start-1", operation="plan_chapter"),
            _decision_command("discard"),
        ],
        artifacts=[],
    )

    assert status.outcome.state == "succeeded"
    assert status.outcome.result.ready is True
    assert status.outcome.result.id == "artifact-1"


def test_plan_projection_rejects_discard_when_artifact_still_exists_with_wrong_kind() -> None:
    status = project_run_status(
        _task(),
        commands=[
            _command("start-1", operation="plan_chapter"),
            _decision_command("discard"),
        ],
        artifacts=[_artifact(kind="chapter_draft")],
    )

    assert status.outcome.state == "inconsistent"
    assert status.outcome.result.ready is False


def test_plan_projection_does_not_guess_between_multiple_artifacts() -> None:
    first = _artifact()
    second = _artifact()
    second.id = "artifact-2"
    second.artifactKey = "chapter-artifact-2"

    status = project_run_status(
        _task(phase="awaiting_user_review"),
        commands=[_command("start-1", operation="plan_chapter")],
        artifacts=[first, second],
    )

    assert status.outcome.state == "inconsistent"
    assert status.activeArtifactId is None


def test_plan_projection_uses_checkpoint_artifact_identity_when_multiple_exist() -> None:
    first = _artifact()
    second = _artifact()
    second.id = "artifact-2"
    second.artifactKey = "chapter-artifact-2"

    status = project_run_status(
        _task(
            phase="awaiting_user_review",
            graph={
                "eventSequence": 3,
                "phase": "waiting_user",
                "artifactReview": {"activeArtifactId": "artifact-1"},
            },
        ),
        commands=[_command("start-1", operation="plan_chapter")],
        artifacts=[first, second],
    )

    assert status.outcome.state == "waiting_user"
    assert status.activeArtifactId == "artifact-1"


def test_plan_projection_requires_a_new_awaiting_revision_after_revise() -> None:
    decision = _decision_command("revise")
    revised = _artifact(
        revision=2,
        updated_at=decision.createdAt + timedelta(milliseconds=1),
    )

    status = project_run_status(
        _task(phase="awaiting_user_review"),
        commands=[_command("start-1", operation="plan_chapter"), decision],
        artifacts=[revised],
    )

    assert status.outcome.state == "waiting_user"
    assert status.activeArtifactId == "artifact-1"
    assert status.outcome.result.id == "artifact-1"


def test_noop_cancel_after_effective_cancel_keeps_cancelled_outcome() -> None:
    effective_cancel = _command(
        "cancel-1",
        kind="cancel",
        result={"effective": True},
        created_at=NOW + timedelta(seconds=1),
    )
    noop_cancel = _command(
        "cancel-2",
        kind="cancel",
        result={
            "effective": False,
            "priorOutcome": {"currentCommand": {"id": "cancel-1"}},
        },
        created_at=NOW + timedelta(seconds=2),
    )

    status = project_run_status(
        _task(phase="error"),
        commands=[_command("start-1"), effective_cancel, noop_cancel],
        artifacts=[],
    )

    assert status.outcome.state == "cancelled"
    assert status.outcome.currentCommand is not None
    assert status.outcome.currentCommand.id == "cancel-2"


@pytest.mark.parametrize(
    ("command_status", "expected_outcome"),
    [("pending", "queued"), ("processing", "running")],
)
def test_fresh_active_command_is_not_recoverable_without_checkpoint(
    command_status: str,
    expected_outcome: str,
) -> None:
    status = project_run_status(
        _task(phase="active"),
        commands=[_command("start-1", status=command_status)],
        artifacts=[],
    )

    assert status.outcome.state == expected_outcome
    assert status.recoverable is False


def test_noop_cancel_preserves_prior_failure_error() -> None:
    failed = _command(
        "start-1",
        result={"code": "MODEL_FAILED", "message": "模型调用失败"},
        status="failed",
    )
    failed.lastError = "MODEL_FAILED"
    noop_cancel = _command(
        "cancel-1",
        kind="cancel",
        result={
            "effective": False,
            "priorOutcome": {"currentCommand": {"id": "start-1"}},
        },
        created_at=NOW + timedelta(seconds=1),
    )

    status = project_run_status(
        _task(phase="error"),
        commands=[failed, noop_cancel],
        artifacts=[],
    )

    assert status.outcome.state == "failed"
    assert status.error == {"code": "MODEL_FAILED", "message": "模型调用失败"}


@pytest.mark.asyncio
async def test_list_runs_enforces_owner_and_novel_and_keeps_tasks_without_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_queries_module, "_SCAN_BATCH_SIZE", 3)
    newer = _task("task-2", phase="active", created_at=NOW + timedelta(seconds=2))
    older = _task(
        "task-1",
        phase="active",
        writing_session_id="session-1",
        created_at=NOW + timedelta(seconds=1),
    )
    commands = [
        _command("start-2", task_id="task-2", status="pending"),
        _command("start-1", task_id="task-1", status="pending"),
    ]
    session = ListQuerySession([[newer, older], commands, []])
    repository = WritingRunQueryRepository(  # type: ignore[arg-type]
        ListQuerySessionFactory(session)
    )

    response = await repository.list_runs(
        "user-1",
        novel_id="novel-1",
        chapter_id=None,
        writing_session_id=None,
        operation=None,
        outcome=None,
        cursor=None,
        limit=10,
    )

    assert [item.taskId for item in response.items] == ["task-2", "task-1"]
    assert response.items[0].writingSessionId is None
    rendered = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert '"Novel"."userId" = \'user-1\'' in rendered
    assert '"WritingTask"."novelId" = \'novel-1\'' in rendered
    expected_order = (
        'ORDER BY public."WritingTask"."createdAt" DESC, '
        'public."WritingTask".id DESC'
    )
    assert expected_order in rendered


@pytest.mark.asyncio
async def test_list_runs_applies_direct_filters_and_strict_stable_cursor() -> None:
    cursor = encode_run_cursor(
        created_at=NOW + timedelta(seconds=5),
        task_id="task-cursor",
    )
    session = ListQuerySession([[]])
    repository = WritingRunQueryRepository(  # type: ignore[arg-type]
        ListQuerySessionFactory(session)
    )

    response = await repository.list_runs(
        "user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        writing_session_id="session-1",
        operation=None,
        outcome=None,
        cursor=cursor,
        limit=10,
    )

    assert response.items == []
    rendered = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert '"WritingTask"."chapterId" = \'chapter-1\'' in rendered
    assert '"WritingTask"."writingSessionId" = \'session-1\'' in rendered
    assert '"WritingTask"."createdAt" < \'2026-08-05 12:30:05\'' in rendered
    assert '"WritingTask".id < \'task-cursor\'' in rendered


@pytest.mark.asyncio
async def test_list_runs_scans_multiple_batches_for_derived_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_queries_module, "_SCAN_BATCH_SIZE", 2)
    review_tasks = [
        _task("task-4", phase="active", created_at=NOW + timedelta(seconds=4)),
        _task("task-3", phase="active", created_at=NOW + timedelta(seconds=3)),
    ]
    plan_tasks = [
        _task("task-2", phase="active", created_at=NOW + timedelta(seconds=2)),
        _task("task-1", phase="active", created_at=NOW + timedelta(seconds=1)),
    ]
    review_commands = [
        _command(
            f"start-{task.id}",
            task_id=task.id,
            operation="review_chapter",
            status="pending",
            created_at=task.createdAt,
        )
        for task in review_tasks
    ]
    plan_commands = [
        _command(
            f"start-{task.id}",
            task_id=task.id,
            operation="plan_chapter",
            status="pending",
            created_at=task.createdAt,
        )
        for task in plan_tasks
    ]
    session = ListQuerySession(
        [
            review_tasks,
            review_commands,
            [],
            plan_tasks,
            plan_commands,
            [],
        ]
    )
    repository = WritingRunQueryRepository(  # type: ignore[arg-type]
        ListQuerySessionFactory(session)
    )

    response = await repository.list_runs(
        "user-1",
        novel_id="novel-1",
        chapter_id=None,
        writing_session_id=None,
        operation="plan_chapter",
        outcome="queued",
        cursor=None,
        limit=1,
    )

    assert [item.taskId for item in response.items] == ["task-2"]
    assert response.nextCursor is not None
    assert decode_run_cursor(response.nextCursor)[1] == "task-2"
    assert len(session.statements) == 6
    entities = [
        statement.column_descriptions[0]["entity"]  # type: ignore[attr-defined]
        for statement in session.statements
    ]
    assert entities == [
        WritingTask,
        WritingRunCommand,
        ReviewArtifact,
        WritingTask,
        WritingRunCommand,
        ReviewArtifact,
    ]
    first_command_params = session.statements[1].compile().params  # type: ignore[attr-defined]
    second_command_params = session.statements[4].compile().params  # type: ignore[attr-defined]
    assert set(first_command_params["taskId_1"]) == {"task-4", "task-3"}
    assert set(second_command_params["taskId_1"]) == {"task-2", "task-1"}
