from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.writing.recovery import (
    InvalidGraphSnapshotError,
    TaskCandidate,
    deserialize_graph_snapshot,
    select_recovery_state,
    validate_resume_session_binding,
)
from inkforge_core.writing.tasks import TaskRecord, WritingTaskService


def _snapshot(**overrides: object) -> str:
    value: dict[str, object] = {
        "taskId": "task-1",
        "userId": "user-1",
        "novelId": "novel-1",
        "chapterId": "chapter-1",
        "targetWordCount": 4000,
        "conversationHistory": [],
        "currentOperation": {"kind": "answer_question"},
        "operationStage": "执行创作操作",
        "artifactReview": {"activeArtifactId": "artifact-1"},
        "activeArtifactId": "artifact-legacy",
    }
    value.update(overrides)
    return json.dumps(value, ensure_ascii=False)


def test_snapshot_rejects_malformed_and_runtime_only_fields() -> None:
    with pytest.raises(InvalidGraphSnapshotError):
        deserialize_graph_snapshot("不是 JSON")
    with pytest.raises(InvalidGraphSnapshotError):
        deserialize_graph_snapshot(_snapshot(runtime={"callbacks": "禁止持久化"}))


def test_snapshot_requires_task_ownership_identity() -> None:
    with pytest.raises(InvalidGraphSnapshotError):
        deserialize_graph_snapshot(
            _snapshot(taskId="other-task"),
            expected_task_id="task-1",
            expected_user_id="user-1",
            expected_novel_id="novel-1",
            expected_chapter_id="chapter-1",
        )


def test_recovery_separates_resumable_and_terminal_tasks() -> None:
    now = datetime(2026, 7, 11, 12, 0, 0)
    state = select_recovery_state(
        [
            TaskCandidate(
                "task-completed", "completed", now, None, _snapshot(taskId="task-completed")
            ),
            TaskCandidate(
                "task-active",
                "active",
                now - timedelta(minutes=1),
                None,
                _snapshot(taskId="task-active"),
            ),
            TaskCandidate(
                "task-review",
                "awaiting_user_review",
                now - timedelta(minutes=2),
                None,
                _snapshot(taskId="task-review"),
            ),
        ]
    )

    assert state.currentTask is not None
    assert state.currentTask.id == "task-review"
    assert state.currentTask.activeArtifactId == "artifact-1"
    assert state.currentTask.hasAwaitingReviewArtifact is True
    assert state.lastTask is not None
    assert state.lastTask.id == "task-completed"


def test_resume_requires_exact_explicit_session_binding() -> None:
    validate_resume_session_binding("session-1", "session-1")
    validate_resume_session_binding(None, None)
    with pytest.raises(ValueError, match="当前任务不属于所选写作会话"):
        validate_resume_session_binding("session-1", None)
    with pytest.raises(ValueError, match="当前任务不属于所选写作会话"):
        validate_resume_session_binding("session-1", "session-2")


class TerminalTaskRepository:
    async def require_task(self, user_id: str, task_id: str) -> TaskRecord:
        return TaskRecord(
            id=task_id,
            user_id=user_id,
            novel_id="novel-1",
            chapter_id="chapter-1",
            writing_session_id="session-1",
            phase="completed",
            graph_state_json=None,
        )


@pytest.mark.asyncio
async def test_completed_task_cannot_resume_even_before_queue_is_connected() -> None:
    service = WritingTaskService(TerminalTaskRepository(), submitter=None)

    with pytest.raises(ApiError) as error:
        await service.resume("user-1", "task-1", "session-1")

    assert error.value.status_code == 409
