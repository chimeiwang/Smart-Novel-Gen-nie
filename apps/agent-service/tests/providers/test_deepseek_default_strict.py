from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import httpx
import jsonschema_rs
import pytest
from inkforge_agents.config import Settings
from inkforge_agents.providers.base import ModelMessage, ModelTool, ModelToolCall, ModelTurnRequest
from inkforge_agents.providers.deepseek_strict import _closed_object, prepare_deepseek_tools
from inkforge_agents.providers.deepseek_v4 import DeepSeekV4Provider
from inkforge_agents.providers.openai_compatible import (
    OpenAICompatibleProvider,
    _DeepSeekChatOpenAI,
)
from inkforge_agents.runtime.model_policy import CREATIVE_HIGH
from inkforge_agents.tools.control import artifact_model_schema_for_operation
from inkforge_agents.tools.registry import build_default_registry
from langchain_openai import ChatOpenAI

_EMPTY = {"_inkforgeEmpty": "empty"}
_OMITTED = {"_inkforgeState": "omitted"}
_NULL = {"_inkforgeState": "null"}


def test闭合对象构造拒绝无属性回归():
    with pytest.raises(ValueError, match="至少声明一个属性"):
        _closed_object({})


@pytest.mark.parametrize(
    "value",
    [None, 0, False, "", [], {}, {"_inkforgeEmpty": "业务值"}, _EMPTY, {"nested": {}}, [{}, None]],
)
def test标记保持全部业务空值和同名字段且历史往返不修改(value):
    empty_object = {"type": "object", "properties": {}, "additionalProperties": False}
    tool = ModelTool(
        name="submit",
        description="测试",
        parameters={
            "type": "object",
            "properties": {
                "option": {
                    "anyOf": [
                        {"type": "null"},
                        {"type": "integer"},
                        {"type": "boolean"},
                        {"type": "string"},
                        {"type": "array", "items": {"anyOf": [empty_object, {"type": "null"}]}},
                        empty_object,
                        {
                            "type": "object",
                            "properties": {"_inkforgeEmpty": {"type": "string"}},
                            "required": ["_inkforgeEmpty"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {"nested": empty_object},
                            "required": ["nested"],
                            "additionalProperties": False,
                        },
                    ]
                }
            },
            "additionalProperties": False,
        },
    )
    arguments = {"option": deepcopy(value)}
    request = _request([tool])
    request.messages.append(
        ModelMessage(
            role="assistant",
            content="",
            toolCalls=[
                ModelToolCall(id="history", name=tool.name, arguments=deepcopy(arguments)),
            ],
        )
    )
    before = request.model_dump()
    prepared = prepare_deepseek_tools(request)
    codec = prepared.codecs[tool.name]
    wire = codec.encode(arguments)
    jsonschema_rs.validate(codec.schema, wire)
    assert codec.decode(wire) == arguments
    assert prepared.request.messages[-1].tool_calls[0].arguments == wire
    assert request.model_dump() == before


@pytest.mark.parametrize("kind", ["raw", "generic"])
@pytest.mark.parametrize(
    "wire", [{}, {"_inkforgeEmpty": "wrong"}, {"_inkforgeEmpty": "empty", "extra": True}]
)
async def test无参工具拒绝非法标记且不能进入业务结果(kind, wire):
    tool = build_default_registry().require("list_available_data").as_model_tool()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_response(tool.name, wire)),
        )
    ) as client:
        result = await _provider(kind, client).complete_turn(_request([tool]))
    assert result.toolCalls == []
    assert result.invalidToolCallCodes == ["provider_strict_schema_violation"]


def test无参根对象历史恢复为空业务对象():
    tool = build_default_registry().require("list_available_data").as_model_tool()
    request = _request([tool])
    request.messages.append(
        ModelMessage(
            role="assistant",
            content="",
            toolCalls=[
                ModelToolCall(id="history", name=tool.name, arguments={}),
            ],
        )
    )
    prepared = prepare_deepseek_tools(request)
    codec = prepared.codecs[tool.name]
    assert codec.encode({}) == _EMPTY
    assert codec.decode(_EMPTY) == {}
    assert prepared.request.messages[-1].tool_calls[0].arguments == _EMPTY
    assert request.messages[-1].tool_calls[0].arguments == {}


def _request(tools: list[ModelTool]) -> ModelTurnRequest:
    return ModelTurnRequest(
        messages=[ModelMessage(role="user", content="请调用工具")],
        tools=tools,
        maxOutputTokens=256,
        policy=CREATIVE_HIGH,
    )


def _response(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "strict-default",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-v4-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "思考",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "prompt_cache_hit_tokens": 2,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }


def _provider(kind: str, client: httpx.AsyncClient) -> Any:
    settings = Settings.model_validate(
        {
            "environment": "test",
            "openai_api_key": "test-key",
            "openai_base_url": "https://api.deepseek.com",
            "openai_model": "deepseek-v4-flash",
        }
    )
    if kind == "raw":
        return DeepSeekV4Provider(settings, client=client)
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.model_name = settings.openai_model
    provider._model = _DeepSeekChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        http_async_client=client,
        max_retries=0,
    )
    provider._strict_model = _DeepSeekChatOpenAI(
        api_key=settings.openai_api_key,
        base_url="https://api.deepseek.com/beta",
        model=settings.openai_model,
        http_async_client=client,
        max_retries=0,
    )
    return provider


@pytest.mark.parametrize("kind", ["raw", "generic"])
@pytest.mark.parametrize(
    "count_wire,expected", [(_OMITTED, {}), (3, {"count": 3})]
)
async def test默认读取工具经_beta且无损保留省略与值(kind, count_wire, expected):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_response("get_recent_chapters", {"count": count_wire}))

    tools = [
        build_default_registry().require(name).as_model_tool()
        for name in ("get_recent_chapters", "get_novel_info")
    ]
    request = _request(tools)
    original = request.model_dump()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(kind, client).complete_turn(request)
    assert request.model_dump() == original
    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.deepseek.com/beta/chat/completions"
    payload = json.loads(requests[0].content)
    assert all(tool["function"]["strict"] is True for tool in payload["tools"])
    assert result.toolCalls[0].arguments == expected
    assert result.usage.totalTokens == 15
    assert result.invalidToolCallCount == 0


@pytest.mark.parametrize("kind", ["raw", "generic"])
async def test默认_strict解码后仍校验原业务约束(kind):
    tool = ModelTool(
        name="submit",
        description="提交完整正文",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 5}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_response("submit", {"text": "短"})),
        )
    ) as client:
        result = await _provider(kind, client).complete_turn(_request([tool]))
    assert result.toolCalls == []
    assert result.invalidToolCallCodes == ["provider_strict_schema_violation"]
    assert result.usage.totalTokens == 15
    diagnostic = result.failureDiagnostics[0]
    assert diagnostic.stage == "tool.business_schema"
    assert json.loads(diagnostic.payloadJson)["arguments"] == {"text": "短"}
    assert json.loads(diagnostic.payloadJson)["validationErrors"]
    assert "failureDiagnostics" not in result.model_dump()


def test历史参数校验错误附完整日志诊断且不改变异常():
    tool = build_default_registry().require("get_recent_chapters").as_model_tool()
    request = _request([tool])
    request.messages.append(
        ModelMessage(
            role="assistant",
            content="",
            toolCalls=[
                ModelToolCall(id="history-bad", name=tool.name, arguments={"count": 0}),
            ],
        )
    )
    before = request.model_dump()
    with pytest.raises(ValueError) as caught:
        prepare_deepseek_tools(request)
    diagnostic = caught.value.failureDiagnostics[0]
    assert diagnostic.stage == "tool.history_business_schema"
    payload = json.loads(diagnostic.payloadJson)
    assert payload["arguments"] == {"count": 0}
    assert payload["callId"] == "history-bad"
    assert payload["businessSchema"] == tool.parameters
    assert payload["validationErrors"]
    assert request.model_dump() == before


def test所有注册工具的默认_schema符合_deepseek子集():
    tools = [tool.as_model_tool() for tool in build_default_registry().all()]
    request = _request(tools)
    before = request.model_dump()
    prepared = prepare_deepseek_tools(request)

    def inspect(node):
        if not isinstance(node, dict):
            return
        assert (
            not {
                "$ref",
                "$defs",
                "$def",
                "default",
                "minLength",
                "maxLength",
                "minItems",
                "maxItems",
                "oneOf",
                "allOf",
            }
            & node.keys()
        )
        assert node.get("type") != "null"
        if node.get("type") == "object":
            assert node["properties"]
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                inspect(child)
        for branch in node.get("anyOf", []):
            inspect(branch)
        if "items" in node:
            inspect(node["items"])

    for tool in prepared.request.tools:
        assert tool.strict is True
        inspect(tool.parameters)
        jsonschema_rs.validator_for(tool.parameters)
    assert request.model_dump() == before


@pytest.mark.parametrize(
    "value,wire",
    [
        ({}, {"option": _OMITTED}),
        ({"option": None}, {"option": _NULL}),
        ({"option": ""}, {"option": ""}),
        ({"option": "正文"}, {"option": "正文"}),
    ],
)
def test省略_null与空串往返独立(value, wire):
    tool = ModelTool(
        name="submit",
        description="测试",
        parameters={
            "type": "object",
            "properties": {
                "option": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "null"},
                    ]
                }
            },
            "additionalProperties": False,
        },
    )
    request = _request([tool])
    request.messages.append(
        ModelMessage(
            role="assistant",
            content="",
            toolCalls=[
                ModelToolCall(id="previous", name="submit", arguments=deepcopy(value)),
            ],
            reasoning_content="保留进程内思考",
        )
    )
    prepared = prepare_deepseek_tools(request)
    codec = prepared.codecs["submit"]
    assert prepared.request.messages[-1].tool_calls[0].arguments == wire
    assert prepared.request.messages[-1].reasoningContent == "保留进程内思考"
    jsonschema_rs.validate(codec.schema, wire)
    assert codec.decode(wire) == value
    assert request.messages[-1].tool_calls[0].arguments == value


def test动态JSON保留全部键与空值并拒绝坏JSON():
    tool = build_default_registry().require("append_update_batch").as_model_tool()
    codec = prepare_deepseek_tools(_request([tool])).codecs[tool.name]
    value = {"artifactKey": "a", "updates": {"自定义": [None, False, 0, "", {}, []]}}
    expected = {
        "artifactKey": "a",
        "updates": '{"自定义":[null,false,0,"",{},[]]}',
        "summary": _OMITTED,
    }
    assert codec.encode(value) == expected
    assert codec.decode(expected) == value
    for invalid in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":'):
        with pytest.raises(ValueError):
            codec.decode({**expected, "updates": invalid})


@pytest.mark.parametrize("operation", ["write_chapter", "rewrite_scene"])
@pytest.mark.parametrize("kind", ["raw", "generic"])
async def test正文提交保留操作收窄与完整内容(operation, kind):
    tool = (
        build_default_registry()
        .require("begin_artifact_output")
        .as_model_tool(
            parameters=artifact_model_schema_for_operation(operation),
        )
    )
    content = "完整正文\n" * 10_000
    wire = {
        "kind": "chapter_draft",
        "summary": "本章草案",
        "content": content,
        "artifactKey": _OMITTED,
        "reviewerAgent": _OMITTED,
        "submitForReview": _OMITTED,
    }
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_response(tool.name, wire))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(kind, client).complete_turn(_request([tool]))
    assert result.toolCalls[0].arguments == {
        "kind": "chapter_draft",
        "summary": "本章草案",
        "content": content,
    }
    parameters = json.loads(requests[0].content)["tools"][0]["function"]["parameters"]
    assert parameters["properties"]["kind"] == {"type": "string", "enum": ["chapter_draft"]}
    assert "replacement" not in parameters["properties"]


@pytest.mark.parametrize("kind", ["raw", "generic"])
async def test未开启strict的兼容调用保留标准端点(kind):
    tool = ModelTool(
        name="read",
        description="兼容",
        strict=False,
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_response(tool.name, {}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(kind, client).complete_turn(_request([tool]))
    assert result.toolCalls[0].arguments == {}
    assert str(requests[0].url) == "https://api.deepseek.com/chat/completions"
    assert not json.loads(requests[0].content)["tools"][0]["function"].get("strict", False)


async def test非DeepSeek保持原默认值():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_response("read", {}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
        provider.model_name = "other-model"
        provider._strict_model = None
        provider._model = ChatOpenAI(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="other-model",
            http_async_client=client,
            max_retries=0,
        )
        await provider.complete_turn(
            _request(
                [
                    ModelTool(
                        name="read",
                        description="查询",
                        parameters={"type": "object", "properties": {}},
                    )
                ]
            )
        )
    function = json.loads(requests[0].content)["tools"][0]["function"]
    assert function["strict"] is False
    assert function["parameters"] == {"type": "object", "properties": {}}


@pytest.mark.parametrize("kind", ["raw", "generic"])
@pytest.mark.parametrize("verdict,accepted", [("pass", True), ("revise", False)])
async def test复审默认_strict且拒绝不完整返工组合(kind, verdict, accepted):
    tool = build_default_registry().require("submit_evaluation").as_model_tool()
    # pass/block 只要求摘要；revise 必须携带完整 revisionMode 与对应修改资料。
    wire = {
        "artifactKey": _OMITTED,
        "artifactId": _OMITTED,
        "requiredChanges": _OMITTED,
        "verdict": verdict,
        "summary": "完整复审报告",
        "revisionMode": _OMITTED,
        "patches": _OMITTED,
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_response(tool.name, wire)),
        )
    ) as client:
        result = await _provider(kind, client).complete_turn(_request([tool]))
    if accepted:
        assert result.toolCalls[0].arguments == {"verdict": "pass", "summary": "完整复审报告"}
    else:
        assert result.toolCalls == []
        assert result.invalidToolCallCodes == ["provider_strict_schema_violation"]
        assert result.usage.totalTokens == 15


@pytest.mark.parametrize("kind", ["raw", "generic"])
async def test节拍计划嵌套默认字段可省略且不请求派生计数(kind):
    tool = build_default_registry().require("submit_beat_plan").as_model_tool()
    wire = {
        "title": "进城",
        "summary": "找到线索",
        "chapterGoal": "抵达城门",
        "artifactKey": _OMITTED,
        "reviewerAgent": _OMITTED,
        "submitForReview": _OMITTED,
        "mainPlotConnection": _OMITTED,
        "chapterAcceptanceCriteria": _OMITTED,
        "totalEstimatedWords": _OMITTED,
        "sceneBeats": [
            {
                "goal": "进入城门",
                "order": _OMITTED,
                "conflict": _OMITTED,
                "characters": _OMITTED,
                "foreshadowingRefs": _OMITTED,
                "estimatedWords": _OMITTED,
                "acceptanceCriteria": _OMITTED,
            }
        ],
    }
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_response(tool.name, wire))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(kind, client).complete_turn(_request([tool]))
    arguments = result.toolCalls[0].arguments
    assert arguments["sceneBeats"] == [{"goal": "进入城门"}]
    assert "beatCount" not in arguments
    assert (
        build_default_registry().require(tool.name).validate_model_arguments(arguments)["beatCount"]
        == 1
    )
    assert (
        "beatCount"
        not in json.loads(requests[0].content)["tools"][0]["function"]["parameters"]["properties"]
    )


@pytest.mark.parametrize("kind", ["raw", "generic"])
@pytest.mark.parametrize("tool_name,returned_arguments,business_arguments,accepted", [
    ("list_outline_summary", {"scope": {"value": "tree_index"},
        "include_full_summary": {"value": True}},
        {"scope": "tree_index", "include_full_summary": True}, False),
    ("get_recent_chapters", {"count": 6}, {"count": 6}, True),
    ("list_outline_summary", {"scope": {"variant": "0", "value": "tree_index"},
        "include_full_summary": {"variant": "0", "value": True}},
        {"scope": "tree_index", "include_full_summary": True}, False),
    ("get_recent_chapters", {"count": {"variant": "0", "value": 2}}, {"count": 2}, False),
])
async def test最新真实失败参数仅自然业务形状直接合法且旧半包装拒绝(
    kind, tool_name, returned_arguments, business_arguments, accepted,
):
    """用真实失败形状区分已简化的合法输入与仍应拒绝的错误包装。"""
    tool = build_default_registry().require(tool_name).as_model_tool()
    replies = [returned_arguments, business_arguments]
    calls = []

    def handler(incoming):
        calls.append(incoming)
        return httpx.Response(200, json=_response(tool_name, replies[len(calls) - 1]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = _provider(kind, client)
        original = _request([tool])
        before = original.model_dump()
        first = await provider.complete_turn(original)
        corrected = await provider.complete_turn(original)
    assert original.model_dump() == before
    assert len(calls) == 2
    assert first.usage.totalTokens == corrected.usage.totalTokens == 15
    if accepted:
        assert first.toolCalls[0].arguments == business_arguments
        assert first.invalidToolCallCount == 0
        assert first.failureDiagnostics == []
    else:
        assert first.toolCalls == []
        assert first.invalidToolCallCodes == ["provider_strict_schema_violation"]
        diagnostic = first.failureDiagnostics[0]
        assert "wire" in diagnostic.stage
        failed_payload = json.loads(diagnostic.payloadJson)
        # 原失败参数完整可查，未自动拆包或降低原业务校验。
        if "rawArguments" in failed_payload:
            assert json.loads(failed_payload["rawArguments"]) == returned_arguments
        else:
            assert failed_payload["arguments"] == returned_arguments
        assert "failureDiagnostics" not in first.model_dump()
    assert corrected.invalidToolCallCount == 0
    assert corrected.toolCalls[0].arguments == business_arguments
    assert corrected.failureDiagnostics == []
    assert "_inkforge_raw_tool_calls" not in corrected.model_dump_json()
    schema = json.loads(calls[0].content)["tools"][0]["function"]["parameters"]
    jsonschema_rs.validate(schema, business_arguments)
    if not accepted:
        assert not jsonschema_rs.is_valid(schema, returned_arguments)


@pytest.mark.parametrize("kind", ["raw", "generic"])
async def test两轮历史业务参数按新自然wire重编码且不修改原历史(kind):
    """旧历史保存业务参数；下一轮使用新 wire，业务结果和用量保持完整。"""
    registry = build_default_registry()
    tools = [registry.require(name).as_model_tool()
        for name in ("get_recent_chapters", "list_outline_summary")]
    calls = []

    def handler(incoming):
        calls.append(incoming)
        if len(calls) == 1:
            return httpx.Response(200, json=_response("get_recent_chapters", {"count": 6}))
        body = json.loads(incoming.content)
        previous_call = body["messages"][-2]["tool_calls"][0]
        assert json.loads(previous_call["function"]["arguments"]) == {"count": 6}
        return httpx.Response(200, json=_response("list_outline_summary", {
            "scope": "tree_index", "include_full_summary": True,
        }))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = _provider(kind, client)
        first_request = _request(tools)
        first = await provider.complete_turn(first_request)
        history = ModelMessage(role="assistant", content="", toolCalls=first.toolCalls,
            reasoning_content="仅进程内历史思考")
        second_request = _request(tools)
        second_request.messages.extend([history, ModelMessage(role="tool",
            name="get_recent_chapters", toolCallId="call-1", content='{"result":"已读取"}')])
        before = second_request.model_dump()
        second = await provider.complete_turn(second_request)
    assert len(calls) == 2
    assert second_request.model_dump() == before
    assert history.tool_calls[0].arguments == {"count": 6}
    assert history.reasoningContent == "仅进程内历史思考"
    assert first.invalidToolCallCount == second.invalidToolCallCount == 0
    assert first.usage.totalTokens == second.usage.totalTokens == 15
    assert second.toolCalls[0].arguments == {
        "scope": "tree_index", "include_full_summary": True,
    }
    assert second.failureDiagnostics == []


@pytest.mark.parametrize("kind", ["raw", "generic"])
@pytest.mark.parametrize("raw_arguments", [
    '{"count":3,"count":6}', '{"count":NaN}', '{"count":Infinity}',
])
async def test自然参数wire从原JSON拒绝重复键和非有限数且保留完整失败用量(kind, raw_arguments):
    """不能只信SDK已解析字典；原JSON字段覆盖与非标准常量都必须拒绝。"""
    tool = build_default_registry().require("get_recent_chapters").as_model_tool()
    reply = _response(tool.name, {})
    reply["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = raw_arguments
    calls = []
    def handler(incoming):
        calls.append(incoming)
        return httpx.Response(200, json=reply)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(kind, client).complete_turn(_request([tool]))
    assert len(calls) == 1
    assert result.toolCalls == []
    assert result.invalidToolCallCount == 1
    assert result.invalidToolCallCodes == ["json_decode_error"]
    assert result.invalidToolCallNames == [tool.name]
    assert result.invalidToolCallArgumentCharacterCounts == [len(raw_arguments)]
    assert result.recoveredToolCallCount == 0
    assert result.usage.totalTokens == 15
    diagnostic = result.failureDiagnostics[0]
    assert diagnostic.stage == "tool.json_parse"
    assert json.loads(diagnostic.payloadJson)["rawArguments"] == raw_arguments
    assert diagnostic.errorDetails.exceptionChain
    assert "failureDiagnostics" not in result.model_dump()


@pytest.mark.parametrize("kind", ["raw", "generic"])
@pytest.mark.parametrize("raw_arguments,recovered", [
    ('{"count":3', True),
    ('{"count":3,"count":4', False),
    ('{"count":NaN', False),
])
async def test唯一必调工具恢复仍拒绝闭合候选重复键和非有限数(kind, raw_arguments, recovered):
    """追加闭合符不能把会丢字段或非标准数字的原JSON升级成合法工具调用。"""
    tool = build_default_registry().require("get_recent_chapters").as_model_tool()
    reply = _response(tool.name, {})
    reply["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = raw_arguments
    calls = []
    def handler(incoming):
        calls.append(incoming)
        return httpx.Response(200, json=reply)

    request = _request([tool]).model_copy(update={"requiredToolName": tool.name,
        "parallelToolCalls": False})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _provider(kind, client).complete_turn(request)
    assert len(calls) == 1
    assert result.usage.totalTokens == 15
    assert result.usage.promptTokens == 10
    assert result.usage.completionTokens == 5
    if recovered:
        assert result.toolCalls[0].arguments == {"count": 3}
        assert result.invalidToolCallCount == 0
        assert result.recoveredToolCallCount == 1
        assert result.recoveredToolCallCodes == ["append_container_closers"]
        assert result.recoveredToolCallAppendedContainerCounts == [1]
    else:
        assert result.toolCalls == []
        assert result.invalidToolCallCount == 1
        assert result.invalidToolCallCodes == ["json_decode_error"]
        assert result.recoveredToolCallCount == 0
    assert result.failureDiagnostics
    assert "failureDiagnostics" not in result.model_dump()
