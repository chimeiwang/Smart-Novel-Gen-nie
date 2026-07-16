from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..definitions.agents import AgentId
from ..operations.contracts import CreativeOperationKind
from ..operations.definitions import OPERATION_DEFINITIONS, OperationDefinition

AgentExecutionMode = Literal["primary", "reviewer", "reviser", "quality"]

_REVIEWER_TOOLS = frozenset({"submit_evaluation"})
_QUALITY_TOOLS = frozenset({"submit_quality_report"})


@dataclass(frozen=True, slots=True)
class ExecutionToolContract:
    mode: AgentExecutionMode
    operation: OperationDefinition | None
    allowedToolNames: frozenset[str]
    terminalControlTools: frozenset[str]


def resolve_execution_contract(
    mode: AgentExecutionMode,
    operation_kind: CreativeOperationKind | None,
) -> ExecutionToolContract:
    if mode == "quality":
        if operation_kind is not None:
            raise ValueError("AGENT_EXECUTION_MODE_INVALID：质量模式不能绑定 Operation")
        return ExecutionToolContract(mode, None, _QUALITY_TOOLS, _QUALITY_TOOLS)
    if operation_kind is None:
        raise ValueError("AGENT_EXECUTION_MODE_INVALID：创作执行模式缺少 Operation")
    operation = OPERATION_DEFINITIONS.get(operation_kind)
    if operation is None:
        raise ValueError(
            f"AGENT_EXECUTION_MODE_INVALID：Operation 不可执行 {operation_kind}"
        )
    if mode == "reviewer":
        return ExecutionToolContract(mode, operation, _REVIEWER_TOOLS, _REVIEWER_TOOLS)
    return ExecutionToolContract(
        mode,
        operation,
        operation.allowedToolNames,
        operation.terminalControlTools,
    )


def validate_execution_agent(
    contract: ExecutionToolContract,
    agent_id: AgentId,
) -> None:
    if contract.mode == "quality":
        valid = agent_id == "编辑"
    elif contract.mode == "reviewer":
        valid = contract.operation is not None and agent_id in contract.operation.reviewers
    else:
        valid = (
            contract.operation is not None
            and agent_id == contract.operation.primaryAgent
        )
    if not valid:
        operation_kind = contract.operation.kind if contract.operation else "quality"
        raise ValueError(
            "AGENT_EXECUTION_MODE_INVALID："
            f"智能体 {agent_id} 不能以 {contract.mode} 执行 {operation_kind}"
        )
