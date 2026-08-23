from __future__ import annotations

import pytest
from inkforge_agents.operations.definitions import OPERATION_DEFINITIONS
from inkforge_agents.providers.base import ModelTurnRequest
from inkforge_agents.runtime.model_policy import (
    CREATIVE_OPERATIONS,
    EXPECTED_OPERATION_KINDS,
    LEGACY_PROVIDER_DEFAULT,
    REPORT_OPERATIONS,
    resolve_agent_model_policy,
    resolve_portrait_model_policy,
    resolve_short_medium_model_policy,
)
from pydantic import ValidationError


def test_reviewer_and_quality_disable_thinking() -> None:
    reviewer = resolve_agent_model_policy("reviewer", "write_chapter")
    quality = resolve_agent_model_policy("quality", None)
    assert (reviewer.thinkingMode, reviewer.reasoningEffort) == ("disabled", None)
    assert reviewer.requiredToolName == "submit_evaluation"
    assert (quality.thinkingMode, quality.reasoningEffort) == ("disabled", None)
    assert quality.requiredToolName == "submit_quality_report"


def test_all_operations_have_exactly_one_policy() -> None:
    assert REPORT_OPERATIONS <= set(OPERATION_DEFINITIONS)
    assert REPORT_OPERATIONS.isdisjoint(CREATIVE_OPERATIONS)
    assert set(OPERATION_DEFINITIONS) == CREATIVE_OPERATIONS | REPORT_OPERATIONS
    assert set(OPERATION_DEFINITIONS) == EXPECTED_OPERATION_KINDS


def test_model_turn_request_requires_policy() -> None:
    with pytest.raises(ValidationError, match="policy"):
        ModelTurnRequest(messages=[], tools=[], maxOutputTokens=100)


@pytest.mark.parametrize(
    ("operation", "thinking_mode", "reasoning_effort"),
    [
        ("generate_outline", "enabled", "high"),
        ("generate_manuscript", "enabled", "high"),
        ("replace_selection", "enabled", "high"),
        ("full_check", "disabled", None),
    ],
)
def test_short_medium_policy_matrix(
    operation: str,
    thinking_mode: str,
    reasoning_effort: str | None,
) -> None:
    policy = resolve_short_medium_model_policy(operation)
    assert (policy.thinkingMode, policy.reasoningEffort) == (
        thinking_mode,
        reasoning_effort,
    )


def test_portrait_policy_disables_thinking() -> None:
    policy = resolve_portrait_model_policy()
    assert (policy.thinkingMode, policy.reasoningEffort) == ("disabled", None)


def test_legacy_policy_is_explicit_and_provider_default() -> None:
    assert LEGACY_PROVIDER_DEFAULT.thinkingMode == "provider_default"
    assert LEGACY_PROVIDER_DEFAULT.reasoningEffort is None


def test_unknown_operation_fails() -> None:
    with pytest.raises(ValueError, match="未知 Operation"):
        resolve_agent_model_policy("primary", "not_an_operation")
