from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ..definitions.agents import AgentId
from ..operations.contracts import CreativeOperationKind
from ..operations.definitions import OPERATION_DEFINITIONS, OperationDefinition

AgentExecutionMode = Literal["primary", "reviewer", "reviser", "quality"]
QUALITY_AGENT_ID: AgentId = "校验"

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
    if mode == "reviewer" and operation is not None:
        goal = "复审当前 Operation 对应的 Core 权威草案。"
    elif mode == "reviser" and operation is not None:
        goal = f"完整重写 {operation.label} 对应的待审核草案。"
    else:
        goal = operation.executionBrief if operation is not None else "提交一致性质量报告。"
    lines = [
        f"当前执行契约：operation={operation_label}，mode={mode}。",
        f"执行目标：{goal}",
    ]
    if mode == "reviewer":
        lines.extend(
            (
                "只评审只读资料中的 Core 权威草案，不得重新读取、猜测或替换审核对象。",
                "完成后只调用一次 submit_evaluation；需要修改时统一提出完整 rewrite 意见。",
            )
        )
    elif mode == "quality":
        lines.extend(
            (
                "从角色、世界规则、时间线、因果和伏笔五个一致性维度完成检查。",
                "只调用一次 submit_quality_report，qualityGate 只能是 pass | revise，"
                "同时提交结构化 issues 和非空 report。",
            )
        )
    elif operation is not None:
        lines.extend(_operation_protocol(mode, operation))
    lines.append(
        "不得改变 Operation、执行模式、工具权限或绕过待审核草案与用户确认边界。"
    )
    controlled = [item for item in additional_instructions if item]
    if controlled:
        lines.append("本次服务端附加指令：\n" + "\n".join(controlled))
    return "\n".join(lines)


def _operation_protocol(
    mode: AgentExecutionMode,
    operation: OperationDefinition,
) -> list[str]:
    if not operation.terminalControlTools:
        return ["本次没有产物终止工具，请用普通正文直接完成回答。"]
    tools = "、".join(sorted(operation.terminalControlTools))
    lines = [f"完成任务时必须且只能从以下终止工具中调用一个：{tools}。"]
    if operation.kind in {"write_chapter", "rewrite_scene"}:
        lines.append(
            "调用 begin_artifact_output，并把完整正文放在 "
            "ARTIFACT_OUTPUT_START 与 ARTIFACT_OUTPUT_END 之间；标记内只放正文。"
        )
    elif operation.kind == "plan_chapter":
        lines.append(
            "调用 submit_beat_plan 提交结构化章节计划；每个场景必须包含场景目标、"
            "冲突、角色、伏笔引用、预估字数和验收标准，整体还要明确转折、代价、"
            "结果与余波。"
        )
    elif operation.artifactPolicy == "agent_updates":
        middle_tools = sorted(
            operation.allowedToolNames
            & {
                "append_update_batch",
                "append_outline_tree",
                "put_update_text_block",
                "put_update_item_text_block",
                "put_update_item_text_blocks",
            }
        )
        middle = " / ".join(middle_tools)
        lines.append(
            "短小更新可直接调用 propose_updates；复杂更新按 "
            f"start_update_builder → {middle} → finish_update_builder 构建。"
        )
        lines.append(
            "构建链必须沿用同一 artifactKey；Runtime 与产物校验器会拒绝身份变化。"
        )
    if mode == "reviser":
        lines.append(
            "根据只读资料中的 Core 权威草案完成完整重写，使用当前 Operation 的产物"
            "提交工具，保持原产物类型和权威 artifactKey。"
        )
    return lines
