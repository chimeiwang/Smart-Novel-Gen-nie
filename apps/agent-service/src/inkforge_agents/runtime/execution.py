from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ..definitions.agents import AgentId
from ..operations.contracts import CreativeOperationKind
from ..operations.definitions import OPERATION_DEFINITIONS, OperationDefinition

AgentExecutionMode = Literal["primary", "reviewer", "reviser", "quality"]
QUALITY_AGENT_ID: AgentId = "编辑"

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
        valid = agent_id == QUALITY_AGENT_ID
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


def build_execution_brief(
    mode: AgentExecutionMode,
    operation_kind: CreativeOperationKind | None,
    additional_instructions: Sequence[str] = (),
) -> str:
    contract = resolve_execution_contract(mode, operation_kind)
    operation = contract.operation
    operation_label = operation.kind if operation is not None else "quality"
    goal = operation.executionBrief if operation is not None else "提交一致性质量报告。"
    terminal_tools = "、".join(sorted(contract.terminalControlTools))
    if terminal_tools:
        completion = f"完成任务时必须调用且只调用契约允许的终止工具：{terminal_tools}。"
    else:
        completion = "本次没有产物终止工具，请用普通正文直接完成回答。"
    lines = [
        f"当前执行契约：operation={operation_label}，mode={mode}。",
        f"执行目标：{goal}",
        completion,
        "不得改变 Operation、执行模式、工具权限或绕过待审核草案与用户确认边界。",
    ]
    controlled = [item for item in additional_instructions if item]
    if controlled:
        lines.append("本次服务端附加指令：\n" + "\n".join(controlled))
    return "\n".join(lines)
