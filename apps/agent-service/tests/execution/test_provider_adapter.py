from __future__ import annotations

import json

import httpx
import pytest
from inkforge_agents.config import Settings
from inkforge_agents.execution.executor import ProviderModelRuntimeAdapter
from inkforge_agents.providers.base import ModelTurnRequest, ModelTurnResult
from inkforge_agents.providers.deepseek_v4 import DeepSeekV4Provider
from inkforge_agents.providers.fake import FakeModelProvider

from .support import execution_request


class RecordingIdempotentProvider:
    billable = False
    provider_name = "recording"
    model_name = "recording-v1"
    supports_request_idempotency = True

    def __init__(self) -> None:
        self.requests: list[ModelTurnRequest] = []

    def supports_structured_output(self, route: str) -> bool:
        return route == "chat_json_output_v1"

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.requests.append(request)
        return await FakeModelProvider().complete_turn(request)


@pytest.mark.asyncio
async def test_provider_adapter_passes_exact_execution_idempotency_key() -> None:
    provider = RecordingIdempotentProvider()
    adapter = ProviderModelRuntimeAdapter(provider)  # type: ignore[arg-type]
    contract = execution_request()
    model_request = ModelTurnRequest(
        messages=[{"role": "user", "content": "返回 JSON"}],
        tools=[],
        maxOutputTokens=100,
        policy={"policyId": "test", "thinkingMode": "disabled"},
        structuredOutput={
            "route": "chat_json_output_v1",
            "name": "output",
            "jsonSchema": contract.outputSchema.jsonSchema,
        },
        requestIdempotencyKey=contract.idempotencyKey,
    )

    attempt, _ = await adapter.run_execution_turn(
        model_request,
        before_provider=_first_attempt,
    )

    assert attempt == 1
    assert adapter.supports_request_idempotency is True
    assert provider.requests[0].requestIdempotencyKey == contract.idempotencyKey


@pytest.mark.asyncio
async def test_deepseek_v4_reports_no_idempotency_but_supports_local_strict_json() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "response-1",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"replacement": "改写文本"},
                                ensure_ascii=False,
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "openai_compatible",
            "openai_compatibility_profile": "deepseek_v4",
            "openai_api_key": "test-key",
            "openai_model": "deepseek-v4-flash",
        }
    )
    provider = DeepSeekV4Provider(settings, client=client)
    contract = execution_request()
    model_request = ModelTurnRequest(
        messages=[{"role": "user", "content": "只返回 JSON 对象"}],
        tools=[],
        maxOutputTokens=100,
        policy={"policyId": "test", "thinkingMode": "disabled"},
        structuredOutput={
            "route": "chat_json_output_v1",
            "name": "selection_replacement",
            "jsonSchema": contract.outputSchema.jsonSchema,
        },
        requestIdempotencyKey=contract.idempotencyKey,
    )
    try:
        result = await provider.complete_turn(model_request)
    finally:
        await client.aclose()

    assert provider.supports_request_idempotency is False
    assert provider.supports_structured_output("chat_json_output_v1") is True
    assert result.structuredOutput is not None
    assert result.structuredOutputCorrectionCount == 0
    assert json.loads(requests[0].content)["response_format"] == {"type": "json_object"}
    assert "Idempotency-Key" not in requests[0].headers


async def _first_attempt() -> int:
    return 1
