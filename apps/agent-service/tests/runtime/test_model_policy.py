from __future__ import annotations

import pytest
from inkforge_agents.runtime.model_policy import (
    ModelExecutionPolicy,
    resolve_model_execution_policy,
)
from pydantic import ValidationError


def test_reviewer_uses_low_reasoning_and_required_tool() -> None:
    policy = resolve_model_execution_policy(
        agent_id="编辑",
        execution_mode="reviewer",
        operation_kind="write_chapter",
        stage="reviewer",
        version="review-v1",
    )

    assert policy.thinkingMode == "enabled"
    assert policy.reasoningEffort == "low"
    assert policy.requiredToolName == "submit_evaluation"
    assert policy.visibleOutputDisposition == "diagnostic_only"


@pytest.mark.parametrize(
    ("stage", "thinking_mode", "reasoning_effort", "required_tool", "disposition"),
    [
        ("primary", "enabled", "high", None, "business"),
        ("reviser", "enabled", "high", None, "business"),
        ("reviewer", "enabled", "low", "submit_evaluation", "diagnostic_only"),
        (
            "quality",
            "enabled",
            "low",
            "submit_quality_report",
            "diagnostic_only",
        ),
        (
            "protocol_repair",
            "disabled",
            None,
            "submit_evaluation",
            "diagnostic_only",
        ),
    ],
)
def test_policy_has_fixed_stage_mapping(
    stage: str,
    thinking_mode: str,
    reasoning_effort: str | None,
    required_tool: str | None,
    disposition: str,
) -> None:
    policy = resolve_model_execution_policy(
        agent_id="写作",
        execution_mode="primary" if stage in {"primary", "reviser"} else stage,
        operation_kind="write_chapter" if stage != "quality" else None,
        stage=stage,
        version="v1",
    )

    assert policy.thinkingMode == thinking_mode
    assert policy.reasoningEffort == reasoning_effort
    assert policy.requiredToolName == required_tool
    assert policy.visibleOutputDisposition == disposition


def test_legacy_policy_keeps_provider_default() -> None:
    policy = resolve_model_execution_policy(
        agent_id="写作",
        execution_mode="primary",
        operation_kind="write_chapter",
        stage="primary",
        version="legacy",
    )

    assert policy.thinkingMode == "provider_default"
    assert policy.reasoningEffort is None
    assert policy.requiredToolName is None


def test_policy_is_strict_and_immutable() -> None:
    policy = ModelExecutionPolicy(
        policyId="policy-v1",
        thinkingMode="enabled",
        reasoningEffort="high",
        visibleOutputDisposition="business",
    )

    with pytest.raises(ValidationError):
        policy.thinkingMode = "disabled"  # type: ignore[misc]
    with pytest.raises(ValueError, match="extra_forbidden"):
        ModelExecutionPolicy(
            policyId="policy-v1",
            thinkingMode="enabled",
            visibleOutputDisposition="business",
            unexpected=True,
        )
