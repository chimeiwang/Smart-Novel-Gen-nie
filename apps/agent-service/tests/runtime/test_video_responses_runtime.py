from __future__ import annotations

import asyncio

import pytest
from inkforge_agents.providers.base import ModelTurnRequest, ModelTurnResult, ModelUsage
from inkforge_agents.providers.embeddings import (
    EmbeddingIdentity,
    EmbeddingRequest,
    EmbeddingResult,
)
from inkforge_agents.providers.video_responses import (
    VideoResponsesIdentity,
    VideoResponsesRequest,
    VideoResponsesResult,
    VideoResponsesUsage,
)
from inkforge_agents.runtime.model_runtime import ModelRuntime


def _turn() -> ModelTurnRequest:
    return ModelTurnRequest(
        messages=[{"role": "user", "content": "完整视频模型请求"}],
        tools=[],
        maxOutputTokens=128,
        policy={"policyId": "video.test.v2", "thinkingMode": "disabled"},
        thinkingMode="disabled",
        structuredOutput={
            "name": "video_test",
            "route": "responses_json_schema_v1",
            "jsonSchema": {"type": "object"},
        },
    )


class Calls:
    def __init__(self):
        self.active = 0
        self.peak = 0
        self.called = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = 0

    async def call(self, name):
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.called.append(name)
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.active -= 1


class Chat:
    billable = True

    def __init__(self, calls):
        self.calls = calls

    async def complete_turn(self, request):
        await self.calls.call("chat")
        return ModelTurnResult(
            content="完成",
            toolCalls=[],
            finishReason="stop",
            rawFinishReason="stop",
            usage=ModelUsage(promptTokens=1, cachedTokens=0, completionTokens=1, totalTokens=2),
        )


class Responses:
    # 测试替身显式使用测试身份，不冒充官方 Adapter。
    identity = VideoResponsesIdentity(
        provider="fake",
        model="fake",
        transport_profile="transport.fake.v1",
        endpoint_profile="endpoint.local-fake.v1",
        capability_version="capability.fake.structured-output.v1",
    )

    def __init__(self, calls):
        self.calls = calls

    async def complete_responses(self, request):
        await self.calls.call("responses")
        return VideoResponsesResult(
            structuredOutput={"result": "完整"},
            diagnostic=None,
            finishReason="stop",
            rawFinishReason="response.completed",
            providerResponseId="resp-test",
            usage=VideoResponsesUsage(inputTokens=3),
            localSchemaSha256="a" * 64,
            wireSchemaSha256="b" * 64,
        )


class Embeddings:
    identity = EmbeddingIdentity(model="test-embedding", endpoint_profile="endpoint.test.v1")

    def __init__(self, calls):
        self.calls = calls

    async def embed_batch(self, request):
        await self.calls.call("embedding")
        return EmbeddingResult([[1.0]], 1)


class NoV1Billing:
    async def authorize(self, *args, **kwargs):
        raise AssertionError("V2 不得调用 V1 授权")

    async def report(self, *args, **kwargs):
        raise AssertionError("V2 不得调用 V1 用量上报")


@pytest.mark.asyncio
async def test_responses_chat_and_embedding_share_same_limiter_and_callback_boundary():
    calls = Calls()
    before = []
    runtime = ModelRuntime(
        Chat(calls),
        responses_provider=Responses(calls),
        embedding_provider=Embeddings(calls),
        billing=NoV1Billing(),
        max_concurrency=1,
    )

    async def begin(name):
        before.append(name)
        return len(before)

    first = asyncio.create_task(
        runtime.run_execution_responses(
            VideoResponsesRequest.from_turn(_turn()),
            before_provider=lambda: begin("responses"),
            lane="batch_media",
        )
    )
    await calls.entered.wait()
    chat = asyncio.create_task(
        runtime.run_execution_turn(_turn(), before_provider=lambda: begin("chat"), lane="creative")
    )
    embedding = asyncio.create_task(
        runtime.run_execution_embedding(
            EmbeddingRequest(texts=["全文"]),
            before_provider=lambda: begin("embedding"),
            lane="batch_media",
        )
    )
    await asyncio.sleep(0)
    assert before == ["responses"] and calls.called == ["responses"]
    calls.release.set()
    first_result, _, _ = await asyncio.gather(first, chat, embedding)
    assert first_result[0] == 1 and first_result[1].providerResponseId == "resp-test"
    assert runtime.responses_identity == Responses.identity
    assert set(calls.called) == {"responses", "chat", "embedding"}
    assert calls.peak == 1 and calls.active == 0


@pytest.mark.asyncio
async def test_cancellation_while_waiting_does_not_cross_provider_receipt_or_leak_slot():
    calls = Calls()
    runtime = ModelRuntime(Chat(calls), responses_provider=Responses(calls), max_concurrency=1)
    before = []

    async def begin():
        before.append(True)
        return 1

    chat = asyncio.create_task(
        runtime.run_execution_turn(_turn(), before_provider=begin, lane="creative")
    )
    await calls.entered.wait()
    pending = asyncio.create_task(
        runtime.run_execution_responses(
            VideoResponsesRequest.from_turn(_turn()), before_provider=begin, lane="batch_media"
        )
    )
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert len(before) == 1 and calls.called == ["chat"]
    calls.release.set()
    await chat
    await runtime.run_execution_responses(
        VideoResponsesRequest.from_turn(_turn()), before_provider=begin, lane="batch_media"
    )
    assert calls.called == ["chat", "responses"] and calls.active == 0


@pytest.mark.asyncio
async def test_active_responses_timeout_cancels_one_call_and_releases_limiter():
    calls = Calls()
    runtime = ModelRuntime(Chat(calls), responses_provider=Responses(calls), max_concurrency=1)

    async def begin():
        return 1

    with pytest.raises(TimeoutError):
        await runtime.run_execution_responses(
            VideoResponsesRequest.from_turn(_turn()),
            before_provider=begin,
            lane="batch_media",
            provider_timeout_seconds=0.01,
        )
    assert calls.called == ["responses"] and calls.cancelled == 1 and calls.active == 0
    calls.release.set()
    await runtime.run_execution_turn(_turn(), before_provider=begin, lane="interactive")
    assert calls.called == ["responses", "chat"]


@pytest.mark.asyncio
async def test_rejected_receipt_never_starts_responses_provider():
    calls = Calls()
    runtime = ModelRuntime(Chat(calls), responses_provider=Responses(calls))

    async def reject():
        raise ValueError("Core 调用前回执拒绝")

    with pytest.raises(ValueError, match="回执拒绝"):
        await runtime.run_execution_responses(
            VideoResponsesRequest.from_turn(_turn()), before_provider=reject, lane="batch_media"
        )
    assert calls.called == [] and calls.active == 0


@pytest.mark.asyncio
async def test_missing_responses_provider_does_not_fallback_to_existing_chat():
    calls = Calls()
    runtime = ModelRuntime(Chat(calls))

    async def begin():
        raise AssertionError("未配置不得先取回执")

    assert runtime.responses_identity is None
    with pytest.raises(ValueError, match="未配置"):
        await runtime.run_execution_responses(
            VideoResponsesRequest.from_turn(_turn()), before_provider=begin, lane="batch_media"
        )
    assert calls.called == []
