"""Core 权威 V2 Workflow Event 与 SSE snapshot 共享契约。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)

from .execution import ModelProfileRef, ResolvedModelRef

WORKFLOW_EVENT_PROTOCOL_VERSION = "2.0"

WorkflowId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
ProtocolCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]
ErrorCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonBlankPrompt = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]
StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]
StrictNonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
Confidence = Annotated[float, Field(strict=True, ge=0, le=1)]

WorkflowEventType = Literal[
    "run_accepted",
    "intent_resolved",
    "clarification_required",
    "evidence_ready",
    "step_queued",
    "step_started",
    "step_progress",
    "step_finished",
    "candidate_ready",
    "review_started",
    "review_completed",
    "awaiting_user",
    "applying",
    "completed",
    "failed",
    "cancelled",
]
WorkflowRunStatus = Literal[
    "pending",
    "running",
    "waiting_user",
    "completed",
    "failed",
    "cancelled",
]
WorkflowStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
WorkflowLane = Literal["control", "interactive", "creative", "batch_media"]
UsageStatus = Literal["complete", "partial", "unknown"]
ReviewAvailability = Literal["complete", "partial", "unavailable"]
ReviewVerdict = Literal["pass", "issues_found", "cannot_assess"]
ArtifactDecision = Literal["approve", "discard", "revise"]

_FORBIDDEN_EVENT_KEYS = frozenset(
    {
        "chainofthought",
        "chaptercontent",
        "content",
        "contenttext",
        "cot",
        "finalcontent",
        "log",
        "logs",
        "manuscript",
        "modeloutput",
        "providerresponse",
        "rawlog",
        "rawoutput",
        "rawproviderresponse",
        "reasoning",
        "reasoningcontent",
        "replacement",
        "正文",
        "正文内容",
        "模型输出",
    }
)


def _normalized_key(value: str) -> str:
    return value.casefold().replace("_", "").replace("-", "")


def _find_forbidden_event_key(value: object) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and _normalized_key(key) in _FORBIDDEN_EVENT_KEYS:
                return key
            found = _find_forbidden_event_key(nested)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _find_forbidden_event_key(nested)
            if found is not None:
                return found
    return None


class _StrictWorkflowEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def reject_logs_reasoning_and_content(cls, value: object) -> object:
        forbidden = _find_forbidden_event_key(value)
        if forbidden is not None:
            raise ValueError(
                f"Workflow Event/Snapshot 禁止包含日志、reasoning 或正文字段：{forbidden}"
            )
        return value


class RunAcceptedEventPayload(_StrictWorkflowEventModel):
    workflow: ProtocolCode
    operation: ProtocolCode | None = None
    targetType: ProtocolCode | None = None
    targetId: WorkflowId | None = None
    runRevision: StrictPositiveInt

    @model_validator(mode="after")
    def validate_target(self) -> RunAcceptedEventPayload:
        if (self.targetType is None) != (self.targetId is None):
            raise ValueError("run_accepted 的 targetType 与 targetId 必须同时提供或同时省略")
        return self


class IntentResolvedEventPayload(_StrictWorkflowEventModel):
    workflow: ProtocolCode
    operation: ProtocolCode
    targetType: ProtocolCode
    targetId: WorkflowId
    confidence: Confidence


class ClarificationRequiredEventPayload(_StrictWorkflowEventModel):
    clarificationCode: ProtocolCode
    prompt: NonBlankPrompt
    decisionStepId: WorkflowId


class EvidenceReadyEventPayload(_StrictWorkflowEventModel):
    bundleId: WorkflowId
    bundleVersion: StrictPositiveInt
    manifestSha256: Sha256
    totalBytes: StrictNonNegativeInt


class StepQueuedEventPayload(_StrictWorkflowEventModel):
    stepId: WorkflowId
    ordinal: StrictPositiveInt
    purpose: ProtocolCode
    lane: WorkflowLane
    modelProfile: ModelProfileRef
    attemptCount: StrictPositiveInt
    fencingToken: StrictPositiveInt
    reason: ProtocolCode


class StepStartedEventPayload(_StrictWorkflowEventModel):
    stepId: WorkflowId
    ordinal: StrictPositiveInt
    purpose: ProtocolCode
    modelProfile: ModelProfileRef
    attemptCount: StrictPositiveInt
    fencingToken: StrictPositiveInt


class WorkflowStepProgressSnapshot(_StrictWorkflowEventModel):
    progressSequence: StrictPositiveInt
    phase: Literal["preparing", "waiting_provider", "validating", "reporting"]
    elapsedSeconds: StrictNonNegativeInt
    waitingOnProvider: StrictBool
    usageStatus: UsageStatus

    @model_validator(mode="after")
    def validate_waiting_phase(self) -> WorkflowStepProgressSnapshot:
        if self.waitingOnProvider != (self.phase == "waiting_provider"):
            raise ValueError("waitingOnProvider 必须与 waiting_provider 阶段一致")
        return self


class StepProgressEventPayload(WorkflowStepProgressSnapshot):
    stepId: WorkflowId
    fencingToken: StrictPositiveInt
    modelProfile: ModelProfileRef
    resolvedModel: ResolvedModelRef

    @model_validator(mode="after")
    def validate_model_identity(self) -> StepProgressEventPayload:
        _validate_model_resolution(self.modelProfile, self.resolvedModel)
        return self


class StepFinishedEventPayload(_StrictWorkflowEventModel):
    stepId: WorkflowId
    fencingToken: StrictPositiveInt
    status: Literal["completed", "failed", "skipped"]
    errorCode: ErrorCode | None

    @model_validator(mode="after")
    def validate_error(self) -> StepFinishedEventPayload:
        if self.status == "failed" and self.errorCode is None:
            raise ValueError("failed step_finished 必须包含 errorCode")
        if self.status != "failed" and self.errorCode is not None:
            raise ValueError("只有 failed step_finished 可以包含 errorCode")
        return self


class CandidateReadyEventPayload(_StrictWorkflowEventModel):
    stepId: WorkflowId
    artifactId: WorkflowId
    artifactRevision: StrictPositiveInt


class ReviewPendingStepSnapshot(_StrictWorkflowEventModel):
    stepId: WorkflowId
    ordinal: StrictPositiveInt
    purpose: Literal["review"]
    lane: WorkflowLane
    modelProfile: ModelProfileRef
    status: Literal["pending"]
    attemptCount: Literal[0]
    fencingToken: Literal[0]

    @model_validator(mode="before")
    @classmethod
    def require_strict_zero_counters(cls, value: object) -> object:
        if isinstance(value, Mapping):
            for field_name in ("attemptCount", "fencingToken"):
                counter = value.get(field_name)
                if type(counter) is not int or counter != 0:
                    raise ValueError(f"{field_name} 必须是严格整数 0")
        return value


class ReviewStartedEventPayload(_StrictWorkflowEventModel):
    artifactId: WorkflowId
    artifactRevision: StrictPositiveInt
    reviewerSteps: tuple[ReviewPendingStepSnapshot, ...] = Field(
        min_length=1,
        max_length=32,
    )

    @model_validator(mode="after")
    def validate_unique_steps(self) -> ReviewStartedEventPayload:
        keys = [(step.ordinal, step.stepId) for step in self.reviewerSteps]
        if keys != sorted(keys):
            raise ValueError("reviewerSteps 必须按 ordinal、stepId 稳定排序")
        step_ids = [step.stepId for step in self.reviewerSteps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("reviewerSteps 不能包含重复 stepId")
        ordinals = [step.ordinal for step in self.reviewerSteps]
        if len(set(ordinals)) != len(ordinals):
            raise ValueError("reviewerSteps 不能包含重复 ordinal")
        return self


class ReviewCompletedEventPayload(_StrictWorkflowEventModel):
    artifactId: WorkflowId
    artifactRevision: StrictPositiveInt
    evaluationIds: tuple[WorkflowId, ...] = Field(min_length=1, max_length=32)
    mergedVerdict: ReviewVerdict
    reviewAvailability: ReviewAvailability

    @model_validator(mode="after")
    def validate_review(self) -> ReviewCompletedEventPayload:
        if len(set(self.evaluationIds)) != len(self.evaluationIds):
            raise ValueError("evaluationIds 不能重复")
        if self.reviewAvailability == "unavailable" and self.mergedVerdict != "cannot_assess":
            raise ValueError("Reviewer 全部不可用时 mergedVerdict 必须是 cannot_assess")
        return self


class AwaitingUserEventPayload(_StrictWorkflowEventModel):
    artifactId: WorkflowId
    artifactRevision: StrictPositiveInt
    allowedDecisions: tuple[ArtifactDecision, ...] = Field(min_length=1, max_length=3)
    reviewAvailability: ReviewAvailability

    @model_validator(mode="after")
    def validate_unique_decisions(self) -> AwaitingUserEventPayload:
        if len(set(self.allowedDecisions)) != len(self.allowedDecisions):
            raise ValueError("allowedDecisions 不能重复")
        return self


class ApplyingEventPayload(_StrictWorkflowEventModel):
    artifactId: WorkflowId
    artifactRevision: StrictPositiveInt
    decisionStepId: WorkflowId


class CompletedEventPayload(_StrictWorkflowEventModel):
    outcomeType: ProtocolCode
    artifactId: WorkflowId | None = None
    artifactRevision: StrictPositiveInt | None = None
    resultId: WorkflowId | None = None

    @model_validator(mode="after")
    def validate_artifact(self) -> CompletedEventPayload:
        if (self.artifactId is None) != (self.artifactRevision is None):
            raise ValueError("completed 的 artifactId 与 artifactRevision 必须同时提供或同时省略")
        return self


class FailedEventPayload(_StrictWorkflowEventModel):
    errorCode: ErrorCode
    failedStepId: WorkflowId | None = None
    outcomeUnknown: StrictBool


class CancelledEventPayload(_StrictWorkflowEventModel):
    cancelRequestId: WorkflowId
    cancelledStepId: WorkflowId | None = None


type WorkflowEventPayload = (
    RunAcceptedEventPayload
    | IntentResolvedEventPayload
    | ClarificationRequiredEventPayload
    | EvidenceReadyEventPayload
    | StepQueuedEventPayload
    | StepStartedEventPayload
    | StepProgressEventPayload
    | StepFinishedEventPayload
    | CandidateReadyEventPayload
    | ReviewStartedEventPayload
    | ReviewCompletedEventPayload
    | AwaitingUserEventPayload
    | ApplyingEventPayload
    | CompletedEventPayload
    | FailedEventPayload
    | CancelledEventPayload
)

_PAYLOAD_MODEL_BY_EVENT_TYPE: dict[str, type[_StrictWorkflowEventModel]] = {
    "run_accepted": RunAcceptedEventPayload,
    "intent_resolved": IntentResolvedEventPayload,
    "clarification_required": ClarificationRequiredEventPayload,
    "evidence_ready": EvidenceReadyEventPayload,
    "step_queued": StepQueuedEventPayload,
    "step_started": StepStartedEventPayload,
    "step_progress": StepProgressEventPayload,
    "step_finished": StepFinishedEventPayload,
    "candidate_ready": CandidateReadyEventPayload,
    "review_started": ReviewStartedEventPayload,
    "review_completed": ReviewCompletedEventPayload,
    "awaiting_user": AwaitingUserEventPayload,
    "applying": ApplyingEventPayload,
    "completed": CompletedEventPayload,
    "failed": FailedEventPayload,
    "cancelled": CancelledEventPayload,
}


class WorkflowEventEnvelope(_StrictWorkflowEventModel):
    protocolVersion: Literal["2.0"]
    engineVersion: Literal[2]
    runId: WorkflowId
    sequence: StrictPositiveInt
    eventType: WorkflowEventType
    occurredAt: AwareDatetime
    payload: WorkflowEventPayload

    @model_validator(mode="before")
    @classmethod
    def parse_discriminated_payload(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        event_type = value.get("eventType")
        expected_model = (
            _PAYLOAD_MODEL_BY_EVENT_TYPE.get(event_type)
            if isinstance(event_type, str)
            else None
        )
        if expected_model is None or "payload" not in value:
            return value
        raw_payload: Any = value["payload"]
        if isinstance(raw_payload, BaseModel):
            raw_payload = raw_payload.model_dump(mode="python")
        parsed = expected_model.model_validate(raw_payload)
        result = dict(value)
        result["payload"] = parsed
        return result

    @model_validator(mode="after")
    def validate_payload_discriminator(self) -> WorkflowEventEnvelope:
        expected_model = _PAYLOAD_MODEL_BY_EVENT_TYPE[self.eventType]
        if not isinstance(self.payload, expected_model):
            raise ValueError(f"{self.eventType} 与 payload 类型不匹配")
        return self


class WorkflowCurrentStepSnapshot(_StrictWorkflowEventModel):
    stepId: WorkflowId
    ordinal: StrictPositiveInt
    purpose: ProtocolCode
    lane: WorkflowLane
    modelProfile: ModelProfileRef | None
    resolvedModel: ResolvedModelRef | None
    status: WorkflowStepStatus
    attemptCount: StrictNonNegativeInt
    fencingToken: StrictNonNegativeInt
    latestProgress: WorkflowStepProgressSnapshot | None
    errorCode: ErrorCode | None = None

    @model_validator(mode="after")
    def validate_model_identity(self) -> WorkflowCurrentStepSnapshot:
        if self.lane == "control":
            if (
                self.modelProfile is not None
                or self.resolvedModel is not None
                or self.latestProgress is not None
            ):
                raise ValueError("control Step 不能伪造模型身份或模型进度")
            return self

        if self.modelProfile is None:
            raise ValueError("模型 Step 必须携带逻辑 modelProfile")
        if self.status == "pending" and self.latestProgress is not None:
            raise ValueError("pending 模型 Step 的 latestProgress 必须为空")
        if self.status == "running" and self.resolvedModel is None:
            raise ValueError("running 模型 Step 必须携带已冻结 resolvedModel")
        if self.resolvedModel is not None:
            _validate_model_resolution(self.modelProfile, self.resolvedModel)
        return self


class WorkflowArtifactSnapshot(_StrictWorkflowEventModel):
    artifactId: WorkflowId
    artifactRevision: StrictPositiveInt
    status: Literal["draft", "under_review", "awaiting_user", "applying", "applied"]
    actionable: StrictBool
    reviewAvailability: ReviewAvailability | None = None


class WorkflowErrorSnapshot(_StrictWorkflowEventModel):
    errorCode: ErrorCode
    failedStepId: WorkflowId | None = None
    outcomeUnknown: StrictBool


class WorkflowRunSnapshot(_StrictWorkflowEventModel):
    workflow: ProtocolCode
    operation: ProtocolCode | None = None
    status: WorkflowRunStatus
    activeSteps: tuple[WorkflowCurrentStepSnapshot, ...] = Field(max_length=32)
    currentStep: WorkflowCurrentStepSnapshot | None = None
    cancelRequestedAt: AwareDatetime | None = None
    lastEventSequence: StrictNonNegativeInt
    revision: StrictPositiveInt
    artifact: WorkflowArtifactSnapshot | None = None
    error: WorkflowErrorSnapshot | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> WorkflowRunSnapshot:
        active_keys = [(step.ordinal, step.stepId) for step in self.activeSteps]
        if active_keys != sorted(active_keys):
            raise ValueError("activeSteps 必须按 ordinal、stepId 稳定排序")
        if len({step.stepId for step in self.activeSteps}) != len(self.activeSteps):
            raise ValueError("activeSteps 不能包含重复 stepId")
        if len({step.ordinal for step in self.activeSteps}) != len(self.activeSteps):
            raise ValueError("activeSteps 不能包含重复 ordinal")
        if any(step.status not in {"pending", "running"} for step in self.activeSteps):
            raise ValueError("activeSteps 只能包含 pending/running Step")
        if self.activeSteps:
            if self.status not in {"pending", "running"}:
                raise ValueError("只有非终态执行中的 Run 可以包含 activeSteps")
            if self.currentStep != self.activeSteps[0]:
                raise ValueError("currentStep 必须等于 activeSteps 稳定排序后的第一项")
        elif self.currentStep is not None:
            raise ValueError("没有 activeSteps 时 currentStep 必须为空")
        if self.status == "failed" and self.error is None:
            raise ValueError("failed snapshot 必须包含结构化 error")
        if self.status != "failed" and self.error is not None:
            raise ValueError("只有 failed snapshot 可以包含 error")
        if self.status == "cancelled" and self.cancelRequestedAt is None:
            raise ValueError("cancelled snapshot 必须包含 cancelRequestedAt")
        if self.cancelRequestedAt is not None and self.status not in {"running", "cancelled"}:
            raise ValueError("cancelRequestedAt 只允许出现在正在停止或已取消的 snapshot")
        if self.artifact is not None and self.artifact.actionable:
            if (
                self.status != "waiting_user"
                or self.cancelRequestedAt is not None
                or self.artifact.status != "awaiting_user"
            ):
                raise ValueError("Artifact 仅在未取消的 waiting_user Run 中可操作")
        return self


def _validate_model_resolution(
    logical: ModelProfileRef,
    resolved: ResolvedModelRef,
) -> None:
    if logical.deploymentProfileKey != resolved.deploymentProfileKey:
        raise ValueError("逻辑 modelProfile 与 resolvedModel 的部署身份不一致")
    if logical.reasoningMode != resolved.reasoningMode:
        raise ValueError("逻辑 modelProfile 与 resolvedModel 的 reasoning mode 不一致")


class RunSnapshot(_StrictWorkflowEventModel):
    protocolVersion: Literal["2.0"]
    engineVersion: Literal[2]
    runId: WorkflowId
    baseSequence: StrictNonNegativeInt
    snapshot: WorkflowRunSnapshot

    @model_validator(mode="after")
    def validate_base_sequence(self) -> RunSnapshot:
        if self.baseSequence != self.snapshot.lastEventSequence:
            raise ValueError("baseSequence 必须等于 snapshot.lastEventSequence")
        return self


def workflow_event_sse_id(sequence: int) -> str:
    """返回持久 WorkflowEvent 的十进制 SSE ID。"""

    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("WorkflowEvent sequence 必须是正整数")
    return str(sequence)


def run_snapshot_sse_id(base_sequence: int) -> str | None:
    """返回 snapshot 的 SSE ID；尚无事件的 baseSequence=0 不发送 ID。"""

    if isinstance(base_sequence, bool) or not isinstance(base_sequence, int) or base_sequence < 0:
        raise ValueError("Run snapshot baseSequence 必须是非负整数")
    return None if base_sequence == 0 else str(base_sequence)


def workflow_snapshot_is_terminal(snapshot: WorkflowRunSnapshot) -> bool:
    """判断 snapshot 是否为 PostgreSQL 权威终态。"""

    return snapshot.status in {"completed", "failed", "cancelled"}


def workflow_snapshot_is_stopping(snapshot: WorkflowRunSnapshot) -> bool:
    """判断 snapshot 是否已受理取消但尚未收敛为终态。"""

    return snapshot.cancelRequestedAt is not None and not workflow_snapshot_is_terminal(snapshot)
