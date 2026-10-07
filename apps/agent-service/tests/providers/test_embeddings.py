"""独立 embedding HTTP 只发完整本批文本，并诚实保留缺失用量。"""

import json

import httpx
import pytest
from inkforge_agents.providers.embeddings import (
    EmbeddingRequest,
    OpenAIExecutionEmbeddingProvider,
    embedding_endpoint,
    embedding_endpoint_profile,
)


@pytest.mark.asyncio
async def test_one_batch_is_one_http_with_actual_model_and_complete_order():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}],
                "usage": {"prompt_tokens": 12, "total_tokens": 12},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = OpenAIExecutionEmbeddingProvider(
            client, model="自有模型/v2", base_url="https://embedding.example"
        )
        result = await provider.embed_batch(EmbeddingRequest(texts=["\ufeff全文😀\r\n", "下一块"]))
    assert len(calls) == 1
    assert json.loads(calls[0].content) == {
        "model": "自有模型/v2",
        "input": ["\ufeff全文😀\r\n", "下一块"],
    }
    assert str(calls[0].url) == "https://embedding.example/v1/embeddings"
    assert result.embeddings == [[1, 0], [0, 1]]
    assert result.input_tokens == 12 and result.protocol_error is None
    assert provider.identity.model == "自有模型/v2"
    assert provider.identity.endpoint_profile == embedding_endpoint_profile(
        "https://embedding.example"
    )


@pytest.mark.parametrize(
    "base",
    ["https://embedding.example", "https://embedding.example/", "https://embedding.example/v1/"],
)
def test_endpoint_uses_original_configuration_rule(base):
    assert embedding_endpoint(base) == "https://embedding.example/v1/embeddings"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage", [None, {}, {"prompt_tokens": True}, {"prompt_tokens": 3, "total_tokens": 4}]
)
async def test_missing_or_invalid_usage_does_not_erase_valid_vectors(usage):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "data": [{"index": 0, "embedding": [1]}],
                    "usage": usage,
                },
            )
        )
    ) as client:
        provider = OpenAIExecutionEmbeddingProvider(
            client, model="embedding", base_url="https://embedding.example"
        )
        result = await provider.embed_batch(EmbeddingRequest(texts=["完整"]))
    assert result.embeddings == [[1]] and result.input_tokens is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        [{"index": 0, "embedding": [1]}, {"index": 0, "embedding": [2]}],
        [{"index": True, "embedding": [1]}],
        [{"index": 2, "embedding": [1]}],
        [{"index": 0, "embedding": [True]}],
        [{"embedding": [1]}],
        [],
    ],
)
async def test_invalid_index_or_vectors_fail_without_losing_reliable_usage(data):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "data": data,
                    "usage": {"prompt_tokens": 3, "total_tokens": 3},
                },
            )
        )
    ) as client:
        provider = OpenAIExecutionEmbeddingProvider(
            client, model="embedding", base_url="https://embedding.example"
        )
        result = await provider.embed_batch(EmbeddingRequest(texts=["完整"]))
    assert result.embeddings is None and result.protocol_error == "EMBEDDING_OUTPUT_INVALID"
    assert result.input_tokens == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 400])
async def test索引失败保留完整响应及脱敏且不改变结果(status, caplog):
    import logging

    from inkforge_agents.providers.base import ProviderTransportError

    raw = {"data": [{"index": 0, "embedding": [True]}],
        "usage": {"prompt_tokens": 3, "total_tokens": 3},
        "error": "完整索引失败" * 10000 + "actual-embedding-key",
        "reasoning_content": "不可记录的索引思考"}
    async with httpx.AsyncClient(headers={"Authorization": "Bearer actual-embedding-key"},
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=raw))) as client:
        provider = OpenAIExecutionEmbeddingProvider(client, model="embedding",
            base_url="https://embedding.example")
        with caplog.at_level(logging.WARNING):
            if status == 400:
                with pytest.raises(ProviderTransportError) as caught:
                    await provider.embed_batch(EmbeddingRequest(texts=["正常输入不得另存"]))
                details = caught.value.details.model_dump_json()
            else:
                result = await provider.embed_batch(EmbeddingRequest(texts=["正常输入不得另存"]))
                assert result.protocol_error == "EMBEDDING_OUTPUT_INVALID"
                assert result.input_tokens == 3
                details = caplog.text
    assert "完整索引失败" * 10000 in details
    assert "actual-embedding-key" not in details
    assert "不可记录的索引思考" not in details
    assert "正常输入不得另存" not in details


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["timeout", "json"])
async def test索引网络和成功无效JSON保留原失败详情(failure_kind):
    from inkforge_agents.providers.base import ProviderProtocolError, ProviderTransportError

    def handle(request):
        if failure_kind == "timeout":
            raise httpx.ReadTimeout("连接失败actual-embedding-key", request=request)
        return httpx.Response(200, text="完整坏JSON actual-embedding-key")

    async with httpx.AsyncClient(headers={"Authorization": "Bearer actual-embedding-key"},
        transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIExecutionEmbeddingProvider(client, model="embedding",
            base_url="https://embedding.example")
        with pytest.raises((ProviderProtocolError, ProviderTransportError)) as caught:
            await provider.embed_batch(EmbeddingRequest(texts=["正常输入"]))
    assert caught.value.code == ("timeout_error" if failure_kind == "timeout"
        else "invalid_response_json")
    assert caught.value.details.exceptionChain
    if failure_kind == "json":
        assert "完整坏JSON" in caught.value.details.responseBody
    assert "actual-embedding-key" not in caught.value.details.model_dump_json()
    assert caught.value.__context__ is None


@pytest.mark.asyncio
async def test索引诊断sink故障不改变失败结果(monkeypatch):
    from inkforge_agents.providers import embeddings as module

    def reject_sink(*args, **kwargs):
        raise RuntimeError("日志sink失败")

    monkeypatch.setattr(module.logger, "warning", reject_sink)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200,
        json={"data": [], "usage": {"prompt_tokens": 5, "total_tokens": 5}}))) as client:
        result = await OpenAIExecutionEmbeddingProvider(client, model="embedding",
            base_url="https://embedding.example").embed_batch(EmbeddingRequest(texts=["正文"]))
    assert result.protocol_error == "EMBEDDING_OUTPUT_INVALID"
    assert result.input_tokens == 5
