from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest
from inkforge_agents.config import Settings
from inkforge_agents.providers.base import ModelTurnRequest, ProviderTransportError
from inkforge_agents.providers.deepseek_v4 import (
    DeepSeekV4Provider,
    _project_deepseek_strict_schema,
)
from inkforge_agents.runtime.model_policy import (
    CREATIVE_HIGH,
    LEGACY_PROVIDER_DEFAULT,
    QUALITY_NO_THINKING,
    REVIEWER_NO_THINKING,
)
from inkforge_agents.tools.control import QualityReportArgs

FIXTURES = Path(__file__).parent.parent / "fixtures" / "deepseek_v4"


def _response_with_usage(usage: object) -> dict[str, Any]:
    return {
        "id": "resp-usage",
        "choices": [
            {
                "message": {"role": "assistant", "content": "完成"},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


def _settings(
    base_url: str = "https://api.deepseek.com",
    *,
    strict_base_url: str | None = None,
) -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "model_provider": "openai_compatible",
            "openai_compatibility_profile": "deepseek_v4",
            "openai_api_key": "test-key",
            "openai_base_url": base_url,
            "openai_strict_base_url": strict_base_url,
            "openai_model": "deepseek-v4-flash",
        }
    )


def _request(
    *,
    policy: Any = LEGACY_PROVIDER_DEFAULT,
    tool_name: str = "lookup",
    strict: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> ModelTurnRequest:
    return ModelTurnRequest(
        messages=[{"role": "user", "content": "请调用工具"}],
        tools=tools
        or [
            {
                "name": tool_name,
                "description": "查询资料",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
                "strict": strict,
            }
        ],
        maxOutputTokens=256,
        policy=policy,
    )


def _provider(
    base_url: str = "https://api.deepseek.com",
    *,
    strict_base_url: str | None = None,
    response: dict[str, Any] | None = None,
    status_code: int = 200,
) -> tuple[
    DeepSeekV4Provider,
    list[httpx.Request],
    httpx.AsyncClient,
]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = response or {
            "id": "resp-1",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "完成"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "prompt_cache_hit_tokens": 0,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }
        return httpx.Response(status_code, json=body, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        DeepSeekV4Provider(_settings(base_url, strict_base_url=strict_base_url), client=client),
        requests,
        client,
    )


@pytest.mark.asyncio
async def test_default_client_waits_up_to_300_seconds_for_response() -> None:
    provider = DeepSeekV4Provider(_settings())
    try:
        timeout = provider._client.timeout
        assert timeout.connect == 10
        assert timeout.read == 300
        assert timeout.write == 60
        assert timeout.pool == 60
    finally:
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
        ("https://api.deepseek.com/", "https://api.deepseek.com/chat/completions"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/chat/completions"),
        ("https://api.deepseek.com/v1/", "https://api.deepseek.com/chat/completions"),
        ("https://proxy.example/llm/v1/", "https://proxy.example/llm/v1/chat/completions"),
    ],
)
async def test_deepseek_endpoint_normalizes_official_and_preserves_proxy_prefix(
    base_url: str,
    expected: str,
) -> None:
    provider, requests, client = _provider(base_url)
    try:
        await provider.complete_turn(_request())
    finally:
        await client.aclose()
    assert str(requests[0].url) == expected


@pytest.mark.asyncio
async def test_quality_strict_request_uses_beta_endpoint_and_strict_wire() -> None:
    provider, requests, client = _provider()
    try:
        await provider.complete_turn(
            _request(policy=QUALITY_NO_THINKING, tool_name="submit_quality_report", strict=True)
        )
    finally:
        await client.aclose()

    assert str(requests[0].url) == "https://api.deepseek.com/beta/chat/completions"
    payload = json.loads(requests[0].content)
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_quality_report"},
    }
    assert payload["tools"][0]["function"]["strict"] is True
    assert "parallel_tool_calls" not in payload


@pytest.mark.asyncio
async def test普通工具仍使用标准端点且不发送_strict字段() -> None:
    provider, requests, client = _provider()
    try:
        await provider.complete_turn(_request(tool_name="lookup", strict=False))
    finally:
        await client.aclose()

    payload = json.loads(requests[0].content)
    assert str(requests[0].url) == "https://api.deepseek.com/chat/completions"
    assert "strict" not in payload["tools"][0]["function"]


@pytest.mark.asyncio
async def test_strict_and_non_strict_tools_fail_before_http_request() -> None:
    provider, requests, client = _provider()
    try:
        with pytest.raises(ValueError, match="不能混用"):
            await provider.complete_turn(
                _request(
                    tools=[
                        {
                            "name": "lookup",
                            "description": "查询资料",
                            "parameters": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "submit_quality_report",
                            "description": "提交质量报告",
                            "parameters": {"type": "object", "properties": {}},
                            "strict": True,
                        },
                    ]
                )
            )
    finally:
        await client.aclose()
    assert requests == []


@pytest.mark.asyncio
async def test_strict_request_with_custom_normal_base_url_fails_before_http_request() -> None:
    provider, requests, client = _provider("https://proxy.example/llm/v1")
    try:
        with pytest.raises(ValueError, match="OPENAI_STRICT_BASE_URL"):
            await provider.complete_turn(
                _request(policy=QUALITY_NO_THINKING, tool_name="submit_quality_report", strict=True)
            )
    finally:
        await client.aclose()
    assert requests == []


@pytest.mark.asyncio
async def test_strict_request_uses_explicit_custom_strict_base_url() -> None:
    provider, requests, client = _provider(
        "https://proxy.example/llm/v1",
        strict_base_url="https://strict-proxy.example/deepseek/beta",
    )
    try:
        await provider.complete_turn(
            _request(policy=QUALITY_NO_THINKING, tool_name="submit_quality_report", strict=True)
        )
    finally:
        await client.aclose()
    assert str(requests[0].url) == "https://strict-proxy.example/deepseek/beta/chat/completions"


def test_deepseek_strict_schema_projection_is_deterministic_and_non_mutating() -> None:
    original = QualityReportArgs.model_json_schema()
    original_snapshot = deepcopy(original)

    projected = _project_deepseek_strict_schema(original)

    assert original == original_snapshot
    assert projected["required"] == list(projected["properties"])
    assert projected["additionalProperties"] is False
    issue = projected["$defs"]["ConsistencyIssue"]
    assert issue["required"] == list(issue["properties"])
    assert issue["additionalProperties"] is False

    forbidden = {"title", "default", "minLength", "maxLength", "minItems", "maxItems"}

    def assert_projected(node: object) -> None:
        if isinstance(node, dict):
            assert forbidden.isdisjoint(node)
            if node.get("type") == "object" and "properties" in node:
                assert node["required"] == list(node["properties"])
                assert node["additionalProperties"] is False
            for value in node.values():
                assert_projected(value)
        elif isinstance(node, list):
            for value in node:
                assert_projected(value)

    assert_projected(projected)


@pytest.mark.parametrize(
    "base_url", ["https://api.deepseek.com/v1?x=1", "https://proxy.example/v1#fragment"]
)
def test_deepseek_rejects_base_url_query_or_fragment(base_url: str) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    with pytest.raises(ValueError, match="query|fragment"):
        DeepSeekV4Provider(_settings(base_url), client=client)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://proxy.example/proxy/../openai",
        "https://proxy.example/proxy/%2e%2e/openai",
        "https://proxy.example/proxy/%5c..%5c/openai",
        "https://proxy.example/proxy//openai",
        "https://proxy.example//proxy/openai",
    ],
)
def test_deepseek_rejects_ambiguous_custom_base_url_path(base_url: str) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    with pytest.raises(ValueError, match="路径"):
        DeepSeekV4Provider(_settings(base_url), client=client)


@pytest.mark.asyncio
async def test_deepseek_accepts_a_single_slash_custom_prefix() -> None:
    provider, _, client = _provider("https://proxy.example/proxy/openai")
    assert provider._endpoint == "https://proxy.example/proxy/openai/chat/completions"
    # 注入的测试 client 不由 Provider 所有，显式关闭避免测试资源泄漏。
    await client.aclose()


@pytest.mark.asyncio
async def test_http_error_does_not_expose_response_body() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            500,
            content=b'{"error":"sk-secret prompt\xe6\x8f\x90\xe7\xa4\xba"}',
            headers={"x-request-id": "deepseek-request-500"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DeepSeekV4Provider(_settings(), client=client)
    try:
        with pytest.raises(ProviderTransportError) as error:
            await provider.complete_turn(_request())
    finally:
        await client.aclose()
    assert error.value.code == "http_error"
    assert error.value.statusCode == 500
    assert error.value.requestId == "deepseek-request-500"
    assert "sk-secret" not in repr(error.value)
    assert "提示" not in repr(error.value)
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_factory", "expected_code"),
    [
        (lambda request: httpx.ReadTimeout("SECRET_TIMEOUT", request=request), "timeout_error"),
        (
            lambda request: httpx.RemoteProtocolError("SECRET_PROTOCOL_BODY", request=request),
            "connection_error",
        ),
    ],
)
async def test_transport_error_is_classified_without_private_message(
    error_factory: Any,
    expected_code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_factory(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DeepSeekV4Provider(_settings(), client=client)
    try:
        with pytest.raises(ProviderTransportError) as caught:
            await provider.complete_turn(_request())
    finally:
        await client.aclose()

    assert caught.value.code == expected_code
    assert caught.value.statusCode is None
    assert caught.value.requestId is None
    assert "SECRET" not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "choices",
    [[], [{"message": {"content": "a"}}, {"message": {"content": "b"}}]],
)
@pytest.mark.asyncio
async def test_deepseek_requires_exactly_one_choice(choices: list[dict[str, Any]]) -> None:
    body = _response_with_usage({"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
    body["choices"] = choices
    provider, _, client = _provider(response=body)
    try:
        with pytest.raises(ValueError, match="choices.*恰好一个"):
            await provider.complete_turn(_request())
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"completion_tokens": 1, "total_tokens": 2},
        {"prompt_tokens": 1, "total_tokens": 2},
        {"prompt_tokens": 1, "completion_tokens": 1},
        {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3},
        {
            "prompt_tokens": 2,
            "completion_tokens": 1,
            "total_tokens": 3,
            "prompt_cache_hit_tokens": 1,
            "prompt_cache_miss_tokens": True,
        },
        {
            "prompt_tokens": 1,
            "prompt_cache_hit_tokens": True,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
        {
            "prompt_tokens": 1,
            "prompt_cache_hit_tokens": -1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
        {
            "prompt_tokens": 2,
            "prompt_cache_hit_tokens": 1,
            "prompt_cache_miss_tokens": 0,
            "completion_tokens": 1,
            "total_tokens": 3,
        },
        {
            "prompt_tokens": 2,
            "completion_tokens": 1,
            "total_tokens": 3,
            "prompt_cache_hit_tokens": 1,
            "prompt_cache_miss_tokens": 1,
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
        {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "prompt_cache_hit_tokens": None,
        },
        {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "prompt_cache_miss_tokens": None,
        },
        {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "completion_tokens_details": {"reasoning_tokens": None},
        },
        {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "reasoning_tokens": None,
        },
    ],
)
@pytest.mark.asyncio
async def test_deepseek_rejects_missing_invalid_or_inconsistent_usage(usage: object) -> None:
    provider, _, client = _provider(response=_response_with_usage(usage))
    try:
        with pytest.raises(ValueError, match="用量"):
            await provider.complete_turn(_request())
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_deepseek_requires_prompt_cache_hit_tokens() -> None:
    provider, _, client = _provider(
        response=_response_with_usage(
            {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        )
    )
    try:
        with pytest.raises(ValueError, match="prompt_cache_hit_tokens"):
            await provider.complete_turn(_request())
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_deepseek_converts_invalid_utf8_to_sanitized_protocol_error() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"\xff\xfe", request=request)
        )
    )
    provider = DeepSeekV4Provider(_settings(), client=client)
    try:
        with pytest.raises(ValueError, match="JSON|协议") as error:
            await provider.complete_turn(_request())
    finally:
        await client.aclose()
    assert "UnicodeDecodeError" not in str(error.value)
    assert "\\xff" not in str(error.value)


@pytest.mark.asyncio
async def test_enabled_policy_serializes_thinking_without_forbidden_parameters() -> None:
    provider, requests, client = _provider()
    try:
        await provider.complete_turn(_request(policy=CREATIVE_HIGH))
    finally:
        await client.aclose()
    payload = json.loads(requests[0].content)
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"
    assert "tool_choice" not in payload
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert payload["max_tokens"] == 256 and payload["tools"][0]["type"] == "function"


@pytest.mark.asyncio
async def test_disabled_policy_serializes_named_tool_choice() -> None:
    provider, requests, client = _provider()
    try:
        await provider.complete_turn(_request(policy=REVIEWER_NO_THINKING))
    finally:
        await client.aclose()
    payload = json.loads(requests[0].content)
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_evaluation"},
    }


@pytest.mark.asyncio
async def test_provider_default_does_not_send_deepseek_policy_parameters() -> None:
    provider, requests, client = _provider()
    try:
        await provider.complete_turn(_request())
    finally:
        await client.aclose()
    assert set(json.loads(requests[0].content)) == {"model", "messages", "max_tokens", "tools"}


@pytest.mark.asyncio
async def test_tool_call_fixture_preserves_reasoning_and_usage_diagnostics() -> None:
    fixture = json.loads((FIXTURES / "tool_call.json").read_text(encoding="utf-8"))
    provider, requests, client = _provider(response=fixture)
    try:
        result = await provider.complete_turn(_request(policy=CREATIVE_HIGH))
    finally:
        await client.aclose()
    assert len(requests) == 1
    assert result.content == "" and result.reasoningContent == "先查资料，再继续写作。"
    assert result.providerResponseId == "resp-tool-1"
    assert result.toolCalls[0].id == "call-1" and result.toolCalls[0].name == "lookup"
    assert result.toolCalls[0].arguments == {"query": "世界观"}
    assert result.usage.promptTokens == 100 and result.usage.cachedTokens == 70
    assert result.usage.completionTokens == 40 and result.usage.totalTokens == 140
    assert result.diagnostics.promptCacheMissTokens == 30
    assert result.diagnostics.reasoningTokens == 12
    assert result.diagnostics.providerUsageKeys == sorted(result.diagnostics.providerUsageKeys)


@pytest.mark.asyncio
async def test_invalid_tool_arguments_fail_before_registry_validation() -> None:
    fixture = json.loads((FIXTURES / "invalid_tool_call.json").read_text(encoding="utf-8"))
    provider, _, client = _provider(response=fixture)
    try:
        with pytest.raises(ValueError, match="JSON|对象|工具名称"):
            await provider.complete_turn(_request(policy=CREATIVE_HIGH))
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_insufficient_system_resource_is_preserved_as_normalized_and_raw_reason() -> None:
    fixture = json.loads((FIXTURES / "insufficient_resource.json").read_text(encoding="utf-8"))
    provider, _, client = _provider(response=fixture)
    try:
        result = await provider.complete_turn(_request())
    finally:
        await client.aclose()
    assert result.finishReason == "insufficient_system_resource"
    assert result.rawFinishReason == "insufficient_system_resource"


@pytest.mark.asyncio
async def test_assistant_reasoning_content_is_replayed_in_second_request() -> None:
    responses = [
        {
            "id": "resp-1",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "需要先查资料",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "prompt_cache_hit_tokens": 0,
                "completion_tokens": 2,
                "total_tokens": 3,
            },
        },
        {
            "id": "resp-2",
            "choices": [
                {"message": {"role": "assistant", "content": "完成"}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 3,
                "prompt_cache_hit_tokens": 0,
                "completion_tokens": 1,
                "total_tokens": 4,
            },
        },
    ]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=responses[len(requests) - 1], request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DeepSeekV4Provider(_settings(), client=client)
    try:
        first = await provider.complete_turn(_request(policy=CREATIVE_HIGH))
        await provider.complete_turn(
            ModelTurnRequest(
                messages=[
                    {"role": "user", "content": "请调用工具"},
                    {
                        "role": "assistant",
                        "content": first.content,
                        "reasoningContent": first.reasoningContent,
                        "toolCalls": [call.model_dump() for call in first.toolCalls],
                    },
                    {"role": "tool", "toolCallId": "call-1", "name": "lookup", "content": "{}"},
                ],
                tools=_request().tools,
                maxOutputTokens=256,
                policy=CREATIVE_HIGH,
            )
        )
    finally:
        await client.aclose()
    second_payload = json.loads(requests[1].content)
    assert second_payload["messages"][1]["reasoning_content"] == "需要先查资料"
    assert second_payload["messages"][1]["tool_calls"][0]["function"]["arguments"] == "{}"


@pytest.mark.asyncio
async def test_http_error_is_single_request() -> None:
    provider, requests, client = _provider(response={"error": {"message": "bad"}}, status_code=429)
    try:
        with pytest.raises(ProviderTransportError) as caught:
            await provider.complete_turn(_request())
    finally:
        await client.aclose()
    assert len(requests) == 1
    assert caught.value.code == "http_error"
    assert caught.value.statusCode == 429


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [301, 302, 307])
async def test_http_redirect_with_valid_model_json_is_rejected_without_body_leak(
    status_code: int,
) -> None:
    provider, _, client = _provider(
        response={
            "id": "redirect-secret-response-body",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "不应解析"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "prompt_cache_hit_tokens": 0,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        },
        status_code=status_code,
    )
    try:
        with pytest.raises(ProviderTransportError) as error:
            await provider.complete_turn(_request())
    finally:
        await client.aclose()
    assert "redirect-secret-response-body" not in str(error.value)
    assert "不应解析" not in str(error.value)
    assert error.value.statusCode == status_code
