from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from inkforge_contracts.jwt_claims import ServiceScope

from ..runs.router import CoreRequestVerifier, get_verifier
from .human_workflow_log import HumanWorkflowLog


class WorkflowLogPort(Protocol):
    def list_runs(self, user_id: str) -> Sequence[object]: ...

    def read_run(self, run_id: str, user_id: str) -> object: ...


def get_workflow_log(request: Request) -> WorkflowLogPort:
    workflow_log = cast(
        HumanWorkflowLog | None,
        getattr(request.app.state, "workflow_log", None),
    )
    if workflow_log is None:
        raise HTTPException(status_code=503, detail="人工工作流日志暂时不可用")
    return workflow_log


Verifier = Annotated[CoreRequestVerifier, Depends(get_verifier)]
WorkflowLog = Annotated[WorkflowLogPort, Depends(get_workflow_log)]
router = APIRouter(prefix="/internal/v1/debug/workflow-runs", include_in_schema=False)


async def _verify(request: Request, verifier: CoreRequestVerifier) -> None:
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
        required_scope=ServiceScope.AGENT_DEBUG_READ,
        task_id="debug",
        run_id="debug",
        novel_id="debug",
    )


@router.get("")
async def list_workflow_runs(
    request: Request,
    verifier: Verifier,
    workflow_log: WorkflowLog,
    user_id: Annotated[str, Query(alias="userId", min_length=1)],
) -> dict[str, object]:
    await _verify(request, verifier)
    return {"runs": workflow_log.list_runs(user_id)}


@router.get("/{run_id}")
async def get_workflow_run(
    run_id: str,
    request: Request,
    verifier: Verifier,
    workflow_log: WorkflowLog,
    user_id: Annotated[str, Query(alias="userId", min_length=1)],
) -> object:
    await _verify(request, verifier)
    try:
        return workflow_log.read_run(run_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="运行日志不存在或无权访问") from exc
