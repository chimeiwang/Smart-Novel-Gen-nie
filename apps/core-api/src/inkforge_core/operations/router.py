from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict


class LiveHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["core-api"]


class ReadyHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"]
    service: Literal["core-api"]
    checks: dict[str, Literal["ok"]]


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LiveHealthResponse)
async def live() -> LiveHealthResponse:
    return LiveHealthResponse(status="ok", service="core-api")


@router.get("/ready", response_model=ReadyHealthResponse)
async def ready() -> ReadyHealthResponse:
    return ReadyHealthResponse(
        status="ready",
        service="core-api",
        checks={"configuration": "ok"},
    )
