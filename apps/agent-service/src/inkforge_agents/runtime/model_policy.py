from __future__ import annotations

from typing import Literal

from ..operations.definitions import OPERATION_DEFINITIONS
from ..providers.base import ModelExecutionPolicy

AgentExecutionMode = Literal["primary", "reviewer", "reviser", "quality"]

REPORT_OPERATIONS = frozenset({"answer_question", "review_chapter"})
CREATIVE_OPERATIONS = frozenset(
    {
        "create_lore",
        "revise_lore",
        "create_outline",
        "revise_outline",
        "plan_chapter",
        "write_chapter",
        "rewrite_scene",
        "rewrite_chapter_selection",
        "rewrite_outline_selection",
        "manage_foreshadowing",
    }
)

CREATIVE_HIGH = ModelExecutionPolicy(
    policyId="v1:creative-high",
    thinkingMode="enabled",
    reasoningEffort="high",
)
REVIEWER_NO_THINKING = ModelExecutionPolicy(
    policyId="v1:reviewer-no-thinking",
    thinkingMode="disabled",
    requiredToolName="submit_evaluation",
)
QUALITY_NO_THINKING = ModelExecutionPolicy(
    policyId="v1:quality-no-thinking",
    thinkingMode="disabled",
    requiredToolName="submit_quality_report",
)
REPORT_NO_THINKING = ModelExecutionPolicy(
    policyId="v1:report-no-thinking",
    thinkingMode="disabled",
)
LEGACY_PROVIDER_DEFAULT = ModelExecutionPolicy(
    policyId="legacy:provider-default",
    thinkingMode="provider_default",
)

_SHORT_MEDIUM_POLICIES = {
    "generate_outline": CREATIVE_HIGH,
    "generate_manuscript": CREATIVE_HIGH,
    "replace_selection": CREATIVE_HIGH,
    "full_check": REPORT_NO_THINKING,
}
_OPERATION_POLICIES = {
    **{operation: REPORT_NO_THINKING for operation in REPORT_OPERATIONS},
    **{operation: CREATIVE_HIGH for operation in CREATIVE_OPERATIONS},
}


def resolve_agent_model_policy(
    mode: AgentExecutionMode,
    operation: str | None,
) -> ModelExecutionPolicy:
    if operation is not None and operation not in OPERATION_DEFINITIONS:
        raise ValueError(f"未知 Operation，无法解析模型策略：{operation}")
    if operation is not None and operation not in _OPERATION_POLICIES:
        raise ValueError(f"Operation 缺少模型策略映射：{operation}")
    if mode == "quality":
        if operation is not None:
            raise ValueError("质量模式不能绑定 Operation")
        return QUALITY_NO_THINKING
    if operation is None:
        raise ValueError("创作执行模式缺少 Operation")
    if mode == "reviewer":
        return REVIEWER_NO_THINKING
    return _OPERATION_POLICIES[operation]


def resolve_short_medium_model_policy(operation: str) -> ModelExecutionPolicy:
    try:
        return _SHORT_MEDIUM_POLICIES[operation]
    except KeyError as exc:
        raise ValueError(f"未知中短篇 Operation，无法解析模型策略：{operation}") from exc


def resolve_portrait_model_policy() -> ModelExecutionPolicy:
    return REPORT_NO_THINKING


__all__ = [
    "CREATIVE_HIGH",
    "CREATIVE_OPERATIONS",
    "LEGACY_PROVIDER_DEFAULT",
    "QUALITY_NO_THINKING",
    "REPORT_NO_THINKING",
    "REPORT_OPERATIONS",
    "REVIEWER_NO_THINKING",
    "resolve_agent_model_policy",
    "resolve_portrait_model_policy",
    "resolve_short_medium_model_policy",
]
