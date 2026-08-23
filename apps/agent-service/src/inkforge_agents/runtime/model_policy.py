from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..definitions.agents import AgentId
from ..operations.contracts import CreativeOperationKind
from .errors import ModelExecutionStage
from .execution import (
    AgentExecutionMode,
    resolve_execution_contract,
    validate_execution_agent,
    validate_execution_stage,
)


class ModelExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policyId: str = Field(min_length=1)
    thinkingMode: Literal["provider_default", "enabled", "disabled"]
    reasoningEffort: Literal["low", "high", "max"] | None = None
    requiredToolName: str | None = Field(default=None, min_length=1)
    visibleOutputDisposition: Literal["business", "diagnostic_only"]

    @model_validator(mode="after")
    def validate_thinking_fields(self) -> ModelExecutionPolicy:
        if self.thinkingMode == "disabled" and self.reasoningEffort is not None:
            raise ValueError("thinkingMode=disabled 时 reasoningEffort 必须为空")
        return self


def resolve_model_execution_policy(
    *,
    agent_id: AgentId,
    execution_mode: AgentExecutionMode | str,
    operation_kind: CreativeOperationKind | str | None,
    stage: ModelExecutionStage,
    version: str,
) -> ModelExecutionPolicy:
    """按调用方显式提供的执行场景选择策略，不让 Provider 反推业务角色。"""

    if version not in {"legacy", "review-v1"}:
        raise ValueError("模型执行策略版本不受支持")
    valid_modes = {"primary", "reviewer", "reviser", "quality"}
    if execution_mode not in valid_modes:
        raise ValueError(f"AGENT_EXECUTION_MODE_INVALID：执行模式不可用 {execution_mode}")
    mode = cast(AgentExecutionMode, execution_mode)
    validate_execution_stage(mode, stage)
    contract = resolve_execution_contract(
        mode,
        cast(CreativeOperationKind | None, operation_kind),
    )
    validate_execution_agent(contract, agent_id)

    if version == "legacy":
        return ModelExecutionPolicy(
            policyId=f"legacy:{_canonical_stage_name(stage)}",
            thinkingMode="provider_default",
            visibleOutputDisposition="business"
            if stage in {"primary", "reviser"}
            else "diagnostic_only",
        )

    mapping: dict[ModelExecutionStage, tuple[str, str | None, str | None, str]] = {
        "primary": ("enabled", "high", None, "business"),
        "reviewer": ("enabled", "low", "submit_evaluation", "diagnostic_only"),
        "reviser": ("enabled", "high", None, "business"),
        "quality": (
            "enabled",
            "low",
            "submit_quality_report",
            "diagnostic_only",
        ),
        "protocol_repair": (
            "disabled",
            None,
            "submit_evaluation",
            "diagnostic_only",
        ),
    }
    thinking_mode, reasoning_effort, required_tool, disposition = mapping[stage]
    return ModelExecutionPolicy(
        policyId=f"{version}:{_canonical_stage_name(stage)}",
        thinkingMode=thinking_mode,  # type: ignore[arg-type]
        reasoningEffort=reasoning_effort,  # type: ignore[arg-type]
        requiredToolName=required_tool,
        visibleOutputDisposition=disposition,  # type: ignore[arg-type]
    )


def _canonical_stage_name(stage: ModelExecutionStage) -> str:
    return "protocol-repair" if stage == "protocol_repair" else stage
