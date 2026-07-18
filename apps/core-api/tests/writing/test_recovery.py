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
from inkforge_core.writing.schemas import ResumeWritingRunRequest, ResumeWritingRunResponse
from inkforge_core.writing.tasks import WritingTaskService


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


@pytest.mark.parametrize(
    "operation",
    ["develop_short_outline", "write_short_story"],
)
def test_snapshot_accepts_explicit_short_story_operations(operation: str) -> None:
    result = deserialize_graph_snapshot(_snapshot(currentOperation={"kind": operation}))

    assert result.current_operation == {"kind": operation}


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


class TerminalCommandRepository:
    async def create_resume_with_message(
        self, user_id: str, task_id: str, request: ResumeWritingRunRequest
    ) -> ResumeWritingRunResponse:
        del user_id, task_id, request
        raise ApiError(
            status_code=409,
            code="WRITING_TASK_TERMINAL",
            message="已完成或失败的任务不能继续恢复",
        )


@pytest.mark.asyncio
async def test_completed_task_cannot_resume_even_before_queue_is_connected() -> None:
    service = WritingTaskService(TerminalCommandRepository(), dispatcher=None)

    with pytest.raises(ApiError) as error:
        await service.resume(
            "user-1",
            "task-1",
            ResumeWritingRunRequest(
                clientRequestId="request-00000001",
                writingSessionId="session-1",
            ),
        )

    assert error.value.status_code == 409


class DurableCommandRepository:
    def __init__(self) -> None:
        self.requests: list[ResumeWritingRunRequest] = []

    async def create_resume_with_message(
        self, user_id: str, task_id: str, request: ResumeWritingRunRequest
    ) -> ResumeWritingRunResponse:
        assert user_id == "user-1"
        assert task_id == "task-1"
        self.requests.append(request)
        return ResumeWritingRunResponse(
            accepted=True,
            taskId=task_id,
            commandId="command-1",
            commandStatus="pending",
        )

class FailingKickDispatcher:
    def __init__(self) -> None:
        self.kicks = 0

    async def run_once(self) -> int:
        self.kicks += 1
        raise RuntimeError("即时投递不可用")


@pytest.mark.asyncio
async def test_resume_is_durable_when_immediate_dispatch_fails() -> None:
    repository = DurableCommandRepository()
    dispatcher = FailingKickDispatcher()
    service = WritingTaskService(repository, dispatcher)

    response = await service.resume(
        "user-1",
        "task-1",
        ResumeWritingRunRequest(
            clientRequestId="request-00000001",
            writingSessionId="session-1",
            userMessage="请继续说明冲突设计。",
        ),
    )

    assert response.model_dump() == {
        "accepted": True,
        "taskId": "task-1",
        "commandId": "command-1",
        "commandStatus": "pending",
    }
    assert repository.requests[0].userMessage == "请继续说明冲突设计。"
    assert dispatcher.kicks == 1
