"""从已下发的 Schema 生成字段提示，不读取供应商失败参数或诊断载荷。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import jsonschema_rs

from .base import ModelTool

_NAME = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{0,63}")
_KINDS = {"string", "integer", "number", "boolean", "array", "object"}
_NO_EXAMPLE = object()


def _alternatives(schema: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    branches = schema.get("anyOf")
    if isinstance(branches, list):
        for branch in branches:
            if isinstance(branch, dict):
                yield from _alternatives(branch)
    else:
        yield schema


def _scalar_example(schema: Mapping[str, Any]) -> Any:
    """只给实际通过字段 Schema 的标量例子，不编造资源对象或正文内容。"""
    for branch in _alternatives(schema):
        kind = branch.get("type")
        if kind not in {"string", "integer", "number", "boolean"}:
            continue
        if isinstance(branch.get("enum"), list):
            candidates = branch["enum"]
        elif "const" in branch:
            candidates = [branch["const"]]
        elif kind == "boolean":
            candidates = [True, False]
        elif kind in {"integer", "number"}:
            candidates = [branch.get("minimum", 1), 0, 1, branch.get("maximum", 1)]
        else:
            candidates = ["示例"]
        for candidate in candidates:
            if isinstance(candidate, (str, int, float, bool)) and jsonschema_rs.is_valid(
                dict(schema), candidate
            ):
                return candidate
    return _NO_EXAMPLE


def _field_hint(name: str, schema: Mapping[str, Any]) -> str:
    kinds: set[str] = set()
    states: set[str] = set()
    for branch in _alternatives(schema):
        properties = branch.get("properties", {})
        state = properties.get("_inkforgeState", {}) if isinstance(properties, dict) else {}
        if isinstance(state, dict):
            states.update(value for value in state.get("enum", []) if value in {"omitted", "null"})
        kind = branch.get("type")
        if kind in _KINDS and not state:
            kinds.add(kind)
    parts = [f"字段 {name}：类型为 {'/'.join(sorted(kinds)) or '当前声明的对象结构'}"]
    example = _scalar_example(schema)
    if example is not _NO_EXAMPLE:
        parts.append("字段格式示例 " + json.dumps({name: example}, ensure_ascii=False))
    if "omitted" in states:
        parts.append('省略业务字段时填写 {"_inkforgeState":"omitted"}')
    if "null" in states:
        parts.append('显式空值时填写 {"_inkforgeState":"null"}')
    return "；".join(parts) + "。"


def build_tool_schema_hints(
    tools: Sequence[ModelTool], invalid_names: Sequence[str]
) -> list[str]:
    """仅提示已暴露的失败工具；提示不可用不得影响原来的纠正或失败流程。"""
    by_name = {tool.name: tool for tool in tools}
    hints: list[str] = []
    for name in dict.fromkeys(invalid_names):
        if name not in by_name or not _NAME.fullmatch(name) or name == "submit_quality_report":
            continue
        try:
            schema = by_name[name].parameters
            properties = schema.get("properties", {})
            if not isinstance(properties, dict):
                continue
            fields = [
                _field_hint(field, value)
                for field, value in properties.items()
                if _NAME.fullmatch(field) and isinstance(value, dict)
            ][:10]
            if fields:
                hints.append(
                    f"工具 {name} 的已声明字段提示：\n" + "\n".join(fields)
                    + "\n示例只说明字段格式，实际值按任务填写；"
                    "其他字段及组合约束仍遵守当前 Schema。"
                )
        except Exception:  # noqa: S112 - 辅助提示故障不得取代原协议错误。
            continue
        if len(hints) == 10:
            break
    return hints
