from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import jsonschema_rs

from .base import ModelTool, ModelTurnRequest, ModelTurnResult
from .error_details import capture_failure_diagnostic
from .tool_schema_hints import build_tool_schema_hints

_MISSING = object()
_EMPTY_MARKER = {"_inkforgeEmpty": "empty"}


def normalize_deepseek_anyof(schema: dict[str, Any]) -> dict[str, Any]:
    """展开纯联合的嵌套分支；带类型或条件约束的联合仍保留完整交集。"""
    result = deepcopy(schema)
    for key in ("properties", "$defs", "definitions", "patternProperties"):
        children = result.get(key)
        if isinstance(children, dict):
            result[key] = {
                name: normalize_deepseek_anyof(child) if isinstance(child, dict) else child
                for name, child in children.items()
            }
    for key in ("items", "additionalProperties", "not", "if", "then", "else"):
        child = result.get(key)
        if isinstance(child, dict):
            result[key] = normalize_deepseek_anyof(child)
    for key in ("anyOf", "allOf", "oneOf", "prefixItems"):
        children = result.get(key)
        if isinstance(children, list):
            result[key] = [
                normalize_deepseek_anyof(child) if isinstance(child, dict) else child
                for child in children
            ]
    branches = result.get("anyOf")
    if isinstance(branches, list):
        flattened = []
        for branch in branches:
            if (
                isinstance(branch, dict)
                and set(branch) <= {"anyOf", "description"}
                and isinstance(branch.get("anyOf"), list)
            ):
                for child in branch["anyOf"]:
                    child = deepcopy(child)
                    if isinstance(child, dict) and branch.get("description"):
                        descriptions = [branch["description"], child.get("description")]
                        child["description"] = "\n".join(
                            dict.fromkeys(text for text in descriptions if text)
                        )
                    flattened.append(child)
            else:
                flattened.append(branch)
        result["anyOf"] = flattened
    return result


def validate_deepseek_wire_dialect(schema: dict[str, Any]) -> None:
    """供应商要求 anyOf 的直接分支有具体类型；普通联合容器无需伪造类型。"""
    def visit(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            return
        branches = node.get("anyOf")
        if isinstance(branches, list):
            for index, branch in enumerate(branches):
                if (
                    not isinstance(branch, dict)
                    or not isinstance(branch.get("type"), str)
                    or branch["type"]
                    not in {"object", "string", "number", "integer", "boolean", "array"}
                ):
                    raise ValueError(f"DeepSeek anyOf 直接分支缺少具体 type：{path}/anyOf/{index}")
        for key in ("properties", "$defs", "definitions", "patternProperties"):
            children = node.get(key)
            if isinstance(children, dict):
                for name, child in children.items():
                    visit(child, f"{path}/{key}/{name}")
        for key in ("items", "additionalProperties", "not", "if", "then", "else"):
            visit(node.get(key), f"{path}/{key}")
        for key in ("anyOf", "allOf", "oneOf", "prefixItems"):
            children = node.get(key)
            if isinstance(children, list):
                for index, child in enumerate(children):
                    visit(child, f"{path}/{key}/{index}")

    visit(schema, "$")


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
            return _marker("missing") if value is _MISSING else self.children["value"].encode(value)
        if self.kind == "optional_tagged":
            return (
                {"variant": "omitted"}
                if value is _MISSING
                else {"variant": "value", "value": self.children["value"].encode(value)}
            )
        if self.kind in {"null", "empty_object", "missing"}:
            return _marker(self.kind)
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
            if value != _marker(self.kind):
                raise ValueError("DeepSeek 空值标记不符合约定")
            return {"null": None, "empty_object": {}, "missing": _MISSING}[self.kind]
        if self.kind == "optional":
            return _MISSING if value == _marker("missing") else self.children["value"].decode(value)
        if self.kind == "optional_tagged":
            return (
                _MISSING
                if value["variant"] == "omitted"
                else self.children["value"].decode(value["value"])
            )
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


def _marker(kind: str) -> dict[str, str]:
    return (
        dict(_EMPTY_MARKER)
        if kind == "empty_object"
        else {"_inkforgeState": "omitted" if kind == "missing" else "null"}
    )


def _wrapped(child: _WireCodec, *, optional: bool = False) -> _WireCodec:
    if not optional:
        return _describe_codec(
            _WireCodec(_closed_object({"value": child.schema}), "wrapped", {"value": child})
        )
    omitted = _empty_codec("missing").schema
    if not jsonschema_rs.is_valid(child.schema, _marker("missing")):
        return _describe_codec(
            _WireCodec({"anyOf": [child.schema, omitted]}, "optional", {"value": child})
        )
    # 真实业务值可能与省略标记同形，必须保留能表达存在性的最小判别。
    schema = {
        "anyOf": [
            _closed_object({"variant": {"type": "string", "enum": ["omitted"]}}),
            _closed_object(
                {"variant": {"type": "string", "enum": ["value"]}, "value": child.schema}
            ),
        ]
    }
    return _describe_codec(_WireCodec(schema, "optional_tagged", {"value": child}))


def _empty_codec(kind: str) -> _WireCodec:
    marker = _marker(kind)
    key, value = next(iter(marker.items()))
    return _describe_codec(
        _WireCodec(_closed_object({key: {"type": "string", "enum": [value]}}), kind)
    )


def _schema_example(schema: Mapping[str, Any]) -> Any:
    for branch in schema.get("anyOf", []):
        example = _schema_example(branch)
        if example is not _MISSING and jsonschema_rs.is_valid(dict(schema), example):
            return example
    if "enum" in schema:
        for value in schema["enum"]:
            if jsonschema_rs.is_valid(dict(schema), value):
                return deepcopy(value)
        return _MISSING
    kind = schema.get("type")
    if kind == "object":
        result = {
            key: _schema_example(child) for key, child in schema.get("properties", {}).items()
        }
        if any(value is _MISSING for value in result.values()):
            return _MISSING
        return result if jsonschema_rs.is_valid(dict(schema), result) else _MISSING
    if kind == "array":
        return []
    candidates: dict[str, list[Any]] = {
        "string": ["示例", "example", "a", "", "00000000-0000-0000-0000-000000000000"],
        "boolean": [False, True],
        "integer": [schema.get("minimum", 0), schema.get("maximum", 1), 1, 0],
        "number": [schema.get("minimum", 0), schema.get("maximum", 1), 1, 0],
    }
    for value in candidates.get(str(kind), []):
        if jsonschema_rs.is_valid(dict(schema), value):
            return value
    return _MISSING


def _describe_codec(codec: _WireCodec, original: str = "") -> _WireCodec:
    explanation = {
        "optional": (
            '正常值直接填写。省略字段用 {"_inkforgeState":"omitted"}，'
            "不能用零、false或空串代替省略。"
        ),
        "optional_tagged": (
            '业务值可能与省略标记同形；省略用 {"variant":"omitted"}，'
            '提供值用 {"variant":"value","value":业务值}。'
        ),
        "null": "此标记表示显式 null，区别于字段省略。",
        "missing": "此标记表示字段省略，保留既有缺省语义。",
        "empty_object": "此非空传输标记表示业务空对象 {}，不是 null 或字段省略。",
        "union_flat": "直接填写匹配业务分支的值，不添加 value 或数字 variant。",
        "union_tagged": "分支传输形状重叠且解码不等价，必须使用声明的 variant 和 value。",
        "wrapped": "函数参数根必须是对象，使用声明的 value 字段携带完整值。",
    }.get(codec.kind, "")
    example = _codec_example(codec)
    if example is not _MISSING and not jsonschema_rs.is_valid(codec.schema, example):
        example = _MISSING
    descriptions = [original, codec.schema.get("description", ""), explanation]
    if codec.kind in {"optional", "optional_tagged"}:
        descriptions.insert(0, codec.children["value"].schema.get("description", ""))
    if codec.kind == "union_tagged":
        descriptions.append(
            "分支说明："
            + "；".join(
                f'variant="{index}" 对应{child.kind}分支，value必须满足该分支Schema'
                for index, (_, child) in enumerate(codec.branches)
            )
        )
    if example is not _MISSING and explanation:
        descriptions.append(
            "合法形状示例：" + json.dumps(example, ensure_ascii=False, separators=(",", ":"))
        )
    codec.schema["description"] = " ".join(dict.fromkeys(item for item in descriptions if item))
    return codec


def _codec_example(codec: _WireCodec) -> Any:
    """从编解码职责生成形状示例，不能把普通字符串当作动态 JSON 的合法值。"""
    if codec.kind == "json":
        return "{}"
    if codec.kind in {"empty_object", "null", "missing"}:
        return _marker(codec.kind)
    if codec.kind in {"optional", "optional_tagged", "wrapped"}:
        value = _codec_example(codec.children["value"])
        if value is _MISSING:
            return _MISSING
        if codec.kind == "optional":
            return value
        return {"value": value} if codec.kind == "wrapped" else {"variant": "value", "value": value}
    if codec.kind == "object":
        result = {key: _codec_example(child) for key, child in codec.children.items()}
        return _MISSING if any(value is _MISSING for value in result.values()) else result
    if codec.kind == "array":
        return []
    if codec.kind in {"union_flat", "union_tagged"}:
        for index, (original, child) in enumerate(codec.branches):
            example = _codec_example(child)
            if example is not _MISSING and jsonschema_rs.is_valid(original, child.decode(example)):
                return (
                    example
                    if codec.kind == "union_flat"
                    else {"variant": str(index), "value": example}
                )
        return _MISSING
    return _schema_example(codec.schema)


def _schemas_disjoint(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if "anyOf" in left:
        return all(_schemas_disjoint(branch, right) for branch in left["anyOf"])
    if "anyOf" in right:
        return all(_schemas_disjoint(left, branch) for branch in right["anyOf"])
    ltype, rtype = left.get("type"), right.get("type")
    if ltype and rtype and ltype != rtype and {ltype, rtype} != {"integer", "number"}:
        return True
    if "enum" in left and "enum" in right:
        if not any(
            jsonschema_rs.is_valid({"enum": [a]}, b) for a in left["enum"] for b in right["enum"]
        ):
            return True
    if ltype == rtype == "object":
        lp, rp = left.get("properties", {}), right.get("properties", {})
        if left.get("additionalProperties") is False and right.get("additionalProperties") is False:
            if set(left.get("required", [])) == set(lp) and set(right.get("required", [])) == set(
                rp
            ):
                if set(lp) != set(rp):
                    return True
                return any(_schemas_disjoint(lp[key], rp[key]) for key in lp)
    return False


def _decoders_compatible(left: _WireCodec, right: _WireCodec) -> bool:
    """证明交集上的解码相同；不能证明时保守保留判别，不依赖抽样。"""
    if _schemas_disjoint(left.schema, right.schema):
        return True
    if left.kind == "union_flat":
        return all(_decoders_compatible(child, right) for _, child in left.branches)
    if right.kind == "union_flat":
        return all(_decoders_compatible(left, child) for _, child in right.branches)
    if left.kind == right.kind == "optional":
        return _decoders_compatible(left.children["value"], right.children["value"])
    if left.kind == "optional":
        return not jsonschema_rs.is_valid(
            right.schema, _marker("missing")
        ) and _decoders_compatible(left.children["value"], right)
    if right.kind == "optional":
        return _decoders_compatible(right, left)
    if left.kind != right.kind:
        return False
    if left.kind in {"scalar", "json", "null", "missing", "empty_object"}:
        return True
    if left.kind == "object":
        return set(left.children) == set(right.children) and all(
            _decoders_compatible(left.children[key], right.children[key]) for key in left.children
        )
    if left.kind == "array":
        return _decoders_compatible(left.children["items"], right.children["items"])
    if left.kind in {"optional_tagged", "wrapped"}:
        return _decoders_compatible(left.children["value"], right.children["value"])
    return False


def _union_schema(children: list[_WireCodec]) -> dict[str, Any]:
    branches = [child.schema for child in children]
    if all(branch.get("type") == "object" for branch in branches):
        properties = [branch.get("properties", {}) for branch in branches]
        if (
            properties
            and properties[0]
            and all(set(item) == set(properties[0]) for item in properties)
        ):
            combined = {}
            for name in properties[0]:
                alternatives = list(
                    {
                        json.dumps(item[name], sort_keys=True, ensure_ascii=False): item[name]
                        for item in properties
                    }.values()
                )
                combined[name] = (
                    alternatives[0] if len(alternatives) == 1 else {"anyOf": alternatives}
                )
            # 外壳满足 strict 根对象要求；分支仍保留完整条件，不能只使用属性并集。
            return {
                **_closed_object(combined),
                "anyOf": [_without_descriptions(branch) for branch in branches],
            }
    return {"anyOf": branches}


def _without_descriptions(schema: dict[str, Any]) -> dict[str, Any]:
    """外壳已经提供字段说明，条件分支只保留约束，避免重复发送整段说明和示例。"""
    result: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "description":
            continue
        if key == "properties":
            result[key] = {name: _without_descriptions(child) for name, child in value.items()}
        elif key == "anyOf":
            result[key] = [_without_descriptions(child) for child in value]
        elif key == "items" and isinstance(value, dict):
            result[key] = _without_descriptions(value)
        else:
            result[key] = deepcopy(value)
    return result


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
        if "const" in schema or "enum" in schema:
            values = [schema["const"]] if "const" in schema else schema["enum"]
            narrowed = []
            for branch in branches:
                allowed = [
                    value
                    for value in values
                    if jsonschema_rs.is_valid({**branch, "$defs": dict(definitions)}, value)
                ]
                if allowed:
                    # 条件可能挂在 nullable anyOf 父节点，必须收窄每个子分支后再编译。
                    narrowed.append({**branch, "enum": allowed})
            if not narrowed:
                raise ValueError("DeepSeek 工具联合的 const/enum 条件没有合法分支")
            branches = narrowed
        compiled = [
            (
                {**branch, "$defs": dict(definitions)},
                _compile_wire(branch, definitions, stack=stack),
            )
            for branch in branches
        ]
        if len(compiled) == 1:
            return _describe_codec(compiled[0][1], schema.get("description", ""))
        compatible = all(
            _decoders_compatible(a[1], b[1])
            for index, a in enumerate(compiled)
            for b in compiled[index + 1 :]
        )
        if compatible:
            wire = _union_schema([child for _, child in compiled])
            return _describe_codec(
                _UnionCodec(wire, "union_flat", branches=compiled), schema.get("description", "")
            )
        tagged = [
            _WireCodec(
                _closed_object(
                    {"variant": {"type": "string", "enum": [str(index)]}, "value": child.schema}
                )
            )
            for index, (_, child) in enumerate(compiled)
        ]
        wire = _union_schema(tagged)
        return _describe_codec(
            _UnionCodec(wire, "union_tagged", branches=compiled), schema.get("description", "")
        )
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
                encoded = child.encode(value)
                return (
                    encoded
                    if self.kind == "union_flat"
                    else {"variant": str(index), "value": encoded}
                )
        raise ValueError("DeepSeek 工具历史不符合原始联合类型")

    def decode(self, value: Any) -> Any:
        if self.kind == "union_tagged":
            return self.branches[int(value["variant"])][1].decode(value["value"])
        results = []
        for original, child in self.branches:
            if jsonschema_rs.is_valid(child.schema, value):
                decoded = child.decode(value)
                if jsonschema_rs.is_valid(original, decoded):
                    results.append(decoded)
        if not results:
            raise ValueError("DeepSeek 工具联合参数没有合法业务分支")
        if not all(_same_decoded(results[0], result) for result in results[1:]):
            raise ValueError("DeepSeek 工具联合参数解码存在歧义")
        return results[0]


def _same_decoded(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same_decoded(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_decoded(a, b) for a, b in zip(left, right, strict=True)
        )
    return bool(left == right)


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
    secrets: tuple[str, ...] = ()

    def decode_result(self, result: ModelTurnResult) -> ModelTurnResult:
        calls = []
        names = list(result.invalidToolCallNames)
        diagnostics = list(result.failureDiagnostics)
        for call in result.toolCalls:
            codec = self.codecs.get(call.name)
            if codec is None:
                calls.append(call)
                continue
            stage = "tool.wire_schema"
            schema = codec.schema
            value = call.arguments
            try:
                jsonschema_rs.validate(codec.schema, call.arguments)
                stage = "tool.codec_decode"
                arguments = codec.decode(call.arguments)
                stage = "tool.business_schema"
                schema = self.originals[call.name].parameters
                value = arguments
                jsonschema_rs.validate(self.originals[call.name].parameters, arguments)
            except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
                names.append(call.name)
                diagnostics.append(
                    capture_failure_diagnostic(
                        stage=stage,
                        code="provider_strict_schema_violation",
                        error=exc,
                        payload={
                            "toolName": call.name,
                            "callId": call.id,
                            "arguments": call.arguments,
                            "decodedArguments": value,
                            "wireSchema": codec.schema,
                            "businessSchema": self.originals[call.name].parameters,
                            "validationErrors": schema_validation_errors(schema, value),
                        },
                        secrets=self.secrets,
                    )
                )
                continue
            calls.append(call.model_copy(update={"arguments": arguments}))
        extra = len(names) - len(result.invalidToolCallNames)
        return result.model_copy(
            update={
                "toolCalls": calls,
                "failureDiagnostics": diagnostics,
                "toolSchemaHints": build_tool_schema_hints(self.request.tools, names),
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


def prepare_deepseek_tools(
    request: ModelTurnRequest,
    *,
    secrets: tuple[str, ...] = (),
) -> DeepSeekToolRequest:
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
        codec: _WireCodec | None = None
        try:
            jsonschema_rs.validator_for(schema)
            if tool.name == _QUALITY_TOOL_NAME and "rewriteBrief" in schema.get("properties", {}):
                codec = _WireCodec(_project_deepseek_quality_schema(schema), "quality")
            else:
                codec = _compile_wire(schema, schema.get("$defs", {}))
                if codec.schema.get("type") != "object":
                    codec = _wrapped(codec)
                codec.schema = normalize_deepseek_anyof(codec.schema)
            validate_deepseek_wire_dialect(codec.schema)
        except Exception as exc:
            exc.failureDiagnostics = [  # type: ignore[attr-defined]
                capture_failure_diagnostic(
                    stage="tool.schema_prepare",
                    code="schema_prepare_failed",
                    error=exc,
                    payload={
                        "toolName": tool.name,
                        "businessSchema": schema,
                        **({"wireSchema": codec.schema} if codec is not None else {}),
                    },
                    secrets=secrets,
                )
            ]
            raise
        codecs[tool.name] = codec
        tools.append(tool.model_copy(update={"parameters": codec.schema, "strict": True}))
    messages = []
    for message in request.messages:
        calls = []
        for call in message.tool_calls:
            history_codec = codecs.get(call.name)
            if history_codec is not None:
                stage = "tool.history_business_schema"
                try:
                    jsonschema_rs.validate(originals[call.name].parameters, call.arguments)
                    stage = "tool.history_encode"
                    call = call.model_copy(
                        update={"arguments": history_codec.encode(call.arguments)}
                    )
                except Exception as exc:
                    exc.failureDiagnostics = [  # type: ignore[attr-defined]
                        capture_failure_diagnostic(
                            stage=stage,
                            code="history_encode_failed",
                            error=exc,
                            payload={
                                "toolName": call.name,
                                "callId": call.id,
                                "arguments": call.arguments,
                                "wireSchema": history_codec.schema,
                                "businessSchema": originals[call.name].parameters,
                                "validationErrors": schema_validation_errors(
                                    originals[call.name].parameters, call.arguments
                                ),
                            },
                            secrets=secrets,
                        )
                    ]
                    raise
            calls.append(call)
        messages.append(message.model_copy(update={"tool_calls": calls}))
    return DeepSeekToolRequest(
        request.model_copy(update={"tools": tools, "messages": messages}),
        originals,
        codecs,
        secrets,
    )


def schema_validation_errors(schema: dict[str, Any], value: Any) -> list[dict[str, Any]]:
    """仅失败后枚举全部校验发现，不改变已有第一处异常及业务拒绝行为。"""
    try:
        return [
            {
                "message": error.message,
                "verboseMessage": error.verbose_message,
                "instancePath": list(error.instance_path),
                "schemaPath": list(error.schema_path),
                "kind": str(error.kind),
            }
            for error in jsonschema_rs.validator_for(schema).iter_errors(value)
        ]
    except Exception as exc:
        return [{"captureFailure": type(exc).__name__}]


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
