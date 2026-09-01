from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .cancellation import WritingRunCancellationService
from .commands import WritingRunCommandRepository
from .outbox import WritingOutboxRepository
from .schemas import (
    CancelWritingRunPublicResponse,
    CancelWritingRunRequest,
    CreateMessageRequest,
    CreateWritingSessionRequest,
    MessageResponse,
    ResumeWritingRunRequest,
    ResumeWritingRunResponse,
    UpdateWritingSessionRequest,
    WritingRunListResponse,
    WritingRunOutcome,
    WritingRunStartRequest,
    WritingRunStartResponse,
    WritingRunStatusPublicResponse,
    WritingSessionDetail,
    WritingSessionListItem,
    WritingSessionResponse,
)
from .service import WritingService
from .sse import stream_task_events
from .tasks import WritingTaskRepository, WritingTaskService

router = APIRouter(prefix="/writing", tags=["写作会话"])


def get_writing_service(request: Request) -> WritingService:
    service = cast(WritingService | None, getattr(request.app.state, "writing_service", None))
    if service is None:
        raise ApiError(status_code=503, code="WRITING_UNAVAILABLE", message="写作服务暂时不可用")
    return service


def get_writing_task_service(request: Request) -> WritingTaskService:
    service = cast(
        WritingTaskService | None,
        getattr(request.app.state, "writing_task_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="WRITING_TASK_UNAVAILABLE",
            message="写作任务服务暂时不可用",
        )
    return service


def get_writing_cancellation_service(request: Request) -> WritingRunCancellationService:
    service = cast(
        WritingRunCancellationService | None,
        getattr(request.app.state, "writing_cancellation_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="WRITING_TASK_UNAVAILABLE",
            message="写作任务服务暂时不可用",
        )
    return service


def get_writing_outbox_repository(request: Request) -> WritingOutboxRepository:
    repository = cast(
        WritingOutboxRepository | None,
        getattr(request.app.state, "writing_outbox_repository", None),
    )
    if repository is None:
        raise ApiError(
            status_code=503,
            code="WRITING_OUTBOX_UNAVAILABLE",
            message="写作事件发件箱暂时不可用",
        )
    return repository


def get_writing_task_repository(request: Request) -> WritingTaskRepository:
    repository = cast(
        WritingTaskRepository | None,
        getattr(request.app.state, "writing_task_repository", None),
    )
    if repository is None:
        raise ApiError(
            status_code=503,
            code="WRITING_TASK_UNAVAILABLE",
            message="写作任务服务暂时不可用",
        )
    return repository


def get_writing_run_command_repository(request: Request) -> WritingRunCommandRepository:
    repository = cast(
        WritingRunCommandRepository | None,
        getattr(request.app.state, "writing_command_repository", None),
    )
    if repository is None:
        raise ApiError(
            status_code=503,
            code="WRITING_TASK_UNAVAILABLE",
            message="写作任务服务暂时不可用",
        )
    return repository


def get_writing_event_store(request: Request) -> object:
    store = getattr(request.app.state, "writing_event_store", None)
    if store is None:
        raise ApiError(
            status_code=503,
            code="WRITING_EVENTS_UNAVAILABLE",
            message="写作事件流暂时不可用",
        )
    return store


Service = Annotated[WritingService, Depends(get_writing_service)]
User = Annotated[AuthUser, Depends(get_current_user)]
TaskService = Annotated[WritingTaskService, Depends(get_writing_task_service)]
CancellationService = Annotated[
    WritingRunCancellationService, Depends(get_writing_cancellation_service)
]
OutboxRepository = Annotated[
    WritingOutboxRepository,
    Depends(get_writing_outbox_repository),
]
TaskRepository = Annotated[WritingTaskRepository, Depends(get_writing_task_repository)]
RunCommandRepository = Annotated[
    WritingRunCommandRepository,
    Depends(get_writing_run_command_repository),
]
EventStore = Annotated[object, Depends(get_writing_event_store)]

_WRITING_RUN_SSE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "持续输出 V1 事件；V2 首帧为 RunSnapshot，后续为 WorkflowEventEnvelope。",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
        "x-inkforge-v2-sse": {
            "firstFrame": {
                "event": "run_snapshot",
                "schema": "inkforge_contracts.workflow_events.RunSnapshot",
            },
            "subsequentFrames": {
                "schema": "inkforge_contracts.workflow_events.WorkflowEventEnvelope",
            },
        },
    }
}


@router.get("/sessions", response_model=list[WritingSessionListItem])
async def list_writing_sessions(
    user: User,
    service: Service,
    novel_id: Annotated[str, Query(alias="novelId", min_length=1)],
    chapter_id: Annotated[str | None, Query(alias="chapterId", min_length=1)] = None,
) -> list[WritingSessionListItem]:
    return await service.list_sessions(user.id, novel_id, chapter_id)


@router.post(
    "/sessions",
    response_model=WritingSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_writing_session(
    body: CreateWritingSessionRequest, user: User, service: Service
) -> WritingSessionResponse:
    return await service.create_session(user.id, body)


@router.get("/sessions/{session_id}", response_model=WritingSessionDetail)
async def get_writing_session(
    session_id: str, user: User, service: Service
) -> WritingSessionDetail:
    return await service.get_session(user.id, session_id)


@router.patch("/sessions/{session_id}", response_model=WritingSessionResponse)
async def update_writing_session(
    session_id: str,
    body: UpdateWritingSessionRequest,
    user: User,
    service: Service,
) -> WritingSessionResponse:
    return await service.update_session(user.id, session_id, body)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_writing_session(session_id: str, user: User, service: Service) -> Response:
    await service.delete_session(user.id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_writing_message(
    session_id: str,
    body: CreateMessageRequest,
    user: User,
    service: Service,
) -> MessageResponse:
    return await service.add_message(user.id, session_id, body)


@router.post(
    "/runs",
    response_model=WritingRunStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_writing_run(
    body: WritingRunStartRequest,
    user: User,
    service: TaskService,
) -> WritingRunStartResponse:
    return await service.start(user.id, body)


@router.get("/runs", response_model=WritingRunListResponse)
async def list_writing_runs(
    user: User,
    repository: RunCommandRepository,
    novel_id: Annotated[str, Query(alias="novelId", min_length=1)],
    chapter_id: Annotated[str | None, Query(alias="chapterId", min_length=1)] = None,
    writing_session_id: Annotated[
        str | None, Query(alias="writingSessionId", min_length=1)
    ] = None,
    operation: Annotated[str | None, Query(min_length=1)] = None,
    outcome: Annotated[
        Literal[
            "queued",
            "running",
            "waiting_user",
            "succeeded",
            "failed",
            "cancelled",
            "inconsistent",
        ]
        | None,
        Query(),
    ] = None,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> WritingRunListResponse:
    return await repository.list_run_statuses(
        user.id,
        novel_id=novel_id,
        chapter_id=chapter_id,
        writing_session_id=writing_session_id,
        operation=operation,
        outcome=outcome,
        cursor=cursor,
        limit=limit,
    )


@router.get("/runs/{task_id}", response_model=WritingRunStatusPublicResponse)
async def get_writing_run_status(
    task_id: str,
    user: User,
    service: TaskService,
) -> WritingRunStatusPublicResponse:
    return await service.get_status(user.id, task_id)


@router.post(
    "/runs/{task_id}/resume",
    response_model=ResumeWritingRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_writing_run(
    task_id: str,
    body: ResumeWritingRunRequest,
    user: User,
    service: TaskService,
) -> ResumeWritingRunResponse:
    return await service.resume(user.id, task_id, body)


@router.post(
    "/runs/{task_id}/cancel",
    response_model=CancelWritingRunPublicResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_writing_run(
    task_id: str,
    body: CancelWritingRunRequest,
    user: User,
    service: CancellationService,
) -> CancelWritingRunPublicResponse:
    return await service.cancel(user.id, task_id, body)


@router.get(
    "/runs/{task_id}/events",
    response_class=StreamingResponse,
    responses=_WRITING_RUN_SSE_RESPONSES,
)
async def stream_writing_run_events(
    task_id: str,
    user: User,
    repository: TaskRepository,
    store: EventStore,
    service: TaskService,
    outbox_repository: OutboxRepository,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    await repository.require_task(user.id, task_id)

    async def load_outcome() -> WritingRunOutcome:
        return (await service.get_status(user.id, task_id)).outcome

    return StreamingResponse(
        stream_task_events(
            store,
            task_id,
            last_event_id=last_event_id,
            outcome_provider=load_outcome,
            event_visibility_provider=outbox_repository.replay_dispositions,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
