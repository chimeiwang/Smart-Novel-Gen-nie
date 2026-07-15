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
from inkforge_core.db.models import WritingRunCommand, WritingTask
from inkforge_core.errors import ApiError
from inkforge_core.writing.job_identity import build_writing_job_id
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
    ) -> None:
        self.task = task
        self.commands = commands
        self.active_command_id = active_command_id
        self.latest_command_id = latest_command_id
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

    async def scalar(self, statement: object) -> str | None:
        query = str(statement)
        if "status" in query and "IN" in query:
            return self.active_command_id
        return self.latest_command_id

    def add(self, value: object) -> None:
        self.added.append(value)

    async def execute(self, statement: object) -> None:
        del statement


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
    assert [event.event for event in events] == [
        "checkpoint",
        "completed" if outcome == "complete" else "error",
    ]
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
