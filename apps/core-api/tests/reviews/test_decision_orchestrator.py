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
from inkforge_core.writing.idempotency import (
    IdempotencyResolution,
    InkForgeCommandMetadata,
    request_fingerprint,
)
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

    async def execute(
        self, statement: object, params: dict[str, object] | None = None
    ) -> None:
        del statement, params


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
    body = {
        "expectedRevision": 1,
        "decision": "discard",
        "editedContent": None,
        "selectedUpdateRefs": None,
        "userMessage": None,
    }
    return WritingCommandRecord(
        id="command-1",
        task=task(),
        kind="artifact_decision",
        payload={
            "_inkforgeCommand": {
                "schemaVersion": 1,
                "clientRequestId": "request-00000001",
                "commandKind": "artifact_decision",
                "resourceIdentity": {"artifactId": "artifact-1"},
                "normalizedBody": body,
                "requestFingerprint": request_fingerprint(
                    command_kind="artifact_decision",
                    resource_identity={"artifactId": "artifact-1"},
                    body=body,
                ),
            },
            "job": {"resume": True},
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
        self.calls = 0

    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None:
        assert user_id == "user-1"
        assert client_request_id == "request-00000001"
        self.calls += 1
        return self.existing


class Resolver:
    def __init__(self, resolution: IdempotencyResolution | None = None) -> None:
        self.resolution = resolution
        self.calls = 0

    async def __call__(
        self,
        session: object,
        *,
        user_id: str,
        client_request_id: str,
        request_fingerprint: str,
    ) -> IdempotencyResolution | None:
        del session
        assert user_id == "user-1"
        assert client_request_id == "request-00000001"
        self.calls += 1
        if (
            self.resolution is not None
            and self.resolution.metadata.requestFingerprint
            != request_fingerprint
        ):
            raise ApiError(
                status_code=409,
                code="IDEMPOTENCY_KEY_REUSED",
                message="同一幂等标识已绑定其他请求",
            )
        return self.resolution


def resolution_for(
    persisted: WritingCommandRecord,
    *,
    record_kind: str = "writing_command",
) -> IdempotencyResolution:
    metadata = InkForgeCommandMetadata.model_validate(
        persisted.payload["_inkforgeCommand"]
    )
    return IdempotencyResolution(
        record_kind=record_kind,  # type: ignore[arg-type]
        record_id=persisted.id,
        metadata=metadata,
    )


class ArtifactRepository:
    def __init__(self) -> None:
        self.required = 0

    async def require_artifact(self, user_id: str, artifact_id: str) -> ArtifactRecord:
        assert user_id == "user-1"
        assert artifact_id == "artifact-1"
        self.required += 1
        return artifact()

    async def lock_decision_scope(
        self, user_id: str, artifact_id: str
    ) -> ArtifactRecord:
        return await self.require_artifact(user_id, artifact_id)


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

    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None:
        del user_id, client_request_id
        return None

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
        idempotency_resolver=Resolver(),
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
                expectedRevision=1,
                decision=decision,
            userMessage="按此决定继续",
        ),
    )

    assert response.taskId == "task-1"
    assert response.status == "pending"
    assert response.decision == decision
    assert subject.commands.created is not None
    assert subject.commands.created["payload"]["job"]["resumeInput"] == {
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
                expectedRevision=1,
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
    persisted = command(result=saved)
    lookup = Lookup(persisted)
    outer = OuterSession()
    orchestrator = ReviewDecisionOrchestrator(
        OuterFactory(outer),  # type: ignore[arg-type]
        command_lookup=lookup,
        idempotency_resolver=Resolver(resolution_for(persisted)),
        dependencies_builder=lambda _factory: pytest.fail("不应再次读取已删除草案"),
        transactional_factory_builder=lambda _connection: object(),
    )

    response = await orchestrator.decide(
        "user-1",
        "artifact-1",
        ReviewArtifactDecisionRequest(
            clientRequestId="request-00000001",
            expectedRevision=1,
            decision="discard",
        ),
    )

    assert response.commandId == "command-1"
    assert response.deleted is True


@pytest.mark.asyncio
async def test_reused_client_request_id_with_different_revision_is_rejected() -> None:
    saved = {
        "artifactId": "artifact-1",
        "taskId": "task-1",
        "commandId": "command-1",
        "decision": "discard",
        "status": "pending",
        "savedCount": 0,
        "deleted": True,
    }
    persisted = command(result=saved)
    orchestrator = ReviewDecisionOrchestrator(
        OuterFactory(OuterSession()),  # type: ignore[arg-type]
        command_lookup=Lookup(persisted),
        idempotency_resolver=Resolver(resolution_for(persisted)),
        dependencies_builder=lambda _factory: pytest.fail("不应执行新的草案决定"),
        transactional_factory_builder=lambda _connection: object(),
    )

    with pytest.raises(ApiError) as captured:
        await orchestrator.decide(
            "user-1",
            "artifact-1",
            ReviewArtifactDecisionRequest(
                clientRequestId="request-00000001",
                expectedRevision=2,
                decision="discard",
            ),
        )

    assert captured.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["completed", "cancelled"])
async def test_decision_retry_replays_accepted_response_after_terminal_update(
    terminal: str,
) -> None:
    accepted = {
        "artifactId": "artifact-1",
        "taskId": "task-1",
        "commandId": "command-1",
        "decision": "discard",
        "status": "pending",
        "savedCount": 0,
        "deleted": True,
    }
    if terminal == "completed":
        persisted_result = {
            **accepted,
            "_inkforgeTerminalCallbackResult": {"finalResponse": "已完成"},
        }
    else:
        persisted_result = {
            "code": "WRITING_RUN_CANCELLED_BY_USER",
            "cancelCommandId": "cancel-1",
            "cancelledJobId": "command-1",
            "_inkforgeArtifactDecisionAcceptedResponse": accepted,
        }
    persisted = command(result=persisted_result)
    orchestrator = ReviewDecisionOrchestrator(
        OuterFactory(OuterSession()),  # type: ignore[arg-type]
        command_lookup=Lookup(persisted),
        idempotency_resolver=Resolver(resolution_for(persisted)),
        dependencies_builder=lambda _factory: pytest.fail(
            "幂等重放不应再次执行草案决定"
        ),
        transactional_factory_builder=lambda _connection: object(),
    )

    response = await orchestrator.decide(
        "user-1",
        "artifact-1",
        ReviewArtifactDecisionRequest(
            clientRequestId="request-00000001",
            expectedRevision=1,
            decision="discard",
        ),
    )

    assert response.model_dump(mode="json") == accepted


@pytest.mark.asyncio
async def test_decision_rejects_cross_table_idempotency_collision() -> None:
    persisted = command()
    collision = resolution_for(persisted, record_kind="workflow_run")
    lookup = Lookup()
    orchestrator = ReviewDecisionOrchestrator(
        OuterFactory(OuterSession()),  # type: ignore[arg-type]
        command_lookup=lookup,
        idempotency_resolver=Resolver(collision),
        dependencies_builder=lambda _factory: pytest.fail(
            "跨表幂等冲突不应读取草案"
        ),
        transactional_factory_builder=lambda _connection: object(),
    )

    with pytest.raises(ApiError) as captured:
        await orchestrator.decide(
            "user-1",
            "artifact-1",
            ReviewArtifactDecisionRequest(
                clientRequestId="request-00000001",
                expectedRevision=1,
                decision="discard",
            ),
        )

    assert captured.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert lookup.calls == 0


@pytest.mark.asyncio
async def test_historical_bare_decision_does_not_shadow_new_enveloped_request() -> None:
    legacy = replace(command(), payload={"version": 1, "resume": True})
    lookup = Lookup(legacy)
    outer = OuterSession()
    artifacts = ArtifactRepository()
    commands = CommandRepository()
    dependencies = ReviewDecisionDependencies(
        repository=artifacts,
        service=DecisionService(),
        commands=commands,
    )
    orchestrator = ReviewDecisionOrchestrator(
        OuterFactory(outer),  # type: ignore[arg-type]
        command_lookup=lookup,
        idempotency_resolver=Resolver(),
        dependencies_builder=lambda _factory: dependencies,
        transactional_factory_builder=lambda _connection: object(),
    )

    response = await orchestrator.decide(
        "user-1",
        "artifact-1",
        ReviewArtifactDecisionRequest(
            clientRequestId="request-00000001",
            expectedRevision=1,
            decision="discard",
        ),
    )

    assert response.commandId != legacy.id
    assert lookup.calls == 0
    assert commands.created is not None
