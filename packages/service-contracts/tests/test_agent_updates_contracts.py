from __future__ import annotations

import json
from copy import deepcopy

import pytest
from inkforge_contracts import (
    AgentUpdatesInput,
    AgentUpdatesOutput,
    AgentUpdatesResult,
    canonical_execution_sha256,
    materialize_agent_updates_output,
)
from pydantic import ValidationError


def complete_updates() -> dict[str, object]:
    return {
        "characters": [
            {
                "action": "create",
                "name": " 林舟 ",
                "aliases": None,
                "currentStatus": "active",
            }
        ],
        "locations": [
            {
                "action": "update",
                "locationId": "location-1",
                "description": None,
            }
        ],
        "items": [{"action": "delete", "id": "item-1"}],
        "factions": [{"action": "create", "name": "调查局", "baseId": None}],
        "glossaries": [{"action": "create", "term": "回声层", "definition": ""}],
        "characterExperiences": [
            {
                "action": "create",
                "characterName": "林舟",
                "chapterId": None,
                "content": "",
                "order": 0,
            }
        ],
        "outline": [
            {
                "nodeId": "node-1",
                "status": "in_progress",
                "actualWordCount": None,
            }
        ],
        "outlineTreeMode": "patch",
        "outlineAdjustments": [
            {
                "action": "create",
                "title": " 第一卷 ",
                "kind": "stage",
                "order": -1,
                "linkedChapterId": None,
            },
            {
                "action": "create",
                "title": "追踪",
                "kind": "plot_unit",
                "clientKey": "plot-1",
                "parentId": "node-1",
                "linkedChapterId": "chapter-2",
            },
            {
                "action": "update",
                "nodeId": "node-2",
                "content": None,
                "order": 9,
                "linkedChapterId": "chapter-9",
            },
        ],
        "foreshadowing": [
            {
                "action": "payoff",
                "id": "foreshadowing-1",
                "payoffAt": None,
            }
        ],
        "references": [
            {
                "action": "update",
                "referenceId": "reference-1",
                "content": "",
                "sourceUrl": None,
            }
        ],
        "outlineContent": "",
        "worldSetting": "  雾城\r\n",
        "storyBackground": "背景😀",
    }


def test_output_accepts_all_real_sections_and_preserves_raw_text() -> None:
    value = {"summary": " \r\n ", "updates": complete_updates()}
    output = AgentUpdatesOutput.model_validate(value)

    assert output.summary == value["summary"]
    assert output.updates.outlineContent == ""
    assert output.updates.worldSetting == "  雾城\r\n"
    assert output.updates.outlineAdjustments[0].order == -1
    assert output.updates.outlineAdjustments[1].linkedChapterId == "chapter-2"
    assert output.updates.references[0].sourceUrl is None

    schema = AgentUpdatesOutput.model_json_schema()
    assert schema["properties"]["summary"]["maxLength"] == 1000
    updates_schema = schema["$defs"]["AgentUpdates"]
    assert "maxItems" not in updates_schema["properties"]["characters"]
    assert "maxLength" not in updates_schema["properties"]["worldSetting"]
    assert "discriminator" not in json.dumps(schema)


@pytest.mark.parametrize(
    "field",
    [
        "characters",
        "locations",
        "items",
        "factions",
        "glossaries",
        "characterExperiences",
        "outline",
        "outlineAdjustments",
        "foreshadowing",
        "references",
        "outlineContent",
        "worldSetting",
        "storyBackground",
    ],
)
def test_top_level_sections_reject_null(field: str) -> None:
    updates: dict[str, object] = {"outlineContent": "正文"}
    if field == "outlineContent":
        updates = {"worldSetting": "正文"}
    updates[field] = None
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate({"summary": "说明", "updates": updates})


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {"characters": []},
        {"outlineTreeMode": "patch"},
        {"outlineTreeMode": "replace", "outlineAdjustments": []},
    ],
)
def test_updates_require_a_nonempty_array_or_provided_full_text(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate({"summary": "说明", "updates": updates})

    assert (
        AgentUpdatesOutput.model_validate(
            {"summary": "说明", "updates": {"outlineContent": ""}}
        ).updates.outlineContent
        == ""
    )


def test_missing_null_and_empty_are_distinct_in_hash_material() -> None:
    missing = materialize_agent_updates_output(
        {
            "summary": "说明",
            "updates": {"characters": [{"action": "update", "id": "c-1", "age": "18"}]},
        }
    )
    explicit_null = materialize_agent_updates_output(
        {
            "summary": "说明",
            "updates": {
                "characters": [{"action": "update", "id": "c-1", "age": "18", "aliases": None}]
            },
        }
    )
    explicit_empty = materialize_agent_updates_output(
        {
            "summary": "说明",
            "updates": {
                "characters": [{"action": "update", "id": "c-1", "age": "18"}],
                "locations": [],
            },
        }
    )

    assert "aliases" not in missing["updates"]["characters"][0]
    assert explicit_null["updates"]["characters"][0]["aliases"] is None
    assert "locations" not in missing["updates"]
    assert explicit_empty["updates"]["locations"] == []
    assert (
        len(
            {
                missing["updatesSha256"],
                explicit_null["updatesSha256"],
                explicit_empty["updatesSha256"],
            }
        )
        == 3
    )


def test_default_model_dump_never_fills_missing_fields_or_drops_explicit_null() -> None:
    value = {
        "summary": "说明",
        "updates": {
            "characters": [{"action": "update", "id": "c-1", "aliases": None}],
            "worldSetting": "",
        },
    }
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value


def test_result_hash_covers_only_presence_preserving_updates() -> None:
    result = materialize_agent_updates_output(
        {
            "summary": " 原始说明 ",
            "updates": {"worldSetting": "", "characters": []},
        }
    )
    assert result["updatesSha256"] == canonical_execution_sha256(result["updates"])
    assert AgentUpdatesResult.model_validate(result).summary == " 原始说明 "

    for changed in (
        {"updatesSha256": "f" * 64},
        {"updatesSha256": True},
        {"clientRequestId": "provider-forged"},
    ):
        with pytest.raises(ValidationError):
            AgentUpdatesResult.model_validate(result | changed)


@pytest.mark.parametrize(
    "summary",
    ["", "😀" * 1001, None, 1],
)
def test_summary_is_raw_length_bounded_but_strict(summary: object) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate({"summary": summary, "updates": {"storyBackground": ""}})

    assert (
        AgentUpdatesOutput.model_validate(
            {"summary": " " * 1000, "updates": {"storyBackground": ""}}
        ).summary
        == " " * 1000
    )


@pytest.mark.parametrize(
    "item",
    [
        {"name": "无 action"},
        {"action": "create", "name": "林舟", "clientRequestId": "伪造"},
        {"action": "update", "id": "c-1", "name": "林舟", "expectedUpdatedAt": "伪造"},
        {"action": "delete", "id": "c-1", "fieldChanges": []},
        {"action": "move", "id": "c-1"},
    ],
)
def test_character_action_union_rejects_unknown_or_core_derived_fields(
    item: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate({"summary": "说明", "updates": {"characters": [item]}})


@pytest.mark.parametrize(
    ("section", "item"),
    [
        ("characters", {"action": "update", "id": "c-1"}),
        ("characters", {"action": "delete"}),
        ("locations", {"action": "update", "id": "location-1"}),
        ("items", {"action": "delete", "itemId": ""}),
        ("glossaries", {"action": "create", "term": "术语"}),
        ("glossaries", {"action": "update", "glossaryId": "g-1"}),
    ],
)
def test_lore_entity_actions_require_real_targets_and_business_fields(
    section: str,
    item: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate({"summary": "说明", "updates": {section: [item]}})


def test_lore_nullable_fields_remain_presence_aware() -> None:
    output = AgentUpdatesOutput.model_validate(
        {
            "summary": "说明",
            "updates": {
                "characters": [
                    {
                        "action": "update",
                        "characterId": "c-1",
                        "aliases": None,
                        "factionId": None,
                    }
                ],
                "glossaries": [{"action": "update", "term": "旧术语", "category": None}],
            },
        }
    )
    dumped = output.model_dump(mode="json", exclude_unset=True)
    assert dumped["updates"]["characters"][0]["aliases"] is None
    assert dumped["updates"]["characters"][0]["factionId"] is None
    assert dumped["updates"]["glossaries"][0]["category"] is None


@pytest.mark.parametrize(
    ("section", "typed_id", "field"),
    [
        ("characters", "characterId", "aliases"),
        ("locations", "locationId", "description"),
        ("items", "itemId", "description"),
        ("factions", "factionId", "description"),
        ("glossaries", "glossaryId", "definition"),
    ],
)
@pytest.mark.parametrize("action", ["update", "delete"])
@pytest.mark.parametrize("primary_id", ["主要目标", ""])
def test_lore_keeps_both_ids_for_existing_core_first_id_resolution(
    section: str, typed_id: str, field: str, action: str, primary_id: str
) -> None:
    item = {"action": action, "id": primary_id, typed_id: "次要目标"}
    if action == "update":
        item[field] = "新内容"
    value = {"summary": "说明", "updates": {section: [item]}}
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value


@pytest.mark.parametrize("name", ["\u0085", "\u00a0", "\u2007", "\u202f", "\ufeff"])
def test_name_accepts_java_non_whitespace_without_normalization(name: str) -> None:
    value = {
        "summary": "说明",
        "updates": {
            "references": [{"action": "create", "title": name, "type": "note", "content": ""}],
            "outlineAdjustments": [{"action": "create", "title": name, "kind": "stage"}],
        },
    }
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value


@pytest.mark.parametrize(
    "name",
    list(
        "\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u1680"
        "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2008\u2009\u200a"
        "\u2028\u2029\u205f\u3000"
    ),
)
def test_name_rejects_each_java_whitespace_character(name: str) -> None:
    for section, item in (
        ("references", {"action": "create", "title": name, "type": "note", "content": ""}),
        ("outlineAdjustments", {"action": "create", "title": name, "kind": "stage"}),
    ):
        with pytest.raises(ValidationError, match="不能为空白文本"):
            AgentUpdatesOutput.model_validate({"summary": "说明", "updates": {section: [item]}})


@pytest.mark.parametrize("name", ["", " \r\n", "\u00a0"])
def test_actual_agent_writer_text_rules_do_not_inherit_public_form_validation(name: str) -> None:
    updates: dict[str, object] = {
        section: [
            {"action": "create", "name": name},
            {"action": "update", "id": "existing", "name": name},
        ]
        for section in ("characters", "locations", "items", "factions")
    }
    updates["glossaries"] = [
        {"action": "create", "term": name, "definition": ""},
        {"action": "update", "id": "existing", "term": name},
    ]
    updates["foreshadowing"] = [{"action": "update", "id": "existing", "name": name}]
    updates["references"] = [{"action": "update", "id": "existing", "title": name}]
    if name:
        updates["foreshadowing"].append({"action": "create", "name": name})
    value = {"summary": "说明", "updates": updates}
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value


def test_unique_name_can_be_both_update_locator_and_business_field() -> None:
    output = AgentUpdatesOutput.model_validate(
        {
            "summary": "说明",
            "updates": {"locations": [{"action": "update", "name": " 旧地名 "}]},
        }
    )
    assert output.updates.locations[0].name == " 旧地名 "


@pytest.mark.parametrize(
    ("section", "item"),
    [
        ("characters", {"action": "delete", "name": "林舟"}),
        ("locations", {"action": "create", "name": "雾城", "parentId": None}),
        ("items", {"action": "update", "itemId": "i-1", "ownerId": None}),
        ("factions", {"action": "delete", "factionId": "f-1"}),
        (
            "glossaries",
            {"action": "update", "glossaryId": "g-1", "definition": ""},
        ),
        (
            "characterExperiences",
            {"action": "update", "id": "e-1", "content": ""},
        ),
        ("characterExperiences", {"action": "delete", "id": "e-1"}),
        (
            "outlineAdjustments",
            {"action": "delete", "nodeTitle": "旧节点"},
        ),
        (
            "foreshadowing",
            {"action": "create", "name": "钟声", "expectedPayoff": None},
        ),
        (
            "foreshadowing",
            {"action": "update", "id": "foreshadowing-1", "plantedAt": None},
        ),
        ("foreshadowing", {"action": "abandon", "name": "钟声"}),
        (
            "references",
            {
                "action": "create",
                "title": " 资料 ",
                "type": "web",
                "content": "",
                "sourceUrl": "",
            },
        ),
        ("references", {"action": "delete", "referenceId": "r-1"}),
    ],
)
def test_supported_action_branches_accept_real_business_shapes(
    section: str,
    item: dict[str, object],
) -> None:
    output = AgentUpdatesOutput.model_validate({"summary": "说明", "updates": {section: [item]}})
    assert output.model_dump(mode="json")["updates"][section] == [item]


@pytest.mark.parametrize(
    "item",
    [
        {"action": "create", "content": "经历"},
        {"action": "update", "id": "experience-1"},
        {"action": "update", "id": "experience-1", "order": None},
        {"action": "update", "id": "experience-1", "order": True},
        {"action": "delete", "id": ""},
        {"action": "delete", "id": "experience-1", "chapterTitle": "伪字段"},
    ],
)
def test_character_experience_action_shapes_are_strict(item: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate(
            {"summary": "说明", "updates": {"characterExperiences": [item]}}
        )


@pytest.mark.parametrize(
    "item",
    [
        {"nodeId": "node-1", "status": "done"},
        {"nodeId": "node-1", "status": "planned", "actualWordCount": True},
        {"nodeId": "", "status": "planned"},
        {"nodeId": "node-1"},
        {"nodeId": "node-1", "status": "planned", "chapterTitle": "伪字段"},
    ],
)
def test_outline_status_update_has_exact_fields(item: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate({"summary": "说明", "updates": {"outline": [item]}})


def test_outline_status_update_accepts_word_count_without_status() -> None:
    output = AgentUpdatesOutput.model_validate(
        {
            "summary": "说明",
            "updates": {"outline": [{"nodeId": "node-1", "actualWordCount": 10}]},
        }
    )
    assert output.model_dump(mode="json")["updates"]["outline"] == [
        {"nodeId": "node-1", "actualWordCount": 10}
    ]


@pytest.mark.parametrize(
    ("section", "base", "field", "minimum"),
    [
        (
            "characterExperiences",
            {"action": "create", "characterId": "c-1", "content": ""},
            "order",
            -(2**31),
        ),
        ("characterExperiences", {"action": "update", "id": "e-1"}, "order", -(2**31)),
        ("outline", {"nodeId": "node-1"}, "actualWordCount", -(2**31)),
        *[
            ("outlineAdjustments", base, field, minimum)
            for base in (
                {"action": "create", "title": "阶段", "kind": "stage"},
                {"action": "update", "nodeId": "node-1"},
            )
            for field, minimum in (
                ("order", -(2**31)),
                ("estimatedWordCount", -(2**31)),
                ("actualWordCount", -(2**31)),
                ("chapterStartOrder", 1),
                ("chapterEndOrder", 1),
            )
        ],
    ],
)
def test_integer_fields_preserve_storage_range_without_coercion_or_fallback(
    section: str, base: dict[str, object], field: str, minimum: int
) -> None:
    def candidate(number: object) -> dict[str, object]:
        item = base | {field: number}
        if base.get("action") == "create" and field in {"chapterStartOrder", "chapterEndOrder"}:
            item |= {"chapterStartOrder": number, "chapterEndOrder": number}
        return {"summary": "说明", "updates": {section: [item]}}

    for number in (minimum, 2**31 - 1):
        value = candidate(number)
        assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value
    for number in (-(2**31) - 1, 2**31, True, 1.0, "1"):
        with pytest.raises(ValidationError) as failure:
            AgentUpdatesOutput.model_validate(candidate(number))
        assert any(
            error["loc"][-1] == field
            and error["type"] in {"int_type", "less_than_equal", "greater_than_equal"}
            for error in failure.value.errors()
        )
    if minimum == 1:
        with pytest.raises(ValidationError, match="正整数"):
            AgentUpdatesOutput.model_validate(candidate(0))


@pytest.mark.parametrize(
    "item",
    [
        {"action": "create", "title": "节点"},
        {"action": "create", "title": "节点", "kind": "plot_unit"},
        {
            "action": "create",
            "title": "阶段",
            "kind": "stage",
            "parentId": "parent-1",
        },
        {"action": "update", "nodeId": "node-1"},
        {"action": "update", "nodeId": "node-1", "order": True},
        {"action": "delete", "nodeId": "node-1", "content": "伪业务字段"},
        {
            "action": "create",
            "title": "节点",
            "kind": "stage",
            "chapterStartOrder": 2,
        },
        {
            "action": "create",
            "title": "节点",
            "kind": "stage",
            "chapterStartOrder": 3,
            "chapterEndOrder": 2,
        },
    ],
)
def test_outline_adjustment_action_shapes_match_domain_rules(
    item: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate(
            {"summary": "说明", "updates": {"outlineAdjustments": [item]}}
        )


def test_outline_update_may_change_one_range_endpoint_against_frozen_current_node() -> None:
    output = AgentUpdatesOutput.model_validate(
        {
            "summary": "说明",
            "updates": {
                "outlineAdjustments": [
                    {
                        "action": "update",
                        "nodeId": "node-1",
                        "chapterEndOrder": 12,
                    }
                ]
            },
        }
    )
    assert output.updates.outlineAdjustments[0].chapterEndOrder == 12


def test_outline_create_preserves_single_explicit_null_range_endpoint() -> None:
    value = {
        "summary": "说明",
        "updates": {
            "outlineAdjustments": [
                {
                    "action": "create",
                    "title": "阶段",
                    "kind": "stage",
                    "chapterStartOrder": None,
                }
            ]
        },
    }
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value


def test_outline_update_may_reparent_to_an_earlier_created_client_key() -> None:
    output = AgentUpdatesOutput.model_validate(
        {
            "summary": "说明",
            "updates": {
                "outlineAdjustments": [
                    {
                        "action": "create",
                        "title": "新阶段",
                        "kind": "stage",
                        "clientKey": "stage-new",
                    },
                    {
                        "action": "update",
                        "nodeId": "node-1",
                        "parentKey": "stage-new",
                    },
                ]
            },
        }
    )
    assert output.updates.outlineAdjustments[1].parentKey == "stage-new"


@pytest.mark.parametrize("mode", ["patch", "replace"])
@pytest.mark.parametrize("parent_id", ["old-stage", "", None])
def test_outline_parent_key_overrides_provided_parent_id(mode: str, parent_id: str | None) -> None:
    value = {
        "summary": "说明",
        "updates": {
            "outlineTreeMode": mode,
            "outlineAdjustments": [
                {"action": "create", "title": "卷一", "kind": "stage", "clientKey": "stage-1"},
                {
                    "action": "create",
                    "title": "主线",
                    "kind": "plot_unit",
                    "parentId": parent_id,
                    "parentKey": "stage-1",
                },
            ],
        },
    }
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value

    if mode == "patch":
        value["updates"]["outlineAdjustments"][1] = {
            "action": "update",
            "nodeId": "node-1",
            "parentId": parent_id,
            "parentKey": "stage-1",
        }
        assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value


def test_outline_patch_accepts_last_client_key_mapping_and_replace_rejects_it() -> None:
    value = {
        "summary": "说明",
        "updates": {
            "outlineTreeMode": "patch",
            "outlineAdjustments": [
                {"action": "create", "title": "卷一", "kind": "stage", "clientKey": "parent"},
                {
                    "action": "create",
                    "title": "主线",
                    "kind": "plot_unit",
                    "parentKey": "parent",
                    "clientKey": "parent",
                },
                {
                    "action": "create",
                    "title": "章节组",
                    "kind": "chapter_group",
                    "parentKey": "parent",
                },
            ],
        },
    }
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value
    value["updates"]["outlineTreeMode"] = "replace"
    with pytest.raises(ValidationError, match="clientKey 不能重复"):
        AgentUpdatesOutput.model_validate(value)


def test_outline_patch_defers_mutated_parent_kind_to_core_sequential_validation() -> None:
    value = {
        "summary": "说明",
        "updates": {
            "outlineAdjustments": [
                {"action": "create", "title": "根", "kind": "stage", "clientKey": "root"},
                {"action": "create", "title": "主线", "kind": "stage", "clientKey": "parent"},
                {"action": "update", "nodeTitle": "主线", "kind": "plot_unit", "parentKey": "root"},
                {
                    "action": "create",
                    "title": "章节组",
                    "kind": "chapter_group",
                    "parentKey": "parent",
                },
            ]
        },
    }
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value


@pytest.mark.parametrize("mode", ["patch", "replace"])
def test_outline_empty_temporary_keys_do_not_create_a_mapping(mode: str) -> None:
    value = {
        "summary": "说明",
        "updates": {
            "outlineTreeMode": mode,
            "outlineAdjustments": [
                {
                    "action": "create",
                    "title": title,
                    "kind": "stage",
                    "clientKey": "",
                    "parentKey": "",
                }
                for title in ("卷一", "卷二")
            ],
        },
    }
    assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value


@pytest.mark.parametrize(
    ("locator", "valid"),
    [
        ({"nodeId": "existing", "title": "", "nodeTitle": ""}, True),
        ({"nodeId": "", "nodeTitle": "已有标题"}, True),
        ({"title": "", "nodeTitle": "已有标题"}, False),
        ({"title": "已有标题", "nodeTitle": ""}, True),
    ],
)
def test_outline_delete_follows_core_id_then_title_then_missing_title_alias(
    locator: dict[str, str], valid: bool
) -> None:
    value = {
        "summary": "说明",
        "updates": {"outlineAdjustments": [{"action": "delete", **locator}]},
    }
    if valid:
        assert AgentUpdatesOutput.model_validate(value).model_dump(mode="json") == value
    else:
        with pytest.raises(ValidationError, match="缺少可解析目标"):
            AgentUpdatesOutput.model_validate(value)


@pytest.mark.parametrize("mode", ["patch", "replace"])
def test_outline_parent_key_must_already_exist_even_with_parent_id(mode: str) -> None:
    with pytest.raises(ValidationError, match="parentKey 必须引用更早的 create"):
        AgentUpdatesOutput.model_validate(
            {
                "summary": "说明",
                "updates": {
                    "outlineTreeMode": mode,
                    "outlineAdjustments": [
                        {
                            "action": "create",
                            "title": "主线",
                            "kind": "plot_unit",
                            "parentId": "existing-stage",
                            "parentKey": "missing-key",
                        }
                    ],
                },
            }
        )


def test_outline_replace_allows_only_create_and_keeps_patch_wire_literal() -> None:
    valid = {
        "summary": "说明",
        "updates": {
            "outlineTreeMode": "replace",
            "outlineAdjustments": [
                {
                    "action": "create",
                    "title": "卷一",
                    "kind": "stage",
                    "clientKey": "stage-1",
                },
                {
                    "action": "create",
                    "title": "主线",
                    "kind": "plot_unit",
                    "parentKey": "stage-1",
                },
            ],
        },
    }
    assert AgentUpdatesOutput.model_validate(valid).updates.outlineTreeMode == "replace"

    invalid = deepcopy(valid)
    invalid["updates"]["outlineAdjustments"] = [
        {"action": "update", "nodeId": "node-1", "title": "新标题"}
    ]
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate(invalid)

    invalid_mode = deepcopy(valid)
    invalid_mode["updates"]["outlineTreeMode"] = "merge"
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate(invalid_mode)

    stale_parent = deepcopy(valid)
    stale_parent["updates"]["outlineAdjustments"][1] = {
        "action": "create",
        "title": "主线",
        "kind": "plot_unit",
        "parentId": "old-stage",
    }
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate(stale_parent)


@pytest.mark.parametrize(
    "item",
    [
        {"action": "create", "name": ""},
        {"action": "update", "id": "f-1"},
        {"action": "payoff"},
        {"action": "abandon", "id": "f-1", "payoffNote": "伪字段"},
        {"action": "delete", "id": "f-1"},
    ],
)
def test_foreshadowing_actions_are_strict(item: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate({"summary": "说明", "updates": {"foreshadowing": [item]}})


@pytest.mark.parametrize(
    "item",
    [
        {"action": "create", "title": "资料", "type": "web"},
        {"action": "create", "title": " \n", "type": "web", "content": ""},
        {"action": "update", "referenceId": "r-1"},
        {"action": "update", "referenceId": "r-1", "content": None},
        {"action": "update", "id": "r-1", "referenceId": "r-2", "content": ""},
        {"action": "delete", "referenceId": "r-1", "sourceUrl": None},
        {"action": "delete", "referenceId": "r-1", "fieldChanges": []},
    ],
)
def test_reference_actions_keep_source_url_but_reject_derived_fields(
    item: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesOutput.model_validate({"summary": "说明", "updates": {"references": [item]}})


def test_revision_input_requires_exact_original_and_previous_candidate_pair() -> None:
    initial = {"userInstruction": "  更新设定\r\n"}
    previous = {
        "artifactId": "artifact-1",
        "artifactRevision": 2,
        "summary": "旧候选说明",
        "updates": {"outlineContent": ""},
    }
    assert AgentUpdatesInput.model_validate(initial).userInstruction == initial["userInstruction"]
    revised = AgentUpdatesInput.model_validate(
        initial
        | {
            "originalUserInstruction": " 最初要求 ",
            "previousCandidate": previous,
        }
    )
    assert revised.previousCandidate is not None
    assert revised.previousCandidate.artifactRevision == 2

    for changed in (
        {"originalUserInstruction": "原要求"},
        {"previousCandidate": previous},
        {"originalUserInstruction": None, "previousCandidate": None},
        {
            "originalUserInstruction": "原要求",
            "previousCandidate": previous | {"updatesSha256": "a" * 64},
        },
        {"workspace": {}},
        {
            "originalUserInstruction": "原要求",
            "previousCandidate": previous | {"artifactRevision": True},
        },
        {
            "originalUserInstruction": "原要求",
            "previousCandidate": previous | {"artifactRevision": 0},
        },
    ):
        with pytest.raises(ValidationError):
            AgentUpdatesInput.model_validate(initial | changed)


@pytest.mark.parametrize("value", ["", " \n\ufeff\u0085", None, 1])
def test_instruction_is_complete_nonblank_text_without_coercion(value: object) -> None:
    with pytest.raises(ValidationError):
        AgentUpdatesInput.model_validate({"userInstruction": value})

    long_value = "甲" * 100_000
    assert (
        AgentUpdatesInput.model_validate({"userInstruction": long_value}).userInstruction
        == long_value
    )


def test_top_level_and_required_business_fields_are_closed_and_non_nullable() -> None:
    invalid_updates = (
        {"outlineContent": "正文", "storyProgress": "伪字段"},
        {"outlineTreeMode": None, "outlineContent": "正文"},
        {"characters": [{"action": "update", "id": "c-1", "name": None}]},
        {"characters": [{"action": "update", "id": "c-1", "currentStatus": None}]},
        {"glossaries": [{"action": "update", "id": "g-1", "term": None}]},
        {"glossaries": [{"action": "update", "id": "g-1", "definition": None}]},
        {"characters": [{"action": "update", "id": "c-1", "factionId": ""}]},
        {
            "outlineAdjustments": [
                {
                    "action": "update",
                    "nodeId": "node-1",
                    "linkedChapterId": "",
                }
            ]
        },
    )
    for updates in invalid_updates:
        with pytest.raises(ValidationError):
            AgentUpdatesOutput.model_validate({"summary": "说明", "updates": updates})
