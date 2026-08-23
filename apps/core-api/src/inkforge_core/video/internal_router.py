"""Agent 回传视频规划结果的签名内部接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_contracts.video import (
    VideoPlanCallReservationRequest,
    VideoPlanCallReservationResponse,
    VideoPlanCompletionCallback,
    VideoPlanFailureCallback,
    VideoPlanProgressQuery,
    VideoPlanProgressResponse,
    VideoStoryPlanCheckpointCallback,
)

from ..errors import ApiError
from ..references.internal_router import RagCallbackVerifier, get_rag_callback_verifier
from .router import get_video_service
from .service import VideoService

router = APIRouter(
    prefix="/internal/v1/video/scenes",
    tags=["内部视频规划回调"],
    include_in_schema=False,
)

Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]
Service = Annotated[VideoService, Depends(get_video_service)]


def _require_scene_path_matches_body(scene_id: str, body_scene_id: str) -> None:
    """在验签前拒绝路径与请求体交叉绑定，所有视频内部接口共用。"""

    if body_scene_id != scene_id:
        raise ApiError(
            status_code=403,
            code="VIDEO_CALLBACK_RESOURCE_MISMATCH",
            message="视频回调路径与请求体场景不一致",
        )


async def _verify_callback(
    request: Request,
    verifier: RagCallbackVerifier,
    *,
    task_id: str,
    run_id: str,
    novel_id: str,
) -> None:
    """同时校验直接对端、签名、请求体摘要和视频写权限。"""

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


@router.post("/{scene_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_plan(
    scene_id: str,
    body: VideoPlanCompletionCallback,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    """保存候选方案并创建等待用户确认的 ReviewArtifact。"""

    _require_scene_path_matches_body(scene_id, body.sceneId)
    await _verify_callback(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.complete_plan(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{scene_id}/fail", status_code=status.HTTP_204_NO_CONTENT)
async def fail_plan(
    scene_id: str,
    body: VideoPlanFailureCallback,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    """保存完整失败事实，允许用户后续重试。"""

    _require_scene_path_matches_body(scene_id, body.sceneId)
    await _verify_callback(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.fail_plan(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{scene_id}/progress", response_model=VideoPlanProgressResponse)
async def get_plan_progress(
    scene_id: str,
    body: VideoPlanProgressQuery,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> VideoPlanProgressResponse:
    """读取当前任务的耐久阶段进度，终态不会泄露故事检查点。"""

    _require_scene_path_matches_body(scene_id, body.sceneId)
    await _verify_callback(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    return await service.get_plan_progress(body)


@router.post("/{scene_id}/story-checkpoint", status_code=status.HTTP_204_NO_CONTENT)
async def save_story_plan_checkpoint(
    scene_id: str,
    body: VideoStoryPlanCheckpointCallback,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    """幂等保存第一阶段规范，不创建或更新 ReviewArtifact。"""

    _require_scene_path_matches_body(scene_id, body.sceneId)
    await _verify_callback(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.save_story_plan_checkpoint(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{scene_id}/call-reservations",
    response_model=VideoPlanCallReservationResponse,
)
async def reserve_plan_call(
    scene_id: str,
    body: VideoPlanCallReservationRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> VideoPlanCallReservationResponse:
    """在每次供应商调用前，以任务行锁原子预留一次全局调用预算。"""

    _require_scene_path_matches_body(scene_id, body.sceneId)
    await _verify_callback(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    return await service.reserve_plan_call(body)
