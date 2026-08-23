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
    agent_id = "写作"
    execution_mode = stage
    if stage in {"reviewer", "protocol_repair"}:
        agent_id = "编辑"
        execution_mode = "reviewer"
    elif stage == "quality":
        agent_id = "校验"
    policy = resolve_model_execution_policy(
        agent_id=agent_id,
        execution_mode=execution_mode,
        operation_kind="write_chapter" if stage != "quality" else None,
        stage=stage,
        version="review-v1",
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


def test_policy_ids_are_canonical_for_every_review_stage() -> None:
    cases = [
        ("写作", "primary", "write_chapter", "primary", "review-v1:primary"),
        ("编辑", "reviewer", "write_chapter", "reviewer", "review-v1:reviewer"),
        ("写作", "reviser", "write_chapter", "reviser", "review-v1:reviser"),
        ("校验", "quality", None, "quality", "review-v1:quality"),
        (
            "编辑",
            "reviewer",
            "write_chapter",
            "protocol_repair",
            "review-v1:protocol-repair",
        ),
    ]

    for agent_id, mode, operation, stage, expected_id in cases:
        policy = resolve_model_execution_policy(
            agent_id=agent_id,
            execution_mode=mode,
            operation_kind=operation,
            stage=stage,
            version="review-v1",
        )
        assert policy.policyId == expected_id


@pytest.mark.parametrize("version", ["", "v1", "review-v2"])
def test_policy_rejects_unknown_version(version: str) -> None:
    with pytest.raises(ValueError, match="模型执行策略版本"):
        resolve_model_execution_policy(
            agent_id="写作",
            execution_mode="primary",
            operation_kind="write_chapter",
            stage="primary",
            version=version,
        )


def test_policy_rejects_mode_stage_mismatch() -> None:
    with pytest.raises(ValueError, match="执行模式与执行阶段不一致"):
        resolve_model_execution_policy(
            agent_id="编辑",
            execution_mode="reviewer",
            operation_kind="write_chapter",
            stage="primary",
            version="review-v1",
        )


def test_policy_rejects_agent_not_allowed_for_operation() -> None:
    with pytest.raises(ValueError, match="AGENT_EXECUTION_MODE_INVALID"):
        resolve_model_execution_policy(
            agent_id="编辑",
            execution_mode="primary",
            operation_kind="write_chapter",
            stage="primary",
            version="review-v1",
        )


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
