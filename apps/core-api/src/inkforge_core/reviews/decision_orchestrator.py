from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
)

from ..db.base import generate_id
from ..errors import ApiError
from ..lore.repository import LoreRepository
from ..outlines.repository import OutlineRepository
from ..references.repository import ReferenceRepository
from ..writing.commands import WritingCommandRecord, WritingRunCommandRepository
from ..writing.records import TaskRecord
from .apply import FormalArtifactApplier
from .formal_writes import FormalWriteRepository
from .repository import ArtifactRecord, ReviewRepository
from .schemas import (
    ArtifactDecisionAcceptedResponse,
    ArtifactDecisionResponse,
    ReviewArtifactDecisionRequest,
)
from .service import ReviewService
from .updates import AgentUpdatesExecutor

logger = logging.getLogger(__name__)


class ReviewArtifactRepositoryPort(Protocol):
    async def require_artifact(
        self,
        user_id: str,
        artifact_id: str,
    ) -> ArtifactRecord: ...

    async def require_artifact_revision(
        self,
        user_id: str,
        artifact_id: str,
        expected_revision: int,
    ) -> ArtifactRecord: ...


class ReviewDecisionServicePort(Protocol):
    async def decide(
        self,
        user_id: str,
        artifact_id: str,
        decision: Literal["approve", "discard", "revise"],
        *,
        edited_content: str | None = None,
        selected_update_refs: list[dict[str, object]] | None = None,
    ) -> ArtifactDecisionResponse: ...


class ReviewCommandRepositoryPort(Protocol):
    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None: ...

    async def require_owned_task(self, user_id: str, task_id: str) -> TaskRecord: ...

    async def create_artifact_decision(
        self,
        *,
        command_id: str,
        user_id: str,
        task_id: str,
        artifact_id: str,
        decision: Literal["approve", "discard", "revise"],
        client_request_id: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> WritingCommandRecord: ...


class ReviewCommandLookupPort(Protocol):
    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None: ...


class ImmediateDispatcherPort(Protocol):
    async def run_once(self) -> int: ...


@dataclass(frozen=True, slots=True)
class ReviewDecisionDependencies:
    repository: ReviewArtifactRepositoryPort
    service: ReviewDecisionServicePort
    commands: ReviewCommandRepositoryPort


class ReviewDecisionOrchestrator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        command_lookup: ReviewCommandLookupPort | None = None,
        dependencies_builder: Callable[[Any], ReviewDecisionDependencies] | None = None,
        transactional_factory_builder: Callable[[Any], Any] | None = None,
        dispatcher: ImmediateDispatcherPort | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._command_lookup = command_lookup or WritingRunCommandRepository(session_factory)
        self._dependencies_builder = dependencies_builder or _build_dependencies
        self._transactional_factory_builder = (
            transactional_factory_builder or _build_transactional_factory
        )
        self._dispatcher = dispatcher

    async def decide(
        self,
        user_id: str,
        artifact_id: str,
        request: ReviewArtifactDecisionRequest,
    ) -> ArtifactDecisionAcceptedResponse:
        existing = await self._command_lookup.get_by_idempotency_key(
            user_id, request.clientRequestId
        )
        if existing is not None:
            return _accepted_response_from_command(existing, artifact_id, request)

        accepted: ArtifactDecisionAcceptedResponse
        async with self._session_factory() as outer:
            async with outer.begin():
                connection = await outer.connection()
                transactional_factory = self._transactional_factory_builder(connection)
                dependencies = self._dependencies_builder(transactional_factory)
                try:
                    artifact_before_lock = await dependencies.repository.require_artifact(
                        user_id, artifact_id
                    )
                except ApiError as exc:
                    if exc.code != "REVIEW_ARTIFACT_FORBIDDEN":
                        raise
                    raced = await dependencies.commands.get_by_idempotency_key(
                        user_id, request.clientRequestId
                    )
                    if raced is not None:
                        return _accepted_response_from_command(raced, artifact_id, request)
                    raise
                if artifact_before_lock.task_id is None:
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_TASK_MISSING",
                        message="待审核草案没有关联写作任务",
                    )
                task = await dependencies.commands.require_owned_task(
                    user_id, artifact_before_lock.task_id
                )
                raced = await dependencies.commands.get_by_idempotency_key(
                    user_id, request.clientRequestId
                )
                if raced is not None:
                    return _accepted_response_from_command(raced, artifact_id, request)
                artifact = await dependencies.repository.require_artifact_revision(
                    user_id, artifact_id, request.expectedRevision
                )
                if (
                    artifact.kind == "outline_draft"
                    and artifact.payload.get("storyLengthProfile") == "short_medium"
                    and request.editedContent is not None
                ):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_OUTLINE_EDIT_REQUIRES_SAVE",
                        message="中短篇大纲必须先保存为新版本，再批准当前精确版本",
                    )
                if artifact.task_id != task.id:
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_CHANGED_DURING_DECISION",
                        message="待审核草案在决定受理前已发生变化",
                    )
                refs = (
                    [item.model_dump(exclude_none=True) for item in request.selectedUpdateRefs]
                    if request.selectedUpdateRefs is not None
                    else None
                )
                decision_result = await dependencies.service.decide(
                    user_id,
                    artifact_id,
                    request.decision,
                    edited_content=request.editedContent,
                    selected_update_refs=refs,
                )
                command_id = generate_id()
                accepted = ArtifactDecisionAcceptedResponse(
                    artifactId=artifact_id,
                    taskId=task.id,
                    commandId=command_id,
                    decision=request.decision,
                    status="pending",
                    savedCount=decision_result.savedCount,
                    deleted=decision_result.deleted,
                )
                resume_input: dict[str, Any] = {
                    "artifactId": artifact_id,
                    "decision": request.decision,
                    "expectedRevision": request.expectedRevision,
                }
                if request.userMessage is not None:
                    resume_input["userMessage"] = request.userMessage
                payload: dict[str, Any] = {
                    "version": 1,
                    "resume": True,
                    "chapterId": task.chapter_id,
                    "writingSessionId": task.writing_session_id,
                    "resumeInput": resume_input,
                    "decisionRequest": _decision_semantics(artifact_id, request),
                }
                persisted_command = await dependencies.commands.create_artifact_decision(
                    command_id=command_id,
                    user_id=user_id,
                    task_id=task.id,
                    artifact_id=artifact_id,
                    decision=request.decision,
                    client_request_id=request.clientRequestId,
                    payload=payload,
                    result=accepted.model_dump(mode="json"),
                )
                accepted = _accepted_response_from_command(
                    persisted_command,
                    artifact_id,
                    request,
                )
        await self._kick_dispatcher()
        return accepted

    async def _kick_dispatcher(self) -> None:
        if self._dispatcher is None:
            return
        try:
            await self._dispatcher.run_once()
        except Exception:
            logger.warning("草案决定命令即时投递失败，已交由后台重试")


def _accepted_response_from_command(
    command: WritingCommandRecord,
    artifact_id: str,
    request: ReviewArtifactDecisionRequest,
) -> ArtifactDecisionAcceptedResponse:
    semantics = _decision_semantics(artifact_id, request)
    if (
        command.kind != "artifact_decision"
        or command.result is None
        or command.artifact_id != artifact_id
        or command.decision != request.decision
        or command.payload.get("decisionRequest") != semantics
    ):
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="客户端请求标识已用于其他操作",
        )
    try:
        return ArtifactDecisionAcceptedResponse.model_validate(command.result)
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code="WRITING_COMMAND_RESULT_INVALID",
            message="写作命令受理结果无效",
        ) from exc


def _decision_semantics(
    artifact_id: str,
    request: ReviewArtifactDecisionRequest,
) -> dict[str, Any]:
    return {
        "artifactId": artifact_id,
        "decision": request.decision,
        "expectedRevision": request.expectedRevision,
        "editedContent": request.editedContent,
        "selectedUpdateRefs": (
            [item.model_dump(mode="json") for item in request.selectedUpdateRefs]
            if request.selectedUpdateRefs is not None
            else None
        ),
        "userMessage": request.userMessage,
    }


def _build_transactional_factory(
    connection: AsyncConnection,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


def _build_dependencies(
    session_factory: async_sessionmaker[AsyncSession],
) -> ReviewDecisionDependencies:
    repository = ReviewRepository(session_factory)
    updates = AgentUpdatesExecutor(
        LoreRepository(session_factory),
        OutlineRepository(session_factory),
        ReferenceRepository(session_factory),
    )
    service = ReviewService(
        repository,
        FormalArtifactApplier(FormalWriteRepository(session_factory), updates),
    )
    return ReviewDecisionDependencies(
        repository=repository,
        service=service,
        commands=WritingRunCommandRepository(session_factory),
    )
