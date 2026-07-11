# ruff: noqa: E501

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .permissions import proposal_permission
from .registry import ToolContext, ToolDefinition


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CharacterProposalArgs(StrictArgs):
    character_name: str = Field(min_length=1)


class CharacterStatusProposalArgs(CharacterProposalArgs):
    status: Literal["active", "missing", "dead", "imprisoned", "unknown"]


class OutlineProposalArgs(StrictArgs):
    node_title: str = Field(min_length=1)
    action: Literal["create", "update"] | None = None
    client_key: str | None = None
    parent_key: str | None = None
    kind: Literal["stage", "plot_unit", "chapter_group"] | None = None
    status: Literal["planned", "in_progress", "completed", "skipped"] | None = None
    content_summary: str | None = Field(default=None, max_length=1000)
    estimated_word_count: float | None = None


class AddForeshadowingArgs(StrictArgs):
    name: str = Field(min_length=1)
    planted_content_summary: str | None = Field(default=None, max_length=1000)
    expected_payoff_summary: str | None = Field(default=None, max_length=1000)


class ResolveForeshadowingArgs(StrictArgs):
    foreshadowing_name: str = Field(min_length=1)
    payoff_note_summary: str | None = Field(default=None, max_length=1000)


async def _proposal_result(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    return {
        "type": "PROPOSAL_TEMPLATE",
        "arguments": arguments,
        "instruction": "请基于模板调用 propose_updates；长文本必须使用更新构建器。",
    }


def proposal_tools() -> list[ToolDefinition]:
    specs: list[tuple[str, str, type[BaseModel], str]] = [
        (
            "propose_update_character",
            "生成角色修改提案模板。",
            CharacterProposalArgs,
            "proposal.lore",
        ),
        (
            "propose_update_character_status",
            "生成角色状态修改提案模板。",
            CharacterStatusProposalArgs,
            "proposal.lore",
        ),
        (
            "propose_update_outline",
            "生成大纲节点短修改提案模板。",
            OutlineProposalArgs,
            "proposal.plot",
        ),
        (
            "propose_add_foreshadowing",
            "生成新增伏笔提案模板。",
            AddForeshadowingArgs,
            "proposal.plot",
        ),
        (
            "propose_resolve_foreshadowing",
            "生成伏笔回收提案模板。",
            ResolveForeshadowingArgs,
            "proposal.plot",
        ),
    ]
    return [
        ToolDefinition(
            name=name,
            description=description,
            argumentsModel=model,
            permission=proposal_permission(capability),
            toolKind="proposal",
            handler=_proposal_result,
        )
        for name, description, model, capability in specs
    ]
