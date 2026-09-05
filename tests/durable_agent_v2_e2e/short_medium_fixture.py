"""仅供既有隔离 E2E Provider 使用的中短篇确定性结果。"""

from __future__ import annotations

import hashlib
import json

from inkforge_agents.providers.base import ModelTurnRequest
from inkforge_contracts.short_medium_execution import (
    ShortMediumContextV2,
    ShortMediumPriorSegment,
    ShortMediumStepInput,
)
from pydantic import JsonValue

SHORT_PROFILES = {
    "plot.short_medium_outline.v2": ("generate_outline", "output_short_medium_outline_v2"),
    "writer.short_medium_manuscript.v2": ("generate_manuscript", "output_short_medium_segment_v2"),
    "writer.short_medium_selection.v2": ("replace_selection", "output_short_medium_replacement_v2"),
    "quality.short_medium_full_check.v2": ("full_check", "output_short_medium_check_report_v2"),
}
OPENING = "隔离开头😀：门已经打开。"
OUTLINE = "主角进入旧城，核对线索，选择承担代价；高潮作出不可逆决定，结尾兑现开门的承诺。\n"
REPLACEMENT = " 新的行动😀\n"
REPORT = (
    "具体位置：正文的开门场景。证据：人物已作出选择。建议：保留因果关系。\r\n" * 200
    + "完整报告尾部🚀"
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manuscript_segment(index: int, count: int, *, source_kind: str, source_text: str) -> str:
    content = f"第{index + 1}连续单元😀。\n" + "人物核对线索，作出选择并承担代价。\n" * 400
    if index == 0 and source_kind == "opening":
        content = source_text + content
    if index == count - 1 and source_kind == "ending":
        content += source_text
    return content


def short_medium_output(request: ModelTurnRequest) -> dict[str, JsonValue] | None:
    expected = SHORT_PROFILES.get(request.policy.policyId)
    if expected is None:
        return None
    if request.structuredOutput is None or request.structuredOutput.name != expected[1]:
        raise ValueError("中短篇 E2E 模型输出身份不一致")
    envelopes = [
        json.loads(message.content) for message in request.messages if message.role == "user"
    ]
    if len(envelopes) != 1 or not isinstance(envelopes[0], dict):
        raise ValueError("中短篇 E2E 缺少唯一完整执行信封")
    envelope = envelopes[0]
    if (envelope.get("workflow"), envelope.get("operation"), envelope.get("purpose")) != (
        "short_medium",
        expected[0],
        "generation",
    ):
        raise ValueError("中短篇 E2E 执行身份不一致")
    step = ShortMediumStepInput.model_validate(envelope["input"])
    items = envelope["evidenceBundle"]["items"]
    if len(items) != step.segmentIndex + 1 or items[0]["resourceType"] != "short_medium_context":
        raise ValueError("中短篇 E2E 缺少完整来源或连续前缀")
    context = ShortMediumContextV2.model_validate(items[0]["contentJson"])
    if context.operation != expected[0] or context.segment_count != step.segmentCount:
        raise ValueError("中短篇 E2E 冻结段数不一致")
    for index, item in enumerate(items[1:]):
        previous = ShortMediumPriorSegment.model_validate(item["contentJson"])
        expected_content = manuscript_segment(
            index,
            step.segmentCount,
            source_kind=context.sourceKind or "",
            source_text=context.sourceText or "",
        )
        if (
            item["resourceType"] != "short_medium_segment"
            or previous.index != index
            or previous.content != expected_content
        ):
            raise ValueError("中短篇 E2E 后续模型请求未保留完整已完成前缀")
    if context.operation == "generate_outline":
        return {"content": OUTLINE}
    if context.operation == "generate_manuscript":
        return {
            "content": manuscript_segment(
                step.segmentIndex,
                step.segmentCount,
                source_kind=context.sourceKind or "",
                source_text=context.sourceText or "",
            )
        }
    if context.operation == "replace_selection":
        return {"replacement": REPLACEMENT}
    return {"text": REPORT}
