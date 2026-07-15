from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class LiveHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["core-api"]


class ReadyHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "not_ready"]
    service: Literal["core-api"]
    checks: dict[str, Literal["ok", "failed"]]
    backgroundTasks: dict[str, str] | None = None


ReadinessCheck = Callable[[], bool | Awaitable[bool]]
ReadinessChecks = dict[str, ReadinessCheck]
ReadinessErrorDetails = Callable[[], dict[str, str]]
ReadinessErrorDetailChecks = dict[str, ReadinessErrorDetails]


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LiveHealthResponse)
async def live() -> LiveHealthResponse:
    return LiveHealthResponse(status="ok", service="core-api")


@router.get(
    "/ready",
    response_model=ReadyHealthResponse,
    response_model_exclude_none=True,
    responses={503: {"model": ReadyHealthResponse, "description": "应用尚未就绪"}},
)
async def ready(request: Request) -> ReadyHealthResponse | JSONResponse:
    readiness_checks = cast(ReadinessChecks, request.app.state.readiness_checks)
    results = {
        name: await _run_readiness_check(check) for name, check in readiness_checks.items()
    }
    is_ready = all(result == "ok" for result in results.values())
    detail_checks = cast(
        ReadinessErrorDetailChecks,
        getattr(request.app.state, "readiness_error_details", {}),
    )
    background_tasks: dict[str, str] = {}
    for name, result in results.items():
        detail_check = detail_checks.get(name)
        if result == "failed" and detail_check is not None:
            try:
                background_tasks.update(detail_check())
            except Exception:
                background_tasks[name] = "BACKGROUND_STATUS_UNAVAILABLE"
    body = ReadyHealthResponse(
        status="ready" if is_ready else "not_ready",
        service="core-api",
        checks=results,
        backgroundTasks=background_tasks or None,
    )
    if is_ready:
        return body
    return JSONResponse(
        status_code=503,
        content=body.model_dump(mode="json", exclude_none=True),
    )


def register_readiness_check(
    app: FastAPI,
    name: str,
    check: ReadinessCheck,
    *,
    error_details: ReadinessErrorDetails | None = None,
) -> None:
    readiness_checks = cast(
        ReadinessChecks,
        getattr(app.state, "readiness_checks", {}),
    )
    readiness_checks[name] = check
    app.state.readiness_checks = readiness_checks
    if error_details is not None:
        detail_checks = cast(
            ReadinessErrorDetailChecks,
            getattr(app.state, "readiness_error_details", {}),
        )
        detail_checks[name] = error_details
        app.state.readiness_error_details = detail_checks


async def _run_readiness_check(check: ReadinessCheck) -> Literal["ok", "failed"]:
    try:
        result = check()
        if not isinstance(result, bool):
            result = await result
    except Exception:
        return "failed"
    return "ok" if result else "failed"
