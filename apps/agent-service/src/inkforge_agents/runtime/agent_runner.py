from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..definitions.agents import AGENT_DEFINITIONS, AgentId
from ..tools.registry import ToolContext, ToolRegistry
from .agent_runtime import AgentRuntime
from .turn_result import AgentTurnResult


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agentId: AgentId
    userMessage: str
    contextMessages: list[str] = Field(default_factory=list)
    conversationMessages: list[dict[str, object]] = Field(default_factory=list)
    toolContext: ToolContext

    @model_validator(mode="after")
    def validate_agent_context(self) -> AgentRunRequest:
        if self.agentId != self.toolContext.agentId:
            raise ValueError("运行智能体与工具上下文智能体不一致")
        return self


class AgentRunResult(AgentTurnResult):
    agentId: AgentId


class AgentRunner:
    def __init__(self, runtime: AgentRuntime, registry: ToolRegistry) -> None:
        self._runtime = runtime
        self._registry = registry

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        definition = AGENT_DEFINITIONS[request.agentId]
        messages: list[dict[str, object]] = [{"role": "system", "content": definition.systemPrompt}]
        messages.extend(
            {"role": "system", "content": context_message}
            for context_message in request.contextMessages
        )
        messages.extend(request.conversationMessages)
        messages.append({"role": "user", "content": request.userMessage})
        tools = self._registry.for_agent(
            agent_id=definition.id,
            capabilities=definition.toolCapabilities,
        )
        result = await self._runtime.run(
            messages=messages,
            exposed_tools=tools,
            context=request.toolContext,
            max_iterations=definition.maxIterations,
            terminal_control_tools=definition.terminalControlTools,
        )
        payload: dict[str, Any] = result.model_dump()
        return AgentRunResult(agentId=definition.id, **payload)
