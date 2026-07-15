from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ..definitions.capabilities import AGENT_CAPABILITIES
from ..providers.base import ModelTool
from .permissions import ToolPermission

ToolKind = Literal["read", "proposal", "control"]


class ToolContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userId: str
    novelId: str
    taskId: str
    runId: str
    agentId: str


class ToolGateway(Protocol):
    async def execute(
        self,
        tool_name: str,
        context: ToolContext,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    argumentsModel: type[BaseModel]
    permission: ToolPermission
    toolKind: ToolKind
    handler: ToolHandler | None = None

    def validate(self, arguments: Mapping[str, object]) -> dict[str, Any]:
        return self.argumentsModel.model_validate(arguments).model_dump(
            by_alias=True,
            exclude_none=True,
        )

    def as_model_tool(self) -> ModelTool:
        schema = self.argumentsModel.model_json_schema()
        schema.pop("title", None)
        return ModelTool(
            name=self.name,
            description=self.description,
            parameters=schema,
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if not tool.name or tool.name in self._tools:
            raise ValueError("工具名称为空或重复注册")
        self._tools[tool.name] = tool

    def all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def require(self, name: str) -> ToolDefinition:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"工具未注册：{name}")
        return tool

    def for_agent(
        self,
        *,
        agent_id: str,
        capabilities: set[str] | frozenset[str],
    ) -> list[ToolDefinition]:
        return [
            tool for tool in self._tools.values() if tool.permission.allows(agent_id, capabilities)
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, object],
        context: ToolContext,
    ) -> dict[str, Any]:
        tool = self.require(name)
        validated = tool.validate(arguments)
        return await self.execute_validated(tool, validated, context)

    async def execute_validated(
        self,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        registered = self.require(tool.name)
        if registered is not tool:
            raise ValueError("工具定义与注册表不一致")
        capabilities = AGENT_CAPABILITIES.get(context.agentId)
        if capabilities is None or not tool.permission.allows(
            context.agentId, capabilities
        ):
            raise PermissionError(f"当前智能体无权执行工具：{tool.name}")
        if tool.toolKind == "control":
            raise ValueError("控制工具只能由智能体运行时捕获")
        if tool.handler is None:
            raise RuntimeError(f"工具缺少执行器：{tool.name}")
        return await tool.handler(arguments, context)


class _UnavailableGateway:
    async def execute(
        self,
        tool_name: str,
        context: ToolContext,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        del tool_name, context, arguments
        raise RuntimeError("核心工具网关尚未接入")


def build_default_registry(gateway: ToolGateway | None = None) -> ToolRegistry:
    from .control import control_tools
    from .proposals import proposal_tools
    from .read import read_tools

    resolved_gateway = gateway or _UnavailableGateway()
    registry = ToolRegistry()
    for tool in read_tools(resolved_gateway) + proposal_tools() + control_tools():
        registry.register(tool)
    return registry
