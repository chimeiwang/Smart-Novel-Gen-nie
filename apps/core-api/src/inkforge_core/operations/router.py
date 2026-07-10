from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ..errors import PUBLIC_ERROR_RESPONSES


class LiveHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["core-api"]


class ReadyHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "not_ready"]
    service: Literal["core-api"]
    checks: dict[str, Literal["ok", "failed"]]


ReadinessCheck = Callable[[], bool | Awaitable[bool]]
ReadinessChecks = dict[str, ReadinessCheck]


router = APIRouter(
    prefix="/health",
    tags=["health"],
    responses=PUBLIC_ERROR_RESPONSES,
)


@router.get("/live", response_model=LiveHealthResponse)
async def live() -> LiveHealthResponse:
    return LiveHealthResponse(status="ok", service="core-api")


@router.get(
    "/ready",
    response_model=ReadyHealthResponse,
    responses={503: {"model": ReadyHealthResponse, "description": "应用尚未就绪"}},
)
async def ready(request: Request) -> ReadyHealthResponse | JSONResponse:
    readiness_checks = cast(ReadinessChecks, request.app.state.readiness_checks)
    results = {
        name: await _run_readiness_check(check) for name, check in readiness_checks.items()
    }
    is_ready = all(result == "ok" for result in results.values())
    body = ReadyHealthResponse(
        status="ready" if is_ready else "not_ready",
        service="core-api",
        checks=results,
    )
    if is_ready:
        return body
    return JSONResponse(status_code=503, content=body.model_dump(mode="json"))


def register_readiness_check(app: FastAPI, name: str, check: ReadinessCheck) -> None:
    readiness_checks = cast(
        ReadinessChecks,
        getattr(app.state, "readiness_checks", {}),
    )
    readiness_checks[name] = check
    app.state.readiness_checks = readiness_checks


async def _run_readiness_check(check: ReadinessCheck) -> Literal["ok", "failed"]:
    try:
        result = check()
        if not isinstance(result, bool):
            result = await result
    except Exception:
        return "failed"
    return "ok" if result else "failed"
