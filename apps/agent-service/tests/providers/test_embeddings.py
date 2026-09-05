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
