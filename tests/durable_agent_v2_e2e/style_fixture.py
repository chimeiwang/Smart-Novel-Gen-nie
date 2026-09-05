"""画像隔离验收使用原纯文本提示与完整 UTF-8 资料，不注入业务执行器。"""

from __future__ import annotations

import hashlib

from inkforge_agents.providers.base import (
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
)
from inkforge_agents.runtime.portrait_prompts import (
    PORTRAIT_SECTION_INSTRUCTIONS,
    PORTRAIT_SYSTEM_PROMPT,
)

SECTIONS = (
    "creativeMethodology",
    "uniqueMarkers",
    "generationStyle",
    "expressionFeatures",
    "styleTraits",
)
TITLES = ("创作方法论", "独特标记", "生成风格", "表达特征", "风格特质")
REFERENCES = (
    ("参考一.txt", "\ufeff甲😀\r\n乙\u0085丙\u00a0丁\u001c戊\n"),
    ("参考二.txt", "另一份\t完整资料🚀\n"),
)
SOURCE_TEXT = "\n\n".join(f"参考资料：{filename}\n\n{content}" for filename, content in REFERENCES)
ORIGINAL_CHAR_COUNT = sum(not char.isspace() for _, content in REFERENCES for char in content)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def raw_section(section: str) -> str:
    if section not in SECTIONS:
        raise ValueError("画像 E2E 未知分节")
    return (
        f" \u001c\u0085\ufeff{section}：完整画像😀\r\n内部\u00a0空白原样保留。\n尾部🚀\u00a0\t\r\n"
    )


def portrait_markdown(sections: dict[str, str]) -> str:
    return "\n\n".join(
        title + "\n" + sections[section] for title, section in zip(TITLES, SECTIONS, strict=True)
    )


def style_turn_result(request: ModelTurnRequest) -> ModelTurnResult | None:
    if request.policy.policyId != "style.portrait.v2":
        return None
    if (
        request.tools
        or request.structuredOutput is not None
        or request.requiredToolName is not None
        or request.policy.thinkingMode != "disabled"
        or request.parallelToolCalls
        or [message.role for message in request.messages] != ["system", "user"]
        or request.messages[0].content != PORTRAIT_SYSTEM_PROMPT
    ):
        raise ValueError("画像 E2E 只接受原关闭思考、无工具的纯文本消息")
    matches = [
        section
        for section in SECTIONS
        if request.messages[1].content
        == f"任务：{PORTRAIT_SECTION_INSTRUCTIONS[section]}\n\n完整参考资料：\n{SOURCE_TEXT}"
    ]
    if len(matches) != 1:
        raise ValueError("画像 E2E 单节提示或完整来源发生变化，不能采样或带入前节结果")
    content = raw_section(matches[0])
    prompt_tokens = sum(len(message.content) for message in request.messages)
    completion_tokens = len(content)
    return ModelTurnResult(
        content=content,
        toolCalls=[],
        finishReason="stop",
        rawFinishReason="stop",
        usage=ModelUsage(
            promptTokens=prompt_tokens,
            cachedTokens=0,
            completionTokens=completion_tokens,
            totalTokens=prompt_tokens + completion_tokens,
        ),
        diagnostics=ModelUsageDiagnostics(promptCacheMissTokens=prompt_tokens, reasoningTokens=0),
        effectiveMaxOutputTokens=request.maxOutputTokens,
    )
