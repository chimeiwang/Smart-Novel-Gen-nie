from __future__ import annotations

from copy import deepcopy

import jsonschema_rs
import pytest
from inkforge_agents.providers.base import ModelMessage, ModelToolCall, ModelTurnRequest
from inkforge_agents.providers.deepseek_strict import (
    _compile_wire,
    _describe_codec,
    _UnionCodec,
    prepare_deepseek_tools,
)
from inkforge_agents.runtime.model_policy import CREATIVE_HIGH
from inkforge_agents.tools.registry import build_default_registry

OMITTED = {"_inkforgeState": "omitted"}
NULL = {"_inkforgeState": "null"}
EMPTY = {"_inkforgeEmpty": "empty"}


def prepared_tool(name: str):
    tool = build_default_registry().require(name).as_model_tool()
    request = ModelTurnRequest(
        messages=[ModelMessage(role="user", content="离线验证")],
        tools=[tool],
        maxOutputTokens=256,
        policy=CREATIVE_HIGH,
    )
    return prepare_deepseek_tools(request), request


def roundtrip(codec, value):
    wire = codec.encode(value)
    jsonschema_rs.validate(codec.schema, wire)
    decoded = codec.decode(wire)
    assert decoded == value
    assert type(decoded) is type(value)
    return wire


def test最近失败两个工具正常值保持业务形状且三态明确():
    prepared, _ = prepared_tool("get_recent_chapters")
    codec = prepared.codecs["get_recent_chapters"]
    assert roundtrip(codec, {"count": 6}) == {"count": 6}
    assert roundtrip(codec, {}) == {"count": OMITTED}
    assert roundtrip(codec, {"count": None}) == {"count": NULL}
    assert "正常值直接" in codec.schema["properties"]["count"]["description"]
    prepared, _ = prepared_tool("list_outline_summary")
    codec = prepared.codecs["list_outline_summary"]
    assert roundtrip(codec, {"scope": "tree_index", "include_full_summary": True}) == {
        "scope": "tree_index",
        "include_full_summary": True,
    }
    for invalid in (
        {"count": {"value": {"variant": "0", "value": 6}}},
        {"count": {"variant": "0", "value": 6}},
    ):
        count, _ = prepared_tool("get_recent_chapters")
        assert not jsonschema_rs.is_valid(count.codecs["get_recent_chapters"].schema, invalid)


@pytest.mark.parametrize("value", [0, False, "", [], {}, [None, {}]])
def test零false及全部真实空值保持区别(value):
    schema = {
        "type": "object",
        "properties": {
            "option": {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "boolean"},
                    {"type": "string"},
                    {
                        "type": "array",
                        "items": {
                            "anyOf": [
                                {"type": "null"},
                                {"type": "object", "properties": {}, "additionalProperties": False},
                            ]
                        },
                    },
                    {"type": "object", "properties": {}, "additionalProperties": False},
                    {"type": "null"},
                ]
            }
        },
        "additionalProperties": False,
    }
    codec = _compile_wire(schema, {})
    supplied = roundtrip(codec, {"option": value})
    assert supplied != roundtrip(codec, {})
    assert supplied != roundtrip(codec, {"option": None})


def test省略标记同形业务对象回退最小存在性判别():
    schema = {
        "type": "object",
        "properties": {
            "option": {
                "type": "object",
                "properties": {"_inkforgeState": {"type": "string", "enum": ["omitted"]}},
                "required": ["_inkforgeState"],
                "additionalProperties": False,
            }
        },
        "additionalProperties": False,
    }
    codec = _compile_wire(schema, {})
    assert codec.children["option"].kind == "optional_tagged"
    assert roundtrip(codec, {}) == {"option": {"variant": "omitted"}}
    assert roundtrip(codec, {"option": OMITTED}) == {
        "option": {"variant": "value", "value": OMITTED}
    }


def testnull标记同形业务对象和JSON字符串重叠不能猜解():
    marker = {
        "type": "object",
        "properties": {"_inkforgeState": {"type": "string"}},
        "required": ["_inkforgeState"],
        "additionalProperties": False,
    }
    codec = _compile_wire({"anyOf": [marker, {"type": "null"}]}, {})
    assert codec.kind == "union_tagged"
    assert roundtrip(codec, NULL) != roundtrip(codec, None)
    codec = _compile_wire({"anyOf": [{"type": "string"}, {"type": "object"}]}, {})
    assert codec.kind == "union_tagged"
    assert roundtrip(codec, "{}") != roundtrip(codec, {})
    assert roundtrip(codec, {"_inkforgeState": "null"})["variant"] == "1"


@pytest.mark.parametrize(
    "name,value",
    [
        ("get_outline_node", {"node_id": "id", "node_title": "标题"}),
        (
            "put_update_item_text_block",
            {
                "artifactKey": "草案",
                "section": "characters",
                "field": "description",
                "targetId": "id",
                "targetKey": "key",
                "targetName": "名字",
            },
        ),
        ("show_review_artifact", {"artifactId": "id", "artifactKey": "key"}),
        (
            "begin_artifact_output",
            {"kind": "chapter_draft", "summary": "摘要", "content": "完整正文"},
        ),
        ("submit_evaluation", {"verdict": "pass", "summary": "通过"}),
    ],
)
def test五个条件根联合用业务字段且重叠合法定位解码一致(name, value):
    prepared, _ = prepared_tool(name)
    codec = prepared.codecs[name]
    assert codec.kind == "union_flat"
    assert codec.schema["type"] == "object"
    assert codec.schema["properties"]
    assert set(codec.schema["required"]) == set(codec.schema["properties"])
    assert codec.schema["additionalProperties"] is False
    assert codec.schema["anyOf"]
    wire = roundtrip(codec, value)
    assert "variant" not in wire and "value" not in wire
    for key, item in value.items():
        assert wire[key] == item


def test根联合条件并未被外壳属性并集替代():
    prepared, _ = prepared_tool("get_outline_node")
    codec = prepared.codecs["get_outline_node"]
    with pytest.raises(ValueError):
        codec.encode({})
    wire = roundtrip(codec, {"node_id": "id"})
    wire["node_id"] = OMITTED
    assert not jsonschema_rs.is_valid(codec.schema, wire)
    prepared, _ = prepared_tool("submit_evaluation")
    codec = prepared.codecs["submit_evaluation"]
    wire = roundtrip(codec, {"verdict": "pass", "summary": "通过"})
    wire["revisionMode"] = "patch"
    assert not jsonschema_rs.is_valid(codec.schema, wire)
    with pytest.raises(ValueError):
        codec.encode({"verdict": "revise", "summary": "返工", "revisionMode": "patch"})
    rewrite = roundtrip(codec, {"verdict": "revise", "summary": "返工", "revisionMode": "rewrite"})
    for invalid in ("patch", NULL):
        wire = {**rewrite, "revisionMode": invalid}
        assert not jsonschema_rs.is_valid(codec.schema, wire)
    patch = roundtrip(
        codec,
        {
            "verdict": "revise",
            "summary": "返工",
            "revisionMode": "patch",
            "patches": [{"kind": "text_replace", "find": "旧", "replace": "新"}],
        },
    )
    for invalid in ("rewrite", NULL):
        wire = {**patch, "revisionMode": invalid}
        assert not jsonschema_rs.is_valid(codec.schema, wire)
    prepared, _ = prepared_tool("begin_artifact_output")
    codec = prepared.codecs["begin_artifact_output"]
    wire = roundtrip(codec, {"kind": "chapter_draft", "summary": "摘要", "content": "正文"})
    wire["replacement"] = "选区替换"
    assert not jsonschema_rs.is_valid(codec.schema, wire)


def test完整选区输入不造字段并拒绝缺失冻结定位():
    prepared, _ = prepared_tool("begin_artifact_output")
    codec = prepared.codecs["begin_artifact_output"]
    selection = {
        "kind": "chapter_content",
        "summary": "替换",
        "operation": "rewrite_chapter_selection",
        "resourceType": "chapter_content",
        "resourceId": "chapter",
        "baseUpdatedAt": "timestamp",
        "baseContentHash": "a" * 64,
        "selectionStart": 0,
        "selectionEnd": 2,
        "selectedTextHash": "b" * 64,
        "replacement": "新正文",
    }
    wire = roundtrip(codec, selection)
    assert wire["content"] == OMITTED
    wire["resourceId"] = OMITTED
    assert not jsonschema_rs.is_valid(codec.schema, wire)


def test历史业务参数按新codec重编码且原消息不修改():
    _, request = prepared_tool("get_recent_chapters")
    request.messages.append(
        ModelMessage(
            role="assistant",
            content="",
            toolCalls=[
                ModelToolCall(id="history", name="get_recent_chapters", arguments={"count": 6})
            ],
        )
    )
    before = deepcopy(request.model_dump())
    prepared = prepare_deepseek_tools(request)
    assert prepared.request.messages[-1].tool_calls[0].arguments == {"count": 6}
    assert request.model_dump() == before


def test全工具闭合全必填非空且质量专用投影保持():
    def inspect(schema):
        if schema.get("type") == "object":
            assert schema["properties"]
            assert set(schema["required"]) == set(schema["properties"])
            assert schema["additionalProperties"] is False
            for child in schema["properties"].values():
                inspect(child)
        for child in schema.get("anyOf", []):
            inspect(child)
        if "items" in schema:
            inspect(schema["items"])

    for tool in build_default_registry().all():
        prepared, _ = prepared_tool(tool.name)
        inspect(prepared.request.tools[0].parameters)
        if tool.name == "submit_quality_report":
            assert prepared.codecs[tool.name].kind == "quality"
        if tool.name == "list_available_data":
            assert roundtrip(prepared.codecs[tool.name], {}) == EMPTY


def test必填字段保留业务描述且非空正常例子符合实际wire():
    codec = _compile_wire(
        {
            "type": "object",
            "properties": {
                "name": {"description": "角色职责", "anyOf": [{"type": "string"}, {"type": "null"}]}
            },
            "additionalProperties": False,
        },
        {},
    )
    description = codec.schema["properties"]["name"]["anyOf"][0]["description"]
    assert "角色职责" in description
    assert roundtrip(codec, {"name": "角色"}) == {"name": "角色"}


def test多个匹配分支解码不一致时保护拒绝而不是选择首个():
    original = [{"type": "string"}, {"type": "object"}]
    children = [_compile_wire(schema, {}) for schema in original]
    # 故意绕过编译时的兼容证明，验证运行时的第二层歧义保护。
    codec = _UnionCodec(
        {"anyOf": [child.schema for child in children]},
        "union_flat",
        branches=list(zip(original, children, strict=True)),
    )
    with pytest.raises(ValueError, match="歧义"):
        codec.decode("{}")


def testbuilder继承状态与false及开放JSON全部键值不混合():
    prepared, _ = prepared_tool("finish_update_builder")
    codec = prepared.codecs["finish_update_builder"]
    omitted = roundtrip(codec, {"artifactKey": "a", "summary": "摘要"})
    explicit = roundtrip(codec, {"artifactKey": "a", "summary": "摘要", "submitForReview": False})
    assert omitted["submitForReview"] == OMITTED
    assert explicit["submitForReview"] is False
    prepared, _ = prepared_tool("append_update_batch")
    codec = prepared.codecs["append_update_batch"]
    value = {
        "artifactKey": "a",
        "updates": {"任意键": [None, False, 0, "", {}, []], "_inkforgeState": "omitted"},
    }
    wire = roundtrip(codec, value)
    assert isinstance(wire["updates"], str)


def test不能称不满足Schema的枚举示例为合法():
    codec = _compile_wire({"type": "integer", "enum": ["不可能的值"]}, {})
    described = _describe_codec(codec)
    assert "合法形状示例" not in described.schema["description"]
