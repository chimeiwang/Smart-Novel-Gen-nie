from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from inkforge_agents.execution.registry import ExecutionRegistry
from inkforge_contracts.execution import (
    EvidenceBundle,
    EvidenceItem,
    EvidenceManifest,
    EvidenceManifestItem,
    ExecutionCancelRequest,
    ExecutionStepRequest,
    ExecutionStepResult,
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    ResolvedModelRef,
    StepBudget,
    StepUsage,
    calculate_resolved_model_fingerprint,
    canonical_execution_sha256,
)
from pydantic import JsonValue


def execution_request(
    *,
    job_id: str = "job-1",
    fencing_token: int = 1,
    dispatch_mode: Literal["initial", "pending_recovery", "running_recovery"] = "initial",
    input_value: dict[str, Any] | None = None,
) -> ExecutionStepRequest:
    run_id = "run-1"
    step_id = "step-1"
    input_data = input_value or {
        "instruction": "在不改变事实的前提下改写选区",
        "selectionStart": 0,
        "selectionEnd": 4,
    }
    evidence = _evidence(run_id)
    profile = ModelProfileRef(
        profile="writer.chapter_selection.v1",
        version=1,
        reasoningMode="bounded",
        deploymentProfileKey="deployment.writer.chapter_selection.v1",
        promptProfile=PromptProfileRef(
            name="prompt.writer.chapter_selection.v1",
            version=1,
            sha256="1b890ddc344c96680dc241d4f869f95e244a92a4e6e0a51a975a51e1c02bc9af",
        ),
    )
    schema = _generator_schema()
    budget = StepBudget(
        maxModelCalls=1,
        maxInputTokens=30_000,
        maxPromptCacheMissTokens=10_000,
        maxCompletionTokens=8_000,
        maxReasoningTokens=4_000,
        maxVisibleOutputTokens=4_000,
        maxCostMicros=300_000,
        maxWallClockSeconds=120,
        maxProviderRetries=2,
        maxProtocolCorrections=1,
    )
    input_hash = canonical_execution_sha256(input_data)
    request_hash = canonical_execution_sha256(
        {
            "runId": run_id,
            "novelId": "novel-1",
            "stepId": step_id,
            "idempotencyKey": "idem-1",
            "inputHash": input_hash,
            "workflow": "long_serial",
            "operation": "rewrite_chapter_selection",
            "purpose": "generation",
            "lane": "creative",
            "evidenceManifest": {
                "bundleId": evidence.id,
                "bundleVersion": evidence.version,
                "policyVersion": evidence.policyVersion,
                "manifestSha256": evidence.manifestSha256,
            },
            "modelProfile": profile.model_dump(mode="json", exclude_none=True),
            "outputSchema": schema.model_dump(mode="json", exclude_none=True),
            "budget": budget.model_dump(mode="json", exclude_none=True),
            "artifact": None,
        }
    )
    return ExecutionStepRequest(
        protocolVersion="2.0",
        jobId=job_id,
        runId=run_id,
        novelId="novel-1",
        stepId=step_id,
        fencingToken=fencing_token,
        dispatchMode=dispatch_mode,
        idempotencyKey="idem-1",
        requestHash=request_hash,
        inputHash=input_hash,
        input=input_data,
        workflow="long_serial",
        operation="rewrite_chapter_selection",
        purpose="generation",
        lane="creative",
        evidenceBundle=evidence,
        modelProfile=profile,
        outputSchema=schema,
        budget=budget,
        submittedAt=datetime(2026, 9, 1, tzinfo=UTC),
    )


def execution_cancel(request: ExecutionStepRequest) -> ExecutionCancelRequest:
    return ExecutionCancelRequest(
        protocolVersion="2.0",
        cancelRequestId="cancel-1",
        runId=request.runId,
        novelId=request.novelId,
        stepId=request.stepId,
        jobId=request.jobId,
        fencingToken=request.fencingToken,
        requestHash=request.requestHash,
        requestedAt=datetime(2026, 9, 1, 0, 0, 1, tzinfo=UTC),
    )


def review_request(
    registry: ExecutionRegistry,
    *,
    profile_key: str = "reviewer.consistency.v1",
    job_id: str = "review-job-1",
    fencing_token: int = 1,
    dispatch_mode: Literal["initial", "pending_recovery", "running_recovery"] = "initial",
) -> ExecutionStepRequest:
    base = execution_request(
        job_id=job_id,
        fencing_token=fencing_token,
        dispatch_mode=dispatch_mode,
    )
    operation = registry.resolve("long_serial", "rewrite_chapter_selection")
    profile = registry.profiles[profile_key]
    budget = operation.reviewer_step_budgets[profile_key]
    schema = operation.reviewer_output_schema
    candidate = base.model_copy(
        update={
            "purpose": "review",
            "lane": operation.operation.review_policy.lane,
            "artifactId": "artifact-1",
            "artifactRevision": 1,
            "input": {
                "task": {
                    "workflow": "long_serial",
                    "operation": "rewrite_chapter_selection",
                    "userInstruction": "保持原任务目标",
                    "rubricVersion": operation.operation.review_policy.rubric_version,
                },
                "candidate": {
                    "replacement": "模拟选区替换文本",
                    "contentSha256": hashlib.sha256("模拟选区替换文本".encode()).hexdigest(),
                }
            },
            "evidenceBundle": base.evidenceBundle.model_copy(
                update={"policyVersion": operation.operation.review_policy.evidence_policy}
            ),
            "modelProfile": ModelProfileRef(
                profile=profile.key,
                version=profile.version,
                reasoningMode=profile.reasoning_mode,
                deploymentProfileKey=profile.deployment_profile_key,
                promptProfile=PromptProfileRef(
                    name=profile.prompt_profile.key,
                    version=profile.prompt_profile.version,
                    sha256=profile.prompt_profile.sha256,
                ),
            ),
            "outputSchema": OutputSchemaRef(
                name=schema.key,
                version=schema.version,
                sha256=schema.sha256,
                jsonSchema=schema.json_schema_value(),
            ),
            "budget": StepBudget(
                maxModelCalls=budget.max_model_calls,
                maxInputTokens=budget.max_input_tokens,
                maxPromptCacheMissTokens=budget.max_prompt_cache_miss_tokens,
                maxCompletionTokens=budget.max_completion_tokens,
                maxReasoningTokens=budget.max_reasoning_tokens,
                maxVisibleOutputTokens=budget.max_visible_output_tokens,
                maxCostMicros=budget.max_cost_micros,
                maxWallClockSeconds=budget.max_wall_clock_seconds,
                maxProviderRetries=budget.max_provider_retries,
                maxProtocolCorrections=budget.max_protocol_corrections,
            ),
        }
    )
    return rehash_request(candidate)


def rehash_request(request: ExecutionStepRequest) -> ExecutionStepRequest:
    input_hash = canonical_execution_sha256(request.input)
    candidate = request.model_copy(update={"inputHash": input_hash})
    request_hash = canonical_execution_sha256(
        candidate._request_hash_payload()  # noqa: SLF001
    )
    return ExecutionStepRequest.model_validate(
        candidate.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=False,
        )
        | {"requestHash": request_hash}
    )


def execution_result(
    request: ExecutionStepRequest,
    *,
    replacement: str = "改写后的选区",
) -> ExecutionStepResult:
    output: dict[str, JsonValue] = {
        "replacement": replacement,
        "contentSha256": hashlib.sha256(replacement.encode("utf-8")).hexdigest(),
    }
    usage = StepUsage(
        usageStatus="partial",
        providerAttempts=1,
        protocolCorrections=0,
        wallTimeMillis=20,
        inputTokens=100,
        cachedTokens=0,
        promptCacheMissTokens=100,
        completionTokens=20,
        reasoningTokens=10,
        visibleOutputTokens=10,
    )
    result_hash = canonical_execution_sha256(
        {
            "resultKind": "output",
            "resolvedModel": resolved_model().model_dump(mode="json", exclude_none=True),
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
        resolvedModel=resolved_model(),
        resultKind="output",
        output=output,
        resultHash=result_hash,
        usage=usage,
        completedAt=datetime(2026, 9, 1, 0, 0, 2, tzinfo=UTC),
    )


def resolved_model() -> ResolvedModelRef:
    deployment_profile_key = "deployment.writer.chapter_selection.v1"
    return ResolvedModelRef(
        deploymentProfileKey=deployment_profile_key,
        deploymentFingerprint=calculate_resolved_model_fingerprint(
            deployment_profile_key=deployment_profile_key,
            provider="fake",
            model="fake",
            transport_profile="transport.fake.v1",
            endpoint_profile="endpoint.local-fake.v1",
            structured_output_route="responses_json_schema_v1",
            capability_version="capability.fake.structured-output.v1",
            reasoning_mode="bounded",
            supports_request_idempotency=True,
        ),
        provider="fake",
        model="fake",
        transportProfile="transport.fake.v1",
        endpointProfile="endpoint.local-fake.v1",
        structuredOutputRoute="responses_json_schema_v1",
        capabilityVersion="capability.fake.structured-output.v1",
        reasoningMode="bounded",
        supportsRequestIdempotency=True,
    )


def _evidence(run_id: str) -> EvidenceBundle:
    content = "原文选区"
    content_bytes = content.encode("utf-8")
    content_sha = hashlib.sha256(content_bytes).hexdigest()
    item = EvidenceItem(
        id="evidence-item-1",
        bundleId="bundle-1",
        ordinal=1,
        resourceType="chapter_content",
        resourceId="chapter-1",
        exists=True,
        resourceRevision=1,
        contentType="text",
        contentText=content,
        contentSha256=content_sha,
        byteCount=len(content_bytes),
    )
    manifest_item = EvidenceManifestItem(
        itemId=item.id,
        ordinal=item.ordinal,
        resourceType=item.resourceType,
        resourceId=item.resourceId,
        exists=item.exists,
        resourceRevision=item.resourceRevision,
        contentType=item.contentType,
        contentSha256=item.contentSha256,
        byteCount=item.byteCount,
    )
    manifest = EvidenceManifest(
        bundleId="bundle-1",
        bundleVersion=1,
        itemCount=1,
        items=[manifest_item],
    )
    return EvidenceBundle(
        id="bundle-1",
        runId=run_id,
        version=1,
        policyVersion="evidence.long_serial.chapter_selection.v1",
        manifest=manifest,
        manifestSha256=canonical_execution_sha256(
            manifest.model_dump(mode="json", exclude_none=True)
        ),
        totalBytes=len(content_bytes),
        items=[item],
    )


def _generator_schema() -> OutputSchemaRef:
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["replacement"],
        "properties": {
            "replacement": {
                "type": "string",
                "minLength": 1,
                "pattern": r"\S",
            },
        },
    }
    return OutputSchemaRef(
        name="output.chapter_selection_replacement.v1",
        version=1,
        sha256=canonical_execution_sha256(schema),
        jsonSchema=schema,
    )
