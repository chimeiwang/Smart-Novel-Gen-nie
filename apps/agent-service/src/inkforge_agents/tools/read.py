from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .permissions import read_only_permission
from .registry import ToolDefinition, ToolGateway


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArgs(StrictArgs):
    pass


class NovelInfoArgs(StrictArgs):
    include_full_sections: bool | None = None


class CharacterNameArgs(StrictArgs):
    character_name: str = Field(min_length=1)


class FactionNameArgs(StrictArgs):
    faction_name: str = Field(min_length=1)


class LocationNameArgs(StrictArgs):
    location_name: str = Field(min_length=1)


class ItemNameArgs(StrictArgs):
    item_name: str = Field(min_length=1)


class TermArgs(StrictArgs):
    term: str = Field(min_length=1)


class KeywordArgs(StrictArgs):
    keyword: str = Field(min_length=1)


class SimilarLoreArgs(KeywordArgs):
    threshold: float | None = Field(default=None, ge=0, le=1)


class OutlineSummaryArgs(StrictArgs):
    scope: Literal["current_chapter", "tree_index"] | None = None
    include_full_summary: bool | None = None


class OutlineNodeArgs(StrictArgs):
    node_id: str | None = Field(default=None, min_length=1)
    node_title: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_locator(self) -> Self:
        if not self.node_id and not self.node_title:
            raise ValueError("node_id 或 node_title 至少提供一个")
        return self


class ForeshadowingNameArgs(StrictArgs):
    foreshadowing_name: str = Field(min_length=1)


class RecentChapterArgs(StrictArgs):
    count: int | None = Field(default=None, ge=1, le=5)


class ArtifactListArgs(StrictArgs):
    status: Literal["draft", "under_review", "awaiting_user", "applying", "applied"] | None = None
    kind: str | None = None


class ArtifactIdArgs(StrictArgs):
    artifact_id: str = Field(min_length=1)


class ReferenceSearchArgs(StrictArgs):
    query: str = Field(min_length=1)
    topK: int | None = Field(default=None, ge=1, le=20)


def read_tools(gateway: ToolGateway) -> list[ToolDefinition]:
    async def execute(
        name: str,
        arguments: dict[str, object],
        context: object,
    ) -> dict[str, object]:
        from .registry import ToolContext

        if not isinstance(context, ToolContext):
            raise TypeError("工具上下文无效")
        return await gateway.execute(name, context, arguments)

    specs: list[tuple[str, str, type[BaseModel], str]] = [
        ("get_novel_info", "读取作品圣经和小说概要。", NovelInfoArgs, "novel.read"),
        ("list_available_data", "列出当前小说可读取的数据类型。", EmptyArgs, "novel.read"),
        ("list_characters_summary", "列出角色摘要。", EmptyArgs, "character.read"),
        ("get_character_detail", "按名称读取角色完整信息。", CharacterNameArgs, "character.read"),
        ("get_character_list", "读取角色列表。", EmptyArgs, "character.read"),
        ("list_factions_summary", "列出势力摘要。", EmptyArgs, "lore.read"),
        ("get_faction_detail", "按名称读取势力详情。", FactionNameArgs, "lore.read"),
        ("list_locations_summary", "列出地点摘要。", EmptyArgs, "lore.read"),
        ("get_location_detail", "按名称读取地点详情。", LocationNameArgs, "lore.read"),
        ("list_items_summary", "列出物品摘要。", EmptyArgs, "lore.read"),
        ("get_item_detail", "按名称读取物品详情。", ItemNameArgs, "lore.read"),
        ("list_glossaries_summary", "列出术语摘要。", EmptyArgs, "lore.read"),
        ("get_glossary_detail", "按名称读取术语详情。", TermArgs, "lore.read"),
        ("search_lore", "按关键词搜索设定。", KeywordArgs, "lore.read"),
        ("find_similar_lore", "查找语义相近的设定。", SimilarLoreArgs, "lore.read"),
        ("semantic_search_references", "语义检索参考资料。", ReferenceSearchArgs, "lore.read"),
        ("get_style_profile", "读取已应用的文风画像。", EmptyArgs, "style.read"),
        ("list_outline_summary", "读取结构化大纲索引。", OutlineSummaryArgs, "plot.read"),
        ("get_outline_node", "读取指定大纲节点。", OutlineNodeArgs, "plot.read"),
        ("get_plot_progress", "读取当前剧情进度。", EmptyArgs, "plot.read"),
        ("list_foreshadowings_summary", "列出伏笔摘要。", EmptyArgs, "plot.read"),
        ("get_foreshadowing_detail", "读取指定伏笔详情。", ForeshadowingNameArgs, "plot.read"),
        ("get_recent_chapters", "读取最近章节正文。", RecentChapterArgs, "plot.read"),
        ("list_review_artifacts", "列出当前任务的待审核草案。", ArtifactListArgs, "artifact.read"),
        ("get_review_artifact", "读取指定待审核草案。", ArtifactIdArgs, "artifact.read"),
        ("get_active_review_artifact", "读取当前活跃待审核草案。", EmptyArgs, "artifact.read"),
    ]
    tools: list[ToolDefinition] = []
    for name, description, model, capability in specs:

        async def handler(
            arguments: dict[str, object],
            context: object,
            *,
            tool_name: str = name,
        ) -> dict[str, object]:
            return await execute(tool_name, arguments, context)

        tools.append(
            ToolDefinition(
                name=name,
                description=description,
                argumentsModel=model,
                permission=read_only_permission(capability),
                toolKind="read",
                handler=handler,
            )
        )
    return tools
