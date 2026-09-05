from __future__ import annotations

import json
from copy import deepcopy

import httpx
import pytest
from inkforge_agents.config import Settings
from inkforge_agents.providers import video_responses as provider_module
from inkforge_agents.providers.base import (
    ModelTurnRequest,
    ProviderProtocolError,
    ProviderTransportError,
)
from inkforge_agents.providers.video_responses import (
    DeepSeekVideoResponsesProvider,
    VideoResponsesRequest,
    VideoResponsesUsage,
)


def request() -> VideoResponsesRequest:
    return VideoResponsesRequest.from_turn(
        ModelTurnRequest(
            messages=[
                {"role": "system", "content": "固定视频阶段说明。"},
                {"role": "user", "content": "完整冻结原文😀\r\n结尾。"},
            ],
            tools=[],
            maxOutputTokens=321,
            thinkingMode="disabled",
            parallelToolCalls=False,
            policy={"policyId": "video.test.v2", "thinkingMode": "disabled"},
            structuredOutput={
                "route": "responses_json_schema_v1",
                "name": "video_test_v2",
                "jsonSchema": {
                    "type": "object",
                    "properties": {"value": {"type": "integer", "minimum": 1}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            },
        )
    )


def settings(**values: object) -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "openai_api_key": "test-only-key",
            "openai_base_url": "https://api.deepseek.com/v1",
            "openai_model": "deepseek-v4-flash",
            **values,
        }
    )


def payload(**changes: object) -> dict[str, object]:
    return {
        "id": "resp-video-1",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": '{"value":2}'}],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_tokens_details": {"cached_tokens": 30},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
        **changes,
    }


@pytest.mark.asyncio
async def test_responses_exact_wire_nullable_usage_and_schema_audit():
    calls = []

    def handle(incoming):
        calls.append(incoming)
        return httpx.Response(200, json=payload())

    value = request()
    original = value.model_dump(mode="json")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = DeepSeekVideoResponsesProvider(settings(), http=http)
        result = await provider.complete_responses(value)
    assert len(calls) == 1 and str(calls[0].url) == "https://api.deepseek.com/responses"
    body = json.loads(calls[0].content)
    assert set(body) == {"model", "input", "max_output_tokens", "text", "reasoning"}
    assert body["model"] == "deepseek-v4-flash" and body["max_output_tokens"] == 321
    assert body["input"] == [
        {"type": "message", "role": message["role"], "content": message["content"]}
        for message in original["messages"]
    ]
    assert body["reasoning"] == {"effort": "none"}
    assert set(body["text"]["format"]) == {"type", "name", "schema"}
    assert "minimum" not in body["text"]["format"]["schema"]["properties"]["value"]
    assert calls[0].headers["authorization"] == "Bearer test-only-key"
    assert "idempotency-key" not in calls[0].headers
    assert value.model_dump(mode="json") == original
    assert result.structuredOutput == {"value": 2} and result.diagnostic is None
    assert result.providerResponseId == "resp-video-1"
    assert result.finishReason == "stop" and result.rawFinishReason == "response.completed"
    assert result.localSchemaSha256 != result.wireSchemaSha256
    assert len(result.localSchemaSha256) == len(result.wireSchemaSha256) == 64
    assert result.usage.model_dump() == {
        "inputTokens": 100,
        "cachedTokens": 30,
        "promptCacheMissTokens": 70,
        "completionTokens": 20,
        "reasoningTokens": 0,
        "visibleOutputTokens": 20,
        "totalTokens": 120,
        "costMicros": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": "100", "output_tokens": True},
        {"input_tokens": 100, "output_tokens": 20, "total_tokens": 121},
    ],
)
async def test_missing_invalid_or_contradictory_usage_is_not_filled_with_zero(usage):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload(usage=usage)))
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.structuredOutput == {"value": 2}
    assert all(value is None for value in result.usage.model_dump().values())


@pytest.mark.asyncio
async def test_known_tokens_survive_missing_details_without_inferred_reasoning_zero():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json=payload(usage={"input_tokens": 100, "output_tokens": 20})
            )
        )
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.usage.inputTokens == 100 and result.usage.completionTokens == 20
    assert result.usage.cachedTokens is result.usage.promptCacheMissTokens is None
    assert result.usage.reasoningTokens is result.usage.visibleOutputTokens is None
    assert result.usage.totalTokens is result.usage.costMicros is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,code,recovered",
    [
        ('{"value":0}', "schema_violation", None),
        ('{"value":', "json_decode_error", None),
        ("[2]", "not_object", None),
        ("", "empty_output", None),
        ('{"value":1,"value":2}', "json_decode_error", None),
        ('{"value":NaN}', "json_decode_error", None),
        ('```json\n{"value":2}\n```', None, "unwrap_single_json_fence"),
    ],
)
async def test_existing_deterministic_json_rules_keep_usage_without_bad_raw_text(
    text, code, recovered
):
    body = payload()
    body["output"][0]["content"][0]["text"] = text
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.usage.inputTokens == 100 and result.providerResponseId == "resp-video-1"
    assert (result.diagnostic.code if result.diagnostic else None) == code
    assert result.recoveryCode == recovered
    assert result.structuredOutput == ({"value": 2} if code is None else None)
    assert not hasattr(result, "rawText") and not hasattr(result, "content")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,reason,finish",
    [
        ("incomplete", "max_output_tokens", "length"),
        ("incomplete", "content_filter", "content_filter"),
        ("incomplete", "arbitrary response text", "unknown"),
        ("failed", None, "unknown"),
        ("queued", None, "unknown"),
    ],
)
async def test_noncomplete_response_keeps_usage_and_sanitized_status(status, reason, finish):
    body = payload(status=status, incomplete_details={"reason": reason})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.structuredOutput is None and result.diagnostic is not None
    assert result.finishReason == finish and result.usage.completionTokens == 20
    assert "arbitrary response text" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["multiple", "tool", "incomplete", "refusal", "malformed"])
async def test_ambiguous_response_output_never_succeeds(kind):
    body = payload()
    if kind == "multiple":
        body["output"] += deepcopy(body["output"])
    elif kind == "tool":
        body["output"].append({"type": "function_call", "arguments": "不能泄露"})
    elif kind == "incomplete":
        body["output"][0]["status"] = "incomplete"
    elif kind == "refusal":
        body["output"][0]["content"] = [{"type": "refusal", "refusal": "不能泄露"}]
    else:
        body["output"] = None
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.structuredOutput is None and result.diagnostic is not None
    assert result.usage.inputTokens == 100 and "不能泄露" not in repr(result)


@pytest.mark.parametrize(
    "config",
    [
        {"openai_base_url": "http://api.deepseek.com"},
        {"openai_base_url": "https://custom.invalid/v1"},
        {"openai_base_url": "https://api.deepseek.com:443"},
        {"openai_base_url": "https://api.deepseek.com/beta"},
        {"openai_model": "fake"},
        {"openai_model": "deepseek-v4-pro"},
    ],
)
def test_official_adapter_rejects_fake_and_other_endpoint_or_model(config):
    with pytest.raises(ValueError):
        DeepSeekVideoResponsesProvider(settings(**config))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 429, 500, 503])
async def test_http_failure_is_one_request_without_raw_exception_context(status):
    calls = []

    def handle(incoming):
        calls.append(incoming)
        return httpx.Response(status, text="secret-raw-provider-body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(ProviderTransportError) as caught:
            await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
                request()
            )
    assert len(calls) == 1 and caught.value.__context__ is None
    assert "secret-raw-provider-body" not in repr(caught.value)


@pytest.mark.asyncio
async def test_invalid_http_json_does_not_leak_or_retry():
    calls = []

    def handle(incoming):
        calls.append(incoming)
        return httpx.Response(200, text="secret invalid body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(ProviderProtocolError) as caught:
            await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
                request()
            )
    assert len(calls) == 1 and caught.value.__context__ is None
    assert "secret invalid body" not in repr(caught.value)


def test_nullable_usage_type_rejects_boolean_and_negative_counters():
    for value in (True, -1, "3", 1.5):
        with pytest.raises(ValueError):
            VideoResponsesUsage(inputTokens=value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "details",
    [
        {"cached_tokens": 101},
        {"cached_tokens": True},
        {"cached_tokens": -1},
        {"cached_tokens": "30"},
        {"cached_tokens": 30, "cache_read": 29},
    ],
)
async def test_unreliable_cache_details_do_not_erase_other_tokens_or_invent_miss(details):
    body = payload()
    body["usage"]["input_tokens_details"] = details
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.usage.inputTokens == 100 and result.usage.completionTokens == 20
    assert result.usage.cachedTokens is result.usage.promptCacheMissTokens is None
    assert result.usage.reasoningTokens == 0 and result.usage.visibleOutputTokens == 20


@pytest.mark.asyncio
@pytest.mark.parametrize("reasoning", [True, -1, 21, "0"])
async def test_invalid_reasoning_does_not_invent_visible_output(reasoning):
    body = payload()
    body["usage"]["output_tokens_details"] = {"reasoning_tokens": reasoning}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.usage.inputTokens == 100 and result.usage.completionTokens == 20
    assert result.usage.cachedTokens == 30 and result.usage.promptCacheMissTokens == 70
    assert result.usage.reasoningTokens is result.usage.visibleOutputTokens is None


@pytest.mark.asyncio
async def test_explicit_zero_cache_and_reasoning_are_reliable_not_missing():
    body = payload()
    body["usage"]["input_tokens_details"] = {"cached_tokens": 0}
    body["usage"]["costMicros"] = 0
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.usage.cachedTokens == 0 and result.usage.promptCacheMissTokens == 100
    assert result.usage.reasoningTokens == 0 and result.usage.visibleOutputTokens == 20
    assert result.usage.costMicros is None  # 供应商随意命名的费用字段没有已冻结单位。


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        '{"status":"completed","usage":{"input_tokens":1,"input_tokens":2}}',
        '{"status":"completed","usage":{"input_tokens":NaN}}',
    ],
)
async def test_outer_envelope_duplicate_or_nonstandard_numbers_cannot_be_reliable_usage(raw):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=raw))
    ) as http:
        with pytest.raises(ProviderProtocolError) as caught:
            await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
                request()
            )
    assert caught.value.__context__ is None


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [[], {"unexpected": "内容"}])
async def test_malformed_incomplete_reason_returns_safe_diagnostic_not_type_error(reason):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json=payload(status="incomplete", incomplete_details={"reason": reason})
            )
        )
    ) as http:
        result = await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
            request()
        )
    assert result.diagnostic.code == "response_incomplete"
    assert result.rawFinishReason == "response.incomplete" and result.usage.inputTokens == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("error_class", [httpx.ConnectError, httpx.ReadTimeout])
async def test_network_errors_are_redacted_single_attempts(error_class):
    calls = []

    def handle(incoming):
        calls.append(incoming)
        raise error_class("secret-network-body", request=incoming)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(ProviderTransportError) as caught:
            await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
                request()
            )
    assert len(calls) == 1 and caught.value.__context__ is None
    assert "secret-network-body" not in repr(caught.value)


@pytest.mark.asyncio
async def test_no_redirect_fallback_or_secondary_http_call():
    calls = []

    def handle(incoming):
        calls.append(incoming)
        return httpx.Response(307, headers={"Location": "https://other.invalid/responses"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), follow_redirects=True
    ) as http:
        with pytest.raises(ProviderTransportError):
            await DeepSeekVideoResponsesProvider(settings(), http=http).complete_responses(
                request()
            )
    assert len(calls) == 1 and calls[0].url.host == "api.deepseek.com"


@pytest.mark.asyncio
async def test_owned_http_client_disables_proxy_and_redirects_and_is_closed(monkeypatch):
    options = []
    closed = []

    class Client:
        def __init__(self, **kwargs):
            options.append(kwargs)

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(provider_module.httpx, "AsyncClient", Client)
    provider = DeepSeekVideoResponsesProvider(settings())
    assert options == [{"timeout": 600.0, "trust_env": False, "follow_redirects": False}]
    await provider.aclose()
    assert closed == [True]


@pytest.mark.parametrize(
    "mutation", ["thinking", "route", "tool_history", "reasoning_history", "idempotency"]
)
def test_narrow_request_rejects_nonvideo_protocol_mixing(mutation):
    value = request()
    turn = ModelTurnRequest(
        messages=value.messages,
        tools=[],
        maxOutputTokens=321,
        policy={"policyId": "video.test", "thinkingMode": "disabled"},
        thinkingMode="disabled",
        structuredOutput=value.structuredOutput,
    )
    if mutation == "thinking":
        turn.thinkingMode = "provider_default"
    elif mutation == "route":
        turn.structuredOutput.route = "chat_json_output_v1"
    elif mutation == "tool_history":
        turn.messages[0].role = "tool"
    elif mutation == "reasoning_history":
        turn.messages[0].reasoningContent = "不能回传"
    else:
        turn.requestIdempotencyKey = "undeclared-key"
    with pytest.raises(ValueError):
        VideoResponsesRequest.from_turn(turn)


def test_invalid_local_schema_is_rejected_before_provider_construction():
    value = request().model_dump(mode="json")
    value["structuredOutput"]["jsonSchema"] = {"type": "not-a-real-json-type"}
    with pytest.raises(ValueError):
        VideoResponsesRequest.model_validate(value)
