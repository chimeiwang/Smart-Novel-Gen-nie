from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..definitions.agents import AGENT_DEFINITIONS, AgentId
from ..operations.contracts import CreativeOperationKind
from ..tools.registry import ToolContext, ToolRegistry
from .agent_runtime import AgentRuntime
from .execution import (
    AgentExecutionMode,
    build_execution_brief,
    resolve_execution_contract,
    validate_execution_agent,
)
from .messages import build_agent_messages
from .model_runtime import ModelCallContext
from .turn_result import AgentTurnResult


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agentId: AgentId
    executionMode: AgentExecutionMode
    operationKind: CreativeOperationKind | None
    userMessage: str
    contextMessages: list[str] = Field(default_factory=list)
    executionInstructions: list[str] = Field(default_factory=list)
    conversationMessages: list[dict[str, object]] = Field(default_factory=list)
    toolContext: ToolContext

    @model_validator(mode="after")
    def validate_execution_scope(self) -> Self:
        if self.agentId != self.toolContext.agentId:
            raise ValueError("运行智能体与工具上下文智能体不一致")
        if self.executionMode == "quality" and self.operationKind is not None:
            raise ValueError("质量模式不能绑定 CreativeOperation")
        if self.executionMode != "quality" and self.operationKind is None:
            raise ValueError("创作执行模式缺少 Operation")
        return self


class AgentRunResult(AgentTurnResult):
    agentId: AgentId


class AgentRunner:
    def __init__(self, runtime: AgentRuntime, registry: ToolRegistry) -> None:
        self._runtime = runtime
        self._registry = registry

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        definition = AGENT_DEFINITIONS[request.agentId]
        execution = resolve_execution_contract(
            request.executionMode,
            request.operationKind,
        )
        validate_execution_agent(execution, request.agentId)
        messages = build_agent_messages(
            agent_system_prompt=definition.systemPrompt,
            execution_brief=build_execution_brief(
                request.executionMode,
                request.operationKind,
                request.executionInstructions,
            ),
            readonly_context=(
                "\n\n".join(request.contextMessages)
                if request.contextMessages
                else None
            ),
            prior_messages=request.conversationMessages,
            user_message=request.userMessage,
        )
        tools = self._registry.for_execution(
            agent_id=definition.id,
            capabilities=definition.toolCapabilities,
            allowed_tool_names=execution.allowedToolNames,
        )
        result = await self._runtime.run(
            messages=messages,
            exposed_tools=tools,
            context=request.toolContext,
            max_iterations=definition.maxIterations,
            terminal_control_tools=execution.terminalControlTools,
            model_context=ModelCallContext(
                userId=request.toolContext.userId,
                novelId=request.toolContext.novelId,
                taskId=request.toolContext.taskId,
                runId=request.toolContext.runId,
                agentId=request.agentId,
            ),
        )
        payload: dict[str, Any] = result.model_dump()
        return AgentRunResult(agentId=definition.id, **payload)
