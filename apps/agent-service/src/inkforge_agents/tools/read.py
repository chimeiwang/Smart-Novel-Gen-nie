from __future__ import annotations

from inkforge_contracts.read_tools import (
    ArtifactIdArgs,
    ArtifactListArgs,
    CharacterNameArgs,
    EmptyArgs,
    FactionNameArgs,
    ForeshadowingNameArgs,
    ItemNameArgs,
    KeywordArgs,
    LocationNameArgs,
    NovelInfoArgs,
    OutlineNodeArgs,
    OutlineSummaryArgs,
    RecentChapterArgs,
    ReferenceSearchArgs,
    SimilarLoreArgs,
    TermArgs,
)
from pydantic import BaseModel

from .permissions import read_only_permission
from .registry import ToolDefinition, ToolGateway


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
