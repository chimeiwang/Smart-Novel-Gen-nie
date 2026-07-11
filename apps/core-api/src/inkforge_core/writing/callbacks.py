from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response, status
from inkforge_contracts.events import (
    AgentEvent,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from inkforge_contracts.jwt_claims import ServiceScope

from ..errors import ApiError
from ..references.internal_router import RagCallbackVerifier, get_rag_callback_verifier
from .tasks import WritingCallbackService, WritingTaskRepository

router = APIRouter(
    prefix="/internal/v1/writing/runs",
    tags=["内部写作运行回调"],
    include_in_schema=False,
)


def get_callback_service(request: Request) -> WritingCallbackService:
    service = cast(
        WritingCallbackService | None,
        getattr(request.app.state, "writing_callback_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="WRITING_CALLBACK_UNAVAILABLE",
            message="写作运行回调暂时不可用",
        )
    return service


def get_task_repository(request: Request) -> WritingTaskRepository:
    repository = cast(
        WritingTaskRepository | None,
        getattr(request.app.state, "writing_task_repository", None),
    )
    if repository is None:
        raise ApiError(
            status_code=503,
            code="WRITING_CALLBACK_UNAVAILABLE",
            message="写作运行回调暂时不可用",
        )
    return repository


Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]
CallbackService = Annotated[WritingCallbackService, Depends(get_callback_service)]
TaskRepository = Annotated[WritingTaskRepository, Depends(get_task_repository)]


async def _verify(
    request: Request,
    verifier: RagCallbackVerifier,
    repository: WritingTaskRepository,
    *,
    run_id: str,
    body_run_id: str,
    task_id: str,
    scope: ServiceScope,
) -> tuple[str, str]:
    if run_id != body_run_id:
        raise ApiError(
            status_code=409,
            code="RUN_ID_MISMATCH",
            message="路径运行标识与回调载荷不一致",
        )
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise ApiError(
            status_code=401,
            code="SERVICE_AUTHENTICATION_FAILED",
            message="服务身份认证失败",
        )
    novel_id, user_id = await repository.get_task_resources(task_id)
    await verifier.verify_request(
        token=authorization.removeprefix("Bearer "),
        body=await request.body(),
        http_method=request.method,
        http_path=request.url.path,
        query_string=request.scope.get("query_string", b""),
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_timestamp=request.headers.get("X-InkForge-Timestamp", ""),
        body_sha256=request.headers.get("X-InkForge-Body-SHA256", ""),
        required_scope=scope,
        task_id=task_id,
        run_id=run_id,
        novel_id=novel_id,
    )
    return novel_id, user_id


@router.post("/{run_id}/events", status_code=status.HTTP_204_NO_CONTENT)
async def accept_event(
    run_id: str,
    body: AgentEvent,
    request: Request,
    verifier: Verifier,
    service: CallbackService,
    repository: TaskRepository,
) -> Response:
    await _verify(
        request,
        verifier,
        repository,
        run_id=run_id,
        body_run_id=body.runId,
        task_id=body.taskId,
        scope=ServiceScope.CALLBACK_EVENT,
    )
    await service.accept_event(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{run_id}/checkpoint", status_code=status.HTTP_204_NO_CONTENT)
async def save_checkpoint(
    run_id: str,
    body: CheckpointCallback,
    request: Request,
    verifier: Verifier,
    service: CallbackService,
    repository: TaskRepository,
) -> Response:
    novel_id, user_id = await _verify(
        request,
        verifier,
        repository,
        run_id=run_id,
        body_run_id=body.runId,
        task_id=body.taskId,
        scope=ServiceScope.CALLBACK_CHECKPOINT,
    )
    await service.save_checkpoint(body, user_id=user_id, novel_id=novel_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{run_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_run(
    run_id: str,
    body: RunCompletionCallback,
    request: Request,
    verifier: Verifier,
    service: CallbackService,
    repository: TaskRepository,
) -> Response:
    await _verify(
        request,
        verifier,
        repository,
        run_id=run_id,
        body_run_id=body.runId,
        task_id=body.taskId,
        scope=ServiceScope.CALLBACK_COMPLETE,
    )
    await service.complete(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{run_id}/fail", status_code=status.HTTP_204_NO_CONTENT)
async def fail_run(
    run_id: str,
    body: RunFailureCallback,
    request: Request,
    verifier: Verifier,
    service: CallbackService,
    repository: TaskRepository,
) -> Response:
    await _verify(
        request,
        verifier,
        repository,
        run_id=run_id,
        body_run_id=body.runId,
        task_id=body.taskId,
        scope=ServiceScope.CALLBACK_FAIL,
    )
    await service.fail(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
