from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    count: int | None = Field(default=None, ge=1, le=20)


class ArtifactListArgs(StrictArgs):
    status: Literal["draft", "under_review", "awaiting_user", "applying", "applied"] | None = None
    kind: str | None = None


class ArtifactIdArgs(StrictArgs):
    artifact_id: str = Field(min_length=1)


class ReferenceSearchArgs(StrictArgs):
    query: str = Field(min_length=1)
    topK: int | None = Field(default=None, ge=1, le=20)


READ_TOOL_ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "get_novel_info": NovelInfoArgs,
    "list_available_data": EmptyArgs,
    "list_characters_summary": EmptyArgs,
    "get_character_detail": CharacterNameArgs,
    "get_character_list": EmptyArgs,
    "list_factions_summary": EmptyArgs,
    "get_faction_detail": FactionNameArgs,
    "list_locations_summary": EmptyArgs,
    "get_location_detail": LocationNameArgs,
    "list_items_summary": EmptyArgs,
    "get_item_detail": ItemNameArgs,
    "list_glossaries_summary": EmptyArgs,
    "get_glossary_detail": TermArgs,
    "search_lore": KeywordArgs,
    "find_similar_lore": SimilarLoreArgs,
    "semantic_search_references": ReferenceSearchArgs,
    "get_style_profile": EmptyArgs,
    "list_outline_summary": OutlineSummaryArgs,
    "get_outline_node": OutlineNodeArgs,
    "get_plot_progress": EmptyArgs,
    "list_foreshadowings_summary": EmptyArgs,
    "get_foreshadowing_detail": ForeshadowingNameArgs,
    "get_recent_chapters": RecentChapterArgs,
    "list_review_artifacts": ArtifactListArgs,
    "get_review_artifact": ArtifactIdArgs,
    "get_active_review_artifact": EmptyArgs,
}

READ_TOOL_NAMES = tuple(READ_TOOL_ARGUMENT_MODELS)
