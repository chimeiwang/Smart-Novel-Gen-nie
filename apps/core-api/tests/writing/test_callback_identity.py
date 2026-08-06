from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_contracts.events import (
    AgentEvent,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from inkforge_core.db.models import (
    ReviewArtifact,
    WritingEventOutbox,
    WritingRunCommand,
    WritingTask,
)
from inkforge_core.errors import ApiError
from inkforge_core.writing.job_identity import build_writing_job_id
from inkforge_core.writing.outbox import BoundaryEvent
from inkforge_core.writing.sse import InMemoryWritingEventStore
from inkforge_core.writing.tasks import (
    CallbackAcceptance,
    WritingCallbackService,
    WritingTaskRepository,
)


def _task(*, sequence: int = 20) -> WritingTask:
    now = datetime.now(UTC).replace(tzinfo=None)
    return WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="awaiting_user_review",
        selectedAgents="写作,编辑",
        targetWordCount=4000,
        graphStateJson=json.dumps(
            {
                "taskId": "task-1",
                "userId": "user-1",
                "novelId": "novel-1",
                "chapterId": "chapter-1",
                "targetWordCount": 4000,
                "conversationHistory": [],
                "phase": "awaiting_user_review",
                "eventSequence": sequence,
            },
            ensure_ascii=False,
        ),
        createdAt=now,
        updatedAt=now,
    )


def _command(command_id: str, status: str) -> WritingRunCommand:
    now = datetime.now(UTC).replace(tzinfo=None)
    return WritingRunCommand(
        id=command_id,
        taskId="task-1",
        kind="resume",
        payloadJson='{"version":1,"resume":true}',
        idempotencyKey=f"user-1:{command_id}",
        status=status,
        attemptCount=0,
        nextAttemptAt=now,
        createdAt=now,
        updatedAt=now,
    )


class CallbackSession:
    def __init__(
        self,
        task: WritingTask,
        commands: dict[str, WritingRunCommand],
        *,
        active_command_id: str | None,
        latest_command_id: str | None = None,
        outbox_rows: list[WritingEventOutbox] | None = None,
    ) -> None:
        self.task = task
        self.commands = commands
        self.active_command_id = active_command_id
        self.latest_command_id = latest_command_id
        self.outbox_rows = outbox_rows or []
        self.added: list[object] = []

    async def __aenter__(self) -> CallbackSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield

    async def get(
        self,
        model: type[object],
        identifier: str,
        *,
        with_for_update: bool = False,
    ) -> object | None:
        assert with_for_update is True
        if model is WritingTask:
            return self.task if identifier == self.task.id else None
        if model is WritingRunCommand:
            return self.commands.get(identifier)
        raise AssertionError(model)

    async def scalar(self, statement: object) -> object | None:
        query = str(statement)
        if '"WritingEventOutbox"' in query:
            return self.outbox_rows[0] if self.outbox_rows else None
        if "status" in query and "IN" in query:
            return self.active_command_id
        return self.latest_command_id

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, WritingEventOutbox):
            self.outbox_rows.append(value)

    async def execute(self, statement: object) -> None:
        del statement

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("callback", ["event", "checkpoint", "complete", "fail"])
async def test_old_job_callback_never_mutates_new_active_command(callback: str) -> None:
    task = _task()
    original_snapshot = task.graphStateJson
    old_command = _command("command-a", "succeeded")
    new_command = _command("command-b", "processing")
    session = CallbackSession(
        task,
        {old_command.id: old_command, new_command.id: new_command},
        active_command_id=new_command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    if callback == "event":
        acceptance = await repository.mark_command_processing(
            task.id, old_command.id, 21
        )
    elif callback == "checkpoint":
        acceptance = await repository.save_checkpoint(
            task.id,
            old_command.id,
            json.dumps({"eventSequence": 21}),
            "active",
            21,
        )
    elif callback == "complete":
        acceptance = await repository.complete_with_message_and_command(
            task.id,
            old_command.id,
            {"finalResponse": "旧结果"},
            "",
            21,
        )
    else:
        acceptance = await repository.fail_with_command(
            task.id,
            old_command.id,
            "OLD_JOB_FAILED",
            21,
        )

    assert acceptance.accepted is False
    assert task.graphStateJson == original_snapshot
    assert task.phase == "awaiting_user_review"
    assert new_command.status == "processing"
    assert old_command.status == "succeeded"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_status", ["pending", "succeeded"])
@pytest.mark.parametrize("callback", ["event", "checkpoint", "complete", "fail"])
async def test_cancelled_job_callbacks_are_rejected_without_side_effects(
    cancel_status: str,
    callback: str,
) -> None:
    task = _task()
    task.phase = "active" if cancel_status == "pending" else "error"
    old_command = _command("command-cancelled", "failed")
    old_command.lastError = "WRITING_RUN_CANCELLED_BY_USER"
    cancel_command = _command("command-cancel", cancel_status)
    cancel_command.kind = "cancel"
    cancel_command.resultJson = (
        None if cancel_status == "pending" else json.dumps({"effective": True})
    )
    artifact = ReviewArtifact(
        id="artifact-1",
        novelId=task.novelId,
        chapterId=task.chapterId,
        taskId=task.id,
        kind="chapter_draft",
        status="draft",
        payloadJson=json.dumps({"kind": "chapter_draft", "content": "原草案"}),
        revision=1,
    )
    session = CallbackSession(
        task,
        {old_command.id: old_command, cancel_command.id: cancel_command},
        active_command_id=(cancel_command.id if cancel_status == "pending" else None),
        latest_command_id=cancel_command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    store = InMemoryWritingEventStore()
    service = WritingCallbackService(repository, store)
    original_task = (
        task.graphStateJson,
        task.phase,
        task.finalContent,
        task.agentOutputs,
    )
    original_artifact = (
        artifact.status,
        artifact.payloadJson,
        artifact.revision,
        artifact.appliedAt,
    )
    original_cancel = (
        cancel_command.status,
        cancel_command.resultJson,
        cancel_command.completedAt,
        cancel_command.lastError,
    )
    occurred_at = datetime.now(UTC)

    if callback == "event":
        receipt = await service.accept_event(
            AgentEvent(
                protocolVersion="1.1",
                eventId="event-late",
                jobId=old_command.id,
                runId=task.id,
                taskId=task.id,
                sequence=21,
                event="agent_start",
                data={},
                occurredAt=occurred_at,
            )
        )
    elif callback == "checkpoint":
        receipt = await service.save_checkpoint(
            CheckpointCallback(
                protocolVersion="1.1",
                eventId="checkpoint-late",
                jobId=old_command.id,
                runId=task.id,
                taskId=task.id,
                sequence=21,
                checkpoint=_checkpoint(21),
                occurredAt=occurred_at,
            ),
            user_id="user-1",
            novel_id=task.novelId,
        )
    elif callback == "complete":
        receipt = await service.complete(
            RunCompletionCallback(
                protocolVersion="1.1",
                eventId="complete-late",
                jobId=old_command.id,
                runId=task.id,
                taskId=task.id,
                sequence=21,
                result={"finalResponse": "迟到正文"},
                occurredAt=occurred_at,
            )
        )
    else:
        receipt = await service.fail(
            RunFailureCallback(
                protocolVersion="1.1",
                eventId="fail-late",
                jobId=old_command.id,
                runId=task.id,
                taskId=task.id,
                sequence=21,
                code="LATE_FAILURE",
                message="迟到失败",
                recoverable=False,
                occurredAt=occurred_at,
            )
        )

    assert receipt.disposition == "rejected"
    assert receipt.reasonCode == "WRITING_JOB_MISMATCH"
    assert (task.graphStateJson, task.phase, task.finalContent, task.agentOutputs) == (
        original_task
    )
    assert (
        artifact.status,
        artifact.payloadJson,
        artifact.revision,
        artifact.appliedAt,
    ) == original_artifact
    assert (
        cancel_command.status,
        cancel_command.resultJson,
        cancel_command.completedAt,
        cancel_command.lastError,
    ) == original_cancel
    assert session.added == []
    assert await store.replay(task.id, None) == []


@pytest.mark.asyncio
async def test_checkpoint_sequence_cannot_move_persisted_snapshot_backwards() -> None:
    task = _task(sequence=20)
    original_snapshot = task.graphStateJson
    command = _command("command-current", "processing")
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    acceptance = await repository.save_checkpoint(
        task.id,
        command.id,
        json.dumps({"eventSequence": 10}),
        "active",
        10,
    )

    assert acceptance.accepted is False
    assert task.graphStateJson == original_snapshot
    assert command.status == "processing"


@pytest.mark.asyncio
async def test_waiting_checkpoint_and_outbox_share_one_repository_transaction() -> None:
    task = _task(sequence=20)
    task.phase = "active"
    command = _command("command-current", "processing")
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    checkpoint = _checkpoint(21)
    boundary = BoundaryEvent(
        source_event_id="event-21",
        source_sequence=21,
        dedupe_key="writing:command-current:waiting:21",
        event_type="artifact_awaiting_user_approval",
        payload={"taskId": task.id},
    )

    acceptance = await repository.save_checkpoint(
        task.id,
        command.id,
        json.dumps(checkpoint, ensure_ascii=False),
        "awaiting_user_review",
        21,
        boundary,
    )

    outbox_rows = [
        value for value in session.added if isinstance(value, WritingEventOutbox)
    ]
    assert acceptance.accepted is True
    assert acceptance.task_phase == "awaiting_user_review"
    assert acceptance.command_status == "succeeded"
    assert acceptance.outbox_event_id == outbox_rows[0].id
    assert task.phase == "awaiting_user_review"
    assert command.status == "succeeded"
    assert outbox_rows[0].taskId == task.id
    assert outbox_rows[0].commandId == command.id
    assert outbox_rows[0].durableBaseline == 20


@pytest.mark.asyncio
async def test_waiting_checkpoint_replay_reuses_original_outbox_baseline() -> None:
    checkpoint = _checkpoint(21)
    task = _task(sequence=21)
    task.phase = "awaiting_user_review"
    task.graphStateJson = json.dumps(checkpoint, ensure_ascii=False)
    command = _command("command-current", "succeeded")
    existing = WritingEventOutbox(
        id="outbox-waiting",
        taskId=task.id,
        commandId=command.id,
        sourceEventId="event-21",
        sourceSequence=21,
        durableBaseline=20,
        dedupeKey="writing:command-current:waiting:21",
        eventType="artifact_awaiting_user_approval",
        payloadJson=json.dumps(
            {"taskId": task.id},
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=None,
        latest_command_id=command.id,
        outbox_rows=[existing],
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    boundary = BoundaryEvent(
        source_event_id="event-21",
        source_sequence=21,
        dedupe_key="writing:command-current:waiting:21",
        event_type="artifact_awaiting_user_approval",
        payload={"taskId": task.id},
    )

    acceptance = await repository.save_checkpoint(
        task.id,
        command.id,
        json.dumps(checkpoint, ensure_ascii=False),
        "awaiting_user_review",
        21,
        boundary,
    )

    assert acceptance.accepted is True
    assert acceptance.already_applied is True
    assert acceptance.outbox_event_id == existing.id
    assert existing.durableBaseline == 20


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["complete", "fail"])
async def test_terminal_outbox_uses_locked_snapshot_baseline(terminal: str) -> None:
    task = _task(sequence=20)
    task.phase = "active"
    command = _command("command-current", "processing")
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    boundary = BoundaryEvent(
        source_event_id=f"event-{terminal}-22",
        source_sequence=22,
        dedupe_key=f"writing:{command.id}:terminal",
        event_type="completed" if terminal == "complete" else "error",
        payload={"taskId": task.id},
    )

    if terminal == "complete":
        acceptance = await repository.complete_with_message_and_command(
            task.id,
            command.id,
            {"finalResponse": "完成"},
            "完成",
            22,
            boundary,
        )
    else:
        acceptance = await repository.fail_with_command(
            task.id,
            command.id,
            "AGENT_RUN_FAILED",
            22,
            boundary,
        )

    row = next(
        value for value in session.added if isinstance(value, WritingEventOutbox)
    )
    assert acceptance.accepted is True
    assert row.sourceSequence == 22
    assert row.durableBaseline == 20


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot_phase", ["completed", "error"])
async def test_terminal_snapshot_does_not_make_task_terminal_before_callback(
    snapshot_phase: str,
) -> None:
    task = _task(sequence=20)
    task.phase = "active"
    command = _command("command-current", "processing")
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    checkpoint = _checkpoint(21)
    checkpoint["phase"] = snapshot_phase

    acceptance = await repository.save_checkpoint(
        task.id,
        command.id,
        json.dumps(checkpoint, ensure_ascii=False),
        snapshot_phase,
        21,
    )

    assert acceptance.accepted is True
    assert json.loads(task.graphStateJson or "{}")["phase"] == snapshot_phase
    assert task.phase == "active"
    assert command.status == "processing"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_status", "stored_result", "incoming_result", "failure_code"),
    [
        (
            "succeeded",
            {"finalResponse": "第一次结果"},
            {"finalResponse": "被篡改的结果"},
            None,
        ),
        (
            "succeeded",
            {"finalResponse": "第一次结果"},
            {},
            None,
        ),
        ("failed", {"code": "FIRST_FAILURE"}, None, "OTHER_FAILURE"),
    ],
)
async def test_terminal_retry_with_different_business_result_is_rejected(
    stored_status: str,
    stored_result: dict[str, Any],
    incoming_result: dict[str, Any] | None,
    failure_code: str | None,
) -> None:
    task = _task(sequence=20)
    task.phase = "completed" if stored_status == "succeeded" else "error"
    command = _command("command-current", stored_status)
    command.resultJson = json.dumps(stored_result, ensure_ascii=False)
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=None,
        latest_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    if incoming_result is not None:
        acceptance = await repository.complete_with_message_and_command(
            task.id,
            command.id,
            incoming_result,
            str(incoming_result.get("finalResponse", "")),
            21,
        )
    else:
        assert failure_code is not None
        acceptance = await repository.fail_with_command(
            task.id,
            command.id,
            failure_code,
            21,
        )

    assert acceptance.accepted is False
    assert acceptance.rejection_code == "WRITING_CALLBACK_RESULT_CONFLICT"
    assert command.resultJson == json.dumps(stored_result, ensure_ascii=False)


@pytest.mark.asyncio
async def test_short_medium_exact_completion_replay_ignores_only_core_enrichment() -> None:
    task = _task(sequence=20)
    task.phase = "completed"
    command = _command("command-current", "succeeded")
    command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "generate_manuscript",
        }
    )
    command.resultJson = json.dumps(
        {
            "resultType": "short_medium_document",
            "content": "正文",
            "candidateVersionId": "candidate-1",
        },
        ensure_ascii=False,
    )
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=None,
        latest_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    acceptance = await repository.complete_with_message_and_command(
        task.id,
        command.id,
        {
            "resultType": "short_medium_document",
            "content": "正文",
        },
        "",
        21,
    )

    assert acceptance.accepted is True
    assert acceptance.already_applied is True


@pytest.mark.asyncio
async def test_terminal_outbox_identity_conflict_returns_rejection() -> None:
    task = _task(sequence=20)
    task.phase = "completed"
    command = _command("command-current", "succeeded")
    command.resultJson = json.dumps({"finalResponse": "完成"}, ensure_ascii=False)
    existing = WritingEventOutbox(
        id="outbox-existing",
        taskId=task.id,
        commandId=command.id,
        sourceEventId="event-original",
        sourceSequence=21,
        durableBaseline=20,
        dedupeKey=f"writing:{command.id}:terminal",
        eventType="completed",
        payloadJson=json.dumps({"taskId": task.id}, separators=(",", ":")),
    )
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=None,
        latest_command_id=command.id,
        outbox_rows=[existing],
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    conflicting_boundary = BoundaryEvent(
        source_event_id="event-conflict",
        source_sequence=21,
        dedupe_key=f"writing:{command.id}:terminal",
        event_type="completed",
        payload={"taskId": task.id},
    )

    acceptance = await repository.complete_with_message_and_command(
        task.id,
        command.id,
        {"finalResponse": "完成"},
        "完成",
        21,
        conflicting_boundary,
    )

    assert acceptance.accepted is False
    assert acceptance.rejection_code == "WRITING_OUTBOX_BOUNDARY_CONFLICT"
    assert acceptance.outbox_event_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("command_kind", ["resume", "artifact_decision"])
async def test_exact_completion_replay_returns_existing_outbox(
    command_kind: str,
) -> None:
    task = _task(sequence=20)
    task.phase = "completed"
    task.finalContent = "完成"
    command = _command("command-current", "succeeded")
    command.kind = command_kind
    command.resultJson = json.dumps(
        {"finalResponse": "完成"}
        if command_kind == "resume"
        else {"artifactId": "artifact-1", "accepted": True},
        ensure_ascii=False,
    )
    existing = WritingEventOutbox(
        id="outbox-completed",
        taskId=task.id,
        commandId=command.id,
        sourceEventId="event-complete-21",
        sourceSequence=21,
        durableBaseline=20,
        dedupeKey=f"writing:{command.id}:terminal",
        eventType="completed",
        payloadJson=json.dumps(
            {"taskId": task.id},
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=None,
        latest_command_id=command.id,
        outbox_rows=[existing],
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    boundary = BoundaryEvent(
        source_event_id="event-complete-21",
        source_sequence=21,
        dedupe_key=f"writing:{command.id}:terminal",
        event_type="completed",
        payload={"taskId": task.id},
    )

    acceptance = await repository.complete_with_message_and_command(
        task.id,
        command.id,
        {"finalResponse": "完成"},
        "完成",
        21,
        boundary,
    )

    assert acceptance.accepted is True
    assert acceptance.already_applied is True
    assert acceptance.outbox_event_id == existing.id


@pytest.mark.asyncio
async def test_artifact_decision_persists_terminal_callback_identity() -> None:
    task = _task(sequence=20)
    task.phase = "active"
    command = _command("command-current", "processing")
    command.kind = "artifact_decision"
    command.resultJson = json.dumps(
        {"artifactId": "artifact-1", "accepted": True},
        ensure_ascii=False,
    )
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
        latest_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    first = await repository.complete_with_message_and_command(
        task.id,
        command.id,
        {"finalResponse": "完成"},
        "完成",
        21,
    )
    session.active_command_id = None
    changed = await repository.complete_with_message_and_command(
        task.id,
        command.id,
        {},
        "",
        22,
    )

    assert first.accepted is True
    assert changed.accepted is False
    assert changed.rejection_code == "WRITING_CALLBACK_RESULT_CONFLICT"


@pytest.mark.asyncio
async def test_legacy_completion_rejects_missing_persisted_final_content() -> None:
    task = _task(sequence=20)
    task.phase = "completed"
    task.finalContent = "完成"
    legacy_job_id = build_writing_job_id(
        task.id,
        resume=True,
        graph_state_json=task.graphStateJson,
    )
    session = CallbackSession(
        task,
        {},
        active_command_id=None,
        latest_command_id=None,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    acceptance = await repository.complete_with_message_and_command(
        task.id,
        legacy_job_id,
        {},
        "",
        21,
    )

    assert acceptance.accepted is False
    assert acceptance.rejection_code == "WRITING_CALLBACK_RESULT_CONFLICT"


@pytest.mark.asyncio
async def test_legacy_completion_rejects_unverifiable_extra_result_fields() -> None:
    task = _task(sequence=20)
    task.phase = "completed"
    task.finalContent = "完成"
    legacy_job_id = build_writing_job_id(
        task.id,
        resume=True,
        graph_state_json=task.graphStateJson,
    )
    session = CallbackSession(
        task,
        {},
        active_command_id=None,
        latest_command_id=None,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    acceptance = await repository.complete_with_message_and_command(
        task.id,
        legacy_job_id,
        {"finalResponse": "完成", "extra": "无法从历史任务核验"},
        "完成",
        21,
    )

    assert acceptance.accepted is False
    assert acceptance.rejection_code == "WRITING_CALLBACK_RESULT_CONFLICT"


@pytest.mark.asyncio
async def test_checkpoint_cannot_self_report_short_workflow_for_long_command() -> None:
    task = _task(sequence=20)
    task.phase = "active"
    command = _command("command-current", "processing")
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    with pytest.raises(ApiError) as error:
        await repository.save_checkpoint(
            task.id,
            command.id,
            json.dumps(
                {
                    "workflow": "short_medium",
                    "operation": "generate_outline",
                    "phase": "generating",
                    "eventSequence": 21,
                }
            ),
            "active",
            21,
        )

    assert error.value.code == "WRITING_CHECKPOINT_COMMAND_MISMATCH"
    assert task.phase == "active"


@pytest.mark.asyncio
async def test_short_checkpoint_operation_must_match_locked_command() -> None:
    task = _task(sequence=20)
    task.phase = "active"
    command = _command("command-current", "processing")
    command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "generate_outline",
            "documentType": "outline",
        }
    )
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    with pytest.raises(ApiError) as error:
        await repository.save_checkpoint(
            task.id,
            command.id,
            json.dumps(
                {
                    "workflow": "short_medium",
                    "operation": "generate_manuscript",
                    "phase": "generating",
                    "eventSequence": 21,
                }
            ),
            "active",
            21,
        )

    assert error.value.code == "WRITING_CHECKPOINT_COMMAND_MISMATCH"
    assert task.phase == "active"


@pytest.mark.asyncio
async def test_short_medium_completion_finalizes_candidate_and_terminal_state_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(sequence=20)
    task.phase = "active"
    command = _command("command-current", "processing")
    command.payloadJson = json.dumps(
        {"workflow": "short_medium", "operation": "generate_outline"}
    )
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    finalized_with: list[object] = []

    async def finalize(
        received_session: object,
        received_task: WritingTask,
        received_command: WritingRunCommand,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        finalized_with.extend(
            [received_session, received_task, received_command, result]
        )
        return {**result, "candidateVersionId": "candidate-1"}

    monkeypatch.setattr(
        "inkforge_core.writing.tasks.finalize_short_medium_completion",
        finalize,
    )

    acceptance = await repository.complete_with_message_and_command(
        task.id,
        command.id,
        {"resultType": "short_medium_document"},
        "",
        21,
    )

    assert acceptance.accepted is True
    assert finalized_with[:3] == [session, task, command]
    assert task.phase == "completed"
    assert command.status == "succeeded"
    assert json.loads(command.resultJson or "{}")["candidateVersionId"] == "candidate-1"


@pytest.mark.asyncio
async def test_short_medium_finalize_failure_leaves_task_and_command_non_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(sequence=20)
    task.phase = "active"
    command = _command("command-current", "processing")
    command.payloadJson = json.dumps(
        {"workflow": "short_medium", "operation": "generate_outline"}
    )
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    async def reject(*args: object, **kwargs: object) -> dict[str, Any]:
        del args, kwargs
        raise ApiError(
            status_code=409,
            code="SHORT_MEDIUM_BASE_VERSION_CONFLICT",
            message="基础版本冲突",
        )

    monkeypatch.setattr(
        "inkforge_core.writing.tasks.finalize_short_medium_completion",
        reject,
    )

    with pytest.raises(ApiError, match="基础版本冲突"):
        await repository.complete_with_message_and_command(
            task.id,
            command.id,
            {"resultType": "short_medium_document"},
            "",
            21,
        )

    assert task.phase == "active"
    assert command.status == "processing"
    assert command.resultJson is None


@pytest.mark.asyncio
async def test_only_latest_terminal_command_can_retry_callback() -> None:
    task = _task(sequence=20)
    task.phase = "completed"
    old_command = _command("command-old", "succeeded")
    latest_command = _command("command-latest", "succeeded")
    session = CallbackSession(
        task,
        {old_command.id: old_command, latest_command.id: latest_command},
        active_command_id=None,
        latest_command_id=latest_command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    old_authorization = await repository.authorize_callback(task.id, old_command.id)
    latest_authorization = await repository.authorize_callback(
        task.id,
        latest_command.id,
    )

    assert old_authorization.accepted is False
    assert latest_authorization.accepted is True
    assert latest_authorization.already_applied is True


@pytest.mark.asyncio
async def test_legacy_callback_is_rejected_after_any_persisted_command_exists() -> None:
    task = _task(sequence=20)
    snapshot = json.loads(task.graphStateJson or "{}")
    snapshot["callbackJobId"] = "writing-legacy"
    task.graphStateJson = json.dumps(snapshot, ensure_ascii=False)
    command = _command("command-latest", "failed")
    session = CallbackSession(
        task,
        {command.id: command},
        active_command_id=None,
        latest_command_id=command.id,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    authorization = await repository.authorize_callback(task.id, "writing-legacy")

    assert authorization.accepted is False


@pytest.mark.asyncio
async def test_legacy_job_identity_survives_its_first_checkpoint() -> None:
    task = _task(sequence=0)
    task.graphStateJson = None
    task.phase = "active"
    legacy_job_id = build_writing_job_id(
        task.id,
        resume=False,
        graph_state_json=None,
    )
    session = CallbackSession(task, {}, active_command_id=None)
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    checkpoint = _checkpoint(1)
    checkpoint["callbackJobId"] = legacy_job_id

    saved = await repository.save_checkpoint(
        task.id,
        legacy_job_id,
        json.dumps(checkpoint, ensure_ascii=False),
        "active",
        1,
    )
    authorized = await repository.authorize_callback(task.id, legacy_job_id)
    reconciled_job_id = build_writing_job_id(
        task.id,
        resume=True,
        graph_state_json=task.graphStateJson,
    )
    reconciled = await repository.authorize_callback(task.id, reconciled_job_id)
    wrong_job = await repository.authorize_callback(task.id, "writing-wrong")

    assert saved.accepted is True
    assert authorized.accepted is True
    assert reconciled.accepted is False
    assert wrong_job.accepted is False


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["complete", "fail"])
async def test_anchored_legacy_job_finishes_after_terminal_checkpoint(
    outcome: str,
) -> None:
    task = _task(sequence=20)
    task.phase = "active"
    legacy_job_id = build_writing_job_id(
        task.id,
        resume=True,
        graph_state_json=task.graphStateJson,
    )
    snapshot = json.loads(task.graphStateJson or "{}")
    snapshot["callbackJobId"] = legacy_job_id
    task.graphStateJson = json.dumps(snapshot, ensure_ascii=False)
    session = CallbackSession(task, {}, active_command_id=None)
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]
    store = InMemoryWritingEventStore()
    service = WritingCallbackService(repository, store)
    terminal_phase = "completed" if outcome == "complete" else "error"
    checkpoint = _checkpoint(21)
    checkpoint["phase"] = terminal_phase

    await service.save_checkpoint(
        CheckpointCallback(
            protocolVersion="1.1",
            eventId="event-21",
            jobId=legacy_job_id,
            runId=task.id,
            taskId=task.id,
            sequence=21,
            checkpoint=checkpoint,
            occurredAt=datetime.now(UTC),
        ),
        user_id="user-1",
        novel_id="novel-1",
    )
    if outcome == "complete":
        await service.complete(
            RunCompletionCallback(
                protocolVersion="1.1",
                eventId="event-22",
                jobId=legacy_job_id,
                runId=task.id,
                taskId=task.id,
                sequence=22,
                result={"finalResponse": "最终正文"},
                occurredAt=datetime.now(UTC),
            )
        )
    else:
        await service.fail(
            RunFailureCallback(
                protocolVersion="1.1",
                eventId="event-22",
                jobId=legacy_job_id,
                runId=task.id,
                taskId=task.id,
                sequence=22,
                code="AGENT_RUN_FAILED",
                message="运行失败",
                recoverable=True,
                occurredAt=datetime.now(UTC),
            )
        )

    events = await store.replay(task.id, None)
    assert [event.event for event in events] == ["checkpoint"]
    assert any(isinstance(value, WritingEventOutbox) for value in session.added)
    assert task.phase == terminal_phase
    if outcome == "complete":
        assert task.finalContent == "最终正文"


def _checkpoint(sequence: object = 21) -> dict[str, Any]:
    return {
        "taskId": "task-1",
        "userId": "user-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "targetWordCount": 4000,
        "conversationHistory": [],
        "phase": "awaiting_user_review",
        "eventSequence": sequence,
    }


class AcceptingRepository:
    def __init__(self) -> None:
        self.saved = False
        self.serialized: str | None = None

    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        del task_id, job_id
        return CallbackAcceptance(True, 20)

    async def save_checkpoint(self, *args: object) -> CallbackAcceptance:
        self.serialized = str(args[2])
        self.saved = True
        return CallbackAcceptance(True, 20)


@pytest.mark.asyncio
async def test_checkpoint_persists_callback_job_identity() -> None:
    repository = AcceptingRepository()
    service = WritingCallbackService(
        repository,  # type: ignore[arg-type]
        InMemoryWritingEventStore(),
    )

    await service.save_checkpoint(
        CheckpointCallback(
            protocolVersion="1.1",
            eventId="event-21",
            jobId="command-current",
            runId="task-1",
            taskId="task-1",
            sequence=21,
            checkpoint=_checkpoint(21),
            occurredAt=datetime.now(UTC),
        ),
        user_id="user-1",
        novel_id="novel-1",
    )

    assert repository.serialized is not None
    assert json.loads(repository.serialized)["callbackJobId"] == "command-current"


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint_sequence", [None, True, -1])
async def test_checkpoint_rejects_missing_bool_or_negative_sequence(
    checkpoint_sequence: object,
) -> None:
    repository = AcceptingRepository()
    service = WritingCallbackService(
        repository,  # type: ignore[arg-type]
        InMemoryWritingEventStore(),
    )
    checkpoint = _checkpoint(checkpoint_sequence)
    if checkpoint_sequence is None:
        checkpoint.pop("eventSequence")

    with pytest.raises(ApiError) as captured:
        await service.save_checkpoint(
            CheckpointCallback(
                protocolVersion="1.1",
                eventId="event-21",
                jobId="command-current",
                runId="task-1",
                taskId="task-1",
                sequence=21,
                checkpoint=checkpoint,
                occurredAt=datetime.now(UTC),
            ),
            user_id="user-1",
            novel_id="novel-1",
        )

    assert captured.value.code == "WRITING_CHECKPOINT_SEQUENCE_INVALID"
    assert repository.saved is False


@pytest.mark.asyncio
async def test_checkpoint_sequence_must_match_callback_sequence() -> None:
    repository = AcceptingRepository()
    service = WritingCallbackService(
        repository,  # type: ignore[arg-type]
        InMemoryWritingEventStore(),
    )

    with pytest.raises(ApiError) as captured:
        await service.save_checkpoint(
            CheckpointCallback(
                protocolVersion="1.1",
                eventId="event-21",
                jobId="command-current",
                runId="task-1",
                taskId="task-1",
                sequence=21,
                checkpoint=_checkpoint(22),
                occurredAt=datetime.now(UTC),
            ),
            user_id="user-1",
            novel_id="novel-1",
        )

    assert captured.value.code == "WRITING_CHECKPOINT_SEQUENCE_MISMATCH"
    assert repository.saved is False


class RejectingRepository:
    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        del task_id, job_id
        return CallbackAcceptance(False, 20)

    async def mark_command_processing(
        self, task_id: str, job_id: str, sequence: int
    ) -> CallbackAcceptance:
        del task_id, job_id, sequence
        return CallbackAcceptance(False, 20)

    async def save_checkpoint(self, *args: object) -> CallbackAcceptance:
        del args
        return CallbackAcceptance(False, 20)

    async def complete_with_message_and_command(
        self, *args: object
    ) -> CallbackAcceptance:
        del args
        return CallbackAcceptance(False, 20)

    async def fail_with_command(self, *args: object) -> CallbackAcceptance:
        del args
        return CallbackAcceptance(False, 20)


@pytest.mark.asyncio
async def test_rejected_old_job_callbacks_do_not_publish_events() -> None:
    store = InMemoryWritingEventStore()
    service = WritingCallbackService(
        RejectingRepository(),  # type: ignore[arg-type]
        store,
    )
    occurred_at = datetime.now(UTC)

    await service.accept_event(
        AgentEvent(
            protocolVersion="1.1",
            eventId="event-21",
            jobId="command-a",
            runId="task-1",
            taskId="task-1",
            sequence=21,
            event="agent_start",
            data={},
            occurredAt=occurred_at,
        )
    )
    await service.save_checkpoint(
        CheckpointCallback(
            protocolVersion="1.1",
            eventId="event-22",
            jobId="command-a",
            runId="task-1",
            taskId="task-1",
            sequence=22,
            checkpoint=_checkpoint(22),
            occurredAt=occurred_at,
        ),
        user_id="user-1",
        novel_id="novel-1",
    )
    await service.complete(
        RunCompletionCallback(
            protocolVersion="1.1",
            eventId="event-23",
            jobId="command-a",
            runId="task-1",
            taskId="task-1",
            sequence=23,
            result={},
            occurredAt=occurred_at,
        )
    )
    await service.fail(
        RunFailureCallback(
            protocolVersion="1.1",
            eventId="event-24",
            jobId="command-a",
            runId="task-1",
            taskId="task-1",
            sequence=24,
            code="OLD_JOB_FAILED",
            message="旧作业失败",
            recoverable=False,
            occurredAt=occurred_at,
        )
    )

    assert await store.replay("task-1", None) == []


class BoundaryReceiptRepository:
    def __init__(self) -> None:
        self.saved_checkpoint = False
        self.completed = False
        self.failed = False

    async def authorize_callback(self, *args: object) -> CallbackAcceptance:
        del args
        return CallbackAcceptance(True, 20)

    async def mark_command_processing(
        self, *args: object, **kwargs: object
    ) -> CallbackAcceptance:
        del args, kwargs
        return CallbackAcceptance(
            True,
            20,
            task_phase="active",
            command_status="processing",
        )

    async def save_checkpoint(self, *args: object, **kwargs: object) -> CallbackAcceptance:
        del args, kwargs
        self.saved_checkpoint = True
        return CallbackAcceptance(
            True,
            20,
            task_phase="awaiting_user_review",
            command_status="succeeded",
            outbox_event_id="outbox-waiting",
        )

    async def complete_with_message_and_command(
        self, *args: object, **kwargs: object
    ) -> CallbackAcceptance:
        del args, kwargs
        self.completed = True
        return CallbackAcceptance(
            True,
            20,
            task_phase="completed",
            command_status="succeeded",
            outbox_event_id="outbox-completed",
        )

    async def fail_with_command(
        self, *args: object, **kwargs: object
    ) -> CallbackAcceptance:
        del args, kwargs
        self.failed = True
        return CallbackAcceptance(
            True,
            20,
            task_phase="error",
            command_status="failed",
            outbox_event_id="outbox-error",
        )


class BoundaryRedisMustNotBeRequired(InMemoryWritingEventStore):
    async def validate_agent_event(self, *args: object, **kwargs: object) -> bool:
        del args, kwargs
        raise AssertionError("持久业务边界不能在事务前依赖 Redis")

    async def append_agent_event(self, *args: object, **kwargs: object) -> Any:
        del args, kwargs
        raise AssertionError("持久业务边界必须由 Outbox 异步发布")


@pytest.mark.asyncio
async def test_progress_event_returns_applied_receipt_after_redis_publish() -> None:
    repository = BoundaryReceiptRepository()
    store = InMemoryWritingEventStore()
    service = WritingCallbackService(
        repository,  # type: ignore[arg-type]
        store,
    )

    receipt = await service.accept_event(
        AgentEvent(
            protocolVersion="1.1",
            eventId="event-progress",
            jobId="command-current",
            runId="task-1",
            taskId="task-1",
            sequence=21,
            event="agent_start",
            data={},
            occurredAt=datetime.now(UTC),
        )
    )

    assert receipt.disposition == "applied"
    assert [event.event for event in await store.replay("task-1", None)] == [
        "agent_start"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("callback_kind", "expected_outbox"),
    [
        ("waiting", "outbox-waiting"),
        ("complete", "outbox-completed"),
        ("fail", "outbox-error"),
    ],
)
async def test_persistent_boundaries_return_receipt_without_direct_redis(
    callback_kind: str,
    expected_outbox: str,
) -> None:
    repository = BoundaryReceiptRepository()
    store = BoundaryRedisMustNotBeRequired()
    service = WritingCallbackService(
        repository,  # type: ignore[arg-type]
        store,
    )
    occurred_at = datetime.now(UTC)

    if callback_kind == "waiting":
        receipt = await service.save_checkpoint(
            CheckpointCallback(
                protocolVersion="1.1",
                eventId="event-waiting",
                jobId="command-current",
                runId="task-1",
                taskId="task-1",
                sequence=21,
                checkpoint=_checkpoint(21),
                occurredAt=occurred_at,
            ),
            user_id="user-1",
            novel_id="novel-1",
        )
    elif callback_kind == "complete":
        receipt = await service.complete(
            RunCompletionCallback(
                protocolVersion="1.1",
                eventId="event-complete",
                jobId="command-current",
                runId="task-1",
                taskId="task-1",
                sequence=21,
                result={"finalResponse": "完成"},
                occurredAt=occurred_at,
            )
        )
    else:
        receipt = await service.fail(
            RunFailureCallback(
                protocolVersion="1.1",
                eventId="event-fail",
                jobId="command-current",
                runId="task-1",
                taskId="task-1",
                sequence=21,
                code="AGENT_RUN_FAILED",
                message="失败",
                recoverable=True,
                occurredAt=occurred_at,
            )
        )

    assert receipt.disposition == "applied"
    assert receipt.outboxEventId == expected_outbox
    assert await store.replay("task-1", None) == []
