from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
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
from ..writing.commands import (
    ARTIFACT_DECISION_ACCEPTED_RESPONSE_FIELD,
    WritingCommandRecord,
    WritingRunCommandRepository,
)
from ..writing.idempotency import (
    IdempotencyResolution,
    acquire_idempotency_lock,
    normalize_json_value,
    parse_command_envelope,
    request_fingerprint,
    resolve_idempotency,
)
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
        self, user_id: str, artifact_id: str
    ) -> ArtifactRecord: ...

    async def lock_decision_scope(
        self, user_id: str, artifact_id: str
    ) -> ArtifactRecord: ...


class ReviewDecisionServicePort(Protocol):
    async def decide(
        self,
        user_id: str,
        artifact_id: str,
        decision: Literal["approve", "discard", "revise"],
        *,
        expected_revision: int,
        edited_content: str | None = None,
        edited_replacement: str | None = None,
        selected_update_refs: list[dict[str, object]] | None = None,
    ) -> ArtifactDecisionResponse: ...


class ReviewCommandRepositoryPort(Protocol):
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
        idempotency_resolver: Callable[
            ..., Awaitable[IdempotencyResolution | None]
        ] = resolve_idempotency,
        dependencies_builder: Callable[[Any], ReviewDecisionDependencies] | None = None,
        transactional_factory_builder: Callable[[Any], Any] | None = None,
        dispatcher: ImmediateDispatcherPort | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._command_lookup = command_lookup or WritingRunCommandRepository(session_factory)
        self._idempotency_resolver = idempotency_resolver
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
        request_body = request.model_dump(mode="json", exclude={"clientRequestId"})
        # 新增字段保持旧请求的幂等指纹兼容：未提供时不改变历史规范化正文。
        if request.editedReplacement is None:
            request_body.pop("editedReplacement", None)
        normalized_body = normalize_json_value(request_body)
        if not isinstance(normalized_body, dict):
            raise RuntimeError("草案决定请求无法规范化")
        fingerprint = request_fingerprint(
            command_kind="artifact_decision",
            resource_identity={"artifactId": artifact_id},
            body=normalized_body,
        )
        accepted: ArtifactDecisionAcceptedResponse
        async with self._session_factory() as outer:
            async with outer.begin():
                await acquire_idempotency_lock(
                    outer,
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                )
                replay = await _resolve_decision_replay(
                    outer,
                    self._command_lookup,
                    self._idempotency_resolver,
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                    fingerprint=fingerprint,
                )
                if replay is not None:
                    return replay
                connection = await outer.connection()
                transactional_factory = self._transactional_factory_builder(connection)
                dependencies = self._dependencies_builder(transactional_factory)
                artifact = await dependencies.repository.lock_decision_scope(
                    user_id, artifact_id
                )
                replay = await _resolve_decision_replay(
                    outer,
                    self._command_lookup,
                    self._idempotency_resolver,
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                    fingerprint=fingerprint,
                )
                if replay is not None:
                    return replay
                if artifact.task_id is None:
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_TASK_MISSING",
                        message="待审核草案没有关联写作任务",
                    )
                task = await dependencies.commands.require_owned_task(
                    user_id, artifact.task_id
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
                    expected_revision=request.expectedRevision,
                    edited_content=request.editedContent,
                    edited_replacement=request.editedReplacement,
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
                }
                if request.userMessage is not None:
                    resume_input["userMessage"] = request.userMessage
                job: dict[str, Any] = {
                    "version": 1,
                    "resume": True,
                    "chapterId": task.chapter_id,
                    "writingSessionId": task.writing_session_id,
                    "resumeInput": resume_input,
                }
                payload: dict[str, Any] = {
                    "_inkforgeCommand": {
                        "schemaVersion": 1,
                        "clientRequestId": request.clientRequestId,
                        "commandKind": "artifact_decision",
                        "resourceIdentity": {"artifactId": artifact_id},
                        "normalizedBody": normalized_body,
                        "requestFingerprint": fingerprint,
                    },
                    "job": job,
                }
                await dependencies.commands.create_artifact_decision(
                    command_id=command_id,
                    user_id=user_id,
                    task_id=task.id,
                    artifact_id=artifact_id,
                    decision=request.decision,
                    client_request_id=request.clientRequestId,
                    payload=payload,
                    result=accepted.model_dump(mode="json"),
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
    fingerprint: str,
) -> ArtifactDecisionAcceptedResponse:
    if command.kind != "artifact_decision" or command.result is None:
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="客户端请求标识已用于其他操作",
        )
    metadata = parse_command_envelope(command.payload)
    if (
        metadata is None
        or metadata.commandKind != "artifact_decision"
        or metadata.requestFingerprint != fingerprint
    ):
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="同一幂等标识已绑定其他请求",
        )
    persisted_result = command.result
    nested = persisted_result.get(ARTIFACT_DECISION_ACCEPTED_RESPONSE_FIELD)
    source = nested if isinstance(nested, dict) else persisted_result
    accepted_result = {
        field: source[field]
        for field in ArtifactDecisionAcceptedResponse.model_fields
        if field in source
    }
    try:
        return ArtifactDecisionAcceptedResponse.model_validate(accepted_result)
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code="WRITING_COMMAND_RESULT_INVALID",
            message="写作命令受理结果无效",
        ) from exc


async def _resolve_decision_replay(
    session: AsyncSession,
    command_lookup: ReviewCommandLookupPort,
    resolver: Callable[..., Awaitable[IdempotencyResolution | None]],
    *,
    user_id: str,
    client_request_id: str,
    fingerprint: str,
) -> ArtifactDecisionAcceptedResponse | None:
    resolution = await resolver(
        session,
        user_id=user_id,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
    )
    if resolution is None:
        return None
    if resolution.record_kind != "writing_command":
        raise _idempotency_reused(client_request_id)
    command = await command_lookup.get_by_idempotency_key(
        user_id,
        client_request_id,
    )
    if command is None or command.id != resolution.record_id:
        raise _idempotency_reused(client_request_id)
    return _accepted_response_from_command(command, fingerprint)


def _idempotency_reused(client_request_id: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        message="同一幂等标识已绑定其他请求",
        details={"clientRequestId": client_request_id},
    )


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
