from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..prompts import (
    AUTHOR_SYSTEM_PROMPT,
    EDITOR_SYSTEM_PROMPT,
    LORE_SYSTEM_PROMPT,
    PLOT_SYSTEM_PROMPT,
    VALIDATOR_SYSTEM_PROMPT,
)
from .capabilities import AGENT_CAPABILITIES

AgentId = Literal["设定", "剧情", "写作", "校验", "编辑"]
OutputMode = Literal["paragraph_text_with_control_tools"]


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    id: AgentId
    name: str
    description: str
    systemPrompt: str
    toolCapabilities: frozenset[str]
    outputMode: OutputMode = "paragraph_text_with_control_tools"
    maxIterations: int = 10
    terminalControlTools: frozenset[str] = frozenset()


AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    "设定": AgentDefinition(
        id="设定",
        name="设定顾问",
        description="讨论、评价、创建和维护小说设定。",
        systemPrompt=LORE_SYSTEM_PROMPT,
        toolCapabilities=AGENT_CAPABILITIES["设定"],
    ),
    "剧情": AgentDefinition(
        id="剧情",
        name="剧情顾问",
        description="规划主线、章节职责、伏笔和节奏结构。",
        systemPrompt=PLOT_SYSTEM_PROMPT,
        toolCapabilities=AGENT_CAPABILITIES["剧情"],
    ),
    "写作": AgentDefinition(
        id="写作",
        name="作家",
        description="根据作品上下文创作小说正文。",
        systemPrompt=AUTHOR_SYSTEM_PROMPT,
        toolCapabilities=AGENT_CAPABILITIES["写作"],
    ),
    "校验": AgentDefinition(
        id="校验",
        name="校验员",
        description="审计一致性、逻辑和设定冲突。",
        systemPrompt=VALIDATOR_SYSTEM_PROMPT,
        toolCapabilities=AGENT_CAPABILITIES["校验"],
        terminalControlTools=frozenset({"submit_evaluation"}),
    ),
    "编辑": AgentDefinition(
        id="编辑",
        name="网文编辑",
        description="评估商业性、读者留存和章节追读。",
        systemPrompt=EDITOR_SYSTEM_PROMPT,
        toolCapabilities=AGENT_CAPABILITIES["编辑"],
        maxIterations=12,
        terminalControlTools=frozenset({"submit_evaluation"}),
    ),
}
