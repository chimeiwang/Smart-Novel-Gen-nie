from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .schemas import (
    CreateMessageRequest,
    CreateWritingSessionRequest,
    MessageResponse,
    ResumeWritingRunRequest,
    ResumeWritingRunResponse,
    StartWritingRunRequest,
    UpdateWritingSessionRequest,
    WritingRunResponse,
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
TaskRepository = Annotated[WritingTaskRepository, Depends(get_writing_task_repository)]
EventStore = Annotated[object, Depends(get_writing_event_store)]


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
    response_model=WritingRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_writing_run(
    body: StartWritingRunRequest,
    user: User,
    service: TaskService,
) -> WritingRunResponse:
    return await service.start(user.id, body)


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
    await service.resume(user.id, task_id, body.writingSessionId)
    return ResumeWritingRunResponse(accepted=True, taskId=task_id)


@router.get("/runs/{task_id}/events", response_class=StreamingResponse)
async def stream_writing_run_events(
    task_id: str,
    user: User,
    repository: TaskRepository,
    store: EventStore,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    await repository.require_task(user.id, task_id)
    return StreamingResponse(
        stream_task_events(store, task_id, last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
