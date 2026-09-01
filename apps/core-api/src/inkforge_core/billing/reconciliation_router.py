from __future__ import annotations

from fastapi import APIRouter, Request
from inkforge_contracts.execution import (
    BillingReconciliationReceipt,
    BillingReconciliationRequest,
)
from inkforge_contracts.jwt_claims import ServiceScope

from ..errors import ApiError
from .router import Verifier, _verify_internal_request

router = APIRouter(
    prefix="/internal/v1/workflow-runs",
    tags=["内部 Workflow 计费对账"],
    include_in_schema=False,
)


@router.put(
    "/{run_id}/steps/{step_id}/billing-reconciliation",
    response_model=BillingReconciliationReceipt,
)
async def reconcile_workflow_billing(
    run_id: str,
    step_id: str,
    body: BillingReconciliationRequest,
    request: Request,
    verifier: Verifier,
) -> BillingReconciliationReceipt:
    """Python 回滚 Core 只保留同形契约与鉴权，不实现第二套结算。"""

    if run_id != body.runId or step_id != body.stepId:
        raise ApiError(
            status_code=409,
            code="WORKFLOW_RESOURCE_MISMATCH",
            message="路径资源与 Workflow 计费对账载荷不一致",
        )
    await _verify_internal_request(
        request,
        verifier,
        scope=ServiceScope.BILLING_RECONCILE,
        task_id=step_id,
        run_id=run_id,
        novel_id=body.novelId,
    )
    raise ApiError(
        status_code=503,
        code="WORKFLOW_BILLING_RECONCILIATION_UNAVAILABLE",
        message="Python 回滚 Core 不提供耐久 Workflow 计费对账",
    )
