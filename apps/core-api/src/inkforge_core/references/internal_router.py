from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request, Response
from inkforge_contracts.jwt_claims import ServiceJwtClaims, ServiceScope

from ..config import Settings
from ..errors import ApiError
from .router import get_reference_service
from .schemas import (
    CompleteReferenceIndexRequest,
    FailReferenceIndexRequest,
    ReferenceIndexContextRequest,
    ReferenceIndexContextResponse,
    ReferenceMaterialResponse,
)
from .service import ReferenceService

router = APIRouter(
    prefix="/internal/v1",
    tags=["内部检索索引回调"],
    include_in_schema=False,
)


class RagCallbackVerifier(Protocol):
    async def verify_request(self, **kwargs: object) -> ServiceJwtClaims: ...


def get_rag_callback_verifier(request: Request) -> RagCallbackVerifier:
    settings = cast(Settings, request.app.state.settings)
    if not settings.trusted_agent_cidrs:
        raise ApiError(
            status_code=503,
            code="AGENT_SERVICE_NETWORK_UNAVAILABLE",
            message="智能体服务可信网段未配置",
        )
    peer_host = request.client.host if request.client is not None else None
    try:
        peer_address = ip_address(peer_host) if peer_host is not None else None
    except ValueError:
        peer_address = None
    if peer_address is None or not any(
        peer_address in ip_network(cidr) for cidr in settings.trusted_agent_cidrs
    ):
        raise ApiError(
            status_code=403,
            code="AGENT_SERVICE_NETWORK_FORBIDDEN",
            message="智能体服务直接对端不在可信网段内",
        )
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


@router.post(
    "/novels/{novel_id}/references/{reference_id}/index-context",
    response_model=ReferenceIndexContextResponse,
)
async def get_reference_index_context(
    novel_id: str,
    reference_id: str,
    body: ReferenceIndexContextRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> ReferenceIndexContextResponse:
    await _verify_callback(
        request,
        verifier,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=novel_id,
    )
    value = await service.get_index_context(
        body.userId,
        novel_id,
        reference_id,
        body.expectedContentHash,
    )
    return ReferenceIndexContextResponse.model_validate(value)


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
