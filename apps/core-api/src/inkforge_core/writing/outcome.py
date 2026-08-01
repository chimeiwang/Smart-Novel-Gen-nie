from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from ..db.base import utc_now
from .schemas import (
    WritingCommandStatus,
    WritingRunOutcome,
    WritingRunOutcomeCommand,
    WritingRunOutcomeResult,
)

WorkflowPolicy = Literal["long_form", "short_medium"]
ResultKind = Literal[
    "none",
    "review_artifact",
    "short_candidate",
    "check_report",
    "final_message",
]


@dataclass(frozen=True, slots=True)
class WritingRunOutcomeFacts:
    task_phase: str
    task_updated_at: datetime
    workflow: WorkflowPolicy
    command_id: str | None
    command_kind: str | None
    command_status: str | None
    command_updated_at: datetime | None
    operation: str | None
    result_kind: ResultKind
    result_id: str | None
    result_ready: bool


def project_writing_run_outcome(
    facts: WritingRunOutcomeFacts,
    *,
    observed_at: datetime | None = None,
) -> WritingRunOutcome:
    observed = observed_at or utc_now()
    command = _command(facts)
    result = WritingRunOutcomeResult(
        kind=facts.result_kind,
        id=facts.result_id,
        ready=facts.result_ready,
    )
    task_terminal = facts.task_phase in {"completed", "error"}

    if _has_terminal_conflict(facts):
        return _outcome(
            "inconsistent",
            "TASK_COMMAND_TERMINAL_CONFLICT",
            task_terminal,
            command,
            result,
            observed,
        )

    if facts.command_status == "pending":
        return _outcome("queued", "COMMAND_PENDING", task_terminal, command, result, observed)
    if facts.command_status in {"submitted", "processing"}:
        return _outcome("running", "COMMAND_RUNNING", task_terminal, command, result, observed)

    if facts.workflow == "short_medium":
        return _project_short_medium(facts, command, result, observed)
    return _project_long_form(facts, command, result, observed)


def _project_short_medium(
    facts: WritingRunOutcomeFacts,
    command: WritingRunOutcomeCommand | None,
    result: WritingRunOutcomeResult,
    observed_at: datetime,
) -> WritingRunOutcome:
    if facts.task_phase == "error" and facts.command_status == "failed":
        if facts.result_ready:
            return _outcome(
                "inconsistent",
                "SHORT_MEDIUM_RESULT_CONFLICT",
                True,
                command,
                result,
                observed_at,
            )
        return _outcome("failed", "WRITING_RUN_FAILED", True, command, result, observed_at)
    if facts.task_phase == "completed" and facts.command_status == "succeeded":
        expected_kind = "check_report" if facts.operation == "full_check" else "short_candidate"
        if facts.result_kind == expected_kind and facts.result_ready:
            return _outcome(
                "succeeded",
                "SHORT_MEDIUM_RESULT_READY",
                True,
                command,
                result,
                observed_at,
            )
        return _outcome(
            "inconsistent",
            "SHORT_MEDIUM_RESULT_MISSING",
            True,
            command,
            result,
            observed_at,
        )
    return _outcome(
        "inconsistent",
        "SHORT_MEDIUM_STATE_UNRESOLVED",
        facts.task_phase in {"completed", "error"},
        command,
        result,
        observed_at,
    )


def _project_long_form(
    facts: WritingRunOutcomeFacts,
    command: WritingRunOutcomeCommand | None,
    result: WritingRunOutcomeResult,
    observed_at: datetime,
) -> WritingRunOutcome:
    if facts.command_status is None and facts.task_phase == "completed":
        return _outcome(
            "succeeded",
            "LEGACY_WRITING_RUN_SUCCEEDED",
            True,
            command,
            result,
            observed_at,
        )
    if facts.command_status is None and facts.task_phase == "error":
        return _outcome(
            "failed",
            "LEGACY_WRITING_RUN_FAILED",
            True,
            command,
            result,
            observed_at,
        )
    if facts.task_phase in {"active", "waiting_call"} and facts.command_status not in {
        "pending",
        "submitted",
        "processing",
    }:
        return _outcome(
            "running",
            "WRITING_RUN_RECONCILING",
            False,
            command,
            result,
            observed_at,
            reconciliation_required=True,
        )
    if facts.task_phase == "awaiting_user_review":
        if (
            facts.command_status in {None, "succeeded"}
            and facts.result_kind == "review_artifact"
            and facts.result_ready
        ):
            return _outcome(
                "waiting_user",
                "REVIEW_ARTIFACT_READY",
                False,
                command,
                result,
                observed_at,
            )
        return _outcome(
            "inconsistent",
            "AWAITING_REVIEW_ARTIFACT_MISSING",
            False,
            command,
            result,
            observed_at,
        )
    if facts.task_phase == "completed" and facts.command_status == "succeeded":
        return _outcome("succeeded", "WRITING_RUN_SUCCEEDED", True, command, result, observed_at)
    if facts.task_phase == "error" and facts.command_status == "failed":
        return _outcome("failed", "WRITING_RUN_FAILED", True, command, result, observed_at)
    return _outcome(
        "inconsistent",
        "WRITING_RUN_STATE_UNRESOLVED",
        facts.task_phase in {"completed", "error"},
        command,
        result,
        observed_at,
    )


def _has_terminal_conflict(facts: WritingRunOutcomeFacts) -> bool:
    return (
        (facts.task_phase == "completed" and facts.command_status == "failed")
        or (facts.task_phase == "error" and facts.command_status == "succeeded")
        or (
            facts.task_phase in {"completed", "error"}
            and facts.command_status in {"pending", "submitted", "processing"}
        )
    )


def _command(facts: WritingRunOutcomeFacts) -> WritingRunOutcomeCommand | None:
    if (
        facts.command_id is None
        or facts.command_kind is None
        or facts.command_status is None
        or facts.command_updated_at is None
    ):
        return None
    return WritingRunOutcomeCommand(
        id=facts.command_id,
        kind=facts.command_kind,
        status=cast(WritingCommandStatus, facts.command_status),
        updatedAt=facts.command_updated_at,
    )


def _outcome(
    state: Literal[
        "queued",
        "running",
        "waiting_user",
        "succeeded",
        "failed",
        "inconsistent",
    ],
    code: str,
    task_terminal: bool,
    command: WritingRunOutcomeCommand | None,
    result: WritingRunOutcomeResult,
    observed_at: datetime,
    *,
    reconciliation_required: bool = False,
) -> WritingRunOutcome:
    should_close = state in {"waiting_user", "succeeded", "failed", "inconsistent"}
    if state == "inconsistent" and result.ready:
        result = result.model_copy(update={"ready": False})
    return WritingRunOutcome(
        state=state,
        code=code,
        taskTerminal=task_terminal,
        streamShouldClose=should_close,
        reconciliationRequired=state == "inconsistent" or reconciliation_required,
        currentCommand=command,
        result=result,
        observedAt=observed_at,
    )
