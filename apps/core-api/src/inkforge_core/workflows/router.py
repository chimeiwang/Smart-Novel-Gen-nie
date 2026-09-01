from __future__ import annotations

from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request
from inkforge_contracts.execution import (
    ExecutionCallbackReceipt,
    ExecutionStepFailure,
    ExecutionStepProgress,
    ExecutionStepResult,
)
from inkforge_contracts.jwt_claims import ServiceScope

from ..errors import ApiError
from ..references.internal_router import RagCallbackVerifier, get_rag_callback_verifier

router = APIRouter(
    prefix="/internal/v1/workflow-runs",
    tags=["内部耐久 Workflow 回调"],
    include_in_schema=False,
)


class WorkflowExecutionCallbackService(Protocol):
    """Python Core 回滚镜像的 V2-aware 端口；生产实现由 Java Core 提供。"""

    async def novel_id(self, run_id: str, step_id: str) -> str | None: ...

    async def progress(
        self, body: ExecutionStepProgress
    ) -> ExecutionCallbackReceipt: ...

    async def result(self, body: ExecutionStepResult) -> ExecutionCallbackReceipt: ...

    async def failure(
        self, body: ExecutionStepFailure
    ) -> ExecutionCallbackReceipt: ...


def get_execution_callback_service(
    request: Request,
) -> WorkflowExecutionCallbackService:
    service = cast(
        WorkflowExecutionCallbackService | None,
        getattr(request.app.state, "workflow_execution_callback_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="WORKFLOW_CALLBACK_UNAVAILABLE",
            message="耐久 Workflow 回调暂时不可用",
        )
    return service


Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]
CallbackService = Annotated[
    WorkflowExecutionCallbackService,
    Depends(get_execution_callback_service),
]


async def _verify(
    request: Request,
    verifier: RagCallbackVerifier,
    service: WorkflowExecutionCallbackService,
    *,
    path_run_id: str,
    path_step_id: str,
    body: ExecutionStepProgress | ExecutionStepResult | ExecutionStepFailure,
    scope: ServiceScope,
) -> None:
    if path_run_id != body.runId or path_step_id != body.stepId:
        raise ApiError(
            status_code=409,
            code="WORKFLOW_RESOURCE_MISMATCH",
            message="路径资源与 Workflow 回调载荷不一致",
        )
    novel_id = await service.novel_id(path_run_id, path_step_id)
    if novel_id != body.novelId:
        raise ApiError(
            status_code=409,
            code="WORKFLOW_RESOURCE_MISMATCH",
            message="Workflow 回调小说归属不一致",
        )
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
        required_scope=scope,
        task_id=path_step_id,
        run_id=path_run_id,
        novel_id=novel_id,
    )


@router.put(
    "/{run_id}/steps/{step_id}/progress",
    response_model=ExecutionCallbackReceipt,
)
async def report_execution_progress(
    run_id: str,
    step_id: str,
    body: ExecutionStepProgress,
    request: Request,
    verifier: Verifier,
    service: CallbackService,
) -> ExecutionCallbackReceipt:
    await _verify(
        request,
        verifier,
        service,
        path_run_id=run_id,
        path_step_id=step_id,
        body=body,
        scope=ServiceScope.EXECUTION_PROGRESS,
    )
    return await service.progress(body)


@router.put(
    "/{run_id}/steps/{step_id}/result",
    response_model=ExecutionCallbackReceipt,
)
async def report_execution_result(
    run_id: str,
    step_id: str,
    body: ExecutionStepResult,
    request: Request,
    verifier: Verifier,
    service: CallbackService,
) -> ExecutionCallbackReceipt:
    await _verify(
        request,
        verifier,
        service,
        path_run_id=run_id,
        path_step_id=step_id,
        body=body,
        scope=ServiceScope.EXECUTION_RESULT,
    )
    return await service.result(body)


@router.put(
    "/{run_id}/steps/{step_id}/failure",
    response_model=ExecutionCallbackReceipt,
)
async def report_execution_failure(
    run_id: str,
    step_id: str,
    body: ExecutionStepFailure,
    request: Request,
    verifier: Verifier,
    service: CallbackService,
) -> ExecutionCallbackReceipt:
    await _verify(
        request,
        verifier,
        service,
        path_run_id=run_id,
        path_step_id=step_id,
        body=body,
        scope=ServiceScope.EXECUTION_RESULT,
    )
    return await service.failure(body)
