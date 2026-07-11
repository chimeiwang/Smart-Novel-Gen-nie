from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address, ip_network
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from inkforge_contracts.jobs import (
    AgentJobAccepted,
    AgentJobCancelRequest,
    AgentJobRequest,
)
from inkforge_contracts.jwt_claims import ServiceScope

from ..config import Settings
from ..queue.repository import QueueJob, RedisRunQueue


class CoreRequestVerifier(Protocol):
    async def verify_request(self, **kwargs: object) -> object: ...


def get_queue(request: Request) -> RedisRunQueue:
    queue = cast(RedisRunQueue | None, getattr(request.app.state, "run_queue", None))
    if queue is None:
        raise HTTPException(status_code=503, detail="智能体运行队列暂时不可用")
    return queue


def get_verifier(request: Request) -> CoreRequestVerifier:
    settings = cast(Settings, request.app.state.settings)
    if not settings.trusted_core_cidrs:
        raise HTTPException(status_code=503, detail="核心服务可信网段未配置")
    peer = request.client.host if request.client is not None else None
    try:
        address = ip_address(peer) if peer is not None else None
    except ValueError:
        address = None
    if address is None or not any(
        address in ip_network(cidr) for cidr in settings.trusted_core_cidrs
    ):
        raise HTTPException(status_code=403, detail="核心服务直接对端不在可信网段内")
    verifier = cast(
        CoreRequestVerifier | None,
        getattr(request.app.state, "core_request_verifier", None),
    )
    if verifier is None:
        raise HTTPException(status_code=503, detail="核心服务签名校验器暂时不可用")
    return verifier


Queue = Annotated[RedisRunQueue, Depends(get_queue)]
Verifier = Annotated[CoreRequestVerifier, Depends(get_verifier)]

router = APIRouter(prefix="/internal/v1/runs", include_in_schema=False)


async def _verify(
    request: Request,
    verifier: CoreRequestVerifier,
    *,
    scope: ServiceScope,
    task_id: str,
    run_id: str,
    novel_id: str,
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


@router.post("", response_model=AgentJobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_run(
    body: AgentJobRequest,
    request: Request,
    queue: Queue,
    verifier: Verifier,
) -> AgentJobAccepted:
    await _verify(
        request,
        verifier,
        scope=ServiceScope.AGENT_RUN,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    queued = await queue.enqueue(
        QueueJob(
            jobId=body.jobId,
            kind=body.kind,
            runId=body.runId,
            taskId=body.taskId,
            novelId=body.novelId,
            userId=body.userId,
            priority=body.priority,
            payload=body.payload,
            createdAt=datetime.now(UTC),
        ),
        force=body.force,
    )
    return AgentJobAccepted(
        jobId=body.jobId,
        runId=body.runId,
        taskId=body.taskId,
        status="queued" if queued else "duplicate",
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    job_id: str,
    body: AgentJobCancelRequest,
    request: Request,
    queue: Queue,
    verifier: Verifier,
) -> Response:
    await _verify(
        request,
        verifier,
        scope=ServiceScope.AGENT_CANCEL,
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    await queue.cancel(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
