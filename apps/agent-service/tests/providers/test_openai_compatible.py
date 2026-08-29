from __future__ import annotations

import hashlib
import json
import logging
import traceback
from copy import deepcopy
from typing import Any

import httpx
import inkforge_agents.providers.openai_compatible as provider_module
import jsonschema_rs
import pytest
from inkforge_agents.config import Settings
from inkforge_agents.providers.base import (
    ModelTool,
    ModelTurnResult,
    ModelUsage,
    ProviderTransportError,
)
from inkforge_agents.providers.base import (
    ModelTurnRequest as BaseModelTurnRequest,
)
from inkforge_agents.providers.openai_compatible import OpenAICompatibleProvider
from inkforge_agents.runtime.model_policy import LEGACY_PROVIDER_DEFAULT
from inkforge_contracts.video import (
    CharacterSettingSnapshot,
    LocationSettingSnapshot,
    LongSerialSettingSnapshot,
    PlannedAssetArguments,
    SceneAssetsStageArguments,
    SettingReference,
    build_video_director_draft_skeleton,
    json_schema_for_scene_assets_draft_response,
    json_schema_for_story_beats_draft_response,
)
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from openai import APITimeoutError, AsyncOpenAI


class ModelTurnRequest(BaseModelTurnRequest):
    """兼容 main 视频侧旧构造器；生产契约仍要求显式 policy。"""

    def __init__(self, **data: Any) -> None:
        data.setdefault("policy", LEGACY_PROVIDER_DEFAULT)
        super().__init__(**data)


def assert_exception_chain_is_sanitized(
    error: BaseException,
    private_text: str,
) -> None:
    """递归审计异常链及常见渲染面，确保底层传输正文没有被保留。"""

    pending = [error]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        surfaces = (
            str(current),
            repr(current),
            repr(current.args),
            repr(getattr(current, "__dict__", {})),
        )
        assert all(private_text not in surface for surface in surfaces)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)

    assert error.__cause__ is None
    assert error.__context__ is None
    assert private_text not in "".join(traceback.format_exception(error))


class StubModel:
    def __init__(self, response: AIMessage) -> None:
        self._response = response
        self.invocation_kwargs: dict[str, object] | None = None
        self.bind_kwargs: dict[str, object] | None = None

    def bind_tools(
        self,
        tools: list[dict[str, object]],
        **kwargs: object,
    ) -> StubModel:
        del tools
        self.bind_kwargs = kwargs
        return self

    async def ainvoke(self, messages: object, **kwargs: object) -> AIMessage:
        del messages
        self.invocation_kwargs = kwargs
        return self._response


class TimeoutStubModel(StubModel):
    async def ainvoke(self, messages: object, **kwargs: object) -> AIMessage:
        del messages, kwargs
        raise APITimeoutError(request=httpx.Request("POST", "https://api.deepseek.com/chat"))


def provider_with_response(response: AIMessage) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider._model = StubModel(response)  # type: ignore[attr-defined]
    provider._strict_model = provider._model  # type: ignore[attr-defined]
    provider.model_name = "deepseek-v4-flash"
    return provider


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.deepseek.com",
        "https://api.deepseek.com/",
        "https://api.deepseek.com/v1",
        "https://api.deepseek.com/v1/",
    ],
)
def test_deepseek_strict_base_url_auto_derivation_requires_canonical_official_url(
    base_url: str,
) -> None:
    settings = Settings.model_validate(
        {
            "openai_api_key": "test-key",
            "openai_base_url": base_url,
            "openai_model": "deepseek-v4-flash",
        }
    )

    assert (
        provider_module._resolve_deepseek_strict_base_url(settings)
        == "https://api.deepseek.com/beta"
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.deepseek.com/v1",
        "https://api.deepseek.com:8443/v1",
        "https://api.deepseek.com/custom",
        "https://api.deepseek.com/v1?tenant=test",
        "https://api.deepseek.com/v1#fragment",
    ],
)
def test_deepseek_strict_base_url_does_not_derive_for_noncanonical_official_url(
    base_url: str,
) -> None:
    settings = Settings.model_validate(
        {
            "openai_api_key": "test-key",
            "openai_base_url": base_url,
            "openai_model": "deepseek-v4-flash",
        }
    )

    assert provider_module._resolve_deepseek_strict_base_url(settings) is None


@pytest.mark.asyncio
async def test_normal_chat_timeout_is_sanitized_transport_error() -> None:
    """普通工具通道的超时也必须脱敏归一化，不能只覆盖结构化输出。"""

    provider = provider_with_response(AIMessage(content="不会返回"))
    provider._model = TimeoutStubModel(AIMessage(content="不会返回"))  # type: ignore[attr-defined]

    with pytest.raises(ProviderTransportError) as caught:
        await provider.complete_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "不能进入异常链的提示词"}],
                tools=[],
                maxOutputTokens=128,
            )
        )

    assert caught.value.code == "timeout_error"
    assert caught.value.statusCode is None
    assert caught.value.requestId is None
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def strict_recovery_request(parameters: dict[str, Any]) -> ModelTurnRequest:
    """构造唯一、必调且禁止并行的 strict 工具请求。"""

    return ModelTurnRequest(
        messages=[{"role": "user", "content": "严格结构任务"}],
        tools=[
            ModelTool(
                name="submit_test",
                description="提交测试结构",
                parameters=parameters,
                strict=True,
            )
        ],
        maxOutputTokens=128,
        requiredToolName="submit_test",
        parallelToolCalls=False,
    )


def test_model_turn_result_rejects_misaligned_invalid_tool_diagnostics() -> None:
    """诊断平行数组必须和无效调用数量严格对齐。"""

    with pytest.raises(ValueError, match="无效工具调用诊断数量"):
        ModelTurnResult(
            content="",
            toolCalls=[],
            invalidToolCallCount=1,
            invalidToolCallNames=["submit_test"],
            invalidToolCallCodes=[],
            invalidToolCallArgumentCharacterCounts=[10],
            usage=ModelUsage(promptTokens=1, completionTokens=1, totalTokens=2),
            finishReason="tool_calls",
        )


def test_model_turn_result_rejects_misaligned_recovery_diagnostics() -> None:
    """恢复审计数组必须与恢复成功的工具调用数量一致。"""

    with pytest.raises(ValueError, match="工具调用恢复审计数量"):
        ModelTurnResult(
            content="",
            toolCalls=[],
            recoveredToolCallCount=1,
            recoveredToolCallCodes=["append_container_closers"],
            recoveredToolCallAppendedContainerCounts=[],
            usage=ModelUsage(promptTokens=1, completionTokens=1, totalTokens=2),
            finishReason="tool_calls",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_reason", "expected_reason", "expected_raw"),
    [
        ("stop", "stop", "stop"),
        ("function_call", "tool_calls", "function_call"),
        ("max_tokens", "length", "max_tokens"),
        ("future_provider_reason", "unknown", "future_provider_reason"),
        (None, "unknown", None),
        (["length"], "unknown", "['length']"),
    ],
)
async def test_complete_turn_normalizes_provider_finish_reason(
    raw_reason: Any,
    expected_reason: str,
    expected_raw: str | None,
) -> None:
    response = AIMessage(
        content="完整响应",
        response_metadata={"finish_reason": raw_reason},
    )

    result = await provider_with_response(response).complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[],
            maxOutputTokens=128,
            policy=LEGACY_PROVIDER_DEFAULT,
        )
    )

    assert result.finishReason == expected_reason
    assert result.rawFinishReason == expected_raw


@pytest.mark.asyncio
async def test_complete_turn_treats_missing_finish_reason_as_unknown() -> None:
    result = await provider_with_response(AIMessage(content="完整响应")).complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[],
            maxOutputTokens=128,
            policy=LEGACY_PROVIDER_DEFAULT,
        )
    )

    assert result.finishReason == "unknown"
    assert result.rawFinishReason is None


@pytest.mark.asyncio
async def test_complete_turn_disables_deepseek_thinking_only_when_requested() -> None:
    provider = provider_with_response(AIMessage(content="完整响应"))

    await provider.complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "严格结构任务"}],
            tools=[],
            maxOutputTokens=128,
            thinkingMode="disabled",
        )
    )

    assert provider._model.invocation_kwargs == {  # type: ignore[attr-defined]
        "extra_body": {
            "max_tokens": 128,
            "thinking": {"type": "disabled"},
        },
    }


@pytest.mark.asyncio
async def test_complete_turn_preserves_provider_default_thinking_mode() -> None:
    provider = provider_with_response(AIMessage(content="完整响应"))

    await provider.complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "普通任务"}],
            tools=[],
            maxOutputTokens=128,
        )
    )

    assert provider._model.invocation_kwargs == {  # type: ignore[attr-defined]
        "extra_body": {"max_tokens": 128}
    }


@pytest.mark.asyncio
async def test_deepseek_rejects_mixed_strict_tools_before_model_invocation() -> None:
    """DeepSeek Beta 要求同一请求的全部函数统一开启 strict。"""

    provider = provider_with_response(AIMessage(content="不应调用"))
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "混合工具测试"}],
        tools=[
            ModelTool(
                name="strict_tool",
                description="严格工具",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                strict=True,
            ),
            ModelTool(
                name="legacy_tool",
                description="非严格工具",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            ),
        ],
        maxOutputTokens=128,
    )

    with pytest.raises(ValueError, match="不能混用 strict 与非 strict"):
        await provider.complete_turn(request)

    assert provider._model.bind_kwargs is None  # type: ignore[attr-defined]
    assert provider._model.invocation_kwargs is None  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_complete_turn_reports_invalid_tool_calls_without_arguments() -> None:
    """无法解析的工具参数只暴露安全诊断，不能把原始正文写入领域结果。"""

    raw_arguments = "{包含未闭合正文"
    response = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "submit_test",
                "args": raw_arguments,
                "id": "call-invalid",
                "error": (
                    "Function submit_test arguments 包含未闭合正文 are not valid JSON. "
                    "Received JSONDecodeError"
                ),
                "type": "invalid_tool_call",
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    result = await provider_with_response(response).complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "严格结构任务"}],
            tools=[
                ModelTool(
                    name="submit_test",
                    description="提交测试结构",
                    parameters={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                )
            ],
            maxOutputTokens=128,
        )
    )

    assert result.toolCalls == []
    assert result.invalidToolCallCount == 1
    assert result.invalidToolCallNames == ["submit_test"]
    assert result.invalidToolCallCodes == ["json_decode_error"]
    assert result.invalidToolCallArgumentCharacterCounts == [len(raw_arguments)]
    assert "未闭合正文" not in result.model_dump_json()
    assert "JSONDecodeError" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_complete_turn_recovers_only_missing_container_closers() -> None:
    """只缺末尾对象闭合符时可恢复，并保留不含正文的安全审计。"""

    raw_arguments = '{"payload":{"value":1'
    response = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "submit_test",
                "args": raw_arguments,
                "id": "call-recoverable",
                "error": "原始参数不得进入结果",
                "type": "invalid_tool_call",
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    schema = {
        "type": "object",
        "properties": {
            "payload": {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            }
        },
        "required": ["payload"],
        "additionalProperties": False,
    }

    result = await provider_with_response(response).complete_turn(strict_recovery_request(schema))

    assert result.invalidToolCallCount == 0
    assert result.toolCalls[0].arguments == {"payload": {"value": 1}}
    assert result.recoveredToolCallCount == 1
    assert result.recoveredToolCallCodes == ["append_container_closers"]
    assert result.recoveredToolCallAppendedContainerCounts == [2]
    assert "原始参数不得进入结果" not in result.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_arguments",
    [
        '{"payload":"未闭合',
        '{"payload":"悬空\\',
        '{"payload":"不完整\\u12',
        '{"payload":[1,2}',
        '{"payload":1,',
        '{"payload":tru',
        '{"payload":1}尾随',
        "{}",
    ],
)
async def test_complete_turn_rejects_non_container_only_json_repairs(
    raw_arguments: str,
) -> None:
    """字符串、标点、字面量、错配括号和尾随垃圾都不能由恢复器改写。"""

    response = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "submit_test",
                "args": raw_arguments,
                "id": "call-invalid",
                "error": "不得回显的解析错误",
                "type": "invalid_tool_call",
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    schema = {
        "type": "object",
        "properties": {"payload": {"type": "integer"}},
        "required": ["payload"],
        "additionalProperties": False,
    }

    result = await provider_with_response(response).complete_turn(strict_recovery_request(schema))

    assert result.toolCalls == []
    assert result.invalidToolCallCount == 1
    assert result.recoveredToolCallCount == 0


@pytest.mark.asyncio
async def test_complete_turn_rejects_repaired_json_that_fails_strict_schema() -> None:
    """容器可闭合但缺字段或带额外字段时仍按原 strict schema 拒绝。"""

    response = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "submit_test",
                "args": '{"payload":1,"composition_note":"旁路"',
                "id": "call-schema-invalid",
                "error": "不得回显的解析错误",
                "type": "invalid_tool_call",
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    schema = {
        "type": "object",
        "properties": {"payload": {"type": "integer"}},
        "required": ["payload"],
        "additionalProperties": False,
    }

    result = await provider_with_response(response).complete_turn(strict_recovery_request(schema))

    assert result.toolCalls == []
    assert result.invalidToolCallCount == 1
    assert result.recoveredToolCallCount == 0
    assert "旁路" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_complete_turn_rejects_parsed_strict_arguments_that_fail_schema(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """LangChain 已解析的 strict 参数仍必须通过原 Schema。"""

    schema = {
        "type": "object",
        "properties": {"payload": {"type": "integer"}},
        "required": ["payload"],
        "additionalProperties": False,
    }
    response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "submit_test",
                "args": {"payload": "不得进入诊断的参数正文"},
                "id": "call-schema-violation",
                "type": "tool_call",
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
        usage_metadata={
            "input_tokens": 21,
            "output_tokens": 8,
            "total_tokens": 29,
            "input_token_details": {"cache_read": 3},
        },
    )
    caplog.set_level(
        logging.WARNING,
        logger="inkforge_agents.providers.openai_compatible",
    )

    result = await provider_with_response(response).complete_turn(strict_recovery_request(schema))

    assert result.toolCalls == []
    assert result.invalidToolCallCount == 1
    assert result.invalidToolCallNames == ["submit_test"]
    assert result.invalidToolCallCodes == ["provider_strict_schema_violation"]
    assert result.invalidToolCallArgumentCharacterCounts == [0]
    assert "不得进入诊断的参数正文" not in result.model_dump_json()

    records = [
        record
        for record in caplog.records
        if record.message == "供应商 strict 工具参数未通过本地 Schema 复验"
    ]
    assert len(records) == 1
    record = records[0]
    canonical_schema = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert record.model_name == "deepseek-v4-flash"  # type: ignore[attr-defined]
    assert record.tool_name == "submit_test"  # type: ignore[attr-defined]
    assert (
        record.schema_sha256
        == hashlib.sha256(  # type: ignore[attr-defined]
            canonical_schema.encode("utf-8")
        ).hexdigest()
    )
    assert record.finish_reason == "tool_calls"  # type: ignore[attr-defined]
    assert record.prompt_tokens == 21  # type: ignore[attr-defined]
    assert record.cached_tokens == 3  # type: ignore[attr-defined]
    assert record.completion_tokens == 8  # type: ignore[attr-defined]
    assert record.total_tokens == 29  # type: ignore[attr-defined]
    assert not hasattr(record, "arguments")
    assert not hasattr(record, "validation_error")
    assert "不得进入诊断的参数正文" not in caplog.text


@pytest.mark.asyncio
async def test_complete_turn_preserves_parsed_unknown_tool_call() -> None:
    """未知工具不猜测 strict Schema，仍交由既有业务工具白名单拒绝。"""

    response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "unknown_tool",
                "args": {"payload": "未知工具参数"},
                "id": "call-unknown",
                "type": "tool_call",
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    schema = {
        "type": "object",
        "properties": {"payload": {"type": "integer"}},
        "required": ["payload"],
        "additionalProperties": False,
    }

    result = await provider_with_response(response).complete_turn(strict_recovery_request(schema))

    assert result.invalidToolCallCount == 0
    assert len(result.toolCalls) == 1
    assert result.toolCalls[0].name == "unknown_tool"
    assert result.toolCalls[0].arguments == {"payload": "未知工具参数"}


@pytest.mark.asyncio
async def test_complete_turn_masks_invalid_tool_name_outside_request_allowlist() -> None:
    """模型伪造的工具名不能越过本次请求白名单进入诊断结果。"""

    response = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "模型伪造的私密工具名",
                "args": "{}",
                "id": "call-invalid",
                "error": "JSONDecodeError，其中可能包含原始参数",
                "type": "invalid_tool_call",
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    result = await provider_with_response(response).complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "严格结构任务"}],
            tools=[
                ModelTool(
                    name="submit_test",
                    description="提交测试结构",
                    parameters={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                )
            ],
            maxOutputTokens=128,
        )
    )

    assert result.invalidToolCallNames == ["未知工具"]
    assert result.invalidToolCallCodes == ["unknown_invalid_tool_call"]
    assert result.invalidToolCallArgumentCharacterCounts == [2]
    assert "模型伪造的私密工具名" not in result.model_dump_json()
    assert "JSONDecodeError" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_deepseek_strict_tool_uses_beta_wire_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 ChatOpenAI 必须把 strict 工具发往 /beta，并保留 DeepSeek 字段。"""

    request_paths: list[str] = []
    request_bodies: list[dict[str, Any]] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        request_paths.append(request.url.path)
        request_bodies.append(body)
        has_tools = bool(body.get("tools"))
        message: dict[str, Any] = {
            "role": "assistant",
            "content": "" if has_tools else "普通响应",
        }
        if has_tools:
            message["tool_calls"] = [
                {
                    "id": "call-video-test",
                    "type": "function",
                    "function": {
                        "name": "submit_test",
                        "arguments": "{}",
                    },
                }
            ]
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chatcmpl-video-test",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if has_tools else "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_real_chat_openai(**kwargs: Any) -> ChatOpenAI:
            # 只替换传输层，Provider 仍构造并调用真实 ChatOpenAI。
            return ChatOpenAI(**kwargs, http_async_client=client)

        monkeypatch.setattr(provider_module, "ChatOpenAI", build_real_chat_openai)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        tool = ModelTool(
            name="submit_test",
            description="提交测试结构",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            strict=True,
        )

        strict_result = await provider.complete_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "测试"}],
                tools=[tool],
                maxOutputTokens=321,
                thinkingMode="disabled",
                requiredToolName="submit_test",
                parallelToolCalls=False,
            )
        )
        strict_default_result = await provider.complete_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "测试 strict 默认思考模式"}],
                tools=[tool],
                maxOutputTokens=654,
                requiredToolName="submit_test",
            )
        )
        default_result = await provider.complete_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "测试普通通道"}],
                tools=[],
                maxOutputTokens=777,
            )
        )

    strict_body, strict_default_body, default_body = request_bodies
    assert request_paths == [
        "/beta/chat/completions",
        "/beta/chat/completions",
        "/v1/chat/completions",
    ]
    assert strict_body["max_tokens"] == 321
    assert strict_result.effectiveMaxOutputTokens == 321
    assert "max_completion_tokens" not in strict_body
    assert strict_body["thinking"] == {"type": "disabled"}
    assert strict_body["tools"][0]["function"]["strict"] is True
    assert strict_body["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_test"},
    }
    assert "parallel_tool_calls" not in strict_body
    assert strict_default_body["max_tokens"] == 654
    assert strict_default_result.effectiveMaxOutputTokens == 654
    assert "max_completion_tokens" not in strict_default_body
    assert "thinking" not in strict_default_body
    assert strict_default_body["tool_choice"] == strict_body["tool_choice"]
    assert default_body["max_tokens"] == 777
    assert default_result.effectiveMaxOutputTokens == 777
    assert "max_completion_tokens" not in default_body
    assert "thinking" not in default_body


@pytest.mark.asyncio
async def test_deepseek_strict_http_failure_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """strict 传输失败只能发生一次，纠正预算由规划器统一治理。"""

    request_count = 0

    async def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            500,
            request=request,
            json={"error": {"message": "临时失败", "type": "server_error"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_real_chat_openai(**kwargs: Any) -> ChatOpenAI:
            return ChatOpenAI(**kwargs, http_async_client=client)

        monkeypatch.setattr(provider_module, "ChatOpenAI", build_real_chat_openai)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )

        with pytest.raises(ProviderTransportError) as caught:
            await provider.complete_turn(
                strict_recovery_request(
                    {
                        "type": "object",
                        "properties": {"payload": {"type": "integer"}},
                        "required": ["payload"],
                        "additionalProperties": False,
                    }
                )
            )

    assert request_count == 1
    assert caught.value.code == "http_error"
    assert caught.value.statusCode == 500


@pytest.mark.asyncio
async def test_custom_deepseek_endpoint_requires_explicit_strict_url() -> None:
    provider = OpenAICompatibleProvider(
        Settings.model_validate(
            {
                "openai_api_key": "test-key",
                "openai_base_url": "https://gateway.example/v1",
                "openai_model": "deepseek-v4-flash",
            }
        )
    )

    with pytest.raises(ValueError, match="OPENAI_STRICT_BASE_URL"):
        await provider.complete_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "严格结构任务"}],
                tools=[
                    ModelTool(
                        name="submit_test",
                        description="提交测试结构",
                        parameters={
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": False,
                        },
                        strict=True,
                    )
                ],
                maxOutputTokens=128,
            )
        )


def structured_request(
    *,
    route: str = "responses_json_schema_v1",
    schema: dict[str, Any] | None = None,
    thinking_mode: str = "disabled",
) -> ModelTurnRequest:
    """构造不携带工具的结构化输出请求。"""

    return ModelTurnRequest(
        messages=[
            {"role": "system", "content": "只输出符合 JSON Schema 的 json 对象。"},
            {"role": "user", "content": "生成测试对象"},
        ],
        tools=[],
        maxOutputTokens=321,
        thinkingMode=thinking_mode,
        structuredOutput={
            "route": route,
            "name": "scene_assets",
            "jsonSchema": schema
            or {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    )


def test_cinematography_v2_normalizes_camera_and_light_circular_azimuths() -> None:
    """v2 按别名对象中的摄影机、主光和边缘光都要恢复为同一等价方位。"""

    parsed = {
        "beatsByAlias": {
            "B01": {
                "cameraSpec": {"position": {"azimuthDegrees": 270}},
                "lightingCue": {
                    "keyLight": {"azimuthDegrees": 540},
                    "edgeLight": {"azimuthDegrees": -450},
                },
            },
            "B02": {
                "cameraSpec": {"position": {"azimuthDegrees": 45}},
                "lightingCue": None,
            },
        }
    }
    original = json.loads(json.dumps(parsed))

    normalized, recovery = provider_module._normalize_cinematography_azimuth(
        parsed,
        format_name="video_cinematography_draft_v2",
    )

    assert recovery == "normalize_cinematography_azimuth"
    assert parsed == original
    first = normalized["beatsByAlias"]["B01"]
    assert first["cameraSpec"]["position"]["azimuthDegrees"] == -90
    assert first["lightingCue"]["keyLight"]["azimuthDegrees"] == -180
    assert first["lightingCue"]["edgeLight"]["azimuthDegrees"] == -90
    assert normalized["beatsByAlias"]["B02"] == parsed["beatsByAlias"]["B02"]


@pytest.mark.parametrize(
    "legacy_lighting",
    [
        "__INHERIT__",
        {
            "continuityMode": "inherit",
            "motivatedChange": "",
            "keyLight": {"visibleResult": "不应被当成变光"},
        },
    ],
    ids=["legacy-sentinel", "legacy-inherit-object"],
)
def test_cinematography_v2_normalizes_only_later_explicit_lighting_inheritance(
    legacy_lighting: object,
) -> None:
    """旧协议的明确继承等价于 null，恢复时不得修改原输入。"""

    parsed = {
        "beatsByAlias": {
            "B01": {"lightingCue": legacy_lighting},
            "B02": {"lightingCue": legacy_lighting},
        }
    }
    original = json.loads(json.dumps(parsed))

    normalized, recovery = provider_module._normalize_cinematography_lighting_inheritance(
        parsed,
        format_name="video_cinematography_draft_v2",
    )

    assert recovery == "normalize_cinematography_lighting_inheritance"
    assert parsed == original
    assert normalized["beatsByAlias"]["B01"]["lightingCue"] == legacy_lighting
    assert normalized["beatsByAlias"]["B02"]["lightingCue"] is None


@pytest.mark.parametrize(
    "lighting",
    [
        "null",
        {"continuityMode": "motivated_change"},
        {"continuityMode": "establish"},
    ],
    ids=["string-null", "incomplete-change", "later-establish"],
)
def test_cinematography_v2_does_not_guess_other_invalid_lighting(
    lighting: object,
) -> None:
    """字符串 null 和不合法变光必须继续交给权威 Schema 拒绝。"""

    parsed = {"beatsByAlias": {"B02": {"lightingCue": lighting}}}

    normalized, recovery = provider_module._normalize_cinematography_lighting_inheritance(
        parsed,
        format_name="video_cinematography_draft_v2",
    )

    assert normalized is parsed
    assert recovery is None


@pytest.mark.parametrize(
    ("placeholder", "relative_stops"),
    [
        ("none", -8),
        ("front_right", -4),
        ("camera_left", 2.5),
        (None, -3),
    ],
)
def test_cinematography_v2_normalizes_closed_no_fill_placeholder_direction(
    placeholder: str | None,
    relative_stops: float,
) -> None:
    """关闭策略确定后，供应商填写的方向与曝光占位都没有业务意义。"""

    parsed = {
        "beatsByAlias": {
            "B01": {
                "lightingCue": {
                    "fillStrategy": "none",
                    "fillDirection": placeholder,
                    "fillRelativeStops": relative_stops,
                }
            },
            "B02": {"lightingCue": None},
        }
    }
    original = json.loads(json.dumps(parsed))

    normalized, recovery = provider_module._normalize_cinematography_no_fill_direction(
        parsed,
        format_name="video_cinematography_draft_v2",
    )

    assert recovery == "normalize_cinematography_no_fill_direction"
    assert parsed == original
    assert normalized["beatsByAlias"]["B01"]["lightingCue"]["fillDirection"] is None
    assert normalized["beatsByAlias"]["B01"]["lightingCue"]["fillRelativeStops"] == -8
    assert normalized["beatsByAlias"]["B02"] == parsed["beatsByAlias"]["B02"]


@pytest.mark.parametrize(
    ("lighting", "format_name"),
    [
        (
            {"fillStrategy": "soft_fill", "fillDirection": "none", "fillRelativeStops": -8},
            "video_cinematography_draft_v2",
        ),
        (
            {"fillStrategy": "none", "fillDirection": "none", "fillRelativeStops": -9},
            "video_cinematography_draft_v2",
        ),
        (
            {"fillStrategy": "none", "fillDirection": None, "fillRelativeStops": -8},
            "video_cinematography_draft_v2",
        ),
        (
            {"fillStrategy": "none", "fillDirection": 0, "fillRelativeStops": -8},
            "video_cinematography_draft_v2",
        ),
        (
            {"fillStrategy": "none", "fillDirection": "none", "fillRelativeStops": -8},
            "video_cinematography_draft_v1",
        ),
    ],
)
def test_cinematography_no_fill_direction_does_not_guess_other_shapes(
    lighting: object,
    format_name: str,
) -> None:
    """策略、关闭值、字段类型或协议版本任一不匹配都不能恢复。"""

    parsed = {"beatsByAlias": {"B01": {"lightingCue": lighting}}}

    normalized, recovery = provider_module._normalize_cinematography_no_fill_direction(
        parsed,
        format_name=format_name,
    )

    assert normalized is parsed
    assert recovery is None


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("camera_left", "side_left"), ("camera_right", "side_right")],
)
def test_cinematography_v2_normalizes_known_active_fill_direction_alias(
    alias: str,
    canonical: str,
) -> None:
    """相邻字段的机位侧别可以无损投影为补光槽的 canonical 侧别。"""

    parsed = {
        "beatsByAlias": {
            "B01": {
                "lightingCue": {
                    "fillStrategy": "negative_fill",
                    "fillDirection": alias,
                    "fillRelativeStops": -2,
                }
            },
            "B02": {"lightingCue": None},
        }
    }
    original = json.loads(json.dumps(parsed))

    normalized, recovery = provider_module._normalize_cinematography_fill_direction_alias(
        parsed,
        format_name="video_cinematography_draft_v2",
    )

    assert recovery == "normalize_cinematography_fill_direction_alias"
    assert parsed == original
    assert normalized["beatsByAlias"]["B01"]["lightingCue"]["fillDirection"] == canonical
    assert normalized["beatsByAlias"]["B02"] == parsed["beatsByAlias"]["B02"]


@pytest.mark.parametrize(
    ("lighting", "format_name"),
    [
        ({"fillStrategy": "none", "fillDirection": "camera_left"}, "video_cinematography_draft_v2"),
        ({"fillStrategy": "soft_fill", "fillDirection": "none"}, "video_cinematography_draft_v2"),
        ({"fillStrategy": "soft_fill", "fillDirection": "both"}, "video_cinematography_draft_v2"),
        (
            {"fillStrategy": "soft_fill", "fillDirection": "camera_left"},
            "video_cinematography_draft_v1",
        ),
    ],
)
def test_cinematography_fill_direction_alias_does_not_guess_other_shapes(
    lighting: object,
    format_name: str,
) -> None:
    """关闭策略、未知别名和旧协议都不能进入 active fill 别名恢复。"""

    parsed = {"beatsByAlias": {"B01": {"lightingCue": lighting}}}

    normalized, recovery = provider_module._normalize_cinematography_fill_direction_alias(
        parsed,
        format_name=format_name,
    )

    assert normalized is parsed
    assert recovery is None


def test_cinematography_v2_normalizes_only_bounded_unsigned_magnitudes() -> None:
    parsed = {
        "lightingSetup": {"keyToFillStops": -3.5, "ambientColorTemperatureK": 4100},
        "beatsByAlias": {
            "B01": {
                "cameraSpec": {
                    "movement": {
                        "travelDistanceMeters": -1.25,
                        "rotationDegrees": -45,
                    },
                    "position": {"azimuthDegrees": -30},
                }
            }
        },
    }
    original = json.loads(json.dumps(parsed))

    normalized, recovery = provider_module._normalize_cinematography_unsigned_magnitudes(
        parsed,
        format_name="video_cinematography_draft_v2",
    )

    assert recovery == "normalize_cinematography_unsigned_magnitudes"
    assert parsed == original
    assert normalized["lightingSetup"]["keyToFillStops"] == 3.5
    movement = normalized["beatsByAlias"]["B01"]["cameraSpec"]["movement"]
    assert movement == {"travelDistanceMeters": 1.25, "rotationDegrees": 45}
    assert normalized["beatsByAlias"]["B01"]["cameraSpec"]["position"] == {"azimuthDegrees": -30}


@pytest.mark.parametrize(
    ("value", "field"),
    [
        (-9, "keyToFillStops"),
        (False, "keyToFillStops"),
        (-51, "travelDistanceMeters"),
        (-361, "rotationDegrees"),
    ],
)
def test_cinematography_unsigned_magnitude_recovery_rejects_other_values(
    value: object,
    field: str,
) -> None:
    parsed: dict[str, Any] = {
        "lightingSetup": {"keyToFillStops": 2},
        "beatsByAlias": {
            "B01": {
                "cameraSpec": {
                    "movement": {
                        "travelDistanceMeters": 0,
                        "rotationDegrees": 0,
                    }
                }
            }
        },
    }
    if field == "keyToFillStops":
        parsed["lightingSetup"][field] = value
    else:
        parsed["beatsByAlias"]["B01"]["cameraSpec"]["movement"][field] = value

    normalized, recovery = provider_module._normalize_cinematography_unsigned_magnitudes(
        parsed,
        format_name="video_cinematography_draft_v2",
    )

    assert normalized is parsed
    assert recovery is None


def _shot_progression_recovery_validator() -> jsonschema_rs.Validator:
    return jsonschema_rs.validator_for(
        {
            "type": "object",
            "properties": {
                "beatsByAlias": {
                    "type": "object",
                    "properties": {
                        "B03": {
                            "type": "object",
                            "properties": {
                                "shotProgression": {
                                    "anyOf": [
                                        {
                                            "type": "object",
                                            "properties": {
                                                "startShotSize": {"enum": ["中景"]},
                                                "endShotSize": {"enum": ["近景"]},
                                                "changeMode": {"enum": ["continuous"]},
                                            },
                                            "required": [
                                                "startShotSize",
                                                "endShotSize",
                                                "changeMode",
                                            ],
                                            "additionalProperties": False,
                                        },
                                        {
                                            "type": "object",
                                            "properties": {
                                                "startShotSize": {"type": "string"},
                                                "endShotSize": {"type": "string"},
                                                "changeMode": {
                                                    "enum": ["cut", "match_cut", "impact_cut"]
                                                },
                                            },
                                            "required": [
                                                "startShotSize",
                                                "endShotSize",
                                                "changeMode",
                                            ],
                                            "additionalProperties": False,
                                        },
                                    ]
                                }
                            },
                            "required": ["shotProgression"],
                            "additionalProperties": False,
                        }
                    },
                    "required": ["B03"],
                    "additionalProperties": False,
                }
            },
            "required": ["beatsByAlias"],
            "additionalProperties": False,
        }
    )


def test_cinematography_v2_recovers_unique_infeasible_continuous_as_cut() -> None:
    parsed = {
        "beatsByAlias": {
            "B03": {
                "shotProgression": {
                    "startShotSize": "大全景",
                    "endShotSize": "特写",
                    "changeMode": "continuous",
                }
            }
        }
    }
    original = json.loads(json.dumps(parsed))

    normalized, recovery = provider_module._normalize_cinematography_infeasible_continuous_cut(
        parsed,
        format_name="video_cinematography_draft_v2",
        validator=_shot_progression_recovery_validator(),
    )

    assert recovery == "normalize_cinematography_infeasible_continuous_cut"
    assert parsed == original
    assert normalized["beatsByAlias"]["B03"]["shotProgression"]["changeMode"] == "cut"


@pytest.mark.parametrize(
    ("change_mode", "format_name"),
    [
        ("continuous", "video_cinematography_draft_v1"),
        ("dolly", "video_cinematography_draft_v2"),
        ("cut", "video_cinematography_draft_v2"),
    ],
)
def test_cinematography_progression_recovery_does_not_guess_other_shapes(
    change_mode: str,
    format_name: str,
) -> None:
    parsed = {
        "beatsByAlias": {
            "B03": {
                "shotProgression": {
                    "startShotSize": "大全景",
                    "endShotSize": "特写",
                    "changeMode": change_mode,
                }
            }
        }
    }

    normalized, recovery = provider_module._normalize_cinematography_infeasible_continuous_cut(
        parsed,
        format_name=format_name,
        validator=_shot_progression_recovery_validator(),
    )

    assert normalized is parsed
    assert recovery is None


def responses_payload(
    *,
    status: str = "completed",
    output: list[dict[str, Any]] | None = None,
    incomplete_reason: str | None = None,
    text: str = '{"value":1}',
) -> dict[str, Any]:
    """生成 OpenAI SDK 可解析的 DeepSeek Responses 测试响应。"""

    return {
        "id": "resp-structured-test",
        "object": "response",
        "created_at": 1,
        "status": status,
        "error": {"code": "不得泄露", "message": "供应商私密错误"} if status == "failed" else None,
        "incomplete_details": {"reason": incomplete_reason}
        if incomplete_reason is not None
        else None,
        "model": "deepseek-v4-flash",
        "output": output
        if output is not None
        else [
            {
                "id": "msg-structured-test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 18,
            "input_tokens_details": {"cached_tokens": 7},
            "output_tokens": 6,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 24,
        },
    }


async def complete_responses_text(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text: str,
    schema: dict[str, Any] | None = None,
) -> tuple[ModelTurnResult, list[dict[str, Any]]]:
    """通过本地 MockTransport 执行一次 Responses 文本解析，不访问外部模型。"""

    request_bodies: list[dict[str, Any]] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        return httpx.Response(200, request=request, json=responses_payload(text=text))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        result = await provider.complete_turn(structured_request(schema=schema))
    return result, request_bodies


@pytest.mark.parametrize(
    ("base_url", "model_name", "supports_responses"),
    [
        ("https://api.deepseek.com", "deepseek-v4-flash", True),
        ("https://api.deepseek.com/v1", "deepseek-v4-flash", True),
        ("https://api.deepseek.com/", "deepseek-v4-flash", True),
        ("https://api.deepseek.com/v1/", "deepseek-v4-flash", True),
        ("https://api.deepseek.com:8443/v1", "deepseek-v4-flash", False),
        ("https://api.deepseek.com/custom", "deepseek-v4-flash", False),
        ("https://api.deepseek.com/v1?tenant=test", "deepseek-v4-flash", False),
        ("https://api.deepseek.com/v1#fragment", "deepseek-v4-flash", False),
        ("http://api.deepseek.com/v1", "deepseek-v4-flash", False),
        ("https://api.deepseek.com/v1", "deepseek-chat", False),
        ("https://gateway.example/v1", "deepseek-v4-flash", False),
    ],
)
def test_provider_reports_structured_output_route_capability(
    base_url: str,
    model_name: str,
    supports_responses: bool,
) -> None:
    """Responses 能力只属于官方指定模型，普通 Chat JSON 路由始终可用。"""

    provider = OpenAICompatibleProvider(
        Settings.model_validate(
            {
                "openai_api_key": "test-key",
                "openai_base_url": base_url,
                "openai_model": model_name,
            }
        )
    )

    assert provider.supports_structured_output("responses_json_schema_v1") is supports_responses
    assert provider.supports_structured_output("chat_json_output_v1") is True


def test_structured_output_request_rejects_tool_protocol_mixing() -> None:
    """同一模型轮次不能同时采用结构化文本协议和工具协议。"""

    tool = ModelTool(
        name="submit_test",
        description="测试工具",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    )
    with pytest.raises(ValueError, match="不能与 tools"):
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[tool],
            maxOutputTokens=128,
            structuredOutput={
                "route": "responses_json_schema_v1",
                "name": "test_output",
                "jsonSchema": {"type": "object"},
            },
        )
    with pytest.raises(ValueError, match="不能与 requiredToolName"):
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[],
            maxOutputTokens=128,
            requiredToolName="submit_test",
            structuredOutput={
                "route": "chat_json_output_v1",
                "name": "test_output",
                "jsonSchema": {"type": "object"},
            },
        )


@pytest.mark.asyncio
async def test_deepseek_responses_json_schema_uses_exact_official_wire(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Responses 路由必须走标准根地址，且 text.format 不得夹带 strict。"""

    request_paths: list[str] = []
    request_bodies: list[dict[str, Any]] = []
    client_options: list[dict[str, Any]] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_paths.append(request.url.path)
        request_bodies.append(json.loads(request.content))
        return httpx.Response(200, request=request, json=responses_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            client_options.append(dict(kwargs))
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        caplog.set_level(logging.INFO, logger=provider_module.__name__)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        result = await provider.complete_turn(structured_request())

    assert request_paths == ["/responses"]
    body = request_bodies[0]
    assert body["model"] == "deepseek-v4-flash"
    assert body["max_output_tokens"] == 321
    assert body["reasoning"] == {"effort": "none"}
    assert body["text"] == {
        "format": {
            "type": "json_schema",
            "name": "scene_assets",
            "schema": {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        }
    }
    assert "strict" not in body["text"]["format"]
    assert "tools" not in body
    assert "tool_choice" not in body
    assert "response_format" not in body
    assert all(options["max_retries"] == 0 for options in client_options)
    assert any(str(options["base_url"]) == "https://api.deepseek.com" for options in client_options)
    assert result.content == ""
    assert result.toolCalls == []
    assert result.structuredOutput == {"value": 1}
    assert result.structuredOutputDiagnostic is None
    assert result.finishReason == "stop"
    assert result.rawFinishReason == "response.completed"
    assert result.effectiveMaxOutputTokens == 321
    assert result.usage == ModelUsage(
        promptTokens=18,
        cachedTokens=7,
        completionTokens=6,
        totalTokens=24,
    )
    audit_records = [
        record for record in caplog.records if record.message == "供应商结构化输出审计"
    ]
    assert len(audit_records) == 1
    audit = audit_records[0]
    assert audit.provider_name == "openai_compatible"  # type: ignore[attr-defined]
    assert audit.model_name == "deepseek-v4-flash"  # type: ignore[attr-defined]
    assert audit.structured_route == "responses_json_schema_v1"  # type: ignore[attr-defined]
    assert audit.provider_response_id == "resp-structured-test"  # type: ignore[attr-defined]
    assert audit.provider_status == "completed"  # type: ignore[attr-defined]
    assert audit.finish_reason == "stop"  # type: ignore[attr-defined]
    assert audit.prompt_tokens == 18  # type: ignore[attr-defined]
    assert not hasattr(audit, "input")
    assert not hasattr(audit, "output")
    assert not hasattr(audit, "raw_text")


@pytest.mark.asyncio
async def test_responses_projects_wire_schema_but_validates_with_original_schema(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """wire 只发送兼容子集，字段名不误删，最终结果仍受完整原 Schema 约束。"""

    private_description = "PRIVATE_SCHEMA_DESCRIPTION_MUST_NOT_REACH_WIRE"
    original_schema = {
        "$defs": {
            # description 在这里是定义名，必须保留；内部 description 才是待剥离关键词。
            "description": {
                "type": "string",
                "title": "定义标题",
                "description": private_description,
                "minLength": 2,
                "maxLength": 12,
                "pattern": "^[a-z]+$",
            }
        },
        "type": "object",
        "title": "根标题",
        "description": private_description,
        "properties": {
            # title 在这里是业务字段名，不能被关键词白名单误删。
            "title": {
                "type": "string",
                "enum": ["wide", "close"],
                "description": private_description,
                "pattern": "^[a-z]+$",
            },
            "value": {
                "type": "integer",
                "minimum": 5,
                "maximum": 9,
                "description": private_description,
            },
            "assets": {
                "type": "array",
                "items": {"$ref": "#/$defs/description"},
                "minItems": 1,
                "maxItems": 3,
            },
            "variant": {
                "anyOf": [
                    {"type": "string", "minLength": 2},
                    {"type": "integer", "maximum": 3},
                ]
            },
        },
        "required": ["value"],
        "additionalProperties": False,
        "minProperties": 1,
        "maxProperties": 4,
    }
    original_snapshot = json.loads(json.dumps(original_schema, ensure_ascii=False))
    caplog.set_level(logging.INFO, logger=provider_module.__name__)

    result, request_bodies = await complete_responses_text(
        monkeypatch,
        text='{"value":1}',
        schema=original_schema,
    )

    wire_schema = request_bodies[0]["text"]["format"]["schema"]
    assert wire_schema == {
        "type": "object",
        "properties": {
            "title": {"type": "string", "enum": ["wide", "close"]},
            "value": {"type": "integer"},
            "assets": {
                "type": "array",
                "items": {"$ref": "#/$defs/description"},
            },
            "variant": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "integer"},
                ]
            },
        },
        "required": ["value"],
        "additionalProperties": False,
        "$defs": {"description": {"type": "string"}},
    }
    assert original_schema == original_snapshot
    assert private_description not in json.dumps(request_bodies[0], ensure_ascii=False)
    assert result.structuredOutput is None
    assert result.structuredOutputDiagnostic is not None
    assert result.structuredOutputDiagnostic.code == "schema_violation"
    assert result.structuredOutputDiagnostic.jsonPointer == "/value"
    assert result.structuredOutputDiagnostic.keyword == "minimum"

    canonical_original = json.dumps(
        original_schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    canonical_wire = json.dumps(
        wire_schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    validation_hash = hashlib.sha256(canonical_original.encode()).hexdigest()
    wire_hash = hashlib.sha256(canonical_wire.encode()).hexdigest()
    audit = next(record for record in caplog.records if record.message == "供应商结构化输出审计")
    assert audit.schema_sha256 == validation_hash  # type: ignore[attr-defined]
    assert audit.validation_schema_sha256 == validation_hash  # type: ignore[attr-defined]
    assert audit.wire_schema_sha256 == wire_hash  # type: ignore[attr-defined]
    assert validation_hash != wire_hash


def test_responses_wire_projection_preserves_scene_asset_source_exclusivity() -> None:
    """供应商方言投影不得移除素材设定别名与临时目标的互斥分支。"""

    snapshot = LongSerialSettingSnapshot.from_entries(
        [
            CharacterSettingSnapshot(
                id="character-lin-lan",
                name="林岚",
                contentHash="a" * 64,
                appearance="清瘦脸型与湿发",
            ),
            LocationSettingSnapshot(
                id="location-tide-tower",
                name="旧潮汐钟楼",
                contentHash="b" * 64,
                description="海雾中的黄铜钟楼",
            ),
        ]
    )
    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=snapshot,
        beat_ranges=[(0, 4)],
    )
    validation_schema = json_schema_for_scene_assets_draft_response(skeleton=skeleton)
    wire_schema = provider_module._project_responses_schema(validation_schema)
    valid = {
        "title": "潮汐机关",
        "summary": "林岚启动机关。",
        "dramaticArc": "迟疑转为决断。",
        "visualStyle": "冷调写实。",
        "globalDirection": "保持人物稳定。",
        "assets": {
            "asset01": {
                "sourceAlias": "C01",
                "duty": "identity",
                "targetEntity": None,
                "includeFeatures": ["清瘦脸型"],
                "excludeFeatures": ["服装"],
            },
            **{f"asset{index:02d}": None for index in range(2, 12)},
        },
        "negativeConstraints": ["人物身份漂移"],
    }

    jsonschema_rs.validate(wire_schema, valid)
    invalid = json.loads(json.dumps(valid, ensure_ascii=False))
    invalid["assets"]["asset01"]["targetEntity"] = "林岚"
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(wire_schema, invalid)

    wrong_duty = json.loads(json.dumps(valid, ensure_ascii=False))
    wrong_duty["assets"]["asset01"].update(
        {
            "sourceAlias": "L01",
            "duty": "prop",
        }
    )
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(wire_schema, wrong_duty)


def test_scene_asset_recovery_discards_only_server_owned_fields() -> None:
    """模型回显的机械字段可忽略，其他未知字段仍必须由闭合 Schema 拒绝。"""

    snapshot = LongSerialSettingSnapshot.from_entries(
        [
            CharacterSettingSnapshot(
                id="character-lin-lan",
                name="林岚",
                contentHash="a" * 64,
                appearance="清瘦脸型与湿发",
            )
        ]
    )
    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=snapshot,
        beat_ranges=[(0, 4)],
    )
    schema = json_schema_for_scene_assets_draft_response(skeleton=skeleton)
    raw = {
        "title": "潮汐机关",
        "summary": "林岚启动机关。",
        "dramaticArc": "迟疑转为决断。",
        "visualStyle": "冷调写实。",
        "globalDirection": "保持人物稳定。",
        "assets": {
            "asset01": {
                "sourceAlias": "C01",
                "duty": "identity",
                "targetEntity": "林岚",
                "includeFeatures": ["清瘦脸型"],
                "excludeFeatures": ["服装"],
                "settingId": "server-owned",
                "bindingScope": "canon_slot",
                "modality": "image",
                "keyframeRole": "not_applicable",
                "assetId": "server-owned",
                "usedInBeats": "1",
            },
            **{f"asset{index:02d}": None for index in range(2, 12)},
        },
        "negativeConstraints": ["人物身份漂移"],
    }

    normalized, recovery = provider_module._normalize_scene_asset_source_redundancy(
        raw,
        format_name="video_scene_assets_draft_v1",
    )

    assert recovery == "normalize_scene_asset_source_redundancy"
    normalized_asset = normalized["assets"]["asset01"]
    assert normalized_asset == {
        "sourceAlias": "C01",
        "duty": "identity",
        "targetEntity": None,
        "includeFeatures": ["清瘦脸型"],
        "excludeFeatures": ["服装"],
    }
    assert raw["assets"]["asset01"]["targetEntity"] == "林岚"
    jsonschema_rs.validate(schema, normalized)

    with_unknown = deepcopy(raw)
    with_unknown["assets"]["asset01"]["privateField"] = "仍须拒绝"
    normalized_unknown, _recovery = provider_module._normalize_scene_asset_source_redundancy(
        with_unknown,
        format_name="video_scene_assets_draft_v1",
    )
    assert "privateField" in normalized_unknown["assets"]["asset01"]
    with pytest.raises(jsonschema_rs.ValidationError):
        jsonschema_rs.validate(schema, normalized_unknown)


def test_responses_wire_projection_preserves_exact_story_asset_usage_object() -> None:
    """故事 wire 必须把每个 A 别名保留为 required 闭合属性。"""

    snapshot = LongSerialSettingSnapshot.from_entries(
        [
            CharacterSettingSnapshot(
                id="character-lin-lan",
                name="林岚",
                contentHash="a" * 64,
                appearance="清瘦脸型与湿发",
            )
        ]
    )
    scene_assets = SceneAssetsStageArguments(
        title="潮汐机关",
        summary="林岚启动机关。",
        dramaticArc="迟疑转为决断。",
        visualStyle="冷调写实。",
        globalDirection="保持人物稳定。",
        assets=[
            PlannedAssetArguments(
                assetId="asset01",
                modality="image",
                duty="identity",
                bindingScope="canon_slot",
                settingReference=SettingReference(
                    kind="character",
                    id="character-lin-lan",
                ),
                featureDomain="character_identity",
                keyframeRole=None,
                targetEntity="林岚",
                includeFeatures=["清瘦脸型"],
                excludeFeatures=["服装"],
            ),
            PlannedAssetArguments(
                assetId="asset02",
                modality="image",
                duty="keyframe",
                bindingScope="scene_direct",
                settingReference=None,
                featureDomain="keyframe",
                keyframeRole="initial_state",
                targetEntity="机关关闭初态",
                includeFeatures=["齿轮未转动"],
                excludeFeatures=["人物"],
            ),
        ],
        negativeConstraints=["身份漂移"],
    )
    skeleton = build_video_director_draft_skeleton(
        setting_snapshot=snapshot,
        beat_ranges=[(0, 4), (4, 8)],
        scene_assets=scene_assets,
    )
    validation_schema = json_schema_for_story_beats_draft_response(skeleton=skeleton)
    wire_schema = provider_module._project_responses_schema(validation_schema)

    usage_schema = wire_schema["properties"]["assetUsageByAlias"]
    assert set(usage_schema["properties"]) == {"A01", "A02"}
    assert usage_schema["required"] == ["A01", "A02"]
    assert usage_schema["additionalProperties"] is False
    usage_item = wire_schema["$defs"]["StoryAssetUsageDraftV2"]
    assert usage_item["required"] == [
        "primaryBeatAlias",
        "additionalBeatAliases",
        "anchorAssetAlias",
    ]
    assert usage_item["properties"]["primaryBeatAlias"]["enum"] == ["B01", "B02"]
    assert usage_item["properties"]["additionalBeatAliases"]["items"]["enum"] == [
        "B01",
        "B02",
    ]


@pytest.mark.asyncio
async def test_deepseek_responses_http_failure_is_not_retried_or_fallbacked(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Responses 的一次 5xx 只能发出一次请求，也不能暗中退回 Chat。"""

    request_paths: list[str] = []
    private_body = "SECRET_BODY_RESPONSES_MUST_NOT_LEAK"

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_paths.append(request.url.path)
        return httpx.Response(
            500,
            request=request,
            headers={"x-request-id": "req_safe_500"},
            json={"error": {"message": private_body, "type": "server_error"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        caplog.set_level(logging.WARNING, logger=provider_module.__name__)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )

        with pytest.raises(ProviderTransportError) as caught:
            await provider.complete_turn(structured_request())

    assert request_paths == ["/responses"]
    error = caught.value
    assert error.__dict__ == {
        "code": "http_error",
        "statusCode": 500,
        "requestId": "req_safe_500",
    }
    assert error.retryable is True
    records = [record for record in caplog.records if record.message == "供应商结构化输出传输失败"]
    assert len(records) == 1
    assert records[0].provider_status == "http_500"  # type: ignore[attr-defined]
    assert records[0].provider_response_id == "req_safe_500"  # type: ignore[attr-defined]
    assert_exception_chain_is_sanitized(error, private_body)
    assert private_body not in caplog.text


@pytest.mark.asyncio
async def test_responses_schema_diagnostic_hides_unknown_name_and_value(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """additionalProperties 失败只能报告父路径，不能泄露未知键名和字段值。"""

    raw_text = '{"value":1,"private_unknown_name":"private field value"}'

    async def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json=responses_payload(
                output=[
                    {
                        "id": "msg-invalid-schema",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": raw_text,
                                "annotations": [],
                            }
                        ],
                    }
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        caplog.set_level(logging.WARNING, logger=provider_module.__name__)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        result = await provider.complete_turn(structured_request())

    assert result.content == ""
    assert result.structuredOutput is None
    assert result.structuredOutputDiagnostic is not None
    assert result.structuredOutputDiagnostic.code == "schema_violation"
    assert result.structuredOutputDiagnostic.jsonPointer == ""
    assert result.structuredOutputDiagnostic.keyword == "additionalProperties"
    serialized = result.model_dump_json()
    assert "private_unknown_name" not in serialized
    assert "private field value" not in serialized
    assert "private_unknown_name" not in caplog.text
    assert "private field value" not in caplog.text
    records = [
        record
        for record in caplog.records
        if record.message.startswith("供应商结构化输出未通过本地验收 code=")
    ]
    assert len(records) == 1
    assert records[0].message == (
        "供应商结构化输出未通过本地验收 "
        'code=schema_violation pointer="" keyword=additionalProperties'
    )
    assert records[0].structured_code == "schema_violation"  # type: ignore[attr-defined]
    assert records[0].structured_json_pointer == ""  # type: ignore[attr-defined]
    assert (  # type: ignore[attr-defined]
        records[0].structured_keyword == "additionalProperties"
    )
    assert not hasattr(records[0], "raw_text")
    assert not hasattr(records[0], "validation_error")


@pytest.mark.asyncio
async def test_responses_required_diagnostic_appends_only_known_missing_property(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """required 诊断仅能在当前 Schema 对象上追加已声明缺失字段。"""

    schema = {
        "type": "object",
        "properties": {
            "outer": {
                "type": "object",
                "properties": {"known": {"type": "integer"}},
                "required": ["known"],
                "additionalProperties": False,
            }
        },
        "required": ["outer"],
        "additionalProperties": False,
    }

    async def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json=responses_payload(
                output=[
                    {
                        "id": "msg-missing-required",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"outer":{}}',
                                "annotations": [],
                            }
                        ],
                    }
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        result = await provider.complete_turn(structured_request(schema=schema))

    assert result.structuredOutputDiagnostic is not None
    assert result.structuredOutputDiagnostic.code == "schema_violation"
    assert result.structuredOutputDiagnostic.jsonPointer == "/outer/known"
    assert result.structuredOutputDiagnostic.keyword == "required"


@pytest.mark.asyncio
async def test_responses_any_of_diagnostic_selects_safe_nested_leaf(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """union 失败要指向已知内层字段，不回显私密值或分支正文。"""

    private_value = "SECRET_LIGHTING_VALUE_MUST_NOT_LEAK"
    schema = {
        "type": "object",
        "properties": {
            "lightingCue": {
                "anyOf": [
                    {
                        "$ref": "#/$defs/LightingCue",
                    },
                    {"type": "null"},
                ]
            }
        },
        "required": ["lightingCue"],
        "additionalProperties": False,
        "$defs": {
            "LightingCue": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["motivated_change"]},
                    "level": {"type": "integer", "minimum": 2},
                    "note": {"type": "string"},
                },
                "required": ["mode", "level", "note"],
                "additionalProperties": False,
            }
        },
    }
    caplog.set_level(logging.WARNING, logger=provider_module.__name__)

    result, _ = await complete_responses_text(
        monkeypatch,
        text=json.dumps(
            {
                "lightingCue": {
                    "mode": "motivated_change",
                    "level": 1,
                    "note": private_value,
                }
            }
        ),
        schema=schema,
    )

    assert result.structuredOutputDiagnostic is not None
    assert result.structuredOutputDiagnostic.jsonPointer == "/lightingCue/level"
    assert result.structuredOutputDiagnostic.keyword == "minimum"
    assert private_value not in result.model_dump_json()
    assert private_value not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_code", "expected_finish"),
    [
        (
            responses_payload(status="incomplete", incomplete_reason="max_output_tokens"),
            "response_incomplete",
            "length",
        ),
        (responses_payload(status="failed"), "response_failed", "unknown"),
        (responses_payload(output=[]), "empty_output", "stop"),
        (
            responses_payload(
                output=[
                    {
                        "id": "msg-multiple",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"value":1}',
                                "annotations": [],
                            },
                            {
                                "type": "output_text",
                                "text": '{"value":2}',
                                "annotations": [],
                            },
                        ],
                    }
                ]
            ),
            "multiple_text_outputs",
            "stop",
        ),
    ],
)
async def test_responses_rejects_non_terminal_or_non_unique_text_results(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    payload: dict[str, Any],
    expected_code: str,
    expected_finish: str,
) -> None:
    """未完成、失败、空输出和多个文本块都必须收敛为显式安全失败。"""

    async def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        caplog.set_level(logging.INFO, logger=provider_module.__name__)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        result = await provider.complete_turn(structured_request())

    assert result.content == ""
    assert result.structuredOutput is None
    assert result.structuredOutputDiagnostic is not None
    assert result.structuredOutputDiagnostic.code == expected_code
    assert result.finishReason == expected_finish
    assert "供应商私密错误" not in result.model_dump_json()
    audit_records = [
        record for record in caplog.records if record.message == "供应商结构化输出审计"
    ]
    assert len(audit_records) == 1
    assert audit_records[0].provider_response_id == "resp-structured-test"  # type: ignore[attr-defined]
    assert audit_records[0].provider_status == payload["status"]  # type: ignore[attr-defined]
    assert "供应商私密错误" not in caplog.text


@pytest.mark.asyncio
async def test_chat_json_output_uses_response_format_and_local_schema_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat 降级路由只发送 json_object，并仍以本地 Schema 决定是否接受。"""

    request_paths: list[str] = []
    request_bodies: list[dict[str, Any]] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_paths.append(request.url.path)
        request_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chat-structured-test",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"value":2}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "prompt_cache_hit_tokens": 4,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        result = await provider.complete_turn(structured_request(route="chat_json_output_v1"))

    assert request_paths == ["/v1/chat/completions"]
    body = request_bodies[0]
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 321
    assert body["thinking"] == {"type": "disabled"}
    assert "tools" not in body
    assert "tool_choice" not in body
    assert "text" not in body
    assert result.content == ""
    assert result.structuredOutput == {"value": 2}
    assert result.structuredOutputDiagnostic is None
    assert result.usage == ModelUsage(
        promptTokens=12,
        cachedTokens=4,
        completionTokens=5,
        totalTokens=17,
    )


@pytest.mark.asyncio
async def test_chat_json_output_http_failure_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """显式 Chat JSON 路由同样不能由 SDK 暗中重发或切换 Responses。"""

    request_paths: list[str] = []
    private_body = "SECRET_BODY_CHAT_MUST_NOT_LEAK"

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_paths.append(request.url.path)
        return httpx.Response(
            500,
            request=request,
            json={"error": {"message": private_body, "type": "server_error"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        caplog.set_level(logging.WARNING, logger=provider_module.__name__)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )

        with pytest.raises(ProviderTransportError) as caught:
            await provider.complete_turn(structured_request(route="chat_json_output_v1"))

    assert request_paths == ["/v1/chat/completions"]
    error = caught.value
    assert error.code == "http_error"
    assert error.statusCode == 500
    assert error.requestId is None
    assert error.retryable is True
    assert_exception_chain_is_sanitized(error, private_body)
    assert private_body not in caplog.text


@pytest.mark.parametrize(
    ("route", "expected_path"),
    [
        ("responses_json_schema_v1", "/responses"),
        ("chat_json_output_v1", "/v1/chat/completions"),
    ],
)
@pytest.mark.parametrize(
    ("failure_kind", "expected_code"),
    [
        ("timeout", "timeout_error"),
        ("connection", "connection_error"),
    ],
)
@pytest.mark.asyncio
async def test_structured_transport_failure_is_safe_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    route: str,
    expected_path: str,
    failure_kind: str,
    expected_code: str,
) -> None:
    """两条结构化路由的超时和连接错误均需脱敏，并禁止 SDK 隐式重试。"""

    request_paths: list[str] = []
    private_message = f"SECRET_BODY_{failure_kind.upper()}_MUST_NOT_LEAK"

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_paths.append(request.url.path)
        if failure_kind == "timeout":
            raise httpx.ReadTimeout(private_message, request=request)
        raise httpx.ConnectError(private_message, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        caplog.set_level(logging.WARNING, logger=provider_module.__name__)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )

        with pytest.raises(ProviderTransportError) as caught:
            await provider.complete_turn(structured_request(route=route))

    assert request_paths == [expected_path]
    error = caught.value
    assert error.code == expected_code
    assert error.statusCode is None
    assert error.requestId is None
    assert error.retryable is True
    assert_exception_chain_is_sanitized(error, private_message)
    assert private_message not in caplog.text


@pytest.mark.asyncio
async def test_invalid_structured_schema_fails_before_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无效 Schema 属于程序错误，必须在供应商计费请求之前拒绝。"""

    request_paths: list[str] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_paths.append(request.url.path)
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )

        with pytest.raises(ValueError, match="不是有效的 JSON Schema"):
            await provider.complete_turn(
                structured_request(schema={"type": "not-a-json-schema-type"})
            )

    assert request_paths == []


@pytest.mark.asyncio
async def test_chat_json_output_requires_json_word_before_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat JSON Output 缺少官方要求的 json 提示词时不能消耗供应商请求。"""

    request_paths: list[str] = []

    async def handle_request(request: httpx.Request) -> httpx.Response:
        request_paths.append(request.url.path)
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        request = structured_request(route="chat_json_output_v1")
        request.messages = [
            request.messages[0].model_copy(update={"content": "只输出符合指定结构的对象。"}),
            request.messages[1].model_copy(update={"content": "生成测试对象"}),
        ]

        with pytest.raises(ValueError, match="必须显式包含 json"):
            await provider.complete_turn(request)

    assert request_paths == []


@pytest.mark.parametrize(
    ("value", "expected_keyword"),
    [
        (5, None),
        (1, "minimum"),
    ],
)
@pytest.mark.asyncio
async def test_single_json_fence_is_unwrapped_and_fully_validated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    value: int,
    expected_keyword: str | None,
) -> None:
    """单一完整 json 围栏可机械解包，但不能绕过原始 Schema 的本地约束。"""

    schema = {
        "type": "object",
        "properties": {"value": {"type": "integer", "minimum": 5}},
        "required": ["value"],
        "additionalProperties": False,
    }
    raw_text = f' \n```json\n{{"value":{value}}}\n```\n '
    caplog.set_level(logging.WARNING, logger=provider_module.__name__)

    result, _ = await complete_responses_text(
        monkeypatch,
        text=raw_text,
        schema=schema,
    )

    recovery_records = [
        record
        for record in caplog.records
        if record.message == "供应商结构化输出已执行确定性恢复 code=unwrap_single_json_fence"
    ]
    assert len(recovery_records) == 1
    recovery = recovery_records[0]
    assert (  # type: ignore[attr-defined]
        recovery.structured_recovery_code == "unwrap_single_json_fence"
    )
    assert not hasattr(recovery, "raw_text")
    assert not hasattr(recovery, "output")
    if expected_keyword is None:
        assert result.structuredOutput == {"value": 5}
        assert result.structuredOutputDiagnostic is None
    else:
        assert result.structuredOutput is None
        assert result.structuredOutputDiagnostic is not None
        assert result.structuredOutputDiagnostic.code == "schema_violation"
        assert result.structuredOutputDiagnostic.jsonPointer == "/value"
        assert result.structuredOutputDiagnostic.keyword == expected_keyword
        assert 'code=schema_violation pointer="/value" keyword=minimum' in caplog.text


@pytest.mark.parametrize(
    "raw_text",
    [
        '前置说明 SECRET_BODY\n```json\n{"value":1}\n```',
        '```json\n{"value":1}\n```\n后置说明 SECRET_BODY',
        '```JSON\n{"value":1}\n```',
        '```javascript\n{"value":1}\n```',
        '```json {"value":1} ```',
        '```json\n{"value":"```"}\n```',
        '```json\n{"value":1}\n```\n```json\n{"value":2}\n```',
        '{"value":1}{"value":2}',
        '{"value":1',
    ],
    ids=[
        "prefix-explanation",
        "suffix-explanation",
        "uppercase-language",
        "other-language",
        "inline-fence",
        "nested-backticks",
        "multiple-fences",
        "concatenated-json",
        "truncated-json",
    ],
)
@pytest.mark.asyncio
async def test_structured_output_rejects_ambiguous_or_incomplete_json_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raw_text: str,
) -> None:
    """说明文字、多围栏、拼接和截断都不能被猜测性修复为成功。"""

    caplog.set_level(logging.WARNING, logger=provider_module.__name__)
    result, _ = await complete_responses_text(monkeypatch, text=raw_text)

    assert result.structuredOutput is None
    assert result.structuredOutputDiagnostic is not None
    assert result.structuredOutputDiagnostic.code == "json_decode_error"
    assert result.structuredOutputDiagnostic.jsonPointer == ""
    assert result.structuredOutputDiagnostic.keyword == "json"
    assert 'code=json_decode_error pointer="" keyword=json' in caplog.text
    assert "供应商结构化输出已执行确定性恢复" not in caplog.text
    assert "SECRET_BODY" not in result.model_dump_json()
    assert "SECRET_BODY" not in caplog.text


@pytest.mark.asyncio
async def test_structured_output_invalid_json_never_returns_partial_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非法 JSON 的部分正文只能存在于解析栈，结果和日志均不得保留。"""

    private_fragment = '{"value":"private unfinished value"'

    async def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json=responses_payload(
                output=[
                    {
                        "id": "msg-invalid-json",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": private_fragment,
                                "annotations": [],
                            }
                        ],
                    }
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:

        def build_async_openai(**kwargs: Any) -> AsyncOpenAI:
            return AsyncOpenAI(**kwargs, http_client=client)

        monkeypatch.setattr(provider_module, "AsyncOpenAI", build_async_openai)
        provider = OpenAICompatibleProvider(
            Settings.model_validate(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "https://api.deepseek.com/v1",
                    "openai_model": "deepseek-v4-flash",
                }
            )
        )
        result = await provider.complete_turn(structured_request())

    assert result.structuredOutput is None
    assert result.structuredOutputDiagnostic is not None
    assert result.structuredOutputDiagnostic.code == "json_decode_error"
    assert result.structuredOutputDiagnostic.jsonPointer == ""
    assert result.structuredOutputDiagnostic.keyword == "json"
    assert "private unfinished value" not in result.model_dump_json()
