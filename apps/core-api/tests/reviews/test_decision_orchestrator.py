from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.reviews.decision_orchestrator import (
    ReviewDecisionDependencies,
    ReviewDecisionOrchestrator,
)
from inkforge_core.reviews.repository import ArtifactRecord
from inkforge_core.reviews.schemas import (
    ArtifactDecisionResponse,
    ReviewArtifactDecisionRequest,
)
from inkforge_core.writing.commands import WritingCommandRecord
from inkforge_core.writing.records import TaskRecord


class Transaction:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc, traceback
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True


class OuterSession:
    def __init__(self) -> None:
        self.transaction = Transaction()

    async def __aenter__(self) -> OuterSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def begin(self) -> Transaction:
        return self.transaction

    async def connection(self) -> object:
        return object()


class OuterFactory:
    def __init__(self, session: OuterSession) -> None:
        self.session = session

    def __call__(self) -> OuterSession:
        return self.session


def task() -> TaskRecord:
    return TaskRecord(
        id="task-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        writing_session_id="session-1",
        phase="awaiting_user_review",
        graph_state_json="{}",
    )


def artifact() -> ArtifactRecord:
    from datetime import UTC, datetime

    now = datetime(2026, 7, 14, tzinfo=UTC)
    return ArtifactRecord(
        id="artifact-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        task_id="task-1",
        workflow_run_id="run-1",
        artifact_key="draft-1",
        kind="chapter_draft",
        status="awaiting_user",
        title="正文草案",
        summary=None,
        payload={"kind": "chapter_draft", "content": "正文"},
        diff=None,
        created_by_agent="写作",
        updated_by_agent=None,
        reviewer_agent=None,
        revision=1,
        created_at=now,
        updated_at=now,
    )


def command(*, result: dict[str, Any] | None = None) -> WritingCommandRecord:
    return WritingCommandRecord(
        id="command-1",
        task=task(),
        kind="artifact_decision",
        payload={"resume": True},
        status="pending",
        attempt_count=0,
        artifact_id="artifact-1",
        decision="discard",
        result=result,
    )


class Lookup:
    def __init__(self, existing: WritingCommandRecord | None = None) -> None:
        self.existing = existing

    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None:
        assert user_id == "user-1"
        assert client_request_id == "request-00000001"
        return self.existing


class ArtifactRepository:
    def __init__(self) -> None:
        self.required = 0

    async def require_artifact(self, user_id: str, artifact_id: str) -> ArtifactRecord:
        assert user_id == "user-1"
        assert artifact_id == "artifact-1"
        self.required += 1
        return artifact()


class DecisionService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def decide(self, user_id: str, artifact_id: str, decision: str, **kwargs: object):
        del user_id, artifact_id, kwargs
        if self.fail:
            raise ApiError(
                status_code=409,
                code="ARTIFACT_APPLY_FAILED",
                message="草案正式写入失败",
            )
        return ArtifactDecisionResponse(
            artifactId="artifact-1",
            decision=decision,
            savedCount=1 if decision == "approve" else 0,
            deleted=decision == "discard",
        )


class CommandRepository:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    async def require_owned_task(self, user_id: str, task_id: str) -> TaskRecord:
        assert user_id == "user-1"
        assert task_id == "task-1"
        return task()

    async def create_artifact_decision(self, **kwargs: Any) -> WritingCommandRecord:
        self.created = kwargs
        return replace(
            command(result=kwargs["result"]),
            id=kwargs["command_id"],
            decision=kwargs["decision"],
        )


@dataclass
class Fixture:
    orchestrator: ReviewDecisionOrchestrator
    outer: OuterSession
    artifacts: ArtifactRepository
    commands: CommandRepository


def fixture(*, fail: bool = False) -> Fixture:
    outer = OuterSession()
    artifacts = ArtifactRepository()
    commands = CommandRepository()
    dependencies = ReviewDecisionDependencies(
        repository=artifacts,
        service=DecisionService(fail=fail),
        commands=commands,
    )
    orchestrator = ReviewDecisionOrchestrator(
        OuterFactory(outer),  # type: ignore[arg-type]
        command_lookup=Lookup(),
        dependencies_builder=lambda _factory: dependencies,
        transactional_factory_builder=lambda _connection: object(),
    )
    return Fixture(orchestrator, outer, artifacts, commands)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "discard", "revise"])
async def test_all_decisions_create_one_durable_resume_command(decision: str) -> None:
    subject = fixture()

    response = await subject.orchestrator.decide(
        "user-1",
        "artifact-1",
        ReviewArtifactDecisionRequest(
            clientRequestId="request-00000001",
            decision=decision,
            userMessage="按此决定继续",
        ),
    )

    assert response.taskId == "task-1"
    assert response.status == "pending"
    assert response.decision == decision
    assert subject.commands.created is not None
    assert subject.commands.created["payload"]["resumeInput"] == {
        "artifactId": "artifact-1",
        "decision": decision,
        "userMessage": "按此决定继续",
    }
    assert subject.outer.transaction.committed is True


@pytest.mark.asyncio
async def test_apply_failure_rolls_back_before_command_creation() -> None:
    subject = fixture(fail=True)

    with pytest.raises(ApiError) as captured:
        await subject.orchestrator.decide(
            "user-1",
            "artifact-1",
            ReviewArtifactDecisionRequest(
                clientRequestId="request-00000001",
                decision="approve",
            ),
        )

    assert captured.value.code == "ARTIFACT_APPLY_FAILED"
    assert subject.commands.created is None
    assert subject.outer.transaction.rolled_back is True


@pytest.mark.asyncio
async def test_discard_retry_returns_original_command_before_artifact_lookup() -> None:
    saved = {
        "artifactId": "artifact-1",
        "taskId": "task-1",
        "commandId": "command-1",
        "decision": "discard",
        "status": "pending",
        "savedCount": 0,
        "deleted": True,
    }
    lookup = Lookup(command(result=saved))
    outer = OuterSession()
    orchestrator = ReviewDecisionOrchestrator(
        OuterFactory(outer),  # type: ignore[arg-type]
        command_lookup=lookup,
        dependencies_builder=lambda _factory: pytest.fail("不应再次读取已删除草案"),
        transactional_factory_builder=lambda _connection: object(),
    )

    response = await orchestrator.decide(
        "user-1",
        "artifact-1",
        ReviewArtifactDecisionRequest(
            clientRequestId="request-00000001",
            decision="discard",
        ),
    )

    assert response.commandId == "command-1"
    assert response.deleted is True
