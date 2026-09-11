"""无状态、有界且每个 Step 至多一次逻辑模型调用的 V2 执行器。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Literal, Protocol

import jsonschema_rs
from inkforge_contracts import (
    AgentUpdatesEvidenceRequestOutput,
    AgentUpdatesInput,
    AgentUpdatesOutput,
    AgentUpdatesResult,
    materialize_agent_updates_evidence_request,
    materialize_agent_updates_output,
)
from inkforge_contracts.execution import (
    ChapterDraftInput,
    ChapterDraftOutput,
    ChapterDraftResult,
    ChapterPlanInput,
    ChapterPlanOutput,
    ChapterPlanResult,
    ChapterReviewInput,
    ChapterReviewOutput,
    ChatAnswerInput,
    ChatAnswerOutput,
    EvidenceEvaluation,
    EvidenceExpansionRequest,
    ExecutionStepFailure,
    ExecutionStepRequest,
    ExecutionStepResult,
    IntentContext,
    IntentContextV2,
    IntentResolutionInput,
    IntentResolutionOutput,
    OutlineSelectionInput,
    OutlineSelectionOutput,
    OutlineSelectionResult,
    ProposedCommand,
    ResolvedModelRef,
    StepUsage,
    calculate_resolved_model_fingerprint,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
    materialize_chapter_draft_output,
    materialize_chapter_plan_output,
    materialize_outline_selection_output,
)
from inkforge_contracts.rag_execution import RagEmbeddingBatchOutput, RagEmbeddingStepInput
from inkforge_contracts.short_medium_execution import materialize_short_medium_output
from inkforge_contracts.style_execution import StylePortraitSectionOutput, StylePortraitStepInput
from pydantic import JsonValue, ValidationError

from ..providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelProvider,
    ModelStructuredOutputRequest,
    ModelStructuredOutputRoute,
    ModelTool,
    ModelTurnRequest,
    ModelTurnResult,
    ProviderProtocolError,
    ProviderTransportError,
)
from ..providers.embeddings import EmbeddingExecutionPort, EmbeddingRequest, EmbeddingResult
from ..providers.video_responses import (
    ResponsesExecutionPort,
    VideoResponsesRequest,
    VideoResponsesResult,
)
from ..runtime.portrait_prompts import PORTRAIT_SECTION_INSTRUCTIONS
from .portrait import portrait_context
from .quality import (
    QUALITY_CORRECTION_REQUIRED,
    QUALITY_TOOL,
    quality_response,
    validate_quality_request,
)
from .rag import rag_context
from .registry import (
    ExecutionRegistry,
    ExecutionRegistryError,
    ExecutionRegistryReferenceError,
    OutputSchemaDefinition,
    ProfileDefinition,
    PromptProfileDefinition,
    StepBudgetDefinition,
)
from .short_medium import SHORT_MEDIUM_HANDLERS, validate_short_medium_request
from .video import (
    VIDEO_PROTOCOL_CORRECTION_REQUIRED,
    VideoStageOutputError,
    build_video_request,
    materialize_video_output,
    video_context,
)

_LOGGER = logging.getLogger(__name__)
_STRUCTURED_DIAGNOSTIC_KEYWORDS = frozenset({
    "additionalItems", "additionalProperties", "allOf", "anyOf", "const", "contains", "content",
    "dependentRequired", "dependentSchemas", "enum", "exclusiveMaximum", "exclusiveMinimum",
    "falseSchema", "format", "items", "json", "maxContains", "maxItems", "maxLength",
    "maxProperties", "maximum", "minContains", "minItems", "minLength", "minProperties",
    "minimum", "multipleOf", "not", "oneOf", "pattern", "patternProperties", "prefixItems",
    "propertyNames", "required", "toolCalls", "type", "unevaluatedItems", "unevaluatedProperties",
    "uniqueItems", "unknown",
    "json_control_character", "json_syntax", "json_duplicate_key", "json_constant",
})

ExecutionPurpose = Literal["generation", "review", "resolve_intent", "protocol_correction"]
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
_SUPPORTED_OPERATION_HANDLERS = frozenset(
    {
        *(("short_medium", operation) for operation in SHORT_MEDIUM_HANDLERS),
        ("quality", "consistency"),
        ("style", "portrait"),
        ("rag", "embedding"),
        ("long_serial", "answer_question"),
        ("long_serial", "create_lore"),
        ("long_serial", "create_outline"),
        ("long_serial", "manage_foreshadowing"),
        ("long_serial", "plan_chapter"),
        ("long_serial", "revise_lore"),
        ("long_serial", "revise_outline"),
        ("long_serial", "write_chapter"),
        ("long_serial", "rewrite_chapter_selection"),
        ("long_serial", "rewrite_scene"),
        ("long_serial", "rewrite_outline_selection"),
        ("long_serial", "review_chapter"),
    }
)
_AGENT_UPDATES_OPERATIONS = frozenset(
    {
        "create_lore",
        "revise_lore",
        "create_outline",
        "revise_outline",
        "manage_foreshadowing",
    }
)
_AGENT_UPDATES_GENERATOR_PROFILES = {
    "create_lore": "lore.generator.v3",
    "revise_lore": "lore.reviser.v3",
    "create_outline": "plot.outline_generator.v3",
    "revise_outline": "plot.outline_reviser.v3",
    "manage_foreshadowing": "plot.foreshadowing.v3",
}
_AGENT_UPDATES_RETAINED_GENERATOR_PROFILES = {
    "create_lore": "lore.generator.v2",
    "revise_lore": "lore.reviser.v2",
    "create_outline": "plot.outline_generator.v2",
    "revise_outline": "plot.outline_reviser.v2",
    "manage_foreshadowing": "plot.foreshadowing.v2",
}
_AGENT_UPDATES_REVIEWER_PROFILES = {
    "create_lore": "reviewer.agent_updates_consistency.v1",
    "revise_lore": "reviewer.agent_updates_consistency.v1",
    "create_outline": "reviewer.agent_updates_editorial.v1",
    "revise_outline": "reviewer.agent_updates_editorial.v1",
    "manage_foreshadowing": "reviewer.agent_updates_consistency.v1",
}
_AGENT_UPDATES_EVIDENCE_POLICIES = {
    "create_lore": "evidence.long_serial.lore_create.v1",
    "revise_lore": "evidence.long_serial.lore_revision.v1",
    "create_outline": "evidence.long_serial.outline_create.v1",
    "revise_outline": "evidence.long_serial.outline_revision.v1",
    "manage_foreshadowing": "evidence.long_serial.foreshadowing.v1",
}
_AGENT_UPDATES_OUTPUT_SCHEMA = "output.agent_updates_step.v1"
_AGENT_UPDATES_RETAINED_OUTPUT_SCHEMA = "output.agent_updates.v2"
_AGENT_UPDATES_REVIEW_OUTPUT_SCHEMA = "output.chapter_review_report.v1"
_AGENT_UPDATES_REVIEW_EVIDENCE_POLICY = "evidence.review.same_bundle_artifact_revision.v1"
_AGENT_UPDATES_RUBRIC = "rubric.agent_updates.review.v1"
_AGENT_UPDATES_SINGLETON_RESOURCE_TYPES = frozenset(
    {"outline_content", "world_setting", "story_background"}
)
_AGENT_UPDATES_INDEX_RESOURCE_TYPES = frozenset(
    {
        "character",
        "location",
        "item",
        "faction",
        "glossary",
        "character_experience",
        "outline_node",
        "foreshadowing",
        "reference",
        "chapter_reference",
    }
)
_INTENT_OPERATIONS = frozenset(
    {"answer_question", "plan_chapter", "write_chapter", "rewrite_scene", "review_chapter"}
)
_INTENT_V3_SCOPES = {
    **dict.fromkeys(_INTENT_OPERATIONS, "chapter"),
    "create_lore": "novel",
    "revise_lore": "novel",
    "create_outline": "novel",
    "revise_outline": "novel",
    "manage_foreshadowing": "chapter",
}
_INTENT_RESOLVER_PROFILE_TUPLES = {
    "system.intent_resolver.v1": (
        1,
        "prompt.system.intent_resolver.v1",
        1,
        "4ebf30f06de85e21db42275f10e88a9ce309ee037dfebfd0fc921bfc77796f63",
        "deployment.system.intent_resolver.v1",
        1,
    ),
    "system.intent_resolver.v2": (
        2,
        "prompt.system.intent_resolver.v2",
        2,
        "5f1b980a61c8c66f9e43b06824816cfbdff723eada0784b2e2f5d7c6796fb5bd",
        "deployment.system.intent_resolver.v2",
        2,
    ),
    "system.intent_resolver.v3": (
        3,
        "prompt.system.intent_resolver.v3",
        3,
        "a0f495e7f011eb8f8f0741a3b4e643bfb4d821a7cf62f29e422ac038ff9217e4",
        "deployment.system.intent_resolver.v3",
        3,
    ),
}
_CURRENT_INTENT_RESOLVER_PROFILE = "system.intent_resolver.v3"
_INTENT_OUTPUT_TUPLE = (
    "output.proposed_command.v1",
    1,
    "d01c3444cfd4da13d9df6fe5dee58dfe5a75c413ad89ac28a766d18f6e8bde25",
)
_INTENT_BUDGET_TUPLE = (
    "step_budget.system.resolve_intent.v1",
    1,
    1,
    8000,
    8000,
    1000,
    0,
    1000,
    50_000,
    30,
    2,
    0,
)


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
    result: ModelTurnResult | EmbeddingResult | VideoResponsesResult | None
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
        embedding: EmbeddingExecutionPort | None = None,
        responses: ResponsesExecutionPort | None = None,
    ) -> None:
        if max_output_tokens < 1:
            raise ValueError("V2 execution 模型输出能力必须为正整数")
        if retry_base_seconds < 0:
            raise ValueError("V2 execution 重试退避不能为负数")
        self._model = model
        self._embedding = embedding
        self._responses = responses
        self._max_output_tokens = max_output_tokens
        self._retry_base_seconds = retry_base_seconds

    def matches_resolved_model(
        self,
        resolved: ResolvedModelRef,
        profile: ProfileDefinition,
    ) -> bool:
        """验证当前 Provider 能精确执行 journal 冻结的部署身份。"""

        if resolved.structuredOutputRoute == "embeddings_v1":
            try:
                return self._embedding_resolved_model(profile) == resolved
            except ExecutionCapabilityError:
                return False
        if profile.key.startswith("video."):
            try:
                return self._responses_resolved_model(profile) == resolved
            except ExecutionCapabilityError:
                return False
        if not self._model.supports_structured_output(resolved.structuredOutputRoute):
            return False
        try:
            endpoint, capability = self._execution_identity(resolved.structuredOutputRoute)
            current = _resolved_model(
                profile,
                provider=self._model.provider_name,
                model=self._model.model_name,
                transport_profile=self._model.transport_profile,
                endpoint_profile=endpoint,
                structured_output_route=resolved.structuredOutputRoute,
                capability_version=capability,
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
        if request.workflow == "video":
            return self._resolve_video(request, registry)
        if request.workflow == "rag":
            return self._resolve_embedding(request, registry)
        if request.purpose == "resolve_intent":
            return self._resolve_intent(request, registry)
        if request.workflow == "quality":
            return self._resolve_quality(request, registry)
        operation_key = (request.workflow, request.operation)
        if operation_key not in _SUPPORTED_OPERATION_HANDLERS:
            raise ExecutionCapabilityError("当前执行器尚未实现该 Operation handler")
        if request.dispatchMode != "initial":
            return self._resolve_retained_request(request, registry)
        try:
            if request.operation is None:
                raise ExecutionCapabilityError("业务 Step 必须绑定 operation")
            operation = registry.resolve(request.workflow, request.operation)
        except ExecutionRegistryError as exc:
            raise ExecutionCapabilityError("当前 Operation 未被 Catalog 精确授权") from exc

        rubric_version: str | None = None
        if request.purpose == "generation":
            purpose: ExecutionPurpose = "generation"
            profile = operation.generator_profile
            output_schema = operation.output_schema
            budget = operation.generator_step_budget
            if profile.purpose != "generation" or output_schema.purpose != "generation":
                raise ExecutionCapabilityError("generation Step 的 Profile/Output 用途不一致")
            if request.lane != operation.operation.lane:
                raise ExecutionCapabilityError("generation Step 的 lane 与 Catalog 不一致")
            if request.evidenceBundle.policyVersion != operation.operation.evidence_policy:
                raise ExecutionCapabilityError(
                    "generation Step 的 Evidence Policy 与 Catalog 不一致"
                )
        elif request.purpose == "review":
            purpose = "review"
            reviewer_profile = next(
                (
                    candidate
                    for candidate in operation.reviewer_profiles
                    if candidate.key == request.modelProfile.profile
                ),
                None,
            )
            if reviewer_profile is None:
                raise ExecutionCapabilityError("当前 Operation 未授权该 Reviewer Profile")
            profile = reviewer_profile
            reviewer_schema = operation.reviewer_output_schema
            if reviewer_schema is None:
                raise ExecutionCapabilityError("当前 Operation 未配置 Reviewer Output Schema")
            output_schema = reviewer_schema
            budget = operation.reviewer_step_budgets[profile.key]
            if profile.purpose != "review" or output_schema.purpose != "evaluation":
                raise ExecutionCapabilityError("review Step 的 Profile/Output 用途不一致")
            if request.artifactId is None or request.artifactRevision is None:
                raise ExecutionCapabilityError("Reviewer Step 必须绑定 Artifact revision")
            review_policy = operation.operation.review_policy
            if request.lane != review_policy.lane:
                raise ExecutionCapabilityError("review Step 的 lane 与 Catalog 不一致")
            if request.evidenceBundle.policyVersion != review_policy.evidence_policy:
                raise ExecutionCapabilityError("review Step 的 Evidence Policy 与 Catalog 不一致")
            rubric_version = _frozen_rubric_version(request)
            if rubric_version != review_policy.rubric_version:
                raise ExecutionCapabilityError("Reviewer rubricVersion 与 Catalog 不一致")
        else:
            raise ExecutionCapabilityError("当前执行器只支持 generation/review Step")

        _validate_operation_input(request)
        _validate_profile_ref(request, profile)
        _validate_prompt_profile_ref(request, profile.prompt_profile)
        _validate_output_schema_ref(request, output_schema)
        budget = _resolve_initial_step_budget(request, budget, registry)
        _validate_step_budget(request, budget)
        if request.budget.maxCompletionTokens < 1:
            raise ExecutionCapabilityError("模型 Step 必须具有正 completion 预算")
        if request.budget.maxCompletionTokens > self._max_output_tokens:
            raise ExecutionCapabilityError("Step completion 预算超过当前部署模型能力")

        structured_output_route = self._structured_output_route(request)
        endpoint, capability = self._execution_identity(structured_output_route)
        try:
            registry.require_authorized_deployment(
                deployment_profile_key=profile.deployment_profile_key,
                provider=self._model.provider_name,
                model=self._model.model_name,
                transport_profile=self._model.transport_profile,
                endpoint_profile=endpoint,
                structured_output_route=structured_output_route,
                capability_version=capability,
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
            endpoint_profile=endpoint,
            structured_output_route=structured_output_route,
            capability_version=capability,
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

    def _responses_resolved_model(self, profile: ProfileDefinition) -> ResolvedModelRef:
        identity = None if self._responses is None else self._responses.responses_identity
        if identity is None:
            raise ExecutionCapabilityError("独立视频 Responses 运行时未配置")
        return _resolved_model(
            profile,
            provider=identity.provider,
            model=identity.model,
            transport_profile=identity.transport_profile,
            endpoint_profile=identity.endpoint_profile,
            structured_output_route="responses_json_schema_v1",
            capability_version=identity.capability_version,
            supports_request_idempotency=identity.supports_request_idempotency,
        )

    def _resolve_video(
        self, request: ExecutionStepRequest, registry: ExecutionRegistry
    ) -> ResolvedExecutionStep:
        try:
            _, value = video_context(request)
            if request.dispatchMode == "initial":
                if request.operation is None:
                    raise ValueError("视频必须有精确 operation")
                operation = registry.resolve("video", request.operation).operation
                stage = next(
                    stage for stage in operation.stage_steps if stage.stage_key == value.stageKey
                )
                profile = registry.profiles[stage.model_profile_key]
                schema = registry.output_schemas[stage.output_schema_key]
                budget = registry.step_budgets[stage.step_budget_key]
            else:
                profile = registry.profiles[f"video.{value.stageKey}.v2"]
                schema = registry.output_schemas[f"output.video_{value.stageKey}_stage.v2"]
                budget = registry.step_budgets[f"step_budget.video.{value.stageKey}.v2"]
            if (
                profile.purpose != "generation"
                or schema.purpose != "generation"
                or profile.reasoning_mode != "disabled"
            ):
                raise ValueError("视频阶段必须使用关闭思考的 generation 资产")
            _validate_profile_ref(request, profile)
            _validate_prompt_profile_ref(request, profile.prompt_profile)
            _validate_output_schema_ref(request, schema)
            _validate_step_budget(request, budget)
            if request.budget.maxCompletionTokens > self._max_output_tokens:
                raise ValueError("视频 Step 输出预算超过部署模型能力")
            resolved = self._responses_resolved_model(profile)
            registry.require_authorized_deployment(
                deployment_profile_key=profile.deployment_profile_key,
                provider=resolved.provider,
                model=resolved.model,
                transport_profile=resolved.transportProfile,
                endpoint_profile=resolved.endpointProfile,
                structured_output_route=resolved.structuredOutputRoute,
                capability_version=resolved.capabilityVersion,
                reasoning_mode=resolved.reasoningMode,
                supports_request_idempotency=resolved.supportsRequestIdempotency,
            )
        except (ValueError, KeyError, StopIteration, ExecutionRegistryError) as exc:
            raise ExecutionCapabilityError(
                "视频 Step 未被精确冻结阶段或 Responses 部署授权"
            ) from exc
        return ResolvedExecutionStep(
            "generation",
            profile,
            profile.prompt_profile,
            schema,
            budget,
            None,
            "responses_json_schema_v1",
            resolved,
        )

    def _embedding_resolved_model(self, profile: ProfileDefinition) -> ResolvedModelRef:
        identity = None if self._embedding is None else self._embedding.embedding_identity
        if identity is None:
            raise ExecutionCapabilityError("独立索引供应商未配置")
        return _resolved_model(
            profile,
            provider=identity.provider,
            model=identity.model,
            transport_profile=identity.transport_profile,
            endpoint_profile=identity.endpoint_profile,
            structured_output_route="embeddings_v1",
            capability_version=identity.capability_version,
            supports_request_idempotency=False,
        )

    def _resolve_embedding(
        self, request: ExecutionStepRequest, registry: ExecutionRegistry
    ) -> ResolvedExecutionStep:
        try:
            rag_context(request)
            if request.dispatchMode == "initial":
                operation = registry.resolve("rag", "embedding")
                profile, schema, budget = (
                    operation.generator_profile,
                    operation.output_schema,
                    operation.generator_step_budget,
                )
            else:
                profile = registry.profiles["rag.embedding.v2"]
                schema = registry.output_schemas["output.embedding_batch.v2"]
                budget = registry.step_budgets["step_budget.rag.embedding.generator.v2"]
            if (
                profile.purpose != "embedding"
                or schema.purpose != "embedding"
                or profile.reasoning_mode != "disabled"
            ):
                raise ValueError("索引执行必须绑定 embedding 专用逻辑用途")
            _validate_profile_ref(request, profile)
            _validate_prompt_profile_ref(request, profile.prompt_profile)
            _validate_output_schema_ref(request, schema)
            _validate_step_budget(request, budget)
            resolved = self._embedding_resolved_model(profile)
            registry.require_authorized_deployment(
                deployment_profile_key=resolved.deploymentProfileKey,
                provider=resolved.provider,
                model=resolved.model,
                transport_profile=resolved.transportProfile,
                endpoint_profile=resolved.endpointProfile,
                structured_output_route=resolved.structuredOutputRoute,
                capability_version=resolved.capabilityVersion,
                reasoning_mode=resolved.reasoningMode,
                supports_request_idempotency=False,
            )
        except (ValueError, KeyError, ExecutionRegistryError) as exc:
            raise ExecutionCapabilityError("索引 Step 未被精确冻结契约或配置授权") from exc
        return ResolvedExecutionStep(
            "generation",
            profile,
            profile.prompt_profile,
            schema,
            budget,
            None,
            "embeddings_v1",
            resolved,
        )

    def _resolve_quality(
        self, request: ExecutionStepRequest, registry: ExecutionRegistry
    ) -> ResolvedExecutionStep:
        try:
            validate_quality_request(request)
            if request.dispatchMode == "initial":
                operation = registry.resolve("quality", "consistency")
                if request.purpose == "protocol_correction":
                    system = registry.resolve_system_purpose("protocol_correction", "quality")
                    if system.definition.parent_operations != ("quality.consistency",):
                        raise ValueError("质量纠正系统用途父操作必须精确限定")
                    if (
                        system.definition.evidence_policy != request.evidenceBundle.policyVersion
                        or system.definition.lane != request.lane
                    ):
                        raise ValueError("质量纠正 Evidence 或 lane 不一致")
                    profile, schema, budget = (
                        system.model_profile,
                        system.output_schema,
                        system.step_budget,
                    )
                else:
                    profile, schema, budget = (
                        operation.generator_profile,
                        operation.output_schema,
                        operation.generator_step_budget,
                    )
                _validate_profile_ref(request, profile)
                _validate_output_schema_ref(request, schema)
                _validate_step_budget(request, budget)
        except (ValueError, ExecutionRegistryError) as exc:
            raise ExecutionCapabilityError("质量 Step 未被精确冻结契约授权") from exc
        return self._resolve_retained_request(request, registry)

    def _resolve_intent(
        self, request: ExecutionStepRequest, registry: ExecutionRegistry
    ) -> ResolvedExecutionStep:
        if (
            request.operation is not None
            or request.workflow != "long_serial"
            or request.artifactId is not None
            or request.artifactRevision is not None
        ):
            raise ExecutionCapabilityError("意图解析不允许业务 Operation 或 Artifact 绑定")
        if (
            request.lane != "interactive"
            or request.evidenceBundle.policyVersion != "evidence.system.intent.v1"
            or request.modelProfile.reasoningMode != "disabled"
        ):
            raise ExecutionCapabilityError("意图解析 lane、Evidence 或模型策略不一致")
        context = _validate_intent_input(request)
        if request.dispatchMode == "initial":
            try:
                contract = registry.resolve_system_purpose("resolve_intent", request.workflow)
            except ExecutionRegistryError as exc:
                raise ExecutionCapabilityError("意图解析系统用途未被精确授权") from exc
            if (
                contract.definition.parent_operations
                or request.lane != contract.definition.lane
                or request.evidenceBundle.policyVersion != contract.definition.evidence_policy
            ):
                raise ExecutionCapabilityError("意图解析当前系统用途绑定不一致")
            _validate_intent_resolver_tuple(
                registry,
                contract.model_profile,
                contract.output_schema,
                contract.step_budget,
                current=True,
            )
            _validate_output_schema_ref(request, contract.output_schema)
            _validate_step_budget(request, contract.step_budget)
            for available in context.availableOperations:
                try:
                    registry.resolve(request.workflow, available.operation)
                except ExecutionRegistryError as exc:
                    raise ExecutionCapabilityError("意图上下文包含当前未启用的 Operation") from exc
        # 共用冻结引用、Prompt、部署能力与预算的完整复验；不改写 journal 的初始或恢复语义。
        return self._resolve_retained_request(request, registry)

    def _resolve_retained_request(
        self,
        request: ExecutionStepRequest,
        registry: ExecutionRegistry,
    ) -> ResolvedExecutionStep:
        """复验已冻结依赖；新意图请求只有先通过独立系统用途授权才能复用此路径。"""

        profile = registry.profiles.get(request.modelProfile.profile)
        if profile is None:
            raise ExecutionCapabilityError("Execution Model Profile 未保留在 Registry")
        output_schema = registry.output_schemas.get(request.outputSchema.name)
        if output_schema is None:
            raise ExecutionCapabilityError("Execution Output Schema 未保留在 Registry")
        matching_budgets = tuple(
            budget
            for budget in registry.step_budgets.values()
            if budget.supported
            and (
                request.workflow != "style"
                or budget.key == "step_budget.style.portrait.generator.v2"
            )
            and _step_budget_matches(request, budget)
            and (
                request.purpose != "resolve_intent"
                or budget.key == "step_budget.system.resolve_intent.v1"
            )
            and (
                request.workflow != "quality"
                or budget.key
                == (
                    "step_budget.system.quality_protocol_correction.v2"
                    if request.purpose == "protocol_correction"
                    else "step_budget.quality.consistency.generator.v2"
                )
            )
        )
        if not matching_budgets:
            raise ExecutionCapabilityError("Execution Step Budget 未保留在 Registry")
        budget = sorted(matching_budgets, key=lambda value: value.key)[0]
        if request.purpose == "generation":
            purpose: ExecutionPurpose = "generation"
            if profile.purpose != "generation" or output_schema.purpose != "generation":
                raise ExecutionCapabilityError("generation Step 的 Profile/Output 用途不一致")
            rubric_version = None
        elif request.purpose == "review":
            purpose = "review"
            if profile.purpose != "review" or output_schema.purpose != "evaluation":
                raise ExecutionCapabilityError("review Step 的 Profile/Output 用途不一致")
            if request.artifactId is None or request.artifactRevision is None:
                raise ExecutionCapabilityError("Reviewer Step 必须绑定 Artifact revision")
            rubric_version = _frozen_rubric_version(request)
        elif request.purpose == "resolve_intent":
            purpose = "resolve_intent"
            if profile.purpose != "generation" or output_schema.purpose != "generation":
                raise ExecutionCapabilityError("意图解析 Profile/Output 用途不一致")
            _validate_intent_resolver_tuple(
                registry,
                profile,
                output_schema,
                budget,
                current=False,
            )
            rubric_version = None
        elif request.purpose == "protocol_correction" and request.workflow == "quality":
            purpose = "protocol_correction"
            if profile.purpose != "generation" or output_schema.purpose != "generation":
                raise ExecutionCapabilityError("质量纠正 Profile/Output 用途不一致")
            rubric_version = None
        else:
            raise ExecutionCapabilityError("当前执行器只支持 generation/review Step")
        if request.purpose == "resolve_intent":
            _validate_intent_input(request)
        else:
            _validate_operation_input(request)
        _validate_profile_ref(request, profile)
        _validate_prompt_profile_ref(request, profile.prompt_profile)
        _validate_output_schema_ref(request, output_schema)
        _validate_step_budget(request, budget)
        if request.budget.maxCompletionTokens < 1:
            raise ExecutionCapabilityError("模型 Step 必须具有正 completion 预算")
        if request.budget.maxCompletionTokens > self._max_output_tokens:
            raise ExecutionCapabilityError("Step completion 预算超过当前部署模型能力")
        structured_output_route = self._structured_output_route(request)
        endpoint, capability = self._execution_identity(structured_output_route)
        try:
            registry.require_authorized_deployment(
                deployment_profile_key=profile.deployment_profile_key,
                provider=self._model.provider_name,
                model=self._model.model_name,
                transport_profile=self._model.transport_profile,
                endpoint_profile=endpoint,
                structured_output_route=structured_output_route,
                capability_version=capability,
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
            endpoint_profile=endpoint,
            structured_output_route=structured_output_route,
            capability_version=capability,
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
    ) -> ModelTurnRequest | EmbeddingRequest | VideoResponsesRequest:
        if request.workflow == "video":
            turn = build_video_request(request, resolved.prompt_profile.system_prompt)
            estimated = sum(len(message.content) for message in turn.messages)
            if turn.structuredOutput is not None:
                estimated += len(turn.structuredOutput.model_dump_json())
            if estimated > request.budget.maxInputTokens:
                raise ExecutionCapabilityError("完整视频消息与动态 Schema 超过 Step maxInputTokens")
            return VideoResponsesRequest.from_turn(turn)
        route = resolved.structured_output_route
        if route == "embeddings_v1":
            embedding_context = rag_context(request)
            texts = embedding_context.batch(
                RagEmbeddingStepInput.model_validate(request.input).batchIndex
            )
            if sum(len(text) for text in texts) > request.budget.maxInputTokens:
                raise ExecutionCapabilityError("索引本批完整来源超过 Step maxInputTokens")
            return EmbeddingRequest(texts=texts)
        system_prompt = resolved.prompt_profile.system_prompt
        if route == "plain_text_v1":
            context = portrait_context(request)
            section = StylePortraitStepInput.model_validate(request.input).section
            instruction = PORTRAIT_SECTION_INSTRUCTIONS[section]
            model_request = ModelTurnRequest(
                messages=[
                    ModelMessage(role="system", content=system_prompt),
                    ModelMessage(
                        role="user",
                        content=f"任务：{instruction}\n\n完整参考资料：\n{context.source_text}",
                    ),
                ],
                tools=[],
                maxOutputTokens=request.budget.maxCompletionTokens,
                policy=ModelExecutionPolicy(
                    policyId=request.modelProfile.profile, thinkingMode="disabled"
                ),
                thinkingMode="disabled",
                parallelToolCalls=False,
                requestIdempotencyKey=request.idempotencyKey,
            )
            if (
                sum(len(message.content) for message in model_request.messages)
                > request.budget.maxInputTokens
            ):
                raise ExecutionCapabilityError("完整画像来源超过 Step maxInputTokens")
            return model_request
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
        structured = (
            None
            if route == "quality_strict_tool_v1"
            else ModelStructuredOutputRequest(
                route=route,
                name=_structured_output_name(request.outputSchema.name),
                jsonSchema=request.outputSchema.jsonSchema,
            )
        )
        policy = ModelExecutionPolicy(
            policyId=request.modelProfile.profile,
            requiredToolName=QUALITY_TOOL if route == "quality_strict_tool_v1" else None,
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
            tools=(
                [
                    ModelTool(
                        name=QUALITY_TOOL,
                        description="提交完整一致性终检报告",
                        parameters=request.outputSchema.jsonSchema,
                        strict=True,
                    )
                ]
                if route == "quality_strict_tool_v1"
                else []
            ),
            requiredToolName=QUALITY_TOOL if route == "quality_strict_tool_v1" else None,
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
        estimated_input += (
            len(structured.model_dump_json())
            if structured is not None
            else sum(len(tool.model_dump_json()) for tool in model_request.tools)
        )
        if estimated_input > request.budget.maxInputTokens:
            raise ExecutionCapabilityError("完整模型输入超过 Step maxInputTokens")
        return model_request

    async def call_provider(
        self,
        request: ExecutionStepRequest,
        model_request: ModelTurnRequest | EmbeddingRequest | VideoResponsesRequest,
        *,
        begin_attempt: BeginAttempt,
        cancel_event: asyncio.Event,
    ) -> ProviderCallOutcome:
        if cancel_event.is_set():
            return ProviderCallOutcome(
                result=None,
                provider_attempts=0,
                elapsed_millis=0,
                failure_category="cancelled",
                failure_code="RUN_CANCELLED",
            )
        provider_started: float | None = None
        attempts = 0
        supports_idempotency = (
            False
            if isinstance(model_request, (EmbeddingRequest, VideoResponsesRequest))
            else self._model.supports_request_idempotency
        )

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
            return min(elapsed_millis(), request.budget.maxWallClockSeconds * 1_000)

        def remaining_seconds() -> float:
            if provider_started is None:
                return float(request.budget.maxWallClockSeconds)
            remaining = request.budget.maxWallClockSeconds - (monotonic() - provider_started)
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
                            embedding=self._embedding,
                            responses=self._responses,
                            before_provider=record_attempt,
                            cancel_event=cancel_event,
                            lane=request.lane,
                            reviewer=request.purpose == "review",
                            provider_timeout_seconds=float(request.budget.maxWallClockSeconds),
                        )
                    else:
                        async with asyncio.timeout(remaining_seconds()):
                            attempts, result = await _call_with_cancel(
                                self._model,
                                model_request,
                                embedding=self._embedding,
                                responses=self._responses,
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
                        supports_request_idempotency=supports_idempotency,
                    )
                    if (
                        retry_safe
                        and attempts <= request.budget.maxProviderRetries
                        and not isinstance(model_request, VideoResponsesRequest)
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
                    if _provider_outcome_unknown(
                        exc, supports_request_idempotency=supports_idempotency
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
                        supports_idempotency
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
                quality_tool_response=request.workflow == "quality",
            )
            error_code = (
                "STEP_BUDGET_EXCEEDED" if _step_budget_exceeded(request, usage) else "RUN_CANCELLED"
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
            if not outcome.outcome_unknown and _step_budget_exceeded(request, usage):
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
            quality_tool_response=request.workflow == "quality",
        )
        if isinstance(result, EmbeddingResult):
            return self._embedding_terminal(request, resolved, result, usage, now)
        if isinstance(result, VideoResponsesResult):
            return self._video_terminal(request, resolved, result, usage, now)
        if request.workflow == "quality":
            failure = _validate_quality_provider_result(request, result, usage)
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
            output, _ = quality_response(result)
            result = result.model_copy(
                update={
                    "content": "",
                    "toolCalls": [],
                    "structuredOutput": output,
                    "finishReason": "stop",
                }
            )
        if request.workflow == "style":
            failure = _validate_portrait_provider_result(result)
            if failure is not None:
                if _step_budget_exceeded(request, usage):
                    failure = ("validation", "STEP_BUDGET_EXCEEDED")
                return _failure(
                    request,
                    resolved.resolved_model,
                    usage=usage,
                    category=failure[0],
                    code=failure[1],
                    outcome_unknown=False,
                    failed_at=now,
                )
            result = result.model_copy(update={"structuredOutput": {"content": result.content}})
        failure = _validate_provider_result(request, result, usage)
        if failure is not None:
            if failure[1] == "MODEL_STRUCTURED_OUTPUT_INVALID":
                diagnostic = result.structuredOutputDiagnostic
                keyword = diagnostic.keyword if diagnostic is not None else "content"
                _LOGGER.warning(
                    "V2 结构化输出未通过本地验收 "
                    "run_id=%s step_id=%s output_schema=%s code=%s keyword=%s",
                    request.runId,
                    request.stepId,
                    request.outputSchema.name,
                    diagnostic.code if diagnostic is not None else "missing_output",
                    keyword if keyword in _STRUCTURED_DIAGNOSTIC_KEYWORDS else "unknown",
                )
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
        value: (
            dict[str, JsonValue] | EvidenceEvaluation | EvidenceExpansionRequest | ProposedCommand
        )
        if (
            resolved.purpose == "generation"
            and _uses_agent_updates_evidence_request_schema(request)
            and "evidenceRequest" in structured_output
        ):
            value = materialize_agent_updates_evidence_request(
                structured_output,
                step_id=request.stepId,
                request_hash=request.requestHash,
                bundle_id=request.evidenceBundle.id,
                bundle_version=request.evidenceBundle.version,
                max_input_tokens=request.budget.maxInputTokens,
            )
            result_kind = "evidence_expansion"
        elif resolved.purpose in {"generation", "protocol_correction"}:
            value = _derive_generation_output(request, structured_output)
            result_kind = "output"
        elif resolved.purpose == "resolve_intent":
            value = _intent_command(request, structured_output)
            result_kind = "proposed_command"
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
            if isinstance(value, (EvidenceEvaluation, EvidenceExpansionRequest, ProposedCommand))
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
        if isinstance(value, ProposedCommand):
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
                resultKind="proposed_command",
                proposedCommand=value,
                resultHash=result_hash,
                usage=usage,
                completedAt=now,
            )
        if isinstance(value, EvidenceExpansionRequest):
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
                resultKind="evidence_expansion",
                evidenceExpansion=value,
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

    def _video_terminal(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep,
        result: VideoResponsesResult,
        usage: StepUsage,
        now: datetime,
    ) -> ExecutionStepResult | ExecutionStepFailure:
        code: str | None = None
        category: FailureCategory = "validation"
        output: dict[str, JsonValue] = {}
        reliable = all(
            value is not None
            for value in (
                usage.inputTokens,
                usage.cachedTokens,
                usage.promptCacheMissTokens,
                usage.completionTokens,
                usage.reasoningTokens,
                usage.visibleOutputTokens,
            )
        )
        _, value = video_context(request)
        correction_available = (
            reliable
            and not value.correction
            and value.cycle == 0
            and value.stageKey in {"dramatic_structure", "shot_design", "shot_prompt"}
        )
        if _step_budget_exceeded(request, usage):
            code = "STEP_BUDGET_EXCEEDED"
        elif result.finishReason in {"length", "content_filter"} and correction_available:
            # 只保留原视频首轮的明确结束重做；Core 结算后另建 Step，绝不续接半截正文。
            category, code = "protocol", VIDEO_PROTOCOL_CORRECTION_REQUIRED
        elif result.finishReason != "stop":
            category = "provider_terminal"
            code = {
                "length": "MODEL_OUTPUT_TRUNCATED",
                "content_filter": "MODEL_OUTPUT_FILTERED",
                "insufficient_system_resource": "MODEL_INSUFFICIENT_SYSTEM_RESOURCE",
            }.get(result.finishReason, "MODEL_FINISH_REASON_INVALID")
        elif result.diagnostic is not None or result.structuredOutput is None:
            category = "protocol"
            code = (
                VIDEO_PROTOCOL_CORRECTION_REQUIRED
                if correction_available
                else "VIDEO_ADAPTATION_OUTPUT_INVALID"
            )
        else:
            try:
                output = materialize_video_output(request, result.structuredOutput)
                if output.get("outcome") == "needs_correction" and not reliable:
                    category, code = "protocol", "MODEL_USAGE_INVALID"
                else:
                    jsonschema_rs.validator_for(request.outputSchema.jsonSchema).validate(output)
            except VideoStageOutputError as exc:
                code = exc.code
            except (ValueError, ValidationError, jsonschema_rs.ValidationError):
                code = "VIDEO_ADAPTATION_OUTPUT_INVALID"
        if code is not None:
            return _failure(
                request,
                resolved.resolved_model,
                usage=usage,
                category=category,
                code=code,
                outcome_unknown=False,
                failed_at=now,
            )
        result_hash = canonical_execution_sha256(
            {
                "resultKind": "output",
                "resolvedModel": resolved.resolved_model.model_dump(mode="json", exclude_none=True),
                "usage": usage.model_dump(mode="json", exclude_none=True),
                "value": output,
            }
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
            output=output,
            resultHash=result_hash,
            usage=usage,
            completedAt=now,
        )

    def _embedding_terminal(
        self,
        request: ExecutionStepRequest,
        resolved: ResolvedExecutionStep,
        result: EmbeddingResult,
        usage: StepUsage,
        now: datetime,
    ) -> ExecutionStepResult | ExecutionStepFailure:
        code = (
            "STEP_BUDGET_EXCEEDED"
            if _step_budget_exceeded(request, usage)
            else result.protocol_error
        )
        output: dict[str, JsonValue] = {}
        if code is None:
            try:
                value = RagEmbeddingBatchOutput.model_validate({"embeddings": result.embeddings})
                expected = rag_context(request).batch(
                    RagEmbeddingStepInput.model_validate(request.input).batchIndex
                )
                if len(value.embeddings) != len(expected):
                    raise ValueError("索引向量数量与本批完整分块不一致")
                output = value.model_dump(mode="json")
            except (ValueError, ValidationError):
                code = "EMBEDDING_OUTPUT_INVALID"
        if code is not None:
            return _failure(
                request,
                resolved.resolved_model,
                usage=usage,
                category="validation",
                code=code,
                outcome_unknown=False,
                failed_at=now,
            )
        result_hash = canonical_execution_sha256(
            {
                "resultKind": "output",
                "resolvedModel": resolved.resolved_model.model_dump(mode="json", exclude_none=True),
                "usage": usage.model_dump(mode="json", exclude_none=True),
                "value": output,
            }
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
            output=output,
            resultHash=result_hash,
            usage=usage,
            completedAt=now,
        )

    def _execution_identity(self, route: ModelStructuredOutputRoute) -> tuple[str, str]:
        resolver = getattr(self._model, "execution_identity", None)
        if callable(resolver):
            endpoint, capability = resolver(route)
            return str(endpoint), str(capability)
        return self._model.endpoint_profile, self._model.capability_version

    def _structured_output_route(
        self, request: ExecutionStepRequest | None = None
    ) -> ModelStructuredOutputRoute:
        if request is not None and request.workflow == "quality":
            if self._model.supports_structured_output("quality_strict_tool_v1"):
                return "quality_strict_tool_v1"
            raise ExecutionCapabilityError("当前 Provider 不支持质量 strict 工具路由")
        if request is not None and request.workflow == "style":
            if self._model.supports_structured_output("plain_text_v1"):
                return "plain_text_v1"
            raise ExecutionCapabilityError("当前 Provider 不支持画像纯文本路由")
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

    def execution_identity(self, route: ModelStructuredOutputRoute) -> tuple[str, str]:
        resolver = getattr(self._provider, "execution_identity", None)
        if callable(resolver):
            endpoint, capability = resolver(route)
            return str(endpoint), str(capability)
        return self.endpoint_profile, self.capability_version

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
    def __init__(
        self, result: ModelTurnResult | EmbeddingResult | VideoResponsesResult | None
    ) -> None:
        self.result = result
        super().__init__("provider_cancelled")


async def _call_with_cancel(
    model: ExecutionModelPort,
    request: ModelTurnRequest | EmbeddingRequest | VideoResponsesRequest,
    *,
    embedding: EmbeddingExecutionPort | None = None,
    responses: ResponsesExecutionPort | None = None,
    before_provider: BeginAttempt,
    cancel_event: asyncio.Event,
    lane: Literal["interactive", "creative", "batch_media"],
    reviewer: bool,
    provider_timeout_seconds: float | None,
) -> tuple[int, ModelTurnResult | EmbeddingResult | VideoResponsesResult]:
    async def invoke() -> tuple[int, ModelTurnResult | EmbeddingResult | VideoResponsesResult]:
        if isinstance(request, VideoResponsesRequest):
            if responses is None:
                raise ExecutionCapabilityError("独立视频 Responses 运行时未配置")
            return await responses.run_execution_responses(
                request,
                before_provider=before_provider,
                lane=lane,
                provider_timeout_seconds=provider_timeout_seconds,
            )
        if isinstance(request, EmbeddingRequest):
            if embedding is None:
                raise ExecutionCapabilityError("独立索引运行时未配置")
            return await embedding.run_execution_embedding(
                request,
                before_provider=before_provider,
                lane=lane,
                provider_timeout_seconds=provider_timeout_seconds,
            )
        return await model.run_execution_turn(
            request,
            before_provider=before_provider,
            lane=lane,
            reviewer=reviewer,
            provider_timeout_seconds=provider_timeout_seconds,
        )

    provider_task = asyncio.create_task(invoke())
    cancel_task = asyncio.create_task(cancel_event.wait())
    try:
        done, _ = await asyncio.wait(
            {provider_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_task in done and cancel_event.is_set():
            result: ModelTurnResult | EmbeddingResult | VideoResponsesResult | None = None
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


def _validate_intent_resolver_tuple(
    registry: ExecutionRegistry,
    profile: ProfileDefinition,
    output_schema: OutputSchemaDefinition,
    budget: StepBudgetDefinition,
    *,
    current: bool,
) -> None:
    expected_profile = _INTENT_RESOLVER_PROFILE_TUPLES.get(profile.key)
    deployment = registry.deployment_profiles.get(profile.deployment_profile_key)
    if expected_profile is None or deployment is None:
        raise ExecutionCapabilityError("意图解析冻结资产不是受支持的 v1/v2/v3 组合")
    actual_profile = (
        profile.version,
        profile.prompt_profile.key,
        profile.prompt_profile.version,
        profile.prompt_profile.sha256,
        profile.deployment_profile_key,
        deployment.version,
    )
    actual_output = (output_schema.key, output_schema.version, output_schema.sha256)
    actual_budget = (
        budget.key,
        budget.version,
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
    if (
        actual_profile != expected_profile
        or actual_output != _INTENT_OUTPUT_TUPLE
        or actual_budget != _INTENT_BUDGET_TUPLE
        or (current and profile.key != _CURRENT_INTENT_RESOLVER_PROFILE)
        or not profile.supported
        or profile.reasoning_mode != "disabled"
        or profile.purpose != "generation"
        or not profile.prompt_profile.supported
        or profile.prompt_profile.purpose != "generation"
        or hashlib.sha256(profile.prompt_profile.system_prompt.encode("utf-8")).hexdigest()
        != profile.prompt_profile.sha256
        or not deployment.supported
        or deployment.purpose != "generation"
        or not output_schema.supported
        or output_schema.purpose != "generation"
        or canonical_execution_sha256(output_schema.json_schema_value()) != output_schema.sha256
        or not budget.supported
    ):
        raise ExecutionCapabilityError("意图解析冻结资产不是受支持的 v1/v2/v3 组合")


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


_RETAINED_CHAPTER_WRITING_BUDGET_KEYS = {
    "step_budget.long_serial.write_chapter.generator.v3": (
        "step_budget.long_serial.write_chapter.generator.v2",
        "step_budget.long_serial.write_chapter.generator.v1",
    ),
    "step_budget.long_serial.write_chapter.reviewer_consistency.v3": (
        "step_budget.long_serial.write_chapter.reviewer_consistency.v2",
        "step_budget.long_serial.write_chapter.reviewer_consistency.v1",
    ),
    "step_budget.long_serial.write_chapter.reviewer_editorial.v3": (
        "step_budget.long_serial.write_chapter.reviewer_editorial.v2",
        "step_budget.long_serial.write_chapter.reviewer_editorial.v1",
    ),
}


def _resolve_initial_step_budget(
    request: ExecutionStepRequest,
    current: StepBudgetDefinition,
    registry: ExecutionRegistry,
) -> StepBudgetDefinition:
    """旧 Run 后续新建的复审或返工仍是首次派发，只精确认可已保留的历史预算。"""
    if (
        request.workflow == "long_serial"
        and request.operation == "write_chapter"
        and not _step_budget_matches(request, current)
    ):
        for retained_key in _RETAINED_CHAPTER_WRITING_BUDGET_KEYS.get(current.key, ()):
            retained = registry.step_budgets.get(retained_key)
            if (
                retained is not None
                and retained.supported
                and _step_budget_matches(request, retained)
            ):
                return retained
    return current


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
    if not isinstance(rubric, str) or re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", rubric) is None:
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


def _validate_intent_input(request: ExecutionStepRequest) -> IntentContext | IntentContextV2:
    try:
        IntentResolutionInput.model_validate(request.input)
        if request.novelId is None or len(request.evidenceBundle.items) != 1:
            raise ValueError("意图解析必须绑定小说与唯一上下文")
        item = request.evidenceBundle.items[0]
        if (
            item.resourceType != "intent_context"
            or not item.exists
            or item.contentType != "json"
            or item.range is not None
            or item.contentJson is None
        ):
            raise ValueError("意图 Evidence 必须是完整 JSON 上下文")
        # 新范围只随精确 v3 冻结引用生效，旧首次派发/恢复继续使用原 chapter-only 模型。
        context: IntentContext | IntentContextV2
        if request.modelProfile.profile == "system.intent_resolver.v3":
            context = IntentContextV2.model_validate(item.contentJson)
            allowed_scopes = _INTENT_V3_SCOPES
        else:
            context = IntentContext.model_validate(item.contentJson)
            allowed_scopes = dict.fromkeys(_INTENT_OPERATIONS, "chapter")
        if (
            context.workflow != request.workflow
            or context.novelId != request.novelId
            or context.chapterId != item.resourceId
            or any(
                option.operation not in allowed_scopes
                or option.scopeKind != allowed_scopes[option.operation]
                for option in context.availableOperations
            )
        ):
            raise ValueError("意图上下文身份或允许操作不一致")
        return context
    except (TypeError, ValueError, ValidationError) as exc:
        raise ExecutionCapabilityError("意图解析输入或 Evidence 不符合冻结契约") from exc


def _intent_command(request: ExecutionStepRequest, output: object) -> ProposedCommand:
    proposed = IntentResolutionOutput.model_validate(output)
    context = _validate_intent_input(request)
    if proposed.operation is not None and (
        proposed.workflow != context.workflow
        or proposed.workflow != request.workflow
        or proposed.operation not in {option.operation for option in context.availableOperations}
    ):
        raise ValueError("意图结果选择了未被当前上下文授权的操作")
    return ProposedCommand.model_validate(proposed.model_dump(mode="json", exclude_none=True))


def _validate_operation_input(request: ExecutionStepRequest) -> None:
    if request.workflow == "style":
        try:
            portrait_context(request)
        except (ValueError, ValidationError) as exc:
            raise ExecutionCapabilityError("画像输入与冻结来源不一致") from exc
        return
    if request.workflow == "quality":
        try:
            validate_quality_request(request)
        except (ValueError, ValidationError) as exc:
            raise ExecutionCapabilityError("质量输入与冻结来源不一致") from exc
        return
    if request.workflow == "short_medium":
        try:
            validate_short_medium_request(request)
        except (ValueError, ValidationError) as exc:
            raise ExecutionCapabilityError("中短篇单 Step 冻结来源无效") from exc
        return
    if request.workflow == "long_serial" and request.operation in _AGENT_UPDATES_OPERATIONS:
        _validate_agent_updates_input(request)
        return
    if request.workflow == "long_serial" and request.operation in {
        "write_chapter",
        "rewrite_scene",
    }:
        _validate_chapter_draft_input(request)
        return
    if (request.workflow, request.operation) == ("long_serial", "review_chapter"):
        _validate_chapter_review_input(request)
        return
    if (request.workflow, request.operation) == ("long_serial", "rewrite_outline_selection"):
        _validate_outline_selection_input(request)
        return
    if (request.workflow, request.operation) == ("long_serial", "plan_chapter"):
        _validate_chapter_plan_input(request)
        return
    if (request.workflow, request.operation) != (
        "long_serial",
        "answer_question",
    ):
        return
    expected = (
        "generation",
        "interactive",
        "editor.answer.v1",
        "output.chat_answer.v1",
        "evidence.long_serial.answer.v1",
    )
    actual = (
        request.purpose,
        request.lane,
        request.modelProfile.profile,
        request.outputSchema.name,
        request.evidenceBundle.policyVersion,
    )
    if actual != expected:
        raise ExecutionCapabilityError("长篇问答 Step 与冻结 handler 身份不一致")
    if request.novelId is None:
        raise ExecutionCapabilityError("长篇问答必须绑定 novelId")
    if request.artifactId is not None or request.artifactRevision is not None:
        raise ExecutionCapabilityError("长篇问答不能绑定 ReviewArtifact")
    try:
        ChatAnswerInput.model_validate(request.input)
    except ValidationError as exc:
        raise ExecutionCapabilityError("长篇问答 input 必须只含完整 userInstruction") from exc
    chapter_items = tuple(
        item for item in request.evidenceBundle.items if item.resourceType == "chapter_content"
    )
    if len(chapter_items) != 1:
        raise ExecutionCapabilityError("长篇问答必须冻结唯一目标章节正文 Evidence")
    chapter = chapter_items[0]
    if (
        not chapter.exists
        or chapter.contentType != "text"
        or chapter.contentText is None
        or chapter.range is not None
    ):
        raise ExecutionCapabilityError("长篇问答章节 Evidence 必须是完整 text 快照")


def _validate_agent_updates_input(request: ExecutionStepRequest) -> None:
    operation = request.operation
    if operation not in _AGENT_UPDATES_OPERATIONS or request.novelId is None:
        raise ExecutionCapabilityError("结构化资料 Step 必须绑定已实现 Operation 与 novelId")

    index_items = [
        item for item in request.evidenceBundle.items if item.resourceType == "agent_updates_index"
    ]
    if len(index_items) != 1:
        raise ExecutionCapabilityError("结构化资料 Evidence 必须包含唯一 agent_updates_index")
    index = index_items[0]
    content = index.contentJson
    metadata = index.metadata
    if (
        not index.exists
        or index.contentType != "json"
        or index.range is not None
        or index.resourceId != request.novelId
        or not isinstance(content, dict)
        or not isinstance(content.get("items"), list)
        or metadata.get("targetType") != "novel"
        or metadata.get("targetId") != request.novelId
        or metadata.get("roles") != ["index"]
    ):
        raise ExecutionCapabilityError("结构化资料 agent_updates_index 不完整或小说身份不一致")

    actual = (
        request.purpose,
        request.lane,
        request.modelProfile.profile,
        request.outputSchema.name,
        request.evidenceBundle.policyVersion,
    )
    if request.purpose == "generation":
        current_expected = (
            "generation",
            "creative",
            _AGENT_UPDATES_GENERATOR_PROFILES[operation],
            _AGENT_UPDATES_OUTPUT_SCHEMA,
            _AGENT_UPDATES_EVIDENCE_POLICIES[operation],
        )
        retained_expected = (
            "generation",
            "creative",
            _AGENT_UPDATES_RETAINED_GENERATOR_PROFILES[operation],
            _AGENT_UPDATES_RETAINED_OUTPUT_SCHEMA,
            _AGENT_UPDATES_EVIDENCE_POLICIES[operation],
        )
        allowed = actual == current_expected or (
            request.dispatchMode != "initial" and actual == retained_expected
        )
    elif request.purpose == "review":
        expected = (
            "review",
            "interactive",
            _AGENT_UPDATES_REVIEWER_PROFILES[operation],
            _AGENT_UPDATES_REVIEW_OUTPUT_SCHEMA,
            _AGENT_UPDATES_REVIEW_EVIDENCE_POLICY,
        )
        allowed = actual == expected
    else:
        raise ExecutionCapabilityError("结构化资料 Step 只支持 generation/review")
    if not allowed:
        raise ExecutionCapabilityError("结构化资料 Step 与冻结 handler 身份不一致")

    try:
        if request.purpose == "review":
            if set(request.input) != {"task", "candidate"}:
                raise ValueError("结构化资料复审只接受 task 与完整候选")
            task = request.input["task"]
            candidate = request.input["candidate"]
            if not isinstance(task, dict):
                raise ValueError("结构化资料复审 task 必须是对象")
            allowed_task_keys = {
                "workflow",
                "operation",
                "target",
                "scope",
                "userInstruction",
                "originalUserInstruction",
                "rubricVersion",
            }
            required_task_keys = {
                "workflow",
                "operation",
                "userInstruction",
                "rubricVersion",
            }
            if not required_task_keys.issubset(task) or not set(task).issubset(allowed_task_keys):
                raise ValueError("结构化资料复审 task 字段不符合冻结契约")
            if (
                task["workflow"] != "long_serial"
                or task["operation"] != operation
                or task["rubricVersion"] != _AGENT_UPDATES_RUBRIC
                or ("target" in task and not isinstance(task["target"], dict))
                or ("scope" in task and not isinstance(task["scope"], dict))
            ):
                raise ValueError("结构化资料复审任务身份不一致")
            AgentUpdatesInput.model_validate({"userInstruction": task["userInstruction"]})
            if "originalUserInstruction" in task:
                AgentUpdatesInput.model_validate(
                    {"userInstruction": task["originalUserInstruction"]}
                )
            AgentUpdatesResult.model_validate(candidate)
            return

        generation = AgentUpdatesInput.model_validate(request.input)
        previous = generation.previousCandidate
        if previous is None:
            if request.artifactId is not None or request.artifactRevision is not None:
                raise ValueError("结构化资料初次生成不能绑定上一候选")
        elif (
            previous.artifactId != request.artifactId
            or previous.artifactRevision != request.artifactRevision
        ):
            raise ValueError("结构化资料返工与精确上一候选身份不一致")
    except (TypeError, ValueError, ValidationError) as exc:
        raise ExecutionCapabilityError("结构化资料输入或完整候选不符合冻结契约") from exc


def _uses_agent_updates_evidence_request_schema(request: ExecutionStepRequest) -> bool:
    operation = request.operation
    return (
        request.workflow == "long_serial"
        and request.purpose == "generation"
        and operation in _AGENT_UPDATES_OPERATIONS
        and request.modelProfile.profile == _AGENT_UPDATES_GENERATOR_PROFILES[operation]
        and request.outputSchema.name == _AGENT_UPDATES_OUTPUT_SCHEMA
    )


def _agent_updates_evidence_request(
    request: ExecutionStepRequest,
    value: object,
) -> AgentUpdatesEvidenceRequestOutput:
    output = AgentUpdatesEvidenceRequestOutput.model_validate(value)
    index = next(
        item for item in request.evidenceBundle.items if item.resourceType == "agent_updates_index"
    )
    content = index.contentJson
    items = content.get("items") if isinstance(content, dict) else None
    if not isinstance(items, list):
        raise ValueError("结构化资料名录缺少 items")
    identities: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("结构化资料名录项必须是对象")
        resource_type = item.get("resourceType")
        resource_id = item.get("id")
        if (
            not isinstance(resource_type, str)
            or resource_type not in _AGENT_UPDATES_INDEX_RESOURCE_TYPES
            or not isinstance(resource_id, str)
            or not resource_id.strip()
            or (resource_type, resource_id) in identities
        ):
            raise ValueError("结构化资料名录身份无效或重复")
        identities.add((resource_type, resource_id))
    for need in output.evidenceRequest:
        if need.resourceType in _AGENT_UPDATES_SINGLETON_RESOURCE_TYPES:
            if need.resourceId != request.novelId:
                raise ValueError("结构化资料单例来源必须绑定当前小说")
        elif need.resourceType == "outline_tree":
            if need.resourceId != request.novelId:
                raise ValueError("结构化大纲树来源必须绑定当前小说")
        elif (need.resourceType, need.resourceId) not in identities:
            raise ValueError("结构化资料来源不在冻结名录中")
    return output


def _validate_chapter_plan_input(request: ExecutionStepRequest) -> None:
    if request.novelId is None:
        raise ExecutionCapabilityError("章节规划必须绑定 novelId")
    context_items = [
        item for item in request.evidenceBundle.items if item.resourceType == "chapter_plan_context"
    ]
    if len(context_items) != 1:
        raise ExecutionCapabilityError("章节规划 Evidence 必须包含唯一规划上下文")
    item = context_items[0]
    context = item.contentJson
    chapter = context.get("chapter") if isinstance(context, dict) else None
    if (
        not item.exists
        or item.contentType != "json"
        or item.range is not None
        or not isinstance(context, dict)
        or type(context.get("schemaVersion")) is not int
        or context.get("schemaVersion") != 1
        or context.get("novelId") != request.novelId
        or not isinstance(chapter, dict)
        or chapter.get("id") != item.resourceId
    ):
        raise ExecutionCapabilityError("章节规划 Evidence 的完整上下文或目标身份不一致")
    try:
        if request.purpose == "review":
            if set(request.input) != {"task", "candidate"}:
                raise ValueError("规划复审只接受 task 与精确候选")
            task = request.input["task"]
            if not isinstance(task, dict) or (
                task.get("workflow") != "long_serial"
                or task.get("operation") != "plan_chapter"
                or task.get("rubricVersion") != "rubric.chapter_plan.review.v1"
            ):
                raise ValueError("规划复审任务身份不一致")
            ChapterPlanInput.model_validate(
                {
                    "userInstruction": task.get("userInstruction"),
                    "targetWordCount": task.get("targetWordCount"),
                }
            )
            ChapterPlanResult.model_validate(request.input["candidate"])
            return
        plan = ChapterPlanInput.model_validate(request.input)
        previous = plan.previousArtifact
        if previous is None:
            if request.artifactId is not None or request.artifactRevision is not None:
                raise ValueError("初始规划不能绑定上一候选")
        elif (
            previous.artifactId != request.artifactId
            or previous.artifactRevision != request.artifactRevision
        ):
            raise ValueError("规划返工与精确上一候选身份不一致")
    except (TypeError, ValueError, ValidationError) as exc:
        raise ExecutionCapabilityError("章节规划输入或候选不符合冻结契约") from exc


def _validate_chapter_draft_input(request: ExecutionStepRequest) -> None:
    if request.novelId is None:
        raise ExecutionCapabilityError("正文写作必须绑定 novelId")
    contexts = [
        item
        for item in request.evidenceBundle.items
        if item.resourceType == "chapter_writing_context"
    ]
    if len(contexts) != 1:
        raise ExecutionCapabilityError("正文写作 Evidence 必须包含唯一完整上下文")
    item = contexts[0]
    context = item.contentJson
    chapter = context.get("currentChapter") if isinstance(context, dict) else None
    if (
        not item.exists
        or item.contentType != "json"
        or item.range is not None
        or not isinstance(context, dict)
        or type(context.get("schemaVersion")) is not int
        or context.get("schemaVersion") != 1
        or context.get("novelId") != request.novelId
        or not isinstance(chapter, dict)
        or chapter.get("id") != item.resourceId
    ):
        raise ExecutionCapabilityError("正文写作 Evidence 的完整上下文或目标身份不一致")
    try:
        if request.purpose == "review":
            if set(request.input) != {"task", "candidate"}:
                raise ValueError("正文复审只接受 task 与完整候选")
            task = request.input["task"]
            if (
                not isinstance(task, dict)
                or task.get("workflow") != "long_serial"
                or task.get("operation") != request.operation
                or task.get("rubricVersion") != "rubric.chapter_draft.review.v1"
            ):
                raise ValueError("正文复审任务身份不一致")
            ChapterDraftInput.model_validate(
                {
                    "userInstruction": task.get("userInstruction"),
                    "targetWordCount": task.get("targetWordCount"),
                }
            )
            if "originalUserInstruction" in task:
                ChapterDraftInput.model_validate(
                    {
                        "userInstruction": task["originalUserInstruction"],
                        "targetWordCount": task.get("targetWordCount"),
                    }
                )
            ChapterDraftResult.model_validate(request.input["candidate"])
            return
        draft = ChapterDraftInput.model_validate(request.input)
        previous = draft.previousArtifact
        if previous is None:
            if request.artifactId is not None or request.artifactRevision is not None:
                raise ValueError("初始写作不能绑定上一候选")
        elif (
            previous.artifactId != request.artifactId
            or previous.artifactRevision != request.artifactRevision
        ):
            raise ValueError("正文返工与精确上一候选身份不一致")
    except (TypeError, ValueError, ValidationError) as exc:
        raise ExecutionCapabilityError("正文输入或完整候选不符合冻结契约") from exc


def _validate_chapter_review_input(request: ExecutionStepRequest) -> None:
    contexts = [
        item
        for item in request.evidenceBundle.items
        if item.resourceType == "chapter_writing_context"
    ]
    item = contexts[0] if len(contexts) == 1 and len(request.evidenceBundle.items) == 1 else None
    context = item.contentJson if item is not None else None
    chapter = context.get("currentChapter") if isinstance(context, dict) else None
    schema_version = context.get("schemaVersion") if isinstance(context, dict) else None
    if (
        request.purpose != "generation"
        or request.lane != "interactive"
        or request.novelId is None
        or request.artifactId is not None
        or request.artifactRevision is not None
        or item is None
        or not item.exists
        or item.contentType != "json"
        or item.range is not None
        or not isinstance(context, dict)
        or type(schema_version) is not int
        or schema_version != 1
        or context.get("novelId") != request.novelId
        or not isinstance(chapter, dict)
        or chapter.get("id") != item.resourceId
    ):
        raise ExecutionCapabilityError("整章审阅输入或完整上下文身份不一致")
    try:
        ChapterReviewInput.model_validate(request.input)
    except ValidationError as exc:
        raise ExecutionCapabilityError("整章审阅 input 必须只含完整 userInstruction") from exc


def _validate_outline_selection_input(request: ExecutionStepRequest) -> None:
    contexts = [
        item
        for item in request.evidenceBundle.items
        if item.resourceType in {"outline_content", "outline_node_content"}
    ]
    item = contexts[0] if len(contexts) == 1 and len(request.evidenceBundle.items) == 1 else None
    try:
        if request.purpose == "review":
            if set(request.input) != {"task", "candidate"}:
                raise ValueError("大纲选区复审只接受 task 与精确候选")
            task = request.input["task"]
            if (
                not isinstance(task, dict)
                or task.get("workflow") != "long_serial"
                or task.get("operation") != "rewrite_outline_selection"
                or task.get("rubricVersion") != "rubric.outline_selection.review.v1"
            ):
                raise ValueError("大纲选区复审任务身份不一致")
            selection = OutlineSelectionInput.model_validate(
                {
                    "userInstruction": task.get("userInstruction"),
                    "selectionTarget": task.get("selectionTarget"),
                }
            )
            OutlineSelectionResult.model_validate(request.input["candidate"])
        else:
            selection = OutlineSelectionInput.model_validate(request.input)
        target = selection.selectionTarget
        if (
            item is None
            or request.novelId is None
            or not item.exists
            or item.contentType != "text"
            or item.contentText is None
        ):
            raise ValueError("大纲选区缺少唯一完整正文 Evidence")
        if (
            item.resourceType != target.resourceType
            or item.resourceId != target.resourceId
            or item.range is None
        ):
            raise ValueError("大纲选区 Evidence 与 selectionTarget 不一致")
        if (
            item.range.startCodePoint != target.selectionStart
            or item.range.endCodePoint != target.selectionEnd
            or target.selectionEnd > len(item.contentText)
        ):
            raise ValueError("大纲选区 Evidence range 不一致")
        if (
            item.contentSha256 != target.baseContentHash
            or item.resourceUpdatedAt != target.baseUpdatedAt
        ):
            raise ValueError("大纲选区 Evidence 来源版本不一致")
        selected = item.contentText[target.selectionStart : target.selectionEnd]
        if hashlib.sha256(selected.encode("utf-8")).hexdigest() != target.selectedTextHash:
            raise ValueError("大纲选区正文或 selectedTextHash 不一致")
        if request.purpose == "review":
            return
        previous = selection.previousCandidate
        if previous is None:
            if request.artifactId is not None or request.artifactRevision is not None:
                raise ValueError("初始大纲改写不能绑定候选")
        elif (
            previous.artifactId != request.artifactId
            or previous.artifactRevision != request.artifactRevision
        ):
            raise ValueError("大纲返工与精确上一候选不一致")
    except (TypeError, ValueError, ValidationError) as exc:
        raise ExecutionCapabilityError("大纲选区输入或 Evidence 不符合冻结契约") from exc


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
    return error.code == "http_error" and (error.statusCode is not None and error.statusCode >= 500)


def _provider_outcome_unknown(
    error: ProviderTransportError,
    *,
    supports_request_idempotency: bool,
) -> bool:
    if supports_request_idempotency:
        return False
    if error.code in {"connection_error", "timeout_error"}:
        return True
    return error.code == "http_error" and error.statusCode is not None and error.statusCode >= 500


def _elapsed_millis(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _usage(
    result: ModelTurnResult | EmbeddingResult | VideoResponsesResult | None,
    *,
    provider_attempts: int,
    wall_time_millis: int,
    reasoning_mode: Literal["disabled", "bounded"],
    quality_tool_response: bool = False,
) -> StepUsage:
    if result is None:
        return _unknown_usage(
            provider_attempts=provider_attempts,
            wall_time_millis=wall_time_millis,
        )
    if isinstance(result, VideoResponsesResult):
        values = result.usage.model_dump(exclude_none=True, exclude={"totalTokens"})
        return StepUsage(
            usageStatus="complete" if len(values) == 7 else "partial" if values else "unknown",
            providerAttempts=provider_attempts,
            protocolCorrections=int(result.recoveryCode is not None),
            wallTimeMillis=wall_time_millis,
            **values,
        )
    if isinstance(result, EmbeddingResult):
        if result.input_tokens is None:
            return _unknown_usage(
                provider_attempts=provider_attempts, wall_time_millis=wall_time_millis
            )
        return StepUsage(
            usageStatus="partial",
            providerAttempts=provider_attempts,
            protocolCorrections=0,
            wallTimeMillis=wall_time_millis,
            inputTokens=result.input_tokens,
            completionTokens=0,
            reasoningTokens=0,
            visibleOutputTokens=0,
        )
    input_tokens = result.usage.promptTokens
    cached_tokens = result.usage.cachedTokens
    protocol_corrections = result.structuredOutputCorrectionCount
    if quality_tool_response:
        # 一次响应的确定性闭合恢复与另一独立模型 Step 分开计数。
        protocol_corrections = int(result.recoveredToolCallCount > 0)
    if cached_tokens > input_tokens:
        return _unknown_usage(
            provider_attempts=provider_attempts,
            wall_time_millis=wall_time_millis,
            protocol_corrections=protocol_corrections,
        )
    cache_miss_tokens = input_tokens - cached_tokens
    completion_tokens = result.usage.completionTokens
    reasoning_tokens = result.diagnostics.reasoningTokens
    if reasoning_mode == "disabled" and reasoning_tokens is None:
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
    if request.workflow == "short_medium" and result.toolCalls:
        return "protocol", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if result.structuredOutputDiagnostic is not None or result.structuredOutput is None:
        return "protocol", "MODEL_STRUCTURED_OUTPUT_INVALID"
    if request.purpose == "generation":
        if request.operation == "rewrite_chapter_selection":
            replacement = result.structuredOutput.get("replacement")
            if isinstance(replacement, str) and not replacement.strip():
                return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
        elif request.operation == "answer_question":
            answer = result.structuredOutput.get("answer")
            if isinstance(answer, str) and not answer.strip():
                return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    try:
        jsonschema_rs.validator_for(request.outputSchema.jsonSchema).validate(
            result.structuredOutput
        )
    except Exception:
        return "validation", "MODEL_OUTPUT_SCHEMA_INVALID"
    if request.purpose == "generation" and request.operation == "answer_question":
        try:
            ChatAnswerOutput.model_validate(result.structuredOutput)
        except ValidationError:
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if request.workflow == "short_medium":
        try:
            materialize_short_medium_output(request.operation or "", result.structuredOutput)
        except (ValueError, ValidationError):
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if request.purpose == "generation" and request.operation == "plan_chapter":
        try:
            ChapterPlanOutput.model_validate(result.structuredOutput)
        except ValidationError:
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if request.purpose == "generation" and request.operation == "write_chapter":
        try:
            ChapterDraftOutput.model_validate(result.structuredOutput)
        except ValidationError:
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if request.purpose == "generation" and request.operation == "rewrite_scene":
        try:
            ChapterDraftOutput.model_validate(result.structuredOutput)
        except ValidationError:
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if request.purpose == "generation" and request.operation == "review_chapter":
        try:
            ChapterReviewOutput.model_validate(result.structuredOutput)
        except ValidationError:
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if request.purpose == "generation" and request.operation == "rewrite_outline_selection":
        try:
            OutlineSelectionOutput.model_validate(result.structuredOutput)
        except ValidationError:
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if request.purpose == "generation" and request.operation in _AGENT_UPDATES_OPERATIONS:
        try:
            if (
                _uses_agent_updates_evidence_request_schema(request)
                and "evidenceRequest" in result.structuredOutput
            ):
                _agent_updates_evidence_request(request, result.structuredOutput)
            else:
                AgentUpdatesOutput.model_validate(result.structuredOutput)
        except (TypeError, ValueError, ValidationError):
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    if request.purpose == "resolve_intent":
        try:
            _intent_command(request, result.structuredOutput)
        except (ValueError, ValidationError, ExecutionCapabilityError):
            return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    return None


def _validate_portrait_provider_result(
    result: ModelTurnResult,
) -> tuple[Literal["provider_terminal", "protocol", "validation"], str] | None:
    if result.finishReason == "length":
        return "provider_terminal", "MODEL_OUTPUT_TRUNCATED"
    if result.finishReason == "content_filter":
        return "provider_terminal", "MODEL_OUTPUT_FILTERED"
    if result.finishReason != "stop":
        return "protocol", "MODEL_FINISH_REASON_INVALID"
    if (
        result.toolCalls
        or result.invalidToolCallCount
        or result.recoveredToolCallCount
        or result.structuredOutput is not None
        or result.structuredOutputDiagnostic is not None
    ):
        return "protocol", "MODEL_OUTPUT_PROTOCOL_INVALID"
    try:
        StylePortraitSectionOutput(content=result.content)
    except ValidationError:
        return "validation", "MODEL_OUTPUT_PROTOCOL_INVALID"
    return None


def _validate_quality_provider_result(
    request: ExecutionStepRequest,
    result: ModelTurnResult,
    usage: StepUsage,
) -> tuple[Literal["provider_terminal", "protocol", "validation"], str] | None:
    if _step_budget_exceeded(request, usage):
        return "validation", "STEP_BUDGET_EXCEEDED"
    if (
        usage.usageStatus == "unknown"
        or any(
            value is None
            for value in (
                usage.inputTokens,
                usage.cachedTokens,
                usage.promptCacheMissTokens,
                usage.completionTokens,
                usage.reasoningTokens,
                usage.visibleOutputTokens,
            )
        )
        or result.usage.totalTokens != result.usage.promptTokens + result.usage.completionTokens
    ):
        return "protocol", "MODEL_USAGE_INVALID"
    if result.finishReason in {"length", "content_filter", "insufficient_system_resource"}:
        return "provider_terminal", {
            "length": "MODEL_OUTPUT_TRUNCATED",
            "content_filter": "MODEL_OUTPUT_FILTERED",
            "insufficient_system_resource": "MODEL_INSUFFICIENT_SYSTEM_RESOURCE",
        }[result.finishReason]
    if result.finishReason != "tool_calls" or result.structuredOutput is not None:
        return "protocol", "MODEL_FINISH_REASON_INVALID"
    output, correctable = quality_response(result)
    if output is None:
        if correctable and request.purpose == "generation":
            return "protocol", QUALITY_CORRECTION_REQUIRED
        return "protocol", "MODEL_TOOL_PROTOCOL_RECOVERY_FAILED"
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
    if request.workflow == "short_medium":
        return materialize_short_medium_output(request.operation or "", output)
    if request.workflow == "long_serial" and request.operation == "rewrite_chapter_selection":
        replacement = output.get("replacement")
        if not isinstance(replacement, str) or not replacement.strip():
            raise ExecutionCapabilityError("章节选区改写结果缺少 replacement")
        output["contentSha256"] = hashlib.sha256(replacement.encode("utf-8")).hexdigest()
    elif request.workflow == "long_serial" and request.operation == "answer_question":
        answer = ChatAnswerOutput.model_validate(output)
        output = answer.model_dump(mode="json")
    elif request.workflow == "long_serial" and request.operation == "plan_chapter":
        output = materialize_chapter_plan_output(output)
    elif request.workflow == "long_serial" and request.operation in {
        "write_chapter",
        "rewrite_scene",
    }:
        output = materialize_chapter_draft_output(output)
    elif request.workflow == "long_serial" and request.operation == "review_chapter":
        output = ChapterReviewOutput.model_validate(output).model_dump(mode="json")
    elif request.workflow == "long_serial" and request.operation == "rewrite_outline_selection":
        output = materialize_outline_selection_output(output)
    elif request.workflow == "long_serial" and request.operation in _AGENT_UPDATES_OPERATIONS:
        output = materialize_agent_updates_output(output)
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
        if request.operation in _AGENT_UPDATES_OPERATIONS and (
            finding.get("candidateRange") is not None or "candidatePatch" in finding
        ):
            raise ValueError("结构化资料 Reviewer 不允许正文定位或补丁")
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
