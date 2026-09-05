"""RAG 来源与向量批次保持完整码点、严格代次和数值边界。"""

import hashlib

import jsonschema_rs
import pytest
from inkforge_contracts.execution import ResolvedModelRef, calculate_resolved_model_fingerprint
from inkforge_contracts.rag_execution import (
    RagEmbeddingBatchOutput,
    RagEmbeddingContextV2,
    RagEmbeddingRunInput,
    RagEmbeddingStepInput,
)
from pydantic import ValidationError


def context(content="\ufeff😀\r\n" * 500):
    return {
        "referenceId": "reference-1",
        "contentHash": hashlib.sha256(content.encode()).hexdigest(),
        "indexGeneration": "2026-09-05T12:30:00.001Z",
        "content": content,
        "chunkCount": (len(content) + 1799) // 1800,
    }


def test_complete_code_points_and_generation_are_exact():
    value = RagEmbeddingContextV2.model_validate(context())
    assert "".join(value.chunks) == value.content
    assert list(map(len, value.chunks)) == [1800, 200]
    assert value.batch(0) == value.chunks
    with pytest.raises(ValueError):
        value.batch(1)
    for key in ("referenceId", "contentHash", "indexGeneration"):
        assert key in RagEmbeddingRunInput.model_fields
    assert RagEmbeddingStepInput(batchIndex=6).batchIndex == 6


@pytest.mark.parametrize(
    "change",
    [
        {"chunkCount": 1},
        {"contentHash": "0" * 64},
        {"content": ""},
        {"indexGeneration": "2026-09-05T12:30:00Z"},
        {"indexGeneration": "2026-09-05T20:30:00.001+08:00"},
        {"indexGeneration": "2026-02-30T12:30:00.001Z"},
        {"path": "/不得读取当前文件"},
    ],
)
def test_context_rejects_drift_or_unfrozen_fields(change):
    with pytest.raises(ValidationError):
        RagEmbeddingContextV2.model_validate(context() | change)


@pytest.mark.parametrize(
    "vectors", [[[True]], [[float("nan")]], [[float("inf")]], [[]], [], [[1], [1, 2]]]
)
def test_vectors_are_finite_non_boolean_and_same_dimension(vectors):
    with pytest.raises(ValidationError):
        RagEmbeddingBatchOutput(embeddings=vectors)


def test_capacity_is_rejected_not_truncated():
    with pytest.raises(ValidationError):
        RagEmbeddingContextV2.model_validate(context("😀" * (1800 * 64 + 1)))
    assert RagEmbeddingBatchOutput(embeddings=[[1, -0.5]]).embeddings == [[1, -0.5]]
    with pytest.raises(ValidationError):
        RagEmbeddingBatchOutput(embeddings=[[1] * 4097])


def resolved_model(route, model, *, fingerprint_model=None):
    values = {
        "deploymentProfileKey": "deployment.rag.embedding.v2",
        "provider": "openai_embeddings",
        "model": model,
        "transportProfile": "transport.openai-embeddings.v1",
        "endpointProfile": "endpoint.embedding.v1",
        "structuredOutputRoute": route,
        "capabilityVersion": "capability.openai-embeddings.batch.v1",
        "reasoningMode": "disabled",
        "supportsRequestIdempotency": False,
    }
    values["deploymentFingerprint"] = calculate_resolved_model_fingerprint(
        deployment_profile_key=values["deploymentProfileKey"],
        provider=values["provider"],
        model=model if fingerprint_model is None else fingerprint_model,
        transport_profile=values["transportProfile"],
        endpoint_profile=values["endpointProfile"],
        structured_output_route=route,
        capability_version=values["capabilityVersion"],
        reasoning_mode="disabled",
        supports_request_idempotency=False,
    )
    return values


def test_only_embedding_route_preserves_arbitrary_nonempty_configured_model():
    actual = " 私有模型/" + "名" * 2100 + " "
    embedding = resolved_model("embeddings_v1", actual)
    assert ResolvedModelRef.model_validate(embedding).model == actual
    validator = jsonschema_rs.validator_for(ResolvedModelRef.model_json_schema())
    validator.validate(embedding)
    for route in (
        "responses_json_schema_v1",
        "chat_json_output_v1",
        "quality_strict_tool_v1",
        "plain_text_v1",
    ):
        normal = resolved_model(route, actual)
        with pytest.raises(ValidationError):
            ResolvedModelRef.model_validate(normal)
        with pytest.raises(jsonschema_rs.ValidationError):
            validator.validate(normal)
        assert (
            ResolvedModelRef.model_validate(
                resolved_model(route, "  model  ", fingerprint_model="model")
            ).model
            == "model"
        )
        with pytest.raises(ValidationError):
            ResolvedModelRef.model_validate(resolved_model(route, "   "))
