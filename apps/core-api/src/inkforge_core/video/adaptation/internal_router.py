"""Agent 回传章节影视化 checkpoint、候选和终态的签名接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_contracts.video_adaptation import (
    VideoAdaptationCheckpointCallback,
    VideoAdaptationFailureCallback,
    VideoAdaptationPlanCompletionCallback,
    VideoAdaptationPromptCompletionCallback,
    VideoAdaptationWorkflowProgressQuery,
    VideoAdaptationWorkflowProgressResponse,
)

from ...errors import ApiError
from ...references.internal_router import RagCallbackVerifier, get_rag_callback_verifier
from .router import get_video_adaptation_service
from .service import VideoAdaptationService

router = APIRouter(
    prefix="/internal/v1/video/adaptations",
    tags=["内部章节影视化回调"],
    include_in_schema=False,
)

Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]
Service = Annotated[VideoAdaptationService, Depends(get_video_adaptation_service)]


def _require_path(adaptation_id: str, body_adaptation_id: str) -> None:
    if adaptation_id != body_adaptation_id:
        raise ApiError(
            status_code=403,
            code="VIDEO_ADAPTATION_CALLBACK_RESOURCE_MISMATCH",
            message="章节影视化回调路径与请求体不一致",
        )


async def _verify(
    request: Request,
    verifier: RagCallbackVerifier,
    *,
    task_id: str,
    run_id: str,
    novel_id: str,
) -> None:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise ApiError(
            status_code=401,
            code="SERVICE_AUTHENTICATION_FAILED",
            message="服务身份认证失败",
        )
    await verifier.verify_request(
        token=authorization.removeprefix("Bearer "),
        body=await request.body(),
        http_method=request.method,
        http_path=request.url.path,
        query_string=request.scope.get("query_string", b""),
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_timestamp=request.headers.get("X-InkForge-Timestamp", ""),
        body_sha256=request.headers.get("X-InkForge-Body-SHA256", ""),
        required_scope=ServiceScope.VIDEO_WRITE,
        task_id=task_id,
        run_id=run_id,
        novel_id=novel_id,
    )


@router.post(
    "/{adaptation_id}/progress",
    response_model=VideoAdaptationWorkflowProgressResponse,
)
async def get_progress(
    adaptation_id: str,
    body: VideoAdaptationWorkflowProgressQuery,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> VideoAdaptationWorkflowProgressResponse:
    _require_path(adaptation_id, body.adaptationId)
    await _verify(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    return await service.get_progress(body)


@router.post(
    "/{adaptation_id}/checkpoint",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def save_checkpoint(
    adaptation_id: str,
    body: VideoAdaptationCheckpointCallback,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    _require_path(adaptation_id, body.adaptationId)
    await _verify(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.save_checkpoint(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{adaptation_id}/plan/complete",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def complete_plan(
    adaptation_id: str,
    body: VideoAdaptationPlanCompletionCallback,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    _require_path(adaptation_id, body.adaptationId)
    await _verify(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.complete_plan(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{adaptation_id}/prompts/complete",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def complete_prompts(
    adaptation_id: str,
    body: VideoAdaptationPromptCompletionCallback,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    _require_path(adaptation_id, body.adaptationId)
    await _verify(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.complete_prompts(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{adaptation_id}/fail",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def fail_task(
    adaptation_id: str,
    body: VideoAdaptationFailureCallback,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    _require_path(adaptation_id, body.adaptationId)
    await _verify(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.fail_task(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
