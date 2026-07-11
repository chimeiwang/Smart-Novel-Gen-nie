from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from inkforge_contracts.jwt_claims import ServiceScope

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from ..references.internal_router import RagCallbackVerifier, get_rag_callback_verifier
from .schemas import (
    AuthorizeModelCallRequest,
    AuthorizeModelCallResponse,
    BillingSummaryResponse,
    BillingUsageResponse,
    ReportModelUsageRequest,
    UsageChargeResponse,
)
from .service import BillingService

router = APIRouter(prefix="/billing", tags=["计费"])
internal_router = APIRouter(
    prefix="/internal/v1/billing",
    tags=["内部模型计费"],
    include_in_schema=False,
)


def get_billing_service(request: Request) -> BillingService:
    service = cast(BillingService | None, getattr(request.app.state, "billing_service", None))
    if service is None:
        raise ApiError(status_code=503, code="BILLING_UNAVAILABLE", message="计费服务暂时不可用")
    return service


Service = Annotated[BillingService, Depends(get_billing_service)]
Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]


@router.get("/summary", response_model=BillingSummaryResponse)
async def get_summary(
    user: Annotated[AuthUser, Depends(get_current_user)], service: Service
) -> BillingSummaryResponse:
    return await service.summary(user.id)


@router.get("/usage", response_model=BillingUsageResponse)
async def get_usage(
    user: Annotated[AuthUser, Depends(get_current_user)], service: Service
) -> BillingUsageResponse:
    return await service.usage(user.id)


async def _verify_internal_request(
    request: Request,
    verifier: RagCallbackVerifier,
    *,
    scope: ServiceScope,
    task_id: str,
    run_id: str,
    novel_id: str,
) -> None:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise ApiError(
            status_code=401, code="SERVICE_AUTHENTICATION_FAILED", message="服务身份认证失败"
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
        required_scope=scope,
        task_id=task_id,
        run_id=run_id,
        novel_id=novel_id,
    )


@internal_router.post("/authorize", response_model=AuthorizeModelCallResponse)
async def authorize_model_call(
    body: AuthorizeModelCallRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> AuthorizeModelCallResponse:
    await _verify_internal_request(
        request,
        verifier,
        scope=ServiceScope.BILLING_AUTHORIZE,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    return await service.authorize(body)


@internal_router.post("/usage", response_model=UsageChargeResponse)
async def report_model_usage(
    body: ReportModelUsageRequest,
    request: Request,
    verifier: Verifier,
    service: Service,
) -> UsageChargeResponse:
    await _verify_internal_request(
        request,
        verifier,
        scope=ServiceScope.BILLING_USAGE_WRITE,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    return await service.charge(body)
