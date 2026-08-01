from __future__ import annotations

import importlib
import importlib.util
from datetime import datetime
from typing import Any

NOW = datetime(2026, 8, 1, 12, 0, 0)


def _outcome_module() -> Any:
    module_name = "inkforge_core.writing.outcome"
    assert importlib.util.find_spec(module_name) is not None
    return importlib.import_module(module_name)


def _facts(module: Any, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "task_phase": "active",
        "task_updated_at": NOW,
        "workflow": "long_form",
        "command_id": "command-1",
        "command_kind": "start",
        "command_status": "processing",
        "command_updated_at": NOW,
        "operation": None,
        "result_kind": "none",
        "result_id": None,
        "result_ready": False,
    }
    values.update(overrides)
    return module.WritingRunOutcomeFacts(**values)


def test_short_medium_state_requires_the_real_candidate_or_report() -> None:
    module = _outcome_module()

    queued = module.project_writing_run_outcome(
        _facts(
            module,
            workflow="short_medium",
            command_status="pending",
            operation="generate_outline",
        )
    )
    running = module.project_writing_run_outcome(
        _facts(
            module,
            workflow="short_medium",
            command_status="processing",
            operation="generate_outline",
        )
    )
    succeeded = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="completed",
            workflow="short_medium",
            command_status="succeeded",
            operation="generate_outline",
            result_kind="short_candidate",
            result_id="candidate-1",
            result_ready=True,
        )
    )
    missing_candidate = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="completed",
            workflow="short_medium",
            command_status="succeeded",
            operation="generate_outline",
            result_kind="short_candidate",
            result_id="candidate-1",
            result_ready=False,
        )
    )

    assert queued.state == "queued"
    assert queued.streamShouldClose is False
    assert running.state == "running"
    assert succeeded.state == "succeeded"
    assert succeeded.result.ready is True
    assert succeeded.streamShouldClose is True
    assert missing_candidate.state == "inconsistent"
    assert missing_candidate.code == "SHORT_MEDIUM_RESULT_MISSING"
    assert missing_candidate.reconciliationRequired is True


def test_short_medium_full_check_has_its_own_success_product() -> None:
    module = _outcome_module()

    outcome = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="completed",
            workflow="short_medium",
            command_status="succeeded",
            operation="full_check",
            result_kind="check_report",
            result_ready=True,
        )
    )

    assert outcome.state == "succeeded"
    assert outcome.result.kind == "check_report"
    assert outcome.result.ready is True


def test_long_form_waiting_user_is_not_treated_as_completed() -> None:
    module = _outcome_module()

    outcome = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="awaiting_user_review",
            command_status="succeeded",
            result_kind="review_artifact",
            result_id="artifact-1",
            result_ready=True,
        )
    )

    assert outcome.state == "waiting_user"
    assert outcome.taskTerminal is False
    assert outcome.streamShouldClose is True


def test_terminal_task_and_command_conflicts_are_explicitly_inconsistent() -> None:
    module = _outcome_module()

    completed_with_failed_command = module.project_writing_run_outcome(
        _facts(module, task_phase="completed", command_status="failed")
    )
    error_with_succeeded_command = module.project_writing_run_outcome(
        _facts(module, task_phase="error", command_status="succeeded")
    )

    assert completed_with_failed_command.state == "inconsistent"
    assert completed_with_failed_command.code == "TASK_COMMAND_TERMINAL_CONFLICT"
    assert error_with_succeeded_command.state == "inconsistent"
    assert error_with_succeeded_command.code == "TASK_COMMAND_TERMINAL_CONFLICT"


def test_consistent_long_form_terminal_states_converge() -> None:
    module = _outcome_module()

    succeeded = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="completed",
            command_status="succeeded",
            result_kind="final_message",
            result_ready=True,
        )
    )
    failed = module.project_writing_run_outcome(
        _facts(module, task_phase="error", command_status="failed")
    )

    assert succeeded.state == "succeeded"
    assert succeeded.taskTerminal is True
    assert failed.state == "failed"
    assert failed.taskTerminal is True
    assert failed.streamShouldClose is True


def test_observed_at_can_be_injected_for_a_stable_projection() -> None:
    module = _outcome_module()

    outcome = module.project_writing_run_outcome(
        _facts(module),
        observed_at=NOW,
    )

    assert outcome.observedAt == NOW


def test_only_long_form_missing_active_command_can_wait_for_reconciliation() -> None:
    module = _outcome_module()
    without_command = {
        "command_id": None,
        "command_kind": None,
        "command_status": None,
        "command_updated_at": None,
    }

    long_form = module.project_writing_run_outcome(
        _facts(module, **without_command),
        observed_at=NOW,
    )
    short_medium = module.project_writing_run_outcome(
        _facts(module, workflow="short_medium", **without_command),
        observed_at=NOW,
    )

    assert long_form.state == "running"
    assert long_form.code == "WRITING_RUN_RECONCILING"
    assert long_form.reconciliationRequired is True
    assert long_form.streamShouldClose is False
    assert short_medium.state == "inconsistent"
    assert short_medium.reconciliationRequired is True
    assert short_medium.streamShouldClose is True


def test_long_form_nonterminal_task_reconciles_after_latest_command_is_terminal() -> None:
    module = _outcome_module()

    outcomes = [
        module.project_writing_run_outcome(
            _facts(module, task_phase=phase, command_status=status),
            observed_at=NOW,
        )
        for phase in ("active", "waiting_call")
        for status in ("succeeded", "failed")
    ]

    assert {outcome.state for outcome in outcomes} == {"running"}
    assert {outcome.code for outcome in outcomes} == {"WRITING_RUN_RECONCILING"}
    assert all(outcome.reconciliationRequired for outcome in outcomes)
    assert all(not outcome.streamShouldClose for outcome in outcomes)


def test_inconsistent_projection_never_exposes_a_ready_result() -> None:
    module = _outcome_module()

    outcome = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="completed",
            command_status="failed",
            result_kind="short_candidate",
            result_id="candidate-1",
            result_ready=True,
        ),
        observed_at=NOW,
    )

    assert outcome.state == "inconsistent"
    assert outcome.result.kind == "short_candidate"
    assert outcome.result.id == "candidate-1"
    assert outcome.result.ready is False


def test_terminal_task_with_an_active_command_is_inconsistent() -> None:
    module = _outcome_module()

    outcome = module.project_writing_run_outcome(
        _facts(module, task_phase="completed", command_status="processing"),
        observed_at=NOW,
    )

    assert outcome.state == "inconsistent"
    assert outcome.code == "TASK_COMMAND_TERMINAL_CONFLICT"
    assert outcome.streamShouldClose is True


def test_legacy_long_form_waiting_state_accepts_an_authoritative_artifact_without_command() -> None:
    module = _outcome_module()

    outcome = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="awaiting_user_review",
            command_id=None,
            command_kind=None,
            command_status=None,
            command_updated_at=None,
            result_kind="review_artifact",
            result_id="artifact-1",
            result_ready=True,
        ),
        observed_at=NOW,
    )

    assert outcome.state == "waiting_user"
    assert outcome.taskTerminal is False
    assert outcome.result.ready is True


def test_legacy_long_form_terminal_task_without_command_keeps_terminal_meaning() -> None:
    module = _outcome_module()
    without_command = {
        "command_id": None,
        "command_kind": None,
        "command_status": None,
        "command_updated_at": None,
    }

    succeeded = module.project_writing_run_outcome(
        _facts(module, task_phase="completed", **without_command),
        observed_at=NOW,
    )
    failed = module.project_writing_run_outcome(
        _facts(module, task_phase="error", **without_command),
        observed_at=NOW,
    )
    short_medium = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="completed",
            workflow="short_medium",
            **without_command,
        ),
        observed_at=NOW,
    )

    assert succeeded.state == "succeeded"
    assert failed.state == "failed"
    assert short_medium.state == "inconsistent"


def test_short_medium_failed_task_with_a_success_product_is_inconsistent() -> None:
    module = _outcome_module()

    outcome = module.project_writing_run_outcome(
        _facts(
            module,
            task_phase="error",
            workflow="short_medium",
            command_status="failed",
            operation="generate_manuscript",
            result_kind="short_candidate",
            result_id="candidate-1",
            result_ready=True,
        ),
        observed_at=NOW,
    )

    assert outcome.state == "inconsistent"
    assert outcome.result.ready is False
    assert outcome.reconciliationRequired is True
