from __future__ import annotations

from typing import Any

from inkforge_agents.definitions.agents import AGENT_DEFINITIONS
from inkforge_agents.operations.definitions import OPERATION_DEFINITIONS
from inkforge_agents.tools.registry import build_default_registry

NOVEL_READ = frozenset({"get_novel_info", "list_available_data"})
CHARACTER_READ = frozenset(
    {"list_characters_summary", "get_character_detail", "get_character_list"}
)
LORE_READ = frozenset(
    {
        "list_factions_summary",
        "get_faction_detail",
        "list_locations_summary",
        "get_location_detail",
        "list_items_summary",
        "get_item_detail",
        "list_glossaries_summary",
        "get_glossary_detail",
        "search_lore",
        "find_similar_lore",
        "semantic_search_references",
    }
)
PLOT_READ = frozenset(
    {
        "list_outline_summary",
        "get_outline_node",
        "get_plot_progress",
        "list_foreshadowings_summary",
        "get_foreshadowing_detail",
        "get_recent_chapters",
    }
)
STYLE_READ = frozenset({"get_style_profile"})
LORE_PROPOSALS = frozenset(
    {"propose_update_character", "propose_update_character_status"}
)
OUTLINE_PROPOSALS = frozenset({"propose_update_outline"})
FORESHADOW_PROPOSALS = frozenset(
    {"propose_add_foreshadowing", "propose_resolve_foreshadowing"}
)
COMMON_BUILDER_TOOLS = frozenset(
    {
        "propose_updates",
        "start_update_builder",
        "append_update_batch",
        "put_update_text_block",
        "put_update_item_text_block",
        "put_update_item_text_blocks",
        "finish_update_builder",
    }
)
OUTLINE_BUILDER_TOOLS = COMMON_BUILDER_TOOLS | {"append_outline_tree"}
BASE_READ = NOVEL_READ | CHARACTER_READ | LORE_READ | PLOT_READ
EDITOR_READ = NOVEL_READ | CHARACTER_READ | PLOT_READ | STYLE_READ


EXPECTED_CONTRACTS: dict[str, dict[str, Any]] = {
    "answer_question": {
        "allowed": EDITOR_READ,
        "terminal": frozenset(),
        "events": frozenset(),
        "text_kind": None,
        "key_policy": "none",
    },
    "create_lore": {
        "allowed": BASE_READ | LORE_PROPOSALS | COMMON_BUILDER_TOOLS,
        "terminal": frozenset({"propose_updates", "finish_update_builder"}),
        "events": frozenset({"propose_updates", "finish_update_builder"}),
        "text_kind": None,
        "key_policy": "builder_or_generated",
    },
    "revise_lore": {
        "allowed": BASE_READ | LORE_PROPOSALS | COMMON_BUILDER_TOOLS,
        "terminal": frozenset({"propose_updates", "finish_update_builder"}),
        "events": frozenset({"propose_updates", "finish_update_builder"}),
        "text_kind": None,
        "key_policy": "builder_or_generated",
    },
    "create_outline": {
        "allowed": BASE_READ | OUTLINE_PROPOSALS | OUTLINE_BUILDER_TOOLS,
        "terminal": frozenset({"propose_updates", "finish_update_builder"}),
        "events": frozenset({"propose_updates", "finish_update_builder"}),
        "text_kind": None,
        "key_policy": "builder_or_generated",
    },
    "revise_outline": {
        "allowed": BASE_READ | OUTLINE_PROPOSALS | OUTLINE_BUILDER_TOOLS,
        "terminal": frozenset({"propose_updates", "finish_update_builder"}),
        "events": frozenset({"propose_updates", "finish_update_builder"}),
        "text_kind": None,
        "key_policy": "builder_or_generated",
    },
    "plan_chapter": {
        "allowed": BASE_READ | {"submit_beat_plan"},
        "terminal": frozenset({"submit_beat_plan"}),
        "events": frozenset({"submit_beat_plan"}),
        "text_kind": "beat_plan_draft",
        "key_policy": "generated_stable",
    },
    "write_chapter": {
        "allowed": BASE_READ | STYLE_READ | {"begin_artifact_output"},
        "terminal": frozenset({"begin_artifact_output"}),
        "events": frozenset({"begin_artifact_output"}),
        "text_kind": "chapter_draft",
        "key_policy": "generated_stable",
    },
    "rewrite_scene": {
        "allowed": BASE_READ | STYLE_READ | {"begin_artifact_output"},
        "terminal": frozenset({"begin_artifact_output"}),
        "events": frozenset({"begin_artifact_output"}),
        "text_kind": "chapter_draft",
        "key_policy": "generated_stable",
    },
    "review_chapter": {
        "allowed": EDITOR_READ,
        "terminal": frozenset(),
        "events": frozenset(),
        "text_kind": None,
        "key_policy": "none",
    },
    "manage_foreshadowing": {
        "allowed": BASE_READ | FORESHADOW_PROPOSALS | OUTLINE_BUILDER_TOOLS,
        "terminal": frozenset({"propose_updates", "finish_update_builder"}),
        "events": frozenset({"propose_updates", "finish_update_builder"}),
        "text_kind": None,
        "key_policy": "builder_or_generated",
    },
}


def test_all_creative_operations_have_exact_execution_contracts() -> None:
    assert set(OPERATION_DEFINITIONS) == set(EXPECTED_CONTRACTS)
    for kind, expected in EXPECTED_CONTRACTS.items():
        definition = OPERATION_DEFINITIONS[kind]  # type: ignore[index]
        assert definition.allowedToolNames == expected["allowed"], kind
        assert definition.terminalControlTools == expected["terminal"], kind
        assert definition.artifactEventTypes == expected["events"], kind
        assert definition.textArtifactKind == expected["text_kind"], kind
        assert definition.artifactKeyPolicy == expected["key_policy"], kind


def test_every_operation_declares_valid_execution_contract() -> None:
    registry = build_default_registry()
    registered = {tool.name for tool in registry.all()}

    for definition in OPERATION_DEFINITIONS.values():
        assert definition.allowedToolNames <= registered
        assert definition.terminalControlTools <= definition.allowedToolNames
        assert definition.artifactEventTypes == definition.terminalControlTools
        if definition.requiresArtifact:
            assert definition.artifactEventTypes
            assert definition.artifactKeyPolicy != "none"
            assert definition.requiresUserApproval is True
        else:
            assert not definition.artifactEventTypes
            assert not definition.terminalControlTools
            assert definition.artifactKeyPolicy == "none"
            assert definition.textArtifactKind is None


def test_primary_agent_is_authorized_for_every_declared_operation_tool() -> None:
    registry = build_default_registry()
    for definition in OPERATION_DEFINITIONS.values():
        agent = AGENT_DEFINITIONS[definition.primaryAgent]
        tools = registry.for_execution(
            agent_id=agent.id,
            capabilities=agent.toolCapabilities,
            allowed_tool_names=definition.allowedToolNames,
        )
        assert {tool.name for tool in tools} == definition.allowedToolNames


def test_lore_operations_do_not_expose_outline_tree_builder() -> None:
    assert "append_outline_tree" not in OPERATION_DEFINITIONS["create_lore"].allowedToolNames
    assert "append_outline_tree" not in OPERATION_DEFINITIONS["revise_lore"].allowedToolNames
