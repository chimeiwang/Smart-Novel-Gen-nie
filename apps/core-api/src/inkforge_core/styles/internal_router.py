from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from inkforge_contracts.jwt_claims import ServiceScope

from ..errors import ApiError
from ..references.internal_router import RagCallbackVerifier, get_rag_callback_verifier
from .router import get_style_service
from .schemas import (
    PortraitFailureRequest,
    PortraitProcessingRequest,
    PortraitSuccessRequest,
    PortraitTaskResponse,
)
from .service import StyleService

router = APIRouter(
    prefix="/internal/v1/styles",
    tags=["内部文风画像回调"],
    include_in_schema=False,
)

Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]
Service = Annotated[StyleService, Depends(get_style_service)]


async def _verify_callback(
    request: Request,
    verifier: RagCallbackVerifier,
    *,
    style_id: str,
    task_id: str,
    run_id: str,
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
        required_scope=ServiceScope.PORTRAIT_WRITE,
        task_id=task_id,
        run_id=run_id,
        novel_id=f"style:{style_id}",
    )


@router.put(
    "/{style_id}/portrait-tasks/{task_id}/processing",
    response_model=PortraitTaskResponse,
)
async def mark_processing(
    style_id: str,
    task_id: str,
    body: PortraitProcessingRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> PortraitTaskResponse:
    await _verify_callback(
        request,
        verifier,
        style_id=style_id,
        task_id=task_id,
        run_id=body.runId,
    )
    return await service.mark_processing(style_id, task_id, body)


@router.put(
    "/{style_id}/portrait-tasks/{task_id}/success",
    response_model=PortraitTaskResponse,
)
async def complete_portrait(
    style_id: str,
    task_id: str,
    body: PortraitSuccessRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> PortraitTaskResponse:
    await _verify_callback(
        request,
        verifier,
        style_id=style_id,
        task_id=task_id,
        run_id=body.runId,
    )
    return await service.complete_portrait(style_id, task_id, body)


@router.put(
    "/{style_id}/portrait-tasks/{task_id}/failure",
    response_model=PortraitTaskResponse,
)
async def fail_portrait(
    style_id: str,
    task_id: str,
    body: PortraitFailureRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> PortraitTaskResponse:
    await _verify_callback(
        request,
        verifier,
        style_id=style_id,
        task_id=task_id,
        run_id=body.runId,
    )
    return await service.fail_portrait(style_id, task_id, body)
