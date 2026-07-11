from __future__ import annotations

from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..config import Settings
from ..errors import ApiError
from .schemas import WorkflowRunDetailResponse, WorkflowRunListResponse


class AgentDebugClient(Protocol):
    async def get_workflow_runs(
        self,
        user_id: str,
        run_id: str | None = None,
    ) -> dict[str, object]: ...


def get_agent_debug_client(request: Request) -> AgentDebugClient:
    settings = cast(Settings, request.app.state.settings)
    if not settings.workflow_event_debug_enabled:
        raise ApiError(status_code=404, code="NOT_FOUND", message="调试接口未启用")
    client = cast(
        AgentDebugClient | None,
        getattr(request.app.state, "agent_client", None),
    )
    if client is None:
        raise ApiError(
            status_code=503,
            code="AGENT_DEBUG_UNAVAILABLE",
            message="智能体调试服务暂时不可用",
        )
    return client


User = Annotated[AuthUser, Depends(get_current_user)]
Client = Annotated[AgentDebugClient, Depends(get_agent_debug_client)]
router = APIRouter(prefix="/debug/workflow-runs", tags=["工作流调试"])


@router.get("", response_model=WorkflowRunListResponse)
async def list_workflow_runs(user: User, client: Client) -> WorkflowRunListResponse:
    return WorkflowRunListResponse.model_validate(await client.get_workflow_runs(user.id))


@router.get("/{run_id}", response_model=WorkflowRunDetailResponse)
async def get_workflow_run(
    run_id: str,
    user: User,
    client: Client,
) -> WorkflowRunDetailResponse:
    return WorkflowRunDetailResponse.model_validate(
        await client.get_workflow_runs(user.id, run_id)
    )
