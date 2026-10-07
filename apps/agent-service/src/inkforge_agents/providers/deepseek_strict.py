from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import jsonschema_rs

from .base import ModelTool, ModelTurnRequest, ModelTurnResult

_MISSING = object()
_EMPTY_MARKER = {"_inkforgeEmpty": "empty"}


def _closed_object(properties: dict[str, Any]) -> dict[str, Any]:
    if not properties:
        raise ValueError("DeepSeek strict 对象必须至少声明一个属性")
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


@dataclass
class _WireCodec:
    """只转换供应商表示；省略、null 与业务空值必须可逆。"""

    schema: dict[str, Any]
    kind: str = "scalar"
    children: dict[str, _WireCodec] = field(default_factory=dict)
    branches: list[tuple[dict[str, Any], _WireCodec]] = field(default_factory=list)

    def encode(self, value: Any) -> Any:
        if self.kind == "json":
            return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if self.kind == "quality":
            result = deepcopy(value)
            if result.get("rewriteBrief") is None:
                result["rewriteBrief"] = ""
            for issue in result.get("issues", []):
                if issue.get("location") is None:
                    issue["location"] = ""
            return result
        if self.kind == "optional":
            return (
                dict(_EMPTY_MARKER)
                if value is _MISSING
                else {"value": self.children["value"].encode(value)}
            )
        if self.kind in {"null", "empty_object", "missing"}:
            return dict(_EMPTY_MARKER)
        if self.kind == "wrapped":
            return {"value": self.children["value"].encode(value)}
        if self.kind == "object":
            return {
                key: child.encode(value.get(key, _MISSING)) for key, child in self.children.items()
            }
        if self.kind == "array":
            return [self.children["items"].encode(item) for item in value]
        return deepcopy(value)

    def decode(self, value: Any) -> Any:
        if self.kind == "json":
            return json.loads(
                value,
                object_pairs_hook=_unique_pairs,
                parse_constant=_reject_constant,
            )
        if self.kind == "quality":
            return _normalize_deepseek_quality_arguments(value)
        if self.kind in {"null", "empty_object", "missing"}:
            if value != _EMPTY_MARKER:
                raise ValueError("DeepSeek 空值标记不符合约定")
            return {"null": None, "empty_object": {}, "missing": _MISSING}[self.kind]
        if self.kind == "optional":
            if "value" not in value:
                return _empty_codec("missing").decode(value)
            return self.children["value"].decode(value["value"])
        if self.kind == "wrapped":
            return self.children["value"].decode(value["value"])
        if self.kind == "object":
            result = {}
            for key, child in self.children.items():
                decoded = child.decode(value[key])
                if decoded is not _MISSING:
                    result[key] = decoded
            return result
        if self.kind == "array":
            return [self.children["items"].decode(item) for item in value]
        return deepcopy(value)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DeepSeek JSON 参数包含重复字段")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("DeepSeek JSON 参数包含非有限数字")


def _wrapped(child: _WireCodec, *, optional: bool = False) -> _WireCodec:
    present = _closed_object({"value": child.schema})
    schema: dict[str, Any] = (
        {"anyOf": [_empty_codec("missing").schema, present]} if optional else present
    )
    if optional:
        schema["description"] = (
            '省略字段时返回 {"_inkforgeEmpty":"empty"}；提供字段时返回 {"value": 字段值}。'
        )
    return _WireCodec(schema, "optional" if optional else "wrapped", {"value": child})


def _empty_codec(kind: str) -> _WireCodec:
    """固定标记仅属于供应商表示层，按原类型恢复空对象、null 或字段省略。"""
    return _WireCodec(
        {
            **_closed_object({"_inkforgeEmpty": {"type": "string", "enum": ["empty"]}}),
            "description": "固定空值标记，业务层会按原类型恢复。",
        },
        kind,
    )


def _object_alternative(schema: Mapping[str, Any], branch: Mapping[str, Any]) -> dict[str, Any]:
    """把定位/复审的条件分支展开为完整对象，让 wire 继续表达合法字段组合。"""
    if set(branch) - {"properties", "required"}:
        raise ValueError("DeepSeek 工具对象联合包含尚未支持的组合约束")
    result = {key: deepcopy(value) for key, value in schema.items() if key != "anyOf"}
    result["required"] = list(
        dict.fromkeys(
            [
                *schema.get("required", []),
                *branch.get("required", []),
            ]
        )
    )
    properties = result["properties"]
    for name, constraint in branch.get("properties", {}).items():
        original = properties.get(name, {})
        alternatives = original.get("anyOf")
        if alternatives and "type" in constraint:
            matching = [item for item in alternatives if item.get("type") == constraint["type"]]
            if len(matching) != 1:
                raise ValueError("DeepSeek 工具对象分支无法确定性收窄")
            original = {
                **{key: value for key, value in original.items() if key != "anyOf"},
                **matching[0],
            }
        properties[name] = {**original, **constraint}
    return result


def _describe_local_limits(wire: dict[str, Any], schema: Mapping[str, Any]) -> None:
    """供应商不支持的长度等约束仍提示模型，并由解码后的原 Schema 强制校验。"""
    hints = {
        key: value
        for key, value in schema.items()
        if key in {"minLength", "maxLength", "minItems", "maxItems", "uniqueItems", "format"}
        and key not in wire
    }
    if hints:
        wire["description"] = f"{wire.get('description', '')} 业务约束：" + json.dumps(
            hints, ensure_ascii=False
        )


def _compile_wire(
    schema: Any,
    definitions: Mapping[str, Any],
    *,
    stack: tuple[str, ...] = (),
) -> _WireCodec:
    if not isinstance(schema, Mapping):
        if schema is True:
            schema = {}
        else:
            raise ValueError("DeepSeek 工具 Schema 不支持此布尔节点")
    if "$ref" in schema:
        reference = schema["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
            raise ValueError("DeepSeek 工具 Schema 只允许本地引用")
        name = reference.removeprefix("#/$defs/")
        if name not in definitions:
            raise ValueError("DeepSeek 工具 Schema 引用不存在")
        if name in stack:
            return _json_codec(schema)
        target = {**definitions[name], **{k: v for k, v in schema.items() if k != "$ref"}}
        return _compile_wire(target, definitions, stack=(*stack, name))

    kind = schema.get("type")
    # Operation 收窄后的 const/enum 可能省略 type，不能把章节 kind 改成 JSON 文本。
    literals = [schema["const"]] if "const" in schema else schema.get("enum", [])
    if kind is None and literals:
        literal_types = {type(value) for value in literals}
        if len(literal_types) == 1:
            inferred = {str: "string", int: "integer", float: "number", bool: "boolean"}
            kind = inferred.get(type(literals[0]))
            if kind is not None:
                schema = {**schema, "type": kind}
    if kind == "null":
        return _empty_codec("null")
    branches = schema.get("anyOf", schema.get("oneOf"))
    if (kind == "object" or "properties" in schema) and "anyOf" in schema:
        branches = [_object_alternative(schema, branch) for branch in schema["anyOf"]]
    elif kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise ValueError("DeepSeek 工具 Schema properties 必须是对象")
        # 开放字典不能被 additionalProperties=false 吞掉键；用 JSON 字符串保留全部数据。
        if schema.get("additionalProperties", True) is not False:
            return _json_codec(schema)
        if not properties:
            return _empty_codec("empty_object")
        children = {}
        required = schema.get("required", [])
        for key, value in properties.items():
            child = _compile_wire(value, definitions, stack=stack)
            children[key] = child if key in required else _wrapped(child, optional=True)
        wire = _closed_object({key: child.schema for key, child in children.items()})
        if "description" in schema:
            wire["description"] = schema["description"]
        return _WireCodec(wire, "object", children)
    if branches is not None:
        compiled: list[tuple[dict[str, Any], _WireCodec]] = []
        for branch in branches:
            child = _compile_wire(branch, definitions, stack=stack)
            # null 与业务空对象使用相同 wire 标记，必须通过独立分支标签保持类型可逆。
            tag = str(len(compiled))
            child = _WireCodec(
                _closed_object(
                    {
                        "variant": {"type": "string", "enum": [tag]},
                        "value": child.schema,
                    }
                ),
                "object",
                {"value": child},
            )
            original = {**branch, "$defs": dict(definitions)}
            compiled.append((original, child))
        return _UnionCodec({"anyOf": [child.schema for _, child in compiled]}, branches=compiled)
    if kind == "array":
        child = _compile_wire(schema.get("items", {}), definitions, stack=stack)
        wire = {"type": "array", "items": child.schema}
        if "description" in schema:
            wire["description"] = schema["description"]
        _describe_local_limits(wire, schema)
        return _WireCodec(wire, "array", {"items": child})
    if kind in {"string", "integer", "number", "boolean"}:
        wire = {
            key: deepcopy(value)
            for key, value in schema.items()
            if key
            in {
                "type",
                "description",
                "enum",
                "pattern",
                "minimum",
                "maximum",
                "exclusiveMinimum",
                "exclusiveMaximum",
                "multipleOf",
            }
        }
        if "const" in schema:
            wire["enum"] = [schema["const"]]
        if schema.get("format") in {"email", "hostname", "ipv4", "ipv6", "uuid"}:
            wire["format"] = schema["format"]
        _describe_local_limits(wire, schema)
        return _WireCodec(wire)
    return _json_codec(schema)


class _UnionCodec(_WireCodec):
    def encode(self, value: Any) -> Any:
        for index, (original, child) in enumerate(self.branches):
            if jsonschema_rs.is_valid(original, value):
                return {"variant": str(index), "value": child.children["value"].encode(value)}
        raise ValueError("DeepSeek 工具历史不符合原始联合类型")

    def decode(self, value: Any) -> Any:
        child = self.branches[int(value["variant"])][1]
        return child.children["value"].decode(value["value"])


def _json_codec(schema: Mapping[str, Any]) -> _WireCodec:
    description = schema.get("description", "")
    return _WireCodec(
        {
            "type": "string",
            "description": (
                f"{description} 此字段传输完整 JSON 编码字符串；保留全部键和值，不截断。"
            ),
        },
        "json",
    )


@dataclass
class DeepSeekToolRequest:
    request: ModelTurnRequest
    originals: dict[str, ModelTool]
    codecs: dict[str, _WireCodec]

    def decode_result(self, result: ModelTurnResult) -> ModelTurnResult:
        calls = []
        names = list(result.invalidToolCallNames)
        for call in result.toolCalls:
            codec = self.codecs.get(call.name)
            if codec is None:
                calls.append(call)
                continue
            try:
                jsonschema_rs.validate(codec.schema, call.arguments)
                arguments = codec.decode(call.arguments)
                jsonschema_rs.validate(self.originals[call.name].parameters, arguments)
            except (ValueError, TypeError, KeyError, IndexError, RecursionError):
                names.append(call.name)
                continue
            calls.append(call.model_copy(update={"arguments": arguments}))
        extra = len(names) - len(result.invalidToolCallNames)
        return result.model_copy(
            update={
                "toolCalls": calls,
                "invalidToolCallCount": result.invalidToolCallCount + extra,
                "invalidToolCallNames": names,
                "invalidToolCallCodes": [
                    *result.invalidToolCallCodes,
                    *(["provider_strict_schema_violation"] * extra),
                ],
                "invalidToolCallArgumentCharacterCounts": [
                    *result.invalidToolCallArgumentCharacterCounts,
                    *([0] * extra),
                ],
            }
        )


def prepare_deepseek_tools(request: ModelTurnRequest) -> DeepSeekToolRequest:
    """统一解析默认值并构建可逆 wire；不修改业务请求或持久历史。"""
    enabled = [tool.strict is not False for tool in request.tools]
    if any(enabled) and not all(enabled):
        raise ValueError("DeepSeek 工具请求不能混用 strict 与非 strict 函数")
    originals = {tool.name: tool for tool in request.tools}
    codecs = {}
    tools = []
    for tool in request.tools:
        if tool.strict is False:
            tools.append(tool)
            continue
        schema: dict[str, Any] = tool.parameters
        jsonschema_rs.validator_for(schema)
        if tool.name == _QUALITY_TOOL_NAME and "rewriteBrief" in schema.get("properties", {}):
            codec = _WireCodec(_project_deepseek_quality_schema(schema), "quality")
        else:
            codec = _compile_wire(schema, schema.get("$defs", {}))
            if codec.schema.get("type") != "object":
                codec = _wrapped(codec)
        codecs[tool.name] = codec
        tools.append(tool.model_copy(update={"parameters": codec.schema, "strict": True}))
    messages = []
    for message in request.messages:
        calls = []
        for call in message.tool_calls:
            history_codec = codecs.get(call.name)
            if history_codec is not None:
                jsonschema_rs.validate(originals[call.name].parameters, call.arguments)
                call = call.model_copy(update={"arguments": history_codec.encode(call.arguments)})
            calls.append(call)
        messages.append(message.model_copy(update={"tool_calls": calls}))
    return DeepSeekToolRequest(
        request.model_copy(update={"tools": tools, "messages": messages}), originals, codecs
    )


_DEEPSEEK_STRICT_SCHEMA_KEYS = (
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "const",
    "anyOf",
    "items",
    "$ref",
    "$defs",
    "description",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
)
_QUALITY_TOOL_NAME = "submit_quality_report"
_QUALITY_OPTIONAL_STRING_PATHS = {
    ("properties", "rewriteBrief"),
    ("properties", "issues", "items", "properties", "location"),
}


def _project_deepseek_quality_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """把质量报告 Schema 收敛为无引用、无 null 的 DeepSeek strict 方言。"""

    # V1 使用 Pydantic 本地定义，V2 冻结 Schema 已由共享生成器完整内联。
    # 缺失引用仍由下面的递归解析拒绝，不能把未解析引用当作空约束。
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, Mapping):
        raise ValueError("质量报告 Schema 的 $defs 必须是对象")
    inlined = _inline_quality_schema_node(schema, definitions, stack=())
    normalized, optional_paths = _replace_quality_nullable_strings(inlined, path=())
    if optional_paths != _QUALITY_OPTIONAL_STRING_PATHS:
        raise ValueError("质量报告 Schema 可选字符串路径不符合预期")
    if not isinstance(normalized, Mapping):
        raise ValueError("质量报告 Schema 根节点必须是对象")
    projected = _project_deepseek_strict_schema(normalized)
    _apply_quality_wire_descriptions(projected)
    return projected


def _inline_quality_schema_node(
    node: object,
    definitions: Mapping[str, Any],
    *,
    stack: tuple[str, ...],
) -> object:
    if isinstance(node, list):
        return [_inline_quality_schema_node(item, definitions, stack=stack) for item in node]
    if not isinstance(node, Mapping):
        return deepcopy(node)
    if "$ref" in node:
        if len(node) != 1:
            raise ValueError("质量报告 Schema 引用节点不能携带其他约束")
        reference = node["$ref"]
        prefix = "#/$defs/"
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise ValueError("质量报告 Schema 只允许本地 $defs 引用")
        name = reference.removeprefix(prefix)
        if not name or "/" in name or name not in definitions:
            raise ValueError("质量报告 Schema 引用目标不存在")
        if name in stack:
            raise ValueError("质量报告 Schema 不能包含循环引用")
        return _inline_quality_schema_node(
            definitions[name],
            definitions,
            stack=(*stack, name),
        )
    return {
        str(key): _inline_quality_schema_node(value, definitions, stack=stack)
        for key, value in node.items()
        if key != "$defs"
    }


def _replace_quality_nullable_strings(
    node: object,
    *,
    path: tuple[str, ...],
) -> tuple[object, set[tuple[str, ...]]]:
    if isinstance(node, list):
        values: list[object] = []
        found: set[tuple[str, ...]] = set()
        for index, item in enumerate(node):
            normalized, child_found = _replace_quality_nullable_strings(
                item,
                path=(*path, str(index)),
            )
            values.append(normalized)
            found.update(child_found)
        return values, found
    if not isinstance(node, Mapping):
        return deepcopy(node), set()
    string_branch = _nullable_string_branch(node)
    if string_branch is not None:
        if path not in _QUALITY_OPTIONAL_STRING_PATHS:
            raise ValueError("质量报告 Schema 出现未登记的可空字符串")
        return deepcopy(string_branch), {path}
    normalized_mapping: dict[str, object] = {}
    found = set()
    for key, value in node.items():
        if key == "properties" and isinstance(value, Mapping):
            properties: dict[str, object] = {}
            for property_name, property_schema in value.items():
                normalized, child_found = _replace_quality_nullable_strings(
                    property_schema,
                    path=(*path, "properties", str(property_name)),
                )
                properties[str(property_name)] = normalized
                found.update(child_found)
            normalized_mapping[key] = properties
        elif key == "items":
            normalized, child_found = _replace_quality_nullable_strings(
                value,
                path=(*path, "items"),
            )
            normalized_mapping[key] = normalized
            found.update(child_found)
        else:
            normalized, child_found = _replace_quality_nullable_strings(
                value,
                path=(*path, str(key)),
            )
            normalized_mapping[str(key)] = normalized
            found.update(child_found)
    return normalized_mapping, found


def _nullable_string_branch(node: Mapping[str, Any]) -> Mapping[str, Any] | None:
    branches = node.get("anyOf")
    if not isinstance(branches, list) or len(branches) != 2:
        return None
    string_branches = [
        branch
        for branch in branches
        if isinstance(branch, Mapping) and branch.get("type") == "string"
    ]
    null_branches = [
        branch
        for branch in branches
        if isinstance(branch, Mapping) and branch.get("type") == "null"
    ]
    return string_branches[0] if len(string_branches) == len(null_branches) == 1 else None


def _apply_quality_wire_descriptions(schema: dict[str, Any]) -> None:
    try:
        properties = schema["properties"]
        issues = properties["issues"]
        issue_properties = issues["items"]["properties"]
    except (KeyError, TypeError) as exc:
        raise ValueError("质量报告 Schema 结构不符合预期") from exc
    descriptions = {
        "message": "1～500 字。",
        "evidence": "1～1000 字。",
        "location": "0～200 字；无明确位置时返回空字符串。",
        "suggestion": "1～1000 字。",
    }
    for field_name, description in descriptions.items():
        target = issue_properties.get(field_name)
        if not isinstance(target, dict):
            raise ValueError("质量报告 issue Schema 结构不符合预期")
        target["description"] = description
    issues["description"] = "最多 100 项；没有问题时返回空数组。"
    report = properties.get("report")
    rewrite_brief = properties.get("rewriteBrief")
    if not isinstance(report, dict) or not isinstance(rewrite_brief, dict):
        raise ValueError("质量报告文本 Schema 结构不符合预期")
    report["description"] = "非空完整一致性终检报告。"
    rewrite_brief["description"] = "0～1000 字；无需返工时返回空字符串。"


def _normalize_deepseek_quality_arguments(
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """只归一化 quality wire 中约定的两个可选字符串。"""

    normalized = deepcopy(dict(arguments))
    if normalized.get("rewriteBrief") == "":
        normalized["rewriteBrief"] = None
    issues = normalized.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            if isinstance(issue, dict) and issue.get("location") == "":
                issue["location"] = None
    return normalized


def _project_deepseek_strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """将业务 JSON Schema 投影为 DeepSeek strict 支持的确定性子集。"""

    projected = _project_deepseek_strict_schema_node(schema)
    if not isinstance(projected, dict):
        raise ValueError("DeepSeek strict Schema 根节点必须是对象")
    return projected


def _project_deepseek_strict_schema_node(node: object) -> object:
    """递归投影 Schema 节点，同时保留 JSON Schema 布尔节点。"""

    if not isinstance(node, Mapping):
        if isinstance(node, list):
            return [_project_deepseek_strict_schema_node(item) for item in node]
        return deepcopy(node)

    projected: dict[str, Any] = {}
    for key in _DEEPSEEK_STRICT_SCHEMA_KEYS:
        if key not in node:
            continue
        value = node[key]
        if key in {"properties", "$defs"} and isinstance(value, Mapping):
            projected[key] = {
                property_name: _project_deepseek_strict_schema_node(property_schema)
                for property_name, property_schema in value.items()
            }
        elif key in {"anyOf", "items", "additionalProperties"}:
            projected[key] = _project_deepseek_strict_schema_node(value)
        else:
            projected[key] = deepcopy(value)

    if projected.get("type") == "object":
        properties = projected.get("properties")
        # 非法 properties 不被放宽为可接收额外字段，保持 strict 约束并让供应商拒绝坏 Schema。
        projected["required"] = list(properties) if isinstance(properties, Mapping) else []
        projected["additionalProperties"] = False
    return projected
