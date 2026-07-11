from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import Chapter, Foreshadowing, Novel, Outline, OutlineNode, PlotProgress
from ..errors import ApiError
from .validation import OutlineNodeSnapshot, validate_outline_node


def _dict(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in value.__table__.columns:
        if column.key == "novelId":
            continue
        item = getattr(value, column.key)
        if isinstance(item, datetime):
            item = item.replace(tzinfo=UTC) if item.tzinfo is None else item.astimezone(UTC)
        result[column.key] = item
    return result


class OutlineRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_nodes(self, novel_id: str, user_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            values = (
                await session.scalars(
                    select(OutlineNode)
                    .where(OutlineNode.novelId == novel_id)
                    .order_by(
                        OutlineNode.order.asc(), OutlineNode.createdAt.asc(), OutlineNode.id.asc()
                    )
                )
            ).all()
        return [_dict(value) for value in values]

    async def list_foreshadowings(self, novel_id: str, user_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            await self._require_owner(session, novel_id, user_id)
            values = (
                await session.scalars(
                    select(Foreshadowing)
                    .where(Foreshadowing.novelId == novel_id)
                    .order_by(Foreshadowing.createdAt.asc(), Foreshadowing.id.asc())
                )
            ).all()
        return [_dict(value) for value in values]

    async def create_foreshadowing(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                value = Foreshadowing(novelId=novel_id, **fields)
                session.add(value)
                await session.flush()
                result = _dict(value)
        return result

    async def update_foreshadowing(
        self,
        novel_id: str,
        user_id: str,
        foreshadowing_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(Foreshadowing)
                        .where(
                            Foreshadowing.id == foreshadowing_id,
                            Foreshadowing.novelId == novel_id,
                        )
                        .values(**fields)
                    ),
                )
                if outcome.rowcount != 1:
                    raise self._foreshadowing_not_found()
                value = await session.scalar(
                    select(Foreshadowing).where(Foreshadowing.id == foreshadowing_id)
                )
                result = _dict(value)
        return result

    async def delete_foreshadowing(
        self, novel_id: str, user_id: str, foreshadowing_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        delete(Foreshadowing).where(
                            Foreshadowing.id == foreshadowing_id,
                            Foreshadowing.novelId == novel_id,
                        )
                    ),
                )
                if outcome.rowcount != 1:
                    raise self._foreshadowing_not_found()

    async def upsert_outline(self, novel_id: str, user_id: str, content: str) -> dict[str, Any]:
        return await self._upsert_singleton(novel_id, user_id, Outline, {"content": content})

    async def upsert_plot(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._upsert_singleton(novel_id, user_id, PlotProgress, fields)

    async def create_node(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                await self._validate_links(session, novel_id, fields)
                snapshots = await self._snapshots(session, novel_id)
                candidate = self._snapshot("待创建", fields)
                validate_outline_node(candidate, snapshots, title=cast(str, fields["title"]))
                value = OutlineNode(novelId=novel_id, **fields)
                session.add(value)
                await session.flush()
                result = _dict(value)
        return result

    async def update_node(
        self, novel_id: str, user_id: str, node_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                current = await session.scalar(
                    select(OutlineNode).where(
                        OutlineNode.id == node_id, OutlineNode.novelId == novel_id
                    )
                )
                if current is None:
                    raise self._not_found()
                merged = {**_dict(current), **fields}
                await self._validate_links(session, novel_id, merged)
                snapshots = await self._snapshots(session, novel_id)
                validate_outline_node(
                    self._snapshot(node_id, merged), snapshots, title=cast(str, merged["title"])
                )
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(OutlineNode)
                        .where(OutlineNode.id == node_id, OutlineNode.novelId == novel_id)
                        .values(**fields)
                    ),
                )
                if outcome.rowcount != 1:
                    raise self._not_found()
                updated = await session.scalar(select(OutlineNode).where(OutlineNode.id == node_id))
                result = _dict(updated)
        return result

    async def delete_node(self, novel_id: str, user_id: str, node_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                child = await session.scalar(
                    select(OutlineNode.id).where(OutlineNode.parentId == node_id).limit(1)
                )
                if child is not None:
                    raise ApiError(
                        status_code=409,
                        code="OUTLINE_NODE_HAS_CHILDREN",
                        message="大纲节点仍有子节点，不能删除",
                    )
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        delete(OutlineNode).where(
                            OutlineNode.id == node_id, OutlineNode.novelId == novel_id
                        )
                    ),
                )
                if outcome.rowcount != 1:
                    raise self._not_found()

    async def replace_nodes(
        self, novel_id: str, user_id: str, adjustments: list[dict[str, Any]]
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                await self._lock_novel(session, novel_id)
                if any(item.get("action") != "create" for item in adjustments):
                    raise ApiError(
                        status_code=422,
                        code="OUTLINE_REPLACE_CREATE_ONLY",
                        message="整树替换只能包含新建节点",
                    )
                await session.execute(delete(OutlineNode).where(OutlineNode.novelId == novel_id))
                snapshots: list[OutlineNodeSnapshot] = []
                client_ids: dict[str, str] = {}
                for order, adjustment in enumerate(adjustments):
                    parent_id = adjustment.get("parentId")
                    parent_key = adjustment.get("parentKey")
                    if isinstance(parent_key, str):
                        parent_id = client_ids.get(parent_key)
                        if parent_id is None:
                            raise ApiError(
                                status_code=422,
                                code="OUTLINE_PARENT_KEY_NOT_FOUND",
                                message="大纲父节点临时标识无法解析",
                            )
                    title = adjustment.get("title") or adjustment.get("nodeTitle")
                    kind = adjustment.get("kind")
                    if not isinstance(title, str) or not isinstance(kind, str):
                        raise ApiError(
                            status_code=422,
                            code="OUTLINE_REPLACE_INVALID",
                            message="整树替换节点缺少标题或类型",
                        )
                    fields = {
                        key: adjustment[key]
                        for key in (
                            "content",
                            "status",
                            "estimatedWordCount",
                            "actualWordCount",
                            "chapterStartOrder",
                            "chapterEndOrder",
                        )
                        if key in adjustment
                    }
                    fields.update(
                        {
                            "title": title,
                            "kind": kind,
                            "parentId": parent_id,
                            "order": order,
                        }
                    )
                    candidate = OutlineNodeSnapshot(
                        id=f"待创建-{order}",
                        kind=kind,
                        parent_id=cast(str | None, parent_id),
                        start=cast(int | None, adjustment.get("chapterStartOrder")),
                        end=cast(int | None, adjustment.get("chapterEndOrder")),
                    )
                    validate_outline_node(candidate, snapshots, title=title)
                    value = OutlineNode(novelId=novel_id, **fields)
                    session.add(value)
                    await session.flush()
                    snapshots.append(
                        OutlineNodeSnapshot(
                            id=value.id,
                            kind=value.kind,
                            parent_id=value.parentId,
                            start=value.chapterStartOrder,
                            end=value.chapterEndOrder,
                        )
                    )
                    client_key = adjustment.get("clientKey")
                    if isinstance(client_key, str):
                        if client_key in client_ids:
                            raise ApiError(
                                status_code=422,
                                code="OUTLINE_CLIENT_KEY_DUPLICATE",
                                message="大纲节点临时标识重复",
                            )
                        client_ids[client_key] = value.id

    async def _upsert_singleton(
        self,
        novel_id: str,
        user_id: str,
        model: type[Any],
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._session_factory() as session:
            async with session.begin():
                await self._require_owner(session, novel_id, user_id)
                statement = (
                    pg_insert(model)
                    .values(novelId=novel_id, **fields)
                    .on_conflict_do_update(index_elements=[model.novelId], set_=fields)
                    .returning(model)
                )
                value = (await session.scalars(statement)).one()
                return _dict(value)

    @staticmethod
    async def _require_owner(session: AsyncSession, novel_id: str, user_id: str) -> None:
        owner = await session.scalar(select(Novel.userId).where(Novel.id == novel_id))
        if owner is None or owner != user_id:
            raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")

    @staticmethod
    async def _lock_novel(session: AsyncSession, novel_id: str) -> None:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            key = int.from_bytes(hashlib.sha256(novel_id.encode()).digest()[:8], "big", signed=True)
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    @staticmethod
    async def _validate_links(session: AsyncSession, novel_id: str, fields: dict[str, Any]) -> None:
        chapter_id = fields.get("linkedChapterId")
        if chapter_id is not None:
            linked_novel = await session.scalar(
                select(Chapter.novelId).where(Chapter.id == chapter_id)
            )
            if linked_novel != novel_id:
                raise ApiError(
                    status_code=422,
                    code="OUTLINE_CHAPTER_CROSS_NOVEL",
                    message="关联章节不属于当前小说",
                )

    @staticmethod
    async def _snapshots(session: AsyncSession, novel_id: str) -> list[OutlineNodeSnapshot]:
        values = (
            await session.scalars(select(OutlineNode).where(OutlineNode.novelId == novel_id))
        ).all()
        return [
            OutlineNodeSnapshot(
                id=value.id,
                kind=value.kind,
                parent_id=value.parentId,
                start=value.chapterStartOrder,
                end=value.chapterEndOrder,
            )
            for value in values
        ]

    @staticmethod
    def _snapshot(node_id: str, fields: dict[str, Any]) -> OutlineNodeSnapshot:
        return OutlineNodeSnapshot(
            id=node_id,
            kind=cast(str, fields["kind"]),
            parent_id=cast(str | None, fields.get("parentId")),
            start=cast(int | None, fields.get("chapterStartOrder")),
            end=cast(int | None, fields.get("chapterEndOrder")),
        )

    @staticmethod
    def _not_found() -> ApiError:
        return ApiError(status_code=404, code="OUTLINE_NODE_NOT_FOUND", message="大纲节点不存在")

    @staticmethod
    def _foreshadowing_not_found() -> ApiError:
        return ApiError(status_code=404, code="FORESHADOWING_NOT_FOUND", message="伏笔不存在")
