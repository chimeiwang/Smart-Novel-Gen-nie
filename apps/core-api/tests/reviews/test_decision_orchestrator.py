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
        payload={
            "resume": True,
            "decisionRequest": {
                "artifactId": "artifact-1",
                "decision": "discard",
                "expectedRevision": 1,
                "editedContent": None,
                "selectedUpdateRefs": None,
                "userMessage": None,
            },
        },
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

    async def require_artifact_revision(
        self, user_id: str, artifact_id: str, expected_revision: int
    ) -> ArtifactRecord:
        result = await self.require_artifact(user_id, artifact_id)
        if result.revision != expected_revision:
            raise ApiError(
                status_code=409,
                code="ARTIFACT_REVISION_CONFLICT",
                message="修订号过期",
            )
        return result


class DecisionService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def decide(self, user_id: str, artifact_id: str, decision: str, **kwargs: object):
        del user_id, artifact_id, kwargs
        self.calls += 1
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
            artifact_id=kwargs["artifact_id"],
            payload=kwargs["payload"],
        )


class RacingCommandRepository(CommandRepository):
    def __init__(self, persisted: WritingCommandRecord) -> None:
        super().__init__()
        self.persisted = persisted

    async def create_artifact_decision(self, **kwargs: Any) -> WritingCommandRecord:
        self.created = kwargs
        return self.persisted


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
            expectedRevision=1,
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
        "expectedRevision": 1,
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
                expectedRevision=1,
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
            expectedRevision=1,
        ),
    )

    assert response.commandId == "command-1"
    assert response.deleted is True


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_before_decision_side_effects() -> None:
    subject = fixture()

    with pytest.raises(ApiError) as caught:
        await subject.orchestrator.decide(
            "user-1",
            "artifact-1",
            ReviewArtifactDecisionRequest(
                clientRequestId="request-00000001",
                decision="discard",
                expectedRevision=2,
            ),
        )

    assert caught.value.code == "ARTIFACT_REVISION_CONFLICT"
    assert subject.commands.created is None
    assert subject.outer.transaction.rolled_back is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact_id", "decision", "expected_revision", "user_message"),
    [
        ("artifact-2", "discard", 1, None),
        ("artifact-1", "approve", 1, None),
        ("artifact-1", "discard", 2, None),
        ("artifact-1", "discard", 1, "不同原文"),
    ],
)
async def test_idempotency_key_reuse_requires_identical_decision_semantics(
    artifact_id: str,
    decision: str,
    expected_revision: int,
    user_message: str | None,
) -> None:
    saved = {
        "artifactId": "artifact-1",
        "taskId": "task-1",
        "commandId": "command-1",
        "decision": "discard",
        "status": "pending",
        "savedCount": 0,
        "deleted": True,
    }
    orchestrator = ReviewDecisionOrchestrator(
        OuterFactory(OuterSession()),  # type: ignore[arg-type]
        command_lookup=Lookup(command(result=saved)),
        dependencies_builder=lambda _factory: pytest.fail("不应执行副作用"),
        transactional_factory_builder=lambda _connection: object(),
    )

    with pytest.raises(ApiError) as caught:
        await orchestrator.decide(
            "user-1",
            artifact_id,
            ReviewArtifactDecisionRequest(
                clientRequestId="request-00000001",
                decision=decision,  # type: ignore[arg-type]
                expectedRevision=expected_revision,
                userMessage=user_message,
            ),
        )
    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_short_outline_approve_rejects_edited_content_shortcut() -> None:
    subject = fixture()
    original = subject.artifacts.require_artifact_revision

    async def short_outline(
        user_id: str, artifact_id: str, expected_revision: int
    ) -> ArtifactRecord:
        result = await original(user_id, artifact_id, expected_revision)
        return replace(
            result,
            kind="outline_draft",
            payload={
                "kind": "outline_draft",
                "storyLengthProfile": "short_medium",
                "content": "大纲",
            },
        )

    subject.artifacts.require_artifact_revision = short_outline  # type: ignore[method-assign]
    with pytest.raises(ApiError) as caught:
        await subject.orchestrator.decide(
            "user-1",
            "artifact-1",
            ReviewArtifactDecisionRequest(
                clientRequestId="request-00000001",
                decision="approve",
                expectedRevision=1,
                editedContent="试图绕过版本保存",
            ),
        )
    assert caught.value.code == "SHORT_OUTLINE_EDIT_REQUIRES_SAVE"
    assert subject.commands.created is None


def _orchestrator_with_commands(
    commands: CommandRepository,
) -> ReviewDecisionOrchestrator:
    dependencies = ReviewDecisionDependencies(
        repository=ArtifactRepository(),
        service=DecisionService(),
        commands=commands,
    )
    return ReviewDecisionOrchestrator(
        OuterFactory(OuterSession()),  # type: ignore[arg-type]
        command_lookup=Lookup(),
        dependencies_builder=lambda _factory: dependencies,
        transactional_factory_builder=lambda _connection: object(),
    )


@pytest.mark.asyncio
async def test_command_insert_race_returns_the_persisted_command_result() -> None:
    persisted_result = {
        "artifactId": "artifact-1",
        "taskId": "task-1",
        "commandId": "command-persisted",
        "decision": "discard",
        "status": "submitted",
        "savedCount": 0,
        "deleted": True,
    }
    persisted = replace(
        command(result=persisted_result),
        id="command-persisted",
        status="submitted",
    )
    orchestrator = _orchestrator_with_commands(RacingCommandRepository(persisted))

    response = await orchestrator.decide(
        "user-1",
        "artifact-1",
        ReviewArtifactDecisionRequest(
            clientRequestId="request-00000001",
            decision="discard",
            expectedRevision=1,
        ),
    )

    assert response.commandId == "command-persisted"
    assert response.status == "submitted"


@pytest.mark.asyncio
async def test_command_insert_race_rejects_different_persisted_semantics() -> None:
    persisted_result = {
        "artifactId": "artifact-1",
        "taskId": "task-1",
        "commandId": "command-persisted",
        "decision": "discard",
        "status": "pending",
        "savedCount": 0,
        "deleted": True,
    }
    persisted = replace(
        command(result=persisted_result),
        id="command-persisted",
        payload={
            **command().payload,
            "decisionRequest": {
                **command().payload["decisionRequest"],
                "expectedRevision": 2,
            },
        },
    )
    orchestrator = _orchestrator_with_commands(RacingCommandRepository(persisted))

    with pytest.raises(ApiError) as caught:
        await orchestrator.decide(
            "user-1",
            "artifact-1",
            ReviewArtifactDecisionRequest(
                clientRequestId="request-00000001",
                decision="discard",
                expectedRevision=1,
            ),
        )
    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"
