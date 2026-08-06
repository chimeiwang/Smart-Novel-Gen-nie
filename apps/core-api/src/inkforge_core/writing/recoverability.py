from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from ..db.models import WritingRunCommand, WritingTask
from .recovery import InvalidGraphSnapshotError, deserialize_graph_snapshot

_TERMINAL_COMMAND_STATUSES = frozenset({"succeeded", "failed"})
_RECOVERABLE_PHASES = frozenset({"active", "waiting_call"})


def resolve_recoverable_checkpoint(
    task: WritingTask,
    commands: Iterable[WritingRunCommand],
) -> dict[str, Any] | None:
    """只接受可证明归属且未被活动命令占用的持久检查点。"""
    if task.phase not in _RECOVERABLE_PHASES or not task.graphStateJson:
        return None
    command_list = list(commands)
    if any(
        command.taskId == task.id and command.status not in _TERMINAL_COMMAND_STATUSES
        for command in command_list
    ):
        return None
    try:
        snapshot = json.loads(task.graphStateJson)
        deserialize_graph_snapshot(
            task.graphStateJson,
            expected_task_id=task.id,
            expected_novel_id=task.novelId,
            expected_chapter_id=task.chapterId,
        )
    except (InvalidGraphSnapshotError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(snapshot, dict):
        return None
    sequence = snapshot.get("eventSequence")
    operation = snapshot.get("currentOperation")
    stage = snapshot.get("operationStage")
    callback_job_id = snapshot.get("callbackJobId")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 0
        or snapshot.get("phase") != task.phase
        or not isinstance(operation, dict)
        or not isinstance(operation.get("kind"), str)
        or not isinstance(stage, str)
        or not stage.strip()
    ):
        return None
    source = next(
        (command for command in command_list if command.id == callback_job_id), None
    )
    if (
        not isinstance(callback_job_id, str)
        or source is None
        or source.taskId != task.id
        or source.status not in _TERMINAL_COMMAND_STATUSES
        or _command_operation(source) != operation["kind"]
    ):
        return None
    return snapshot


def _command_operation(command: WritingRunCommand) -> str | None:
    try:
        payload = json.loads(command.payloadJson)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    job = payload.get("job", payload)
    operation = job.get("operation") if isinstance(job, dict) else None
    return operation if isinstance(operation, str) else None
