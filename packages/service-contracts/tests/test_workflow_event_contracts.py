from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import cast, get_args

import pytest
from inkforge_contracts import (
    WORKFLOW_EVENT_PROTOCOL_VERSION,
    ApplyingEventPayload,
    AwaitingUserEventPayload,
    CancelledEventPayload,
    CandidateReadyEventPayload,
    ClarificationRequiredEventPayload,
    CompletedEventPayload,
    EvidenceReadyEventPayload,
    ExecutionStepAccepted,
    ExecutionStepFailure,
    ExecutionStepProgress,
    ExecutionStepRequest,
    ExecutionStepResult,
    FailedEventPayload,
    IntentResolvedEventPayload,
    ReviewCompletedEventPayload,
    ReviewPendingStepSnapshot,
    ReviewStartedEventPayload,
    RunAcceptedEventPayload,
    RunSnapshot,
    StepFinishedEventPayload,
    StepProgressEventPayload,
    StepQueuedEventPayload,
    StepStartedEventPayload,
    WorkflowCurrentStepSnapshot,
    WorkflowEventEnvelope,
    WorkflowEventType,
    WorkflowRunSnapshot,
    WorkflowStepProgressSnapshot,
    calculate_resolved_model_fingerprint,
    run_snapshot_sse_id,
    workflow_event_sse_id,
    workflow_snapshot_is_stopping,
    workflow_snapshot_is_terminal,
)
from pydantic import BaseModel, ValidationError

NOW = datetime(2026, 8, 31, 8, 30, tzinfo=UTC)
SHA = "a" * 64


def model_profile_payload(
    *,
    profile: str = "writer.chapter_selection.v1",
    deployment_profile_key: str = "deployment.writer.chapter_selection.v1",
    reasoning_mode: str = "bounded",
) -> dict[str, object]:
    return {
        "profile": profile,
        "version": 1,
        "reasoningMode": reasoning_mode,
        "deploymentProfileKey": deployment_profile_key,
        "promptProfile": {
            "name": f"prompt.{profile}",
            "version": 1,
            "sha256": SHA,
        },
    }


def resolved_model_payload(
    *,
    deployment_profile_key: str = "deployment.writer.chapter_selection.v1",
    reasoning_mode: str = "bounded",
    model: str = "fake-writer",
) -> dict[str, object]:
    material = {
        "deploymentProfileKey": deployment_profile_key,
        "provider": "fake",
        "model": model,
        "transportProfile": "transport.fake.v1",
        "endpointProfile": "endpoint.local-fake.v1",
        "structuredOutputRoute": "responses_json_schema_v1",
        "capabilityVersion": "capability.fake.structured-output.v1",
        "reasoningMode": reasoning_mode,
        "supportsRequestIdempotency": True,
    }
    return {
        **material,
        "deploymentFingerprint": calculate_resolved_model_fingerprint(
            deployment_profile_key=deployment_profile_key,
            provider="fake",
            model=model,
            transport_profile="transport.fake.v1",
            endpoint_profile="endpoint.local-fake.v1",
            structured_output_route="responses_json_schema_v1",
            capability_version="capability.fake.structured-output.v1",
            reasoning_mode=reasoning_mode,
            supports_request_idempotency=True,
        ),
    }

EVENT_CASES: dict[str, tuple[type[BaseModel], dict[str, object]]] = {
    "run_accepted": (
        RunAcceptedEventPayload,
        {
            "workflow": "long_serial",
            "operation": "rewrite_chapter_selection",
            "targetType": "chapter_selection",
            "targetId": "selection-1",
            "runRevision": 1,
        },
    ),
    "intent_resolved": (
        IntentResolvedEventPayload,
        {
            "workflow": "long_serial",
            "operation": "rewrite_chapter_selection",
            "targetType": "chapter_selection",
            "targetId": "selection-1",
            "confidence": 0.95,
        },
    ),
    "clarification_required": (
        ClarificationRequiredEventPayload,
        {
            "clarificationCode": "target_required",
            "prompt": "请选择要重写的章节选区",
            "decisionStepId": "step-clarification-1",
        },
    ),
    "evidence_ready": (
        EvidenceReadyEventPayload,
        {
            "bundleId": "bundle-1",
            "bundleVersion": 1,
            "manifestSha256": SHA,
            "totalBytes": 12_345,
        },
    ),
    "step_queued": (
        StepQueuedEventPayload,
        {
            "stepId": "step-generation-1",
            "ordinal": 1,
            "purpose": "generation",
            "lane": "creative",
            "modelProfile": model_profile_payload(),
            "attemptCount": 1,
            "fencingToken": 1,
            "reason": "initial_dispatch",
        },
    ),
    "step_started": (
        StepStartedEventPayload,
        {
            "stepId": "step-generation-1",
            "ordinal": 1,
            "purpose": "generation",
            "modelProfile": model_profile_payload(),
            "attemptCount": 1,
            "fencingToken": 1,
        },
    ),
    "step_progress": (
        StepProgressEventPayload,
        {
            "stepId": "step-generation-1",
            "fencingToken": 1,
            "progressSequence": 2,
            "modelProfile": model_profile_payload(),
            "resolvedModel": resolved_model_payload(),
            "phase": "waiting_provider",
            "elapsedSeconds": 10,
            "waitingOnProvider": True,
            "usageStatus": "partial",
        },
    ),
    "step_finished": (
        StepFinishedEventPayload,
        {
            "stepId": "step-generation-1",
            "fencingToken": 1,
            "status": "completed",
            "errorCode": None,
        },
    ),
    "candidate_ready": (
        CandidateReadyEventPayload,
        {
            "stepId": "step-generation-1",
            "artifactId": "artifact-1",
            "artifactRevision": 1,
        },
    ),
    "review_started": (
        ReviewStartedEventPayload,
        {
            "artifactId": "artifact-1",
            "artifactRevision": 1,
            "reviewerSteps": [
                {
                    "stepId": "step-review-1",
                    "ordinal": 2,
                    "purpose": "review",
                    "lane": "interactive",
                    "modelProfile": model_profile_payload(
                        profile="reviewer.consistency.v1",
                        deployment_profile_key="deployment.reviewer.consistency.v1",
                        reasoning_mode="disabled",
                    ),
                    "status": "pending",
                    "attemptCount": 0,
                    "fencingToken": 0,
                },
                {
                    "stepId": "step-review-2",
                    "ordinal": 3,
                    "purpose": "review",
                    "lane": "interactive",
                    "modelProfile": model_profile_payload(
                        profile="reviewer.editorial.v1",
                        deployment_profile_key="deployment.reviewer.editorial.v1",
                        reasoning_mode="disabled",
                    ),
                    "status": "pending",
                    "attemptCount": 0,
                    "fencingToken": 0,
                },
            ],
        },
    ),
    "review_completed": (
        ReviewCompletedEventPayload,
        {
            "artifactId": "artifact-1",
            "artifactRevision": 1,
            "evaluationIds": ["evaluation-1", "evaluation-2"],
            "mergedVerdict": "pass",
            "reviewAvailability": "complete",
        },
    ),
    "awaiting_user": (
        AwaitingUserEventPayload,
        {
            "artifactId": "artifact-1",
            "artifactRevision": 1,
            "allowedDecisions": ["approve", "discard", "revise"],
            "reviewAvailability": "complete",
        },
    ),
    "applying": (
        ApplyingEventPayload,
        {
            "artifactId": "artifact-1",
            "artifactRevision": 1,
            "decisionStepId": "step-decision-1",
        },
    ),
    "completed": (
        CompletedEventPayload,
        {
            "outcomeType": "approved",
            "artifactId": "artifact-1",
            "artifactRevision": 1,
            "resultId": "chapter-revision-2",
        },
    ),
    "failed": (
        FailedEventPayload,
        {
            "errorCode": "MODEL_TIMEOUT",
            "failedStepId": "step-generation-1",
            "outcomeUnknown": False,
        },
    ),
    "cancelled": (
        CancelledEventPayload,
        {
            "cancelRequestId": "cancel-request-1",
            "cancelledStepId": "step-generation-1",
        },
    ),
}


def event_envelope(event_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "protocolVersion": "2.0",
        "engineVersion": 2,
        "runId": "run-1",
        "sequence": 7,
        "eventType": event_type,
        "occurredAt": NOW,
        "payload": payload,
    }


def running_snapshot_payload() -> dict[str, object]:
    current_step = {
        "stepId": "step-generation-1",
        "ordinal": 1,
        "purpose": "generation",
        "lane": "creative",
        "modelProfile": model_profile_payload(),
        "resolvedModel": resolved_model_payload(),
        "status": "running",
        "attemptCount": 1,
        "fencingToken": 1,
        "latestProgress": {
            "progressSequence": 2,
            "phase": "waiting_provider",
            "elapsedSeconds": 10,
            "waitingOnProvider": True,
            "usageStatus": "partial",
        },
        "errorCode": None,
    }
    return {
        "workflow": "long_serial",
        "operation": "rewrite_chapter_selection",
        "status": "running",
        "activeSteps": [copy.deepcopy(current_step)],
        "currentStep": current_step,
        "cancelRequestedAt": None,
        "lastEventSequence": 7,
        "revision": 3,
        "artifact": None,
        "error": None,
    }


def snapshot_frame(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "protocolVersion": "2.0",
        "engineVersion": 2,
        "runId": "run-1",
        "baseSequence": snapshot["lastEventSequence"],
        "snapshot": snapshot,
    }


def test_event_catalog_covers_exactly_sixteen_durable_event_types() -> None:
    assert WORKFLOW_EVENT_PROTOCOL_VERSION == "2.0"
    assert set(EVENT_CASES) == set(get_args(WorkflowEventType))
    assert len(EVENT_CASES) == 16


@pytest.mark.parametrize(("event_type", "case"), EVENT_CASES.items())
def test_event_envelope_discriminates_all_payloads(
    event_type: str,
    case: tuple[type[BaseModel], dict[str, object]],
) -> None:
    payload_type, payload = case

    event = WorkflowEventEnvelope.model_validate(event_envelope(event_type, payload))

    assert type(event.payload) is payload_type
    assert event.eventType == event_type
    assert workflow_event_sse_id(event.sequence) == "7"
    assert WorkflowEventEnvelope.model_validate_json(event.model_dump_json()) == event


def test_event_envelope_rejects_payload_from_a_different_event_type() -> None:
    _, wrong_payload = EVENT_CASES["run_accepted"]

    with pytest.raises(ValidationError):
        WorkflowEventEnvelope.model_validate(event_envelope("candidate_ready", wrong_payload))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"eventType": "unknown"}),
        lambda value: value.update({"unexpected": True}),
        lambda value: value["payload"].update({"unexpected": True}),
        lambda value: value.update({"sequence": 0}),
        lambda value: value.update({"sequence": True}),
        lambda value: value.update({"engineVersion": 1}),
        lambda value: value.update({"protocolVersion": "1.0"}),
        lambda value: value.update({"occurredAt": datetime(2026, 8, 31, 8, 30)}),
    ],
)
def test_event_envelope_rejects_unknown_fields_and_invalid_identity_or_sequence(
    mutation: object,
) -> None:
    _, payload = EVENT_CASES["candidate_ready"]
    value = event_envelope("candidate_ready", copy.deepcopy(payload))
    assert callable(mutation)
    mutation(value)

    with pytest.raises(ValidationError):
        WorkflowEventEnvelope.model_validate(value)


@pytest.mark.parametrize("forbidden_key", ["logs", "reasoning", "finalContent", "正文"])
def test_event_envelope_rejects_logs_reasoning_and_body_at_any_depth(
    forbidden_key: str,
) -> None:
    _, payload = EVENT_CASES["step_progress"]
    value = event_envelope("step_progress", copy.deepcopy(payload))
    envelope_payload = cast(dict[str, object], value["payload"])
    envelope_payload[forbidden_key] = {"nested": "不得进入事件"}

    with pytest.raises(ValidationError, match="禁止包含"):
        WorkflowEventEnvelope.model_validate(value)


def test_payload_invariants_reject_inconsistent_progress_and_duplicate_ids() -> None:
    _, progress_payload = EVENT_CASES["step_progress"]
    progress = copy.deepcopy(progress_payload)
    progress["waitingOnProvider"] = False
    with pytest.raises(ValidationError, match="waitingOnProvider"):
        WorkflowEventEnvelope.model_validate(event_envelope("step_progress", progress))

    _, review_payload = EVENT_CASES["review_started"]
    review = copy.deepcopy(review_payload)
    reviewer_steps = cast(list[dict[str, object]], review["reviewerSteps"])
    reviewer_steps[1]["stepId"] = "step-review-1"
    with pytest.raises(ValidationError, match="重复 stepId"):
        WorkflowEventEnvelope.model_validate(event_envelope("review_started", review))

    _, awaiting_payload = EVENT_CASES["awaiting_user"]
    awaiting = copy.deepcopy(awaiting_payload)
    awaiting["allowedDecisions"] = ["approve", "approve"]
    with pytest.raises(ValidationError, match="不能重复"):
        WorkflowEventEnvelope.model_validate(event_envelope("awaiting_user", awaiting))


def test_review_started_requires_stable_safe_pending_reviewer_steps() -> None:
    _, raw_payload = EVENT_CASES["review_started"]
    payload = copy.deepcopy(raw_payload)
    reviewer_steps = cast(list[dict[str, object]], payload["reviewerSteps"])

    reviewer_steps.reverse()
    with pytest.raises(ValidationError, match="稳定排序"):
        WorkflowEventEnvelope.model_validate(event_envelope("review_started", payload))

    payload = copy.deepcopy(raw_payload)
    reviewer_steps = cast(list[dict[str, object]], payload["reviewerSteps"])
    reviewer_steps[1]["ordinal"] = reviewer_steps[0]["ordinal"]
    with pytest.raises(ValidationError, match="重复 ordinal"):
        WorkflowEventEnvelope.model_validate(event_envelope("review_started", payload))

    for field, invalid in (
        ("purpose", "generation"),
        ("status", "running"),
        ("attemptCount", 1),
        ("attemptCount", False),
        ("fencingToken", 0.0),
        ("fencingToken", 1),
    ):
        payload = copy.deepcopy(raw_payload)
        reviewer_steps = cast(list[dict[str, object]], payload["reviewerSteps"])
        reviewer_steps[0][field] = invalid
        with pytest.raises(ValidationError):
            WorkflowEventEnvelope.model_validate(
                event_envelope("review_started", payload)
            )


def test_step_finished_requires_status_consistent_nullable_error() -> None:
    _, raw_payload = EVENT_CASES["step_finished"]

    failed_without_error = {**raw_payload, "status": "failed"}
    with pytest.raises(ValidationError, match="必须包含 errorCode"):
        WorkflowEventEnvelope.model_validate(
            event_envelope("step_finished", failed_without_error)
        )

    completed_with_error = {**raw_payload, "errorCode": "MODEL_TIMEOUT"}
    with pytest.raises(ValidationError, match="只有 failed"):
        WorkflowEventEnvelope.model_validate(
            event_envelope("step_finished", completed_with_error)
        )

    failed = {**raw_payload, "status": "failed", "errorCode": "MODEL_TIMEOUT"}
    event = WorkflowEventEnvelope.model_validate(event_envelope("step_finished", failed))
    assert isinstance(event.payload, StepFinishedEventPayload)
    assert event.payload.status == "failed"


def test_running_and_stopping_snapshots_are_distinct_nonterminal_states() -> None:
    running = RunSnapshot.model_validate(snapshot_frame(running_snapshot_payload()))

    assert not workflow_snapshot_is_terminal(running.snapshot)
    assert not workflow_snapshot_is_stopping(running.snapshot)
    assert run_snapshot_sse_id(running.baseSequence) == "7"
    assert running.snapshot.currentStep is not None
    assert running.snapshot.currentStep.latestProgress is not None
    assert running.snapshot.currentStep.latestProgress.progressSequence == 2
    assert running.snapshot.currentStep.latestProgress.elapsedSeconds == 10

    stopping_payload = running_snapshot_payload()
    stopping_payload["cancelRequestedAt"] = NOW
    stopping = RunSnapshot.model_validate(snapshot_frame(stopping_payload))

    assert not workflow_snapshot_is_terminal(stopping.snapshot)
    assert workflow_snapshot_is_stopping(stopping.snapshot)


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_terminal_snapshots_are_explicit(status: str) -> None:
    payload = running_snapshot_payload()
    payload["status"] = status
    payload["activeSteps"] = []
    payload["currentStep"] = None
    if status == "failed":
        payload["error"] = {
            "errorCode": "MODEL_TIMEOUT",
            "failedStepId": "step-generation-1",
            "outcomeUnknown": False,
        }
    if status == "cancelled":
        payload["cancelRequestedAt"] = NOW

    frame = RunSnapshot.model_validate(snapshot_frame(payload))

    assert workflow_snapshot_is_terminal(frame.snapshot)
    assert not workflow_snapshot_is_stopping(frame.snapshot)


def test_snapshot_enforces_failure_cancel_and_artifact_lifecycle() -> None:
    failed_without_error = running_snapshot_payload()
    failed_without_error["status"] = "failed"
    failed_without_error["activeSteps"] = []
    failed_without_error["currentStep"] = None
    with pytest.raises(ValidationError, match="结构化 error"):
        RunSnapshot.model_validate(snapshot_frame(failed_without_error))

    cancelled_without_request = running_snapshot_payload()
    cancelled_without_request["status"] = "cancelled"
    cancelled_without_request["activeSteps"] = []
    cancelled_without_request["currentStep"] = None
    with pytest.raises(ValidationError, match="cancelRequestedAt"):
        RunSnapshot.model_validate(snapshot_frame(cancelled_without_request))

    completed_with_actionable_artifact = running_snapshot_payload()
    completed_with_actionable_artifact.update(
        {
            "status": "completed",
            "activeSteps": [],
            "currentStep": None,
            "artifact": {
                "artifactId": "artifact-1",
                "artifactRevision": 1,
                "status": "awaiting_user",
                "actionable": True,
                "reviewAvailability": "complete",
            },
        }
    )
    with pytest.raises(ValidationError, match="仅在未取消"):
        RunSnapshot.model_validate(snapshot_frame(completed_with_actionable_artifact))

    waiting_user = running_snapshot_payload()
    waiting_user.update(
        {
            "status": "waiting_user",
            "activeSteps": [],
            "currentStep": None,
            "artifact": {
                "artifactId": "artifact-1",
                "artifactRevision": 1,
                "status": "awaiting_user",
                "actionable": True,
                "reviewAvailability": "partial",
            },
        }
    )
    RunSnapshot.model_validate(snapshot_frame(waiting_user))


def test_snapshot_preserves_two_parallel_reviewer_identities() -> None:
    consistency_profile = model_profile_payload(
        profile="reviewer.consistency.v1",
        deployment_profile_key="deployment.reviewer.consistency.v1",
        reasoning_mode="disabled",
    )
    editorial_profile = model_profile_payload(
        profile="reviewer.editorial.v1",
        deployment_profile_key="deployment.reviewer.editorial.v1",
        reasoning_mode="disabled",
    )
    consistency = {
        "stepId": "step-review-consistency",
        "ordinal": 2,
        "purpose": "review",
        "lane": "interactive",
        "modelProfile": consistency_profile,
        "resolvedModel": resolved_model_payload(
            deployment_profile_key="deployment.reviewer.consistency.v1",
            reasoning_mode="disabled",
            model="fake-reviewer-consistency",
        ),
        "status": "running",
        "attemptCount": 1,
        "fencingToken": 3,
        "latestProgress": {
            "progressSequence": 4,
            "phase": "validating",
            "elapsedSeconds": 31,
            "waitingOnProvider": False,
            "usageStatus": "complete",
        },
        "errorCode": None,
    }
    editorial = {
        "stepId": "step-review-editorial",
        "ordinal": 3,
        "purpose": "review",
        "lane": "interactive",
        "modelProfile": editorial_profile,
        "resolvedModel": resolved_model_payload(
            deployment_profile_key="deployment.reviewer.editorial.v1",
            reasoning_mode="disabled",
            model="fake-reviewer-editorial",
        ),
        "status": "running",
        "attemptCount": 1,
        "fencingToken": 4,
        "latestProgress": None,
        "errorCode": None,
    }
    payload = running_snapshot_payload()
    payload["activeSteps"] = [consistency, editorial]
    payload["currentStep"] = consistency

    snapshot = WorkflowRunSnapshot.model_validate(payload)

    assert [step.stepId for step in snapshot.activeSteps] == [
        "step-review-consistency",
        "step-review-editorial",
    ]
    assert [step.modelProfile.profile for step in snapshot.activeSteps if step.modelProfile] == [
        "reviewer.consistency.v1",
        "reviewer.editorial.v1",
    ]
    assert [step.resolvedModel.model for step in snapshot.activeSteps if step.resolvedModel] == [
        "fake-reviewer-consistency",
        "fake-reviewer-editorial",
    ]
    assert snapshot.activeSteps[0].latestProgress is not None
    assert snapshot.activeSteps[0].latestProgress.elapsedSeconds == 31
    assert snapshot.activeSteps[1].latestProgress is None


def test_snapshot_progress_is_strict_and_obeys_step_lifecycle() -> None:
    payload = running_snapshot_payload()
    current = cast(dict[str, object], payload["currentStep"])
    progress = cast(dict[str, object], current["latestProgress"])
    progress["waitingOnProvider"] = False
    payload["activeSteps"] = [copy.deepcopy(current)]
    with pytest.raises(ValidationError, match="waitingOnProvider"):
        WorkflowRunSnapshot.model_validate(payload)

    pending = running_snapshot_payload()
    current = cast(dict[str, object], pending["currentStep"])
    current.update(
        {
            "status": "pending",
            "resolvedModel": None,
        }
    )
    pending["activeSteps"] = [copy.deepcopy(current)]
    with pytest.raises(ValidationError, match="pending.*latestProgress"):
        WorkflowRunSnapshot.model_validate(pending)

    control = running_snapshot_payload()
    current = cast(dict[str, object], control["currentStep"])
    current.update(
        {
            "purpose": "user_confirmation",
            "lane": "control",
            "modelProfile": None,
            "resolvedModel": None,
        }
    )
    control["activeSteps"] = [copy.deepcopy(current)]
    with pytest.raises(ValidationError, match="模型进度"):
        WorkflowRunSnapshot.model_validate(control)

    current["latestProgress"] = None
    control["activeSteps"] = [copy.deepcopy(current)]
    snapshot = WorkflowRunSnapshot.model_validate(control)
    assert snapshot.currentStep is not None
    assert snapshot.currentStep.latestProgress is None


def test_snapshot_rejects_unsorted_or_non_authoritative_active_steps() -> None:
    payload = running_snapshot_payload()
    current = copy.deepcopy(cast(dict[str, object], payload["currentStep"]))
    later = copy.deepcopy(current)
    later.update({"stepId": "step-generation-2", "ordinal": 2})

    payload["activeSteps"] = [later, current]
    payload["currentStep"] = later
    with pytest.raises(ValidationError, match="稳定排序"):
        WorkflowRunSnapshot.model_validate(payload)

    payload["activeSteps"] = [current, later]
    payload["currentStep"] = later
    with pytest.raises(ValidationError, match="第一项"):
        WorkflowRunSnapshot.model_validate(payload)

    payload = running_snapshot_payload()
    payload["activeSteps"] = []
    with pytest.raises(ValidationError, match="没有 activeSteps"):
        WorkflowRunSnapshot.model_validate(payload)


def test_snapshot_and_progress_reject_model_identity_drift() -> None:
    payload = running_snapshot_payload()
    current = cast(dict[str, object], payload["currentStep"])
    current["resolvedModel"] = resolved_model_payload(
        deployment_profile_key="deployment.reviewer.editorial.v1",
        reasoning_mode="disabled",
        model="fake-reviewer-editorial",
    )
    payload["activeSteps"] = [copy.deepcopy(current)]
    with pytest.raises(ValidationError, match="部署身份|reasoning mode"):
        WorkflowRunSnapshot.model_validate(payload)

    _, raw_progress = EVENT_CASES["step_progress"]
    progress = copy.deepcopy(raw_progress)
    progress["resolvedModel"] = resolved_model_payload(
        deployment_profile_key="deployment.reviewer.editorial.v1",
        reasoning_mode="disabled",
        model="fake-reviewer-editorial",
    )
    with pytest.raises(ValidationError, match="部署身份|reasoning mode"):
        WorkflowEventEnvelope.model_validate(event_envelope("step_progress", progress))


def test_snapshot_enforces_base_sequence_unknown_fields_and_forbidden_body() -> None:
    value = snapshot_frame(running_snapshot_payload())
    value["baseSequence"] = 6
    with pytest.raises(ValidationError, match="baseSequence"):
        RunSnapshot.model_validate(value)

    value = snapshot_frame(running_snapshot_payload())
    snapshot = cast(dict[str, object], value["snapshot"])
    snapshot["unexpected"] = True
    with pytest.raises(ValidationError):
        RunSnapshot.model_validate(value)

    value = snapshot_frame(running_snapshot_payload())
    snapshot = cast(dict[str, object], value["snapshot"])
    snapshot["artifact"] = {"content": "候选正文"}
    with pytest.raises(ValidationError, match="禁止包含"):
        RunSnapshot.model_validate(value)


@pytest.mark.parametrize("sequence", [0, -1, True, 1.0, "1"])
def test_event_sse_id_rejects_non_positive_or_non_integer_sequence(sequence: object) -> None:
    with pytest.raises(ValueError, match="正整数"):
        workflow_event_sse_id(sequence)  # type: ignore[arg-type]


def test_snapshot_sse_id_omits_zero_and_reuses_positive_base_sequence() -> None:
    assert run_snapshot_sse_id(0) is None
    assert run_snapshot_sse_id(12) == "12"

    for invalid in (-1, True, 1.0, "1"):
        with pytest.raises(ValueError, match="非负整数"):
            run_snapshot_sse_id(invalid)  # type: ignore[arg-type]


def test_snapshot_schema_is_closed_and_base_sequence_is_nonnegative() -> None:
    schema = RunSnapshot.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["properties"]["protocolVersion"]["const"] == "2.0"
    assert schema["properties"]["engineVersion"]["const"] == 2
    assert schema["properties"]["baseSequence"]["minimum"] == 0


def test_execution_and_public_event_contracts_share_authoritative_model_identity() -> None:
    assert "modelProfile" in ExecutionStepRequest.model_json_schema()["required"]
    for callback_type in (
        ExecutionStepAccepted,
        ExecutionStepProgress,
        ExecutionStepResult,
        ExecutionStepFailure,
    ):
        assert "resolvedModel" in callback_type.model_json_schema()["required"]

    assert "modelProfile" in StepQueuedEventPayload.model_json_schema()["required"]
    assert "modelProfile" in StepStartedEventPayload.model_json_schema()["required"]
    assert {"modelProfile", "resolvedModel"} <= set(
        StepProgressEventPayload.model_json_schema()["required"]
    )

    step_schema = WorkflowCurrentStepSnapshot.model_json_schema()
    assert {"modelProfile", "resolvedModel", "latestProgress"} <= set(
        step_schema["required"]
    )
    assert WorkflowStepProgressSnapshot.model_json_schema()["additionalProperties"] is False
    assert ReviewPendingStepSnapshot.model_json_schema()["additionalProperties"] is False
    snapshot_schema = WorkflowRunSnapshot.model_json_schema()
    assert "activeSteps" in snapshot_schema["required"]


def test_workflow_run_snapshot_rejects_error_outside_failed_state() -> None:
    value = running_snapshot_payload()
    value["error"] = {
        "errorCode": "MODEL_TIMEOUT",
        "failedStepId": "step-generation-1",
        "outcomeUnknown": False,
    }

    with pytest.raises(ValidationError, match="只有 failed"):
        WorkflowRunSnapshot.model_validate(value)
