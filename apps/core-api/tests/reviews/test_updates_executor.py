import pytest
from inkforge_core.reviews.updates import AgentUpdatesExecutor


class FakeLore:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def list_entities(self, novel_id: str, user_id: str, kind: str):
        del novel_id, user_id
        if kind == "characters":
            return [{"id": "character-1", "name": "甲"}]
        return []

    async def create_entity(self, novel_id: str, user_id: str, kind: str, fields: dict):
        self.calls.append(("create", novel_id, user_id, kind, fields))

    async def update_entity(
        self, novel_id: str, user_id: str, kind: str, entity_id: str, fields: dict
    ):
        self.calls.append(("update", novel_id, user_id, kind, entity_id, fields))

    async def delete_entity(self, novel_id: str, user_id: str, kind: str, entity_id: str):
        self.calls.append(("delete", novel_id, user_id, kind, entity_id))

    async def upsert_content(self, novel_id: str, user_id: str, kind: str, content: str):
        self.calls.append(("content", novel_id, user_id, kind, content))


class FakeOutlines:
    def __init__(self) -> None:
        self.replaced: list[dict] | None = None

    async def replace_nodes(self, novel_id: str, user_id: str, adjustments: list[dict]):
        del novel_id, user_id
        self.replaced = adjustments


class FakeReferences:
    pass


@pytest.mark.asyncio
async def test_executor_sanitizes_control_fields_and_resolves_existing_name() -> None:
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
                    "fieldChanges": [{"field": "personality"}],
                }
            ],
            "worldSetting": "完整世界设定",
        },
    )

    assert count == 2
    assert lore.calls == [
        (
            "update",
            "novel-1",
            "user-1",
            "characters",
            "character-1",
            {"name": "甲", "personality": "谨慎"},
        ),
        ("content", "novel-1", "user-1", "world-setting", "完整世界设定"),
    ]


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
