"""只读加载并解析 Core 权威 V2 Operation/Profile/Prompt/Deployment/Output Registry。"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal, Self, cast

import jsonschema_rs
from inkforge_contracts.execution import StepBudget as ContractStepBudget
from inkforge_contracts.execution import canonical_execution_sha256
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
    model_validator,
)

Environment = Literal["dev", "test", "production"]
ReasoningMode = Literal["disabled", "bounded"]
ProfilePurpose = Literal["generation", "review", "evaluation", "embedding", "media"]
OutputPurpose = Literal["generation", "evaluation", "embedding", "media"]
Lane = Literal["interactive", "creative", "batch_media"]
StructuredOutputRoute = Literal["responses_json_schema_v1", "chat_json_output_v1"]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

_DEFAULT_CONTRACT_DIR = Path("/app/contracts/agent-execution")
_MAX_CONTRACT_FILE_BYTES = 8 * 1024 * 1024
_MANIFEST_FILENAMES = {
    "catalog": "operation-catalog.v1.json",
    "schema": "operation-catalog.schema.json",
    "profileRegistry": "profile-registry.v1.json",
    "profileRegistrySchema": "profile-registry.schema.json",
    "deploymentProfileRegistry": "deployment-profile-registry.v1.json",
    "deploymentProfileRegistrySchema": "deployment-profile-registry.schema.json",
    "promptProfileRegistry": "prompt-profile-registry.v1.json",
    "promptProfileRegistrySchema": "prompt-profile-registry.schema.json",
    "outputSchemaRegistry": "output-schema-registry.v1.json",
    "outputSchemaRegistrySchema": "output-schema-registry.schema.json",
    "stepBudgetRegistry": "step-budget-registry.v1.json",
    "stepBudgetRegistrySchema": "step-budget-registry.schema.json",
    "systemPurposeRegistry": "system-purpose-registry.v1.json",
    "systemPurposeRegistrySchema": "system-purpose-registry.schema.json",
    "hashVectors": "hash-vectors.v1.json",
}


class ExecutionRegistryError(RuntimeError):
    """Registry 不完整、不可信或不能用于当前执行环境。"""


class ExecutionRegistryHashError(ExecutionRegistryError):
    """Manifest 声明的原始文件哈希与实际文件不一致。"""


class ExecutionRegistryReferenceError(ExecutionRegistryError):
    """Catalog 引用了缺失或不可执行的 Registry 条目。"""


class ExecutionOperationNotFoundError(ExecutionRegistryError):
    """请求的 Operation 不存在。"""


class ExecutionOperationDisabledError(ExecutionRegistryError):
    """Operation 尚未开放 V2 执行。"""


class ExecutionOperationEnvironmentError(ExecutionRegistryError):
    """Operation 被当前环境门禁禁止。"""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _ManifestEntry(_StrictModel):
    path: str = Field(min_length=1, max_length=128)
    sha256: Sha256


class _Manifest(_StrictModel):
    manifestVersion: Literal["1"]
    catalogVersion: Literal["1"]
    catalog: _ManifestEntry
    schema_entry: _ManifestEntry = Field(alias="schema")
    profileRegistry: _ManifestEntry
    profileRegistrySchema: _ManifestEntry
    deploymentProfileRegistry: _ManifestEntry
    deploymentProfileRegistrySchema: _ManifestEntry
    promptProfileRegistry: _ManifestEntry
    promptProfileRegistrySchema: _ManifestEntry
    outputSchemaRegistry: _ManifestEntry
    outputSchemaRegistrySchema: _ManifestEntry
    stepBudgetRegistry: _ManifestEntry
    stepBudgetRegistrySchema: _ManifestEntry
    systemPurposeRegistry: _ManifestEntry
    systemPurposeRegistrySchema: _ManifestEntry
    hashVectors: _ManifestEntry


class _ReviewPolicyDocument(_StrictModel):
    profile: str
    mode: Literal["none", "single", "parallel"]
    reviewerProfiles: list[str]
    reviewerStepBudgetProfiles: dict[str, str] = Field(default_factory=dict)
    reviewerOutputSchema: str | None = None
    rubricVersion: str | None = None
    evidencePolicy: str | None = None
    lane: Lane | None = None
    mergePolicy: str
    maxAutomaticRevisions: int = Field(ge=0, le=1)
    onUnavailable: Literal["continue", "awaiting_user", "fail"]


class _RunBudgetDocument(_StrictModel):
    profile: str
    maxModelCalls: int = Field(ge=1, le=64)
    maxInputTokens: int = Field(ge=1, le=10_000_000)
    maxPromptCacheMissTokens: int = Field(ge=1, le=10_000_000)
    maxCompletionTokens: int = Field(ge=0, le=10_000_000)
    maxReasoningTokens: int = Field(ge=0, le=10_000_000)
    maxVisibleOutputTokens: int = Field(ge=0, le=10_000_000)
    maxCostMicros: int = Field(ge=0, le=1_000_000_000)
    maxWallClockSeconds: int = Field(ge=1, le=86_400)
    maxProtocolCorrectionSteps: int = Field(ge=0, le=1)
    maxProviderRetriesPerStep: int = Field(ge=0, le=2)

    @model_validator(mode="after")
    def validate_totals(self) -> Self:
        if self.maxPromptCacheMissTokens > self.maxInputTokens:
            raise ValueError("Run cache miss 预算不能超过输入预算")
        if self.maxReasoningTokens + self.maxVisibleOutputTokens > self.maxCompletionTokens:
            raise ValueError("Run reasoning 与可见输出预算之和不能超过 completion 预算")
        return self


class _OperationDocument(_StrictModel):
    key: str
    workflow: str
    operation: str
    labels: dict[str, str]
    targetKinds: list[str]
    scopeKinds: list[str]
    mutating: bool
    developmentOnly: bool
    v2Enabled: bool
    evidencePolicy: str
    generatorProfile: str
    generatorStepBudgetProfile: str | None = None
    outputSchema: str
    deterministicValidators: list[str]
    reviewPolicy: _ReviewPolicyDocument
    applyHandler: str
    runBudgetProfile: _RunBudgetDocument
    lane: Lane


class _CatalogDocument(_StrictModel):
    catalogVersion: Literal["1"]
    operations: list[_OperationDocument]


class _ProfileDocument(_StrictModel):
    key: str
    version: int = Field(ge=1)
    supported: bool
    reasoningMode: ReasoningMode
    purpose: ProfilePurpose
    promptProfile: str
    deploymentProfileKey: str


class _ProfileRegistryDocument(_StrictModel):
    registryVersion: Literal["1"]
    profiles: list[_ProfileDocument]


class _DeploymentModelDocument(_StrictModel):
    provider: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    model: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    )
    transportProfile: str
    endpointProfile: str
    structuredOutputRoute: StructuredOutputRoute
    capabilityVersion: str
    reasoningMode: ReasoningMode
    supportsRequestIdempotency: bool
    allowedEnvironments: list[Environment]
    pricingVersion: str
    billable: bool


class _DeploymentProfileDocument(_StrictModel):
    key: str
    version: int = Field(ge=1)
    supported: bool
    purpose: ProfilePurpose
    allowedModels: list[_DeploymentModelDocument]


class _DeploymentProfileRegistryDocument(_StrictModel):
    registryVersion: Literal["1"]
    profiles: list[_DeploymentProfileDocument]


class _PromptProfileDocument(_StrictModel):
    key: str
    version: int = Field(ge=1)
    supported: bool
    purpose: ProfilePurpose
    sha256: Sha256
    systemPrompt: str = Field(min_length=1, max_length=16_000)


class _PromptProfileRegistryDocument(_StrictModel):
    registryVersion: Literal["1"]
    hashAlgorithm: Literal["sha256-utf8/1"]
    prompts: list[_PromptProfileDocument]


class _OutputSchemaDocument(_StrictModel):
    key: str
    version: int = Field(ge=1)
    supported: bool
    purpose: OutputPurpose
    sha256: Sha256
    jsonSchema: dict[str, JsonValue]


class _OutputSchemaRegistryDocument(_StrictModel):
    registryVersion: Literal["1"]
    hashAlgorithm: Literal["inkforge-canonical-json/1"]
    schemas: list[_OutputSchemaDocument]


class _StepBudgetProfileDocument(_StrictModel):
    key: str
    version: int = Field(ge=1)
    supported: bool
    budget: ContractStepBudget


class _StepBudgetRegistryDocument(_StrictModel):
    registryVersion: Literal["1"]
    budgets: list[_StepBudgetProfileDocument]


class _SystemPurposeDocument(_StrictModel):
    purpose: str
    supported: bool
    modelProfile: str
    outputSchema: str
    evidencePolicy: str
    lane: Lane
    stepBudgetProfile: str
    workflows: list[str]
    parentOperations: list[str]


class _SystemPurposeRegistryDocument(_StrictModel):
    registryVersion: Literal["1"]
    purposes: list[_SystemPurposeDocument]


@dataclass(frozen=True, slots=True)
class RunBudgetProfile:
    profile: str
    max_model_calls: int
    max_input_tokens: int
    max_prompt_cache_miss_tokens: int
    max_completion_tokens: int
    max_reasoning_tokens: int
    max_visible_output_tokens: int
    max_cost_micros: int
    max_wall_clock_seconds: int
    max_protocol_correction_steps: int
    max_provider_retries_per_step: int


@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    profile: str
    mode: Literal["none", "single", "parallel"]
    reviewer_profile_keys: tuple[str, ...]
    reviewer_step_budget_keys: Mapping[str, str]
    reviewer_output_schema_key: str | None
    rubric_version: str | None
    evidence_policy: str | None
    lane: Lane | None
    merge_policy: str
    max_automatic_revisions: int
    on_unavailable: Literal["continue", "awaiting_user", "fail"]


@dataclass(frozen=True, slots=True)
class PromptProfileDefinition:
    key: str
    version: int
    supported: bool
    purpose: ProfilePurpose
    sha256: str
    system_prompt: str


@dataclass(frozen=True, slots=True)
class DeploymentModelDefinition:
    provider: str
    model: str
    transport_profile: str
    endpoint_profile: str
    structured_output_route: StructuredOutputRoute
    capability_version: str
    reasoning_mode: ReasoningMode
    supports_request_idempotency: bool
    allowed_environments: tuple[Environment, ...]
    pricing_version: str
    billable: bool


@dataclass(frozen=True, slots=True)
class DeploymentProfileDefinition:
    key: str
    version: int
    supported: bool
    purpose: ProfilePurpose
    allowed_models: tuple[DeploymentModelDefinition, ...]


@dataclass(frozen=True, slots=True)
class ProfileDefinition:
    key: str
    version: int
    supported: bool
    reasoning_mode: ReasoningMode
    purpose: ProfilePurpose
    prompt_profile: PromptProfileDefinition
    deployment_profile_key: str


@dataclass(frozen=True, slots=True)
class OutputSchemaDefinition:
    key: str
    version: int
    supported: bool
    purpose: OutputPurpose
    sha256: str
    json_schema: Mapping[str, object]

    def json_schema_value(self) -> dict[str, JsonValue]:
        """返回可交给 Pydantic/Provider 的独立 JSON 值，避免泄露可变 Registry 状态。"""

        return cast(dict[str, JsonValue], _thaw_json(self.json_schema))


@dataclass(frozen=True, slots=True)
class StepBudgetDefinition:
    key: str
    version: int
    supported: bool
    max_model_calls: int
    max_input_tokens: int
    max_prompt_cache_miss_tokens: int
    max_completion_tokens: int
    max_reasoning_tokens: int
    max_visible_output_tokens: int
    max_cost_micros: int
    max_wall_clock_seconds: int
    max_provider_retries: int
    max_protocol_corrections: int


@dataclass(frozen=True, slots=True)
class SystemPurposeDefinition:
    purpose: str
    supported: bool
    model_profile_key: str
    output_schema_key: str
    evidence_policy: str
    lane: Lane
    step_budget_key: str
    workflows: tuple[str, ...]
    parent_operations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    key: str
    workflow: str
    operation: str
    labels: Mapping[str, str]
    target_kinds: tuple[str, ...]
    scope_kinds: tuple[str, ...]
    mutating: bool
    development_only: bool
    v2_enabled: bool
    evidence_policy: str
    generator_profile_key: str
    generator_step_budget_key: str | None
    output_schema_key: str
    deterministic_validators: tuple[str, ...]
    review_policy: ReviewPolicy
    apply_handler: str
    run_budget: RunBudgetProfile
    lane: Lane


@dataclass(frozen=True, slots=True)
class ResolvedExecutionOperation:
    operation: OperationDefinition
    generator_profile: ProfileDefinition
    generator_step_budget: StepBudgetDefinition
    reviewer_profiles: tuple[ProfileDefinition, ...]
    reviewer_step_budgets: Mapping[str, StepBudgetDefinition]
    output_schema: OutputSchemaDefinition
    reviewer_output_schema: OutputSchemaDefinition | None


@dataclass(frozen=True, slots=True)
class ExecutionRegistry:
    catalog_version: str
    manifest_fingerprint: str
    environment: Environment
    operations: Mapping[str, OperationDefinition]
    profiles: Mapping[str, ProfileDefinition]
    deployment_profiles: Mapping[str, DeploymentProfileDefinition]
    prompt_profiles: Mapping[str, PromptProfileDefinition]
    output_schemas: Mapping[str, OutputSchemaDefinition]
    step_budgets: Mapping[str, StepBudgetDefinition]
    system_purposes: Mapping[str, SystemPurposeDefinition]

    def require_authorized_deployment(
        self,
        *,
        deployment_profile_key: str,
        provider: str,
        model: str,
        transport_profile: str,
        endpoint_profile: str,
        structured_output_route: StructuredOutputRoute,
        capability_version: str,
        reasoning_mode: ReasoningMode,
        supports_request_idempotency: bool,
    ) -> DeploymentModelDefinition:
        """按 manifest 冻结的完整部署元组授权，禁止只信任 Agent 自算 fingerprint。"""

        profile = self.deployment_profiles.get(deployment_profile_key)
        if profile is None or not profile.supported:
            raise ExecutionRegistryReferenceError("Deployment Profile 未发布或不存在")
        for allowed in profile.allowed_models:
            if (
                allowed.provider == provider
                and allowed.model == model
                and allowed.transport_profile == transport_profile
                and allowed.endpoint_profile == endpoint_profile
                and allowed.structured_output_route == structured_output_route
                and allowed.capability_version == capability_version
                and allowed.reasoning_mode == reasoning_mode
                and allowed.supports_request_idempotency == supports_request_idempotency
                and self.environment in allowed.allowed_environments
            ):
                return allowed
        raise ExecutionRegistryReferenceError("部署 provider/model 未被 Deployment Profile 授权")

    def resolve(self, workflow: str, operation: str) -> ResolvedExecutionOperation:
        key = f"{workflow}.{operation}"
        definition = self.operations.get(key)
        if definition is None:
            raise ExecutionOperationNotFoundError(f"未知 V2 Operation：{key}")
        if definition.development_only and self.environment != "dev":
            raise ExecutionOperationEnvironmentError(f"当前环境禁止 Operation：{key}")
        if not definition.v2_enabled:
            raise ExecutionOperationDisabledError(f"Operation 尚未启用 V2：{key}")
        generator = self.profiles[definition.generator_profile_key]
        reviewers = tuple(
            self.profiles[profile_key]
            for profile_key in definition.review_policy.reviewer_profile_keys
        )
        output_schema = self.output_schemas[definition.output_schema_key]
        generator_budget_key = definition.generator_step_budget_key
        reviewer_schema_key = definition.review_policy.reviewer_output_schema_key
        if generator_budget_key is None:
            raise ExecutionRegistryReferenceError(f"V2 Operation 执行引用不完整：{key}")
        reviewer_output_schema = (
            None
            if reviewer_schema_key is None
            else self.output_schemas[reviewer_schema_key]
        )
        return ResolvedExecutionOperation(
            operation=definition,
            generator_profile=generator,
            generator_step_budget=self.step_budgets[generator_budget_key],
            reviewer_profiles=reviewers,
            reviewer_step_budgets=MappingProxyType(
                {
                    profile_key: self.step_budgets[budget_key]
                    for profile_key, budget_key in (
                        definition.review_policy.reviewer_step_budget_keys.items()
                    )
                }
            ),
            output_schema=output_schema,
            reviewer_output_schema=reviewer_output_schema,
        )


def resolve_execution_contract_dir(contract_dir: str | Path | None = None) -> Path:
    explicit = contract_dir
    if explicit is None:
        explicit = os.environ.get("INKFORGE_EXECUTION_CONTRACT_DIR")
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if not path.is_dir():
            raise ExecutionRegistryError("显式配置的 V2 execution contract 目录不存在")
        return path

    if _DEFAULT_CONTRACT_DIR.is_dir():
        return _DEFAULT_CONTRACT_DIR.resolve()
    repository_fallback = Path(__file__).resolve().parents[5] / "contracts" / "agent-execution"
    if repository_fallback.is_dir():
        return repository_fallback.resolve()
    raise ExecutionRegistryError("找不到 V2 execution contract 目录")


def load_execution_registry(
    contract_dir: str | Path | None = None,
    *,
    environment: Environment,
) -> ExecutionRegistry:
    root = resolve_execution_contract_dir(contract_dir)
    manifest_document = _read_json(root / "manifest.json")
    manifest = _parse_model(_Manifest, manifest_document, "manifest.json")
    entries = {
        "catalog": manifest.catalog,
        "schema": manifest.schema_entry,
        "profileRegistry": manifest.profileRegistry,
        "profileRegistrySchema": manifest.profileRegistrySchema,
        "deploymentProfileRegistry": manifest.deploymentProfileRegistry,
        "deploymentProfileRegistrySchema": manifest.deploymentProfileRegistrySchema,
        "promptProfileRegistry": manifest.promptProfileRegistry,
        "promptProfileRegistrySchema": manifest.promptProfileRegistrySchema,
        "outputSchemaRegistry": manifest.outputSchemaRegistry,
        "outputSchemaRegistrySchema": manifest.outputSchemaRegistrySchema,
        "stepBudgetRegistry": manifest.stepBudgetRegistry,
        "stepBudgetRegistrySchema": manifest.stepBudgetRegistrySchema,
        "systemPurposeRegistry": manifest.systemPurposeRegistry,
        "systemPurposeRegistrySchema": manifest.systemPurposeRegistrySchema,
        "hashVectors": manifest.hashVectors,
    }
    documents: dict[str, dict[str, object]] = {}
    for name, expected_filename in _MANIFEST_FILENAMES.items():
        entry = entries[name]
        if entry.path != expected_filename:
            raise ExecutionRegistryError(f"Manifest 的 {name} 路径不符合固定契约")
        path = _safe_contract_path(root, entry.path)
        raw = _read_bytes(path)
        if hashlib.sha256(raw).hexdigest() != entry.sha256:
            raise ExecutionRegistryHashError(f"V2 execution contract 哈希不一致：{entry.path}")
        documents[name] = _decode_json(raw, entry.path)

    _validate_json_schema(documents["schema"], documents["catalog"], "Operation Catalog")
    _validate_json_schema(
        documents["profileRegistrySchema"],
        documents["profileRegistry"],
        "Profile Registry",
    )
    _validate_json_schema(
        documents["deploymentProfileRegistrySchema"],
        documents["deploymentProfileRegistry"],
        "Deployment Profile Registry",
    )
    _validate_json_schema(
        documents["promptProfileRegistrySchema"],
        documents["promptProfileRegistry"],
        "Prompt Profile Registry",
    )
    _validate_json_schema(
        documents["outputSchemaRegistrySchema"],
        documents["outputSchemaRegistry"],
        "Output Schema Registry",
    )
    _validate_json_schema(
        documents["stepBudgetRegistrySchema"],
        documents["stepBudgetRegistry"],
        "Step Budget Registry",
    )
    _validate_json_schema(
        documents["systemPurposeRegistrySchema"],
        documents["systemPurposeRegistry"],
        "System Purpose Registry",
    )

    catalog = _parse_model(_CatalogDocument, documents["catalog"], "Operation Catalog")
    profile_registry = _parse_model(
        _ProfileRegistryDocument,
        documents["profileRegistry"],
        "Profile Registry",
    )
    deployment_profile_registry = _parse_model(
        _DeploymentProfileRegistryDocument,
        documents["deploymentProfileRegistry"],
        "Deployment Profile Registry",
    )
    prompt_profile_registry = _parse_model(
        _PromptProfileRegistryDocument,
        documents["promptProfileRegistry"],
        "Prompt Profile Registry",
    )
    output_registry = _parse_model(
        _OutputSchemaRegistryDocument,
        documents["outputSchemaRegistry"],
        "Output Schema Registry",
    )
    step_budget_registry = _parse_model(
        _StepBudgetRegistryDocument,
        documents["stepBudgetRegistry"],
        "Step Budget Registry",
    )
    system_purpose_registry = _parse_model(
        _SystemPurposeRegistryDocument,
        documents["systemPurposeRegistry"],
        "System Purpose Registry",
    )
    if catalog.catalogVersion != manifest.catalogVersion:
        raise ExecutionRegistryError("Manifest 与 Operation Catalog 版本不一致")

    prompt_profiles = _prompt_profiles(prompt_profile_registry)
    deployment_profiles = _deployment_profiles(deployment_profile_registry)
    profiles = _profiles(profile_registry, prompt_profiles, deployment_profiles)
    output_schemas = _output_schemas(output_registry)
    step_budgets = _step_budgets(step_budget_registry)
    system_purposes = _system_purposes(system_purpose_registry)
    operations = _operations(catalog)
    _validate_references(
        operations,
        profiles,
        output_schemas,
        step_budgets,
        system_purposes,
    )
    return ExecutionRegistry(
        catalog_version=catalog.catalogVersion,
        manifest_fingerprint=canonical_execution_sha256(manifest_document),
        environment=environment,
        operations=MappingProxyType(operations),
        profiles=MappingProxyType(profiles),
        deployment_profiles=MappingProxyType(deployment_profiles),
        prompt_profiles=MappingProxyType(prompt_profiles),
        output_schemas=MappingProxyType(output_schemas),
        step_budgets=MappingProxyType(step_budgets),
        system_purposes=MappingProxyType(system_purposes),
    )


def _prompt_profiles(
    document: _PromptProfileRegistryDocument,
) -> dict[str, PromptProfileDefinition]:
    result: dict[str, PromptProfileDefinition] = {}
    for item in document.prompts:
        _require_key_version(item.key, item.version)
        if item.key in result:
            raise ExecutionRegistryReferenceError(
                f"Prompt Profile Registry 存在重复 key：{item.key}"
            )
        if hashlib.sha256(item.systemPrompt.encode("utf-8")).hexdigest() != item.sha256:
            raise ExecutionRegistryHashError(
                f"Prompt Profile UTF-8 SHA-256 不一致：{item.key}"
            )
        result[item.key] = PromptProfileDefinition(
            key=item.key,
            version=item.version,
            supported=item.supported,
            purpose=item.purpose,
            sha256=item.sha256,
            system_prompt=item.systemPrompt,
        )
    return result


def _deployment_profiles(
    document: _DeploymentProfileRegistryDocument,
) -> dict[str, DeploymentProfileDefinition]:
    result: dict[str, DeploymentProfileDefinition] = {}
    for item in document.profiles:
        _require_key_version(item.key, item.version)
        if item.key in result:
            raise ExecutionRegistryReferenceError(
                f"Deployment Profile Registry 存在重复 key：{item.key}"
            )
        if item.supported != bool(item.allowedModels):
            raise ExecutionRegistryReferenceError(
                f"Deployment Profile supported 与 allowedModels 不一致：{item.key}"
            )
        allowed_models: list[DeploymentModelDefinition] = []
        identities: set[
            tuple[str, str, str, str, StructuredOutputRoute, str, ReasoningMode, bool]
        ] = set()
        for allowed in item.allowedModels:
            _require_versioned_identifier(allowed.transportProfile, "transportProfile")
            _require_versioned_identifier(allowed.endpointProfile, "endpointProfile")
            _require_versioned_identifier(allowed.capabilityVersion, "capabilityVersion")
            _require_versioned_identifier(allowed.pricingVersion, "pricingVersion")
            if len(allowed.allowedEnvironments) != len(set(allowed.allowedEnvironments)):
                raise ExecutionRegistryReferenceError(
                    f"Deployment Profile allowedEnvironments 重复：{item.key}"
                )
            identity = (
                allowed.provider,
                allowed.model,
                allowed.transportProfile,
                allowed.endpointProfile,
                allowed.structuredOutputRoute,
                allowed.capabilityVersion,
                allowed.reasoningMode,
                allowed.supportsRequestIdempotency,
            )
            if identity in identities:
                raise ExecutionRegistryReferenceError(
                    f"Deployment Profile 存在重复授权元组：{item.key}"
                )
            identities.add(identity)
            allowed_models.append(
                DeploymentModelDefinition(
                    provider=allowed.provider,
                    model=allowed.model,
                    transport_profile=allowed.transportProfile,
                    endpoint_profile=allowed.endpointProfile,
                    structured_output_route=allowed.structuredOutputRoute,
                    capability_version=allowed.capabilityVersion,
                    reasoning_mode=allowed.reasoningMode,
                    supports_request_idempotency=allowed.supportsRequestIdempotency,
                    allowed_environments=tuple(allowed.allowedEnvironments),
                    pricing_version=allowed.pricingVersion,
                    billable=allowed.billable,
                )
            )
        result[item.key] = DeploymentProfileDefinition(
            key=item.key,
            version=item.version,
            supported=item.supported,
            purpose=item.purpose,
            allowed_models=tuple(allowed_models),
        )
    return result


def _profiles(
    document: _ProfileRegistryDocument,
    prompts: Mapping[str, PromptProfileDefinition],
    deployments: Mapping[str, DeploymentProfileDefinition],
) -> dict[str, ProfileDefinition]:
    result: dict[str, ProfileDefinition] = {}
    for item in document.profiles:
        _require_key_version(item.key, item.version)
        if item.key in result:
            raise ExecutionRegistryReferenceError(f"Profile Registry 存在重复 key：{item.key}")
        prompt = prompts.get(item.promptProfile)
        if prompt is None:
            raise ExecutionRegistryReferenceError(
                f"Profile {item.key} 引用了缺失 Prompt Profile：{item.promptProfile}"
            )
        if prompt.purpose != item.purpose:
            raise ExecutionRegistryReferenceError(
                f"Profile {item.key} 与 Prompt Profile purpose 不一致"
            )
        if item.supported and not prompt.supported:
            raise ExecutionRegistryReferenceError(
                f"已启用 Profile {item.key} 引用了未发布 Prompt Profile"
            )
        deployment = deployments.get(item.deploymentProfileKey)
        if deployment is None:
            raise ExecutionRegistryReferenceError(
                f"Profile {item.key} 引用了缺失 Deployment Profile：{item.deploymentProfileKey}"
            )
        if deployment.purpose != item.purpose:
            raise ExecutionRegistryReferenceError(
                f"Profile {item.key} 与 Deployment Profile purpose 不一致"
            )
        if item.supported and not deployment.supported:
            raise ExecutionRegistryReferenceError(
                f"已启用 Profile {item.key} 引用了未发布 Deployment Profile"
            )
        if any(
            allowed.reasoning_mode != item.reasoningMode
            for allowed in deployment.allowed_models
        ):
            raise ExecutionRegistryReferenceError(
                f"Profile {item.key} 与 Deployment Profile reasoningMode 不一致"
            )
        result[item.key] = ProfileDefinition(
            key=item.key,
            version=item.version,
            supported=item.supported,
            reasoning_mode=item.reasoningMode,
            purpose=item.purpose,
            prompt_profile=prompt,
            deployment_profile_key=item.deploymentProfileKey,
        )
    return result


def _output_schemas(
    document: _OutputSchemaRegistryDocument,
) -> dict[str, OutputSchemaDefinition]:
    result: dict[str, OutputSchemaDefinition] = {}
    for item in document.schemas:
        _require_key_version(item.key, item.version)
        if item.key in result:
            raise ExecutionRegistryReferenceError(
                f"Output Schema Registry 存在重复 key：{item.key}"
            )
        _validate_strict_output_schema(item)
        result[item.key] = OutputSchemaDefinition(
            key=item.key,
            version=item.version,
            supported=item.supported,
            purpose=item.purpose,
            sha256=item.sha256,
            json_schema=cast(Mapping[str, object], _freeze_json(item.jsonSchema)),
        )
    return result


def _step_budgets(
    document: _StepBudgetRegistryDocument,
) -> dict[str, StepBudgetDefinition]:
    result: dict[str, StepBudgetDefinition] = {}
    for item in document.budgets:
        _require_key_version(item.key, item.version)
        if item.key in result:
            raise ExecutionRegistryReferenceError(f"Step Budget Registry 存在重复 key：{item.key}")
        budget = item.budget
        result[item.key] = StepBudgetDefinition(
            key=item.key,
            version=item.version,
            supported=item.supported,
            max_model_calls=budget.maxModelCalls,
            max_input_tokens=budget.maxInputTokens,
            max_prompt_cache_miss_tokens=budget.maxPromptCacheMissTokens,
            max_completion_tokens=budget.maxCompletionTokens,
            max_reasoning_tokens=budget.maxReasoningTokens,
            max_visible_output_tokens=budget.maxVisibleOutputTokens,
            max_cost_micros=budget.maxCostMicros,
            max_wall_clock_seconds=budget.maxWallClockSeconds,
            max_provider_retries=budget.maxProviderRetries,
            max_protocol_corrections=budget.maxProtocolCorrections,
        )
    return result


def _system_purposes(
    document: _SystemPurposeRegistryDocument,
) -> dict[str, SystemPurposeDefinition]:
    result: dict[str, SystemPurposeDefinition] = {}
    for item in document.purposes:
        if item.purpose in result:
            raise ExecutionRegistryReferenceError(
                f"System Purpose Registry 存在重复 purpose：{item.purpose}"
            )
        result[item.purpose] = SystemPurposeDefinition(
            purpose=item.purpose,
            supported=item.supported,
            model_profile_key=item.modelProfile,
            output_schema_key=item.outputSchema,
            evidence_policy=item.evidencePolicy,
            lane=item.lane,
            step_budget_key=item.stepBudgetProfile,
            workflows=tuple(item.workflows),
            parent_operations=tuple(item.parentOperations),
        )
    return result


def _operations(document: _CatalogDocument) -> dict[str, OperationDefinition]:
    result: dict[str, OperationDefinition] = {}
    for item in document.operations:
        if item.key != f"{item.workflow}.{item.operation}":
            raise ExecutionRegistryReferenceError(
                f"Operation key 与 workflow/operation 不一致：{item.key}"
            )
        if item.key in result:
            raise ExecutionRegistryReferenceError(f"Operation Catalog 存在重复 key：{item.key}")
        budget = item.runBudgetProfile
        result[item.key] = OperationDefinition(
            key=item.key,
            workflow=item.workflow,
            operation=item.operation,
            labels=MappingProxyType(dict(item.labels)),
            target_kinds=tuple(item.targetKinds),
            scope_kinds=tuple(item.scopeKinds),
            mutating=item.mutating,
            development_only=item.developmentOnly,
            v2_enabled=item.v2Enabled,
            evidence_policy=item.evidencePolicy,
            generator_profile_key=item.generatorProfile,
            generator_step_budget_key=item.generatorStepBudgetProfile,
            output_schema_key=item.outputSchema,
            deterministic_validators=tuple(item.deterministicValidators),
            review_policy=ReviewPolicy(
                profile=item.reviewPolicy.profile,
                mode=item.reviewPolicy.mode,
                reviewer_profile_keys=tuple(item.reviewPolicy.reviewerProfiles),
                reviewer_step_budget_keys=MappingProxyType(
                    dict(item.reviewPolicy.reviewerStepBudgetProfiles)
                ),
                reviewer_output_schema_key=item.reviewPolicy.reviewerOutputSchema,
                rubric_version=item.reviewPolicy.rubricVersion,
                evidence_policy=item.reviewPolicy.evidencePolicy,
                lane=item.reviewPolicy.lane,
                merge_policy=item.reviewPolicy.mergePolicy,
                max_automatic_revisions=item.reviewPolicy.maxAutomaticRevisions,
                on_unavailable=item.reviewPolicy.onUnavailable,
            ),
            apply_handler=item.applyHandler,
            run_budget=RunBudgetProfile(
                profile=budget.profile,
                max_model_calls=budget.maxModelCalls,
                max_input_tokens=budget.maxInputTokens,
                max_prompt_cache_miss_tokens=budget.maxPromptCacheMissTokens,
                max_completion_tokens=budget.maxCompletionTokens,
                max_reasoning_tokens=budget.maxReasoningTokens,
                max_visible_output_tokens=budget.maxVisibleOutputTokens,
                max_cost_micros=budget.maxCostMicros,
                max_wall_clock_seconds=budget.maxWallClockSeconds,
                max_protocol_correction_steps=budget.maxProtocolCorrectionSteps,
                max_provider_retries_per_step=budget.maxProviderRetriesPerStep,
            ),
            lane=item.lane,
        )
    return result


def _validate_references(
    operations: Mapping[str, OperationDefinition],
    profiles: Mapping[str, ProfileDefinition],
    output_schemas: Mapping[str, OutputSchemaDefinition],
    step_budgets: Mapping[str, StepBudgetDefinition],
    system_purposes: Mapping[str, SystemPurposeDefinition],
) -> None:
    for operation in operations.values():
        profile_keys = (
            operation.generator_profile_key,
            *operation.review_policy.reviewer_profile_keys,
        )
        for profile_key in profile_keys:
            if profile_key not in profiles:
                raise ExecutionRegistryReferenceError(
                    f"Operation {operation.key} 引用了缺失 Profile：{profile_key}"
                )
        if operation.output_schema_key not in output_schemas:
            raise ExecutionRegistryReferenceError(
                f"Operation {operation.key} 引用了缺失 Output Schema：{operation.output_schema_key}"
            )
        _validate_optional_operation_references(
            operation,
            output_schemas=output_schemas,
            step_budgets=step_budgets,
        )
        if not operation.v2_enabled:
            continue
        generator = profiles[operation.generator_profile_key]
        reviewers = [profiles[key] for key in operation.review_policy.reviewer_profile_keys]
        output_schema = output_schemas[operation.output_schema_key]
        generator_budget_key = operation.generator_step_budget_key
        reviewer_schema_key = operation.review_policy.reviewer_output_schema_key
        if generator_budget_key is None:
            raise ExecutionRegistryReferenceError(
                f"启用的 Operation {operation.key} 缺少 Generator Step Budget"
            )
        generator_budget = step_budgets[generator_budget_key]
        review_policy = operation.review_policy
        review_enabled = review_policy.mode != "none"
        if review_enabled:
            if (
                not reviewers
                or set(review_policy.reviewer_step_budget_keys)
                != set(review_policy.reviewer_profile_keys)
                or reviewer_schema_key is None
                or review_policy.rubric_version is None
                or review_policy.evidence_policy is None
                or review_policy.lane is None
            ):
                raise ExecutionRegistryReferenceError(
                    f"启用的 Operation {operation.key} 缺少 Reviewer 执行语义"
                )
        elif (
            reviewers
            or review_policy.reviewer_step_budget_keys
            or reviewer_schema_key is not None
            or review_policy.rubric_version is not None
            or review_policy.evidence_policy is not None
            or review_policy.lane is not None
        ):
            raise ExecutionRegistryReferenceError(
                f"无 Reviewer 的 Operation {operation.key} 不能冻结 Reviewer 执行引用"
            )
        if not generator.supported or generator.purpose not in {
            "generation",
            "evaluation",
            "embedding",
            "media",
        }:
            raise ExecutionRegistryReferenceError(
                f"启用的 Operation {operation.key} 没有可执行 Generator Profile"
            )
        if any(not reviewer.supported or reviewer.purpose != "review" for reviewer in reviewers):
            raise ExecutionRegistryReferenceError(
                f"启用的 Operation {operation.key} 包含不可执行 Reviewer Profile"
            )
        if not output_schema.supported:
            raise ExecutionRegistryReferenceError(
                f"启用的 Operation {operation.key} 使用了未支持 Output Schema"
            )
        if not generator_budget.supported:
            raise ExecutionRegistryReferenceError(
                f"启用的 Operation {operation.key} 使用了未支持 Generator Step Budget"
            )
        if reviewer_schema_key is not None:
            reviewer_schema = output_schemas[reviewer_schema_key]
            if not reviewer_schema.supported or reviewer_schema.purpose != "evaluation":
                raise ExecutionRegistryReferenceError(
                    f"启用的 Operation {operation.key} 没有可执行 Reviewer Output Schema"
                )
        for reviewer in reviewers:
            budget_key = operation.review_policy.reviewer_step_budget_keys[reviewer.key]
            budget = step_budgets[budget_key]
            if not budget.supported:
                raise ExecutionRegistryReferenceError(
                    f"启用的 Operation {operation.key} 使用了未支持 Reviewer Step Budget"
                )
            _validate_profile_budget(reviewer, budget, operation.key)
        _validate_profile_budget(generator, generator_budget, operation.key)
        _validate_step_within_run(operation, generator_budget)
        for budget_key in operation.review_policy.reviewer_step_budget_keys.values():
            _validate_step_within_run(operation, step_budgets[budget_key])

    _validate_system_purpose_references(
        system_purposes,
        profiles=profiles,
        output_schemas=output_schemas,
        step_budgets=step_budgets,
        operations=operations,
    )


def _validate_optional_operation_references(
    operation: OperationDefinition,
    *,
    output_schemas: Mapping[str, OutputSchemaDefinition],
    step_budgets: Mapping[str, StepBudgetDefinition],
) -> None:
    generator_budget_key = operation.generator_step_budget_key
    if generator_budget_key is not None and generator_budget_key not in step_budgets:
        raise ExecutionRegistryReferenceError(
            f"Operation {operation.key} 引用了缺失 Generator Step Budget：{generator_budget_key}"
        )
    review_policy = operation.review_policy
    if set(review_policy.reviewer_step_budget_keys) != set(review_policy.reviewer_profile_keys):
        if review_policy.reviewer_step_budget_keys:
            raise ExecutionRegistryReferenceError(
                f"Operation {operation.key} 的 Reviewer 与 Step Budget 映射不闭合"
            )
    for budget_key in review_policy.reviewer_step_budget_keys.values():
        if budget_key not in step_budgets:
            raise ExecutionRegistryReferenceError(
                f"Operation {operation.key} 引用了缺失 Reviewer Step Budget：{budget_key}"
            )
    reviewer_schema_key = review_policy.reviewer_output_schema_key
    if reviewer_schema_key is not None and reviewer_schema_key not in output_schemas:
        raise ExecutionRegistryReferenceError(
            f"Operation {operation.key} 引用了缺失 Reviewer Output Schema：{reviewer_schema_key}"
        )


def _validate_profile_budget(
    profile: ProfileDefinition,
    budget: StepBudgetDefinition,
    operation_key: str,
) -> None:
    reasoning_enabled = profile.reasoning_mode == "bounded"
    if reasoning_enabled != (budget.max_reasoning_tokens > 0):
        raise ExecutionRegistryReferenceError(
            f"Operation {operation_key} 的 Profile 与 Step reasoning 预算不一致"
        )


def _validate_step_within_run(
    operation: OperationDefinition,
    budget: StepBudgetDefinition,
) -> None:
    run = operation.run_budget
    dimensions = (
        (budget.max_input_tokens, run.max_input_tokens),
        (budget.max_prompt_cache_miss_tokens, run.max_prompt_cache_miss_tokens),
        (budget.max_completion_tokens, run.max_completion_tokens),
        (budget.max_reasoning_tokens, run.max_reasoning_tokens),
        (budget.max_visible_output_tokens, run.max_visible_output_tokens),
        (budget.max_cost_micros, run.max_cost_micros),
        (budget.max_wall_clock_seconds, run.max_wall_clock_seconds),
        (budget.max_provider_retries, run.max_provider_retries_per_step),
    )
    if budget.max_model_calls != 1 or any(step > total for step, total in dimensions):
        raise ExecutionRegistryReferenceError(
            f"Operation {operation.key} 的 Step Budget 超过 Run 总预算"
        )


def _validate_system_purpose_references(
    purposes: Mapping[str, SystemPurposeDefinition],
    *,
    profiles: Mapping[str, ProfileDefinition],
    output_schemas: Mapping[str, OutputSchemaDefinition],
    step_budgets: Mapping[str, StepBudgetDefinition],
    operations: Mapping[str, OperationDefinition],
) -> None:
    for purpose in purposes.values():
        if purpose.model_profile_key not in profiles:
            raise ExecutionRegistryReferenceError(
                f"System Purpose {purpose.purpose} 引用了缺失 Profile"
            )
        if purpose.output_schema_key not in output_schemas:
            raise ExecutionRegistryReferenceError(
                f"System Purpose {purpose.purpose} 引用了缺失 Output Schema"
            )
        if purpose.step_budget_key not in step_budgets:
            raise ExecutionRegistryReferenceError(
                f"System Purpose {purpose.purpose} 引用了缺失 Step Budget"
            )
        if any(operation not in operations for operation in purpose.parent_operations):
            raise ExecutionRegistryReferenceError(
                f"System Purpose {purpose.purpose} 引用了未知父 Operation"
            )
        if purpose.supported and not (
            profiles[purpose.model_profile_key].supported
            and output_schemas[purpose.output_schema_key].supported
            and step_budgets[purpose.step_budget_key].supported
        ):
            raise ExecutionRegistryReferenceError(
                f"启用的 System Purpose {purpose.purpose} 依赖尚未完整实现"
            )


def _validate_strict_output_schema(item: _OutputSchemaDocument) -> None:
    schema = item.jsonSchema
    properties = schema.get("properties")
    required = schema.get("required")
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or not isinstance(properties, dict)
        or not isinstance(required, list)
        or set(required) != set(properties)
    ):
        raise ExecutionRegistryReferenceError(f"Output Schema 不是严格闭合对象：{item.key}")
    if canonical_execution_sha256(schema) != item.sha256:
        raise ExecutionRegistryHashError(f"Output Schema canonical 哈希不一致：{item.key}")
    try:
        jsonschema_rs.validator_for(schema)
    except Exception as exc:
        raise ExecutionRegistryReferenceError(f"Output Schema 无法编译：{item.key}") from exc
    if not item.supported and (properties or required):
        raise ExecutionRegistryReferenceError(
            f"未支持 Output Schema 不能携带伪装可执行的业务字段：{item.key}"
        )


def _validate_json_schema(schema: dict[str, object], value: dict[str, object], label: str) -> None:
    try:
        jsonschema_rs.validator_for(schema).validate(value)
    except Exception as exc:
        raise ExecutionRegistryError(f"{label} 不符合固定 JSON Schema") from exc


def _parse_model[ModelT: BaseModel](model: type[ModelT], value: object, label: str) -> ModelT:
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise ExecutionRegistryError(f"{label} 结构无效") from exc


def _require_key_version(key: str, version: int) -> None:
    if not key.endswith(f".v{version}"):
        raise ExecutionRegistryReferenceError(f"Registry key 与 version 不一致：{key}")


def _require_versioned_identifier(value: str, field: str) -> None:
    prefix, separator, version_text = value.rpartition(".v")
    if (
        not separator
        or not prefix
        or not version_text.isdigit()
        or int(version_text) < 1
    ):
        raise ExecutionRegistryReferenceError(f"{field} 必须是正版本标识：{value}")


def _freeze_json(value: JsonValue) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return cast(JsonValue, value)


def _safe_contract_path(root: Path, filename: str) -> Path:
    if Path(filename).name != filename:
        raise ExecutionRegistryError("Manifest contract 路径只能是固定文件名")
    path = (root / filename).resolve()
    if path.parent != root.resolve():
        raise ExecutionRegistryError("Manifest contract 路径越界")
    return path


def _read_bytes(path: Path) -> bytes:
    try:
        size = path.stat().st_size
        if size > _MAX_CONTRACT_FILE_BYTES:
            raise ExecutionRegistryError(f"V2 execution contract 文件过大：{path.name}")
        return path.read_bytes()
    except OSError as exc:
        raise ExecutionRegistryError(f"无法读取 V2 execution contract：{path.name}") from exc


def _read_json(path: Path) -> dict[str, object]:
    return _decode_json(_read_bytes(path), path.name)


def _decode_json(raw: bytes, label: str) -> dict[str, object]:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ExecutionRegistryError(f"V2 execution contract 存在重复 JSON key：{label}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionRegistryError(f"V2 execution contract 不是有效 UTF-8 JSON：{label}") from exc
    if not isinstance(value, dict):
        raise ExecutionRegistryError(f"V2 execution contract 根节点必须是对象：{label}")
    return cast(dict[str, object], value)
