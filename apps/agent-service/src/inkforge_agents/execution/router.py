"""Core -> Agent V2 execution 内部入口。"""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from inkforge_contracts.execution import (
    ExecutionCancelAccepted,
    ExecutionCancelRequest,
    ExecutionStepAccepted,
    ExecutionStepRequest,
)
from inkforge_contracts.jwt_claims import ServiceScope
from pydantic import BaseModel, ConfigDict

from ..runs.router import CoreRequestVerifier, get_verifier
from .executor import ExecutionCapabilityError
from .journal import (
    ExecutionJournalConflictError,
    ExecutionJournalError,
    ExecutionJournalStaleFenceError,
)
from .registry import ExecutionRegistryError
from .service import (
    ExecutionAdmissionSaturatedError,
    ExecutionService,
    ExecutionServiceUnavailableError,
)


def get_execution_service(request: Request) -> ExecutionService:
    service = cast(
        ExecutionService | None,
        getattr(request.app.state, "execution_service", None),
    )
    if service is None:
        raise HTTPException(status_code=503, detail="V2 execution 服务暂时不可用")
    return service


Service = Annotated[ExecutionService, Depends(get_execution_service)]
Verifier = Annotated[CoreRequestVerifier, Depends(get_verifier)]

router = APIRouter(prefix="/internal/v1/executions", include_in_schema=False)


class ExecutionAdmissionSaturatedResponse(BaseModel):
    """仅表示 Agent 已证明未创建 journal 的可安全快速重投。"""

    model_config = ConfigDict(extra="forbid")

    protocolVersion: Literal["2.0"] = "2.0"
    errorCode: Literal["EXECUTION_ADMISSION_SATURATED"] = (
        "EXECUTION_ADMISSION_SATURATED"
    )
    retryable: Literal[True] = True
    retryAfterSeconds: int


@router.post("", response_model=ExecutionStepAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_execution(
    body: ExecutionStepRequest,
    request: Request,
    service: Service,
    verifier: Verifier,
) -> ExecutionStepAccepted | JSONResponse:
    await _verify(
        request,
        verifier,
        scope=ServiceScope.EXECUTION_SUBMIT,
        task_id=body.stepId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    _require_idempotency_header(request, body.idempotencyKey)
    try:
        return await service.submit(body)
    except ExecutionAdmissionSaturatedError as exc:
        retry_after = exc.retry_after_seconds
        payload = ExecutionAdmissionSaturatedResponse(retryAfterSeconds=retry_after)
        return JSONResponse(
            status_code=503,
            content=payload.model_dump(mode="json"),
            headers={"Retry-After": str(retry_after)},
        )
    except (
        ExecutionCapabilityError,
        ExecutionRegistryError,
        ExecutionJournalConflictError,
        ExecutionJournalStaleFenceError,
    ):
        raise HTTPException(
            status_code=409,
            detail="V2 execution 请求与已发布能力或执行身份冲突",
        ) from None
    except ExecutionJournalError:
        raise HTTPException(status_code=503, detail="V2 execution journal 暂时不可用") from None
    except ExecutionServiceUnavailableError:
        raise HTTPException(status_code=503, detail="V2 execution 基础设施保护门已关闭") from None


@router.put(
    "/{job_id}/cancel",
    response_model=ExecutionCancelAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_execution(
    job_id: str,
    body: ExecutionCancelRequest,
    request: Request,
    service: Service,
    verifier: Verifier,
) -> ExecutionCancelAccepted:
    await _verify(
        request,
        verifier,
        scope=ServiceScope.EXECUTION_CANCEL,
        task_id=body.stepId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    _require_idempotency_header(request, body.cancelRequestId)
    if job_id != body.jobId:
        raise HTTPException(status_code=409, detail="取消路径 jobId 与请求正文不一致")
    try:
        return await service.cancel(body)
    except ExecutionJournalConflictError:
        raise HTTPException(status_code=409, detail="V2 execution 取消身份冲突") from None
    except ExecutionJournalError:
        raise HTTPException(status_code=503, detail="V2 execution journal 暂时不可用") from None


async def _verify(
    request: Request,
    verifier: CoreRequestVerifier,
    *,
    scope: ServiceScope,
    task_id: str,
    run_id: str,
    novel_id: str | None,
) -> None:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="服务身份认证失败")
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


def _require_idempotency_header(request: Request, expected: str) -> None:
    if request.headers.get("Idempotency-Key") != expected:
        raise HTTPException(status_code=409, detail="Idempotency-Key 与 execution 请求不一致")
