from __future__ import annotations

import json

from inkforge_agents.providers.base import ModelTool, ModelTurnResult, ModelUsage
from inkforge_agents.providers.tool_schema_hints import build_tool_schema_hints


def _tool() -> ModelTool:
    return ModelTool(
        name="get_recent_chapters",
        description="描述不会被复制进纠正提示",
        parameters={
            "type": "object",
            "properties": {
                "count": {"anyOf": [
                    {"type": "integer", "minimum": 1, "maximum": 20},
                    {
                        "type": "object",
                        "properties": {"_inkforgeState": {
                            "type": "string", "enum": ["omitted", "null"],
                        }},
                        "required": ["_inkforgeState"], "additionalProperties": False,
                    },
                ]},
            },
            "required": ["count"], "additionalProperties": False,
        },
    )


def test字段提示只来自已暴露Schema且例子满足实际范围() -> None:
    hints = build_tool_schema_hints([_tool()], ["unknown", "get_recent_chapters"] * 2)
    assert len(hints) == 1
    assert '字段 count：类型为 integer' in hints[0]
    assert '{"count": 1}' in hints[0]
    assert '{"_inkforgeState":"omitted"}' in hints[0]
    assert '{"_inkforgeState":"null"}' in hints[0]
    assert "描述不会被复制" not in hints[0]
    assert "unknown" not in hints[0]


def test不能满足模式的例子不冒充合法而质量专用映射不增加提示() -> None:
    tool = _tool().model_copy(update={"parameters": {
        "type": "object", "properties": {
            "hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
    }})
    hints = build_tool_schema_hints([tool], [tool.name])
    assert "字段 hash：类型为 string" in hints[0]
    assert "字段格式示例" not in hints[0]
    quality = tool.model_copy(update={"name": "submit_quality_report"})
    assert build_tool_schema_hints([quality], [quality.name]) == []


def test提示不进入普通结果序列化或repr() -> None:
    hints = build_tool_schema_hints([_tool()], ["get_recent_chapters"])
    result = ModelTurnResult(
        content="", toolCalls=[], toolSchemaHints=hints,
        usage=ModelUsage(promptTokens=1, completionTokens=1, totalTokens=2),
        finishReason="tool_calls",
    )
    assert result.toolSchemaHints == hints
    assert "toolSchemaHints" not in result.model_dump()
    assert "字段提示" not in json.dumps(result.model_dump(), ensure_ascii=False)
    assert "字段提示" not in repr(result)
