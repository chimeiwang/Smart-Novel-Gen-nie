from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import Chapter, Novel, WritingMessage, WritingSession, WritingTask
from ..errors import ApiError
from .recovery import TaskCandidate
from .schemas import CreateMessageRequest, UpdateWritingSessionRequest


class WritingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_session(
        self, user_id: str, novel_id: str, chapter_id: str, title: str | None
    ) -> dict[str, object]:
        async with self._session_factory() as session:
            async with session.begin():
                await _require_chapter(session, user_id, novel_id, chapter_id)
                record = WritingSession(
                    novelId=novel_id,
                    chapterId=chapter_id,
                    title=title,
                    phase="idle",
                )
                session.add(record)
                await session.flush()
            return _session_dict(record)

    async def list_sessions(
        self, user_id: str, novel_id: str, chapter_id: str | None
    ) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            await _require_novel(session, user_id, novel_id)
            statement = select(WritingSession).where(WritingSession.novelId == novel_id)
            if chapter_id is not None:
                statement = statement.where(WritingSession.chapterId == chapter_id)
            records = list(
                (
                    await session.execute(
                        statement.order_by(
                            WritingSession.updatedAt.desc(), WritingSession.id.asc()
                        )
                    )
                ).scalars()
            )
            session_ids = [record.id for record in records]
            counts_by_session: dict[str, int] = {}
            last_by_session: dict[str, dict[str, str | None]] = {}
            if session_ids:
                count_rows = (
                    await session.execute(
                        select(
                            WritingMessage.sessionId.label("sessionId"),
                            func.count().label("messageCount"),
                        )
                        .where(WritingMessage.sessionId.in_(session_ids))
                        .group_by(WritingMessage.sessionId)
                    )
                ).all()
                counts_by_session = {
                    row.sessionId: int(row.messageCount) for row in count_rows
                }
                ranked_messages = (
                    select(
                        WritingMessage.sessionId.label("sessionId"),
                        WritingMessage.content.label("content"),
                        WritingMessage.role.label("role"),
                        WritingMessage.agentId.label("agentId"),
                        func.row_number()
                        .over(
                            partition_by=WritingMessage.sessionId,
                            order_by=(
                                WritingMessage.createdAt.desc(),
                                WritingMessage.id.desc(),
                            ),
                        )
                        .label("messageRank"),
                    )
                    .where(WritingMessage.sessionId.in_(session_ids))
                    .subquery()
                )
                last_rows = (
                    await session.execute(
                        select(
                            ranked_messages.c.sessionId,
                            ranked_messages.c.content,
                            ranked_messages.c.role,
                            ranked_messages.c.agentId,
                        ).where(ranked_messages.c.messageRank == 1)
                    )
                ).all()
                last_by_session = {
                    row.sessionId: {
                        "content": row.content,
                        "role": row.role,
                        "agentId": row.agentId,
                    }
                    for row in last_rows
                }
            result: list[dict[str, object]] = []
            for record in records:
                value = _session_dict(record)
                value["messageCount"] = counts_by_session.get(record.id, 0)
                value["lastMessage"] = last_by_session.get(record.id)
                result.append(value)
            return result

    async def get_session_detail(
        self, user_id: str, session_id: str
    ) -> tuple[dict[str, object], list[TaskCandidate]]:
        async with self._session_factory() as session:
            record = await _require_session(session, user_id, session_id)
            messages = (
                await session.execute(
                    select(WritingMessage)
                    .where(WritingMessage.sessionId == session_id)
                    .order_by(WritingMessage.createdAt, WritingMessage.id)
                )
            ).scalars()
            tasks = (
                await session.execute(
                    select(WritingTask)
                    .where(WritingTask.writingSessionId == session_id)
                    .order_by(WritingTask.updatedAt.desc())
                )
            ).scalars()
            value = _session_dict(record)
            value["messages"] = [_message_dict(item) for item in messages]
            candidates = [
                TaskCandidate(
                    id=item.id,
                    phase=item.phase,
                    updated_at=item.updatedAt,
                    generated_content=item.generatedContent,
                    graph_state_json=item.graphStateJson,
                )
                for item in tasks
            ]
            return value, candidates

    async def update_session(
        self, user_id: str, session_id: str, request: UpdateWritingSessionRequest
    ) -> dict[str, object]:
        async with self._session_factory() as session:
            async with session.begin():
                record = await _require_session(session, user_id, session_id)
                changes = request.model_dump(exclude_none=True)
                for key, value in changes.items():
                    setattr(record, key, value)
                record.updatedAt = utc_now()
                await session.flush()
            return _session_dict(record)

    async def delete_session(self, user_id: str, session_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await _require_session(session, user_id, session_id)
                await session.execute(delete(WritingSession).where(WritingSession.id == session_id))

    async def add_message(
        self, user_id: str, session_id: str, request: CreateMessageRequest
    ) -> dict[str, object]:
        async with self._session_factory() as session:
            async with session.begin():
                await _require_session(session, user_id, session_id)
                record = WritingMessage(
                    sessionId=session_id,
                    role=request.role,
                    agentId=request.agentId,
                    content=request.content,
                    intent=request.intent,
                    metadata_=(
                        json.dumps(request.metadata, ensure_ascii=False)
                        if request.metadata is not None
                        else None
                    ),
                    parentId=request.parentId,
                )
                session.add(record)
                await session.flush()
                await session.execute(
                    update(WritingSession)
                    .where(WritingSession.id == session_id)
                    .values(updatedAt=utc_now())
                )
            return _message_dict(record)


async def _require_novel(session: AsyncSession, user_id: str, novel_id: str) -> None:
    found = await session.scalar(
        select(Novel.id).where(Novel.id == novel_id, Novel.userId == user_id)
    )
    if found is None:
        raise ApiError(status_code=403, code="NOVEL_FORBIDDEN", message="无权访问该小说")


async def _require_chapter(
    session: AsyncSession, user_id: str, novel_id: str, chapter_id: str
) -> None:
    found = await session.scalar(
        select(Chapter.id)
        .join(Novel, Novel.id == Chapter.novelId)
        .where(
            Chapter.id == chapter_id,
            Chapter.novelId == novel_id,
            Novel.userId == user_id,
        )
    )
    if found is None:
        raise ApiError(
            status_code=404, code="CHAPTER_NOT_FOUND", message="章节不存在或不属于该小说"
        )


async def _require_session(session: AsyncSession, user_id: str, session_id: str) -> WritingSession:
    record = (
        await session.execute(
            select(WritingSession)
            .join(Novel, Novel.id == WritingSession.novelId)
            .where(WritingSession.id == session_id, Novel.userId == user_id)
        )
    ).scalar_one_or_none()
    if record is None:
        raise ApiError(
            status_code=403, code="WRITING_SESSION_FORBIDDEN", message="无权访问该写作会话"
        )
    return record


def _session_dict(record: WritingSession) -> dict[str, object]:
    return {
        "id": record.id,
        "novelId": record.novelId,
        "chapterId": record.chapterId,
        "title": record.title,
        "phase": record.phase,
        "createdAt": record.createdAt,
        "updatedAt": record.updatedAt,
    }


def _message_dict(record: WritingMessage) -> dict[str, object]:
    metadata: Any = None
    if record.metadata_ is not None:
        try:
            metadata = json.loads(record.metadata_)
        except json.JSONDecodeError:
            metadata = None
    return {
        "id": record.id,
        "sessionId": record.sessionId,
        "role": record.role,
        "agentId": record.agentId,
        "content": record.content,
        "intent": record.intent,
        "metadata": metadata,
        "parentId": record.parentId,
        "createdAt": record.createdAt,
    }
