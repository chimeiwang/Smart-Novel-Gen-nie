"""无状态、有界且每个 Step 至多一次逻辑模型调用的 V2 执行器。"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Literal, Protocol

import jsonschema_rs
from inkforge_contracts.execution import (
    EvidenceEvaluation,
    ExecutionStepFailure,
    ExecutionStepRequest,
    ExecutionStepResult,
    ResolvedModelRef,
    StepUsage,
    calculate_resolved_model_fingerprint,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
)
from pydantic import JsonValue, ValidationError

from ..providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelProvider,
    ModelStructuredOutputRequest,
    ModelStructuredOutputRoute,
    ModelTurnRequest,
    ModelTurnResult,
    ProviderProtocolError,
    ProviderTransportError,
)
from .registry import (
    ExecutionRegistry,
    ExecutionRegistryReferenceError,
    OutputSchemaDefinition,
    ProfileDefinition,
    PromptProfileDefinition,
    StepBudgetDefinition,
)

ExecutionPurpose = Literal["generation", "review"]
FailureCategory = Literal[
    "provider_transient",
    "provider_terminal",
    "protocol",
    "validation",
    "model_outcome_unknown",
    "cancelled",
    "internal",
]
BeginAttempt = Callable[[], Awaitable[int]]


class ExecutionModelPort(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def transport_profile(self) -> str: ...

    @property
    def endpoint_profile(self) -> str: ...

    @property
    def capability_version(self) -> str: ...

    @property
    def supports_request_idempotency(self) -> bool: ...

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool: ...

    async def run_execution_turn(
        self,
        request: ModelTurnRequest,
        *,
        before_provider: BeginAttempt,
        lane: Literal["interactive", "creative", "batch_media"],
        reviewer: bool = False,
        provider_timeout_seconds: float | None = None,
    ) -> tuple[int, ModelTurnResult]: ...


class ExecutionCapabilityError(RuntimeError):
    """请求未被当前已发布 V2 能力完整授权。"""


class ExecutionProviderGateClosed(RuntimeError):
    """基础设施保护门关闭；调用方必须保留 journal 等待安全恢复。"""


@dataclass(frozen=True, slots=True)
class ResolvedExecutionStep:
    purpose: ExecutionPurpose
    profile: ProfileDefinition
    prompt_profile: PromptProfileDefinition
    output_schema: OutputSchemaDefinition
    budget: StepBudgetDefinition
    rubric_version: str | None
    structured_output_route: ModelStructuredOutputRoute
    resolved_model: ResolvedModelRef


@dataclass(frozen=True, slots=True)
class ProviderCallOutcome:
    result: ModelTurnResult | None
    provider_attempts: int
    elapsed_millis: int
    failure_category: FailureCategory | None = None
    failure_code: str | None = None
    outcome_unknown: bool = False


class StatelessExecutionStepExecutor:
    def __init__(
        self,
        model: ExecutionModelPort,
        *,
        max_output_tokens: int,
        retry_base_seconds: float = 0.05,
    ) -> None:
        if max_output_tokens < 1:
            raise ValueError("V2 execution 模型输出能力必须为正整数")
        if retry_base_seconds < 0:
            raise ValueError("V2 execution 重试退避不能为负数")
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._retry_base_seconds = retry_base_seconds

    def matches_resolved_model(
        self,
        resolved: ResolvedModelRef,
        profile: ProfileDefinition,
    ) -> bool:
        """验证当前 Provider 能精确执行 journal 冻结的部署身份。"""

        if not self._model.supports_structured_output(
            resolved.structuredOutputRoute
        ):
            return False
        try:
            current = _resolved_model(
                profile,
                provider=self._model.provider_name,
                model=self._model.model_name,
                transport_profile=self._model.transport_profile,
                endpoint_profile=self._model.endpoint_profile,
                structured_output_route=resolved.structuredOutputRoute,
                capability_version=self._model.capability_version,
                supports_request_idempotency=self._model.supports_request_idempotency,
            )
        except ExecutionCapabilityError:
            return False
        return current == resolved

    def resolve(
        self,
        request: ExecutionStepRequest,
        registry: ExecutionRegistry,
    ) -> ResolvedExecutionStep:
        if (request.workflow, request.operation) != (
            "long_serial",
            "rewrite_chapter_selection",
        ):
            raise ExecutionCapabilityError("当前执行器尚未实现该 Operation handler")
        profile = registry.profiles.get(request.modelProfile.profile)
        if profile is None:
            raise ExecutionCapabilityError("Execution Model Profile 未保留在 Registry")
        output_schema = registry.output_schemas.get(request.outputSchema.name)
        if output_schema is None:
            raise ExecutionCapabilityError("Execution Output Schema 未保留在 Registry")
        matching_budgets = tuple(
            budget
            for budget in registry.step_budgets.values()
            if budget.supported and _step_budget_matches(request, budget)
        )
        if not matching_budgets:
            raise ExecutionCapabilityError("Execution Step Budget 未保留在 Registry")
        budget = sorted(matching_budgets, key=lambda value: value.key)[0]
        rubric_version: str | None = None
        if request.purpose == "generation":
            purpose: ExecutionPurpose = "generation"
            if profile.purpose != "generation" or output_schema.purpose != "generation":
                raise ExecutionCapabilityError("generation Step 的 Profile/Output 用途不一致")
        elif request.purpose == "review":
            purpose = "review"
            if profile.purpose != "review" or output_schema.purpose != "evaluation":
                raise ExecutionCapabilityError("review Step 的 Profile/Output 用途不一致")
            if request.artifactId is None or request.artifactRevision is None:
                raise ExecutionCapabilityError("Reviewer Step 必须绑定 Artifact revision")
            rubric_version = _frozen_rubric_version(request)
        else:
            raise ExecutionCapabilityError("当前执行器只支持 generation/review Step")

        _validate_profile_ref(request, profile)
        _validate_prompt_profile_ref(request, profile.prompt_profile)
        _validate_output_schema_ref(request, output_schema)
        _validate_step_budget(request, budget)
        if request.budget.maxCompletionTokens < 1:
            raise ExecutionCapabilityError("模型 Step 必须具有正 completion 预算")
        if request.budget.maxCompletionTokens > self._max_output_tokens:
            raise ExecutionCapabilityError("Step completion 预算超过当前部署模型能力")

        structured_output_route = self._structured_output_route()
        try:
            registry.require_authorized_deployment(
                deployment_profile_key=profile.deployment_profile_key,
                provider=self._model.provider_name,
                model=self._model.model_name,
                transport_profile=self._model.transport_profile,
                endpoint_profile=self._model.endpoint_profile,
                structured_output_route=structured_output_route,
                capability_version=self._model.capability_version,
                reasoning_mode=profile.reasoning_mode,
                supports_request_idempotency=self._model.supports_request_idempotency,
            )
        except ExecutionRegistryReferenceError as exc:
            raise ExecutionCapabilityError("当前部署模型未被 Deployment Profile 授权") from exc

        resolved_model = _resolved_model(
            profile,
            provider=self._model.provider_name,
            model=self._model.model_name,
            transport_profile=self._model.transport_profile,
            endpoint_profile=self._model.endpoint_profile,
            structured_output_route=structured_output_route,
            capability_version=self._model.capability_version,
            supports_request_idempotency=self._model.supports_request_idempotency,
        )
        return ResolvedExecutionStep(
            purpose=purpose,
            profile=profile,
            prompt_profile=profile.prompt_profile,
            output_schema=output_schema,
            budget=budget,
            rubric_version=rubric_version,
            structured_output_route=structured_output_route,
            resolved_model=resolved_model,
        )

    def build_model_request(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep,
    ) -> ModelTurnRequest:
        route = resolved.structured_output_route
        system_prompt = resolved.prompt_profile.system_prompt
        input_envelope = {
            "protocolVersion": "2.0",
            "workflow": request.workflow,
            "operation": request.operation,
            "purpose": request.purpose,
            "input": request.input,
            "outputSchema": request.outputSchema.model_dump(
                mode="json",
                by_alias=True,
            ),
            "evidenceBundle": request.evidenceBundle.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
        }
        user_content = canonical_execution_json_bytes(input_envelope).decode("utf-8")
        structured = ModelStructuredOutputRequest(
            route=route,
            name=_structured_output_name(request.outputSchema.name),
            jsonSchema=request.outputSchema.jsonSchema,
        )
        policy = ModelExecutionPolicy(
            policyId=request.modelProfile.profile,
            thinkingMode=(
                "enabled" if request.modelProfile.reasoningMode == "bounded" else "disabled"
            ),
            reasoningEffort=("high" if request.modelProfile.reasoningMode == "bounded" else None),
        )
        model_request = ModelTurnRequest(
            messages=[
                ModelMessage(role="system", content=system_prompt),
                ModelMessage(role="user", content=user_content),
            ],
            tools=[],
            maxOutputTokens=request.budget.maxCompletionTokens,
            policy=policy,
            thinkingMode=(
                "provider_default"
                if request.modelProfile.reasoningMode == "bounded"
                else "disabled"
            ),
            parallelToolCalls=False,
            structuredOutput=structured,
            requestIdempotencyKey=request.idempotencyKey,
        )
        estimated_input = sum(len(message.content) for message in model_request.messages)
        estimated_input += len(structured.model_dump_json())
        if estimated_input > request.budget.maxInputTokens:
            raise ExecutionCapabilityError("完整模型输入超过 Step maxInputTokens")
        return model_request

    async def call_provider(
        self,
        request: ExecutionStepRequest,
        model_request: ModelTurnRequest,
        *,
        begin_attempt: BeginAttempt,
        cancel_event: asyncio.Event,
    ) -> ProviderCallOutcome:
        provider_started: float | None = None
        attempts = 0

        async def record_attempt() -> int:
            nonlocal attempts, provider_started
            attempts = await begin_attempt()
            if provider_started is None:
                # lane/admission 初始排队不属于供应商墙钟；AOF attempt 成功后才起算。
                provider_started = monotonic()
            return attempts

        def elapsed_millis() -> int:
            return 0 if provider_started is None else _elapsed_millis(provider_started)

        def timeout_boundary_millis() -> int:
            # asyncio 取消与事件循环调度可能比授权截止点晚几个毫秒返回；这部分
            # 本地收尾延迟不属于 Provider 墙钟事实，不能伪造为模型超预算。
            return min(
                elapsed_millis(), request.budget.maxWallClockSeconds * 1_000
            )

        def remaining_seconds() -> float:
            if provider_started is None:
                return float(request.budget.maxWallClockSeconds)
            remaining = request.budget.maxWallClockSeconds - (
                monotonic() - provider_started
            )
            if remaining <= 0:
                raise TimeoutError
            return remaining

        try:
            while True:
                try:
                    if provider_started is None:
                        attempts, result = await _call_with_cancel(
                            self._model,
                            model_request,
                            before_provider=record_attempt,
                            cancel_event=cancel_event,
                            lane=request.lane,
                            reviewer=request.purpose == "review",
                            provider_timeout_seconds=float(
                                request.budget.maxWallClockSeconds
                            ),
                        )
                    else:
                        async with asyncio.timeout(remaining_seconds()):
                            attempts, result = await _call_with_cancel(
                                self._model,
                                model_request,
                                before_provider=record_attempt,
                                cancel_event=cancel_event,
                                lane=request.lane,
                                reviewer=request.purpose == "review",
                                provider_timeout_seconds=None,
                            )
                except _ProviderCancelled as cancelled:
                    return ProviderCallOutcome(
                        result=cancelled.result,
                        provider_attempts=attempts,
                        elapsed_millis=elapsed_millis(),
                        failure_category="cancelled",
                        failure_code="RUN_CANCELLED",
                    )
                except ExecutionProviderGateClosed:
                    raise
                except ProviderTransportError as exc:
                    retry_safe = _safe_to_retry(
                        exc,
                        supports_request_idempotency=(self._model.supports_request_idempotency),
                    )
                    if retry_safe and attempts <= request.budget.maxProviderRetries:
                        async with asyncio.timeout(remaining_seconds()):
                            await asyncio.sleep(
                                _retry_delay_seconds(
                                    self._retry_base_seconds,
                                    attempts,
                                    request.requestHash,
                                )
                            )
                        continue
                    if _provider_outcome_unknown(
                        exc,
                        supports_request_idempotency=(
                            self._model.supports_request_idempotency
                        )
                    ):
                        return ProviderCallOutcome(
                            result=None,
                            provider_attempts=attempts,
                            elapsed_millis=elapsed_millis(),
                            failure_category="model_outcome_unknown",
                            failure_code="MODEL_OUTCOME_UNKNOWN",
                            outcome_unknown=True,
                        )
                    if not retry_safe:
                        return ProviderCallOutcome(
                            result=None,
                            provider_attempts=attempts,
                            elapsed_millis=elapsed_millis(),
                            failure_category="provider_terminal",
                            failure_code="MODEL_PROVIDER_REJECTED",
                        )
                    return ProviderCallOutcome(
                        result=None,
                        provider_attempts=attempts,
                        elapsed_millis=elapsed_millis(),
                        failure_category="provider_transient",
                        failure_code="MODEL_PROVIDER_RETRY_EXHAUSTED",
                    )
                except ProviderProtocolError:
                    return ProviderCallOutcome(
                        result=None,
                        provider_attempts=attempts,
                        elapsed_millis=elapsed_millis(),
                        failure_category="protocol",
                        failure_code="MODEL_PROVIDER_PROTOCOL_INVALID",
                    )
                except TimeoutError:
                    if (
                        self._model.supports_request_idempotency
                        and attempts > 0
                        and attempts <= request.budget.maxProviderRetries
                    ):
                        async with asyncio.timeout(remaining_seconds()):
                            await asyncio.sleep(
                                _retry_delay_seconds(
                                    self._retry_base_seconds,
                                    attempts,
                                    request.requestHash,
                                )
                            )
                        continue
                    return ProviderCallOutcome(
                        result=None,
                        provider_attempts=attempts,
                        elapsed_millis=timeout_boundary_millis(),
                        failure_category="model_outcome_unknown",
                        failure_code="MODEL_OUTCOME_UNKNOWN",
                        outcome_unknown=True,
                    )
                except Exception:
                    if attempts > 0:
                        return ProviderCallOutcome(
                            result=None,
                            provider_attempts=attempts,
                            elapsed_millis=elapsed_millis(),
                            failure_category="model_outcome_unknown",
                            failure_code="MODEL_OUTCOME_UNKNOWN",
                            outcome_unknown=True,
                        )
                    return ProviderCallOutcome(
                        result=None,
                        provider_attempts=attempts,
                        elapsed_millis=elapsed_millis(),
                        failure_category="internal",
                        failure_code="MODEL_PROVIDER_INTERNAL_ERROR",
                    )
                return ProviderCallOutcome(
                    result=result,
                    provider_attempts=attempts,
                    elapsed_millis=elapsed_millis(),
                )
        except TimeoutError:
            return ProviderCallOutcome(
                result=None,
                provider_attempts=attempts,
                elapsed_millis=timeout_boundary_millis(),
                failure_category="model_outcome_unknown",
                failure_code="MODEL_OUTCOME_UNKNOWN",
                outcome_unknown=True,
            )

    def terminal_from_outcome(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep,
        outcome: ProviderCallOutcome,
        *,
        cancel_request_id: str | None = None,
        completed_at: datetime | None = None,
    ) -> ExecutionStepResult | ExecutionStepFailure:
        now = completed_at or datetime.now(UTC)
        if cancel_request_id is not None or outcome.failure_category == "cancelled":
            usage = _usage(
                outcome.result,
                provider_attempts=outcome.provider_attempts,
                wall_time_millis=outcome.elapsed_millis,
                reasoning_mode=request.modelProfile.reasoningMode,
            )
            error_code = (
                "STEP_BUDGET_EXCEEDED"
                if _step_budget_exceeded(request, usage)
                else "RUN_CANCELLED"
            )
            return _failure(
                request,
                resolved.resolved_model,
                usage=usage,
                category="cancelled",
                code=error_code,
                outcome_unknown=False,
                cancel_request_id=cancel_request_id,
                failed_at=now,
            )
        if outcome.failure_category is not None:
            usage = _unknown_usage(
                provider_attempts=outcome.provider_attempts,
                wall_time_millis=outcome.elapsed_millis,
            )
            category = outcome.failure_category
            code = outcome.failure_code or "MODEL_EXECUTION_FAILED"
            if (
                not outcome.outcome_unknown
                and _step_budget_exceeded(request, usage)
            ):
                category = "validation"
                code = "STEP_BUDGET_EXCEEDED"
            return _failure(
                request,
                resolved.resolved_model,
                usage=usage,
                category=category,
                code=code,
                outcome_unknown=outcome.outcome_unknown,
                failed_at=now,
            )
        result = outcome.result
        if result is None:
            return _failure(
                request,
                resolved.resolved_model,
                usage=_unknown_usage(
                    provider_attempts=outcome.provider_attempts,
                    wall_time_millis=outcome.elapsed_millis,
                ),
                category="internal",
                code="MODEL_RESULT_MISSING",
                outcome_unknown=False,
                failed_at=now,
            )
        usage = _usage(
            result,
            provider_attempts=outcome.provider_attempts,
            wall_time_millis=outcome.elapsed_millis,
            reasoning_mode=request.modelProfile.reasoningMode,
        )
        failure = _validate_provider_result(request, result, usage)
        if failure is not None:
            return _failure(
                request,
                resolved.resolved_model,
                usage=usage,
                category=failure[0],
                code=failure[1],
                outcome_unknown=False,
                failed_at=now,
            )
        structured_output = result.structuredOutput
        if structured_output is None:
            return _failure(
                request,
                resolved.resolved_model,
                usage=usage,
                category="protocol",
                code="MODEL_STRUCTURED_OUTPUT_INVALID",
                outcome_unknown=False,
                failed_at=now,
            )
        if resolved.purpose == "generation":
            output = _derive_generation_output(request, structured_output)
            result_kind = "output"
            value: dict[str, JsonValue] | EvidenceEvaluation = output
        else:
            try:
                evaluation = _evaluation(request, resolved, structured_output)
            except (TypeError, ValueError, ValidationError):
                return _failure(
                    request,
                    resolved.resolved_model,
                    usage=usage,
                    category="validation",
                    code="MODEL_EVALUATION_INVALID",
                    outcome_unknown=False,
                    failed_at=now,
                )
            result_kind = "evaluation"
            value = evaluation
        hash_value: object = (
            value.model_dump(mode="json", exclude_none=True)
            if isinstance(value, EvidenceEvaluation)
            else value
        )
        result_hash = canonical_execution_sha256(
            {
                "resultKind": result_kind,
                "resolvedModel": resolved.resolved_model.model_dump(mode="json", exclude_none=True),
                "usage": usage.model_dump(mode="json", exclude_none=True),
                "value": hash_value,
            }
        )
        if isinstance(value, EvidenceEvaluation):
            return ExecutionStepResult(
                protocolVersion="2.0",
                jobId=request.jobId,
                runId=request.runId,
                novelId=request.novelId,
                stepId=request.stepId,
                fencingToken=request.fencingToken,
                requestHash=request.requestHash,
                inputHash=request.inputHash,
                resolvedModel=resolved.resolved_model,
                resultKind="evaluation",
                evaluation=value,
                resultHash=result_hash,
                usage=usage,
                completedAt=now,
            )
        return ExecutionStepResult(
            protocolVersion="2.0",
            jobId=request.jobId,
            runId=request.runId,
            novelId=request.novelId,
            stepId=request.stepId,
            fencingToken=request.fencingToken,
            requestHash=request.requestHash,
            inputHash=request.inputHash,
            resolvedModel=resolved.resolved_model,
            resultKind="output",
            output=value,
            resultHash=result_hash,
            usage=usage,
            completedAt=now,
        )

    def _structured_output_route(self) -> ModelStructuredOutputRoute:
        for route in ("responses_json_schema_v1", "chat_json_output_v1"):
            if self._model.supports_structured_output(route):
                return route
        raise ExecutionCapabilityError("当前 Provider 不支持严格结构化输出")


class ProviderModelRuntimeAdapter:
    """给测试或独立组装使用的 Provider 适配器；生产优先复用全局 ModelRuntime。"""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    @property
    def transport_profile(self) -> str:
        return self._provider.transport_profile

    @property
    def endpoint_profile(self) -> str:
        return self._provider.endpoint_profile

    @property
    def capability_version(self) -> str:
        return self._provider.capability_version

    @property
    def supports_request_idempotency(self) -> bool:
        return bool(getattr(self._provider, "supports_request_idempotency", False))

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        checker = getattr(self._provider, "supports_structured_output", None)
        return bool(checker(route)) if callable(checker) else False

    async def run_execution_turn(
        self,
        request: ModelTurnRequest,
        *,
        before_provider: BeginAttempt,
        lane: Literal["interactive", "creative", "batch_media"] = "interactive",
        reviewer: bool = False,
        provider_timeout_seconds: float | None = None,
    ) -> tuple[int, ModelTurnResult]:
        del lane, reviewer
        attempt = await before_provider()
        if provider_timeout_seconds is None:
            return attempt, await self._provider.complete_turn(request)
        async with asyncio.timeout(provider_timeout_seconds):
            return attempt, await self._provider.complete_turn(request)


class _ProviderCancelled(Exception):
    def __init__(self, result: ModelTurnResult | None) -> None:
        self.result = result
        super().__init__("provider_cancelled")


async def _call_with_cancel(
    model: ExecutionModelPort,
    request: ModelTurnRequest,
    *,
    before_provider: BeginAttempt,
    cancel_event: asyncio.Event,
    lane: Literal["interactive", "creative", "batch_media"],
    reviewer: bool,
    provider_timeout_seconds: float | None,
) -> tuple[int, ModelTurnResult]:
    provider_task = asyncio.create_task(
        model.run_execution_turn(
            request,
            before_provider=before_provider,
            lane=lane,
            reviewer=reviewer,
            provider_timeout_seconds=provider_timeout_seconds,
        )
    )
    cancel_task = asyncio.create_task(cancel_event.wait())
    try:
        done, _ = await asyncio.wait(
            {provider_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done and cancel_event.is_set():
            result: ModelTurnResult | None = None
            if provider_task.done() and not provider_task.cancelled():
                try:
                    _, result = provider_task.result()
                except Exception:
                    result = None
            else:
                provider_task.cancel()
                await asyncio.gather(provider_task, return_exceptions=True)
            raise _ProviderCancelled(result)
        return provider_task.result()
    finally:
        cancel_task.cancel()
        await asyncio.gather(cancel_task, return_exceptions=True)


def _validate_profile_ref(
    request: ExecutionStepRequest,
    profile: ProfileDefinition,
) -> None:
    expected = (
        profile.key,
        profile.version,
        profile.reasoning_mode,
        profile.deployment_profile_key,
    )
    actual = (
        request.modelProfile.profile,
        request.modelProfile.version,
        request.modelProfile.reasoningMode,
        request.modelProfile.deploymentProfileKey,
    )
    if actual != expected or not profile.supported:
        raise ExecutionCapabilityError("Execution Model Profile 与 Registry 不一致")


def _validate_prompt_profile_ref(
    request: ExecutionStepRequest,
    prompt: PromptProfileDefinition,
) -> None:
    expected = (prompt.key, prompt.version, prompt.sha256)
    reference = request.modelProfile.promptProfile
    actual = (reference.name, reference.version, reference.sha256)
    if actual != expected or not prompt.supported:
        raise ExecutionCapabilityError("Execution Prompt Profile 与 Registry 不一致")


def _validate_output_schema_ref(
    request: ExecutionStepRequest,
    schema: OutputSchemaDefinition,
) -> None:
    if not schema.supported:
        raise ExecutionCapabilityError("Execution Output Schema 尚未实现")
    expected = (
        schema.key,
        schema.version,
        schema.sha256,
        canonical_execution_sha256(schema.json_schema_value()),
    )
    actual = (
        request.outputSchema.name,
        request.outputSchema.version,
        request.outputSchema.sha256,
        canonical_execution_sha256(request.outputSchema.jsonSchema),
    )
    if actual != expected:
        raise ExecutionCapabilityError("Execution Output Schema 与 Registry 不一致")


def _validate_step_budget(
    request: ExecutionStepRequest,
    budget: StepBudgetDefinition,
) -> None:
    if not _step_budget_matches(request, budget) or not budget.supported:
        raise ExecutionCapabilityError("Execution Step Budget 与 Registry 不一致")


def _step_budget_matches(
    request: ExecutionStepRequest,
    budget: StepBudgetDefinition,
) -> bool:
    expected = (
        budget.max_model_calls,
        budget.max_input_tokens,
        budget.max_prompt_cache_miss_tokens,
        budget.max_completion_tokens,
        budget.max_reasoning_tokens,
        budget.max_visible_output_tokens,
        budget.max_cost_micros,
        budget.max_wall_clock_seconds,
        budget.max_provider_retries,
        budget.max_protocol_corrections,
    )
    actual = (
        request.budget.maxModelCalls,
        request.budget.maxInputTokens,
        request.budget.maxPromptCacheMissTokens,
        request.budget.maxCompletionTokens,
        request.budget.maxReasoningTokens,
        request.budget.maxVisibleOutputTokens,
        request.budget.maxCostMicros,
        request.budget.maxWallClockSeconds,
        request.budget.maxProviderRetries,
        request.budget.maxProtocolCorrections,
    )
    return actual == expected


def _frozen_rubric_version(request: ExecutionStepRequest) -> str:
    task = request.input.get("task")
    if not isinstance(task, Mapping):
        raise ExecutionCapabilityError("Reviewer input 缺少冻结任务目标")
    rubric = task.get("rubricVersion")
    if not isinstance(rubric, str) or re.fullmatch(
        r"[a-z][a-z0-9_.-]{0,127}", rubric
    ) is None:
        raise ExecutionCapabilityError("Reviewer input 缺少冻结 rubricVersion")
    return rubric


def _resolved_model(
    profile: ProfileDefinition,
    *,
    provider: str,
    model: str,
    transport_profile: str,
    endpoint_profile: str,
    structured_output_route: ModelStructuredOutputRoute,
    capability_version: str,
    supports_request_idempotency: bool,
) -> ResolvedModelRef:
    fingerprint = calculate_resolved_model_fingerprint(
        deployment_profile_key=profile.deployment_profile_key,
        provider=provider,
        model=model,
        transport_profile=transport_profile,
        endpoint_profile=endpoint_profile,
        structured_output_route=structured_output_route,
        capability_version=capability_version,
        reasoning_mode=profile.reasoning_mode,
        supports_request_idempotency=supports_request_idempotency,
    )
    try:
        return ResolvedModelRef(
            deploymentProfileKey=profile.deployment_profile_key,
            deploymentFingerprint=fingerprint,
            provider=provider,
            model=model,
            transportProfile=transport_profile,
            endpointProfile=endpoint_profile,
            structuredOutputRoute=structured_output_route,
            capabilityVersion=capability_version,
            reasoningMode=profile.reasoning_mode,
            supportsRequestIdempotency=supports_request_idempotency,
        )
    except ValidationError as exc:
        raise ExecutionCapabilityError("部署模型标识不符合 V2 契约") from exc


def _structured_output_name(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in value)
    return normalized[:128]


def _retry_delay_seconds(base_seconds: float, attempt: int, request_hash: str) -> float:
    """按 requestHash 与 attempt 生成稳定抖动，重启可复现且不同请求不会惊群。"""

    material = f"{request_hash}:{attempt}".encode("ascii")
    fraction = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") / ((1 << 64) - 1)
    jitter_factor = 0.75 + (0.5 * fraction)
    exponential = 2.0 ** max(0, attempt - 1)
    return base_seconds * exponential * jitter_factor


def _safe_to_retry(
    error: ProviderTransportError,
    *,
    supports_request_idempotency: bool,
) -> bool:
    if error.code == "http_error" and error.statusCode == 429:
        return True
    if not supports_request_idempotency:
        return False
    if error.code in {"connection_error", "timeout_error"}:
        return True
    return error.code == "http_error" and (
        error.statusCode is not None and error.statusCode >= 500
    )


def _provider_outcome_unknown(
    error: ProviderTransportError,
    *,
    supports_request_idempotency: bool,
) -> bool:
    if supports_request_idempotency:
        return False
    if error.code in {"connection_error", "timeout_error"}:
        return True
    return (
        error.code == "http_error"
        and error.statusCode is not None
        and error.statusCode >= 500
    )


def _elapsed_millis(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _usage(
    result: ModelTurnResult | None,
    *,
    provider_attempts: int,
    wall_time_millis: int,
    reasoning_mode: Literal["disabled", "bounded"],
) -> StepUsage:
    if result is None:
        return _unknown_usage(
            provider_attempts=provider_attempts,
            wall_time_millis=wall_time_millis,
        )
    input_tokens = result.usage.promptTokens
    cached_tokens = result.usage.cachedTokens
    protocol_corrections = result.structuredOutputCorrectionCount
    if cached_tokens > input_tokens:
        return _unknown_usage(
            provider_attempts=provider_attempts,
            wall_time_millis=wall_time_millis,
            protocol_corrections=protocol_corrections,
        )
    cache_miss_tokens = input_tokens - cached_tokens
    completion_tokens = result.usage.completionTokens
    reasoning_tokens = result.diagnostics.reasoningTokens
    if reasoning_mode == "disabled":
        reasoning_tokens = 0
    visible_tokens = (
        completion_tokens - reasoning_tokens
        if reasoning_tokens is not None and reasoning_tokens <= completion_tokens
        else None
    )
    return StepUsage(
        usageStatus="partial",
        providerAttempts=provider_attempts,
        protocolCorrections=protocol_corrections,
        wallTimeMillis=wall_time_millis,
        inputTokens=input_tokens,
        cachedTokens=cached_tokens,
        promptCacheMissTokens=cache_miss_tokens,
        completionTokens=completion_tokens,
        reasoningTokens=reasoning_tokens,
        visibleOutputTokens=visible_tokens,
        costMicros=None,
    )


def _unknown_usage(
    *,
    provider_attempts: int,
    wall_time_millis: int,
    protocol_corrections: int = 0,
) -> StepUsage:
    return StepUsage(
        usageStatus="unknown",
        providerAttempts=provider_attempts,
        protocolCorrections=protocol_corrections,
        wallTimeMillis=wall_time_millis,
    )


def _validate_provider_result(
    request: ExecutionStepRequest,
    result: ModelTurnResult,
    usage: StepUsage,
) -> tuple[Literal["provider_terminal", "protocol", "validation"], str] | None:
    if _step_budget_exceeded(request, usage):
        return "validation", "STEP_BUDGET_EXCEEDED"
    if usage.usageStatus == "unknown":
        return "protocol", "MODEL_USAGE_INVALID"
    if result.usage.totalTokens != (result.usage.promptTokens + result.usage.completionTokens):
        return "protocol", "MODEL_USAGE_INVALID"
    if result.finishReason == "length":
        return "provider_terminal", "MODEL_OUTPUT_TRUNCATED"
    if result.finishReason == "content_filter":
        return "provider_terminal", "MODEL_OUTPUT_FILTERED"
    if result.finishReason != "stop":
        return "protocol", "MODEL_FINISH_REASON_INVALID"
    if result.structuredOutputDiagnostic is not None or result.structuredOutput is None:
        return "protocol", "MODEL_STRUCTURED_OUTPUT_INVALID"
    if request.purpose == "generation":
        replacement = result.structuredOutput.get("replacement")
        if not isinstance(replacement, str) or not replacement.strip():
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    try:
        jsonschema_rs.validator_for(request.outputSchema.jsonSchema).validate(
            result.structuredOutput
        )
    except Exception:
        return "validation", "MODEL_OUTPUT_SCHEMA_INVALID"
    return None


def _step_budget_exceeded(
    request: ExecutionStepRequest,
    usage: StepUsage,
) -> bool:
    budget = request.budget
    dimensions = (
        (usage.inputTokens, budget.maxInputTokens),
        (usage.promptCacheMissTokens, budget.maxPromptCacheMissTokens),
        (usage.completionTokens, budget.maxCompletionTokens),
        (usage.reasoningTokens, budget.maxReasoningTokens),
        (usage.visibleOutputTokens, budget.maxVisibleOutputTokens),
        (usage.costMicros, budget.maxCostMicros),
    )
    return (
        usage.providerAttempts > budget.maxProviderRetries + 1
        or usage.protocolCorrections > budget.maxProtocolCorrections
        or usage.wallTimeMillis > budget.maxWallClockSeconds * 1000
        or any(value is not None and value > limit for value, limit in dimensions)
    )


def _derive_generation_output(
    request: ExecutionStepRequest,
    provider_output: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    output = dict(provider_output)
    if (
        request.workflow == "long_serial"
        and request.operation == "rewrite_chapter_selection"
    ):
        replacement = output.get("replacement")
        if not isinstance(replacement, str) or not replacement.strip():
            raise ExecutionCapabilityError("章节选区改写结果缺少 replacement")
        output["contentSha256"] = hashlib.sha256(replacement.encode("utf-8")).hexdigest()
    return output


def _evaluation(
    request: ExecutionStepRequest,
    resolved: ResolvedExecutionStep,
    output: Mapping[str, JsonValue],
) -> EvidenceEvaluation:
    findings = output.get("findings")
    verdict = output.get("contentVerdict")
    if not isinstance(findings, list) or not isinstance(verdict, str):
        raise ValueError("Reviewer 输出缺少 verdict/findings")
    evidence_by_id = {
        item.id: item.contentSha256
        for item in request.evidenceBundle.items
        if item.exists and item.contentSha256 is not None
    }
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("Reviewer finding 不是对象")
        references = finding.get("evidence")
        if not isinstance(references, list):
            raise ValueError("Reviewer finding 缺少 evidence")
        for reference in references:
            if not isinstance(reference, dict):
                raise ValueError("Reviewer evidence reference 不是对象")
            item_id = reference.get("evidenceItemId")
            content_sha = reference.get("contentSha256")
            if not isinstance(item_id, str) or evidence_by_id.get(item_id) != content_sha:
                raise ValueError("Reviewer 引用了不属于当前 Bundle 的 Evidence")
    evaluation_id = (
        "evaluation-"
        + hashlib.sha256(f"{request.stepId}:{request.requestHash}".encode()).hexdigest()[:32]
    )
    rubric_version = resolved.rubric_version
    if rubric_version is None:
        raise ValueError("Reviewer rubricVersion 未发布")
    return EvidenceEvaluation.model_validate(
        {
            "evaluationId": evaluation_id,
            "runId": request.runId,
            "stepId": request.stepId,
            "evidenceBundleId": request.evidenceBundle.id,
            "artifactId": request.artifactId,
            "artifactRevision": request.artifactRevision,
            "evaluatorProfile": request.modelProfile.model_dump(mode="json"),
            "resolvedModel": resolved.resolved_model.model_dump(mode="json"),
            "rubricVersion": rubric_version,
            "executionStatus": "completed",
            "contentVerdict": verdict,
            "findings": findings,
        }
    )


def _failure(
    request: ExecutionStepRequest,
    resolved_model: ResolvedModelRef,
    *,
    usage: StepUsage,
    category: FailureCategory,
    code: str,
    outcome_unknown: bool,
    failed_at: datetime,
    cancel_request_id: str | None = None,
) -> ExecutionStepFailure:
    retryable = False
    hash_payload: dict[str, object] = {
        "errorCategory": category,
        "errorCode": code,
        "outcomeUnknown": outcome_unknown,
        "retryable": retryable,
        "resolvedModel": resolved_model.model_dump(mode="json", exclude_none=True),
        "usage": usage.model_dump(mode="json", exclude_none=True),
    }
    if cancel_request_id is not None:
        hash_payload["cancelRequestId"] = cancel_request_id
    return ExecutionStepFailure(
        protocolVersion="2.0",
        jobId=request.jobId,
        runId=request.runId,
        novelId=request.novelId,
        stepId=request.stepId,
        fencingToken=request.fencingToken,
        requestHash=request.requestHash,
        inputHash=request.inputHash,
        resolvedModel=resolved_model,
        errorCategory=category,
        errorCode=code,
        retryable=retryable,
        outcomeUnknown=outcome_unknown,
        cancelRequestId=cancel_request_id,
        resultHash=canonical_execution_sha256(hash_payload),
        usage=usage,
        failedAt=failed_at,
    )
