from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from inkforge_contracts.jwt_claims import ServiceScope

from ..errors import ApiError
from ..references.internal_router import RagCallbackVerifier, get_rag_callback_verifier
from .router import get_quality_service
from .schemas import (
    QualityRunContextRequest,
    QualityRunContextResponse,
    QualityRunFailureRequest,
    QualityRunSuccessRequest,
)
from .service import QualityService

router = APIRouter(
    prefix="/internal/v1/quality-checks",
    tags=["内部质量检查"],
    include_in_schema=False,
)

Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]
Service = Annotated[QualityService, Depends(get_quality_service)]


async def _verify(
    request: Request,
    verifier: RagCallbackVerifier,
    *,
    user_id: str,
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
    del user_id
    await verifier.verify_request(
        token=authorization.removeprefix("Bearer "),
        body=await request.body(),
        http_method=request.method,
        http_path=request.url.path,
        query_string=request.scope.get("query_string", b""),
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_timestamp=request.headers.get("X-InkForge-Timestamp", ""),
        body_sha256=request.headers.get("X-InkForge-Body-SHA256", ""),
        required_scope=ServiceScope.QUALITY_WRITE,
        task_id=task_id,
        run_id=run_id,
        novel_id=novel_id,
    )


def _require_novel(context: dict[str, object], expected_novel_id: str) -> None:
    if context.get("novelId") != expected_novel_id:
        raise ApiError(
            status_code=403,
            code="QUALITY_RESOURCE_MISMATCH",
            message="质量检查资源绑定不匹配",
        )


@router.post("/{check_id}/context", response_model=QualityRunContextResponse)
async def get_quality_context(
    check_id: str,
    body: QualityRunContextRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> QualityRunContextResponse:
    await _verify(
        request,
        verifier,
        user_id=body.userId,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    context = await service.get_run_context(
        body.userId,
        check_id,
        body.sourceTaskId,
        body.message,
        body.runId,
    )
    _require_novel(context, body.novelId)
    return QualityRunContextResponse.model_validate(context)


@router.put("/{check_id}/success", status_code=204)
async def complete_quality(
    check_id: str,
    body: QualityRunSuccessRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    await _verify(
        request,
        verifier,
        user_id=body.userId,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.complete_run(
        body.userId,
        check_id,
        body.model_dump(exclude={"userId", "novelId", "taskId", "runId"}),
        run_id=body.runId,
        novel_id=body.novelId,
    )
    return Response(status_code=204)


@router.put("/{check_id}/failure", status_code=204)
async def fail_quality(
    check_id: str,
    body: QualityRunFailureRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    await _verify(
        request,
        verifier,
        user_id=body.userId,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await service.fail_run(
        body.userId,
        check_id,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    return Response(status_code=204)
