from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, Request
from inkforge_contracts.jwt_claims import ServiceScope
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ..errors import ApiError
from ..references.internal_router import RagCallbackVerifier, get_rag_callback_verifier

ToolHandler = Callable[["ToolRequest"], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolRequest:
    user_id: str
    novel_id: str
    task_id: str
    run_id: str
    agent_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    agent_ids: frozenset[str]
    read_only: bool
    handler: ToolHandler


class TaskBindingPort(Protocol):
    async def require_binding(self, user_id: str, novel_id: str, task_id: str) -> None: ...


class ToolGateway:
    def __init__(self, authorizer: TaskBindingPort) -> None:
        self._authorizer = authorizer
        self._tools: dict[str, ToolRegistration] = {}

    def register(
        self,
        name: str,
        agent_ids: set[str],
        read_only: bool,
        handler: ToolHandler,
    ) -> None:
        if not name or name in self._tools or not agent_ids:
            raise ValueError("工具注册信息无效或名称重复")
        self._tools[name] = ToolRegistration(frozenset(agent_ids), read_only, handler)

    async def execute(self, request: ToolRequest) -> dict[str, Any]:
        registration = self._tools.get(request.tool_name)
        if registration is None:
            raise ApiError(
                status_code=404,
                code="TOOL_NOT_FOUND",
                message="工具不存在或未注册",
            )
        if request.agent_id not in registration.agent_ids:
            raise ApiError(
                status_code=403,
                code="TOOL_AGENT_FORBIDDEN",
                message="当前智能体无权调用该工具",
            )
        await self._authorizer.require_binding(request.user_id, request.novel_id, request.task_id)
        result = await registration.handler(request)
        if not isinstance(result, dict):
            raise TypeError("工具处理器必须返回对象")
        return result

    def is_read_only(self, name: str) -> bool:
        registration = self._tools.get(name)
        if registration is None:
            raise ApiError(
                status_code=404,
                code="TOOL_NOT_FOUND",
                message="工具不存在或未注册",
            )
        return registration.read_only


class ToolCallBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    agentId: str = Field(min_length=1, max_length=64)
    arguments: dict[str, JsonValue]


class ToolCallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: dict[str, JsonValue]


internal_router = APIRouter(
    prefix="/internal/v1/tools",
    tags=["内部智能体工具"],
    include_in_schema=False,
)


def get_tool_gateway(request: Request) -> ToolGateway:
    gateway = getattr(request.app.state, "tool_gateway", None)
    if not isinstance(gateway, ToolGateway):
        raise ApiError(
            status_code=503,
            code="TOOL_GATEWAY_UNAVAILABLE",
            message="智能体工具网关暂时不可用",
        )
    return gateway


Gateway = Annotated[ToolGateway, Depends(get_tool_gateway)]
Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]


@internal_router.post("/{tool_name}", response_model=ToolCallResponse)
async def execute_internal_tool(
    tool_name: str,
    body: ToolCallBody,
    request: Request,
    gateway: Gateway,
    verifier: Verifier,
) -> ToolCallResponse:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise ApiError(
            status_code=401,
            code="SERVICE_AUTHENTICATION_FAILED",
            message="服务身份认证失败",
        )
    scope = ServiceScope.TOOL_READ if gateway.is_read_only(tool_name) else ServiceScope.TOOL_WRITE
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
        task_id=body.taskId,
        run_id=body.runId,
        novel_id=body.novelId,
    )
    result = await gateway.execute(
        ToolRequest(
            user_id=body.userId,
            novel_id=body.novelId,
            task_id=body.taskId,
            run_id=body.runId,
            agent_id=body.agentId,
            tool_name=tool_name,
            arguments=body.arguments,
        )
    )
    return ToolCallResponse.model_validate({"result": result})
