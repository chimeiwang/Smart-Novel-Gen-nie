"""旧视频规划与章节改编共用的长篇设定冻结器。"""

from __future__ import annotations

import hashlib
import json

from inkforge_contracts.video import (
    CharacterSettingSnapshot,
    ItemSettingSnapshot,
    LocationSettingSnapshot,
    LongSerialSettingSnapshot,
    RelationshipSettingSnapshot,
    SettingSnapshotEntry,
    WorldSettingSnapshot,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Character, CharacterRelation, Item, Location, WorldSetting


async def build_long_serial_setting_snapshot(
    session: AsyncSession,
    novel_id: str,
) -> LongSerialSettingSnapshot:
    """按类型和主键冻结长篇资料，并让关系与所有者引用保持闭合。"""

    # 创建任务的事务锁定设定行，避免指纹由不同时刻的混合状态组成。
    characters = list(
        (
            await session.scalars(
                select(Character)
                .where(Character.novelId == novel_id)
                .order_by(Character.id)
                .with_for_update()
            )
        ).all()
    )
    character_ids = {character.id for character in characters}
    character_names = {character.id: character.name for character in characters}
    relations: list[CharacterRelation] = []
    if character_ids:
        relations = list(
            (
                await session.scalars(
                    select(CharacterRelation)
                    .where(
                        CharacterRelation.characterId.in_(character_ids),
                        CharacterRelation.targetId.in_(character_ids),
                    )
                    .order_by(CharacterRelation.id)
                    .with_for_update()
                )
            ).all()
        )
    locations = list(
        (
            await session.scalars(
                select(Location)
                .where(Location.novelId == novel_id)
                .order_by(Location.id)
                .with_for_update()
            )
        ).all()
    )
    location_ids = {location.id for location in locations}
    items = list(
        (
            await session.scalars(
                select(Item).where(Item.novelId == novel_id).order_by(Item.id).with_for_update()
            )
        ).all()
    )
    world_setting = await session.scalar(
        select(WorldSetting).where(WorldSetting.novelId == novel_id).with_for_update()
    )
    entries: list[SettingSnapshotEntry] = []
    for character in characters:
        content: dict[str, object] = {
            "kind": "character",
            "id": character.id,
            "name": character.name,
            "aliases": _parse_aliases(character.aliases),
            "appearance": character.appearance,
            "identity": character.identity,
        }
        entries.append(
            CharacterSettingSnapshot.model_validate(
                {**content, "contentHash": setting_entry_content_hash(content)}
            )
        )
    for relation in relations:
        content = {
            "kind": "relationship",
            "id": relation.id,
            "name": (
                f"{character_names[relation.characterId]} → "
                f"{character_names[relation.targetId]}"
            ),
            "sourceCharacterId": relation.characterId,
            "targetCharacterId": relation.targetId,
            "relationType": relation.relationType,
            "description": relation.description,
        }
        entries.append(
            RelationshipSettingSnapshot.model_validate(
                {**content, "contentHash": setting_entry_content_hash(content)}
            )
        )
    for location in locations:
        content = {
            "kind": "location",
            "id": location.id,
            "name": location.name,
            "aliases": _parse_aliases(location.aliases),
            "locationType": location.type,
            "parentLocationId": (
                location.parentId if location.parentId in location_ids else None
            ),
            "climate": location.climate,
            "culture": location.culture,
            "description": location.description,
        }
        entries.append(
            LocationSettingSnapshot.model_validate(
                {**content, "contentHash": setting_entry_content_hash(content)}
            )
        )
    for item in items:
        content = {
            "kind": "item",
            "id": item.id,
            "name": item.name,
            "aliases": _parse_aliases(item.aliases),
            "itemType": item.type,
            "ownerCharacterId": item.ownerId if item.ownerId in character_ids else None,
            "description": item.description,
        }
        entries.append(
            ItemSettingSnapshot.model_validate(
                {**content, "contentHash": setting_entry_content_hash(content)}
            )
        )
    if world_setting is not None and world_setting.content:
        content = {
            "kind": "world_setting",
            "id": world_setting.id,
            "name": "世界设定",
            "content": world_setting.content,
        }
        entries.append(
            WorldSettingSnapshot.model_validate(
                {**content, "contentHash": setting_entry_content_hash(content)}
            )
        )
    return LongSerialSettingSnapshot.from_entries(entries)


def setting_entry_content_hash(content: dict[str, object]) -> str:
    """对不含 contentHash 的完整类型化投影计算稳定内容哈希。"""
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_aliases(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
