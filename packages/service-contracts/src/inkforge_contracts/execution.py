"""Core 权威耐久执行器的 V2 服务间协议。"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

EXECUTION_PROTOCOL_VERSION = "2.0"
EXECUTION_HASH_ALGORITHM = "inkforge-canonical-json/1"
EXECUTION_CALLBACK_HTTP_METHOD = "PUT"
EXECUTION_CALLBACK_RECEIPT_HTTP_STATUS = 200
EXECUTION_CALLBACK_STOP_RETRY_STATUSES = frozenset(
    {"accepted", "duplicate", "superseded"}
)

ExecutionId = Annotated[
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
NonBlankText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]
StrictNonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
StrictNonNegativeLong = Annotated[
    int,
    Field(
        strict=True,
        ge=0,
        le=9_000_000_000_000_000_000,
        json_schema_extra={"format": "int64"},
    ),
]
BudgetPositiveTokens = Annotated[int, Field(strict=True, gt=0, le=10_000_000)]
BudgetNonNegativeTokens = Annotated[int, Field(strict=True, ge=0, le=10_000_000)]
BudgetCostMicros = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)]
BudgetWallClockSeconds = Annotated[int, Field(strict=True, gt=0, le=86_400)]
Confidence = Annotated[float, Field(strict=True, ge=0, le=1)]
type ExecutionCallbackKind = Literal["progress", "result", "failure"]

_EXECUTION_ID_ADAPTER = TypeAdapter(ExecutionId)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _canonical_number(value: int | float | Decimal) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("执行哈希不允许 NaN 或 Infinity")
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError("执行哈希不允许 NaN 或 Infinity")
    if decimal.is_zero():
        return "0"
    return format(decimal.normalize(), "f")


def _canonical_json_text(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float, Decimal)):
        return _canonical_number(value)
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("执行哈希不允许未配对的 Unicode 代理字符")
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json_text(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("执行哈希 JSON 对象 key 必须是字符串")
        entries = (
            f"{_canonical_json_text(key)}:{_canonical_json_text(value[key])}"
            for key in sorted(value)
        )
        return "{" + ",".join(entries) + "}"
    raise TypeError(f"执行哈希不支持类型：{type(value).__name__}")


def canonical_execution_json_bytes(value: object) -> bytes:
    """按 `inkforge-canonical-json/1` 生成跨语言稳定字节。"""

    return _canonical_json_text(value).encode("utf-8")


def canonical_execution_sha256(value: object) -> str:
    return _sha256(canonical_execution_json_bytes(value))


def _canonical_model_value(value: BaseModel) -> dict[str, object]:
    return value.model_dump(mode="json", by_alias=True, exclude_none=True)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_forbidden_diagnostic(value: JsonValue) -> bool:
    forbidden_keys = {
        "chainofthought",
        "cot",
        "logs",
        "providerresponse",
        "rawlog",
        "rawproviderresponse",
        "reasoning",
        "reasoningcontent",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in forbidden_keys or _contains_forbidden_diagnostic(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_diagnostic(item) for item in value)
    return False


class EvidenceRange(_StrictModel):
    """以 Unicode 码点计数的半开区间。"""

    startCodePoint: StrictNonNegativeInt
    endCodePoint: StrictPositiveInt

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.endCodePoint <= self.startCodePoint:
            raise ValueError("证据区间终点必须大于起点")
        return self


class EvidenceItem(_StrictModel):
    id: ExecutionId
    bundleId: ExecutionId
    ordinal: StrictPositiveInt
    resourceType: ProtocolCode
    resourceId: ExecutionId
    exists: StrictBool
    resourceRevision: StrictPositiveInt | None = None
    resourceUpdatedAt: AwareDatetime | None = None
    contentType: Literal["text", "json"] | None = None
    contentText: str | None = None
    contentJson: JsonValue | None = None
    contentSha256: Sha256 | None = None
    byteCount: StrictNonNegativeInt
    range: EvidenceRange | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        if not self.exists:
            if any(
                value is not None
                for value in (
                    self.resourceRevision,
                    self.resourceUpdatedAt,
                    self.contentType,
                    self.contentText,
                    self.contentJson,
                    self.contentSha256,
                    self.range,
                )
            ):
                raise ValueError("不存在的证据资源不能包含版本、时间、内容、哈希或范围")
            if self.byteCount != 0:
                raise ValueError("不存在的证据资源 byteCount 必须为 0")
            return self

        has_text = self.contentText is not None
        has_json = self.contentJson is not None
        if has_text == has_json:
            raise ValueError("证据项必须且只能包含 text 或 JSON 内容之一")
        if self.contentType is None or self.contentSha256 is None:
            raise ValueError("存在的证据资源必须包含内容类型与内容哈希")
        if self.contentType == "text" and not has_text:
            raise ValueError("text 证据必须使用 contentText")
        if self.contentType == "json" and not has_json:
            raise ValueError("json 证据必须使用 contentJson")

        encoded = (
            self.contentText.encode("utf-8")
            if self.contentText is not None
            else canonical_execution_json_bytes(self.contentJson)
        )
        if len(encoded) != self.byteCount:
            raise ValueError("证据项 byteCount 与完整内容不一致")
        if _sha256(encoded) != self.contentSha256:
            raise ValueError("证据项 contentSha256 与完整内容不一致")
        return self


class EvidenceManifestItem(_StrictModel):
    itemId: ExecutionId
    ordinal: StrictPositiveInt
    resourceType: ProtocolCode
    resourceId: ExecutionId
    exists: StrictBool
    resourceRevision: StrictPositiveInt | None = None
    resourceUpdatedAt: AwareDatetime | None = None
    contentType: Literal["text", "json"] | None = None
    contentSha256: Sha256 | None = None
    byteCount: StrictNonNegativeInt
    range: EvidenceRange | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceManifest(_StrictModel):
    bundleId: ExecutionId
    bundleVersion: StrictPositiveInt
    itemCount: StrictPositiveInt
    items: list[EvidenceManifestItem] = Field(min_length=1, max_length=4_096)

    @model_validator(mode="after")
    def validate_item_count(self) -> Self:
        if self.itemCount != len(self.items):
            raise ValueError("证据 manifest 的 itemCount 与 items 不一致")
        return self


class EvidenceBundle(_StrictModel):
    id: ExecutionId
    runId: ExecutionId
    version: StrictPositiveInt
    policyVersion: ProtocolCode = Field(
        description=(
            "本 Step 对同一不可变 bundle 的授权视图；generation 使用捕获策略，"
            "review 可使用 Catalog 固定的 reviewer evidence policy，bundle id/items/manifest 不变"
        )
    )
    manifest: EvidenceManifest
    manifestSha256: Sha256
    totalBytes: StrictNonNegativeInt
    items: list[EvidenceItem] = Field(min_length=1, max_length=4_096)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.manifest.bundleId != self.id or self.manifest.bundleVersion != self.version:
            raise ValueError("证据 manifest 未绑定当前 bundle 及版本")

        expected_ordinals = list(range(1, len(self.items) + 1))
        actual_ordinals = [item.ordinal for item in self.items]
        if actual_ordinals != expected_ordinals:
            raise ValueError("证据项 ordinal 必须从 1 开始连续且按序排列")
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("同一证据 bundle 不能包含重复 item ID")
        if any(item.bundleId != self.id for item in self.items):
            raise ValueError("证据项必须绑定当前 bundle")

        expected_manifest_items = [
            EvidenceManifestItem(
                itemId=item.id,
                ordinal=item.ordinal,
                resourceType=item.resourceType,
                resourceId=item.resourceId,
                exists=item.exists,
                resourceRevision=item.resourceRevision,
                resourceUpdatedAt=item.resourceUpdatedAt,
                contentType=item.contentType,
                contentSha256=item.contentSha256,
                byteCount=item.byteCount,
                range=item.range,
                metadata=item.metadata,
            )
            for item in self.items
        ]
        if self.manifest.items != expected_manifest_items:
            raise ValueError("证据 manifest 与完整 items 不一致")
        if self.totalBytes != sum(item.byteCount for item in self.items):
            raise ValueError("证据 bundle totalBytes 与完整 items 不一致")

        manifest_bytes = canonical_execution_json_bytes(_canonical_model_value(self.manifest))
        if self.manifestSha256 != _sha256(manifest_bytes):
            raise ValueError("证据 manifestSha256 与 manifest 不一致")
        return self


class StepBudget(_StrictModel):
    """一个耐久 Step 的完整、不可隐式扩张的执行预算。"""

    maxModelCalls: Literal[1]
    maxInputTokens: BudgetPositiveTokens
    maxPromptCacheMissTokens: BudgetPositiveTokens
    maxCompletionTokens: BudgetNonNegativeTokens
    maxReasoningTokens: BudgetNonNegativeTokens
    maxVisibleOutputTokens: BudgetNonNegativeTokens
    maxCostMicros: BudgetCostMicros
    maxWallClockSeconds: BudgetWallClockSeconds
    maxProviderRetries: StrictNonNegativeInt = Field(
        le=2,
        description="当前单 Step 内的供应商重试上限；不是 RunBudget catalog 字段",
    )
    maxProtocolCorrections: StrictNonNegativeInt = Field(le=1)

    @model_validator(mode="after")
    def validate_token_budget(self) -> Self:
        if self.maxPromptCacheMissTokens > self.maxInputTokens:
            raise ValueError("cache miss token 预算不能超过总输入 token 预算")
        if self.maxReasoningTokens + self.maxVisibleOutputTokens > self.maxCompletionTokens:
            raise ValueError("reasoning 与可见输出 token 预算之和不能超过 completion 预算")
        return self


class PromptProfileRef(_StrictModel):
    """Manifest 管理的静态 system prompt 身份；正文由双端 Registry 按哈希校验。"""

    name: ProtocolCode
    version: StrictPositiveInt
    sha256: Sha256

    @model_validator(mode="after")
    def validate_versioned_name(self) -> Self:
        if not self.name.endswith(f".v{self.version}"):
            raise ValueError("Prompt Profile name 与 version 不一致")
        return self


class ModelProfileRef(_StrictModel):
    """Core 授权的逻辑模型 Profile；不包含 Agent 部署配置。"""

    profile: ProtocolCode
    version: StrictPositiveInt
    reasoningMode: Literal["disabled", "bounded"]
    deploymentProfileKey: ProtocolCode
    promptProfile: PromptProfileRef


def calculate_resolved_model_fingerprint(
    *,
    deployment_profile_key: str,
    provider: str,
    model: str,
    transport_profile: str,
    endpoint_profile: str,
    structured_output_route: str,
    capability_version: str,
    reasoning_mode: str,
    supports_request_idempotency: bool,
) -> str:
    """按部署、模型、传输适配器、结构化能力与幂等事实计算无密钥指纹。"""

    return canonical_execution_sha256(
        {
            "deploymentProfileKey": deployment_profile_key,
            "provider": provider,
            "model": model,
            "transportProfile": transport_profile,
            "endpointProfile": endpoint_profile,
            "structuredOutputRoute": structured_output_route,
            "capabilityVersion": capability_version,
            "reasoningMode": reasoning_mode,
            "supportsRequestIdempotency": supports_request_idempotency,
        }
    )


class ResolvedModelRef(_StrictModel):
    """Agent 对逻辑 Profile 的一次可审计部署解析。"""

    deploymentProfileKey: ProtocolCode
    deploymentFingerprint: Sha256
    provider: ProtocolCode
    model: NonBlankText
    transportProfile: ProtocolCode
    endpointProfile: ProtocolCode
    structuredOutputRoute: Literal[
        "responses_json_schema_v1",
        "chat_json_output_v1",
    ]
    capabilityVersion: ProtocolCode
    reasoningMode: Literal["disabled", "bounded"]
    supportsRequestIdempotency: StrictBool = Field(
        description="仅当 Provider 确实原样传递 ExecutionStepRequest.idempotencyKey 时为 true"
    )

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Self:
        expected = calculate_resolved_model_fingerprint(
            deployment_profile_key=self.deploymentProfileKey,
            provider=self.provider,
            model=self.model,
            transport_profile=self.transportProfile,
            endpoint_profile=self.endpointProfile,
            structured_output_route=self.structuredOutputRoute,
            capability_version=self.capabilityVersion,
            reasoning_mode=self.reasoningMode,
            supports_request_idempotency=self.supportsRequestIdempotency,
        )
        if self.deploymentFingerprint != expected:
            raise ValueError("deploymentFingerprint 与规范部署模型材料不一致")
        return self


def _validate_logical_and_resolved_model(
    logical: ModelProfileRef,
    resolved: ResolvedModelRef,
) -> None:
    if logical.deploymentProfileKey != resolved.deploymentProfileKey:
        raise ValueError("逻辑 Profile 与解析模型的 deploymentProfileKey 不一致")
    if logical.reasoningMode != resolved.reasoningMode:
        raise ValueError("逻辑 Profile 与解析模型的 reasoningMode 不一致")


class OutputSchemaRef(_StrictModel):
    name: ProtocolCode
    version: StrictPositiveInt
    sha256: Sha256
    jsonSchema: dict[str, JsonValue] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schema_hash(self) -> Self:
        if self.sha256 != canonical_execution_sha256(self.jsonSchema):
            raise ValueError("输出 jsonSchema 的 canonical SHA-256 不一致")
        return self


class ChatAnswerInput(_StrictModel):
    """`long_serial.answer_question` 冻结到通用 Step input 的完整任务。"""

    userInstruction: Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]

    @model_validator(mode="after")
    def validate_non_blank_instruction(self) -> Self:
        if not self.userInstruction.strip():
            raise ValueError("长篇问答指令不能是空白文本")
        return self


class ChatAnswerOutput(_StrictModel):
    """只读问答 Step 的严格语义结果；保留原始段落与换行。"""

    answer: Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]

    @model_validator(mode="after")
    def validate_non_blank_answer(self) -> Self:
        if not self.answer.strip():
            raise ValueError("长篇问答结果不能是空白文本")
        return self


class StepUsage(_StrictModel):
    usageStatus: Literal["complete", "partial", "unknown"]
    providerAttempts: StrictNonNegativeInt = Field(le=3)
    protocolCorrections: StrictNonNegativeInt = Field(le=1)
    wallTimeMillis: StrictNonNegativeInt
    inputTokens: StrictNonNegativeInt | None = None
    cachedTokens: StrictNonNegativeInt | None = None
    promptCacheMissTokens: StrictNonNegativeInt | None = None
    completionTokens: StrictNonNegativeInt | None = None
    reasoningTokens: StrictNonNegativeInt | None = None
    visibleOutputTokens: StrictNonNegativeInt | None = None
    costMicros: StrictNonNegativeInt | None = None

    @model_validator(mode="after")
    def validate_token_accounting(self) -> Self:
        provider_fields = (
            self.inputTokens,
            self.cachedTokens,
            self.promptCacheMissTokens,
            self.completionTokens,
            self.reasoningTokens,
            self.visibleOutputTokens,
            self.costMicros,
        )
        known_count = sum(value is not None for value in provider_fields)
        if self.providerAttempts == 0 and (
            self.usageStatus != "unknown"
            or known_count != 0
            or self.protocolCorrections != 0
        ):
            raise ValueError(
                "零供应商尝试必须使用 unknown usage，且不能携带供应商字段或协议纠正"
            )
        if self.usageStatus == "complete" and known_count != len(provider_fields):
            raise ValueError("complete usage 必须包含全部 token 与金额字段")
        if self.usageStatus == "partial" and known_count in {0, len(provider_fields)}:
            raise ValueError("partial usage 必须且只能包含部分 token 或金额字段")
        if self.usageStatus == "unknown" and known_count != 0:
            raise ValueError("unknown usage 不能伪装任何供应商 token 或金额事实")

        input_tokens = self.inputTokens
        cached_tokens = self.cachedTokens
        cache_miss_tokens = self.promptCacheMissTokens
        if input_tokens is not None and cached_tokens is not None and cache_miss_tokens is not None:
            if cached_tokens + cache_miss_tokens != input_tokens:
                raise ValueError("cachedTokens + promptCacheMissTokens 必须等于 inputTokens")
        completion_tokens = self.completionTokens
        reasoning_tokens = self.reasoningTokens
        visible_tokens = self.visibleOutputTokens
        if (
            completion_tokens is not None
            and reasoning_tokens is not None
            and visible_tokens is not None
        ):
            if reasoning_tokens + visible_tokens != completion_tokens:
                raise ValueError("reasoningTokens + visibleOutputTokens 必须等于 completionTokens")
        return self


class BillingReconciliationRequest(_StrictModel):
    """供应商账单证据驱动的 V2 预留对账命令。"""

    protocolVersion: Literal["2.0"]
    reconciliationId: ExecutionId
    runId: ExecutionId
    novelId: ExecutionId | None
    stepId: ExecutionId
    reservationRequestId: ExecutionId
    supplierEvidenceRef: NonBlankText
    supplierReportSha256: Sha256
    decision: Literal["exact_usage", "proven_zero"]
    usage: StepUsage

    @model_validator(mode="after")
    def validate_decision_usage(self) -> Self:
        if self.decision == "exact_usage":
            if self.usage.usageStatus != "complete":
                raise ValueError("exact_usage 对账必须携带 complete usage")
            if self.usage.providerAttempts == 0:
                raise ValueError("exact_usage 对账必须证明至少一次供应商调用")
            return self
        if self.usage.providerAttempts != 0 or self.usage.usageStatus != "unknown":
            raise ValueError("proven_zero 对账必须携带零供应商尝试的 unknown usage")
        return self


class BillingReconciliationReceipt(_StrictModel):
    """对账结算回执；duplicate 不得暗示再次扣费。"""

    protocolVersion: Literal["2.0"]
    reconciliationId: ExecutionId
    reservationRequestId: ExecutionId
    decision: Literal["exact_usage", "proven_zero"]
    reservationStatus: Literal["settled", "released"]
    chargedMicros: StrictNonNegativeLong
    balanceAfterMicros: StrictNonNegativeLong
    settledAt: AwareDatetime
    duplicate: StrictBool


class ExecutionCancelRequest(_StrictModel):
    protocolVersion: Literal["2.0"]
    cancelRequestId: ExecutionId
    runId: ExecutionId
    novelId: ExecutionId | None
    stepId: ExecutionId
    jobId: ExecutionId
    fencingToken: StrictPositiveInt
    requestHash: Sha256
    requestedAt: AwareDatetime


class ExecutionCancelAccepted(_StrictModel):
    protocolVersion: Literal["2.0"]
    cancelRequestId: ExecutionId
    runId: ExecutionId
    novelId: ExecutionId | None
    stepId: ExecutionId
    jobId: ExecutionId
    fencingToken: StrictPositiveInt
    status: Literal["accepted", "already_cancelled", "already_terminal", "not_found"]
    acceptedAt: AwareDatetime


class ExecutionStepRequest(_StrictModel):
    protocolVersion: Literal["2.0"]
    jobId: ExecutionId
    runId: ExecutionId
    novelId: ExecutionId | None
    stepId: ExecutionId
    fencingToken: StrictPositiveInt
    dispatchMode: Literal["initial", "pending_recovery", "running_recovery"] = Field(
        description=(
            "transport/fencing 事实，不进入 requestHash；running_recovery 缺 journal 时必须"
            " MODEL_OUTCOME_UNKNOWN"
        )
    )
    idempotencyKey: ExecutionId = Field(
        description="Agent 必须把此键原样传给声明支持请求幂等的供应商"
    )
    requestHash: Sha256
    inputHash: Sha256
    input: dict[str, JsonValue]
    workflow: ProtocolCode
    operation: ProtocolCode
    purpose: ProtocolCode
    lane: Literal["interactive", "creative", "batch_media"]
    evidenceBundle: EvidenceBundle
    modelProfile: ModelProfileRef
    outputSchema: OutputSchemaRef
    budget: StepBudget
    artifactId: ExecutionId | None = None
    artifactRevision: StrictPositiveInt | None = None
    submittedAt: AwareDatetime

    def _request_hash_payload(self) -> dict[str, object]:
        artifact: dict[str, object] | None = None
        if self.artifactId is not None and self.artifactRevision is not None:
            artifact = {
                "artifactId": self.artifactId,
                "artifactRevision": self.artifactRevision,
            }
        return {
            "runId": self.runId,
            "novelId": self.novelId,
            "stepId": self.stepId,
            "idempotencyKey": self.idempotencyKey,
            "inputHash": self.inputHash,
            "workflow": self.workflow,
            "operation": self.operation,
            "purpose": self.purpose,
            "lane": self.lane,
            "evidenceManifest": {
                "bundleId": self.evidenceBundle.id,
                "bundleVersion": self.evidenceBundle.version,
                "policyVersion": self.evidenceBundle.policyVersion,
                "manifestSha256": self.evidenceBundle.manifestSha256,
            },
            "modelProfile": _canonical_model_value(self.modelProfile),
            "outputSchema": _canonical_model_value(self.outputSchema),
            "budget": _canonical_model_value(self.budget),
            "artifact": artifact,
        }

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.evidenceBundle.runId != self.runId:
            raise ValueError("执行 Step 与 Evidence bundle 必须属于同一 Run")
        if (self.artifactId is None) != (self.artifactRevision is None):
            raise ValueError("artifactId 与 artifactRevision 必须同时提供或同时省略")
        if self.modelProfile.reasoningMode == "disabled":
            if self.budget.maxReasoningTokens != 0:
                raise ValueError("关闭 reasoning 的 Profile 必须使用零 reasoning 预算")
        elif self.budget.maxReasoningTokens == 0:
            raise ValueError("bounded reasoning Profile 必须具有正 reasoning 预算")
        if self.inputHash != canonical_execution_sha256(self.input):
            raise ValueError("inputHash 与完整 canonical input 不一致")
        if self.requestHash != canonical_execution_sha256(self._request_hash_payload()):
            raise ValueError("requestHash 与稳定执行请求材料不一致")
        return self


class ExecutionStepAccepted(_StrictModel):
    protocolVersion: Literal["2.0"]
    jobId: ExecutionId
    runId: ExecutionId
    novelId: ExecutionId | None
    stepId: ExecutionId
    fencingToken: StrictPositiveInt
    requestHash: Sha256
    resolvedModel: ResolvedModelRef
    status: Literal["accepted", "queued"]
    acceptedAt: AwareDatetime


class ExecutionStepProgress(_StrictModel):
    protocolVersion: Literal["2.0"]
    progressId: ExecutionId
    jobId: ExecutionId
    runId: ExecutionId
    novelId: ExecutionId | None
    stepId: ExecutionId
    fencingToken: StrictPositiveInt
    requestHash: Sha256
    resolvedModel: ResolvedModelRef
    sequence: StrictPositiveInt
    phase: Literal["preparing", "waiting_provider", "validating", "reporting"]
    progressCode: ProtocolCode
    elapsedSeconds: StrictNonNegativeInt
    waitingOnProvider: StrictBool
    usage: StepUsage
    occurredAt: AwareDatetime

    @model_validator(mode="after")
    def validate_provider_phase(self) -> Self:
        if self.waitingOnProvider != (self.phase == "waiting_provider"):
            raise ValueError("waitingOnProvider 必须与 waiting_provider 阶段一致")
        return self


class EvidenceExpansionItem(_StrictModel):
    resourceType: ProtocolCode
    resourceId: ExecutionId
    range: EvidenceRange | None = None
    purposeCode: ProtocolCode


class EvidenceExpansionRequest(_StrictModel):
    requestId: ExecutionId
    sourceBundleId: ExecutionId
    sourceBundleVersion: StrictPositiveInt
    reasonCode: ProtocolCode
    maxAdditionalBytes: StrictPositiveInt
    items: list[EvidenceExpansionItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_items(self) -> Self:
        identities = [
            (
                item.resourceType,
                item.resourceId,
                None
                if item.range is None
                else (item.range.startCodePoint, item.range.endCodePoint),
            )
            for item in self.items
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("证据扩展请求不能包含重复资源范围")
        return self


class CommandClarification(_StrictModel):
    code: ProtocolCode
    prompt: NonBlankText


class ProposedCommand(_StrictModel):
    workflow: ProtocolCode | None = None
    operation: ProtocolCode | None = None
    targetType: ProtocolCode | None = None
    targetId: ExecutionId | None = None
    scopeKind: ProtocolCode | None = None
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    confidence: Confidence
    clarification: CommandClarification | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if (self.workflow is None) != (self.operation is None):
            raise ValueError("workflow 与 operation 必须同时提供或同时省略")
        if (self.targetType is None) != (self.targetId is None):
            raise ValueError("targetType 与 targetId 必须同时提供或同时省略")

        resolved = self.workflow is not None
        if resolved == (self.clarification is not None):
            raise ValueError("ProposedCommand 必须且只能包含已解析命令或澄清请求")
        if not resolved and any(
            value is not None for value in (self.targetType, self.targetId, self.scopeKind)
        ):
            raise ValueError("澄清请求不能夹带目标或范围")
        if not resolved and self.arguments:
            raise ValueError("澄清请求不能夹带命令参数")
        return self


class EvaluationEvidenceReference(_StrictModel):
    evidenceItemId: ExecutionId
    contentSha256: Sha256
    range: EvidenceRange | None = None


class EvaluationFinding(_StrictModel):
    dimension: ProtocolCode
    severity: Literal["info", "warning", "error"]
    claim: NonBlankText
    candidateRange: EvidenceRange | None = None
    evidence: list[EvaluationEvidenceReference] = Field(min_length=1, max_length=50)
    suggestion: NonBlankText
    confidence: Confidence


class EvidenceEvaluation(_StrictModel):
    evaluationId: ExecutionId
    runId: ExecutionId
    stepId: ExecutionId
    evidenceBundleId: ExecutionId
    artifactId: ExecutionId | None = None
    artifactRevision: StrictPositiveInt | None = None
    evaluatorProfile: ModelProfileRef
    resolvedModel: ResolvedModelRef
    rubricVersion: ProtocolCode
    executionStatus: Literal["completed", "incomplete", "failed"]
    contentVerdict: Literal["pass", "issues_found", "cannot_assess"]
    findings: list[EvaluationFinding] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        _validate_logical_and_resolved_model(self.evaluatorProfile, self.resolvedModel)
        if (self.artifactId is None) != (self.artifactRevision is None):
            raise ValueError("Evaluation 的 artifactId 与 revision 必须成对提供")
        if self.executionStatus != "completed":
            if self.contentVerdict != "cannot_assess" or self.findings:
                raise ValueError("未完成的评审不能生成内容结论或 findings")
            return self
        if self.contentVerdict == "pass" and self.findings:
            raise ValueError("pass 评审不能包含 findings")
        if self.contentVerdict == "issues_found" and not self.findings:
            raise ValueError("issues_found 评审必须包含证据化 findings")
        if self.contentVerdict == "cannot_assess" and self.findings:
            raise ValueError("cannot_assess 评审不能包含 findings")
        return self


class ExecutionStepResult(_StrictModel):
    protocolVersion: Literal["2.0"]
    jobId: ExecutionId
    runId: ExecutionId
    novelId: ExecutionId | None
    stepId: ExecutionId
    fencingToken: StrictPositiveInt
    requestHash: Sha256
    inputHash: Sha256
    resolvedModel: ResolvedModelRef
    resultKind: Literal["output", "evidence_expansion", "proposed_command", "evaluation"]
    output: dict[str, JsonValue] | None = None
    evidenceExpansion: EvidenceExpansionRequest | None = None
    proposedCommand: ProposedCommand | None = None
    evaluation: EvidenceEvaluation | None = None
    resultHash: Sha256
    usage: StepUsage
    completedAt: AwareDatetime

    def _selected_result(self) -> tuple[str, object]:
        branches: dict[str, object | None] = {
            "output": self.output,
            "evidence_expansion": self.evidenceExpansion,
            "proposed_command": self.proposedCommand,
            "evaluation": self.evaluation,
        }
        selected = [(kind, value) for kind, value in branches.items() if value is not None]
        if len(selected) != 1:
            raise ValueError("执行结果必须且只能包含一个结果分支")
        return selected[0]

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        selected_kind, selected_value = self._selected_result()
        if selected_kind != self.resultKind:
            raise ValueError("resultKind 与实际结果分支不一致")

        if isinstance(selected_value, BaseModel):
            canonical_value: object = _canonical_model_value(selected_value)
        else:
            canonical_value = selected_value
        hash_payload = {
            "resultKind": selected_kind,
            "resolvedModel": _canonical_model_value(self.resolvedModel),
            "usage": _canonical_model_value(self.usage),
            "value": canonical_value,
        }
        if self.resultHash != canonical_execution_sha256(hash_payload):
            raise ValueError("resultHash 与完整结构化结果不一致")

        if self.output is not None and _contains_forbidden_diagnostic(self.output):
            raise ValueError("执行结果不能包含日志、供应商原文或 reasoning 原文")
        if self.evaluation is not None:
            if self.evaluation.runId != self.runId or self.evaluation.stepId != self.stepId:
                raise ValueError("Evaluation 必须绑定当前 Run 与 Step")
            if self.evaluation.resolvedModel != self.resolvedModel:
                raise ValueError("Evaluation 与执行结果必须携带同一解析模型")
        return self


class ExecutionStepFailure(_StrictModel):
    protocolVersion: Literal["2.0"]
    jobId: ExecutionId
    runId: ExecutionId
    novelId: ExecutionId | None
    stepId: ExecutionId
    fencingToken: StrictPositiveInt
    requestHash: Sha256
    inputHash: Sha256
    resolvedModel: ResolvedModelRef
    errorCategory: Literal[
        "provider_transient",
        "provider_terminal",
        "protocol",
        "validation",
        "model_outcome_unknown",
        "cancelled",
        "internal",
    ]
    errorCode: ErrorCode
    retryable: StrictBool
    outcomeUnknown: StrictBool
    cancelRequestId: ExecutionId | None = None
    resultHash: Sha256
    usage: StepUsage
    failedAt: AwareDatetime

    @model_validator(mode="after")
    def validate_failure(self) -> Self:
        is_unknown = self.errorCategory == "model_outcome_unknown"
        if self.outcomeUnknown != is_unknown:
            raise ValueError("outcomeUnknown 必须只用于 MODEL_OUTCOME_UNKNOWN")
        if self.outcomeUnknown and self.retryable:
            raise ValueError("结果未知时禁止盲目重试")
        if self.retryable and self.errorCategory not in {"provider_transient", "internal"}:
            raise ValueError("只有明确的暂态供应商或内部故障可以标记 retryable")
        if (self.errorCategory == "cancelled") != (self.cancelRequestId is not None):
            raise ValueError("cancelled 失败必须且只能绑定 cancelRequestId")

        hash_payload: dict[str, object] = {
            "errorCategory": self.errorCategory,
            "errorCode": self.errorCode,
            "outcomeUnknown": self.outcomeUnknown,
            "retryable": self.retryable,
            "resolvedModel": _canonical_model_value(self.resolvedModel),
            "usage": _canonical_model_value(self.usage),
        }
        if self.cancelRequestId is not None:
            hash_payload["cancelRequestId"] = self.cancelRequestId
        if self.resultHash != canonical_execution_sha256(hash_payload):
            raise ValueError("失败 resultHash 与结构化错误及 usage 不一致")
        return self


class ExecutionCallbackReceipt(_StrictModel):
    """Core 的回调收据；stale 保留终态，其他状态确认无需再投递。"""

    protocolVersion: Literal["2.0"]
    runId: ExecutionId
    stepId: ExecutionId
    jobId: ExecutionId
    fencingToken: StrictPositiveInt
    requestHash: Sha256
    status: Literal["accepted", "duplicate", "stale", "superseded"]
    receivedAt: AwareDatetime


def execution_callback_path(
    *,
    run_id: str,
    step_id: str,
    callback_kind: ExecutionCallbackKind,
) -> str:
    """返回 V2 progress/result/failure 的唯一内部 PUT 路径。"""

    validated_run_id = _EXECUTION_ID_ADAPTER.validate_python(run_id)
    validated_step_id = _EXECUTION_ID_ADAPTER.validate_python(step_id)
    if callback_kind not in {"progress", "result", "failure"}:
        raise ValueError("未知 Execution callback 类型")
    return (
        f"/internal/v1/workflow-runs/{validated_run_id}/steps/"
        f"{validated_step_id}/{callback_kind}"
    )
