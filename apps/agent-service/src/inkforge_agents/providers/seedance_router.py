"""Core 调用的 Seedance 短提交/短查询内部接口。"""

from __future__ import annotations

from typing import Annotated, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_contracts.video_render import (
    SeedanceRenderQueryRequest,
    SeedanceRenderQueryResponse,
    SeedanceRenderSubmitRequest,
    SeedanceRenderSubmitResponse,
)

from ..runs.router import CoreRequestVerifier, _verify, get_verifier
from .seedance import SeedanceProvider

router = APIRouter(
    prefix="/internal/v1/video/seedance/tasks",
    include_in_schema=False,
)

Verifier = Annotated[CoreRequestVerifier, Depends(get_verifier)]


def _provider(request: Request) -> SeedanceProvider:
    provider = cast(
        SeedanceProvider | None,
        getattr(request.app.state, "seedance_provider", None),
    )
    if provider is None:
        raise HTTPException(status_code=503, detail="Seedance 适配器暂时不可用")
    return provider


@router.post(
    "",
    response_model=SeedanceRenderSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_seedance_task(
    body: SeedanceRenderSubmitRequest,
    request: Request,
    verifier: Verifier,
) -> SeedanceRenderSubmitResponse:
    await _verify(
        request,
        verifier,
        scope=ServiceScope.VIDEO_RENDER,
        task_id=body.taskId,
        run_id=body.taskId,
        novel_id=body.novelId,
    )
    try:
        return await _provider(request).submit_render(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500:
            raise HTTPException(
                status_code=422,
                detail="Seedance 明确拒绝创建任务",
            ) from exc
        raise HTTPException(status_code=502, detail="Seedance 创建任务失败") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Seedance 创建任务结果不确定") from exc


@router.post(
    "/{provider_task_id}/query",
    response_model=SeedanceRenderQueryResponse,
)
async def query_seedance_task(
    provider_task_id: str,
    body: SeedanceRenderQueryRequest,
    request: Request,
    verifier: Verifier,
) -> SeedanceRenderQueryResponse:
    if provider_task_id != body.providerTaskId:
        raise HTTPException(status_code=403, detail="供应商任务路径与请求体不一致")
    await _verify(
        request,
        verifier,
        scope=ServiceScope.VIDEO_RENDER,
        task_id=body.taskId,
        run_id=body.taskId,
        novel_id=body.novelId,
    )
    try:
        return await _provider(request).query_render(
            task_id=body.taskId,
            provider_task_id=provider_task_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Seedance 查询任务失败") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Seedance 查询任务失败") from exc
