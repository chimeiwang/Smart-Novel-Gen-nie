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
from inkforge_agents.providers.openai_compatible import OpenAICompatibleProvider
from inkforge_agents.runtime.model_policy import CREATIVE_HIGH
from inkforge_agents.tools.control import artifact_model_schema_for_operation
from inkforge_agents.tools.registry import build_default_registry
from langchain_openai import ChatOpenAI

_EMPTY = {"_inkforgeEmpty": "empty"}


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
    provider._model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        http_async_client=client,
        max_retries=0,
    )
    provider._strict_model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url="https://api.deepseek.com/beta",
        model=settings.openai_model,
        http_async_client=client,
        max_retries=0,
    )
    return provider


@pytest.mark.parametrize("kind", ["raw", "generic"])
@pytest.mark.parametrize(
    "count_wire,expected", [(_EMPTY, {}), ({"value": {"variant": "0", "value": 3}}, {"count": 3})]
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
        ({}, {"option": _EMPTY}),
        ({"option": None}, {"option": {"value": {"variant": "1", "value": _EMPTY}}}),
        ({"option": ""}, {"option": {"value": {"variant": "0", "value": ""}}}),
        ({"option": "正文"}, {"option": {"value": {"variant": "0", "value": "正文"}}}),
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
        "summary": _EMPTY,
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
        "artifactKey": _EMPTY,
        "reviewerAgent": _EMPTY,
        "submitForReview": _EMPTY,
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
    # 第零分支只允许 pass/block；revise 必须进入带完整 revisionMode 的其他分支。
    wire = {
        "value": {
            "variant": "0",
            "value": {
                "artifactKey": _EMPTY,
                "artifactId": _EMPTY,
                "requiredChanges": _EMPTY,
                "verdict": verdict,
                "summary": "完整复审报告",
                "revisionMode": _EMPTY,
                "patches": _EMPTY,
            },
        }
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
        "artifactKey": _EMPTY,
        "reviewerAgent": _EMPTY,
        "submitForReview": _EMPTY,
        "mainPlotConnection": _EMPTY,
        "chapterAcceptanceCriteria": _EMPTY,
        "totalEstimatedWords": _EMPTY,
        "sceneBeats": [
            {
                "goal": "进入城门",
                "order": _EMPTY,
                "conflict": _EMPTY,
                "characters": _EMPTY,
                "foreshadowingRefs": _EMPTY,
                "estimatedWords": _EMPTY,
                "acceptanceCriteria": _EMPTY,
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
