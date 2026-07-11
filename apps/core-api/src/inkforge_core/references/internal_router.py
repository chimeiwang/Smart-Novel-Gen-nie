from __future__ import annotations

from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request, Response
from inkforge_contracts.jwt_claims import ServiceJwtClaims, ServiceScope

from ..errors import ApiError
from .router import get_reference_service
from .schemas import (
    CompleteReferenceIndexRequest,
    FailReferenceIndexRequest,
    ReferenceMaterialResponse,
)
from .service import ReferenceService

router = APIRouter(prefix="/internal", tags=["内部检索索引回调"])


class RagCallbackVerifier(Protocol):
    async def verify_request(self, **kwargs: object) -> ServiceJwtClaims: ...


def get_rag_callback_verifier(request: Request) -> RagCallbackVerifier:
    verifier = cast(
        RagCallbackVerifier | None,
        getattr(request.app.state, "rag_callback_verifier", None),
    )
    if verifier is None:
        raise ApiError(
            status_code=503,
            code="RAG_CALLBACK_AUTH_UNAVAILABLE",
            message="索引回调认证暂时不可用",
        )
    return verifier


Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]
Service = Annotated[ReferenceService, Depends(get_reference_service)]


async def _verify_callback(
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
        required_scope=ServiceScope.RAG_INDEX_WRITE,
        task_id=task_id,
        run_id=run_id,
        novel_id=novel_id,
    )


@router.put(
    "/novels/{novel_id}/references/{reference_id}/index-success",
    response_model=ReferenceMaterialResponse,
)
async def complete_reference_index(
    novel_id: str,
    reference_id: str,
    body: CompleteReferenceIndexRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> ReferenceMaterialResponse:
    await _verify_callback(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=novel_id,
    )
    return await service.complete_index(
        novel_id,
        reference_id,
        body.expectedContentHash,
        body.embeddings,
    )


@router.put(
    "/novels/{novel_id}/references/{reference_id}/index-failure",
    status_code=204,
)
async def fail_reference_index(
    novel_id: str,
    reference_id: str,
    body: FailReferenceIndexRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> Response:
    await _verify_callback(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=novel_id,
    )
    await service.fail_index(
        novel_id,
        reference_id,
        body.expectedContentHash,
        body.message,
    )
    return Response(status_code=204)
