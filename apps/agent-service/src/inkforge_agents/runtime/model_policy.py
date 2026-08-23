from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..definitions.agents import AgentId
from ..operations.contracts import CreativeOperationKind
from .errors import ModelExecutionStage

ModelExecutionMode = Literal["primary", "reviewer", "reviser", "quality"]


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
    execution_mode: ModelExecutionMode | str,
    operation_kind: CreativeOperationKind | str | None,
    stage: ModelExecutionStage,
    version: str,
) -> ModelExecutionPolicy:
    """按调用方显式提供的执行场景选择策略，不让 Provider 反推业务角色。"""

    del agent_id, execution_mode, operation_kind
    if not version:
        raise ValueError("模型执行策略版本不能为空")

    if version == "legacy":
        return ModelExecutionPolicy(
            policyId=f"legacy:{stage}",
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
        policyId=f"{version}:{stage}",
        thinkingMode=thinking_mode,  # type: ignore[arg-type]
        reasoningEffort=reasoning_effort,  # type: ignore[arg-type]
        requiredToolName=required_tool,
        visibleOutputDisposition=disposition,  # type: ignore[arg-type]
    )
