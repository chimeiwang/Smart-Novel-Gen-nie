"""索引每批一个独立执行；真实身份、未知用量和 journal 恢复不借用聊天。"""

import asyncio
import hashlib
from dataclasses import replace
from types import MappingProxyType

import pytest
from inkforge_agents.execution.executor import (
    ExecutionCapabilityError,
    StatelessExecutionStepExecutor,
)
from inkforge_agents.execution.registry import load_execution_registry
from inkforge_agents.execution.service import ExecutionService
from inkforge_agents.providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelTurnRequest,
    ProviderTransportError,
)
from inkforge_agents.providers.embeddings import (
    EmbeddingIdentity,
    EmbeddingRequest,
    EmbeddingResult,
    embedding_endpoint_profile,
)
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_contracts.execution import (
    EvidenceManifest,
    EvidenceManifestItem,
    ModelProfileRef,
    OutputSchemaRef,
    PromptProfileRef,
    StepBudget,
    canonical_execution_json_bytes,
    canonical_execution_sha256,
)

from .support import rehash_request
from .test_portrait import portrait_request
from .test_service import RecordingCallbacks, _journal

MODEL = " 私有嵌入模型/v2 "
BASE = "https://embedding.example"


def registry(*, enabled=True, model=MODEL, base=BASE):
    original = load_execution_registry(environment="test").with_rag_embedding_config(model, base)
    return replace(
        original,
        operations=MappingProxyType(
            {
                key: replace(value, v2_enabled=enabled) if key == "rag.embedding" else value
                for key, value in original.operations.items()
            }
        ),
    )


def request(batch=0, *, count=11):
    operation = registry().resolve("rag", "embedding")
    profile, schema, budget = (
        operation.generator_profile,
        operation.output_schema,
        operation.generator_step_budget,
    )
    template = portrait_request()
    content = "\ufeff😀\r\n" * (450 * count)
    context = {
        "referenceId": "reference-1",
        "contentHash": hashlib.sha256(content.encode()).hexdigest(),
        "indexGeneration": "2026-09-05T12:00:00.001Z",
        "content": content,
        "chunkCount": count,
    }
    item = template.evidenceBundle.items[0].model_copy(
        update={
            "resourceType": "rag_embedding_context",
            "resourceId": "reference-1",
            "contentJson": context,
            "contentSha256": canonical_execution_sha256(context),
            "byteCount": len(canonical_execution_json_bytes(context)),
        }
    )
    manifest = EvidenceManifest(
        bundleId=item.bundleId,
        bundleVersion=1,
        itemCount=1,
        items=[
            EvidenceManifestItem(
                itemId=item.id,
                **item.model_dump(exclude={"id", "bundleId", "contentJson", "contentText"}),
            )
        ],
    )
    bundle = template.evidenceBundle.model_copy(
        update={
            "policyVersion": "evidence.rag.reference_chunks.v1",
            "items": [item],
            "manifest": manifest,
            "manifestSha256": canonical_execution_sha256(
                manifest.model_dump(mode="json", exclude_none=True)
            ),
            "totalBytes": item.byteCount,
        }
    )
    return rehash_request(
        template.model_copy(
            update={
                "novelId": "novel-1",
                "workflow": "rag",
                "operation": "embedding",
                "input": {"batchIndex": batch},
                "evidenceBundle": bundle,
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
                    maxModelCalls=1,
                    maxInputTokens=budget.max_input_tokens,
                    maxPromptCacheMissTokens=budget.max_prompt_cache_miss_tokens,
                    maxCompletionTokens=0,
                    maxReasoningTokens=0,
                    maxVisibleOutputTokens=0,
                    maxCostMicros=budget.max_cost_micros,
                    maxWallClockSeconds=budget.max_wall_clock_seconds,
                    maxProviderRetries=budget.max_provider_retries,
                    maxProtocolCorrections=0,
                ),
            }
        )
    )


class Embedding:
    identity = EmbeddingIdentity(MODEL, embedding_endpoint_profile(BASE))

    def __init__(self, *, tokens=100, invalid=False):
        self.requests = []
        self.tokens = tokens
        self.invalid = invalid

    async def embed_batch(self, batch):
        self.requests.append(batch)
        if self.invalid:
            return EmbeddingResult(None, self.tokens, "EMBEDDING_OUTPUT_INVALID")
        return EmbeddingResult([[1, -0.5] for _ in batch.texts], self.tokens)


def executor(provider):
    runtime = ModelRuntime(FakeModelProvider(), embedding_provider=provider, max_concurrency=1)
    return StatelessExecutionStepExecutor(
        runtime, embedding=runtime, max_output_tokens=1, retry_base_seconds=0
    )


async def execute(provider, execution_request):
    value = executor(provider)
    resolved = value.resolve(execution_request, registry())

    async def attempt():
        return 1

    model_request = value.build_model_request(execution_request, resolved)
    outcome = await value.call_provider(
        execution_request, model_request, begin_attempt=attempt, cancel_event=asyncio.Event()
    )
    return value.terminal_from_outcome(execution_request, resolved, outcome)


@pytest.mark.asyncio
async def test_all_64_chunks_are_seven_exact_single_call_batches():
    provider = Embedding()
    for index in range(7):
        terminal = await execute(provider, request(index, count=64))
        assert len(terminal.output["embeddings"]) == (10 if index < 6 else 4)
        assert terminal.resolvedModel.model == MODEL
        assert terminal.resolvedModel.provider == "openai_embeddings"
        assert terminal.resolvedModel.structuredOutputRoute == "embeddings_v1"
        assert terminal.usage.providerAttempts == 1 and terminal.usage.protocolCorrections == 0
        assert terminal.usage.inputTokens == 100
        assert (
            terminal.usage.cachedTokens
            is terminal.usage.promptCacheMissTokens
            is terminal.usage.costMicros
            is None
        )
        assert (
            terminal.usage.completionTokens
            == terminal.usage.reasoningTokens
            == terminal.usage.visibleOutputTokens
            == 0
        )
    assert len(provider.requests) == 7
    assert all(isinstance(item, EmbeddingRequest) for item in provider.requests)
    assert "".join(text for item in provider.requests for text in item.texts) == "\ufeff😀\r\n" * (
        450 * 64
    )


@pytest.mark.asyncio
async def test_valid_vectors_with_absent_usage_remain_success_with_unknown_facts():
    terminal = await execute(Embedding(tokens=None), request(count=1))
    assert terminal.output == {"embeddings": [[1, -0.5]]}
    assert terminal.usage.usageStatus == "unknown"
    assert (
        terminal.usage.inputTokens
        is terminal.usage.completionTokens
        is terminal.usage.costMicros
        is None
    )


@pytest.mark.asyncio
async def test_invalid_vectors_preserve_usage_without_correction():
    provider = Embedding(invalid=True)
    terminal = await execute(provider, request(count=1))
    assert terminal.errorCode == "EMBEDDING_OUTPUT_INVALID"
    assert terminal.usage.inputTokens == 100 and terminal.usage.protocolCorrections == 0
    assert len(provider.requests) == 1


def test_configuration_binding_is_exact_and_retained_is_not_new_admission():
    value = executor(Embedding())
    current = request(count=1)
    for configured in [
        registry(model="其他模型"),
        registry(base="https://other.example"),
        registry(model=None),
        registry(enabled=False),
    ]:
        with pytest.raises(ExecutionCapabilityError):
            value.resolve(current, configured)
    assert (
        value.resolve(
            current.model_copy(update={"dispatchMode": "pending_recovery"}), registry(enabled=False)
        ).profile.key
        == "rag.embedding.v2"
    )
    for changes in [
        {"novelId": None},
        {"input": {"batchIndex": 1}},
        {"input": {"batchIndex": 0, "text": "伪造"}},
        {"purpose": "protocol_correction"},
    ]:
        with pytest.raises(ExecutionCapabilityError):
            value.resolve(rehash_request(current.model_copy(update=changes)), registry())


@pytest.mark.asyncio
async def test_embedding_completed_journal_never_reissues_http():
    provider, callbacks = Embedding(), RecordingCallbacks()
    current = request(count=1)
    journal = _journal(prefix="test:rag:replay")
    service = ExecutionService(
        journal=journal, registry=registry(), executor=executor(provider), callbacks=callbacks
    )
    await service.submit(current)
    await service.wait_idle()
    assert len(provider.requests) == len(callbacks.results) == 1
    replay_provider = Embedding()
    restarted = ExecutionService(
        journal=journal,
        registry=registry(),
        executor=executor(replay_provider),
        callbacks=RecordingCallbacks(),
    )
    await restarted.submit(current)
    await restarted.wait_idle()
    assert replay_provider.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "status", "attempts", "expected"),
    [
        ("timeout_error", None, 1, "MODEL_OUTCOME_UNKNOWN"),
        ("http_error", 500, 1, "MODEL_OUTCOME_UNKNOWN"),
        ("http_error", 429, 3, "MODEL_PROVIDER_RETRY_EXHAUSTED"),
        ("http_error", 400, 1, "MODEL_PROVIDER_REJECTED"),
    ],
)
async def test_embedding_never_inherits_chat_provider_idempotency(code, status, attempts, expected):
    class BrokenEmbedding(Embedding):
        async def embed_batch(self, batch):
            self.requests.append(batch)
            raise ProviderTransportError(code=code, statusCode=status, requestId=None)

    provider = BrokenEmbedding()
    value = executor(provider)
    current = request(count=1)
    resolved = value.resolve(current, registry())
    started = 0

    async def attempt():
        nonlocal started
        started += 1
        return started

    outcome = await value.call_provider(
        current,
        value.build_model_request(current, resolved),
        begin_attempt=attempt,
        cancel_event=asyncio.Event(),
    )
    terminal = value.terminal_from_outcome(current, resolved, outcome)
    assert terminal.errorCode == expected
    assert terminal.usage.providerAttempts == len(provider.requests) == attempts
    assert terminal.resolvedModel.supportsRequestIdempotency is False


@pytest.mark.asyncio
async def test_embedding_and_chat_share_one_limiter_and_waiting_cancellation_is_zero_call():
    started, release = asyncio.Event(), asyncio.Event()

    class BlockingChat(FakeModelProvider):
        async def complete_turn(self, turn):
            started.set()
            await release.wait()
            return await super().complete_turn(turn)

    provider = Embedding()
    runtime = ModelRuntime(BlockingChat(), embedding_provider=provider, max_concurrency=1)
    value = StatelessExecutionStepExecutor(runtime, embedding=runtime, max_output_tokens=1)
    calls = []

    async def chat_attempt():
        calls.append("chat")
        return 1

    async def embedding_attempt():
        calls.append("embedding")
        return 1

    chat = asyncio.create_task(
        runtime.run_execution_turn(
            ModelTurnRequest(
                messages=[ModelMessage(role="user", content="正文")],
                tools=[],
                maxOutputTokens=1,
                policy=ModelExecutionPolicy(policyId="test", thinkingMode="disabled"),
            ),
            before_provider=chat_attempt,
            lane="creative",
        )
    )
    await asyncio.wait_for(started.wait(), 1)
    current = request(count=1)
    resolved = value.resolve(current, registry())
    cancel = asyncio.Event()
    embedding_call = asyncio.create_task(
        value.call_provider(
            current,
            value.build_model_request(current, resolved),
            begin_attempt=embedding_attempt,
            cancel_event=cancel,
        )
    )
    await asyncio.sleep(0.01)
    assert calls == ["chat"] and provider.requests == []
    cancel.set()
    outcome = await asyncio.wait_for(embedding_call, 1)
    terminal = value.terminal_from_outcome(
        current, resolved, outcome, cancel_request_id="cancel-rag-1"
    )
    assert terminal.errorCode == "RUN_CANCELLED" and terminal.usage.providerAttempts == 0
    release.set()
    await chat
    outcome = await value.call_provider(
        current,
        value.build_model_request(current, resolved),
        begin_attempt=embedding_attempt,
        cancel_event=asyncio.Event(),
    )
    assert value.terminal_from_outcome(current, resolved, outcome).output == {
        "embeddings": [[1, -0.5]]
    }
    assert calls == ["chat", "embedding"]


@pytest.mark.asyncio
async def test_missing_started_embedding_journal_never_reissues_http():
    current = request(count=1)
    replay_provider = Embedding()
    missing_callbacks = RecordingCallbacks()
    missing = ExecutionService(
        journal=_journal(prefix="test:rag:missing"),
        registry=registry(),
        executor=executor(replay_provider),
        callbacks=missing_callbacks,
    )
    await missing.submit(current.model_copy(update={"dispatchMode": "running_recovery"}))
    await missing.wait_idle()
    assert missing_callbacks.failures[0].errorCode == "MODEL_OUTCOME_UNKNOWN"
    assert replay_provider.requests == []
