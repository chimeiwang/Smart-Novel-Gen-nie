from datetime import UTC, datetime

import pytest
from inkforge_core.lore.repository import EntityMutation
from inkforge_core.references.repository import ReferenceMutation
from inkforge_core.reviews.updates import AgentUpdatesExecutor


class FakeLore:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def list_entities(self, novel_id: str, user_id: str, kind: str):
        del novel_id, user_id
        if kind == "characters":
            return [{"id": "character-1", "name": "甲"}]
        return []

    async def apply_entity_mutations(
        self, novel_id: str, user_id: str, mutations: list[EntityMutation]
    ):
        self.calls.append(("entity_batch", novel_id, user_id, mutations))
        return []

    async def apply_experience_mutations(self, novel_id, user_id, mutations):
        self.calls.append(("experience_batch", novel_id, user_id, mutations))
        return []

    async def upsert_content(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        content: str,
        expected_updated_at: datetime | None,
    ):
        self.calls.append(
            ("content", novel_id, user_id, kind, content, expected_updated_at)
        )


class FakeOutlines:
    def __init__(self) -> None:
        self.replaced: list[dict] | None = None
        self.outline_write: tuple[str, str, str, datetime | None] | None = None

    async def replace_nodes(self, novel_id: str, user_id: str, adjustments: list[dict]):
        del novel_id, user_id
        self.replaced = adjustments

    async def upsert_outline(
        self,
        novel_id: str,
        user_id: str,
        content: str,
        expected_updated_at: datetime | None = None,
    ):
        self.outline_write = (
            novel_id,
            user_id,
            content,
            expected_updated_at,
        )


class FakeReferences:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def apply_reference_mutations(
        self, novel_id, user_id, mutations, *, index_enabled=False
    ):
        self.calls.append(("reference_batch", novel_id, user_id, mutations))
        assert index_enabled is False
        return []


@pytest.mark.asyncio
async def test_references_use_one_batch_and_keep_controls_out_of_business_fields() -> None:
    references = FakeReferences()
    executor = AgentUpdatesExecutor(FakeLore(), FakeOutlines(), references)

    count = await executor.apply(
        "novel-1",
        "user-1",
        {
            "references": [
                {
                    "action": "create",
                    "clientRequestId": "artifact-reference-create",
                    "title": "新资料",
                    "type": "book",
                    "content": "完整正文",
                    "sourceUrl": None,
                    "fieldChanges": [{"field": "content"}],
                },
                {
                    "action": "update",
                    "id": "reference-1",
                    "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                    "title": "新标题",
                },
                {
                    "action": "delete",
                    "referenceId": "reference-2",
                    "expectedUpdatedAt": "2026-08-06T00:00:01Z",
                },
            ]
        },
    )

    assert count == 3
    assert len(references.calls) == 1
    call = references.calls[0]
    assert call[:3] == ("reference_batch", "novel-1", "user-1")
    mutations = call[3]
    assert all(isinstance(mutation, ReferenceMutation) for mutation in mutations)
    assert [mutation.action for mutation in mutations] == ["create", "update", "delete"]
    assert mutations[0].client_request_id == "artifact-reference-create"
    assert mutations[0].fields == {
        "title": "新资料",
        "type": "book",
        "content": "完整正文",
        "sourceUrl": None,
    }
    assert mutations[1].reference_id == "reference-1"
    assert mutations[1].expected_updated_at == datetime(2026, 8, 6, tzinfo=UTC)
    assert mutations[1].fields == {"title": "新标题"}
    assert mutations[2].reference_id == "reference-2"
    assert mutations[2].expected_updated_at == datetime(
        2026, 8, 6, 0, 0, 1, tzinfo=UTC
    )
    assert mutations[2].fields == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item", "message"),
    [
        (
            {"action": "create", "title": "资料", "type": "note", "content": "正文"},
            "clientRequestId",
        ),
        (
            {
                "action": "create",
                "clientRequestId": "artifact-reference-create",
                "title": "资料",
                "type": "note",
                "content": "正文",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            },
            "无法持久化字段",
        ),
        (
            {"action": "update", "id": "reference-1", "title": "新标题"},
            "expectedUpdatedAt",
        ),
        (
            {
                "action": "update",
                "id": "reference-1",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                "clientRequestId": "artifact-reference-create",
                "title": "新标题",
            },
            "无法持久化字段",
        ),
        (
            {
                "action": "delete",
                "id": "reference-1",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                "content": "不能附带业务字段",
            },
            "无法持久化字段",
        ),
        (
            {
                "action": "delete",
                "id": "reference-1",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                "characterId": "character-1",
            },
            "无法持久化字段",
        ),
    ],
)
async def test_reference_actions_use_exact_dto_whitelists(
    item: dict[str, object], message: str
) -> None:
    references = FakeReferences()
    executor = AgentUpdatesExecutor(FakeLore(), FakeOutlines(), references)

    with pytest.raises(ValueError, match=message):
        await executor.apply("novel-1", "user-1", {"references": [item]})

    assert references.calls == []


@pytest.mark.asyncio
async def test_executor_sanitizes_controls_and_defers_name_resolution_to_batch() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    count = await executor.apply(
        "novel-1",
        "user-1",
        {
            "characters": [
                {
                    "action": "update",
                    "name": "甲",
                    "personality": "谨慎",
                    "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                    "fieldChanges": [{"field": "personality"}],
                }
            ],
            "worldSetting": "完整世界设定",
        },
    )

    assert count == 2
    assert lore.calls == [
        (
            "entity_batch",
            "novel-1",
            "user-1",
            [
                EntityMutation(
                    action="update",
                    kind="characters",
                    fields={"name": "甲", "personality": "谨慎"},
                    expected_updated_at=datetime(2026, 8, 6, tzinfo=UTC),
                    lookup_field="name",
                    lookup_value="甲",
                    error_label="characters",
                )
            ],
        ),
        (
            "content",
            "novel-1",
            "user-1",
            "world-setting",
            "完整世界设定",
            None,
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item", "message"),
    [
        ({"action": "create", "name": "甲"}, "clientRequestId"),
        (
            {"action": "create", "clientRequestId": "too-short", "name": "甲"},
            "clientRequestId",
        ),
        ({"action": "update", "id": "character-1", "name": "甲"}, "expectedUpdatedAt"),
        (
            {
                "action": "update",
                "id": "character-1",
                "name": "甲",
                "expectedUpdatedAt": "not-a-time",
            },
            "expectedUpdatedAt",
        ),
        ({"action": "delete", "id": "character-1"}, "expectedUpdatedAt"),
    ],
)
async def test_entity_updates_require_safe_operation_controls(item: dict, message: str) -> None:
    executor = AgentUpdatesExecutor(FakeLore(), FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match=message):
        await executor.apply("novel-1", "user-1", {"characters": [item]})


@pytest.mark.asyncio
async def test_entity_create_and_delete_forward_controls_separately() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    count = await executor.apply(
        "novel-1",
        "user-1",
        {
            "items": [
                {
                    "action": "create",
                    "clientRequestId": "artifact-create-1",
                    "name": "信物",
                },
                {
                    "action": "delete",
                    "id": "item-1",
                    "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                },
            ]
        },
    )

    assert count == 2
    assert lore.calls == [
        (
            "entity_batch",
            "novel-1",
            "user-1",
            [
                EntityMutation(
                    action="create",
                    kind="items",
                    fields={"name": "信物"},
                    client_request_id="artifact-create-1",
                    error_label="items",
                ),
                EntityMutation(
                    action="delete",
                    kind="items",
                    fields={},
                    entity_id="item-1",
                    expected_updated_at=datetime(2026, 8, 6, tzinfo=UTC),
                    error_label="items",
                ),
            ],
        ),
    ]


@pytest.mark.asyncio
async def test_all_entity_controls_are_validated_before_any_write() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="expectedUpdatedAt"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [
                    {
                        "action": "create",
                        "clientRequestId": "artifact-create-1",
                        "name": "信物",
                    },
                    {"action": "update", "id": "item-1", "name": "新信物"},
                ]
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
async def test_all_experience_controls_are_validated_before_any_write() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="expectedUpdatedAt"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "artifact-experience-create",
                        "content": "新增经历",
                    },
                    {
                        "action": "update",
                        "id": "experience-1",
                        "content": "陈旧更新",
                    },
                ]
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
async def test_experience_controls_are_checked_before_other_section_writes() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="expectedUpdatedAt"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [
                    {
                        "action": "create",
                        "clientRequestId": "artifact-item-create",
                        "name": "信物",
                    }
                ],
                "characterExperiences": [
                    {
                        "action": "update",
                        "id": "experience-1",
                        "content": "缺少版本",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        {
            "action": "create",
            "characterId": "character-1",
            "clientRequestId": "valid-experience-create",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            "content": "不应写入",
        },
        {
            "action": "update",
            "id": "experience-1",
            "clientRequestId": "valid-experience-update",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            "content": "不应写入",
        },
        {
            "action": "delete",
            "id": "experience-1",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            "fieldChanges": [{"field": "content"}],
        },
    ],
)
async def test_experience_rejects_control_from_another_action_before_any_batch(
    item: dict[str, object],
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="无法持久化字段"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [
                    {
                        "action": "create",
                        "clientRequestId": "valid-item-create",
                        "name": "不应写入",
                    }
                ],
                "characterExperiences": [item],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "foreign_control",
    [
        "locationId",
        "itemId",
        "factionId",
        "glossaryId",
        "referenceId",
        "nodeId",
        "nodeTitle",
        "chapterTitle",
    ],
)
async def test_experience_create_rejects_cross_section_control_before_any_batch(
    foreign_control: str,
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="无法持久化字段"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [
                    {
                        "action": "create",
                        "clientRequestId": "valid-item-create",
                        "name": "不应写入",
                    }
                ],
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                        foreign_control: "foreign-1",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("business_field", "value"),
    [
        ("content", "不应写入"),
        ("order", 1),
        ("chapterId", "chapter-1"),
    ],
)
async def test_experience_delete_rejects_business_field_before_any_batch(
    business_field: str, value: object
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="无法持久化字段"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [
                    {
                        "action": "create",
                        "clientRequestId": "valid-item-create",
                        "name": "不应写入",
                    }
                ],
                "characterExperiences": [
                    {
                        "action": "delete",
                        "id": "experience-1",
                        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                        business_field: value,
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        {
            "action": "create",
            "characterId": "",
            "characterName": "合法名称",
            "clientRequestId": "valid-experience-create",
            "content": "不应写入",
        },
        {
            "action": "create",
            "characterId": "character-1",
            "characterName": "",
            "clientRequestId": "valid-experience-create",
            "content": "不应写入",
        },
        {
            "action": "update",
            "id": "",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            "content": "不应写入",
        },
        {
            "action": "delete",
            "id": "",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
        },
    ],
)
async def test_experience_rejects_bad_own_hint_before_any_batch(
    item: dict[str, object],
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError):
        await executor.apply(
            "novel-1", "user-1", {"characterExperiences": [item]}
        )

    assert lore.calls == []


@pytest.mark.asyncio
async def test_experiences_use_one_batch_and_forward_controls_separately() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    count = await executor.apply(
        "novel-1",
        "user-1",
        {
            "characterExperiences": [
                {
                    "action": "create",
                    "characterId": "character-1",
                    "clientRequestId": "artifact-experience-create",
                    "content": "新增经历",
                    "fieldChanges": [{"field": "content"}],
                },
                {
                    "action": "update",
                    "id": "experience-1",
                    "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                    "content": "更新经历",
                    "fieldChanges": [{"field": "content"}],
                },
                {
                    "action": "delete",
                    "id": "experience-2",
                    "expectedUpdatedAt": "2026-08-06T00:00:01Z",
                },
            ]
        },
    )

    assert count == 3
    assert len(lore.calls) == 1
    call = lore.calls[0]
    assert call[:3] == ("experience_batch", "novel-1", "user-1")
    mutations = call[3]
    assert [mutation.action for mutation in mutations] == ["create", "update", "delete"]
    assert mutations[0].character_id == "character-1"
    assert mutations[0].client_request_id == "artifact-experience-create"
    assert mutations[0].fields == {"content": "新增经历"}
    assert mutations[1].entity_id == "experience-1"
    assert mutations[1].expected_updated_at == datetime(2026, 8, 6, tzinfo=UTC)
    assert mutations[1].fields == {"content": "更新经历"}
    assert mutations[2].entity_id == "experience-2"
    assert mutations[2].expected_updated_at == datetime(2026, 8, 6, 0, 0, 1, tzinfo=UTC)
    for mutation in mutations:
        assert "clientRequestId" not in mutation.fields
        assert "expectedUpdatedAt" not in mutation.fields


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["content", "order"])
async def test_experience_update_rejects_null_required_fields(field: str) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="不能为 null"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "characterExperiences": [
                    {
                        "action": "update",
                        "id": "experience-1",
                        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                        field: None,
                    }
                ]
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        {"action": "update", "id": "experience-1", "content": 1},
        {"action": "update", "id": "experience-1", "order": "1"},
        {"action": "update", "id": "experience-1", "chapterId": 1},
    ],
)
async def test_experience_update_rejects_wrong_business_field_types(item: dict) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())
    item["expectedUpdatedAt"] = "2026-08-06T00:00:00Z"

    with pytest.raises(ValueError, match="字段类型无效"):
        await executor.apply(
            "novel-1", "user-1", {"characterExperiences": [item]}
        )

    assert lore.calls == []


@pytest.mark.asyncio
async def test_character_experiences_section_must_be_an_array() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="必须是数组"):
        await executor.apply(
            "novel-1", "user-1", {"characterExperiences": {"action": "delete"}}
        )

    assert lore.calls == []


@pytest.mark.asyncio
async def test_entity_section_shape_is_checked_before_valid_experience_write() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="items 必须是数组"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": {"action": "create", "name": "错误结构"},
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("section", "item"),
    [
        (
            "glossaries",
            {
                "action": "create",
                "clientRequestId": "invalid-glossary-create",
                "term": "缺少释义",
            },
        ),
        (
            "items",
            {
                "action": "create",
                "clientRequestId": "invalid-item-create",
                "name": 1,
            },
        ),
        (
            "items",
            {
                "action": "update",
                "id": "item-1",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                "name": 1,
            },
        ),
        (
            "items",
            {
                "action": "update",
                "id": "item-1",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            },
        ),
        (
            "items",
            {
                "action": "delete",
                "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            },
        ),
    ],
)
async def test_entity_business_contracts_are_checked_before_any_write(
    section: str, item: dict
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                section: [item],
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("section", "id_field", "name_field"),
    [
        ("characters", "characterId", "name"),
        ("locations", "locationId", "name"),
        ("items", "itemId", "name"),
        ("factions", "factionId", "name"),
        ("glossaries", "glossaryId", "term"),
        ("items", "id", "name"),
    ],
)
@pytest.mark.parametrize("invalid_id", [123, ""])
async def test_delete_rejects_every_invalid_id_hint_before_any_batch(
    section: str,
    id_field: str,
    name_field: str,
    invalid_id: object,
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="标识必须是非空字符串"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                section: [
                    {
                        "action": "delete",
                        id_field: invalid_id,
                        name_field: "合法名称",
                        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                    }
                ],
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("extra_field", "value"),
    [
        ("name", ""),
        ("characterName", 123),
        ("referenceId", 123),
        ("nodeId", "node-1"),
        ("nodeTitle", "节点"),
        ("chapterTitle", "章节"),
    ],
)
async def test_item_delete_rejects_bad_or_foreign_hint_before_any_batch(
    extra_field: str, value: object
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [
                    {
                        "action": "delete",
                        "id": "item-1",
                        extra_field: value,
                        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                    }
                ],
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("section", "own_id", "foreign_hint"),
    [
        ("characters", "characterId", "itemId"),
        ("locations", "locationId", "characterId"),
        ("items", "itemId", "locationId"),
        ("factions", "factionId", "glossaryId"),
        ("glossaries", "glossaryId", "factionId"),
    ],
)
async def test_delete_rejects_correctly_typed_cross_section_hint_before_any_batch(
    section: str, own_id: str, foreign_hint: str
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="无法持久化字段"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                section: [
                    {
                        "action": "delete",
                        own_id: "entity-1",
                        foreign_hint: "foreign-entity-1",
                        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                    }
                ],
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        {
            "action": "create",
            "clientRequestId": "valid-item-create",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            "name": "信物",
        },
        {
            "action": "update",
            "clientRequestId": "valid-item-update",
            "expectedUpdatedAt": "2026-08-06T00:00:00Z",
            "id": "item-1",
            "description": "不应写入",
        },
    ],
)
async def test_entity_action_rejects_control_from_another_action_before_any_batch(
    item: dict[str, object],
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="无法持久化字段"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [item],
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("id_field", ["id", "itemId"])
@pytest.mark.parametrize("invalid_id", [123, ""])
async def test_update_rejects_invalid_id_without_valid_name_before_any_batch(
    id_field: str, invalid_id: object
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [
                    {
                        "action": "update",
                        id_field: invalid_id,
                        "description": "不应写入",
                        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                    }
                ],
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
async def test_update_rejects_empty_id_even_with_valid_name_before_any_batch() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="标识必须是非空字符串"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "items": [
                    {
                        "action": "update",
                        "id": "",
                        "name": "信物",
                        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                    }
                ]
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("section", "invalid_field"),
    [
        ("characters", {"aliases": 1}),
        ("locations", {"climate": 1}),
        ("items", {"name": 1}),
        ("factions", {"baseId": 1}),
        ("glossaries", {"definition": 1}),
    ],
)
async def test_delete_rejects_invalid_business_fields_before_any_batch(
    section: str, invalid_field: dict[str, object]
) -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                section: [
                    {
                        "action": "delete",
                        "id": "entity-1",
                        "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                        **invalid_field,
                    }
                ],
                "characterExperiences": [
                    {
                        "action": "create",
                        "characterId": "character-1",
                        "clientRequestId": "valid-experience-create",
                        "content": "不应写入",
                    }
                ],
            },
        )

    assert lore.calls == []


@pytest.mark.asyncio
async def test_entity_create_keeps_field_changes_as_compatible_control() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    count = await executor.apply(
        "novel-1",
        "user-1",
        {
            "items": [
                {
                    "action": "create",
                    "clientRequestId": "valid-item-create",
                    "name": "信物",
                    "fieldChanges": [{"field": "name"}],
                }
            ]
        },
    )

    assert count == 1
    mutation = lore.calls[0][3][0]
    assert mutation.fields == {"name": "信物"}


@pytest.mark.asyncio
async def test_delete_mutation_discards_valid_attached_business_fields() -> None:
    lore = FakeLore()
    executor = AgentUpdatesExecutor(lore, FakeOutlines(), FakeReferences())

    count = await executor.apply(
        "novel-1",
        "user-1",
        {
            "items": [
                {
                    "action": "delete",
                    "id": "item-1",
                    "name": "仅用于严格预检",
                    "expectedUpdatedAt": "2026-08-06T00:00:00Z",
                }
            ]
        },
    )

    assert count == 1
    mutation = lore.calls[0][3][0]
    assert mutation.entity_id == "item-1"
    assert mutation.fields == {}


@pytest.mark.asyncio
async def test_replace_outline_tree_uses_single_repository_operation() -> None:
    outlines = FakeOutlines()
    executor = AgentUpdatesExecutor(FakeLore(), outlines, FakeReferences())
    adjustments = [
        {
            "action": "create",
            "clientKey": "stage-1",
            "kind": "stage",
            "title": "第一卷",
            "chapterStartOrder": 1,
            "chapterEndOrder": 20,
        }
    ]

    count = await executor.apply(
        "novel-1",
        "user-1",
        {"outlineTreeMode": "replace", "outlineAdjustments": adjustments},
    )

    assert count == 1
    assert outlines.replaced == adjustments


@pytest.mark.asyncio
async def test_outline_content_forwards_expected_updated_at() -> None:
    outlines = FakeOutlines()
    executor = AgentUpdatesExecutor(FakeLore(), outlines, FakeReferences())
    expected = datetime(2026, 7, 30, tzinfo=UTC)

    count = await executor.apply(
        "novel-1",
        "user-1",
        {"outlineContent": "候选大纲"},
        expected_outline_updated_at=expected,
    )

    assert count == 1
    assert outlines.outline_write == (
        "novel-1",
        "user-1",
        "候选大纲",
        expected,
    )


@pytest.mark.asyncio
async def test_unpersistable_update_field_is_rejected_explicitly() -> None:
    executor = AgentUpdatesExecutor(FakeLore(), FakeOutlines(), FakeReferences())

    with pytest.raises(ValueError, match="payoffNote"):
        await executor.apply(
            "novel-1",
            "user-1",
            {
                "foreshadowing": [
                    {
                        "action": "payoff",
                        "id": "f-1",
                        "name": "伏笔",
                        "payoffNote": "数据库没有对应字段",
                    }
                ]
            },
        )
