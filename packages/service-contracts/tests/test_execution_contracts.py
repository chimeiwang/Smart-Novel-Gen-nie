from __future__ import annotations

import copy
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from inkforge_contracts import (
    EXECUTION_CALLBACK_HTTP_METHOD,
    EXECUTION_CALLBACK_RECEIPT_HTTP_STATUS,
    EXECUTION_CALLBACK_STOP_RETRY_STATUSES,
    EXECUTION_HASH_ALGORITHM,
    EXECUTION_PROTOCOL_VERSION,
    BillingReconciliationReceipt,
    BillingReconciliationRequest,
    ChatAnswerInput,
    ChatAnswerOutput,
    EvidenceBundle,
    EvidenceEvaluation,
    EvidenceExpansionRequest,
    EvidenceItem,
    ExecutionCallbackReceipt,
    ExecutionCancelAccepted,
    ExecutionCancelRequest,
    ExecutionStepAccepted,
    ExecutionStepFailure,
    ExecutionStepProgress,
    ExecutionStepRequest,
    ExecutionStepResult,
    ModelProfileRef,
    PromptProfileRef,
    ProposedCommand,
    ResolvedModelRef,
    StepBudget,
    StepUsage,
    calculate_resolved_model_fingerprint,
    canonical_execution_json_bytes,
    execution_callback_path,
)
from pydantic import ValidationError

NOW = datetime(2026, 8, 31, 8, 30, tzinfo=UTC)
SHA = "a" * 64


def test_execution_canonical_json_v1_has_stable_cross_language_bytes() -> None:
    value = {
        "z": None,
        "a": [1.0, -0.0, 1e-7, "换行\n😀", {"😀": 2, "\ue000": 1}],
        "decimal": 1.2300,
    }

    assert EXECUTION_HASH_ALGORITHM == "inkforge-canonical-json/1"
    canonical = canonical_execution_json_bytes(value)
    assert (
        canonical
        == (
            '{"a":[1,0,0.0000001,"换行\\n😀",{"\ue000":1,"😀":2}],"decimal":1.23,"z":null}'
        ).encode()
    )
    assert hashlib.sha256(canonical).hexdigest() == (
        "8120300c6d33bc324976d7175a1311532a5f69f3a45775a3e6f8b94999fb134e"
    )


def test_chat_answer_contract_preserves_complete_text_and_is_strict() -> None:
    instruction = "  这个人物为什么选择离开？\n请只依据作品资料。  "
    answer = "  他离开是为了保护同伴。\n现有证据没有说明他将去哪里。  "

    assert ChatAnswerInput(userInstruction=instruction).userInstruction == instruction
    assert ChatAnswerOutput(answer=answer).answer == answer

    for value in ("", "   ", "\n\t", "\u3000"):
        with pytest.raises(ValidationError):
            ChatAnswerInput(userInstruction=value)
        with pytest.raises(ValidationError):
            ChatAnswerOutput(answer=value)

    with pytest.raises(ValidationError):
        ChatAnswerInput.model_validate(
            {"userInstruction": "问题", "selectedAgents": ["编辑"]}
        )
    with pytest.raises(ValidationError):
        ChatAnswerOutput.model_validate({"answer": "回答", "review": "禁止"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "非法"}, "\ud800"])
def test_execution_canonical_json_rejects_unstable_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_execution_json_bytes(value)


def canonical_bytes(value: object) -> bytes:
    return canonical_execution_json_bytes(value)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def valid_item_payload(*, item_id: str = "evidence-item-1", ordinal: int = 1) -> dict[str, object]:
    content = "  完整章节证据\n"
    encoded = content.encode("utf-8")
    return {
        "id": item_id,
        "bundleId": "bundle-1",
        "ordinal": ordinal,
        "resourceType": "chapter",
        "resourceId": "chapter-1",
        "exists": True,
        "resourceRevision": 3,
        "resourceUpdatedAt": NOW,
        "contentType": "text",
        "contentText": content,
        "contentJson": None,
        "contentSha256": sha256(encoded),
        "byteCount": len(encoded),
        "range": {"startCodePoint": 0, "endCodePoint": len(content)},
        "metadata": {"source": "authoritative"},
    }


def manifest_item_from(item: dict[str, object]) -> dict[str, object]:
    resource_updated_at = item.get("resourceUpdatedAt")
    if isinstance(resource_updated_at, datetime):
        resource_updated_at = resource_updated_at.isoformat().replace("+00:00", "Z")
    manifest_item = {
        "itemId": item["id"],
        "ordinal": item["ordinal"],
        "resourceType": item["resourceType"],
        "resourceId": item["resourceId"],
        "exists": item["exists"],
        "resourceRevision": item.get("resourceRevision"),
        "resourceUpdatedAt": resource_updated_at,
        "contentType": item.get("contentType"),
        "contentSha256": item.get("contentSha256"),
        "byteCount": item["byteCount"],
        "range": item.get("range"),
        "metadata": item.get("metadata", {}),
    }
    return {key: value for key, value in manifest_item.items() if value is not None}


def valid_bundle_payload() -> dict[str, object]:
    item = valid_item_payload()
    manifest = {
        "bundleId": "bundle-1",
        "bundleVersion": 1,
        "itemCount": 1,
        "items": [manifest_item_from(item)],
    }
    return {
        "id": "bundle-1",
        "runId": "run-1",
        "version": 1,
        "policyVersion": "chapter-evidence-v1",
        "manifest": manifest,
        "manifestSha256": sha256(canonical_bytes(manifest)),
        "totalBytes": item["byteCount"],
        "items": [item],
    }


def valid_budget_payload() -> dict[str, object]:
    return {
        "maxModelCalls": 1,
        "maxInputTokens": 20_000,
        "maxPromptCacheMissTokens": 12_000,
        "maxCompletionTokens": 12_000,
        "maxReasoningTokens": 4_000,
        "maxVisibleOutputTokens": 8_000,
        "maxCostMicros": 2_000_000,
        "maxWallClockSeconds": 180,
        "maxProviderRetries": 2,
        "maxProtocolCorrections": 1,
    }


def valid_profile_payload(*, reasoning_mode: str = "bounded") -> dict[str, object]:
    return {
        "profile": "chapter-writer",
        "version": 1,
        "reasoningMode": reasoning_mode,
        "deploymentProfileKey": "deployment.writer.chapter_selection.v1",
        "promptProfile": valid_prompt_profile_payload(),
    }


def valid_prompt_profile_payload() -> dict[str, object]:
    return {
        "name": "prompt.writer.chapter_selection.v1",
        "version": 1,
        "sha256": "c" * 64,
    }


def valid_resolved_model_payload(
    *,
    reasoning_mode: str = "bounded",
    supports_request_idempotency: bool = True,
) -> dict[str, object]:
    deployment_profile_key = "deployment.writer.chapter_selection.v1"
    provider = "deepseek"
    model = "deepseek-v4-flash"
    transport_profile = "transport.deepseek-v4.v1"
    endpoint_profile = "endpoint.deepseek-official.v1"
    structured_output_route = "chat_json_output_v1"
    capability_version = "capability.deepseek-v4.chat-json.v1"
    return {
        "deploymentProfileKey": deployment_profile_key,
        "deploymentFingerprint": calculate_resolved_model_fingerprint(
            deployment_profile_key=deployment_profile_key,
            provider=provider,
            model=model,
            transport_profile=transport_profile,
            endpoint_profile=endpoint_profile,
            structured_output_route=structured_output_route,
            capability_version=capability_version,
            reasoning_mode=reasoning_mode,
            supports_request_idempotency=supports_request_idempotency,
        ),
        "provider": provider,
        "model": model,
        "transportProfile": transport_profile,
        "endpointProfile": endpoint_profile,
        "structuredOutputRoute": structured_output_route,
        "capabilityVersion": capability_version,
        "reasoningMode": reasoning_mode,
        "supportsRequestIdempotency": supports_request_idempotency,
    }


def valid_usage_payload() -> dict[str, object]:
    return {
        "usageStatus": "complete",
        "providerAttempts": 1,
        "protocolCorrections": 0,
        "wallTimeMillis": 12_345,
        "inputTokens": 1_200,
        "cachedTokens": 400,
        "promptCacheMissTokens": 800,
        "completionTokens": 900,
        "reasoningTokens": 300,
        "visibleOutputTokens": 600,
        "costMicros": 15_000,
    }


def valid_reconciliation_payload() -> dict[str, object]:
    return {
        "protocolVersion": "2.0",
        "reconciliationId": "reconciliation-1",
        "runId": "run-1",
        "novelId": "novel-1",
        "stepId": "step-1",
        "reservationRequestId": "reservation-request-1",
        "supplierEvidenceRef": "supplier-report://deepseek/report-1",
        "supplierReportSha256": "d" * 64,
        "decision": "exact_usage",
        "usage": valid_usage_payload(),
    }


def valid_output_schema_payload() -> dict[str, object]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"replacement": {"type": "string"}},
        "required": ["replacement"],
    }
    return {
        "name": "chapter-selection-replacement",
        "version": 1,
        "sha256": sha256(canonical_bytes(schema)),
        "jsonSchema": schema,
    }


def request_hash_material(payload: dict[str, object]) -> dict[str, object]:
    evidence = payload["evidenceBundle"]
    profile = payload["modelProfile"]
    output_schema = payload["outputSchema"]
    budget = payload["budget"]
    assert isinstance(evidence, dict)
    assert isinstance(profile, dict)
    assert isinstance(output_schema, dict)
    assert isinstance(budget, dict)
    artifact = None
    if payload["artifactId"] is not None:
        artifact = {
            "artifactId": payload["artifactId"],
            "artifactRevision": payload["artifactRevision"],
        }
    return {
        "runId": payload["runId"],
        "novelId": payload["novelId"],
        "stepId": payload["stepId"],
        "idempotencyKey": payload["idempotencyKey"],
        "inputHash": payload["inputHash"],
        "workflow": payload["workflow"],
        "operation": payload["operation"],
        "purpose": payload["purpose"],
        "lane": payload["lane"],
        "evidenceManifest": {
            "bundleId": evidence["id"],
            "bundleVersion": evidence["version"],
            "policyVersion": evidence["policyVersion"],
            "manifestSha256": evidence["manifestSha256"],
        },
        "modelProfile": profile,
        "outputSchema": output_schema,
        "budget": budget,
        "artifact": artifact,
    }


def valid_request_payload() -> dict[str, object]:
    input_value = {"instruction": "重写选区", "targetWordCount": 1_000}
    payload: dict[str, object] = {
        "protocolVersion": "2.0",
        "jobId": "job-1",
        "runId": "run-1",
        "novelId": "novel-1",
        "stepId": "step-1",
        "fencingToken": 7,
        "dispatchMode": "initial",
        "idempotencyKey": "run-1.step-1",
        "requestHash": "0" * 64,
        "inputHash": sha256(canonical_bytes(input_value)),
        "input": input_value,
        "workflow": "long_serial",
        "operation": "rewrite_chapter_selection",
        "purpose": "generation",
        "lane": "creative",
        "evidenceBundle": valid_bundle_payload(),
        "modelProfile": valid_profile_payload(),
        "outputSchema": valid_output_schema_payload(),
        "budget": valid_budget_payload(),
        "artifactId": None,
        "artifactRevision": None,
        "submittedAt": NOW,
    }
    payload["requestHash"] = sha256(canonical_bytes(request_hash_material(payload)))
    return payload


def test_logical_profile_excludes_deployment_authority_and_resolution_hash_is_fixed() -> None:
    logical = ModelProfileRef.model_validate(valid_profile_payload())
    resolved = ResolvedModelRef.model_validate(valid_resolved_model_payload())

    assert logical.deploymentProfileKey == resolved.deploymentProfileKey
    assert logical.reasoningMode == resolved.reasoningMode
    assert resolved.deploymentFingerprint == (
        "f8d54b16d2dbf9ad32997020b4d2f22080f0717870e0ae84c2f78c3846f696fa"
    )
    assert set(logical.model_dump()) == {
        "profile",
        "version",
        "reasoningMode",
        "deploymentProfileKey",
        "promptProfile",
    }
    assert PromptProfileRef.model_validate(valid_prompt_profile_payload()).version == 1
    with pytest.raises(ValidationError, match="name 与 version"):
        PromptProfileRef.model_validate(
            {**valid_prompt_profile_payload(), "version": 2}
        )
    assert "idempotencyKey" in ResolvedModelRef.model_json_schema()["properties"][
        "supportsRequestIdempotency"
    ]["description"]
    assert "原样传" in ExecutionStepRequest.model_json_schema()["properties"][
        "idempotencyKey"
    ]["description"]

    with pytest.raises(ValidationError):
        ModelProfileRef.model_validate(
            {**valid_profile_payload(), "provider": "deepseek", "model": "forbidden"}
        )
    with pytest.raises(ValidationError, match="deploymentFingerprint"):
        ResolvedModelRef.model_validate(
            {**valid_resolved_model_payload(), "provider": "openai_compatible"}
        )

    unsupported = ResolvedModelRef.model_validate(
        valid_resolved_model_payload(supports_request_idempotency=False)
    )
    assert unsupported.supportsRequestIdempotency is False
    assert unsupported.deploymentFingerprint == (
        "55895cc3e4c2c89a84a246af5395a974057d6e09818e6631967c30a3119dadf2"
    )
    with pytest.raises(ValidationError, match="deploymentFingerprint"):
        ResolvedModelRef.model_validate(
            {
                **valid_resolved_model_payload(),
                "supportsRequestIdempotency": False,
            }
        )


def test_evidence_item_preserves_complete_text_and_verifies_hash_and_bytes() -> None:
    item = EvidenceItem.model_validate(valid_item_payload())

    assert item.contentText == "  完整章节证据\n"
    assert item.byteCount == len(item.contentText.encode("utf-8"))


def test_evidence_item_accepts_canonical_json_content() -> None:
    content = {"章节": 1, "tags": ["主线", "伏笔"]}
    encoded = canonical_bytes(content)
    payload = valid_item_payload()
    payload.update(
        {
            "contentType": "json",
            "contentText": None,
            "contentJson": content,
            "contentSha256": sha256(encoded),
            "byteCount": len(encoded),
        }
    )

    assert EvidenceItem.model_validate(payload).contentJson == content


def test_evidence_item_accepts_empty_existing_text_with_zero_bytes() -> None:
    payload = valid_item_payload()
    payload.update(
        {
            "contentText": "",
            "contentSha256": sha256(b""),
            "byteCount": 0,
            "range": None,
        }
    )

    item = EvidenceItem.model_validate(payload)

    assert item.exists is True
    assert item.contentText == ""
    assert item.byteCount == 0


def test_missing_evidence_has_no_content_version_or_hash_and_manifest_supports_zero() -> None:
    item = {
        "id": "evidence-item-missing",
        "bundleId": "bundle-missing",
        "ordinal": 1,
        "resourceType": "chapter",
        "resourceId": "chapter-missing",
        "exists": False,
        "contentType": None,
        "contentText": None,
        "contentJson": None,
        "contentSha256": None,
        "byteCount": 0,
        "metadata": {"absenceSentinel": "not_found"},
    }
    manifest = {
        "bundleId": "bundle-missing",
        "bundleVersion": 1,
        "itemCount": 1,
        "items": [manifest_item_from(item)],
    }
    bundle = EvidenceBundle.model_validate(
        {
            "id": "bundle-missing",
            "runId": "run-1",
            "version": 1,
            "policyVersion": "chapter-evidence-v1",
            "manifest": manifest,
            "manifestSha256": sha256(canonical_bytes(manifest)),
            "totalBytes": 0,
            "items": [item],
        }
    )

    assert bundle.items[0].exists is False
    assert bundle.items[0].contentSha256 is None
    assert bundle.totalBytes == 0

    with pytest.raises(ValidationError):
        EvidenceItem.model_validate({**item, "resourceRevision": 1})
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate({**item, "contentType": "text", "contentText": ""})


@pytest.mark.parametrize(
    "mutation",
    [
        {"contentJson": {"also": "present"}},
        {"contentText": None},
        {"contentSha256": "A" * 64},
        {"contentSha256": "0" * 64},
        {"byteCount": 1},
        {"id": "../../item"},
        {"id": " evidence-item-1 "},
        {"resourceType": " chapter "},
        {"exists": "true"},
        {"ordinal": 0},
        {"ordinal": "1"},
        {"unknown": True},
    ],
)
def test_evidence_item_rejects_ambiguous_or_unverified_content(
    mutation: dict[str, object],
) -> None:
    payload = valid_item_payload()
    payload.update(mutation)

    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(payload)


def test_evidence_bundle_verifies_manifest_order_hash_and_total() -> None:
    bundle = EvidenceBundle.model_validate(valid_bundle_payload())

    assert bundle.manifest.itemCount == 1
    assert bundle.items[0].bundleId == bundle.id


@pytest.mark.parametrize("field", ["manifestSha256", "totalBytes", "items"])
def test_evidence_bundle_rejects_manifest_drift(field: str) -> None:
    payload = valid_bundle_payload()
    if field == "manifestSha256":
        payload[field] = "0" * 64
    elif field == "totalBytes":
        total_bytes = payload[field]
        assert isinstance(total_bytes, int)
        payload[field] = total_bytes + 1
    else:
        item = valid_item_payload(item_id="evidence-item-2", ordinal=2)
        payload[field] = [item]

    with pytest.raises(ValidationError):
        EvidenceBundle.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resourceId", "chapter-2"),
        ("resourceRevision", 4),
        ("resourceUpdatedAt", NOW + timedelta(seconds=1)),
        ("range", {"startCodePoint": 1, "endCodePoint": 4}),
        ("metadata", {"source": "unbound"}),
    ],
)
def test_evidence_manifest_binds_provenance_and_metadata(field: str, value: object) -> None:
    payload = valid_bundle_payload()
    items = payload["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    items[0][field] = value

    with pytest.raises(ValidationError):
        EvidenceBundle.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maxModelCalls", 2),
        ("maxInputTokens", 0),
        ("maxInputTokens", "20000"),
        ("maxPromptCacheMissTokens", 20_001),
        ("maxReasoningTokens", 12_001),
        ("maxVisibleOutputTokens", 12_001),
        ("maxProviderRetries", 3),
        ("maxProtocolCorrections", 2),
    ],
)
def test_step_budget_is_strict_and_bounded(field: str, value: object) -> None:
    payload = valid_budget_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        StepBudget.model_validate(payload)


def test_step_budget_does_not_reuse_run_budget_per_step_field_name() -> None:
    schema = StepBudget.model_json_schema()

    assert "maxProviderRetries" in schema["properties"]
    assert "maxProviderRetriesPerStep" not in schema["properties"]
    assert "单 Step" in schema["properties"]["maxProviderRetries"]["description"]


def test_execution_request_binds_run_evidence_artifact_and_reasoning_budget() -> None:
    request = ExecutionStepRequest.model_validate(valid_request_payload())

    assert request.protocolVersion == EXECUTION_PROTOCOL_VERSION
    assert request.evidenceBundle.runId == request.runId
    assert request.budget.maxModelCalls == 1

    artifact_mismatch = valid_request_payload()
    artifact_mismatch["artifactId"] = "artifact-1"
    with pytest.raises(ValidationError):
        ExecutionStepRequest.model_validate(artifact_mismatch)

    disabled_reasoning = valid_request_payload()
    disabled_reasoning["modelProfile"] = valid_profile_payload(reasoning_mode="disabled")
    with pytest.raises(ValidationError):
        ExecutionStepRequest.model_validate(disabled_reasoning)


def test_execution_messages_require_explicit_nullable_novel_binding() -> None:
    user_scoped = valid_request_payload()
    user_scoped["novelId"] = None
    user_scoped["requestHash"] = sha256(canonical_bytes(request_hash_material(user_scoped)))
    assert ExecutionStepRequest.model_validate(user_scoped).novelId is None

    missing = valid_request_payload()
    missing.pop("novelId")
    with pytest.raises(ValidationError):
        ExecutionStepRequest.model_validate(missing)

    for model in (
        ExecutionCancelRequest,
        ExecutionCancelAccepted,
        ExecutionStepRequest,
        ExecutionStepAccepted,
        ExecutionStepProgress,
        ExecutionStepResult,
        ExecutionStepFailure,
    ):
        schema = model.model_json_schema()
        assert "novelId" in schema["required"]
        assert {branch.get("type") for branch in schema["properties"]["novelId"]["anyOf"]} == {
            "string",
            "null",
        }


def test_execution_request_verifies_input_and_stable_request_hashes() -> None:
    stale_input_hash = valid_request_payload()
    stale_input_hash["input"] = {"instruction": "已改变"}
    with pytest.raises(ValidationError):
        ExecutionStepRequest.model_validate(stale_input_hash)

    stale_request_hash = valid_request_payload()
    changed_input = {"instruction": "已改变"}
    stale_request_hash["input"] = changed_input
    stale_request_hash["inputHash"] = sha256(canonical_bytes(changed_input))
    with pytest.raises(ValidationError):
        ExecutionStepRequest.model_validate(stale_request_hash)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("novelId", "novel-2"),
        ("stepId", "step-2"),
        ("idempotencyKey", "run-1.step-2"),
        ("workflow", "short_medium"),
        ("operation", "generate_manuscript"),
        ("purpose", "review"),
        ("lane", "interactive"),
    ],
)
def test_execution_request_hash_rejects_bound_identity_drift(field: str, value: object) -> None:
    payload = valid_request_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        ExecutionStepRequest.model_validate(payload)


def test_execution_request_hash_binds_evidence_profile_schema_budget_and_artifact() -> None:
    run_drift = valid_request_payload()
    run_drift["runId"] = "run-2"
    run_evidence = copy.deepcopy(run_drift["evidenceBundle"])
    assert isinstance(run_evidence, dict)
    run_evidence["runId"] = "run-2"
    run_drift["evidenceBundle"] = run_evidence

    profile_drift = valid_request_payload()
    profile = copy.deepcopy(profile_drift["modelProfile"])
    assert isinstance(profile, dict)
    profile["version"] = 2
    profile_drift["modelProfile"] = profile

    prompt_drift = valid_request_payload()
    prompt_profile = copy.deepcopy(prompt_drift["modelProfile"])
    assert isinstance(prompt_profile, dict)
    prompt_ref = prompt_profile["promptProfile"]
    assert isinstance(prompt_ref, dict)
    prompt_ref["sha256"] = "d" * 64
    prompt_drift["modelProfile"] = prompt_profile

    budget_drift = valid_request_payload()
    budget = copy.deepcopy(budget_drift["budget"])
    assert isinstance(budget, dict)
    budget["maxCostMicros"] = 0
    budget_drift["budget"] = budget

    schema_drift = valid_request_payload()
    schema_ref = copy.deepcopy(schema_drift["outputSchema"])
    assert isinstance(schema_ref, dict)
    schema = schema_ref["jsonSchema"]
    assert isinstance(schema, dict)
    schema["title"] = "漂移后的 Schema"
    schema_ref["sha256"] = sha256(canonical_bytes(schema))
    schema_drift["outputSchema"] = schema_ref

    evidence_drift = valid_request_payload()
    evidence = copy.deepcopy(evidence_drift["evidenceBundle"])
    assert isinstance(evidence, dict)
    evidence["id"] = "bundle-2"
    items = evidence["items"]
    manifest = evidence["manifest"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    assert isinstance(manifest, dict)
    items[0]["bundleId"] = "bundle-2"
    manifest["bundleId"] = "bundle-2"
    evidence["manifestSha256"] = sha256(canonical_bytes(manifest))
    evidence_drift["evidenceBundle"] = evidence

    artifact_drift = valid_request_payload()
    artifact_drift["artifactId"] = "artifact-1"
    artifact_drift["artifactRevision"] = 1

    for payload in (
        run_drift,
        profile_drift,
        prompt_drift,
        budget_drift,
        schema_drift,
        evidence_drift,
        artifact_drift,
    ):
        with pytest.raises(ValidationError):
            ExecutionStepRequest.model_validate(payload)


def test_execution_request_hash_excludes_lease_delivery_fields() -> None:
    original = valid_request_payload()
    original_hash = original["requestHash"]

    redelivered = {
        **original,
        "jobId": "job-2",
        "fencingToken": 8,
        "dispatchMode": "pending_recovery",
        "submittedAt": NOW + timedelta(minutes=1),
    }
    request = ExecutionStepRequest.model_validate(redelivered)

    assert request.requestHash == original_hash
    assert request.jobId == "job-2"
    assert request.fencingToken == 8

    running_recovery = ExecutionStepRequest.model_validate(
        {**redelivered, "dispatchMode": "running_recovery"}
    )
    assert running_recovery.requestHash == original_hash


def test_zero_output_and_cost_budget_and_output_schema_hash_are_supported() -> None:
    budget = StepBudget.model_validate({**valid_budget_payload(), "maxCostMicros": 0})
    assert budget.maxCostMicros == 0
    embedding_budget = StepBudget.model_validate(
        {
            **valid_budget_payload(),
            "maxCompletionTokens": 0,
            "maxReasoningTokens": 0,
            "maxVisibleOutputTokens": 0,
            "maxCostMicros": 0,
            "maxProtocolCorrections": 0,
        }
    )
    assert embedding_budget.maxCompletionTokens == 0

    request = ExecutionStepRequest.model_validate(valid_request_payload())
    assert request.outputSchema.jsonSchema["type"] == "object"

    invalid_schema = valid_request_payload()
    schema_ref = valid_output_schema_payload()
    schema_ref["sha256"] = "0" * 64
    invalid_schema["outputSchema"] = schema_ref
    with pytest.raises(ValidationError):
        ExecutionStepRequest.model_validate(invalid_schema)


@pytest.mark.parametrize(
    "mutation",
    [
        {"protocolVersion": "1.1"},
        {"fencingToken": 0},
        {"fencingToken": "7"},
        {"dispatchMode": "retry"},
        {"requestHash": "not-a-hash"},
        {"resolvedModel": valid_resolved_model_payload()},
        {"logs": ["禁止携带正文日志"]},
        {"reasoningContent": "禁止携带推理原文"},
    ],
)
def test_execution_request_rejects_legacy_or_unsafe_fields(
    mutation: dict[str, object],
) -> None:
    payload = valid_request_payload()
    payload.update(mutation)

    with pytest.raises(ValidationError):
        ExecutionStepRequest.model_validate(payload)


def test_accepted_and_progress_are_protocol_v2_and_semantically_consistent() -> None:
    accepted = ExecutionStepAccepted.model_validate(
        {
            "protocolVersion": "2.0",
            "jobId": "job-1",
            "runId": "run-1",
            "novelId": "novel-1",
            "stepId": "step-1",
            "fencingToken": 7,
            "requestHash": SHA,
            "resolvedModel": valid_resolved_model_payload(),
            "status": "queued",
            "acceptedAt": NOW,
        }
    )
    progress_payload = {
        "protocolVersion": "2.0",
        "progressId": "progress-1",
        "jobId": "job-1",
        "runId": "run-1",
        "novelId": "novel-1",
        "stepId": "step-1",
        "fencingToken": 7,
        "requestHash": SHA,
        "resolvedModel": valid_resolved_model_payload(),
        "sequence": 1,
        "phase": "waiting_provider",
        "progressCode": "provider_wait",
        "elapsedSeconds": 10,
        "waitingOnProvider": True,
        "usage": {
            "usageStatus": "unknown",
            "providerAttempts": 0,
            "protocolCorrections": 0,
            "wallTimeMillis": 0,
        },
        "occurredAt": NOW,
    }
    progress = ExecutionStepProgress.model_validate(progress_payload)

    assert accepted.protocolVersion == progress.protocolVersion == "2.0"
    inconsistent = {**progress_payload, "waitingOnProvider": False}
    with pytest.raises(ValidationError):
        ExecutionStepProgress.model_validate(inconsistent)

    for field, value in (("cachedTokens", 399), ("completionTokens", 899)):
        invalid_usage = copy.deepcopy(progress_payload)
        assert isinstance(invalid_usage["usage"], dict)
        invalid_usage["usage"][field] = value
        with pytest.raises(ValidationError):
            ExecutionStepProgress.model_validate(invalid_usage)


def test_usage_distinguishes_complete_partial_and_unknown_provider_facts() -> None:
    partial = {
        **valid_usage_payload(),
        "usageStatus": "partial",
        "cachedTokens": None,
        "promptCacheMissTokens": None,
        "costMicros": None,
    }
    unknown = {
        "usageStatus": "unknown",
        "providerAttempts": 1,
        "protocolCorrections": 0,
        "wallTimeMillis": 5_000,
    }

    progress = ExecutionStepProgress.model_validate(
        {
            "protocolVersion": "2.0",
            "progressId": "progress-partial",
            "jobId": "job-1",
            "runId": "run-1",
            "novelId": None,
            "stepId": "step-1",
            "fencingToken": 7,
            "requestHash": SHA,
            "resolvedModel": valid_resolved_model_payload(),
            "sequence": 1,
            "phase": "reporting",
            "progressCode": "usage_reconciliation",
            "elapsedSeconds": 5,
            "waitingOnProvider": False,
            "usage": partial,
            "occurredAt": NOW,
        }
    )
    assert progress.usage.usageStatus == "partial"

    accepted_unknown = {**partial, **unknown}
    for field in (
        "inputTokens",
        "cachedTokens",
        "promptCacheMissTokens",
        "completionTokens",
        "reasoningTokens",
        "visibleOutputTokens",
        "costMicros",
    ):
        accepted_unknown.pop(field, None)
    assert StepUsage.model_validate(accepted_unknown).usageStatus == "unknown"

    with pytest.raises(ValidationError):
        StepUsage.model_validate({**valid_usage_payload(), "usageStatus": "partial"})
    with pytest.raises(ValidationError):
        StepUsage.model_validate({**accepted_unknown, "usageStatus": "unknown", "inputTokens": 1})
    with pytest.raises(ValidationError, match="零供应商尝试"):
        StepUsage.model_validate({**valid_usage_payload(), "providerAttempts": 0})
    with pytest.raises(ValidationError, match="零供应商尝试"):
        StepUsage.model_validate(
            {
                "usageStatus": "unknown",
                "providerAttempts": 0,
                "protocolCorrections": 1,
                "wallTimeMillis": 1,
            }
        )


def test_billing_reconciliation_contract_requires_exact_or_proven_zero_usage() -> None:
    exact = BillingReconciliationRequest.model_validate(valid_reconciliation_payload())
    assert exact.decision == "exact_usage"
    assert exact.usage.usageStatus == "complete"

    proven_zero = valid_reconciliation_payload()
    proven_zero["decision"] = "proven_zero"
    proven_zero["usage"] = {
        "usageStatus": "unknown",
        "providerAttempts": 0,
        "protocolCorrections": 0,
        "wallTimeMillis": 321,
    }
    assert BillingReconciliationRequest.model_validate(proven_zero).decision == "proven_zero"

    for mutation in (
        {"supplierEvidenceRef": "   "},
        {"supplierReportSha256": "not-a-sha"},
        {"decision": "proven_zero"},
    ):
        invalid = copy.deepcopy(valid_reconciliation_payload())
        invalid.update(mutation)
        with pytest.raises(ValidationError):
            BillingReconciliationRequest.model_validate(invalid)

    incomplete = copy.deepcopy(valid_reconciliation_payload())
    usage = incomplete["usage"]
    assert isinstance(usage, dict)
    usage.update({"usageStatus": "partial", "costMicros": None})
    with pytest.raises(ValidationError, match="complete usage"):
        BillingReconciliationRequest.model_validate(incomplete)


def test_billing_reconciliation_receipt_is_explicit_and_bounded() -> None:
    receipt = BillingReconciliationReceipt.model_validate(
        {
            "protocolVersion": "2.0",
            "reconciliationId": "reconciliation-1",
            "reservationRequestId": "reservation-request-1",
            "decision": "exact_usage",
            "reservationStatus": "settled",
            "chargedMicros": 1_200,
            "balanceAfterMicros": 998_800,
            "settledAt": NOW,
            "duplicate": False,
        }
    )
    assert receipt.chargedMicros == 1_200
    with pytest.raises(ValidationError):
        BillingReconciliationReceipt.model_validate(
            {**receipt.model_dump(), "chargedMicros": -1}
        )


def test_cancel_contract_binds_active_lease_identity() -> None:
    request = ExecutionCancelRequest.model_validate(
        {
            "protocolVersion": "2.0",
            "cancelRequestId": "cancel-1",
            "runId": "run-1",
            "novelId": "novel-1",
            "stepId": "step-1",
            "jobId": "job-1",
            "fencingToken": 7,
            "requestHash": SHA,
            "requestedAt": NOW,
        }
    )
    accepted = ExecutionCancelAccepted.model_validate(
        {
            "protocolVersion": "2.0",
            "cancelRequestId": request.cancelRequestId,
            "runId": request.runId,
            "novelId": request.novelId,
            "stepId": request.stepId,
            "jobId": request.jobId,
            "fencingToken": request.fencingToken,
            "status": "accepted",
            "acceptedAt": NOW,
        }
    )

    assert accepted.cancelRequestId == request.cancelRequestId
    assert accepted.fencingToken == request.fencingToken


def test_proposed_command_requires_exactly_one_resolution_path() -> None:
    resolved = ProposedCommand.model_validate(
        {
            "workflow": "long_serial",
            "operation": "write_chapter",
            "targetType": "chapter",
            "targetId": "chapter-1",
            "scopeKind": "chapter",
            "arguments": {"targetWordCount": 4_000},
            "confidence": 0.96,
            "clarification": None,
        }
    )
    clarification = ProposedCommand.model_validate(
        {
            "confidence": 0.4,
            "clarification": {
                "code": "missing_target",
                "prompt": "请选择要处理的章节。",
            },
        }
    )

    assert resolved.operation == "write_chapter"
    assert clarification.operation is None

    with pytest.raises(ValidationError):
        ProposedCommand.model_validate(
            {
                **resolved.model_dump(),
                "clarification": {
                    "code": "ambiguous",
                    "prompt": "请确认。",
                },
            }
        )


def test_evidence_expansion_rejects_duplicate_resource_ranges() -> None:
    item = {
        "resourceType": "chapter",
        "resourceId": "chapter-2",
        "range": {"startCodePoint": 0, "endCodePoint": 10},
        "purposeCode": "missing_context",
    }
    payload = {
        "requestId": "expansion-1",
        "sourceBundleId": "bundle-1",
        "sourceBundleVersion": 1,
        "reasonCode": "insufficient_evidence",
        "maxAdditionalBytes": 20_000,
        "items": [item],
    }
    assert EvidenceExpansionRequest.model_validate(payload).items[0].resourceId == "chapter-2"

    payload["items"] = [item, copy.deepcopy(item)]
    with pytest.raises(ValidationError):
        EvidenceExpansionRequest.model_validate(payload)


def valid_finding_payload() -> dict[str, object]:
    item = valid_item_payload()
    return {
        "dimension": "timeline",
        "severity": "warning",
        "claim": "候选中的时间顺序与证据冲突。",
        "candidateRange": {"startCodePoint": 8, "endCodePoint": 16},
        "evidence": [
            {
                "evidenceItemId": item["id"],
                "contentSha256": item["contentSha256"],
                "range": {"startCodePoint": 0, "endCodePoint": 5},
            }
        ],
        "suggestion": "保持权威事件顺序。",
        "confidence": 0.91,
    }


def valid_evaluation_payload() -> dict[str, object]:
    return {
        "evaluationId": "evaluation-1",
        "runId": "run-1",
        "stepId": "step-1",
        "evidenceBundleId": "bundle-1",
        "artifactId": "artifact-1",
        "artifactRevision": 1,
        "evaluatorProfile": {
            **valid_profile_payload(reasoning_mode="disabled"),
            "profile": "timeline-reviewer",
        },
        "resolvedModel": valid_resolved_model_payload(reasoning_mode="disabled"),
        "rubricVersion": "timeline-v1",
        "executionStatus": "completed",
        "contentVerdict": "issues_found",
        "findings": [valid_finding_payload()],
    }


def test_evaluation_separates_execution_failure_from_content_verdict() -> None:
    evaluation = EvidenceEvaluation.model_validate(valid_evaluation_payload())
    assert evaluation.findings[0].evidence[0].evidenceItemId == "evidence-item-1"

    error_finding = valid_evaluation_payload()
    assert isinstance(error_finding["findings"], list)
    assert isinstance(error_finding["findings"][0], dict)
    error_finding["findings"][0]["severity"] = "error"
    assert EvidenceEvaluation.model_validate(error_finding).findings[0].severity == "error"

    failed = valid_evaluation_payload()
    failed.update(
        {
            "executionStatus": "failed",
            "contentVerdict": "cannot_assess",
            "findings": [],
        }
    )
    assert EvidenceEvaluation.model_validate(failed).contentVerdict == "cannot_assess"

    invalid_reviewer_block = copy.deepcopy(failed)
    invalid_reviewer_block.update(
        {
            "contentVerdict": "issues_found",
            "findings": [{**valid_finding_payload(), "severity": "block"}],
        }
    )
    with pytest.raises(ValidationError):
        EvidenceEvaluation.model_validate(invalid_reviewer_block)

    deployment_mismatch = valid_evaluation_payload()
    resolved = copy.deepcopy(deployment_mismatch["resolvedModel"])
    assert isinstance(resolved, dict)
    resolved["deploymentProfileKey"] = "deployment.reviewer.timeline.v2"
    resolved["deploymentFingerprint"] = calculate_resolved_model_fingerprint(
        deployment_profile_key="deployment.reviewer.timeline.v2",
        provider="deepseek",
        model="deepseek-v4-flash",
        transport_profile="transport.deepseek-v4.v1",
        endpoint_profile="endpoint.deepseek-official.v1",
        structured_output_route="chat_json_output_v1",
        capability_version="capability.deepseek-v4.chat-json.v1",
        reasoning_mode="disabled",
        supports_request_idempotency=True,
    )
    deployment_mismatch["resolvedModel"] = resolved
    with pytest.raises(ValidationError, match="deploymentProfileKey"):
        EvidenceEvaluation.model_validate(deployment_mismatch)


def test_execution_result_is_single_branch_and_hash_bound() -> None:
    output = {"replacement": "完整候选", "contentSha256": "d" * 64}
    usage = valid_usage_payload()
    resolved_model = valid_resolved_model_payload()
    hash_payload = {
        "resultKind": "output",
        "resolvedModel": resolved_model,
        "usage": usage,
        "value": output,
    }
    payload = {
        "protocolVersion": "2.0",
        "jobId": "job-1",
        "runId": "run-1",
        "novelId": "novel-1",
        "stepId": "step-1",
        "fencingToken": 7,
        "requestHash": SHA,
        "inputHash": "b" * 64,
        "resolvedModel": resolved_model,
        "resultKind": "output",
        "output": output,
        "resultHash": sha256(canonical_bytes(hash_payload)),
        "usage": usage,
        "completedAt": NOW,
    }
    result = ExecutionStepResult.model_validate(payload)
    assert result.output == output

    ambiguous = {
        **payload,
        "proposedCommand": {
            "confidence": 0.2,
            "clarification": {"code": "missing_target", "prompt": "请选择目标。"},
        },
    }
    with pytest.raises(ValidationError):
        ExecutionStepResult.model_validate(ambiguous)

    with pytest.raises(ValidationError):
        ExecutionStepResult.model_validate({**payload, "resultHash": "0" * 64})

    with pytest.raises(ValidationError):
        ExecutionStepResult.model_validate({**payload, "reasoningContent": "禁止"})
    unsafe_output = {"replacement": "候选", "diagnostics": {"reasoning_content": "禁止"}}
    unsafe_hash = {
        "resultKind": "output",
        "resolvedModel": resolved_model,
        "usage": usage,
        "value": unsafe_output,
    }
    with pytest.raises(ValidationError):
        ExecutionStepResult.model_validate(
            {
                **payload,
                "output": unsafe_output,
                "resultHash": sha256(canonical_bytes(unsafe_hash)),
            }
        )


def test_evaluation_result_repeats_the_same_resolved_model() -> None:
    evaluation = valid_evaluation_payload()
    resolved = valid_resolved_model_payload(reasoning_mode="disabled")
    usage = valid_usage_payload()
    hash_payload = {
        "resultKind": "evaluation",
        "resolvedModel": resolved,
        "usage": usage,
        "value": evaluation,
    }
    payload = {
        "protocolVersion": "2.0",
        "jobId": "job-review-1",
        "runId": "run-1",
        "novelId": "novel-1",
        "stepId": "step-1",
        "fencingToken": 7,
        "requestHash": SHA,
        "inputHash": "b" * 64,
        "resolvedModel": resolved,
        "resultKind": "evaluation",
        "evaluation": evaluation,
        "resultHash": sha256(canonical_bytes(hash_payload)),
        "usage": usage,
        "completedAt": NOW,
    }
    result = ExecutionStepResult.model_validate(payload)
    assert result.evaluation is not None
    assert result.evaluation.resolvedModel == result.resolvedModel

    drifted = copy.deepcopy(payload)
    outer_resolved = valid_resolved_model_payload(reasoning_mode="disabled")
    outer_resolved["model"] = "deepseek-v4-flash-canary"
    outer_resolved["deploymentFingerprint"] = calculate_resolved_model_fingerprint(
        deployment_profile_key="deployment.writer.chapter_selection.v1",
        provider="deepseek",
        model="deepseek-v4-flash-canary",
        transport_profile="transport.deepseek-v4.v1",
        endpoint_profile="endpoint.deepseek-official.v1",
        structured_output_route="chat_json_output_v1",
        capability_version="capability.deepseek-v4.chat-json.v1",
        reasoning_mode="disabled",
        supports_request_idempotency=True,
    )
    drifted["resolvedModel"] = outer_resolved
    drifted_hash = {
        "resultKind": "evaluation",
        "resolvedModel": outer_resolved,
        "usage": usage,
        "value": evaluation,
    }
    drifted["resultHash"] = sha256(canonical_bytes(drifted_hash))
    with pytest.raises(ValidationError, match="同一解析模型"):
        ExecutionStepResult.model_validate(drifted)


def test_execution_failure_is_structured_hash_bound_and_never_contains_logs() -> None:
    usage = valid_usage_payload()
    resolved_model = valid_resolved_model_payload()
    failure_value = {
        "errorCategory": "model_outcome_unknown",
        "errorCode": "MODEL_OUTCOME_UNKNOWN",
        "outcomeUnknown": True,
        "retryable": False,
        "resolvedModel": resolved_model,
        "usage": usage,
    }
    payload = {
        "protocolVersion": "2.0",
        "jobId": "job-1",
        "runId": "run-1",
        "novelId": "novel-1",
        "stepId": "step-1",
        "fencingToken": 7,
        "requestHash": SHA,
        "inputHash": "b" * 64,
        "resolvedModel": resolved_model,
        **{
            key: failure_value[key]
            for key in ("errorCategory", "errorCode", "outcomeUnknown", "retryable")
        },
        "resultHash": sha256(canonical_bytes(failure_value)),
        "usage": usage,
        "failedAt": NOW,
    }
    failure = ExecutionStepFailure.model_validate(payload)
    assert failure.outcomeUnknown is True

    with pytest.raises(ValidationError):
        ExecutionStepFailure.model_validate({**payload, "retryable": True})
    with pytest.raises(ValidationError):
        ExecutionStepFailure.model_validate({**payload, "logs": "供应商原始响应"})


def test_cancelled_failure_reports_matching_cancel_id_and_unknown_usage() -> None:
    usage = {
        "usageStatus": "unknown",
        "providerAttempts": 1,
        "protocolCorrections": 0,
        "wallTimeMillis": 3_000,
    }
    resolved_model = valid_resolved_model_payload()
    failure_value = {
        "cancelRequestId": "cancel-1",
        "errorCategory": "cancelled",
        "errorCode": "EXECUTION_CANCELLED",
        "outcomeUnknown": False,
        "retryable": False,
        "resolvedModel": resolved_model,
        "usage": usage,
    }
    payload = {
        "protocolVersion": "2.0",
        "jobId": "job-1",
        "runId": "run-1",
        "novelId": None,
        "stepId": "step-1",
        "fencingToken": 7,
        "requestHash": SHA,
        "inputHash": "b" * 64,
        "resolvedModel": resolved_model,
        **failure_value,
        "resultHash": sha256(canonical_bytes(failure_value)),
        "failedAt": NOW,
    }

    failure = ExecutionStepFailure.model_validate(payload)
    assert failure.cancelRequestId == "cancel-1"
    assert failure.usage.usageStatus == "unknown"

    with pytest.raises(ValidationError):
        ExecutionStepFailure.model_validate({**payload, "cancelRequestId": None})
    with pytest.raises(ValidationError):
        ExecutionStepFailure.model_validate(
            {**payload, "errorCategory": "internal", "cancelRequestId": "cancel-1"}
        )


@pytest.mark.parametrize("status", ["accepted", "duplicate", "superseded"])
def test_callback_receipt_is_http_200_and_stops_delivery_retry(status: str) -> None:
    receipt = ExecutionCallbackReceipt.model_validate(
        {
            "protocolVersion": "2.0",
            "runId": "run-1",
            "stepId": "step-1",
            "jobId": "job-1",
            "fencingToken": 7,
            "requestHash": SHA,
            "status": status,
            "receivedAt": NOW,
        }
    )

    assert EXECUTION_CALLBACK_RECEIPT_HTTP_STATUS == 200
    assert receipt.status in EXECUTION_CALLBACK_STOP_RETRY_STATUSES


def test_stale_callback_receipt_requires_terminal_retry_or_refence() -> None:
    receipt = ExecutionCallbackReceipt.model_validate(
        {
            "protocolVersion": "2.0",
            "runId": "run-1",
            "stepId": "step-1",
            "jobId": "job-1",
            "fencingToken": 7,
            "requestHash": SHA,
            "status": "stale",
            "receivedAt": NOW,
        }
    )

    assert receipt.status not in EXECUTION_CALLBACK_STOP_RETRY_STATUSES


@pytest.mark.parametrize("callback_kind", ["progress", "result", "failure"])
def test_callback_path_is_frozen_for_each_dto(callback_kind: str) -> None:
    assert EXECUTION_CALLBACK_HTTP_METHOD == "PUT"
    assert execution_callback_path(
        run_id="run-1",
        step_id="step-1",
        callback_kind=callback_kind,  # type: ignore[arg-type]
    ) == f"/internal/v1/workflow-runs/run-1/steps/step-1/{callback_kind}"


def test_callback_path_and_receipt_reject_unknown_protocol_values() -> None:
    with pytest.raises(ValidationError):
        ExecutionCallbackReceipt.model_validate(
            {
                "protocolVersion": "2.0",
                "runId": "run-1",
                "stepId": "step-1",
                "jobId": "job-1",
                "fencingToken": 7,
                "requestHash": SHA,
                "status": "retry",
                "receivedAt": NOW,
            }
        )
    with pytest.raises(ValidationError):
        execution_callback_path(
            run_id="../run-1",
            step_id="step-1",
            callback_kind="progress",
        )
    with pytest.raises(ValueError, match="未知"):
        execution_callback_path(
            run_id="run-1",
            step_id="step-1",
            callback_kind="unknown",  # type: ignore[arg-type]
        )
